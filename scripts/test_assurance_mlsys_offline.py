"""Offline checks of `assurance.mlsys` (manufacturing and IT operations). No model calls, no WSL, no reference code.

Uses the real document maps (runs/mlsys_docs/<doc>/navmap.json, built by otf_r1.navmap from the committed PDFs),
the real input records of Claude R1 programs (read with their own reading functions; nothing is simulated by the
reference), OTF's own patch application (`records.apply_patches`) with hand-written patches, and fake stdin
programs. Each check prints PASS or FAIL; the exit code is the number of failures.

Usage: python -X utf8 scripts/test_assurance_mlsys_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "redesign")]
sys.dont_write_bytecode = True

from assurance import mlsys as M                       # noqa: E402
from assurance.backends import _count_by_case, _record_diff   # noqa: E402
from assurance.registry import Registry                # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def nav(doc):
    p = ROOT / "runs" / "mlsys_docs" / doc / "navmap.json"
    if not p.exists():
        from otf_r1 import navmap
        p.parent.mkdir(parents=True, exist_ok=True)
        blob = __import__("subprocess").run(["git", "-C", str(ROOT / "baseline" / "otf-tools-10f5401"), "show",
                                             f"HEAD:implementation-1/runs/{doc}/document.pdf"], capture_output=True, check=True).stdout
        (p.parent / "document.pdf").write_bytes(blob)
        p.write_text(json.dumps(navmap.build_map(p.parent / "document.pdf")))
    return json.loads(p.read_text())


MNAV, INAV = nav("mfg_dev"), nav("itops_dev")
MS, IS = M.schema_from_map(MNAV), M.schema_from_map(INAV)
MSC, ISC = "Plant 1912, Period 01", "Cell window 08"


def req(scope, iv, q):
    return M.DRequest(scope, [iv], q)


# ---------------------------------------------------------------- schema
def schema_tests():
    check("schema: domains detected", MS.domain == M.MFG and IS.domain == M.IT)
    check("schema: 4 mfg chapters, 4 IT windows", len(MS.scopes) == 4 and len(IS.scopes) == 4, f"{MS.scopes} {IS.scopes}")
    caps = {s: c["capacity_kg"] for s, c in MS.chapters.items()}
    check("schema: every capacity parsed, including a line-broken 'kg'", all(caps.values()), str(caps))
    ch = MS.chapters[MSC]
    check("schema: ledger 14 days x 3 products, book 7 days", len(ch["ledger"]) == 42 and len(ch["book_days"]) == 7)
    ich = IS.chapters[ISC]
    check("schema: IT window has W, 8 machines, 85 tasks", ich["W"] == 1200 and len(ich["machines"]) == 8 and len(ich["tasks"]) == 85)
    check("schema: policy fingerprint differs between domains", MS.policy_fingerprint() != IS.policy_fingerprint())


# ---------------------------------------------------------------- contract
def contract_tests():
    q = M.DQuery("stock_end_of_day", "ATN02K12P", day=10)
    ok = lambda s, sc, iv, qq=q: M.validate(req(sc, iv, qq), s)
    check("contract: valid production change", ok(MS, MSC, M.Change("production_quantity", "set", "ATN02K12P", 5, 0.0)).ok)
    check("contract: unknown product", ok(MS, MSC, M.Change("production_quantity", "set", "NOPE", 5, 0.0)).status == "unknown_target")
    check("contract: query day outside the ledger", ok(MS, MSC, M.Change("production_quantity", "set", "ATN02K12P", 5, 0.0),
                                                      M.DQuery("stock_end_of_day", "ATN02K12P", day=30)).status == "invalid_time")
    check("contract: fractional units", ok(MS, MSC, M.Change("production_quantity", "set", "ATN02K12P", 5, 1.5)).status == "invalid_units")
    no_order = next((d for d in range(1, 15) if MS.chapters[MSC]["ledger"][(d, "MAR02K12P")]["ordered"] == 0), None)
    if no_order:
        check("contract: removing an order that was not placed",
              ok(MS, MSC, M.Change("order_removal", "remove", "MAR02K12P", no_order)).status == "unknown_target")
    check("contract: capacity factor must be positive", ok(MS, MSC, M.Change("dispatch_capacity", "scale", day=1, value=0.0)).status == "invalid_units")
    check("contract: IT family on a manufacturing document", ok(MS, MSC, M.Change("job_removal", "remove", "J01")).status == "unsupported_operation")
    check("contract: two changes are unsupported",
          M.validate(M.DRequest(MSC, [M.Change("order_removal", "remove", "ATN02K12P", 1)] * 2, q), MS).status == "unsupported_operation")
    t = IS.chapters[ISC]["tasks"]
    task = sorted(t)[0]
    iq = M.DQuery("task_start_time", task)
    check("contract: removing the queried task's job is unsupported",
          M.validate(req(ISC, M.Change("job_removal", "remove", t[task]["job"]), iq), IS).status == "unsupported_operation")
    check("contract: priority out of range", M.validate(req(ISC, M.Change("task_priority", "set", task, value=12.0), iq), IS).status == "invalid_units")
    check("contract: request without a resource", M.validate(req(ISC, M.Change("task_request", "set", task, value=5.0), iq), IS).status == "ambiguous_binding")
    healthy = next(m for m, a in IS.chapters[ISC]["machines"].items() if a["down"] is None)
    check("contract: removing a failure that is not recorded",
          M.validate(req(ISC, M.Change("failure_removal", "remove", healthy), iq), IS).status == "unknown_target")
    check("contract: unresolved meaning", M.validate(M.DRequest(ISC, [], iq, unresolved="x"), IS).status == "unresolved_meaning")


# ---------------------------------------------------------------- parse and answers
def parse_tests():
    r = M.parse('```json\n{"scope": "Plant 1912, Period 01", "interventions": [{"family": "production_timing", "op": "delay", '
                '"target": "ATN02K12P", "day": 3, "value": 2}], "query": {"kind": "stock_end_of_day", "product": "ATN02K12P", "day": 9}}\n```', M.MFG)
    check("parse: manufacturing reply", r.interventions == [M.Change("production_timing", "delay", "ATN02K12P", 3, 2.0)]
          and r.query == M.DQuery("stock_end_of_day", "ATN02K12P", 9), str(r))
    r = M.parse('{"scope": "Cell window 08", "interventions": [{"family": "task_request", "op": "set", "target": "T010", '
                '"resource": "mem", "value": 40}], "query": {"kind": "task_starts_by", "task": "T010", "deadline": 300}}', M.IT)
    check("parse: IT reply", r.interventions[0].resource == "mem" and r.query.deadline == 300 and r.query.entity == "T010")
    check("parse: malformed reply is unresolved", M.parse("no json here", M.IT).unresolved is not None)
    check("parse: bad number is malformed", M.parse('{"scope": "x", "interventions": [{"family": "task_priority", "value": "high"}], '
                                                    '"query": {}}', M.IT).unresolved == "malformed intervention")
    canon = M.printed(MS, MSC)
    v, _ = M.answer(M.DQuery("stock_end_of_day", "ATN02K12P", 1), canon)
    check("answer: printed stock on day 1", v == MS.chapters[MSC]["ledger"][(1, "ATN02K12P")]["stock"])
    ican = M.printed(IS, ISC)
    first = min(e for e in ican if e[1] == "start")
    v, _ = M.answer(M.DQuery("task_start_time", first[2]), ican)
    b, _ = M.answer(M.DQuery("task_starts_by", first[2], deadline=first[0] - 1), ican)
    check("answer: first start and starts-by", v == first[0] and b is False)
    check("answer: missing task gives no answer", M.answer(M.DQuery("task_start_time", "T999"), ican)[0] is None)
    p = M.build_prompt = M.prompt_for("In Cell window 08, suppose ...", IS)
    check("interpreter prompt: names the scopes, not gold", "Cell window 08" in p and "gold" not in p.lower())


# ---------------------------------------------------------------- edits: document map route equals stdin route
def edit_tests():
    cases = [(MS, MNAV, MSC, M.Change("order_removal", "remove", "ATN02K12P", 1)),
             (MS, MNAV, MSC, M.Change("production_quantity", "set", "MAR02K12P", 14, 999.0)),
             (MS, MNAV, MSC, M.Change("production_timing", "delay", "ATN02K12P", 13, 3.0)),
             (IS, INAV, ISC, M.Change("job_removal", "remove", "J05")),
             (IS, INAV, ISC, M.Change("failure_removal", "remove", "M02")),
             (IS, INAV, ISC, M.Change("task_priority", "set", "T020", value=11.0)),
             (IS, INAV, ISC, M.Change("task_request", "set", "T020", value=7.0, resource="mem")),
             (IS, INAV, ISC, M.Change("machine_removal", "remove", "M03"))]
    for s, nv, sc, iv in cases:
        e = M.edit_nav(nv, s, sc, iv, {})
        a = M.inputs_from_schema(M.schema_from_map(e[0]), sc) if e else None
        b = M.apply_inputs(M.inputs_from_schema(s, sc), iv)
        check(f"edit: {iv.family} written the same way into the map and the stdin input", a == b and a != M.inputs_from_schema(s, sc))
    cap = MS.chapters[MSC]["capacity_kg"]
    e = M.edit_nav(MNAV, MS, MSC, M.Change("dispatch_capacity", "scale", day=1, value=0.8), {"cap_kg": float(cap)})
    check("edit: capacity from the first day is a constant edit", e is not None and e[1] == {"cap_kg": cap * 0.8})
    check("edit: capacity from a later day cannot be written into a single constant",
          M.edit_nav(MNAV, MS, MSC, M.Change("dispatch_capacity", "scale", day=5, value=0.8), {"cap_kg": float(cap)}) is None)
    check("edit: capacity with two candidate constants is refused",
          M.edit_nav(MNAV, MS, MSC, M.Change("dispatch_capacity", "scale", day=1, value=0.8), {"a": cap, "b": cap}) is None)
    d = M.apply_inputs(M.inputs_from_schema(MS, MSC), M.Change("dispatch_capacity", "scale", day=5, value=0.5))
    check("stdin: capacity from a later day changes only those days",
          all((x["capacity_kg"] == cap) == (x["day"] < 5) for x in d["days"]))


# ---------------------------------------------------------------- binding check on real OTF input records
def otf_inputs(build, scope):
    from otf_r1 import toolgen
    p = ROOT / "runs" / "build_test_r1_claude" / build
    code = json.loads((p / "program.json").read_text(encoding="utf-8"))["code"]
    with tempfile.TemporaryDirectory() as t:
        m = Path(t) / "m.json"
        m.write_text((p / "navmap.json").read_text())
        return toolgen.read_scope(code, m, scope)


def bind(r, patches):
    from otf_r1 import records
    from otf_r1.engine import OTFEngine
    names = OTFEngine._names(r)
    ap = records.apply_patches(r["inputs"], r["params"], r["outcomes"], patches, names, r["t0"])
    return {"errors": ap["errors"], "overrides": ap["overrides"], "t_star": ap["t_c"],
            "params_changed": {k: [r["params"].get(k), v] for k, v in ap["params"].items() if r["params"].get(k) != v},
            "case_input_count": _count_by_case(r["inputs"]), **_record_diff(r["inputs"], ap["inputs"])}


def binding_tests():
    for build in ("claude-sonnet-5-5/mfg_dev/b1", "claude-haiku-5-5/mfg_dev/b2"):
        r = otf_inputs(build, MSC)
        tag = build.split("/")[0].split("-")[1]
        kinds = {x["kind"] for x in r["inputs"]}
        prod_kind = next(k for k in sorted(kinds) if "production" in k and "plan" not in k)
        order_kind = next((k for k in kinds if k == "order"), prod_kind)
        prod_field = next(f for x in r["inputs"] if x["kind"] == prod_kind for f in x["fields"] if "order" not in f.lower())
        order_field = next(f for x in r["inputs"] if x["kind"] == order_kind for f in x["fields"]
                           if ("order" in f.lower()) or order_kind == "order")
        iv = M.Change("production_quantity", "set", "ATN02K12P", 5, 777.0)
        good = [{"op": "set", "select": {"entity": "ATN02K12P", "kind": prod_kind, "time": 5}, "field": prod_field, "value": 777}]
        check(f"binding {tag}: production set accepted", M.check_otf(iv, bind(r, good), MS, MSC)[0], M.check_otf(iv, bind(r, good), MS, MSC)[1])
        wrong_day = [{"op": "set", "select": {"entity": "ATN02K12P", "kind": prod_kind, "time": 6}, "field": prod_field, "value": 777}]
        check(f"binding {tag}: wrong day rejected", not M.check_otf(iv, bind(r, wrong_day), MS, MSC)[0])
        wrong_prod = [{"op": "set", "select": {"entity": "MAR02K12P", "kind": prod_kind, "time": 5}, "field": prod_field, "value": 777}]
        check(f"binding {tag}: wrong product rejected", not M.check_otf(iv, bind(r, wrong_prod), MS, MSC)[0])
        wrong_field = [{"op": "set", "select": {"entity": "ATN02K12P", "kind": order_kind, "time": 5}, "field": order_field, "value": 777}]
        check(f"binding {tag}: order changed instead of production rejected", not M.check_otf(iv, bind(r, wrong_field), MS, MSC)[0])
        ivo = M.Change("order_removal", "remove", "ATN02K12P", 5)
        if order_kind == prod_kind:
            good_o = [{"op": "set", "select": {"entity": "ATN02K12P", "kind": order_kind, "time": 5}, "field": order_field, "value": 0}]
            bad_o = [{"op": "remove", "select": {"entity": "ATN02K12P", "kind": order_kind, "time": 5}}]
        else:
            good_o = [{"op": "remove", "select": {"entity": "ATN02K12P", "kind": order_kind, "time": 5}}]
            bad_o = [{"op": "remove", "select": {"entity": "ATN02K12P", "kind": prod_kind, "time": 5}}]
        check(f"binding {tag}: order removal accepted", M.check_otf(ivo, bind(r, good_o), MS, MSC)[0], M.check_otf(ivo, bind(r, good_o), MS, MSC)[1])
        check(f"binding {tag}: removing production too (or instead) rejected", not M.check_otf(ivo, bind(r, bad_o), MS, MSC)[0])
        ivt = M.Change("production_timing", "delay", "ATN02K12P", 5, 2.0)
        q5 = MS.chapters[MSC]["ledger"][(5, "ATN02K12P")]["produced"]
        q7 = MS.chapters[MSC]["ledger"][(7, "ATN02K12P")]["produced"]
        good_t = [{"op": "set", "select": {"entity": "ATN02K12P", "kind": prod_kind, "time": 5}, "field": prod_field, "value": 0},
                  {"op": "set", "select": {"entity": "ATN02K12P", "kind": prod_kind, "time": 7}, "field": prod_field, "value": q5 + q7}]
        res = M.check_otf(ivt, bind(r, good_t), MS, MSC)
        check(f"binding {tag}: delay as two production cells accepted", res[0] or q5 == 0, res[1])
        half = good_t[:1]
        check(f"binding {tag}: delay that only removes production rejected", q5 == 0 or not M.check_otf(ivt, bind(r, half), MS, MSC)[0])
        shift = [{"op": "shift", "select": {"entity": "ATN02K12P", "kind": prod_kind, "time": 5}, "by": 2}]
        res = M.check_otf(ivt, bind(r, shift), MS, MSC)
        check(f"binding {tag}: delay as a shifted record is {'accepted' if prod_kind != 'daily_production_order' else 'rejected (it moves the order too)'}",
              res[0] == (prod_kind != "daily_production_order"), res[1])
        cap_key = next(k for k, v in r["params"].items() if M._num(v) == MS.chapters[MSC]["capacity_kg"])
        ivc = M.Change("dispatch_capacity", "scale", day=1, value=0.8)
        check(f"binding {tag}: capacity scale from day 1 accepted",
              M.check_otf(ivc, bind(r, [{"op": "scale", "param": cap_key, "factor": 0.8}]), MS, MSC)[0])
        ivc5 = M.Change("dispatch_capacity", "scale", day=5, value=0.8)
        check(f"binding {tag}: capacity from day 5 accepted only with from=5",
              M.check_otf(ivc5, bind(r, [{"op": "scale", "param": cap_key, "factor": 0.8, "from": 5}]), MS, MSC)[0]
              and not M.check_otf(ivc5, bind(r, [{"op": "scale", "param": cap_key, "factor": 0.8}]), MS, MSC)[0])
        check(f"binding {tag}: wrong factor rejected",
              not M.check_otf(ivc, bind(r, [{"op": "scale", "param": cap_key, "factor": 0.5}]), MS, MSC)[0])
    for build in ("claude-sonnet-5-5/itops_dev/b1", "claude-haiku-5-5/itops_dev/b1"):
        r = otf_inputs(build, ISC)
        tag = build.split("/")[0].split("-")[1]
        kinds = {x["kind"] for x in r["inputs"]}
        sub = next(k for k in kinds if "sub" in k)
        fail = next(k for k in kinds if "fail" in k)
        ivp = M.Change("task_priority", "set", "T020", value=11.0)
        check(f"binding {tag}: priority set accepted",
              M.check_otf(ivp, bind(r, [{"op": "set", "select": {"entity": "T020", "kind": sub}, "field": "priority", "value": 11}]), IS, ISC)[0])
        check(f"binding {tag}: priority on another task rejected",
              not M.check_otf(ivp, bind(r, [{"op": "set", "select": {"entity": "T021", "kind": sub}, "field": "priority", "value": 11}]), IS, ISC)[0])
        ivr = M.Change("task_request", "set", "T020", value=50.0, resource="mem")
        check(f"binding {tag}: request on the wrong resource rejected",
              not M.check_otf(ivr, bind(r, [{"op": "set", "select": {"entity": "T020", "kind": sub}, "field": "CPU", "value": 50}]), IS, ISC)[0])
        check(f"binding {tag}: memory request accepted",
              M.check_otf(ivr, bind(r, [{"op": "set", "select": {"entity": "T020", "kind": sub}, "field": "memory", "value": 50}]), IS, ISC)[0])
        job = IS.chapters[ISC]["tasks"]["T020"]["job"]
        tasks = [t for t, a in IS.chapters[ISC]["tasks"].items() if a["job"] == job]
        ivj = M.Change("job_removal", "remove", job)
        allj = [{"op": "remove", "select": {"entity": t, "kind": sub}} for t in tasks]
        check(f"binding {tag}: removing all the job's tasks accepted", M.check_otf(ivj, bind(r, allj), IS, ISC)[0],
              M.check_otf(ivj, bind(r, allj), IS, ISC)[1])
        if len(tasks) > 1:
            check(f"binding {tag}: removing only part of the job rejected", not M.check_otf(ivj, bind(r, allj[:1]), IS, ISC)[0])
        ivf = M.Change("failure_removal", "remove", "M02")
        check(f"binding {tag}: removing the failure record accepted",
              M.check_otf(ivf, bind(r, [{"op": "remove", "select": {"entity": "M02", "kind": fail}}]), IS, ISC)[0])
        mach = next(k for k in kinds if k not in (sub, fail))
        check(f"binding {tag}: removing the machine instead of its failure rejected",
              not M.check_otf(ivf, bind(r, [{"op": "remove", "select": {"entity": "M02", "kind": mach}}]), IS, ISC)[0])
        ivm = M.Change("machine_removal", "remove", "M02")
        check(f"binding {tag}: machine removal must remove its failure too",
              M.check_otf(ivm, bind(r, [{"op": "remove", "select": {"entity": "M02"}}]), IS, ISC)[0]
              and not M.check_otf(ivm, bind(r, [{"op": "remove", "select": {"entity": "M02", "kind": mach}}]), IS, ISC)[0])
        check(f"binding {tag}: patch errors rejected",
              not M.check_otf(ivp, bind(r, [{"op": "set", "select": {"entity": "T999"}, "field": "priority", "value": 1}]), IS, ISC)[0])


# ---------------------------------------------------------------- policy on fake stdin programs
class Replayer:
    """Prints the recorded outcomes whatever the input: replays history exactly, ignores every change."""

    def __init__(self, schema, scope):
        self.out = M.printed(schema, scope)
        self.domain = schema.domain

    def __call__(self, data, horizon, timeout):
        if self.domain == M.MFG:
            rows = {}
            for (c, p, d), v in self.out.items():
                rows.setdefault((d, p), {"event": "ledger", "day": d, "product": p})[c] = v
            lines = [json.dumps(x) for x in rows.values()]
        else:
            lines = [json.dumps({"time": t, "event": e, "task": k, "machine": m}) for t, e, k, m in self.out]
        return 0, "\n".join(lines), ""


def policy_tests():
    for s, nv, sc, iv, q in ((MS, MNAV, MSC, M.Change("production_quantity", "set", "ATN02K12P", 5, 0.0),
                              M.DQuery("stock_end_of_day", "ATN02K12P", 9)),
                             (IS, INAV, ISC, M.Change("task_priority", "set", "T020", value=11.0), M.DQuery("task_start_time", "T020"))):
        b = M.DEVSDomain("fake", s, runner=Replayer(s, sc))
        b._hash = "replayer"
        rq = req(sc, iv, q)
        for config, want in (("native", True), ("schema", True), ("replay", True), ("directed", False), ("generic", False), ("program_wide", False)):
            with tempfile.TemporaryDirectory() as t:
                d = M.decide(config, rq, s, M.ProbeRunner(b, nv, s), Registry(Path(t) / "r.jsonl"), b)
            check(f"policy {s.domain}: an input-ignoring replayer is {'Trusted' if want else 'Caught'} by {config}", d.permit == want, d.reason)
        with tempfile.TemporaryDirectory() as t:
            reg = Registry(Path(t) / "r.jsonl")
            M.decide("directed", rq, s, M.ProbeRunner(b, nv, s), reg, b)
            d = M.decide("directed", rq, s, M.ProbeRunner(b, nv, s), reg, b)
        check(f"policy {s.domain}: a recorded failure blocks the same capability (Already caught)", not d.permit and "failed earlier" in d.reason, d.reason)
    crash = M.DEVSDomain("fake", MS, runner=lambda data, h, t: (1, "", "boom"))
    crash._hash = "crash"
    ok, why = M.ProbeRunner(crash, MNAV, MS).replay(MSC)
    check("policy: a crashing program fails the history check", not ok, why)
    bad_q = req(MSC, M.Change("production_quantity", "set", "ATN02K12P", 5, 0.0), M.DQuery("task_start_time", "T001"))
    with tempfile.TemporaryDirectory() as t:
        d = M.decide("directed", bad_q, MS, M.ProbeRunner(crash, MNAV, MS), Registry(Path(t) / "r.jsonl"), crash)
    check("policy: contract failure declines before any execution", not d.permit and d.reason.startswith("contract"), d.reason)
    data = M.inputs_from_schema(MS, MSC)
    check("stdin: manufacturing input lists ledger and order-book days", len(data["days"]) == 21 and len(data["flows"]) == 63)
    ev = M.parse_events(M.IT, [{"time": 5, "event": "start", "task": "T001", "machine": "M01"}, {"time": 3, "event": "submit", "task": "T001"}, "x"])
    check("parse_events: submit rows and junk ignored", ev == [(5, "start", "T001", "M01")])


# ---------------------------------------------------------------- review 1 regressions
class Silent(Replayer):
    """Replays history on the factual input and prints nothing for any changed input."""

    def __init__(self, schema, scope):
        super().__init__(schema, scope)
        self.first = None

    def __call__(self, data, horizon, timeout):
        if self.first is None:
            self.first = data
        return super().__call__(data, horizon, timeout) if data == self.first else (0, "", "")


def review1_tests():
    for s, nv, sc, iv, q in ((IS, INAV, ISC, M.Change("machine_removal", "remove", "M03"), M.DQuery("task_start_time", "T020")),
                             (MS, MNAV, MSC, M.Change("order_removal", "remove", "ATN02K12P", 1), M.DQuery("stock_end_of_day", "ATN02K12P", 9))):
        b = M.DEVSDomain("fake", s, runner=Silent(s, sc))
        b._hash = "silent"
        with tempfile.TemporaryDirectory() as t:
            d = M.decide("directed", req(sc, iv, q), s, M.ProbeRunner(b, nv, s), Registry(Path(t) / "r.jsonl"), b)
        check(f"review1 {s.domain}: empty output for a changed input is Caught", not d.permit and not d.untested, d.reason)
    # rule alone never permits: a window whose failing machine has no fail event offers no witness
    for title, ch in IS.chapters.items():
        if any(a["down"] is not None for a in ch["machines"].values()) and not any(e[1] == "fail" for e in ch["log"]):
            m = next(k for k, a in ch["machines"].items() if a["down"] is not None)
            b = M.DEVSDomain("fake", IS, runner=Replayer(IS, title))
            b._hash = "replayer"
            with tempfile.TemporaryDirectory() as t:
                d = M.decide("directed", req(title, M.Change("failure_removal", "remove", m), M.DQuery("task_start_time", sorted(ch["tasks"])[-1])),
                             IS, M.ProbeRunner(b, INAV, IS), Registry(Path(t) / "r.jsonl"), b)
            check("review1: with no witness, directed does not permit (no input-use probe ran)",
                  not d.permit and not any(n.startswith("input_use") and ok for n, ok, _ in d.evidence), d.reason)
            break
    r = otf_inputs("claude-sonnet-5-5/mfg_dev/b1", MSC)
    cap_key = next(k for k, v in r["params"].items() if M._num(v) == MS.chapters[MSC]["capacity_kg"])
    ivc = M.Change("dispatch_capacity", "scale", day=1, value=0.8)
    check("review1: a day-1 capacity request bound to a later restart is rejected",
          not M.check_otf(ivc, bind(r, [{"op": "scale", "param": cap_key, "factor": 0.8, "from": 8}]), MS, MSC)[0])
    shared_old = {"id": "x", "time": 5.0, "kind": "orders", "entities": ["ATN02K12P", "MAR02K12P"], "fields": {"MAR02K12P ordered": 47.0}}
    shared_new = {**shared_old, "fields": {"MAR02K12P ordered": 0.0}}
    d = {"modified": [[shared_old, shared_new]], "added": [], "removed": [], "params_changed": {}, "overrides": [], "errors": []}
    check("review1: a change inside a record shared by two products is rejected",
          not M.check_otf(M.Change("order_removal", "remove", "ATN02K12P", 5), d, MS, MSC)[0])
    fps = {M.schema_from_map(nav(d)).policy_fingerprint() for d in ("mfg_dev", "mfg_d01", "mfg_d03")}
    fpi = {M.schema_from_map(nav(d)).policy_fingerprint() for d in ("itops_dev", "itops_d02")}
    check("review1: one policy fingerprint per domain across documents", len(fps) == 1 and len(fpi) == 1, f"{fps} {fpi}")
    for text in ('{"scope": "x", "query": "stock", "interventions": 3}', '{"scope": "x", "interventions": [{"family": "task_priority", "value": "inf"}]}',
                 '{"scope": "x", "interventions": [{"family": "production_timing", "day": 3.7, "value": 1}]}', '{"scope": 1, "unresolved": 5}'):
        try:
            r2 = M.parse(text, M.MFG)
            c = M.validate(r2, MS)
            check(f"review1: odd reply handled without a crash ({text[:40]})", not c.ok)
        except Exception as e:
            check(f"review1: odd reply handled without a crash ({text[:40]})", False, repr(e))
    nan = M.DRequest(MSC, [M.Change("dispatch_capacity", "scale", day=1, value=float("nan"))], M.DQuery("stock_end_of_day", "ATN02K12P", 9))
    check("review1: a NaN factor fails the contract", M.validate(nan, MS).status == "invalid_units")
    bad = M.it_invariants(IS, ISC, M.inputs_from_schema(IS, ISC), [(5, "start", "T001", None)], None)
    check("review1: a start on no machine is flagged, not a crash", any("no machine" in x for x in bad))
    check("review1: scaled capacity is whole grams", M.scaled_kg(34500, 0.8) == 27600.0)


def native_tests():
    """OTF's own native path with a fake patch model: the binding check accepts the correct patch, and the native
    answer equals the program's diagnostic-path answer for the same change. No model is called."""
    for build, s, nv, sc, iv, q, patch in (
            ("claude-sonnet-5-5/mfg_dev/b1", MS, MNAV, MSC, M.Change("production_quantity", "set", "ATN02K12P", 5, 0.0),
             M.DQuery("stock_end_of_day", "ATN02K12P", 9),
             {"op": "set", "select": {"entity": "ATN02K12P", "kind": "daily_production_order", "time": 5}, "field": "produced", "value": 0}),
            ("claude-sonnet-5-5/itops_dev/b1", IS, INAV, ISC, M.Change("task_priority", "set", "T020", value=11.0),
             M.DQuery("task_start_time", "T020"),
             {"op": "set", "select": {"entity": "T020", "kind": "task_submit"}, "field": "priority", "value": 11})):
        be = M.OTFDomain(ROOT / "runs" / "build_test_r1_claude" / build / "program.json", "r1", ROOT, nav=nv)
        fake = lambda messages, _p=patch: json.dumps({"patches": [_p]})
        ex, binding = be.native_what_if(sc, "question text (unused by the fake)", fake)
        ok, why = M.check_otf(iv, binding, s, sc)
        check(f"native {s.domain}: correct patch passes the binding check", ex.status == "ran" and ok, f"{ex.status} {ex.detail} {why}")
        a_native = M.answer(q, ex.case_ends.get("canon"))[0] if ex.status == "ran" else None
        a_diag = M.answer(q, be.execute(sc, iv).case_ends["canon"])[0]
        check(f"native {s.domain}: native answer equals the diagnostic answer", a_native == a_diag, f"{a_native} vs {a_diag}")


