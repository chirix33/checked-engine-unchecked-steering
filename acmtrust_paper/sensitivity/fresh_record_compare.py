"""Compare Vouch with its capability record (frozen) against Vouch retesting every question (fresh record).

The fresh variant equals the frozen decision on every row that did not depend on the record (checked by the
`check` mode of fresh_record_rerun.py) and takes the rerun decision on the rows that did. Uses the reviewed
main_analysis.py functions unchanged: same rows, groups, B = 2000 and seed, paired two-level bootstrap; and repeats the
comparison with the run-clustered bootstrap (programs, then runs).

Usage: python -X utf8 acmtrust_paper/sensitivity/fresh_record_compare.py <root> <rerun_dir> <out.md>
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

root = Path(sys.argv[1]).resolve()
rerun_dir, out_md = Path(sys.argv[2]), Path(sys.argv[3])
sys.dont_write_bytecode = True
sys.path[:0] = [str(root), str(root / "scripts")]
import main_analysis as ma  # noqa: E402
import main_runner as mr  # noqa: E402
import main_summary as ms  # noqa: E402

fresh = {}
for p in sorted(rerun_dir.glob("rerun_shard*.jsonl")):
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            fresh[(r["set"], r["program"], r["question"])] = r
dep = json.loads((Path(__file__).resolve().parent / "fresh_record_rows.json").read_text(encoding="utf-8"))
dep_keys = {(r["set"], r["program"], r["question"]) for r in dep}
missing = dep_keys - set(fresh)
assert not missing, f"{len(missing)} dependent rows have no rerun"

rows, _, _, _, _ = ma.load_rows(root, ["wf_test", "ml_test"], mr, ms)
tab = ma.table(rows)
t_fresh, fresh_exec, frozen_exec = [], 0, 0
terms = defaultdict(Counter)
for r in rows:
    k = (r["set"], r["program"], r["question"])
    d = fresh[k]["fresh"] if k in fresh else r["decisions"]["directed"]
    t_fresh.append(float(bool(d["permit"])))
    frozen_exec += r["executions"]["directed"]
    fresh_exec += fresh[k]["fresh_executions"] if k in fresh else r["executions"]["directed"]
    if r["has"]:
        side = "wrong" if not r["correct"] else "right"
        terms[(r["class"], side, "record")][ma.term(r["decisions"]["directed"], True)] += 1
        terms[(r["class"], side, "fresh")][ma.term(d, True)] += 1
tab["t_fresh"] = np.array(t_fresh)

frozen_bw = ma.boot_weights
CLUSTER = {}
for s in ("wf_test", "ml_test"):
    for q in mr.questions(root, s):
        CLUSTER[f"{s}|{q['id']}"] = f"{s}|{q['doc']}|{q['scope']}"


def run_bw(prog, qid, B, seed):
    rng = np.random.default_rng(seed)
    up, pi = np.unique(prog, return_inverse=True)
    runs = np.array([CLUSTER[q] for q in qid], dtype=object)
    ur, ri = np.unique(runs, return_inverse=True)
    wp = rng.multinomial(len(up), np.full(len(up), 1 / len(up)), size=B).astype(float)
    wr = rng.multinomial(len(ur), np.full(len(ur), 1 / len(ur)), size=B).astype(float)
    return wp[:, pi] * wr[:, ri]


ma.RULE_JUDGES = ("fresh", "directed")
groups = ma.groups_of(rows)
want = ["class=claude", "class=ollama", "platform=otf_r1|class=claude", "platform=devs|class=claude",
        "platform=agent|class=claude", "process=it_ops|class=claude", "process=loan|class=claude",
        "process=pharmacy|class=claude", "process=manufacturing|class=claude"]
res = {}
for label, bw in (("questions", frozen_bw), ("runs", run_bw)):
    ma.boot_weights = bw
    res[label] = {g: ma.compare_rule_judges(tab, groups[g], ma.B if hasattr(ma, "B") else 2000, ma.SEED) for g in want}
ma.boot_weights = frozen_bw


def pp(x):
    return "--" if x is None else f"{100 * x:+.1f}"


def ci(d):
    c = d.get("ci95")
    return "--" if not c else f"[{100 * c[0]:.1f}, {100 * c[1]:.1f}]"


L = ["# Vouch with its capability record vs retesting every question (fresh record)", "",
     f"Rows that depended on the record and were rerun: {len(dep_keys)}. Program executions on the main sets: "
     f"record {frozen_exec}, fresh {fresh_exec}.", "",
     "| group | n | record: cov / prec (wrong) | fresh: cov / prec (wrong) | record - fresh kept (pp), questions | runs | record - fresh precision (pp), questions | runs |",
     "|---|---|---|---|---|---|---|---|"]
for g in want:
    a, b = res["questions"][g], res["runs"][g]
    rec, fr = a["directed"], a["fresh"]
    fprec = "--" if fr["precision"] is None else f"{fr['precision']:.3f}"
    rprec = "--" if rec["precision"] is None else f"{rec['precision']:.3f}"
    L.append(f"| {g} | {a['n']} | {100 * rec['coverage']:.1f} / {rprec} ({rec['wrong']}) | {100 * fr['coverage']:.1f} / {fprec} ({fr['wrong']}) | "
             f"{pp(fr['gate_minus_this_yield']['point'])} {ci(fr['gate_minus_this_yield'])} | {ci(b['fresh']['gate_minus_this_yield'])} | "
             f"{pp(fr['gate_minus_this_precision']['point'])} {ci(fr['gate_minus_this_precision'])} | {ci(b['fresh']['gate_minus_this_precision'])} |")
L += ["", "Decision terms on answered rows (record vs fresh):", ""]
for k in sorted(terms):
    L.append(f"- {k[0]} {k[1]} {k[2]}: " + ", ".join(f"{t} {n}" for t, n in sorted(terms[k].items())))
out_md.write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
