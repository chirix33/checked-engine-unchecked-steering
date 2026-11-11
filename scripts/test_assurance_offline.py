"""Offline checks of the assurance library: binding check, probes, policy, contract and parser.

No model calls, no reference engine, no WSL. Uses the real document maps and fake backends. Each check prints PASS
or FAIL; the exit code is the number of failures. Covers the defects found by library review 2 (2026-11-07).

Usage: python -X utf8 scripts/test_assurance_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from assurance import contract, policy, probes                                   # noqa: E402
from assurance.backends import Execution, _record_diff, recorded_case_ends        # noqa: E402
from assurance.binding import check_otf                                            # noqa: E402
from assurance.interpret import parse                                              # noqa: E402
from assurance.registry import Registry                                            # noqa: E402
from assurance.request import Intervention, Query, Request, schema_from_map       # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def nav_of(doc):
    p = ROOT / f"runs/build_test_r1_claude/claude-sonnet-5-5/{doc}/b2/navmap.json"
    return json.loads(p.read_text(encoding="utf-8"))


def rec(id_, case, fields, kind="work_plan"):
    return {"id": id_, "time": None, "kind": kind, "entities": [case], "fields": fields}


# ---------------------------------------------------------------- binding
def binding_tests():
    iv = Intervention("activity_duration", "set", case="c0013", target="Design loan offer", visit=1, value=5000.0)
    good_old = rec("work_plan_c0013_Design loan offer", "c0013", {"activity": "Design loan offer", "visit 1": 1822.0, "visit 2": 900.0})
    good_new = rec("work_plan_c0013_Design loan offer", "c0013", {"activity": "Design loan offer", "visit 1": 5000.0, "visit 2": 900.0})
    before = [good_old, rec("work_plan_c0013_Consider re-design loan offer", "c0013", {"activity": "Consider re-design loan offer", "visit 1": 10.0})]

    d = _record_diff(before, [good_new, before[1]])
    check("binding: exact single-field change accepted", check_otf(iv, d)[0], check_otf(iv, d)[1])

    added = rec("extra", "c0013", {"activity": "Design loan offer", "visit 1": 5000.0})
    d = _record_diff(before, before + [added])
    check("binding: an added partial record is rejected", not check_otf(iv, d)[0], check_otf(iv, d)[1])

    sub_old = before[1]
    sub_new = rec("work_plan_c0013_Consider re-design loan offer", "c0013", {"activity": "Consider re-design loan offer", "visit 1": 5000.0})
    d = _record_diff(before, [good_old, sub_new])
    check("binding: substring-named activity is rejected", not check_otf(iv, d)[0], check_otf(iv, d)[1])
    del sub_old

    v2 = rec("work_plan_c0013_Design loan offer", "c0013", {"activity": "Design loan offer", "visit 1": 1822.0, "visit 2": 5000.0})
    d = _record_diff(before, [v2, before[1]])
    check("binding: change in the wrong visit is rejected", not check_otf(iv, d)[0], check_otf(iv, d)[1])

    d = _record_diff(before, [before[1]])
    check("binding: a removed record is visible and rejected", not check_otf(iv, d)[0], check_otf(iv, d)[1])

    d = {**_record_diff(before, before), "overrides": [{"x": 1}]}
    check("binding: outcome overrides are rejected", not check_otf(iv, d)[0], check_otf(iv, d)[1])

    d = _record_diff(before, before)
    check("binding: no change rejected when the request differs from the plan", not check_otf(iv, d, plan_value=1822.0)[0])
    check("binding: no change accepted when the request equals the plan", check_otf(iv, d, plan_value=5000.0)[0])

    both = [good_new, rec("work_plan_c0013_Consider re-design loan offer", "c0013", {"activity": "Consider re-design loan offer", "visit 1": 5000.0})]
    d = _record_diff(before, both)
    check("binding: over-broad patch (two records) is rejected", not check_otf(iv, d)[0])

    ivw = Intervention("timer_delay", "set", case="c0013", target="W1", visit=1, value=1.0)
    w_old = rec("wait_plan_c0013_W1", "c0013", {"wait": "W1", "visit 1": 18431.0, "visit 2": 7.0}, "wait_plan")
    w_new = rec("wait_plan_c0013_W1", "c0013", {"wait": "W1", "visit 1": 18431.0, "visit 2": 1.0}, "wait_plan")
    check("binding: timer change in the wrong visit is rejected", not check_otf(ivw, _record_diff([w_old], [w_new]))[0])

    ivr = Intervention("case_set", "remove", case="c0003")
    arr_old = {"id": "arr_c0003", "time": 100.0, "kind": "case_arrival", "entities": ["c0003"], "fields": {}}
    arr_new = {**arr_old, "time": 10 ** 9}
    check("binding: an arrival edit is not a removal", not check_otf(ivr, _record_diff([arr_old], [arr_new]))[0])
    other = {"id": "arr_c0004", "time": 200.0, "kind": "case_arrival", "entities": ["c0004"], "fields": {}}
    plan3 = rec("work_plan_c0003_A", "c0003", {"activity": "A", "visit 1": 1.0})
    full = {**_record_diff([arr_old, plan3, other], [other]), "case_input_count": {"c0003": 2, "c0004": 1}}
    check("binding: removing all of the case's inputs is accepted", check_otf(ivr, full)[0], check_otf(ivr, full)[1])
    part = {**_record_diff([arr_old, plan3, other], [plan3, other]), "case_input_count": {"c0003": 2, "c0004": 1}}
    check("binding: removing part of the case's inputs is rejected", not check_otf(ivr, part)[0])

    one = rec("work_plan_c0013_Design loan offer_v1", "c0013", {"activity": "Design loan offer", "visit": 1, "work": 1822.0})
    moved = {**one, "time": 5000.0}
    check("binding: a change to the record's time attribute is rejected", not check_otf(iv, _record_diff([one], [moved]))[0],
          check_otf(iv, _record_diff([one], [moved]))[1])
    other_rec = rec("work_plan_c0013_X", "c0013", {"activity": "X", "visit 1": 3.0})
    d = _record_diff([good_old, other_rec], [other_rec, good_new])
    check("binding: remove and re-add at the end (order changed) is rejected", not check_otf(iv, d)[0], check_otf(iv, d)[1])
    ent_old = {"id": "wp7", "time": None, "kind": "work_plan", "entities": ["c0013", "activity:Design loan offer"], "fields": {"visit 1": 1822.0}}
    ent_new = {**ent_old, "fields": {"visit 1": 5000.0}}
    check("binding: a target named only in entities ('activity:...') is accepted", check_otf(iv, _record_diff([ent_old], [ent_new]))[0],
          check_otf(iv, _record_diff([ent_old], [ent_new]))[1])

    ivu = Intervention("resource_availability", "unavailable", target="Clerk", value=2, effective_from=100000, effective_to=130000)
    check("binding: 'unavailable' as a pool-size cut is rejected", not check_otf(ivu, {"params_changed": {"Clerk_workers": [9, 7]}})[0])
    iva = Intervention("resource_availability", "add_workers", target="Clerk", value=2)
    check("binding: add 2 with the parameter set to 100 is rejected", not check_otf(iva, {"params_changed": {"clerk_count": [9, 100]}})[0])
    check("binding: add 2 with the parameter 9 -> 11 is accepted", check_otf(iva, {"params_changed": {"clerk_count": [9, 11]}}, pool_size=9)[0])


# ---------------------------------------------------------------- probes on real documents
def probe_tests():
    pharm, loan = nav_of("workflow_pharmacy_dev"), nav_of("workflow_loan_dev")
    sp, sl = schema_from_map(pharm), schema_from_map(loan)
    p = probes.stated_probabilities(sp)
    check("probes: nested parentheses parse (Pharmacy D3 has both routes)", set(p.get("D3", {})) == {"D3-a", "D3-b"}, str(p.get("D3")))
    check("probes: every decision's stated routes cover the schema's routes",
          all(set(probes.stated_probabilities(s).get(d, {})) == set(r) for s in (sp, sl) for d, r in s.decisions.items()))
    check("probes: stated probabilities sum to 1",
          all(abs(sum(v.values()) - 1) < 1e-9 for s in (sp, sl) for v in probes.stated_probabilities(s).values()))
    pools = probes.stated_pools(sl)
    check("probes: every Loan pool has a stated calendar", set(pools) == set(sl.pools), f"{sorted(pools)} vs {sorted(sl.pools)}")
    check("probes: Loan pool sizes match the schema", all(pools[k][0] == sl.pools[k] for k in pools))
    clerk = pools["Clerk"]
    check("probes: next_open Monday 08:00 -> 09:00", probes.next_open(clerk, 8 * 3600) == 9 * 3600)
    check("probes: next_open Friday 17:00 -> Monday 09:00", probes.next_open(clerk, 4 * 86400 + 17 * 3600) == 7 * 86400 + 9 * 3600)
    check("probes: next_open inside a window is unchanged", probes.next_open(clerk, 10 * 3600) == 10 * 3600)

    n = sl.pools["Clerk"]
    edited = probes.policy_with_pool(loan, "Clerk", n, 2)
    check("probes: pool text edit applies once", edited is not None)
    if edited:
        s2 = schema_from_map(edited)
        check("probes: edited document states the larger pool", s2.pools.get("Clerk") == n + 2, str(s2.pools.get("Clerk")))
    lo = probes.policy_with_pool(loan, "Loan Officer", sl.pools["Loan Officer"], 1)
    check("probes: pool text edit works across a line break (Loan Officer)", lo is not None and schema_from_map(lo).pools["Loan Officer"] == sl.pools["Loan Officer"] + 1)
    r = probes.policy_with_routes(pharm, sp, "D3", {"D3-a": 0.3, "D3-b": 0.7})
    check("probes: route text edit applies", r is not None and probes.stated_probabilities(schema_from_map(r))["D3"] == {"D3-a": 0.3, "D3-b": 0.7},
          str(r and probes.stated_probabilities(schema_from_map(r)).get("D3")))



# ---------------------------------------------------------------- policy with fake backends
class IgnoringDEVS:
    """A program that ignores every input: always prints the factual record."""
    name = "devs_gen"
    adapter_version = "fake"

    def __init__(self, nav):
        self.nav = nav

    def program_hash(self):
        return "ignoring"

    @staticmethod
    def stdin_from_map(nav, scope):
        return {"scope": scope}

    @staticmethod
    def apply(data, iv, schema):
        return {**data, "iv": repr(iv)}

    def run_input(self, data):
        sc = data["scope"]
        ends = recorded_case_ends(self.nav, sc)
        recs = [{"event": "case_end", "case": c, "time": float(t)} for c, t in ends.items()]
        for r in probes._task_log(self.nav, sc):
            recs.append({"event": "task_start", "case": r[0], "name": r[1], "visit": int(r[2]), "time": float(r[4]), "worker": r[6]})
        for r in probes._table_rows(self.nav, sc, "Decision log"):
            recs.append({"event": "decision", "case": r[0], "name": r[1], "visit": int(r[2]), "time": float(r[3]), "route": r[4] if len(r) > 4 else None})
        return Execution("ran", case_ends={k: float(v) for k, v in ends.items()}, records=recs)


class IgnoringFree(IgnoringDEVS):
    """Like IgnoringDEVS, but with OTF's free-form record shape (time, kind, entities; no decision events)."""

    def run_input(self, data):
        sc = data["scope"]
        ends = recorded_case_ends(self.nav, sc)
        recs = [{"time": float(t), "kind": "case finished", "entities": [c], "value": None} for c, t in ends.items()]
        for r in probes._task_log(self.nav, sc):
            recs.append({"time": float(r[4]), "kind": f"task started: {r[1]}", "entities": [r[0], r[6]], "value": None})
        return Execution("ran", case_ends={k: float(v) for k, v in ends.items()}, records=recs)


