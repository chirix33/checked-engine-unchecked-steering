"""Trace the one program-level case C: compare the failing case record by record and show the program's scheduling code."""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

root = os.path.abspath(sys.argv[1])
sys.path.insert(0, os.path.join(root, "scripts"))
import replay_screen as rs
root = rs.setup_paths(root)
from otf_r1 import sandbox, toolgen

doc, run = "workflow_loan_dev", "Run 02"
d = Path(root, "runs", "build_test_r1_claude", "claude-haiku-5-5", doc, "b2")
code = json.load(open(d / "program.json", encoding="utf-8"))["code"]
nav = json.loads((d / "navmap.json").read_text())
targets = json.load(open(os.path.join(root, "manifests", "screen_targets_v1.json"), encoding="utf-8"))
target = next(t for t in targets if t["doc"] == doc and t["run"] == run and t["name"] == "work_down_to_1s")
with tempfile.TemporaryDirectory() as tmp:
    m = Path(tmp) / "m.json"
    changed = rs.changed_map(nav, run, rs.plan_tables(root, doc, run, target))
    m.write_text(json.dumps(changed))
    r = toolgen.read_scope(code, m, run)
    cut = toolgen._cut(r)
    blind = toolgen.blinded_map(changed, m, run, r, cut)
    ok, out = sandbox.run(code, "simulate", blind, [run], {"inputs": r["inputs"], "params": r["params"], "start": cut, "horizon": rs.HORIZON})
assert ok
case = "c0007"


def rows(records):
    return sorted((round(float(x["time"])), x["kind"], ",".join(sorted(x["entities"]))) for x in records if case in x.get("entities", []) and x.get("time") is not None)


true_rows, sim_rows = rows(r["outcomes"]), rows(out)
print("true records", len(true_rows), "simulated", len(sim_rows))
print(f"{'TRUE':80}SIMULATED")
for a, b in list(zip(true_rows, sim_rows))[:46]:
    flag = "" if a == b else "  <--"
    print(f"{str(a)[:78]:80}{str(b)[:78]}{flag}")
print("\n--- program: lines mentioning the applicant, calendars or fixed durations")
lines = code.splitlines()
for i, line in enumerate(lines):
    if re.search(r"applicant|86400|23:59|86340|1439|calendar|def next_work|def work_end|def add_work|closing|open_time", line, re.I):
        print(f"{i:4}: {line[:130]}")
