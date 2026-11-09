"""One shared task spec per domain, for every stdin platform (DEVS-Gen and the plain coding agent), and the DEVS-Gen
task files for manufacturing and IT operations (Category 2 shared task adapter, D16 decision 2).

A spec is the process prose, the generic input and output format and one example input, with no per-family hints.
- Loan and pharmacy: written out verbatim from the existing DEVS-Gen task files, which are not changed. The script
  checks that the spec re-assembles into byte-identical YAML.
- Manufacturing and IT operations: the prose is the MLSys document front matter (`render.intro` in the pinned clone),
  with the paragraphs that describe the document's chapters and sections replaced by the input description, and the
  constants paragraph and the workload-sampling paragraph (how the documents were made) replaced by "given in the
  input". The input and output format matches `assurance/mlsys.py` (`inputs_from_schema`, `parse_events`). The
  example is one dev chapter or window seen at build time, built from the document map only.

Outputs: adapters/generic_tasks/<Task>/{spec.md, spec.json, example_input.json};
         adapters/devs_gen_tasks/<Task>/{<Task>.yaml, <task>_test_config.json} for Manufacturing and ITOperations.

Usage: python -X utf8 scripts/make_generic_task_specs.py
"""
import json
import re
import sys
import textwrap
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import mlsys_gold as G  # noqa: E402
from assurance import mlsys as M  # noqa: E402

GEN = ROOT / "adapters" / "generic_tasks"
DEVS = ROOT / "adapters" / "devs_gen_tasks"
KEYS = ("general", "scenario", "args_input_output")


def read_task_yaml(path: Path) -> dict:
    """The three requirement blocks of a DEVS-Gen task file in the layout make_devs_gen_workflow_task.py writes."""
    lines = path.read_text(encoding="utf-8").split("\n")
    out, key, buf = {}, None, []
    head = {}
    for ln in lines:
        m = re.fullmatch(r"    (\w+): \|", ln)
        if m:
            if key:
                out[key] = buf
            key, buf = m.group(1), []
            continue
        if key is None:
            if ":" in ln:
                k, v = ln.split(":", 1)
                head[k.strip()] = v.strip()
            continue
        buf.append(ln)
    out[key] = buf
    blocks = {}
    for k, b in out.items():
        while b and b[-1] == "":
            b.pop()
        blocks[k] = "\n".join(x[8:] if x.startswith(" " * 8) else x.strip() for x in b) + "\n"
    return {"head": head, **blocks}


def write_yaml(path: Path, name: str, spec: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(f"root_model_name: {name}\n")
        f.write("required_cli_options: [--horizon]\n")
        f.write("requirements:\n")
        for key in KEYS:
            f.write(f"    {key}: |\n")
            f.write(textwrap.indent(spec[key].strip(), " " * 8) + "\n\n")


def write_spec(name: str, spec: dict, example: dict, source: str) -> None:
    d = GEN / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps({"task": name, "required_cli_options": ["--horizon"], "source": source,
                                             **{k: spec[k] for k in KEYS}}, indent=1), encoding="utf-8")
    (d / "example_input.json").write_text(json.dumps(example, indent=1), encoding="utf-8")
    md = [f"# Task: {name}", "", f"Source: {source}", "", "## General implementation requirements", "", spec["general"].strip(),
          "", "## Scenario", "", spec["scenario"].strip(), "", "## Command line, input and output", "",
          spec["args_input_output"].strip(), ""]
    (d / "spec.md").write_text("\n".join(md), encoding="utf-8")


def clean(p: str) -> str:
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("<b>", ""), ("</b>", ""), ("<i>", ""), ("</i>", "")):
        p = p.replace(a, b)
    return p


def compact(data: dict) -> str:
    parts = []
    for key, rows in data.items():
        if isinstance(rows, list):
            parts.append(f' "{key}": [\n  ' + ",\n  ".join(json.dumps(r) for r in rows) + "\n ]")
        else:
            parts.append(f' "{key}": {json.dumps(rows)}')
    return "{\n" + ",\n".join(parts) + "\n}"


