"""Recompute the results.tex macros that come from the raw rows and compare them with results.tex.

The analysis JSON stores means and totals, so a few numbers in the paper were counted directly from the decision
rows (runs/main_v1/<set>/programs/*.jsonl) and the judge rows (runs/judges_main_v1/*/judgments_*.jsonl). This
script counts them again, with the analysis code's own loaders and scorer (scripts/main_analysis.py,
scripts/main_summary.py), and checks each value against the macro in acmtrust_paper/results.tex.

Rows and groups, as in the paper:
- decision rows: main test sets (wf_test, ml_test), interpreted request, structured answer path, programs that are
  not native-only, hosted-API (Claude) builder class: 7,056 pairs from 62 programs;
- a wrong answer under a judge = the judge trusts the row, the row has an answer, and the answer is not gold;
- judge rows: every judged row of the run, as in the cost section of main_analysis.py (main sets plus wf_policy).

Usage (from the repository root):
    python -X utf8 acmtrust_paper/paper_numbers/raw_rows.py .
Exit code 0 if every value matches, 1 otherwise.
"""
from __future__ import annotations

import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

MAIN_SETS = ["wf_test", "ml_test"]
POLICY_SET = "wf_policy"


def macros(tex: str) -> dict:
    """{name: value} for every \\newcommand{\\rName}{value} in results.tex (value without braces' outer pair)."""
    out = {}
    for m in re.finditer(r"\\newcommand\{\\(r\w+)\}\{", tex):
        i, depth = m.end(), 1
        j = i
        while depth:
            depth += {"{": 1, "}": -1}.get(tex[j], 0)
            j += 1
        out[m.group(1)] = tex[i:j - 1]
    return out


