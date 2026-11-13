"""Compare the run-clustered analysis with the frozen one.

1. Every point estimate must be identical (only interval fields may differ).
2. List every gate-minus-judge difference whose 'interval excludes 0' status changes.

Usage: python -X utf8 acmtrust_paper/sensitivity/compare.py <frozen main_analysis.json> <clustered main_analysis.json> [out.md]
"""
import json
import sys

fz = json.load(open(sys.argv[1], encoding="utf-8"))
cl = json.load(open(sys.argv[2], encoding="utf-8"))
out = sys.argv[3] if len(sys.argv) > 3 else None
CI_KEYS = {"ci95", "defined_share", "share_above_0"}

mism = []


def walk(a, b, path):
    if isinstance(a, dict):
        for k in a:
            if k in CI_KEYS or k.endswith("_ci") or k in ("bootstrap",):
                continue
            if k not in b:
                mism.append((path + "/" + k, "missing"))
                continue
            walk(a[k], b[k], path + "/" + k)
    elif isinstance(a, list):
        if len(a) != len(b):
            mism.append((path, "length"))
            return
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]")
    else:
        if a != b:
            mism.append((path, f"{a} != {b}"))


walk(fz, cl, "")

diffs = []


def excl(ci):
    return ci is not None and (ci[0] > 0 or ci[1] < 0)


def find(a, b, path):
    if isinstance(a, dict):
        if "point" in a and "ci95" in a:
            diffs.append((path, a["point"], a.get("ci95"), b.get("ci95")))
            return
        for k in a:
            if k in b and isinstance(a[k], (dict, list)):
                find(a[k], b[k], path + "/" + k)
    elif isinstance(a, list):
        for i, (x, y) in enumerate(zip(a, b)):
            find(x, y, f"{path}[{i}]")


find(fz, cl, "")
changed = [d for d in diffs if excl(d[2]) != excl(d[3])]
lines = [f"point-estimate mismatches: {len(mism)}"] + [f"  {p}: {m}" for p, m in mism[:20]]
lines.append(f"differences with intervals: {len(diffs)}; significance status changed: {len(changed)}")
lines.append(f"  significant frozen: {sum(excl(d[2]) for d in diffs)}; significant clustered: {sum(excl(d[3]) for d in diffs)}")
for p, pt, a, b in changed:
    lines.append(f"  {p}: point {pt}; frozen {a} -> clustered {b}")
txt = "\n".join(lines)
print(txt)
if out:
    open(out, "w", encoding="utf-8", newline="\n").write(txt + "\n")
