"""Deterministic-realization check for the manufacturing and IT question files (evaluation-only).

For each question:
1. every input the reference reads for that chapter or window under the change (opening stock, unit weights,
   capacity, production and orders for the simulated days; machines and every task's attributes) is printed in the
   document, with the value the reference uses: the raw-rebuilt inputs must equal the inputs parsed from the PDF;
2. every entity the question names (product, order, job, task, machine, failure) is printed in that chapter;
3. the changed values are set by the question text itself;
4. gold recomputed from the PDF alone (validate.py) and from the raw rebuild (sim.py) equals the stored gold.
Both references are deterministic (no random draws), so 1-3 mean the answer is derivable from the document and
the question. Exits nonzero if any question fails.

The workflow counterpart is validation/question_draw_coverage.py.

Usage: python -X utf8 validation/mlsys_input_coverage.py <questions.json> [...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mlsys_gold as G  # noqa: E402


def mfg_problems(q):
    title, s, p = q["scope"], G.scope("manufacturing", q["scope"]), G.ps("manufacturing", q["scope"])
    out = []
    if p["capacity"] != s.capacity_kg:
        out.append("capacity not printed as used")
    for prod in s.products:
        if p["products"].get(prod) != (s.grams_per_unit[prod], s.opening_stock[prod]):
            out.append(f"constants of {prod}")
    for d in range(s.first_day, s.last_day + 1):          # days the reference simulates for a ledger-day query
        for prod in s.products:
            row = p["ledger"].get((d, prod))
            if row is None or (row["produced"], row["ordered"]) != (s.production[d][prod], s.orders[d][prod]):
                out.append(f"inputs day {d} {prod}")
    b, qq = q["binding"], q["query"]
    if qq["product"] not in s.products or not s.first_day <= qq["day"] <= s.last_day:
        out.append("query target not in the chapter's ledger")
    if b.get("target") is not None and b["target"] not in s.products:
        out.append("change target not in the chapter")
    if b["family"] == "order_removal" and s.orders[b["day"]][b["target"]] <= 0:
        out.append("removed order does not exist")
    return out


def it_problems(q):
    title, w, p = q["scope"], G.scope("it_ops", q["scope"]), G.ps("it_ops", q["scope"])
    out = []
    tasks = {t.tid: {"job": t.job, "pri": t.priority, "cpu": t.cpu, "mem": t.mem, "submit": t.submit, "run": t.duration}
             for t in w.tasks}
    if tasks != p["tasks"]:
        out.append("task inputs not printed as used")
    machines = [{"id": m.mid, "cpu": m.cpu, "mem": m.mem, "down": m.down, "back": m.back} for m in w.machines]
    if machines != p["machines"]:
        out.append("machine inputs not printed as used")
    b = q["binding"]
    if q["query"]["task"] not in p["tasks"]:
        out.append("query task not printed")
    fam = b["family"]
    if fam == "job_removal" and b["target"] not in {a["job"] for a in p["tasks"].values()}:
        out.append("job not printed")
    if fam in ("task_priority", "task_request") and b["target"] not in p["tasks"]:
        out.append("task not printed")
    if fam in ("failure_removal", "machine_removal") and b["target"] not in {m["id"] for m in p["machines"]}:
        out.append("machine not printed")
    if fam == "failure_removal" and next(m for m in p["machines"] if m["id"] == b["target"])["down"] is None:
        out.append("failure not printed")
    if fam == "job_removal" and q["query"]["task"] in {t for t, a in p["tasks"].items() if a["job"] == b["target"]}:
        out.append("queried task is removed")
    return out


def text_sets_change(q):
    """Each changed value is stated as a whole token of the question text (review 1: not a substring)."""
    import re
    b, t = q["binding"], q["text"]
    tokens = set(re.findall(r"[A-Za-z0-9%.-]+", t.replace(",", " ")))
    tokens |= {x.rstrip(".") for x in tokens}
    need = [str(b[k]) for k in ("target", "day") if b.get(k) is not None]
    if b.get("value") is not None and b["family"] != "dispatch_capacity":
        need.append(str(int(b["value"])))
    if b["family"] == "dispatch_capacity":
        need.append(f"{round(b['value'] * 100)}%")
    out = [f"text does not state {x!r}" for x in need if x not in tokens]
    if b["family"] == "task_request" and ({"cpu": "CPU", "mem": "memory"}[b["resource"]] not in tokens):
        out.append("text does not name the resource")
    if b["family"] == "production_timing" and str(b["day"] + int(b["value"])) not in tokens:
        out.append("text does not state the arrival day")
    return out


def main(paths):
    bad = {}
    n = 0
    for path in paths:
        for q in json.loads(Path(path).read_text(encoding="utf-8")):
            n += 1
            probs = (mfg_problems(q) if q["domain"] == "manufacturing" else it_problems(q)) + text_sets_change(q)
            g_sim, g_ref = G.gold(q["domain"], q["scope"], q["interventions"], q["query"])
            if not (g_sim == g_ref == q["gold"] == q["gold_reimpl"]):
                probs.append(f"gold {q['gold']} vs sim {g_sim} vs PDF-only {g_ref}")
            if probs:
                bad[q["id"]] = probs
    print(n, "questions checked;", len(bad), "fail")
    for k, v in list(bad.items())[:20]:
        print(" ", k, v)
    if n == 0:
        print("no questions checked: pass at least one question file")
        return 2
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
