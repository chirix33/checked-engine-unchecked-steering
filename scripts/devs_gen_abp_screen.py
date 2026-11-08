"""DEVS-Gen column of the replay screen (D17). Reported apart from the OTF column and never pooled.

The analogue of replay is the program's native pass on its own test inputs. The change scales delay settings that
both the simulator and the checker take, so the checker's own rules still apply. A failure is a rule violation at a
setting the native tests did not use. This cannot catch a wrong value that still satisfies the rules.

Run inside WSL from the pinned release: python devs_gen_abp_screen.py <release_root> <work_dir> <out_json>
"""
import csv
import glob
import json
import os
import shutil
import subprocess
import sys

SCALES = {"delays_x2": 2.0, "delays_x0.5": 0.5, "delays_x3": 3.0}
SCALE_KEYS = ("sender_delay", "receiver_delay")


def scaled_manifest(source, target, factor):
    if os.path.exists(target):
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
    path = os.path.join(target, "manifest.json")
    m = json.load(open(path, encoding="utf-8"))
    for case in m["test_cases"]:
        for section in ("sim_args", "checker_config"):
            for key in SCALE_KEYS:
                if key in case[section]:
                    value = case[section][key] * factor
                    case[section][key] = int(value) if float(value).is_integer() else value
    with open(path, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1)
    return path


def run(python, manifest, program, out_dir, root):
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    env = dict(os.environ, PYTHONPATH=os.path.join(root, "src"))
    p = subprocess.run([python, "-m", "devs_eval.cli", "run-scenario", "--manifest", manifest, "--simulator-directory", program,
                        "--output-directory", out_dir], capture_output=True, text=True, timeout=1200, env=env, cwd=root)
    return p


def read_scores(out_dir, stdout):
    found = {}
    for path in glob.glob(os.path.join(out_dir, "**", "*.json"), recursive=True):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(d, dict):
            for key in ("score_ope", "score_beh", "fully_operational", "operational_score", "behavior_score"):
                if key in d:
                    found[key] = d[key]
            if "case_results" in d and "cases" not in found:
                found["cases"] = d["case_results"]
    return found


def main(root, work, out_path):
    root, work = os.path.abspath(root), os.path.abspath(work)
    os.makedirs(work, exist_ok=True)
    python = os.path.join(root, ".venvs", "devs-gen", "bin", "python")
    rows = list(csv.DictReader(open(os.path.join(root, "results", "task_results.csv"), encoding="utf-8")))
    perfect = [r for r in rows if r["method"] == "devs_gen" and r["scenario"] == "ABP" and r["fully_operational"] in ("1", "1.0", "True")
               and float(r["score_beh"] or 0) >= 0.999]
    print(len(perfect), "native-perfect ABP programs", flush=True)
    results = []
    variants = {"native": os.path.join(root, "benchmark", "ABP", "manifest.json")}
    for name, factor in SCALES.items():
        variants[name] = scaled_manifest(os.path.join(root, "benchmark", "ABP"), os.path.join(work, "benchmark_" + name, "ABP"), factor)
    first = True
    for r in perfect:
        program = os.path.join(root, "generated", "devs_gen", r["model"], "ABP", r["run"])
        entry = {"model": r["model"], "run": r["run"], "reported_ope": r["score_ope"], "reported_beh": r["score_beh"], "variants": {}}
        for name, manifest in variants.items():
            out_dir = os.path.join(work, "out", r["model"], r["run"], name)
            p = run(python, manifest, program, out_dir, root)
            scores = read_scores(out_dir, p.stdout)
            entry["variants"][name] = {"exit": p.returncode, "scores": scores, "stdout_tail": p.stdout[-300:], "stderr_tail": p.stderr[-300:] if p.returncode else ""}
            if first:
                print("sample output files:", sorted(os.path.relpath(x, out_dir) for x in glob.glob(os.path.join(out_dir, "**", "*"), recursive=True))[:12], flush=True)
                print("stdout:", p.stdout[-500:], flush=True)
                first = False
            print(r["model"], r["run"], name, p.returncode, {k: v for k, v in scores.items() if k != "cases"}, flush=True)
        results.append(entry)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:4])
