"""Soundness check of the record-comparison route-probability probe (`ProbeRunner.route_change`), run offline
against the reference engine (evaluation-only).

The reference's own output under changed route probabilities is fed to the probe as if a program had produced it,
in OTF's free-form record shape (time, kind text, entity list; no decision events), which is the shape the policy
uses this probe for. A structured-event shape is checked as well. A sound probe never rejects the reference.

Changes tried per run and decision: all probability on each single route, the stated probabilities reversed, equal
shares, and every routing_probability change in the pilot questions. Changes the reference cannot run (a loop with
probability 1) are skipped and counted.

Usage: python -X utf8 validation/probe_soundness_route_records.py   (needs the environment with reportlab)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "reference_engine"), str(ROOT / "validation")]
sys.dont_write_bytecode = True

import engine                                                    # noqa: E402
import render_workflow_doc as render                             # noqa: E402
import replay_screen as rs                                       # noqa: E402
from assurance import probes                                     # noqa: E402
from assurance.backends import Execution                         # noqa: E402
from assurance.request import Intervention, schema_from_map      # noqa: E402
from probe_soundness_route_rule import changes                   # noqa: E402


class Skip(Exception):
    pass


class Reference:
    name = "devs_gen"       # the generic input path (stdin_from_map, apply, run_input); the record shape is set by `shape`
    adapter_version = "reference-as-program"

    def __init__(self, doc, labels, inv, shape):
        self.doc, self.labels, self.inv, self.shape = doc, labels, inv, shape

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
        except engine.RunError as e:
            raise Skip(str(e))
        if out.get("status") != "ok":
            return Execution("crashed", detail=str(out.get("error")))
        lab = self.labels.label
        if self.shape == "free":
            recs = [{"time": float(c["end"]), "kind": "case finished", "entities": [c["case"]], "value": None} for c in out["cases"]]
            for t in out["tasks"]:
                recs.append({"time": float(t["start"]), "kind": f"task started: {lab[t['task']]}", "entities": [t["case"], t["resource"]], "value": None})
                recs.append({"time": float(t["end"]), "kind": f"task finished: {lab[t['task']]}", "entities": [t["case"], t["resource"]], "value": None})
            for w in out["timers"]:
                recs.append({"time": float(w["start"]), "kind": "wait", "entities": [w["case"], lab[w["timer"]]], "value": float(w["delay"])})
            for b in out["branches"]:
                recs.append({"time": float(b["time"]), "kind": f"route {self.labels.routes(b['gateway'])[b['flow']]}",
                             "entities": [b["case"], lab[b["gateway"]]], "value": None})
        else:
            recs = [{"event": "case_end", "case": c["case"], "time": float(c["end"])} for c in out["cases"]]
            for t in out["tasks"]:
                recs.append({"event": "task_start", "case": t["case"], "name": lab[t["task"]], "visit": t["visit"], "time": float(t["start"]), "worker": t["resource"]})
                recs.append({"event": "task_end", "case": t["case"], "name": lab[t["task"]], "visit": t["visit"], "time": float(t["end"]), "worker": t["resource"]})
            for b in out["branches"]:
                recs.append({"event": "decision", "case": b["case"], "name": lab[b["gateway"]], "visit": b["visit"],
                             "time": float(b["time"]), "route": self.labels.routes(b["gateway"])[b["flow"]]})
        return Execution("ran", case_ends={c["case"]: float(c["end"]) for c in out["cases"]}, records=recs)


def main():
    qs = json.loads((ROOT / "manifests" / "pilot_questions_v1.json").read_text(encoding="utf-8"))
    bad, counts = [], {"free": [0, 0, 0], "events": [0, 0, 0]}       # tested, not run, skipped
    for doc in ("workflow_loan_dev", "workflow_pharmacy_dev"):
        nav = json.loads((ROOT / f"runs/build_test_r1_claude/claude-sonnet-5-5/{doc}/b2/navmap.json").read_text(encoding="utf-8"))
        schema = schema_from_map(nav)
        bpmn, params = rs.model_files(str(ROOT), doc)
        model = engine.Model(bpmn, params)
        labels = render.Labels(model, bpmn)
        inv = {v: k for k, v in labels.label.items()}
        stated = probes.stated_probabilities(schema)
        tried = []
        for scope in schema.scopes:
            for dec, probs in sorted(stated.items()):
                tried += [(scope, dec, ch, "generated") for ch in changes(probs)]
        tried += [(q["scope"], q["binding"]["target"], q["binding"]["routes"], q["id"])
                  for q in qs if q["doc"] == doc and q["family"] == "routing_probability"]
        for shape in ("free", "events"):
            b = Reference(doc, labels, inv, shape)
            for scope, dec, ch, src in tried:
                runner = probes.ProbeRunner(b, nav, schema)
                try:
                    ok, why = runner.route_change(scope, Intervention("routing_probability", "set", target=dec, routes=ch))
                except Skip:
                    counts[shape][2] += 1
                    continue
                if ok is None:
                    counts[shape][1] += 1
                    continue
                counts[shape][0] += 1
                if not ok:
                    bad.append((shape, doc, scope, dec, ch, src, why))
        print(f"{doc}: {len(tried)} changes per record shape")
    for x in bad[:10]:
        print("  REJECTED", x)
    for shape, (n, none, skip) in counts.items():
        print(f"{shape:6}: {n} tested, {none} not run, {skip} the reference cannot run")
    print(f"{len(bad)} rejections of the reference")
    return len(bad)


if __name__ == "__main__":
    sys.exit(main())
