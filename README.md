# Intervention-level assurance for reusable LLM-built process models

**The question.** An LLM can turn a process document into a simulator program and then reuse that program for what-if questions ("what if we add one clerk?", "what if this step takes twice as long?"). A program that reproduces the recorded history can still mishandle the requested change. This project builds and tests an assurance library. For each answer, the library decides whether the program can be trusted on the specific change being asked about, or whether the answer should be declined.


## What is compared

**Domains (four):** manufacturing, IT operations, and two business workflows: loan and pharmacy. The workflow processes come from the open logs, process models and simulation parameters at <https://zenodo.org/records/10435849>.

**Platforms, which build the programs (118 programs in all):**
- OTF-Tools. The original code is pinned as **B0** and kept unpatched as a reference. **R1** is our redesigned generation path (`redesign/otf_r1/`).
- DEVS-Gen.
- A plain reason-and-code agent (`scripts/coding_agent_build.py`).

**Trust judges, which decide whether to accept an answer:**
- **Ours:** the `directed` gate in `assurance/`. It reads the question into a structured request (target, operation, value, units, time) and checks that request against the current records. It then runs checks specific to the family of change being made, keeping a per-program record of what has passed, which is rechecked when the program is reused.
- **Baselines:**
  - the platform's native check;
  - the history check (replay of recorded outcomes);
  - generic behaviour tests;
  - disagreement with a reading-only answer;
  - an answer-level LLM judge;
  - a program-level LLM judge;
  - a ReAct judge with one sandboxed code tool and 8 turns (`scripts/judges.py`).
- Vanilla and RAG reading answers are reference answerers.

**Models:** Claude Haiku and Sonnet, gpt-oss and Gemma (Ollama Cloud), and Qwen 3.5 9B (local Ollama). Which model is used in which role, with which subsets, is set by D22, D27 and D29.

**Scoring:**
- Gold answers come from an independently checked reference implementation (`reference_engine/`, `checker/`, `validation/`), never from an LLM judge.
- An answer counts only if the judge permits it and the program produced one (rule A).
- Judges are compared at matched answer coverage, with a two-level bootstrap. Results are reported per domain, platform, model, family of change, and program.
- Declines are reported in plain terms: Caught, Already caught, Untestable, Failed history check, Can't express, and Trusted (accepted).

## Repository layout

| Path | What it holds |
|---|---|
| `assurance/` | The assurance library (the method). Frozen. |
| `redesign/otf_r1/` | The R1 generation path built on OTF-Tools. |
| `adapters/` | DEVS-Gen hooks, DEVS-Gen task specs and generic test specs, per domain. |
| `scripts/` | Builders, runners, scorers, judges, question-set generators, checks and offline tests. |
| `spec/` | The workflow semantics specification (`workflow_semantics_v1.md`) and test scenarios. |
| `reference_engine/`, `checker/` | Evaluation-only reference simulator and its independent validator. |
| `validation/` | Blind-review samples and keys used to check gold. Evaluation-only. |
| `manifests/` | Decisions, the run manifest, the freeze record, question files, splits, hashes and design notes. |
| `baseline/`, `data/`, `runs/` | Pinned OTF-Tools, the downloaded workflow data, and all programs and run outputs. Not in git, so they exist only on the working machine. |

**Evaluation-only material** (`reference_engine/`, `checker/`, `validation/`, the gold fields in question files) must never reach a program, the library, a reading model or a judge.

## Environment

- **Windows Python** `.tools/b0_env/Scripts/python.exe`: the library, runners, judges and builds. Run it with `-X utf8`.
- **`.venv`** (Python 3.12 with Prosimos): used only for the reference-engine comparisons and the checker.
- **WSL Ubuntu-24.04** (`~/trust2027`):
  - DEVS-Gen and the generated programs;
  - the bubblewrap sandbox, with the seccomp filter from `scripts/make_seccomp_filter.py`. Every program runs inside this sandbox.
- **API keys** are read from `.env`. That file is never committed, printed or logged.

## Common commands

Run from the project root. `PY` stands for `.tools/b0_env/Scripts/python.exe -X utf8`.

Offline test suites, which use no model calls and should all report 0 failures:

```bash
.tools/b0_env/Scripts/python.exe -X utf8 scripts/test_assurance_offline.py
```

```bash
.tools/b0_env/Scripts/python.exe -X utf8 scripts/test_assurance_mlsys_offline.py
```

```bash
.tools/b0_env/Scripts/python.exe -X utf8 scripts/test_judges_offline.py
```

```bash
.tools/b0_env/Scripts/python.exe -X utf8 scripts/test_coding_agent_offline.py
```

Check that the frozen files are unchanged, by writing a fresh record and comparing it with `manifests/freeze_v1.json`:

```bash
.tools/b0_env/Scripts/python.exe -X utf8 scripts/make_freeze_record.py . runs/freeze_check.json
```

Main run. The sets are `wf_dev`, `wf_test`, `wf_policy`, `ml_dev` and `ml_test`. These commands make paid model calls.

- `PY scripts/main_runner.py shared . <set> [interpret|vanilla|rag]`: question interpretation and the reading answers.
- `PY scripts/main_shard.py . <set> <i> <n> [--registry-from SET]`: shard *i* of *n* of the program stage. Shards can run in parallel.
- `PY scripts/main_summary.py . <set> <out.json>`: scoring. This is the only step that reads gold.
- `PY scripts/judges.py {smoke|draw|run|summary} . <sets> [--model ...] [--subset-name ...] [--shard K/N]`: the LLM and ReAct judges.

Outputs go to `runs/main_v1/<set>/`.