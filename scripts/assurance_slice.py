"""Minimal end-to-end slice (handoff Stage 2). Evaluation side: the library never sees the gold computed here.

Four cases on hand-checkable development examples: an effectful change, a valid no-effect change, an invalid
request, and reuse, both on new records under the same policy and under a changed policy. Each runs through the
library: interpret, validate, look up evidence, probe, decide, then execute and answer.

This validates plumbing, not research effectiveness.

Usage: python -X utf8 scripts/assurance_slice.py <project_root> <out_json> [devs_program_dir_in_wsl]
"""
import copy
import json
import os
import sys
import time
from pathlib import Path


def main(root, out_path, devs_dir=None):
    root = Path(root).resolve()
    sys.path[:0] = [str(root), str(root / "scripts"), str(root / "reference_engine")]
    sys.dont_write_bytecode = True
    import b0_build_test as runner_mod
    import replay_screen as rs
    from assurance import answer, contract, policy
    from assurance.backends import DEVSBackend, OTFBackend
    from assurance.interpret import interpret
    from assurance.probes import ProbeRunner
    from assurance.registry import Registry
    from assurance.request import schema_from_map

    env = runner_mod.load_env(root / ".env")
    ledger = runner_mod.Ledger(root / "runs" / "build_test_assurance_claude", "claude-haiku-5-5")
    client = runner_mod.Client("claude-haiku-5-5", env, ledger)
    doc = "workflow_loan_dev"

    def gold(scope, interventions, case):
        _, _, out = rs.reference(str(root), doc, scope, {"interventions": interventions})
        return {c["case"]: c["end"] for c in out["cases"]}.get(case)

    cases = [
        {"name": "effectful", "scope": "Run 02",
         "question": "In Run 02, suppose that for case c0007 the activity 'Applicant completes form' needed only 1 second of work on its first visit. At what time, in seconds, would case c0007 end?",
         "gold": lambda: gold("Run 02", [{"type": "duration_set", "task": "Activity_1w0dur0", "seconds": 1, "selector": {"case": "c0007", "visit": 1}}], "c0007")},
        {"name": "no_effect", "scope": "Run 02",
         "question": "In Run 02, suppose that for case c0000 the activity 'Design loan offer' needed 5000 seconds of work on its third visit. At what time, in seconds, would case c0000 end?",
         "gold": lambda: gold("Run 02", [], "c0000")},
        {"name": "invalid", "scope": "Run 02",
         "question": "In Run 02, suppose the activity 'Inspect building' took 600 seconds for case c0003 on its first visit. When would case c0003 end?",
         "gold": lambda: None},
        {"name": "reuse_same_policy", "scope": "Run 03",
         "question": "In Run 03, suppose that for case c0004 the activity 'Applicant completes form' needed only 1 second of work on its first visit. At what time, in seconds, would case c0004 end?",
         "gold": lambda: gold("Run 03", [{"type": "duration_set", "task": "Activity_1w0dur0", "seconds": 1, "selector": {"case": "c0004", "visit": 1}}], "c0004")},
    ]
    programs = [
        ("r1_claude", "claude-haiku-5-5", "b2"),   # replay-exact, hardcodes the applicant task (screen case C)
        ("r1_claude", "claude-sonnet-5-5", "b2"),  # replay-exact
    ]
    results = []
    out_dir = root / "runs" / "assurance_slice_v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    for system, setup, build in programs:
        path = root / "runs" / rs.SYSTEM_FOLDERS[system] / setup / doc / build / "program.json"
        backend = OTFBackend(path, system, root)
        nav = backend.nav
        schema = schema_from_map(nav)
        registry = Registry(out_dir / f"registry_{setup}_{build}.jsonl")
        if registry.path.exists():
            registry.path.unlink()
        runner = ProbeRunner(backend, nav, schema)
        for case in cases:
            results.append(run_case(case, backend, schema, runner, registry, client, policy, contract, answer, interpret,
                                    f"otf/{setup}/{build}"))
        # Reuse under a changed policy: the Clerk pool grows by one. Review fix: the document is regenerated, so its
        # records (every run) come from 10 clerks and its text says 10 clerks, Clerk_0 to Clerk_9. Gold is computed
        # for the changed policy. The fingerprint must invalidate earlier evidence.
        from assurance.probes import policy_with_pool
        add = [{"type": "resource_add", "pool": "Clerk", "count": 1, "from": 0}]
        changed = copy.deepcopy(nav)
        for sc in schema.scopes:
            changed = rs.changed_map(changed, sc, rs.plan_tables(str(root), doc, sc, {"interventions": add}))
        changed = policy_with_pool(changed, "Clerk", schema.pools["Clerk"], 1)
        assert changed is not None, "pool text edit failed"
        schema2 = schema_from_map(changed)
        assert schema2.pools["Clerk"] == schema.pools["Clerk"] + 1
        runner2 = ProbeRunner(backend, changed, schema2)
        backend.nav = changed
        c = dict(cases[3], name="reuse_changed_policy",
                 gold=lambda: gold("Run 03", add + [{"type": "duration_set", "task": "Activity_1w0dur0", "seconds": 1,
                                                       "selector": {"case": "c0004", "visit": 1}}], "c0004"))
        results.append(run_case(c, backend, schema2, runner2, registry, client, policy, contract, answer, interpret,
                                f"otf/{setup}/{build}", gold_note="gold computed under the changed policy (10 clerks)"))
        backend.nav = nav
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, default=str)
    for r in results:
        b = r.get("binding_check")
        print(f"{r['program']:28}{r['case']:22}contract {r['contract']:18} permit {str(r['permit']):6} raw {str(r['answer_before_binding_check']):8} "
              f"binding {('ok' if b and b[0] else ('FAIL' if b else '-')):5} answer {str(r['answer']):8} gold {str(r['gold']):8} {(b[1] if b and not b[0] else r['reason'])[:60]}")


