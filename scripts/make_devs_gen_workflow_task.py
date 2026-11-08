"""Write a DEVS-Gen task for a workflow process (Category 2 shared task adapter, D16 decision 2).

The process prose and rules are the same text the OTF documents carry in their front matter, so both backends get
the same process knowledge. Inputs arrive on standard input in one generic JSON format that covers cases, plans,
route draws, worker schedule changes, extra workers and route probabilities. No family-specific hints. The test
config holds one factual development run as an example, as DEVS-Gen's discovery requires a config file.

Usage: python scripts/make_devs_gen_workflow_task.py <project_root> <model_name> <task_name> <out_dir> <seed_prefix>
"""
import json
import os
import sys
import textwrap

N_CASES = 15


def main(root, model_name, task_name, out_dir, seed_prefix):
    root = os.path.abspath(root)
    sys.path[:0] = [os.path.join(root, "reference_engine"), os.path.join(root, "scripts")]
    import engine
    import render_workflow_doc as render
    import replay_screen as rs

    syn = os.path.join(root, "data", "zenodo_10435849", "inputs", "synthetic")
    bpmn, params = os.path.join(syn, model_name + ".bpmn"), os.path.join(syn, model_name + ".json")
    model = engine.Model(bpmn, params)
    labels = render.Labels(model, bpmn)
    cycles = render.in_cycle(model)
    title = model_name.split("_3_timers")[0].replace("_", " ")
    prose = [p.replace("&lt;", "<").replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
             for p in render.intro(model, labels, title)]
    # The OTF front matter also describes its document sections. Those two paragraphs are replaced here by the
    # input description below, because this backend receives the same information on standard input instead.
    prose = [p for p in prose if not p.startswith("The document is divided into chapters")]
    prose = [p.replace("This document records independent runs of one business process",
                       "This task simulates one business process") for p in prose]
    # Same tie-break order, stated against this backend's input: the work list lists each case's activities in
    # activity id order, exactly as the OTF document's Work plan table does.
    prose = [p.replace("given by each activity's position in the 'Work plan' table",
                       "given by the order in which each case's activities appear in the `work` input list") for p in prose]
    assert any("`work` input list" in p for p in prose), "tie-break sentence not found"

    activities = sorted({labels.label[e] for e, k in model.kind.items() if k == "task"})
    waits = sorted({labels.label[e] for e, k in model.kind.items() if k == "intermediateCatchEvent"})
    decisions = sorted({labels.label[e] for e in model.kind if model.is_branching(e)})
    routes = {labels.label[g]: [r for r in labels.routes(g).values()] for g in model.kind if model.is_branching(g)}
    pools = sorted(model.pools)

    example = example_input(root, model, labels, cycles, render, engine, f"{seed_prefix}-01")

    def block(text):
        return textwrap.indent(text.strip(), " " * 8)

    general = """
### General Implementation Requirements
1. Language & Environment:
- Target Language: Python 3.10+
- Standard Libraries: `argparse`, `sys`, `json`, `logging`, `collections`, `heapq`, `math`, `xdevs`.

2. Input Interface (Arguments & Stdin):
- **CLI Arguments:** You MUST use the `argparse` library to handle configuration parameters.
- **Data Stream:** Read ONE JSON object from `sys.stdin` (the whole of standard input) before starting the simulation.

3. Output Interface:
- Stream 1: KPI Data (sys.stdout)
    - You MUST print ONLY the required event records to Standard Output.
    - Format: JSONL. Each line is a valid, independent JSON object representing a key event.
    - Emit records in nondecreasing absolute simulation-time order.
- Stream 2: Debug/Log data (sys.stderr)
    - Print any other information (debug, progress, warnings) to Standard Error.

4. Entry point: executable via `python run.py`

Do not use real time, use simulation time, and guarantee the simulation ends in 10 seconds in real time.
"""
    scenario = "### Scenario: " + title + " process\n\n" + "\n\n".join(prose)
    io = f"""
1. Command Line Interface
* `--horizon` (int): Stop at this simulation time in seconds. Default: 100000000 (every case runs until it ends).

2. Input Data Format (one JSON object on standard input)
All times and durations are whole seconds from time 0, a Monday at 00:00, as in the rules above.
* `cases`: list of {{"case": id, "arrival": time}}. Only these cases exist. A case not listed does not arrive.
* `work`: list of {{"case": id, "activity": name, "visit": n, "seconds": s}}. The work activity `name` needs on visit
  `n` of that case. Activity names are: {", ".join(activities)}.
* `waits`: list of {{"case": id, "wait": label, "visit": n, "seconds": s}}. Wait labels are: {", ".join(waits)}.
* `draws`: list of {{"case": id, "decision": label, "visit": n, "draw": u}}. Decision labels are: {", ".join(decisions)}.
* `route_probabilities` (optional): {{decision label: {{route label: probability}}}}. When present, these replace the
  probabilities stated in the rules for that decision. Route labels are: {json.dumps(routes)}.
* `workers` (optional): {{pool: number}}. When present, the pool has that many workers instead of the stated number.
  Workers are numbered from 0 and named `<pool>_<k>`. Pools are: {", ".join(pools)}.
* `unavailable` (optional): list of {{"worker": name, "from": t1, "to": t2}}. That worker has no working time in
  [t1, t2), in addition to its working hours.
Entries for visits that never happen may be present and are then unused.

Example input (abridged to the first two cases):
```json
{compact(example)}
```

3. Output Data Format (STDOUT)
Emit JSONL. Every record has exactly these keys:
* `time` (int): absolute simulation time in seconds.
* `case` (str): the case id.
* `event` (str): one of `task_start`, `task_end`, `wait_start`, `wait_end`, `decision`, `case_end`.
* `name` (str): the activity name, wait label or decision label; for `case_end`, the empty string.
* `visit` (int): the visit number; for `case_end`, 0.
* `worker` (str): the worker name for `task_start` and `task_end`; otherwise the empty string.
* `route` (str): the route label taken for `decision`; otherwise the empty string.
"""
    task = {"root_model_name": task_name, "required_cli_options": ["--horizon"],
            "requirements": {"general": general.strip() + "\n", "scenario": scenario + "\n", "args_input_output": io.strip() + "\n"}}
    os.makedirs(out_dir, exist_ok=True)
    yaml_path = os.path.join(out_dir, f"{task_name}.yaml")
    with open(yaml_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"root_model_name: {task_name}\n")
        f.write("required_cli_options: [--horizon]\n")
        f.write("requirements:\n")
        for key in ("general", "scenario", "args_input_output"):
            f.write(f"    {key}: |\n")
            f.write(block(task["requirements"][key]) + "\n\n")
    full = example_input(root, model, labels, cycles, render, engine, f"{seed_prefix}-01", abridge=False)
    config = [{"name": "Example_Run", "description": "One factual development run", "cases": [
        {"sim_args": {"horizon": 100000000}, "sim_stdin": json.dumps(full)}], "checker_args": {}}]
    with open(os.path.join(out_dir, f"{task_name.lower()}_test_config.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(config, f, indent=1)
    print(yaml_path, os.path.getsize(yaml_path), "bytes")


def compact(data):
    """One record per line, so the example stays readable and short."""
    parts = []
    nl = "\n"
    for key, rows in data.items():
        body = ("," + nl + "  ").join(json.dumps(r) for r in rows)
        parts.append(" \"" + key + "\": [" + nl + "  " + body + nl + " ]")
    return "{" + nl + ("," + nl).join(parts) + nl + "}"


def example_input(root, model, labels, cycles, render, engine, seed, abridge=True, interventions=(), draw_overrides=()):
    """The standard-input object for one realization, built from the same plan values the OTF document lists."""
    scenario = {"schema": "wf-scenario/1", "scenario_id": seed, "seed": seed, "n_cases": N_CASES,
                "interventions": list(interventions), "draw_overrides": list(draw_overrides)}
    tables, _ = render.chapter_tables(engine, model, labels, cycles, scenario, seed)
    t = {name: rows for name, rows, _ in tables}

    def plan(rows, key):
        out = []
        head = rows[0]
        for row in rows[1:]:
            for j, h in enumerate(head[2:], start=2):
                if row[j] != "":
                    out.append({"case": row[0], key: row[1], "visit": int(h.split()[1]),
                                ("draw" if key == "decision" else "seconds"): float(row[j]) if key == "decision" else int(row[j])})
        return out

    data = {"cases": [{"case": r[0], "arrival": int(r[1])} for r in t["Cases"][1:]],
            "work": plan(t["Work plan"], "activity"), "waits": plan(t["Wait plan"], "wait"),
            "draws": plan(t["Route draws"], "decision")}
    if abridge:
        keep = {c["case"] for c in data["cases"][:2]}
        data = {k: [x for x in v if x["case"] in keep] for k, v in data.items()}
    return data


if __name__ == "__main__":
    main(*sys.argv[1:6])
