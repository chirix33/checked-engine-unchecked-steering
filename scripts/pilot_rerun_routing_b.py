"""Pilot v1b: the development pilot re-decided with the record-comparison route-probability probe (form (b)).

Evaluation side. Ashraf chose form (b) on 2026-11-07, after the v1 pilot showed the rule probe could never run on
OTF's free-form records. What changes from v1 is only the `directed` decision on routing_probability questions, for
every program that has gates (OTF R1 and DEVS-Gen; B0 is native-only):
- programs whose records name no decisions (OTF) now run `ProbeRunner.route_change`;
- programs that record decisions (DEVS-Gen) keep the rule probe, re-decided only so that no evidence from excluded
  questions reaches them;
- route-probability passes are no longer reused across requests (review 4).
Every other row, decision and answer is copied from v1 unchanged.

The 8 questions that fail the deterministic-realization rule (`manifests/pilot_excluded_v1.json`) are dropped
before anything is decided. Directed evidence is keyed by family, so a fresh registry holding only routing_probability
evidence gives the same evidence order as v1 for this family (v1 order, per program and request source).

Variants: default `check` runs the no-switch check (a change that switches no recorded decision must leave the
records unchanged); `nocheck` reports such changes as not run, as first designed.

Output: runs/pilot_v1b/ or runs/pilot_v1b_nocheck/ (same layout as runs/pilot_v1/).
Usage: python -X utf8 scripts/pilot_rerun_routing_b.py <project_root> [check|nocheck]
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
sys.dont_write_bytecode = True

import pilot_runner as pr                                        # noqa: E402

SRC = ROOT / "runs" / "pilot_v1"


def main(root: Path, variant: str = "check"):
    assert variant in ("check", "nocheck"), variant
    DST = ROOT / "runs" / ("pilot_v1b" if variant == "check" else "pilot_v1b_nocheck")
    from assurance import policy
    from assurance.backends import DEVSBackend, OTFBackend
    from assurance.registry import Registry
    from assurance.request import schema_from_map
    excluded = set(json.loads((root / "manifests" / "pilot_excluded_v1.json").read_text(encoding="utf-8")))
    qs = {q["id"]: q for q in json.loads(pr.QUESTIONS.read_text(encoding="utf-8"))}
    interp = {json.loads(l)["key"]: json.loads(l) for l in (SRC / "interpret.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    (DST / "programs").mkdir(parents=True, exist_ok=True)
    (DST / "registries").mkdir(parents=True, exist_ok=True)
    for k in ("interpret", "vanilla", "rag"):
        shutil.copyfile(SRC / f"{k}.jsonl", DST / f"{k}.jsonl")
    progs = {p["name"]: p for p in pr.programs_list(root)}
    changed = 0
    for f in sorted((SRC / "programs").glob("*.jsonl")):
        rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows = [r for r in rows if r.get("question") not in excluded]
        name = next((r["program"] for r in rows if "program" in r), None)
        prog = progs.get(name)
        redo = prog is not None and not prog["native_only"]
        if redo:
            nav = json.loads(pr.NAV_OF[prog["doc"]].read_text(encoding="utf-8"))
            schema = schema_from_map(nav)
            if prog["backend"] == "otf":
                backend = OTFBackend(Path(prog["path"]), prog["system"], root)
            else:
                backend = DEVSBackend(prog["dir"], prog["task"], root)
            runners = {s: pr.make_runner(backend, nav, schema) for s in ("interpreted", "oracle")}
            for rn in runners.values():
                rn.no_switch_check = variant == "check"
            regs = {s: pr.Deferred(Registry(DST / "registries" / f"{f.stem}_{s}.jsonl")) for s in ("interpreted", "oracle")}
            for p in regs.values():                      # fresh, idempotent reruns
                if p.registry.path.exists():
                    p.registry.path.unlink()
        out = []
        for r in rows:
            q = qs.get(r.get("question"))
            if redo and q is not None and q["family"] == "routing_probability":
                src = r["source"]
                req = pr.request_from(interp[q["id"]]["request"]) if src == "interpreted" else pr.oracle_request(q)
                runner = runners[src]
                start = runner.executions
                try:
                    d = policy.decide("directed", req, schema, runner, regs[src], backend, budget=pr.BUDGET)
                except Exception as e:
                    d = policy.Decision(False, f"policy error {type(e).__name__}: {e}"[:300])
                r = {**r, "decisions": {**r["decisions"], "directed": {
                    "permit": d.permit, "reason": d.reason[:300], "probes_run": d.probes_run,
                    "executions": runner.executions - start, "untested": d.untested, "inexpressible": d.inexpressible,
                    "evidence": d.evidence, "form_b": True}}}
                regs[src].commit()
                changed += 1
                print(name, r["key"], d.permit, d.reason[:100], flush=True)
            out.append(r)
        tmp = DST / "programs" / (f.name + ".tmp")
        tmp.write_text("".join(json.dumps(x, default=str) + "\n" for x in out), encoding="utf-8")
        tmp.replace(DST / "programs" / f.name)
    print(f"{changed} directed decisions re-decided")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), sys.argv[2] if len(sys.argv) > 2 else "check")
