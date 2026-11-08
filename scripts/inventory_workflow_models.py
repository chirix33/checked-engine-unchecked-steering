"""Inventory the Zenodo BPS models: topology, resources, calendars, durations, routing, timers, logs.

Usage: python -I scripts/inventory_workflow_models.py <inputs_dir> <out_json>
"""
import collections
import gzip
import csv
import glob
import json
import os
import sys
import xml.etree.ElementTree as ET


def local(tag):
    return tag.split("}")[-1]


def bpmn_summary(path):
    root = ET.parse(path).getroot()
    counts = collections.Counter()
    timers = 0
    process_names = []
    for el in root.iter():
        name = local(el.tag)
        if name == "process":
            process_names.append(el.get("name") or el.get("id"))
        if name in {
            "task", "userTask", "serviceTask", "manualTask", "scriptTask", "sendTask", "receiveTask",
            "exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway",
            "startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent",
            "boundaryEvent", "subProcess", "sequenceFlow", "lane",
        }:
            counts[name] += 1
        if name == "timerEventDefinition":
            timers += 1
    tasks = sum(v for k, v in counts.items() if k.lower().endswith("task"))
    return {
        "tasks": tasks,
        "xor": counts["exclusiveGateway"],
        "and": counts["parallelGateway"],
        "or": counts["inclusiveGateway"],
        "event_gateways": counts["eventBasedGateway"],
        "flows": counts["sequenceFlow"],
        "timers": timers,
        "catch_events": counts["intermediateCatchEvent"],
        "subprocesses": counts["subProcess"],
        "lanes": counts["lane"],
        "cycles": has_cycle(root),
    }


def has_cycle(root):
    edges = collections.defaultdict(list)
    for el in root.iter():
        if local(el.tag) == "sequenceFlow":
            edges[el.get("sourceRef")].append(el.get("targetRef"))
    state = {}
    def visit(n):
        stack = [(n, iter(edges[n]))]
        state[n] = 1
        while stack:
            cur, it = stack[-1]
            for nxt in it:
                s = state.get(nxt)
                if s == 1:
                    return True
                if s is None:
                    state[nxt] = 1
                    stack.append((nxt, iter(edges[nxt])))
                    break
            else:
                state[cur] = 2
                stack.pop()
        return False
    return any(visit(n) for n in list(edges) if n not in state)


def json_summary(path):
    d = json.load(open(path, encoding="utf-8"))
    out = {"top_keys": sorted(d.keys())}
    profiles = d.get("resource_profiles", [])
    pool_sizes, all_res = [], set()
    for p in profiles:
        rl = p.get("resource_list", [])
        pool_sizes.append(sum(int(r.get("amount", 1)) for r in rl))
        all_res |= {r.get("name") for r in rl}
    out["pools"] = len(profiles)
    out["pool_sizes"] = pool_sizes
    out["named_resources"] = len(all_res)
    out["calendars"] = len(d.get("resource_calendars", []))
    dist = collections.Counter()
    for t in d.get("task_resource_distribution", []):
        for r in t.get("resources", []):
            dist[r.get("distribution_name")] += 1
    out["duration_distributions"] = dict(dist)
    out["arrival_distribution"] = (d.get("arrival_time_distribution") or {}).get("distribution_name")
    out["n_gateways_with_probabilities"] = len(d.get("gateway_branching_probabilities", []))
    out["event_distribution_entries"] = len(d.get("event_distribution", []) or [])
    for k in ("case_attributes", "event_attributes", "global_attributes", "branch_rules",
              "prioritisation_rules", "batch_processing", "model_type", "multitask"):
        if k in d:
            v = d[k]
            out[k] = len(v) if hasattr(v, "__len__") else v
    return out


def log_summary(path):
    with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as f:
        r = csv.DictReader(f)
        cols = r.fieldnames
        n = 0
        cases, acts, res = set(), set(), set()
        case_col = next((c for c in cols if c.lower() in ("case_id", "case:concept:name", "caseid", "case id")), cols[0])
        act_col = next((c for c in cols if c.lower() in ("activity", "concept:name", "task")), None)
        res_col = next((c for c in cols if c.lower() in ("resource", "org:resource")), None)
        for row in r:
            n += 1
            cases.add(row[case_col])
            if act_col:
                acts.add(row[act_col])
            if res_col:
                res.add(row[res_col])
    return {"columns": cols, "events": n, "cases": len(cases), "activities": len(acts), "resources": len(res)}


def main(inputs, out):
    res = {}
    for bpmn in sorted(glob.glob(os.path.join(inputs, "*", "*.bpmn"))):
        name = os.path.basename(bpmn)[:-5]
        folder = os.path.basename(os.path.dirname(bpmn))
        entry = {"folder": folder, "bpmn": bpmn_summary(bpmn)}
        jp, lp = bpmn[:-5] + ".json", bpmn[:-5] + ".csv.gz"
        entry["json"] = json_summary(jp) if os.path.exists(jp) else None
        entry["log"] = log_summary(lp) if os.path.exists(lp) else None
        res[name] = entry
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(res, open(out, "w", encoding="utf-8"), indent=1)
    print(f"{'model':34}{'task':>5}{'xor':>4}{'and':>4}{'or':>3}{'tmr':>4}{'cyc':>4} {'pools':>5} {'res':>4} {'cal':>4} {'cases':>6} {'events':>7}  durations")
    for k, v in res.items():
        b, j, l = v["bpmn"], v["json"] or {}, v["log"] or {}
        print(f"{k:34}{b['tasks']:>5}{b['xor']:>4}{b['and']:>4}{b['or']:>3}{b['timers']:>4}{str(b['cycles'])[0]:>4} "
              f"{j.get('pools','-'):>5} {j.get('named_resources','-'):>4} {j.get('calendars','-'):>4} "
              f"{l.get('cases','-'):>6} {l.get('events','-'):>7}  {j.get('duration_distributions','-')}")
    first = next(v for v in res.values() if v["json"] and v["folder"] == "synthetic")
    print("\nsynthetic json keys:", first["json"]["top_keys"])
    print("log columns:", first["log"]["columns"])
    print("arrival:", {k: v["json"]["arrival_distribution"] for k, v in res.items() if v["json"] and k.endswith(("Claims", "Application", "Pharmacy", "Pay", "Credentials", "_W"))})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
