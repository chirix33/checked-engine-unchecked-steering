"""Read the saved outputs of the DEVS-Gen ABP screen and report scores per program and setting."""
import glob
import json
import os
import sys

out_root, out_path = sys.argv[1], sys.argv[2]
sample = json.load(open(os.path.join(out_root, "gpt", "run_01", "native", "scenario_result.json"), encoding="utf-8"))["result"]
print("result keys:", {k: (v if isinstance(v, (int, float, str, bool)) else type(v).__name__) for k, v in sample.items()})
results = []
for path in sorted(glob.glob(os.path.join(out_root, "*", "run_*", "*", "scenario_result.json"))):
    parts = path.split(os.sep)
    model, run, variant = parts[-4], parts[-3], parts[-2]
    res = json.load(open(path, encoding="utf-8"))["result"]
    row = {"model": model, "run": run, "variant": variant}
    row.update({k: v for k, v in res.items() if isinstance(v, (int, float, bool, str))})
    lists = {k: v for k, v in res.items() if isinstance(v, list)}
    failures = []
    for name, items in lists.items():
        for item in items:
            if not isinstance(item, dict):
                continue
            rid = item.get("requirement_id")
            quality = item.get("quality_score")
            per_case = next((v for k, v in item.items() if isinstance(v, dict) and all(isinstance(x, (int, float)) for x in v.values())), None)
            if rid is not None and quality is not None and quality < 0.999:
                failures.append({"section": name, "requirement": rid, "quality": round(quality, 4),
                                 "cases_below_1": {k: round(v, 3) for k, v in (per_case or {}).items() if v < 0.999}})
    row["failures"] = failures
    results.append(row)
scalars = sorted({k for r in results for k in r if k not in ("model", "run", "variant", "failures")})
print("scalar keys:", scalars)
for r in results:
    print(r["model"], r["run"], f"{r['variant']:12}", {k: (round(r[k], 4) if isinstance(r.get(k), float) else r.get(k)) for k in scalars if "score" in k or "operational" in k},
          "fails", [(f["requirement"], f["quality"], list(f["cases_below_1"])[:4]) for f in r["failures"]][:5])
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=1)