class ReactingFree(IgnoringFree):
    """Free-form program that reacts to any change: adds a late record for every case (after any decision time).
    With `early`, it also adds a record at time 0, which moves the prefix."""

    def __init__(self, nav, early=False):
        super().__init__(nav)
        self.early = early

    def run_input(self, data):
        ex = super().run_input(data)
        if "iv" in data:
            ex.records += [{"time": 1e12, "kind": "changed", "entities": [c], "value": None} for c in ex.case_ends]
            if self.early:
                ex.records.append({"time": 0.0, "kind": "early", "entities": ["nobody"], "value": None})
        return ex


def route_change_tests():
    loan = nav_of("workflow_loan_dev")
    sl = schema_from_map(loan)
    st = probes.stated_probabilities(sl)
    b = IgnoringFree(loan)
    row = next(r for r in probes._table_rows(loan, "Run 01", "Decision log") if len(st.get(r[1], {})) > 1)
    dec = row[1]
    routes = sorted(st[dec])
    other = next(r for r in routes if r != row[4])
    flip = {r: (1.0 if r == other else 0.0) for r in routes}                # that recorded decision now takes another route
    run = probes.ProbeRunner(b, loan, sl)
    check("route_change: free-form records have no decision events", not run.has_decision_events("Run 01"))
    ok, why = run.route_change("Run 01", Intervention("routing_probability", "set", target=dec, routes=flip))
    check("route_change: an input-ignoring free-form program fails", ok is False, f"{ok} {why}")
    same = Intervention("routing_probability", "set", target=dec, routes=dict(st[dec]))
    r0 = probes.ProbeRunner(b, loan, sl)
    r0.no_switch_check = False
    ok, why = r0.route_change("Run 01", same)
    check("route_change: with the no-switch check off, a change that switches nothing is not run", ok is None, f"{ok} {why}")
    ok, why = probes.ProbeRunner(b, loan, sl).route_change("Run 01", same)
    check("route_change: a change that switches nothing passes when the records are unchanged", ok is True, f"{ok} {why}")
    ok, why = probes.ProbeRunner(ReactingFree(loan), loan, sl).route_change("Run 01", same)
    check("route_change: a change that switches nothing fails when the records change", ok is False, f"{ok} {why}")
    ok, why = probes.ProbeRunner(ReactingFree(loan), loan, sl).route_change("Run 01", Intervention("routing_probability", "set", target=dec, routes=flip))
    check("route_change: a program whose switched case changes after the decision passes", ok is True, f"{ok} {why}")
    ok, why = probes.ProbeRunner(ReactingFree(loan, early=True), loan, sl).route_change("Run 01", Intervention("routing_probability", "set", target=dec, routes=flip))
    check("route_change: a program whose records before the decision move fails", ok is False and "before" in why, f"{ok} {why}")
    three = {"X-a": 0.3, "X-b": 0.6, "X-c": 0.1}                            # float sum is 0.9999999999999999
    check("route_change: exact route rule where a float sum falls short of 1", probes._route_of(three, 0.9999999999999999) == "X-c",
          str(probes._route_of(three, 0.9999999999999999)))
    check("route_change: a draw within rounding of a boundary is detected", probes._near_boundary(three, 0.9000003)
          and not probes._near_boundary(three, 0.95))
    with tempfile.TemporaryDirectory() as tmp:
        reg = Registry(Path(tmp) / "r_noreuse.jsonl")
        rq = Request("Run 01", [Intervention("routing_probability", "set", target=dec, routes=flip)], Query("case_end_time", "c0001"))
        d1 = policy.decide("directed", rq, sl, probes.ProbeRunner(ReactingFree(loan), loan, sl), reg, ReactingFree(loan))
        other = {r: (1.0 if r == routes[0] else 0.0) for r in routes}
        rq2 = Request("Run 01", [Intervention("routing_probability", "set", target=dec, routes=other)], Query("case_end_time", "c0001"))
        d2 = policy.decide("directed", rq2, sl, probes.ProbeRunner(ReactingFree(loan), loan, sl), reg, ReactingFree(loan))
        check("route_change: a passing route-probability probe is not reused for another request",
              d1.permit and not any(e[0] == "reused" for e in d2.evidence) and d2.probes_run >= 1,
              f"{d1.reason} | {d2.reason} | {[e[0] for e in d2.evidence]}")
    ok, why = probes.ProbeRunner(b, loan, sl).route_change("Run 01", Intervention("routing_probability", "set", target=dec, routes={routes[0]: 1.0}))
    check("route_change: routes that do not match the stated ones are not run", ok is None, f"{ok} {why}")
    with tempfile.TemporaryDirectory() as tmp:
        reg = Registry(Path(tmp) / "r_rc.jsonl")
        d = policy.decide("directed", Request("Run 01", [Intervention("routing_probability", "set", target=dec, routes=flip)],
                                              Query("case_end_time", "c0001")), sl, probes.ProbeRunner(b, loan, sl), reg, b)
        names = [e[0] for e in d.evidence]
        check("route_change: directed uses the record form on free-form records and declines the ignoring program",
              not d.permit and not d.untested and "records routing_probability" in names and "did not change" in d.reason,
              f"{d.permit} {d.reason} {names}")
        dd = policy.decide("directed", Request("Run 01", [Intervention("routing_probability", "set", target=dec, routes=flip)],
                                               Query("case_end_time", "c0001")), sl, probes.ProbeRunner(IgnoringDEVS(loan), loan, sl), None, IgnoringDEVS(loan))
        check("route_change: records with decision events still use the rule probe",
              "rule routing_probability" in [e[0] for e in dd.evidence], str([e[0] for e in dd.evidence]))


