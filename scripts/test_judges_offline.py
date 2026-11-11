"""Offline checks of the trust-judge baselines (scripts/judges.py) and the client changes in b0_build_test.py.

No model calls: a fake model and fake programs. Covers reply parsing, failure handling, what enters a prompt and
a sandbox (no gold, binding, reference path, other run, native verdict or build history), the prompt layout for
caching, the turn cap, the shared-subset draw, and that default client calls (builds) are unchanged.

The sandbox checks need WSL with bubblewrap (no model): isolation (no /run, session bus, Windows drive, network,
credentials or leftover processes), and real runs of an OTF-style, a DEVS-Gen-style and a coding-agent-style fake
program. Pass --no-wsl to skip them; they are then reported as SKIP, not as passes. Checks on real project data
(the main runner's dev interpretations) are skipped the same way when that data is absent.
Each check prints PASS or FAIL; the exit code is the number of failures.

Not covered here: the `run` loop itself (draw, resume, the --max-usd stop), which needs a model or a full fake of
the main runner's outputs. It is exercised by the dev smoke run.

Usage: python -X utf8 scripts/test_judges_offline.py [--no-wsl]
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
sys.dont_write_bytecode = True

import b0_build_test as bt   # noqa: E402
import judges as J           # noqa: E402

FAILS, SKIPS = [], []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def skip(name):
    print("SKIP " + name)
    SKIPS.append(name)


def raises(exc, fn) -> bool:
    try:
        fn()
    except exc:
        return True
    return False


# ---------------------------------------------------------------- fakes
GOLD, BINDING, OTHER_RUN, NATIVE, HISTORY = "987654321", "BINDING_SENTINEL", "OTHER_RUN_SENTINEL", "0.31415926", "BUILD_HISTORY_SENTINEL"
PATHS = ("reference_engine", "pilot_questions", "mlsys_gold", "document_meta", "gen_meta", "_analysis_logs", "quick_smoke")
SENTINELS = (GOLD, BINDING, OTHER_RUN, NATIVE, HISTORY, "manifests", "validation", "checker", ".env", "mean_f1", "attempts") + PATHS


def fake_nav():
    def table(i, title, cols, rows):
        return {"node_id": f"n{i:04d}", "title": title, "level": 1, "parent_id": None, "kind": "table", "pages": [1, 1],
                "table": {"columns": cols, "rows": rows}, "children": []}
    return {"document_id": "fake", "source_files": ["C:/somewhere/reference_engine/document.pdf"], "intro_text": "", "nodes": [
        {"node_id": "n0000", "title": "Loan Application Process Records", "level": 0, "parent_id": None, "kind": "list", "children": [],
         "pages": [1, 1], "lines": ["Front matter: the process rules.", "Clerk: 2 workers."]},
        {"node_id": "n0001", "title": "Run 01", "level": 0, "parent_id": None, "kind": "text", "pages": [1, 1], "text": "Run 01 has 3 cases.",
         "children": ["n0002", "n0003"]},
        table(2, "Run 01: Cases", ["case", "arrival", "end"], [["c0000", "100", "900"], ["c0001", "200", "1000"], ["c0002", "300", "1100"]]),
        table(3, "Run 01: Work plan", ["case", "activity", "visit 1"], [["c0000", "Check", "50"]]),
        {"node_id": "n0004", "title": "Run 02", "level": 0, "parent_id": None, "kind": "text", "pages": [2, 2], "text": OTHER_RUN, "children": ["n0005"]},
        table(5, "Run 02: Cases", ["case", "arrival", "end"], [["c0007", "100", OTHER_RUN]]),
    ]}


# An evaluation-side question row. Only its text may reach a judge.
QUESTION_ROW = {"id": "loa-x-00", "question": "In Run 01, suppose case c0000 needed 60 seconds for Check on visit 1. When would it end?",
                "gold": int(GOLD), "factual_end": 900, "effectful": True, "binding": {"family": "activity_duration", "target": BINDING},
                "interventions": [{"type": BINDING}]}
REQUEST = {"scope": "Run 01", "interventions": [{"family": "activity_duration", "op": "set", "case": "c0000", "target": "Check",
                                                 "visit": 1, "value": 60.0, "routes": None}],
           "query": {"kind": "case_end_time", "case": "c0000", "deadline": None}, "unresolved": None}

# A small program in the OTF platform's form: every case ends 800 after it arrives.
OTF_CODE = '''
def _cases(doc, scope):
    for n in scope_nodes(doc, scope):
        if n["title"].endswith(": Cases"):
            return n

def entities(doc, scope):
    return [{"id": row["case"], "description": "a case"} for i, row in table_rows(_cases(doc, scope))]

def recorded_end(doc, scope):
    return 1100.0

def inputs(doc, scope):
    node, out = _cases(doc, scope), []
    for i, row in table_rows(node):
        r = Reader()
        case, t = r.cell(node, i, "case"), float(r.cell(node, i, "arrival"))
        out.append({"id": "arrival-" + case, "time": t, "kind": "arrival", "entities": [case], "fields": {}, "src": r.src})
    return out

def outcomes(doc, scope):
    node, out = _cases(doc, scope), []
    for i, row in table_rows(node):
        r = Reader()
        case, end = r.cell(node, i, "case"), r.cell(node, i, "end")
        if end != "":
            out.append({"time": float(end), "kind": "case end", "entities": [case], "value": None, "src": r.src})
    return out

def simulate(doc, scope, inputs, params, start=None, horizon=None):
    return [{"time": x["time"] + 800.0, "kind": "case end", "entities": x["entities"], "value": None} for x in inputs]
'''


def fake_otf(tmp: Path) -> J.Program:
    p = tmp / "program.json"
    p.write_text(json.dumps({"code": OTF_CODE, "passed": True, "mean_f1": float(NATIVE), "tries": 5, "attempts": [HISTORY], "failed_step": None}))
    return J.otf_program(p, "r1", ROOT)


DEVS_FILES = {"run.py": "import subprocess, sys\nsys.exit(subprocess.run([sys.executable, '-m', 'devs_project.run_model'] + sys.argv[1:], stdin=sys.stdin).returncode)\n",
              "devs_project/model.py": "DELAY = 800\n",
              "devs_project/run_model.py": "import json, sys\nfrom devs_project.model import DELAY\nfor c in json.load(sys.stdin)['cases']:\n"
                                           "    print(json.dumps({'time': c['arrival'] + DELAY, 'case': c['case'], 'event': 'case_end'}))\n"}
STDIN = {"cases": [{"case": "c0000", "arrival": 100}, {"case": "c0001", "arrival": 200}]}


def fake_devs() -> J.Program:
    return J.devs_program("unused", files=dict(DEVS_FILES))


def views(tmp: Path):
    nav = fake_nav()
    otf = J.make_view(nav, "Run 01", fake_otf(tmp), 10 ** 8, QUESTION_ROW["question"], REQUEST, 910, 900)
    devs = J.make_view(nav, "Run 01", fake_devs(), 10 ** 8, QUESTION_ROW["question"], REQUEST, 910, 900, stdin=STDIN)
    return otf, devs


class FakeClient:
    """Scripted replies: each item is text, or (text, finish), or an exception to raise. The last one repeats."""

    def __init__(self, replies):
        self.replies, self.calls, self.prompts, self.kwargs, self.build_id = list(replies), [], [], [], None

    def llm(self, messages, empty_retries=2, stop=None, auto_cache=True):
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(r, Exception):
            raise r
        text, finish = r if isinstance(r, tuple) else (r, "end_turn")
        self.prompts.append(messages)
        self.kwargs.append({"stop": stop, "auto_cache": auto_cache})
        self.calls.append({"usd": 0.001, "prompt_tokens": 10, "output_tokens": 5, "finish": finish, "seconds": 0.1})
        return text


class FakeSandbox:
    def __init__(self, outputs=("ran",), counts_fail=False):
        self.outputs, self.codes, self.closed, self.counts_fail = list(outputs), [], False, counts_fail

    def run(self, code):
        self.codes.append(code)
        return {"output": self.outputs[min(len(self.codes), len(self.outputs)) - 1], "exit": 0, "timed_out": False, "seconds": 0.5}

    def counts(self):
        if self.counts_fail:
            raise OSError("WSL is not answering")
        return {"program_executions": len(self.codes), "python_starts": len(self.codes), "sandbox_log": []}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True


ACTION = "Thought: run it.\nAction: run_code\n```python\nprint(1)\n```"
FINAL = "Thought: done.\nVERDICT: TRUST\nCONFIDENCE: 80\nREASON: matches a rerun"


# ---------------------------------------------------------------- tests
def parsing_tests():
    pv = J.parse_verdict
    check("parse: plain verdict", pv("x\nVERDICT: TRUST\nCONFIDENCE: 85\nREASON: fine") == ("TRUST", 85, "fine"))
    check("parse: markdown bold and lower case", pv("**Verdict:** decline\n**Confidence:** 12%\n**Reason:** wrong pool") == ("DECLINE", 12, "wrong pool"))
    check("parse: a verdict in backticks or quotes", pv("VERDICT: `TRUST`\nCONFIDENCE: 60")[:2] == ("TRUST", 60) and pv('VERDICT: "DECLINE"\nCONFIDENCE: 10')[:2] == ("DECLINE", 10))
    check("parse: the last verdict wins", pv("VERDICT: TRUST\nCONFIDENCE: 90\nlater\nVERDICT: DECLINE\nCONFIDENCE: 20\nREASON: b")[:2] == ("DECLINE", 20))
    check("parse: a trailing period is accepted", pv("VERDICT: TRUST\nCONFIDENCE: 70.\nREASON: a")[:2] == ("TRUST", 70))
    check("parse: confidence above 100 is unparsable", pv("VERDICT: TRUST\nCONFIDENCE: 101\nREASON: a") is None)
    check("parse: a fractional confidence is unparsable", pv("VERDICT: TRUST\nCONFIDENCE: 85.5\nREASON: a") is None)
    check("parse: a missing confidence is unparsable", pv("VERDICT: TRUST\nREASON: a") is None)
    check("parse: a missing verdict is unparsable", pv("I think it is right. CONFIDENCE: 80") is None)
    check("parse: another word is not a verdict", pv("VERDICT: MAYBE\nCONFIDENCE: 50") is None and pv("VERDICT: TRUSTED\nCONFIDENCE: 50") is None)
    check("parse: an echo of the format line is not a verdict", pv("VERDICT: TRUST or DECLINE\nCONFIDENCE: 50\nREASON: one line") is None
          and pv("VERDICT: TRUST/DECLINE\nCONFIDENCE: 50") is None)
    check("parse: a real verdict after an echoed format line is read", pv("VERDICT: TRUST or DECLINE\nCONFIDENCE: 50\n\nVERDICT: DECLINE\nCONFIDENCE: 30\nREASON: r") == ("DECLINE", 30, "r"))
    check("parse: a missing reason is allowed", pv("VERDICT: DECLINE\nCONFIDENCE: 5") == ("DECLINE", 5, ""))
    check("parse: empty and None", pv("") is None and pv(None) is None)
    check("consistency: TRUST below 50 and DECLINE above 50 are flagged, the rest are not",
          J.inconsistent("TRUST", 49) and J.inconsistent("DECLINE", 95) and not J.inconsistent("TRUST", 50) and not J.inconsistent("DECLINE", 50)
          and not J.inconsistent("TRUST", 90) and not J.inconsistent("DECLINE", 5))
    pa = J.parse_action
    check("action: fenced code", pa(ACTION) == ("Thought: run it.\nAction: run_code", "print(1)"))
    check("action: text after the code block is dropped", pa(ACTION + "\nObservation: 1\nVERDICT: TRUST")[1] == "print(1)")
    check("action: an unclosed fence still gives the code", pa("Action: run_code\n```python\nprint(2)")[1] == "print(2)")
    check("action: no fence gives the rest of the reply", pa("Action: run_code\nprint(3)")[1] == "print(3)")
    check("action: none without an Action line", pa("Thought: x\n```python\nprint(1)\n```") is None)
    check("action: an empty action is none", pa("Action: run_code\n") is None)
    c = J.clip("a" * 3000 + "b" * 9000)
    check("clip: cut to the fixed length, head and tail kept", len(c) < J.OBS_CHARS + 60 and c.startswith("aaa") and c.endswith("bbb") and "characters cut" in c)
    check("clip: short text unchanged", J.clip("abc") == "abc")


def failure_tests(tmp):
    otf, _ = views(tmp)
    for label, reply, want in (("an empty reply", ("", "end_turn"), "unparsable"), ("free text", "It looks right to me.", "unparsable"),
                               ("an output cutoff", ("VERDICT: TRUST\nCONFIDENCE: 90", "max_tokens"), "cutoff"),
                               ("an Ollama length cutoff", ("partial", "length"), "cutoff"),
                               ("a refusal", ("", "refusal"), "refusal")):
        for judge, fn in (("answer", J.judge_answer), ("program", J.judge_program)):
            r = fn(FakeClient([reply]), otf)
            check(f"failure: {label} is DECLINE at the lowest confidence, recorded as {want} ({judge})",
                  (r["verdict"], r["confidence"], r["failure"]) == ("DECLINE", J.LOWEST_CONFIDENCE, want), str(r))
        r = J.judge_react(FakeClient([reply]), otf, FakeSandbox())
        check(f"failure: {label} is DECLINE at the lowest confidence, recorded as {want} (react)",
              (r["verdict"], r["confidence"], r["failure"]) == ("DECLINE", J.LOWEST_CONFIDENCE, want), str(r))
    r = J.judge_answer(FakeClient(["VERDICT: DECLINE\nCONFIDENCE: 15\nREASON: ignores the plan"]), otf)
    check("a parsed verdict has no failure", (r["verdict"], r["confidence"], r["failure"], r["reason"], r["inconsistent"]) == ("DECLINE", 15, None, "ignores the plan", False))
    check("cost fields, the full reply and the prompt hash are recorded", r["model_calls"] == 1 and abs(r["usd"] - 0.001) < 1e-9 and r["turns"] == 1
          and r["reply"].startswith("VERDICT") and r["prompt_hash"] == J.PROMPT_HASH and len(J.PROMPT_HASH) == 16)
    r = J.judge_answer(FakeClient(["VERDICT: DECLINE\nCONFIDENCE: 95\nREASON: sure it is wrong"]), otf)
    check("a verdict that disagrees with its confidence is kept as given and flagged", (r["verdict"], r["confidence"], r["inconsistent"]) == ("DECLINE", 95, True))
    r = J.judge_answer(FakeClient([("", "refusal")]), otf)
    check("a failure is never flagged as inconsistent", r["inconsistent"] is False)
    for fn in (J.judge_answer, J.judge_program):
        check("a service failure is raised, not recorded as a verdict", raises(bt.InfrastructureFailure, lambda: fn(FakeClient([bt.InfrastructureFailure("busy")]), otf)))
    check("the spending stop is raised, not recorded as a verdict (react)", raises(bt.CapReached, lambda: J.judge_react(FakeClient([bt.CapReached("cap")]), otf, FakeSandbox())))
    no_answer = J.make_view(fake_nav(), "Run 01", fake_otf(tmp), 10 ** 8, QUESTION_ROW["question"], REQUEST, None, 900)
    for judge in ("answer", "react"):
        c = FakeClient([FINAL])
        r = J.judge_row(judge, c, no_answer, sandbox_factory=lambda v: FakeSandbox())
        check(f"a row without an answer is not judged and costs nothing ({judge})", r["status"] == "no_answer" and not c.calls and r["verdict"] is None)
    r = J.judge_row("program", FakeClient([FINAL]), no_answer)
    check("the program-level judge does not need an answer", r["status"] == "judged" and r["verdict"] == "TRUST")
    box = []
    failed = raises(bt.InfrastructureFailure, lambda: J.judge_row("react", FakeClient([ACTION, bt.InfrastructureFailure("busy")]), otf,
                                                                  sandbox_factory=lambda v: box.append(FakeSandbox()) or box[0]))
    check("a service failure in the middle of a ReAct row is raised and the sandbox is still closed", failed and box and box[0].closed and len(box[0].codes) == 1)


def leakage_tests(tmp):
    otf, devs = views(tmp)
    for name, view in (("otf", otf), ("devs", devs)):
        prompts = {"answer": J.answer_prompt(view), "program": J.program_prompt(view),
                   "react": J.react_prompt(view, ["Thought: a\nAction: run_code\n```python\nx\n```\nObservation:\nout\n\n"])}
        for judge, msgs in prompts.items():
            text = J.prompt_text(msgs)
            hit = [s for s in SENTINELS if s in text]
            check(f"leak: no gold, binding, other run, native verdict, build history or evaluation path in the {judge} prompt ({name})", not hit, str(hit))
        files = J.sandbox_files(view)
        blob = "\n".join(f"{k}\n{v}" for k, v in files.items() if not k.startswith("box/otf_runtime/"))
        hit = [s for s in SENTINELS if s in blob]
        check(f"leak: none of them in the sandbox files ({name})", not hit, str(hit))
        runtime = "\n".join(f"{k}\n{v}" for k, v in files.items() if k.startswith("box/otf_runtime/"))
        hit = [s for s in (GOLD, BINDING, OTHER_RUN, NATIVE, HISTORY) + PATHS if s in runtime]
        check(f"leak: the platform runtime in the sandbox holds no sentinel or evaluation path ({name})", not hit, str(hit))
        check(f"leak: the queried run is in the prompt, the other run is not ({name})",
              "Run 01: Cases" in J.prompt_text(prompts["answer"]) and "Run 02" not in J.prompt_text(prompts["answer"]))
        check(f"leak: the sandbox map holds only the front matter and the queried run ({name})",
              [n["title"] for n in json.loads(files["box/document/navmap.json"])["nodes"]] ==
              ["Loan Application Process Records", "Run 01", "Run 01: Cases", "Run 01: Work plan"])
    check("leak: the program-level prompt has no question, request or answer",
          QUESTION_ROW["question"] not in J.prompt_text(J.program_prompt(otf)) and "910" not in J.prompt_text(J.program_prompt(otf)))
    check("view: the answer-level prompt has the question, the request and both answers",
          all(s in J.prompt_text(J.answer_prompt(otf)) for s in (QUESTION_ROW["question"], '"target": "Check"', "With the change: 910", "run of the recorded inputs): 900")))
    check("view: None fields of the request are dropped", "routes" not in json.dumps(otf.request) and "unresolved" not in json.dumps(otf.request))
    check("view: OTF shows only the code field", list(otf.program.shown) == ["program.py"] and "def simulate" in otf.program.shown["program.py"])
    check("view: DEVS-Gen shows the model files, not the launcher", sorted(devs.program.shown) == ["devs_project/model.py", "devs_project/run_model.py"]
          and "subprocess.run([sys.executable" not in J.prompt_text(J.answer_prompt(devs)) and list(devs.program.runtime) == ["run.py"])
    for bad in ("devs_project/_analysis_logs/llm_call_summary.json", "gen_meta.json", "quick_smoke_stdout.txt", "../outside.py", "build_log.txt",
                "attempt_1/run.py", "prompt_log.jsonl", "build.json"):
        check(f"view: a file named {bad} is refused", raises(J.ViewError, lambda: J.make_view(
            fake_nav(), "Run 01", J.Program("devs_gen", {"devs_project/m.py": "x", bad: "y"}, {"run.py": "z"}), 1, "q", REQUEST, 1, 1, stdin={})))
    check("view: an oversized program is refused, not cut", raises(J.ViewError, lambda: J.make_view(
        fake_nav(), "Run 01", J.Program("coding_agent", {"run.py": "x" * (J.PROGRAM_CHAR_LIMIT + 1)}), 1, "q", REQUEST, 1, 1, stdin={})))
    # coding agent build folder: only run.py is read, never the prompt log, example runs or earlier attempts
    d = tmp / "agent"
    (d / "attempt_1").mkdir(parents=True)
    for rel, text in (("run.py", "Y = 2\n"), ("attempt_1/run.py", HISTORY), ("prompt_log.jsonl", HISTORY), ("example_runs.jsonl", HISTORY),
                      ("build.json", HISTORY)):
        (d / rel).write_text(text)
    agent = J.coding_agent_program(str(d), wsl=False)
    check("view: a coding-agent program is run.py alone, not its build folder", agent.shown == {"run.py": "Y = 2\n"} and not agent.runtime)
    check("view: extra coding-agent files are refused", raises(J.ViewError, lambda: J.coding_agent_program("unused", files={"run.py": "x", "attempt_1/run.py": HISTORY})))
    missing = J.document_view(fake_nav(), "Run 99")
    check("view: an unknown run gives the front matter alone", "Run 01" not in missing[0] and len(missing[1]["nodes"]) == 1 and "no chapter" in missing[0])
    spec = J.stdin_spec("WorkflowLoan", ROOT)
    check("view: the input format note has the fields and the output format, without the long example or the scenario",
          "route_probabilities" in spec and "Output Data Format" in spec and '"case": "c0000"' not in spec and "Scenario" not in spec and len(spec) < 6000, str(len(spec)))
    src = (ROOT / "scripts" / "judges.py").read_text(encoding="utf-8")
    hits = [l.strip() for l in src.splitlines() if any(k in l for k in ('["gold', '"gold"', "'gold'", '["binding', '"binding"', "factual_end",
                                                                          "effectful", "oracle", "request_from_binding", "reference_engine"))]
    check("leak: judges.py never reads gold, bindings, effect labels, the oracle source or the reference", not hits, str(hits[:3]))


def real_data_tests():
    """Rows built from the main runner's dev outputs, with a real OTF program run locally. No model, no WSL."""
    name = "rows: question rows are cut down to id, document, text and family"
    if not (ROOT / "runs" / "main_v1" / "wf_dev" / "interpret.jsonl").exists():
        for n in (name, "rows: the run comes from the interpretation and only that run is shown", "rows: a real row has both answers and the gate's request"):
            skip(n + " (no main-run dev interpretations on this disk)")
        return
    rows = J.Rows(ROOT, "wf_dev")
    check(name, bool(rows.questions) and all(set(q) == {"id", "doc", "question", "family"} for q in rows.questions), str(len(rows.questions)))
    check("rows: B0 (native-only) programs are left out", all(not p["native_only"] and "/b0" not in p["name"] for p in rows.programs))
    prog = next((p for p in rows.programs if p["name"].startswith("otf/r1_claude/") and "loan" in p["name"]), None)
    q = next((q for q in rows.questions if q["doc"] == "workflow_loan_dev"), None)
    if prog is None or q is None:
        skip("rows: a real row (no Claude OTF loan program on this disk)")
        return
    view, info = rows.view(prog, q)
    req, schema, ad = rows.request(q)
    text = J.prompt_text(J.answer_prompt(view))
    others = [s for s in schema.scopes if s != req.scope]
    check("rows: the run comes from the interpretation and only that run is shown", view.scope == req.scope and f"## {req.scope}: Cases" in text
          and not any(f"## {s}: Cases" in text for s in others), view.scope)
    check("rows: a real row has both answers and the gate's request", view.answer_changed is not None and view.answer_factual is not None
          and view.request == J._plain(req) and info.get("structured") == "ran", str(info)[:200])
    hit = [s for s in ("reference_engine", "pilot_questions", "manifests", "document_meta", "mean_f1", '"passed"') if s in text]
    check("rows: a real prompt names no evaluation path or native result", not hit, str(hit))
    check("rows: cohorts are read from program names", J.cohort_of("otf/r1_claude/claude-haiku-5-5/workflow_loan_dev/b1") == "otf/r1_claude/claude-haiku-5-5"
          and J.cohort_of("devs/haiku/workflow_loan_dev/run_02") == "devs/haiku" and J.cohort_of("agent/claude-haiku-5-5/WorkflowLoan/b1") == "agent/claude-haiku-5-5")


