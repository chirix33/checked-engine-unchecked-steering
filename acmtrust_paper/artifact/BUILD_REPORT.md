# Build report: the anonymous GitHub source

The anonymous GitHub source is the folder `C:\Users\aashraf\Desktop\Work\2026\vouch_artifact\`, built by `acmtrust_paper/artifact/build_artifact.py`. **Do not ship this file or anything in `acmtrust_paper/artifact/`**: the rules name the strings that were removed. The builder copies only an allow-list of paper files, so none of this folder reaches the anonymous GitHub source.

Labels: **verified** = checked by running a command here. **Decision** = needs a person. Secret values were never printed.

## 1. Result

| | |
|---|---|
| Folder | `C:\Users\aashraf\Desktop\Work\2026\vouch_artifact\` |
| Size | **3,805 files, 202.2 MB** (3,822 files, 202.5 MB before this round; 3,998 files, 209.2 MB two rounds ago). Largest file 9.2 MB (`runs/judges_main_v1/main_react_qwen150/judgments_qwen3.5-9b.s0of1.jsonl`); largest folder 500 files (`validation/fuzz_v1/`); longest path 155 characters. |
| Rebuild | `python -X utf8 acmtrust_paper/artifact/build_artifact.py` (about 30 s; reads the working tree, never edits it; empties the folder but keeps a `.git` folder if one exists) |
| Rescan | `python -X utf8 acmtrust_paper/artifact/verify_artifact.py` (exit 0 = clean) |
| Fallback | `build_artifact.py --pack` replaces the large evidence folders by `.tar.gz` archives (about 1,160 files, 52 MB); `scripts/unpack_evidence.py` restores them. Last measured two rounds ago, not remeasured. |
| Where the rules live | `scrub_rules.json` (exclusions, name rules, structural fixes), `prose_fixes.json` (108 hand-written sentence edits: 7 before and 101 after the name rules), `templates/` (README, NOTICE, licence, data README). A rebuild reproduces everything; nothing was edited by hand in the folder. |

The folder reflects the working tree at build time. Rebuild and rescan after any change to results, figures or `paper_numbers/`. The paper source is no longer in it, so paper edits do not matter to it.

## 2. This round: the paper folder trimmed

**Left out of `acmtrust_paper/` (17 files, builder allow-list):** `main.tex`, `sections/` (all 11 files), `macros.tex`, `references.bib`, `acmart.cls`, `ACM-Reference-Format.bst`, `latexmkrc`. `references.bib` is gone, which removes the header comment that said the OTF-Tools paper "is cited anonymously in the third person, as double-blind review requires".

**Kept (81 files):** `results.tex`; `figures/` (`history_gap.pdf`, `pipeline.pdf`, `riskcov.tex`, and `figures/src/` with `history_gap/`, `pipeline/` and `fonts/libertine_ttf.py`, no font files); `sensitivity/`; `paper_numbers/`. The `paper_numbers/` files, including your new `tables.py` and README, were copied unchanged.

**README of the anonymous GitHub source:**
- the "Rebuild the paper" section is gone (section 9 is now "Figures");
- the `acmtrust_paper/` row says the paper is provided as a PDF with the submission, not as LaTeX source, and lists what the folder holds;
- the section 6 note says `tables.py` prints the rebuilt Tables 3, 4 and 5 for comparison with the PDF and exits 0, and compares cell by cell only when the source is present;
- `NOTICE.md` lost its `acmart.cls` row, since the class is no longer shipped.

**References to dropped paper files, fixed in the builder:**
- `b0_results.md` no longer cites `sections/04_benchmark.tex`; it says "The paper says: …" (the builder reads that sentence from the working tree);
- three comments in the figure sources named `acmart` as the font's origin; they now say "the paper's body font" (`libertine_ttf.py`, `history_gap/src/index.css`, `pipeline/src/index.css`);
- the `results.tex` comments name `tables.md` sections and `manifests/main_results_v1.md`, which are shipped; none points at a dropped section file, so none needed rewriting.

**Beyond your list (please check):** the search for review-status wording found one more leak in a kept file: `manifests/design_decisions.md` D2 was titled "Overlap and dual submission" and said "No chair contact". It now reads "D2. Venue process: Owned by the authors" and "Not an agent decision."

**Remaining hits for "cited anonymously", "double-blind", "under review", "third person" and related words, over the whole folder:**

| Hit | Why kept |
|---|---|
| `README.md:3` "the anonymized artifact for a double-blind submission" | the plain statement of what the folder is; it names no one and no other paper |
| 0 hits for "cited anonymously", "under review", "third person", "anonymous paper", "dual submission", "chair" | none |
| `paper_numbers/README.md:9` and `paper_numbers/tables.py` lines 4, 19, 230 name `sections/06_results.tex` | they describe the optional source `tables.py` compares with when present; you asked for these files unchanged |
| `results.tex:152-153` contain `\TBD{…}` | these are the values of two macros in the paper's map (`macros.tex`, which defines `\TBD`, is not shipped); the file is a map and is not compiled |
| "submission" in scheduling text (`ITOperations.yaml`, specs, `assurance/mlsys.py`, validation notes) | task submission times in the IT-operations simulator |
| "no overlap and" in two judge rows under `runs/judges_main_v1` | model output about a simulation, not review wording |

## 3. Earlier rounds, in short

**Last cleanups.** The 8 coding-agent `prompt_log.jsonl` files no longer say "MLSys": a generic rule rewrites "from the MLSys front matter" to "from the source benchmark front matter" (the same wording as the shipped specs, so each logged prompt contains the shipped `spec.md` text verbatim; checked on all 8). They are listed with old and new sha256 under `changed_run_files` in `anonymization_map.json`; no hash list, freeze record, index or `build.json` hashes a prompt log. "Coordinating session", "main-run session", "agent session", "tool session" and "judges session" were removed in 32 edits in 15 files (`domain_readiness.md`, `workflow_test_set.md`, `design_decisions.md`, `jev_judge_design.md`, `builder_isolation.md`, two script comments, eight blind-review notes). Searches now find 0 hits for "MLSys" and "coordinating session" anywhere, `runs/` and the gunzipped log members included.

**Slimming round.** Left out: `manifests/run_manifest.md`, `baseline_judges_design.md`, `baseline_feasibility.md`, `pilot_report.md`, `blindspots.md`, `it_blindspot.md`; the four API-check JSONs; `model_endpoint_check.py`, `openrouter_free_probe.py` and `model_connection_test.py` (nothing kept imports them); 162 console logs under `runs/main_v1/logs/` (the 7 run-start scripts and `policy_programs.*` stay); `figures/pipeline.tex`. References to them say "working notes, not included". Roles are always "the authors"; no advisor, meeting quote or time, or pronoun remains. Credit balances, top-ups and key ownership were removed (caps and published prices stay). "MLSys" prose became "the OTF-Tools release" or "the source benchmark". Mentions of `AGENTS.md`, `RESEARCH_DIRECTION.md` and "handoff" became "the project's research plan (not included)" or "the implementation plan (not included)". Deleted rather than rewritten: the D8 balance paragraph and key-owner sentence, D7's "Saved MLSys programs" sentence, one isolation-table row about the earlier project, D3's related-paper sentence, and a timestamp with a time zone.

**Consequences.**
- 14 of the 30 frozen files differ from `freeze_v1.json` (comments, docstrings, names, paths); `freeze_v1_anonymized.json` has the new hashes and the freeze check passes on it.
- The `Source:` line of two task specs changed, so the `spec_sha256` stored in 8 `build.json` files no longer matches the shipped spec; the README says so and `anonymization_map.json` maps it.
- The map lists 69 changed files outside `runs/`, 298 run files and 127 manual edits (121 sentence edits, 6 code patches).
- The prose rules never touch `runs/` or `programs/`; run rows differ from the originals only in names, paths and the 8 prompt logs.

## 4. Earlier decisions (1 to 11)

| # | Decision | Done |
|---|---|---|
| 1 | Evidence set | `runs/main_v1/{wf_test,ml_test,wf_policy}` (+ `*_summary.json`), `analysis_v1/v2`, `domain_tables_v1/v2`, `jev_long_context_v1`, `judges_main_v1`, `judges_jev_ledger`, all `build_test_*` folders (ledgers, `builds_*.jsonl`, console logs, 120 `program.json`), `devs_gen`, `coding_agent`, `workflow_docs`, `mlsys_docs`. |
| 2 | Gold shipped | Question files as they are, plus all of `validation/`. |
| 3 | No `baseline/` | README section 2 says plainly that R1 and B0 import the pinned OTF-Tools implementation and that it is withheld for anonymity. Code paths still name `baseline/otf-tools-10f5401/...`. |
| 4 | Scrub frozen files | `freeze_v1_anonymized.json` and `anonymization_map.json` written. |
| 5 | Decision log | `design_decisions.md` shipped, scrubbed. The run manifest is not shipped. |
| 6, 7 | Licence, attribution | `LICENSE` (MIT, "Anonymous Authors"), `NOTICE.md`. Upstream licences checked on the web: Zenodo 10435849 CC BY 4.0; SupplyGraph LGPL-2.1 (no separate dataset licence stated); Google cluster data CC-BY (4.0). Nothing blocks redistribution. |
| 8 | DEVS-Gen programs | 22 programs in `programs/devs_gen/` (1,385 files, 8.3 MB). |
| 9 | Paper source | Now only `results.tex`, `figures/`, `sensitivity/` and `paper_numbers/` (section 2). |
| 10 | New files | `README.md`, `data/README.md`, `program_list.csv` (118 rows), `b0_results.md` (32 of 60 accepted, matching the paper), `NOTICE.md`, `LICENSE`, `artifact_files.sha256`, `scripts/verify_files.py`. |
| 11 | OTF-Tools name | Not touched. |

Also added: an export-specific `.gitignore`, a `.gitattributes` with `* -text` (frozen files are CRLF and your Git for Windows has `core.autocrlf=true`), `manifests/abstract_draft.md` left out, and the `--pack` fallback.

## 5. Other remaining hits, with the reason to keep each

| Search | Remaining | Why kept |
|---|---|---|
| `mlsys` as identifiers | 38 file or folder names (`assurance/mlsys.py`, `mlsys_questions_*.json`, `runs/mlsys_docs`, ...), code names, the set names `ml_dev`/`ml_test`, `MLSYS_RAW` | identifiers; renaming would break frozen hashes |
| `meeting` | 1: `scripts/check_builder_isolation.py:38`, the folder name `"meeting"` in the isolation check's directory list | you asked to keep that list; a folder name, not a quote or a time |
| `transcript` | ReAct judge transcripts in `scripts/judges.py`, `test_judges_offline.py`; "transcripts" of model runs in `builder_isolation.md` | about model transcripts |
| `AGENTS.md`, `RESEARCH_DIRECTION.md`, `.claude`, `Claude-Data`, the earlier project's path | only in `scripts/check_builder_isolation.py` (lines 38 to 58, the file and folder lists) | the list documents the isolation check; its comments no longer quote the files |
| Clock times | working-hours text of the processes, and the venue's "Nov 15, 11:59 PM Pacific" in `design_decisions.md` | process data and a public deadline |
| "session" | `DBUS_SESSION_BUS_ADDRESS`, "session bus", "new session" (3 code lines) | the sandbox's own terms |
| `credit`, `balance` | published prices, caps ($20, $150, $5, $25, $80, $21), the free OpenRouter rate-limit rule | caps and prices, as you asked |

## 6. Scans and tests on the final folder (verified; Windows, CPython 3.12.16)

| Check | Result |
|---|---|
| Identity strings (name parts, handle, e-mail parts, university, advisor name, plus 9 terms from `git log` and `git config`) in 3,780 text files, `.gz` decompressed | **0 hits** |
| Binary files (24), identity-like bytes | 0 |
| Local paths with a user name | **0 hits** |
| Links | every host on the allow-list; none to the authors' GitHub or an OTF-Tools repository |
| Secrets, key-shaped | **0 hits**. Literal values of the 4 `.env` keys: **0 files** contain any (counts only) |
| File sizes | none over 10 MB; no `__pycache__` |
| LaTeX references in the remaining `.tex` files | all present |
| `verify_files.py` | 3,804 files listed, 0 missing or changed, 0 unlisted |
| Freeze check (`make_freeze_record.py`) | 30 files equal `freeze_v1_anonymized.json`; 118 programs; program-name hash equal |
| `test_assurance_offline`, `test_assurance_mlsys_offline`, `test_coding_agent_offline`, `test_jev_judge_offline` | 0 failures each |
| `test_judges_offline` | 2 failures, 4 skipped, **identical to the original tree** (stale $25 cap test; 4 tests need `wf_dev`/`ml_dev` rows that are not shipped) |
| `main_analysis.py --selftest`; `analysis_v2` recomputed | 0 failures; `main_analysis.json` and digest byte-identical |
| `raw_rows.py` | 19 of 19 match |
| `figure3.py --check` (analysis_v1 and analysis_v2) | identical to `figures/riskcov.tex` |
| `tables.py` | prints "Paper source not found … printing the rebuilt tables to compare with the paper's PDF", then Tables 3, 4 and 5 (46 lines); exit 0 |
| Paper compile | removed from the checks (the source is not in the folder) |
| Searches | 0 hits for "MLSys" and "coordinating session"; 0 references to dropped notes or dropped paper files except those in section 2 |

Analysis outputs other than `analysis_v2`, the domain tables, the summaries and `analysis_v1` were verified in the previous round and are unchanged: this round touched no row, no analysis script and no question file. I did not run `git init` anywhere in this round or the last two; the git workflow test (neutral author, clone byte-exact) predates the slimming.

## 7. Not done or not verified

- **WSL execution** against the folder (scripts now say `/home/user/...`), end-to-end Vouch reruns (paid calls; OTF programs need the withheld code), and rebuilds of Figures 1 and 2, the workflow documents and manufacturing/IT gold.
- **Anonymous mirror limits** are not confirmed for the hosted service (open-source defaults: 100 MB per file, 1,000 files per folder, 2 GiB free storage, a 60,000 KB constant I could not find applied). The folder has no file over 9.2 MB, no folder over 500 files and 202 MB in total. `--pack` is the fallback.
- **Provider terms** on redistributing LLM outputs: flagged in `NOTICE.md`, not reviewed.
- With the paper source gone, `tables.py` cannot compare cell by cell inside the anonymous GitHub source; the cell-by-cell check was run earlier on the working tree.

## 8. Decisions for you

1. The OTF-Tools name (30 files mention it) and `manifests/redesign_r1.diff` (9.5 KB, fragments of the withheld code as diff context).
2. Gold and keys are public in the artifact, as decided.
3. The D2 rewrite in section 2 (beyond your list).

## 9. Steps left for you

1. Rebuild after any further change to results, figures or `paper_numbers/`: `python -X utf8 acmtrust_paper/artifact/build_artifact.py`, then `verify_artifact.py` (expect exit 0).
2. Make the repository with a neutral author:

   ```bash
   cd /c/Users/aashraf/Desktop/Work/2026/vouch_artifact
   git init -b main
   git config user.name "Anonymous"
   git config user.email "anonymous@example.com"
   git add -A
   git commit -m "Anonymized artifact"
   git log --format="%an <%ae> | %cn <%ce>"
   ```

   The last command must print only `Anonymous <anonymous@example.com> | Anonymous <anonymous@example.com>`. Re-running the builder keeps `.git`.
3. Create an empty GitHub repository with a neutral name, `git remote add origin <url>`, `git push -u origin main`.
4. At anonymous.4open.science add the repository and list your GitHub login(s), your name and `aashraf` among the terms to replace. Open the mirror and check the README, `manifests/design_decisions.md` and a few `runs/` files for any personal string.
5. Put the mirror URL into the paper (paper session). Nothing in the anonymous GitHub source needs to change for that.

## Summary

1. Dropped 17 files from `acmtrust_paper/`: `main.tex`, the 11 section files, `macros.tex`, `references.bib`, `acmart.cls`, the `.bst` and `latexmkrc`. Kept `results.tex`, `figures/`, `sensitivity/` and `paper_numbers/` unchanged. The anonymous GitHub source is now 3,805 files, 202.2 MB.
2. README: "Rebuild the paper" removed; it says the paper is a PDF with the submission, describes `acmtrust_paper/`, and notes that `tables.py` prints the tables for comparison with the PDF. Dangling references fixed (the B0 note, three font comments, the `acmart` NOTICE row). One extra leak removed: D2's "Overlap and dual submission … No chair contact".
3. Scans are clean (0 identity, path and secret hits; none of the 4 `.env` values). Four of five offline suites pass and the fifth fails the same two stale tests as the original. `raw_rows.py` 19 of 19, `figure3.py --check` identical, `tables.py` prints the tables and exits 0, and the freeze check passes.
4. Searches: "cited anonymously", "under review", "third person" and "chair" have no hits; "double-blind" appears once in the README as a plain statement; "MLSys" and "coordinating session" have none. The remaining hits and reasons are in sections 2 and 5.
5. Left for you: the git steps in section 9 and the decisions in section 8.
