# Artifact: Vouch, intervention-level assurance for reusable LLM-built process models

This is the anonymized artifact for a double-blind submission. It holds the assurance library (**Vouch**, the `directed` gate), the
{{N_PROGRAMS}} programs it was run on, the question sets with gold, every decision and judge row behind the paper's numbers, the model-call
ledgers, and the scripts that recompute the numbers. Total size about {{APPROX_MB}} MB.

{{PACK_NOTE}}
**Please read section 2 first:** the OTF-Tools implementation, which the OTF-Tools platform (the unchanged original B0 and our revised
path R1) imports at run time, is withheld during review. Everything that recomputes the paper's numbers from stored rows works without it.

## 1. What is here

| Path | What it holds |
|---|---|
| `assurance/` | The assurance library (the method). Frozen before the main run. |
| `redesign/otf_r1/` | R1, our revised generation path built on OTF-Tools (the diff against the original is `manifests/redesign_r1.diff`). |
| `adapters/` | DEVS-Gen hooks and task specs, and the generic task specs (`generic_tasks/*/spec.md`, `spec.json`) the plain coding agent and DEVS-Gen were given. |
| `scripts/` | Builders, runners, scorers, judges, question-set generators, checks, analysis scripts and the five offline test suites. |
| `spec/`, `reference_engine/`, `checker/` | Workflow semantics specification, and the evaluation-only reference simulator with its independent validator. |
| `validation/` | Evaluation-only: blind-review samples and keys, fuzz scenarios, probe-soundness checks. Never shown to a program, the library, a reading model or a judge. |
| `manifests/` | Decision log (`design_decisions.md`), freeze records (`freeze_v1.md`, `freeze_v1.json`), results write-up (`main_results_v1.md`), **question files with gold**, splits, hash lists, design notes, lock files. The working notes (run log, planning and API-check notes) are not included. |
| `runs/main_v1/{wf_test,ml_test,wf_policy}/` | Decision rows of the three scored sets (per-program rows, interpretations, reading answers, registries) and, beside them, `<set>_summary.json` (the scored result). `runs/main_v1/logs/` holds the shell scripts the runs were started with (the console output of the main run is not included). |
| `runs/main_v1/{analysis_v1,analysis_v2,domain_tables_v1,domain_tables_v2,jev_long_context_v1}/` | The analysis outputs behind `acmtrust_paper/results.tex`. v1 is the 12 judge runs; v2 adds the TypeSafe Jev judge. |
| `runs/judges_main_v1/`, `runs/judges_jev_ledger/` | LLM-judge, ReAct-judge and Jev judgment rows, and the Jev call ledger. |
| `runs/build_test_*/` | Build records and **model-call ledgers** (`calls_*.jsonl`: calls, tokens, cost, failures), `builds_*.jsonl` (every build, accepted or not), console logs, and the OTF programs (`program.json`). `b0_*` and `v1` hold the unchanged original (B0); `r1*` hold R1. |
| `runs/coding_agent/`, `runs/devs_gen/` | The plain-agent programs and indexes; the DEVS-Gen generation index (all 32 attempts, failures included) and token ledger. |
| `programs/devs_gen/` | The {{N_DEVS}} DEVS-Gen programs (`run.py` and `devs_project/`), copied from the WSL machine they were generated on. |
| `runs/workflow_docs/`, `runs/mlsys_docs/` | The process documents the programs read (derived from public sources; see `NOTICE.md`). |
| `acmtrust_paper/` | The paper is provided as a PDF with the submission, not as LaTeX source. This folder holds `results.tex` (the map from every number in the paper to the file it comes from), `figures/` (the built figure PDFs, `riskcov.tex` for Figure 3, and the sources of Figures 1 and 2 under `figures/src/`), `sensitivity/` (run-clustered sensitivity analyses) and `paper_numbers/` (scripts that recompute Figure 3, the tables and the raw-row numbers). |
| `program_list.csv` | The {{N_PROGRAMS}} programs: platform, builder model, process, document or task, and where each lives. {{N_R1}} OTF R1, {{N_B0}} OTF B0, {{N_DEVS}} DEVS-Gen, {{N_AGENT}} agent. |
| `b0_results.md` | The unchanged original OTF-Tools builds: {{B0_ACC}} of {{B0_TOTAL}} accepted, derived from the build records. |
| `anonymization_map.json`, `manifests/freeze_v1_anonymized.json`, `artifact_files.sha256` | What the anonymization changed, the freeze record re-hashed, and the sha256 of every file here. |
| `LICENSE`, `NOTICE.md`, `data/README.md` | MIT licence for our material; third-party notices; pointers to the public source data. |

## 2. What is withheld, and why