def layout_tests(tmp):
    otf, devs = views(tmp)
    a, p = J.answer_prompt(otf), J.program_prompt(otf)
    scratch = ["Thought: a\nAction: run_code\n```python\nx\n```\nObservation:\n[turn 1 of 8 used]\nout\n\n",
               "Thought: b\nAction: run_code\n```python\ny\n```\nObservation:\n[turn 2 of 8 used]\nout\n\n"]
    r = J.react_prompt(otf, scratch)
    blocks = a[0]["content"]
    check("layout: document, then program, then task", len(blocks) == 3 and blocks[0]["text"].startswith("DOCUMENT") and blocks[1]["text"].startswith("PROGRAM")
          and "QUESTION" in blocks[2]["text"])
    check("layout: cache breakpoints after the document and after the program, none on the task",
          blocks[0].get("cache_control") == {"type": "ephemeral"} and blocks[1].get("cache_control") == {"type": "ephemeral"} and "cache_control" not in blocks[2])
    check("layout: the three judges share the document and program blocks byte for byte",
          a[0]["content"][:2] == p[0]["content"][:2] == r[0]["content"][:2])
    other = J.make_view(fake_nav(), "Run 01", otf.program, 10 ** 8, "Another question?", REQUEST, 5, 6)
    check("layout: two rows on one program and run share the cached prefix", J.answer_prompt(other)[0]["content"][:2] == blocks[:2]
          and J.answer_prompt(other)[0]["content"][2] != blocks[2])
    check("layout: two programs on one run share the document block", J.answer_prompt(devs)[0]["content"][0] == blocks[0]
          and J.answer_prompt(devs)[0]["content"][1] != blocks[1])
    check("layout: with a transcript, at most four cache breakpoints counting the request-level one",
          len(r[0]["content"]) == 5 and sum("cache_control" in b for b in r[0]["content"]) == 2)
    check("layout: every block before the last ends in a blank line, so joined text is the same for every service",
          all(b["text"].endswith("\n\n") for b in r[0]["content"][:-1]) and all(b["text"].endswith("\n\n") for b in a[0]["content"][:-1])
          and bt.content_text(r[0]["content"]) == J.prompt_text(r) and "\n\n\n\n" not in J.prompt_text(r))
    task = r[0]["content"][2]["text"].lower()
    check("layout: the ReAct prompt names no way to test", not any(w in task for w in ("probe", "witness", "replay", "perturb", "--params", "constants to replace")))
    check("layout: the ReAct prompt lists the tool's own folder and the turn limit", ".rt/" in task and "at most 8 turns" in task)
    check("layout: the stdin layout names the launcher only for DEVS-Gen",
          "its launcher run.py" in J.react_prompt(devs, [])[0]["content"][2]["text"]
          and "the program run.py shown above" in J.react_prompt(J.make_view(fake_nav(), "Run 01", J.coding_agent_program("x", files={"run.py": "x"}), 5, "q", REQUEST, 1, 1, stdin={}), [])[0]["content"][2]["text"])
    check("layout: the program-level wording asks the same exact-match question as the answer level, without 'only if'",
          "would be exactly right" in J.PROGRAM_TASK and "only if" not in J.PROGRAM_TASK)


