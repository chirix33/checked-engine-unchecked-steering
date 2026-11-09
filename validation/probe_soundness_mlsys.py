"""Probe soundness for the manufacturing and IT families (evaluation-only; it runs the reference as a program).

The pinned reference simulator (sim.py) is wrapped as a program that reads the generic stdin format and writes the
generic output format, so it goes through exactly the library path a DEVS-Gen or coding-agent program goes through
(`assurance.mlsys.DEVSDomain` with a local runner instead of WSL).

1. **Reference passes.** On every dev chapter and window: the history check, every input-use witness of every
   family (up to 6 per family), the rule probe and the no-op on every dev question's own change, and the directed
   decision on every dev question. Required: 0 rejections. A probe that rejects the reference is a blocker.
2. **Broken programs are Caught.** Variants of the reference with one deliberate defect each:
   - ignores the input: manufacturing ignores changed production (uses the first production it was given);
     IT ignores changed priorities;
   - changes the wrong field: manufacturing applies production to orders when they differ from the first input;
     IT reads a changed CPU request as a memory request;
   - moves records before the change point: any changed input shifts every output one day (manufacturing: stock
     on the first day +1) or one second (IT: every event time +1);
   - ignores capacity (manufacturing) or ignores a removed machine (IT).
   Reported: per defect, on dev questions of the families it touches, how directed decides (Caught, Untestable,
   Trusted), split by whether the defective program's answer is right. "0 rejections" in part 1 means no probe
   Caught the reference; Untestable declines (no witness exists) are counted and reported, not hidden.

Usage: python -X utf8 validation/probe_soundness_mlsys.py [out_json]
"""
from __future__ import annotations

import copy
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "redesign")]
import mlsys_gold as G  # noqa: E402
from assurance import mlsys as M  # noqa: E402
from assurance.registry import Registry  # noqa: E402
from domains.manufacturing import sim as msim  # noqa: E402
from domains.it_ops import sim as isim  # noqa: E402


# ---------------------------------------------------------------- the reference as a stdin program
def mfg_program(data, horizon):
    prods = [p["product"] for p in data["products"]]
    days = [d["day"] for d in data["days"]]
    cap = {d["day"]: d["capacity_kg"] for d in data["days"]}
    base = cap[days[0]]
    flows = {(f["day"], f["product"]): f for f in data["flows"]}
    s = msim.Scope("X", 1, days[0], horizon, days[-1], prods,
                   {p["product"]: round(p["kg_per_unit"] * 1000) for p in data["products"]},
                   {p["product"]: p["opening_stock"] for p in data["products"]}, base,
                   {d: {p: flows[(d, p)]["produced"] for p in prods} for d in days},
                   {d: {p: flows[(d, p)]["ordered"] for p in prods} for d in days})
    ivs, prev = [], base
    for d in days:
        if cap[d] != prev:
            ivs.append({"kind": "scale_capacity", "factor": cap[d] / prev, "from_day": d})
            prev = cap[d]
    res = msim.simulate(s, ivs, through=horizon)
    return [{"event": "ledger", "day": d, "product": p, **{c: res.rows[(d, p)][c] for c in M.LEDGER_COLS}}
            for d in days if d <= horizon for p in prods]


def it_program(data, horizon):
    w = isim.Window(1, data["window_end"],
                    [isim.Machine(m["machine"], m["cpu"], m["memory"], m["fails_at"], m["returns_at"]) for m in data["machines"]],
                    [isim.Task(t["task"], t["job"], t["priority"], t["cpu"], t["memory"], t["submit"], t["run_time"])
                     for t in data["tasks"]])
    res = isim.simulate(w)
    return [{"time": t, "event": ev, "task": tid, "machine": m} for t, tid, ev, m in res.log if t <= horizon]


class Program:
    """A local runner for DEVSDomain: the reference, optionally with one defect."""

    def __init__(self, domain, defect=None):
        self.domain, self.defect, self.first = domain, defect, None

    def __call__(self, data, horizon, timeout):
        data = copy.deepcopy(data)
        if self.first is None:
            self.first = copy.deepcopy(data)
        changed = data != self.first
        d = self.defect
        if self.domain == M.MFG:
            f0 = {(x["day"], x["product"]): x for x in self.first["flows"]}
            for x in data["flows"]:
                old = f0.get((x["day"], x["product"]))
                if d == "ignores_input" and old:
                    x["produced"] = old["produced"]
                if d == "wrong_field" and old and x["produced"] != old["produced"]:
                    x["ordered"], x["produced"] = x["ordered"] + x["produced"] - old["produced"], old["produced"]
            if d == "ignores_capacity":
                for x in data["days"]:
                    x["capacity_kg"] = self.first["days"][0]["capacity_kg"]
            out = mfg_program(data, horizon)
            if d == "moves_prefix" and changed:
                out[0]["stock"] += 1
        else:
            t0 = {t["task"]: t for t in self.first["tasks"]}
            for t in data["tasks"]:
                old = t0.get(t["task"])
                if d == "ignores_input" and old:
                    t["priority"] = old["priority"]
                if d == "wrong_field" and old and t["cpu"] != old["cpu"]:
                    t["memory"], t["cpu"] = min(t["cpu"], max(m["memory"] for m in data["machines"]) + 1), old["cpu"]
            if d == "ignores_removed_machine":
                data["machines"] = copy.deepcopy(self.first["machines"])
            out = it_program(data, horizon)
            if d == "moves_prefix" and changed:
                for e in out:
                    e["time"] += 1
        return 0, "\n".join(json.dumps(e) for e in out), ""