# ---------------------------------------------------------------- manufacturing
def mfg_spec(general: str):
    from domains.manufacturing import data, render, scopes
    rec = data.load(G.SUPPLYGRAPH)
    prose = [clean(p) for p in render.intro(rec, scopes.capacity(rec))]
    out = []
    for p in prose:
        if p.startswith("This document records stock and dispatch"):
            p = ("This task simulates stock and dispatch at one plant of a manufacturer of packaged consumer goods. The "
                 "daily production and daily sales-order quantities of every product are given as input (they are real "
                 "company records). Stock, shipments and backorders are computed from them by the stock and dispatch "
                 "policy stated below, applied exactly.")
        elif p.startswith("The document is divided into chapters") or p.startswith("Each chapter has four sections"):
            continue
        elif p.startswith("Constants."):
            p = ("Constants. The input gives each product's weight per unit and opening stock, and the plant's dispatch "
                 "capacity in kilograms for every day.")
        p = p.replace("Every period is an independent run: on its first day",
                      "Every run is independent: on its first day (the first day in the input)")
        p = p.replace("Terms used in the Events section and in questions.", "Terms.")
        p = p.replace("; the Events section lists the first day of each such run of days. ", ". ")
        out.append(p)
    assert len(out) == len(prose) - 2, "front-matter layout changed"
    scenario = "### Scenario: Plant stock and dispatch\n\n" + "\n\n".join(out)
    schema = M.schema_from_map(json.loads((G.DOCS_DIR / "mfg_dev" / "navmap.json").read_text()))
    full = M.inputs_from_schema(schema, "Plant 1912, Period 01")
    ab = {"products": full["products"], "days": full["days"][:2], "flows": [f for f in full["flows"] if f["day"] <= 2]}
    io = f"""
1. Command Line Interface
* `--horizon` (int): the last day to simulate and report. Default: the last day listed in `days`.

2. Input Data Format (one JSON object on standard input)
Days are whole numbers; the run starts on the first day listed in `days`. Quantities are whole units. Weights and
capacities are given in kg with at most 3 decimals; work in whole grams (kg x 1000, rounded to an integer), so that
"as many whole units as the capacity still unused allows" is exact.
* `products`: list of {{"product": code, "kg_per_unit": weight in kg, "opening_stock": units}}. Only these products exist.
* `days`: list of {{"day": d, "capacity_kg": kg}}, one per day, in day order. The plant's dispatch capacity that day.
* `flows`: list of {{"day": d, "product": code, "produced": units, "ordered": units}}, one per day and product. The units
  of the product that arrive from production that day, and the quantity of that day's sales order (0: no order).

Example input (abridged to the first two days):
```json
{compact(ab)}
```

3. Output Data Format (STDOUT)
Emit JSONL: for every day from the first day through the horizon, and for every product, one record with exactly
these keys, in day order (simulation time is the day):
* `event` (str): always `ledger`.
* `day` (int), `product` (str).
* `produced`, `ordered`, `shipped`, `backordered`, `stock` (int): as defined in the rules above (units that arrived,
  the quantity of the order placed that day, units shipped that day for all of the product's orders together, units
  of all its open orders at the end of the day, units on hand at the end of the day).
"""
    return {"general": general, "scenario": scenario + "\n", "args_input_output": io.strip() + "\n"}, full, schema.chapters["Plant 1912, Period 01"]["last"]


