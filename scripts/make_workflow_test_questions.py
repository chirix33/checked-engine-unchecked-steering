"""Final-test questions for the business workflows (Loan Application, Pharmacy), with gold (evaluation-only).

Reuses the dev generator's own functions (`make_pilot_questions.draft`, `undocumented_draws`) and the same selection
loop, parameterized by documents, runs, size and id. `make_pilot_questions.py` is not changed. The loop here is
checked against the dev set: run on the dev documents with the dev size and seed, with the realization filter off
(the filter did not exist when the dev set was made), it must reproduce `manifests/pilot_questions_v1.json` byte for
byte (`regen-dev`), and with the filter on it must equal the current dev generator's output (`regen-dev-filtered`).

Test questions: 20 per family per process (6 families, 120 per process, 240 in all), on the test runs
(`scripts/workflow_test_set.py`), with the deterministic-realization filter on. About one in five per family is a
valid no-effect control (the dev quota rule: max(1, n // 5), so 4 of 20).

Rules for the test and policy sets only (the dev regeneration path uses none of them):
  1. an exact repeat of a kept question (same run, change and query case) is skipped;
  2. the try cap per family is 2000 instead of 400 (with repeats skipped, Pharmacy routing_outcome needs more);
  3. when only part of a pool is unavailable, the question names the workers (text only);
  4. no activity-duration change at a visit the case never makes (an unknown-target request, not a control);
  5. no identity change (equal to the factual work or wait, or to the published route probabilities);
  6. resource_availability is stratified by operation: half the questions and half the controls each;
  7. no "unavailable" change whose workers do no task in the factual run (trivially no effect).
Rules 4-7 were added after the external reviews of 2026-11-09 (`rule_skip`, `rules=True`). When only part of a pool
is unavailable, the question text names the workers (the highest-numbered, as gold assumes); the front matter does not
say which workers a count means. Selection follows a fixed rule and seed,
decided before any method is run on these questions, and never looks at a program.

Fields: every field of `pilot_questions_v1.json` (id, doc, scope, family, gold, factual_end, effectful, question,
text, interventions, query_case, binding, and draw_overrides for routing_outcome), plus the fields the
manufacturing/IT test file adds where they apply: domain, split, seen_at_build, query (structured). Gold is the
reference engine's; the independent checker's agreement is checked separately (`validation/workflow_test_checker.py`).

Usage: python -X utf8 scripts/make_workflow_test_questions.py test <out_json> [seed]       (default seed 20271109)
       python -X utf8 scripts/make_workflow_test_questions.py regen-dev <seed> <out_json>
       python -X utf8 scripts/make_workflow_test_questions.py regen-dev-filtered <seed> <out_json>
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "reference_engine")]

import make_pilot_questions as mk          # noqa: E402  (draft, undocumented_draws: unchanged dev functions)
import workflow_test_set as W              # noqa: E402

FAMILIES = ["activity_duration", "timer_delay", "routing_outcome", "routing_probability", "resource_availability", "case_set"]
TEST_SEED = 20271109
TEST_PER_FAMILY = 20
MAX_TRIES = 400                            # the dev loop's cap (used for the dev regeneration checks)
TEST_MAX_TRIES = 2000                      # test: with repeats skipped, Pharmacy routing_outcome needs more than 400


def rule_skip(family, q, base, model):
    """Why a draft is not a valid change under the test-only rules (`rules=True`), or None (2026-11-09, review).
    - unreached visit: an activity-duration change at a visit the case never makes in the factual run. That is an
      unknown-target request, not a no-effect change (RESEARCH_DIRECTION.md treats them as different failures).
    - identity: a change equal to the factual value (work or wait seconds at that visit) or to the published route
      probabilities. Nothing is changed, so it is not a valid change of either kind.
    - unused workers: making unavailable only workers who do no task in the factual run. The run cannot change, so
      it is a trivial no-effect control (second review)."""
    from fractions import Fraction
    iv = (q.get("interventions") or [None])[0]
    if family == "activity_duration":
        sel = iv["selector"]
        done = {(t["case"], t["task"], t["visit"]): t["service"] for t in base["tasks"]}
        key = (sel["case"], iv["task"], sel["visit"])
        if key not in done:
            return "unreached visit"
        if int(done[key]) == int(iv["seconds"]):
            return "identity"
    if family == "timer_delay":
        sel = iv["selector"]
        done = {(t["case"], t["timer"], t["visit"]): t["delay"] for t in base["timers"]}
        if int(done.get((sel["case"], iv["timer"], sel["visit"]), -1)) == int(iv["seconds"]):
            return "identity"
    if family == "routing_probability":
        published = {f: Fraction(str(p)) for f, p in model.branch[iv["gateway"]]}
        if {f: Fraction(v) for f, v in iv["probabilities"].items()} == published:
            return "identity"
    if family == "resource_availability" and iv["type"] == "resource_unavailable":
        n = model.pools[iv["pool"]]["amount"]
        names = {f"{iv['pool']}_{k}" for k in range(n - int(iv["count"]), n)}
        if not names & {t["resource"] for t in base["tasks"]}:
            return "unused workers"         # the workers made unavailable do nothing in the run: trivially no effect
    return None


def generate(root, docs, runs, per_family, seed, realization_filter=True, id_of=None, max_tries=MAX_TRIES, unique=False,
             rules=False, skipped=None, control_op=None):
    """The dev selection loop (make_pilot_questions.main), with documents, runs, size and id as parameters.
    unique: skip a draft identical to a kept question (same run, change and query case). Off for the dev set,
    which has 3 such repeats; on for the test set, so every test question is distinct.
    rules (test and policy only; off for the dev set): skip unreached-visit, identity and unused-worker changes
    (`rule_skip`), and stratify resource_availability by operation (added workers, unavailable workers): during the
    first half of the tries each operation gets half the family's questions and half its no-effect controls, so the
    rate of controls is the same for both wordings. With an odd number of controls (the policy set has 1 per family
    per document), `control_op[doc]` names the operation the control must use. After half the tries the quotas lift
    and any valid question is accepted, so a document where one operation has too few valid questions still fills.
    Counts of skipped drafts go to `skipped` (a dict) when given."""
    root = os.path.abspath(root)
    import replay_screen as rs
    import render_workflow_doc as render
    import engine
    W.register(rs)
    assert render.MIN_VISITS == mk.MIN_VISITS, "printed_draws must follow the renderer"
    id_of = id_of or (lambda doc, family, made: f"{doc[9:12]}-{family}-{made:02d}")
    rng = random.Random(int(seed))
    questions, short, kept = [], [], set()
    for doc in docs:
        bpmn, params = rs.model_files(root, doc)
        model = engine.Model(bpmn, params)
        labels = render.Labels(model, bpmn)
        cycles = render.in_cycle(model)
        per_run = {run: rs.reference(root, doc, run, {})[2] for run in runs}
        for family in FAMILIES:
            made, tries = 0, 0
            want_noeffect = max(1, per_family // 5)
            noeffect = 0
            OPS = ("add_workers", "unavailable")
            ctrl_target = {op: want_noeffect // 2 for op in OPS}
            if want_noeffect % 2:
                ctrl_target[(control_op or {}).get(doc, OPS[0])] += 1
            eff_target = {op: per_family // 2 - ctrl_target[op] for op in OPS}
            ctrl_n, eff_n = {op: 0 for op in OPS}, {op: 0 for op in OPS}
            while made < per_family and tries < max_tries:
                tries += 1
                run = rng.choice(runs)
                base = per_run[run]
                ends = {c["case"]: c["end"] for c in base["cases"]}
                q = mk.draft(family, rng, base, model, labels, cycles, run, render, engine)
                if q is None:
                    continue
                if rules:
                    why = rule_skip(family, q, base, model)
                    if why:
                        if skipped is not None:
                            skipped[(doc, family, why)] = skipped.get((doc, family, why), 0) + 1
                        continue
                _, _, out = rs.reference(root, doc, run, {"interventions": q["interventions"], "draw_overrides": q.get("draw_overrides", [])})
                new_ends = {c["case"]: c["end"] for c in out["cases"]}
                case = q["query_case"]
                if case not in new_ends:
                    continue
                same = (doc, run, json.dumps(q["interventions"], sort_keys=True),
                        json.dumps(q.get("draw_overrides", []), sort_keys=True), case)
                if unique and same in kept:
                    continue
                if realization_filter and mk.undocumented_draws(base, out, model, cycles, q):
                    continue                # gold not derivable from the document (deterministic-realization rule)
                effect = new_ends[case] != ends.get(case)
                if not effect and noeffect >= want_noeffect:
                    continue
                if rules and family == "resource_availability" and tries <= max_tries // 2:
                    op = q["binding"].get("op")
                    if (eff_n if effect else ctrl_n)[op] >= (eff_target if effect else ctrl_target)[op]:
                        if skipped is not None:
                            skipped[(doc, family, "op quota")] = skipped.get((doc, family, "op quota"), 0) + 1
                        continue
                if effect and made - noeffect >= per_family - want_noeffect:
                    continue
                noeffect += not effect
                if family == "resource_availability":
                    (eff_n if effect else ctrl_n)[q["binding"].get("op")] += 1
                q.update({"id": id_of(doc, family, made), "doc": doc, "scope": run, "family": family,
                          "gold": new_ends[case], "factual_end": ends.get(case), "effectful": effect,
                          "question": q["text"] + f" At what time, in seconds from time 0, would case {case} end?"})
                questions.append(q)
                kept.add(same)
                made += 1
            print(doc, family, made, "questions,", noeffect, "no-effect,", tries, "tries")
            if made < per_family:
                short.append((doc, family, made))
    return questions, short


def write_dev_style(questions, out_path):
    """Exactly as make_pilot_questions.main writes (text mode, so the platform's line endings)."""
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, indent=1)


