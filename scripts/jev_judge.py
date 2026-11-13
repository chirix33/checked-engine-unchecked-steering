"""TypeSafe Jev as an answer-level trust judge (D30; Ashraf, 2026-11-12). A logged addition after the freeze.

Jev is a hosted "System One" decision model: it reads a `state` and returns, for a yes/no ("noul") question, the
probability of yes. It writes no text and has no tools, so it is an answer-level judge only (no ReAct, no reason).

Fair inputs, by construction (manifests/jev_judge_design.md):
- Jev sees exactly the text the answer-level LLM judges saw for the same row, minus their output-format lines
  (VERDICT/CONFIDENCE/REASON), which do not apply to a model that returns a probability. The view comes from the
  frozen `judges.Rows.view` and `judges.make_view`; the text from the frozen `judges.base_blocks` and
  `judges._answer_task`. A run checks first that `judges.py` still has its freeze hash and its recorded prompt hash.
  Nothing is added: no criteria, no hints, no decomposition into sub-questions, no examples.
- One noul question whose wording restates the LLM judges' task sentence. It was fixed before any call and is never
  changed on results (dev or test).
- The rows are the frozen D27 subset `answer_haiku` (3,000 rows, which contain the shared 150), read with its sha256.
  Rows without an answer are not judged (rule A), as for every judge.
- The answer comes from the main run's own row only; a row that would need recomputing stops the run.
- Fixed model version `jev-1.14.0` (never an alias); a reply naming any other version stops the run.
- Long context: a request is first sent with the default limits; only if the service answers 400
  `max_tokens_exceeded` is the same request resent once with the long-context header. The rule depends on input
  length only, never on labels; each row records which mode answered.
- Confidence is 100 x the noul probability, unrounded (the model's own resolution). The verdict is TRUST when the
  probability is at least 0.5: the probability that the answer is right, the same quantity the LLM judges report.
  No threshold, temperature or calibration is fitted on any labels.

Failure handling, as in `judges.py`:
- DECLINE at confidence 0, with the kind in `failure`: a 200 reply that cannot be read (not JSON, no answer, a value
  outside [0, 1]) is `unparsable`; a request still too long with long context is `too_long`.
- Retried with backoff, then raised (never a verdict; the run is resumable): rate limits, overload, any 5xx, network
  and protocol errors.
- The run stops: authentication errors, validation errors, any other 4xx, a redirect, or a reply from another model
  version.

The API key is read from `.env` (TYPESAFE_API_KEY). It is sent only in the Authorization header, never follows a
redirect, and is masked in every error text before anything is logged, printed or raised.

The call ledger is `runs/judges_jev_ledger/calls_jev-1.14.0.jsonl`: outside `runs/build_test_*`, so Jev's spend never
counts against the runner's shared Ollama stop (review, 2026-11-12). Each judgment row also carries its own cost.

Evaluation side only: no gold, binding, label or reference is read. Rows and views come from `judges.py`.

Usage:
  python -X utf8 scripts/jev_judge.py <root> wf_test,wf_policy,ml_test --out runs/judges_main_v1/main_answer_jev
        --subsets manifests/judge_subsets_main_v1.json --subset-name answer_haiku [--max-usd 6.0] [--shard K/N]
  python -X utf8 scripts/jev_judge.py <root> ml_dev,wf_dev --out runs/judges_jev_devcheck_v1 --rows 4 --max-usd 0.05
        the dev path check: the first rows with an answer, in a fixed hash order (no test rows, no accuracy reading)
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
sys.dont_write_bytecode = True

import judges as J   # noqa: E402

MODEL = "jev-1.14.0"
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
USD_PER_INPUT_TOKEN = 0.042 / 1_000_000       # output tokens are free (docs.typesafe.ai/models, 2026-11-12)
KEY_NAME = "TYPESAFE_API_KEY"
LONG_HEADER = "TypeSafe-Danger-Zone-Long-Context"
QUESTION_ID = "answer_right"                  # the id is not sent to the model (docs: primitives/noul)
INSTRUCTIONS = "Is the program's answer with the change exactly right for the question?"
TRUST_AT = 0.5
PROMPT_VERSION = "jev-v1"
# The frozen answer-level prompt this judge must reproduce (judges.py at the freeze, D28; every main-run answer judge).
FROZEN_JUDGES_SHA256 = "ab971e9df2c1728a4f8e20034439e4a2cc1c4a528e37afd392783a698a4f4f81"
FROZEN_PROMPT_HASH = "ed45fe10bab7c96c"
PROMPT_HASH = hashlib.sha256("\x1e".join([J.PROMPT_HASH, MODEL, INSTRUCTIONS, QUESTION_ID, repr(TRUST_AT),
                                          "state=base_blocks+answer_task", "long_context=on_max_tokens_exceeded"]).encode("utf-8")).hexdigest()[:16]
RETRY_CODES = {408, 409, 425, 429, 529}       # plus every 5xx
RETRY_DELAYS = [2, 4, 8, 16, 32, 60, 60, 60]
TIMEOUT_S = 300
USER_AGENT = "trust-eval-client/1.0"


class ServiceError(Exception):
    """The service did not answer after the retries. Never a verdict; the run stops and can be resumed."""


class StopRun(Exception):
    """A configuration problem (key, request shape, model version, redirect). The run stops."""


def check_frozen_prompt(root: Path = ROOT):
    """Stop unless judges.py is the frozen file whose prompt every main-run answer judge used."""
    got = hashlib.sha256((root / "scripts" / "judges.py").read_bytes()).hexdigest()
    if got != FROZEN_JUDGES_SHA256 or J.PROMPT_HASH != FROZEN_PROMPT_HASH:
        raise StopRun(f"scripts/judges.py is not the frozen file (sha256 {got[:12]}…, prompt hash {J.PROMPT_HASH}); "
                      "Jev's input would no longer equal the LLM judges' input")


# ---------------------------------------------------------------- what Jev sees
def jev_state(view: J.View) -> str:
    """The answer-level LLM judge's prompt text for this row, without its output-format lines. Identical by
    construction: the same frozen blocks, joined as the client joins them (no separator)."""
    if view.question is None or view.request is None:
        raise ValueError("the answer-level judge needs the question and the interpreted request")
    blocks = J.base_blocks(view)
    return blocks[0]["text"] + blocks[1]["text"] + J._answer_task(view)


def jev_request(view: J.View) -> dict:
    return {"model": MODEL, "state": jev_state(view),
            "questions": {QUESTION_ID: {"type": "noul", "instructions": INSTRUCTIONS}}}


# ---------------------------------------------------------------- the call
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: urllib would copy the Authorization header to the new location."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def http_post(url: str, body: bytes, headers: dict, timeout: int = TIMEOUT_S):
    """(status, response text, headers). A redirect comes back as its 3xx status. Network and protocol failures are
    raised (OSError or http.client.HTTPException)."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers or {})


