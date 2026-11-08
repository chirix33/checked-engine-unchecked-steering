"""Replay screen (D17): do programs that replay history exactly still answer valid interventions wrongly?

Two steps, kept apart so targets are fixed before any program is scored:

  targets   Choose changes by a fixed rule from the reference's factual run. No program is opened.
  score     Run every accepted workflow program on the factual run and on each change.

A change is written into a copy of the program's own document map, using table rows from the reference, and the
program reads that copy with its own reader. Outcomes are hidden with the same pinned blinding as acceptance. The
true outcomes are also read by the program, so every program is judged in its own format. No model calls.

Evaluation-side only. Development data. Nothing here reaches a system under test.

Usage: python -X utf8 scripts/replay_screen.py <project_root> targets <out_json>
       python -X utf8 scripts/replay_screen.py <project_root> check
       python -X utf8 scripts/replay_screen.py <project_root> score <targets_json> <out_json> [workers] [builds_glob_root ...]
"""
import collections
import copy
import glob
import hashlib
import json
import multiprocessing
import os
import re
import sys
import tempfile
import time
from pathlib import Path

DOCS = {
    "workflow_loan_dev": {"model": "Loan_Application_3_timers", "seed_prefix": "dev-loan"},
    "workflow_pharmacy_dev": {"model": "Pharmacy_3_timers", "seed_prefix": "dev-pharmacy"},
}
RUNS = ["Run 01", "Run 02", "Run 03", "Run 04"]
N_CASES = 15
HORIZON = 10 ** 8
SYSTEM_FOLDERS = {"b0": "build_test_v1", "r1": "build_test_r1", "r1_claude": "build_test_r1_claude", "b0_claude": "build_test_b0_claude"}
SECTIONS = {"Cases", "Work plan", "Wait plan", "Route draws", "Task log", "Wait log", "Decision log"}


def setup_paths(root):
    root = os.path.abspath(root)
    for sub in ("redesign", "reference_engine", "scripts"):
        path = os.path.join(root, sub)
        if path not in sys.path:
            sys.path.insert(0, path)
    sys.dont_write_bytecode = True
    return root


def model_files(root, doc):
    syn = os.path.join(root, "data", "zenodo_10435849", "inputs", "synthetic")
    name = DOCS[doc]["model"]
    return os.path.join(syn, name + ".bpmn"), os.path.join(syn, name + ".json")


def seed_of(doc, run):
    return f"{DOCS[doc]['seed_prefix']}-{run.split()[1]}"


def scenario(doc, run, change):
    return {"schema": "wf-scenario/1", "scenario_id": f"{doc}/{run}", "seed": seed_of(doc, run), "n_cases": N_CASES,
            "interventions": change.get("interventions", []), "draw_overrides": change.get("draw_overrides", [])}


def reference(root, doc, run, change):
    """Run the reference engine, returning the run object and the output records."""
    import engine
    bpmn, params = model_files(root, doc)
    model = engine.Model(bpmn, params)
    state = engine.Run(model, scenario(doc, run, change))
    return model, state, state.execute()


def plan_tables(root, doc, run, change):
    """Rows of every chapter section for this realization, including changed plan values."""
    import render_workflow_doc as render
    bpmn, params = model_files(root, doc)
    import engine
    model = engine.Model(bpmn, params)
    labels = render.Labels(model, bpmn)
    cycles = render.in_cycle(model)
    tables, _ = render.chapter_tables(engine, model, labels, cycles, scenario(doc, run, change), seed_of(doc, run))
    return {name: rows for name, rows, _ in tables}


def changed_map(nav, run, tables):
    """A copy of a document map with one run's section tables replaced. Node ids and other runs stay as they are."""
    out = copy.deepcopy(nav)
    for node in out["nodes"]:
        prefix = f"{run}: "
        if node["title"].startswith(prefix) and node["kind"] == "table":
            section = node["title"][len(prefix):]
            if section in tables:
                rows = tables[section]
                node["table"] = {**node["table"], "columns": list(rows[0]), "rows": [list(r) for r in rows[1:]]}
    return out


# ---- Target rule. It reads only the reference's factual run. ----

