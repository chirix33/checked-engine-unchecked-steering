"""Score the development pilot. Evaluation side: this is the only place gold is read.

A correct answer is exactly the gold case end, in whole seconds. For each backend, request source, answer path and
policy configuration, per program, then pooled:

- coverage: share of questions the policy permits and the path then answers;
- precision: correct among those answered;
- yield: correct answers per question, with declined questions abstained (`abstain`) or answered by the reading
  fallback (`fallback_vanilla`, `fallback_rag`);
- matched random refusal: the expected precision if the same coverage were reached by refusing at random from the
  ungated (`native` config) answers of the same path, which is that path's ungated precision;
- cost: program executions made by probes, per question.

Answer paths: `structured` (the structured request applied by the adapter) and, on OTF, `native` (the program's own
LLM patch) and `native+binding` (native, with the binding check able to reject). On OTF, `native` gated by a
policy is "gate only"; `structured` gated is "interpretation plus assurance"; `structured` under `native` config is
"interpretation only". Uncertainty: percentile bootstrap over programs (programs are the independent units, not
questions), 2000 resamples, fixed seed.

Usage: python -X utf8 scripts/pilot_summary.py <project_root> <out_json>
"""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

CONFIGS = ("native", "replay", "schema", "generic", "directed", "program_wide")


def load_jsonl(p: Path):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def correct(a, gold):
    return a is not None and gold is not None and abs(a - gold) < 1


def path_answer(row, path):
    if path == "structured":
        s = row.get("structured") or {}
        return s.get("answer") if s.get("status") == "ran" else None
    n = row.get("native") or {}
    if n.get("status") != "ran":
        return None
    if path == "native+binding":
        b = n.get("binding_check")
        return n.get("answer") if b and b[0] else None
    return n.get("answer")


def boot(per_program: dict, stat, n=2000, seed=7):
    """Two-level percentile bootstrap: resample programs, then questions (shared across the resampled programs).
    Builds of one model on one specification are not independent (D17), so this is descriptive, not a guarantee.
    Returns the interval and the share of resamples where the statistic was defined."""
    keys = sorted(per_program)
    if not keys:
        return None
    qids = sorted({i["qid"] for v in per_program.values() for i in v})
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        progs = [rng.choice(keys) for _ in keys]
        qw = {}
        for _ in qids:
            q = rng.choice(qids)
            qw[q] = qw.get(q, 0) + 1
        sample = [[i for i in per_program[p] for _ in range(qw.get(i["qid"], 0))] for p in progs]
        v = stat(sample)
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    vals.sort()
    return {"ci95": [round(vals[int(0.025 * len(vals))], 4), round(vals[int(0.975 * len(vals)) - 1], 4)],
            "defined_share": round(len(vals) / n, 3)}


def _ratio(xs):
    return round(sum(xs) / len(xs), 4) if xs else None


def cohort(program: str) -> str:
    """backend/engine/model: B0 apart from R1, and every model its own cohort (D16, D18)."""
    parts = program.split("/")
    return "/".join(parts[:3]) if parts[0] == "otf" else f"devs/{parts[1]}"