def _int(x) -> int:
    try:
        v = int(x)
        return v if v >= 0 else 0
    except (TypeError, ValueError):
        return 0


class JevClient:
    """One HTTP client with retries and a call ledger, in the form the other judges' ledgers use (`build`, `utc`,
    `usd`, `prompt_tokens`, `seconds`, `failed`)."""

    def __init__(self, key: str, ledger: Path, post=http_post, sleep=time.sleep, delays=RETRY_DELAYS):
        if not key:
            raise StopRun(f"{KEY_NAME} is not set in .env")
        self._key, self.ledger, self.post, self.sleep, self.delays = key, ledger, post, sleep, list(delays)
        self.build_id = None
        self._offset, self._usd = 0, []          # ledger bytes read so far; (build, usd) of every call read

    def mask(self, text: str) -> str:
        """Error text with the key, and any 8-character piece of it, replaced."""
        text = (text or "").replace(self._key, "[KEY]")
        k = self._key
        for i in range(0, max(len(k) - 7, 0)):
            piece = k[i:i + 8]
            if piece in text:
                text = text.replace(piece, "[KEY]")
        return text

    def _log(self, row: dict):
        J.append(self.ledger, {"build": self.build_id, "model": MODEL, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **row})

    def spent(self, prefix: str) -> float:
        """Spend of the calls whose build id starts with `prefix`, from the ledger as it is now: every process's calls
        (shards running side by side share one stop, as in judges.py). Only lines added since the last read are
        parsed; a half-written last line is left for the next read."""
        if self.ledger.exists():
            with self.ledger.open("rb") as f:
                f.seek(self._offset)
                data = f.read()
            end = data.rfind(b"\n") + 1
            for line in data[:end].splitlines():
                try:
                    c = json.loads(line.decode("utf-8"))
                except ValueError:
                    continue
                self._usd.append((str(c.get("build") or ""), c.get("usd") or 0.0))
            self._offset += end
        return sum(u for b, u in self._usd if b.startswith(prefix))

    def ask(self, request: dict, long_context: bool) -> tuple[int, object, str, list]:
        """(status, parsed body or None, masked text, calls). Retries busy, 5xx, network and protocol failures, then
        raises ServiceError."""
        body = json.dumps(request, ensure_ascii=False).encode("utf-8")
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json", "User-Agent": USER_AGENT}
        if long_context:
            headers[LONG_HEADER] = "true"
        calls = []
        for attempt in range(len(self.delays) + 1):
            t0 = time.time()
            try:
                status, raw, rh = self.post(ENDPOINT, body, headers)
            except (OSError, http.client.HTTPException) as e:
                status, raw, rh = None, f"{type(e).__name__}: {e}", {}
            except Exception as e:                    # e.g. a header value error: masked, then stop
                raise StopRun(self.mask(f"the request could not be sent: {type(e).__name__}: {e}")) from None
            secs = round(time.time() - t0, 3)
            try:
                parsed = json.loads(raw) if raw else None       # parsed from the raw body: masking never alters a reply
            except ValueError:
                parsed = None
            text = self.mask(raw)                               # only the masked copy is logged, recorded or raised
            ok = status == 200
            usage = parsed.get("usage") if ok and isinstance(parsed, dict) else None
            itok = _int(usage.get("input_tokens")) if isinstance(usage, dict) else 0
            otok = _int(usage.get("output_tokens")) if isinstance(usage, dict) else 0
            call = {"status": status, "long_context": long_context, "failed": not ok, "seconds": secs,
                    "prompt_tokens": itok, "output_tokens": otok, "usd": round(itok * USD_PER_INPUT_TOKEN, 8),
                    "error": None if ok else text[:300]}
            calls.append(call)
            self._log(call)
            if status is None or status in RETRY_CODES or 500 <= status <= 599:
                if attempt < len(self.delays):
                    wait = self.delays[attempt]
                    try:
                        wait = max(wait, float((rh or {}).get("retry-after") or (rh or {}).get("Retry-After") or 0))
                    except (TypeError, ValueError):
                        pass
                    self.sleep(min(wait, 300))
                    continue
                raise ServiceError(f"no answer after {len(calls)} tries; last: {status} {text[:200]}")
            return status, parsed, text, calls
        raise ServiceError("unreachable")


