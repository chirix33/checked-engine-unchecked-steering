"""Write Figure 3 (acmtrust_paper/figures/riskcov.tex, pgfplots) from the analysis JSON.

Figure 3 shows OTF-Tools R1 programs built by the hosted-API (Claude) models, on the pairs that have an answer:
the risk-coverage curves of the Haiku answer-level, ReAct and program-level judges, and the single points of the
platform check (no added check), the history check, disagreement with the reading answer, and Vouch.

Source: main_analysis.json, `llm_judges[<run>].groups["platform=otf_r1|class=claude"].risk_coverage` and
`rule_judges["platform=otf_r1|class=claude"]`. analysis_v1 and analysis_v2 give the same figure (v2 only adds the
Jev judge, which the figure does not show).

Usage (from the repository root):
    python -X utf8 acmtrust_paper/paper_numbers/figure3.py runs/main_v1/analysis_v1/main_analysis.json
        [--out acmtrust_paper/figures/riskcov.tex] [--check]
--check compares with the existing file instead of writing it (exit 1 if they differ).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BS = chr(92)
GROUP = "platform=otf_r1|class=claude"
CURVES = [("main_answer_haiku|answer|claude-haiku-5-5", "answer"), ("main_react_haiku|react|claude-haiku-5-5", "react"),
          ("main_program_haiku|program|claude-haiku-5-5", "program")]


def figure_data(d: dict) -> dict:
    x = d["rule_judges"][GROUP]
    ans = x["native"]["answered"]
    pts = {}
    for key in ("native", "replay", "disagreement", "directed"):
        y = x[key]
        pts[key] = (y["answered"] / ans, 100 * (1 - y["precision"]) if y["precision"] is not None else None, y["wrong"])
    curves = {}
    for run, name in CURVES:
        g = d["llm_judges"][run]["groups"][GROUP]
        curves[name] = {"n": g["n"], "points": [(p[1], 100 * p[2]) for p in g["risk_coverage"]["points"]]}
    return {"points": pts, "curves": curves}


def coords(pts):
    return " ".join(f"({100 * c:.2f},{r:.2f})" for c, r in sorted(pts))


def thou(x):
    return f"{x:,}".replace(",", "{,}")


def tikz(fig: dict) -> str:
    L = []
    a = L.append
    a('%% Generated from runs/main_v1/analysis_v1/main_analysis.json (llm_judges.*.groups["platform=otf_r1|class=claude"].risk_coverage')
    a('%% and rule_judges["platform=otf_r1|class=claude"]). Do not edit numbers by hand; regenerate.')
    a(BS + "begin{tikzpicture}")
    a(BS + "begin{axis}[")
    a("  width=" + BS + "columnwidth, height=3.4cm,")
    a("  xmin=0, xmax=104, ymin=-0.6, ymax=12,")
    a("  xlabel={Coverage of answered pairs (" + BS + "%)}, ylabel={Error among trusted (" + BS + "%)},")
    a("  xlabel style={font=" + BS + "footnotesize, yshift=3pt}, ylabel style={font=" + BS + "footnotesize, yshift=-4pt},")
    a("  tick label style={font=" + BS + "footnotesize},")
    a("  xtick={0,20,40,60,80,100}, ytick={0,2,4,6,8,10,12},")
    a("  legend style={font=" + BS + "scriptsize, at={(0.5,-0.31)}, anchor=north, draw=none, column sep=4pt},")
    a("  legend columns=3, legend cell align=left, clip=true,")
    a("]")
    styles = {"answer": ("blue!70!black, thick", "Answer"),
              "react": ("orange!85!black, thick, dashed", "ReAct"),
              "program": ("black!55, thick, dotted", "Program-level")}
    for k in ("answer", "react", "program"):
        c = fig["curves"][k]
        st, lab = styles[k]
        a(BS + "addplot[" + st + ", mark=none] coordinates {" + coords(c["points"]) + "};")
        a(BS + "addlegendentry{" + lab + " ($n{=}" + thou(c["n"]) + "$)}")
    marks = [("native", "mark=square*, mark size=1.8pt, black!75", "no check", "left", "xshift=-1pt, yshift=3pt"),
             ("replay", "mark=triangle*, mark size=2.4pt, black!75", "history", "left", "xshift=-1pt, yshift=-3pt"),
             ("disagreement", "mark=diamond*, mark size=2.4pt, black!75", "disagreement", "left", ""),
             ("directed", "mark=*, mark size=2.6pt, red!75!black", BS + "gate", "above", "yshift=1pt")]
    for k, st, lab, pos, shift in marks:
        cov, err, _ = fig["points"][k]
        xy = f"{100 * cov:.2f},{err:.2f}"
        a(BS + "addplot[only marks, forget plot, " + st + "] coordinates {(" + xy + ")};")
        a(BS + "node[font=" + BS + "scriptsize, " + pos + (", " + shift if shift else "") + "] at (axis cs:" + xy + ") {" + lab + "};")
    a(BS + "end{axis}")
    a(BS + "end{tikzpicture}")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("analysis_json")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "figures" / "riskcov.tex"))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = tikz(figure_data(json.loads(Path(a.analysis_json).read_text(encoding="utf-8"))))
    out = Path(a.out)
    if a.check:
        same = out.read_text(encoding="utf-8").replace("\r\n", "\n") == text
        print(f"{out}: {'identical' if same else 'DIFFERS'}")
        return 0 if same else 1
    out.write_text(text, encoding="utf-8", newline="\n")
    print("written", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
