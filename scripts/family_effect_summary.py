"""How much does each validation intervention change outcomes, compared with its factual run?

Reports per scenario: cases whose record changed, cases whose end time changed, and the mean change in cycle
time. These are single illustrative interventions, not a sample of the benchmark.

Usage: python -I scripts/family_effect_summary.py <engine_out_dir> <out_json>
"""
import json
import os
import statistics
import sys

ORDER = ["unavailable", "resource_add", "duration_set", "duration_scale", "duration_dist", "timer_set", "timer_scale",
         "timer_dist", "routing", "case_add", "case_remove"]


def load(folder, name):
    return json.load(open(os.path.join(folder, name + ".json"), encoding="utf-8"))


def by_case(run):
    tasks = {}
    for t in run["tasks"]:
        tasks.setdefault(t["case"], []).append(t)
    return {c["case"]: {"end": c["end"], "cycle": c["end"] - c["arrival"], "tasks": tasks.get(c["case"], [])} for c in run["cases"]}


def main(folder, out_path):
    rows = []
    for process in ("loan", "pharmacy"):
        for seed in ("trust-a", "trust-b"):
            base = by_case(load(folder, f"P_{process}_{seed}_factual"))
            for name in ORDER:
                run = by_case(load(folder, f"P_{process}_{seed}_{name}"))
                shared = sorted(set(base) & set(run))
                changed = sum(base[c]["tasks"] != run[c]["tasks"] for c in shared)
                end_changed = sum(base[c]["end"] != run[c]["end"] for c in shared)
                delta = statistics.mean(run[c]["cycle"] - base[c]["cycle"] for c in shared) / 60
                rows.append({"process": process, "seed": seed, "intervention": name, "shared_cases": len(shared),
                             "records_changed": changed, "end_changed": end_changed, "mean_cycle_change_min": round(delta, 1)})
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    print(f"{'process':9}{'seed':9}{'intervention':16}{'shared':>7}{'changed':>8}{'end chg':>8}{'cycle chg min':>14}")
    for r in rows:
        print(f"{r['process']:9}{r['seed']:9}{r['intervention']:16}{r['shared_cases']:>7}{r['records_changed']:>8}"
              f"{r['end_changed']:>8}{r['mean_cycle_change_min']:>14}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