def too_long(status, parsed, text) -> bool:
    """A 400 that says the request is over the context length (`max_tokens_exceeded`)."""
    if status != 400:
        return False
    d = parsed.get("detail") if isinstance(parsed, dict) else None
    if isinstance(d, dict) and (d.get("error") == "max_tokens_exceeded" or d.get("type") == "max_tokens_exceeded" or d.get("code") == "max_tokens_exceeded"):
        return True
    return "max_tokens_exceeded" in (text or "")          # the documented marker, wherever the body puts it


def read_noul(parsed) -> float | None:
    """The noul probability, or None if the reply does not hold a valid one."""
    try:
        a = parsed["answers"][QUESTION_ID]
        if a.get("type") != "noul":
            return None
        p = a["noul"]
        if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0.0 <= p <= 1.0:
            return None
        return float(p)
    except (KeyError, TypeError, AttributeError):
        return None


def judge_jev(client: JevClient, view: J.View) -> dict:
    """One answer-level judgment. Same record shape as `judges._result`."""
    t0 = time.time()
    if view.answer_changed is None:
        return {"judge": "answer", "prompt_version": PROMPT_VERSION, "prompt_hash": PROMPT_HASH, "status": "no_answer", "verdict": None,
                "confidence": None, "reason": "the program produced no answer", "failure": None, "model_calls": 0, "usd": 0.0}
    req = jev_request(view)
    status, parsed, text, calls = client.ask(req, long_context=False)
    long_context = False
    if too_long(status, parsed, text):
        long_context = True
        status, parsed, text, more = client.ask(req, long_context=True)
        calls += more
    failure, p = None, None
    if status == 200:
        if isinstance(parsed, dict) and parsed.get("model") is not None and parsed.get("model") != MODEL:
            raise StopRun(f"the reply came from model {parsed.get('model')!r}, not {MODEL}")
        p = read_noul(parsed) if isinstance(parsed, dict) and parsed.get("model") == MODEL else None
        if p is None:
            failure = "unparsable"
    elif too_long(status, parsed, text):
        failure = "too_long"
    elif status in (401, 403):
        raise StopRun(f"authentication failed ({status}); check {KEY_NAME} in .env")
    elif status is not None and 300 <= status < 400:
        raise StopRun(f"the service answered with a redirect ({status}); it is not followed, so the key is never sent elsewhere")
    else:
        raise StopRun(f"the service refused the request: {status} {text[:300]}")
    good = [c for c in calls if not c["failed"]]
    cost = {"model_calls": len(calls), "failed_calls": len(calls) - len(good), "usd": round(sum(c["usd"] for c in calls), 8),
            "prompt_tokens": sum(c["prompt_tokens"] for c in good), "output_tokens": sum(c["output_tokens"] for c in good),
            "cache_read_tokens": 0, "cache_write_tokens": 0, "model_seconds": round(sum(c["seconds"] for c in calls), 3)}
    common = {"judge": "answer", "prompt_version": PROMPT_VERSION, "prompt_hash": PROMPT_HASH, "status": "judged",
              "wall_seconds": round(time.time() - t0, 3), "turns": 1, "finish": None, "long_context": long_context,
              "state_sha256": hashlib.sha256(req["state"].encode("utf-8")).hexdigest(), **cost}
    if failure:
        return {**common, "verdict": "DECLINE", "confidence": J.LOWEST_CONFIDENCE, "reason": f"judge failure: {failure}",
                "failure": failure, "inconsistent": False, "noul": None, "reply": (text or "")[:2000]}
    verdict = "TRUST" if p >= TRUST_AT else "DECLINE"
    conf = 100.0 * p
    return {**common, "verdict": verdict, "confidence": conf, "reason": f"noul={p}", "failure": None,
            "inconsistent": J.inconsistent(verdict, conf), "noul": p, "reply": client.mask(json.dumps(parsed.get("answers")))[:2000]}