def react_tests(tmp):
    otf, _ = views(tmp)
    c, sb = FakeClient([ACTION]), FakeSandbox()
    r = J.judge_react(c, otf, sb)
    check("turn cap: a judge that only acts is stopped after 8 turns", r["turns"] == J.TURN_CAP == 8 and len(c.calls) == 8 and r["model_calls"] == 8)
    check("turn cap: running out of turns is DECLINE at the lowest confidence, recorded apart",
          (r["verdict"], r["confidence"], r["failure"]) == ("DECLINE", 0, "out_of_turns"))
    check("turn cap: the last turn's code is not run", len(sb.codes) == 7 and r["sandbox_calls"] == 7)
    c, sb = FakeClient([ACTION] * 7 + [ACTION + "\nVERDICT: DECLINE\nCONFIDENCE: 30\nREASON: could not confirm"]), FakeSandbox()
    r = J.judge_react(c, otf, sb)
    check("turn cap: a verdict given with an action on the last turn stands, and the action is not run",
          (r["verdict"], r["confidence"], r["failure"], r["turns"], len(sb.codes)) == ("DECLINE", 30, None, 8, 7) and r.get("last_turn_action_ignored") is True, str(r)[:200])
    c, sb = FakeClient([ACTION, ACTION, FINAL]), FakeSandbox(["first", "second"])
    r = J.judge_react(c, otf, sb)
    check("react: a verdict on turn 3 ends the loop", (r["verdict"], r["confidence"], r["failure"], r["turns"], r["sandbox_calls"]) == ("TRUST", 80, None, 3, 2))
    check("react: sandbox calls, program executions and wall time are logged",
          r["program_executions"] == 2 and r["sandbox_seconds"] == 1.0 and "wall_seconds" in r and len(r["transcript"]) == 3)
    check("react: every call carries the stop sequence", all(k["stop"] == ["\nObservation:"] for k in c.kwargs))
    check("react: the growing transcript uses the request-level cache breakpoint", all(k["auto_cache"] for k in c.kwargs))
    third = c.prompts[2][0]["content"]
    check("react: observations come back in order", len(third) == 5 and "first" in third[3]["text"] and "second" in third[4]["text"]
          and "[turn 2 of 8 used]" in third[4]["text"])
    check("react: earlier blocks never change between turns", c.prompts[1][0]["content"] == third[:4] and c.prompts[0][0]["content"] == third[:3])
    c, sb = FakeClient([ACTION + "\nObservation:\nall good\nVERDICT: TRUST\nCONFIDENCE: 99\nREASON: invented", FINAL]), FakeSandbox(["real output"])
    r = J.judge_react(c, otf, sb)
    seen = c.prompts[1][0]["content"][3]["text"]
    check("react: before the last turn, an action wins over a verdict written in the same reply", r["turns"] == 2 and r["confidence"] == 80 and sb.codes == ["print(1)"])
    check("react: an observation the model wrote itself is dropped", "all good" not in seen and "invented" not in seen and "real output" in seen)
    c = FakeClient(["Thought: hmm, not sure what to do.", FINAL])
    r = J.judge_react(c, otf, FakeSandbox())
    check("react: a reply with neither action nor verdict uses a turn", r["turns"] == 2 and r["verdict"] == "TRUST" and r["sandbox_calls"] == 0)
    r = J.judge_react(FakeClient(["Thought: nothing."]), otf, FakeSandbox())
    check("react: eight replies with neither end as unparsable", (r["failure"], r["turns"], r["verdict"]) == ("unparsable", 8, "DECLINE"))
    c, sb = FakeClient([ACTION, ACTION, ("Thought: a very long", "max_tokens")]), FakeSandbox()
    r = J.judge_react(c, otf, sb)
    check("react: a cutoff on a later turn is recorded as a cutoff, with the earlier work counted",
          (r["failure"], r["turns"], r["sandbox_calls"], r["model_calls"]) == ("cutoff", 3, 2, 3))
    c, sb = FakeClient([ACTION, FINAL]), FakeSandbox(["z" * 50000])
    J.judge_react(c, otf, sb)
    check("react: a long result is cut to the fixed length", len(c.prompts[1][0]["content"][3]["text"]) < J.OBS_CHARS + 300)
    c = FakeClient([FINAL])
    r = J.judge_react(c, otf, FakeSandbox())
    check("react: a judge may give its verdict without running anything", r["turns"] == 1 and r["sandbox_calls"] == 0 and r["verdict"] == "TRUST")
    r = J.judge_react(FakeClient([ACTION, FINAL]), otf, FakeSandbox(counts_fail=True))
    check("react: a failure while counting executions does not lose the judged row", r["verdict"] == "TRUST" and r["program_executions"] is None and "counts_error" in r)
    c = FakeClient([FINAL])
    J.judge_answer(c, otf)
    check("single-call judges place their own breakpoints only and pass no stop sequence", c.kwargs == [{"stop": None, "auto_cache": False}])
    box = []
    r = J.judge_row("react", FakeClient([FINAL]), otf, sandbox_factory=lambda v: box.append(FakeSandbox()) or box[0])
    check("react: the sandbox is closed after the row", box and box[0].closed and r["status"] == "judged")


