"""Write the validation scenario inputs to spec/scenarios. Inputs only: no expected outputs.

H* scenarios use the small model in spec/mini. P* scenarios use the published Zenodo models and exercise
every intervention type on real process structures. Only standard-library imports; no engine involved.

Usage: python -I scripts/make_validation_scenarios.py <project_root>
"""
import json
import os
import sys

MINI = {"bpmn": "../mini/mini.bpmn", "params": "../mini/mini.json"}
BASE_OVERRIDES = [
    ("c0000", "G", 1, "branch", "0.1"), ("c0000", "G", 2, "branch", "0.9"),
    ("c0001", "G", 1, "branch", "0.4"), ("c0001", "G", 2, "branch", "0.8"),
    ("c0002", "G", 1, "branch", "0.9"),
]
FRI_1650, FRI_1655 = 406200, 406500


def overrides(rows):
    return [{"case": c, "element": e, "visit": v, "variable": x, "u": u} for c, e, v, x, u in rows]


def mini(sid, interventions=(), n=3, extra=(), base=True):
    rows = (BASE_OVERRIDES if base else []) + list(extra)
    return {
        "schema": "wf-scenario/1", "scenario_id": sid, "model": MINI, "seed": "hand", "n_cases": n,
        "draw_overrides": overrides(rows), "interventions": list(interventions),
    }


def hand_scenarios():
    half = {"f_rework": "0.5", "f_ok": "0.5"}
    return [
        mini("H01_factual_contention_ties_loop"),
        mini("H02_unavailable_pauses_running_task",
             [{"type": "resource_unavailable", "pool": "Officer", "count": 1, "from": 34000, "to": 34600}]),
        mini("H03_unavailable_count_uses_highest_index",
             [{"type": "resource_unavailable", "pool": "Clerk", "count": 1, "from": 32000, "to": 33500}]),
        mini("H04_resource_add", [{"type": "resource_add", "pool": "Officer", "count": 1, "from": 33700}]),
        mini("H05_duration_scale_interval_bounds",
             [{"type": "duration_scale", "task": "T_review", "factor": "1.5", "selector": {"from": 33000, "to": 33300}}]),
        mini("H06_duration_set_zero",
             [{"type": "duration_set", "task": "T_decide", "seconds": 0, "selector": {"case": "c0001", "visit": 1}}]),
        mini("H07_duration_distribution_keeps_draw", [
            {"type": "duration_distribution", "task": "T_decide", "distribution_name": "expon",
             "distribution_params": [1300, 1200, 2400], "selector": {"case": "c0001"}},
            {"type": "duration_distribution", "task": "T_notify", "distribution_name": "norm",
             "distribution_params": [300, 30, 0, 600], "selector": {"case": "c0002"}},
        ], extra=[("c0001", "T_decide", 1, "service", "0.5"), ("c0002", "T_notify", 1, "service", "0.8413447")]),
        mini("H08_timer_scale_interval",
             [{"type": "timer_scale", "timer": "W", "factor": "2", "selector": {"from": 33500}}]),
        mini("H09_timer_set_zero_simultaneous",
             [{"type": "timer_set", "timer": "W", "seconds": 0, "selector": {"case": "c0002"}}]),
        mini("H10_routing_keeps_draw", [{"type": "routing_set", "gateway": "G", "probabilities": half}]),
        mini("H11_routing_from_is_inclusive",
             [{"type": "routing_set", "gateway": "G", "probabilities": half, "selector": {"from": 33300}}]),
        mini("H12_routing_no_effect_after_boundary",
             [{"type": "routing_set", "gateway": "G", "probabilities": half, "selector": {"from": 33301}}]),
        mini("H13_routing_no_effect_threshold",
             [{"type": "routing_set", "gateway": "G", "probabilities": {"f_rework": "0.3", "f_ok": "0.7"}}]),
        mini("H14_resource_no_effect_off_hours",
             [{"type": "resource_unavailable", "pool": "Officer", "count": 1, "from": 61200, "to": 64800}]),
        mini("H15_case_add_calendar_edges",
             [{"type": "case_add", "case": "x1", "arrival": FRI_1650}, {"type": "case_add", "case": "x2", "arrival": FRI_1655}],
             n=1, base=False,
             extra=[("c0000", "G", 1, "branch", "0.9"), ("x1", "G", 1, "branch", "0.9"), ("x2", "G", 1, "branch", "0.9")]),
        mini("H16_case_remove_preserves_others", [{"type": "case_remove", "case": "c0000"}]),
        # Added after mutation testing showed these two rules were barely exercised. See run_manifest.md.
        mini("H17_tie_order_uses_arrival_before_case_id", [{"type": "case_add", "case": "a1", "arrival": 33000}],
             extra=[("a1", "G", 1, "branch", "0.9")]),
        mini("H18_scale_rounds_half_up_exactly", [{"type": "duration_scale", "task": "T_notify", "factor": "1.015"}]),
    ]


