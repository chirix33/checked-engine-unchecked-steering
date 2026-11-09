"""Development build test: fresh, independent builds per model and specification.

System b0 (default) is the pinned OTF-Tools code, imported unchanged. System r1 is redesign/otf_r1, the generation
fixes from scripts/make_redesign_r1.py, selected with the environment variable BUILD_SYSTEM=r1. Its acceptance check
is the same code. This runner only supplies the model connection, with the library off, so every build is fresh.

Metered per call: tokens, latency, finish reason, busy errors and served provider. Busy and connection failures
are kept separate from model failures. A shared ledger enforces the spending cap at list prices. Finished builds
are skipped on rerun. Keys come from .env and are never written or printed.

Usage: python scripts/b0_build_test.py <project_root> <setup> <builds_per_doc> <doc_name=pdf_path> [...]
"""
import hashlib
import json
import os
import statistics
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

CAP_USD = 5.00
EARLIER_SPEND_USD = 0.03
CAP_MARGIN_USD = 0.25
CLAUDE_CAP_USD = 25.00  # Raised from 15.00 by Ashraf on 2026-11-08 for the judge baselines (D18, baseline_judges_design.md). Tracked apart from Ollama credits.
NUM_CTX = 131072
MAX_OUTPUT = 16384
BUSY_DELAYS = [30, 60, 120, 240, 300, 300]
BUSY_CODES = {408, 409, 425, 429, 500, 502, 503, 504, 529}
BILLING_CODES = {401, 402, 403}

SETUPS = {
    "gpt-oss-120b": {"kind": "ollama", "base": "https://ollama.com", "model": "gpt-oss:120b", "key": "OLLAMA_API_KEY",
                     "timeout": 600, "think": "medium", "options": {"temperature": 1.0},
                     "price_per_million": (0.15, 0.60)},
    "qwen3.5-9b": {"kind": "ollama", "base": "http://127.0.0.1:11535", "model": "qwen3.5:9b", "key": None,
                   "timeout": 1800, "think": True,
                   "options": {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "presence_penalty": 0.0},
                   "price_per_million": (0.0, 0.0)},
    "gemma-31b-ollama": {"kind": "ollama", "base": "https://ollama.com", "model": "gemma4:31b", "key": "OLLAMA_API_KEY",
                         "timeout": 600, "think": True, "options": {"temperature": 1.0, "top_p": 0.95, "top_k": 64},
                         "price_per_million": (0.14, 0.40)},
    "claude-sonnet-5-5": {"kind": "claude", "model": "claude-sonnet-5-5", "key": "ANTHROPIC_API_KEY", "timeout": 900, "effort": "medium",
                          "price_per_million": (2.00, 10.00), "cache_read": 0.20, "options": {}},
    "claude-haiku-5-5": {"kind": "claude", "model": "claude-haiku-5-5", "key": "ANTHROPIC_API_KEY", "timeout": 900, "effort": "medium",
                         "price_per_million": (0.10, 0.50), "cache_read": 0.01, "options": {}},
    "gemma-26b-openrouter-free": {"kind": "router", "base": "https://openrouter.ai/api/v1",
                                  "model": "google/gemma-4-26b-a4b-it:free", "key": "OPENROUTER_API_KEY", "timeout": 600,
                                  "options": {"temperature": 1.0, "top_p": 0.95, "top_k": 64},
                                  "price_per_million": (0.0, 0.0)},
}


class InfrastructureFailure(Exception):
    """The service could not answer. Not a model failure."""


class CapReached(Exception):
    pass


def load_env(path):
    env = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class Ledger:
    def __init__(self, folder, setup_name):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / f"calls_{setup_name}.jsonl"
        self.is_claude = setup_name.startswith("claude")

    def spent(self):
        total = 0.0 if self.is_claude else EARLIER_SPEND_USD
        for p in self.folder.parent.glob("build_test_*/calls_*.jsonl"):  # Each cap is shared across all build tests.
            if ("claude" in p.name) != self.is_claude:
                continue
            with p.open(encoding="utf-8") as f:
                for line in f:
                    total += json.loads(line).get("usd", 0.0)
        return total

    def add(self, record):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