# ---------------------------------------------------------------- the run
def ledger_path(root: Path) -> Path:
    return root / "runs" / "judges_jev_ledger" / f"calls_{MODEL}.jsonl"


def run(root: Path, qsets: tuple, out: Path, max_usd: float, subsets_file: Path | None, subset_name: str | None,
        n_rows: int | None = None, shard: tuple | None = None, client: JevClient | None = None, seed: int = 20261112):
    """Judge the rows of a frozen subset (main run), or the first `n_rows` rows with an answer (dev path check).
    Resumable: a row whose key is already in the output is skipped."""
    if (subsets_file is None) == (n_rows is None):
        raise SystemExit("give either --subsets with --subset-name (main run) or --rows (dev path check), not both")
    if subsets_file is not None and any(not s.endswith("_test") and s != "wf_policy" for s in qsets):
        raise SystemExit("a frozen subset is judged on the test sets only")
    if n_rows is not None and any(not s.endswith("_dev") for s in qsets):
        raise SystemExit("the path check (--rows) runs on dev sets only")
    if shard is not None and not (len(shard) == 2 and 0 <= shard[0] < shard[1]):
        raise SystemExit("--shard is K/N with 0 <= K < N")
    check_frozen_prompt(root)
    if client is None:
        import b0_build_test as bt
        env = bt.load_env(root / ".env")
        client = JevClient(env.get(KEY_NAME, ""), ledger_path(root))
    tag = f"judges/{out.name}/"
    sets = {s: J.Rows(root, s) for s in qsets}
    by_prog = {(s, p["name"]): p for s, rows in sets.items() for p in rows.programs}
    by_q = {(s, q["id"]): q for s, rows in sets.items() for q in rows.questions}

    def cand(s, p, q):
        return {"row_id": f"{p['name']}|{q['id']}", "set": s, "program": p["name"], "question": q["id"], "cohort": J.cohort_of(p["name"]),
                "process": p["process"], "family": q["family"], "doc": q["doc"], "scope": sets[s].scope(q)}

    frozen = None
    if subsets_file is not None:
        ids, frozen = J.load_subset(subsets_file, subset_name)
        cands, missing = [], []
        for rid in sorted(ids):
            s, prog, qid = rid.split("|")
            if (s, prog) in by_prog and (s, qid) in by_q:
                cands.append(cand(s, by_prog[(s, prog)], by_q[(s, qid)]))
            else:
                missing.append(rid)
        if missing:
            raise SystemExit(f"{len(missing)} rows of subset {subset_name} are not in sets {qsets} (first: {missing[0]})")
        cands.sort(key=lambda r: (r["set"], r["doc"], str(r["scope"]), r["program"], r["question"]))
    else:
        h = lambda x: hashlib.sha256(f"{seed}|{x}".encode()).hexdigest()   # noqa: E731
        cands = sorted((cand(s, p, q) for s, rows in sets.items() for p, q in rows.pairs()), key=lambda r: h(r["row_id"]))

    part = "" if shard is None else f".s{shard[0]}of{shard[1]}"
    if shard is not None:
        cands = [r for r in cands if J.shard_of(r["set"], r["doc"], r["scope"], shard[1]) == shard[0]]
    result_path = out / f"judgments_{MODEL}{part}.jsonl"
    have = {r["key"] for p in out.glob(f"judgments_{MODEL}*.jsonl") for r in J.read_jsonl(p) if "key" in r}
    judged = 0
    try:
        for r in cands:
            if n_rows is not None and judged >= n_rows:
                break
            key = f"answer|{MODEL}|{r['set']}|{r['row_id']}"
            if key in have:
                judged += 1
                continue
            s = client.spent(tag)
            if s >= max_usd:
                print(f"stopped: this run's spend {s:.4f} reached its limit of {max_usd:.2f}", flush=True)
                break
            try:
                view, info = sets[r["set"]].view(by_prog[(r["set"], r["program"])], by_q[(r["set"], r["question"])])
            except J.ViewError as e:
                view, info = None, {"view_error": str(e)[:300]}
            meta = {"key": key, "model": MODEL, "set": r["set"], "row_id": r["row_id"], "program": r["program"], "doc": r["doc"],
                    "scope": r["scope"], "question": r["question"], "cohort": r["cohort"], "process": r["process"], "family": r["family"]}
            if frozen is not None:
                meta.update({"subset": subset_name, "subsets_sha256": frozen})
            if n_rows is not None and (view is None or view.answer_changed is None):
                continue                                     # the path check looks for rows with an answer
            if view is None:
                J.append(result_path, {**meta, "judge": "answer", "status": "skipped", "verdict": None, "confidence": None,
                                       "reason": info.get("view_error"), "failure": None, "model_calls": 0, "usd": 0.0})
                have.add(key)
                continue
            if view.answer_changed is not None and info.get("answer_source") != "main run row":
                raise SystemExit(f"{r['row_id']}: the answer is not the main run's own row ({info.get('answer_source')}); nothing is recomputed here")
            client.build_id = f"{tag}answer/{r['set']}/{r['row_id']}"
            res = judge_jev(client, view)
            J.append(result_path, {**meta, **res})
            have.add(key)
            judged += 1
            print("answer", r["row_id"], res.get("verdict"), res.get("confidence"), res.get("failure"),
                  f"long={res.get('long_context')}", f"usd={res.get('usd', 0.0):.6f}", flush=True)
    except ServiceError as e:
        print("stopped (service; resumable):", e, flush=True)
    print(f"this run's spend so far: ${client.spent(tag):.4f}", flush=True)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("sets")
    ap.add_argument("--out", required=True)
    ap.add_argument("--subsets", default=None)
    ap.add_argument("--subset-name", default=None)
    ap.add_argument("--rows", type=int, default=None, help="dev path check: judge this many rows with an answer")
    ap.add_argument("--max-usd", type=float, default=6.0)
    ap.add_argument("--shard", default=None, help="K/N: judge only part K (from 0) of N")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    shard = tuple(int(x) for x in a.shard.split("/")) if a.shard else None
    if (a.subsets is None) != (a.subset_name is None):
        raise SystemExit("--subsets and --subset-name go together")
    run(root, tuple(a.sets.split(",")), Path(a.out), a.max_usd, Path(a.subsets) if a.subsets else None, a.subset_name,
        n_rows=a.rows, shard=shard)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
