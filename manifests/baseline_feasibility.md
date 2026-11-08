# Baseline feasibility

Handoff Stage 1 record. "Verified" means checked in code, a run or the paper on the date given. Cells marked "pending" have not been checked yet. Native behavior stays separate from any adapter.

Cell classes used: eligible and successful, eligible but model or program failed, ineligible regime, adapter or infrastructure defect.

## Summary, 2026-11-06

| Backend | Role | Status | Evidence |
|---|---|---|---|
| OTF-Tools at `10f5401` | Required | Eligible and running. Native code imported unchanged as B0. R1 is a separate named treatment | `manifests/run_manifest.md`, build tests and screen |
| DEVS-Gen at `f7461b9f9d23` | Required | Native release reproduced. Workflow task not yet generated | Smoke run, 9 of 12 scores exact |
| G-Sim at `72b5d51a7790` | Conditional | **Deferred, ineligible regime for the primary study.** Not run, no spend | Paper Appendix C.4 and repository, below |

## G-Sim decision

Cap was 3 hours and $1 (D16). Used under 1 hour of reading and $0. No generation was attempted, so this says nothing about G-Sim's quality on its own tasks.

Evidence:

- **Interventions are manual.** Appendix C.4 describes a person inspecting the final generated simulator code and locating the parameter or section analogous to the one changed in the ground truth, then applying the same change. The repository's `insight_experiments` holds scripts for its own SIR and supply environments. There is no automated request-to-intervention path to test.
- **Regime.** G-Sim calibrates simulators to data distributions by simulation-based inference or evolution strategies. The primary study grades exact outcomes of deterministic realizations. The handoff forbids forcing a distribution method into exact per-case grading by an undisclosed rewrite, and distributional questions are a separate optional regime that is out of the required core (D16).
- **Setup.** Its environments are hospital, supply chain and SIR (`config/config.yaml`). Its LLM client defaults to Azure, with default model `o3`. Install needs conda, torch and system packages. All are solvable, so none of them is the reason for this decision.

Inclusion would need a substantial task adapter and a person or new component mapping each intervention to code. That would no longer be G-Sim's method. It stays listed as a coverage limit in the paper. The label follows from its method and the declared regime, not from any score.

## Feasibility matrix

| Question | OTF-Tools | DEVS-Gen | G-Sim |
|---|---|---|---|
| Generation input | PDF document with records and process prose | YAML task spec in natural language, with required CLI options | Natural-language description plus data |
| Calibration | None beyond its forecast check | None in generation | Yes, core to the method |
| Load without regenerating | Yes, stored code | Yes, stored `run.py` | Not tested |
| Domains so far | Manufacturing, IT, workflow documents | Ten own scenarios; workflow pending | Own three environments |
| Intervention surface | Inputs and params of a generated program, patched by an LLM, with restart and replay | Launch arguments, and on some tasks a standard-input stream | Manual code or parameter edit |
| Time-varying changes without code edits | Only if the program models that input. Not available in current programs | Only if the task spec declares it | No |
| Observations | Program's own outcome records, whose kinds vary by program | JSONL event trace under a declared schema | Trajectories |
| Reset, restart, full history | Restart from a checkpoint time, plus full-history simulate | Full history only per run; restart probe not applicable | Not tested |
| Randomness | Programs read plan values in our documents | Seeded in native tasks; workflow task supplies plans | Stochastic |
| Native validation | Automatic gate: forecast F1 at least 0.4 plus shortcut tests, in generation | Hand-written per-scenario `checker.py` and trace schema, used for evaluation; whether anything runs in generation is pending | Calibration fit |
| Cost per build, measured or published | Haiku about $0.03, Sonnet about $0.21 | Published median 133k tokens; ours pending | Not tested |
| License | Identified repository, no license file | Apache-2.0, bundled xDEVS GPLv3 | MIT |
| Platform | Windows here | Linux tools, in WSL here, no sudo | Not tested |

## Changes to DEVS-Gen so far

| Change | Category | Reason |
|---|---|---|
| Evaluator's bubblewrap path points at a locally unpacked official package | 1, mechanical | No system install. Diff in `~/trust2027/category1.diff` |

## Reproduction

Bundled programs re-evaluated against published scores: gpt ABP, gpt barbershop, qwen StoreCashier and glm oft, 3 runs each. 9 of 12 match exactly. StoreCashier differs slightly on behavior score only. Operational scores match on all 12.
