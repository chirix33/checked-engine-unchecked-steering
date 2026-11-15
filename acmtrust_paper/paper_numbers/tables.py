"""Check every cell of Tables 3, 4 and 5 (sections/06_results.tex) against the analysis files.

For each table row the script rebuilds the cells from the analysis JSON in the paper's format and compares them
with the LaTeX source, cell by cell, including which differences are set in bold.

- Table 3 (tab:main), rule-based judges: `rule_judges[<group>]` of main_analysis.json.
- Table 4 (tab:llm), LLM judges and Jev: `llm_judges[<run>].groups["class=claude"]` and `cost.judges[<run>]`.
- Bold (\\sig) in Tables 3 and 4: the 95% interval excludes zero in BOTH the frozen analysis (questions resampled
  within programs) and the run-clustered sensitivity analysis (acmtrust_paper/sensitivity/analysis_v2_runclustered).
  A star ($^\\ast$) marks an interval that excludes zero only in the frozen analysis.
- Table 5 (tab:families), why Vouch declined, by change family: counted from the decision rows with the analysis
  code's loader and decline terms (scripts/main_analysis.py `load_rows`, `term`), Claude-built programs, main sets.

Usage (from the repository root):
    python -X utf8 acmtrust_paper/paper_numbers/tables.py . [--analysis runs/main_v1/analysis_v2/main_analysis.json]
        [--clustered acmtrust_paper/sensitivity/analysis_v2_runclustered/main_analysis.json]
Exit code 0 if every cell matches, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BS = chr(92)
PAPER = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- formatting, as in the paper
def sgn(v):
    v = round(100 * v, 1)
    if v == 0:
        return "0.0"
    return f"${'+' if v > 0 else '-'}{abs(v):.1f}$"


def lo(v):
    v = round(100 * v, 1)
    if v == 0:
        return "0.0"
    return f"{v:.1f}" if v > 0 else f"$-{abs(v):.1f}$"


def thou(x):
    return f"{x:,}".replace(",", "{,}")


def excl(ci):
    return ci is not None and (ci[0] > 0 or ci[1] < 0)


def norm(cell: str) -> str:
    return cell.replace("$", "").replace("{,}", ",").replace(" ", "").replace("~", "")


def tex_rows(tex: str, label: str) -> dict:
    """{row name: [cells]} for the table with this label (rows that end in \\\\ and have & cells)."""
    start = tex.index(BS + "label{" + label + "}")
    end = tex.index(BS + "end{tabular}", start)
    body = tex[tex.index(BS + "midrule", start):end]
    out = {}
    for line in body.splitlines():
        line = line.strip()
        if "&" not in line or not line.endswith(BS + BS):
            continue
        cells = [c.strip() for c in line[:-2].split("&")]
        name = cells[0].replace(BS + "quad", "").strip()
        out.setdefault(name, []).append(cells[1:])
    return out


# ---------------------------------------------------------------- Table 3
GROUPS3 = ["platform=otf_r1|class=claude", "platform=devs|class=claude", "platform=agent|class=claude",
           "class=claude", "platform=otf_r1|class=ollama"]
ROWS3 = [("Platform check only", "native"), ("History check", "replay"), ("Generic tests", "generic"),
         ("Disagreement", "disagreement"), ("Random refusal", "random"), ("Program-wide tests", "program_wide"),
         ("Vouch", "directed")]


def table3(d, rc):
    exp = {}
    for name, key in ROWS3:
        cells = []
        for g in GROUPS3:
            x, xc = d["rule_judges"][g], rc["rule_judges"][g]
            n = x["n"]
            if key == "random":
                m, mc = x["matched_random_refusal"], xc["matched_random_refusal"]
                dk = m.get("gate_minus_this_yield") or m.get("gate_minus_random_yield")
                dkc = mc.get("gate_minus_this_yield") or mc.get("gate_minus_random_yield")
                cov = x["directed"]["coverage"]
                cells += [f"{100 * cov:.1f}", f"({round(cov * n * (1 - x['native']['precision']))})"]
            else:
                y = x[key]
                cells += [f"{100 * y['coverage']:.1f}", str(y["wrong"])]
                if key == "directed":
                    cells.append("--")
                    continue
                dk, dkc = y["gate_minus_this_yield"], xc[key]["gate_minus_this_yield"]
            t = sgn(dk["point"])
            cells.append(BS + "sig{" + t + "}" if excl(dk["ci95"]) and excl(dkc["ci95"]) else t)
        exp[name] = cells
    return exp


# ---------------------------------------------------------------- Table 4
ROWS4 = [("Answer-level judge", [("main_answer_haiku|answer|claude-haiku-5-5", "Haiku"), ("main_answer_sonnet150|answer|claude-sonnet-5-5", "Sonnet"),
                                 ("main_answer_gptoss150|answer|gpt-oss-120b", "gpt-oss"), ("main_answer_gemma150|answer|gemma-31b-ollama", "Gemma"),
                                 ("main_answer_qwen150|answer|qwen3.5-9b", "Qwen")]),
         ("Program-level judge", [("main_program_haiku|program|claude-haiku-5-5", "Haiku")]),
         ("ReAct judge", [("main_react_haiku|react|claude-haiku-5-5", "Haiku"), ("main_react_sonnet50|react|claude-sonnet-5-5", "Sonnet"),
                          ("main_react_gptoss150|react|gpt-oss-120b", "gpt-oss"), ("main_react_gemma150|react|gemma-31b-ollama", "Gemma"),
                          ("main_react_qwen150|react|qwen3.5-9b", "Qwen")]),
         ("Decision model, answer-level input", [("main_answer_jev|answer|jev-1.14.0", "Jev")])]


def table4(d, rc):
    exp = defaultdict(list)
    for _, runs in ROWS4:
        for k, name in runs:
            g, gc = d["llm_judges"][k]["groups"]["class=claude"], rc["llm_judges"][k]["groups"]["class=claude"]
            n, ga, jm, jo = g["n"], g["gate"], g["judge_matched"], g["judge_own_verdict"]
            expw = round(ga["coverage"] * n) * (1 - jm["precision"])
            c = d["cost"]["judges"][k]

            def diff(key):
                dd, dc = g[key], gc[key]
                t = f"{sgn(dd['point'])} [{lo(dd['ci95'][0])}, {lo(dd['ci95'][1])}]"
                if excl(dd["ci95"]) and excl(dc["ci95"]):
                    return BS + "sig{" + t + "}"
                return t + ("$^" + BS + "ast$" if excl(dd["ci95"]) else "")

            exp[name].append([thou(n), f"{100 * (1 - ga['precision']):.1f} ({g['gate_wrong_trusted']})",
                              f"{100 * (1 - jm['precision']):.1f} ({expw:.0f})", diff("gate_minus_judge_matched_precision"),
                              f"{100 * jo['coverage']:.1f}", f"{100 * (1 - jo['precision']):.1f} ({jo['wrong_trusted']})",
                              diff("gate_minus_judge_own_yield"), f"{sum(c['failures'].values())}/{thou(c['rows'])}"])
    return exp


# ---------------------------------------------------------------- Table 5
ROWS5 = [("Activity duration", "activity_duration"), ("Timer delay", "timer_delay"), ("Route draw (one case)", "routing_outcome"),
         ("Routing probabilities", "routing_probability"), ("Worker availability", "resource_availability"),
         ("Case removal", "case_set"), ("Job removal", "job_removal"), ("Failure removal", "failure_removal"),
         ("Task priority", "task_priority"), ("Task resource request", "task_request"), ("Machine removal", "machine_removal")]
DETECT = ("Caught", "Already caught", "Failed history check")
ABSTAIN = ("Untestable", "Can't express")


def table5(root):
    sys.path[:0] = [str(root), str(root / "scripts")]
    sys.dont_write_bytecode = True
    import main_runner as mr
    import main_summary as ms
    import main_analysis as ma
    rows, _, _, _, _ = ma.load_rows(root, ["wf_test", "ml_test"], mr, ms)
    cl = [r for r in rows if r["class"] == "claude"]

    def cells(rs):
        c = Counter()
        for r in rs:
            c["pairs"] += 1
            if not r["has"]:
                continue
            t = ma.term(r["decisions"]["directed"], True)
            c[("wrong" if not r["correct"] else "right", t)] += 1
        wrong = sum(v for k, v in c.items() if k != "pairs" and k[0] == "wrong")
        part = lambda kind, terms: sum(c[(kind, t)] for t in terms)
        return [thou(c["pairs"]), str(wrong), str(c[("wrong", "Trusted")]),
                f"{part('wrong', DETECT)}/{part('right', DETECT)}", f"{part('wrong', ABSTAIN)}/{part('right', ABSTAIN)}"]

    exp = {name: cells([r for r in cl if r["family"] == fam]) for name, fam in ROWS5}
    exp["All families"] = cells(cl)
    exp["No-effect controls"] = cells([r for r in cl if not r["effectful"]])
    return exp


# ---------------------------------------------------------------- compare
def compare(title, paper_rows, expected):
    bad = 0
    print(f"\n== {title}")
    for name, exp in expected.items():
        got = paper_rows.get(name)
        exps = exp if isinstance(exp[0], list) else [exp]
        if got is None or len(got) != len(exps):
            print(f"  {name}: row MISSING or repeated in the paper")
            bad += 1
            continue
        for g, e in zip(got, exps):
            diffs = [(i, a, b) for i, (a, b) in enumerate(zip(g, e)) if norm(a) != norm(b)]
            if len(g) != len(e):
                diffs.append(("cells", len(g), len(e)))
            bad += len(diffs)
            print(f"  {name:24s} {'ok' if not diffs else 'DIFF'}" + "".join(f"\n      cell {i}: paper {a!r} vs files {b!r}" for i, a, b in diffs))
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--analysis", default="runs/main_v1/analysis_v2/main_analysis.json")
    ap.add_argument("--clustered", default="acmtrust_paper/sensitivity/analysis_v2_runclustered/main_analysis.json")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    d = json.loads((root / a.analysis).read_text(encoding="utf-8"))
    rc = json.loads((root / a.clustered).read_text(encoding="utf-8"))
    tex = (PAPER / "sections" / "06_results.tex").read_text(encoding="utf-8")
    bad = compare("Table 3 (tab:main)", tex_rows(tex, "tab:main"), table3(d, rc))
    bad += compare("Table 4 (tab:llm)", tex_rows(tex, "tab:llm"), table4(d, rc))
    bad += compare("Table 5 (tab:families)", tex_rows(tex, "tab:families"), table5(root))
    print(f"\n{'all cells match' if not bad else f'{bad} cell(s) differ'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
