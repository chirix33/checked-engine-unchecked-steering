"""Render a workflow specification and its factual records into a PDF that any system under test can read.

The front matter states the published process and the semantics in prose. Each chapter is one independent
deterministic realization: its exogenous plan (inputs) and its factual records (outcomes). The PDF holds no
questions, labels or code. The reference engine is used here only to produce the factual records, and it is
never given to a system under test.

Layout follows the existing manufacturing and IT documents, so all systems read it the same way.

Usage: python scripts/render_workflow_doc.py <project_root> <model_name> <out_dir> <n_scopes> <n_cases> <seed_prefix>
"""
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

MIN_VISITS = 3
DAY_ORDER = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]


def local(tag):
    return tag.split("}")[-1]


class Labels:
    """Readable names for model elements, using only what the published model states."""

    def __init__(self, model, bpmn_path):
        self.model = model
        root = ET.parse(bpmn_path).getroot()
        self.names = {e.get("id"): " ".join((e.get("name") or "").split()) for e in root.iter() if e.get("id")}
        self.flow_names = dict(self.names)
        self.label = {}
        counters = {"decision": 0, "timer": 0, "split": 0, "join": 0}
        order, seen, pending = [], set(), [model.start]
        while pending:
            element = pending.pop(0)
            if element in seen:
                continue
            seen.add(element)
            order.append(element)
            pending += [model.flows[f][1] for f in sorted(model.outgoing.get(element, []))]
        self.order = order
        for element in order:
            kind = model.kind[element]
            if kind == "task":
                self.label[element] = self.names[element]
            elif kind == "intermediateCatchEvent":
                counters["timer"] += 1
                self.label[element] = f"W{counters['timer']}"
            elif kind == "exclusiveGateway" and model.is_branching(element):
                counters["decision"] += 1
                self.label[element] = f"D{counters['decision']}"
            elif kind == "parallelGateway":
                many_in, many_out = len(model.incoming[element]) > 1, len(model.outgoing[element]) > 1
                name = "join" if many_in and not many_out else "split"
                counters[name] += 1
                self.label[element] = f"{name.upper()[0]}{counters[name]}"
            elif kind == "endEvent":
                self.label[element] = "End"
            elif kind == "startEvent":
                self.label[element] = "Start"

    def resolve(self, flow):
        """The next labelled element, passing through exclusive gateways with one outgoing flow."""
        element = self.model.flows[flow][1]
        while self.model.kind[element] == "exclusiveGateway" and not self.model.is_branching(element):
            element = self.model.flows[self.model.outgoing[element][0]][1]
        return element

    def next_label(self, flow):
        return self.label[self.resolve(flow)]

    def routes(self, gateway):
        return {flow: f"{self.label[gateway]}-{chr(97 + i)}" for i, (flow, _) in enumerate(self.model.branch[gateway])}


def in_cycle(model):
    """Elements that can be visited more than once in a case."""
    succ = {e: [model.flows[f][1] for f in model.outgoing.get(e, [])] for e in model.kind}
    result = set()
    for element in model.kind:
        seen, pending = set(), list(succ[element])
        while pending:
            cur = pending.pop()
            if cur == element:
                result.add(element)
                break
            if cur not in seen:
                seen.add(cur)
                pending += succ[cur]
    return result


def clock(seconds):
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"