def main(root, out_path, exclude_path=None, run_dir="pilot_v1"):
    root = Path(root)
    out = root / "runs" / run_dir
    qs = {q["id"]: q for q in json.loads((root / "manifests" / "pilot_questions_v1.json").read_text(encoding="utf-8"))}
    # optional: question ids to leave out (e.g. questions failing the deterministic-realization rule), as a JSON list
    excluded = set(json.loads(Path(exclude_path).read_text(encoding="utf-8"))) if exclude_path else set()
    summary_run_dir = run_dir
    assert excluded <= set(qs), sorted(excluded - set(qs))
    qs = {k: v for k, v in qs.items() if k not in excluded}
    reading = {k: {r["key"]: r.get("answer") for r in load_jsonl(out / f"{k}.jsonl")} for k in ("vanilla", "rag")}
    interp = {r["key"]: r for r in load_jsonl(out / "interpret.jsonl")}
    rows = [r for p in sorted((out / "programs").glob("*.jsonl")) for r in load_jsonl(p)
            if r.get("key") != "__program__" and r.get("question") not in excluded]

    summary = {"questions": len(qs), "run_dir": summary_run_dir, "excluded": sorted(excluded), "programs": sorted({r["program"] for r in rows}), "rows": len(rows)}
    # reading comparators alone
    summary["reading"] = {k: {"answered": sum(v.get(q) is not None for q in qs), "correct": sum(correct(v.get(q), qs[q]["gold"]) for q in qs)}
                          for k, v in reading.items()}
    # interpretation quality against the hidden binding (evaluation only)
    def interp_ok(qid):
        r = interp.get(qid)
        if not r:
            return None
        req, b = r["request"], qs[qid]["binding"]
        if req.get("unresolved") or len(req.get("interventions") or []) != 1:
            return False
        iv = req["interventions"][0]
        op = b.get("op", {"activity_duration": "set", "timer_delay": "set", "routing_outcome": "set_draw",
                          "routing_probability": "set"}.get(b["family"]))
        same = (iv["family"] == b["family"] and iv.get("op") == op and req["scope"] == qs[qid]["scope"]
                and req["query"]["case"] == qs[qid]["query_case"] and req["query"].get("kind") == "case_end_time"
                and req["query"].get("deadline") is None)
        for k in ("effective_from", "effective_to"):
            got, want = iv.get(k), b.get(k)
            if op == "add_workers" and k == "effective_from":
                got, want = got or 0, want or 0      # the contract treats a start of 0 as "throughout"
            if got != want:
                same = False
        for k in ("case", "target", "visit"):
            if b.get(k) is not None and iv.get(k) != b.get(k):
                same = False
        if b.get("value") is not None and (iv.get("value") is None or abs(float(iv["value"]) - float(b["value"])) > 1e-6):
            same = False
        if b.get("routes") and iv.get("routes") != b.get("routes"):
            same = False
        return same
    summary["interpretation_exact"] = {"exact": sum(1 for q in qs if interp_ok(q)), "of": sum(1 for q in qs if q in interp)}

    summary["reading_missing"] = {k: sum(1 for q in qs if q not in v) for k, v in reading.items()}
    groups = defaultdict(lambda: defaultdict(list))   # (cohort, source, path, config) -> program -> list of outcomes
    for r in rows:
        q = qs[r["question"]]
        backend = cohort(r["program"])
        native_only = backend.startswith("otf/b0/")
        paths = ([] if native_only else ["structured"]) + (
            ["native", "native+binding"] if backend.startswith("otf") and r["source"] == "interpreted" else [])
        for path in paths:
            for cfg, d in r["decisions"].items():
                a = path_answer(r, path)
                permitted = d["permit"]
                answered = permitted and a is not None
                fb = {k: reading[k].get(q["id"]) for k in reading}
                have = {k: q["id"] in reading[k] for k in reading}
                groups[(backend, r["source"], path, cfg)][r["program"]].append({
                    "qid": q["id"], "have_vanilla": have["vanilla"], "have_rag": have["rag"],
                    "family": q["family"], "effectful": q["effectful"], "answered": answered, "correct": answered and correct(a, q["gold"]),
                    "wrong": answered and not correct(a, q["gold"]), "executions": d.get("executions", 0),
                    "fallback_vanilla": correct(a, q["gold"]) if answered else correct(fb["vanilla"], q["gold"]),
                    "fallback_rag": correct(a, q["gold"]) if answered else correct(fb["rag"], q["gold"]),
                    "untested": d.get("untested"), "inexpressible": d.get("inexpressible")})

    def agg(items):
        n = len(items)
        ans = sum(i["answered"] for i in items)
        cor = sum(i["correct"] for i in items)
        return {"n": n, "answered": ans, "correct": cor, "wrong": sum(i["wrong"] for i in items),
                "coverage": round(ans / n, 4) if n else None, "precision": round(cor / ans, 4) if ans else None,
                "yield_abstain": round(cor / n, 4) if n else None,
                # fallback yields over one shared question set for every config: questions whose reading answer exists
                "yield_fallback_vanilla": _ratio([i["fallback_vanilla"] for i in items if i["have_vanilla"]]),
                "yield_fallback_rag": _ratio([i["fallback_rag"] for i in items if i["have_rag"]]),
                "fallback_n": {"vanilla": sum(i["have_vanilla"] for i in items), "rag": sum(i["have_rag"] for i in items)},
                "executions_per_question": round(sum(i["executions"] for i in items) / n, 3) if n else None,
                "untested": sum(bool(i["untested"]) for i in items), "inexpressible": sum(bool(i["inexpressible"]) for i in items)}

    table = []
    for (backend, src, path, cfg), per_prog in sorted(groups.items()):
        pooled = [i for v in per_prog.values() for i in v]
        a = agg(pooled)
        base = groups.get((backend, src, path, "native"))
        if base:
            b = agg([i for v in base.values() for i in v])
            a["matched_random_refusal_precision"] = b["precision"]
        flat = {p: v for p, v in per_prog.items()}
        a["precision_ci_programs"] = boot(flat, lambda s: (lambda x: x["precision"])(agg([i for v in s for i in v])))
        a["yield_ci_programs"] = boot(flat, lambda s: agg([i for v in s for i in v])["yield_abstain"])
        a["per_family"] = {f: agg([i for i in pooled if i["family"] == f]) for f in sorted({i["family"] for i in pooled})}
        a["no_effect_controls"] = agg([i for i in pooled if not i["effectful"]])
        a["per_program"] = {p: {k: agg(v)[k] for k in ("n", "answered", "correct", "wrong")} for p, v in sorted(per_prog.items())}
        table.append({"backend": backend, "source": src, "path": path, "config": cfg, **a})
    summary["table"] = table
    Path(out_path).write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"{'cohort':34} {'source':11} {'path':15} {'config':13} {'cov':>6} {'prec':>6} {'rand':>6} {'yield':>6} {'+van':>6} {'+rag':>6} {'exec/q':>6}")
    for t in table:
        f = lambda x: "-" if x is None else f"{x:.3f}"
        print(f"{t['backend']:34} {t['source']:11} {t['path']:15} {t['config']:13} {f(t['coverage']):>6} {f(t['precision']):>6} "
              f"{f(t.get('matched_random_refusal_precision')):>6} {f(t['yield_abstain']):>6} {f(t['yield_fallback_vanilla']):>6} "
              f"{f(t['yield_fallback_rag']):>6} {f(t['executions_per_question']):>6}")
    print("reading:", summary["reading"], "interpretation exact:", summary["interpretation_exact"])


if __name__ == "__main__":
    main(*sys.argv[1:5])   # root out_json [exclude_json|''] [run_dir under runs/]
