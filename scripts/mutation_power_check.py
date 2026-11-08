"""Can the validation scenarios detect an engine bug? Break copies of the engine on purpose and count detections.

Each mutation changes one semantic rule. A mutation is detected if any scenario output differs from the correct
engine's output. The mutated engine is written to a temporary folder and never replaces the real one.

Usage: python -X utf8 scripts/mutation_power_check.py <project_root> <out_json> <fuzz_limit>
"""
import glob
import importlib.util
import json
import os
import sys
import tempfile

MUTATIONS = {
    "tie_break_ignores_longest_idle": ("rank = (s, r.free_at, r.k)", "rank = (s, 0, r.k)"),
    "queue_key_ignores_arrival": ("heapq.heappush(self.heap, (t, self.arrival[case], case, element, visit))",
                                  "heapq.heappush(self.heap, (t, 0, case, element, visit))"),
    "interval_end_inclusive": ("(self.hi is None or time < self.hi)", "(self.hi is None or time <= self.hi)"),
    "interval_start_exclusive": ("(self.lo is None or time >= self.lo)", "(self.lo is None or time > self.lo)"),
    "draw_ignores_visit": ('text = f"{self.seed}|{case}|{element}|{visit}|{variable}"',
                           'text = f"{self.seed}|{case}|{element}|1|{variable}"'),
    "routing_threshold_inclusive": ("if u < cumulative:", "if u <= cumulative or cumulative >= Fraction(1, 4):"),
    "unavailability_ignored_during_work": ("end = r.working.work_end(start, service)", "end = start + service"),
    "scale_rounds_down": ("* rule.value + Fraction(1, 2))", "* rule.value)"),
}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(root, out_path, fuzz_limit):
    root = os.path.abspath(root)
    source = open(os.path.join(root, "reference_engine", "engine.py"), encoding="utf-8").read()
    hand = sorted(glob.glob(os.path.join(root, "spec", "scenarios", "H*.json")))
    process = sorted(glob.glob(os.path.join(root, "spec", "scenarios", "P*.json")))
    fuzz = sorted(glob.glob(os.path.join(root, "validation", "fuzz_v1", "*.json")))[:int(fuzz_limit)]
    good = load(os.path.join(root, "reference_engine", "engine.py"), "engine_good")
    sets = {"hand": hand, "process": process, "fuzz": fuzz}
    baseline = {p: good.run_scenario(p) for group in sets.values() for p in group}
    report = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, (old, new) in MUTATIONS.items():
            if source.count(old) != 1:
                report[name] = {"error": f"pattern found {source.count(old)} times"}
                continue
            path = os.path.join(tmp, name + ".py")
            with open(path, "w", encoding="utf-8") as f:
                f.write(source.replace(old, new))
            bad = load(path, "m_" + name)
            result = {}
            for label, group in sets.items():
                hits = [os.path.basename(p) for p in group if bad.run_scenario(p) != baseline[p]]
                result[label] = {"detected_by": len(hits), "of": len(group), "first": hits[:3]}
            report[name] = result
            print(name, {k: f"{v['detected_by']}/{v['of']}" for k, v in result.items()}, flush=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:4])
