"""Do the candidate processes produce queues caused by busy resources?

Runs Prosimos factually (no interventions) over several seeds and reports, per resource pool, how much
waiting falls inside working hours. Waiting outside the pool's working hours is excluded because it comes
from the calendar, not from contention. This is a screen for choosing processes, not a benchmark result.

Usage: .venv/Scripts/python -I scripts/prosimos_contention_check.py <inputs/synthetic> <out_dir> <out_json>
"""
import json
import os
import random
import re
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from prosimos.simulation_engine import run_simulation

SEEDS = [20261104, 20261105, 20261106]
SIZES = [100, 400]
START = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
MODELS = ["Loan_Application_3_timers", "Pharmacy_3_timers", "Insurance_Claims_3_timers", "Procure_to_Pay_3_timers"]
DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]


def windows(calendar):
    """Weekly working windows as (start, end) seconds from Monday 00:00."""
    out = []
    for p in calendar["time_periods"]:
        a, b = DAYS.index(p["from"]), DAYS.index(p["to"])
        h1, m1, s1 = p["beginTime"].split(".")[0].split(":")
        h2, m2, s2 = p["endTime"].split(".")[0].split(":")
        begin = int(h1) * 3600 + int(m1) * 60 + int(s1)
        end = int(h2) * 3600 + int(m2) * 60 + int(s2)
        for d in range(a, b + 1):
            out.append((d * 86400 + begin, d * 86400 + end))
    return sorted(out)


def working_seconds(wins, t0, t1):
    """Working seconds in [t0, t1), both given as seconds since a Monday 00:00."""
    if t1 <= t0:
        return 0.0
    week = 7 * 86400
    total = 0.0
    for w in range(int(t0 // week), int(t1 // week) + 1):
        for a, b in wins:
            lo, hi = max(t0, w * week + a), min(t1, w * week + b)
            if hi > lo:
                total += hi - lo
    return total


def run(inputs, name, cases, seed, out_dir):
    random.seed(seed)
    np.random.seed(seed)
    log = os.path.join(out_dir, f"{name}_{cases}_{seed}.csv")
    run_simulation(
        os.path.join(inputs, name + ".bpmn"), os.path.join(inputs, name + ".json"), cases,
        stat_out_path=os.path.join(out_dir, f"{name}_{cases}_{seed}_stats.csv"), log_out_path=log,
        starting_at=START.isoformat(),
    )
    df = pd.read_csv(log)
    for col in ("enable_time", "start_time", "end_time"):
        df[col] = pd.to_datetime(df[col], format="ISO8601", utc=True)
    return df


def analyse(df, spec, cases, seed):
    monday = pd.Timestamp("2026-01-05", tz="UTC")
    cal = {c["id"]: windows(c) for c in spec["resource_calendars"]}
    pools = {}
    for prof in spec["resource_profiles"]:
        res = prof["resource_list"][0]
        pools[prof["name"]] = {"size": sum(int(r["amount"]) for r in prof["resource_list"]), "wins": cal[res["calendar"]]}
    df = df.copy()
    df["pool"] = df["resource"].map(lambda r: re.sub(r"_\d+$", "", str(r)))
    e = (df["enable_time"] - monday).dt.total_seconds()
    s = (df["start_time"] - monday).dt.total_seconds()
    t = (df["end_time"] - monday).dt.total_seconds()
    span0, span1 = float(e.min()), float(t.max())
    rows = {}
    for pool, idx in df.groupby("pool").groups.items():
        p = pools[pool]
        wait = [working_seconds(p["wins"], e[i], s[i]) for i in idx]
        busy = sum(working_seconds(p["wins"], s[i], t[i]) for i in idx)
        avail = p["size"] * working_seconds(p["wins"], span0, span1)
        rows[pool] = {
            "size": p["size"], "tasks": len(idx),
            "share_waiting_in_hours": round(float(np.mean([w > 0 for w in wait])), 3),
            "mean_wait_min": round(float(np.mean(wait)) / 60, 1),
            "p90_wait_min": round(float(np.percentile(wait, 90)) / 60, 1),
            "max_wait_min": round(float(np.max(wait)) / 60, 1),
            "utilization": round(busy / avail, 3) if avail else None,
        }
    return {"cases": cases, "seed": seed, "span_days": round((span1 - span0) / 86400, 1), "pools": rows}


def main(inputs, out_dir, out_json):
    os.makedirs(out_dir, exist_ok=True)
    results = {}
    for name in MODELS:
        spec = json.load(open(os.path.join(inputs, name + ".json"), encoding="utf-8"))
        results[name] = []
        for cases in SIZES:
            for seed in SEEDS:
                results[name].append(analyse(run(inputs, name, cases, seed, out_dir), spec, cases, seed))
        for r in results[name]:
            print(name, r["cases"], r["seed"], "days", r["span_days"], flush=True)
            for pool, v in r["pools"].items():
                print("   ", pool, v, flush=True)
    meta = {"prosimos": "2.1.0", "seeds": SEEDS, "sizes": SIZES, "start": START.isoformat(), "results": results}
    json.dump(meta, open(out_json, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:4])