def process_scenarios():
    """Loan and Pharmacy, primary 3-timer versions, one scenario per intervention type and seed."""
    loan = {
        "file": "Loan_Application_3_timers", "n": 60, "pool": "Appraiser",
        "task": "sid-9F775FDB-CD87-40D7-8B8D-DFD50176CE88",  # Appraise property
        "timer": "Event_1g228xj",  # Before Assess loan risk
        "loop_timer": "Event_19s1gwa",  # In the form-return loop
        "gateway": "Gateway_0eqakhv",  # Offer needs refinement
        "flows": ["Flow_0mpn0oz", "Flow_1ltuf1s"],
        "window": [32400 + 3600, 32400 + 3 * 3600], "new_arrival": 32400 + 1000,
    }
    pharmacy = {
        "file": "Pharmacy_3_timers", "n": 120, "pool": "Technician",
        "task": "sid-18F562AE-0F3A-489F-8660-38E177904BB0",  # Check for Quality Assurance
        "timer": "Event_1hrnfk3",  # Before Pack the drugs
        "loop_timer": "Event_1hrnfk3",
        "gateway": "sid-FEC69A74-A114-4118-8057-2CC467F9BC26",  # Bag filled correctly or not
        "flows": ["sid-5557ED54-1A2C-4EC2-8F49-48C111186F71", "sid-61D66A8C-4729-4335-A5B8-F02BD7FEE5E5"],
        "window": [28800 + 600, 28800 + 2 * 3600], "new_arrival": 28800 + 1000,
    }
    out = []
    for key, m in (("loan", loan), ("pharmacy", pharmacy)):
        lo, hi = m["window"]
        cases = {
            "factual": [],
            "unavailable": [{"type": "resource_unavailable", "pool": m["pool"], "count": 1, "from": lo, "to": hi}],
            "resource_add": [{"type": "resource_add", "pool": m["pool"], "count": 1, "from": lo}],
            "duration_set": [{"type": "duration_set", "task": m["task"], "seconds": 900, "selector": {"case": "c0005"}}],
            "duration_scale": [{"type": "duration_scale", "task": m["task"], "factor": "1.25", "selector": {"from": lo, "to": hi}}],
            "duration_dist": [{"type": "duration_distribution", "task": m["task"], "distribution_name": "norm",
                               "distribution_params": [1500, 200, 0, 3600]}],
            "timer_set": [{"type": "timer_set", "timer": m["timer"], "seconds": 0, "selector": {"from": lo}}],
            "timer_scale": [{"type": "timer_scale", "timer": m["loop_timer"], "factor": "0.5"}],
            "timer_dist": [{"type": "timer_distribution", "timer": m["timer"], "distribution_name": "expon",
                            "distribution_params": [1200, 600, 3600]}],
            "routing": [{"type": "routing_set", "gateway": m["gateway"],
                         "probabilities": {m["flows"][0]: "0.4", m["flows"][1]: "0.6"}}],
            "case_add": [{"type": "case_add", "case": "x1", "arrival": m["new_arrival"]}],
            "case_remove": [{"type": "case_remove", "case": "c0003"}],
        }
        for seed in ("trust-a", "trust-b"):
            for name, ivs in cases.items():
                out.append({
                    "schema": "wf-scenario/1", "scenario_id": f"P_{key}_{seed}_{name}",
                    "model": {"bpmn": f"../../data/zenodo_10435849/inputs/synthetic/{m['file']}.bpmn",
                              "params": f"../../data/zenodo_10435849/inputs/synthetic/{m['file']}.json"},
                    "seed": seed, "n_cases": m["n"], "interventions": ivs,
                })
    return out


def main(root):
    out_dir = os.path.join(root, "spec", "scenarios")
    os.makedirs(out_dir, exist_ok=True)
    scenarios = hand_scenarios() + process_scenarios()
    for s in scenarios:
        with open(os.path.join(out_dir, s["scenario_id"] + ".json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(s, f, indent=1)
            f.write("\n")
    print(len(scenarios), "scenarios written")


if __name__ == "__main__":
    main(sys.argv[1])