def check_binding(iv, binding, nav, scope, schema):
    from assurance.binding import check_otf
    from assurance.probes import plan_value
    pv = plan_value(nav, scope, iv) if iv.family in ("activity_duration", "timer_delay", "routing_outcome") else None
    return check_otf(iv, binding, plan_value=pv, pool_size=schema.pools.get(iv.target))


def run_case(case, backend, schema, runner, registry, client, policy, contract, answer, interpret, label, gold_note=""):
    t0 = time.time()
    client.build_id = f"slice/{label}/{case['name']}"
    req, raw = interpret(case["question"], schema, client.llm)
    c = contract.validate(req, schema)
    d = policy.decide("directed", req, schema, runner, registry, backend) if c.ok else policy.Decision(False, f"contract {c.status}: {c.detail}")
    ans, binding, detail, bound, raw_answer = None, {}, "", None, None
    if d.permit:
        ex, binding = backend.native_what_if(req.scope, case["question"], client.llm)
        if ex.status != "ran":
            detail = ex.detail
        else:
            raw_answer, detail = answer.answer(req.query, ex.case_ends)
            bound = check_binding(req.interventions[0], binding, backend.nav, req.scope, schema)
            ans = raw_answer if bound[0] else None
    g = case["gold"]()
    return {"program": label, "case": case["name"], "request": req.__dict__ | {"interventions": [i.__dict__ for i in req.interventions]},
            "contract": c.status, "permit": d.permit, "reason": d.reason, "evidence": d.evidence, "answer": ans, "gold": g,
            "probes_run": d.probes_run, "untested": d.untested, "inexpressible": d.inexpressible,
            "correct": (ans == g) if g is not None and ans is not None else None, "binding": binding, "detail": detail,
            "binding_check": bound, "answer_before_binding_check": raw_answer,
            "raw_correct": (raw_answer == g) if g is not None and raw_answer is not None else None,
            "seconds": round(time.time() - t0, 1), "note": gold_note}


if __name__ == "__main__":
    main(*sys.argv[1:4])
