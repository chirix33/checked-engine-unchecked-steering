"""Do accepted workflow programs answer interventions correctly? No model calls.

Each program is scored in its own format. The true result of a change is rendered as a document by the reference
engine, and the program's own outcomes() reads it. The program's simulate(), run with the change applied to its own
inputs or params on a copy with outcomes hidden, must then match those records exactly: same kind, same entities,
same whole-second time. A program that reports only task starts is therefore judged on task starts.

A change is applied only if the program's inputs or params can be matched to it mechanically. Otherwise it is
reported as not mappable, which says nothing about the program. Evaluation-side only. This is a development screen
on a few programs, not a benchmark result.

Usage: python -X utf8 scripts/program_intervention_probe.py <project_root> <out_json>
"""
import collections
import copy
import glob
import json
import os
import re
import sys
import tempfile
from pathlib import Path

SYSTEMS = {"b0": "build_test_v1", "r1": "build_test_r1"}
DOCS = {
    "workflow_loan_dev": {"model": "Loan_Application_3_timers", "seed": "dev-loan-01", "task_name": "Appraise property",
                          "pool": "Appraiser", "case": "c0003", "remove": "c0002"},
    "workflow_pharmacy_dev": {"model": "Pharmacy_3_timers", "seed": "dev-pharmacy-01", "task_name": "Check for Quality Assurance",
                              "pool": "Technician", "case": "c0003", "remove": "c0002"},
}
SCOPE = "Run 01"
N_CASES = 15
HORIZON = 10 ** 8
NAMES = ["duration_set", "timer_set", "case_remove", "resource_add"]


def norm(text):
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def keys_of(records, after, skip_kinds):
    """Comparable identity of each outcome record: kind, entities and whole-second time."""
    out = collections.Counter()
    for r in records:
        t = r.get("time")
        if t is None or (after is not None and float(t) <= after) or r.get("kind") in skip_kinds:
            continue
        out[(str(r.get("kind")), tuple(sorted(str(e) for e in r.get("entities") or [])), round(float(t)))] += 1
    return out


def score(pred, truth, cases):
    """Exact match of records, overall and per case."""
    hit = sum((pred & truth).values())
    n_pred, n_true = sum(pred.values()), sum(truth.values())
    per_case = {}
    for c in cases:
        p = collections.Counter({k: v for k, v in pred.items() if c in k[1]})
        q = collections.Counter({k: v for k, v in truth.items() if c in k[1]})
        per_case[c] = p == q and bool(q)
    f1 = 2 * hit / (n_pred + n_true) if n_pred + n_true else 0.0
    return {"exact_f1": round(f1, 3), "records_true": n_true, "records_predicted": n_pred, "cases_exact": sum(per_case.values()),
            "cases": len(cases), "per_case": per_case}


def match_input(inputs, case, label, value):
    """Where a case's input records hold this value and name this element."""
    wanted = norm(label)
    hits = []
    for i, r in enumerate(inputs):
        if case not in (r.get("entities") or []) and case not in str(r.get("id", "")):
            continue
        if wanted not in norm(json.dumps({k: v for k, v in r.items() if k != "src"}, default=str)):
            continue
        for key, v in (r.get("fields") or {}).items():
            try:
                if abs(float(v) - value) < 0.5:
                    hits.append((i, "fields", key))
            except (TypeError, ValueError):
                pass
        for key in ("value", "amount", "seconds", "duration", "delay", "work"):
            try:
                if key in r and abs(float(r[key]) - value) < 0.5:
                    hits.append((i, None, key))
            except (TypeError, ValueError):
                pass
    return hits


