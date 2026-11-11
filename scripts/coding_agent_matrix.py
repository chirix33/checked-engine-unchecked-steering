"""The coding-agent build matrix (D27): Haiku 5.5 and Sonnet 5.5, 2 builds per domain, four domains (16 programs).

Builds run one at a time through scripts/coding_agent_build.py (which runs the isolation check before and after each
build). Every build that produced a program is replayed on its domain's dev document (scripts/coding_agent_replay.py)
and listed in runs/coding_agent/index.jsonl, whether or not it replays: no build is selected by result.

Spending: the matrix stops at MATRIX_USD of Claude spend, counting every attempt of every matrix build (build.json
and stopped.json, including attempt_<n>/). Each build gets --max-usd = what is left, so the generator's per-call
guard stops before a call that could pass it. The shared runner stop in b0_build_test is also enforced per call.

Usage: python -X utf8 scripts/coding_agent_matrix.py [--index-only]
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "coding_agent"
MATRIX_USD = 8.0
MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5"]
DOMAINS = ["WorkflowLoan", "WorkflowPharmacy", "Manufacturing", "ITOperations"]
PROCESS = {"WorkflowLoan": "loan", "WorkflowPharmacy": "pharmacy", "Manufacturing": "manufacturing", "ITOperations": "it_ops"}
BUILDS = (1, 2)
PY = [str(ROOT / ".tools" / "b0_env" / "Scripts" / "python.exe"), "-X", "utf8"]


def folder(model, domain, k):
    return OUT / model / domain / f"b{k}"


def build_cost(f: Path) -> float:
    total = 0.0
    for name in ("build.json", "stopped.json"):
        for p in [f / name] + sorted(f.glob(f"attempt_*/{name}")):
            if p.exists():
                total += json.loads(p.read_text(encoding="utf-8")).get("cost", {}).get("usd", 0.0)
    return total


def matrix_spent() -> float:
    return sum(build_cost(folder(m, d, k)) for m in MODELS for d in DOMAINS for k in BUILDS if folder(m, d, k).exists())


def write_index():
    rows = []
    for m in MODELS:
        for d in DOMAINS:
            for k in BUILDS:
                p = folder(m, d, k) / "build.json"
                if not p.exists():
                    continue
                r = json.loads(p.read_text(encoding="utf-8"))
                if r.get("status") == "built" and r.get("wsl_dir"):
                    rows.append({"model": m, "name": f"{d}/b{k}", "process": PROCESS[d], "dir": r["wsl_dir"], "task": d})
    (OUT / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")
    return rows


def main():
    env = {"PYTHONDONTWRITEBYTECODE": "1"}
    import os
    env = {**os.environ, **env}
    log = OUT / "matrix_log.jsonl"
    if "--index-only" in sys.argv:
        print(len(write_index()), "programs indexed")
        return 0
    for m in MODELS:
        for d in DOMAINS:
            for k in BUILDS:
                f = folder(m, d, k)
                if not (f / "build.json").exists():
                    left = MATRIX_USD - matrix_spent()
                    if left <= 0.05:
                        print(f"matrix budget reached: spent {matrix_spent():.3f} of {MATRIX_USD}; stopping before {m}/{d}/b{k}")
                        return 2
                    t0 = time.time()
                    p = subprocess.run(PY + ["scripts/coding_agent_build.py", m, d, str(k), "--max-usd", f"{left:.4f}"],
                                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
                    line = (p.stdout.strip().splitlines() or [""])[-1]
                    print(f"[build] {m}/{d}/b{k} exit {p.returncode}: {line}", flush=True)
                    with log.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "build": f"{m}/{d}/b{k}",
                                             "exit": p.returncode, "seconds": round(time.time() - t0, 1), "stdout": p.stdout[-1500:],
                                             "stderr": p.stderr[-1500:], "matrix_spent": round(matrix_spent(), 4)}) + "\n")
                    if p.returncode == 2 or not (f / "build.json").exists():
                        stop = f / "stopped.json"
                        detail = json.loads(stop.read_text(encoding="utf-8")).get("status") if stop.exists() else p.stderr[-300:]
                        print(f"build stopped ({detail}); matrix stops here, spent {matrix_spent():.3f}")
                        return 2
                rec = json.loads((f / "build.json").read_text(encoding="utf-8"))
                if rec.get("status") == "built" and not (f / "replay_dev.json").exists():
                    p = subprocess.run(PY + ["scripts/coding_agent_replay.py", m, d, str(k)], cwd=ROOT, capture_output=True,
                                       text=True, encoding="utf-8", errors="replace", env=env)
                    print("[replay] " + (p.stdout.strip().replace("\n", "\n[replay] ") or p.stderr[-800:]), flush=True)
                    if p.returncode != 0:
                        (f / "replay_error.txt").write_text(p.stdout[-2000:] + p.stderr[-3000:], encoding="utf-8")
                write_index()
    rows = write_index()
    print(f"matrix done: {len(rows)} programs indexed, spent {matrix_spent():.3f} of {MATRIX_USD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
