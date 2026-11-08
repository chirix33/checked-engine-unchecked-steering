"""Soundness check of routing witnesses, run offline against the reference engine (evaluation-only).

Every route flip the probes may use as a witness is run on the reference. A sound witness (1) runs, (2) needs no
plan visit beyond the columns the document lists, so a correct program has every input it needs, and (3) changes
the flipped case's timed records, so "changed nothing" never rejects a correct program.

Usage: python -X utf8 validation/probe_soundness_route_flips.py   (needs the environment with reportlab)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "reference_engine")]
sys.dont_write_bytecode = True

import engine                                                    # noqa: E402
import render_workflow_doc as render                             # noqa: E402
import replay_screen as rs                                       # noqa: E402
from assurance import probes                                     # noqa: E402
from assurance.request import Intervention, schema_from_map      # noqa: E402


def sig(out, case):
    s = [("t", t["end"]) for t in out["tasks"] if t["case"] == case] + [("w", t["end"]) for t in out["timers"] if t["case"] == case]
    s += [("d", b["time"]) for b in out["branches"] if b["case"] == case] + [("e", c["end"]) for c in out["cases"] if c["case"] == case]
    return sorted(s)


def main():
    bad_total = 0
    for doc in ("workflow_loan_dev", "workflow_pharmacy_dev"):
        nav = json.loads((ROOT / f"runs/build_test_r1_claude/claude-sonnet-5-5/{doc}/b2/navmap.json").read_text(encoding="utf-8"))
        schema = schema_from_map(nav)
        bpmn, params = rs.model_files(str(ROOT), doc)
        model = engine.Model(bpmn, params)
        inv = {v: k for k, v in render.Labels(model, bpmn).label.items()}
        total, unused, failed, deep, same = 0, 0, [], [], []
        for sc in schema.scopes:
            depth = len(next(n for n in nav["nodes"] if n["title"] == f"{sc}: Work plan")["table"]["columns"]) - 2
            _, _, base = rs.reference(str(ROOT), doc, sc, {})
            for r in probes._table_rows(nav, sc, "Decision log"):
                w = Intervention("routing_outcome", "set_draw", case=r[0], target=r[1], visit=int(r[2]))
                p = probes.perturb(nav, schema, sc, w)
                if p is None:
                    unused += 1
                    continue
                total += 1
                _, _, out = rs.reference(str(ROOT), doc, sc, {"draw_overrides": [
                    {"case": p.case, "element": inv[p.target], "visit": p.visit, "variable": "branch", "u": f"{p.value:.6f}"}]})
                if out.get("status") != "ok":
                    failed.append((sc, r[:3], out.get("error")))
                    continue
                mx = max([t["visit"] for t in out["tasks"]] + [t["visit"] for t in out["timers"]] + [b["visit"] for b in out["branches"]])
                if mx > depth:
                    deep.append((sc, r[:3], mx, depth))
                if sig(out, p.case) == sig(base, p.case):
                    same.append((sc, r[:3]))
        bad = len(failed) + len(deep) + len(same)
        bad_total += bad
        print(f"{doc}: {total} witness flips, {unused} decisions without a usable flip; failed {len(failed)}, "
              f"needing unlisted visits {len(deep)}, leaving the case unchanged {len(same)}")
        for x in (failed + deep + same)[:5]:
            print("   ", x)
    return bad_total


if __name__ == "__main__":
    sys.exit(main())