def main(root: Path) -> int:
    sys.path[:0] = [str(root), str(root / "scripts")]
    sys.dont_write_bytecode = True
    import main_runner as mr
    import main_summary as ms
    import main_analysis as ma

    rows, _, _, _, _ = ma.load_rows(root, MAIN_SETS, mr, ms)
    cl = [r for r in rows if r["class"] == "claude"]

    def wrong(r, cfg):
        return bool(r["decisions"][cfg]["permit"]) and r["has"] and not r["correct"]

    got, notes = {}, {}

    # ---- programs: which Claude-built programs give a wrong answer, and what the gate does with them
    per = defaultdict(Counter)
    for r in cl:
        per[r["program"]]["native"] += wrong(r, "native")
        per[r["program"]]["directed"] += wrong(r, "directed")
    with_wrong = [p for p, c in per.items() if c["native"]]
    kept = [p for p in with_wrong if per[p]["directed"]]
    otf = {p: c["native"] for p, c in per.items() if ma.platform(p) == "otf_r1"}
    got["rProgsClaude"] = str(len(per))
    got["rProgsWithWrong"] = str(len(with_wrong))
    got["rProgsAllRemoved"] = str(len(with_wrong) - len(kept))
    got["rProgsWrongKept"] = str(len(kept))
    notes["rProgsWrongKept"] = ", ".join(f"{p} ({per[p]['directed']})" for p in sorted(kept))
    got["rOtfLargestProgWrong"] = str(max(otf.values()))
    got["rOtfNoCheckWrong"] = str(sum(otf.values()))
    notes["rOtfLargestProgWrong"] = max(otf, key=otf.get)

    # ---- correct answers the gate declined as Untestable, and how many were no-effect controls
    unt = [r for r in cl if r["has"] and r["correct"] and ma.term(r["decisions"]["directed"], True) == "Untestable"]
    got["rUntestableRight"] = str(len(unt))
    got["rUntestableRightNoEffect"] = str(sum(not r["effectful"] for r in unt))

    # ---- cost: program runs and wall time per pair
    ex = {cfg: [r["executions"].get(cfg, 0) for r in cl] for cfg in ("directed", "generic", "program_wide")}
    got["rGateExecPerQ"] = f"{st.mean(ex['directed']):.1f}"
    got["rGateExecMedian"] = f"{st.median(ex['directed']):g}"
    got["rGenericExecPerQ"] = f"{st.mean(ex['generic']):.1f}"
    got["rProgWideExecPerQ"] = f"{st.mean(ex['program_wide']):.1f}"
    notes["rGateExecPerQ"] = f"mean {st.mean(ex['directed']):.3f} over {len(cl)} pairs"
    notes["rGenericExecPerQ"] = f"mean {st.mean(ex['generic']):.3f}, median {st.median(ex['generic']):g}"
    notes["rProgWideExecPerQ"] = f"mean {st.mean(ex['program_wide']):.3f}, median {st.median(ex['program_wide']):g}"
    sec = {}
    for s in MAIN_SETS:
        for p in sorted((mr.OUT / s / "programs").glob("*.jsonl")):
            for r in ms.load_jsonl(p):
                if r.get("source") == "interpreted" and "decisions" in r:
                    sec[(s, r["program"], r["question"])] = r.get("seconds") or 0.0
    secs = [sec[(r["set"], r["program"], r["question"])] for r in cl]
    got["rGateSecPerQ"] = f"{st.median(secs):.1f}"
    notes["rGateSecPerQ"] = f"median; mean {st.mean(secs):.2f}"

    # ---- judge rows (all judged rows of a run: main sets plus the policy set)
    runs = ma.load_judges(root / "runs" / "judges_main_v1", set(MAIN_SETS + [POLICY_SET]))

    def judged(label):
        return [x for x in runs[label]["rows"].values() if x.get("status") == "judged"]

    def ran_share(label):
        rs = judged(label)
        n = sum((x.get("program_executions") or 0) > 0 for x in rs)
        return n, len(rs)

    n, d = ran_share("main_react_haiku|react|claude-haiku-5-5")
    got["rReactRanProgHaiku"] = f"{100 * n / d:.1f}"
    notes["rReactRanProgHaiku"] = f"{n} of {d} rows"
    n, d = ran_share("main_react_sonnet50|react|claude-sonnet-5-5")
    got["rReactRanProgSonnet"] = f"{100 * n / d:g}"
    notes["rReactRanProgSonnet"] = f"{n} of {d} rows"
    fails = lambda label: Counter(x.get("failure") for x in judged(label) if x.get("failure"))
    f = fails("main_react_gptoss150|react|gpt-oss-120b")
    got["rGptossUnparsed"] = str(f["unparsable"])
    notes["rGptossUnparsed"] = f"of {len(judged('main_react_gptoss150|react|gpt-oss-120b'))} rows; {dict(f)}"
    f = fails("main_react_qwen150|react|qwen3.5-9b")
    got["rQwenReactFailed"] = str(sum(f.values()))
    notes["rQwenReactFailed"] = str(dict(f))
    for mac, label in (("rAnsJudgeSecPerRow", "main_answer_haiku|answer|claude-haiku-5-5"),
                       ("rReactSecPerRow", "main_react_haiku|react|claude-haiku-5-5")):
        w = [x.get("wall_seconds") or 0.0 for x in judged(label)]
        got[mac] = f"{st.mean(w):.1f}"
        notes[mac] = f"mean over {len(w)} rows; median {st.median(w):.1f}"

    # ---- compare with results.tex
    paper = macros((Path(__file__).resolve().parents[1] / "results.tex").read_text(encoding="utf-8"))
    bad = 0
    print(f"{'macro':28s} {'paper':>8s} {'rows':>8s}  status  note")
    for k, v in got.items():
        p = paper.get(k)
        ok = p is not None and p.strip() == v
        bad += not ok
        print(f"{k:28s} {str(p):>8s} {v:>8s}  {'ok' if ok else 'DIFF':6s}  {notes.get(k, '')}")
    print(f"\n{len(got) - bad} of {len(got)} match")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()))
