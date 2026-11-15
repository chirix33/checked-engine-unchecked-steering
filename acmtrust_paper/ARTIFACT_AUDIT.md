# Artifact audit for the anonymized mirror

Audit date 2026-11-14. Repository HEAD at the end of the audit: `5846430`. The audit was read-only; the only file written is this one.

**Do not ship this file.** It quotes identifying strings by file and line so that you can remove them. `.gitignore` lets `acmtrust_paper/**/*.md` through, so exclude it from the export by name.

Labels: **verified** = checked on files or by running a command here. **Proposal** = a suggestion, nothing done. **Open** = needs your decision. Secret values were never printed.

---

## 0. What matters most

1. **The working repository cannot be mirrored as is.** Its 100 commits carry the author's full name, a GitHub handle and a personal Gmail address. `origin` points to the author's personal GitHub account, and the repository name echoes the banned headline. Branches `main-g9xb04`, `old_paper` and `paper-draft` also exist, and several commit messages say "Updates from Overleaf". Build the artifact from a clean export with no history (section 7).
2. **The evidence behind every number is not in git.** `runs/` is ignored, so the decision rows, judge rows, B0 results, call ledgers (including the Jev ledger), test documents, analysis outputs and OTF programs are not tracked. A mirror of the tracked tree would hold the code and the questions but none of the results the paper reports as "in the artifact".
3. **The DEVS-Gen programs (22) exist only in WSL**, under `/home/aashraf/trust2027/gen/`, outside the repository. Without them nobody can rerun Vouch on those programs.
4. **One line names the authors' public OTF-Tools repository:** `manifests/domain_readiness.md:177`. This is the highest-priority fix.
5. **Seven LaTeX build files are tracked in `acmtrust_paper/build/`; three of them leak the local user name and path.** These are `main.fls`, `main.fdb_latexmk` and `main.log` (1,333 matching lines between them). The other four (`.aux .bbl .blg .out`) have no hit, but the whole folder is junk for an artifact.
6. **213 lines in 44 tracked files** name the author, a supervisor or a local path. Nine of those files are hash-frozen by `manifests/freeze_v1.json`. Scrubbing them changes their sha256, so the freeze check will fail unless you also publish a mapping (section 7, step 4).
7. **No secrets found.** No key-shaped strings in tracked files, `runs/`, `validation/`, `manifests/` or the WSL program trees. None of the four `.env` values appears literally in any of the 9,934 files scanned. `.env` is ignored and never appeared in git history.
8. **Reproduction gaps.** There is no generator for Figure 3 (`figures/riskcov.tex`) and none for the macros that `results.tex` labels "raw rows". The README has no analysis path and points to an ignored 10 GB interpreter (`.tools/`).
9. **Size is not a problem.** The tracked tree is 16.8 MB. No file to ship is over 10 MB (the largest is 9.2 MB), so the 50 MB and 100 MB limits are not an issue.

---

## 1. What the paper promises, and where it lives

Status: **ok**, **missing**, **not tracked** (file exists on disk but git ignores it) or **needs anonymizing**.

