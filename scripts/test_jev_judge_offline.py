"""Offline checks of the Jev answer-level judge (scripts/jev_judge.py, D30). No network: a fake HTTP service.

Covers: Jev's input is the answer-level LLM judge's prompt text minus its output-format lines (byte for byte), with
no gold, binding, other run, native verdict, build history or evaluation path; the request has one noul question and
nothing else; the reply mapping (probability -> confidence and verdict); failures (unparsable, out of range, still too
long) as DECLINE at 0; long context only after `max_tokens_exceeded`; busy retries then a raised service error;
auth, validation, redirect and model-version errors stop the run; a key echoed by the service never reaches the
ledger, a record, output or an exception; the run loop (keys, meta, subset sha, rule A, skipped views, resume,
shards, the spending stop, the no-recompute stop, argument guards) on a fake row source; the source never reads gold,
bindings or labels, and judges.py is still the frozen file.

Usage: python -X utf8 scripts/test_jev_judge_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
sys.dont_write_bytecode = True

import judges as J                 # noqa: E402
import jev_judge as V              # noqa: E402
import test_judges_offline as T    # noqa: E402  (fixtures only; its tests run only as a script)

FAILS = []
KEY = "sk-test-SENTINEL-KEY-0000"


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def raises(exc, fn) -> bool:
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


class FakeService:
    """Scripted replies: each item is (status, body dict or text) or an OSError to raise. Records every request."""

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def __call__(self, url, body, headers, timeout=None):
        self.seen.append({"url": url, "body": json.loads(body.decode("utf-8")), "headers": dict(headers)})
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(r, Exception):
            raise r
        status, b = r
        return status, (b if isinstance(b, str) else json.dumps(b)), {}


def ok(p, model=V.MODEL, tokens=1000):
    return 200, {"model": model, "answers": {V.QUESTION_ID: {"type": "noul", "noul": p}}, "usage": {"input_tokens": tokens, "output_tokens": 3}}


TOO_LONG = (400, {"detail": {"error": "max_tokens_exceeded", "message": "too long"}})


def client(tmp, replies, delays=(0, 0, 0)):
    svc = FakeService(replies)
    c = V.JevClient(KEY, tmp / "calls.jsonl", post=svc, sleep=lambda s: None, delays=list(delays))
    c.build_id = "judges/test/answer/x/row"
    return c, svc


def input_tests(tmp):
    otf, devs = T.views(tmp)
    for name, view in (("otf", otf), ("devs", devs)):
        state = V.jev_state(view)
        llm = J.prompt_text(J.answer_prompt(view))
        check(f"input: Jev's state is the LLM judge's prompt minus its output-format lines ({name})",
              llm == state + "\n" + J.ANSWER_END, f"{len(state)} vs {len(llm)}")
        hit = [s for s in T.SENTINELS if s in state]
        check(f"leak: no gold, binding, other run, native verdict, build history or evaluation path in the state ({name})", not hit, str(hit))
        check(f"input: the state has the question, request and both answers ({name})",
              all(s in state for s in (T.QUESTION_ROW["question"], '"target": "Check"', "With the change: 910", "run of the recorded inputs): 900")))
        check(f"input: the state has no VERDICT/CONFIDENCE format lines ({name})", "VERDICT:" not in state and "CONFIDENCE:" not in state)
        req = V.jev_request(view)
        check(f"request: model, state and one noul question, nothing else ({name})",
              set(req) == {"model", "state", "questions"} and req["model"] == "jev-1.14.0"
              and req["questions"] == {V.QUESTION_ID: {"type": "noul", "instructions": V.INSTRUCTIONS}})
    no_q = J.make_view(T.fake_nav(), "Run 01", T.fake_otf(tmp), 10 ** 8)
    check("input: a view without a question or request is refused", raises(ValueError, lambda: V.jev_state(no_q)))


def mapping_tests(tmp):
    otf, _ = T.views(tmp)
    c, svc = client(tmp, [ok(0.83)])
    r = V.judge_jev(c, otf)
    check("map: p=0.83 -> TRUST at confidence 83, consistent", r["verdict"] == "TRUST" and abs(r["confidence"] - 83.0) < 1e-9
          and not r["inconsistent"] and r["noul"] == 0.83 and r["failure"] is None and r["judge"] == "answer" and r["status"] == "judged", str(r))
    check("map: confidence keeps the model's resolution (not rounded)", V.judge_jev(client(tmp, [ok(0.12345)])[0], otf)["confidence"] == 100.0 * 0.12345)
    r = V.judge_jev(client(tmp, [ok(0.5)])[0], otf)
    check("map: p=0.5 -> TRUST at 50 (threshold inclusive)", r["verdict"] == "TRUST" and r["confidence"] == 50.0 and not r["inconsistent"])
    r = V.judge_jev(client(tmp, [ok(0.4999)])[0], otf)
    check("map: p=0.4999 -> DECLINE", r["verdict"] == "DECLINE" and not r["inconsistent"])
    check("cost: input tokens priced at $0.042 per million", abs(V.judge_jev(client(tmp, [ok(0.9, tokens=1_000_000)])[0], otf)["usd"] - 0.042) < 1e-12)
    h = svc.seen[0]["headers"]
    check("request: no long-context header by default", V.LONG_HEADER not in h)
    check("request: the key goes only in the Authorization header", h["Authorization"] == f"Bearer {KEY}"
          and KEY not in json.dumps(svc.seen[0]["body"]))
    for bad, what in ((1.2, "above 1"), (-0.1, "below 0"), (float("nan"), "NaN"), ("0.9", "a string"), (True, "a boolean")):
        st, body = ok(0.5)
        body["answers"][V.QUESTION_ID]["noul"] = bad
        r = V.judge_jev(client(tmp, [(st, json.dumps(body, allow_nan=True))])[0], otf)
        check(f"fail: a noul {what} is DECLINE at 0, unparsable", r["verdict"] == "DECLINE" and r["confidence"] == 0 and r["failure"] == "unparsable", str(r)[:200])
    r = V.judge_jev(client(tmp, [(200, {"model": V.MODEL, "answers": {}, "usage": {"input_tokens": 5, "output_tokens": 0}})])[0], otf)
    check("fail: a reply without the answer is DECLINE at 0, unparsable", r["failure"] == "unparsable" and r["confidence"] == 0)
    check("stop: a reply from another model version stops the run", raises(V.StopRun, lambda: V.judge_jev(client(tmp, [ok(0.9, model="jev-1.13.0")])[0], otf)))
    no_answer = J.make_view(T.fake_nav(), "Run 01", T.fake_otf(tmp), 10 ** 8, T.QUESTION_ROW["question"], T.REQUEST, None, 900)
    c, svc = client(tmp, [ok(0.9)])
    r = V.judge_jev(c, no_answer)
    check("rule A: a row without an answer is not judged and costs nothing", r["status"] == "no_answer" and not svc.seen and r["usd"] == 0.0)


def long_context_tests(tmp):
    otf, _ = T.views(tmp)
    c, svc = client(tmp, [TOO_LONG, ok(0.7)])
    r = V.judge_jev(c, otf)
    check("long: max_tokens_exceeded -> one resend with the long-context header",
          len(svc.seen) == 2 and V.LONG_HEADER not in svc.seen[0]["headers"] and svc.seen[1]["headers"].get(V.LONG_HEADER) == "true"
          and svc.seen[0]["body"] == svc.seen[1]["body"] and r["long_context"] is True and r["verdict"] == "TRUST", str(r)[:200])
    check("long: the refused first call is recorded and costs nothing", r["model_calls"] == 2 and r["failed_calls"] == 1 and abs(r["usd"] - 1000 * V.USD_PER_INPUT_TOKEN) < 1e-12)
    r = V.judge_jev(client(tmp, [ok(0.7)])[0], otf)
    check("long: a request that fits is answered without long context", r["long_context"] is False and r["model_calls"] == 1)
    c, svc = client(tmp, [TOO_LONG, TOO_LONG])
    r = V.judge_jev(c, otf)
    check("long: still too long with long context -> DECLINE at 0, too_long", r["failure"] == "too_long" and r["confidence"] == 0 and len(svc.seen) == 2)
    c, svc = client(tmp, [(400, {"detail": "invalid UTF-8"})])
    check("stop: another 400 stops the run (no long-context resend)", raises(V.StopRun, lambda: V.judge_jev(c, otf)) and len(svc.seen) == 1)


def service_tests(tmp):
    otf, _ = T.views(tmp)
    c, svc = client(tmp, [(529, "overloaded"), (429, "slow down"), OSError("reset"), ok(0.6)], delays=(0, 0, 0, 0))
    r = V.judge_jev(c, otf)
    check("retry: overload, rate limit and network errors are retried, then the answer is used", r["verdict"] == "TRUST" and r["model_calls"] == 4
          and r["failed_calls"] == 3, str(r)[:200])
    c, svc = client(tmp, [(503, "down")], delays=(0, 0))
    check("retry: a service that never answers raises a service error (never a verdict)", raises(V.ServiceError, lambda: V.judge_jev(c, otf)) and len(svc.seen) == 3)
    for code in (401, 403):
        c, _ = client(tmp, [(code, "bad key")])
        check(f"stop: {code} stops the run", raises(V.StopRun, lambda: V.judge_jev(c, otf)))
    c, _ = client(tmp, [(422, {"detail": [{"loc": ["body", "state"], "msg": "Field required", "type": "missing"}]})])
    check("stop: 422 stops the run", raises(V.StopRun, lambda: V.judge_jev(c, otf)))
    check("stop: a missing key stops before any call", raises(V.StopRun, lambda: V.JevClient("", tmp / "x.jsonl")))
    led = (tmp / "calls.jsonl").read_text(encoding="utf-8")
    check("secret: the key is never written to the ledger", KEY not in led and len(led) > 0)
    rows = [json.loads(l) for l in led.splitlines()]
    check("ledger: every call is recorded with build, usd, tokens, seconds and failed",
          all({"build", "usd", "prompt_tokens", "seconds", "failed"} <= set(x) for x in rows) and rows[0]["build"].startswith("judges/"))


def source_tests():
    src = (ROOT / "scripts" / "jev_judge.py").read_text(encoding="utf-8")
    code = [l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")]
    body = "\n".join(code[code.index('from __future__ import annotations'):])     # skip the module docstring
    hits = [l.strip() for l in body.splitlines() if any(k in l for k in ('["gold', '"gold"', "'gold'", '["binding', '"binding"', "factual_end",
                                                                          "effectful", "oracle", "reference_engine", "main_summary", "correct"))]
    check("leak: jev_judge.py never reads gold, bindings, effect labels, the oracle source, the reference or the scorer", not hits, str(hits[:3]))
    check("frozen: judges.py has its freeze hash and recorded prompt hash (else a run stops)",
          V.check_frozen_prompt(ROOT) is None and J.PROMPT_HASH == "ed45fe10bab7c96c")
    check("ledger: Jev's ledger is outside runs/build_test_* (never counted against the runner's Ollama stop)",
          "build_test" not in str(V.ledger_path(ROOT)) and V.ledger_path(ROOT).name == "calls_jev-1.14.0.jsonl")


def key_leak_tests(tmp):
    """The service echoes the key in error bodies: it must not reach the ledger, a record, stdout or an exception."""
    import contextlib
    import io as _io
    otf, _ = T.views(tmp)
    echo = f"bad token Bearer {KEY}"
    part = KEY[3:13]
    outs, msgs, recs = _io.StringIO(), [], []
    with contextlib.redirect_stdout(outs), contextlib.redirect_stderr(outs):
        for replies in ([(401, echo)], [(422, {"detail": echo})], [(400, "invalid " + part)], [(503, echo)]):
            c, _ = client(tmp, replies, delays=(0,))
            try:
                recs.append(V.judge_jev(c, otf))
            except Exception as e:
                msgs.append(str(e))
        c, _ = client(tmp, [(500, echo), ok(0.7)], delays=(0,))
        recs.append(V.judge_jev(c, otf))
        c, _ = client(tmp, [TOO_LONG, (200, "not json " + echo)], delays=(0,))
        recs.append(V.judge_jev(c, otf))
    blob = "\n".join([outs.getvalue(), (tmp / "calls.jsonl").read_text(encoding="utf-8"), json.dumps(recs)] + msgs)
    check("secret: a key echoed by the service never reaches the ledger, a record, output or an exception",
          KEY not in blob and part not in blob and "[KEY]" in blob, "leaked" if (KEY in blob or part in blob) else "no [KEY] marker")
    check("secret: the masked errors still say what failed", any("authentication failed (401)" in m for m in msgs) and len(msgs) == 4, str(msgs)[:300])


class FakeRows:
    """A stand-in for judges.Rows: rows of one program (q0 answer, q1 no answer, q2 view error, q3 answer that
    would have to be recomputed when `recompute` is set)."""
    PROG = {"name": "otf/r1_claude/claude-haiku-5-5/loan/b1", "process": "loan"}

    def __init__(self, tmp, recompute=False):
        self.tmp, self.recompute = tmp, recompute
        self.programs = [self.PROG]
        self.questions = [{"id": f"q{i}", "doc": f"loan_d0{i}", "question": f"Q{i}?", "family": "activity_duration"} for i in range(8)]

    def scope(self, q):
        return "Run 01"

    def pairs(self):
        for q in self.questions:
            yield self.PROG, q

    def view(self, prog, q):
        i = int(q["id"][1:])
        if i >= 4:
            return (J.make_view(T.fake_nav(), "Run 01", T.fake_otf(self.tmp), 10 ** 8, q["question"], T.REQUEST, 910 + i, 900),
                    {"answer_source": "main run row"})
        if i == 2:
            raise J.ViewError("no interpreted request for this question")
        if i == 1:
            return J.make_view(T.fake_nav(), "Run 01", T.fake_otf(self.tmp), 10 ** 8, q["question"], T.REQUEST, None, 900), {"answer_source": "main run row"}
        src = "computed (no main run row yet)" if (i == 3 and self.recompute) else "main run row"
        return (J.make_view(T.fake_nav(), "Run 01", T.fake_otf(self.tmp), 10 ** 8, q["question"], T.REQUEST, 910 + i, 900),
                {"answer_source": src, "platform_records": [{"SENTINEL": T.GOLD}]})


def run_loop_tests(tmp):
    orig_rows, orig_load = J.Rows, J.load_subset
    name = FakeRows.PROG["name"]
    ids = {f"wf_test|{name}|q{i}" for i in range(3)}
    try:
        J.Rows = lambda root, s: FakeRows(tmp)
        J.load_subset = lambda path, nm: (ids, "SHA_OF_SUBSETS")
        out = tmp / "jevrun"
        c, svc = client(tmp, [ok(0.9)])
        V.run(ROOT, ("wf_test",), out, 1.0, Path("subsets.json"), "answer_haiku", client=c)
        rows = [json.loads(l) for l in (out / "judgments_jev-1.14.0.jsonl").read_text(encoding="utf-8").splitlines()]
        by = {r["question"]: r for r in rows}
        check("run: one record per subset row, keyed as the other judges' (answer|model|set|row_id)",
              sorted(by) == ["q0", "q1", "q2"] and by["q0"]["key"] == f"answer|jev-1.14.0|wf_test|{name}|q0", str(sorted(by)))
        check("run: subset name and sha recorded; meta as judges.py", all(r["subset"] == "answer_haiku" and r["subsets_sha256"] == "SHA_OF_SUBSETS"
              and r["cohort"] == "otf/r1_claude/claude-haiku-5-5" and r["process"] == "loan" and r["family"] == "activity_duration" for r in rows))
        check("run: the answered row is judged; no-answer and view-error rows recorded without a call",
              by["q0"]["status"] == "judged" and by["q1"]["status"] == "no_answer" and by["q2"]["status"] == "skipped" and len(svc.seen) == 1)
        check("run: the platform records in `info` never reach the request", T.GOLD not in json.dumps(svc.seen))
        V.run(ROOT, ("wf_test",), out, 1.0, Path("subsets.json"), "answer_haiku", client=c)
        check("run: a rerun resumes (nothing judged twice)",
              len(svc.seen) == 1 and len((out / "judgments_jev-1.14.0.jsonl").read_text(encoding="utf-8").splitlines()) == 3)
        ids8 = {f"wf_test|{name}|q{i}" for i in (0, 4, 5, 6, 7)}
        J.load_subset = lambda path, nm: (ids8, "SHA")
        parts = {J.shard_of("wf_test", f"loan_d0{i}", "Run 01", 2) for i in (0, 4, 5, 6, 7)}
        out2 = tmp / "jevrun_shards"
        c2, _ = client(tmp, [ok(0.9)])
        for k in range(2):
            V.run(ROOT, ("wf_test",), out2, 1.0, Path("subsets.json"), "answer_haiku", shard=(k, 2), client=c2)
        files = sorted(out2.glob("judgments_*.jsonl"))
        per = [[json.loads(l)["question"] for l in p.read_text(encoding="utf-8").splitlines()] for p in files]
        check("run: the fake rows really fall in both shards", parts == {0, 1}, str(parts))
        check("run: two shards write two non-empty, disjoint files that together hold each row once",
              len(files) == 2 and all(per) and not set(per[0]) & set(per[1]) and sorted(per[0] + per[1]) == ["q0", "q4", "q5", "q6", "q7"], str(per))
        J.load_subset = lambda path, nm: (ids, "SHA_OF_SUBSETS")
        J.Rows = lambda root, s: FakeRows(tmp)
        J.load_subset = lambda path, nm: ({f"wf_test|{name}|q0", f"wf_test|{name}|q3"}, "SHA")
        c3, svc3 = client(tmp, [ok(0.9, tokens=10_000_000)])
        V.run(ROOT, ("wf_test",), tmp / "jevrun_budget", 0.3, Path("subsets.json"), "answer_haiku", client=c3)
        check("run: the spending stop holds (one $0.42 call, then stop at $0.30)", len(svc3.seen) == 1, str(len(svc3.seen)))
        led = tmp / "shared_ledger.jsonl"
        a = V.JevClient(KEY, led, post=FakeService([ok(0.9, tokens=5_000_000)]), sleep=lambda s: None)
        b = V.JevClient(KEY, led, post=FakeService([ok(0.9, tokens=5_000_000)]), sleep=lambda s: None)
        tag = "judges/shared/"
        check("budget: a second client starts at zero", b.spent(tag) == 0.0)
        a.build_id = tag + "answer/wf_test/x"
        V.judge_jev(a, T.views(tmp)[0])
        check("budget: one process sees another process's spend (shards share one stop)", abs(b.spent(tag) - 0.21) < 1e-9, str(b.spent(tag)))
        with led.open("a", encoding="utf-8") as f:
            f.write('{"build": "judges/shared/answer/x", "usd": 5.0')     # a half-written line from another process
        check("budget: a half-written last line is left for the next read", abs(b.spent(tag) - 0.21) < 1e-9)
        with led.open("a", encoding="utf-8") as f:
            f.write("}\n")
        check("budget: the completed line is then counted", abs(b.spent(tag) - 5.21) < 1e-9, str(b.spent(tag)))
        check("budget: other folders' spend is not counted", b.spent("judges/other/") == 0.0)
        J.Rows = lambda root, s: FakeRows(tmp, recompute=True)
        J.load_subset = lambda path, nm: ({f"wf_test|{name}|q3"}, "SHA")
        check("run: an answer that would be recomputed stops the run",
              raises(SystemExit, lambda: V.run(ROOT, ("wf_test",), tmp / "jevrun_re", 1.0, Path("s.json"), "answer_haiku", client=client(tmp, [ok(0.9)])[0])))
    finally:
        J.Rows, J.load_subset = orig_rows, orig_load


def guard_tests(tmp):
    c = client(tmp, [ok(0.5)])[0]
    check("run: a frozen subset on a dev set is refused", raises(SystemExit, lambda: V.run(ROOT, ("wf_dev",), tmp / "o", 1.0, Path("x.json"), "answer_haiku", client=c)))
    check("run: the dev path check on a test set is refused", raises(SystemExit, lambda: V.run(ROOT, ("wf_test",), tmp / "o", 1.0, None, None, n_rows=2, client=c)))
    check("run: --rows together with --subsets is refused",
          raises(SystemExit, lambda: V.run(ROOT, ("wf_test",), tmp / "o", 1.0, Path("x.json"), "answer_haiku", n_rows=4, client=c)))
    check("run: neither --rows nor --subsets is refused", raises(SystemExit, lambda: V.run(ROOT, ("wf_test",), tmp / "o", 1.0, None, None, client=c)))
    check("run: a shard K >= N is refused",
          raises(SystemExit, lambda: V.run(ROOT, ("wf_test",), tmp / "o", 1.0, Path("x.json"), "answer_haiku", shard=(2, 2), client=c)))
    check("cli: --rows with --subsets is refused at the command line",
          raises(SystemExit, lambda: V.main([str(ROOT), "wf_test", "--out", str(tmp / "o"), "--subsets", "x.json", "--subset-name", "answer_haiku", "--rows", "4"])))


def _with_headers(svc, hdr):
    def post(url, body, headers, timeout=None):
        status, text, _ = svc(url, body, headers)
        return status, text, (hdr if status == 429 else {})
    return post


def more_service_tests(tmp):
    otf, _ = T.views(tmp)
    agent = J.make_view(T.fake_nav(), "Run 01", J.coding_agent_program("x", files={"run.py": "Y = 2\n"}), 5, T.QUESTION_ROW["question"], T.REQUEST, 7, 6, stdin={})
    check("input: equality holds for the coding-agent platform too", J.prompt_text(J.answer_prompt(agent)) == V.jev_state(agent) + "\n" + J.ANSWER_END)
    waits = []
    c = V.JevClient(KEY, tmp / "calls.jsonl", post=_with_headers(FakeService([(429, "slow"), ok(0.6)]), {"Retry-After": "7"}), sleep=waits.append, delays=[1, 1])
    V.judge_jev(c, otf)
    check("retry: Retry-After is honoured (7 s over a 1 s backoff)", waits == [7.0], str(waits))
    waits = []
    c = V.JevClient(KEY, tmp / "calls.jsonl", post=_with_headers(FakeService([(429, "slow"), ok(0.6)]), {"retry-after": "9999"}), sleep=waits.append, delays=[1])
    V.judge_jev(c, otf)
    check("retry: waits are capped at 300 s", waits == [300], str(waits))
    r = V.judge_jev(client(tmp, [(520, "edge"), (501, "x"), ok(0.6)], delays=(0, 0))[0], otf)
    check("retry: any 5xx is retried (520, 501)", r["verdict"] == "TRUST" and r["failed_calls"] == 2)
    import http.client as hc
    r = V.judge_jev(client(tmp, [hc.IncompleteRead(b"x"), ok(0.6)], delays=(0,))[0], otf)
    check("retry: a protocol error (IncompleteRead) is retried", r["verdict"] == "TRUST" and r["failed_calls"] == 1)
    r = V.judge_jev(client(tmp, [(200, "<html>not json</html>")])[0], otf)
    check("fail: a 200 reply that is not JSON is DECLINE at 0, unparsable", r["failure"] == "unparsable" and r["confidence"] == 0)
    r = V.judge_jev(client(tmp, [(200, {"answers": {V.QUESTION_ID: {"type": "noul", "noul": 0.9}}, "usage": {"input_tokens": "x"}})])[0], otf)
    check("fail: a reply with no model field is unparsable, not trusted; bad usage counts 0 tokens", r["failure"] == "unparsable" and r["usd"] == 0.0)
    for code in (302, 307):
        check(f"stop: a {code} redirect stops the run", raises(V.StopRun, lambda: V.judge_jev(client(tmp, [(code, "moved")])[0], otf)))
    check("stop: 413 stops the run", raises(V.StopRun, lambda: V.judge_jev(client(tmp, [(413, "too big")])[0], otf)))
    import io as _io
    import urllib.request as ur
    import email.message as em

    sent = []

    class Fake302(ur.HTTPSHandler):
        handler_order = 100

        def https_open(self, req):
            sent.append((req.get_method(), req.full_url, req.get_header("Authorization")))
            h = em.Message()
            h["Location"] = "https://elsewhere.example/steal"
            r = ur.addinfourl(_io.BytesIO(b"moved"), h, req.full_url, 302)
            r.msg = "Found"
            return r

    opener = ur.build_opener(V._NoRedirect, Fake302)
    orig = V._OPENER
    try:
        V._OPENER = opener
        status, text, _ = V.http_post(V.ENDPOINT, b"{}", {"Authorization": "Bearer " + KEY})
    finally:
        V._OPENER = orig
    check("http: the real opener returns a 302 as its status and sends nothing to the new location",
          status == 302 and len(sent) == 1 and sent[0][0] == "POST" and sent[0][1] == V.ENDPOINT, str((status, sent))[:200])

    def bad_post(url, body, headers, timeout=None):
        raise ValueError("Invalid header value " + headers["Authorization"])
    c = V.JevClient(KEY, tmp / "calls.jsonl", post=bad_post, sleep=lambda s: None)
    try:
        V.judge_jev(c, otf)
        msg = ""
    except V.StopRun as e:
        msg = str(e)
    check("secret: an unexpected send error stops the run with the key masked", msg and KEY not in msg and "[KEY]" in msg, msg[:200])

    k8 = KEY[2:10]
    st, body = ok(0.42)
    body["answers"][V.QUESTION_ID]["note"] = k8
    r = V.judge_jev(client(tmp, [(st, body)])[0], otf)
    check("secret: masking never alters a reply that is parsed (a key piece inside a 200 body)", r["noul"] == 0.42 and r["failure"] is None, str(r)[:200])


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        input_tests(tmp)
        mapping_tests(tmp)
        long_context_tests(tmp)
        service_tests(tmp)
        source_tests()
        key_leak_tests(tmp)
        run_loop_tests(tmp)
        guard_tests(tmp)
        more_service_tests(tmp)
    print(f"\n{len(FAILS)} failures")
    sys.exit(len(FAILS))