class Client:
    def __init__(self, setup_name, env, ledger):
        self.name = setup_name
        self.setup = SETUPS[setup_name]
        self.key = env[self.setup["key"]] if self.setup["key"] else None
        self.ledger = ledger
        self.build_id = None
        self.calls = []

    def _request(self, messages):
        s = self.setup
        if s["kind"] == "ollama":
            url = s["base"] + "/api/chat"
            options = {**s["options"], "num_predict": MAX_OUTPUT, "num_ctx": NUM_CTX}
            body = {"model": s["model"], "stream": False, "think": s["think"], "options": options, "messages": messages}
        else:
            url = s["base"] + "/chat/completions"
            options = dict(s["options"])
            body = {"model": s["model"], "max_tokens": MAX_OUTPUT, "reasoning": {"enabled": True}, "messages": messages,
                    "temperature": options["temperature"], "top_p": options["top_p"], "top_k": options["top_k"]}
        headers = {"Content-Type": "application/json", "User-Agent": "trust-artifact-check/0.1"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        return urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)

    def _parse(self, data):
        if self.setup["kind"] == "ollama":
            message = data.get("message", {})
            return {"text": message.get("content") or "", "reasoning_chars": len(message.get("thinking") or ""),
                    "prompt_tokens": data.get("prompt_eval_count"), "output_tokens": data.get("eval_count"),
                    "finish": data.get("done_reason"), "provider": "ollama-cloud" if self.key else "local"}
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage") or {}
        return {"text": message.get("content") or "", "reasoning_chars": len(message.get("reasoning") or ""),
                "prompt_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
                "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                "finish": choice.get("finish_reason"), "provider": data.get("provider")}

    def _claude_call(self, messages):
        """One call through the official SDK. Busy errors are retried by the caller, so the SDK's own retries are off."""
        import anthropic
        s = self.setup
        client = anthropic.Anthropic(api_key=self.key, max_retries=0, timeout=s["timeout"])
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        kwargs = {"system": system} if system else {}
        with client.messages.stream(model=s["model"], max_tokens=MAX_OUTPUT, messages=turns, thinking={"type": "adaptive"},
                                    output_config={"effort": s["effort"]}, cache_control={"type": "ephemeral"}, **kwargs) as stream:
            final = stream.get_final_message()
        text = "".join(b.text for b in final.content if b.type == "text")
        u = final.usage
        read, write = u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0
        total_prompt = u.input_tokens + read + write
        in_price, out_price = s["price_per_million"]
        scale = 5.0 if s["model"] == "claude-haiku-5-5" and total_prompt > 100_000 else 1.0
        usd = (u.input_tokens * in_price * scale + write * in_price * scale * 1.25 + read * s["cache_read"] * scale + u.output_tokens * out_price * scale) / 1e6
        return {"text": text, "reasoning_chars": 0, "prompt_tokens": total_prompt, "output_tokens": u.output_tokens,
                "uncached_input_tokens": u.input_tokens, "cache_read_tokens": read, "cache_write_tokens": write, "usd": usd,
                "finish": final.stop_reason, "provider": "anthropic"}

    def _claude_with_retries(self, messages):
        import anthropic
        started = time.time()
        busy = []
        for attempt in range(len(BUSY_DELAYS) + 1):
            attempt_start = time.time()
            try:
                return self._claude_call(messages), busy, started
            except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError, anthropic.BadRequestError) as e:
                error = {"http": e.status_code, "detail": str(e)[:200]}
                self._log_failure(messages, busy + [error], started)
                raise InfrastructureFailure(f"request refused {e.status_code}: {str(e)[:200]}")
            except anthropic.APIStatusError as e:
                error = {"http": e.status_code, "detail": str(e)[:200]}
            except anthropic.APIConnectionError as e:
                error = {"http": None, "detail": str(e)[:200]}
            error["seconds"] = round(time.time() - attempt_start, 1)
            busy.append(error)
            if attempt == len(BUSY_DELAYS):
                self._log_failure(messages, busy, started)
                raise InfrastructureFailure(f"still busy after {len(busy)} attempts: {error['detail'][:120]}")
            time.sleep(BUSY_DELAYS[attempt])

    def _one_call(self, messages):
        spent = self.ledger.spent()
        cap = CLAUDE_CAP_USD if self.setup["kind"] == "claude" else CAP_USD
        if spent >= cap - CAP_MARGIN_USD:
            raise CapReached(f"list-price spend {spent:.2f}")
        if self.setup["kind"] == "claude":
            parsed, busy, started = self._claude_with_retries(messages)
            record = {"build": self.build_id, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                      "seconds": round(time.time() - started, 2), "prompt_chars": sum(len(m.get("content") or "") for m in messages),
                      "busy": busy, **{k: v for k, v in parsed.items() if k != "text"}, "reply_chars": len(parsed["text"])}
            self.ledger.add(record)
            self.calls.append(record)
            return parsed["text"]
        started = time.time()
        busy = []
        for attempt in range(len(BUSY_DELAYS) + 1):
            attempt_start = time.time()
            error = None
            try:
                with urllib.request.urlopen(self._request(messages), timeout=self.setup["timeout"]) as r:
                    data = json.load(r)
                break
            except urllib.error.HTTPError as e:
                detail = e.read(300).decode("utf-8", "replace")
                error = {"http": e.code, "detail": detail[:200]}
                if e.code in BILLING_CODES:
                    self._log_failure(messages, busy + [error], started)
                    raise InfrastructureFailure(f"account or billing error {e.code}: {detail[:200]}")
                if e.code not in BUSY_CODES:
                    self._log_failure(messages, busy + [error], started)
                    raise InfrastructureFailure(f"request refused {e.code}: {detail[:200]}")
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
                error = {"http": None, "detail": str(e)[:200]}
            error["seconds"] = round(time.time() - attempt_start, 1)
            busy.append(error)
            if attempt == len(BUSY_DELAYS):
                self._log_failure(messages, busy, started)
                raise InfrastructureFailure(f"still busy after {len(busy)} attempts: {error['detail'][:120]}")
            time.sleep(BUSY_DELAYS[attempt])
        parsed = self._parse(data)
        chars = sum(len(m.get("content") or "") for m in messages)
        in_price, out_price = self.setup["price_per_million"]
        usd = ((parsed["prompt_tokens"] or 0) * in_price + (parsed["output_tokens"] or 0) * out_price) / 1e6
        record = {"build": self.build_id, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                  "seconds": round(time.time() - started, 2), "prompt_chars": chars, "busy": busy, "usd": usd,
                  **{k: v for k, v in parsed.items() if k != "text"}, "reply_chars": len(parsed["text"])}
        self.ledger.add(record)
        self.calls.append(record)
        return parsed["text"]

    def _log_failure(self, messages, busy, started):
        # A failed stream may still be billed for tokens it generated; that amount is unknown, so it is flagged.
        record = {"build": self.build_id, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                  "seconds": round(time.time() - started, 2), "prompt_chars": sum(len(m.get("content") or "") for m in messages),
                  "busy": busy, "usd": 0.0, "failed": True, "billing_unknown": True}
        self.ledger.add(record)
        self.calls.append(record)

    def llm(self, messages, empty_retries=2):
        """Same behaviour as the pinned adapter: an empty reply is retried up to twice, and every call counts."""
        for _ in range(empty_retries + 1):
            text = self._one_call(messages)
            if text.strip():
                return text
        return ""


