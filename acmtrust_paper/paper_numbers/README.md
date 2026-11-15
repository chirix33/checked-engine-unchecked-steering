# Paper numbers that are not in the analysis JSON

Most numbers in `results.tex` are copied from `runs/main_v1/analysis_v2/main_analysis.json` and its `tables.md`. Each macro's comment names its source. The two scripts here cover what those files do not hold. Run them from the repository root with the project's Python 3.12 environment.

| script | what it does | check |
|---|---|---|
| `raw_rows.py` | Recounts the macros marked "raw rows" in `results.tex` from the decision rows and judge rows: which programs give wrong answers, the correct answers Vouch declined as Untestable, program runs and wall time per question, the ReAct judges' program runs and failures, and the judges' wall time. It uses the loaders and scorer in `scripts/main_analysis.py` and `scripts/main_summary.py`. | prints paper value vs recount; exit 1 on any difference |
| `figure3.py` | Writes Figure 3 (`figures/riskcov.tex`) from `main_analysis.json`. | `--check` compares with the file in the paper |
| `tables.py` | Rebuilds every cell of Tables 3, 4 and 5 of the paper. Tables 3 and 4 come from `main_analysis.json`. A difference is bold only if its interval excludes zero in both the frozen analysis and the run-clustered one in `sensitivity/`. Table 5 is counted from the decision rows with the analysis code's decline terms. | with the paper's LaTeX source (`sections/06_results.tex`): prints each row as ok or the differing cells, exit 1 on any difference. Without it (the public artifact ships no paper source): prints the rebuilt tables to compare with the PDF |

```bash
python -X utf8 acmtrust_paper/paper_numbers/raw_rows.py .
python -X utf8 acmtrust_paper/paper_numbers/figure3.py runs/main_v1/analysis_v1/main_analysis.json --check
python -X utf8 acmtrust_paper/paper_numbers/tables.py .
```

Checked on 2026-11-14:
- all 19 recounted macros equal `results.tex`;
- Figure 3 regenerates byte for byte from both `analysis_v1` and `analysis_v2`;
- every cell of Tables 3, 4 and 5 matches, bold and the star included. A check with one number and one bold changed on purpose reported both.

Table 1 counts questions and programs. The question files and `manifests/freeze_v1.json` give these counts directly; no script checks them.