def req(scope, iv, qcase):
    return Request(scope, [iv], Query("case_end_time", qcase))


def policy_tests():
    loan, pharm = nav_of("workflow_loan_dev"), nav_of("workflow_pharmacy_dev")
    sl, sp = schema_from_map(loan), schema_from_map(pharm)
    with tempfile.TemporaryDirectory() as tmp:
        # D3 routing request on an input-ignoring program must be declined
        b = IgnoringDEVS(pharm)
        reg = Registry(Path(tmp) / "r1.jsonl")
        run = probes.ProbeRunner(b, pharm, sp)
        scope = sp.scopes[0]
        row = probes._table_rows(pharm, scope, "Decision log")
        d3 = [r for r in row if r[1] == "D3"]
        if d3:
            iv = Intervention("routing_outcome", "set_draw", case=d3[0][0], target="D3", visit=int(d3[0][2]), value=0.5)
            d = policy.decide("directed", req(scope, iv, d3[0][0]), sp, run, reg, b)
            check("policy: input-ignoring program declined on Pharmacy D3", not d.permit, d.reason)
        else:
            check("policy: Pharmacy run has a D3 decision", False)

        # A target reached by one case only: must still be probed (own case), never permitted untested
        b = IgnoringDEVS(loan)
        reg = Registry(Path(tmp) / "r2.jsonl")
        run = probes.ProbeRunner(b, loan, sl)
        tl = probes._task_log(loan, "Run 01")
        counts = {}
        for r in tl:
            counts.setdefault(r[1], set()).add(r[0])
        single = sorted(a for a, cs in counts.items() if len(cs) == 1)
        if single:
            a = single[0]
            case = next(iter(counts[a]))
            iv = Intervention("activity_duration", "set", case=case, target=a, visit=1, value=10.0)
            d = policy.decide("directed", req("Run 01", iv, case), sl, run, reg, b)
            check(f"policy: single-case target '{a}' on an ignoring program is declined", not d.permit, d.reason)
            # the next scope must not be permitted by reuse
            iv2 = Intervention("activity_duration", "set", case=case, target=a, visit=1, value=10.0)
            d2 = policy.decide("directed", req("Run 02", iv2, case), sl, probes.ProbeRunner(b, loan, sl), reg, b)
            check("policy: a later scope is not permitted by reuse after a failure", not d2.permit, d2.reason)

        # a target with no usable witness: a passing no-op alone must not permit an input-ignoring program
        reg = Registry(Path(tmp) / "r_noop.jsonl")
        for dec in ("D3", "D5"):
            rows = [r for r in probes._table_rows(loan, "Run 01", "Decision log") if r[1] == dec]
            if not rows:
                continue
            ivd = Intervention("routing_outcome", "set_draw", case=rows[0][0], target=dec, visit=int(rows[0][2]), value=0.5)
            dd = policy.decide("directed", req("Run 01", ivd, rows[0][0]), sl, probes.ProbeRunner(b, loan, sl), reg, b)
            check(f"policy: Loan Run 01 {dec} on an ignoring program is not permitted by a no-op alone", not dd.permit, dd.reason)
            other = next((r for r in rows[1:] if r[0] != rows[0][0]), None)
            if other:
                ivo = Intervention("routing_outcome", "set_draw", case=other[0], target=dec, visit=int(other[2]), value=0.5)
                do = policy.decide("directed", req("Run 01", ivo, other[0]), sl, probes.ProbeRunner(b, loan, sl), reg, b)
                check(f"policy: a recorded no-op pass on {dec} is not reused to permit a later request", not do.permit, do.reason)
        check("probes: probabilities are written in fixed-point decimal", probes._fixed(1e-05) == "0.00001" and probes._fixed(0.5) == "0.5")

        # add_workers then unavailable: evidence must not cross operations
        reg = Registry(Path(tmp) / "r3.jsonl")
        iva = Intervention("resource_availability", "add_workers", target="Clerk", value=2)
        run = probes.ProbeRunner(b, loan, sl)
        da = policy.decide("directed", req("Run 01", iva, "c0000"), sl, run, reg, b)
        detail = next(e[2] for e in da.evidence if e[0] == "rule add_workers")   # (Phase 2 adds an exact row after it)
        check("policy: ignoring program declined for add_workers when the record shows waiting, or passed when none waited",
              da.permit == ("no task of this pool waited" in detail), detail)
        for pool in sl.pools:
            ivp = Intervention("resource_availability", "add_workers", target=pool, value=1)
            ok, why = probes.ProbeRunner(b, loan, sl).resource_rule("Run 01", ivp)
            print(f"     add_workers {pool}: {ok} {why}")
        ivu = Intervention("resource_availability", "unavailable", target="Clerk", value=2, effective_from=30000, effective_to=60000)
        du = policy.decide("directed", req("Run 02", ivu, "c0000"), sl, probes.ProbeRunner(b, loan, sl), reg, b)
        check("policy: 'unavailable' is probed on its own, not by reuse", not any(e[0] == "reused" for e in du.evidence), du.reason)

        # reuse only on the same scope; a new scope reprobes
        class Honest(IgnoringDEVS):
            pass
        reg = Registry(Path(tmp) / "r4.jsonl")
        iv = Intervention("activity_duration", "set", case="c0001", target=tl[0][1], visit=1, value=10.0)
        run = probes.ProbeRunner(b, loan, sl)
        reg.add(policy.Key(b.name, b.program_hash(), b.adapter_version, sl.policy_fingerprint(), iv.family, iv.op),
                policy.Evidence("input_use", iv.family, iv.target, "Run 01", True, "seeded pass"))
        d = policy.decide("directed", req("Run 01", iv, "c0001"), sl, probes.ProbeRunner(b, loan, sl), reg, b)
        check("policy: seeded pass on Run 01 is reused on Run 01", any(e[0] == "reused" for e in d.evidence), d.reason)
        d = policy.decide("directed", req("Run 02", iv, "c0001"), sl, run, reg, b)
        check("policy: seeded pass on Run 01 is not reused on Run 02", not any(e[0] == "reused" for e in d.evidence), d.reason)
        d = policy.decide("directed", req("Run 01", iv, "c0001"), sl, probes.ProbeRunner(b, loan, sl), reg, b)
        check("policy: after a failure on Run 02, Run 01 is blocked too", not d.permit, d.reason)

        # untested probes never count as passes
        reg = Registry(Path(tmp) / "r5.jsonl")
        reg.add(policy.Key("devs_gen", "x", "fake", "p", "f", "o"), policy.Evidence("p", "f", "t", "s", None, "not run"))
        check("registry: a not-run record leaves the state untested",
              reg.state(policy.Key("devs_gen", "x", "fake", "p", "f", "o"), "t")[0] == "untested")

        # generic: budget is honoured and the seed depends on the request
        run = probes.ProbeRunner(b, loan, sl)
        iv1 = Intervention("activity_duration", "set", case="c0001", target=tl[0][1], visit=1, value=10.0)
        iv2 = Intervention("activity_duration", "set", case="c0002", target=tl[0][1], visit=1, value=11.0)
        g1 = policy.decide("generic", req("Run 01", iv1, "c0001"), sl, run, None, b, budget=3)
        g2 = policy.decide("generic", req("Run 01", iv2, "c0002"), sl, run, None, b, budget=3)
        check("policy: generic stops at the first failure and never exceeds its budget", 1 <= g1.probes_run <= 3, str(g1.probes_run))
        picks = set()
        for k in range(6):
            ivk = Intervention("activity_duration", "set", case=f"c000{k}", target=tl[0][1], visit=1, value=10.0 + k)
            ws = policy._random_witnesses(run, sl, "Run 01", 3, __import__("random").Random(policy.request_seed(req("Run 01", ivk, f"c000{k}"), 0)))
            picks.add(tuple((w.case, w.target, w.visit) for w in ws))
        check("policy: generic picks depend on the request (6 requests, more than one witness set)", len(picks) > 1, str(len(picks)))
        g0 = policy.decide("generic", req("Run 01", iv1, "c0001"), sl, probes.ProbeRunner(b, loan, sl), None, b, budget=0)
        check("policy: generic with budget 0 still runs at least one probe", g0.probes_run >= 1, g0.reason)
        dd = policy.decide("directed", req("Run 01", iv1, "c0001"), sl, probes.ProbeRunner(b, loan, sl), None, b, budget=3)
        check("policy: directed never exceeds its budget", dd.probes_run <= 3, str(dd.probes_run))