def summarize(client, started, info, status, error=None):
    calls = client.calls
    good = [c for c in calls if not c.get("failed")]
    prompts = [c["prompt_tokens"] for c in good if c.get("prompt_tokens")]
    ratios = [c["prompt_chars"] / c["prompt_tokens"] for c in good if c.get("prompt_tokens")]
    return {
        "build": client.build_id, "setup": client.name, "status": status, "error": error, "accepted": bool(info and info.get("model_passed")),
        "mean_f1": info.get("model_f1") if info else None, "tries": info.get("model_tries") if info else None,
        "seconds": round(time.time() - started, 1), "calls": len(calls), "failed_calls": len(calls) - len(good),
        "busy_events": sum(len(c.get("busy", [])) for c in calls),
        "prompt_tokens": sum(prompts), "output_tokens": sum(c.get("output_tokens") or 0 for c in good),
        "reasoning_tokens": sum(c.get("reasoning_tokens") or 0 for c in good),
        "reasoning_chars": sum(c.get("reasoning_chars") or 0 for c in good),
        "largest_prompt_tokens": max(prompts, default=0),
        "chars_per_token_range": [round(min(ratios), 2), round(max(ratios), 2)] if ratios else None,
        "length_cutoffs": sum(c.get("finish") in ("length", "max_tokens") for c in good),  # review fix: Claude reports max_tokens
        "calls_missing_tokens": sum(not c.get("prompt_tokens") or c.get("output_tokens") is None for c in good),
        "cache_read_tokens": sum(c.get("cache_read_tokens") or 0 for c in good), "refusals": sum(c.get("finish") == "refusal" for c in good),
        "providers": sorted({str(c.get("provider")) for c in good}), "usd_list_price": round(sum(c.get("usd", 0.0) for c in calls), 4),
    }