def sandbox_file_tests(tmp):
    otf, devs = views(tmp)
    f = J.sandbox_files(otf)
    runtime = {f"box/otf_runtime/otf_r1/{p.name}" for p in (ROOT / "redesign" / "otf_r1").glob("*.py")}
    check("sandbox: an OTF sandbox holds the document view, the program, its runtime and the harness, and nothing else",
          set(f) == {"box/document/document.txt", "box/document/navmap.json", "box/program/program.py", "box/program/otf_run.py",
                     "rt/sitecustomize.py", "rt/exec.sh"} | runtime, str(sorted(f)))
    check("sandbox: the OTF launcher takes the scope and the map, and no way to replace constants", "--params" not in f["box/program/otf_run.py"]
          and "HORIZON = 100000000" in f["box/program/otf_run.py"])
    f = J.sandbox_files(devs)
    check("sandbox: a stdin sandbox holds the document view, the run's input, the program and the harness, and nothing else",
          set(f) == {"box/document/document.txt", "box/document/navmap.json", "box/document/input.json", "box/program/run.py",
                     "box/program/devs_project/model.py", "box/program/devs_project/run_model.py", "rt/sitecustomize.py", "rt/exec.sh"}, str(sorted(f)))
    cmd = J.bwrap("$HOME/x", "true")
    check("sandbox: the command mounts no host root, /run, /var or /mnt, and unshares every namespace",
          "--ro-bind / /" not in cmd and " /run" not in cmd and " /var" not in cmd and " /mnt" not in cmd
          and all(s in cmd for s in ("--unshare-all", "--clearenv", "--die-with-parent", "--new-session", "--tmpfs /home", "--ro-bind /usr /usr", "--tmpfs /usr/lib/wsl", "--bind $HOME/x/box /home/sandbox",
                                   "--ro-bind $HOME/x/rt /home/rt", "os.closerange(3, 65536)")))
    check("sandbox: no API key or project path is passed in", "ANTHROPIC" not in cmd and "/mnt/c" not in cmd and "OLLAMA" not in cmd)
    check("sandbox: the command loads the socket filter on descriptor 10, refuses to start without it, and sets the soft limits",
          all(s in cmd for s in ("--seccomp 10", "os.dup2(fd, 10)", "$HOME/trust2027/tools/seccomp_unix_only.bpf", "exit 97",
                                 '/bin/bash -c "ulimit -S -v 8388608 -u 4096 -f 4194304 && exec true"'))
          and cmd.startswith("[ -s $HOME/trust2027/tools/seccomp_unix_only.bpf ] || "), cmd[:300])
    bad = []
    for folder, inner in (("$HOME/x y", "true"), ("$HOME/x'; id; '", "true"), ("$HOME/x", 'true"; id; "'), ("$HOME/x", "echo $(id)")):
        try:
            J.bwrap(folder, inner)
            bad.append((folder, inner))
        except (J.ViewError, ValueError):
            pass
    check("sandbox: a folder or command that would need shell quoting is refused", not bad, str(bad))
    ce = J.count_executions
    check("count: OTF runs through the launcher", ce("otf", [["python", "program/otf_run.py", "--scope", "Run 01"], ["python", "snippet_01.py"]]) == 1)
    check("count: a DEVS-Gen run through run.py counts once", ce("devs_gen", [["python", "run.py", "--horizon", "9"], ["/x/python", "-m", "devs_project.run_model", "--horizon", "9"]]) == 1)
    check("count: a coding-agent run", ce("coding_agent", [["python", "/home/sandbox/program/run.py"], ["python", "x.py"]]) == 1)


