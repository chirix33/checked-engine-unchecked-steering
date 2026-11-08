"""Compare two folders of wf-run outputs field by field. Any difference counts: there is no tolerance.

Usage: python -I scripts/compare_runs.py <dir_a> <dir_b> <out_json>
"""
import json
import os
import sys

SECTIONS = ["status", "error", "cases", "tasks", "timers", "branches", "draws"]


def first_diff(a, b):
    if a == b:
        return None
    if isinstance(a, list) and isinstance(b, list):
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return {"index": i, "a": x, "b": y, "len_a": len(a), "len_b": len(b)}
        return {"index": min(len(a), len(b)), "len_a": len(a), "len_b": len(b)}
    return {"a": a, "b": b}


def main(dir_a, dir_b, out_path):
    names = sorted(set(os.listdir(dir_a)) & set(os.listdir(dir_b)))
    names = [n for n in names if n.endswith(".json")]
    only_a = sorted(set(os.listdir(dir_a)) - set(os.listdir(dir_b)))
    only_b = sorted(set(os.listdir(dir_b)) - set(os.listdir(dir_a)))
    same, different, statuses = 0, [], {}
    for name in names:
        a = json.load(open(os.path.join(dir_a, name), encoding="utf-8"))
        b = json.load(open(os.path.join(dir_b, name), encoding="utf-8"))
        key = a.get("error") if a.get("status") == "error" else "ok"
        statuses[key] = statuses.get(key, 0) + 1
        diffs = {s: first_diff(a.get(s), b.get(s)) for s in SECTIONS if a.get(s) != b.get(s)}
        if diffs:
            different.append({"scenario": name, "sections": sorted(diffs), "first": diffs})
        else:
            same += 1
    report = {"compared": len(names), "identical": same, "different": len(different), "status_counts_a": statuses,
              "only_in_a": only_a, "only_in_b": only_b, "differences": different}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(f"compared {len(names)}, identical {same}, different {len(different)}; statuses in A: {statuses}")
    print("only in A:", only_a[:5], "only in B:", only_b[:5])
    for d in different[:12]:
        print(" ", d["scenario"], d["sections"])


if __name__ == "__main__":
    main(*sys.argv[1:4])
