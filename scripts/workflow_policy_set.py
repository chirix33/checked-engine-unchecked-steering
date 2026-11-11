"""Policy-variant reuse documents for the business workflows (evaluation-side). Decided by Ashraf, 2026-11-09.

Two variants per process, each on 2 new runs, rendered by the unchanged renderer (`render_workflow_doc.render`):

  P  changed policy, same tables: the bottleneck pool gets one more worker (Loan Appraiser 2 -> 3, Pharmacy Pharmacist
     1 -> 2). Only that pool's "amount" changes in a copy of the published parameter file; the front matter then
     states the new count, and the records follow it. Runs 13-14, seeds policyP-<process>-13..14.
  H  harmless rewording: the same parameters, with the front matter's prose reworded by a fixed table (`REWORD`).
     The statements of parameters, which the library parses (the worker list with counts and hours, the arrival
     pattern, and the whole "Process." paragraph), are kept verbatim. Runs 15-16, seeds policyH-<process>-15..16.

P and H have distinct run titles (13-14 and 15-16), different from dev (01-04) and test (05-12), because evidence
reuse is keyed by run title: a shared title would let one variant's evidence stand for another's whenever the
fingerprint is ignored (the "carry the record unchanged" regime).

Variant parameter files are written to runs/workflow_policy_v1/root_<doc>/data/zenodo_10435849/inputs/synthetic/,
so the renderer, which reads models from <root>/data/zenodo_10435849/inputs/synthetic, runs unchanged with that
root. The BPMN is copied byte for byte; for H the JSON is too. replay_screen's lookups reach the files through a
relative model path (`register`).

Usage: python -X utf8 scripts/workflow_policy_set.py docs                  (renders only documents that are absent)
       python -X utf8 scripts/workflow_policy_set.py check <out_json>      (provenance and rule checks)
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
for sub in ("", "redesign", "reference_engine", "scripts"):
    if str(ROOT / sub) not in sys.path:
        sys.path.insert(0, str(ROOT / sub))

import workflow_test_set as wt          # noqa: E402

SYN_REL = Path("data") / "zenodo_10435849" / "inputs" / "synthetic"
OUT = ROOT / "runs" / "workflow_policy_v1"
DOC_DIR = wt.DOC_DIR
N_CASES = wt.N_CASES
VARIANTS = {
    "workflow_loan_policyP": {"process": "loan", "model": "Loan_Application_3_timers", "variant": "P",
                              "pool": "Appraiser", "amount": 3, "runs": ["Run 13", "Run 14"], "seed_prefix": "policyP-loan"},
    "workflow_pharmacy_policyP": {"process": "pharmacy", "model": "Pharmacy_3_timers", "variant": "P",
                                  "pool": "Pharmacist", "amount": 2, "runs": ["Run 13", "Run 14"], "seed_prefix": "policyP-pharmacy"},
    "workflow_loan_policyH": {"process": "loan", "model": "Loan_Application_3_timers", "variant": "H",
                              "runs": ["Run 15", "Run 16"], "seed_prefix": "policyH-loan"},
    "workflow_pharmacy_policyH": {"process": "pharmacy", "model": "Pharmacy_3_timers", "variant": "H",
                                  "runs": ["Run 15", "Run 16"], "seed_prefix": "policyH-pharmacy"},
}
DEV_OF = {d: f"workflow_{v['process']}_dev" for d, v in VARIANTS.items()}

# H: (exact sentence or clause in the renderer's front matter, its rewording). Each must occur exactly once. The
# meaning of every rule is kept; the parameter paragraphs ("Workers." list, "Process.") are not touched.
REWORD = [
    ("This document records independent runs of one business process, ",
     "The runs recorded here are independent runs of a single business process, "),
    ("The process structure and its parameters come from a published simulation model.",
     "Its structure and parameters are taken from a published simulation model."),
    ("Each run is one fixed realization: every case's arrival time, every activity's required work, every wait and "
     "every route draw are fixed in advance and listed.",
     "A run is a single fixed realization: the arrival time of every case, the work each activity requires, every "
     "wait and every route draw are set in advance and listed."),
    ("The records are computed from those plans by the rules below, applied exactly.",
     "The rules below are applied exactly to those plans to compute the records."),
    ("Knowing the plans in advance is a condition of this benchmark, not a claim about real operations.",
     "That the plans are known in advance is a condition of this benchmark; it is not a claim about real operations."),
    ("The document is divided into chapters titled 'Run &lt;NN&gt;'. Runs are independent, and a question names its "
     "run by that title.",
     "Each chapter is titled 'Run &lt;NN&gt;', and a question refers to a run by this title. The runs do not depend "
     "on one another."),
    ("Each chapter has these sections.", "A chapter contains the following sections."),
    ("'Cases' gives each case's arrival time and end time.", "'Cases': the arrival time and end time of each case."),
    ("'Work plan' gives, for each case and activity, the work required on each visit.",
     "'Work plan': per case and activity, the work needed on each visit."),
    ("'Wait plan' gives, for each case and timed wait, the delay on each visit.",
     "'Wait plan': per case and timed wait, the delay on each visit."),
    ("'Route draws' gives, for each case and decision, the draw on each visit.",
     "'Route draws': per case and decision, the draw on each visit."),
    ("'Task log' records each performed activity. 'Wait log' records each wait. 'Decision log' records each decision.",
     "'Task log': one row for each time an activity is performed. 'Wait log': one row for each wait. 'Decision log': "
     "one row for each time a decision is made."),
    ("Plans list values for visits that did not happen, because a change could make them happen.",
     "The plans also give values for visits that did not take place, since a change could cause them to take place."),
    ("All times are whole seconds from time 0, which is a Monday at 00:00. Weekday = floor(t / 86400) mod 7, where 0 "
     "is Monday. An interval [a, b) includes a and excludes b.",
     "Every time is a whole number of seconds counted from time 0, a Monday at 00:00. The weekday of t is "
     "floor(t / 86400) mod 7, with 0 for Monday. An interval [a, b) contains a but not b."),
    ("Arrival times are given in 'Cases' and do not depend on other cases. A new case arriving at a stated time does "
     "not change other cases' plans.",
     "'Cases' lists the arrival times, and no case's arrival depends on any other case. If a new case arrives at a "
     "stated time, the plans of the other cases stay as they are."),
    ("Workers in a pool are interchangeable, and the assigned worker does not change how much work an activity needs.",
     "Any worker of a pool can take any of its tasks, and which worker is assigned does not affect the work an "
     "activity needs."),
    ("A <i>visit</i> counts how many times a case has reached an activity, wait or decision, starting at 1. Reaching "
     "an activity enables it. Passing through a decision, split or join takes no time.",
     "The <i>visit</i> number counts how often a case has reached an activity, wait or decision, beginning with 1. "
     "An activity is enabled when a case reaches it. A decision, split or join is passed through in zero time."),
    ("Enabled activities wait in one first-come-first-served line per pool, shared by all activities of that pool. "
     "Order: earliest enabled time, then the case that arrived earlier, then the lower case id, then the lower "
     "activity id, then the lower visit. Activity id order is fixed by the model and given by each activity's "
     "position in the 'Work plan' table.",
     "Each pool has a single first-come-first-served line, shared by all of its activities, in which enabled "
     "activities wait. The line is ordered by earliest enabled time; ties go to the case that arrived earlier, then "
     "to the lower case id, then to the lower activity id, then to the lower visit. The model fixes the order of "
     "activity ids, which is the order in which activities appear in the 'Work plan' table."),
    ("The task goes to the worker who can start it earliest. On a tie, the worker free for longest; on a further tie, "
     "the lower-numbered worker. A worker can start at the first time that is at or after both the enabled time and "
     "the time the worker is free, and within that worker's working hours.",
     "A task is given to the worker able to start it earliest. If several workers can start it at that same earliest "
     "time, the one that has been free for longest gets it, and if that also ties, the lower-numbered one. A worker's start time is the first time that "
     "is no earlier than the enabled time and no earlier than the time the worker is free, and that falls within "
     "that worker's working hours."),
    ("A worker does one task at a time and keeps it until it ends. Work counts only during working hours. Outside "
     "them the task pauses and resumes with the same worker, who stays held. A task that needs exactly the time left "
     "ends at closing time. If a worker is declared unavailable for an interval, that interval counts as non-working "
     "time in the same way.",
     "Each worker handles one task at a time and keeps it until it ends. Only working hours count as work. Outside "
     "working hours the task is paused, and it resumes with the same worker, who remains held by it. If a task needs "
     "exactly the remaining working time, it ends at closing time. An interval in which a worker is declared "
     "unavailable counts as non-working time in the same way."),
    ("A wait starts when reached and ends after its delay. It uses no worker and ignores working hours.",
     "A wait begins when it is reached and ends once its delay has passed. It needs no worker, and working hours do "
     "not apply to it."),
    ("Take the decision's routes in the listed order and add up their probabilities. The route taken is the first "
     "whose running total is greater than the draw for this case and visit. If a probability changes, the draw stays "
     "the same and the route is chosen again from the changed probabilities.",
     "Go through the decision's routes in the order listed, summing their probabilities. The case takes the first "
     "route at which this running sum is greater than its draw for that visit. When a probability is changed, the "
     "draw is kept and the route is chosen again from the changed probabilities."),
    ("A case ends when its last path reaches End. All cases run until they end.",
     "A case ends when its last path arrives at End. Every case runs until it ends."),
    ("Work and delays are in whole seconds. Draws are between 0 and 1, shown to 6 decimal places.",
     "Work and delays are whole seconds. Draws lie between 0 and 1 and are printed with 6 decimal places."),
]


def model_dir(doc):
    return OUT / f"root_{doc}" / SYN_REL


def register(rs):
    """replay_screen lookups for the variant documents (model files through a relative path). Lookup only, as
    workflow_test_set.register: never call it in a process that iterates rs.DOCS."""
    syn = ROOT / SYN_REL
    for doc, v in VARIANTS.items():
        rel = os.path.relpath(model_dir(doc) / v["model"], syn)
        rs.DOCS.setdefault(doc, {"model": rel, "seed_prefix": v["seed_prefix"]})
    return rs


def seed(doc, run):
    return f"{VARIANTS[doc]['seed_prefix']}-{run.split()[1]}"


def pdf(doc):
    return DOC_DIR / doc / "document.pdf"


def nav_path(doc):
    return DOC_DIR / doc / "navmap.json"


def load_nav(doc):
    if doc in VARIANTS:
        return json.loads(nav_path(doc).read_text(encoding="utf-8"))
    return wt.load_nav(doc)


def write_models():
    for doc, v in VARIANTS.items():
        d = model_dir(doc)
        d.mkdir(parents=True, exist_ok=True)
        src = ROOT / SYN_REL
        shutil.copyfile(src / f"{v['model']}.bpmn", d / f"{v['model']}.bpmn")
        if v["variant"] == "H":
            shutil.copyfile(src / f"{v['model']}.json", d / f"{v['model']}.json")
            continue
        params = json.loads((src / f"{v['model']}.json").read_text(encoding="utf-8"))
        hits = [r for prof in params["resource_profiles"] for r in prof["resource_list"] if r["name"] == v["pool"]]
        assert len(hits) == 1, (doc, v["pool"])
        old = hits[0]["amount"]
        hits[0]["amount"] = str(v["amount"]) if isinstance(old, str) else v["amount"]   # keep the file's own type
        (d / f"{v['model']}.json").write_bytes((json.dumps(params, indent=2) + "\n").encode("utf-8"))


def reworded_intro(original):
    """The renderer's own front matter, with REWORD applied. Each rewording must match exactly once."""
    def intro(model, labels, title):
        sep = "\x00"
        joined = sep.join(original(model, labels, title))
        for old, new in REWORD:
            assert joined.count(old) == 1, ("reword target not found exactly once", old[:60])
            joined = joined.replace(old, new)
        return joined.split(sep)
    return intro


