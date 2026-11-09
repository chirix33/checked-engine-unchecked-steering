"""Counterfactual questions for manufacturing and IT operations, with gold (evaluation-only, never shown to a system).

New questions on the MLSys documents (MLSys's own multiple-choice items are not reused). Each question states one
change in the document's own names and asks for one number (or yes/no) about one product-day or one task. Gold
comes from the pinned reference simulator on raw-rebuilt chapters and windows, and is kept only if MLSys's
independent re-implementation, fed only from the PDF, gives exactly the same value (`mlsys_gold.py`).

Selection follows a fixed rule and seed, decided before any method is run on these questions, and never looks at
any program. Per family, about one question in five is a valid no-effect control (same quota rule as
`make_pilot_questions.py`). Splits follow `manifests/mlsys_splits_v1.json`: dev questions are half on chapters or
windows of the build document (seen at build) and half on unseen dev ones; test questions are all on unseen test
chapters or windows. Queries ask about days or tasks at or after the change, so no-effect controls are not
trivially before the change.

Fields follow `manifests/pilot_questions_v1.json` (id, doc, scope, family, gold, factual_end, effectful, question,
text, interventions, query_case, binding), plus: domain, split, seen_at_build, query (structured), gold_reimpl.
`interventions` are the pinned simulators' own change dicts; `binding` is the hidden request in library style.

Usage: python -X utf8 scripts/make_mlsys_questions.py <splits_json> <out_dev_json> <out_test_json> <seed>
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mlsys_gold as G  # noqa: E402

FAMILIES = {"manufacturing": ["order_removal", "production_quantity", "production_timing", "dispatch_capacity"],
            "it_ops": ["job_removal", "failure_removal", "task_priority", "task_request", "machine_removal"]}
PER_FAMILY = {"dev": 12, "test": 24}
SHORT = {"manufacturing": "mfg", "it_ops": "itops"}


# ---------------------------------------------------------------- manufacturing
def mfg_query(rng, s, product, day):
    kind = rng.choice(["stock_end_of_day", "backordered_end_of_day"])
    q = {"kind": kind, "product": product, "day": day}
    what = "be in stock" if kind == "stock_end_of_day" else "be backordered"
    return q, f"How many units of {product} would {what} at the end of day {day}?"


def mfg_draft(family, rng, s):
    T, days, prods = s.title, s.days, s.products
    pick_q = lambda p, d: (p if rng.random() < 0.75 else rng.choice(prods), rng.randint(d, s.last_day))
    if family == "order_removal":
        cands = [(p, d) for d in days for p in prods if s.orders[d][p] > 0]
        if not cands:
            return None
        p, d = rng.choice(cands)
        qp, qd = pick_q(p, d)
        return ([{"kind": "remove_order", "product": p, "day": d}],
                {"family": family, "op": "remove", "target": p, "day": d},
                f"In {T}, suppose the order for {p} placed on day {d} had not been placed.", qp, qd)
    if family == "production_quantity":
        p, d = rng.choice(prods), rng.choice(days)
        cur = s.production[d][p]
        mean = round(sum(s.orders[x][p] for x in days) / len(days))
        options = sorted({v for v in (0, 2 * cur, cur // 2, cur + max(mean, 1)) if v != cur and v >= 0})
        if not options:
            return None
        v = rng.choice(options)
        qp, qd = pick_q(p, d)
        return ([{"kind": "set_production", "product": p, "day": d, "value": v}],
                {"family": family, "op": "set", "target": p, "day": d, "value": v},
                f"In {T}, suppose {v} units of {p} had been produced on day {d} (instead of the recorded {cur}).", qp, qd)
    if family == "production_timing":
        cands = [(p, d) for d in days for p in prods if s.production[d][p] > 0]
        if not cands:
            return None
        p, d = rng.choice(cands)
        k = rng.choice([1, 2, 3])
        qp, qd = pick_q(p, d)
        return ([{"kind": "delay_production", "product": p, "day": d, "by": k}],
                {"family": family, "op": "delay", "target": p, "day": d, "value": k},
                f"In {T}, suppose the production of {p} on day {d} had arrived {k} day{'s' if k > 1 else ''} later, "
                f"on day {d + k}, instead of on day {d}.", qp, qd)
    if family == "dispatch_capacity":
        f = rng.choice([0.5, 0.8, 1.2])
        d = s.first_day if rng.random() < 0.5 else rng.randint(s.first_day + 1, s.last_day)
        kg = s.capacity_kg * f
        qp, qd = rng.choice(prods), rng.randint(d, s.last_day)
        return ([{"kind": "scale_capacity", "factor": f, "from_day": d}],
                {"family": family, "op": "scale", "day": d, "value": f},
                f"In {T}, suppose the daily dispatch capacity had been {round(f * 100)}% of its stated value "
                f"({kg:g} kg instead of {s.capacity_kg} kg) on every day from day {d} on.", qp, qd)
    raise ValueError(family)


# ---------------------------------------------------------------- IT operations
def it_query(rng, w, task, factual):
    if rng.random() < 0.75 or factual is None:
        return ({"kind": "task_start_time", "task": task},
                f"At what time, in seconds from the window start, would task {task} first start?")
    return ({"kind": "task_starts_by", "task": task, "deadline": factual},
            f"Would task {task} first start at or before time {factual}? Answer yes or no.")


def it_draft(family, rng, w, f_starts):
    T = w.title
    tasks = {t.tid: t for t in w.tasks}
    started = [t for t in tasks if f_starts.get(t) is not None]

    def later(t0, exclude=()):
        c = [t for t in started if f_starts[t] >= t0 and t not in exclude]
        return rng.choice(c) if c else None

    if family == "job_removal":
        job = rng.choice(sorted({t.job for t in w.tasks}))
        mine = {t.tid for t in w.tasks if t.job == job}
        q = later(min(tasks[t].submit for t in mine), mine)
        if q is None:
            return None
        return ([{"kind": "remove_job", "job": job}], {"family": family, "op": "remove", "target": job},
                f"In {T}, suppose job {job} had never been submitted (none of its tasks).", q)
    if family == "failure_removal":
        down = [m for m in w.machines if m.down is not None and m.down <= w.length]
        if not down:
            return None
        m = rng.choice(down)
        q = later(m.down)
        if q is None:
            return None
        return ([{"kind": "remove_failure", "machine": m.mid}], {"family": family, "op": "remove", "target": m.mid},
                f"In {T}, suppose machine {m.mid} had not failed during the window.", q)
    if family == "task_priority":
        x = rng.choice(started)
        p = rng.choice([v for v in (0, 1, 5, 9, 11) if v != tasks[x].priority])
        q = x if rng.random() < 0.7 else later(tasks[x].submit, {x})
        if q is None:
            return None
        return ([{"kind": "set_priority", "task": x, "value": p}], {"family": family, "op": "set", "target": x, "value": p},
                f"In {T}, suppose task {x} had priority {p} (instead of {tasks[x].priority}).", q)
    if family == "task_request":
        x = rng.choice(started)
        res = rng.choice(["cpu", "mem"])
        cur = getattr(tasks[x], res)
        v = max(1, round(cur * rng.choice([0.5, 2])))
        other = tasks[x].mem if res == "cpu" else tasks[x].cpu
        if v == cur or not any((m.cpu >= v and m.mem >= other) if res == "cpu" else (m.mem >= v and m.cpu >= other)
                               for m in w.machines):
            return None
        q = x if rng.random() < 0.7 else later(tasks[x].submit, {x})
        if q is None:
            return None
        name = "CPU" if res == "cpu" else "memory"
        return ([{"kind": "set_request", "task": x, "resource": res, "value": v}],
                {"family": family, "op": "set", "target": x, "resource": res, "value": v},
                f"In {T}, suppose task {x} had requested {v} units of {name} (instead of {cur}).", q)
    if family == "machine_removal":
        m = rng.choice([m.mid for m in w.machines])
        q = rng.choice(started)
        return ([{"kind": "remove_machine", "machine": m}], {"family": family, "op": "remove", "target": m},
                f"In {T}, suppose machine {m} had not been part of the cluster.", q)
    raise ValueError(family)


# ---------------------------------------------------------------- driver
def make(domain, split, splits, rng, stats):
    chapters = splits[domain]
    pool = [t for t, v in chapters.items() if v["split"] == split]
    seen = [t for t in pool if chapters[t]["seen_at_build"]]
    unseen = [t for t in pool if not chapters[t]["seen_at_build"]]
    n = PER_FAMILY[split]
    want_noeffect = max(1, n // 5)
    out = []
    factual = {}
    for family in FAMILIES[domain]:
        made = noeffect = tries = 0
        while made < n and tries < 3000:
            tries += 1
            if split == "dev":
                title = rng.choice(seen if made % 2 == 0 else unseen)
            else:
                title = rng.choice(unseen)
            if domain == "manufacturing":
                s = G.scope(domain, title)
                d = mfg_draft(family, rng, s)
                if d is None:
                    continue
                changes, binding, text, qp, qd = d
                query, qtext = mfg_query(rng, s, qp, qd)
                if title not in factual:
                    factual[title] = G.mfg_rows_sim(title, [])
                f_val = G.mfg_value(factual[title], query)
                entity = qp
            else:
                w = G.scope(domain, title)
                if title not in factual:
                    factual[title] = G.it_starts_sim(title, [])
                d = it_draft(family, rng, w, factual[title])
                if d is None:
                    continue
                changes, binding, text, q_task = d
                query, qtext = it_query(rng, w, q_task, factual[title].get(q_task))
                f_val = G.it_value(factual[title], query)
                entity = q_task
            g_sim, g_ref = G.gold(domain, title, changes, query)
            if (g_sim is None) != (g_ref is None):
                stats["gold_disagreement"] += 1            # one reference has an answer, the other none (review 1)
                stats["disagreements"].append({"scope": title, "changes": changes, "query": query, "sim": g_sim, "ref": g_ref})
                continue
            if g_sim is None:
                stats["no_answer"] += 1                    # queried task removed or never starts, in both
                continue
            if g_sim != g_ref:
                stats["gold_disagreement"] += 1
                stats["disagreements"].append({"scope": title, "changes": changes, "query": query, "sim": g_sim, "ref": g_ref})
                continue
            effect = g_sim != f_val
            if not effect and noeffect >= want_noeffect:
                continue
            if effect and made - noeffect >= n - want_noeffect:
                continue
            noeffect += not effect
            qid = f"{SHORT[domain]}-{split}-{family}-{made:02d}"
            out.append({"id": qid, "domain": domain, "split": split, "doc": chapters[title]["doc"], "scope": title,
                        "seen_at_build": chapters[title]["seen_at_build"], "family": family,
                        "gold": g_sim, "gold_reimpl": g_ref, "factual_end": f_val, "effectful": effect,
                        "question": f"{text} {qtext}", "text": text, "interventions": changes,
                        "query_case": entity, "query": query, "binding": binding})
            made += 1
        stats["made"][f"{domain}/{split}/{family}"] = [made, noeffect, tries]
    return out


def main(splits_path, out_dev, out_test, seed):
    splits = json.loads(Path(splits_path).read_text(encoding="utf-8"))
    rng = random.Random(int(seed))
    stats = {"no_answer": 0, "gold_disagreement": 0, "disagreements": [], "made": {}}
    files = {"dev": out_dev, "test": out_test}
    for split in ("dev", "test"):
        qs = []
        for domain in ("manufacturing", "it_ops"):
            qs += make(domain, split, splits, rng, stats)
        Path(files[split]).write_text(json.dumps(qs, indent=1), encoding="utf-8")
        print(split, len(qs), Counter(q["domain"] for q in qs), "no-effect", sum(not q["effectful"] for q in qs),
              "seen at build", sum(q["seen_at_build"] for q in qs))
    print(json.dumps({k: v for k, v in stats.items() if k != "disagreements"}, indent=0))
    if stats["disagreements"]:
        print("DISAGREEMENTS", json.dumps(stats["disagreements"][:5]))


if __name__ == "__main__":
    main(*sys.argv[1:5])
