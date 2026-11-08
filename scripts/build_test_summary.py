"""Summarize the development build test: acceptance, failure stage, tokens, time and list-price cost.

Infrastructure failures are reported apart from model failures. Accepted means the pinned B0 check passed.

Usage: python -X utf8 -I scripts/build_test_summary.py <project_root> <out_json> [<mlsys_runs_dir>]
"""
import collections
import glob
import json
import os
import statistics
import sys


def stage(path):
    """Where a completed build stopped, from its saved program."""
    if not os.path.exists(path):
        return "no_program_saved"
    program = json.load(open(path, encoding="utf-8"))
    if program.get("passed"):
        return "accepted"
    return "failed_at_" + str(program.get("failed_step"))


def main(root, out_path, mlsys=None):
    base = os.path.join(root, "runs", "build_test_v1")
    rows = []
    for path in sorted(glob.glob(os.path.join(base, "builds_*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            rows += [json.loads(line) for line in f]
    report = {"builds": [], "by_setup_doc": {}, "by_setup": {}}
    groups = collections.defaultdict(list)
    for r in rows:
        setup, doc, build = r["build"].split("/")
        r["doc"] = doc
        r["stage"] = stage(os.path.join(base, setup, doc, build, "program.json")) if r["status"] == "completed" else r["status"]
        groups[(setup, doc)].append(r)
        report["builds"].append(r)

    def aggregate(items):
        done = [x for x in items if x["status"] in ("completed", "build_crashed")]
        total_s = sum(x["seconds"] for x in items)
        accepted = sum(x["accepted"] for x in items)
        return {
            "builds": len(items), "model_outcomes": len(done), "accepted": accepted,
            "infrastructure_failures": sum(x["status"] == "infrastructure_failure" for x in items),
            "crashed": sum(x["status"] == "build_crashed" for x in items),
            "stages": dict(collections.Counter(x["stage"] for x in items)),
            "accepted_f1": [x["mean_f1"] for x in items if x["accepted"]],
            "median_seconds": round(statistics.median(x["seconds"] for x in items), 1),
            "seconds_total": round(total_s, 1), "seconds_per_accepted": round(total_s / accepted, 1) if accepted else None,
            "prompt_tokens_mean": round(statistics.mean(x["prompt_tokens"] for x in items)),
            "output_tokens_mean": round(statistics.mean(x["output_tokens"] for x in items)),
            "largest_prompt_tokens": max(x["largest_prompt_tokens"] for x in items),
            "usd_mean": round(statistics.mean(x["usd_list_price"] for x in items), 4),
            "usd_total": round(sum(x["usd_list_price"] for x in items), 4),
            "busy_events": sum(x["busy_events"] for x in items),
            "failed_calls": sum(x["failed_calls"] for x in items),
            "length_cutoffs": sum(x["length_cutoffs"] for x in items),
            "calls_missing_tokens": sum(x["calls_missing_tokens"] for x in items),
            "providers": sorted({p for x in items for p in x["providers"]}),
        }

    for (setup, doc), items in sorted(groups.items()):
        report["by_setup_doc"][f"{setup} | {doc}"] = aggregate(items)
    for setup in sorted({s for s, _ in groups}):
        report["by_setup"][setup] = aggregate([x for (s, _), v in groups.items() if s == setup for x in v])

    print(f"{'setup | specification':46}{'acc':>5}{'stages':>4}  {'med s':>7}{'prompt':>9}{'output':>8}{'usd':>8}{'busy':>5}{'cut':>4}")
    for key, a in report["by_setup_doc"].items():
        print(f"{key:46}{a['accepted']}/{a['builds']:<3}     {a['median_seconds']:>7}{a['prompt_tokens_mean']:>9}{a['output_tokens_mean']:>8}"
              f"{a['usd_mean']:>8}{a['busy_events']:>5}{a['length_cutoffs']:>4}  {a['stages']} f1={a['accepted_f1']}")
    print()
    for key, a in report["by_setup"].items():
        print(key, {k: a[k] for k in ("builds", "accepted", "infrastructure_failures", "crashed", "seconds_total", "seconds_per_accepted", "usd_total",
                                      "largest_prompt_tokens", "busy_events", "failed_calls", "calls_missing_tokens", "providers")})

    if mlsys:
        print("\nMLSys on the same development documents (historical, different models and provider):")
        history = {}
        for doc in ("mfg_dev", "itops_dev"):
            for path in sorted(glob.glob(os.path.join(mlsys, doc, "systems", "otf_no_library__*", "setup.json"))):
                data = json.load(open(path, encoding="utf-8"))
                info = data.get("info") or data
                system = os.path.basename(os.path.dirname(path))
                history[f"{doc} | {system}"] = {k: info.get(k) for k in ("model_passed", "model_f1", "model_tries")}
                print(" ", doc, system, history[f"{doc} | {system}"])
        report["mlsys_dev_history"] = history
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:])