def docs():
    import engine                       # noqa: F401  (imported from this project before render inserts any path)
    import render_workflow_doc as render
    from reportlab import rl_config
    from otf_r1 import navmap
    rl_config.invariant = 1
    todo = [doc for doc in VARIANTS if not (DOC_DIR / doc / "document.pdf").exists()]
    if not todo:
        raise SystemExit("every variant document exists; remove one by hand to re-render it")
    print("rendering", todo, "(existing documents are kept)")
    write_models()
    original = render.intro
    for doc, v in VARIANTS.items():
        out = DOC_DIR / doc
        if doc not in todo:
            continue
        render.intro = reworded_intro(original) if v["variant"] == "H" else original
        try:
            chapters = [(run, seed(doc, run), []) for run in v["runs"]]
            render.render(str(OUT / f"root_{doc}"), v["model"], str(out), chapters, N_CASES)
        finally:
            render.intro = original
        nav = navmap.build_map(out / "document.pdf")
        (out / "navmap.json").write_text(json.dumps(nav, indent=1), encoding="utf-8")
        print(doc, "pdf", wt.sha(out / "document.pdf"), "navmap", wt.sha(out / "navmap.json"))


def front_text(nav):
    f = next(n for n in nav["nodes"] if n["level"] == 0 and n["kind"] == "list")
    return " ".join(" ".join(f.get("lines", [])).split())


