"""Main-run analysis (new after the freeze; not a frozen file). Evaluation side: reads gold.

Reads the main runner's rows (`runs/main_v1/<set>/`), the question files (gold), and the judges' rows
(`<judges_dir>/<label>/judgments_*.jsonl`). Writes one JSON file and a markdown digest. Nothing here is fed back to
any system, gate or judge.

Scoring is the frozen scorer's: `main_summary.correct` (numbers within 1, booleans exactly), `main_summary.cohort`
and rule A (a row is answered only if it is trusted and the answer exists). Primary unit: one (set, program,
question) row with the interpreted request source and the structured answer path, for programs that are not
native-only. B0 (native-only) appears only on the OTF native path, as a reference.

Comparisons, all fixed before any test label was seen (written and checked on dev data and synthetic cases):

1. Rule-based judges on every row: ungated (`native` config), history check (`replay`), generic tests, schema,
   program-wide, disagreement-only (trust when the program's answer agrees with the vanilla reading answer, numbers
   within 1 or the same boolean), and our gate (`directed`). Matched random refusal at the gate's coverage: precision
   equal to the ungated precision, yield equal to the gate's coverage times it.
2. LLM judges at matched coverage. Within each cell (process | cohort), the judge takes the k rows with the highest
   confidence, k being the number the gate trusts in that cell; tied confidences at the cut give the expected
   precision under a random tie-break (exact, no draw). Larger groups are sums over their cells. Also each judge's
   own TRUST verdict, AUROC of its confidence, and its risk-coverage curve with the gate's point.
3. Uncertainty: two-level bootstrap (programs, then questions; question weights shared across the resampled
   programs), 2000 resamples, fixed seed. The coverage match is redone inside every resample. Gate-minus-judge
   differences are paired (same resample). Descriptive, not a guarantee: builds of one model are not independent.
4. Never pooled across builder classes: Claude-built and Ollama-built cells are reported apart. Groups are sums of
   cells within one class.

Usage: python -X utf8 scripts/main_analysis.py <root> <out_dir> [--judges-dir runs/judges_main_v1]
       [--main-sets wf_test,ml_test] [--policy-set wf_policy] [--boot 2000]
       python -X utf8 scripts/main_analysis.py --selftest
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

CONFIGS = ("native", "replay", "schema", "generic", "directed", "program_wide")
RULE_JUDGES = ("native", "replay", "generic", "schema", "program_wide", "disagreement", "directed")
TERMS = ("Trusted", "Caught", "Already caught", "Untestable", "Failed history check", "Can't express",
         "Request rejected", "Other")
SEED = 20261111


# ---------------------------------------------------------------- labels
def builder_class(program: str) -> str:
    p = program.split("/")
    if p[0] == "otf":
        return "claude" if p[2].startswith("claude-") else "ollama"
    if p[0] == "devs":
        return "claude" if p[1] in ("haiku", "sonnet") else "ollama"
    if p[0] == "agent":
        return "claude" if p[1].startswith("claude-") else "ollama"
    raise ValueError(program)


def platform(program: str) -> str:
    p = program.split("/")
    if p[0] == "otf":
        return "otf_b0" if p[1].startswith("b0") else "otf_r1"
    return p[0]


def builder_model(program: str) -> str:
    p = program.split("/")
    if p[0] == "otf":
        return p[2]
    if p[0] == "devs":
        return {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}.get(p[1], p[1])
    return p[1]


def model_family(model: str) -> str:
    return "claude" if model.startswith("claude") else model


def term(dec: dict, has_answer: bool) -> str:
    """Ashraf's plain term for a gate decision (the logic of scripts/pilot_attribution.py `cause`, plus rule A:
    a trusted row with no answer is Can't express). Library reason strings are left as they are."""
    if dec["permit"]:
        return "Trusted" if has_answer else "Can't express"
    r = dec.get("reason") or ""
    if dec.get("inexpressible"):
        return "Can't express"
    if dec.get("untested"):
        return "Untestable"
    if r.startswith("replay"):
        return "Failed history check"
    if r.startswith("contract") or r.startswith(("unparsable", "no_interpretation")):
        return "Request rejected"
    if "capability failed earlier" in r:      # also "exact-check …", "fill …", "blind-spot …" (review 1)
        return "Already caught"
    if r.startswith("backend_failed"):
        return "Other"
    if any(e[1] is False for e in (dec.get("evidence") or [])[1:]):
        return "Caught"
    return "Other"


# ---------------------------------------------------------------- matched coverage (point and bootstrap)
class Levels:
    """Rows of one cell grouped by confidence level, highest first."""

    def __init__(self, conf: np.ndarray):
        lv = np.unique(conf)[::-1]
        self.member = (conf[:, None] == lv[None, :]).astype(float)        # rows x levels


def matched_correct(w: np.ndarray, c: np.ndarray, g: np.ndarray, lev: Levels):
    """Expected correct rows when a judge takes, by descending confidence, the same weight of rows the gate trusts.
    w: (B, n) weights; c, g: (n,) 0/1 correct and gate-trusted. Returns (expected correct, taken weight), each (B,).
    Ties at the cut are taken in proportion (expected value under a random tie-break)."""
    target = w @ g                                                        # (B,)
    W = w @ lev.member                                                    # (B, L) weight per level
    C = (w * c) @ lev.member                                              # (B, L) correct weight per level
    cumW = np.cumsum(W, axis=1)
    cumC = np.cumsum(C, axis=1)
    L = W.shape[1]
    reach = cumW >= target[:, None] - 1e-9
    idx = np.where(reach.any(axis=1), reach.argmax(axis=1), L - 1)
    rows = np.arange(len(target))
    prevW = np.where(idx > 0, cumW[rows, np.maximum(idx - 1, 0)], 0.0)
    prevC = np.where(idx > 0, cumC[rows, np.maximum(idx - 1, 0)], 0.0)
    Wl, Cl = W[rows, idx], C[rows, idx]
    frac = np.where(Wl > 0, np.clip(target - prevW, 0, None) / np.where(Wl > 0, Wl, 1), 0.0)
    exp_c = np.where(target > 1e-12, prevC + frac * Cl, 0.0)
    return exp_c, target


def boot_weights(prog: np.ndarray, qid: np.ndarray, B: int, seed: int):
    """(B, n) row weights of the two-level bootstrap, plus the point weights (1, n) first."""
    rng = np.random.default_rng(seed)
    up, pi = np.unique(prog, return_inverse=True)
    uq, qi = np.unique(qid, return_inverse=True)
    wp = rng.multinomial(len(up), np.full(len(up), 1 / len(up)), size=B).astype(float)
    wq = rng.multinomial(len(uq), np.full(len(uq), 1 / len(uq)), size=B).astype(float)
    return wp[:, pi] * wq[:, qi]


def _ci(vals: np.ndarray):
    v = vals[~np.isnan(vals)]
    if not len(v):
        return None
    return {"ci95": [round(float(np.quantile(v, 0.025)), 4), round(float(np.quantile(v, 0.975)), 4)],
            "defined_share": round(len(v) / len(vals), 3), "share_above_0": round(float((v > 0).mean()), 3)}


def _div(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b > 1e-12, a / np.where(b > 1e-12, b, 1), np.nan)