# ---------------------------------------------------------------- contract and parser
def contract_tests():
    loan = nav_of("workflow_loan_dev")
    s = schema_from_map(loan)
    sc = s.scopes[0]
    ok_iv = Intervention("activity_duration", "set", case="c0001", target=s.activities[0], visit=1, value=10.0)
    check("contract: a plain request is ok", contract.validate(req(sc, ok_iv, "c0002"), s).ok,
          contract.validate(req(sc, ok_iv, "c0002"), s).detail)
    two = Request(sc, [ok_iv, ok_iv], Query("case_end_time", "c0002"))
    check("contract: two changes in one request are refused", contract.validate(two, s).status == "unsupported_operation")
    dec = next(iter(s.decisions))
    rp = Intervention("routing_probability", "set", case="c0001", target=dec, routes={r: 1 / len(s.decisions[dec]) for r in s.decisions[dec]})
    check("contract: case-scoped route probability is refused", contract.validate(req(sc, rp, "c0002"), s).status == "unsupported_operation")
    aw = Intervention("resource_availability", "add_workers", target="Clerk", value=1, effective_from=5000)
    check("contract: timed add_workers is refused", contract.validate(req(sc, aw, "c0002"), s).status == "unsupported_operation")
    rm = Intervention("case_set", "remove", case="c0002")
    check("contract: removing the queried case is refused", not contract.validate(req(sc, rm, "c0002"), s).ok)

    r = parse('Here you go:\n```json\n{"scope": "Run 01", "interventions": [], "query": {"kind": "case_end_time", "case": "c0001"}, '
              '"unresolved": null}\n```\nNote: {braces} in prose.')
    check("parser: fenced JSON followed by prose with braces is read", r.scope == "Run 01", r.scope)
    r = parse("I cannot do this {not json")
    check("parser: malformed reply is unresolved meaning", r.unresolved is not None and contract.validate(r, s).status == "unresolved_meaning",
          str(r.unresolved))


