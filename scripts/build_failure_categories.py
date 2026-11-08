"""Count build failures by type, per attempt and per failed build, from saved programs and build logs.

Mechanical: the model broke the code contract (syntax, record format, crash, reading what it did not declare).
Logic: the code ran and met the contract, but forecast the process poorly.

Usage: python -X utf8 -I scripts/build_failure_categories.py <builds_dir> <out_json>
"""
import collections
import glob
import json
import os
import re
import sys

RULES = [
    ("syntax_or_rejected", r"does not run: rejected|syntax error|rejected:"),
    ("bad_location_format", r"bad src"),
    ("reads_undeclared_cells", r"reads differently once the outcomes are hidden|fails on the copy in which"),
    ("outcomes_found_after_hiding", r"still finds them"),
    ("unknown_entity_ids", r"not ids from entities"),
    ("time_out_of_range", r"outside|recorded period"),
    ("timeout", r"timeout after"),
    ("runtime_crash", r"Traceback|failed: |Error:|Error\b"),
    ("low_forecast_f1", r"mean record-match F1|need 0\.4"),
    ("not_sensitive_to_inputs", r"sensitiv|does not react"),
    ("no_reply_or_empty_code", r"^$"),
]


def classify(text):
    for name, pattern in RULES:
        if re.search(pattern, text or ""):
            return name
    return "other"


def main(base, out_path):
    attempts = collections.Counter()
    final = collections.Counter()
    by_build = {}
    for path in sorted(glob.glob(os.path.join(base, "*", "*", "b*", "program.json"))):
        parts = os.path.normpath(path).split(os.sep)
        setup, doc, build = parts[-4], parts[-3], parts[-2]
        program = json.load(open(path, encoding="utf-8"))
        rows = []
        for a in program.get("attempts", []):
            report = a.get("report") or {}
            if a.get("step") in ("explore", "syntax_repair"):
                kind = "not_a_check"                       # review fix: these steps have no check report
            elif report.get("passed"):
                kind = "passed"
            elif report.get("error"):
                kind = classify(report["error"])
            else:
                kind = "not_sensitive_to_inputs" if report.get("mean_f1", 0) >= 0.4 else "low_forecast_f1"
            rows.append((a.get("step"), kind))
            attempts[(setup, a.get("step"), kind)] += 1
        last = next((k for s, k in reversed(rows) if k != "passed"), None)
        result = "accepted" if program.get("passed") else f"{program.get('failed_step')}:{last}"
        final[(setup, doc, result)] += 1
        by_build[f"{setup}/{doc}/{build}"] = {"result": result, "attempts": rows}
    print("Final state of each build")
    for key, n in sorted(final.items()):
        print(f"  {n}  {key[0]:20}{key[1]:20}{key[2]}")
    print("\nAll attempts")
    for key, n in sorted(attempts.items()):
        print(f"  {n:3}  {key[0]:20}{str(key[1]):10}{key[2]}")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"by_build": by_build, "final": {" | ".join(k): v for k, v in final.items()},
                   "attempts": {" | ".join(map(str, k)): v for k, v in attempts.items()}}, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
