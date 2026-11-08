"""Survey the DEVS-Gen release for the separate screen column (D17): native passes, and which settings can change."""
import collections
import csv
import json
import os
import sys

root = sys.argv[1]
rows = list(csv.DictReader(open(os.path.join(root, "results", "task_results.csv"), encoding="utf-8")))
gen = [r for r in rows if r["method"] == "devs_gen"]


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


perfect = collections.Counter()
for r in gen:
    if r["fully_operational"] in ("1", "1.0", "True") and (f(r["score_beh"]) or 0) >= 0.999:
        perfect[(r["scenario"], r["model"])] += 1
print("native perfect, by scenario and model:", sorted(perfect.items()))
print("total perfect", sum(perfect.values()), "of", len(gen))
by_s = collections.Counter(k[0] for k, v in perfect.items() for _ in range(v))
print("by scenario", dict(by_s))
for s in sorted(os.listdir(os.path.join(root, "benchmark"))):
    m = json.load(open(os.path.join(root, "benchmark", s, "manifest.json"), encoding="utf-8"))
    cases = m["test_cases"]
    sim = collections.Counter(k for c in cases for k in (c.get("sim_args") or {}))
    chk = collections.Counter(k for c in cases for k in (c.get("checker_config") or {}))
    norm = lambda k: k.lstrip("-").replace("-", "_")
    both = sorted({norm(k) for k in sim} & {norm(k) for k in chk})
    stdin = sum(1 for c in cases if c.get("sim_stdin") not in (None, "", "\n") or c.get("sim_stdin_file"))
    keys = sorted({k for c in cases for k in c})
    print(f"\n{s}: {len(cases)} cases, stdin cases {stdin}, shared numeric candidates {both}")
    print("  sim_args", dict(sim))
    print("  checker_config", dict(list(chk.items())[:12]))
    print("  case fields", keys)
    print("  sample", json.dumps({k: cases[0].get(k) for k in ("sim_args", "checker_config")})[:300])