- **The pinned OTF-Tools implementation (`baseline/otf-tools-10f5401/`) is not included.** It is withheld for anonymity during review.
  R1 and the unchanged original (B0) import this code at run time (`assurance/backends.py`, `scripts/b0_build_test.py`,
  `scripts/judges.py`, `scripts/make_redesign_r1.py`, `scripts/mlsys_gold.py`, and the `test_assurance_mlsys_offline.py` suite).
  The code paths still name `baseline/otf-tools-10f5401/implementation-1`; if the code is released after review it goes there.
  - **Included:** every B0 and R1 build record, program, ledger and decision row, so all reported B0 and R1 numbers can be recomputed and
    inspected (`b0_results.md`).
  - **Not possible without it:** rebuilding OTF programs, re-executing OTF programs (R1 or B0), and regenerating manufacturing/IT gold.
    Programs from DEVS-Gen and the plain agent do not import it.
- **Source data** is not copied; `data/README.md` gives pointers, versions and hashes. Derived documents are included.
- **Not included:** development-set rows (`wf_dev`, `ml_dev`), pilots, console output of the main run, model-server logs, working notes, regenerable reference-engine outputs, API keys
  (`.env`), and the DEVS-Gen source tree (clone it with `scripts/wsl_setup_devs_gen.sh`).
- The LLM outputs here come from commercial and open-weight providers; their terms apply (see `NOTICE.md`).

## 3. Anonymization

Names of people, dates attached to names, local file paths (user name and project folders), and sentences that referred to material
that is not part of this artifact (working notes, planning files, accounts and credit balances) were rewritten or deleted,
in documentation and in code comments and docstrings. Three small code edits were also made so nothing depends on the authors' machine:

- `scripts/mlsys_gold.py` reads the raw-data folder from the environment variable `MLSYS_RAW`;
- `scripts/test_judges_offline.py` derives the Windows and WSL user names at run time (they used to be spelled out);
- `acmtrust_paper/sensitivity/run_fresh_*.sh` change into the repository root relative to the script.

The `Source:` line of the four task specs under `adapters/generic_tasks/` was reworded; the `spec_sha256` stored in each
`runs/coding_agent/*/*/*/build.json` is the hash of the original spec, and `anonymization_map.json` maps it to the file here.
Paths inside the code that name a WSL account now say `/home/user/...` (for example `/home/user/trust2027/gen`); see section 8.
{{N_FROZEN_CHANGED}} of the 30 frozen files (library files, scripts and the coding-agent index) were changed by this, so their sha256 differ from `manifests/freeze_v1.json`, which is kept
as the original record (the truncated hashes printed in `manifests/freeze_v1.md` are the original ones too). `manifests/freeze_v1_anonymized.json` has the re-hashed values, and `anonymization_map.json` maps every old
sha256 to the new one and lists every manual edit. Rows, scores and numbers were not changed.

## 4. Environment

Analysis environment: CPython 3.12 and the 31 packages of `manifests/requirements_b0.lock` (pinned on Windows; includes `numpy==2.5.4`).
This recipe was run from scratch on the build machine and gave the test results in section 7:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r manifests/requirements_b0.lock    # Linux/macOS: .venv/bin/python
```

(`python -m venv .venv` followed by `.venv/Scripts/python -m pip install -r manifests/requirements_b0.lock` is equivalent.)
Use `python -X utf8` for every script (several files contain non-ASCII text); the commands below say `python`, meaning the environment's
interpreter. A second environment with Prosimos 2.1.0 (`manifests/requirements_p0.lock`) is used only for the reference-engine comparisons.

WSL (Ubuntu 24.04) is needed only to execute DEVS-Gen and agent programs and the sandboxed judges: DEVS-Gen at release `f7461b9f9d23`
via `scripts/wsl_setup_devs_gen.sh` (clones commit `f7461b9f9d23e5c590975d7ecb3a58092c34204a`; Python 3.10; package lock
`manifests/requirements_devs_gen_wsl.lock`, whose two `file://` lines name the local DEVS-Gen checkout and its bundled xDEVS source, so
install those two from the clone), bubblewrap, and the seccomp filter from `scripts/make_seccomp_filter.py`. None of this was rebuilt
for the anonymized copy: the WSL setup, sandbox and DEVS-Gen/agent program execution were not re-run on the artifact.

## 5. Check the files

```bash
python scripts/verify_files.py              # every file against artifact_files.sha256 (Linux/macOS also: sha256sum -c artifact_files.sha256)
python -X utf8 scripts/make_freeze_record.py . freeze_check.json
```

`make_freeze_record.py` writes a fresh record; its `files` block must equal `manifests/freeze_v1_anonymized.json` (30 files), and its
`programs` block (118 names, `sha256_of_sorted_names`) must equal the recorded one. Do not let git convert line endings
(`.gitattributes` sets `* -text`); the frozen hashes are byte-exact. A few build records under `runs/coding_agent/*/*/*/build.json` store
the sha256 of `scripts/coding_agent_build.py` as it was when each program was built; those are the original values, and
`anonymization_map.json` maps them to the anonymized file.

## 6. Recompute the paper's numbers (no model calls, no sandbox)

Run from this folder. Each command rewrites a new folder; compare it with the shipped one.

