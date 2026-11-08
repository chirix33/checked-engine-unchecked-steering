"""Generate randomized scenario inputs for comparing the two implementations. Inputs only.

Times are biased toward working-window edges and values toward boundaries, where implementations are most
likely to differ. A small share of scenarios is deliberately invalid or conflicting, to compare error handling.

Usage: python -I scripts/make_fuzz_scenarios.py <project_root> <out_dir> <count> <seed>
"""
import json
import os
import random
import sys

SYN = "data/zenodo_10435849/inputs/synthetic/"
MODELS = {
    "mini": ("spec/mini/mini.bpmn", "spec/mini/mini.json"),
    "loan": (SYN + "Loan_Application_3_timers.bpmn", SYN + "Loan_Application_3_timers.json"),
    "pharmacy": (SYN + "Pharmacy_3_timers.bpmn", SYN + "Pharmacy_3_timers.json"),
}
DAY = 86400


def facts(root, name):
    p = json.load(open(os.path.join(root, MODELS[name][1]), encoding="utf-8"))
    return {
        "tasks": [t["task_id"] for t in p["task_resource_distribution"]],
        "timers": [e["event_id"] for e in p["event_distribution"]],
        "gateways": {g["gateway_id"]: [x["path_id"] for x in g["probabilities"]]
                     for g in p["gateway_branching_probabilities"] if len(g["probabilities"]) >= 2},
        "pools": {r["name"]: int(r["amount"]) for prof in p["resource_profiles"] for r in prof["resource_list"]},
        "open": int(p["arrival_time_calendar"][0]["beginTime"][:2]) * 3600,
    }


def moment(rng, f):
    day = rng.choice([0, 0, 0, 1, 4])
    base = day * DAY + f["open"]
    return base + rng.choice([0, 300, 900, 1800, 3600, 7200, 8 * 3600, rng.randrange(0, 12 * 3600)])


def selector(rng, f, cases):
    s = {}
    if rng.random() < 0.3:
        s["case"] = rng.choice(cases)
    if rng.random() < 0.2:
        s["visit"] = rng.choice([1, 1, 2])
    if rng.random() < 0.5:
        s["from"] = moment(rng, f)
        if rng.random() < 0.5:
            s["to"] = s["from"] + rng.choice([1, 600, 3600, 3 * DAY])
    return s


def distribution(rng):
    kind = rng.choice(["fix", "expon", "norm"])
    if kind == "fix":
        return "fix", [rng.choice([0, 1, 60, 600, 5400])]
    if kind == "expon":
        lo = rng.choice([0, 60, 600])
        return "expon", [lo + rng.choice([30, 300, 1800]), lo, lo + rng.choice([600, 3600, 7200])]
    return "norm", [rng.choice([120, 600, 1800]), rng.choice([10, 60, 300]), 0, rng.choice([3600, 7200])]


