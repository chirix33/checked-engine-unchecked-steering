"""Soundness check of the added-workers probe, run offline against the reference engine.

The reference engine is evaluation-only; it is used here only to check that the probe never rejects a correct
program. For every document, run and pool, the reference's own output with one worker added from time 0 is fed to
the probe as if a program had produced it. A sound probe passes every case.

Usage: python -X utf8 validation/probe_soundness_added_workers.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "reference_engine")]
sys.dont_write_bytecode = True

import replay_screen as rs                                       # noqa: E402
from assurance import probes                                     # noqa: E402
from assurance.backends import Execution                         # noqa: E402
from assurance.request import Intervention, schema_from_map      # noqa: E402


def events(out):
    recs = [{"event": "case_end", "case": c["case"], "time": float(c["end"])} for c in out["cases"]]
    for t in out["tasks"]:
        recs.append({"event": "task_start", "case": t["case"], "task": t["task"], "visit": t["visit"], "time": float(t["start"]), "worker": t["resource"]})
        recs.append({"event": "task_end", "case": t["case"], "task": t["task"], "visit": t["visit"], "time": float(t["end"]), "worker": t["resource"]})
    return recs


class Reference:
    name = "devs_gen"
    adapter_version = "reference-as-program"

    def __init__(self, doc):
        self.doc = doc

    def program_hash(self):
        return "reference"

    @staticmethod
    def stdin_from_map(nav, scope):
        return {"scope": scope, "interventions": []}

    def apply(self, data, iv, schema):
        pool_id = self.pool_ids[iv.target]
        return {**data, "interventions": [{"type": "resource_add", "pool": pool_id, "count": int(iv.value), "from": 0}]}

    def run_input(self, data):
        _, _, out = rs.reference(str(ROOT), self.doc, data["scope"], {"interventions": data["interventions"]})
        ends = {c["case"]: float(c["end"]) for c in out["cases"]}
        return Execution("ran", case_ends=ends, records=events(out))


def main():
    import engine
    total, bad, untested = 0, [], 0
    for doc in ("workflow_loan_dev", "workflow_pharmacy_dev"):
        nav = json.loads((ROOT / f"runs/build_test_r1_claude/claude-sonnet-5-5/{doc}/b2/navmap.json").read_text(encoding="utf-8"))
        schema = schema_from_map(nav)
        bpmn, params = rs.model_files(str(ROOT), doc)
        model = engine.Model(bpmn, params)
        b = Reference(doc)
        b.pool_ids = {k: k for k in model.pools}
        for scope in schema.scopes:
            for pool in schema.pools:
                for added in (1, 2):
                    runner = probes.ProbeRunner(b, nav, schema)
                    ok, why = runner.resource_rule(scope, Intervention("resource_availability", "add_workers", target=pool, value=added))
                    total += 1
                    if ok is None:
                        untested += 1
                    elif not ok:
                        bad.append((doc, scope, pool, added, why))
                    print(f"{doc:22} {scope:7} {pool:18} +{added}  {ok}  {why}")
    print(f"\n{total} cases, {len(bad)} rejections of the reference, {untested} not run")
    return len(bad)


if __name__ == "__main__":
    sys.exit(main())