def name_workers(qs, docs):
    """Name the workers when only part of a pool is unavailable (rule added 2026-11-09). The front matter does not say
    which workers a count refers to; gold, DEVSBackend.apply and the resource probe all use the highest-numbered ones,
    so the question names them. Whole-pool questions keep the dev wording. Selection is not affected."""
    import engine
    import replay_screen as rs
    pools = {doc: engine.Model(*rs.model_files(str(ROOT), doc)).pools for doc in docs}
    for q in qs:
        b = q["binding"]
        n = pools[q["doc"]][b["target"]]["amount"] if b.get("op") == "unavailable" else None
        if n is not None and b["value"] < n:
            k, pool = int(b["value"]), b["target"]
            names = ", ".join(f"{pool}_{i}" for i in range(n - k, n))
            old = f"suppose {k} {pool} worker{'s were' if k > 1 else ' was'} unavailable"
            new = f"suppose {k} {pool} worker{'s' if k > 1 else ''} ({names}) {'were' if k > 1 else 'was'} unavailable"
            assert q["text"].count(old) == 1 and q["question"].count(old) == 1, q["id"]
            q["text"], q["question"] = q["text"].replace(old, new), q["question"].replace(old, new)


ORDER = ["id", "doc", "scope", "domain", "split", "variant", "seen_at_build", "family", "gold", "factual_end", "effectful",
         "question", "text", "interventions", "draw_overrides", "query_case", "query", "binding"]