def main(root, out_path):
    root = os.path.abspath(root)
    sys.path[:0] = [os.path.join(root, "redesign"), os.path.join(root, "reference_engine"), os.path.join(root, "scripts")]
    sys.dont_write_bytecode = True
    import engine
    import render_workflow_doc as render_module
    from otf_r1 import sandbox
    from otf_r1.navmap import build_map
    from otf_r1.toolgen import _cut, blinded_map, read_scope

    syn = os.path.join(root, "data", "zenodo_10435849", "inputs", "synthetic")
    results = []
    work_root = Path(root, "runs", "intervention_probe_v1")
    work_root.mkdir(parents=True, exist_ok=True)
    for doc, cfg in DOCS.items():
        bpmn, params = os.path.join(syn, cfg["model"] + ".bpmn"), os.path.join(syn, cfg["model"] + ".json")
        model = engine.Model(bpmn, params)
        meta = json.load(open(os.path.join(root, "runs", "build_test_v1", "docs", doc, "document_meta.json"), encoding="utf-8"))
        labels = meta["element_labels"]

        def reference(interventions):
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "s.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"schema": "wf-scenario/1", "scenario_id": "probe", "model": {"bpmn": bpmn, "params": params},
                               "seed": cfg["seed"], "n_cases": N_CASES, "interventions": interventions}, f)
                out = engine.run_scenario(path)
            assert out["status"] == "ok", out
            return out

        factual = reference([])
        task_id = next(k for k, v in labels.items() if v == cfg["task_name"])
        with_timer = {t["case"] for t in factual["timers"]}
        task_row = next(t for t in factual["tasks"] if t["case"] >= cfg["case"] and t["case"] in with_timer
                        and t["task"] == task_id and t["visit"] == 1)
        case = task_row["case"]
        timer_row = next(t for t in factual["timers"] if t["case"] == case)
        new_work, new_delay = task_row["service"] + 3600, timer_row["delay"] + 3600
        changes = {
            "factual": [],
            "duration_set": [{"type": "duration_set", "task": task_id, "seconds": new_work, "selector": {"case": case, "visit": 1}}],
            "timer_set": [{"type": "timer_set", "timer": timer_row["timer"], "seconds": new_delay, "selector": {"case": case, "visit": timer_row["visit"]}}],
            "case_remove": [{"type": "case_remove", "case": cfg["remove"]}],
            "resource_add": [{"type": "resource_add", "pool": cfg["pool"], "count": 1, "from": 0}],
        }
        truth_maps, truth_runs = {}, {}
        for name, ivs in changes.items():
            folder = work_root / doc / name
            render_module.render(root, cfg["model"], str(folder), [(SCOPE, cfg["seed"], ivs)], N_CASES)
            nav = build_map(folder / "document.pdf")
            truth_maps[name] = folder / "navmap.json"
            truth_maps[name].write_text(json.dumps(nav))
            truth_runs[name] = reference(ivs)
        for system, folder in SYSTEMS.items():
            for path in sorted(glob.glob(os.path.join(root, "runs", folder, "*", doc, "b*", "program.json"))):
                program = json.load(open(path, encoding="utf-8"))
                if not program.get("passed"):
                    continue
                parts = os.path.normpath(path).split(os.sep)
                entry = {"system": system, "setup": parts[-4], "doc": doc, "build": parts[-2], "acceptance_f1": program.get("mean_f1"), "tests": {}}
                results.append(entry)
                code = program["code"]
                map_path = Path(path).with_name("navmap.json")
                nav = json.loads(map_path.read_text())
                try:
                    r = read_scope(code, map_path, SCOPE)
                except Exception as e:
                    entry["error"] = f"read failed: {str(e)[:160]}"
                    continue
                cut = _cut(r)
                skip = set(r["schedule_kinds"])
                blind = blinded_map(nav, map_path, SCOPE, r, cut)

                def run(inputs, prm):
                    ok, res = sandbox.run(code, "simulate", blind, [SCOPE], {"inputs": inputs, "params": prm, "start": cut, "horizon": HORIZON})
                    return (res, None) if ok and isinstance(res, list) else (None, str(res)[-160:])

                base = None
                for name in ["factual"] + NAMES:
                    inputs, prm = copy.deepcopy(r["inputs"]), copy.deepcopy(r["params"])
                    applied = True
                    if name == "case_remove":
                        inputs = [x for x in inputs if cfg["remove"] not in (x.get("entities") or [])]
                        applied = len(inputs) < len(r["inputs"])
                    elif name in ("duration_set", "timer_set"):
                        label = cfg["task_name"] if name == "duration_set" else labels[timer_row["timer"]]
                        old, new = (task_row["service"], new_work) if name == "duration_set" else (timer_row["delay"], new_delay)
                        hits = match_input(inputs, case, label, old)
                        applied = bool(hits)
                        for i, section, key in hits:
                            (inputs[i][section] if section else inputs[i])[key] = new
                    elif name == "resource_add":
                        amount = model.pools[cfg["pool"]]["amount"]
                        keys = [k for k, v in prm.items() if norm(cfg["pool"]) in norm(k) and isinstance(v, (int, float)) and v == amount]
                        applied = len(keys) == 1
                        for k in keys:
                            prm[k] = amount + 1
                    if not applied:
                        entry["tests"][name] = {"status": "not_mappable"}
                        continue
                    out, err = run(inputs, prm)
                    if out is None:
                        entry["tests"][name] = {"status": "crashed", "detail": err}
                        continue
                    ok, truth_records = sandbox.run(code, "outcomes", truth_maps[name], [SCOPE])
                    if not ok or not isinstance(truth_records, list):
                        entry["tests"][name] = {"status": "truth_unreadable", "detail": str(truth_records)[-160:]}
                        continue
                    cases = sorted(c["case"] for c in truth_runs[name]["cases"])
                    pred_keys, true_keys = keys_of(out, cut, skip), keys_of(truth_records, cut, skip)
                    result = score(pred_keys, true_keys, cases)
                    result["status"] = "ran"
                    if name == "factual":
                        base = {"pred": pred_keys, "true": true_keys}
                    else:
                        result["program_reacted"] = pred_keys != base["pred"]
                        moved = [c for c in cases if collections.Counter({k: v for k, v in true_keys.items() if c in k[1]})
                                 != collections.Counter({k: v for k, v in base["true"].items() if c in k[1]})]
                        result["cases_truly_changed"] = len(moved)
                        result["changed_cases_exact"] = sum(result["per_case"][c] for c in moved)
                        result["truly_changed_at_all"] = bool(moved)
                    result.pop("per_case")
                    entry["tests"][name] = result
                blind.unlink(missing_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    print(f"{'program':38}{'accept f1':>10}{'factual':>14}" + "".join(f"{n:>22}" for n in NAMES))
    for e in results:
        tag = f"{e['system']} {e['setup'][:12]} {e['doc'][9:12]} {e['build']}"
        if e.get("error"):
            print(f"{tag:38}{e['acceptance_f1']:>10}  {e['error'][:90]}")
            continue
        f = e["tests"].get("factual", {})
        head = f"{f.get('exact_f1')} ({f.get('cases_exact')}/{f.get('cases')})" if f.get("status") == "ran" else str(f.get("status"))
        cells = []
        for n in NAMES:
            t = e["tests"].get(n, {"status": "skipped"})
            cells.append(t["status"] if t["status"] != "ran" else f"{t['exact_f1']} chg {t['changed_cases_exact']}/{t['cases_truly_changed']}")
        print(f"{tag:38}{e['acceptance_f1']:>10}{head:>14}" + "".join(f"{c:>22}" for c in cells))


if __name__ == "__main__":
    main(*sys.argv[1:3])