def describe_windows(windows):
    days = {}
    for lo, hi in windows:
        days.setdefault((lo % 86400, hi % 86400), []).append(DAY_ORDER[lo // 86400].title())
    parts = []
    for (lo, hi), names in days.items():
        span = names[0] if len(names) == 1 else f"{names[0]} to {names[-1]}"
        parts.append(f"{span} {clock(lo)} to {clock(hi)}")
    return "; ".join(parts)


def describe_dist(dist):
    p = dist.params
    if dist.name == "fix":
        return f"fixed at {p[0]:g} seconds"
    if dist.name == "expon":
        return f"exponential, mean {p[0]:g}, between {p[1]:g} and {p[2]:g} seconds"
    return f"normal, mean {p[0]:g}, standard deviation {p[1]:g}, between {p[2]:g} and {p[3]:g} seconds"


def intro(model, labels, title):
    paragraphs = [
        f"This document records independent runs of one business process, {title}. The process structure and its "
        "parameters come from a published simulation model. Each run is one fixed realization: every case's arrival "
        "time, every activity's required work, every wait and every route draw are fixed in advance and listed. The "
        "records are computed from those plans by the rules below, applied exactly. Knowing the plans in advance is "
        "a condition of this benchmark, not a claim about real operations.",
        "The document is divided into chapters titled 'Run &lt;NN&gt;'. Runs are independent, and a question names its "
        "run by that title. Each chapter has these sections. 'Cases' gives each case's arrival time and end time. "
        "'Work plan' gives, for each case and activity, the work required on each visit. 'Wait plan' gives, for each "
        "case and timed wait, the delay on each visit. 'Route draws' gives, for each case and decision, the draw on "
        "each visit. 'Task log' records each performed activity. 'Wait log' records each wait. 'Decision log' records "
        "each decision. Plans list values for visits that did not happen, because a change could make them happen.",
        "<b>Time.</b> All times are whole seconds from time 0, which is a Monday at 00:00. Weekday = floor(t / 86400) "
        "mod 7, where 0 is Monday. An interval [a, b) includes a and excludes b.",
        "<b>Arrivals.</b> Arrival times are given in 'Cases' and do not depend on other cases. A new case arriving at a "
        "stated time does not change other cases' plans. Published arrival pattern: one case every "
        f"{describe_dist(model.arrival_dist)}, within {describe_windows(model.arrival_windows)}.",
    ]
    pools = [f"{name}: {info['amount']} workers ({name}_0 to {name}_{info['amount'] - 1}), working "
             f"{describe_windows(info['windows'])}" for name, info in model.pools.items()]
    paragraphs.append("<b>Workers.</b> " + ". ".join(pools) + ". Workers in a pool are interchangeable, and the "
                      "assigned worker does not change how much work an activity needs.")
    rows = []
    for element in labels.order:
        kind = model.kind[element]
        out = model.outgoing.get(element, [])
        if kind == "startEvent":
            rows.append(f"A new case goes to {labels.next_label(out[0])}.")
        elif kind == "task":
            rows.append(f"{labels.label[element]} (pool {model.task_pool[element]}, published work "
                        f"{describe_dist(model.task_dist[element])}): then {labels.next_label(out[0])}.")
        elif kind == "intermediateCatchEvent":
            rows.append(f"Wait {labels.label[element]} (published delay {describe_dist(model.timer_dist[element])}): "
                        f"then {labels.next_label(out[0])}.")
        elif kind == "exclusiveGateway" and model.is_branching(element):
            routes = labels.routes(element)
            options = [f"route {routes[f]}{' (' + labels.flow_names[f] + ')' if labels.flow_names.get(f) else ''}, "
                       f"probability {float(p):g}, to {labels.next_label(f)}" for f, p in model.branch[element]]
            rows.append(f"Decision {labels.label[element]}: " + "; ".join(options) + ".")
        elif kind == "parallelGateway":
            targets = ", ".join(labels.next_label(f) for f in out)
            if len(model.incoming[element]) > 1:
                rows.append(f"Join {labels.label[element]}: waits until all its {len(model.incoming[element])} incoming "
                            f"paths have finished, then {targets}.")
            else:
                rows.append(f"Split {labels.label[element]}: starts all of these at the same time: {targets}.")
    paragraphs.append("<b>Process.</b> " + " ".join(rows))
    paragraphs += [
        "<b>Rules.</b> A <i>visit</i> counts how many times a case has reached an activity, wait or decision, starting "
        "at 1. Reaching an activity enables it. Passing through a decision, split or join takes no time.",
        "1. <b>Which task is assigned next.</b> Enabled activities wait in one first-come-first-served line per pool, "
        "shared by all activities of that pool. Order: earliest enabled time, then the case that arrived earlier, then "
        "the lower case id, then the lower activity id, then the lower visit. Activity id order is fixed by the model "
        "and given by each activity's position in the 'Work plan' table.",
        "2. <b>Which worker.</b> The task goes to the worker who can start it earliest. On a tie, the worker free for "
        "longest; on a further tie, the lower-numbered worker. A worker can start at the first time that is at or after "
        "both the enabled time and the time the worker is free, and within that worker's working hours.",
        "3. <b>Work and pauses.</b> A worker does one task at a time and keeps it until it ends. Work counts only during "
        "working hours. Outside them the task pauses and resumes with the same worker, who stays held. A task that needs "
        "exactly the time left ends at closing time. If a worker is declared unavailable for an interval, that interval "
        "counts as non-working time in the same way.",
        "4. <b>Waits.</b> A wait starts when reached and ends after its delay. It uses no worker and ignores working "
        "hours.",
        "5. <b>Decisions.</b> Take the decision's routes in the listed order and add up their probabilities. The route "
        "taken is the first whose running total is greater than the draw for this case and visit. If a probability "
        "changes, the draw stays the same and the route is chosen again from the changed probabilities.",
        "6. <b>Case end.</b> A case ends when its last path reaches End. All cases run until they end.",
        "<b>Units.</b> Work and delays are in whole seconds. Draws are between 0 and 1, shown to 6 decimal places.",
    ]
    return paragraphs


def grid(data, widths):
    table = Table(data, repeatRows=1, colWidths=[w * inch for w in widths])
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7.5),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return table


def planned_value(engine, rules, element, case, visit, dist, u):
    """The plan's value for one visit. A case-and-visit change appears in the plan; with no change this is the draw's value."""
    found = [r for r in rules.get(element, []) if r.selector.lo is None and r.selector.hi is None and r.selector.matches(case, visit, 0)]
    return engine.apply_value(found[0] if found else None, dist, u)


def chapter_tables(engine, model, labels, cycles, scenario, seed):
    """Run one realization and return its section tables and summary numbers."""
    run = engine.Run(model, scenario)
    body = run.execute()
    label = labels.label
    observed = {}
    for t in body["tasks"]:
        observed[t["task"]] = max(observed.get(t["task"], 0), t["visit"])
    for t in body["timers"]:
        observed[t["timer"]] = max(observed.get(t["timer"], 0), t["visit"])
    for b in body["branches"]:
        observed[b["gateway"]] = max(observed.get(b["gateway"], 0), b["visit"])
    depth = max([MIN_VISITS] + [v + 1 for v in observed.values()])

    def visits(element):
        return list(range(1, depth + 1)) if element in cycles else [1]

    def plan_row(case, element, value):
        cells = [value(v) for v in visits(element)]
        return [case, label[element]] + cells + [""] * (depth - len(cells))

    heads = [f"visit {i}" for i in range(1, depth + 1)]
    cases = [c["case"] for c in sorted(body["cases"], key=lambda x: (x["arrival"], x["case"]))]
    tasks = sorted(e for e, k in model.kind.items() if k == "task")
    timers = sorted(e for e, k in model.kind.items() if k == "intermediateCatchEvent")
    decisions = sorted(e for e in model.kind if model.is_branching(e))
    work = [["case", "activity"] + heads]
    wait = [["case", "wait"] + heads]
    draws = [["case", "decision"] + heads]
    for case in cases:
        for t in tasks:
            work.append(plan_row(case, t, lambda v: str(planned_value(engine, run.plan.duration, t, case, v, model.task_dist[t], run.u(case, t, v, "service")))))
        for t in timers:
            wait.append(plan_row(case, t, lambda v: str(planned_value(engine, run.plan.timer, t, case, v, model.timer_dist[t], run.u(case, t, v, "timer")))))
        for d in decisions:
            draws.append(plan_row(case, d, lambda v: f"{float(run.u(case, d, v, 'branch')):.6f}"))
    case_rows = [["case", "arrival", "end"]] + [[c["case"], str(c["arrival"]), str(c["end"])] for c in body["cases"]]
    log = [["case", "activity", "visit", "enabled", "start", "end", "worker"]]
    log += [[t["case"], label[t["task"]], str(t["visit"]), str(t["enabled"]), str(t["start"]), str(t["end"]), t["resource"]]
            for t in body["tasks"]]
    wlog = [["case", "wait", "visit", "start", "end"]]
    wlog += [[t["case"], label[t["timer"]], str(t["visit"]), str(t["start"]), str(t["end"])] for t in body["timers"]]
    dlog = [["case", "decision", "visit", "time", "route"]]
    dlog += [[b["case"], label[b["gateway"]], str(b["visit"]), str(b["time"]), labels.routes(b["gateway"])[b["flow"]]]
             for b in body["branches"]]
    plan_width = [0.5, 2.35] + [min(0.6, 3.9 / depth)] * depth
    return [
        ("Cases", case_rows, [0.7, 1.0, 1.0]),
        ("Work plan", work, plan_width),
        ("Wait plan", wait, plan_width),
        ("Route draws", draws, plan_width),
        ("Task log", log, [0.5, 2.35, 0.4, 0.75, 0.75, 0.75, 1.1]),
        ("Wait log", wlog, [0.5, 0.6, 0.4, 0.8, 0.8]),
        ("Decision log", dlog, [0.5, 0.7, 0.4, 0.8, 0.7]),
    ], {"seed": seed, "cases": len(cases), "tasks": len(body["tasks"]), "visit_columns": depth,
        "max_end": max(c["end"] for c in body["cases"])}


def main(root, model_name, out_dir, n_scopes, n_cases, seed_prefix):
    names = [f"Run {i + 1:02d}" for i in range(int(n_scopes))]
    return render(root, model_name, out_dir, [(name, f"{seed_prefix}-{i + 1:02d}", []) for i, name in enumerate(names)], n_cases)


def render(root, model_name, out_dir, chapters, n_cases):
    """chapters: (title, seed, interventions). Interventions are used only to render evaluation-side truth documents."""
    root = os.path.abspath(root)
    sys.path.insert(0, os.path.join(root, "reference_engine"))
    import engine  # Evaluation-side only. Its output here is the factual record.

    syn = os.path.join(root, "data", "zenodo_10435849", "inputs", "synthetic")
    bpmn, params = os.path.join(syn, model_name + ".bpmn"), os.path.join(syn, model_name + ".json")
    model = engine.Model(bpmn, params)
    labels = Labels(model, bpmn)
    cycles = in_cycle(model)
    title = model_name.split("_3_timers")[0].replace("_", " ")
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, "document.pdf")
    styles = getSampleStyleSheet()
    h1, h2, body_style = styles["Heading1"], styles["Heading2"], styles["BodyText"]
    h1.fontName = h2.fontName = "Helvetica-Bold"
    meta = {"model": model_name, "scopes": [], "element_labels": labels.label}

    class Doc(SimpleDocTemplate):
        def afterFlowable(self, flowable):
            info = getattr(flowable, "_outline", None)
            if info:
                key, text, level = info
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=level)

    def heading(text, style, key, level):
        p = Paragraph(text, style)
        p._outline = (key, text, level)
        return p

    doc_title = f"{title} Process Records"
    story = [heading(doc_title, styles["Title"], "intro", 0)]
    story += [Paragraph(t, body_style) for t in intro(model, labels, title)]
    names = [c[0] for c in chapters]
    story.append(Paragraph("Chapters in this document: " + ", ".join(names) + ".", body_style))
    for i, (name, seed, interventions) in enumerate(chapters):
        scenario = {"schema": "wf-scenario/1", "scenario_id": name, "seed": seed, "n_cases": int(n_cases), "interventions": interventions}
        tables, summary = chapter_tables(engine, model, labels, cycles, scenario, seed)
        meta["scopes"].append({"title": name, **summary})
        key = f"r{i + 1:02d}"
        story += [PageBreak(), heading(name, h1, key, 0),
                  Paragraph(f"{name} has {summary['cases']} cases.", body_style)]
        for j, (section, rows, widths) in enumerate(tables):
            story.append(heading(f"{name}: {section}", h2, f"{key}s{j}", 1))
            story += [Spacer(1, 4), grid(rows, widths)]
    doc = Doc(pdf_path, pagesize=letter, title=doc_title, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
              topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    doc.build(story)
    meta["pages"] = doc.page
    with open(os.path.join(out_dir, "document_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    print(json.dumps({k: meta[k] for k in ("model", "pages", "scopes")}))


if __name__ == "__main__":
    main(*sys.argv[1:7])