DEFECTS = {M.MFG: {"ignores_input": ["production_quantity", "production_timing"],
                   "wrong_field": ["production_quantity", "production_timing"],
                   "moves_prefix": ["order_removal", "production_quantity", "production_timing", "dispatch_capacity"],
                   "ignores_capacity": ["dispatch_capacity"]},
           M.IT: {"ignores_input": ["task_priority"], "wrong_field": ["task_request"],
                  "moves_prefix": ["job_removal", "failure_removal", "task_priority", "task_request"],
                  "ignores_removed_machine": ["machine_removal"]}}


def navs():
    out = {}
    for dom in G.DOCS.values():
        for d in dom:
            p = G.DOCS_DIR / d / "navmap.json"
            if not p.exists():
                from otf_r1 import navmap
                p.write_text(json.dumps(navmap.build_map(G.pdf(d))))
            out[d] = json.loads(p.read_text())
    return out


def main(out=None):
    import tempfile
    NAV = navs()
    splits = json.loads((ROOT / "manifests" / "mlsys_splits_v1.json").read_text(encoding="utf-8"))
    qs = json.loads((ROOT / "manifests" / "mlsys_questions_dev_v1.json").read_text(encoding="utf-8"))
    report = {"reference": {}, "broken": {}}
    rng = random.Random(7)
    rejections = []
    # 1. reference passes: every dev chapter, every family's witnesses
    for dom in (M.MFG, M.IT):
        counts = Counter()
        for title, v in splits[dom].items():
            if v["split"] != "dev":
                continue
            schema = M.schema_from_map(NAV[v["doc"]])
            backend = M.DEVSDomain("ref", schema, runner=Program(dom))
            backend._hash = "reference"
            runner = M.ProbeRunner(backend, NAV[v["doc"]], schema)
            ok, why = runner.replay(title)
            counts["replay " + ("pass" if ok else "fail")] += 1
            if not ok:
                rejections.append((title, "replay", why))
            for fam, (d, _) in M.FAMILIES.items():
                if d != dom:
                    continue
                for w in runner.witnesses(title, fam, 6, rng):
                    ok, why = runner.input_use(title, w)
                    counts[f"{fam} input_use {ok}"] += 1
                    if ok is False:
                        rejections.append((title, fam, why))
        report["reference"][dom] = dict(counts)
    # rule, no-op and directed on every dev question
    dec = Counter()
    for q in qs:
        dom = q["domain"]
        schema = M.schema_from_map(NAV[q["doc"]])
        backend = M.DEVSDomain("ref", schema, runner=Program(dom))
        backend._hash = "reference"
        runner = M.ProbeRunner(backend, NAV[q["doc"]], schema)
        req = M.request_from_binding(q["scope"], q["binding"], q["query"])
        iv = req.interventions[0]
        for name, res in (("rule", runner.rule(q["scope"], iv)), ("no_op", runner.no_op(q["scope"], iv))):
            dec[f"{dom} {name} {res[0]}"] += 1
            if res[0] is False:
                rejections.append((q["id"], name, res[1]))
        with tempfile.TemporaryDirectory() as tmp:
            d = M.decide("directed", req, schema, runner, Registry(Path(tmp) / "r.jsonl"), backend)
        label = "Trusted" if d.permit else "Untestable" if d.untested else "Can't express" if d.inexpressible else "Caught"
        dec[f"{dom} directed {label}"] += 1
        if label == "Caught":
            rejections.append((q["id"], "directed", d.reason))
        # the reference's answer through the projection equals gold
        a, _ = M.answer(req.query, runner.canon(runner.execute(q["scope"], iv)))
        dec[f"{dom} answer {'== gold' if a == q['gold'] else '!= gold'}"] += 1
        if a != q["gold"]:
            rejections.append((q["id"], "answer", f"{a} vs gold {q['gold']}"))
    report["reference"]["questions"] = dict(dec)
    report["reference"]["rejections"] = rejections
    # 2. broken programs
    for dom, defects in DEFECTS.items():
        for defect, fams in defects.items():
            caught = Counter()
            for q in qs:
                if q["domain"] != dom or q["family"] not in fams:
                    continue
                schema = M.schema_from_map(NAV[q["doc"]])
                prog = Program(dom, defect)
                backend = M.DEVSDomain("broken", schema, runner=prog)
                backend._hash = f"broken-{defect}"
                runner = M.ProbeRunner(backend, NAV[q["doc"]], schema)
                req = M.request_from_binding(q["scope"], q["binding"], q["query"])
                with tempfile.TemporaryDirectory() as tmp:
                    d = M.decide("directed", req, schema, runner, Registry(Path(tmp) / "r.jsonl"), backend)
                a, _ = M.answer(req.query, runner.canon(runner.execute(q["scope"], req.interventions[0])))
                wrong = a != q["gold"]
                label = "Trusted" if d.permit else "Untestable" if d.untested else "Can't express" if d.inexpressible else "Caught"
                caught[("wrong " if wrong else "right ") + label] += 1
            report["broken"][f"{dom}/{defect}"] = dict(caught)
    print(json.dumps(report["reference"]["questions"], indent=0))
    for dom in (M.MFG, M.IT):
        print(dom, report["reference"][dom])
    print("REFERENCE REJECTIONS:", len(rejections), rejections[:8])
    for k, v in report["broken"].items():
        print("broken", k, v)
    if out:
        Path(out).write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return 1 if rejections else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