# ---------------------------------------------------------------- IT operations
def it_spec(general: str):
    from domains.it_ops import render
    prose = [clean(p) for p in render.intro()]
    out = []
    for p in prose:
        if p.startswith("This document records how tasks were scheduled"):
            p = ("This task simulates how tasks are scheduled on one small compute cluster. Every task's submission time, "
                 "job, priority, CPU and memory request and run time, and every machine's capacity, failure time and "
                 "return time, are given as input (they come from real records of a production compute cell). Where and "
                 "when each task runs is computed from those inputs by the scheduling policy stated below, applied exactly.")
        elif p.startswith("The document is divided into chapters") or p.startswith("Each chapter has four sections"):
            continue
        elif p.startswith("The cluster and the workload."):
            p = ("The cluster. The input lists the machines with their CPU and memory capacity, the time a machine fails "
                 "(if it does) and the time it returns (if it does), and every task submitted.")
        elif p.startswith("After the window."):
            p = ("After the window. No task is submitted and no machine fails after `window_end`; a machine that is down "
                 "returns at its listed return time (if any); the policy continues unchanged until every task that can "
                 "start has finished.")
        p = p.replace("Order of rows. Task log rows with the same time", "Order of output records. Records with the same time")
        p = p.replace("Terms used in the Events section and in questions.", "Terms.")
        p = p.replace("The run time is given on every row of the task log, starting with the task's submit row.",
                      "The run time is given in the input.")
        out.append(p)
    assert len(out) == len(prose) - 2, "front-matter layout changed"
    scenario = "### Scenario: Compute cluster scheduling\n\n" + "\n\n".join(out)
    schema = M.schema_from_map(json.loads((G.DOCS_DIR / "itops_dev" / "navmap.json").read_text()))
    full = M.inputs_from_schema(schema, "Cell window 08")
    ab = {"window_end": full["window_end"], "machines": full["machines"], "tasks": full["tasks"][:6]}
    io = f"""
1. Command Line Interface
* `--horizon` (int): Stop at this simulation time in seconds. Default: 100000000 (every task that can start runs until it finishes).

2. Input Data Format (one JSON object on standard input)
Times are whole seconds from the window start (time 0). CPU and memory are whole units.
* `window_end` (int): the end of the window; no task is submitted and no machine fails after it.
* `machines`: list of {{"machine": id, "cpu": units, "memory": units, "fails_at": time or null, "returns_at": time or null}},
  in machine id order. Only these machines exist. `fails_at` null: the machine does not fail; `returns_at` null: a failed
  machine does not return.
* `tasks`: list of {{"task": id, "job": id, "priority": 0-11, "cpu": units, "memory": units, "submit": time, "run_time": seconds}}.
  Only these tasks exist.

Example input (abridged to the first six tasks):
```json
{compact(ab)}
```

3. Output Data Format (STDOUT)
Emit JSONL: one record per event, in the order the events happen (records with the same time in the order of the steps
above). Every record has exactly these keys:
* `time` (int): absolute simulation time in seconds.
* `event` (str): one of `submit`, `start`, `finish`, `evict`, `fail`.
* `task` (str): the task id.
* `machine` (str or null): the machine for `start`, `finish`, `evict` and `fail`; null for `submit`.
"""
    return {"general": general, "scenario": scenario + "\n", "args_input_output": io.strip() + "\n"}, full, M.IT_HORIZON


def main():
    G.materialize_docs()
    for doc in ("mfg_dev", "itops_dev"):
        p = G.DOCS_DIR / doc / "navmap.json"
        if not p.exists():
            sys.path.insert(0, str(ROOT / "redesign"))
            from otf_r1 import navmap
            p.write_text(json.dumps(navmap.build_map(G.pdf(doc))))
    general = None
    for name in ("WorkflowLoan", "WorkflowPharmacy"):
        y = DEVS / name / f"{name}.yaml"
        spec = read_task_yaml(y)
        general = general or spec["general"]
        cfg = json.loads((DEVS / name / f"{name.lower()}_test_config.json").read_text(encoding="utf-8"))
        example = json.loads(cfg[0]["cases"][0]["sim_stdin"])
        write_spec(name, spec, example, f"adapters/devs_gen_tasks/{name}/{name}.yaml (verbatim)")
        tmp = GEN / name / "_roundtrip.yaml"
        write_yaml(tmp, name, spec)
        same = tmp.read_bytes() == y.read_bytes()
        tmp.unlink()
        print(name, "spec written; re-assembles into the identical DEVS-Gen YAML:", same)
        assert same
    for name, fn, horizon_key in (("Manufacturing", mfg_spec, None), ("ITOperations", it_spec, None)):
        spec, full, horizon = fn(general)
        write_spec(name, spec, full, "scripts/make_generic_task_specs.py from the MLSys front matter")
        d = DEVS / name
        d.mkdir(parents=True, exist_ok=True)
        write_yaml(d / f"{name}.yaml", name, spec)
        cfg = [{"name": "Example_Run", "description": "One factual development chapter (seen at build time)",
                "cases": [{"sim_args": {"horizon": horizon}, "sim_stdin": json.dumps(full)}], "checker_args": {}}]
        with (d / f"{name.lower()}_test_config.json").open("w", encoding="utf-8", newline="\n") as f:
            json.dump(cfg, f, indent=1)
        print(name, "spec and DEVS-Gen task written:", (d / f"{name}.yaml").stat().st_size, "bytes")


if __name__ == "__main__":
    main()