def finish(qs, split, variant_of=None):
    """The shared fields and key order of the test file; `variant` only when variant_of is given."""
    out = []
    for q in qs:
        q.update({"domain": "workflow_" + q["doc"].split("_")[1], "split": split, "seen_at_build": False,
                  "query": {"kind": "case_end_time", "case": q["query_case"]}})
        if variant_of:
            q["variant"] = variant_of(q["doc"])
        assert set(q) <= set(ORDER), set(q) - set(ORDER)
        out.append({k: q[k] for k in ORDER if k in q})
    ids = [q["id"] for q in out]
    assert len(ids) == len(set(ids))
    return out


def write_lf(out, out_path):
    Path(out_path).write_bytes((json.dumps(out, indent=1) + "\n").encode("utf-8"))   # LF everywhere: a portable hash


def test(out_path, seed=TEST_SEED):
    docs = list(W.TEST_DOCS)
    skipped = {}
    qs, short = generate(str(ROOT), docs, W.TEST_RUNS, TEST_PER_FAMILY, seed, unique=True, max_tries=TEST_MAX_TRIES,
                         id_of=lambda doc, family, made: f"{doc[9:12]}-test-{family}-{made:02d}", rules=True, skipped=skipped)
    print("drafts skipped by the test-only rules:", {f"{d} {f} {w}": n for (d, f, w), n in sorted(skipped.items())})
    if short:
        raise SystemExit(f"families short of {TEST_PER_FAMILY}: {short}")
    name_workers(qs, docs)
    out = finish(qs, "test")
    write_lf(out, out_path)
    from collections import Counter
    print(len(out), "questions;", Counter(q["doc"] for q in out), "no-effect:", sum(not q["effectful"] for q in out))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "test":
        test(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else TEST_SEED)
    elif cmd in ("regen-dev", "regen-dev-filtered"):
        qs, _ = generate(str(ROOT), ["workflow_loan_dev", "workflow_pharmacy_dev"], W.DEV_RUNS, 10, int(sys.argv[2]),
                         realization_filter=(cmd == "regen-dev-filtered"))
        write_dev_style(qs, sys.argv[3])
        print(len(qs), "questions")
    else:
        raise SystemExit(__doc__)