def fingerprint_tests():
    """Policy fingerprint (Ashraf, 2026-11-09): the closing chapter list is not policy; any policy edit is."""
    import copy
    from assurance import probes
    from assurance.request import schema_from_map
    nav = nav_of("workflow_loan_dev")
    s = schema_from_map(nav)
    front = next(n for n in nav["nodes"] if n["level"] == 0 and n["kind"] == "list")

    def with_lines(f):
        out = copy.deepcopy(nav)
        node = next(n for n in out["nodes"] if n["level"] == 0 and n["kind"] == "list")
        node["lines"] = f(list(front["lines"]))
        return schema_from_map(out).policy_fingerprint()
    other = lambda ls: [l.replace("Run 01, Run 02, Run 03, Run 04.", "Run 05, Run 06,") for l in ls] + ["Run 07."]
    check("fingerprint: the edited front matter really lists other chapters", other(front["lines"]) != front["lines"]
          and "Run 05" in " ".join(other(front["lines"])))
    check("fingerprint: another chapter list gives the same fingerprint", with_lines(other) == s.policy_fingerprint())
    check("fingerprint: no chapter list gives the same fingerprint", with_lines(lambda ls: [l for l in ls if "Chapters in" not in l]) == s.policy_fingerprint())
    check("fingerprint: text after the chapter list is policy", with_lines(lambda ls: ls + ["Clerk works weekends."]) != s.policy_fingerprint())
    check("fingerprint: a worker-count edit changes it", schema_from_map(probes.policy_with_pool(nav, "Clerk", 9, 1)).policy_fingerprint() != s.policy_fingerprint())
    check("fingerprint: a route-probability edit changes it",
          schema_from_map(probes.policy_with_routes(nav, s, "D1", {"D1-a": 0.5, "D1-b": 0.5})).policy_fingerprint() != s.policy_fingerprint())
    check("fingerprint: Loan and Pharmacy differ", schema_from_map(nav_of("workflow_pharmacy_dev")).policy_fingerprint() != s.policy_fingerprint())