def main(root, setup_name, builds_per_doc, *doc_args):
    root = Path(root).resolve()
    system = os.environ.get("BUILD_SYSTEM", "b0")
    sys.dont_write_bytecode = True
    if system == "r1":
        sys.path.insert(0, str(root / "redesign"))
        from otf_r1.engine import OTFEngine
    else:
        sys.path.insert(0, str(root / "baseline" / "otf-tools-10f5401" / "implementation-1"))
        from otf.engine import OTFEngine  # Pinned baseline, unchanged.

    env = load_env(root / ".env")
    if setup_name.startswith("claude"):
        out = root / "runs" / f"build_test_{system}_claude"
    else:
        out = root / "runs" / ("build_test_r1" if system == "r1" else "build_test_v1")
    ledger = Ledger(out, setup_name)
    docs = dict(a.split("=", 1) for a in doc_args)
    client = Client(setup_name, env, ledger)
    results_path = out / f"builds_{setup_name}.jsonl"
    done = set()
    if results_path.exists():
        done = {json.loads(line)["build"] for line in results_path.open(encoding="utf-8")}
    # Round-robin, so an early stop still leaves results for every specification.
    for k in range(1, int(builds_per_doc) + 1):
        for doc_name, pdf in docs.items():
            build_id = f"{setup_name}/{doc_name}/b{k}"
            if build_id in done:
                continue
            work = out / setup_name / doc_name / f"b{k}"
            work.mkdir(parents=True, exist_ok=True)
            client.build_id, client.calls = build_id, []
            log_path = work / "build_log.txt"
            log = lambda s, p=log_path: p.open("a", encoding="utf-8").write(s + "\n")  # noqa: E731
            started = time.time()
            info, status, error = None, "completed", None
            try:
                engine = OTFEngine(client.llm, work, 3, log=log, ablation=None)
                info = engine.prepare(Path(pdf), None, None)
                (work / "program.json").write_text(json.dumps(engine.model), encoding="utf-8")
            except CapReached as e:
                status, error = "stopped_at_cap", str(e)
            except InfrastructureFailure as e:
                status, error = "infrastructure_failure", str(e)
            except Exception:  # A crash in the pinned code on a model's output counts as a failed build, and is kept.
                status, error = "build_crashed", traceback.format_exc()[-800:]
            result = summarize(client, started, info, status, error)
            result["pdf_sha256"] = hashlib.sha256(Path(pdf).read_bytes()).hexdigest()
            with results_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(result) + "\n")
            print(json.dumps({x: result[x] for x in ("build", "status", "accepted", "mean_f1", "seconds", "calls", "busy_events",
                                                     "prompt_tokens", "output_tokens", "largest_prompt_tokens", "usd_list_price")}), flush=True)
            if status == "stopped_at_cap":
                print("cap reached, stopping", flush=True)
                return


if __name__ == "__main__":
    main(*sys.argv[1:])