```bash
# Main analysis with the TypeSafe Jev judge (analysis_v2). Arguments verified to reproduce the shipped file byte for byte.
python -X utf8 scripts/main_analysis.py . runs/main_v1/analysis_v2_recomputed --judges-dir runs/judges_main_v1 \
  --subsets manifests/judge_subsets_main_v1.json --react50 manifests/judge_subsets_main_v1_react_sonnet50.json
python -X utf8 scripts/report_tables.py runs/main_v1/analysis_v2_recomputed/main_analysis.json runs/main_v1/analysis_v2_recomputed/tables.md
# analysis_v1 (the 12 judge runs, no Jev): the same command on a copy of the judge folder without main_answer_jev
mkdir judges_nojev && for d in runs/judges_main_v1/main_*/; do [ "$(basename "$d")" = main_answer_jev ] || cp -r "$d" judges_nojev/; done
python -X utf8 scripts/main_analysis.py . runs/main_v1/analysis_v1_recomputed --judges-dir judges_nojev \
  --subsets manifests/judge_subsets_main_v1.json --react50 manifests/judge_subsets_main_v1_react_sonnet50.json
# Domain x platform x judge tables, long-context Jev table, run-clustered sensitivity
python -X utf8 scripts/domain_tables.py . runs/main_v1/domain_tables_v2_recomputed --sets wf_test,ml_test --judges-dir runs/judges_main_v1 \
  --subsets manifests/judge_subsets_main_v1.json --react50 manifests/judge_subsets_main_v1_react_sonnet50.json
python -X utf8 scripts/jev_long_context_table.py . runs/main_v1/jev_long_context_v1_recomputed
python -X utf8 acmtrust_paper/sensitivity/run_clustered.py . acmtrust_paper/sensitivity/analysis_v2_runclustered_recomputed
python -X utf8 scripts/main_analysis.py --selftest
```

{{RECOMPUTE_NOTES}}

{{PAPER_NUMBERS}}

## 7. Offline tests (no model calls)

```bash
python -X utf8 scripts/test_assurance_offline.py
python -X utf8 scripts/test_assurance_mlsys_offline.py
python -X utf8 scripts/test_judges_offline.py
python -X utf8 scripts/test_coding_agent_offline.py
python -X utf8 scripts/test_jev_judge_offline.py
```

{{TEST_NOTES}}

## 8. Rerun Vouch on the programs

This makes paid model calls for the interpretation and judge stages, and runs programs in the WSL sandbox. The cached interpretations and
reading answers are in `runs/main_v1/<set>/{interpret,vanilla,rag}.jsonl`.

1. Set up WSL (section 4) and install the programs where the scripts look for them: `bash scripts/wsl_install_programs.sh`
   (the scripts say `/home/user/trust2027/gen/...`; create that account name or link it, see the script). Plain-agent programs are
   in `runs/coding_agent/` and their index points at `/home/user/trust2027/coding_agent/...`.
2. API keys go in `.env` (never committed): `ANTHROPIC_API_KEY`, `OLLAMA_API_KEY`, `OPENROUTER_API_KEY`, `TYPESAFE_API_KEY`.
3. `python -X utf8 scripts/main_runner.py shared . <set> [interpret|vanilla|rag]`, then
   `python -X utf8 scripts/main_shard.py . <set> <i> <n>` and `python -X utf8 scripts/main_summary.py . <set> <out.json>`;
   judges: `python -X utf8 scripts/judges.py {smoke|draw|run|summary} . <sets> ...`. Sets: `wf_test`, `ml_test`, `wf_policy`.
   OTF programs need the withheld OTF-Tools code (section 2).

## 9. Figures

The paper itself is not included (reviewers have the PDF); see the `acmtrust_paper/` row in section 1.

Figures 1 and 2 are HTML figures printed to PDF with the paper's font (Libertine). Their sources are
`acmtrust_paper/figures/src/history_gap/` (Figure 1) and `acmtrust_paper/figures/src/pipeline/` (Figure 2), with the shared font converter
`figures/src/fonts/libertine_ttf.py`; the built PDFs are `figures/history_gap.pdf` and `figures/pipeline.pdf` (included as shipped). Each
`build.sh` needs Node, Microsoft Edge or Chrome, a TeX installation with the `libertine` package, and a Python with `fontTools`
(`PYTHON=<python> bash build.sh`); no font files are shipped, the build creates them. These builds were not rerun for the artifact. Figure 3, the tables and the `results.tex` macros: see section 6 and `acmtrust_paper/paper_numbers/README.md`.

## 10. Size

About {{APPROX_MB}} MB in total. On Windows, clone into a short folder or run `git config --global core.longpaths true`: the longest path in this
artifact is 155 characters (DEVS-Gen build logs under `programs/devs_gen/`). Largest file: {{LARGEST_FILE}}. Largest folder: {{LARGEST_FOLDER}}. {{MIRROR_NOTES}}