class ConfusedOTF(M.OTFDomain):
    """A real OTF R1 program with one defect added outside its code: a changed CPU request in the task log is
    read as a memory request (the CPU is restored, the value goes to memory). Factual runs are unchanged."""

    def run_map(self, nav, scope, params_edit=None):
        nav = json.loads(json.dumps(nav))
        orig = M._node(self.nav, f"{scope}: Task log")
        log = M._node(nav, f"{scope}: Task log")
        cols = log["table"]["columns"]
        c, m = cols.index("CPU"), cols.index("memory")
        before = {(r[cols.index("task")], r[cols.index("event")]): r for r in orig["table"]["rows"]}
        for r in log["table"]["rows"]:
            old = before.get((r[cols.index("task")], r[cols.index("event")]))
            if old is not None and r[c] != old[c]:
                r[m], r[c] = r[c], old[c]
        return super().run_map(nav, scope, params_edit)


def blindspot_tests():
    """The IT CPU/memory blind spot (manifests/it_blindspot.md): router, the added split step, registry reuse."""
    blind_sc, plain_sc = "Cell window 27", ISC
    rng = __import__("random").Random(0)
    for sc, want in ((blind_sc, True), (plain_sc, False)):
        for res in ("cpu", "mem"):
            av = M.Change("task_request", "set", "T001", value=1.0, resource=res)
            ws = M.ProbeRunner(None, INAV, IS).witnesses(sc, "task_request", 1, rng, avoid=av)
            check(f"blindspot: router says {'blind' if want else 'not blind'} in {sc} ({res})", M._blind(IS, sc, av, ws) == want)
    for res in ("cpu", "mem"):
        removed, ws = M._split_cluster(IS, blind_sc, res)
        check(f"blindspot: the split removes both 12500/12500 machines and finds a witness ({res})",
              removed == ["M04", "M05"] and ws and all(M.discriminates(
                  M.DomainSchema(IS.domain, IS.policy_text, IS.scopes, {blind_sc: {**IS.chapters[blind_sc], "machines": {
                      k: a for k, a in IS.chapters[blind_sc]["machines"].items() if k not in removed}}}), blind_sc, w) for w in ws),
              f"{removed} {len(ws)}")
    check("blindspot: no split where today's witnesses already exist", M._split_cluster(IS, plain_sc, "cpu") == ([], []))

    def synth(machines):
        ch_ = IS.chapters[blind_sc]
        return M.DomainSchema(IS.domain, IS.policy_text, [blind_sc], {blind_sc: {**ch_, "machines": machines}})
    mk_m = lambda c, m: {"cpu": c, "mem": m, "down": None, "back": None}
    same = synth({f"M0{i}": mk_m(6250, 6250) for i in range(1, 5)})
    check("blindspot: identical machines give no split and no loop", M._split_cluster(same, blind_sc, "cpu") == ([], []))
    nodom = synth({"M01": mk_m(12500, 100), "M02": mk_m(100, 12500), "M03": mk_m(100, 100)})
    got = M._split_cluster(nodom, blind_sc, "cpu")
    check("blindspot: with no dominating machine nothing is removed", got[0] == [], str(got[0]))
    check("blindspot: an unknown backend cannot run several changes",
          M._run_changes(M.ProbeRunner(object(), INAV, IS), blind_sc, [M.Change("machine_removal", "remove", "M04")]) is None)
    cpu, mem = (M.Change("task_request", "set", "T001", value=1.0, resource=r) for r in ("cpu", "mem"))
    check("blindspot: reuse router is blind in a blind window for both resources",
          M._scope_blind(IS, blind_sc, cpu) and M._scope_blind(IS, blind_sc, mem))
    check("blindspot: reuse router unchanged outside a blind window", not M._scope_blind(IS, plain_sc, mem))
    check("blindspot: other families never blind", not M._scope_blind(IS, blind_sc, M.Change("task_priority", "set", "T001", value=3.0)))
    k = M.Key("b", "h", "a", "p", "task_request", "set")
    check("blindspot: split evidence has its own key per resource",
          M._split_key(k, cpu) != M._split_key(k, mem) and M._split_key(k, cpu) != k and k.op == "set")

    class Recorder:
        def __init__(self):
            self.seen = []

        def __call__(self, data, horizon, timeout):
            self.seen.append(data)
            return 0, "", ""
    rec = Recorder()
    dv = M.DEVSDomain("fake", IS, runner=rec)
    x0 = sorted(IS.chapters[blind_sc]["tasks"])[0]
    ex = M._run_changes(M.ProbeRunner(dv, INAV, IS), blind_sc, [M.Change("machine_removal", "remove", "M04"),
                                                               M.Change("task_request", "set", x0, value=77.0, resource="mem")])
    got = rec.seen[-1] if rec.seen else {"machines": [], "tasks": []}
    check("blindspot: the DEVS path writes every change into one input",
          ex is not None and ex.status == "ran" and len(got["machines"]) == 7
          and "M04" not in [m["machine"] for m in got["machines"]]
          and any(t["task"] == x0 and t["memory"] == 77 for t in got["tasks"]))
    prog = ROOT / "runs" / "build_test_r1_claude" / "claude-sonnet-5-5" / "itops_dev" / "b1" / "program.json"
    ch = IS.chapters[blind_sc]
    t = sorted({e[2] for e in ch["log"] if e[1] == "start"})[3]
    started = sorted({e[2] for e in ch["log"] if e[1] == "start"})
    for cls, want in ((M.OTFDomain, True), (ConfusedOTF, False)):
        be = cls(prog, "r1", ROOT, nav=INAV)
        for res in ("cpu", "mem"):
            removed, ws = M._split_cluster(IS, blind_sc, res)
            got = [M._without(M.ProbeRunner(be, INAV, IS), blind_sc, removed, w)[0] for w in ws[:2]]
            exp = want if res == "cpu" else True                # the defect only touches CPU changes
            check(f"blindspot: split witness on {cls.__name__} ({res}) is {'passed' if exp else 'failed'}", got == [exp] * len(got), str(got))
            # a decision that today's method would permit: the added step decides it
            hit = None
            for x in started[:12]:
                rq = req(blind_sc, M.Change("task_request", "set", x, value=float(max(1, ch["tasks"][x][res] // 2)), resource=res),
                         M.DQuery("task_start_time", x))
                with tempfile.TemporaryDirectory() as tmp:
                    d = M.decide("directed", rq, IS, M.ProbeRunner(be, INAV, IS), Registry(Path(tmp) / "r.jsonl"), be)
                names = [n for n, _, _ in d.evidence]
                if any(n.startswith("precheck") for n in names):
                    hit = (d, names)
                    break
            check(f"blindspot: {cls.__name__} reaches the split step on some blind {res} row", hit is not None)
            if hit:
                d, names = hit
                check(f"blindspot: {cls.__name__} blind {res} row is {'Trusted' if exp else 'Caught'} by the split step",
                      d.permit == exp and not d.untested
                      and [e[1] for e in d.evidence if e[0].endswith("without M04, M05)")] == [exp], d.reason)
                check(f"blindspot: {cls.__name__} {res} keeps today's witness and rule first",
                      names[:4] == ["replay", "input_use task_request" + M.BLIND, "rule task_request", "precheck without M04, M05"], str(names))
        # outside the blind spot nothing is added
        rq = req(plain_sc, M.Change("task_request", "set", "T020", value=50.0, resource="cpu"), M.DQuery("task_start_time", "T020"))
        with tempfile.TemporaryDirectory() as tmp:
            d = M.decide("directed", rq, IS, M.ProbeRunner(be, INAV, IS), Registry(Path(tmp) / "r.jsonl"), be)
        check(f"blindspot: {cls.__name__} outside the blind spot gets no split step", not any("without" in n for n, _, _ in d.evidence), d.reason)
    # a shared registry: a failure the split finds blocks later blind-spot rows of that resource only
    conf = ConfusedOTF(prog, "r1", ROOT, nav=INAV)
    plain = req(plain_sc, M.Change("task_request", "set", "T020", value=50.0, resource="mem"), M.DQuery("task_start_time", "T020"))

    def half_cpu(x):
        return req(blind_sc, M.Change("task_request", "set", x, value=float(max(1, ch["tasks"][x]["cpu"] // 2)), resource="cpu"),
                   M.DQuery("task_start_time", x))
    with tempfile.TemporaryDirectory() as tmp:
        fresh = M.decide("directed", plain, IS, M.ProbeRunner(conf, INAV, IS), Registry(Path(tmp) / "f.jsonl"), conf)
        reg = Registry(Path(tmp) / "r.jsonl")
        first, used = None, None
        for x in started[:12]:
            d = M.decide("directed", half_cpu(x), IS, M.ProbeRunner(conf, INAV, IS), reg, conf)
            if any(n.startswith("precheck") for n, _, _ in d.evidence):
                first, used = d, x
                break
        after = M.decide("directed", plain, IS, M.ProbeRunner(conf, INAV, IS), reg, conf)
        other = next(x for x in started if x != used)
        again = M.decide("directed", half_cpu(other), IS, M.ProbeRunner(conf, INAV, IS), reg, conf)
    check("blindspot: shared registry, the split catches the confused program",
          first is not None and not first.permit and not first.untested, first and first.reason)
    check("blindspot: shared registry, a later non-blind row is decided as with a fresh registry",
          (after.permit, after.reason, after.untested) == (fresh.permit, fresh.reason, fresh.untested), f"{after.reason} vs {fresh.reason}")
    check("blindspot: shared registry, a later blind cpu row is Already caught (or Caught by today's probes)",
          not again.permit and not again.untested, again.reason)
    # precheck failure: Untestable, and nothing written for the split
    w30 = "Cell window 30"
    ch30 = IS.chapters[w30]
    be = M.OTFDomain(prog, "r1", ROOT, nav=INAV)
    with tempfile.TemporaryDirectory() as tmp:
        reg = Registry(Path(tmp) / "r.jsonl")
        hit = None
        for x in sorted({e[2] for e in ch30["log"] if e[1] == "start"})[:12]:
            rq = req(w30, M.Change("task_request", "set", x, value=float(max(1, ch30["tasks"][x]["cpu"] // 2)), resource="cpu"),
                     M.DQuery("task_start_time", x))
            d = M.decide("directed", rq, IS, M.ProbeRunner(be, INAV, IS), reg, be)
            if any(n.startswith("precheck") for n, _, _ in d.evidence):
                hit = (d, rq)
                break
        key = M.Key(be.name, be.program_hash(), be.adapter_version, IS.policy_fingerprint(), "task_request", "set")
        split_rows = reg.history(M._split_key(key, hit[1].interventions[0])) if hit else None
    check("blindspot: a precheck the program fails gives Untestable (window 30, OTF)",
          hit is not None and hit[0].untested and not hit[0].permit and "not usable" in hit[0].reason, hit and hit[0].reason)
    check("blindspot: a failed precheck writes no split row", split_rows == [], str(split_rows))
    with tempfile.TemporaryDirectory() as tmp:
        reg = Registry(Path(tmp) / "r.jsonl")
        mk = lambda res, x: req(blind_sc, M.Change("task_request", "set", x, value=float(max(1, ch["tasks"][x][res] * 2)), resource=res),
                                M.DQuery("task_start_time", x))
        d1 = M.decide("directed", mk("cpu", t), IS, M.ProbeRunner(be, INAV, IS), reg, be)
        d2 = M.decide("directed", mk("cpu", t), IS, M.ProbeRunner(be, INAV, IS), reg, be)
        d3 = M.decide("directed", mk("mem", t), IS, M.ProbeRunner(be, INAV, IS), reg, be)
    check("blindspot: a resolved cpu row is reused for cpu (after today's probes)", d1.permit and d2.permit
          and "reused evidence" in d2.reason and not any(n.startswith("precheck") for n, _, _ in d2.evidence), d2.reason)
    check("blindspot: a resolved cpu row is not reused for mem", d3.permit and "reused" not in d3.reason
          and any(n.startswith("precheck") for n, _, _ in d3.evidence), d3.reason)


def phase2_tests():
    """manifests/blindspots.md: the dispatch completeness check and the IT fill witness."""
    for sc in MS.scopes:
        data = M.inputs_from_schema(MS, sc)
        canon = M.printed(MS, sc)
        check(f"phase2: the printed ledger passes dispatch completeness ({sc})", M.mfg_dispatch_full(MS, sc, data, canon) == [])
    sc = MS.scopes[0]
    data, canon = M.inputs_from_schema(MS, sc), dict(M.printed(MS, sc))
    hit = next(((p, d) for (c, p, d), v in canon.items() if c == "shipped" and v > 0), None)
    if hit:
        p, d = hit
        canon[("shipped", p, d)] -= 1                 # one unit fewer shipped, stock and backorder one higher
        canon[("stock", p, d)] += 1
        canon[("backordered", p, d)] += 1
        check("phase2: an order left short with stock and capacity unused is flagged",
              bool(M.mfg_dispatch_full(MS, sc, data, canon)))
    iv = M.Change("task_request", "set", "T001", value=10.0, resource="cpu")
    ws = M._fill_witnesses(IS, "Cell window 27", iv)
    check("phase2: fill witnesses use the largest machine's capacity", ws and all(w.value == 12500.0 and w.target != "T001" for w in ws))
    ws8 = M._fill_witnesses(IS, ISC, M.Change("task_request", "set", "T001", value=10.0, resource="mem"))
    top = max(a["mem"] for a in IS.chapters[ISC]["machines"].values())
    check("phase2: fill value is the largest memory in the window", ws8 and {w.value for w in ws8} == {float(top)})


if __name__ == "__main__":
    phase2_tests()
    for f in (schema_tests, contract_tests, parse_tests, edit_tests, binding_tests, policy_tests, review1_tests, native_tests,
              blindspot_tests):
        f()
    print(f"\n{len(FAILS)} failures")
    sys.exit(len(FAILS))
