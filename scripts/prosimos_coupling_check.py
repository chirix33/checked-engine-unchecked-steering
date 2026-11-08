"""Does a shared seed keep Prosimos runs paired when one case is added?

Runs each process three ways with the same seed: twice with N cases (is it repeatable?) and once
with N+1 cases (do the first N cases keep their realization?). Removing a case is the same comparison
read in reverse. No model calls.

Usage: .venv/Scripts/python -I scripts/prosimos_coupling_check.py <inputs/synthetic> <out_dir> <out_json>
"""
import json
import os
import random
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from prosimos.simulation_engine import run_simulation

N = 50
SEED = 20261104
START = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
PROCESSES = ["Insurance_Claims", "Loan_Application", "Pharmacy", "Procure_to_Pay"]


def run(inputs, name, cases, out_dir, tag):
    random.seed(SEED)
    np.random.seed(SEED)
    log = os.path.join(out_dir, f"{name}_{tag}.csv")
    stat = os.path.join(out_dir, f"{name}_{tag}_stats.csv")
    run_simulation(
        os.path.join(inputs, name + ".bpmn"), os.path.join(inputs, name + ".json"),
        cases, stat_out_path=stat, log_out_path=log, starting_at=START.isoformat(),
    )
    df = pd.read_csv(log)
    df["start_time"] = pd.to_datetime(df["start_time"], format="ISO8601", utc=True)
    df["end_time"] = pd.to_datetime(df["end_time"], format="ISO8601", utc=True)
    return df


def norm(df):
    df = df.sort_values(["case_id", "start_time", "end_time", "activity"])
    return df[["case_id", "activity", "start_time", "end_time", "resource"]].reset_index(drop=True)


def main(inputs, out_dir, out_json):
    os.makedirs(out_dir, exist_ok=True)
    results = {}
    for name in PROCESSES:
        a = norm(run(inputs, name, N, out_dir, "a"))
        b = norm(run(inputs, name, N, out_dir, "b"))
        c = norm(run(inputs, name, N + 1, out_dir, "plus1"))
        repeatable = a.equals(b)
        ids = sorted(a["case_id"].unique())
        same_path, same_full = 0, 0
        for cid in ids:
            x = a[a.case_id == cid]
            y = c[c.case_id == cid]
            same_path += x["activity"].tolist() == y["activity"].tolist()
            same_full += x.drop(columns="case_id").reset_index(drop=True).equals(y.drop(columns="case_id").reset_index(drop=True))
        first_a = a.groupby("case_id")["start_time"].min()
        first_c = c.groupby("case_id")["start_time"].min()
        same_arrival = int((first_a == first_c.reindex(first_a.index)).sum())
        results[name] = {
            "cases": len(ids), "repeatable_same_seed": bool(repeatable),
            "first_start_unchanged": same_arrival, "activity_path_unchanged": int(same_path),
            "full_record_unchanged": int(same_full),
        }
        print(name, results[name], flush=True)
    meta = {"seed": SEED, "n": N, "prosimos": "2.1.0", "start": START.isoformat(), "results": results}
    json.dump(meta, open(out_json, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:4])
