"""Hand inspection of replay-screen results (D17): what do exact programs report, and what does a case-C failure look like?

Usage: python -X utf8 scripts/inspect_screen_case.py <project_root> <screen_json> <targets_json>
"""
import collections
import json
import os
import sys
import tempfile
from pathlib import Path


def main(root, screen_path, targets_path):
    sys.path.insert(0, os.path.join(os.path.abspath(root), "scripts"))
    import replay_screen as rs
    root = rs.setup_paths(root)
    from otf_r1 import sandbox, toolgen
    screen = json.load(open(screen_path, encoding="utf-8"))
    targets = json.load(open(targets_path, encoding="utf-8"))

    def load(e):
        folder = rs.SYSTEM_FOLDERS[e["system"]]
        d = Path(root, "runs", folder, e["setup"], e["doc"], e["build"])
        return json.load(open(d / "program.json", encoding="utf-8"))["code"], json.loads((d / "navmap.json").read_text())

    def simulate(code, nav, run):
        with tempfile.TemporaryDirectory() as tmp:
            m = Path(tmp) / "m.json"
            m.write_text(json.dumps(nav))
            r = toolgen.read_scope(code, m, run)
            cut = toolgen._cut(r)
            blind = toolgen.blinded_map(nav, m, run, r, cut)
            ok, out = sandbox.run(code, "simulate", blind, [run], {"inputs": r["inputs"], "params": r["params"], "start": cut, "horizon": rs.HORIZON})
            return r, cut, out if ok else []

    print("== what replay-exact programs report")
    for e in screen["programs"]:
        if not e["replay_exact_program"]:
            continue
        code, nav = load(e)
        tables = rs.plan_tables(root, e["doc"], "Run 01", {})
        r, cut, out = simulate(code, rs.changed_map(nav, "Run 01", tables), "Run 01")
        print(e["system"], e["setup"], e["doc"], e["build"], "cut", cut)
        print("  recorded kinds", collections.Counter(x.get("kind") for x in r["outcomes"]).most_common(8), "schedule kinds", sorted(r["schedule_kinds"]))
        print("  inputs kinds", collections.Counter(x.get("kind") for x in r["inputs"]).most_common(8))
        print("  reads", sorted({n["title"].split(": ")[-1] for n in nav["nodes"] if n["title"].startswith("Run 01:")}))
        print("  code lines", code.count("\n"), "| mentions of draw/route:", "draw" in code.lower(), "route" in code.lower())

    print("\n== sample of case-C failures")
    shown = collections.Counter()
    for e in screen["programs"]:
        for run, rec in e["runs"].items():
            for x in rec["changes"]:
                if x["status"] != "ran" or not x.get("case_level_c"):
                    continue
                key = (e["setup"], e["doc"], e["build"], x["family"])
                if shown[key] >= 1 or sum(shown.values()) >= 6:
                    continue
                shown[key] += 1
                target = next(t for t in targets if t["doc"] == e["doc"] and t["run"] == run and t["name"] == x["name"])
                code, nav = load(e)
                changed = rs.changed_map(nav, run, rs.plan_tables(root, e["doc"], run, target))
                r, cut, out = simulate(code, changed, run)
                skip = set(r["schedule_kinds"])
                pred, truth = rs.keys_of(out, cut, skip), rs.keys_of(r["outcomes"], cut, skip)
                case = x["case_level_c"][0]
                missing = sorted(k for k in (truth - pred) if case in k[1])[:5]
                extra = sorted(k for k in (pred - truth) if case in k[1])[:5]
                print(f"{e['system']} {e['setup']} {e['doc'][9:12]} {e['build']} {run} {x['name']}: run f1 {rec['factual'].get('f1')} -> {x['f1']}; "
                      f"case {case}; changed {x['reference_changed_cases']}, exact {x['changed_exact']}")
                print("   change:", json.dumps({k: target[k] for k in ("interventions", "draw_overrides", "flip") if k in target})[:230])
                print("   true not simulated:", missing)
                print("   simulated not true:", extra)


if __name__ == "__main__":
    main(*sys.argv[1:4])
