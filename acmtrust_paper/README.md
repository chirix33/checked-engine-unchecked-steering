# The ACM TRUST 2027 paper source

**Title:** Beyond Pass or Fail: Checking When LLM-Generated Simulators Can Answer What-If Questions

**Status (2026-11-10):** full draft. Every section is written. Every test-set number is a red placeholder, because the main (test) run was still being scored when the draft was written.

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
| `macros.tex` | Shared names (platforms, the gate, the decline terms) and the placeholder macros `\tbd` and `\TBD{...}` |
| `results.tex` | **Every number quoted in the prose.** Fill these from the scored test run. |
| `sections/00_abstract.tex` | The registered abstract, verbatim, plus one placeholder sentence for the headline result |
| `sections/01`–`09` | Introduction, problem, method, benchmark, judges, results, related work, limitations, conclusion |
| `sections/10_genai_disclosure.tex` | The required GenAI Usage Disclosure |
| `figures/pipeline.tex` | Figure 1 (TikZ) |
| `references.bib` | 30 entries. Each was checked against its arXiv record, its DOI (via Crossref), Zenodo or the publisher on 2026-11-10. |

## Filling in the results

1. Score the test run with `scripts/main_analysis.py`, using the main sets, the policy set and `runs/judges_main_v1`.
2. Put the headline numbers into `results.tex`.
3. Fill the table cells marked `\tbd` in `sections/06_results.tex`, which has Tables 3–7.
4. Rewrite every `\TBD{...}` sentence so it states what was measured. Report null and negative results as well; the bracketed text describes what each sentence has to cover.
5. Add the headline sentence to the abstract only after scoring.
6. Before submitting, this command must print nothing:

```bash
grep -n "\\\\tbd\|\\\\TBD" *.tex sections/*.tex
```

Use test-run numbers only. Development results helped design the method, so the paper does not report them as evidence.

## Still to do before submission

- Fill the placeholders, as described above.
- Add the anonymized artifact link in `sections/09_conclusion.tex`.
- Confirm the GenAI disclosure paragraph that describes how the software was written. A comment in `sections/10_genai_disclosure.tex` flags it.
- Write the MLSys overlap statement. Ashraf owns it, and it is not part of this source.
- Make sure the page count is still 9 or fewer after the numbers go in.
- Remove the line numbers (the `review` option) only if the venue asks for that.
