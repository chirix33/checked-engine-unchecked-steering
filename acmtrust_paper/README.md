# The ACM TRUST 2027 paper source

**Title:** Reproducing History Is Not Enough: Intervention-Level Assurance for LLM-Generated Simulators

**Status (2026-11-12):** full draft written for readers new to the project, with every number from the scored test run (`results.tex`, tables in `sections/06_results.tex`). The body ends on page 9. The only placeholder left is the anonymous artifact link.

## Build

Needs a TeX distribution with `latexmk` (MiKTeX or TeX Live). The ACM class and bibliography style are bundled here (`acmart.cls` and `ACM-Reference-Format.bst`, acmart v2.21, 2026-11-01, the current CTAN release).

```bash
latexmk main.tex
```

The PDF is written to `build/main.pdf`. `latexmkrc` holds the settings.

## Venue rules this source follows

These are the ACM TRUST 2027 author guidelines as checked on 2026-11-10. Check them again before submitting.

- ACM `sigconf`, two columns, submitted as a PDF through CMT.
- At most 9 pages, appendices included. References and the GenAI Usage Disclosure section are exempt from the limit.
- Double-blind review: the `review,anonymous` class options are set, and there are no acknowledgments. The OTF-Tools paper is cited anonymously in the third person. Its URL and repository must not appear in the submission.
- Deadline: November 15, 2026, 11:59 PM Pacific.

## Files

| File | What it holds |
|---|---|
| `main.tex` | Preamble, title, abstract hook, section order |
| `macros.tex` | Shared names (platforms, `\gate` = Vouch, the decline terms), `\sig{}` for bold significant differences, and the placeholder macros `\tbd` and `\TBD{...}` |
| `results.tex` | **Every number quoted in the prose**, with its source in the analysis files. |
| `sections/00_abstract.tex` | The registered abstract (lightly corrected) plus the headline result |
| `sections/01`–`09` | Introduction, problem, method, benchmark, judges, results, related work, limitations, conclusion |
| `sections/10_genai_disclosure.tex` | The required GenAI Usage Disclosure |
| `figures/pipeline.tex`, `figures/riskcov.tex` | Figure 1 (TikZ) and Figure 2 (pgfplots, generated from the analysis JSON) |
| `references.bib` | 32 entries, each checked against its arXiv record, DOI, Zenodo or publisher page (2026-11-10; two added and checked 2026-11-12). |
| `sensitivity/` | The run-clustered bootstrap check and its comparison with the frozen analysis |

## Still to do before submission

- Add the anonymized artifact link in `sections/09_conclusion.tex`.
- Confirm the GenAI disclosure paragraphs (how the software and the text were written).
- The Jev judge (D30) is left out until it is scored; a source comment in `sections/05_judges.tex` marks where it would go.
- Write the MLSys overlap statement. Ashraf owns it, and it is not part of this source.
- Before submitting, this must print only the artifact-link line, then nothing once the link is in:

```bash
grep -n "\\\\tbd\|\\\\TBD" *.tex sections/*.tex
```
