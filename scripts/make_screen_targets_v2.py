"""Follow-up targets (D19): tasks whose published work is a fixed value, so history never varies it. Reference only."""
import json
import os
import sys

root = os.path.abspath(sys.argv[1])
sys.path.insert(0, os.path.join(root, "scripts"))
import replay_screen as rs
root = rs.setup_paths(root)

targets = []
for doc in rs.DOCS:
    for run in rs.RUNS:
        model, _, base = rs.reference(root, doc, run, {})
        ends = {c["case"]: c["end"] for c in base["cases"]}
        fixed = sorted(t for t, d in model.task_dist.items() if d.name == "fix")
        for task in fixed:
            rows = sorted((t for t in base["tasks"] if t["task"] == task), key=lambda t: (t["enabled"], t["case"], t["visit"]))
            for t in rows:
                change = {"interventions": [{"type": "duration_set", "task": task, "seconds": t["service"] + 600,
                                             "selector": {"case": t["case"], "visit": t["visit"]}}]}
                if rs.moved(root, doc, run, change, ends):
                    targets.append({"doc": doc, "run": run, "name": f"fixed_input_up:{task}", "family": "activity_duration", **change})
                    break
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(targets, f, indent=1)
print(len(targets), "targets", sorted({(t["doc"][9:12], t["name"].split(":")[1][-8:]) for t in targets}))