def subset_tests():
    rows = [{"row_id": f"p{p}|q{q}", "cohort": f"c{p % 3}", "family": f"f{q % 4}", "gold": p * q} for p in range(6) for q in range(20)]
    a = J.subset(rows, 30, 7)
    check("subset: the requested size, no duplicates", len(a) == 30 == len(set(a)))
    check("subset: the same draw for any input order", a == J.subset(list(reversed(rows)), 30, 7))
    check("subset: only row id, cohort and family are read", a == J.subset([{k: r[k] for k in ("row_id", "cohort", "family")} for r in rows], 30, 7))
    check("subset: another seed gives another draw", a != J.subset(rows, 30, 8))
    by = {}
    for r in rows:
        if r["row_id"] in a:
            by[(r["cohort"], r["family"])] = by.get((r["cohort"], r["family"]), 0) + 1
    check("subset: every stratum is represented in proportion", len(by) == 12 and set(by.values()) <= {2, 3})
    check("subset: asking for more than exist returns all", len(J.subset(rows, 10 ** 6, 7)) == 120)
    check("subset: with equal strata, one per stratum is contained in two per stratum", set(J.subset(rows, 12, 7)) < set(J.subset(rows, 24, 7))
          and len(J.subset(rows, 12, 7)) == 12)
    check("subset: a row id listed twice is refused", raises(ValueError, lambda: J.subset(rows + [dict(rows[0], cohort="other")], 5, 7)))
    check("subset: a missing family is its own stratum", len(J.subset([{"row_id": "a", "cohort": "c", "family": None}, {"row_id": "b", "cohort": "c", "family": "f"}], 2, 1)) == 2)
    check("subset: nothing asked gives nothing", J.subset(rows, 0, 7) == [])
    keys = [("wf_test", f"doc{d}", f"Run {r:02d}") for d in range(4) for r in range(40)]
    parts = [J.shard_of(*k, 8) for k in keys]
    check("shard: every run falls in exactly one of the parts, the same on every call, and every part is used",
          parts == [J.shard_of(*k, 8) for k in keys] and set(parts) == set(range(8)) and all(J.shard_of(*k, 1) == 0 for k in keys))


def frozen_subset_tests(tmp):
    """The D27 draw: nested subsets, frozen with their hashes, from answered rows only."""
    rows = [{"row_id": f"wf_test|otf/r1/m{p % 4}/doc/b{p}|q{q}", "set": "wf_test", "program": f"otf/r1/m{p % 4}/doc/b{p}", "question": f"q{q}",
             "process": "loan" if p % 2 else "pharmacy", "cohort": f"{'loan' if p % 2 else 'pharmacy'}|otf/r1/m{p % 4}", "family": f"f{q % 5}"}
            for p in range(12) for q in range(50)]
    sizes = (("answer_haiku", 300), ("react_haiku", 100), ("answer_sonnet", 15))
    d = J.draw_subsets(rows, sizes, 11)
    a, r, s = (set(d[k]) for k in ("answer_haiku", "react_haiku", "answer_sonnet"))
    check("D27 draw: the asked sizes", (len(a), len(r), len(s)) == (300, 100, 15))
    check("D27 draw: nested, so every judge sees the Sonnet rows", s < r < a)
    check("D27 draw: the same for any input order, and different for another seed", d == J.draw_subsets(list(reversed(rows)), sizes, 11) and d != J.draw_subsets(rows, sizes, 12))
    strata = {(x["cohort"], x["family"]) for x in rows}
    hit = {(x["cohort"], x["family"]) for x in rows if x["row_id"] in r}
    check("D27 draw: every process, cohort and family stratum is in the ReAct subset", hit == strata, f"{len(hit)} of {len(strata)}")
    check("D27 draw: the default sizes and nesting order are the decided ones", J.SUBSET_SIZES == (("answer_haiku", 3000), ("react_haiku", 1000), ("answer_sonnet", 150)))
    check("D27 draw: fewer answered rows than asked gives them all", len(J.draw_subsets(rows[:40], sizes, 11)["answer_haiku"]) == 40)
    real, path = J.answered_rows, tmp / "subsets" / "judge_subsets.json"
    try:
        J.answered_rows = lambda root, qsets: list(rows)
        first = J.freeze_subsets(ROOT, ("wf_test",), path, sizes, 11)
        text = path.read_text(encoding="utf-8")
        doc = json.loads(text)
        check("frozen: the file holds the ids with their sha256, the seed and the population's hash",
              first["status"] == "written" and doc["seed"] == 11 and doc["population"]["rows"] == 600 and len(doc["population"]["sha256"]) == 64
              and all(J._sha("\n".join(v["ids"])) == v["sha256"] for v in doc["subsets"].values()) and doc["subsets"]["react_haiku"]["n"] == 100)
        side = path.with_name(path.name + ".sha256").read_text(encoding="utf-8")
        check("frozen: a sidecar records the file's hash and when it was drawn", side.split()[0] == J._sha(text) == first["file_sha256"] and "drawn 20" in side)
        check("frozen: nothing about correctness is stored", not any(k in text for k in ("gold", "correct", "answer\":", "binding")))
        again = J.freeze_subsets(ROOT, ("wf_test",), path, sizes, 11)
        check("frozen: a second draw from the same rows changes nothing", again["status"] == "unchanged" and path.read_text(encoding="utf-8") == text)
        J.answered_rows = lambda root, qsets: list(rows[:-1])
        check("frozen: a draw from changed rows is refused and the file is kept", raises(SystemExit, lambda: J.freeze_subsets(ROOT, ("wf_test",), path, sizes, 11))
              and path.read_text(encoding="utf-8") == text)
        ids, sha = J.load_subset(path, "answer_sonnet")
        check("frozen: a subset loads with the file's hash", ids == s and sha == J._sha(text))
        path.write_text(text.replace(sorted(s)[0], sorted(a - r)[0], 1), encoding="utf-8")
        check("frozen: an edited file is refused", raises(SystemExit, lambda: J.load_subset(path, "answer_sonnet")))
    finally:
        J.answered_rows = real
    if (ROOT / "runs" / "main_v1" / "wf_dev" / "programs").exists():
        got = J.answered_rows(ROOT, ("wf_dev",))
        check("answered rows: from the main run's program rows, with ids and stratum labels only, each once",
              bool(got) and all(set(x) == {"row_id", "set", "program", "question", "process", "cohort", "family"} for x in got)
              and len({x["row_id"] for x in got}) == len(got) and all("/b0" not in x["program"] for x in got), str(len(got)))
    else:
        skip("answered rows: from the main run's program rows (no dev program rows on this disk)")