| # | Promise (source) | Location | Tracked by git? | Status |
|---|---|---|---|---|
| 1 | "the code" (`09_conclusion.tex`, Artifact) | `assurance/` (11 files), `redesign/otf_r1/` (8), `adapters/` (17), `scripts/` (90), `reference_engine/` (1), `checker/` (24), `validation/` (646, including `fuzz_v1/` with 500), `spec/` (69) | yes, 1,037 tracked files in total | **needs anonymizing** (section 3) |
| 1b | the task specs the coding agent and the DEVS-Gen tasks were given | `adapters/generic_tasks/{ITOperations,Manufacturing,WorkflowLoan,WorkflowPharmacy}/spec.md` (4 files); `scripts/coding_agent_build.py` and `scripts/judges.py` read them; `scripts/make_generic_task_specs.py` regenerates them | the `.md` files **no** (`*.md` rule in `.gitignore`); the `.json` specs and the script yes | **not tracked**. Ship them. Also ignored by `*.md`: 33 blind-review step and concern notes under `validation/blind_review*/agent_*/` (230 KB together). They have no identity or path hits, and are optional evidence for the gold check |
| 1a | the programs Vouch was run on (needed to rerun Vouch, task item 3c) | OTF programs: 120 `program.json` under `runs/build_test_{b0_claude,v1,r1,r1_claude}/` (11 MB). Coding-agent programs: 17 `run.py` under `runs/coding_agent/` (1.3 MB). DEVS-Gen programs: 22 `run.py` plus project folders **only in WSL** `~/trust2027/gen/` (15.6 MB, 1,715 files) | no (`runs/` ignored; WSL is outside the repo) | **not tracked**; DEVS-Gen is **missing** from the repo tree |
| 2 | "questions" | `manifests/workflow_questions_test_v1.json` (240), `workflow_questions_policy_v1.json` (91), `mlsys_questions_dev_v1.json`, `mlsys_questions_test_v1.json` (216), `pilot_questions_v1.json`, with `.sha256`, splits and id maps. They carry a `gold` field. | yes | **ok** (but see open question 2 on gold) |
| 2a | the documents the programs read | `runs/workflow_docs/` (2.8 MB), `runs/mlsys_docs/` (3.6 MB), `runs/build_test_v1/docs/` (0.5 MB) | no | **not tracked**. Workflow docs regenerate with `workflow_test_set.py docs`; manufacturing/IT docs need raw data from outside the repo |
| 3 | "program list" | `manifests/freeze_v1.json` → `programs.names`: 118 names (80 OTF = 48 R1 + 32 B0, 22 DEVS-Gen, 16 agent). Also `runs/devs_gen/generation_index.jsonl` (32 attempts, failures included) and `runs/coding_agent/index.jsonl` (16) | `freeze_v1.json` yes; the two indexes no | **ok** (list), **not tracked** (indexes). A plain `program_list.csv` with platform, model, domain and accepted flag would help reviewers (proposal) |
| 4 | "judge prompts" | `scripts/judges.py` (`PROMPT_VERSION judges-v2`; answer-level, program-level, ReAct), `scripts/jev_judge.py` (`jev-v1`), `assurance/interpret.py` (`PROMPT`), `redesign/otf_r1/prompts.py`, `scripts/coding_agent_build.py` (`SYSTEM`) | yes | **needs anonymizing** (judges.py:72, :837; jev_judge.py:1) |
| 5 | "decision rows" | rule-judge rows: `runs/main_v1/{wf_test,ml_test,wf_policy,wf_dev,ml_dev}/programs/*.jsonl` (plus `interpret.jsonl`, `vanilla.jsonl`, `rag.jsonl`, `registries/`). LLM, ReAct and Jev judge rows: `runs/judges_main_v1/*/judgments_*.jsonl` (13 folders, 34 MB) | no | **not tracked**; also contain `/home/aashraf/...` in stack traces (section 3.4) |
| 6 | "analysis scripts" | `scripts/main_analysis.py`, `main_summary.py`, `domain_tables.py`, `report_tables.py`, `jev_long_context_table.py`, `family_effect_summary.py`; `acmtrust_paper/sensitivity/{run_clustered,paper_claims,fresh_record_rows,fresh_record_rerun,fresh_record_compare,compare}.py` and the two shell wrappers | yes | **needs anonymizing**. The sensitivity shell wrappers hard-code `cd "/c/Users/aashraf/..."` (`run_fresh_check.sh:3`, `run_fresh_rerun.sh:3`) |
| 7 | "Exact selection rules and tolerances are in the artifact" (`03_method.tex:35`) | `assurance/policy.py` (decision), `probes.py`, `binding.py`, `contract.py`, `mlsys.py`, `answer.py`; scoring tolerance in `scripts/main_summary.py` (`correct`: numbers within 1, booleans exactly); semantics in `spec/workflow_semantics_v1.md`; decisions in `manifests/design_decisions.md` | yes | **needs anonymizing** (policy.py:195 is frozen) |
| 8 | "unchanged original OTF-Tools builds (B0, 32 of 60 accepted) … reported in the artifact" (`04_benchmark.tex:36`) | B0 builds: `runs/build_test_b0_claude/` (24 builds, Claude, 4.6 MB) and `runs/build_test_v1/` (36 builds, open models, 8.5 MB). B0 decision rows: native-only rows in `runs/main_v1/*/programs/`. Tracked summaries: `manifests/build_test_summary_v1.json`, `manifests/compare_b0_r1_v1.json` | summaries yes; builds and rows no | **not tracked** (partial). I did not find the string "32 of 60" in any tracked file; the count has to be derived from `builds_*.jsonl`. A short `b0_results.md` that states it would close the promise (proposal) |
| 9 | "All model calls, tokens, costs and failures are logged in the artifact" (`10_genai_disclosure.tex:6`) | 20 `calls_*.jsonl` ledgers (about 12 MB) under `runs/build_test_{main_claude,judges,pilot_claude,assurance_claude,coding_agent,b0_claude,r1,r1_claude,v1}/`; Jev ledger `runs/judges_jev_ledger/calls_jev-1.14.0.jsonl` (3,410 lines, matches the paper's "3,410"); `runs/devs_gen/generation_tokens.jsonl`; build logs `console_*.log`; per-row cost in the judgment rows | no | **not tracked** |
| 10 | every `results.tex` macro names its source | `runs/main_v1/analysis_v1/{main_analysis.json,tables.md}` (12 judge runs) and `analysis_v2/` (13, adds Jev); `domain_tables_v{1,2}/`; `jev_long_context_v1/` | no | **not tracked**. The run-clustered versions are tracked in `acmtrust_paper/sensitivity/analysis_v{1,2}_runclustered/`; `manifests/main_results_v1.md` is tracked |
| 10a | macros marked "raw rows" in `results.tex` (for example `\rReactRanProgHaiku`, `\rUntestableRightNoEffect`, `\rGptossUnparsed`) | computed from the decision rows | — | **missing**: I found no tracked script that produces them (searched `scripts/` and `sensitivity/`). Add one, or say in the README how they were counted |
| 11 | Figure 3 (`figures/riskcov.tex`) | its header says "Generated from runs/main_v1/analysis_v1/main_analysis.json … regenerate" | the `.tex` yes | **missing**: no generator in the tracked tree |
| 12 | Figure 1 source | `acmtrust_paper/figures/src/history_gap/` (React/Vite/Playwright, `build.sh`) | no (`.gitignore:2`) | **not tracked**. The built `figures/history_gap.pdf` is tracked. Needs Node and a Chromium for Playwright |
| 13 | "the workflow models are under CC BY 4.0" | `data/zenodo_10435849/` (18.8 MB: `inputs.zip` plus extracted models) | no | pointer is enough (section 5) |

---

## 2. Reproducibility

**(a) Recompute the paper's numbers from the decision rows.** Verified: the scripts exist and are tracked. Their usage lives only in their docstrings, not in `README.md`:

```bash
.tools/b0_env/Scripts/python.exe -X utf8 scripts/main_analysis.py . runs/main_v1/analysis_v2 --judges-dir runs/judges_main_v1
.tools/b0_env/Scripts/python.exe -X utf8 scripts/report_tables.py runs/main_v1/analysis_v2/main_analysis.json runs/main_v1/analysis_v2/tables.md
.tools/b0_env/Scripts/python.exe -X utf8 scripts/domain_tables.py . runs/main_v1/domain_tables_v2 --sets wf_test,ml_test
.tools/b0_env/Scripts/python.exe -X utf8 scripts/jev_long_context_table.py . runs/main_v1/jev_long_context_v1
.tools/b0_env/Scripts/python.exe -X utf8 acmtrust_paper/sensitivity/run_clustered.py . acmtrust_paper/sensitivity/analysis_v2_runclustered
.tools/b0_env/Scripts/python.exe -X utf8 acmtrust_paper/sensitivity/paper_claims.py <frozen.json> <clustered.json> <out.md>
```

These are my reconstruction from docstrings and `run_manifest.md:1679`, not commands I ran. `analysis_v1.log` and `analysis_v2.log` record only row counts, not the command line, so the exact arguments for v1 and v2 should be written into the artifact README. All of these read `runs/`, which a tracked-only mirror lacks.

**(b) Regenerate tables and figures.** Partly. `results.tex` holds every number the prose quotes, but I did not trace how each cell of the tables in `sections/06_results.tex` is produced. Figure 3 has no generator (row 11). Figure 1 needs Node, Playwright and a browser (row 12). Figure 2 (`pipeline.tex`) is hand-drawn TikZ and needs nothing.

**(c) Rerun Vouch on the programs.** Possible only with extra material that is outside git:
- the OTF `program.json` files and indexes under `runs/`;
- the DEVS-Gen programs, found through `runs/devs_gen/generation_index.jsonl` and `/home/aashraf/trust2027/gen/...` (hard-coded at `scripts/main_runner.py:176` and `scripts/pilot_runner.py:202`);
- the coding-agent programs, whose `dir` fields point to `/home/aashraf/trust2027/coding_agent/...`;
- the pinned OTF-Tools clone `baseline/otf-tools-10f5401/implementation-1`, which R1 and B0 import at run time (`assurance/backends.py:123-126`, `scripts/b0_build_test.py:324-327`);
- WSL with bubblewrap and the seccomp filter, built by `scripts/make_seccomp_filter.py`;
- paid API keys for any step that makes model calls. The cached interpretations (`interpret.jsonl`) and reading answers (`vanilla.jsonl`, `rag.jsonl`) are in `runs/main_v1/<set>/`, so the program stage should not need a model call, but I did not test that.

**Offline tests.** There are five suites in `scripts/`: `test_assurance_offline.py`, `test_assurance_mlsys_offline.py`, `test_judges_offline.py`, `test_coding_agent_offline.py` and `test_jev_judge_offline.py`. The README lists only the first four. I did not run any of them (read-only audit). `test_judges_offline.py:644` asserts that the WSL sandbox lists a user directory named `aashraf`, so a blind rename of the user breaks that test.

**Environment pin.**
- Tracked: `manifests/requirements_b0.lock` (31 packages, Windows, CPython 3.12.16) and `manifests/requirements_p0.lock` (44 packages, `prosimos==2.1.0`).
- Not tracked: `.tools/` (10 GB) and `.venv/` (0.6 GB), so the interpreter the README names does not exist in a fresh checkout.
- Not in the repo: the WSL DEVS-Gen environment (`~/trust2027/requirements.lock`, Python 3.10.19) and the DEVS-Gen release (`f7461b9f9d23`; `scripts/wsl_setup_devs_gen.sh` clones it).
- There is no `requirements.txt` or `pyproject.toml` at the root. The artifact README needs a `python -m venv` plus `pip install -r manifests/requirements_b0.lock` line, and the Python and WSL versions.

**Hard-coded paths in code** (all names also listed in section 3.2):
- `scripts/check_builder_isolation.py:34-35,54-58`
- `scripts/coding_agent_build.py:31,71,240`
- `scripts/devs_gen_mlsys_build.py:42,100,130,171,198,258`
- `scripts/main_runner.py:176`
- `scripts/pilot_runner.py:202`
- `scripts/mlsys_gold.py:32` (an absolute path into the authors' other project)
- `scripts/wsl_sandbox_check.sh:7`
- `scripts/wsl_scan_workflow_programs.sh:2,8`
- `acmtrust_paper/sensitivity/run_fresh_check.sh:3` and `run_fresh_rerun.sh:3`

Everything else takes `<root>` on the command line.

---

## 3. Anonymization hits (tracked files, outside `acmtrust_paper/build/`)

Search terms: `ashraf|aashraf|chirix|crimson|ua.edu|alabama`, local paths, links, supervisor and project self-references. Counts: 213 matching lines in 44 files; 45 files if the path-only hit in `test_coding_agent_offline.py:206` is included.

### 3.1 Critical: link to the authors' public OTF-Tools repository, and the pinned clone

| file:line | what | suggested fix |
|---|---|---|
| `manifests/domain_readiness.md:177` | names the authors' public GitHub repository for the OTF-Tools code and documents | change to "The reference code and documents are public, so there is a memorization risk for all builder and judge models." (no repository name) |
| `manifests/run_manifest.md:11` | "Baseline clone `baseline/otf-tools-10f5401`, commit `10f540118756…`" | keep the commit only if open question 3 says the baseline ships; otherwise "pinned baseline clone (commit withheld for review)" |
| `assurance/backends.py:126`, `scripts/b0_build_test.py:327`, `scripts/check_builder_isolation.py:46` | the path `baseline/otf-tools-10f5401/implementation-1` | functional, and `backends.py` and `b0_build_test.py` are frozen. Leave it unless you rename the folder everywhere; see open question 3 |
| `manifests/run_manifest.md:1699` | "Paper files are not committed; they may need syncing with Overleaf" | delete the clause |
| `acmtrust_paper/README.md:23, 45` | OTF-Tools paper cited anonymously; "Ashraf owns [the overlap statement]" | drop this file from the export, or rewrite without names |

Note for you, not an artifact issue: `domain_readiness.md:177` says the OTF-Tools repository is public. The paper names the system "OTF-Tools", so a reviewer who searches the name may find it. That is a call about the paper, not the artifact.

### 3.2 Code and scripts: names and local paths

"Frozen" means `manifests/freeze_v1.json` records the file's sha256 (section 7, step 4).

| file:line | hit | suggested fix |
|---|---|---|
| `assurance/policy.py:195` (frozen) | comment "(form (b), Ashraf 2026-11-07)" | "(form (b), chosen 2026-11-07)" |
| `assurance/request.py:66` (frozen) | docstring "(Ashraf, 2026-11-09; changed after the development pilot)" | "(2026-11-09; changed after the development pilot)" |
| `scripts/judges.py:72, :837` (frozen) | "# Ashraf, 2026-11-08" and "(Ashraf, 2026-11-10)" | drop the name, keep the date |
| `scripts/b0_build_test.py:24, :27` (frozen) | "Ashraf reported a balance…" and "(D27, D29; Ashraf, 2026-11-10)" | "(balance reported 2026-11-10)" and "(D27, D29; 2026-11-10)" |
| `scripts/main_summary.py:6` (frozen) | "(Ashraf, 2026-11-09)" | "(2026-11-09)" |
| `scripts/main_runner.py:176` (frozen) | `/home/aashraf/trust2027/gen/...` | `/home/user/trust2027/gen/...` and document the layout |
| `scripts/pilot_runner.py:202` (frozen) | same path | same fix |
| `scripts/coding_agent_build.py:31, :71, :240` (frozen) | `/home/aashraf/trust2027/coding_agent`, `/home/aashraf` | `/home/user/...` |
| `scripts/check_builder_isolation.py:34, :35, :54-58` (frozen) | `C:\Users\aashraf\Desktop\Work\2026\ACM Trust 2027`, its `/mnt/c/...` twin, and the exclusion list (`.claude`, `.git-credentials`, `.ssh`, `\\wsl$\...\home\aashraf\...`) | `C:\Users\user\...`; keep the list shape because it documents the isolation check |
| `runs/coding_agent/index.jsonl`, `runs/devs_gen/generation_index.jsonl` (frozen) | `dir` / `program_dir` fields with `/home/aashraf/...` | `/home/user/...` |
| `scripts/devs_gen_mlsys_build.py:42, :100, :130, :171, :198, :258` | `/mnt/c/Users/aashraf/...`, `/home/aashraf/...` | `/mnt/c/Users/user/...`, `/home/user/...` |
| `scripts/mlsys_gold.py:32` | absolute `C:\Users\aashraf\Desktop\Work\2026\MLSystem 2027\implementation-1\data\domains\raw` | read from an environment variable such as `MLSYS_RAW` and document it |
| `scripts/test_judges_offline.py:641, :642, :644` | `aashraf` in sandbox expectations | replace with `user` in the code and the expected listing together |
| `scripts/test_coding_agent_offline.py:206` | path hit (no user name seen) | check by eye |
| `scripts/test_assurance_offline.py:408` | "(Ashraf, 2026-11-09)" | "(2026-11-09)" |
| `scripts/wsl_sandbox_check.sh:7` | `/home/aashraf/...` | `/home/user/...` |
| `scripts/wsl_scan_workflow_programs.sh:2, :8` | `/home/aashraf/trust2027/gen` | `/home/user/trust2027/gen` |
| `scripts/domain_tables.py:1`, `jev_judge.py:1`, `main_analysis.py:83`, `pilot_attribution.py:7`, `pilot_rerun_routing_b.py:3`, `workflow_policy_set.py:1`, `make_workflow_policy_questions.py:1`, `make_workflow_blind_sample.py:7`, `make_mlsys_blind_sample.py:6`, `make_mlsys_splits.py:10` | "Ashraf's plain terms", "(Ashraf, 2026-11-12)" and similar in docstrings and comments | "the project's plain terms" or just delete the name |
| `acmtrust_paper/sensitivity/run_fresh_check.sh:3`, `run_fresh_rerun.sh:3` | `cd "/c/Users/aashraf/Desktop/Work/2026/ACM Trust 2027"` | `cd "$(dirname "$0")/../.."` |
| `acmtrust_paper/sensitivity/fresh_record/check_shard0.jsonl:6`, `rerun_shard10.jsonl:49`, `rerun_shard11.jsonl:49` | stack traces with local paths | replace `aashraf` with `user` |
| `manifests/probe_soundness_mlsys_v3_dev.json:500`, `probe_soundness_mlsys_v4_dev.json:500` | `C:\Users\aashraf\...\mlsys_questions_dev_v1.json` | `manifests/mlsys_questions_dev_v1.json` |
| `manifests/mlsys_raw_hashes_v1.json:2` | `"root": "C:\\Users\\aashraf\\Desktop\\Work\\2026\\MLSystem 2027\\implementation-1\\data\\domains\\raw"` | `"root": "<raw data directory>"` |

### 3.3 Manifests (markdown)

Replace "Ashraf" with "the author", "Ashraf's" with "the author's", "Dr. Roy" with "the advisor", and `C:\Users\aashraf\...` with `<project root>`. Do it with a script, then read each result. A few lines need rewording.

| file | lines | extra note |
|---|---|---|
| `manifests/design_decisions.md` (54) | 3, 5, 9, 13, 17, 21, 25, 42, 63, 73, 75, 84, 86, 100, 102, 104, 108, 116, 118, 122, 146, 150, 169, 197, 210, 212, 214, 223, 258, 260, 264, 309, 320, 324, 347, 349, 364, 387, 415, 458, 489, 508, 518, 555, 557, 559, 567, 576, 583, 588, 604, 607, 615, 619 | also 366 (a meeting with "Dr. Roy"); 260 ("Ashraf's $100 in Anthropic credits") and 604 ("Ashraf's key") name the person and the account |
| `manifests/run_manifest.md` (66) | 16, 70, 103, 147, 180, 378, 391, 410, 424, 432, 433, 436, 438, 443, 445, 446, 450, 455, 456, 461, 471, 472, 481, 597, 602, 612, 616, 618, 670, 684, 730, 780, 808, 875, 878, 879, 880, 883, 951, 968, 970, 1077, 1181, 1204, 1315, 1389, 1488, 1489, 1496, 1497, 1498, 1512, 1546, 1549, 1550, 1554, 1555, 1560, 1572, 1588, 1594, 1620, 1709, 1714 | also 994 (`/home/aashraf/trust2027/coding_agent/...`), 1168 ("the user is `aashraf`"), 434 ("Dr. Roy"), 13 and 11 (see 3.1) |
| `manifests/baseline_judges_design.md` (11) | 3, 56, 68, 69, 88, 117, 121, 123, 128, 135, 155 | also "Dr. Roy" at 3, 7, 29, 167, 178, 194; line 123 quotes the ReCode GitHub URL (third party, fine) |
| `manifests/workflow_test_set.md` (9) | 4, 10, 51, 53, 157, 209, 214, 256, 335 | line 51 says "`.gitignore`, owned by Ashraf" |
| `manifests/domain_readiness.md` (6) | 5, 160, 170, 177, 186, 292 | 177 is the critical line; 179 and 224 name the authors' other project folder |
| `manifests/main_results_v1.md` (4) | 346, 347, 368, 432 | |
| `manifests/builder_isolation.md` (4) | 33, 48, 49, 50 | local paths including `C:\Users\aashraf\.claude\` and the session scratch folders |
| `manifests/pilot_report.md` (3) | 13, 105, 396 | |
| `manifests/jev_judge_design.md` (3) | 3, 71, 72 | line 72 names the key variable `TYPESAFE_API_KEY` and whose account it is |
| `manifests/blindspots.md` | 290 | |
| `acmtrust_paper/README.md` | 45 | drop the file from the export |

### 3.4 Run outputs, if you ship them

Stack traces and logs carry `/home/aashraf/...` and `C:\Users\aashraf\AppData\Local\Temp\tmp...`. Verified counts of files with a hit:

| folder | files with a hit |
|---|---|
| `runs/main_v1/wf_test` | 26 of 247 |
| `runs/main_v1/ml_test` | 8 of 237 |
| `runs/main_v1/wf_policy` | 12 of 194 |
| `runs/main_v1/wf_dev` | 25 of 197 |
| `runs/main_v1/ml_dev` | 4 of 240 |
| `runs/main_v1/logs` | 25 of 220 |
| `runs/main_v1/domain_tables_v2` | 1 of 2 (header text "Ashraf's plain terms") |
| `runs/judges_main_v1` | 9 of 56 |
| `runs/build_test_v1` | 44 of 124 |
| `runs/build_test_r1` | 61 of 117 |
| `runs/build_test_r1_claude` | 16 of 78 |
| `runs/build_test_b0_claude` | 13 of 76 |
| `runs/coding_agent` | 18 of 138 |
| `runs/devs_gen` | 9 of 12 |

Clean (0 hits): `analysis_v1`, `analysis_v2`, `jev_long_context_v1`, `judges_jev_ledger`, `build_test_main_claude`, `build_test_judges`, `workflow_docs`, `mlsys_docs`, `workflow_test_v1`, `workflow_policy_v1`, `validation_v1`.

Suggested fix: byte-level replace `aashraf` → `user` in paths, only in the shipped copies. The WSL program folders (`gen_meta.json`, `run_*.log`) have the same problem.

### 3.5 Tracked build files

| file | hits | fix |
|---|---|---|
| `acmtrust_paper/build/main.fls` | 732 lines with `C:\Users\aashraf\...MiKTeX` | exclude the whole `acmtrust_paper/build/` folder (7 tracked files: `.aux .bbl .blg .fdb_latexmk .fls .log .out`) |
| `acmtrust_paper/build/main.fdb_latexmk` | 343 | same |
| `acmtrust_paper/build/main.log` | 258 | same |

Recommend adding `acmtrust_paper/build/` to `.gitignore` and running `git rm -r --cached acmtrust_paper/build`. You own `.gitignore`, so I changed nothing.

### 3.6 Other places a mirror could expose the author

- **Git metadata** (section 0, item 1). Do not push this repository. Export files, then `git init` with a neutral author such as `Anonymous <anonymous@example.com>`.
- **The word "mlsys" in names.** 65 tracked paths contain it (for example `assurance/mlsys.py`, `manifests/mlsys_questions_test_v1.json`, `scripts/make_mlsys_*.py`), the text of 52 tracked files mentions it, and the set names are `ml_dev` and `ml_test`. Prose in `builder_isolation.md:48` ("MLSys raw records and the MLSys reference code"), `domain_readiness.md:179,224` and `run_manifest.md:13` ("Saved MLSys results") says the authors have an MLSys project. This is low risk, since the paper itself cites OTF-Tools as an anonymous paper under review, but those prose lines are easy to neutralize ("an earlier benchmark release"). Renaming files would break frozen hashes; I would not.
- **Figure and PDF metadata.** `figures/history_gap.pdf` and `history_gap_col.pdf`: title only, creator string "Mozilla/5.0 (Windows NT 10.0; Win64; x64…)" and producer "Skia/PDF m157", no author. `build/main.pdf` (ignored): producer MiKTeX-pdfTeX, no author. No identifying strings inside decompressed streams. The unused `figures/src/history_gap_col/history_gap_col_preview.png` has only a resolution chunk. No notebooks exist in the repo.
- **Paper source.** `main.tex` has the anonymous author block and no `pdfauthor`. `references.bib` cites `otftools2026` as `{Anonymous}`, "Under review". No hits in `sections/`, `macros.tex` or `results.tex`.
- **Untracked files that must not be copied by hand:** `otf-tools.pdf` (the authors' own paper; ignored by `*.pdf`), `AGENTS.md` and `RESEARCH_DIRECTION.md` (ignored by `*.md`; name the author and the MLSys submission), `meeting/` (transcripts naming the supervisor), `papers/` (other people's PDFs), `gap-figure/` (120 MB), `skills-lock.json`, `.agents/`, `.claude/`, `.env`.
- **Links.** The only external hosts in tracked files are: `github.com` (the DEVS-Gen clone and uv download in `scripts/wsl_setup_devs_gen.sh:10,29`), `zenodo.org`, `openrouter.ai`, `ollama.com`, `docs.typesafe.ai` and `api.typesafe.ai` (`references.bib:305`, `jev_judge.py:67`), `api.anthropic.com`, `www.omg.org`, `jmlr.org`, and `127.0.0.1` proxies. None is a personal site or the authors' GitHub, apart from item 3.1.

---

## 4. Secret findings

Verified results; no value was printed.

- **Tracked files** (1,037): no key-shaped strings (`sk-ant-`, `sk-or-`, `sk-`, `ghp_`, `github_pat_`, `AKIA`, `AIza`, private-key blocks, `Bearer <token>`).
- **`runs/`, `validation/`, `manifests/`**: no key-shaped strings.
- **WSL `gen/`, `coding_agent/`, `judge_sandbox/`, `sandbox_probe_lib/`**: no key-shaped strings, and no file names a key variable.
- **Literal values from `.env`**: I loaded the four values in a script and searched every file in the repo tree (9,934 files, excluding `.tools/`, `.venv/`, `.git/`, `node_modules/`, and `data/`). No file contains any of them.
- **`.env`**: keys present: `OPENROUTER_API_KEY`, `OLLAMA_API_KEY`, `ANTHROPIC_API_KEY`, `TYPESAFE_API_KEY`. It is ignored (`.gitignore:20`) and has never been in any commit.
- **Key names appear in tracked code as environment lookups only** (no values):
  - `scripts/b0_build_test.py:36,43,46,48,51`: `OLLAMA_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`
  - `scripts/devs_gen_mlsys_build.py:53,59,61,62`: `ANTHROPIC_API_KEY`
  - `scripts/jev_judge.py:33,69`: `TYPESAFE_API_KEY`
  - `scripts/model_connection_test.py:22,26,29`; `scripts/model_endpoint_check.py:40,46,48`
  - `scripts/test_judges_offline.py:570,596,600,606`
  - `scripts/wsl_devs_gen_isolated_generate.sh:11,22,153,195`
  - `manifests/design_decisions.md:604`; `manifests/jev_judge_design.md:72`; `manifests/run_manifest.md:1162,1196,1655`

  These are fine to ship. Line 604 of `design_decisions.md` and line 72 of `jev_judge_design.md` also say whose key it is; see 3.3.
- **Not checked:** the content of `.git/` objects (history) for secrets. The history check I did covers file names only: `.env` was never added.

---

## 5. Licences

| material | licence (source) | redistribute in the mirror? |
|---|---|---|
| Workflow models and logs, Zenodo record 10435849 | CC BY 4.0 (the paper states it, citing `chapela2023zenodo`; I did not re-read the Zenodo page, and `data/zenodo_10435849/` holds no licence file) | allowed with attribution, but **a pointer is enough**: URL, `manifests/workflow_model_inventory.json` (already lists the models) and the hashes. Skip the 18.8 MB copy. The generated documents (`runs/workflow_docs`, 2.8 MB) are derived from it; ship them with an attribution line stating that they are derived |
| SupplyGraph (manufacturing) | LGPL-2.1 per `baseline/.../docs/domains/README.md` (written by the authors from the upstream `LICENSE`; I did not re-check upstream) | **pointer** (upstream URL plus the hashes in `manifests/mlsys_raw_hashes_v1.json`). Whether derived documents under `runs/mlsys_docs` can be shipped is open question 7 |
| Google 2011 cluster trace (IT operations) | CC BY 4.0 per the same note | pointer, plus attribution (Reiss, Wilkes and Hellerstein 2011); derived documents are allowed with attribution |
| OTF-Tools baseline code (`baseline/otf-tools-10f5401`) | the authors' own work, no top-level `LICENSE` in the clone (only `third_party/recode/LICENSE`, MIT) | open question 3. If shipped, include only `implementation-1/otf/` and what R1 and B0 import, not `.git/` (its remote is a local path with the user name) and not `implementation-1/runs/` (232 MB of the MLSys paper's own results) |
| DEVS-Gen (`devs_gen_code`, release `f7461b9f9d23`) | Apache-2.0 (`devs_gen_code/LICENSE` in WSL) | **pointer**: do not vendor its 558 MB. Ship our hooks and task files (`adapters/devs_gen_hooks`, `adapters/devs_gen_tasks`) and the setup script. The generated program folders may embed DEVS-Gen template code; ship them with a short NOTICE saying so |
| ReCode (`baseline/.../third_party/recode`) | MIT, Foundation Agents | not used by the final paper; do not ship |
| Fonts: Source Sans 3 in `figures/src/history_gap_col/fonts/*.woff2` | SIL OFL 1.1 (`LICENSE-OFL.txt` sits beside them) | may be redistributed with the licence file. That folder is the rejected, unused single-column redesign, so leave the whole folder out. `history_gap/` takes the same font from the npm package `@fontsource/source-sans-3` (OFL), which `npm install` fetches |
| `acmart.cls`, `ACM-Reference-Format.bst` | LPPL 1.3c / ACM, as distributed on CTAN | allowed; or omit and say "install from CTAN" |
| Python and npm dependencies | their own licences | pointer through the lock files |
| Our code, questions and manifests | **no `LICENSE` file at the repository root** | add one (open question 6) |
| LLM outputs (programs, judge rows) | provider terms | I did not review Anthropic, Ollama Cloud or TypeSafe terms on redistributing outputs; check before shipping the rows |

---

## 6. Size

Verified on disk (sizes are `du` block sizes, so they run slightly high). The proposed paper-evidence set in section 7 adds up to about 172 MB from `runs/` plus 15.6 MB of WSL programs, about 187 MB before compression (not measured after compression). That sums the scored sets (82), analysis (6.2), judges and Jev ledger (35.5), ledger folders (11.8), B0 builds (13.2), R1 builds (15.3), agent and DEVS-Gen indexes (1.4) and documents (6.4).

| group | size | note |
|---|---|---|
| tracked tree, without `acmtrust_paper/build/` | 16.8 MB | `manifests` 6.4, `acmtrust_paper` 7.8 (mostly `sensitivity/`: two run-clustered `main_analysis.json` of 2.3 and 2.6 MB, `fresh_record/` 4 MB), `validation` 0.9, `scripts` 0.9, `checker` 0.2, `spec` 0.06 |
| `runs/main_v1/{wf_test,ml_test,wf_policy}` | 82 MB | decision rows for the three scored sets |
| `runs/main_v1/{wf_dev,ml_dev}` | 33 MB | development sets, optional |
| `runs/main_v1/analysis_v1,analysis_v2,domain_tables_v1,domain_tables_v2,jev_long_context_v1` | 6.2 MB | |
| `runs/main_v1/logs` | 15.5 MB | 5.4 MB is a model-server log (`ollama_serve_2.log`); leave it out |
| `runs/judges_main_v1` + `runs/judges_jev_ledger` | 35 MB | |
| ledgers: `runs/build_test_{main_claude,judges,pilot_claude,assurance_claude,coding_agent}` | 11.8 MB | |
| B0 builds: `runs/build_test_b0_claude` + `runs/build_test_v1` | 13.2 MB | |
| R1 builds: `runs/build_test_r1` + `runs/build_test_r1_claude` | 15.3 MB | |
| `runs/coding_agent` + `runs/devs_gen` | 1.4 MB | |
| `runs/workflow_docs` + `runs/mlsys_docs` | 6.4 MB | |
| DEVS-Gen programs, WSL `~/trust2027/gen` | 15.6 MB | `run.py` files are 240 KB; the rest is project folders and caches |
| reference-engine outputs `runs/workflow_test_v1,workflow_policy_v1,validation_v1` | 237 MB | regenerable; leave out |
| `data/` 18.8 MB, `baseline/` 258 MB, `checker/out/`, `gap-figure/` 120 MB, `.tools/` 10.4 GB, `.venv/` 0.6 GB | | leave out |

**Files over 5 MB in the proposed set:** `runs/judges_main_v1/main_react_qwen150/judgments_qwen3.5-9b.s0of1.jsonl` (9.2 MB) and `runs/build_test_main_claude/calls_claude-haiku-5-5.jsonl` (7.1 MB). **No file is near 50 MB, and none exceeds 100 MB**; the only file above 20 MB outside `.git/`, `.tools/` and `.venv/` is a git pack inside `baseline/` (24.5 MB), which is excluded. I recall that some anonymous-mirror services cap file size (around 8–10 MB) but did not verify; if yours does, split the Qwen judgment file by shard or gzip it, and note the change in the README.

---

## 7. Proposed include / exclude list and plan (proposal only; nothing done)

### Include

| path | from | note |
|---|---|---|
| `assurance/`, `redesign/otf_r1/`, `adapters/`, `scripts/`, `reference_engine/`, `checker/` (without `checker/out/`), `spec/`, `validation/` | tracked, plus 37 ignored `.md` files | scrub per section 3. Copy the ignored `adapters/generic_tasks/*/spec.md` (4) and, optionally, the 33 blind-review notes by hand, since `git archive` skips them. `validation/` holds the evaluation-only keys and blind samples; the paper says these never reach a system under test, and they do not |
| `manifests/` | tracked | scrub per 3.1 and 3.3 |
| `acmtrust_paper/results.tex`, `sensitivity/`, `figures/*.tex`, `figures/history_gap.pdf`, `macros.tex`, `references.bib`, `sections/`, `main.tex` | tracked | optional as a group (open question 10); `results.tex` and `sensitivity/` are the traceable part |
| `acmtrust_paper/figures/src/history_gap/` | ignored | only `build.sh`, `package.json`, `package-lock.json`, `index.html`, `scripts/`, `src/`, `vite.config.js`; no `node_modules`, no `history_gap_col` |
| `runs/main_v1/{wf_test,ml_test,wf_policy}`, `analysis_v1`, `analysis_v2`, `domain_tables_v1`, `domain_tables_v2`, `jev_long_context_v1` | ignored | scrub paths |
| `runs/judges_main_v1/`, `runs/judges_jev_ledger/` | ignored | scrub paths |
| `runs/build_test_*` **ledgers** (`calls_*.jsonl`, `builds_*.jsonl`, `console_*.log`) | ignored | scrub paths |
| `runs/build_test_{b0_claude,v1,r1,r1_claude}` programs (`program.json`) | ignored | B0 results and the OTF programs |
| `runs/devs_gen/{generation_index.jsonl,generation_tokens.jsonl}`, `runs/coding_agent/` | ignored | scrub paths; copy WSL `gen/**/run.py` and `devs_project` (without `.db` caches and `gen_meta.json` path fields) into a new folder such as `programs/devs_gen/` |
| `runs/workflow_docs/`, `runs/mlsys_docs/` | ignored | open question 7 for `mlsys_docs` |
| `runs/main_v1/{wf_dev,ml_dev}` and the pilot folders | ignored | optional; the paper does not rely on them |
| new files | — | `README.md` (artifact version), `LICENSE`, `NOTICE`, `data/README.md` with pointers and hashes, `program_list.csv`, `b0_results.md`, `anonymization_map.json` (step 4), a lock file for the WSL environment |

### Exclude

`.git/`, `.env`, `.env.*`, `.venv/`, `.tools/`, `.agents/`, `.claude/`, `skills-lock.json`, `otf-tools.pdf`, `AGENTS.md`, `RESEARCH_DIRECTION.md`, `acmtrust_paper/ARTIFACT_AUDIT.md` (this file), `acmtrust_paper/README.md`, `acmtrust_paper/build/`, `acmtrust_paper/figures/src/history_gap_col/`, `meeting/`, `papers/`, `gap-figure/`, `baseline/` (unless open question 3 says otherwise), `data/` (pointer instead), `checker/out/`, `runs/workflow_test_v1`, `runs/workflow_policy_v1`, `runs/validation_v1`, `runs/main_v1/logs/ollama_serve_*.log`, `runs/main_v1/analysis_v1_partial`, `runs/main_v1/analysis_v1_noqwenreact`, `runs/p0_prosimos_*`, `runs/fingerprint_check_v1`, `runs/*_console.log` for pilots, WSL `devs_gen_code/`, `tools/`, `screen/`, `stage/`, `judge_sandbox*`.

### Steps

1. **Commit or snapshot your current work.** The audit saw HEAD `5846430`.
2. **Build a clean folder outside the repository** (for example `../artifact_export/`) with `git archive HEAD`, which contains no history. Then copy the "Include" runs and WSL items into it with a copy script that writes a file list (`artifact_files.txt`). Do not use `git add -f` on `runs/` in the working repository: that would put 500 MB and the user name into your history.
3. **Delete the excluded items** from the export (`acmtrust_paper/build/`, `acmtrust_paper/README.md`, this audit, `history_gap_col`, `checker/out/`).
4. **Scrub** with one script that works on bytes (some pinned files use CRLF) and only on text files:
   - `aashraf` → `user` in paths; `Ashraf's` → `the author's`; `Ashraf` → `the author`; `Dr. Roy` → `the advisor`; remove the line-177 clause in `domain_readiness.md`;
   - then **re-hash**. Nine frozen scripts and the two frozen indexes change bytes. Write a second record, `freeze_v1_anonymized.json`, with `make_freeze_record.py`, plus `anonymization_map.json` listing old sha256 → new sha256 for each changed file, and one sentence in the README that only names, dates and paths changed. Check the `.sha256` and `hashes_*.txt` files in `manifests/` and `validation/` against the files you changed (`mlsys_docs_v1.sha256`, `judge_subsets_main_v1*.sha256`, the `*_questions_*.sha256`, `validation/blind_review_*.sha256`) and update any that list a scrubbed file.
5. **Fix the two things scrubbing cannot:** `test_judges_offline.py:641-644` (rename in code and expected listing together) and `mlsys_gold.py:32` (read the raw-data path from an environment variable).
6. **Add the missing pieces:** the artifact README (sections 2a–2c above, plus the environment recipe), `LICENSE`, `NOTICE`, `data/README.md`, `program_list.csv`, `b0_results.md`, a Figure 3 generator and a script for the "raw rows" macros (or a note saying how they were counted), and the WSL environment lock.
7. **Verify on the export, not on the working tree:**
   - repeat the identity, path, link and secret scans (section 3 and 4 patterns); expect zero hits;
   - run the five offline suites;
   - run `main_analysis.py --selftest`;
   - recompute `analysis_v2` from the exported rows and diff it against the shipped `main_analysis.json`;
   - build the paper with the link filled in and run `grep -n "\\\\TBD" acmtrust_paper/sections/*.tex` (it should print nothing);
   - open `git log` of the new folder after `git init` with a neutral author.
8. **You** create the throwaway GitHub repository from the export, point the anonymous mirror service at it, check the mirror pages for any remaining personal string, and put the URL into `\TBD{anonymous link}` in `sections/09_conclusion.tex`. I did none of this.

Suggested `.gitignore` changes for you to consider (not made): add `acmtrust_paper/build/`, and `acmtrust_paper/ARTIFACT_AUDIT.md`.

---

## 8. Open questions for you

1. **Which run evidence ships?** Proposal: decision rows and judge rows for the three scored sets, analysis outputs, all ledgers and the B0 and R1 builds (about 172 MB from `runs/` before compression, plus 15.6 MB of WSL programs). Development sets (33 MB) and pilots are optional. Say if you want less.
2. **Ship the gold?** The question files carry the `gold` field and `validation/` holds the blind-review keys. The paper promises the questions. Publishing gold has a contamination cost for future models; the alternative is questions without gold plus a hash of the gold file. The scorer needs gold to recompute anything.
3. **Ship the OTF-Tools baseline code?** B0 and R1 import it at run time, so the B0 results cannot be reproduced without it. Shipping a stripped copy (no `.git/`, no `runs/`) is possible, but it links the artifact to the MLSys submission in the reviewers' eyes (the code, its docs and its folder name `otf-tools-10f5401`). The alternative is to ship B0 results only and say the code is withheld for anonymity. Also decide whether to leave the folder name and commit hash (they sit in frozen code).
4. **Scrub frozen files?** The only way to remove the name from nine frozen files is to change their hashes and publish an old→new map. Do you accept that, and does the paper say anywhere that the shipped hashes equal the frozen ones? (I did not check the paper text for that.)
5. **Keep the decision log and run manifest?** `run_manifest.md` (1,700+ lines) and `design_decisions.md` record decisions as "Ashraf decided…", plus session notes. They are the design decision log `AGENTS.md` requires, and they back the GenAI disclosure. I suggest shipping them scrubbed. The other choice is dropping them and shipping only `freeze_v1.md` and `main_results_v1.md`.
6. **Licence for our code and data.** No `LICENSE` exists. Common choices are MIT or Apache-2.0 with "Anonymous Authors" as holder. Decide before the camera-ready too.
7. **Derived manufacturing and IT documents (`runs/mlsys_docs`).** They derive from SupplyGraph (LGPL-2.1 per the authors' note) and the Google trace (CC BY 4.0). Ship them with attribution, or ship only a pointer plus the regeneration script (which also needs the raw data and the path fix in `mlsys_gold.py`)?
8. **Copy the WSL programs?** The 22 DEVS-Gen programs live only in WSL (15.6 MB). I did not copy them (read-only). Do you want them added to the export, with `gen_meta.json` and logs scrubbed?
9. **Paper source in the artifact?** Proposal: include `results.tex`, `sensitivity/` and `figures/*.tex` (they trace the numbers) and optionally the rest.
10. **Who builds the export?** I can write `scripts/build_artifact.py` (copy list, scrub rules, hash map, verification scans) as a separate task if you want; it is the only way to make steps 2–7 repeatable.
11. **Search-by-name risk.** The authors' OTF-Tools repository is public (per `domain_readiness.md:177`) and the paper uses the name "OTF-Tools". Is that acceptable for double-blind review? This is a paper question, not an artifact one.

---

## What I did and did not check

Verified: file inventory, git tracking and ignore rules, sizes, identity, path, link and secret scans (tracked files, `runs/`, `validation/`, `manifests/`, WSL program trees), literal `.env` values (names and counts only), PDF and PNG metadata, the freeze file list, the `freeze_v1.json` program list (118), the Jev ledger line count (3,410), and the WSL folder inventory (read-only).

Not done: running any script or test; reading git blobs from history; opening `data/` or `baseline/` contents beyond licence and identity strings; checking upstream licences; checking provider terms; confirming the "32 of 60" B0 count from `builds_*.jsonl`; tracing every table cell in `06_results.tex` to a script; checking the anonymous mirror service's limits.

---

## Summary

1. Do not mirror the working repo: its history, remote and branches carry the author's name, handle and email. Export files only and start a fresh repository.
2. The tracked tree (16.8 MB) holds the code, questions, program list (118 names in `freeze_v1.json`), judge prompts and analysis scripts; the four builder task specs (`adapters/generic_tasks/*/spec.md`) are the one ignored exception inside it. The decision rows, B0 results, ledgers (including Jev), documents and OTF programs sit in ignored `runs/`, and the 22 DEVS-Gen programs sit only in WSL; about 187 MB (before compression) must be copied in.
3. Anonymization needs 213 lines in 44 files fixed, one line naming the public OTF-Tools repository (`domain_readiness.md:177`), the tracked `build/` logs removed, and a hash map for nine frozen files.
4. No secrets: no key-shaped strings anywhere scanned, and none of the four `.env` values appears in any file; no file is near 50 MB.
5. Gaps to close: no generator for Figure 3 or the "raw rows" macros, no README path for the analysis, no LICENSE, and the pinned environment is not usable from a fresh checkout; eleven decisions are yours (section 8).
