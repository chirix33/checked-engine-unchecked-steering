"""Re-derive workflow question gold with the independent checker (evaluation-only).

`checker/run.py` was written by a separate agent from the spec alone (D9, D12). It runs here as a separate process
(`python -I`), reading scenario files, so no engine code is imported into it. Two checks per question:

A. **Same scenario.** The question's scenario (its run's seed, the question's interventions and draw overrides): the
   checker's whole output (status, cases, tasks, timers, branches, draws) must equal the reference engine's, and the
   checker's end time for the query case must equal the question's gold.
B. **Printed route draws.** The same scenario, but every route draw printed in the run's Route draws table replaces
   the seed's draw (rounded to the printed 6 decimals), with the question's own overrides on top. The checker's
   query-case end must still equal gold: rounding of route draws does not decide gold. B alone does not show that gold
   is derivable from the document (draws that are not printed still come from the seed; review 2026-11-09 showed B
   agrees on all 8 known non-derivable dev questions).
C. **Every value used is printed.** From the checker's own check-A output (not the generator's rule): every work
   duration, wait delay and route draw the checker used under the change must equal a printed Work plan, Wait plan or
   Route draws cell (route draws compared at 6 decimals), unless the question itself sets it. Arrivals are printed in
   Cases and checked by the factual comparison. This is the derivability check; it is independent of
   `question_draw_coverage.py`, which reuses the generator's own rule.

Per run, the factual scenario is also checked both ways, against the printed Cases table.

The question file is not changed; the checker's end times are in the report (`checker_end`). Exit 1 on any
disagreement, 2 if the file has no questions.

Usage: python -X utf8 validation/workflow_test_checker.py <questions.json> <work_dir> <out_json> [workers]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "reference_engine")]
sys.dont_write_bytecode = True

import engine                                                    # noqa: E402
import render_workflow_doc as render                             # noqa: E402
import replay_screen as rs                                       # noqa: E402
import workflow_policy_set as wp                                 # noqa: E402
import workflow_test_set as wt                                   # noqa: E402

wt.register(rs)
wp.register(rs)       # policy-variant documents: their own parameter files, through the same lookups
PY = sys.executable
SECTIONS = ["status", "error", "cases", "tasks", "timers", "branches", "draws"]


def printed_draws(nav, run, model, bpmn):
    """Route draws as printed in the document, keyed to engine element ids."""
    ids = {v: k for k, v in render.Labels(model, bpmn).label.items()}
    node = next(n for n in nav["nodes"] if n["title"] == f"{run}: Route draws" and n["kind"] == "table")
    cols = node["table"]["columns"]
    out = []
    for r in node["table"]["rows"]:
        for j, h in enumerate(cols[2:], start=2):
            if r[j] != "":
                out.append({"case": r[0], "element": ids[r[1]], "visit": int(h.split()[1]), "variable": "branch", "u": r[j]})
    return out


def merged(printed, own):
    keyed = {(o["case"], o["element"], o["visit"], o["variable"]): o for o in printed}
    for o in own:
        keyed[(o["case"], o["element"], o["visit"], o["variable"])] = o
    return list(keyed.values())


def scenario(doc, run, sid, interventions, overrides, work):
    bpmn, params = rs.model_files(str(ROOT), doc)
    rel = lambda p: os.path.relpath(p, work).replace("\\", "/")
    return {"schema": "wf-scenario/1", "scenario_id": sid, "model": {"bpmn": rel(bpmn), "params": rel(params)},
            "seed": rs.seed_of(doc, run), "n_cases": rs.N_CASES, "interventions": interventions, "draw_overrides": overrides}


def run_checker(job):
    scen, work = job
    sp, op = work / f"{scen['scenario_id']}.json", work / f"{scen['scenario_id']}.out.json"
    sp.write_text(json.dumps(scen, indent=1), encoding="utf-8")
    p = subprocess.run([PY, "-I", str(ROOT / "checker" / "run.py"), str(sp), str(op)], capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        return {"status": "checker_crashed", "error": p.stderr[-300:]}
    return json.loads(op.read_text(encoding="utf-8"))


def unprinted(out, nav, run, lab, q=None):
    """Values the checker used that the document does not print and the question does not set (check C)."""
    def tab(sec):
        n = next(n for n in nav["nodes"] if n["title"] == f"{run}: {sec}" and n["kind"] == "table")
        return {(r[0], r[1], int(h.split()[1])): r[j] for r in n["table"]["rows"]
                for j, h in enumerate(n["table"]["columns"][2:], start=2) if r[j] != ""}
    wp, wq, rd = tab("Work plan"), tab("Wait plan"), tab("Route draws")
    q = q or {}
    sets = {(iv["selector"]["case"], iv.get("task") or iv.get("timer"), iv["selector"]["visit"])
            for iv in q.get("interventions", []) if isinstance(iv.get("selector"), dict) and "case" in iv["selector"]}
    over = {(o["case"], o["element"], o["visit"]) for o in q.get("draw_overrides", [])}
    miss = []
    for t in out.get("tasks", []):
        if (t["case"], t["task"], t["visit"]) not in sets:
            v = wp.get((t["case"], lab[t["task"]], t["visit"]))
            if v is None or int(v) != t["service"]:
                miss.append(["work", t["case"], lab[t["task"]], t["visit"], v, t["service"]])
    for t in out.get("timers", []):
        if (t["case"], t["timer"], t["visit"]) not in sets:
            v = wq.get((t["case"], lab[t["timer"]], t["visit"]))
            if v is None or int(v) != t["delay"]:
                miss.append(["wait", t["case"], lab[t["timer"]], t["visit"], v, t["delay"]])
    for d in out.get("draws", []):
        if d["variable"] == "branch" and (d["case"], d["element"], d["visit"]) not in over:
            v = rd.get((d["case"], lab[d["element"]], d["visit"]))
            if v is None or v != "%.6f" % float(d["u"]):
                miss.append(["route", d["case"], lab[d["element"]], d["visit"], v, d["u"]])
    return miss


def ends(out):
    return {c["case"]: c["end"] for c in out.get("cases", [])} if out.get("status") == "ok" else {}


def main(q_path, work_dir, out_path, workers=8):
    qs = json.loads(Path(q_path).read_text(encoding="utf-8"))
    if not qs:
        print("no questions")
        return 2
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    models, navs, labels, jobs, meta = {}, {}, {}, [], []
    for doc in sorted({q["doc"] for q in qs}):
        bpmn, params = rs.model_files(str(ROOT), doc)
        models[doc] = (engine.Model(bpmn, params), bpmn)
        labels[doc] = render.Labels(models[doc][0], bpmn).label
        navs[doc] = wp.load_nav(doc)
    runs = sorted({(q["doc"], q["scope"]) for q in qs})
    for doc, run in runs:
        model, bpmn = models[doc]
        pd = printed_draws(navs[doc], run, model, bpmn)
        tag = f"{doc}__{run.replace(' ', '_')}"
        jobs += [(scenario(doc, run, f"F_{tag}_A", [], [], work), work), (scenario(doc, run, f"F_{tag}_B", [], pd, work), work)]
        meta += [("factual", doc, run, None, "A"), ("factual", doc, run, None, "B")]
    for q in qs:
        model, bpmn = models[q["doc"]]
        own = q.get("draw_overrides", [])
        pd = printed_draws(navs[q["doc"]], q["scope"], model, bpmn)
        jobs += [(scenario(q["doc"], q["scope"], f"Q_{q['id']}_A", q["interventions"], own, work), work),
                 (scenario(q["doc"], q["scope"], f"Q_{q['id']}_B", q["interventions"], merged(pd, own), work), work)]
        meta += [("question", q["doc"], q["scope"], q, "A"), ("question", q["doc"], q["scope"], q, "B")]
    with ThreadPoolExecutor(int(workers)) as ex:
        outs = list(ex.map(run_checker, jobs))
    rows, bad = [], []
    for (kind, doc, run, q, form), (scen, _), out in zip(meta, jobs, outs):
        row = {"kind": kind, "doc": doc, "run": run, "form": form, "id": q["id"] if q else None, "checker_status": out.get("status")}
        if form == "A":
            ref = rs.reference(str(ROOT), doc, run, {"interventions": scen["interventions"], "draw_overrides": scen["draw_overrides"]})[2]
            diff = [s for s in SECTIONS if ref.get(s) != out.get(s)]
            row["sections_differing_from_engine"] = diff
            miss = unprinted(out, navs[doc], run, labels[doc], q) if out.get("status") == "ok" else [["no output"]]
            row["C_unprinted_values"] = miss
            row["C_ok"] = not miss
            ok = not diff and not miss
        else:
            ok = True
        if kind == "factual":
            rec = {r[0]: int(r[2]) for r in next(n for n in navs[doc]["nodes"] if n["title"] == f"{run}: Cases")["table"]["rows"]}
            row["case_ends_match_printed"] = ends(out) == rec
            ok = ok and row["case_ends_match_printed"]
        else:
            row["checker_end"] = ends(out).get(q["query_case"])
            row["gold"] = q["gold"]
            ok = ok and row["checker_end"] == q["gold"]
        row["agree"] = ok
        rows.append(row)
        if not ok:
            bad.append(row)
    import hashlib
    summary = {"questions": len(qs), "questions_file": str(q_path).replace("\\", "/"),
               "questions_sha256": hashlib.sha256(Path(q_path).read_bytes()).hexdigest(), "runs": len(runs),
               "A_same_scenario": {"agree": sum(not r["sections_differing_from_engine"] and r["checker_end"] == r["gold"]
                                            for r in rows if r["form"] == "A" and r["kind"] == "question"),
                                   "of": len(qs)},
               "B_printed_route_draws": {"agree": sum(r["agree"] for r in rows if r["form"] == "B" and r["kind"] == "question"),
                                         "of": len(qs)},
               "C_every_value_printed": {"pass": sum(r["C_ok"] for r in rows if r["form"] == "A" and r["kind"] == "question"),
                                         "of": len(qs)},
               "factual_runs": {"agree": sum(r["agree"] for r in rows if r["kind"] == "factual"), "of": 2 * len(runs)},
               "disagreements": bad}
    Path(out_path).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "disagreements"}), "disagreements:", len(bad))
    for b in bad[:20]:
        print("  ", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