def client_tests(tmp):
    blocks = [{"type": "text", "text": "abcde\n\n", "cache_control": {"type": "ephemeral"}}, {"type": "text", "text": "fgh"}]
    check("client: prompt_chars counts characters of list content, not blocks", bt.prompt_chars([{"role": "user", "content": blocks}]) == 10)
    check("client: prompt_chars of string content is unchanged", bt.prompt_chars([{"role": "system", "content": "ab"}, {"role": "user", "content": "cde"}]) == 5)
    check("client: blocks are joined as they are", bt.content_text(blocks) == "abcde\n\nfgh" and bt.content_text("plain") == "plain" and bt.content_text(None) == "")
    check("client: the Claude stop is $25", bt.CLAUDE_CAP_USD == 25.00)
    check("client: builds keep the 16k output cap; per-question calls get 64k", bt.MAX_OUTPUT == 16384 and bt.MAX_OUTPUT_PER_QUESTION == 64000)
    import anthropic
    seen = []

    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            usage = type("U", (), {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0})()
            block = type("B", (), {"type": "text", "text": "ok"})()
            return type("M", (), {"content": [block], "usage": usage, "stop_reason": "end_turn"})()

    class FakeAnthropic:
        def __init__(self, **kw):
            self.messages = self

        def stream(self, **kw):
            seen.append(kw)
            return FakeStream()

    real = anthropic.Anthropic
    anthropic.Anthropic = FakeAnthropic
    try:
        env = {"ANTHROPIC_API_KEY": "k"}
        build = bt.Client("claude-haiku-5-5", env, bt.Ledger(tmp / "ledgers" / "build_test_x", "claude-haiku-5-5"))
        text = build.llm([{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}])
        check("client: a default (build) call sends exactly what it sent before",
              text == "ok" and seen[-1] == {"model": "claude-haiku-5-5", "max_tokens": 16384, "messages": [{"role": "user", "content": "hello"}],
                                           "thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"},
                                           "cache_control": {"type": "ephemeral"}, "system": "sys"}, str(seen[-1]))
        judge = bt.Client("claude-haiku-5-5", env, bt.Ledger(tmp / "ledgers" / "build_test_judges", "claude-haiku-5-5"), max_output=bt.MAX_OUTPUT_PER_QUESTION)
        judge.llm([{"role": "user", "content": blocks}], stop=["\nObservation:"], auto_cache=False)
        kw = seen[-1]
        check("client: a judge call sends the blocks with their breakpoints, the stop sequence and the 64k cap",
              kw["messages"][0]["content"] == blocks and kw["stop_sequences"] == ["\nObservation:"] and kw["max_tokens"] == 64000 and "cache_control" not in kw)
        judge.llm([{"role": "user", "content": blocks}], stop=["\nObservation:"], auto_cache=True)
        check("client: a ReAct call adds the request-level breakpoint to the blocks' own",
              seen[-1]["cache_control"] == {"type": "ephemeral"} and seen[-1]["messages"][0]["content"] == blocks)
        check("client: the ledger records characters for list content", judge.calls[-1]["prompt_chars"] == 10)
        # a judges-folder ledger counts toward the shared Claude stop, and a half-written line does not crash the count
        led = tmp / "ledgers" / "build_test_judges" / "calls_claude-haiku-5-5.jsonl"
        before = len(seen)
        with led.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"build": "judges/x/answer/r", "usd": 24.9}) + "\n" + '{"build": "judges/x/answer/r2", "us')
        check("client: judge spend counts toward the $25 stop, and the stop is raised before any call",
              raises(bt.CapReached, lambda: build.llm([{"role": "user", "content": "hello"}])) and len(seen) == before
              and abs(build.ledger.spent() - judge.ledger.spent()) < 1e-9 and judge.ledger.spent() > 24.9)
    finally:
        anthropic.Anthropic = real
    oll = bt.Client("gpt-oss-120b", {"OLLAMA_API_KEY": "k"}, None, max_output=bt.MAX_OUTPUT_PER_QUESTION)
    body = json.loads(oll._request([{"role": "user", "content": blocks}], stop=["\nObservation:"]).data)
    check("client: Ollama gets the blocks as one string, with the stop sequence",
          body["messages"] == [{"role": "user", "content": "abcde\n\nfgh"}] and body["options"]["stop"] == ["\nObservation:"] and body["options"]["num_predict"] == 64000)
    plain = bt.Client("gpt-oss-120b", {"OLLAMA_API_KEY": "k"}, None)
    body = json.loads(plain._request([{"role": "user", "content": "plain"}]).data)
    s = bt.SETUPS["gpt-oss-120b"]
    check("client: a default Ollama (build) request is unchanged", body == {
        "model": "gpt-oss:120b", "stream": False, "think": s["think"], "messages": [{"role": "user", "content": "plain"}],
        "options": {**s["options"], "num_predict": 16384, "num_ctx": bt.NUM_CTX}}, str(body))
    router = bt.Client("gemma-26b-openrouter-free", {"OPENROUTER_API_KEY": "k"}, None)
    o = bt.SETUPS["gemma-26b-openrouter-free"]["options"]
    body = json.loads(router._request([{"role": "user", "content": "plain"}]).data)
    check("client: a default OpenRouter (build) request is unchanged", body == {
        "model": "google/gemma-4-26b-a4b-it:free", "max_tokens": 16384, "reasoning": {"enabled": True}, "messages": [{"role": "user", "content": "plain"}],
        "temperature": o["temperature"], "top_p": o["top_p"], "top_k": o["top_k"]}, str(body))
    body = json.loads(router._request([{"role": "user", "content": blocks}], stop=["\nObservation:"]).data)
    check("client: OpenRouter gets the stop sequence and one string", body["stop"] == ["\nObservation:"] and body["messages"][0]["content"] == "abcde\n\nfgh")
    old = bt.MAX_OUTPUT
    try:
        bt.MAX_OUTPUT = 32000        # what scripts/coding_agent_build.py does in its own process
        check("client: a caller that sets the module's MAX_OUTPUT still changes the default cap",
              plain.max_output == 32000 and oll.max_output == 64000)
    finally:
        bt.MAX_OUTPUT = old


