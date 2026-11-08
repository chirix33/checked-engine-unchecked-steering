"""Compare B0 and R1 development builds, using the keep-or-drop rule in D15.

Usage: python -X utf8 -I scripts/compare_b0_r1.py <project_root> <out_json>
"""
import collections
import glob
import json
import os
import statistics
import sys

SYSTEMS = {"b0": "build_test_v1", "r1": "build_test_r1"}
DOCS = ["mfg_dev", "itops_dev", "workflow_loan_dev", "workflow_pharmacy_dev"]
SETUPS = ["gpt-oss-120b", "qwen3.5-9b", "gemma-31b-ollama"]


def load(root):
    rows = {}
    for system, folder in SYSTEMS.items():
        rows[system] = []
        for path in glob.glob(os.path.join(root, "runs", folder, "builds_*.jsonl")):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    r["doc"] = r["build"].split("/")[1]
                    rows[system].append(r)
    return rows


def stage(root, system, r):
    setup, doc, build = r["build"].split("/")
    path = os.path.join(root, "runs", SYSTEMS[system], setup, doc, build, "program.json")
    if not os.path.exists(path):
        return r["status"]
    p = json.load(open(path, encoding="utf-8"))
    return "accepted" if p.get("passed") else f"failed_{p.get('failed_step')}"


def main(root, out_path):
    root = os.path.abspath(root)
    rows = load(root)
    report = {"accepted": {}, "cost": {}, "stages": {}, "status": {}}
    print(f"{'accepted of builds':24}" + "".join(f"{d.replace('workflow_', '').replace('_dev', ''):>18}" for d in DOCS) + f"{'total':>10}")
    totals = collections.Counter()
    for setup in SETUPS:
        for system in SYSTEMS:
            cells, acc, n = [], 0, 0
            for doc in DOCS:
                items = [r for r in rows[system] if r["build"].startswith(f"{setup}/{doc}/")]
                a = sum(r["accepted"] for r in items)
                f1 = [r["mean_f1"] for r in items if r["accepted"]]
                cells.append(f"{a}/{len(items)}" + (f" ({statistics.mean(f1):.2f})" if f1 else ""))
                acc += a
                n += len(items)
                report["accepted"][f"{setup}|{system}|{doc}"] = {"accepted": a, "builds": len(items), "f1": f1}
            totals[system] += acc
            print(f"{setup + ' ' + system:24}" + "".join(f"{c:>18}" for c in cells) + f"{acc}/{n:>7}")
    print("totals:", dict(totals), "gain:", totals["r1"] - totals["b0"])
    print()
    print(f"{'cost':24}{'builds':>7}{'acc':>5}{'hours':>7}{'prompt M':>10}{'output M':>10}{'usd':>8}{'prompt/acc k':>14}{'output/acc k':>14}{'s/acc':>8}{'busy':>6}{'cut':>5}")
    for setup in SETUPS:
        for system in SYSTEMS:
            items = [r for r in rows[system] if r["build"].startswith(setup + "/")]
            acc = sum(r["accepted"] for r in items)
            p, o = sum(r["prompt_tokens"] for r in items), sum(r["output_tokens"] for r in items)
            s = sum(r["seconds"] for r in items)
            usd = sum(r["usd_list_price"] for r in items)
            entry = {"builds": len(items), "accepted": acc, "seconds": round(s), "prompt_tokens": p, "output_tokens": o, "usd": round(usd, 3),
                     "prompt_per_accepted": round(p / acc) if acc else None, "output_per_accepted": round(o / acc) if acc else None,
                     "seconds_per_accepted": round(s / acc) if acc else None, "busy": sum(r["busy_events"] for r in items),
                     "length_cutoffs": sum(r["length_cutoffs"] for r in items), "largest_prompt": max(r["largest_prompt_tokens"] for r in items),
                     "missing_tokens": sum(r["calls_missing_tokens"] for r in items), "failed_calls": sum(r["failed_calls"] for r in items),
                     "non_completed": dict(collections.Counter(r["status"] for r in items if r["status"] != "completed"))}
            report["cost"][f"{setup}|{system}"] = entry
            print(f"{setup + ' ' + system:24}{len(items):>7}{acc:>5}{s / 3600:>7.2f}{p / 1e6:>10.2f}{o / 1e6:>10.2f}{usd:>8.2f}"
                  f"{(p / acc / 1e3 if acc else 0):>14.0f}{(o / acc / 1e3 if acc else 0):>14.0f}{(s / acc if acc else 0):>8.0f}{entry['busy']:>6}{entry['length_cutoffs']:>5}"
                  f"  largest {entry['largest_prompt']}, missing {entry['missing_tokens']}, failed calls {entry['failed_calls']} {entry['non_completed'] or ''}")
    print()
    for system in SYSTEMS:
        for setup in SETUPS:
            items = [r for r in rows[system] if r["build"].startswith(setup + "/")]
            c = collections.Counter(stage(root, system, r) for r in items)
            report["stages"][f"{setup}|{system}"] = dict(c)
            print(system, setup, dict(c))
    pharm = {s: sum(r["accepted"] for r in rows[s] if r["doc"] == "workflow_pharmacy_dev") for s in SYSTEMS}
    print("\nRule: gain >= 4 of 36:", totals["r1"] - totals["b0"] >= 4, "| Pharmacy not worse:", pharm["r1"] >= pharm["b0"], pharm)
    all_usd = sum(e["usd"] for e in report["cost"].values())
    print("list-price spend in build tests:", round(all_usd, 2), "plus connection tests about 0.03")
    report["totals"], report["pharmacy"], report["usd_total"] = dict(totals), pharm, round(all_usd, 3)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:3])
