"""Compare selected factual behavior of the reference engine with Prosimos, and measure queues in the engine.

This checks that the engine's factual realizations resemble the published simulator on the same models. It
does not establish equivalence and cannot validate any what-if answer. Runs are not paired: the two programs
draw differently, so only aggregates over realizations are compared, with their spread.

Usage: python -I scripts/engine_vs_prosimos_factual.py <project_root> <prosimos_log_dir> <out_json>
Prosimos logs come from scripts/prosimos_contention_check.py.
"""
import json
import os
import re
import statistics
import sys
import tempfile
import xml.etree.ElementTree as ET

import pandas as pd

MODELS = ["Loan_Application_3_timers", "Pharmacy_3_timers"]
SIZE = 400
PROSIMOS_SEEDS = [20261104, 20261105, 20261106]
ENGINE_SEEDS = [f"factual-{i}" for i in range(10)]
DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
WEEK = 7 * 86400


def windows(cal):
    out = []
    for p in cal["time_periods"]:
        begin = [int(x) for x in p["beginTime"].split(".")[0].split(":")]
        end = [int(x) for x in p["endTime"].split(".")[0].split(":")]
        for d in range(DAYS.index(p["from"]), DAYS.index(p["to"]) + 1):
            out.append((d * 86400 + begin[0] * 3600 + begin[1] * 60 + begin[2],
                        d * 86400 + end[0] * 3600 + end[1] * 60 + end[2]))
    return sorted(out)


def working(wins, t0, t1):
    total = 0.0
    if t1 <= t0:
        return total
    for w in range(int(t0 // WEEK), int(t1 // WEEK) + 1):
        for a, b in wins:
            lo, hi = max(t0, w * WEEK + a), min(t1, w * WEEK + b)
            if hi > lo:
                total += hi - lo
    return total


def summarize(rows, wins_by_pool, n_cases):
    """rows: dicts with case, activity, pool, enabled, start, end (seconds)."""
    by_activity, by_pool = {}, {}
    starts, ends = {}, {}
    for r in rows:
        wins = wins_by_pool[r["pool"]]
        service = working(wins, r["start"], r["end"])
        wait = working(wins, r["enabled"], r["start"])
        a = by_activity.setdefault(r["activity"], {"n": 0, "service": 0.0})
        a["n"] += 1
        a["service"] += service
        p = by_pool.setdefault(r["pool"], {"n": 0, "wait": 0.0, "waited": 0})
        p["n"] += 1
        p["wait"] += wait
        p["waited"] += wait > 0
        starts[r["case"]] = min(starts.get(r["case"], r["enabled"]), r["enabled"])
        ends[r["case"]] = max(ends.get(r["case"], r["end"]), r["end"])
    return {
        "visits_per_case": {k: v["n"] / n_cases for k, v in by_activity.items()},
        "mean_service_s": {k: v["service"] / v["n"] for k, v in by_activity.items()},
        "mean_wait_min": {k: v["wait"] / v["n"] / 60 for k, v in by_pool.items()},
        "share_waiting": {k: v["waited"] / v["n"] for k, v in by_pool.items()},
        "mean_cycle_days": statistics.mean((ends[c] - starts[c]) / 86400 for c in ends),
    }


def merge(runs):
    out = {}
    for key in runs[0]:
        if isinstance(runs[0][key], dict):
            names = sorted({n for r in runs for n in r[key]})
            out[key] = {n: [r[key].get(n, 0.0) for r in runs] for n in names}
        else:
            out[key] = [r[key] for r in runs]
    return out


def describe(values):
    return {"mean": round(statistics.mean(values), 3), "min": round(min(values), 3), "max": round(max(values), 3)}


def main(root, log_dir, out_path):
    root = os.path.abspath(root)
    sys.path.insert(0, os.path.join(root, "reference_engine"))
    from engine import run_scenario  # Evaluation-only reference code.

    syn = os.path.join(root, "data", "zenodo_10435849", "inputs", "synthetic")
    report = {"cases": SIZE, "prosimos_seeds": PROSIMOS_SEEDS, "engine_seeds": ENGINE_SEEDS, "models": {}}
    for model in MODELS:
        spec = json.load(open(os.path.join(syn, model + ".json"), encoding="utf-8"))
        cals = {c["id"]: windows(c) for c in spec["resource_calendars"]}
        pool_wins = {r["name"]: cals[r["calendar"]] for prof in spec["resource_profiles"] for r in prof["resource_list"]}
        names = {e.get("id"): e.get("name") for e in ET.parse(os.path.join(syn, model + ".bpmn")).getroot().iter()
                 if e.tag.endswith("}task")}

        prosimos_runs = []
        monday = pd.Timestamp("2026-01-05", tz="UTC")
        for seed in PROSIMOS_SEEDS:
            df = pd.read_csv(os.path.join(log_dir, f"{model}_{SIZE}_{seed}.csv"))
            rows = []
            for col in ("enable_time", "start_time", "end_time"):
                df[col] = (pd.to_datetime(df[col], format="ISO8601", utc=True) - monday).dt.total_seconds()
            for r in df.itertuples():
                rows.append({"case": r.case_id, "activity": r.activity, "pool": re.sub(r"_\d+$", "", str(r.resource)),
                             "enabled": r.enable_time, "start": r.start_time, "end": r.end_time})
            prosimos_runs.append(summarize(rows, pool_wins, SIZE))

        engine_runs = []
        with tempfile.TemporaryDirectory() as tmp:
            for seed in ENGINE_SEEDS:
                path = os.path.join(tmp, "s.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"schema": "wf-scenario/1", "scenario_id": "factual",
                               "model": {"bpmn": os.path.join(syn, model + ".bpmn"), "params": os.path.join(syn, model + ".json")},
                               "seed": seed, "n_cases": SIZE, "interventions": []}, f)
                run = run_scenario(path)
                assert run["status"] == "ok", run
                rows = [{"case": t["case"], "activity": names[t["task"]], "pool": re.sub(r"_\d+$", "", t["resource"]),
                         "enabled": t["enabled"], "start": t["start"], "end": t["end"]} for t in run["tasks"]]
                engine_runs.append(summarize(rows, pool_wins, SIZE))

        a, b = merge(engine_runs), merge(prosimos_runs)
        entry = {}
        for key in a:
            if isinstance(a[key], dict):
                entry[key] = {n: {"engine": describe(a[key].get(n, [0.0])), "prosimos": describe(b[key].get(n, [0.0]))}
                              for n in sorted(set(a[key]) | set(b[key]))}
            else:
                entry[key] = {"engine": describe(a[key]), "prosimos": describe(b[key])}
        report["models"][model] = entry
        print("==", model)
        print(" mean cycle days", entry["mean_cycle_days"])
        for section in ("mean_wait_min", "share_waiting"):
            print(" ", section)
            for n, v in entry[section].items():
                print("   ", n, "engine", v["engine"], "prosimos", v["prosimos"])
        for section in ("visits_per_case", "mean_service_s"):
            worst = sorted(((abs(v["engine"]["mean"] - v["prosimos"]["mean"]) / max(v["prosimos"]["mean"], 1e-9), n)
                            for n, v in entry[section].items()), reverse=True)[:3]
            print(" ", section, "largest relative gaps:", [(n, round(g, 3)) for g, n in worst])
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:4])