def wsl_tests(tmp, enabled):
    names = ["the Windows drive, /run, /var, host /home and the project are absent", "no network", "no credentials in the environment",
             "only the row's files are present", "the session bus cannot be reached, so no process can be started outside",
             "the builder isolation check finds nothing", "a coding-agent program runs and is counted", "a snippet over the time limit is stopped",
             "an exit code of 124 from a quick snippet is not shown as a timeout", "files persist between snippets",
             "a process left running does not outlive its snippet", "the sandbox folder is removed on close",
             "a DEVS-Gen-style program runs through its launcher and is counted once", "an OTF-style program runs under the platform runtime and is counted",
             "the sandbox run is compared with the platform's records", "a program folder is read without its logs, build history or data files"]
    if not enabled:
        for n in names:
            skip(f"sandbox (WSL): {n}")
        return
    nav = fake_nav()
    prog = J.coding_agent_program("unused", files={"run.py": "import sys, json\ndata = json.load(sys.stdin)\nprint(json.dumps({'event': 'case_end', 'n': len(data['cases'])}))\n"})
    view = J.make_view(nav, "Run 01", prog, 10 ** 8, QUESTION_ROW["question"], REQUEST, 910, 900, stdin=STDIN)
    sb = J.WslSandbox(view, timeout_s=4)
    try:
        r = sb.run("import os\nprint(sorted(os.listdir('/')), sorted(os.listdir('/home')))\n"
                   "print('ABSENT', [p for p in ('/mnt', '/run', '/var', '/mnt/c/Users/aashraf/Desktop/Work/2026/ACM Trust 2027', "
                   "'/home/aashraf/trust2027/gen', '/home/aashraf/trust2027/coding_agent', '/home/aashraf/trust2027/judge_sandbox', '/run/user', '/run/WSL') if os.path.exists(p)])\n"
                   "print('WSLLIB', os.listdir('/usr/lib/wsl') if os.path.isdir('/usr/lib/wsl') else [])\n")
        check(f"sandbox (WSL): {names[0]}", "['bin', 'dev', 'etc', 'home', 'lib', 'lib64', 'proc', 'sbin', 'tmp', 'usr'] ['aashraf', 'rt', 'sandbox']" in r["output"]
              and "ABSENT []" in r["output"] and "WSLLIB []" in r["output"], r["output"][:400])
        r = sb.run("import socket\ntry:\n    socket.create_connection(('1.1.1.1', 53), timeout=3)\n    print('UP')\nexcept Exception as e:\n    print('DOWN', type(e).__name__)\n")
        check(f"sandbox (WSL): {names[1]}", "DOWN" in r["output"] and "UP" not in r["output"], r["output"][:200])
        r = sb.run("import os\nprint(sorted(os.environ))\n")
        check(f"sandbox (WSL): {names[2]}", "['HOME', 'LANG', 'PATH', 'PWD', 'PYTHONDONTWRITEBYTECODE', 'PYTHONPATH'" in r["output"]
              and not any(s in r["output"].upper() for s in ("KEY", "TOKEN", "SECRET")), r["output"][:300])
        r = sb.run("import os\nprint(sorted(os.path.relpath(os.path.join(d, f)) for d, _, fs in os.walk('.') for f in fs if '.rt' not in d))\n")
        check(f"sandbox (WSL): {names[3]}", "['document/document.txt', 'document/input.json', 'document/navmap.json', 'program/run.py']" in r["output"], r["output"][:300])
        r = sb.run("import os, subprocess\nenv = {**os.environ, 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/1000/bus', 'XDG_RUNTIME_DIR': '/run/user/1000'}\n"
                   "for cmd in (['systemd-run', '--user', '--wait', '--pipe', '/bin/sh', '-c', 'echo OUTSIDE_RAN'], ['busctl', '--user', 'list']):\n"
                   "    try:\n        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=env)\n        print(cmd[0], 'rc', p.returncode, (p.stdout + p.stderr)[:150])\n"
                   "    except FileNotFoundError:\n        print(cmd[0], 'rc absent')\n"
                   "print('PROCS', len([p for p in os.listdir('/proc') if p.isdigit()]))\n")
        check(f"sandbox (WSL): {names[4]}", "OUTSIDE_RAN" not in r["output"] and "systemd-run rc 0" not in r["output"] and "busctl rc 0" not in r["output"]
              and "systemd-run rc" in r["output"] and any(f"PROCS {n}\n" in r["output"] for n in range(1, 8)), r["output"][:500])
        src = (ROOT / "scripts" / "check_builder_isolation.py").read_text(encoding="utf-8")
        src = src.replace('if __name__ == "__main__":\n    sys.exit(main(sys.argv[1:]))', f'print("EXIT", main(["--wsl", "--workspace", "{J.SBX}"]))')
        r = sb.run(src)
        check(f"sandbox (WSL): {names[5]}", "EXIT 0" in r["output"] and ", 0 findings" in r["output"], r["output"][-400:])
        r = sb.run("import subprocess\np = subprocess.run(['python', 'run.py', '--horizon', '5'], stdin=open('document/input.json'), capture_output=True, text=True, cwd='program')\nprint(p.stdout, p.stderr)\n")
        counts = sb.counts()
        check(f"sandbox (WSL): {names[6]}", '"n": 2' in r["output"] and counts["program_executions"] == 1 and counts["python_starts"] >= 7, str(counts)[:200] + r["output"][:200])
        r = sb.run("import time\nopen('kept.txt', 'w').write('kept')\nprint('before', flush=True)\ntime.sleep(30)\nprint('after')\n")
        check(f"sandbox (WSL): {names[7]}", r["timed_out"] and "before" in r["output"] and "after" not in r["output"] and r["seconds"] < 20
              and "ran longer than 4 seconds" in r["output"], str(r)[:300])
        r = sb.run("import sys\nprint('quick')\nsys.exit(124)\n")
        check(f"sandbox (WSL): {names[8]}", not r["timed_out"] and "[exit code 124]" in r["output"], str(r)[:200])
        r = sb.run("print(open('kept.txt').read())\n")
        check(f"sandbox (WSL): {names[9]}", "kept" in r["output"], r["output"][:200])
        marker = f"sleep 86{uuid.uuid4().int % 900 + 100}"
        r = sb.run(f"import subprocess\nsubprocess.Popen({marker.split()!r})\nprint('started')\n")
        # "[s]leep" keeps this shell's own command line from matching the pattern
        p = subprocess.run(J.WSL + [f"sleep 1; pgrep -fc '[s]{marker[1:]}' || true"], capture_output=True, text=True)
        check(f"sandbox (WSL): {names[10]}", "started" in r["output"] and p.stdout.strip() == "0", f"{r['output'][:100]} left={p.stdout.strip()}")
        r = sb.run("import os\nfds = {}\nfor n in sorted(int(x) for x in os.listdir('/proc/self/fd')):\n    try:\n        fds[n] = os.readlink(f'/proc/self/fd/{n}')\n"
                   "    except OSError:\n        pass\nprint('FDS', sorted(n for n, t in fds.items() if '/proc/' not in t), [t for n, t in fds.items() if n > 2 and '/proc/' not in t])\n")
        check("sandbox (WSL): no inherited file descriptor is open inside (only 0, 1 and 2), the filter's descriptor included", "FDS [0, 1, 2] []" in r["output"], r["output"][:300])
        # review 3: --unshare-net does not cover AF_VSOCK on the WSL2 kernel; the seccomp filter does
        r = sb.run("import errno, socket\nfor name, fam, typ in (('vsock', 40, socket.SOCK_STREAM), ('vsock_dgram', 40, socket.SOCK_DGRAM), ('inet', socket.AF_INET, socket.SOCK_STREAM),\n"
                   "                       ('inet6', socket.AF_INET6, socket.SOCK_DGRAM), ('netlink', 16, socket.SOCK_RAW), ('packet', 17, socket.SOCK_RAW), ('unix', socket.AF_UNIX, socket.SOCK_STREAM)):\n"
                   "    try:\n        s = socket.socket(fam, typ)\n        if name.startswith('vsock'):\n            s.settimeout(3)\n            try:\n                s.connect((2, 50002))\n"
                   "                print('VSOCK_CONNECTED')\n            except OSError:\n                pass\n        s.close()\n        print('SOCKET', name, 'open')\n"
                   "    except OSError as e:\n        print('SOCKET', name, errno.errorcode.get(e.errno, e.errno))\n"
                   "for name, fam in (('unix', socket.AF_UNIX), ('inet', socket.AF_INET), ('vsock', 40)):\n"
                   "    try:\n        a, b = socket.socketpair(fam, socket.SOCK_STREAM)\n        a.sendall(b'ok')\n        print('PAIR', name, b.recv(2).decode())\n"
                   "    except OSError as e:\n        print('PAIR', name, errno.errorcode.get(e.errno, e.errno))\n")
        o = r["output"]
        check("sandbox (WSL): a vsock socket to the Windows host cannot be opened (EPERM)", "SOCKET vsock EPERM" in o and "SOCKET vsock_dgram EPERM" in o
              and "PAIR vsock EPERM" in o and "VSOCK_CONNECTED" not in o, o[:500])
        check("sandbox (WSL): inet, inet6, netlink and packet sockets are refused (EPERM), and AF_UNIX still works",
              all(f"SOCKET {n} EPERM" in o for n in ("inet", "inet6", "netlink", "packet")) and "PAIR inet EPERM" in o
              and "SOCKET unix open" in o and "PAIR unix ok" in o, o[:500])
        r = sb.run("import subprocess, sys\np = subprocess.run([sys.executable, '-c', 'import ctypes; print(ctypes.CDLL(None).syscall(0x40000000 + 39))'], capture_output=True, text=True)\n"
                   "print('X32 rc', p.returncode, p.stdout.strip())\n"
                   "p = subprocess.run([sys.executable, '-c', 'import ctypes; print(ctypes.CDLL(None).syscall(39) > 0)'], capture_output=True, text=True)\nprint('X64 rc', p.returncode, p.stdout.strip())\n")
        check("sandbox (WSL): a system call through the x32 numbering is killed, the same call through x86_64 runs", "X32 rc -31" in r["output"] and "X64 rc 0 True" in r["output"], r["output"][:300])
        r = sb.run("import resource\nfor n in ('RLIMIT_AS', 'RLIMIT_NPROC', 'RLIMIT_FSIZE'):\n    print(n, resource.getrlimit(getattr(resource, n))[0])\n")
        check("sandbox (WSL): the soft limits on address space, processes and file size are set",
              "RLIMIT_AS 8589934592\n" in r["output"] and "RLIMIT_NPROC 4096\n" in r["output"] and "RLIMIT_FSIZE 4294967296\n" in r["output"], r["output"][:300])
        r = sb.run("import os, shutil\nfor name in ('/home/rt/exec.sh', '/home/rt/sitecustomize.py'):\n    for how in ('write', 'remove', 'rename'):\n        try:\n"
                   "            if how == 'write':\n                open(name, 'w').write('x')\n            elif how == 'remove':\n                os.remove(name)\n"
                   "            else:\n                os.rename('/home/rt', '/home/rt2')\n            print('CHANGED', name, how)\n        except OSError as e:\n            print('refused', name, how, type(e).__name__)\n"
                   "shutil.rmtree('.rt', ignore_errors=True)\nos.makedirs('.rt')\nos.symlink('/etc/ld.so.conf', '.rt/starts.jsonl')\n")
        check("sandbox (WSL): the two harness files cannot be changed, removed or moved from inside", "CHANGED" not in r["output"] and r["output"].count("refused") == 6, r["output"][:500])
        r = sb.run("print('still limited')\nimport time\ntime.sleep(30)\n")
        check("sandbox (WSL): the time limit still holds after the attempt", r["timed_out"] and r["seconds"] < 20, str(r)[:200])
        check("sandbox (WSL): a start log replaced by a link is not followed when counting", sb.counts()["python_starts"] == 0 and sb.read(".rt/starts.jsonl") == "")
        r = sb.run("print(open('/home/rt/exec.sh').read()[:11])\n")
        check("sandbox (WSL): the harness is still in place after a snippet removed the tool's folder", "#!/bin/bash" in r["output"], r["output"][:200])
    finally:
        sb.close()
    p = subprocess.run(J.WSL + [f"test -e {sb.folder} && echo THERE || echo GONE"], capture_output=True, text=True)
    check(f"sandbox (WSL): {names[11]}", "GONE" in p.stdout, p.stdout + p.stderr)
    kept, started = J.BPF, None
    J.BPF = "$HOME/trust2027/tools/no_such_filter.bpf"
    try:
        direct = J._wsl(J.bwrap(sb.folder, "true"))
        try:
            started = J.WslSandbox(view)
            started.close()
        except RuntimeError as e:
            started = str(e)
    finally:
        J.BPF = kept
    check("sandbox (WSL): without the filter file no sandbox is created and the command does not start",
          isinstance(started, str) and "seccomp filter" in started and direct.returncode == 97, f"{started!r} rc={direct.returncode}")

    otf, devs = views(tmp)
    with J.WslSandbox(devs) as sb:
        r = sb.run("import subprocess\np = subprocess.run(['python', 'run.py', '--horizon', '100000000'], stdin=open('document/input.json'), capture_output=True, text=True, cwd='program')\nprint(p.returncode, p.stdout, p.stderr[-300:])\n")
        counts = sb.counts()
    check(f"sandbox (WSL): {names[12]}", '"time": 900' in r["output"] and '"time": 1000' in r["output"] and counts["program_executions"] == 1, r["output"][:300] + str(counts)[:100])
    with J.WslSandbox(otf) as sb:
        r = sb.run("import subprocess\np = subprocess.run(['python', 'program/otf_run.py', '--scope', 'Run 01', '--map', 'document/navmap.json'], capture_output=True, text=True)\nprint(p.returncode, p.stdout, p.stderr[-600:])\n")
        counts = sb.counts()
    check(f"sandbox (WSL): {names[13]}", r["output"].startswith("0 ") and '"time": 900.0' in r["output"] and '"time": 1100.0' in r["output"]
          and "src" not in r["output"] and counts["program_executions"] == 1, r["output"][:600] + str(counts)[:100])
    want = [{"time": 900, "case": "c0000", "event": "case_end"}, {"time": 1000, "case": "c0001", "event": "case_end", "src": [["n", 1]]}]
    same = J.sandbox_matches_platform(devs, want)
    differ = J.sandbox_matches_platform(devs, want[:1])
    check(f"sandbox (WSL): {names[14]}", same == {"same": True, "platform_ran": True, "sandbox_ran": True, "records": 2, "sandbox_records": 2}
          and differ["same"] is False and J.sandbox_matches_platform(devs, None)["same"] is False, f"{same} {differ}")
    # a program folder in WSL with logs, build history and data files beside the code
    folder = f"{J.SBX_BASE}/test_{uuid.uuid4().hex}"
    extra = {**DEVS_FILES, "devs_project/_analysis_logs/llm_calls/notes.py": HISTORY, "devs_project/__pycache__/model.py": HISTORY, "logs/trace.py": HISTORY,
             "gen_meta.json": HISTORY, "quick_smoke_stdout.txt": HISTORY, "devs_project/default_run.json": HISTORY, ".model_summary_cache.db": HISTORY, "README.md": HISTORY}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, text in extra.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    try:
        J._wsl(f"mkdir -p {folder} && tar -xf - -C {folder}", buf.getvalue())
        got = J.devs_program(folder)
        check(f"sandbox (WSL): {names[15]}", sorted(got.shown) == ["devs_project/model.py", "devs_project/run_model.py"] and list(got.runtime) == ["run.py"]
              and HISTORY not in json.dumps(got.shown) + json.dumps(got.runtime), str(sorted(got.shown)))
    finally:
        J._wsl(f"rm -rf {folder}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        parsing_tests()
        failure_tests(tmp)
        leakage_tests(tmp)
        real_data_tests()
        layout_tests(tmp)
        react_tests(tmp)
        sandbox_file_tests(tmp)
        subset_tests()
        frozen_subset_tests(tmp)
        client_tests(tmp)
        wsl_tests(tmp, "--no-wsl" not in sys.argv)
    print(f"\n{len(FAILS)} failures, {len(SKIPS)} skipped")
    sys.exit(len(FAILS))