# ---------------------------------------------------------------- full review, 2026-11-09
def review3_tests():
    loan = nav_of("workflow_loan_dev")
    sl = schema_from_map(loan)
    ign = IgnoringDEVS(loan)
    # 1. route rule: a change that switches only a later visit must catch an input-ignoring program
    iv = Intervention("routing_probability", "set", target="D1", routes={"D1-a": 0.1124, "D1-b": 0.8876})
    run = probes.ProbeRunner(ign, loan, sl)
    ok, why = run.route_rule("Run 01", iv)
    check("review3: route rule catches an ignoring program when only a later visit switches", ok is False, f"{ok} {why}")
    with tempfile.TemporaryDirectory() as tmp:
        d = policy.decide("directed", Request("Run 01", [iv], Query("case_end_time", "c0001")), sl,
                          probes.ProbeRunner(ign, loan, sl), Registry(Path(tmp) / "r1.jsonl"), ign)
        check("review3: directed declines the ignoring program on that request", not d.permit, d.reason)
    st = probes.stated_probabilities(sl)["D1"]
    ok, why = probes.ProbeRunner(ign, loan, sl).route_rule("Run 01", Intervention("routing_probability", "set", target="D1", routes=dict(st)))
    check("review3: route rule passes when nothing switches and the records are unchanged", ok is True, f"{ok} {why}")

    class NullVisit(IgnoringDEVS):
        def run_input(self, data):
            ex = super().run_input(data)
            for r in ex.records:
                if r.get("event") == "decision":
                    r["visit"] = None
            return ex
    nv = NullVisit(loan)
    try:
        ok, why = probes.ProbeRunner(nv, loan, sl).route_rule("Run 01", iv)
        check("review3: a decision event with no visit does not crash the route rule", ok in (None, False), f"{ok} {why}")
    except Exception as e:
        check("review3: a decision event with no visit does not crash the route rule", False, repr(e))
    # 2. no reuse of a rule pass across unavailable intervals
    with tempfile.TemporaryDirectory() as tmp:
        reg = Registry(Path(tmp) / "r2.jsonl")
        a = Intervention("resource_availability", "unavailable", target="Clerk", value=2, effective_from=0, effective_to=3600)
        b = Intervention("resource_availability", "unavailable", target="Clerk", value=2, effective_from=36097, effective_to=39697)
        policy.decide("directed", Request("Run 01", [a], Query("case_end_time", "c0001")), sl, probes.ProbeRunner(ign, loan, sl), reg, ign)
        d2 = policy.decide("directed", Request("Run 01", [b], Query("case_end_time", "c0001")), sl, probes.ProbeRunner(ign, loan, sl), reg, ign)
        check("review3: an unavailable pass on one interval is not reused for another", not any(e[0] == "reused" for e in d2.evidence),
              f"{d2.reason} {[e[0] for e in d2.evidence]}")
        check("review3: the second interval is probed and the ignoring program is caught", not d2.permit and "unavailable" in d2.reason, d2.reason)
    # 3. NaN and infinity are malformed
    q = Query("case_end_time", "c0001")
    nanroutes = Intervention("routing_probability", "set", target="D1", routes={"D1-a": float("nan"), "D1-b": float("nan")})
    check("review3: NaN route probabilities are invalid", contract.validate(Request("Run 01", [nanroutes], q), sl).status == "invalid_units")
    for fam, op, extra in (("activity_duration", "set", {"case": "c0001", "target": sl.activities[0], "visit": 1}),
                           ("resource_availability", "add_workers", {"target": "Clerk"})):
        for bad in (float("nan"), float("inf")):
            try:
                r = contract.validate(Request("Run 01", [Intervention(fam, op, value=bad, **extra)], q), sl)
                check(f"review3: {fam} value {bad} is invalid, not an exception", r.status == "invalid_units", r.status)
            except Exception as e:
                check(f"review3: {fam} value {bad} is invalid, not an exception", False, repr(e))
    r = contract.validate(Request("Run 01", [Intervention("case_set", "remove", case="c0002")], Query("case_ends_by", "c0001", float("inf"))), sl)
    check("review3: an infinite deadline is invalid", r.status == "invalid_time", r.status)
    reply = json.dumps({"scope": "Run 01", "interventions": [{"family": "activity_duration", "op": "set", "case": "c0001",
                        "target": sl.activities[0], "visit": 1, "value": "NaN"}], "query": {"kind": "case_end_time", "case": "c0001"}})
    check("review3: a NaN value from the interpreter is rejected by the contract",
          contract.validate(parse(reply), sl).status in ("invalid_units", "unresolved_meaning"))
    # 4. program_wide: one verdict per program and scope
    acts = [Intervention("activity_duration", "set", case="c0001", target=a_, visit=1, value=100) for a_ in sl.activities[:4]]
    picks = []
    for x in acts:
        d = policy.decide("program_wide", Request("Run 01", [x], q), sl, probes.ProbeRunner(ign, loan, sl), None, ign)
        picks.append(tuple((e[0], e[2]) for e in d.evidence))
    check("review3: program_wide picks the same witnesses for every request on a scope", len(set(picks)) == 1, str(len(set(picks))))
    # 5. generic: no repeated witness
    dup = 0
    for k in range(60):
        x = Intervention("activity_duration", "set", case="c0001", target=sl.activities[k % len(sl.activities)], visit=1, value=100 + k)
        d = policy.decide("generic", Request("Run 01", [x], q), sl, probes.ProbeRunner(ign, loan, sl), None, ign)
        ws = [e[2] for e in d.evidence if e[0].startswith("input_use")]
        dup += len(ws) != len(set(ws))
    check("review3: generic never repeats a witness", dup == 0, str(dup))
    # 6. route-flip witnesses need only printed inputs and change an activity or wait
    for doc in ("workflow_loan_dev", "workflow_pharmacy_dev"):
        nav = nav_of(doc)
        s = schema_from_map(nav)
        bad_walk = bad_flip = n = 0
        for sc in s.scopes:
            tl, wl = probes._table_rows(nav, sc, "Task log"), probes._table_rows(nav, sc, "Wait log")
            for c in s.cases[sc]:
                items, ok = probes.flow_walk(nav, s, sc, c)
                want = sorted([(r[1], int(r[2])) for r in tl if r[0] == c] + [(r[1], int(r[2])) for r in wl if r[0] == c])
                bad_walk += (not ok) or items != want
            for r in probes._table_rows(nav, sc, "Decision log"):
                w = Intervention("routing_outcome", "set_draw", case=r[0], target=r[1], visit=int(r[2]))
                pw = probes.perturb(nav, s, sc, w)
                if pw is None:
                    continue
                n += 1
                base, _ = probes.flow_walk(nav, s, sc, r[0])
                flipped, ok = probes.flow_walk(nav, s, sc, r[0], {(r[1], int(r[2])): pw.value})
                bad_flip += (not ok) or flipped == base
        check(f"review3: {doc} stated flow reproduces every recorded case path", bad_walk == 0, str(bad_walk))
        check(f"review3: {doc} every usable route flip is printed and changes the case ({n} flips)", bad_flip == 0 and n > 0, f"{bad_flip} of {n}")
    for doc, sc, case, dec in (("workflow_pharmacy_policyP", "Run 13", "c0010", "D7"), ("workflow_loan_policyP", "Run 13", "c0014", "D4")):
        pol = ROOT / f"runs/workflow_docs/{doc}/navmap.json"
        if pol.exists():
            nav = json.loads(pol.read_text(encoding="utf-8"))
            s = schema_from_map(nav)
            w = Intervention("routing_outcome", "set_draw", case=case, target=dec, visit=1)
            check(f"review3: the misfiring flip ({doc} {sc} {case} {dec}) is not used", probes.perturb(nav, s, sc, w) is None)


