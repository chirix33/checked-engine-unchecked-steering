"""Policy-variant reuse questions for the business workflows, with gold (evaluation-only). Ashraf, 2026-11-09.

Same generator as the test set (`make_workflow_test_questions.generate`, which is the dev selection loop with its
dev functions), with the test-only rules: exact repeats skipped, try cap 2000, workers named when only part of a pool is
unavailable, and (`rules=True`) no unreached-visit, identity or unused-worker changes, with resource_availability
stratified by operation (2 questions each; the one control's operation fixed per document by CONTROL_OP). Where an
operation has too few valid questions (Loan P: no added-workers change has an effect), the quota lifts after half
the tries. On the policy-variant documents (`scripts/workflow_policy_set.py`): for each process, variant P
(changed policy) and variant H (harmless rewording), 4 questions per family per variant, 1 of them a valid no-effect
control (the dev quota rule, max(1, 4 // 5) = 1). 6 families x 4 x 2 variants x 2 processes = 96 planned. A family
may fall short only if an exhaustive check (`candidates`) proves the missing kind of question does not exist on that
document's runs; runs are not re-chosen to create it. The shortfalls and their proofs are written to
`<out>.shortfalls.json`, which `scripts/workflow_policy_set.py check` copies into the policy check file. Gold is
the reference engine's on the variant's own parameter file. Kept apart from the test set and reported separately.

Fields: those of `workflow_questions_test_v1.json`, with split "policy" and an added `variant` ("P" or "H").

Usage: python -X utf8 scripts/make_workflow_policy_questions.py <out_json> [seed]       (default seed 20271110)
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "reference_engine")]

import make_workflow_test_questions as mt      # noqa: E402
import workflow_policy_set as wp               # noqa: E402

SEED = 20271110
# The one resource_availability control per document: each operation twice, once per process and once per variant.
CONTROL_OP = {"workflow_loan_policyP": "add_workers", "workflow_pharmacy_policyP": "unavailable",
              "workflow_loan_policyH": "unavailable", "workflow_pharmacy_policyH": "add_workers"}
PER_FAMILY = 4


def main(out_path, seed=SEED):
    import replay_screen as rs
    wp.register(rs)
    qs, shortfalls, skipped = [], [], {}
    for doc, v in wp.VARIANTS.items():           # one generate call per document, so each uses its own runs
        got, short = mt.generate(str(ROOT), [doc], v["runs"], PER_FAMILY, int(seed) + list(wp.VARIANTS).index(doc),
                                 unique=True, max_tries=mt.TEST_MAX_TRIES, rules=True, skipped=skipped, control_op=CONTROL_OP,
                                 id_of=lambda d, family, made, V=v["variant"]: f"{d[9:12]}-pol{V}-{family}-{made:02d}")
        for d, family, made in short:
            kinds = Counter("no_effect" if not q["effectful"] else "effectful" for q in got if q["family"] == family)
            want = {"no_effect": max(1, PER_FAMILY // 5)}
            want["effectful"] = PER_FAMILY - want["no_effect"]
            missing = [k for k in want if kinds[k] < want[k]]
            n = candidates(d, v["runs"], family)
            if any(n[k] != 0 for k in missing):
                raise SystemExit(f"{d} {family}: {made} of {PER_FAMILY}, and the shortfall is not proven unavoidable ({n})")
            shortfalls.append({"doc": d, "family": family, "made": made, "missing": missing, "candidates": n})
        qs += got
    print("drafts skipped by the test-only rules:", {f"{d} {f} {w}": n for (d, f, w), n in sorted(skipped.items())})
    mt.name_workers(qs, list(wp.VARIANTS))
    out = mt.finish(qs, "policy", variant_of=lambda d: wp.VARIANTS[d]["variant"])
    mt.write_lf(out, out_path)
    print(len(out), "questions;", dict(Counter((q["doc"], q["effectful"]) for q in out)))
    mt.write_lf(shortfalls, Path(out_path).with_suffix(".shortfalls.json"))
    print("shortfalls (proven unavoidable):", shortfalls)


def candidates(doc, runs, family):
    """Every distinct question the generator's draft can produce for this family on these runs, enumerated: how many
    pass the realization filter, split by effect. Implemented for the two families whose draft spaces are finite and
    small: case_set (run, removed case, query case) and timer_delay (run, recorded wait, the 3 values the draft uses:
    0, delay + 1 h, 2 x delay). A count of 0 proves that kind of question cannot be drawn."""
    import engine
    import make_pilot_questions as mk
    import render_workflow_doc as render
    import replay_screen as rs
    model = engine.Model(*rs.model_files(str(ROOT), doc))
    cycles = render.in_cycle(model)
    n = {"effectful": 0, "no_effect": 0}
    for run in runs:
        base = rs.reference(str(ROOT), doc, run, {})[2]
        ends = {c["case"]: c["end"] for c in base["cases"]}
        if family == "case_set":
            drafts = [({"interventions": [{"type": "case_remove", "case": g}]}, [c for c in ends if c != g]) for g in ends]
        elif family == "timer_delay":
            drafts = [({"interventions": [{"type": "timer_set", "timer": t["timer"], "seconds": int(v),
                                           "selector": {"case": t["case"], "visit": t["visit"]}}]}, [t["case"]])
                      for t in base["timers"] for v in sorted({0, t["delay"] + mk.HOUR, t["delay"] * 2} - {t["delay"]})]
            # (identity values, equal to the factual delay, are excluded as the generator's rules exclude them)
        else:
            raise SystemExit(f"no exhaustive check for {family}")
        for q, cases in drafts:
            out = rs.reference(str(ROOT), doc, run, q)[2]
            if mk.undocumented_draws(base, out, model, cycles, q):
                continue
            new = {c["case"]: c["end"] for c in out["cases"]}
            for c in cases:
                n["effectful" if new[c] != ends[c] else "no_effect"] += 1
    return n


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else SEED)