def intervention(rng, f, cases, used):
    kind = rng.choice(["resource_unavailable", "resource_add", "duration_set", "duration_scale", "duration_distribution",
                       "timer_set", "timer_scale", "timer_distribution", "routing_set", "routing_set", "case_add",
                       "case_remove"])
    if kind == "resource_unavailable":
        pool = rng.choice(sorted(f["pools"]))
        lo = moment(rng, f)
        iv = {"type": kind, "pool": pool, "from": lo, "to": lo + rng.choice([1, 600, 3600, DAY, 3 * DAY])}
        if rng.random() < 0.8:
            iv["count"] = rng.randint(1, f["pools"][pool])
        else:
            iv["instances"] = [f"{pool}_{rng.randrange(f['pools'][pool])}"]
        return iv
    if kind == "resource_add":
        return {"type": kind, "pool": rng.choice(sorted(f["pools"])), "count": rng.randint(1, 3), "from": moment(rng, f)}
    if kind.startswith("duration") or kind.startswith("timer"):
        family, op = kind.split("_")
        field = "task" if family == "duration" else "timer"
        iv = {"type": kind, field: rng.choice(f["tasks"] if family == "duration" else f["timers"]),
              "selector": selector(rng, f, cases)}
        if op == "set":
            iv["seconds"] = rng.choice([0, 1, 60, 3600, 40000])
        elif op == "scale":
            iv["factor"] = rng.choice(["0", "0.5", "0.333", "1", "1.25", "2.5", "10"])
        else:
            iv["distribution_name"], iv["distribution_params"] = distribution(rng)
        return iv
    if kind == "routing_set":
        gateway = rng.choice(sorted(f["gateways"]))
        flows = f["gateways"][gateway]
        p = rng.choice(["0", "0.01", "0.2", "0.5", "0.77", "0.99"])
        rest = str(1 - float(p)) if p in ("0", "0.5") else {"0.01": "0.99", "0.2": "0.8", "0.77": "0.23", "0.99": "0.01"}[p]
        probabilities = {flows[0]: p, flows[1]: rest}
        for extra in flows[2:]:
            probabilities[extra] = "0"
        return {"type": kind, "gateway": gateway, "probabilities": probabilities, "selector": selector(rng, f, cases)}
    if kind == "case_add":
        used["added"] += 1
        return {"type": kind, "case": f"x{used['added']}", "arrival": moment(rng, f)}
    return {"type": kind, "case": rng.choice(cases)}


def broken(rng, f, cases):
    return rng.choice([
        {"type": "resource_add", "pool": "No such pool", "count": 1, "from": 0},
        {"type": "resource_unavailable", "pool": sorted(f["pools"])[0], "count": 0, "from": 0, "to": 10},
        {"type": "resource_unavailable", "pool": sorted(f["pools"])[0], "count": 1, "from": 10, "to": 10},
        {"type": "duration_scale", "task": f["tasks"][0], "factor": "-1"},
        {"type": "duration_scale", "task": f["tasks"][0], "factor": 2},
        {"type": "timer_set", "timer": "missing", "seconds": 1},
        {"type": "case_remove", "case": "c9999"},
        {"type": "case_add", "case": cases[0], "arrival": 0},
        {"type": "unknown_type"},
    ])


def scenario(rng, root, index, all_facts, out_dir):
    name = rng.choice(["mini", "loan", "loan", "pharmacy", "pharmacy"])
    f = all_facts[name]
    n = rng.choice([3, 8, 20, 40]) if name == "mini" else rng.choice([5, 20, 40, 80])
    cases = ["c%04d" % k for k in range(n)]
    used = {"added": 0}
    roll = rng.random()
    if roll < 0.06:
        ivs = [broken(rng, f, cases)]
    elif roll < 0.10:
        # A loop-back route with probability 1 can exceed the visit limit, and two rules can conflict.
        gateway = rng.choice(sorted(f["gateways"]))
        flows = f["gateways"][gateway]
        ivs = [{"type": "routing_set", "gateway": gateway, "probabilities": {flows[0]: "1", **{x: "0" for x in flows[1:]}}}]
        if rng.random() < 0.5:
            ivs.append(dict(ivs[0]))
    else:
        ivs = [intervention(rng, f, cases, used) for _ in range(rng.choice([0, 1, 1, 1, 2, 3]))]
    bpmn, params = MODELS[name]
    rel = os.path.relpath(root, out_dir).replace("\\", "/")
    return {
        "schema": "wf-scenario/1", "scenario_id": f"F{index:04d}_{name}",
        "model": {"bpmn": f"{rel}/{bpmn}", "params": f"{rel}/{params}"},
        "seed": f"fuzz-{rng.randrange(10 ** 6)}", "n_cases": n, "interventions": ivs,
    }


def main(root, out_dir, count, seed):
    rng = random.Random(int(seed))
    os.makedirs(out_dir, exist_ok=True)
    all_facts = {name: facts(root, name) for name in MODELS}
    for i in range(int(count)):
        s = scenario(rng, root, i, all_facts, out_dir)
        with open(os.path.join(out_dir, s["scenario_id"] + ".json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(s, fh, indent=1)
    print(count, "scenarios written to", out_dir)


if __name__ == "__main__":
    main(*sys.argv[1:5])
