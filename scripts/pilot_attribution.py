"""Attribute each gate's declines in the development pilot (evaluation side: reads gold).

For every cohort and gate, each question the native path answered is classified by why the gate declined it:
failed history check (factual replay), contract, caught (a probe showed the program gets this kind of change
wrong), untestable (no way to test this kind of change on this program), can't express (the program has no input
for the change), already caught (the program failed this test on an earlier question), or trusted (permitted).
These are Ashraf's plain terms (2026-11-07); the library's internal reason strings are unchanged. Within each class it counts how many native
answers were wrong (errors removed) and right (correct answers lost). This separates detection (a failing probe or
replay) from abstention on a family the probes cannot observe.

Structured path, interpreted requests. Usage: python -X utf8 scripts/pilot_attribution.py . out.json
"""
from __future__ import annotations

import collections
import glob
import json
import sys
from pathlib import Path


def correct(a, gold):
    return a is not None and gold is not None and abs(a - gold) < 1


def cohort(program: str) -> str:
    parts = program.split("/")
    return "/".join(parts[:3]) if parts[0] == "otf" else f"devs/{parts[1]}"


def cause(dec: dict) -> str:
    if dec["permit"]:
        return "trusted"
    r = dec["reason"]
    if dec.get("inexpressible"):
        return "cant_express"
    if dec.get("untested"):
        return "untestable"
    if r.startswith("replay"):
        return "failed_history_check"
    if r.startswith("contract"):
        return "contract"
    if r.startswith("capability failed earlier"):
        return "already_caught"
    if any(e[1] is False for e in dec.get("evidence", [])[1:]):
        return "caught"
    return "other"


def main(root: Path, out: Path, exclude_path=None, run_dir="pilot_v1"):
    qs = {q["id"]: q for q in json.loads((root / "manifests" / "pilot_questions_v1.json").read_text(encoding="utf-8"))}
    excluded = set(json.loads(Path(exclude_path).read_text(encoding="utf-8"))) if exclude_path else set()
    assert excluded <= set(qs), sorted(excluded - set(qs))
    table = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.Counter()))
    by_family = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.Counter()))
    for f in sorted(glob.glob(str(root / "runs" / run_dir / "programs" / "*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            if r.get("source") != "interpreted" or "structured" not in r or r["question"] in excluded:
                continue
            q = qs[r["question"]]
            s = r["structured"]
            a = s.get("answer") if s.get("status") == "ran" else None
            if a is None:
                continue                      # the structured path (ungated) gave no answer: nothing for a gate to remove
            ok = correct(a, q["gold"])
            for cfg, dec in r["decisions"].items():
                if cfg == "native":
                    continue
                c = cause(dec)
                table[(cohort(r["program"]), cfg)][c]["right" if ok else "wrong"] += 1
                by_family[(cohort(r["program"]), cfg, q["family"])][c]["right" if ok else "wrong"] += 1
    res = {"note": __doc__.strip().splitlines()[0],
           "table": [{"cohort": k[0], "config": k[1], **{c: dict(v) for c, v in d.items()}} for k, d in sorted(table.items())],
           "by_family": [{"cohort": k[0], "config": k[1], "family": k[2], **{c: dict(v) for c, v in d.items()}}
                         for k, d in sorted(by_family.items())]}
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    order = ("trusted", "failed_history_check", "caught", "already_caught", "untestable", "cant_express", "contract", "other")
    print(f"{'cohort':32} {'config':12} " + " ".join(f"{c[:14]:>16}" for c in order) + "   (wrong/right among native answers)")
    for k, d in sorted(table.items()):
        print(f"{k[0]:32} {k[1]:12} " + " ".join(f"{str(d[c]['wrong']) + '/' + str(d[c]['right']):>16}" for c in order))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), (sys.argv[3] or None) if len(sys.argv) > 3 else None,
         sys.argv[4] if len(sys.argv) > 4 else "pilot_v1")
