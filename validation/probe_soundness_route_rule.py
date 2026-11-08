"""Soundness check of the routing-probability rule probe, run offline against the reference engine (evaluation-only).

For every document, run and decision with stated routes, the reference's own output under changed route
probabilities is fed to `ProbeRunner.route_rule` as if a program had produced it. A sound probe never rejects it.
Changes tried per decision: all probability on each single route, the stated probabilities reversed, and equal shares.

Usage: python -X utf8 validation/probe_soundness_route_rule.py   (needs the environment with reportlab)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "reference_engine")]
sys.dont_write_bytecode = True

import engine                                                    # noqa: E402
import render_workflow_doc as render                             # noqa: E402
import replay_screen as rs                                       # noqa: E402
from assurance import probes                                     # noqa: E402
from assurance.backends import Execution                         # noqa: E402
from assurance.request import Intervention, schema_from_map      # noqa: E402


SKIPS = []


class Skip(Exception):
    pass


class Reference:
    name = "devs_gen"
    adapter_version = "reference-as-program"

    def __init__(self, doc, labels, inv):
        self.doc, self.labels, self.inv = doc, labels, inv

    def program_hash(self):
        return "reference"

    @staticmethod
    def stdin_from_map(nav, scope):
        return {"scope": scope, "interventions": []}

    def apply(self, data, iv, schema):
        gw = self.inv[iv.target]
        flow_of = {lab: f for f, lab in self.labels.routes(gw).items()}
        probs = {flow_of[r]: probes._fixed(p) for r, p in iv.routes.items()}
        return {**data, "interventions": [{"type": "routing_set", "gateway": gw, "probabilities": probs}]}

    def run_input(self, data):
        try:
            _, _, out = rs.reference(str(ROOT), self.doc, data["scope"], {"interventions": data["interventions"]})
        except engine.RunError as e:          # e.g. all probability on a loop-back route: no valid reference run
            SKIPS.append(str(e)); raise Skip(str(e))
        if out.get("status") != "ok":
            return Execution("crashed", detail=str(out.get("error")))
        recs = [{"event": "case_end", "case": c["case"], "time": float(c["end"])} for c in out["cases"]]
        for b in out["branches"]:
            recs.append({"event": "decision", "case": b["case"], "name": self.labels.label[b["gateway"]], "visit": b["visit"],
                         "time": float(b["time"]), "route": self.labels.routes(b["gateway"])[b["flow"]]})
        return Execution("ran", case_ends={c["case"]: float(c["end"]) for c in out["cases"]}, records=recs)


def changes(stated: dict):
    routes = sorted(stated)
    out = []
    for r in routes:
        out.append({x: (1.0 if x == r else 0.0) for x in routes})
    vals = [stated[r] for r in routes]
    out.append(dict(zip(routes, reversed(vals))))
    n = len(routes)
    eq = [round(1 / n, 6)] * n
    eq[-1] = round(1 - sum(eq[:-1]), 6)
    out.append(dict(zip(routes, eq)))
    return out


def main():
    total, bad, untested, skipped = 0, [], 0, 0
    for doc in ("workflow_loan_dev", "workflow_pharmacy_dev"):
        nav = json.loads((ROOT / f"runs/build_test_r1_claude/claude-sonnet-5-5/{doc}/b2/navmap.json").read_text(encoding="utf-8"))
        schema = schema_from_map(nav)
        bpmn, params = rs.model_files(str(ROOT), doc)
        model = engine.Model(bpmn, params)
        labels = render.Labels(model, bpmn)
        inv = {v: k for k, v in labels.label.items()}
        b = Reference(doc, labels, inv)
        stated = probes.stated_probabilities(schema)
        for scope in schema.scopes:
            for dec, probs in sorted(stated.items()):
                for ch in changes(probs):
                    runner = probes.ProbeRunner(b, nav, schema)
                    try:
                        ok, why = runner.route_rule(scope, Intervention("routing_probability", "set", target=dec, routes=ch))
                    except Skip:
                        skipped += 1
                        continue
                    total += 1
                    if ok is None:
                        untested += 1
                    elif not ok:
                        bad.append((doc, scope, dec, ch, why))
        print(f"{doc}: decisions {sorted(stated)}")
    for x in bad[:10]:
        print("  REJECTED", x)
    print(f"\n{total} cases, {len(bad)} rejections of the reference, {untested} not run, {skipped} changes the reference cannot run")
    print("skip reasons:", {r: SKIPS.count(r) for r in set(SKIPS)})
    return len(bad)


if __name__ == "__main__":
    sys.exit(main())