def r4(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 4)


# ---------------------------------------------------------------- comparisons on a row table
def binary_stats(w, has, c, t):
    """coverage, precision, yield of a binary judge t (trust) under rule A (answered = trusted and has answer)."""
    a = t * has
    n, ans, cor = w.sum(axis=-1), w @ a, w @ (a * c)
    return _div(ans, n), _div(cor, ans), _div(cor, n)


def compare_rule_judges(tab: dict, idx: np.ndarray, B: int, seed: int) -> dict:
    """Every binary judge on these rows, with the gate, matched random refusal and paired gate-minus-judge yield and
    precision differences."""
    prog, qid, has, c = tab["prog"][idx], tab["qid"][idx], tab["has"][idx], tab["correct"][idx]
    W = np.vstack([np.ones((1, len(idx))), boot_weights(prog, qid, B, seed)])
    out = {"n": int(len(idx)), "programs": int(len(np.unique(prog))), "questions": int(len(np.unique(qid)))}
    g = tab["t_directed"][idx]
    gcov, gprec, gyld = binary_stats(W, has, c, g)
    ucov, uprec, uyld = binary_stats(W, has, c, np.ones(len(idx)))
    out["vanilla_row_share"] = r4(tab["vanilla_row"][idx].mean()) if len(idx) else None
    out["vanilla_answer_share"] = r4(tab["vanilla_answer"][idx].mean()) if len(idx) else None
    out["boolean_gold_rows"] = int(tab["bool_gold"][idx].sum())
    for name in RULE_JUDGES:
        t = tab[f"t_{name}"][idx]
        if name == "disagreement" and not tab["vanilla_row"][idx].any():
            out[name] = None                      # no reading rows: the comparator is not available (review 1)
            continue
        cov, prec, yld = binary_stats(W, has, c, t)
        a = t * has
        out[name] = {"coverage": r4(cov[0]), "precision": r4(prec[0]), "yield": r4(yld[0]),
                     "answered": int(a.sum()), "correct": int((a * c).sum()), "wrong": int((a * (1 - c)).sum()),
                     "coverage_ci": _ci(cov[1:]), "precision_ci": _ci(prec[1:]), "yield_ci": _ci(yld[1:])}
        if name != "directed":
            out[name]["gate_minus_this_yield"] = {"point": r4(gyld[0] - yld[0]), **(_ci(gyld[1:] - yld[1:]) or {})}
            out[name]["gate_minus_this_precision"] = {"point": r4(gprec[0] - prec[0]), **(_ci(gprec[1:] - prec[1:]) or {})}
    rand_prec, rand_yld = uprec, gcov * uprec
    out["matched_random_refusal"] = {"precision": r4(rand_prec[0]), "yield": r4(rand_yld[0]),
                                     "gate_minus_this_precision": {"point": r4(gprec[0] - rand_prec[0]), **(_ci(gprec[1:] - rand_prec[1:]) or {})},
                                     "gate_minus_this_yield": {"point": r4(gyld[0] - rand_yld[0]), **(_ci(gyld[1:] - rand_yld[1:]) or {})}}
    return out


