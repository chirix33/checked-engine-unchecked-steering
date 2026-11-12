"""Per-domain tables: platform x judge, with the gate's decisions in Ashraf's plain terms (post-freeze reporting view).

Reuses the reviewed functions of scripts/main_analysis.py (row loading, plain terms, rule-judge and LLM-judge
comparisons, bootstrap) and only regroups rows by domain (process) x platform x builder class. Claude-built and
Ollama-built programs are never pooled. Nothing here changes a frozen file or a decision; it is a reporting view.

usage: python -X utf8 scripts/domain_tables.py <root> <out_dir> --sets wf_test,ml_test [--judges-dir runs/judges_main_v1
       --subsets manifests/judge_subsets_main_v1.json --react50 manifests/judge_subsets_main_v1_react_sonnet50.json] [--boot 2000]
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
import main_analysis as ma  # noqa: E402

PLAIN = ("Trusted", "Caught", "Already caught", "Untestable", "Failed history check", "Can't express", "Request rejected", "Other")
BASE = ("native", "replay", "generic", "schema", "program_wide", "disagreement")
LLM_RUNS = ("main_answer_haiku|answer|claude-haiku-5-5", "main_program_haiku|program|claude-haiku-5-5",
            "main_react_haiku|react|claude-haiku-5-5")
DOMAIN_ORDER = ("manufacturing", "it_ops", "loan", "pharmacy")
PLAT_ORDER = ("otf_r1|claude", "devs|claude", "agent|claude", "all|claude", "otf_r1|ollama")
PLAT_NAME = {"otf_r1|claude": "OTF-R1, Claude-built", "devs|claude": "DEVS-Gen, Claude-built", "agent|claude": "Coding agent, Claude-built",
             "all|claude": "All Claude-built", "otf_r1|ollama": "OTF-R1, Ollama-built"}


def name(k):
    """Display name of a 'domain|platform|class' key (no pipes, so markdown columns stay aligned: review fix)."""
    return PLAT_NAME[k.split("|", 1)[1]]


def groups(rows, idx=None):
    """{(domain, platform|class): row indices}. 'all|claude' pools the Claude-built platforms only."""
    g = defaultdict(list)
    for i in (range(len(rows)) if idx is None else idx):
        r = rows[i]
        g[(r["process"], f"{r['platform']}|{r['class']}")].append(i)
        if r["class"] == "claude":
            g[(r["process"], "all|claude")].append(i)
    return {k: np.array(v) for k, v in g.items()}


def plain_terms(rows, idx):
    """Gate decisions on answered rows, right and wrong apart, plus rows with no answer."""
    c = {"right": Counter(), "wrong": Counter(), "no_answer": 0}
    for i in idx:
        r = rows[i]
        if not r["has"]:
            c["no_answer"] += 1
            continue
        c["wrong" if not r["correct"] else "right"][ma.term(r["decisions"]["directed"], True)] += 1
    return {"right": dict(c["right"]), "wrong": dict(c["wrong"]), "no_answer": c["no_answer"]}


def llm_section(rows, tab, runs, idsets, sets, B):
    out = {}
    main_idx = np.array([i for i, r in enumerate(rows) if r["set"] in sets and r["has"]])
    for lab in LLM_RUNS:
        run = runs.get(lab)
        if run is None:
            continue
        exp = ma.expected_ids(run, idsets)
        if run["judge"] == "program":
            idx = main_idx
        elif exp:
            idx = np.array([i for i in main_idx if (rows[i]["set"], rows[i]["program"], rows[i]["question"]) in exp])
        else:
            idx = np.array([i for i in main_idx if (rows[i]["set"], rows[i]["program"], rows[i]["question"]) in run["rows"]])
        conf, trust, present = ma.verdict_arrays(rows, idx, run)
        res = {}
        for key, gi in groups(rows, idx).items():
            # gi are row indices; map back to positions in idx
            pos = np.searchsorted(idx, gi)
            pos = pos[present[pos]]
            if not len(pos):
                continue
            res["|".join(key)] = ma.compare_llm_judge(tab, idx[pos], conf[pos], trust[pos], B, ma.SEED)
        out[lab] = res
    return out


def main(root, out_dir, sets, judges_dir, idsets, B):
    sys.path[:0] = [str(root), str(root / "scripts")]
    import main_runner as mr
    import main_summary as ms
    rows, _, _, failures, _ = ma.load_rows(root, sets, mr, ms)
    tab = ma.table(rows)
    res = {"what": __doc__.strip().splitlines()[0], "sets": sets, "rows": len(rows), "bootstrap": B, "seed": ma.SEED,
           "program_failures": len(failures), "groups": {}}
    for key, idx in sorted(groups(rows).items()):
        res["groups"]["|".join(key)] = {"rule": ma.compare_rule_judges(tab, idx, B, ma.SEED), "terms": plain_terms(rows, idx)}
    if judges_dir is not None and judges_dir.exists():
        runs = ma.load_judges(judges_dir, set(sets))
        res["llm"] = llm_section(rows, tab, runs, idsets, set(sets), B)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "domain_tables.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    (out_dir / "domain_tables.md").write_text(render(res), encoding="utf-8")
    print(f"rows {len(rows)}; groups {len(res['groups'])}; wrote {out_dir}")


def f3(x):
    return "-" if x is None else f"{x:.3f}"


def ci(d):
    if not d:
        return "-"
    p = d.get("point")
    lo, hi = (d.get("ci95") or [None, None])
    s = "-" if p is None else f"{p:+.3f}"
    return s if lo is None else f"{s} [{lo:.3f}, {hi:.3f}]"


def sign(d):
    """+ if the 95% interval of (gate - judge) is above 0, - if below, 0 if it includes 0, ? if undefined.
    Intervals are rounded to 4 decimals first, so a bound of 0.0000 counts as including 0 (conservative)."""
    if not d or not d.get("ci95"):
        return "?"
    lo, hi = d["ci95"]
    return "+" if lo > 0 else ("-" if hi < 0 else "0")


def pair(p, y):
    return f"{sign(p)}{sign(y)}"


def summary(res):
    G, L = res["groups"], res.get("llm") or {}
    lab3 = [lab.split("|")[1] for lab in LLM_RUNS]
    cols = list(BASE) + ([f"{j} at gate coverage" for j in lab3] + [f"{j}, own verdict" for j in lab3] if L else [])
    n_llm = {lab.split("|")[1]: sum(v["n"] for k, v in (L.get(lab) or {}).items() if not k.split("|", 1)[1].startswith("all|")) for lab in LLM_RUNS}
    out = ["## Summary: gate against each judge, by domain and platform", "",
           "Each cell has two signs, for precision and then yield, from the paired 95% interval of (gate - judge): "
           "+ = gate significantly higher, - = gate significantly lower, 0 = interval includes 0, ? = undefined (a side kept no rows). "
           "So '+0' means the gate is more precise with no significant yield difference; '+-' means more precise but fewer correct answers kept. "
           "Brackets give wrong answers kept: for rule-based judges, judge then gate over the same rows; for LLM columns, judge then gate over the rows that judge saw. "
           "native and schema make identical decisions here, and replay and program_wide nearly so: they are not independent comparisons.", "",
           "| domain | platform | rows | gate yield | " + " | ".join(cols) + " |", "|---|---|---|---|" + "---|" * len(cols)]
    for dom in DOMAIN_ORDER:
        for p in PLAT_ORDER:
            k = f"{dom}|{p}"
            if k not in G:
                continue
            r = G[k]["rule"]
            gw = r["directed"]["wrong"]
            if not r["directed"]["answered"] and not any((r.get(j) or {}).get("answered") for j in BASE):
                out.append(f"| {dom} | {name(k)} | {r['n']} | {f3(r['directed']['yield'])} | " + " | ".join(["n/a (no answers)"] + ["n/a"] * (len(cols) - 1)) + " |")
                continue
            cells = []
            for j in BASE:
                v = r.get(j)
                cells.append("n/a" if v is None else f"{pair(v.get('gate_minus_this_precision'), v.get('gate_minus_this_yield'))} ({v['wrong']} vs {gw})")
            if L:
                for lab in LLM_RUNS:
                    v = (L.get(lab) or {}).get(k)
                    cells.append("-" if not v else f"{pair(v['gate_minus_judge_matched_precision'], v['gate_minus_judge_matched_yield'])}")
                for lab in LLM_RUNS:
                    v = (L.get(lab) or {}).get(k)
                    cells.append("-" if not v else f"{pair(v['gate_minus_judge_own_precision'], v['gate_minus_judge_own_yield'])} "
                                                   f"({v['judge_own_verdict']['wrong_trusted']} vs {v['gate_wrong_trusted']})")
            out.append(f"| {dom} | {name(k)} | {r['n']} | {f3(r['directed']['yield'])} | " + " | ".join(cells) + " |")
    if L:
        out += ["", "LLM columns cover only the rows each judge saw in these sets (answered rows): "
                + ", ".join(f"{j} {n_llm[j]}" for j in lab3)
                + ". The answer-level and ReAct judges ran on frozen random subsets; the program-level judge on every answered row."]
    out.append("")
    return out


def render(res):
    out = [f"# Domain x platform x judge tables ({', '.join(res['sets'])})", "",
           f"Generated by scripts/domain_tables.py; {res['rows']} rows; bootstrap B={res['bootstrap']} (two-level, programs and questions), seed {res['seed']}; program failures {res['program_failures']}.",
           "Claude-built and Ollama-built programs are never pooled ('all Claude' pools only Claude-built platforms).",
           "kept = answered and Trusted by that judge. yield = correct kept / rows. 'gate - X' > 0 means the gate keeps more correct answers per row.",
           ""]
    G = res["groups"]
    out += summary(res)
    for dom in DOMAIN_ORDER:
        keys = [k for k in (f"{dom}|{p}" for p in PLAT_ORDER) if k in G]
        if not keys:
            continue
        out += [f"## {dom}", "", "### Gate decisions in plain terms (answered rows; wrong answers in brackets)", "",
                "| platform | rows | programs | answered (wrong) | " + " | ".join(PLAIN) + " | no answer |",
                "|---|---|---|---|" + "---|" * len(PLAIN) + "---|"]
        for k in keys:
            t, r = G[k]["terms"], G[k]["rule"]
            ans = sum(t["right"].values()) + sum(t["wrong"].values())
            cells = [f"{t['right'].get(p, 0) + t['wrong'].get(p, 0)} ({t['wrong'].get(p, 0)})" for p in PLAIN]
            out.append(f"| {name(k)} | {r['n']} | {r['programs']} | {ans} ({sum(t['wrong'].values())}) | " + " | ".join(cells) + f" | {t['no_answer']} |")
        out += ["", "### Every rule-based judge: coverage / precision (wrong kept)", "",
                "| platform | " + " | ".join(BASE) + " | gate (directed) |", "|---|" + "---|" * (len(BASE) + 1)]
        for k in keys:
            r = G[k]["rule"]
            cells = []
            for j in BASE + ("directed",):
                v = r.get(j)
                cells.append("n/a" if v is None else f"{f3(v['coverage'])}/{f3(v['precision'])} ({v['wrong']})")
            out.append(f"| {name(k)} | " + " | ".join(cells) + " |")
        out += ["", "### Yield: gate, and gate minus each judge [95% interval]", "",
                "| platform | gate yield | " + " | ".join(BASE) + " | matched random |", "|---|---|" + "---|" * (len(BASE) + 1)]
        for k in keys:
            r = G[k]["rule"]
            cells = []
            for j in BASE:
                v = r.get(j)
                if v is None:
                    cells.append("n/a")
                    continue
                cells.append(ci(v.get("gate_minus_this_yield")))
            mr_ = r.get("matched_random_refusal") or {}
            cells.append(ci(mr_.get("gate_minus_this_yield")))
            out.append(f"| {name(k)} | {f3(r['directed']['yield'])} | " + " | ".join(cells) + " |")
        if res.get("llm"):
            out += ["", "### LLM judges (Haiku), matched to the gate's coverage within cells; answered rows only (answer-level and ReAct: frozen random subsets)", "",
                    "| platform | judge | n (wrong) | gate prec (wrong kept) | judge prec at gate coverage | gate - judge, matched yield | judge's own verdict cov/prec (wrong kept) | gate - own verdict yield |",
                    "|---|---|---|---|---|---|---|---|"]
            for k in keys:
                for lab in LLM_RUNS:
                    v = (res["llm"].get(lab) or {}).get(k)
                    if not v:
                        continue
                    o = v["judge_own_verdict"]
                    out.append(f"| {name(k)} | {lab.split('|')[1]} | {v['n']} ({v['wrong_rows']}) | {f3(v['gate']['precision'])} ({v['gate_wrong_trusted']}) | "
                               f"{f3(v['judge_matched']['precision'])} | {ci(v['gate_minus_judge_matched_yield'])} | "
                               f"{f3(o['coverage'])}/{f3(o['precision'])} ({o['wrong_trusted']}) | {ci(v['gate_minus_judge_own_yield'])} |")
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("out_dir")
    ap.add_argument("--sets", required=True)
    ap.add_argument("--judges-dir", default=None)
    ap.add_argument("--subsets", default=None)
    ap.add_argument("--react50", default=None)
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args()
    root = Path(a.root).resolve()
    idsets = {}
    if a.subsets:
        idsets.update({k: v["ids"] for k, v in json.loads((root / a.subsets).read_text(encoding="utf-8"))["subsets"].items()})
    if a.react50:
        idsets["react50"] = json.loads((root / a.react50).read_text(encoding="utf-8"))["ids"]
    main(root, Path(a.out_dir), a.sets.split(","), (root / a.judges_dir) if a.judges_dir else None, idsets, a.boot)
