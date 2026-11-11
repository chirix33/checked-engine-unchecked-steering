"""Offline tests for scripts/coding_agent_build.py: a fake model and a local runner, no model calls, no cost.

Usage: python -X utf8 scripts/test_coding_agent_offline.py          (local tests only)
       python -X utf8 scripts/test_coding_agent_offline.py --wsl    (also one fake-model build through the real
                                                                     WSL sandbox and isolation check)
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts")]
sys.dont_write_bytecode = True
import coding_agent_build as C  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


class LocalSandbox:
    """Runs the program with the local interpreter in a temp folder (stands in for WSL + bubblewrap)."""

    def __init__(self, folder: Path, timeout=5):
        self.dir, self.timeout, self.writes = folder, timeout, []

    def write(self, code):
        self.writes.append(code)
        (self.dir / "run.py").write_text(code, encoding="utf-8")

    def run(self, stdin, args=""):
        t0 = time.time()
        try:
            p = subprocess.run([sys.executable, "run.py", *args.split()], cwd=self.dir, input=stdin, capture_output=True,
                               text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return None, "", "", time.time() - t0, True
        return p.returncode, p.stdout, p.stderr, time.time() - t0, False


GOOD = "import sys, json\nd = json.load(sys.stdin)\nfor c in d['cases']:\n    print(json.dumps({'case': c['case'], 'event': 'case_end'}))\n"
CRASH = "import sys\nprint('not json')\nraise SystemExit('boom')\n"
SLEEP = "import time\ntime.sleep(30)\n"
EXAMPLE = json.dumps({"cases": [{"case": f"c{i:04d}", "arrival": i} for i in range(80)]})
SPEC = "# Task: Toy\nRead JSON from stdin and print one JSONL line per case."


def block(code):
    return f"Some reasoning first.\n\n```python\n{code}```\nThat is all."


def run_build(replies, turns=3, guard=None, timeout=5, client=None, stop_errors=None):
    tmp = Path(tempfile.mkdtemp())
    (tmp / "prog").mkdir()
    sb = LocalSandbox(tmp / "prog", timeout)
    client = client or C.FakeClient(replies)
    res = C.build(SPEC, EXAMPLE, client, sb, tmp, turns, guard, stop_errors or {})
    log = [json.loads(l) for l in (tmp / "prompt_log.jsonl").read_text(encoding="utf-8").splitlines()]
    runs = [json.loads(l) for l in (tmp / "example_runs.jsonl").read_text(encoding="utf-8").splitlines()] \
        if (tmp / "example_runs.jsonl").exists() else []
    return res, log, runs, sb, client


def main():
    # code extraction
    code, n = C.extract_code("a\n```python\nx = 1\ny = 2\n```\nb\n```python\nz = 2\n```")
    check("longest of several python blocks wins", code == "x = 1\ny = 2\n" and n == 2)
    check("```Python and ```python3 accepted", C.extract_code("```Python\na = 1\n```")[0] == "a = 1\n"
          and C.extract_code("```python3\nb = 1\n```")[0] == "b = 1\n")
    check("bare fence accepted when it is the only block", C.extract_code("```\nc = 1\n```")[0] == "c = 1\n")
    check("bare fence ignored next to a python block",
          C.extract_code("```\nls -la now\n```\n```python\nd = 1\n```")[0] == "d = 1\n")
    check("two bare fences: no code", C.extract_code("```\ne = 1\n```\n```\nf = 1\n```")[0] is None)
    check("```py fence accepted", C.extract_code("```py\nz = 3\n```")[0] == "z = 3\n")
    check("unclosed block is no code", C.extract_code("```python\nx = 1\n")[0] is None)
    check("non-python block is no code", C.extract_code("```bash\nls\n```")[0] is None)
    check("DONE recognised", C.is_done(" done. ") and not C.is_done("not done"))

    # good program, then DONE
    res, log, runs, sb, cl = run_build([block(GOOD), "DONE"])
    check("good then DONE: built, stop done", res["status"] == "built" and res["stop"] == "done")
    check("good then DONE: 2 turns, program from turn 1", res["turns_used"] == 2 and res["final_turn"] == 1)
    check("good then DONE: example ran clean", res["final_example_exit"] == 0 and res["final_example_lines"] == 80
          and res["final_example_bad_lines"] == 0)
    check("good then DONE: program text kept", res["program"] == GOOD)
    fb = [m for m in log if m["role"] == "user" and m["turn"] == 1][0]["content"]
    check("feedback shows head and tail, skips the middle", "[25 lines not shown]" in fb and "c0079" in fb
          and "c0039" in fb and "c0050" not in fb)
    check("feedback has no derived counts", "valid JSON" not in fb and "non-empty" not in fb)
    check("feedback counts turns left", "You have 2 more replies" in fb)
    sent = [m for m in log if m["role"] in ("system", "user")]
    check("model sees only system, spec and run output", len(sent) == 3 and SPEC in sent[1]["content"]
          and EXAMPLE not in "".join(m["content"] for m in sent))

    # no code first, then a crashing program, then turn limit with a fixed program
    res, log, runs, sb, cl = run_build(["I will think more.", block(CRASH), block(GOOD)])
    check("no code first: NO_CODE message sent", any("did not contain a complete" in m["content"] for m in log if m["role"] == "user"))
    check("crash reported with exit code and stderr", any("Exit code: 1" in m["content"] and "boom" in m["content"]
                                                          for m in log if m["role"] == "user"))
    check("non-JSON line counted", runs[0]["bad_lines"] == 1)
    check("last turn's program is run but gets no feedback", res["stop"] == "turn_limit" and res["final_turn"] == 3
          and len(runs) == 2 and log[-1]["role"] == "assistant")
    check("final program is the last one", res["program"] == GOOD and res["final_example_exit"] == 0)

    # last program crashes: still the build's program (no acceptance check)
    res, *_ = run_build([block(GOOD), block(CRASH)], turns=2)
    check("crashing last program is kept", res["status"] == "built" and res["program"] == CRASH and res["final_example_exit"] == 1)

    # never any code
    res, *_ = run_build(["no", "still no", "DONE"])
    check("no code at all: no_program", res["status"] == "no_program" and res["program"] is None)

    # prose reply after a program: the program stays current and the model is asked again
    res, log, *_ = run_build([block(GOOD), "Looks fine to me.", "DONE"])
    check("prose reply after a program: asked again, then DONE", res["stop"] == "done" and res["program"] == GOOD
          and any("still the current one" in m["content"] for m in log if m["role"] == "user"))

    # cut-off reply
    class CutClient(C.FakeClient):
        def llm(self, messages):
            t = super().llm(messages)
            self.calls[-1]["finish"] = "max_tokens"
            return t
    res, log, *_ = run_build(None, client=CutClient(["```python\nx = 1\n", block(GOOD), "DONE"]))
    check("cut-off reply named in the NO_CODE message", any("output limit" in m["content"] for m in log if m["role"] == "user"))
    res, log, *_ = run_build(None, client=CutClient([block(CRASH), "```python\nx = 1\n", block(GOOD)]))
    check("cut-off revision after a program gets another turn", res["program"] == GOOD and res["final_turn"] == 3
          and res["steps"][1]["action"] == "cut_off")

    # timeout
    res, log, runs, *_ = run_build([block(SLEEP)], turns=1, timeout=1)
    check("timeout recorded as exit None", res["final_example_exit"] is None and runs[0]["exit"] is None)
    check("timeout recorded as killed", res["final_example_killed"] is True and runs[0]["killed_by_timeout"] is True)
    check("timeout feedback wording", "stopped after the time limit" in C.feedback_text(C.summarize_run(None, "", "", 1.0, True), 1))
    check("exit 124 from the program itself is not called a timeout",
          "time limit" not in C.feedback_text(C.summarize_run(124, "", "", 1.0, False), 1))

    # local spending stop
    class Pricey(C.FakeClient):
        def llm(self, messages):
            t = super().llm(messages)
            self.calls[-1]["usd"] = 0.6
            return t
    def guard(messages, cl=None):
        return "over" if sum(c["usd"] for c in pricey.calls) + 0.6 > 1.0 else None
    pricey = Pricey([block(CRASH), block(CRASH), block(GOOD)])
    res, *_ = run_build(None, client=pricey, guard=guard)
    check("guard stops before the second call, status stopped_at_cap", res["status"] == "stopped_at_cap"
          and res["turns_used"] == 1 and res["stop"] == "over")

    # infrastructure stop
    class Boom(Exception):
        pass

    class Failing(C.FakeClient):
        def llm(self, messages):
            raise Boom("service down")
    tmp = Path(tempfile.mkdtemp())
    (tmp / "prog").mkdir()
    res = C.build(SPEC, EXAMPLE, Failing([]), LocalSandbox(tmp / "prog"), tmp, 3, None, {Boom: "infrastructure_failure"})
    check("client error gives its own status", res["status"] == "infrastructure_failure" and res["stop"].startswith("Boom"))
    check("horizon argument per domain", C.horizon_arg("WorkflowLoan", "{}") == "--horizon 100000000"
          and C.horizon_arg("Manufacturing", json.dumps({"days": [{"day": 1}, {"day": 9}]})) == "--horizon 9")

    # pattern scan
    tmp = Path(tempfile.mkdtemp())
    pat = tmp / "pat"
    pat.mkdir()
    (pat / "test_names.txt").write_text("Run 05\ntest-loan-05\n", encoding="utf-8")
    (pat / "test_draws.txt").write_text("0.123456\n", encoding="utf-8")
    b = tmp / "b"
    b.mkdir()
    (b / "run.py").write_text("x = 'Run 05'\ny = 0.123456\n", encoding="utf-8")
    (b / "build.json").write_text("test-loan-05", encoding="utf-8")
    old = C.PATTERNS
    C.PATTERNS = pat
    s = C.pattern_scan(b)
    C.PATTERNS = old
    check("pattern scan finds planted name and draw, skips build.json",
          s["files_naming_test"] == {"run.py": ["Run 05"]} and s["test_draw_strings"] == ["0.123456"])
    clean = tmp / "c"
    clean.mkdir()
    (clean / "run.py").write_text(GOOD, encoding="utf-8")
    C.PATTERNS = pat
    s = C.pattern_scan(clean)
    C.PATTERNS = old
    check("pattern scan clean folder", not s["files_naming_test"] and not s["test_draw_strings"])

    if "--wsl" in sys.argv:
        wsl_test()
    print(f"{len(FAILS)} failures")
    return 1 if FAILS else 0


def wsl_test():
    """One fake-model build through the real sandbox: write, run under bubblewrap, isolation before and after."""
    tmp = Path(tempfile.mkdtemp())
    prog = ("import sys, json, os, socket\nd = json.load(sys.stdin)\n"
            "print('mnt', os.path.exists('/mnt/c/Users'), 'gen', os.path.exists(os.path.expanduser('~/trust2027/gen')), file=sys.stderr)\n"
            "try:\n    socket.create_connection(('github.com', 443), timeout=3); print('net yes', file=sys.stderr)\n"
            "except OSError:\n    print('net no', file=sys.stderr)\n"
            "print('env', sorted(k for k in os.environ), file=sys.stderr)\n"
            "for c in d['cases']:\n    print(json.dumps({'time': 0, 'case': c['case'], 'event': 'case_end', 'name': '', 'visit': 0, 'worker': '', 'route': ''}))\n")
    replies = tmp / "replies.json"
    replies.write_text(json.dumps([block(prog), "DONE"]), encoding="utf-8")
    out = tmp / "fake-test" / "WorkflowLoan" / "b1"
    out.mkdir(parents=True)
    (out / "prompt_log.jsonl").write_text("{}\n", encoding="utf-8")        # an earlier, interrupted attempt
    rc = C.main(["fake-test", "WorkflowLoan", "1", "--fake-replies", str(replies), "--out-root", str(tmp)])
    rec = json.loads((out / "build.json").read_text(encoding="utf-8"))
    runs = [json.loads(l) for l in (out / "example_runs.jsonl").read_text(encoding="utf-8").splitlines()]
    err = runs[0]["stderr_tail"]
    check("wsl: build exit 0", rc == 0)
    check("wsl: built, example ran, 15 cases", rec["status"] == "built" and rec["final_example_exit"] == 0
          and rec["final_example_lines"] == 15)
    check("wsl: program cannot see /mnt/c or ~/trust2027/gen", "mnt False gen False" in err)
    check("wsl: no network", "net no" in err)
    check("wsl: environment cleared", "ANTHROPIC" not in err and "API_KEY" not in err)
    check("wsl: positive control and isolation before/after pass", rec["isolation"]["positive_control_exit"] == 0
          and rec["isolation"]["before_exit"] == 0 and rec["isolation"]["after_exit"] == 0)
    check("wsl: pattern scan ran, no hits", rec["pattern_scan"]["ran"] and not rec["pattern_scan"]["files_naming_test"]
          and not rec["pattern_scan"]["test_draw_strings"])
    check("wsl: no cost", rec["cost"]["usd"] == 0)
    check("wsl: earlier attempt kept, new build id", (out / "attempt_1" / "prompt_log.jsonl").exists()
          and rec["attempt"] == 2 and rec["build_id"].endswith("attempt2"))
    check("wsl: WSL run.py byte-identical to the local copy", rec["wsl_matches_local"] is True
          and rec["wsl_run_py_sha256"] == C.sha((out / "run.py").read_bytes()))
    check("wsl: record-only --horizon run made", rec["horizon_run"]["exit"] == 0 and rec["horizon_run"]["args"] == "--horizon 100000000")
    check("wsl: /home probe sees nothing extra", rec["isolation"]["after_home_extra"] == 0)
    check("wsl: isolation outputs kept in full", "35 of 35" in (out / "isolation_positive_control.txt").read_text(encoding="utf-8")
          and "0 findings" in (out / "isolation_before.txt").read_text(encoding="utf-8"))
    check("wsl: program_hash recorded", rec["program_hash"] and len(rec["program_hash"]) == 16)
    # the program folder is what DEVSBackend runs, unchanged
    sys.path[:0] = [str(ROOT)]
    from assurance.backends import DEVSBackend
    b = DEVSBackend(rec["wsl_dir"], "WorkflowLoan", ROOT)
    ex = b.run_input(json.loads((ROOT / "adapters/generic_tasks/WorkflowLoan/example_input.json").read_text(encoding="utf-8")))
    check("wsl: DEVSBackend runs the folder and reads case ends", ex.status == "ran" and len(ex.case_ends) == 15)
    check("wsl: DEVSBackend hashes the folder", len(b.program_hash()) == 16)
    subprocess.run(["wsl.exe", "-d", C.WSL_DISTRO, "--", "bash", "-c", f"rm -rf {C.WSL_BASE}/fake-test"],
                   env={**__import__('os').environ, "MSYS_NO_PATHCONV": "1"})


if __name__ == "__main__":
    sys.exit(main())
