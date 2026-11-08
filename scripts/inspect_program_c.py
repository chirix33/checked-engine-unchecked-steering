"""Hand inspection of program-level case C (D17): diff the failing records, then find the cause in the program's code.

Usage: python -X utf8 scripts/inspect_program_c.py <project_root> <screen_json> <targets_json>
"""
import collections
import json
import os
import re
import sys
import tempfile
from pathlib import Path


def main(root, screen_path, targets_path):
    sys.path.insert(0, os.path.join(os.path.abspath(root), "scripts"))
    import replay_screen as rs
    root = rs.setup_paths(root)
    from otf_r1 import sandbox, toolgen
    data = json.load(open(screen_path, encoding="utf-8"))
    targets = json.load(open(targets_path, encoding="utf-8"))
    programs = data["programs"]

    print("== replay-exact programs: changes by family (exact / wrong / not mappable / crashed)")
    totals = collections.Counter()
    for e in programs:
        if not e["replay_exact_program"]:
            continue
        c = collections.Counter()
        for rec in e["runs"].values():
            for x in rec["changes"]:
                if x["status"] != "ran":
                    c[(x["family"], x["status"])] += 1
                else:
                    kind = "exact" if x["exact"] else "wrong"
                    if x["family"] != "no_effect_control" and x.get("reference_changed_cases", 0) == 0:
                        kind = "ran_no_case_end_change_" + kind
                    c[(x["family"], kind)] += 1
        totals.update(c)
        print(e["system"], e["setup"][:16], e["doc"][9:12], e["build"], dict((f"{a[:8]}:{b}", n) for (a, b), n in sorted(c.items()) if b not in ("exact",)) or "all exact")
    print("totals:")
    for k, v in sorted(totals.items()):
        print("  ", k, v)

    def load(e):
        d = Path(root, "runs", rs.SYSTEM_FOLDERS[e["system"]], e["setup"], e["doc"], e["build"])
        return json.load(open(d / "program.json", encoding="utf-8"))["code"], json.loads((d / "navmap.json").read_text())

    def simulate(code, nav, run):
        with tempfile.TemporaryDirectory() as tmp:
            m = Path(tmp) / "m.json"
            m.write_text(json.dumps(nav))
            r = toolgen.read_scope(code, m, run)
            cut = toolgen._cut(r)
            blind = toolgen.blinded_map(nav, m, run, r, cut)
            ok, out = sandbox.run(code, "simulate", blind, [run], {"inputs": r["inputs"], "params": r["params"], "start": cut, "horizon": rs.HORIZON})
            assert ok, out
            return r, cut, out

    print("\n== program-level case C, inspected")
    for name, rec_list in (("c", data["summary"]["program_level_c"]),):
        for tag in rec_list:
            system, setup, doc, build, run, change, f1 = tag
            e = next(p for p in programs if (p["system"], p["setup"], p["doc"], p["build"]) == (system, setup, doc, build))
            target = next(t for t in targets if t["doc"] == doc and t["run"] == run and t["name"] == change)
            print(tag)
            print(" change:", json.dumps(target["interventions"])[:300])
            code, nav = load(e)
            r0, cut0, out0 = simulate(code, rs.changed_map(nav, run, rs.plan_tables(root, doc, run, {})), run)
            r1, cut1, out1 = simulate(code, rs.changed_map(nav, run, rs.plan_tables(root, doc, run, target)), run)
            print(" cut", cut0, "->", cut1)
            model, _, ref0 = rs.reference(root, doc, run, {})
            _, _, ref1 = rs.reference(root, doc, run, target)
            task = target["interventions"][0]["task"]
            case = target["interventions"][0]["selector"]["case"]
            print(" reference factual row:", [t for t in ref0["tasks"] if t["case"] == case and t["task"] == task])
            print(" reference changed row:", [t for t in ref1["tasks"] if t["case"] == case and t["task"] == task])
            changed_inputs = [x for x in r1["inputs"] if case in (x.get("entities") or []) and x not in r0["inputs"]]
            print(" inputs that differ on the changed document:", json.dumps([{k: v for k, v in x.items() if k != "src"} for x in changed_inputs])[:500])
            skip = set(r1["schedule_kinds"])
            pred, truth = rs.keys_of(out1, cut1, skip), rs.keys_of(r1["outcomes"], cut1, skip)
            print(" records true", sum(truth.values()), "simulated", sum(pred.values()), "exact", sum((pred & truth).values()))
            missing, extra = truth - pred, pred - truth
            by_case = collections.Counter()
            for k, v in missing.items():
                by_case[k[1]] += v
            print(" wrong records by case:", by_case.most_common(8))
            print(" first true not simulated:", sorted(missing, key=lambda k: k[2])[:6])
            print(" first simulated not true:", sorted(extra, key=lambda k: k[2])[:6])
            d0 = {c["case"]: c["end"] for c in ref0["cases"]}
            d1 = {c["case"]: c["end"] for c in ref1["cases"]}
            print(" reference cases whose end moved:", {c: (d0[c], d1[c]) for c in d1 if c in d0 and d0[c] != d1[c]})
            lines = code.splitlines()
            for i, line in enumerate(lines):
                if re.search(r"\b(work|service|remaining|duration)\b", line, re.I) and re.search(r"<=|>=|==|<|>|\bif\b|\bmax\(|\bmin\(", line) and "src" not in line:
                    print(f"   code {i}: {line.strip()[:120]}")

    print("\n== accepted near 1.0 but not replay-exact")
    for e in programs:
        if e["acceptance_f1"] and e["acceptance_f1"] >= 0.95 and not e["replay_exact_program"]:
            print(e["system"], e["setup"], e["doc"][9:12], e["build"], e["acceptance_f1"], [e["runs"][r]["factual"].get("f1") for r in rs.RUNS])


if __name__ == "__main__":
    main(*sys.argv[1:4])