def auroc(conf, c):
    pos, neg = conf[c == 1], conf[c == 0]
    if not len(pos) or not len(neg):
        return None
    allv = np.concatenate([pos, neg])
    ranks = _rank(allv)
    return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def _rank(x):
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x))
    xs = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and xs[j + 1] == xs[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def risk_coverage(conf, c, g):
    """Points (threshold, coverage, risk) of a confidence threshold over these rows (all have an answer), and the
    gate's own point."""
    pts = []
    n = len(conf)
    for t in np.unique(conf)[::-1]:
        m = conf >= t
        pts.append([float(t), round(m.sum() / n, 4), round(1 - c[m].mean(), 4)])
    gate = [None, round(g.sum() / n, 4), round(1 - c[g == 1].mean(), 4) if g.sum() else None]
    return {"points": pts, "gate": gate, "base_risk": round(1 - c.mean(), 4) if n else None}


def compare_llm_judge(tab: dict, idx: np.ndarray, conf: np.ndarray, trust: np.ndarray, B: int, seed: int) -> dict:
    """One LLM judge on rows `idx` (all with an answer), against the gate at matched coverage within each cell."""
    prog, qid, c, g, cell = tab["prog"][idx], tab["qid"][idx], tab["correct"][idx], tab["t_directed"][idx], tab["cell"][idx]
    W = np.vstack([np.ones((1, len(idx))), boot_weights(prog, qid, B, seed)])
    exp_c = np.zeros(W.shape[0])
    taken = np.zeros(W.shape[0])
    for cl in np.unique(cell):
        m = cell == cl
        e, k = matched_correct(W[:, m], c[m], g[m], Levels(conf[m]))
        exp_c += e
        taken += k
    n = W.sum(axis=1)
    g_cor, g_ans = W @ (g * c), W @ g
    j_cor, j_ans = W @ (trust * c), W @ trust
    m_prec, m_yld = _div(exp_c, taken), _div(exp_c, n)
    g_prec, g_yld, g_cov = _div(g_cor, g_ans), _div(g_cor, n), _div(g_ans, n)
    o_prec, o_yld, o_cov = _div(j_cor, j_ans), _div(j_cor, n), _div(j_ans, n)
    base = _div(W @ c, n)
    return {"n": int(len(idx)), "programs": int(len(np.unique(prog))), "wrong_rows": int((1 - c).sum()),
            "gate": {"coverage": r4(g_cov[0]), "precision": r4(g_prec[0]), "yield": r4(g_yld[0]),
                     "precision_ci": _ci(g_prec[1:]), "yield_ci": _ci(g_yld[1:])},
            "judge_matched": {"coverage": r4(g_cov[0]), "precision": r4(m_prec[0]), "yield": r4(m_yld[0]),
                              "precision_ci": _ci(m_prec[1:]), "yield_ci": _ci(m_yld[1:])},
            "judge_own_verdict": {"coverage": r4(o_cov[0]), "precision": r4(o_prec[0]), "yield": r4(o_yld[0]),
                                  "precision_ci": _ci(o_prec[1:]), "yield_ci": _ci(o_yld[1:]),
                                  "wrong_trusted": int((trust * (1 - c)).sum()), "right_declined": int(((1 - trust) * c).sum())},
            "matched_random_refusal": {"precision": r4(base[0]), "yield": r4(g_cov[0] * base[0])},
            "gate_minus_judge_matched_precision": {"point": r4(g_prec[0] - m_prec[0]), **(_ci(g_prec[1:] - m_prec[1:]) or {})},
            "gate_minus_judge_matched_yield": {"point": r4(g_yld[0] - m_yld[0]), **(_ci(g_yld[1:] - m_yld[1:]) or {})},
            "gate_minus_judge_own_yield": {"point": r4(g_yld[0] - o_yld[0]), **(_ci(g_yld[1:] - o_yld[1:]) or {})},
            "gate_minus_judge_own_precision": {"point": r4(g_prec[0] - o_prec[0]), **(_ci(g_prec[1:] - o_prec[1:]) or {})},
            "gate_wrong_trusted": int((g * (1 - c)).sum()),
            "auroc": r4(auroc(conf, c)) if auroc(conf, c) is not None else None,
            "risk_coverage": risk_coverage(conf, c, g)}


# ---------------------------------------------------------------- loading
def load_rows(root: Path, sets, mr, ms):
    """Every interpreted-source row of non-native-only programs (structured path), plus the OTF native-path rows,
    plus oracle rows (for interpretation diagnostics)."""
    rows, native_rows, oracle, failures, qinfo = [], [], {}, [], {}
    for s in sets:
        out = mr.OUT / s
        qs = {q["id"]: q for q in mr.questions(root, s)}
        for k, q in qs.items():
            qinfo[(s, k)] = q
        van = {r["key"]: r.get("answer") for r in ms.load_jsonl(out / "vanilla.jsonl")}
        rag = {r["key"]: r.get("answer") for r in ms.load_jsonl(out / "rag.jsonl")}
        for p in sorted((out / "programs").glob("*.jsonl")):
            for r in ms.load_jsonl(p):
                if str(r.get("key", "")).startswith("__program__"):
                    failures.append({"set": s, **{k: r.get(k) for k in ("key", "program", "error")}})
                    continue
                if "decisions" not in r or r.get("question") not in qs:
                    continue
                q = qs[r["question"]]
                prog = r["program"]
                coh = ms.cohort(prog)
                base = {"set": s, "program": prog, "question": r["question"], "qid": f"{s}|{r['question']}",
                        "process": r["process"], "cohort": coh, "cell": f"{r['process']}|{coh}",
                        "class": builder_class(prog), "platform": platform(prog), "builder": builder_model(prog),
                        "family": q["family"], "effectful": bool(q.get("effectful")), "variant": q.get("variant"),
                        "gold": q["gold"], "scope": (r.get("request") or {}).get("scope"), "request": r.get("request")}
                if r["source"] == "oracle":
                    oracle[(s, prog, r["question"])] = r
                    continue
                if r["source"] != "interpreted":
                    continue
                if coh.startswith("otf") and not r.get("native_skipped"):
                    for path in ("native", "native+binding"):
                        a = ms.path_answer(r, path)
                        native_rows.append({**base, "path": path, "answer": a, "has": a is not None,
                                            "correct": ms.correct(a, q["gold"]), "directed": (r["decisions"].get("directed") or {}).get("permit"),
                                            "native_status": (r.get("native") or {}).get("status")})
                if coh.startswith("otf/b0"):
                    continue
                a = ms.path_answer(r, "structured")
                rows.append({**base, "answer": a, "has": a is not None, "correct": ms.correct(a, q["gold"]),
                             "decisions": r["decisions"], "contract": r.get("contract"),
                             "vanilla": van.get(r["question"]), "rag": rag.get(r["question"]),
                             "vanilla_row": r["question"] in van, "bool_gold": isinstance(q["gold"], bool),
                             "agree_vanilla": a is not None and ms.correct(a, van.get(r["question"])),
                             "executions": {k: v.get("executions", 0) for k, v in r["decisions"].items()},
                             "actual_runs_so_far": r.get("actual_runs_so_far")})
    return rows, native_rows, oracle, failures, qinfo


def table(rows):
    """Arrays for the numeric comparisons."""
    # The matching cell includes the set, so policy rows never share a cell with test rows (review 1).
    t = {"prog": np.array([r["program"] for r in rows], dtype=object), "qid": np.array([r["qid"] for r in rows], dtype=object),
         "cell": np.array([f"{r['set']}|{r['cell']}" for r in rows], dtype=object),
         "has": np.array([float(r["has"]) for r in rows]), "correct": np.array([float(r["correct"]) for r in rows]),
         "vanilla_row": np.array([bool(r["vanilla_row"]) for r in rows]),
         "vanilla_answer": np.array([float(r["vanilla"] is not None) for r in rows]),
         "bool_gold": np.array([float(r["bool_gold"]) for r in rows])}
    for cfg in CONFIGS:
        t[f"t_{cfg}"] = np.array([float(bool((r["decisions"].get(cfg) or {}).get("permit"))) for r in rows])
    t["t_disagreement"] = np.array([float(r["agree_vanilla"]) for r in rows])
    return t


def groups_of(rows, cells_only=False):
    """{group name: row indices}: builder class, process x class, platform x class, and every cell. Never across classes."""
    g = defaultdict(list)
    for i, r in enumerate(rows):
        if not cells_only:
            g[f"class={r['class']}"].append(i)
            g[f"process={r['process']}|class={r['class']}"].append(i)
            g[f"platform={r['platform']}|class={r['class']}"].append(i)
            g[f"effectful={r['effectful']}|class={r['class']}"].append(i)   # no-effect controls apart (AGENTS.md)
        g[f"cell={r['cell']}"].append(i)
    return {k: np.array(v) for k, v in sorted(g.items())}


def load_judges(jdir: Path, sets=None):
    """{label: {"judge", "model", "rows": {key: judgment}}}, key = (set, program, question) or, for the program-level
    judge, (set, program, scope)."""
    runs = {}
    if not jdir.exists():
        return runs
    for d in [jdir] + sorted(p for p in jdir.iterdir() if p.is_dir()):    # the folder itself too (review 1)
        for f in sorted(d.glob("judgments_*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    j = json.loads(line)
                except ValueError:
                    continue
                if sets is not None and j.get("set") not in sets:   # keep the dev/test boundary (review 1)
                    continue
                lab = f"{d.name}|{j['judge']}|{j['model']}"
                run = runs.setdefault(lab, {"dir": d.name, "judge": j["judge"], "model": j["model"], "rows": {},
                                            "prompt_hashes": set(), "subsets": set()})
                run["prompt_hashes"].add(j.get("prompt_hash"))
                run["subsets"].add((j.get("subset"), j.get("subsets_sha256")))
                key = (j["set"], j["program"], j["scope"]) if j["judge"] == "program" else (j["set"], j["program"], j["question"])
                if key in run["rows"]:
                    run.setdefault("duplicates", 0)
                    run["duplicates"] += 1
                    continue
                run["rows"][key] = j
    return runs


def verdict_arrays(rows, idx, run):
    """(conf, trust, present) for rows idx under one judge run. A failure or a skipped row is DECLINE at
    confidence 0 (design); a row the run never judged is absent."""
    conf, trust, present = [], [], []
    for i in idx:
        r = rows[i]
        key = (r["set"], r["program"], r["scope"]) if run["judge"] == "program" else (r["set"], r["program"], r["question"])
        j = run["rows"].get(key)
        if j is None:
            conf.append(0.0); trust.append(0.0); present.append(False)
            continue
        present.append(True)
        if j.get("status") != "judged" or j.get("verdict") is None:
            conf.append(0.0); trust.append(0.0)
            continue
        conf.append(float(j.get("confidence") or 0)); trust.append(float(j.get("verdict") == "TRUST"))
    return np.array(conf), np.array(trust), np.array(present)


# ---------------------------------------------------------------- sections
def section_rule(rows, tab, B):
    out = {}
    for name, idx in groups_of(rows).items():
        out[name] = compare_rule_judges(tab, idx, B if not name.startswith("cell=") else 0, SEED)
    return out


def section_breakdowns(rows):
    """Per family (within class) and per program: every rule judge's coverage, precision, yield and wrong trusted."""
    def agg(rs):
        res = {"n": len(rs)}
        for name in RULE_JUDGES:
            if name == "disagreement":
                if not any(r["vanilla_row"] for r in rs):
                    res[name] = None                    # no reading rows: not available
                    continue
                t = [r["agree_vanilla"] for r in rs]
            else:
                t = [bool((r["decisions"].get(name) or {}).get("permit")) for r in rs]
            ans = [a and r["has"] for a, r in zip(t, rs)]
            cor = sum(a and r["correct"] for a, r in zip(ans, rs))
            na = sum(ans)
            res[name] = {"coverage": r4(na / len(rs)) if rs else None, "precision": r4(cor / na) if na else None,
                         "yield": r4(cor / len(rs)) if rs else None, "wrong": na - cor}
        return res
    fam, prog = defaultdict(list), defaultdict(list)
    for r in rows:
        fam[f"{r['class']}|{r['process']}|{r['family']}"].append(r)
        prog[r["program"]].append(r)
    return {"per_family": {k: agg(v) for k, v in sorted(fam.items())}, "per_program": {k: agg(v) for k, v in sorted(prog.items())}}


def section_native_path(native_rows):
    """OTF's own patch-and-replay answers (the platform's native path), per cell: ungated and gated by directed.
    B0 is native-only: this is its only appearance (a reference, never the method)."""
    out = defaultdict(lambda: defaultdict(Counter))
    for r in native_rows:
        c = out[r["cell"]][r["path"]]
        c["n"] += 1
        c["answered"] += r["has"]
        c["correct"] += r["has"] and r["correct"]
        if r["directed"] is not None and not r["cell"].split("|")[1].startswith("otf/b0"):
            c["gated_answered"] += bool(r["directed"]) and r["has"]
            c["gated_correct"] += bool(r["directed"]) and r["has"] and r["correct"]
    res = {}
    for cell, paths in sorted(out.items()):
        res[cell] = {}
        for p, c in paths.items():
            d = {k: int(v) for k, v in c.items()}
            d["coverage"] = r4(c["answered"] / c["n"]) if c["n"] else None
            d["precision"] = r4(c["correct"] / c["answered"]) if c["answered"] else None
            if "gated_answered" in c or not cell.split("|")[1].startswith("otf/b0"):
                d["gated_coverage"] = r4(c["gated_answered"] / c["n"]) if c["n"] else None
                d["gated_precision"] = r4(c["gated_correct"] / c["gated_answered"]) if c["gated_answered"] else None
            res[cell][p] = d
    return res


def section_natural_errors(rows, oracle):
    """Real programs' wrong answers (structured path, an answer exists, it is not gold): what the gate did, in the
    plain terms, and whether the interpreted request equalled the oracle request. Also right answers lost."""
    by = defaultdict(lambda: defaultdict(Counter))
    missed = []
    for r in rows:
        if not r["has"]:
            continue
        d = r["decisions"]["directed"]
        t = term(d, True)
        o = oracle.get((r["set"], r["program"], r["question"]))
        same = None if o is None else _norm_req(o.get("request")) == _norm_req(r["request"])
        kind = "wrong" if not r["correct"] else "right"
        for gname in (f"class={r['class']}", f"class={r['class']}|platform={r['platform']}",
                      f"class={r['class']}|process={r['process']}", f"class={r['class']}|family={r['family']}"):
            by[gname][kind][t] += 1
            if kind == "wrong":
                by[gname]["wrong_interp"]["interpretation exact" if same else ("interpretation differs" if same is False else "no oracle row")] += 1
        if kind == "wrong" and t == "Trusted":
            missed.append({"set": r["set"], "program": r["program"], "question": r["question"], "family": r["family"],
                           "answer": r["answer"], "gold": r["gold"], "interpretation_exact": same, "reason": d.get("reason"),
                           "evidence": [e[:2] + [str(e[2])[:120]] for e in (d.get("evidence") or [])]})
    return {"terms": {g: {k: dict(v) for k, v in d.items()} for g, d in sorted(by.items())}, "wrong_trusted_rows": missed}


def _norm_req(d):
    d = dict(d or {})
    d.pop("unresolved", None)
    return json.dumps(d, sort_keys=True, default=str)


def section_interpretation(rows, oracle, qinfo, correct):
    """Interpreted request equal to the oracle request, per question (once per question, as main_summary does), by
    set and family; and the gate under each source, per class (oracle is a labelled diagnostic only)."""
    per_q, no_request = {}, set()
    for r in rows:
        o = oracle.get((r["set"], r["program"], r["question"]))
        if o is not None and r["request"] is not None and o.get("request") is not None:
            per_q.setdefault((r["set"], r["question"]), _norm_req(o["request"]) == _norm_req(r["request"]))
        elif r["request"] is None:
            no_request.add((r["set"], r["question"]))
    by = defaultdict(Counter)
    for (s, q), ok in per_q.items():
        f = qinfo[(s, q)]["family"]
        for k in (s, f"{s}|{f}"):
            by[k]["of"] += 1
            by[k]["exact"] += ok
    for (s, q) in no_request - set(per_q):   # unparsable or missing interpretation: not exact, counted apart (review 1)
        for k in (s, f"{s}|{qinfo[(s, q)]['family']}"):
            by[k]["no_request"] += 1
    src = defaultdict(Counter)
    for r in rows:
        o = oracle.get((r["set"], r["program"], r["question"]))
        if o is None:
            continue
        oa = (o.get("structured") or {})
        oans = oa.get("answer") if oa.get("status") == "ran" else None
        for name, dec, ans, cor in (("interpreted", r["decisions"]["directed"], r["answer"], r["correct"]),
                                    ("oracle", o["decisions"]["directed"], oans, None)):
            if cor is None:
                cor = ans is not None and correct(ans, r["gold"])
            k = f"{r['set']}|class={r['class']}|{name}"
            src[k]["n"] += 1
            if dec["permit"] and ans is not None:
                src[k]["answered"] += 1
                src[k]["correct"] += bool(cor)
    srcd = {k: {**dict(v), "coverage": r4(v["answered"] / v["n"]), "precision": r4(v["correct"] / v["answered"]) if v["answered"] else None}
            for k, v in sorted(src.items())}
    return {"exact": {k: dict(v) for k, v in sorted(by.items())}, "gate_by_source": srcd}


def section_study_c(rows, root, mr, policy_set="wf_policy"):
    """Policy reuse (D20, D23). P is a real policy change, H a harmless rewording; each policy document has new runs
    (scopes) and its own policy fingerprint. Each program's policy registry starts as a copy of its final wf_test
    registry (`--registry-from wf_test`). Under the frozen rules a pass is reused only on the same scope, and a
    failure blocks the same (program, adapter, fingerprint, family, op) and target anywhere. What can carry over from
    test is therefore only a failure, and only where the fingerprint is unchanged.

    Reported per variant and class:
    - fingerprints: each policy document's against the test documents' (equal would mean carry-over is possible);
    - carry-over seen: policy decisions that cite a test-set scope (reused evidence or Already caught "on Run X");
    - for rows whose capability and target failed on test (`test_failed`): what the gate did now. On P, dropping
      the old failure is a correct invalidation; on H, it is an unnecessary one, and a wrong answer Trusted on such
      an H row is an error a fingerprint-agnostic registry would have blocked (a counterfactual, not a method run);
      a right answer Trusted there is coverage it would have lost;
    - missed invalidation: a P row decided on evidence recorded under the old policy (a cited test scope). Expected 0
      by construction; the count is the check;
    - re-checking cost: probe executions per row, and same-run reuse within the policy set."""
    pol = [r for r in rows if r["set"] == policy_set]
    if not pol:
        return None
    import re
    safe = lambda n: re.sub(r"[^A-Za-z0-9._-]+", "_", n)
    fps = {}
    for s in ("wf_test", policy_set):
        for d in sorted({q["doc"] for q in mr.questions(root, s)}):
            nav = mr.split_nav(root, d, mr.SETS[s][2])
            fps[d] = {"set": s, "fingerprint": mr.adapter(mr.process_of(d)).schema(nav).policy_fingerprint()}
    test_fps = {v["fingerprint"] for v in fps.values() if v["set"] == "wf_test"}
    test_scopes = {q["scope"] for q in mr.questions(root, "wf_test")}
    pol_scopes = {q["scope"] for q in mr.questions(root, policy_set)}
    if test_scopes & pol_scopes:          # the carry-over check reads scope names, so they must not repeat (review 1)
        raise SystemExit(f"test and policy scope names overlap: {sorted(test_scopes & pol_scopes)}")
    test_fail, prefix_ok, test_missing = {}, {}, []
    for prog in sorted({r["program"] for r in pol}):
        tp = mr.OUT / "wf_test" / "registries" / f"{safe(prog)}_interpreted.jsonl"
        pp = mr.OUT / policy_set / "registries" / f"{safe(prog)}_interpreted.jsonl"
        if not tp.exists():
            test_missing.append(prog)
        tl = [json.loads(l) for l in tp.read_text(encoding="utf-8").splitlines() if l.strip()] if tp.exists() else []
        pl = [json.loads(l) for l in pp.read_text(encoding="utf-8").splitlines() if l.strip()] if pp.exists() else []
        prefix_ok[prog] = pl[:len(tl)] == tl
        # key layout backend|program_hash|adapter|fingerprint|family|op; op is already bare for "op|exact" keys
        # (the key's own "|" splits it), so today's checks and the exact checks are both matched here.
        test_fail[prog] = {(e["key"].split("|")[4], e["key"].split("|")[5], str(e.get("target"))) for e in tl if e.get("passed") is False}
    scope_re = re.compile(r" on (Run \d+)")
    by = defaultdict(Counter)
    for r in pol:
        d = r["decisions"]["directed"]
        reason = d.get("reason") or ""
        req = r["request"] or {}
        iv = (req.get("interventions") or [{}])[0] if req.get("interventions") else {}
        cap = (str(iv.get("family")), str(iv.get("op")), str(iv.get("target")))
        failed_on_test = cap in test_fail.get(r["program"], set())
        cited = scope_re.findall(reason)
        t = term(d, r["has"])
        for kk in (f"variant={r['variant']}|class={r['class']}", f"variant={r['variant']}|class={r['class']}|platform={r['platform']}"):
            c = by[kk]
            c["n"] += 1
            c["answered"] += d["permit"] and r["has"]
            c["correct"] += d["permit"] and r["has"] and r["correct"]
            c["wrong_trusted"] += d["permit"] and r["has"] and not r["correct"]
            c["ungated_wrong"] += r["has"] and not r["correct"]
            c["executions"] += d.get("executions", 0)
            c["reused_same_run"] += reason.startswith("reused evidence")
            c[f"term {t}"] += 1
            c["cites_test_scope"] += any(s in test_scopes for s in cited)
            if failed_on_test:
                c["test_failed"] += 1
                c[f"test_failed term {t}"] += 1
                c["test_failed trusted wrong"] += t == "Trusted" and not r["correct"]
                c["test_failed trusted right"] += t == "Trusted" and r["correct"]
    res = {}
    for k, c in sorted(by.items()):
        res[k] = {**{a: int(b) for a, b in sorted(c.items())}, "coverage": r4(c["answered"] / c["n"]),
                  "precision": r4(c["correct"] / c["answered"]) if c["answered"] else None,
                  "executions_per_row": r4(c["executions"] / c["n"])}
    return {"fingerprints": fps,
            "policy_fingerprint_equals_a_test_fingerprint": {d: v["fingerprint"] in test_fps for d, v in fps.items() if v["set"] == policy_set},
            "policy_registry_starts_with_test_registry": {p: ok for p, ok in prefix_ok.items()},
            "test_registry_missing": test_missing,
            "missed_invalidations_P": sum(v.get("cites_test_scope", 0) for k, v in res.items() if k.startswith("variant=P") and k.count("|") == 1),
            "by_variant": res}


def expected_ids(run, idsets):
    """The rows a run was asked to judge: its frozen subset (from the judgments' own `subset` field), narrowed to the
    50-row draw for the Sonnet ReAct run. None for the program-level judge (every answered row)."""
    if run["judge"] == "program":
        return None
    names = {s for s, _ in run["subsets"] if s}
    if not names:
        return set()
    ids = set().union(*(set(idsets.get(n, [])) for n in names))   # nested subsets: the union is the largest (review 2)
    if "react50" in idsets and run["judge"] == "react" and run["model"].startswith("claude-sonnet"):
        ids &= set(idsets["react50"])                                # D29: Sonnet's ReAct judge saw the 50 only
    return {tuple(x.split("|", 2)) for x in ids}


def section_judges(rows, tab, runs, B, sets_main, idsets):
    """Every LLM judge run against the gate on its own rows (main sets), per group and per cell. Reports expected,
    judged and missing rows, so a run stopped early is visible (review 1)."""
    out = {}
    main_idx = np.array([i for i, r in enumerate(rows) if r["set"] in sets_main and r["has"]])
    for lab, run in sorted(runs.items()):
        exp = expected_ids(run, idsets)
        if run["judge"] == "program":
            idx = main_idx                                     # verdict per (program, chapter) applies to every row
        elif exp:
            idx = np.array([i for i in main_idx if (rows[i]["set"], rows[i]["program"], rows[i]["question"]) in exp])
        else:
            idx = np.array([i for i in main_idx if (rows[i]["set"], rows[i]["program"], rows[i]["question"]) in run["rows"]])
        if not len(idx):
            continue
        conf, trust, present = verdict_arrays(rows, idx, run)
        res = {"judge": run["judge"], "model": run["model"], "dir": run["dir"],
               "expected_ids_all_sets": None if exp is None else len(exp),
               "expected_ids_main_sets": None if exp is None else sum(1 for k in exp if k[0] in sets_main),
               "expected_rows_in_main_sets": int(len(idx)),
               "rows_with_judgment": int(present.sum()), "rows_without_judgment": int((~present).sum()),
               "expected_known": exp is None or bool(exp), "duplicates": run.get("duplicates", 0),
               "prompt_hashes": sorted(map(str, run["prompt_hashes"])), "subsets": sorted(map(str, run["subsets"])),
               "note": "n, coverage and yield here are over answered rows only (every judged row has an answer)",
               "groups": {}}
        sub_rows = [rows[i] for i in idx]
        for gname, gi in groups_of(sub_rows).items():
            keep = present[gi]
            gi = gi[keep]
            if not len(gi):
                continue
            res["groups"][gname] = compare_llm_judge(tab, idx[gi], conf[gi], trust[gi], B, SEED)
        out[lab] = res
    return out


def section_policy_judges(rows, tab, runs, B, policy_set="wf_policy"):
    """Judges on the policy set, by variant and class (Study C), against the gate."""
    out = {}
    for lab, run in sorted(runs.items()):
        idx = np.array([i for i, r in enumerate(rows) if r["set"] == policy_set and r["has"]
                        and (run["judge"] == "program" or (r["set"], r["program"], r["question"]) in run["rows"])])
        if not len(idx):
            continue
        conf, trust, present = verdict_arrays(rows, idx, run)
        g = defaultdict(list)
        for k, i in enumerate(idx):
            if present[k]:
                g[f"variant={rows[i]['variant']}|class={rows[i]['class']}"].append(k)
        out[lab] = {gn: compare_llm_judge(tab, idx[np.array(v)], conf[np.array(v)], trust[np.array(v)], B, SEED) for gn, v in sorted(g.items())}
    return out


def section_shared(rows, tab, runs, idsets: dict, B: int):
    """The same fixed rows for every model (the shared 150, and the 50 of them Sonnet's ReAct judge saw): every judge
    run restricted to them, against the gate, per builder class (never pooled across classes). Rows of all three
    test sets, as drawn. Also the rule-based judges on the same rows."""
    index = {(r["set"], r["program"], r["question"]): i for i, r in enumerate(rows)}
    out = {}
    for name, ids in idsets.items():
        keys = [tuple(x.split("|", 2)) for x in ids]
        idx_all = np.array([index[k] for k in keys if k in index and rows[index[k]]["has"]])
        res = {"ids": len(ids), "rows_found_with_answer": int(len(idx_all)), "runs": {}, "rule_judges": {}}
        cls = np.array([rows[i]["class"] for i in idx_all], dtype=object)
        for c in sorted(set(cls)):
            res["rule_judges"][f"class={c}"] = compare_rule_judges(tab, idx_all[cls == c], B, SEED)
        for lab, run in sorted(runs.items()):
            conf, trust, present = verdict_arrays(rows, idx_all, run)
            if not present.any():
                continue
            r = {"rows_with_judgment": int(present.sum()), "rows_without_judgment": int((~present).sum()), "groups": {}}
            for c in sorted(set(cls)):
                m = (cls == c) & present
                if m.any():
                    r["groups"][f"class={c}"] = compare_llm_judge(tab, idx_all[m], conf[m], trust[m], B, SEED)
            res["runs"][lab] = r
        out[name] = res
    return out


def section_agreement(rows, runs):
    """Self-agreement of a repeated judge run (same judge and model, two folders) on their shared rows; self-judging
    (judge model family vs builder family); the shared-subset comparison across models."""
    res = {"repeat": {}, "self_judging": {}}
    by_jm = defaultdict(list)
    for lab, run in runs.items():
        if run["judge"] != "program":
            by_jm[(run["judge"], run["model"])].append(lab)
    for (jg, mdl), labs in sorted(by_jm.items()):
        for i in range(len(labs)):
            for k in range(i + 1, len(labs)):
                a, b = runs[labs[i]]["rows"], runs[labs[k]]["rows"]
                shared = sorted(set(a) & set(b))
                if not shared:
                    continue
                # binary TRUST vs not (a failure or skip is DECLINE), for both agreement and kappa (review 1)
                va = [a[x].get("verdict") == "TRUST" and a[x].get("status") == "judged" for x in shared]
                vb = [b[x].get("verdict") == "TRUST" and b[x].get("status") == "judged" for x in shared]
                ca = np.array([float(a[x].get("confidence") or 0) for x in shared])
                cb = np.array([float(b[x].get("confidence") or 0) for x in shared])
                agree = sum(x == y for x, y in zip(va, vb)) / len(shared)
                pa = sum(va) / len(shared)
                pb = sum(vb) / len(shared)
                pe = pa * pb + (1 - pa) * (1 - pb)
                res["repeat"][f"{labs[i]} vs {labs[k]}"] = {
                    "rows": len(shared), "verdict_agreement": r4(agree), "kappa": r4((agree - pe) / (1 - pe)) if pe < 1 else None,
                    "trust_rate": [r4(pa), r4(pb)], "confidence_mean_abs_diff": r4(np.abs(ca - cb).mean()),
                    "confidence_pearson": r4(np.corrcoef(ca, cb)[0, 1]) if ca.std() > 0 and cb.std() > 0 else None,
                    "confidence_spearman": r4(np.corrcoef(_rank(ca), _rank(cb))[0, 1]) if ca.std() > 0 and cb.std() > 0 else None}
    rindex = {(r["set"], r["program"], r["question"]): r for r in rows}
    for lab, run in sorted(runs.items()):
        if run["judge"] == "program":
            continue
        c = defaultdict(Counter)
        for key, j in run["rows"].items():
            r = rindex.get(key)
            if r is None or not r["has"]:
                continue
            fam = model_family(run["model"])
            own = (model_family(r["builder"]) == fam)
            for gk in (f"builder={r['builder']}", f"builder_class={r['class']}", f"own_family={own}"):
                cc = c[gk]
                t = j.get("verdict") == "TRUST" and j.get("status") == "judged"
                cc["n"] += 1
                cc["right"] += r["correct"]
                cc["wrong"] += not r["correct"]
                cc["trust_right"] += t and r["correct"]
                cc["trust_wrong"] += t and not r["correct"]
        res["self_judging"][lab] = {k: {**dict(v), "trust_rate_on_right": r4(v["trust_right"] / v["right"]) if v["right"] else None,
                                        "trust_rate_on_wrong": r4(v["trust_wrong"] / v["wrong"]) if v["wrong"] else None}
                                    for k, v in sorted(c.items())}
    return res


def section_cost(rows, runs, root, sets):
    """Gate executions per row; judges' calls, tokens, dollars, time, turns; shared-stage calls from the ledger."""
    gate = defaultdict(lambda: defaultdict(list))
    for r in rows:
        for cfg, e in r["executions"].items():
            gate[f"{r['set']}|class={r['class']}"][cfg].append(e)
    g = {k: {cfg: {"per_row": r4(sum(v) / len(v)), "total": int(sum(v)), "rows": len(v)} for cfg, v in d.items()} for k, d in sorted(gate.items())}
    j = {}
    for lab, run in sorted(runs.items()):
        rs = [x for x in run["rows"].values() if x.get("status") == "judged"]
        if not rs:
            continue
        s = lambda k: sum((x.get(k) or 0) for x in rs)
        turns = Counter(str(x.get("turns")) for x in rs)
        j[lab] = {"rows": len(rs), "skipped": sum(x.get("status") == "skipped" for x in run["rows"].values()),
                  "model_calls": s("model_calls"), "failed_calls": s("failed_calls"), "prompt_tokens": s("prompt_tokens"),
                  "output_tokens": s("output_tokens"), "cache_read_tokens": s("cache_read_tokens"), "cache_write_tokens": s("cache_write_tokens"),
                  "usd": round(s("usd"), 4), "usd_per_row": r4(s("usd") / len(rs)), "wall_seconds": round(s("wall_seconds"), 1),
                  "wall_seconds_per_row": r4(s("wall_seconds") / len(rs)),
                  "failures": dict(Counter(x.get("failure") for x in rs if x.get("failure"))),
                  "inconsistent": sum(bool(x.get("inconsistent")) for x in rs)}
        if run["judge"] == "react":
            j[lab].update({"turns_histogram": dict(sorted(turns.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 99)),
                           "hit_turn_cap_without_verdict": sum(x.get("failure") == "out_of_turns" for x in rs),
                           "verdict_on_last_turn": sum(x.get("turns") == x.get("turn_cap") and not x.get("failure") for x in rs),
                           "sandbox_calls": s("sandbox_calls"), "program_executions": s("program_executions"),
                           "sandbox_seconds": round(s("sandbox_seconds"), 1),
                           "sandbox_differs_from_platform": sum(x.get("sandbox_matches_platform") is False for x in rs)})
    led = defaultdict(lambda: Counter())
    lp = root / "runs" / "build_test_main_claude" / "calls_claude-haiku-5-5.jsonl"
    for line in (lp.read_text(encoding="utf-8").splitlines() if lp.exists() else []):
        try:
            c = json.loads(line)
        except ValueError:
            continue
        b = str(c.get("build") or "").split("/")
        if len(b) >= 3 and b[0] == "main" and b[1] in sets:
            k = f"{b[1]}|{b[2]}"
            led[k]["calls"] += 1
            led[k]["usd"] += c.get("usd") or 0.0
            led[k]["prompt_tokens"] += c.get("prompt_tokens") or 0
            led[k]["output_tokens"] += c.get("output_tokens") or 0
            led[k]["seconds"] += c.get("seconds") or 0.0
    shared = {k: {a: (round(b, 4) if isinstance(b, float) else b) for a, b in v.items()} for k, v in sorted(led.items())}
    jl = defaultdict(float)
    for p in sorted((root / "runs" / "build_test_judges").glob("calls_*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                c = json.loads(line)
            except ValueError:
                continue
            b = str(c.get("build") or "")
            if b.startswith("judges/"):
                jl[f"{b.split('/')[1]}|{p.stem.removeprefix('calls_')}"] += c.get("usd") or 0.0
    return {"gate_executions": g, "judges": j, "shared_stage_ledger": shared,
            "judges_ledger_usd_by_folder_and_model": {k: round(v, 4) for k, v in sorted(jl.items())}}


# ---------------------------------------------------------------- markdown digest
def fmt(x):
    return "-" if x is None else (f"{x:.3f}" if isinstance(x, float) else str(x))


def ci(d):
    return "" if not d else f" [{d['ci95'][0]:.3f}, {d['ci95'][1]:.3f}]"


def digest(res) -> str:
    L = ["# Main-run analysis digest (generated by scripts/main_analysis.py)", ""]
    L.append("## Rule-based judges on every row (structured path, interpreted requests), main sets")
    L.append("")
    L.append("| group | n | progs | " + " | ".join(f"{k} cov/prec/yield" for k in RULE_JUDGES) + " | random@gate prec/yield |")
    L.append("|---|---|---|" + "---|" * (len(RULE_JUDGES) + 1))
    for g, d in res["rule_judges"].items():
        if g.startswith("cell="):
            continue
        cells = ["n/a" if d[k] is None else f"{fmt(d[k]['coverage'])}/{fmt(d[k]['precision'])}/{fmt(d[k]['yield'])} (w{d[k]['wrong']})" for k in RULE_JUDGES]
        L.append(f"| {g} | {d['n']} | {d['programs']} | " + " | ".join(cells) +
                 f" | {fmt(d['matched_random_refusal']['precision'])}/{fmt(d['matched_random_refusal']['yield'])} |")
    L.append("")
    L.append("Gate minus each judge, yield (paired bootstrap 95% interval):")
    L.append("")
    L.append("| group | " + " | ".join(k for k in RULE_JUDGES if k != "directed") + " | random |")
    L.append("|---|" + "---|" * len(RULE_JUDGES))
    for g, d in res["rule_judges"].items():
        if g.startswith("cell="):
            continue
        cells = ["n/a" if d[k] is None else f"{fmt(d[k]['gate_minus_this_yield']['point'])}{ci(d[k]['gate_minus_this_yield'] if 'ci95' in d[k]['gate_minus_this_yield'] else None)}"
                 for k in RULE_JUDGES if k != "directed"]
        rr = d["matched_random_refusal"]["gate_minus_this_yield"]
        L.append(f"| {g} | " + " | ".join(cells) + f" | {fmt(rr['point'])}{ci(rr if 'ci95' in rr else None)} |")
    L.append("")
    L.append("## LLM judges vs the gate (matched within cells)")
    L.append("")
    L.append("| run | group | n | wrong | gate prec | judge@matched prec | gate-judge prec | gate yield | judge@matched yield | judge own cov/prec/yield | gate-own yield | AUROC |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for lab, d in res["llm_judges"].items():
        for g, c in d["groups"].items():
            dp, dy = c["gate_minus_judge_matched_precision"], c["gate_minus_judge_own_yield"]
            o = c["judge_own_verdict"]
            L.append(f"| {lab} | {g} | {c['n']} | {c['wrong_rows']} | {fmt(c['gate']['precision'])} | {fmt(c['judge_matched']['precision'])} | "
                     f"{fmt(dp['point'])}{ci(dp if 'ci95' in dp else None)} | {fmt(c['gate']['yield'])} | {fmt(c['judge_matched']['yield'])} | "
                     f"{fmt(o['coverage'])}/{fmt(o['precision'])}/{fmt(o['yield'])} | {fmt(dy['point'])}{ci(dy if 'ci95' in dy else None)} | {fmt(c['auroc'])} |")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- main
def main(root: Path, out_dir: Path, judges_dir: Path, main_sets, policy_set, B: int, idsets: dict):
    sys.path[:0] = [str(root), str(root / "scripts")]
    sys.dont_write_bytecode = True
    import main_runner as mr
    import main_summary as ms
    sets = list(main_sets) + ([policy_set] if policy_set else [])
    rows, native_rows, oracle, failures, qinfo = load_rows(root, sets, mr, ms)
    main_rows = [r for r in rows if r["set"] in main_sets]
    res = {"what": __doc__.strip().splitlines()[0], "sets": sets, "bootstrap": B, "seed": SEED,
           "rows": {s: sum(r["set"] == s for r in rows) for s in sets}, "program_failures": failures}
    mtab = table(main_rows)
    res["rule_judges"] = section_rule(main_rows, mtab, B)
    res["breakdowns"] = section_breakdowns(main_rows)
    res["native_path"] = section_native_path([r for r in native_rows if r["set"] in main_sets])
    res["natural_errors"] = section_natural_errors(main_rows, oracle)
    res["interpretation"] = section_interpretation(rows, oracle, qinfo, ms.correct)
    runs = load_judges(judges_dir, set(sets))
    if judges_dir.exists() and not runs:
        print(f"WARNING: no judge runs for sets {sets} under {judges_dir}", flush=True)
    atab = table(rows)
    res["llm_judges"] = section_judges(rows, atab, runs, B, set(main_sets), idsets)
    shared = {k: idsets[v] for k, v in (("shared150", "answer_sonnet"), ("react50", "react50")) if v in idsets}
    res["shared_rows"] = section_shared(rows, atab, runs, shared, B)
    res["study_c"] = section_study_c(rows, root, mr, policy_set) if policy_set else None
    if res["study_c"] is not None:
        prow = [r for r in rows if r["set"] == policy_set]
        ptab = table(prow)
        res["study_c"]["rule_judges"] = {f"variant={v}|class={c}": compare_rule_judges(ptab, np.array([i for i, r in enumerate(prow) if r["variant"] == v and r["class"] == c]), B, SEED)
                                         for v in sorted({r["variant"] for r in prow}) for c in sorted({r["class"] for r in prow})
                                         if any(r["variant"] == v and r["class"] == c for r in prow)}
        res["study_c"]["llm_judges"] = section_policy_judges(rows, atab, runs, B, policy_set)
    res["agreement"] = section_agreement(rows, runs)
    res["cost"] = section_cost(rows, runs, root, sets)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "main_analysis.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    (out_dir / "main_analysis_digest.md").write_text(digest(res), encoding="utf-8")
    print(f"rows {res['rows']}; judge runs {len(runs)}; wrote {out_dir}")


# ---------------------------------------------------------------- self-test (synthetic, no project data)
def selftest():
    fails = 0

    def check(name, got, want, tol=1e-9):
        nonlocal fails
        ok = abs(got - want) <= tol
        fails += not ok
        print(("PASS " if ok else "FAIL ") + name, got, want)

    # one cell, 5 rows; gate trusts 2; judge confidences 90, 80, 80, 80, 10; correct 1, 0, 1, 1, 0
    c = np.array([1, 0, 1, 1, 0.]); g = np.array([1, 1, 0, 0, 0.]); conf = np.array([90, 80, 80, 80, 10.])
    e, k = matched_correct(np.ones((1, 5)), c, g, Levels(conf))
    check("ties: takes 90 then 1 of 3 tied (2 of 3 correct)", float(e[0]), 1 + 2 / 3)
    check("taken equals gate count", float(k[0]), 2)
    g0 = np.zeros(5)
    e, k = matched_correct(np.ones((1, 5)), c, g0, Levels(conf))
    check("gate trusts none: judge takes none", float(e[0]), 0)
    gall = np.ones(5)
    e, k = matched_correct(np.ones((1, 5)), c, gall, Levels(conf))
    check("gate trusts all: judge takes all", float(e[0]), 3)
    w = np.array([[2, 1, 1, 1, 1.]])
    e, k = matched_correct(w, c, g, Levels(conf))
    check("weights: gate weight 3, row 1 weight 2 then 1 of tied weight 3", float(e[0]), 2 + 2 / 3)
    allsame = np.array([50, 50, 50, 50, 50.])
    e, k = matched_correct(np.ones((1, 5)), c, g, Levels(allsame))
    check("all tied: expected precision equals base rate", float(e[0]) / 2, 3 / 5)
    # AUROC
    check("auroc perfect", auroc(np.array([3, 2, 1.]), np.array([1, 1, 0.])), 1.0)
    check("auroc ties", auroc(np.array([1, 1.]), np.array([1, 0.])), 0.5)
    # bootstrap weights: point unaffected; each resample sums to programs x questions per row pairing
    w = boot_weights(np.array(["a", "a", "b"], dtype=object), np.array(["q1", "q2", "q1"], dtype=object), 50, 1)
    check("boot weights shape", w.shape[0], 50)
    # terms
    check("term trusted", float(term({"permit": True}, True) == "Trusted"), 1)
    check("term cant express (rule A)", float(term({"permit": True}, False) == "Can't express"), 1)
    check("term history", float(term({"permit": False, "reason": "replay: 3 of 5 case ends differ"}, True) == "Failed history check"), 1)
    check("term already", float(term({"permit": False, "reason": "capability failed earlier for x"}, True) == "Already caught"), 1)
    check("term caught", float(term({"permit": False, "reason": "directed: c1 differs", "evidence": [["replay", True, ""], ["input_use", False, ""]]}, True) == "Caught"), 1)
    check("term untestable", float(term({"permit": False, "reason": "directed: no probe could be run", "untested": True}, True) == "Untestable"), 1)
    check("term inexpressible", float(term({"permit": False, "reason": "directed: no probe", "inexpressible": True}, True) == "Can't express"), 1)
    for pre in ("exact-check ", "fill ", "blind-spot "):
        check(f"term already ({pre.strip()})", float(term({"permit": False, "reason": pre + "capability failed earlier for x on Run 06",
                                                           "evidence": [["replay", True, ""]]}, True) == "Already caught"), 1)
    # compare_llm_judge: two cells; matching stays inside each cell
    tab = {"prog": np.array(["p1", "p1", "p2", "p2"], dtype=object), "qid": np.array(["a", "b", "a", "b"], dtype=object),
           "cell": np.array(["x", "x", "y", "y"], dtype=object), "correct": np.array([1, 0, 0, 1.]), "t_directed": np.array([1, 0, 0, 1.])}
    r = compare_llm_judge(tab, np.arange(4), np.array([10, 90, 90, 10.]), np.array([0, 1, 1, 0.]), 20, 1)
    check("per-cell match: judge takes its top row in each cell (both wrong)", r["judge_matched"]["precision"], 0.0)
    check("gate precision", r["gate"]["precision"], 1.0)
    check("judge own verdict wrong trusted", r["judge_own_verdict"]["wrong_trusted"], 2)
    check("builder class", float(builder_class("otf/b0/gpt-oss-120b/x/b1") == "ollama" and builder_class("devs/sonnet/X/run_01") == "claude"
                                 and builder_class("otf/r1_claude/claude-haiku-5-5/x/b1") == "claude"), 1)
    print(f"{fails} failures")
    return fails


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        sys.exit(1 if selftest() else 0)
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("out_dir")
    ap.add_argument("--judges-dir", default="runs/judges_main_v1")
    ap.add_argument("--main-sets", default="wf_test,ml_test")
    ap.add_argument("--policy-set", default="wf_policy")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--subsets", default=None, help="frozen judge subsets file; its answer_sonnet ids are the shared rows")
    ap.add_argument("--react50", default=None, help="the Sonnet ReAct draw file of scripts/draw_react50.py (its `ids`: set|program|question)")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    idsets = {}
    if a.subsets:
        idsets.update({k: v["ids"] for k, v in json.loads((root / a.subsets).read_text(encoding="utf-8"))["subsets"].items()})
    if a.react50:
        idsets["react50"] = json.loads((root / a.react50).read_text(encoding="utf-8"))["ids"]
    main(root, Path(a.out_dir), root / a.judges_dir, a.main_sets.split(","), a.policy_set or None, a.boot, idsets)