def choose_targets(root):
    targets = []
    for doc in DOCS:
        for run in RUNS:
            model, state, base = reference(root, doc, run, {})
            end_of = {c["case"]: c["end"] for c in base["cases"]}
            cases = [c["case"] for c in sorted(base["cases"], key=lambda c: c["arrival"])]
            middle = cases[len(cases) // 2]
            pool_of = lambda t: model.task_pool[t["task"]]
            waits = collections.defaultdict(list)
            for t in base["tasks"]:
                waits[pool_of(t)].append(t["start"] - t["enabled"])
            busiest = max(waits, key=lambda p: (sum(waits[p]) / len(waits[p]), p))
            sized = [p for p in waits if model.pools[p]["amount"] > 1]
            busiest_sized = max(sized, key=lambda p: (sum(waits[p]) / len(waits[p]), p))
            add = []

            def effectful_work(rows, new_value, name):
                for t in rows:
                    change = {"interventions": [{"type": "duration_set", "task": t["task"], "seconds": new_value(t),
                                                 "selector": {"case": t["case"], "visit": t["visit"]}}]}
                    if moved(root, doc, run, change, end_of):
                        add.append({"name": name, "family": "activity_duration", **change})
                        return

            pool_tasks = sorted((t for t in base["tasks"] if pool_of(t) == busiest), key=lambda t: (t["enabled"], t["case"], t["task"]))
            effectful_work(pool_tasks, lambda t: t["service"] + 3600, "work_up_busiest_pool")
            late = sorted((t for t in base["tasks"] if t["case"] == middle), key=lambda t: (-t["service"], t["task"]))
            effectful_work(late, lambda t: 1, "work_down_to_1s")

            def effectful_timer(rows, new_value, name):
                for t in rows:
                    change = {"interventions": [{"type": "timer_set", "timer": t["timer"], "seconds": new_value(t),
                                                 "selector": {"case": t["case"], "visit": t["visit"]}}]}
                    if moved(root, doc, run, change, end_of):
                        add.append({"name": name, "family": "timer_delay", **change})
                        return

            timers = sorted(base["timers"], key=lambda t: (t["start"], t["case"]))
            effectful_timer(timers, lambda t: t["delay"] + 3600, "wait_up")
            effectful_timer(list(reversed(timers)), lambda t: 0, "wait_zero")

            # Route flips reach paths the history did not take. A flip sets one draw so the other route is chosen.
            used = collections.Counter(b["flow"] for b in base["branches"])
            flips = []
            for b in sorted(base["branches"], key=lambda b: (b["time"], b["case"], b["gateway"])):
                for flow, p in model.branch[b["gateway"]]:
                    if flow != b["flow"] and p > 0:
                        flips.append((used[flow], b, flow))
            flips.sort(key=lambda x: (x[0], x[1]["time"], x[1]["case"]))

            def draw_for(gateway, flow):
                low = 0
                for f, p in model.branch[gateway]:
                    if f == flow:
                        return str(float(low + p / 2))
                    low += p
                raise AssertionError(flow)

            def try_flips(candidates, name):
                for _, b, flow in candidates:
                    change = {"draw_overrides": [{"case": b["case"], "element": b["gateway"], "visit": b["visit"],
                                                  "variable": "branch", "u": draw_for(b["gateway"], flow)}]}
                    try:
                        ok = moved(root, doc, run, change, end_of)
                    except engine_errors():
                        ok = False
                    if ok:
                        add.append({"name": name, "family": "routing_outcome", "flip": {"from": b["flow"], "to": flow}, **change})
                        return

            try_flips(flips, "route_flip_least_used_path")
            cycles = __import__("render_workflow_doc").in_cycle(model)
            # Review fix: exclude the flip already chosen, so the two route targets never duplicate each other.
            chosen = {json.dumps(t.get("draw_overrides"), sort_keys=True) for t in add if t["family"] == "routing_outcome"}
            loop_flips = [x for x in flips if x[1]["gateway"] in cycles and _reaches(model, x[2], x[1]["gateway"])
                          and json.dumps([{"case": x[1]["case"], "element": x[1]["gateway"], "visit": x[1]["visit"],
                                           "variable": "branch", "u": draw_for(x[1]["gateway"], x[2])}], sort_keys=True) not in chosen]
            try_flips(loop_flips, "route_flip_into_loop")

            add.append({"name": "case_remove_middle", "family": "case_set",
                        "interventions": [{"type": "case_remove", "case": middle}]})
            arrival = {c["case"]: c["arrival"] for c in base["cases"]}[middle]
            add.append({"name": "case_add_near_middle", "family": "case_set",
                        "interventions": [{"type": "case_add", "case": "x1", "arrival": arrival + 450}]})
            add.append({"name": "worker_added", "family": "resource_availability", "params_pool": busiest_sized, "params_delta": 1,
                        "interventions": [{"type": "resource_add", "pool": busiest_sized, "count": 1, "from": 0}]})
            add.append({"name": "worker_removed", "family": "resource_availability", "params_pool": busiest_sized, "params_delta": -1,
                        "interventions": [{"type": "resource_unavailable", "pool": busiest_sized, "count": 1, "from": 0, "to": HORIZON}]})

            # No-effect control: change the work for a visit that never happens.
            reached = {(t["case"], t["task"], t["visit"]) for t in base["tasks"]}
            repeat = sorted(t for t, k in model.kind.items() if k == "task" and t in cycles)
            for t in repeat:
                candidate = (cases[0], t, 3)
                if candidate not in reached and (cases[0], t, 2) not in reached:
                    add.append({"name": "no_effect_unreached_visit", "family": "no_effect_control", "interventions": [
                        {"type": "duration_set", "task": t, "seconds": 5000, "selector": {"case": cases[0], "visit": 3}}]})
                    break
            for item in add:
                targets.append({"doc": doc, "run": run, **item})
    return targets


def engine_errors():
    import engine
    return (engine.RunError,)


def _reaches(model, flow, element):
    seen, pending = set(), [model.flows[flow][1]]
    while pending:
        cur = pending.pop()
        if cur == element:
            return True
        if cur not in seen:
            seen.add(cur)
            pending += [model.flows[f][1] for f in model.outgoing.get(cur, [])]
    return False


def moved(root, doc, run, change, base_ends):
    _, _, out = reference(root, doc, run, change)
    ends = {c["case"]: c["end"] for c in out["cases"]}
    return any(ends.get(c) != e for c, e in base_ends.items() if c in ends)


# ---- Scoring ----

def keys_of(records, after, skip):
    out = collections.Counter()
    skip = {str(k).strip().lower() for k in skip}         # review fix: schedule kinds are lower-cased by records.kind
    for r in records:
        t = r.get("time")
        if t is None or (after is not None and float(t) <= after) or str(r.get("kind", "")).strip().lower() in skip:
            continue
        out[(str(r.get("kind")), tuple(sorted(str(e) for e in r.get("entities") or [])), round(float(t)))] += 1
    return out


def per_case(keys, cases):
    return {c: collections.Counter({k: v for k, v in keys.items() if c in k[1]}) for c in cases}


def norm(text):
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def run_one(code, nav, run, cases, sandbox, toolgen, workdir, params_edit=None):
    """Read a document map with the program's own reader, hide outcomes, simulate, and compare exactly."""
    map_path = Path(workdir) / f"map_{hashlib.sha1((run + str(params_edit) + str(time.time())).encode()).hexdigest()[:10]}.json"
    map_path.write_text(json.dumps(nav))
    blind = None
    try:
        try:
            r = toolgen.read_scope(code, map_path, run)
        except Exception as e:
            return {"status": "read_failed", "detail": str(e)[:200]}
        cut = toolgen._cut(r)
        skip = set(r["schedule_kinds"])
        # Review fix: flag programs that declare outcome columns as inputs, since blinding then keeps those cells.
        outcome_inputs = sorted({(loc[0], tuple(loc[2])) for x in r["inputs"] for loc in x.get("src") or []
                                 if len(loc) == 3 and isinstance(loc[2], list) and any(c in ("end", "start", "enabled", "route", "worker", "time") for c in loc[2])})
        blind = toolgen.blinded_map(nav, map_path, run, r, cut)
        inputs, params = r["inputs"], dict(r["params"])
        if params_edit:
            pool, delta, amount = params_edit
            keys = [k for k, v in params.items() if norm(pool) in norm(k) and isinstance(v, (int, float)) and v == amount]
            if len(keys) != 1:
                return {"status": "not_mappable"}
            params[keys[0]] = amount + delta
        ok, res = sandbox.run(code, "simulate", blind, [run], {"inputs": inputs, "params": params, "start": cut, "horizon": HORIZON})
        if not ok or not isinstance(res, list):
            return {"status": "crashed", "detail": str(res)[-200:]}
        pred, truth = keys_of(res, cut, skip), keys_of(r["outcomes"], cut, skip)
        hit = sum((pred & truth).values())
        total = sum(pred.values()) + sum(truth.values())
        p_case, t_case = per_case(pred, cases), per_case(truth, cases)
        exact_cases = sorted(c for c in cases if p_case[c] == t_case[c] and t_case[c])
        return {"status": "ran", "exact": pred == truth and bool(truth), "f1": round(2 * hit / total, 4) if total else 0.0,
                "outcome_columns_as_inputs": [list(x) for x in outcome_inputs][:6],
                "records_true": sum(truth.values()), "records_pred": sum(pred.values()), "exact_cases": exact_cases,
                "case_keys": {c: sorted(map(str, t_case[c].items())) for c in cases}}
    finally:
        if blind is not None:
            Path(blind).unlink(missing_ok=True)
        map_path.unlink(missing_ok=True)


def score_program(job):
    root, path, system, targets = job
    root = setup_paths(root)
    from otf_r1 import sandbox, toolgen
    parts = os.path.normpath(path).split(os.sep)
    setup, doc, build = parts[-4], parts[-3], parts[-2]
    program = json.load(open(path, encoding="utf-8"))
    code = program["code"]
    nav = json.loads(Path(path).with_name("navmap.json").read_text())
    entry = {"system": system, "setup": setup, "doc": doc, "build": build, "acceptance_f1": program.get("mean_f1"), "runs": {}}
    with tempfile.TemporaryDirectory() as tmp:
        for run in RUNS:
            base_change = {}
            base_tables = plan_tables(root, doc, run, base_change)
            _, _, base_out = reference(root, doc, run, base_change)
            cases = sorted(c["case"] for c in base_out["cases"])
            factual = run_one(code, changed_map(nav, run, base_tables), run, cases, sandbox, toolgen, tmp)
            run_entry = {"factual": {k: v for k, v in factual.items() if k != "case_keys"}, "changes": []}
            entry["runs"][run] = run_entry
            for target in [t for t in targets if t["doc"] == doc and t["run"] == run]:
                _, _, truth_out = reference(root, doc, run, target)
                truth_cases = sorted(c["case"] for c in truth_out["cases"])
                edit = None
                if "params_pool" in target:
                    model = __import__("engine").Model(*model_files(root, doc))
                    edit = (target["params_pool"], target["params_delta"], model.pools[target["params_pool"]]["amount"])
                result = run_one(code, changed_map(nav, run, plan_tables(root, doc, run, target)), run, truth_cases, sandbox, toolgen, tmp, edit)
                record = {"name": target["name"], "family": target["family"], "status": result["status"],
                          "signature": json.dumps({k: v for k, v in target.items() if k != "name"}, sort_keys=True)}
                if result["status"] == "ran":
                    base_ends = {c["case"]: c["end"] for c in base_out["cases"]}
                    truth_ends = {c["case"]: c["end"] for c in truth_out["cases"]}
                    changed = sorted(c for c in truth_ends if c in base_ends and truth_ends[c] != base_ends[c])
                    exact_factual = set(factual.get("exact_cases", []))
                    record.update({"exact": result["exact"], "f1": result["f1"], "reference_changed_cases": len(changed),
                                   "records_true": result["records_true"], "records_pred": result["records_pred"],
                                   "changed_exact": sum(c in result["exact_cases"] for c in changed),
                                   "case_level_c": sorted(c for c in changed if c in exact_factual and c not in result["exact_cases"]),
                                   "case_level_ok": sorted(c for c in changed if c in exact_factual and c in result["exact_cases"])})
                else:
                    record["detail"] = result.get("detail", "")[:160]
                run_entry["changes"].append(record)
    return entry


def summarize(results):
    lines = []
    for e in results:
        statuses = [e["runs"][r]["factual"].get("status") for r in RUNS]
        exact = [e["runs"][r]["factual"].get("exact", False) for r in RUNS]
        f1 = [e["runs"][r]["factual"].get("f1", 0) for r in RUNS]
        e["replay_exact_runs"] = sum(exact)
        e["replay_exact_program"] = all(exact)
        lines.append(f"{e['system']:9} {e['setup'][:16]:17}{e['doc'][9:12]} {e['build']} accept {e['acceptance_f1']:<6} replay exact runs {sum(exact)}/4  "
                     f"exact-F1 {[round(x, 2) for x in f1]}  {'' if set(statuses) == {'ran'} else statuses}")
    print("\n".join(lines))
    prog_c, run_c, case_c, case_ok = [], [], 0, 0
    fam = collections.defaultdict(lambda: collections.Counter())
    for e in results:
        for run in RUNS:
            r = e["runs"][run]
            seen = set()
            for c in r["changes"]:
                key = c.get("signature") or c["name"]
                if key in seen:                         # review fix: a duplicated change is counted once
                    continue
                seen.add(key)
                fam[c["family"]][c["status"]] += 1
                if c["status"] != "ran":
                    continue
                effectful = c["family"] != "no_effect_control" and c.get("reference_changed_cases", 0) > 0
                if c["family"] == "no_effect_control":
                    # Review fix: a control is a failure only where the program was exact on the factual run.
                    if r["factual"].get("exact"):
                        fam[c["family"]]["control_exact" if c["exact"] else "control_wrong_given_factual_exact"] += 1
                    else:
                        fam[c["family"]]["control_on_inexact_program"] += 1
                if effectful:
                    tag_exact = "given_factual_exact" if r["factual"].get("exact") else "on_inexact_program"
                    fam[c["family"]][("exact_" if c["exact"] else "wrong_") + tag_exact] += 1
                    case_c += len(c["case_level_c"])
                    case_ok += len(c["case_level_ok"])
                    tag = (e["system"], e["setup"], e["doc"], e["build"], run, c["name"], c["f1"])
                    if not c["exact"] and r["factual"].get("exact"):
                        run_c.append(tag)
                        if e["replay_exact_program"]:
                            prog_c.append(tag)
    print("\nby family:")
    for k, v in sorted(fam.items()):
        print(" ", k, dict(v))
    exact_programs = [e for e in results if e["replay_exact_program"]]
    print(f"\nreplay-exact programs: {len(exact_programs)} of {len(results)}; models {sorted({e['setup'] for e in exact_programs})}; specs {sorted({e['doc'] for e in exact_programs})}")
    print(f"runs exact: {sum(e['replay_exact_runs'] for e in results)} of {4 * len(results)}")
    print(f"program-level C: {len(prog_c)}; run-level C: {len(run_c)}; case-level C {case_c} vs ok {case_ok}")
    for t in prog_c[:25]:
        print("  program C", t)
    for t in run_c[:25]:
        if t not in prog_c:
            print("  run C", t)
    return {"replay_exact_programs": len(exact_programs), "program_level_c": prog_c, "run_level_c": run_c,
            "case_level_c": case_c, "case_level_ok": case_ok, "families": {k: dict(v) for k, v in fam.items()}}


def main():
    root = setup_paths(sys.argv[1])
    mode = sys.argv[2]
    if mode == "targets":
        targets = choose_targets(root)
        with open(sys.argv[3], "w", encoding="utf-8") as f:
            json.dump(targets, f, indent=1)
        counts = collections.Counter((t["doc"][9:12], t["family"]) for t in targets)
        print(len(targets), "targets;", dict(counts))
    elif mode == "check":
        # A map built directly from reference rows must equal the map read from the PDF, or the screen is unsound.
        bad = 0
        for doc in DOCS:
            nav = json.load(open(next(iter(glob.glob(os.path.join(root, "runs", "build_test_v1", "*", doc, "b*", "navmap.json")))), encoding="utf-8"))
            index = {n["title"]: n for n in nav["nodes"]}
            for run in RUNS:
                for section, rows in plan_tables(root, doc, run, {}).items():
                    node = index[f"{run}: {section}"]
                    same = node["table"]["columns"] == rows[0] and node["table"]["rows"] == rows[1:]
                    if not same:
                        bad += 1
                        print("DIFF", doc, run, section, len(node["table"]["rows"]), len(rows) - 1, node["table"]["columns"][:8], rows[0][:8])
                        for a, b in zip(node["table"]["rows"], rows[1:]):
                            if a != b:
                                print("   ", a, b)
                                break
        print("map differences:", bad)
    elif mode == "score":
        targets = json.load(open(sys.argv[3], encoding="utf-8"))
        out_path = sys.argv[4]
        workers = int(sys.argv[5]) if len(sys.argv) > 5 else 8
        jobs = []
        for system, folder in SYSTEM_FOLDERS.items():
            for doc in DOCS:
                for path in sorted(glob.glob(os.path.join(root, "runs", folder, "*", doc, "b*", "program.json"))):
                    program = json.load(open(path, encoding="utf-8"))
                    if program.get("passed"):
                        jobs.append((root, path, system, targets))
        print(len(jobs), "accepted workflow programs", flush=True)
        with multiprocessing.Pool(workers) as pool:
            results = []
            for k, entry in enumerate(pool.imap_unordered(score_program, jobs), 1):
                results.append(entry)
                print(k, entry["system"], entry["setup"], entry["doc"], entry["build"], flush=True)
        results.sort(key=lambda e: (e["doc"], e["system"], e["setup"], e["build"]))
        summary = summarize(results)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "programs": results}, f, indent=1)


if __name__ == "__main__":
    main()