# ---------------------------------------------------------------- review 4 of the 2026-11-09 fixes
def review4_tests():
    import copy as _copy
    loan = nav_of("workflow_loan_dev")
    sl = schema_from_map(loan)
    iv = Intervention("routing_probability", "set", target="D1", routes={"D1-a": 0.1124, "D1-b": 0.8876})
    draws = probes.ProbeRunner(None, loan, sl)._route_draws("Run 01", "D1")

    class RightDecisionsOnly(IgnoringDEVS):
        """Records every decision with the route the stated rule gives under the change, but copies every other
        record from the factual run: it reports the new routes without acting on them."""
        def run_input(self, data):
            ex = super().run_input(data)
            if "iv" in data:
                for r in ex.records:
                    if r.get("event") == "decision" and r.get("name") == "D1":
                        u = draws.get((r["case"], r["visit"]))
                        if u is not None:
                            r["route"] = probes._route_of(iv.routes, u)
            return ex
    ok, why = probes.ProbeRunner(RightDecisionsOnly(loan), loan, sl).route_rule("Run 01", iv)
    check("review4: right decision records with unchanged activities are caught", ok is False and "activities" in why, f"{ok} {why}")

    class NoEnds(IgnoringDEVS):
        def run_input(self, data):
            ex = super().run_input(data)
            if "iv" in data:
                ex.records = [r for r in ex.records if r.get("event") != "case_end"]
            return ex
    nd = NoEnds(loan)
    run = probes.ProbeRunner(nd, loan, sl)
    run.base("Run 01")
    ok, why = run.route_rule("Run 01", iv)
    check("review4: a run with case ends missing is not trusted", ok is not True, f"{ok} {why}")
    # parser: infinite numbers are malformed, not a crash
    for reply in ('{"scope":"Run 01","interventions":[],"query":{"kind":"case_ends_by","case":"c0001","deadline":Infinity}}',
                  '{"scope":"Run 01","interventions":[{"family":"activity_duration","op":"set","case":"c0001","target":"x","visit":1e999,"value":5}],'
                  '"query":{"kind":"case_end_time","case":"c0001"}}'):
        try:
            r = parse(reply)
            check("review4: the parser handles infinite numbers without crashing", True)
        except Exception as e:
            check("review4: the parser handles infinite numbers without crashing", False, repr(e))
    check("review4: an over-large integer is not finite", not contract._finite(10 ** 400))
    # an unreadable flow means no route-flip witness
    broken = _copy.deepcopy(loan)
    front = next(n for n in broken["nodes"] if n["level"] == 0 and n["kind"] == "list")
    front["lines"] = [l.replace("Process.", "Flow.") for l in front["lines"]]
    sb = schema_from_map(broken)
    row = next(r for r in probes._table_rows(loan, "Run 01", "Decision log"))
    w = Intervention("routing_outcome", "set_draw", case=row[0], target=row[1], visit=int(row[2]))
    check("review4: with an unreadable flow no route flip is used", probes.perturb(broken, sb, "Run 01", w) is None)
    # case removal passes are family-level and still reused on the same scope
    with tempfile.TemporaryDirectory() as tmp:
        reg = Registry(Path(tmp) / "r4.jsonl")
        class Remover(IgnoringFree):
            """Drops every record of a removed case; ignores every other change."""
            @staticmethod
            def apply(data, iv, schema):
                return {**data, "iv": repr(iv), "drop": iv.case if iv.family == "case_set" else None}

            def run_input(self, data):
                ex = super().run_input(data)
                if data.get("drop"):
                    ex.records = [r for r in ex.records if data["drop"] not in (r.get("entities") or [])]
                    ex.case_ends.pop(data["drop"], None)
                return ex
        b = Remover(loan)
        q = Query("case_end_time", "c0001")
        d1 = policy.decide("directed", Request("Run 01", [Intervention("case_set", "remove", case="c0003")], q), sl, probes.ProbeRunner(b, loan, sl), reg, b)
        d2 = policy.decide("directed", Request("Run 01", [Intervention("case_set", "remove", case="c0004")], q), sl, probes.ProbeRunner(b, loan, sl), reg, b)
        passed1 = any(e[0] == "rule case_removal" and e[1] is True for e in d1.evidence)
        check("review4: a case-removal pass is reused for another removal on the same scope",
              passed1 and any(e[0] == "reused" for e in d2.evidence), f"{d1.reason} | {d2.reason} | {[e[0] for e in d2.evidence]}")


