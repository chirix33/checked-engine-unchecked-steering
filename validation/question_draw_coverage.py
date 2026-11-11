"""Check a question file against the deterministic-realization rule (evaluation-only).

For each question, list the draws the reference uses under the change that the document does not print and the
question does not set. Uses the generator's own rule (`make_pilot_questions.undocumented_draws`). Exits nonzero
if any question fails.

Test and policy-variant documents (`workflow_*_test`, `workflow_*_policy{P,H}`) are resolved through the same lookups. A file with
no questions exits 2, so an empty input never passes.

Usage: python -X utf8 validation/question_draw_coverage.py <questions.json>   (needs the environment with reportlab)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "reference_engine")]
sys.dont_write_bytecode = True

import engine                                                    # noqa: E402
import make_pilot_questions as mk                                # noqa: E402
import render_workflow_doc as render                             # noqa: E402
import replay_screen as rs                                       # noqa: E402
import workflow_policy_set as wp                                 # noqa: E402
import workflow_test_set as wt                                   # noqa: E402

wt.register(rs)     # lookups only: lets model_files/reference resolve the test documents (2026-11-09)
wp.register(rs)     # and the policy-variant documents, with their own parameter files


def main(path):
    qs = json.loads(Path(path).read_text(encoding="utf-8"))
    cache, bad = {}, []
    for q in qs:
        if q["doc"] not in cache:
            bpmn, params = rs.model_files(str(ROOT), q["doc"])
            model = engine.Model(bpmn, params)
            cache[q["doc"]] = (model, render.in_cycle(model), {})
        model, cycles, bases = cache[q["doc"]]
        if q["scope"] not in bases:
            bases[q["scope"]] = rs.reference(str(ROOT), q["doc"], q["scope"], {})[2]
        _, _, out = rs.reference(str(ROOT), q["doc"], q["scope"], {"interventions": q["interventions"], "draw_overrides": q.get("draw_overrides", [])})
        miss = mk.undocumented_draws(bases[q["scope"]], out, model, cycles, q)
        if miss:
            bad.append((q["id"], sum(1 for m in miss if m[0] == q["query_case"]), len(miss)))
    for b in bad:
        print(f"  {b[0]}: {b[2]} undocumented draws, {b[1]} of them for the query case")
    print(f"{len(bad)} of {len(qs)} questions need draws the document does not give")
    if not qs:
        return 2
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
