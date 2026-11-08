"""Development pilot questions with gold from the reference engine (evaluation-only, never shown to a system).

Family-balanced, on the 4 development runs of each workflow document. Each question states one change in the
document's own names and asks when a case ends. Gold, the hidden binding and an effect label come from the
reference. Selection follows a fixed rule and seed, decided before any method is run on these questions. About
one question in five per family is a valid no-effect change.

Deterministic realization (added 2026-11-07 after review): a question is kept only if every draw the reference uses
under the change is printed in the document (Work plan, Wait plan, Route draws) or set by the question itself.
Otherwise its gold cannot be derived from the document, for the query case or for another case that can reach it
through shared workers. `undocumented_draws` reproduces the renderer's rule for which draws are printed.
Limitation: Work plan and Wait plan print durations, not the underlying draws, and a printed duration counts as a
documented draw here. That is right for the set, scale, remove and add changes used now. It would be wrong for a
change that redraws from a new distribution.

pilot_questions_v1.json was made by the earlier version, without this filter. That version is this file minus the
`undocumented_draws` skip in `main`. With the filter, the same seed keeps different drafts.

Usage: python -X utf8 scripts/make_pilot_questions.py <project_root> <out_json> <per_family_per_doc> <seed>
"""
import json
import os
import random
import sys

HOUR = 3600
MIN_VISITS = 3          # must equal render_workflow_doc.MIN_VISITS
VARIABLE = {"task": "service", "intermediateCatchEvent": "timer"}


def printed_draws(base, model, cycles):
    """(case, element, visit, variable) for every draw the document prints, following
    render_workflow_doc.chapter_tables: elements in a cycle get visits 1..depth, all others visit 1."""
    observed = {}
    for t in base["tasks"]:
        observed[t["task"]] = max(observed.get(t["task"], 0), t["visit"])
    for t in base["timers"]:
        observed[t["timer"]] = max(observed.get(t["timer"], 0), t["visit"])
    for b in base["branches"]:
        observed[b["gateway"]] = max(observed.get(b["gateway"], 0), b["visit"])
    depth = max([MIN_VISITS] + [v + 1 for v in observed.values()])
    out = set()
    for c in base["cases"]:
        for e, k in model.kind.items():
            var = VARIABLE.get(k) or ("branch" if model.is_branching(e) else None)
            if var is None:
                continue
            for v in (range(1, depth + 1) if e in cycles else [1]):
                out.add((c["case"], e, v, var))
    return out


def undocumented_draws(base, out, model, cycles, q):
    over = {(o["case"], o["element"], o["visit"], o["variable"]) for o in q.get("draw_overrides", [])}
    need = {(d["case"], d["element"], d["visit"], d["variable"]) for d in out["draws"]}
    return need - printed_draws(base, model, cycles) - over


def main(root, out_path, per_family, seed):
    per_family = int(per_family)
    root = os.path.abspath(root)
    sys.path[:0] = [os.path.join(root, "scripts"), os.path.join(root, "reference_engine")]
    import replay_screen as rs
    import render_workflow_doc as render
    assert render.MIN_VISITS == MIN_VISITS, "printed_draws must follow the renderer"
    rng = random.Random(int(seed))
    questions = []
    for doc in rs.DOCS:
        bpmn, params = rs.model_files(root, doc)
        import engine
        model = engine.Model(bpmn, params)
        labels = render.Labels(model, bpmn)
        lab = labels.label
        cycles = render.in_cycle(model)
        name_of = {v: k for k, v in lab.items()}
        per_run = {run: rs.reference(root, doc, run, {})[2] for run in rs.RUNS}
        families = ["activity_duration", "timer_delay", "routing_outcome", "routing_probability", "resource_availability", "case_set"]
        for family in families:
            made, tries = 0, 0
            want_noeffect = max(1, per_family // 5)
            noeffect = 0
            while made < per_family and tries < 400:
                tries += 1
                run = rng.choice(rs.RUNS)
                base = per_run[run]
                ends = {c["case"]: c["end"] for c in base["cases"]}
                q = draft(family, rng, base, model, labels, cycles, run, render, engine)
                if q is None:
                    continue
                _, _, out = rs.reference(root, doc, run, {"interventions": q["interventions"], "draw_overrides": q.get("draw_overrides", [])})
                new_ends = {c["case"]: c["end"] for c in out["cases"]}
                case = q["query_case"]
                if case not in new_ends:
                    continue
                if undocumented_draws(base, out, model, cycles, q):
                    continue                # gold not derivable from the document (deterministic-realization rule)
                effect = new_ends[case] != ends.get(case)
                if not effect and noeffect >= want_noeffect:
                    continue
                if effect and made - noeffect >= per_family - want_noeffect:
                    continue
                noeffect += not effect
                q.update({"id": f"{doc[9:12]}-{family}-{made:02d}", "doc": doc, "scope": run, "family": family,
                          "gold": new_ends[case], "factual_end": ends.get(case), "effectful": effect,
                          "question": q["text"] + f" At what time, in seconds from time 0, would case {case} end?"})
                questions.append(q)
                made += 1
            print(doc, family, made, "questions,", noeffect, "no-effect")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, indent=1)
    print(len(questions), "questions")


