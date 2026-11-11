"""Probe soundness on the workflow test documents (evaluation-only; it runs the reference as a program).

A sound probe never rejects a correct program. The reference engine is the correct program here. Nothing in the
library is changed; its probes and decision code run as they are.

Part 1 reruns the four existing workflow soundness checks on the test documents and test runs, using those scripts'
own reference wrappers and helpers (their files are unchanged; only the document list and maps differ):
  route_rule      every test run and decision, changes from `probe_soundness_route_rule.changes`;
  route_records   form (b), both record shapes, the same changes plus every test routing_probability question;
  route_flips     every routing witness flip: runs, needs no unlisted visit, changes the flipped case;
  added_workers   every test run and pool, +1 and +2 workers.

Part 2 runs the full decision. The reference is wrapped as a program that reads the generic stdin input built from
the test document (`DEVSBackend.stdin_from_map`, with changes written by `DEVSBackend.apply`), exactly the input a
DEVS-Gen or coding-agent program gets. It turns that input into reference interventions (changed work or waits
become per-visit sets, every route draw is the printed one, removed cases are removed, route probabilities, added
and unavailable workers as stated) and prints the generic output records. Two record shapes:
  events        the generic output format, with decision events (routing_probability uses the rule probe);
  no_decisions  the same without decision events (routing_probability uses form (b), as for OTF records).
The wrapper fails a run (and the check) if the input has a key it does not read, adds a case or changes an arrival,
or if the engine used any work, wait or route value that the input does not give (review 2026-11-09), so it never
passes on seed values a document-only program would not have.
For each shape, on every test question, with the question's hidden binding as the request (`pilot_runner.
oracle_request`, interpretation removed), a fresh registry per document and shape, budget 3, seed 0:
  history check on every run; `directed` (required: 0 Caught, 0 Already caught, 0 Failed history check); `generic`
  and `program_wide` (reported); and the program's answer to the question, which must equal gold whenever the
  change can be written into the generic input (`pilot_runner` records the others as "inexpressible"; they are
  listed, not counted as wrong).
Part 1's route_flips also counts flips that change only decision records (e.g. a route that loops back through a
zero-time decision to the same next step): for records that name no decisions, such a witness would fail a correct
program. Both it and "needing unlisted visits" are limits of the library's witness choice, reported and not counted
as rejections in part 1; if part 2 draws one, the resulting Caught is a rejection and is counted. Deep witnesses: the reference has every draw, but a document-only program would lack inputs for such a witness, so
part 2 also lists any decision whose evidence used one.

Documents are those of the question file: dev, test or policy-variant documents (each with its own parameter file).

Usage: python -X utf8 validation/probe_soundness_workflow_test.py <questions.json> <work_dir> <out_json>
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "reference_engine"), str(ROOT / "validation")]
sys.dont_write_bytecode = True

import engine                                                    # noqa: E402
import render_workflow_doc as render                             # noqa: E402
import replay_screen as rs                                       # noqa: E402
import workflow_policy_set as wp                                 # noqa: E402
import workflow_test_set as wt                                   # noqa: E402
from assurance import probes                                     # noqa: E402
from assurance.answer import answer                              # noqa: E402
from assurance.backends import DEVSBackend, Execution            # noqa: E402
from assurance.policy import decide                              # noqa: E402
from assurance.registry import Registry                          # noqa: E402
from assurance.request import Intervention, schema_from_map      # noqa: E402
from pilot_attribution import cause                              # noqa: E402
from pilot_runner import BUDGET, oracle_request                  # noqa: E402
import probe_soundness_added_workers as paw                      # noqa: E402
import probe_soundness_route_flips as pfl                        # noqa: E402
import probe_soundness_route_records as prc                      # noqa: E402
import probe_soundness_route_rule as prr                         # noqa: E402

wt.register(rs)
wp.register(rs)
DOCS = []          # the documents of the question file, set in main
TERMS = {"trusted": "Trusted", "caught": "Caught", "already_caught": "Already caught", "untestable": "Untestable",
         "failed_history_check": "Failed history check", "cant_express": "Can't express", "contract": "contract",
         "other": "other"}


def setup(doc):
    nav = wp.load_nav(doc)
    schema = schema_from_map(nav)
    bpmn, params = rs.model_files(str(ROOT), doc)
    model = engine.Model(bpmn, params)
    labels = render.Labels(model, bpmn)
    inv = {v: k for k, v in labels.label.items()}
    return nav, schema, model, labels, inv


# ---------------------------------------------------------------- part 1: existing checks on test documents
def part1(qs):
    res = {}
    rule = {"cases": 0, "rejections": [], "not_run": 0, "reference_cannot_run": 0}
    recs = {"free": [0, 0, 0], "events": [0, 0, 0], "rejections": []}
    flips = {"witness_flips": 0, "unused": 0, "failed": [], "needing_unlisted_visits": [], "case_unchanged": [],
             "case_unchanged_without_decisions": []}
    workers = {"cases": 0, "rejections": [], "not_run": 0}
    for doc in DOCS:
        nav, schema, model, labels, inv = setup(doc)
        stated = probes.stated_probabilities(schema)
        # route_rule
        b = prr.Reference(doc, labels, inv)
        for scope in schema.scopes:
            for dec, pr in sorted(stated.items()):
                for ch in prr.changes(pr):
                    runner = probes.ProbeRunner(b, nav, schema)
                    try:
                        ok, why = runner.route_rule(scope, Intervention("routing_probability", "set", target=dec, routes=ch))
                    except prr.Skip:
                        rule["reference_cannot_run"] += 1
                        continue
                    rule["cases"] += 1
                    if ok is None:
                        rule["not_run"] += 1
                    elif not ok:
                        rule["rejections"].append([doc, scope, dec, ch, why])
        # route_records (form b), both shapes
        tried = [(scope, dec, ch, "generated") for scope in schema.scopes for dec, pr in sorted(stated.items()) for ch in prr.changes(pr)]
        tried += [(q["scope"], q["binding"]["target"], q["binding"]["routes"], q["id"])
                  for q in qs if q["doc"] == doc and q["family"] == "routing_probability"]
        for shape in ("free", "events"):
            b = prc.Reference(doc, labels, inv, shape)
            for scope, dec, ch, src in tried:
                runner = probes.ProbeRunner(b, nav, schema)
                try:
                    ok, why = runner.route_change(scope, Intervention("routing_probability", "set", target=dec, routes=ch))
                except prc.Skip:
                    recs[shape][2] += 1
                    continue
                if ok is None:
                    recs[shape][1] += 1
                    continue
                recs[shape][0] += 1
                if not ok:
                    recs["rejections"].append([shape, doc, scope, dec, ch, src, why])
        # route_flips (the loop of probe_soundness_route_flips.main, on this document)
        for sc in schema.scopes:
            depth = len(next(n for n in nav["nodes"] if n["title"] == f"{sc}: Work plan")["table"]["columns"]) - 2
            _, _, base = rs.reference(str(ROOT), doc, sc, {})
            for r in probes._table_rows(nav, sc, "Decision log"):
                w = Intervention("routing_outcome", "set_draw", case=r[0], target=r[1], visit=int(r[2]))
                p = probes.perturb(nav, schema, sc, w)
                if p is None:
                    flips["unused"] += 1
                    continue
                flips["witness_flips"] += 1
                _, _, out = rs.reference(str(ROOT), doc, sc, {"draw_overrides": [
                    {"case": p.case, "element": inv[p.target], "visit": p.visit, "variable": "branch", "u": f"{p.value:.6f}"}]})
                if out.get("status") != "ok":
                    flips["failed"].append([doc, sc, r[:3], out.get("error")])
                    continue
                mx = max([t["visit"] for t in out["tasks"]] + [t["visit"] for t in out["timers"]] + [x["visit"] for x in out["branches"]])
                if mx > depth:
                    flips["needing_unlisted_visits"].append([doc, sc, r[:3], mx, depth])
                if pfl.sig(out, p.case) == pfl.sig(base, p.case):
                    flips["case_unchanged"].append([doc, sc, r[:3]])
                # records that name no decisions (form (b), OTF): the flip must change a task, wait or case end
                no_dec = lambda o: sorted(x for x in pfl.sig(o, p.case) if x[0] != "d")
                if no_dec(out) == no_dec(base):
                    flips["case_unchanged_without_decisions"].append([doc, sc, r[:3]])
        # added_workers
        b = paw.Reference(doc)
        b.pool_ids = {k: k for k in model.pools}
        for scope in schema.scopes:
            for pool in schema.pools:
                for added in (1, 2):
                    runner = probes.ProbeRunner(b, nav, schema)
                    ok, why = runner.resource_rule(scope, Intervention("resource_availability", "add_workers", target=pool, value=added))
                    workers["cases"] += 1
                    if ok is None:
                        workers["not_run"] += 1
                    elif not ok:
                        workers["rejections"].append([doc, scope, pool, added, why])
    res["route_rule"] = rule
    res["route_records"] = {"free": dict(zip(("tested", "not_run", "reference_cannot_run"), recs["free"])),
                            "events": dict(zip(("tested", "not_run", "reference_cannot_run"), recs["events"])),
                            "rejections": recs["rejections"]}
    res["route_flips"] = flips
    res["added_workers"] = workers
    res["rejections"] = (len(rule["rejections"]) + len(recs["rejections"]) + len(flips["failed"])
                         + len(flips["case_unchanged"]) + len(workers["rejections"]))
    return res


# ---------------------------------------------------------------- part 2: the reference as a stdin program
def _dec(x):
    return format(Decimal(repr(float(x))), "f")


class Unfaithful(Exception):
    pass


class StdinReference(DEVSBackend):
    """The reference engine behind the generic stdin input (DEVSBackend's own stdin_from_map and apply)."""

    adapter_version = "devs-adapter-0.1"

    def __init__(self, doc, nav, model, labels, inv, shape):
        self.doc, self.nav, self.model, self.labels, self.inv, self.shape = doc, nav, model, labels, inv, shape
        self.factual, self.runs, self.unfaithful = {}, 0, []

    def program_hash(self):
        return f"reference-{self.shape}"

    def stdin_from_map(self, nav, scope):
        """The library's generic input, plus the run title so this wrapper knows which seed to use."""
        return {**DEVSBackend.stdin_from_map(nav, scope), "scope": scope}

    KNOWN = {"scope", "cases", "work", "waits", "draws", "route_probabilities", "workers", "unavailable"}

    def scenario(self, data):
        unknown = set(data) - self.KNOWN
        if unknown:
            raise Unfaithful(f"input keys this wrapper does not read: {sorted(unknown)}")
        scope = data["scope"]
        if scope not in self.factual:
            self.factual[scope] = DEVSBackend.stdin_from_map(self.nav, scope)
        f = self.factual[scope]
        was = {c["case"]: c["arrival"] for c in f["cases"]}
        if any(c["case"] not in was or was[c["case"]] != c["arrival"] for c in data["cases"]):
            raise Unfaithful("the input adds a case or changes an arrival, which the wrapper cannot pass on")
        ivs, over = [], []
        cases = {c["case"] for c in data["cases"]}
        for c in f["cases"]:
            if c["case"] not in cases:
                ivs.append({"type": "case_remove", "case": c["case"]})
        for key, name, kind, field in (("work", "activity", "duration_set", "task"), ("waits", "wait", "timer_set", "timer")):
            was = {(x["case"], x[name], x["visit"]): x["seconds"] for x in f[key]}
            for x in data[key]:
                if was.get((x["case"], x[name], x["visit"])) != x["seconds"]:
                    ivs.append({"type": kind, field: self.inv[x[name]], "seconds": int(x["seconds"]),
                                "selector": {"case": x["case"], "visit": x["visit"]}})
        for x in data["draws"]:
            over.append({"case": x["case"], "element": self.inv[x["decision"]], "visit": x["visit"], "variable": "branch", "u": _dec(x["draw"])})
        for dec, routes in (data.get("route_probabilities") or {}).items():
            gw = self.inv[dec]
            flow_of = {lab: fl for fl, lab in self.labels.routes(gw).items()}
            ivs.append({"type": "routing_set", "gateway": gw, "probabilities": {flow_of[r]: probes._fixed(p) for r, p in routes.items()}})
        for pool, n in (data.get("workers") or {}).items():
            ivs.append({"type": "resource_add", "pool": pool, "count": int(n) - self.model.pools[pool]["amount"], "from": 0})
        groups = {}
        for u in data.get("unavailable") or []:
            pool, k = u["worker"].rsplit("_", 1)
            groups.setdefault((pool, u["from"], u["to"]), []).append(int(k))
        for (pool, lo, hi), ks in groups.items():
            n = self.model.pools[pool]["amount"]
            assert sorted(ks) == list(range(n - len(ks), n)), "unavailable workers are not the highest-numbered"
            ivs.append({"type": "resource_unavailable", "pool": pool, "count": len(ks), "from": lo, "to": hi})
        return scope, {"interventions": ivs, "draw_overrides": over}

    def run_input(self, data, timeout=60):
        self.runs += 1
        try:
            scope, change = self.scenario(data)
        except Unfaithful as e:
            self.unfaithful.append(str(e))
            return Execution("crashed", detail=f"unfaithful wrapper: {e}")
        try:
            _, _, out = rs.reference(str(ROOT), self.doc, scope, change)
        except engine.RunError as e:
            return Execution("crashed", detail=f"reference cannot run: {e}")
        if out.get("status") != "ok":
            return Execution("crashed", detail=str(out.get("error")))
        lab = self.labels.label
        # Only the input may decide the run: every work, wait and route value the engine used must be in the input
        # (review 2026-11-09). Otherwise the seed supplied it, which a document-only program would not have.
        given = {("service", x["case"], x["activity"], x["visit"]) for x in data["work"]}
        given |= {("timer", x["case"], x["wait"], x["visit"]) for x in data["waits"]}
        given |= {("branch", x["case"], x["decision"], x["visit"]) for x in data["draws"]}
        used = {(d["variable"], d["case"], lab[d["element"]], d["visit"]) for d in out["draws"]
                if d["variable"] in ("service", "timer", "branch")}
        if used - given:
            miss = sorted(used - given)
            self.unfaithful.append(f"{scope}: {len(miss)} values not in the input, e.g. {miss[0]}")
            return Execution("crashed", detail=f"used {len(miss)} values the input does not give, e.g. {miss[0]}")
        ev = lambda t, case, kind, name="", visit=0, worker="", route="": {
            "time": int(t), "case": case, "event": kind, "name": name, "visit": int(visit), "worker": worker, "route": route}
        recs = []
        for t in out["tasks"]:
            recs += [ev(t["start"], t["case"], "task_start", lab[t["task"]], t["visit"], t["resource"]),
                     ev(t["end"], t["case"], "task_end", lab[t["task"]], t["visit"], t["resource"])]
        for w in out["timers"]:
            recs += [ev(w["start"], w["case"], "wait_start", lab[w["timer"]], w["visit"]),
                     ev(w["end"], w["case"], "wait_end", lab[w["timer"]], w["visit"])]
        if self.shape == "events":
            recs += [ev(b["time"], b["case"], "decision", lab[b["gateway"]], b["visit"], route=self.labels.routes(b["gateway"])[b["flow"]])
                     for b in out["branches"]]
        recs += [ev(c["end"], c["case"], "case_end") for c in out["cases"]]
        recs.sort(key=lambda r: (r["time"], r["case"], r["event"], r["name"], r["visit"]))
        return Execution("ran", case_ends={c["case"]: float(c["end"]) for c in out["cases"]}, records=recs)


def part2(qs, work):
    out = {"rows": [], "summary": {}}
    for shape in ("events", "no_decisions"):
        tally, wrong, replay_bad, inexpressible, unfaithful = {c: Counter() for c in ("directed", "generic", "program_wide")}, [], [], [], []
        for doc in DOCS:
            nav, schema, model, labels, inv = setup(doc)
            backend = StdinReference(doc, nav, model, labels, inv, shape)
            runner = probes.ProbeRunner(backend, nav, schema)
            for scope in schema.scopes:
                ok, why = runner.replay(scope)
                if not ok:
                    replay_bad.append([doc, scope, why])
            regs = {}
            for cfg in tally:
                p = Path(work) / f"registry_{shape}_{doc}_{cfg}.jsonl"
                p.unlink(missing_ok=True)
                regs[cfg] = Registry(p)
            for q in (q for q in qs if q["doc"] == doc):
                req = oracle_request(q)
                row = {"shape": shape, "id": q["id"], "family": q["family"], "effectful": q["effectful"]}
                for cfg in tally:
                    d = decide(cfg, req, schema, runner, regs[cfg], backend, budget=BUDGET, seed=0)
                    term = TERMS[cause({"permit": d.permit, "reason": d.reason, "inexpressible": d.inexpressible,
                                        "untested": d.untested, "evidence": d.evidence})]
                    tally[cfg][term] += 1
                    row[cfg] = {"term": term, "reason": d.reason, "probes_run": d.probes_run,
                                "evidence": [list(e) for e in d.evidence]}
                # The structured answer, as pilot_runner computes it. None from execute means the generic input has
                # no place for the change (e.g. a visit with no plan column): "inexpressible", reported apart.
                ex = runner.execute(req.scope, req.interventions[0])
                a = answer(req.query, ex.case_ends)[0] if ex is not None and ex.status == "ran" else None
                row["answer"], row["gold"] = a, q["gold"]
                row["structured"] = "inexpressible" if ex is None else ex.status
                if ex is None:
                    inexpressible.append([q["id"], q["effectful"], q["binding"].get("visit")])
                elif a != q["gold"]:
                    wrong.append([shape, q["id"], a, q["gold"], ex.status])
                out["rows"].append(row)
            unfaithful += [[doc, u] for u in backend.unfaithful]
        out["summary"][shape] = {"history_check_failures": replay_bad, "answers_wrong": wrong,
                                 "structured_inexpressible": inexpressible,
                                 "wrapper_unfaithful_runs": unfaithful,
                                 **{cfg: dict(c) for cfg, c in tally.items()},
                                 "directed_by_family": {f: dict(Counter(r["directed"]["term"] for r in out["rows"]
                                                                        if r["shape"] == shape and r["family"] == f))
                                                        for f in sorted({q["family"] for q in qs})}}
    return out


def main(q_path, work, out_path):
    qs = json.loads(Path(q_path).read_text(encoding="utf-8"))
    if not qs:
        print("no questions")
        return 2
    Path(work).mkdir(parents=True, exist_ok=True)
    DOCS[:] = sorted({q["doc"] for q in qs})
    p1 = part1(qs)
    print("part 1:", json.dumps({k: (v if not isinstance(v, dict) else {a: (b if not isinstance(b, list) else len(b)) for a, b in v.items()})
                                 for k, v in p1.items()}))
    p2 = part2(qs, work)
    for shape, s in p2["summary"].items():
        print(f"part 2 [{shape}]: history failures {len(s['history_check_failures'])}, wrong answers {len(s['answers_wrong'])},",
              f"inexpressible {len(s['structured_inexpressible'])}, unfaithful wrapper runs {len(s['wrapper_unfaithful_runs'])},",
              "directed", s["directed"], "| generic", s["generic"], "| program_wide", s["program_wide"])
    deep = {(d, sc, r[0], r[1], r[2]) for d, sc, r, _, _ in p1["route_flips"]["needing_unlisted_visits"]}
    qdoc = {q["id"]: (q["doc"], q["scope"]) for q in qs}
    used = []
    for row in p2["rows"]:
        for cfg in ("directed", "generic", "program_wide"):
            for name, ok, why in row[cfg]["evidence"]:
                hit = "values the input does not give" in str(why)     # a deep witness that made the wrapper fail
                for d, sc, case, dec, visit in deep:
                    hit = hit or (qdoc[row["id"]] == (d, sc) and str(why).startswith(f"{case} {dec} visit {visit}:"))
                if hit:
                    used.append([row["shape"], row["id"], cfg, ok, why])
    p2["decisions_using_deep_witnesses"] = used
    print("decisions whose evidence used a witness needing unlisted visits:", len(used))
    bad_terms = ("Caught", "Already caught", "Failed history check")
    blockers = p1["rejections"] + sum(len(s["history_check_failures"]) + len(s["answers_wrong"]) + len(s["wrapper_unfaithful_runs"])
                                      + sum(s[cfg].get(t, 0) for cfg in ("directed", "generic", "program_wide") for t in bad_terms)
                                      for s in p2["summary"].values())
    import hashlib
    Path(out_path).write_text(json.dumps({"questions": q_path, "questions_sha256": hashlib.sha256(Path(q_path).read_bytes()).hexdigest(),
                                          "part1": p1, "part2": p2, "blockers": blockers}, indent=1),
                              encoding="utf-8")
    print("blockers (any rejection of the reference):", blockers)
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