def check(out_path):
    import difflib
    import engine
    import render_workflow_doc as render
    import replay_screen as rs
    from otf_r1 import navmap
    from assurance import probes
    from assurance.request import schema_from_map
    wt.register(rs)
    register(rs)
    res = {"version": "workflow_policy_v1", "variants": {}, "checks": {}}
    all_titles = {}
    for doc in list(wt.DEV_OF.values()) + list(wt.TEST_DOCS):
        all_titles[doc] = wt._chapters(wt.load_nav(doc))
    bad = []
    for doc, v in VARIANTS.items():
        nav = load_nav(doc)
        dev = wt.load_nav(DEV_OF[doc])
        test = wt.load_nav(f"workflow_{v['process']}_test")
        s, sd, st = schema_from_map(nav), schema_from_map(dev), schema_from_map(test)
        bpmn, params = rs.model_files(str(ROOT), doc)
        src_b, src_p = ROOT / SYN_REL / f"{v['model']}.bpmn", ROOT / SYN_REL / f"{v['model']}.json"
        model, model_dev = engine.Model(bpmn, params), engine.Model(str(src_b), str(src_p))
        # which parameters differ from the published model
        pools_diff = {p: [model_dev.pools[p]["amount"], model.pools[p]["amount"]] for p in model.pools
                      if model.pools[p]["amount"] != model_dev.pools[p]["amount"]}
        same_other = (model.pools.keys() == model_dev.pools.keys()
                      and all(model.pools[p]["windows"] == model_dev.pools[p]["windows"] for p in model.pools)
                      and model.task_pool == model_dev.task_pool and model.branch == model_dev.branch
                      and {k: (d.name, d.params) for k, d in model.task_dist.items()} == {k: (d.name, d.params) for k, d in model_dev.task_dist.items()}
                      and {k: (d.name, d.params) for k, d in model.timer_dist.items()} == {k: (d.name, d.params) for k, d in model_dev.timer_dist.items()}
                      and model.arrival_windows == model_dev.arrival_windows
                      and (model.arrival_dist.name, model.arrival_dist.params) == (model_dev.arrival_dist.name, model_dev.arrival_dist.params))
        # every printed section equals the renderer's tables for the reference's factual run under these parameters
        labels, cycles, tabs = render.Labels(model, bpmn), render.in_cycle(model), wt._tables(nav)
        for r in v["runs"]:
            expect, _ = render.chapter_tables(engine, model, labels, cycles, rs.scenario(doc, r, {}), seed(doc, r))
            for section, rows, _w in expect:
                if [tuple(x) for x in rows[1:]] != tabs[(r, section)]:
                    bad.append([doc, r, section, "printed table differs from the reference"])
        # what the library reads from the front matter
        parsed = lambda x: {"pools": x.pools, "decisions": x.decisions, "activities": sorted(x.activities),
                            "waits": sorted(x.waits), "routes": probes.stated_routes(x),
                            "probabilities": probes.stated_probabilities(x), "calendars": probes.stated_pools(x)}
        pv, pdv = parsed(s), parsed(sd)
        library_diff = {k: [pdv[k], pv[k]] for k in pv if pv[k] != pdv[k] and k not in ("decisions",)}
        a, b = front_text(dev), front_text(nav)
        diff = [d for d in difflib.ndiff(a.replace(". ", ".\n").split("\n"), b.replace(". ", ".\n").split("\n")) if d[:1] in "+-"]
        res["variants"][doc] = {
            **{k: v[k] for k in ("process", "variant", "runs", "seed_prefix") if k in v},
            "seeds": [seed(doc, r) for r in v["runs"]],
            "pdf": str(pdf(doc).relative_to(ROOT)).replace("\\", "/"), "pdf_sha256": wt.sha(pdf(doc)),
            "navmap_sha256": wt.sha(nav_path(doc)),
            "document_meta_sha256": wt.sha(pdf(doc).parent / "document_meta.json"),
            "map_rebuilt_from_pdf_equals_stored": navmap.build_map(pdf(doc)) == nav,
            "model_files": {Path(bpmn).name: wt.sha(bpmn), Path(params).name: wt.sha(params)},
            "bpmn_equals_published": wt.sha(bpmn) == wt.sha(src_b),
            "params_equal_published": wt.sha(params) == wt.sha(src_p),
            "pool_amounts_changed": pools_diff, "all_other_parameters_equal": same_other,
            "library_reads_differ_from_dev": library_diff,
            "front_matter_lines_changed_vs_dev": diff,
            "fingerprint": s.policy_fingerprint(), "fingerprint_dev": sd.policy_fingerprint(),
            "fingerprint_test": st.policy_fingerprint(),
            "fingerprint_equals_dev": s.policy_fingerprint() == sd.policy_fingerprint()}
        titles = wt._chapters(nav)
        if titles != v["runs"]:
            bad.append([doc, "chapters", titles])
        for other, t in all_titles.items():      # titles must be unique within one process (scopes key reuse)
            if other.split("_")[1] == v["process"] and set(t) & set(titles):
                bad.append([doc, "shares titles with", other])
        all_titles[doc] = titles
        if v["variant"] == "P" and (list(pools_diff) != [v["pool"]] or not same_other):
            bad.append([doc, "P must change exactly one pool count", pools_diff, same_other])
        if v["variant"] == "H" and (pools_diff or not same_other or library_diff or not res["variants"][doc]["params_equal_published"]):
            bad.append([doc, "H must change no parameter and nothing the library reads", pools_diff, library_diff])
    sf = ROOT / "manifests" / "workflow_questions_policy_v1.shortfalls.json"
    res["question_shortfalls"] = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else None
    res["checks"] = {"problems": bad, "dev_equals_test_fingerprint": {
        p: schema_from_map(wt.load_nav(f"workflow_{p}_dev")).policy_fingerprint() == schema_from_map(wt.load_nav(f"workflow_{p}_test")).policy_fingerprint()
        for p in ("loan", "pharmacy")}}
    Path(out_path).write_text(json.dumps(res, indent=1), encoding="utf-8")
    for doc, r in res["variants"].items():
        print(doc, r["variant"], "pools changed", r["pool_amounts_changed"], "other params equal", r["all_other_parameters_equal"],
              "| library reads differ:", list(r["library_reads_differ_from_dev"]), "| front-matter lines changed:",
              len(r["front_matter_lines_changed_vs_dev"]), "| fingerprint equals dev:", r["fingerprint_equals_dev"])
    print("dev == test fingerprint:", res["checks"]["dev_equals_test_fingerprint"], "| problems:", len(bad))
    for b in bad:
        print("  ", b)
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1] == "docs":
        docs()
    elif sys.argv[1] == "check":
        sys.exit(check(sys.argv[2]))
    else:
        raise SystemExit(__doc__)