# ---------------------------------------------------------------- review 5
def review5_tests():
    loan = nav_of("workflow_loan_dev")
    sl = schema_from_map(loan)
    iv = Intervention("routing_probability", "set", target="D1", routes={"D1-a": 0.1124, "D1-b": 0.8876})
    draws = probes.ProbeRunner(None, loan, sl)._route_draws("Run 01", "D1")

    class RightRoutes(IgnoringDEVS):
        """Records the routes the stated rule gives under the change; copies everything else."""
        def run_input(self, data):
            ex = super().run_input(data)
            if "iv" in data:
                for r in ex.records:
                    if r.get("event") == "decision" and r.get("name") == "D1" and (r["case"], r["visit"]) in draws:
                        r["route"] = probes._route_of(iv.routes, draws[(r["case"], r["visit"])])
            return ex

    class DecisionsOnly(RightRoutes):
        def run_input(self, data):
            ex = super().run_input(data)
            ex.records = [r for r in ex.records if r.get("event") in ("decision", "case_end")]
            return ex
    ok, why = probes.ProbeRunner(DecisionsOnly(loan), loan, sl).route_rule("Run 01", iv)
    check("review5: records with no task events are Untestable, never Trusted", ok is None and "no tasks" in why, f"{ok} {why}")

    class SomeStarts(RightRoutes):
        def run_input(self, data):
            ex = super().run_input(data)
            ex.records = [r for r in ex.records if r.get("event") != "task_start" or str(r.get("name"))[:1] < "N"]
            return ex
    ok, why = probes.ProbeRunner(SomeStarts(loan), loan, sl).route_rule("Run 01", iv)
    check("review5: a partial task shape is not comparable (Untestable), not Caught", ok is None and "cannot be compared" in why, f"{ok} {why}")


def phase2_tests():
    """Exact stated-rule checks (manifests/blindspots.md): the calendar arithmetic, and the printed record itself
    passing the timing check (it is computed by the stated rules), with a one-minute error caught."""
    from assurance.backends import Execution
    wk = (1, 0, 4, 9 * 3600, 17 * 3600)                                  # Monday to Friday 09:00 to 17:00
    check("phase2: work crosses the night", probes.work_end(wk, 16 * 3600, 7200) == 86400 + 10 * 3600)
    check("phase2: exactly the time left ends at closing", probes.work_end(wk, 16 * 3600, 3600) == 17 * 3600)
    check("phase2: Friday work resumes on Monday", probes.work_end(wk, 4 * 86400 + 16 * 3600, 7200) == 7 * 86400 + 10 * 3600)
    check("phase2: an unavailable block pauses work", probes.work_end(wk, 9 * 3600, 3600, [(9 * 3600 + 1800, 10 * 3600)]) == 10 * 3600 + 1800)
    allweek = (1, 0, 6, 0, 23 * 3600 + 59 * 60)                          # Monday to Sunday 00:00 to 23:59
    check("phase2: the last minute of a day is not working time", probes.work_end(allweek, 0, 86400) == 86400 + 60)
    for doc in ("workflow_loan_dev", "workflow_pharmacy_dev"):
        nav = nav_of(doc)
        s = schema_from_map(nav)
        pools = probes.activity_pools(s)
        check(f"phase2: every activity's pool is read ({doc})", set(pools) == set(s.activities) and set(pools.values()) <= set(s.pools),
              str(set(s.activities) - set(pools)))
        runner = probes.ProbeRunner(None, nav, s)
        for scope in s.scopes:
            recs = []
            for r in probes._table_rows(nav, scope, "Task log"):
                recs += [{"time": int(r[4]), "case": r[0], "event": "task_start", "name": r[1], "visit": int(r[2]), "worker": r[6]},
                         {"time": int(r[5]), "case": r[0], "event": "task_end", "name": r[1], "visit": int(r[2]), "worker": r[6]}]
            for r in probes._table_rows(nav, scope, "Wait log"):
                recs += [{"time": int(r[3]), "case": r[0], "event": "wait_start", "name": r[1], "visit": int(r[2])},
                         {"time": int(r[4]), "case": r[0], "event": "wait_end", "name": r[1], "visit": int(r[2])}]
            runner._base[scope] = Execution("ran", records=recs)      # the printed record as the factual run
            ok, why = runner._timing(scope, Execution("ran", records=recs), None)
            check(f"phase2: the printed record passes the timing check ({doc} {scope})", ok is True, why)
            bad = [dict(x) for x in recs]
            j = next(i for i, x in enumerate(bad) if x["event"] == "task_end")
            bad[j]["time"] += 60
            check(f"phase2: a task ending a minute late fails it ({doc} {scope})", runner._timing(scope, Execution("ran", records=bad), None)[0] is False)


if __name__ == "__main__":
    phase2_tests()
    fingerprint_tests()
    binding_tests()
    probe_tests()
    policy_tests()
    route_change_tests()
    contract_tests()
    review3_tests()
    review4_tests()
    review5_tests()
    print(f"\n{len(FAILS)} failures")
    sys.exit(len(FAILS))