def draft(family, rng, base, model, labels, cycles, run, render, engine):
    lab = labels.label
    cases = [c["case"] for c in base["cases"]]
    if family == "activity_duration":
        t = rng.choice(base["tasks"])
        new = rng.choice([1, t["service"] + HOUR, t["service"] * 2])
        visit = t["visit"] if rng.random() < 0.85 else t["visit"] + 2       # some changes at visits that don't happen
        return {"interventions": [{"type": "duration_set", "task": t["task"], "seconds": int(new), "selector": {"case": t["case"], "visit": visit}}],
                "query_case": t["case"],
                "text": f"In {run}, suppose case {t['case']} needed {int(new)} seconds of work for the activity '{lab[t['task']]}' on visit {visit}.",
                "binding": {"family": "activity_duration", "case": t["case"], "target": lab[t["task"]], "visit": visit, "value": int(new)}}
    if family == "timer_delay":
        if not base["timers"]:
            return None
        t = rng.choice(base["timers"])
        new = rng.choice([0, t["delay"] + HOUR, t["delay"] * 2])
        return {"interventions": [{"type": "timer_set", "timer": t["timer"], "seconds": int(new), "selector": {"case": t["case"], "visit": t["visit"]}}],
                "query_case": t["case"],
                "text": f"In {run}, suppose the wait {lab[t['timer']]} for case {t['case']} lasted {int(new)} seconds on visit {t['visit']}.",
                "binding": {"family": "timer_delay", "case": t["case"], "target": lab[t["timer"]], "visit": t["visit"], "value": int(new)}}
    if family == "routing_outcome":
        b = rng.choice(base["branches"])
        routes = labels.routes(b["gateway"])
        options = [f for f, p in model.branch[b["gateway"]] if f != b["flow"] and p > 0]
        if not options:
            return None
        to = rng.choice(options)
        low = 0
        for f, p in model.branch[b["gateway"]]:
            if f == to:
                u = float(low + p / 2)
                break
            low += p
        return {"interventions": [], "draw_overrides": [{"case": b["case"], "element": b["gateway"], "visit": b["visit"], "variable": "branch", "u": str(u)}],
                "query_case": b["case"],
                "text": f"In {run}, suppose the route draw for case {b['case']} at decision {lab[b['gateway']]} on visit {b['visit']} were {u:.6f}.",
                "binding": {"family": "routing_outcome", "case": b["case"], "target": lab[b["gateway"]], "visit": b["visit"], "value": round(u, 6)}}
    if family == "routing_probability":
        gws = sorted({b["gateway"] for b in base["branches"]})
        g = rng.choice(gws)
        flows = [f for f, _ in model.branch[g]]
        p = rng.choice([0.1, 0.3, 0.5, 0.7, 0.9])
        probs = {flows[0]: str(p), flows[1]: str(round(1 - p, 10))}
        for f in flows[2:]:
            probs[f] = "0"
        routes = labels.routes(g)
        case = rng.choice(sorted({b["case"] for b in base["branches"] if b["gateway"] == g}))
        text = ", ".join(f"route {routes[f]} {float(v):g}" for f, v in probs.items())
        return {"interventions": [{"type": "routing_set", "gateway": g, "probabilities": probs}], "query_case": case,
                "text": f"In {run}, suppose decision {lab[g]} used the probabilities {text}.",
                "binding": {"family": "routing_probability", "target": lab[g], "routes": {routes[f]: float(v) for f, v in probs.items()}}}
    if family == "resource_availability":
        pools = [p for p in model.pools if model.pools[p]["amount"] >= 1]
        pool = rng.choice(pools)
        case = rng.choice(cases)
        if rng.random() < 0.5:
            k = rng.choice([1, 2])
            return {"interventions": [{"type": "resource_add", "pool": pool, "count": k, "from": 0}], "query_case": case,
                    "text": f"In {run}, suppose the pool {pool} had {k} more worker{'s' if k > 1 else ''} throughout.",
                    "binding": {"family": "resource_availability", "op": "add_workers", "target": pool, "value": k}}
        n = model.pools[pool]["amount"]
        k = rng.choice([1, 2]) if n >= 2 else 1
        starts = sorted(t["start"] for t in base["tasks"] if model.task_pool[t["task"]] == pool)
        if not starts:
            return None
        t0 = (starts[len(starts) // 3] // HOUR) * HOUR
        t1 = t0 + rng.choice([2, 4, 8]) * HOUR
        return {"interventions": [{"type": "resource_unavailable", "pool": pool, "count": k, "from": t0, "to": t1}], "query_case": case,
                "text": f"In {run}, suppose {k} {pool} worker{'s were' if k > 1 else ' was'} unavailable from time {t0} to time {t1}.",
                "binding": {"family": "resource_availability", "op": "unavailable", "target": pool, "value": k, "effective_from": t0, "effective_to": t1}}
    if family == "case_set":
        if len(cases) < 3:
            return None
        gone, case = rng.sample(cases, 2)
        return {"interventions": [{"type": "case_remove", "case": gone}], "query_case": case,
                "text": f"In {run}, suppose case {gone} had never arrived.",
                "binding": {"family": "case_set", "op": "remove", "case": gone}}
    return None


if __name__ == "__main__":
    main(*sys.argv[1:5])
