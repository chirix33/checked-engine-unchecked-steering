"""Re-decide a sample of dev pilot rows with the current library (evaluation-only; no model calls).

Used to show that a library change leaves pilot decisions unchanged (2026-11-09: the policy fingerprint no longer
hashes the "Chapters in this document" line). Run once before and once after the change, then compare the two files
with `compare`. Rows are re-decided the way `scripts/pilot_runner.py` does it: the same programs, maps, requests
(stored interpreted requests from `runs/pilot_v1/interpret.jsonl`, and oracle requests from the hidden binding), the
same cached probe runner, budget 3, and one registry per program and source that accumulates in the fixed question
order. Registries are fresh files in <work_dir>, so the pilot's own registries are not touched. OTF programs run
locally with their pinned engine code; nothing calls a model.

Usage: python -X utf8 validation/fingerprint_redecide.py run <out_json> <work_dir> <program-substring> [...]
       python -X utf8 validation/fingerprint_redecide.py compare <before_json> <after_json>
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
sys.dont_write_bytecode = True

CONFIGS = ("replay", "schema", "generic", "directed", "program_wide")


def run(out_path, work, *names):
    import pilot_runner as pr
    pr.setup_paths()
    from assurance import contract, policy
    from assurance.backends import OTFBackend
    from assurance.registry import Registry
    from assurance.request import schema_from_map
    qs = json.loads(pr.QUESTIONS.read_text(encoding="utf-8"))
    excluded = set(json.loads((ROOT / "manifests" / "pilot_excluded_v1.json").read_text(encoding="utf-8")))
    interp = {json.loads(l)["key"]: json.loads(l) for l in (pr.OUT / "interpret.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    progs = [p for p in pr.programs_list(ROOT) if p["backend"] == "otf" and not p["native_only"] and any(n in p["name"] for n in names)]
    if not progs:
        raise SystemExit("no program matches")
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    rows, fps, t0 = [], {}, time.time()
    for prog in progs:
        nav = json.loads(pr.NAV_OF[prog["doc"]].read_text(encoding="utf-8"))
        schema = schema_from_map(nav)
        fps[prog["doc"]] = schema.policy_fingerprint()
        backend = OTFBackend(Path(prog["path"]), prog["system"], ROOT)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", prog["name"])
        runners = {src: pr.make_runner(backend, nav, schema) for src in ("interpreted", "oracle")}
        regs = {}
        for src in ("interpreted", "oracle"):
            p = work / f"{safe}_{src}.jsonl"
            p.unlink(missing_ok=True)
            regs[src] = Registry(p)
        for q in qs:
            if q["doc"] != prog["doc"] or q["id"] in excluded:
                continue
            for src in ("interpreted", "oracle"):
                req = pr.request_from(interp[q["id"]]["request"]) if src == "interpreted" else pr.oracle_request(q)
                c = contract.validate(req, schema)
                dec = {}
                for cfg in CONFIGS:
                    try:
                        d = policy.decide(cfg, req, schema, runners[src], regs[src] if cfg == "directed" else None, backend, budget=pr.BUDGET)
                        dec[cfg] = {"permit": d.permit, "reason": d.reason, "untested": d.untested,
                                    "inexpressible": d.inexpressible, "probes_run": d.probes_run,
                                    "evidence": [[str(x) for x in e] for e in d.evidence]}
                    except Exception as e:  # recorded, as the runner does
                        dec[cfg] = {"error": f"{type(e).__name__}: {e}"[:300]}
                rows.append({"program": prog["name"], "question": q["id"], "source": src, "contract": c.status, "decisions": dec})
        print(prog["name"], len(rows), "rows so far,", round(time.time() - t0), "s", flush=True)
    Path(out_path).write_text(json.dumps({"fingerprints": fps, "programs": [p["name"] for p in progs], "rows": rows}, indent=1),
                              encoding="utf-8")
    print(len(rows), "rows written")


def compare(a_path, b_path):
    a = json.loads(Path(a_path).read_text(encoding="utf-8"))
    b = json.loads(Path(b_path).read_text(encoding="utf-8"))
    key = lambda r: (r["program"], r["question"], r["source"])
    ra, rb = {key(r): r for r in a["rows"]}, {key(r): r for r in b["rows"]}
    diff = [k for k in ra if ra[k] != rb.get(k)] + [k for k in rb if k not in ra]
    n_dec = sum(len(r["decisions"]) for r in a["rows"])
    print("fingerprints before", a["fingerprints"], "after", b["fingerprints"])
    print(f"{len(ra)} rows ({n_dec} decisions) before, {len(rb)} after; {len(diff)} rows differ")
    from collections import Counter
    print("decisions by config and outcome:", dict(Counter((cfg, d.get("permit")) for r in a["rows"] for cfg, d in r["decisions"].items())))
    for k in diff[:10]:
        print("  differs:", k)
    return 1 if diff or not ra else 0


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(*sys.argv[2:])
    elif sys.argv[1] == "compare":
        sys.exit(compare(*sys.argv[2:4]))
    else:
        raise SystemExit(__doc__)
