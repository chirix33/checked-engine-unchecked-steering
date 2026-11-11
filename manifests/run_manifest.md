# Run manifest

Append-only record of what was run, with which inputs. Paid model use so far, at list prices from recorded tokens (not billed amounts, and not reflecting off-peak rates or credits): **Ollama cloud $1.95** (build tests $1.92, connection tests $0.03), **Anthropic $2.87** for the first Claude build test, plus later slice calls recorded in `runs/build_test_assurance_claude/`. Corrected 2026-11-07 after independent review: this line previously said $0.03.

**Spend update 2026-11-09 (supersedes the figures above):** Anthropic $11.07 at list price: the runner ledger $5.99, plus DEVS-Gen's estimated $5.08, which the ledger and the $25 stop do not see. Ollama cloud $1.95.

## 2026-11-04: P0 setup

| Item | Value |
|---|---|
| Baseline clone | `baseline/otf-tools-10f5401`, commit `10f540118756b6062feb0ccc5e2012fe771f1579`, clean checkout. Git-tracked files only; ignored raw data is not copied. |
| Other baseline refs | `react-baselines` branch `fc78481`, final results tag `otf-v3.4.4` `62038f0` |
| Saved MLSys results | Left in place in `MLSystem 2027/`, not edited. Hashes below. |
| Workflow data | Zenodo 10.5281/zenodo.10435849 v4.0, `inputs.zip`, MD5 `4328addf237dd05dc631e5e7b341552b` (matches the record), CC BY 4.0. `outputs.zip` not downloaded. |
| Environment | CPython 3.12.16 in `.venv`, installed through `uv` under `.tools`; `prosimos==2.1.0`. Locked in `requirements_p0.lock`. |
| Paper | `otf-tools.pdf` is treated as the MLSys `main.pdf` under another name, per Ashraf. Their bytes differ. |

Saved MLSys results SHA-256:

```text
37da82020a8050c54bde50c6d3cab1f2c6ed87ad4011e523079c4c8a0f949116  all_results.zip
38d300c486fd7caccde76b12e25eee16576f2cd54c33b757c254543b55cdd678  tier_b_results.zip
eac42cce80020c0b08feb98a03fa3f1cd3da949f247cd867cdd9de622f2696a9  tier_b_results 1.zip
2a23dc57bfcc4fb57f7dddf0b78ee4d5870228719f4244d9ff51d1b61d250fdc  tier_b_results 2.zip
d70cb28c13c1b5d94d9905e36e6c3cd7654c504859ff0a19b8743774c237909a  implementation-1/paper/main.pdf
```

The source checkout also has an uncommitted 12-line addition to `runs/logs/resume_after_reboot.log`, which is not in the pinned clone. Other file hashes are in `hashes_p0.txt`.

## 2026-11-04: Workflow model inventory

- Script: `scripts/inventory_workflow_models.py`
- Output: `workflow_model_inventory.json`

## 2026-11-04: Prosimos pairing check

- Script: `scripts/prosimos_coupling_check.py`; output `prosimos_coupling_check.json`; logs in `runs/p0_prosimos_coupling/`
- Setup: seed 20261104, 50 cases against 51 cases, start 2026-01-05 08:00 UTC, no timers, base models.

| Process | Repeatable with same seed | Same route after adding a case | Same full record after adding a case |
|---|---|---|---|
| Insurance_Claims | yes | 23/50 | 0/50 |
| Loan_Application | yes | 23/50 | 22/50 |
| Pharmacy | yes | 49/50 | 44/50 |
| Procure_to_Pay | yes | 5/50 | 0/50 |

Routing draws do not depend on other cases, so a changed route is a coupling failure, not a real queueing effect. Changes in full records can include real queueing effects, so that column alone does not separate the two. One seed and one case count only: this demonstrates the problem and does not measure its size.

## 2026-11-04: Prosimos queue screen

- Script: `scripts/prosimos_contention_check.py`; output `prosimos_contention_check.json`; logs in `runs/p0_prosimos_contention/`
- Setup: `_3_timers` versions, factual only, 100 and 400 cases, seeds 20261104 to 20261106. Waiting counts working-hours time only.

Range across the three seeds at 400 cases:

| Process | Pool (size) | Share of tasks waiting | Mean wait, working minutes | Utilization |
|---|---|---|---|---|
| Loan_Application | Appraiser (2) | 0.93 to 0.95 | 156 to 190 | 0.82 |
| Loan_Application | Clerk (9) | 0.59 to 0.70 | 13 to 21 | 0.74 to 0.77 |
| Loan_Application | Senior Officer (3) | 0.39 to 0.62 | 5 to 14 | 0.57 to 0.73 |
| Pharmacy | Pharmacist (1) | 0.63 to 0.65 | 0.9 to 1.1 | 0.67 to 0.69 |
| Pharmacy | Technician (8) | 0.15 to 0.17 | under 0.1 | 0.68 to 0.69 |

Screen only: this is Prosimos, not the reference engine. Pharmacy's factual queues are short, so capacity questions there depend on the intervention creating a queue. Procure_to_Pay also queues heavily (seed 20261104: Requester 490 minutes, Financial Manager 123 minutes), but its durations are all fixed.

## 2026-11-04: Workflow semantics freeze

- Spec, small model and scenario inputs written before any engine or checker. Hashes in `hashes_spec_v1.txt`, including the hand-worked expected outputs.
- Scenarios: 16 hand-worked on `spec/mini`, 48 on the published models.
- Hand-worked expected outputs were derived from the spec by the agent, without running code. Ashraf has not reviewed them.
- The checker agent started from the spec, the formats and the model files only, on a different model (Sonnet). Neither the engine nor the expected outputs were in the project tree while it worked.

## 2026-11-04: Model lineup checks (D7, D11)

Catalogues checked with no model calls:

| Setup | Finding |
|---|---|
| `gpt-oss:120b-cloud` | In the Ollama library. The direct cloud API lists it as `gpt-oss:120b`. |
| `gemma4:31b-cloud` | In the Ollama library. The direct cloud API lists it as `gemma4:31b`. |
| `qwen3.5:9b` | In the Ollama library, Q4_K_M, 6.55 GB, context 262144, thinking on by default. Its default parameters include `presence_penalty` 1.5. |
| `google/gemma-4-26b-a4b-it:free` | In the OpenRouter catalogue, context 262144, maximum output 32768. |

OpenRouter key endpoint (`model_endpoint_check.json`): free-model limit 1,000 requests a day, confirmed. The per-minute limit is not reported, because its field is marked deprecated, so 20 a minute stays documented but unmeasured. The key has no spending limit of its own. Account credits show $38.73 remaining of $1,100.

Local tools: Ollama 0.40.14 from the official GitHub release, SHA-256 `65d68cade6cf6375f398b518224f8c8a15e062387f38cf477abfc848de7e7e29` verified. Installed under `.tools/ollama`, models under `.tools/ollama_models`, server on `127.0.0.1:11535`, no system-wide change. Hardware: RTX 5090 with 32 GB, 64 GB RAM.

`.env` holds the Ollama and OpenRouter keys. It is git-ignored, and scripts neither print nor record the values.

## 2026-11-04: Connection tests

- Script: `scripts/model_connection_test.py`; output `model_connection_test.json`. Synthetic prompts only, temperature 0, requested context 131072.

| Setup | Tokens reported | Reasoning | Output limit | Output speed (wall) | Long document, both markers returned |
|---|---|---|---|---|---|
| `qwen3.5:9b`, local | Yes | On and off both work | Respected | 182 tokens/s | 85,840 prompt tokens, 10 s, yes |
| `gpt-oss:120b`, cloud | Yes | Cannot be turned off; `low` still reasons | Respected | 352 tokens/s | 56,240 prompt tokens, 2 s, yes |
| `gemma4:31b`, cloud | Yes | On and off both work | Respected | 236 tokens/s | 85,841 prompt tokens, 4 s, yes |
| `gemma-4-26b-a4b-it:free`, OpenRouter | Not observed | Not observed | Not observed | Not observed | Not observed |

- Truncation control with a 2048 context: local Qwen truncated (1,026 prompt tokens, start marker lost), so the detector works. Both cloud setups ignored the limit (8,640 and 13,072 prompt tokens, both markers kept).
- OpenRouter free Gemma: all 15 attempts across 5 probes returned HTTP 429, "temporarily rate-limited upstream", provider Google AI Studio. These are busy errors, not model failures. The daily free-request counter stayed at 0. A second burst test timed out in backoff with no results. A spaced probe is recorded in `openrouter_free_probe_1.json`.
- Spaced probe result: 11 of 11 single calls returned 429, one every 5 minutes from 00:45 to 01:35 UTC on 2026-11-05, with no success and no full test. Ashraf then dropped this setup (D7), and the probe was stopped before its 12th sample. No model behavior was observed on this route, so nothing about Gemma 26B itself can be concluded.
- Only about 86k prompt tokens were tested, not the full 131072, and real document sizes on these models have not been measured. The build test must compare returned prompt tokens with the documents sent.
- Local timing excludes a first-call model load of about 48 s.

## 2026-11-04: Reference engine and checker comparison

- Engine: `reference_engine/engine.py`, sequential dispatch as in section 8. Checker: `checker/run.py` and `checker/validate.py`, time-stepped, built by a separately started agent on Sonnet from the spec alone. 206k tokens, about 17 minutes.
- Isolation audit of that agent's tool calls: 0 touched a forbidden path. The audit covers tool inputs in its transcript.
- Spec hash unchanged when the checker finished. Later amendments and hashes are recorded in `hashes_spec_v1.txt`.

| Check | Result |
|---|---|
| Hand-worked cases vs engine | 18 of 18 match (tasks and case times) |
| Hand-worked cases vs checker | 18 of 18 match |
| Engine vs checker, fixed scenarios | 66 of 66 identical, every field including draws |
| Engine vs checker, randomized (`validation/fuzz_v1`, seed 20261104) | 500 of 500 identical: 445 ok, 31 invalid_intervention, 17 conflicting_interventions, 7 visit_limit_exceeded |
| Checker's validator on engine outputs | 66 validated, 0 property failures |
| Validator on 5 tampered records | 5 of 5 caught |

The checker's agent listed 30 ambiguities in `checker/AMBIGUITIES.md`. One was a real spec defect: property 5 was false for zero-length tasks. Amendments A1 to A3 in the spec handle them, and no validation output changed. No disagreement between the implementations has occurred, so no engine bug has been found by this comparison.

Deadlock is untested in the fixed and randomized sets, because the supported models cannot produce it. The checker's agent tested it only on its own small models, and the engine has not been run on them.

Mutation check (`scripts/mutation_power_check.py`, `mutation_power_v1.json`), scenarios detecting each deliberate engine bug:

| Mutation | Hand (18) | Process (48) | Random (150) |
|---|---|---|---|
| Tie-break ignores longest idle | 14 | 48 | 124 |
| Queue key ignores arrival | 1 | 0 | 1 |
| Interval end inclusive | 1 | 0 | 1 |
| Interval start exclusive | 2 | 0 | 1 |
| Draw ignores visit | 16 | 48 | 111 |
| Routing threshold wrong | 18 | 48 | 131 |
| Unavailability ignored during work | 2 | 27 | 67 |
| Scale rounds down | 1 | 8 | 5 |

The first run caught "queue key ignores arrival" in 0 of 64 fixed scenarios and "scale rounds down" in 0 hand cases, so H17 and H18 were added, worked by hand before running. All 8 are now detected, but boundary and tie rules rest on very few scenarios each.

## 2026-11-04: Blind hand-check

Two separately started agents (Opus, Sonnet) worked H01, H02, H10 and H15 by hand from the spec, without code and without any answers. Their answers are in `validation/blind_review/`.

- Task rows and case ends match the recorded hand-worked answers in 8 of 8 agent-case pairs. Timers and routes match the engine's output in 8 of 8.
- Audit: neither agent read or wrote outside its own folder, and neither had a shell tool call.
- Each had the amended spec, so this tests the spec as it now stands. Ashraf's own check is still to come.

## 2026-11-05: Development build test, B0 and R1

- Runner: `scripts/b0_build_test.py`. Comparison: `scripts/compare_b0_r1.py`, `compare_b0_r1_v1.json`. Failure types: `build_failure_categories_v1.json`, `build_failure_categories_r1.json`. Per-call ledgers and programs in `runs/build_test_v1/` and `runs/build_test_r1/`.
- 72 fresh builds: 3 per model per specification per system. Library off. Development documents only: `mfg_dev`, `itops_dev`, and rendered Loan and Pharmacy documents (hashes in `runs/build_test_v1/docs/hashes.txt`). Pharmacy played no part in designing R1. No question or test label was used.

Accepted builds, of 3 per cell, with mean acceptance F1:

| Model, system | Manufacturing | IT | Loan | Pharmacy | Total of 12 |
|---|---|---|---|---|---|
| gpt-oss-120b, B0 | 1 (0.92) | 3 (0.74) | 2 (0.57) | 2 (0.75) | 8 |
| gpt-oss-120b, R1 | 3 (0.84) | 2 (0.61) | 2 (0.66) | 3 (0.84) | 10 |
| qwen3.5:9b, B0 | 0 | 0 | 0 | 0 | 0 |
| qwen3.5:9b, R1 | 0 | 1 (0.45) | 2 (0.53) | 0 | 3 |
| gemma4:31b, B0 | 0 | 1 (0.93) | 0 | 1 (1.00) | 2 |
| gemma4:31b, R1 | 3 (0.71) | 3 (0.82) | 3 (0.75) | 2 (0.89) | 11 |

Cost, per 12 builds:

| Model, system | Hours | Prompt tokens, M | Output tokens, M | List price | Largest prompt | Busy events | Output cutoffs |
|---|---|---|---|---|---|---|---|
| gpt-oss-120b, B0 | 0.37 | 2.37 | 0.39 | $0.59 | 48,784 | 2 | 0 |
| gpt-oss-120b, R1 | 0.32 | 2.35 | 0.39 | $0.59 | 41,012 | 0 | 0 |
| qwen3.5:9b, B0 | 0.61 | 1.58 | 0.39 | $0 | 59,256 | 0 | 7 |
| qwen3.5:9b, R1 | 1.50 | 4.68 | 0.96 | $0 | 79,173 | 0 | 15 |
| gemma4:31b, B0 | 0.26 | 0.43 | 0.22 | $0.15 | 20,575 | 2 | 0 |
| gemma4:31b, R1 | 0.76 | 2.44 | 0.62 | $0.59 | 53,448 | 0 | 1 |

- No build hit an infrastructure failure, and no call lacked token counts. Busy events were connection timeouts that succeeded on retry. gpt-oss and Gemma ran together with no rate-limit error, at 2 concurrent requests.
- Largest prompt was 79,173 tokens, below the 131072 local context. Cloud prompts came nowhere near a tested limit.
- List prices do not reflect off-peak rates or credits, so actual charges are unconfirmed.

Decisions after these results (D7, D8): Qwen stays `qwen3.5:9b`, caps are $20 for pilots and $150 overall, and Ollama credits stood at $8.73 on 2026-11-05, as reported by Ashraf.

## 2026-11-05: Intervention test on accepted workflow programs

`scripts/program_intervention_probe.py`, `program_intervention_probe_v1.json`. No model calls. 17 accepted programs on Loan and Pharmacy, Run 01 only. Each change's true result is rendered as a document and read by the program's own `outcomes()`, then compared exactly with its `simulate()`, requiring the same kind, entities and whole second. An earlier version of this test scored only case end times and wrongly gave 0 to programs that report task starts, so it was discarded.

- Acceptance is a much weaker bar than exactness. Exact factual F1 ranged from 0.00 to 1.00 across accepted programs. Examples: Gemma Loan b1 accepted at 0.40, exact 0.00; Qwen Loan b2 accepted at 0.61, exact 0.10. The check allows time errors up to 5% of the recorded period, which is hours on Loan.
- Only 2 programs were factually exact: Gemma Pharmacy b3 under B0 and under R1.
- Duration change, with 9 or 10 cases truly changing: 6 programs tested. Exact changed cases: 8/10, 2/10, 1/9, and 0 in the other three. These are not cleanly intervention-specific, because several programs were also inexact factually.
- Duration and timer changes were not mechanically mappable for the other 11 programs, including all Gemma programs. That says nothing about those programs.
- Case removal changed no other case's outcomes in Run 01, so it is a no-effect test only. Adding a worker changed 2 Loan cases and no Pharmacy cases. Timer changes altered only 1 case.
- This is one run, a few programs and mechanical mapping: a development screen, not a result.

## 2026-11-06: Replay screen under the D17 bar, first pass

Scripts: `scripts/replay_screen.py`, `scripts/inspect_screen_case.py`. Targets: `screen_targets_v1.json` (88, hash in `screen_targets_v1.sha256`), fixed before scoring. Results: `replay_screen_v1.json`. No model calls. A map rebuilt from reference rows equals the PDF-derived map on every table, so changed documents are sound.

| Measure, 17 accepted workflow programs (Ollama models, B0 and R1) | Result |
|---|---|
| Replay-exact programs, all 4 runs | 2: Gemma Pharmacy b3 under B0 and under R1. One model, one specification |
| Runs exact | 8 of 68 |
| Program-level case C | 0 |
| Run-level case C | 0 |
| Case-level: exact factually and truly changed, then wrong vs right | 78 vs 579. 76 of the 78 come from 3 gpt-oss programs |
| No-effect controls | 68 of 68 gave the same score as the program's factual run |
| Crashes or unreadable documents | 0 |
| Resource changes not mappable to a `params` key | 72 of 136 |

**Status against the bar: insufficient.** The bar asks for at least 8 replay-exact programs, from at least 2 models and 2 specifications. The 2 exact programs matched on all 88 of their changes, including route flips onto untaken paths. They report every record kind and read the full plans, so this isn't trivial. Two programs say nothing about the rate.

Sampled case-level failures, inspected by hand, are real logic errors. One is off by exactly 60 s after a flip through the 24-hour applicant task, consistent with missing the published 23:59 calendar gap, though the cause has not been confirmed in code. Another misses queueing after a longer task. All sampled programs were already inexact factually, so replay would have flagged them too.

## 2026-11-06: Claude build test and replay screen, second pass

Claude cohorts (D18), R1 generator, 3 builds per specification on 4 development specifications. Ledgers and programs in `runs/build_test_r1_claude/`.

| Model | Accepted of 12 | List price | Hours | Prompt tokens, M (cached) | Output tokens, M | Output cutoffs | Refusals |
|---|---|---|---|---|---|---|---|
| `claude-haiku-5-5` | 12 | $0.34 | 0.78 | 1.29 (0.93) | 0.57 | 0 | 0 |
| `claude-sonnet-5-5` | 12 | $2.52 | 0.31 | 1.13 (0.84) | 0.16 | 0 | 1 |

These are far cheaper than the estimate. Effort was medium for both. Sonnet's single refusal did not stop its build, and the cause hasn't been inspected. List price only; actual charges are unconfirmed.

Replay screen with the same 88 targets on all 29 accepted workflow programs: `replay_screen_v2.json`, with hand inspection in `scripts/inspect_program_c.py` and `scripts/inspect_program_c2.py`.

| Measure | Result |
|---|---|
| Replay-exact programs, all 4 runs | 12 of 29: Haiku 6, Sonnet 4, Gemma 2. Loan 4, Pharmacy 8 |
| D17 bar (8 programs, 2 models, 2 specifications, 3 families) | **Met** |
| Program-level case C | 1 of 12. Exact 95% interval for the program rate: 0.2% to 38% |
| Changes on replay-exact programs | 368 with a case end moving: 367 exact, 1 wrong. 88 others moved no case end, all exact. 48 of 48 no-effect controls exact. 24 not mappable |
| Case level, all 29 programs | 81 wrong vs 2,077 right, among cases exact factually and truly changed |

**The confirmed case C:** Haiku Loan b2. Acceptance F1 1.0 and exact on all 4 runs. In code it hardcodes the published fixed 86,400 s for "Applicant completes form" (`dur = fixed_applicant`), and ignores the plan value it read as an input. No recorded value differs, so replay can't reveal it. Setting that case's work to 1 s leaves the program 86,400 s late on that case, with knock-on errors in other cases' worker assignments.

**Acceptance vs exact replay:** 4 programs accepted at F1 0.95 or above are not replay-exact, including 2 Sonnet Loan programs accepted at 0.998 with exact F1 between 0.66 and 0.95. Strict replay catches what the pinned check's 5% time tolerance lets through.

**Post-hoc follow-up (D19):** 14 targets changing every fixed-value task. On the 12 replay-exact programs, 102 of 104 matched. Both wrong results are that same program, so the hypothesis did not find new programs here. Results: `replay_screen_v2_followup.json`.

**Reading under D17:** case C exists, and it is a clear example of the paper's premise. In this screen it is rare among replay-exact programs, so strict replay is a strong comparator, and the pilot may show it catches most dynamics errors. This does not narrow the claim, which rests on the planned pilot.

**Limits:**
- Gold changes were supplied directly, so this tests dynamics only. Interpretation, binding and reuse are untested.
- Only changes with an input surface could be tested: plan cells and pool-size `params`. Time-windowed unavailability and policy changes have no such surface here.
- Programs are development builds on two process structures. Builds from one model and specification are not independent.
- Replay-exact counts differ strongly by model family: Claude 10 of 12 on these two specifications, Ollama models 2 of 17. The reference was also written by Claude models (D18), so a shared reading of the semantics can't be ruled out.

## 2026-11-07: Corrections after independent code review

A separately started agent reviewed the screen, renderer, runner, R1 generator and summary scripts. It found no defect that changes the headline: 12 of 29 replay-exact, 1 program-level case C, and the D17 bar met. I verified each numeric claim before correcting anything. The frozen targets and results files are unchanged; corrected counts sit beside them.

| Finding | Correction |
|---|---|
| 4 of 88 v1 targets duplicated a route flip: Loan Runs 01, 02, 04 and Pharmacy Run 03 | Effectful changes on replay-exact programs: **348 unique, 347 exact**, not 368 and 367. Case level: **80 wrong vs 2,031 right**, not 81 vs 2,077. Program-level C and the bar unchanged. Target rule fixed so the two flips can't coincide; it now gives 88 unique targets. |
| Claude output cutoffs were not counted, because Claude reports `max_tokens` | Haiku had **9** cutoffs in its build test, not 0. Sonnet 0. Runner fixed. |
| Explore and syntax-repair steps were labeled as low forecast F1 in failure categories | Labeled as not a check. The D15 figure of 18 of 27 Gemma reading attempts used reading attempts only, so it stands. |
| No-effect controls and family results were labeled without checking factual exactness | The 68 "control wrong" entries all came from programs inexact factually. None is a real no-effect failure. Summary now separates these. "48 of 48" on replay-exact programs stands. |
| One program, Qwen R1 Loan b1, declares the Cases end column as an input, so blinding leaves it changed outcomes | No reported number changes: it isn't replay-exact, factual F1 about 0.002. The screen now flags outcome columns used as inputs. |
| "Effectful" means a case end moved | 88 changes on replay-exact programs moved no case end, and all were exact. Definition added to D17. |
| Manifest header showed $0.03 spend | Corrected above. |
| Native OTF answer catches every exception around the model call | Pinned code, not changed. The library's OTF adapter now re-raises service failures and reached caps, so they can't be counted as program failures. |
| R1's acceptance check compared 6 functions only | Now compares every pinned function except the generation loop, plus module constants, and checks the sandbox apart from the helper text. Regenerated R1 matches the recorded hashes byte for byte. `Reader` remains visible to checked code under R1. That is a known generation aid, disclosed in D15. |
| Schedule kinds compared without lower-casing | Fixed. No effect now: all 29 programs have none. |
| A failed Claude stream is logged as $0 though it may be billed | Now flagged `billing_unknown`. Concurrent processes can overshoot a cap by about one call each; the $0.25 margin covers one. |

## 2026-11-07: Minimal end-to-end slice (handoff Stage 2), OTF backend

Library `assurance/`. Slice runner `scripts/assurance_slice.py`, results `assurance_slice_v1.json`. Interpreter and native patch calls on `claude-haiku-5-5`. Two replay-exact programs on the Loan document: Haiku R1 b2, the case C program, and Sonnet R1 b2.

| Case | Haiku b2 (hardcodes applicant work) | Sonnet b2 |
|---|---|---|
| Effectful: applicant work set to 1 s, Run 02 | **Declined**: a witness change to that task changed nothing | Permitted by probes. Native patch set visit 1 to 1 s for all 15 of the case's activities, answer 227,456 vs gold 315,061. **Rejected by the binding check** |
| Valid no-effect: work for an unreached visit | Permitted, but native execution gave no answer | Permitted, binding correct, **answer 208,849 = gold** |
| Invalid: an activity the document doesn't have | Declined: interpreter returned unresolved | Same |
| Reuse, same policy, Run 03 | **Declined**: earlier failure on this target recorded | Earlier evidence reused. Raw answer equals gold, but the patch was again over-broad, so it was **rejected by the binding check** as right only by accident |
| Reuse, changed policy (Clerk 9 to 10) | Re-probed, declined | Re-probed, passed. Binding check rejected the same over-broad patch |

What this shows, as plumbing only:
- Directed probes catch the hardcoded input that replay can't.
- A replay-exact program that passes all dynamics probes can still answer wrongly through its native binding. OTF's patch language selects inputs by entity, kind and time, so for programs that store one record per activity it can't target a single activity. A post-execution binding check catches this.
- In this run, Sonnet's native patch bound correctly in 1 of 4 calls: the no-effect question. The other 3, all on the applicant task, were over-broad. In the first run of the same slice, the no-effect question failed to bind: the program's input record held no field for that visit, so the native patch raised an error. Binding varies across calls.
- The DEVS-Gen half of the slice is still pending.

**Corrections to the v1 slice above (library review 2, 2026-11-07).** The v1 table is kept as run, but parts of it are wrong:
- "All 15 of the case's activities" should read 17. The JSON shows 17 changed work-plan records.
- Sonnet's no-effect "binding correct, answer = gold" rested on a binding check that accepted any added record holding the value. The native patch had added a partial duplicate record. The reviewer reproduced the same patch form passing on two wrong answers. So "bound correctly in 1 of 4 calls" does not hold.
- The changed-policy case only changed the policy text's count. Its records still came from 9 clerks, and its `raw_correct` was scored against unchanged-policy gold. It tested the fingerprint only.
- Reuse on a new scope skipped probes. It should have rechecked them.

All 15 review findings were fixed in the library before v2. The fixes are listed in the next section.

## 2026-11-07: Library fixes after review 2, and slice v2

Second independent review of `assurance/` and the slice: 15 findings, most severe first. 12 were confirmed, and 3 were plausible (DEVS hash collisions, sandbox exposure, OTF key missing the engine). Each was fixed:
- **Binding check** now compares the inputs before and after record by record: added, removed and modified records, constants with old and new values, and outcome overrides. A case-level change must alter exactly one record, for the exact case, the exact target (no substring matching), one field, the requested visit and the requested value. A request equal to the plan value may change nothing. A removal must remove all of the case's inputs. add_workers must change one pool constant by exactly the requested count. Anything else is rejected.
- **Probes** that can't run now return "not run", which is never counted as a pass. Route parsing handles nested parentheses, so Pharmacy D3 has both routes. Route flips that loop back into elements the case already reached are not used, because they may need plan visits the document doesn't list. Witnesses fall back to the request's own case when no other case reached the target.
- **add_workers check:** derived from spec sections 8 and 9, using calendars stated in the document. Nothing may move before the first recorded task of that pool that waited for a worker, and that task's case must change. If no task waited, only worker names may change. Checked against reference output on 72 cases (both documents, 4 runs, every pool, +1 and +2 workers): 0 false rejections (`validation/probe_soundness_added_workers.py`). It cannot catch a program that ignores the change when no task waited, but then the true answer is unchanged anyway.
- **Registry:** the key now includes the operation, and the OTF key includes the engine (B0 or R1).
- **Reuse:** evidence is reused only for the same key, target and scope. A new scope or policy is probed again, and a recorded failure blocks use everywhere.
- **Budgets:** `probes_run` counts program executions. Directed uses at most `budget` executions. Generic takes a budget the caller sets to directed's count on the same request, and its random seed comes from the request.
- **OTF adapter:** add_workers is expressed through a params key naming the pool, else by editing the pool text. Route probabilities are expressed by editing the text. A change the adapter can't express is reported as such, not recorded as a capability failure.
- **DEVS adapter:** the hash covers all program files and fails loudly. Any nonzero exit counts as a crash. The sandbox now hides `/mnt` and `/home`, except the interpreter and the program folder (read-only). Checked: `/mnt/c`, the DEVS-Gen benchmark folder and `~/.bashrc` are hidden, the network is blocked, and the program folder is read-only.
- **Contract** rejects multi-change requests, route probabilities with case or time fields, timed add_workers, and removing the queried case.
- **Interpreter:** a malformed reply now counts as unresolved meaning.

Offline tests: `scripts/test_assurance_offline.py`, 48 checks, all pass.

**Slice v2** (`manifests/assurance_slice_v2.json`, registries in `runs/assurance_slice_v2/`). Same programs and questions as v1. Haiku calls cost $0.0047, about $0.012 for both slices. The changed-policy case now regenerates every run's records with 10 clerks, edits the text to "Clerk_0 to Clerk_9", and computes gold under that change. Clerks were never the bottleneck in these runs, so case ends do not move. The change is real but outcome-neutral here.

| Case | Haiku b2 (hardcodes applicant work) | Sonnet b2 |
|---|---|---|
| Effectful, Run 02 | **Declined**: a witness change to the task changed nothing for that case | Permitted after 3 probes. Native patch changed all 17 work-plan records. **Rejected by the binding check** (raw 227,456 vs gold 315,061) |
| Valid no-effect (visit 3, not in the plan) | Permitted after 3 probes. Native patch raised an error: the input has no field for visit 3. No answer | Same |
| Invalid activity | Declined: unresolved meaning | Same |
| Reuse, same policy, Run 03 | **Declined**: the failure recorded on Run 02 blocks the key | Probed again on Run 03 (no longer reused), passed. Patch again over-broad, so **rejected by the binding check**. Raw answer equals gold by accident |
| Reuse, changed policy (10 clerks) | New fingerprint, probed again, declined | Probed again, passed. Same over-broad patch, rejected |

Still plumbing only. On these two programs the native OTF patch never bound correctly (0 of 4 attempts that ran: 3 over-broad, 1 inexpressible). The binding check rejected the 2 cases whose raw answer happened to equal gold.

**DEVS-Gen builds.** Release method unchanged, via `scripts/wsl_devs_gen_generate.sh`, which now takes the output-token limit and the timeout as arguments.
- Haiku Loan run_01: 16,384 output tokens, 1,800 s. It timed out with no program. Every code-generation call stopped at 16,384 output tokens and returned no text: 29 calls, 665k prompt and 370k completion tokens, about $0.25 at list prices. Haiku 5.5 thinks by default, so the limit was most likely used up before any code was written.
- Haiku Loan run_02: 64,000 tokens and 3,600 s. Built in 228 s with 10 calls, and DEVS-Gen's own smoke test passed. Through the library's adapter it replays all case ends exactly on Runs 01, 02 and 03, while Run 04 has 5 of 15 case ends wrong.
- Eleven more builds are queued: 3 per model and task, for Haiku and Sonnet on Loan and Pharmacy. All use 64,000 tokens and 3,600 s.

## 2026-11-06: DEVS-Gen, unmodified smoke run and separate screen column

Release `czyarl/devs_gen_code` at `f7461b9f9d23`, in WSL at `~/trust2027`, Python 3.10.19, no sudo. Scripts: `scripts/wsl_setup_devs_gen.sh`, `scripts/wsl_devs_gen_smoke.sh`, `scripts/devs_gen_survey.py`, `scripts/devs_gen_abp_screen.py`, `scripts/devs_gen_abp_summary.py`, `scripts/devs_gen_abp_check.py`. Category 1 change: the evaluator's hardcoded bubblewrap path points at the official Ubuntu package unpacked locally (`~/trust2027/category1.diff`), with no change to behavior.

- **Native smoke run:** reproducing 12 bundled programs, 9 match published scores exactly. The 3 StoreCashier programs differ slightly on behavior score only (for example 0.988 and 0.985).
- **Native-perfect programs:** 20 of 120, on ABP, SEIRD, SAA, StoreCashier and HouseHeating.
- **Testable by this method:** ABP only, 7 programs. Its delays are shared by simulator and checker. Other scenarios have hardcoded expected values or no such setting, so they would need new reference answers.
- **Result:** all 7 pass with delays scaled ×2 and ×3. With ×0.5, 5 pass, and 2 refuse a case whose delay became 7.5. The spec defines delays as integers, so that change was invalid, not a defect. No case C.
- **Limits:** one scenario, and this catches rule violations only, not wrong values that satisfy the rules. Not pooled with the OTF column.

## 2026-11-04: Factual comparison with Prosimos

- Script: `scripts/engine_vs_prosimos_factual.py`; output `engine_vs_prosimos_factual_v1.json`. 400 cases, 10 engine seeds, 3 Prosimos seeds. Unpaired aggregates only.

| Measure, mean across runs | Loan engine | Loan Prosimos | Pharmacy engine | Pharmacy Prosimos |
|---|---|---|---|---|
| Case cycle time, days | 2.07 | 2.10 | 0.034 | 0.033 |
| Largest-queue pool wait, working minutes | 147 (Appraiser) | 176 | 0.98 (Pharmacist) | 0.99 |

Activity service times agree within about 1%. Visit rates differ most on rare branches (Contact customer or doctor, 38%; Return application, 14%), not tested for significance. Share of tasks waiting differs for Applicant (0 vs 0.16, though its mean wait is 0 in both) and Technician (0.09 vs 0.16). Sub-second waits in Prosimos' continuous times may explain this, because the engine uses whole seconds. That has not been checked. This comparison does not establish equivalence and cannot validate what-if answers.

## 2026-11-04: Family effects on the reference engine

`scripts/family_effect_summary.py`, `family_effects_v1.json`. Single illustrative interventions from the validation set, not a benchmark sample. Cases whose end time changed, across two seeds:

| Intervention | Loan (of 60) | Pharmacy (of 120) |
|---|---|---|
| Resource unavailable | 45, 42 | 34, 44 |
| Resource added | 34, 42 | 13, 51 |
| Duration scaled | 27, 14 | 54, 54 |
| Timer set to 0 | 56, 58 | 119, 114 |
| Routing probability changed | 28, 40 | 102, 112 |
| Case removed (of 59, of 119) | 4, 31 | 1, 27 |

## 2026-11-08: Pilot scripts and their review

Runner `scripts/pilot_runner.py` (stages `shared` and `programs`, resumable), summary `scripts/pilot_summary.py` (the only place gold is read), outputs in `runs/pilot_v1/`. Haiku calls go to the ledger `runs/build_test_pilot_claude/`. Questions: `pilot_questions_v1.json` (120, development data).

The same independent reviewer checked the scripts twice. It found no rows that needed rerunning. Fixes:
- **Summary, cohorts:** B0, each Ollama R1 model, each Claude R1 model and each DEVS-Gen model are now separate groups. They were pooled, against D16 and D18.
- **Summary, fallback yields:** missing reading answers no longer count as wrong fallbacks. Every configuration's fallback yield now uses one shared set of questions: those with a reading answer.
- **Summary, interpretation check:** it now compares every field.
- **Summary, bootstrap:** it resamples programs, then questions. It is descriptive only, since builds are not independent.
- **Runner, evidence:** directed evidence is committed only after its row is written, so a restart cannot reuse a question's own evidence. A crash between the two writes would drop that question's evidence instead; this is disclosed.
- **Runner, scope:** the native OTF path uses the interpreted scope, not the evaluation file's. Interpretation is 120 of 120 exact, so this changed no rows.
- **Runner, crash cache, not changed:** executions are cached in memory per process, so a transient crash is reused for that program's later configurations in the same process.
- **Runner, running processes:** the four stage-2 processes started before these fixes are left running, because stopping them mid-row would cause the contamination the fix prevents.

The pilot's templated questions were interpreted exactly in 120 of 120 cases. So this pilot cannot separate the gate from interpretation. That needs paraphrased questions, which are an optional extension.

**DEVS-Gen on Sonnet 5.5:** all six builds failed within 5 s. LiteLLM forces a tool call for JSON output, and Sonnet 5.5 rejects forced tool choice. The compatibility hook `adapters/devs_gen_hooks/sitecustomize.py` now sends `tool_choice: auto` for models that reject forced tool choice. Haiku is unchanged. This is a Category 1 change, disclosed with the temperature hook. The six builds are being rerun. Haiku Loan run_04 failed inside DEVS-Gen ("All root detailed-plan drafts failed"), a natural build failure.

**DEVS-Gen builds after the hook fix (2026-11-08):** all six Sonnet builds succeeded, in 206 to 269 s each. In total, DEVS-Gen built 11 of the 13 attempts that ran: Haiku Loan 2 of 4 (run_01 hit the 16k output limit, run_04 was a natural failure), Haiku Pharmacy 3 of 3, Sonnet Loan 3 of 3 and Sonnet Pharmacy 3 of 3. The first six Sonnet attempts were rejected with 400 errors before any build started, so they are not counted. Token use comes from the release's own call log (`runs/devs_gen/generation_tokens.jsonl`, via `scripts/wsl_generation_tokens.sh`). At list prices, with no cache discount assumed, this is Haiku $0.47 and Sonnet $4.61, $5.08 in all. This spend does not pass through our ledger.

**Anthropic spend so far, list prices:** $4.55 on the ledger (first build test $2.87, slices $0.01, pilot so far $1.67), plus DEVS-Gen $5.08, which makes **$9.63** of Ashraf's $100 in credits. The ledger's shared $15 cap still applies to ledger calls.

## 2026-11-07 (PT): Development pilot v1 complete

All 40 built programs finished stage 2 (24 OTF R1, 5 B0 native-only, 11 DEVS-Gen), 60 questions each, with no duplicate rows. Stage 1 finished all 120 interpretation, vanilla and RAG calls. Summary: `runs/pilot_v1/summary_v1.json`. Decline attribution: `scripts/pilot_attribution.py`, giving `runs/pilot_v1/attribution_v1.json`. Report: `manifests/pilot_report.md`, development data only.

Main verified points (details in the report):
- **Replay does most of the filtering.** It rejects every gpt-oss and qwen R1 program and 4 of 5 gemma programs.
- **Probes detect few errors.** In programs that passed replay, failing probes removed 6 wrong answers, all on OTF Claude. On DEVS-Gen they detected none, and their failures were timeout false alarms.
- **Directed's gain on OTF Claude is mostly abstention.** 50 of 54 errors removed (Haiku) and 42 of 58 (Sonnet) were questions where no probe could run. OTF records have no structured decision events, so the routing_probability probe never runs on OTF.
- **Vanilla reading is strong.** Haiku with the full document answers 0.667 of questions correctly, even though 17 of 120 calls were truncated at the 16,384-token output cap.
- **Interpretation cannot be tested here.** It was exact on 120 of 120 questions.

Decisions before the freeze are listed in the report. The routing_probability probe form is for Ashraf to decide. Timeouts as "could not run" and the vanilla output cap are routine.

**Spend, list prices:** the pilot ledger is $3.11 (2,136 Haiku calls). Our ledger total is $5.99: build test $2.87, slices $0.01, pilot $3.11. With DEVS-Gen at $5.08, Anthropic spend is **$11.07** of $100.

**Pilot review round 2 (2026-11-07):**
- The independent reviewer found that 8 of the 120 pilot questions need draws the document does not print, so their gold cannot be derived from the document (deterministic-realization rule). Verified with `validation/question_draw_coverage.py`, which flags the same 8.
- `scripts/make_pilot_questions.py` now rejects such questions (`undocumented_draws`).
- The pilot was re-scored on the 112 valid questions (`manifests/pilot_excluded_v1.json`, giving `summary_v1_valid112.json` and `attribution_v1_valid112.json`). The summary and attribution scripts gained an optional exclusion argument; without it they reproduce the earlier outputs exactly.
- Conclusions unchanged. Two observations rested only on invalid questions: generic's 2 OTF Haiku detections and the DEVS-Gen run_03 rule failures.
- The run_03 failures were dropped cases, not misroutings.
- `validation/probe_soundness_route_rule.py`: the rule probe accepts the reference in 184 of 184 cases.
- Disagreement-only was computed as a preliminary comparator (`scripts/pilot_disagreement.py`).
- **Review round 3:**
  - The generator filter, the validator and the exclusion code all passed. `printed_draws` equals the documents' plan-table cells exactly for both documents and all runs.
  - Report fixes: 4 blocked answers on the valid set carry over from the excluded question loa-routing_probability-02, so the valid-set numbers understate directed by up to 2 right answers per DEVS-Gen cohort. The exclusion also shifts the family balance. Three numbers were double-rounded. Claims resting only on the reviewer's local runs are now labelled as reviewer observations.
  - Provenance: `pilot_questions_v1.json` came from the generator without the filter.

## 2026-11-07: Form (b) route-probability probe and pilot v1b (D21)

- **What changed.** Ashraf chose form (b). `ProbeRunner.route_change` (record comparison) is used by directed when a program's records name no decisions.
  - Review 4 led to three changes: route-probability passes are not reused, the route rule uses exact decimals, and a no-switch check was added.
  - Review 5 led to a guard for draws within rounding of a route boundary. It fires on none of the pilot's 960 draws.
- **Validation:**
  - `validation/probe_soundness_route_records.py`: 204 of 204 reference cases pass per record shape.
  - `scripts/test_assurance_offline.py`: 0 failures, including 14 route_change checks.
- **Pilot v1b** (`scripts/pilot_rerun_routing_b.py`): re-decides only the directed routing_probability decisions (450 rows, OTF and DEVS-Gen) on the 112 valid questions, with fresh registries. It was run with and without the no-switch check (`runs/pilot_v1b/`, `runs/pilot_v1b_nocheck/`). The reviewer confirmed that nothing else differs from v1 and that no remaining block traces to an excluded question.
- **Result:** on OTF Claude, directed now removes its errors by detection.
  - Haiku: 22 probe failures and 12 blocks, at no cost in right answers. Coverage 0.765, precision 1.000.
  - Sonnet: 18 probe failures and 10 blocks. Coverage 0.717, precision 0.975.
  - Form (a) had 30 and 26 untested declines, costing 15 right answers each.
  - The detected defect is route probabilities fixed in the program, unaffected by the document.
- **Scoring scripts:** `pilot_summary.py` and `pilot_attribution.py` gained an optional run-directory argument.
- **Spend:** no model calls. Spend is unchanged at $11.07.
- **2026-11-07, Ashraf's decisions:**
  - Keep the no-switch check.
  - Use plain terms for decline classes: Caught, Already caught, Untestable, Failed history check, Can't express, Trusted.
  - The attribution files were regenerated with the new labels (`attribution_v1.json`, `attribution_v1_valid112.json`, `runs/pilot_v1b/attribution.json`, `runs/pilot_v1b_nocheck/attribution.json`). Each was checked to hold the same counts as before, under renamed keys.
  - The report has a glossary. Earlier manifest entries keep the old wording.

## 2026-11-08: Abstract registered; baseline judges proposed

- Ashraf registered the abstract himself on Nov 8. `manifests/abstract_draft.md` now holds the registered text verbatim; the earlier draft is kept below it.
- Domains confirmed by Ashraf: manufacturing, IT operations, loan and pharmacy (four settings; loan and pharmacy are the business-workflow processes).
- After the Nov 8 meeting with Dr. Roy, `manifests/baseline_judges_design.md` proposes trust-judge baselines: answer-level and program-level LLM-as-a-judge, and a ReAct judge with the same execution access as the gate. OTF-Tools and DEVS-Gen are platforms, not baselines.
  - One independent review found 16 issues (DEVS-Gen program view, a wrong claim that replay covers all runs, native-verdict leakage in `program.json`, cost and caching assumptions, scoring details). All were applied in the proposal.
  - Open for Ashraf: third platform, the spend and Claude-stop raise, and the Sonnet judge subset.
- Nothing implemented or run; no model calls.
- Later on 2026-11-08, Ashraf decided:
  - **Third platform:** ReCode. Still open: the published ReCode (arXiv 2510.23564, "Unify Plan and Action", built for interactive environments) or a plain reason-and-code agent.
  - **Claude stop:** raised from $15 to $25 in `scripts/b0_build_test.py`.
  - **Sonnet judge:** not run on dev.
  - **ReAct judge:** kept raw, with one sandbox code tool. The structured run tool and record diff were dropped.
- **Third platform (Ashraf, 2026-11-08):** a plain reason-and-code agent, named generically in the paper.
- **ReAct turn cap:** to be set from a dev smoke run (a generous cap of 20, then the smallest cap that lets about 95% of rows finish), replacing the unmeasured 8.
- **ReAct turn cap:** Ashraf kept 8, which replaces the data-set cap noted above. The smoke run reports turns used, and many rows hitting the cap goes to Ashraf.
- **Models (Ashraf, 2026-11-08):** the same everywhere.
  - All three platforms build with Claude Sonnet 5.5 and Haiku 5.5. Ollama-built OTF programs and B0 stay as extra, labeled cohorts.
  - Every LLM-based judge runs on Haiku for all rows, and on Sonnet for one shared random subset, drawn from row ids only and stratified by cohort and family.
  - Shared per-question work stays Haiku.
- **All five models everywhere (Ashraf, 2026-11-08):**
  - DEVS-Gen and the coding agent also build with gpt-oss, Gemma and Qwen.
  - Every LLM judge runs on Haiku for all rows. Sonnet, gpt-oss, Gemma and Qwen each judge the same shared subset.
  - Measured: Qwen local takes a median of 16 s per call. DEVS-Gen's LiteLLM supports Ollama, but this is untested. Local Ollama isn't running.
  - The estimated Ollama need is $15–20 against $8.73 credit. Details are in `baseline_judges_design.md`, decision 6.
- **B0 on Claude (Ashraf, 2026-11-08):** B0 also builds with Sonnet 5.5 and Haiku 5.5, at an estimated $1.50–3. It was never run on Claude before. B0 stays native-only.
- **Domain readiness (Ashraf, 2026-11-08):**
  - Manufacturing and IT operations reuse the MLSys documents and their validated simulators, with new counterfactual questions that carry structured bindings and no-effect controls (overlap with MLSys disclosed).
  - Gold is OTF-Tools' simulator plus its independent re-implementation, with an added sampled blind check by a separate agent.
  - **The freeze moves from Nov 10 to Nov 11**, so all three platforms can cover all four domains. Completion stays Nov 13.
  - The readiness work is delegated to a separate session that reports back for review.
- **Abstract updated in the submission system by Ashraf (2026-11-08):** it names three platforms, five builder models, four domains, and the native-check, LLM-judge and ReAct-judge baselines. The text and its commitments are in `manifests/abstract_draft.md`.

## 2026-11-08: Domain readiness, Phase 1 review (manufacturing and IT operations)

Readiness review only. No builds, no model calls, nothing in the library changed. Detail and plan: `manifests/domain_readiness.md`.
- **Verified:** both domains' gold sources (`sim.py`, and `validate.py` from the PDF alone) are deterministic. Every input they read is printed in the document, so the deterministic-realization rule holds by construction. It is still to be checked per question in Phase 2.
- **Verified:** IT windows fall into 6 time-overlap groups, which bound job sharing. Every MLSys IT document mixes groups, so the split is by window. The proposed split: dev groups 1, 3 and 5 (all `itops_dev` windows) and test groups 0, 2 and 4. Manufacturing: dev periods 01–03, period 04 left out, test periods 05–15.
- **Verified:** dev programs exist; all 12 Claude R1 builds are accepted. The adapter's fixed `HORIZON = 10**8` makes 5 of 6 Claude R1 manufacturing programs time out. With a last-ledger-day horizon all 6 run and match the reference on one changed production cell. All 6 IT programs match first starts (85 of 85) under one priority change. One change per program: it shows the path works, not a rate.
- **Verified:** the library is workflow-only throughout. `policy.request_seed` hashes the `Query` and `Intervention` `__dict__`, so new domains need new types, leaving workflow seeds unchanged.
- DEVS-Gen has no manufacturing or IT tasks. Conversion looks clean, with a generic stdin format and no per-family keys.
- Open for Ashraf: test programs (new builds on a test document, or dev programs reused), the IT blind-check method, and the test-set size.
- **Domain readiness, Phase 1 reviewed (2026-11-08).** Ashraf decided:
  - **Test programs:** dev-built programs are reused on unseen test records for all four domains and all platforms; no new OTF builds on test documents.
  - **IT blind check:** agents write their own scheduler from the document alone, recorded as a third independent implementation.
  - **Test size as proposed:** 96 manufacturing and 120 IT, with dev at 48 and 60.
  - **Added after review:** probe soundness for every new family, one shared spec per domain for all four domains, a documented runner interface, and provenance hashes and licenses for the raw data.
  - Phase 2 is under way in the domain-readiness session.

## 2026-11-08: Domain readiness, Phase 2 checkpoint (question files and realization check)

Ashraf's decisions, relayed by the coordinating session:
- **Test programs:** dev-built programs are reused, so there are no test builds.
- **IT blind check:** separate agents write their own scheduler. It counts as a third implementation.
- **Sizes:** dev 48 manufacturing and 60 IT; test 96 and 120.

No model calls, no builds.

- **Gold** (`scripts/mlsys_gold.py`). `sim.py` runs on chapters and windows rebuilt from the raw records (read-only from the MLSys folder). `validate.py` runs from the PDF alone.
  - **Factual check:** all 60 manufacturing chapters and all 30 IT windows reproduce every printed ledger or task-log row through both routes, with identical inputs.
- **Split** (`scripts/make_mlsys_splits.py`, giving `manifests/mlsys_splits_v1.json`):
  - **Manufacturing:** dev 12 chapters (periods 01–03), 4 left out (period 04), test 44 (periods 05–15).
  - **IT:** dev 16 windows (time-overlap groups 1, 3, 5), test 14 (groups 0, 2, 4).
  - **Sharing, from real ids:** 0 jobs and 0 machines shared across the split. 51 within-group window pairs share jobs, which is why the grouping is needed.
- **Build-input check:** all 48 existing manufacturing and IT OTF programs (B0, R1 and R1 Claude) were built on `mfg_dev` or `itops_dev`, all of which is dev. No program's code names a test chapter or window.
  - The builds read a byte-different copy of each PDF (`runs/build_test_v1/docs/`) whose document map is identical.
- **Questions** (`scripts/make_mlsys_questions.py`, seed 20271108):
  - `manifests/mlsys_questions_dev_v1.json`: 108 questions (48 + 60). Half of them are on chapters seen at build time.
  - `manifests/mlsys_questions_test_v1.json`: 216 questions (96 + 120), all on unseen chapters.
  - 12 dev and 24 test questions per family. One in five is a no-effect control (18 dev, 36 test).
  - 0 disagreements between the two references, and 0 questions without a defined answer.
  - Hashes are in `manifests/mlsys_questions_v1.sha256`. Regenerating gives byte-identical files.
- **Realization check** (`validation/mlsys_input_coverage.py`) on both files: 324 of 324 pass, 0 fail.

## 2026-11-09: Domain readiness, Phase 2 complete (manufacturing and IT operations)

No paid model calls, no builds. Detail is in `manifests/domain_readiness.md`, Phase 2.
- **Correction to the checkpoint entry above.**
  - The pinned clone's working-tree PDFs were rewritten by a `core.autocrlf=true` checkout. pdfium reads them; pdfplumber fails on some.
  - All gold, maps and specs now use the committed blobs, written byte-exact to `runs/mlsys_docs/`. Their hashes equal the MLSys originals and the dev builds' copies, so the "byte-different copy" line above is wrong.
  - The question files regenerated byte-identical, and the build-input check now matches stored navmaps exactly (48 of 48).
- **Library:** `assurance/mlsys.py` is new and no shared library file changed.
  - Offline tests: 118 PASS, 0 failures. Workflow offline tests: 0 failures.
- **Separate-agent review: two rounds, all fixes applied.**
  - Round 1 had 13 findings. The worst was IT probes passing an empty changed output, fixed with a completeness invariant. Also fixed: rule-only permits, two binding-check holes, a per-document policy fingerprint and crash paths.
  - Round 2 confirmed the fixes and found no new hole. It added a positive `task_request` witness, labels for non-discriminating witnesses, a gram tolerance and an adapter version bump to 0.2.
- **Probe soundness** (`validation/probe_soundness_mlsys.py`, giving `manifests/probe_soundness_mlsys_v1.json`): the reference run as a program is Caught 0 times.
  - Directed on the 108 dev questions: 106 Trusted, 2 Untestable. Every answer equals gold.
  - Broken programs are Caught on every defect except CPU-into-memory confusion, where 1 wrong answer is Trusted. 21 of 36 reference `task_request` permits rest on witnesses that cannot tell the two resources apart. This is a reported limit.
- **Blind check:**
  - Manufacturing by hand: 2 agents, 16 of 16 match gold.
  - IT: 2 agents wrote their own scheduler from the document, reproduced all 8 printed logs, and 20 of 20 match gold.
  - Files: `validation/blind_review_mlsys/`.
- **Shared task specs** for all four domains are in `adapters/generic_tasks/`. The workflow specs are verbatim; the existing workflow DEVS-Gen files are unchanged.
- **DEVS-Gen tasks:** `Manufacturing` and `ITOperations` are installed in WSL and listed by `--list-benchmarks`. Not built.
- **Adapter smoke on dev** (676 rows, 29 existing OTF programs): 102 Trusted, all right on the diagnostic path.
- **Provenance:** raw-file sha256 values are in `manifests/mlsys_raw_hashes_v1.json`. Licenses: SupplyGraph LGPL-2.1, Google trace CC-BY 4.0.
- **Runner:** entry points are listed in `domain_readiness.md`; `pilot_runner.py` was not edited.

## 2026-11-09: Coordinating session's review of domain-readiness Phase 2

The domain-readiness session's checks were rerun independently.
- Workflow offline tests: 0 failures.
- mlsys offline tests: 0 failures.
- Realization check on both question files: 324 of 324 pass.
- Question-file hashes match `manifests/mlsys_questions_v1.sha256`.
- Blind score: manufacturing 16 of 16, IT 20 of 20, two agents each.
- Only tracked change: `scripts/b0_build_test.py` (the cap raise). The baseline clone is clean at `10f5401`, and the workflow DEVS-Gen task files are untouched.
- Ledgers unchanged: Claude $5.99, gpt-oss $1.18, Gemma $0.74.

One fix requested: the coverage script passes silently when given no files. Accepted limits to report in the paper:
- CPU/memory confusion is untestable where one machine is largest in both.
- The IT history check covers the window only, while half of the IT questions ask about after it.
- IT `failure_removal` is Untestable where no task stopped.
- 31 mid-period capacity questions are Can't express on single-constant OTF programs.
- **Fix (2026-11-09, after the coordinating session's check):** `validation/mlsys_input_coverage.py` run with no question file used to print "0 questions checked" and exit 0. It now exits 2 when no questions are checked. Rerun on both files: 324 checked, 0 fail, exit 0.

## 2026-11-09: Workflow test set (Loan Application and Pharmacy)

No paid model calls, no builds. Unchanged: `assurance/`, `pilot_runner.py`, the dev set, the manufacturing and IT files, and `baseline/`. Detail is in `manifests/workflow_test_set.md`.

- **Test documents:** `runs/workflow_docs/workflow_{loan,pharmacy}_test/` (`scripts/workflow_test_set.py`).
  - Run 05–12 with seeds `test-<process>-05..12`, 15 cases per run.
  - Same renderer, layout and `MIN_VISITS` as dev. Maps are made with `otf_r1.navmap.build_map`.
  - Byte-reproducible: reportlab invariant mode, which fixes only the timestamp and file id.
  - `runs/` is git-ignored, so the test documents are regenerated, not committed.
- **Split:** `manifests/workflow_splits_v1.json`, by full run.
  - Seeds and titles are disjoint from dev, and no table is shared.
  - All seven printed sections of every dev and test run equal the reference's factual run.
  - All 48 OTF programs were built on dev maps only. The spec files and all 13 built DEVS-Gen programs (WSL scan) contain no test title, seed or test route draw.
- **Questions:** `manifests/workflow_questions_test_v1.json`, 240 in all.
  - 120 per process, 20 per family, 48 no-effect controls. Seed 20271109, byte-reproducible. Hashes in `manifests/workflow_questions_test_v1.sha256`.
  - The generator reuses the dev functions. It reproduces `pilot_questions_v1.json` byte for byte with seed 20261107 (found by regeneration; not recorded before).
  - Test-only rules:
    - exact repeats are skipped;
    - the try cap is 2000;
    - workers are named when only part of a pool is unavailable (10 questions).
- **Checks, all passing:**

  | check | result |
  |---|---|
  | realization coverage | 0 of 240 fail |
  | independent checker, same scenario | 240 of 240, whole output identical |
  | checker with the printed route draws | 240 of 240 |
  | every value used is printed (new form C, which flags exactly the 8 excluded dev questions) | 240 of 240 |
  | factual runs | 32 of 32 |
  | checker on the dev file | 120 of 120 dev gold |
  | workflow offline tests | 0 failures |

- **Probe soundness on test documents** (`manifests/probe_soundness_workflow_test_v1.json`): the reference, run as a program, is **Caught 0 times**.
  - The four existing workflow checks were rerun on test runs: 0 rejections.
  - Full decisions in two record shapes:
    - directed: 236 Trusted and 4 Untestable;
    - generic and program_wide: 240 Trusted each;
    - 0 history-check failures;
    - the answer equals gold on 235 of 235 expressible questions.
  - 5 no-effect controls can't be written into the generic input and are recorded as inexpressible; directed still Trusts them.
  - 2 Loan route-flip witnesses need unprinted visits; dev has 0. Neither was used.
- **Blind check:** 12 questions, 1 per family per process. Agents A (Opus) and B (Sonnet) each wrote their own simulator from the document. Both reproduced all 9 chapters, and **24 of 24 answers match gold**. A sample-script bug that truncated chapters was caught by agent B, fixed, and the check redone.
- **Review:** one separate reviewer, 8 findings. Fixed:
  - the checker's derivability claim (form C added);
  - the program-input check (DEVS-Gen config parsing, a WSL program scan, failing on empty input);
  - the factual check, now all seven sections;
  - the reference wrapper, which now fails on any value not in the input;
  - blind scoring.

  Reported, not changed (library): the policy fingerprint and the 5 Trusted-but-inexpressible controls.
- **For decision (Ashraf or the coordinating session):**
  1. The workflow policy fingerprint includes the "Chapters in this document" line, so dev evidence never carries over to test. `mlsys.py` already drops it.
  2. How to count the 5 inexpressible controls.
  3. Policy-variant reuse: no question in any domain tests it. The smallest design is about 96 workflow questions, about 5 hours and no builds (`workflow_test_set.md`, section 9).

## 2026-11-09: Coordinating session's review of the workflow test set; Ashraf's decisions

- **Rerun independently:**
  - `sha256sum -c` on all 13 files: OK. The dev file's hash is unchanged.
  - Coverage: test 0 of 240, dev exactly 8.
  - Offline tests: 0 failures.
  - Checker A, B and C: 240 of 240 each.
  - Soundness: 0 blockers.
  - Blind check: 12 of 12 for each of two agents.
  - No new spend.
- **Ashraf decided:**
  - **Policy fingerprint:** drop the "Chapters in this document" line in `assurance/request.py`, as `mlsys.py` already does, so dev evidence carries over to test documents. This is a library change made after the pilot: disclosed, reviewed, with dev decisions shown unchanged.
  - **Policy-variant reuse:** added for workflows only. Variant P is a real policy change and variant H a harmless rewording, with 96 questions in a separate file.
- **Adopted:** test material is hidden from builders during DEVS-Gen and coding-agent builds.
- **Open:** how to count the 5 no-effect controls that the gate can Trust but the generic input cannot run. Ashraf asked for an explanation first.
- The work is assigned to the `workflow-test-set` session.
- **Ashraf chose option A (2026-11-09) for questions with no answer.** A question counts as answered only if it is trusted and an answer exists; otherwise it is recorded as Can't express. The rule applies to every judge and every domain, with no library change. It affects at most 5 of the 240 workflow test questions per spec-built program (coverage only; precision and yield are unchanged). The scorer applies it, and the paper reports these cases.

## 2026-11-09: Full review of what is implemented (three separate reviewers)

The coordinating session checked the main findings against the code and data. Nothing is fixed yet except the stale records.

**Library: must fix before main runs**
1. `probes.route_rule` checks only visit-1 decisions. A program that ignores a route-probability change is Trusted when the change switches only a later visit. This affects programs whose records name decisions (DEVS-Gen). Verified by reading the code; the reviewer reproduced it on Loan Runs 01–04.
2. In `policy._directed`, passes of the request's own rule are reused across requests. For `resource_availability/unavailable`, a pass on one interval is reused for another interval. Verified by reading the code.
3. NaN and infinite values are not guarded in the workflow contract or parser (`mlsys` guards them).
4. `program_wide` is seeded per request, so one program gets different verdicts.
5. Generic witnesses can repeat.
6. The `replay` config also applies the contract; this needs to be documented.

**Questions: should fix before freeze**
1. IT yes/no deadlines equal the factual start. The text reveals that value even when the window doesn't print it (14 questions), and "effectful" coincides with "gold = no". Verified.
2. Six workflow test controls and two dev controls for activity_duration target a visit the case never makes. These are unknown-target requests, not no-effect controls.
3. The four files can't be read by one scorer yet: the dev workflow file lacks some fields, and `gold` types differ across files.
4. Dev runs pass whole MLSys document maps, which include test chapters' records.
5. Test files are visible to future builders.
6. Smaller items:
   - wording predicts the effect in `resource_availability`;
   - one identity-change control;
   - three duplicate pairs in dev;
   - delays that move production past the chapter end;
   - hash coverage gaps;
   - two count errors in `domain_readiness.md`: 10 Can't-express capacity questions, not 31; and a no-effect rate of 1 in 6, not 1 in 5.

**Fine**
- All hashes pass, and the generators are byte-reproducible.
- Gold recomputes on all 684 questions.
- No test leakage into any build or spec: 309 files and 13 DEVS-Gen programs scanned.
- Question text agrees with the bindings.
- Both offline suites pass (68 and 118).
- Spend matches the ledgers.

**Records: fixed now**
- D22 and D23 added; D7, D10 and D16 superseded parts marked.
- Stale status, freeze, stop and spend lines corrected in `baseline_judges_design.md` and the manifest header.

**Not built yet** (from the records review):
- judges;
- the coding-agent platform;
- runner support for manufacturing, IT, test and policy files;
- scoring rule A in the summary;
- the 64k output cap and caching;
- B0 Claude builds;
- DEVS-Gen manufacturing and IT builds;
- Ollama DEVS-Gen builds.

The estimated remaining work does not fit before the Nov 11 freeze without cuts, and the test-run cost estimate from actual row counts is still owed.

## 2026-11-09: Workflow test set, Ashraf's decisions applied (fingerprint, policy variants, builder isolation)

No paid model calls and no builds. Detail is in `manifests/workflow_test_set.md`, sections 8 and 10–12.

**Library change, made after the development pilot (disclosed).**
- **What changed:** `ProcessSchema.policy_fingerprint` in `assurance/request.py` drops the closing "Chapters in this document: Run …" line, anchored to the exact list at the end. This is the only library change.
- **Fingerprints:** dev and test now share one per process (Loan `78b0ef97…`, Pharmacy `eaadfaae…`), so dev capability evidence carries over to test. Policy edits still change the fingerprint.
- **No dev pilot decision changes:**
  - 5 dev OTF programs re-decided before and after on every valid question, both request sources and all five configurations: 0 of 554 rows differ (2,770 decisions);
  - the reference run as a program on dev gives byte-identical output;
  - test-set soundness is identical;
  - offline tests: 0 failures, with 7 new fingerprint checks.
- **Old pilot registries:** `runs/pilot_v1*/registries` still hold the old fingerprint values. They must not seed reuse.

**Scoring rule for inexpressible questions (Ashraf):** a question counts as answered only if it is Trusted and an answer exists; otherwise it is Can't express. This applies to every judge and domain. The coordinating session applies it in the scorer; no library change.

**Policy-variant reuse set.** `scripts/workflow_policy_set.py`, `scripts/make_workflow_policy_questions.py`, giving `manifests/workflow_questions_policy_v1.json`; hashes in `manifests/workflow_questions_policy_v1.sha256`.
- **Variants:**
  - P raises one pool by one worker (Loan Appraiser 2→3, Pharmacy Pharmacist 1→2), on Runs 13–14;
  - H rewords the front-matter prose with the same parameters, on Runs 15–16.
- **Checks on the variants:**
  - P changes only that count;
  - H changes no parameter and nothing the library parses;
  - all printed sections equal the reference.
- **Fingerprints:** P differs from dev, as it should. H also differs from dev: an unnecessary invalidation, reported, and the fingerprint was not tuned.
- **91 questions, 5 short of the planned 96.** Exhaustive enumeration proves the shortfall unavoidable on the decided runs:
  - Loan P has no effectful case removal (0 of 420);
  - Pharmacy P and H have no no-effect timer change (270 of 270 effectful).
- **Checks on the questions:** coverage 0 of 91 fail; checker A, B and C 91 of 91 each; 16 of 16 factual runs.
- **Blind check:** four agents, 96 of 96 answers match gold.
  - All four reproduced all 8 variant chapters, and all found no rule change in H.
  - H was reworded once after review (two slight shifts), and the blind check was redone on the new text.
- **Probe soundness is not clean on the variants.** The reference is Caught on 2 of 91 questions in the shape with decision events and 3 of 91 without:
  - two route-flip witnesses need loop visits the document does not print;
  - one flip changes only decision records.

  These are gaps in the library's witness choice, not in gold. They need a decision: a library fix, or report them as measured unsoundness. Test (240) and dev (112) remain at 0 Caught.

**Builder isolation.** `manifests/builder_isolation.md` and `scripts/check_builder_isolation.py`.
- The rule: hide everything with OS isolation and give back only the inputs. For WSL, bubblewrap with `--tmpfs /mnt --tmpfs /home --unshare-net --clearenv`.
- The check has a positive control and treats a permission error as visible. It also reports alternate Windows spellings, host mounts, the network, credential names and workspace escapes.
- Tested: 0 findings under the prescribed WSL isolation; 44 to 153 findings without it.
- The DEVS-Gen scan and the split check now also cover the variant documents: 13 DEVS-Gen run folders (11 with a built program), 0 violations.

**Review:** a second separate reviewer found 6 issues. Fixed:
- the H wording, then re-rendered;
- the anchored fingerprint regex;
- isolation-check holes;
- the path list;
- the variant scan;
- a docstring;
- the hash files;
- the zero-time-flip check.

Reported, not fixed (library or runner): the probe-witness gaps and the old registries.

## 2026-11-09: Manufacturing and IT fixes after the independent review (items 1–3), with item 1 open

No paid calls, no builds, `assurance/` not touched.

- **Item 1, IT yes/no deadlines: open, needs Ashraf.** The old rule (deadline equal to the factual start) is gone.
  - **Steered draw, tried and rejected.** A printed-range draw (`[submit, W + longest run time]`) keeping the first random candidate with the wanted effect passed the requested checks: 39 yes/no, both answers, no equalities, no unprinted time in the text. But the separate-agent review of the generator showed that effectful deadlines then sit inside the narrow gap between the two starts (median 14 s, minimum 1 s). That points at unprinted starts, for example `itops-test-machine_removal-06` with factual 1409 and deadline 1405.
  - **Unsteered draw, now in the files.** One draw per draft from `[submit, W + this task's run time]`, with no use of either start (`scripts/make_mlsys_questions.py draw_deadline`). It does not leak, but only 13 yes/no questions survive the no-effect quota, all with gold yes. It fails the "both yes and no" check (`validation/mlsys_deadline_check.py`, which now also reports deadline-to-start distance, the yes rate and two baselines).
  - **Fixed deadline at the window end, tried in scratch only.** 18 yes/no, but dev is all yes, and 1 deadline equals a start.
  - **Recommendation:** drop yes/no questions from IT and ask every IT question as a first-start time. Alternatives are steering with a minimum gap (still a partial leak) or exempting yes/no from the quota.
  - **Current files:** dev `910fc0d3…` and test `f1feeb44…`, in `manifests/mlsys_questions_v1.sha256`. Coverage is 324 of 324 and gold agreement holds for all 60 chapters and 30 windows. Manufacturing questions are unchanged throughout. 133 IT questions differ from the original files (`manifests/mlsys_questions_v1_changed_ids.json`): ids are kept, but the drafts filling them shift.
  - **Blind check v2:** IT agents A and B re-answered the 10 sampled IT questions of the steered version with their own schedulers, reproduced all 9 printed logs, and both scored 20 of 20. Manufacturing is unchanged at 16 of 16. Key: `validation/blind_review_mlsys_key_v2.json`, which records the steered files' hashes. Score: `validation/blind_review_mlsys/score_v2.json`. Hashes: `validation/blind_review_mlsys_v2.sha256`. Redo it for whichever rule is chosen.
- **Item 2, doc corrections in `manifests/domain_readiness.md`, done:**
  - 10 mid-period capacity questions (3 dev, 7 test), not 31. The 31 came from a check run before the capacity-line parsing fix.
  - The no-effect rate is 1 in 6 (`n // 5`).
  - The status line is updated, and so is the DEVS-Gen tasks line.
  - Delays past the last ledger day are disclosed: 4 of 12 dev and 10 of 24 test.
- **Item 3, hashes, done:**
  - `manifests/mlsys_docs_v1.sha256` covers the 12 PDFs and 12 navmaps under `runs/mlsys_docs/`; the navmaps are also in `manifests/mlsys_raw_hashes_v1.json`.
  - The blind key now records its seed, the question files with their sha256, and the input files' sha256.
  - `validation/blind_review_mlsys_v2.sha256` covers the v1 and v2 keys and scores.
- **Item 4:** soundness and the offline tests wait for the library fix.

## 2026-11-09: Library fixes after the full review (D24)

- **Fixed in `assurance/`** (probes, policy, contract, interpret, mlsys):
  - the route rule checks every visit, every case end and the fully printed case paths;
  - no reuse of request-specific rule passes;
  - NaN and infinity guards;
  - `program_wide` seeded per program;
  - generic dedupe;
  - route-flip witnesses limited to fully printed, path-changing flips.
- **Pre-fix copy** kept in the coordinating session's scratchpad (`assurance_before_fix`).
- **Results:**
  - offline tests 0 failures;
  - dev soundness 0 rejections;
  - the reviewer's adversarial programs are never Trusted;
  - 2,610 reference paths, 0 mismatches.
- **Usable route flips** before → after: dev 168/265 unchanged; test Loan 350 → 348; policy Loan H 97 → 96, Loan P 77 → 75, Pharmacy P 123 → 122.
- **Next:**
  - the domain sessions rerun test and policy soundness on the fixed library;
  - the dev pilot is rescored with the fixed library before the freeze.
- **IT yes/no questions dropped (coordinating session, 2026-11-09).** IT questions now all ask for a first-start time. Three deadline rules were tried: steered (leaks the start, with a median gap of 14 s), unsteered (gold always yes) and window end (one deadline equals a start). Each either leaked the start or lost the yes/no mix. This is a question-format change, decided on the generator's own checks; no system result was seen. Sizes, quota and seeds are kept.
- **Review 5 (confirmation round), fixed:**
  - no Trusted route rule without a path check: no task records or an unreadable flow give Untestable;
  - a partial task shape gives Untestable, not Caught.

  The soundness wrapper in `validation/probe_soundness_route_rule.py` now prints task starts, as the generic output format requires.
  - Reviewer adversaries: no bad program Trusted in any of 5 modes; the correct reference is accepted with task ends only.
  - Dev soundness: route rule 184 cases with 0 rejections and 3 Untestable (no altered path fully printed); route records 0; flips 433 with 0 problems; workers 0.
  - Offline tests: 0 failures.
  - Timing after a switch is unchecked by the route rule; reported as a limit.

## 2026-11-09: IT questions made numeric only; soundness on the final library

- **Decision (Ashraf, via the coordinating session):** drop IT yes/no questions. Every IT question now asks for a first-start time.
- **Generator** (`scripts/make_mlsys_questions.py`): `it_query` keeps its single main-stream draw. The deadline code is removed, and so is a dead `seed` parameter.
  - A new label field, `beyond_window`, marks 22 dev and 71 test IT questions.
  - Seed, sizes and the `n // 5` quota are unchanged. The files are byte-reproducible: dev `f9c58262…`, test `d9f5ff82…` (`manifests/mlsys_questions_v1.sha256`).
  - 271 of 324 questions differ from the original files (`manifests/mlsys_questions_v1_changed_ids.json`; new label fields ignored). Manufacturing test changed too, because one random stream is shared across blocks.
  - The separate-agent review found the diff correct and complete. It recommends per-block seeding (not adopted, open).
- **Checks:**
  - Coverage: 324 of 324 pass.
  - Gold agreement: all 60 chapters and 30 windows.
  - `validation/mlsys_deadline_check.py` now asserts that no question is yes/no. It finds 0.
- **Blind check v3**, redone for sampled questions whose text changed (4 of 8 manufacturing, by hand; 10 of 10 IT, with the agents' own schedulers, all 8 logs reproduced):
  - Manufacturing 16 of 16 and IT 20 of 20 match gold.
  - Key: `validation/blind_review_mlsys_key_v3.json`, which records the current questions-file hashes.
  - Files: `validation/blind_review_mlsys/v3/` and `score_v3.json`. Hashes: `validation/blind_review_mlsys_v3.sha256`.
  - The 4 unchanged manufacturing answers are carried from v1 and marked as such.
  - IT agent A notes that its B05 answer depends on the reservation tie rule "first machine, in id order", which no printed log separates from the alternative reading. The answer follows the text.
- **Final library (D24) results:**
  - `scripts/test_assurance_mlsys_offline.py`: 118 PASS, 0 failures. `scripts/test_assurance_offline.py`: 0 failures.
  - **Probe soundness**, reference Caught 0 on both splits:
    - dev (108): manufacturing 48 Trusted; IT 57 Trusted, 3 Untestable; answers equal gold 108 of 108;
    - test (216): manufacturing 95 Trusted, 1 Untestable; IT 119 Trusted, 1 Untestable; answers equal gold 216 of 216;
    - files: `manifests/probe_soundness_mlsys_v2_{dev,test}.json`.
  - **Broken programs** on test: Caught on every defect except IT CPU-into-memory confusion, where 5 wrong answers are Trusted (dev: 0 wrong Trusted).
  - **No directed change:** on the original dev questions, the final library reproduces the v1 directed counts (manufacturing 48 Trusted; IT 58 Trusted, 2 Untestable) and every broken-program count.
- **Coordinating session, after the manufacturing/IT final soundness (2026-11-09):**
  - Accepted the numeric-only IT questions: reference Caught 0 on dev and test, blind v3 at 16/16 and 20/20.
  - Removed `task_starts_by` from the IT interpreter prompt in `assurance/mlsys.py`. No questions use it; code support is kept. mlsys offline tests: 0 failures.
  - Per-block seeding not adopted (files are final).
  - Open: whether `task_request` permits that rest only on witnesses that cannot tell CPU from memory become Untestable. The cost and gain are being measured for Ashraf.

## 2026-11-09: Workflow test and policy sets regenerated after the external review; soundness with the final library

No paid calls, no builds. This task did not touch `assurance/`: the library fix is the coordinating session's (D24). Detail is in `manifests/workflow_test_set.md`, sections 3, 10 and 13.

**New generator rules** (`scripts/make_workflow_test_questions.py` `rule_skip`, `rules=True`). They apply to test and policy only. The dev regeneration checks still give `7f0d560d…` and `2f81ac6f…`.
- **Rule 4:** no activity-duration change at a visit the case never makes. Those are unknown-target requests. They were 6 of 8 earlier test controls, including the 5 inexpressible ones, and 3 policy controls.
- **Rule 5:** no identity change (factual work or wait, or published route probabilities). Example: `loa-test-routing_probability-03`.
- **Rule 6:** resource_availability stratified by operation. Each operation gets half the questions and half the controls. In the test set that is 2 controls and 8 effectful per operation per process; before, Loan "unavailable" was never a control. In the policy set, Loan P has no effectful added-workers change, so it falls back.
- **Rule 7:** no "unavailable" change whose workers do no task in the factual run.
- A second separate reviewer checked the first version. It found:
  - stale hashes;
  - positional ids;
  - an overstated balance claim;
  - rule 6 unable to act on the policy set;
  - uncounted skips;
  - one trivial control.

  All were fixed: full stratification, rule 7, skip counts, questions sha256 in every derived file, and old-to-new id maps.

**Files:**
- **Test:** `manifests/workflow_questions_test_v1.json` is now `fe754f44…` (was `b5fb5bec…`). 240 questions, 48 controls. 147 earlier questions survive by content and 116 keep their id. Map: `…test_v1.idmap_b5fb5bec.json`.
- **Policy:** `manifests/workflow_questions_policy_v1.json` is now `fc79f0db…` (was `9a2b863b…`). 91 questions; the 5-question shortfall proof is unchanged. Map: `…policy_v1.idmap_9a2b863b.json`.
- **Ids are positional:** join earlier results only through the maps.
- **Dev, not edited:** `pha-activity_duration-03` and `-04` are unknown-target requests, to report separately. Three exact duplicate pairs remain after exclusions, and Loan routing_probability has 4 valid questions.
- `manifests/pilot_excluded_v1.json` is now hashed in `manifests/workflow_questions_test_v1.sha256`.

**Checks on the final files:**

| check | test | policy |
|---|---|---|
| coverage | 0 of 240 fail | 0 of 91 fail |
| checker A, B, C | 240 of 240 each | 91 of 91 each |
| factual runs | 32 of 32 | 16 of 16 |
| byte-reproducible | yes | yes |
| hashes | all 40 verify | |

- **Blind checks:** each regeneration changed the sampled questions, so fresh agents redid them on the final files:
  - test, agents K and L: 24 of 24;
  - policy, agents M and N: 48 of 48.

  All reproduced every chapter. Earlier samples: test A/B and G/H, 24 of 24 each; policy C/D, E/F and I/J, 48 of 48 each.

**Probe soundness with the final library** (D24):

| set | directed | Caught |
|---|---|---|
| dev, 112 | 110 Trusted, 2 Untestable | 0 |
| test, 240 | 239 Trusted, 1 Untestable | 0 |
| policy, 91 | 90 Trusted, 1 Untestable | 0 |

- 0 Caught in both record shapes, and 0 blockers.
- Answers equal gold on every expressible question. The test and policy sets have no inexpressible questions.
- **The three earlier misfires:** `loa-polP-routing_outcome-00` and `-01` are now Trusted. `pha-polP-routing_outcome-03` is now Untestable (its only witness was the zero-time flip, now excluded). That is the only Untestable the fix introduced.
- Offline tests: 0 failures, workflow and mlsys.

**Doc corrections:**
- builder isolation is marked adopted;
- section 8 records the decisions;
- the status line is updated;
- the DEVS-Gen scan covers 13 run folders, of which 11 hold a built program (Haiku Loan `run_01` and `run_04` have no `run.py`).
- **Measurement only (scratch wrapper, no library change):** what if a `task_request` permit resting only on witnesses labelled `(cannot tell cpu from mem)` became Untestable?
  - **Reference:** IT `task_request` rows going from Trusted to Untestable: 3 of 12 on dev and 11 of 24 on test.
  - **CPU-into-memory broken program:** wrong Trusted answers go from 0 to 0 on dev, and from 5 to 0 on test, so all 5 are removed. It also loses 2 right answers on dev and 2 on test.
  - **Elsewhere:** no other family, domain or broken program changes, and manufacturing is unaffected.
  - Script: the session scratchpad's `measure_nondisc.py`.
- **IT CPU/memory blind spot (Ashraf, 2026-11-09):** delegated to session `cpu-mem-blindspot`.
  - **Structure:** a deterministic router. Where there is no blind spot, today's method is unchanged; where there is, a new method; if that fails, Untestable.
  - **Rules:** open search for ideas; dev data and generated dev scenarios only; up to 10 logged attempts; deadline Nov 10, 12:00; the success bar is written before the first attempt; a separate-agent review; one final test run, reported as it comes out.
  - **Fallback, if no attempt meets the bar:** still Ashraf's choice.
- **Blind-spot fallback (Ashraf, 2026-11-09):** if no attempt meets the bar, task_request permits that rest only on non-discriminating witnesses become Untestable. This is to be disclosed as decided after seeing test diagnostics from planted bugs; no real system results were seen.
- **Blind-spot check extended to every family (Ashraf, 2026-11-09).** Phase 2 of the `cpu-mem-blindspot` session runs after the IT work.
  - A confusion catalog per family is written before any measurement: wrong visit, target, case, day, field or magnitude, or a wrong time.
  - Planted programs are measured on dev, with the same router and guardrails as the IT work.
  - The Untestable fallback outside IT is measured only, not applied, until Ashraf decides.
  - Deadline Nov 10, 23:59. During this phase only, that session may edit `probes.py`, `policy.py` and `mlsys.py`.

## 2026-11-09: IT CPU/memory blind spot resolved (session `cpu-mem-blindspot`)

Details: `manifests/it_blindspot.md` (success bar written before attempt 1, both attempts, review, test run).
- **Method (attempt 2 of 10 allowed):** on a blind-spot `task_request` row, today's probes and today's reuse
  path run unchanged. Only where today's method would say Trusted, a new step decides:
  - split off the machines largest in both resources;
  - check the program handles that removal alone (else Untestable);
  - run today's kind of discriminating witness on the remaining cluster, as one composite input (fail: Caught;
    pass: Trusted).
  Non-blind rows are untouched by construction. The split's registry rows use their own key per resource.
- **Attempt 1 failed bar 3:** it replaced today's witness, losing 2 `moves_prefix` Caught rows. It was discarded.
- **Library:** `assurance/mlsys.py` only (router lines in `_directed` plus the new functions); final sha256
  `e06dd8be284a157d8698410f4658ff98adfaab35089c8c607c179223be3372c0`, pre-change
  `20eaa46f...48500` (copy in the session scratchpad).
- **Tests:** `blindspot_tests` added to `scripts/test_assurance_mlsys_offline.py`. Both offline suites: 0 failures.
- **Dev (exhaustive generated scenarios, 40,800 rows; fresh and shared registries):**
  - reference Caught 0; non-blind and other-family rows all identical; no Caught row lost;
  - reference Trusted on 2,191 of 2,191 blind rows;
  - CPU-into-memory program Caught on 1,098 of 1,098 blind CPU rows; wrong Trusted 75 -> 0 (fresh registry);
  - dev questions: 0 reference rejections, saved as `manifests/probe_soundness_mlsys_v3_dev.json`.
- **Review (separate agent):** no soundness hole. A shared-registry leak into non-blind rows was fixed, plus a
  second leak of the same kind found during the fix; both now tested.
- **Test (one run, after freezing):** `manifests/probe_soundness_mlsys_v3_test.json`.
  - 0 reference rejections; IT `task_request` reference 24 of 24 Trusted, including the 11 blind-spot rows the
    Untestable fallback would have cost.
  - CPU-into-memory program: wrong Trusted 5 -> 0 (all Caught); right Trusted 5 -> 3.
  - Every other row and broken program unchanged.
- **Costs and limits:** 4 executions instead of 2 on a resolved blind-spot row. Untestable where the program
  mishandles the machine removal: on dev this is both Claude R1 OTF programs in window 30, and the
  ignores-removed-machine program everywhere. `generic` and `program_wide` keep the blind spot.
- **Not committed.**
- **IT blind spot resolved (D25), checked by the coordinating session:**
  - `mlsys.py` sha256 e06dd8be…; both offline suites have 0 failures.
  - Test: reference 24 of 24 `task_request` rows Trusted; CPU-into-memory wrong answers Trusted fell from 5 to 0.
  - Phase 2 (all families) has started, with a deadline of Nov 10, 23:59.

## 2026-11-09: Blind spots in every family, Phase 2 (session `cpu-mem-blindspot`)

Details: `manifests/blindspots.md` (catalog and bars written before measurement, 3 attempts, review, test run).
`manifests/it_blindspot.md` is kept unchanged for Phase 1.
- **Catalog:** 35 planted confusions across 16 families: wrong visit, activity, wait, decision, case, product,
  task, job or machine; wrong size (added instead of set, 1 - draw, half, inverse); wrong place in time. MR-idle
  turned out equivalent to removal, so it is not a confusion.
- **Method, all families:** today's method runs unchanged. Where it would permit, exact stated-rule checks run:
  - workflow: task ends from work and working hours, wait ends from delays, case paths from printed draws,
    worker names and unused workers, every other case ends, and the request's own change;
  - manufacturing: dispatch completeness;
  - IT: a fill witness.
  A failed check gives Caught, under its own registry key. Rows today's method declines are unchanged
  (0 of 9,992 dev rows; 0 on test).
- **Library:** `probes.py`, `policy.py`, `mlsys.py` (sha256 42a86e31, 619052b9, cfb85128); pre-change copies in
  the session scratchpad. Tests: `phase2_tests` in both offline suites, plus two test lookups made by name; 0 failures.
- **Dev:** reference never Caught. 18 confusions go from wrong answers Trusted to 0, e.g. TD-add 94, AD-add 80,
  TD-wait 36, CS-both 20, TR-add 14.
  - Unresolved: RA-pool 10, RA-count 14, TP-add 5.
  - Fallback costs measured, not applied: RA residue 88 of 184 reference Trusted rows lost for 24 wrong answers
    removed; TP-add 60 of 60 lost for 5.
- **Review (separate agent):** 3 confirmed issues fixed (an unprinted-path crash Caught as a correct program;
  exact failures under today's registry key; dispatch check on declined rows), plus 4 lower ones.
- **Test (one run):**
  - soundness: 0 blockers and 0 rejections; every directed term and reason unchanged
    (`manifests/probe_soundness_workflow_test_v2.json`, `manifests/probe_soundness_mlsys_v4_test.json`);
  - planted confusions on the test questions: same pattern as dev; unresolved remain RA-pool 12, RA-count 6,
    TP-add 5;
  - cost: workflow directed executions 644 -> 882.
- **Decisions for Ashraf:** the Untestable fallback for the RA residue and for TP-add.
- **Not committed.**

## 2026-11-10: After the PC restart, the coordinating session's check of phase 2 (blind spots, all families)

- **Nothing was lost.** Every linked session had finished before the restart.
- **Library hashes match the frozen phase 2 code:** probes 42a86e31, policy 619052b9, mlsys cfb85128.
- **Both offline suites:** 0 failures.
- **Every question and blind-review hash file passes `sha256sum -c`.**
- **Phase 2 accepted.**
  - Today's method runs first and unchanged. Exact stated-rule checks are added where it would permit.
  - On test:
    - 0 reference rejections;
    - every directed term and reason is unchanged;
    - planted wrong answers Trusted fall to 0 for every confusion except RA-pool, RA-count and TP-add.
  - Cost: workflow directed executions 644 → 882 on test.
- **Limit to report:** the exact checks do not apply to OTF's free-form records, so OTF programs get no gain from phase 2.
- **Open for Ashraf:** the Untestable fallback for the RA residue and for TP-add.
  - Measured on dev: the RA residue loses 88 of 184 reference Trusted rows to remove 24 wrong answers; TP-add loses 60 of 60 to remove 5.
- **Ashraf (2026-11-10): keep both unresolved blind spots as reported limits.** These are the RA residue (pool and count on used workers' unavailability) and TP-add. The Untestable fallbacks are not applied. The library stays frozen at phase 2 (probes 42a86e31, policy 619052b9, mlsys cfb85128).

## 2026-11-10: Third platform, the plain coding agent: generator, offline tests, Haiku smoke on Loan

Decision 1 in `baseline_judges_design.md`. In the paper it is called "a plain coding agent", never "ReCode". Nothing is committed.

**What was built (Verified):**
- **Generator:** `scripts/coding_agent_build.py` (version coding-agent-0.2, sha256 24d4acac…).
  - One model gets the domain's `adapters/generic_tasks/<Domain>/spec.md` and writes `run.py`.
  - The program is run on the spec's `example_input.json`. The model then sees the raw output only: exit code, wall time, the first 40 and last 15 lines of stdout, and the last 3,000 characters of stderr.
  - It may revise, up to 3 replies in all, or reply DONE.
  - There is no checker, reference, expected output, format count or test document. The last program written is the build's program.
- **Disclosed scaffolding:**
  - The system prompt says the program runs on Python 3.10, with no network and no file writes.
  - The example run uses no options.
  - After the build, a run with `--horizon` (the way the adapters call programs) is made for the record only and never shown to the model.
- **Settings:**
  - 3 replies; output cap 32,000 tokens per reply, passed as `Client(..., max_output=)`; 60 s per run.
  - The shared client's empty-reply retries (2) are kept, the same as for the other builds.
- **Calls and spending stop:** calls go through the `scripts/b0_build_test.py` client. The ledger is `runs/build_test_coding_agent/calls_<setup>.jsonl`, which the shared Claude cap counts.
  - Before each call, the generator also checks the shared spend plus that call's worst-case cost against the cap, and against `--max-usd`.
  - A stop for the cap, a service failure or a harness error writes `stopped.json` and is retried on rerun. Earlier attempts are kept in `attempt_<n>/`.
- **Outputs:** `runs/coding_agent/<setup>/<Domain>/b<k>/` holds `run.py`, `prompt_log.jsonl` (every message in full; the client keeps no thinking text), `example_runs.jsonl`, the full isolation outputs and `build.json`.
  - `build.json` records tokens, cost, hashes of the code and inputs, the setup's settings, the SDK version and the git head.
  - The WSL copy is at `/home/aashraf/trust2027/coding_agent/<setup>/<Domain>/b<k>/run.py`. It is byte-identical to the Windows copy; both hashes are recorded.
- **Adapter:** `assurance.backends.DEVSBackend` and `assurance.mlsys.DEVSDomain` run that folder unchanged. No change to `assurance/` was needed.
- **Replay script:** `scripts/coding_agent_replay.py` runs the history check through `ProbeRunner.replay` on the dev maps the pilot runners use.

**Builder isolation (Verified):**
- The model has no tools. It sees only the prompt log.
- Its code runs only under bwrap with `--tmpfs /mnt --tmpfs /home --unshare-net --clearenv`. Its own folder is read-only.
- `check_builder_isolation.py` results:
  - positive control (35 of 35) outside the sandbox before every build;
  - 0 findings inside the same sandbox, before and after the build.
- **Added probe:** it lists everything under `/home` that the sandbox can see. It caught a sibling build folder planted as a negative control. The check script's own list does not cover sibling builds or the DEVS-Gen code.
- **Spec files:** none of the four workflow spec files names a test title or contains a test draw (separate reviewer).
- **After the builds:**
  - `patterns`, unchanged;
  - `wsl_scan_workflow_programs.sh`, unchanged, 13 programs with 0 hits;
  - `splits`: 0 violations; `workflow_splits_v1.json` unchanged;
  - a grep of both coding-agent programs: 0 names, 0 draws.

**Tests and review (Verified):**
- `scripts/test_coding_agent_offline.py --wsl`: 52 checks, 0 failures. These are a fake model, a local runner and one fake build through the real WSL sandbox.
- A separate-agent review found no isolation leak and listed these issues, all fixed:
  - newline translation into WSL, so the WSL copy differed from the recorded hash;
  - a cut-off revision ended the build;
  - fragile fence parsing;
  - cap and service stops were recorded as finished builds;
  - lost logs after a crash;
  - too little margin under the cap;
  - unbounded output;
  - derived counts shown to the model;
  - no `--horizon` run;
  - missing provenance fields.
- Found later: `wsl.exe` expands `${PIPESTATUS}` in an outer shell. Exit codes now use `pipefail`; this was rechecked with exit 3, exit 124 and a timeout.

**Smoke, Haiku 5.5, Loan (Verified):**

| build | output cap in force | model replies (calls) | built | example run | `--horizon` run | dev replay (Run 01–04) | cost | wall time |
|---|---|---|---|---|---|---|---|---|
| `claude-haiku-5-5/WorkflowLoan/b1` | 32,000 | 2 (2): program, DONE | yes | exit 0, 372 lines | exit 0 | **4 of 4 pass**, all case ends match | $0.0160 | 133 s |
| `_smoke_cap16k/claude-haiku-5-5/WorkflowLoan/b1` (labelled extra, outside the matrix) | 16,384 | 3 (7) | yes | exit 0, 372 lines | exit 0 | 3 of 4; Run 04: 5 of 15 case ends differ | $0.0587 | 526 s |

- **Why the second build exists:** `b0_build_test.py` was edited by the caching session at 14:17, during the first build. That build ran with the client's 16,384 cap.
  - Both of its first two replies ran out of output budget while still thinking, with no text. The client's empty-reply retries made those 6 of its 7 calls.
  - It was moved out of the matrix path, and its `build.json` records the move. The generator now refuses to build unless the client reports the requested cap.
- **Total smoke spend:** $0.075 of the $2 allowed.
- **The build matrix has not started.** It waits for the coordinating session's go-ahead: Haiku and Sonnet only, or all five models, and 2 or 3 builds per domain.

## 2026-11-10: Main runner and scorer; dev rescore on the frozen library

- **New `scripts/main_runner.py`:** every domain, question set (wf_dev, wf_test, wf_policy, ml_dev, ml_test) and platform; outputs in `runs/main_v1/<set>/`.
  - Reuses the pilot's tested pieces; `pilot_runner.py` itself is unchanged.
  - The system sees only question text and the document map.
  - MLSys maps keep only the chapters of the set's own split, so dev runs hold no test records. The policy set counts as test.
  - Reading comparators see the front matter plus the interpreted chapter, the same view the judges get. This replaces the pilot's whole-document view, which would cross 100k tokens on MLSys documents.
  - `--registry-from` carries evidence between sets (Study C).
  - `scripts/main_shard.py` runs program shards in parallel.
- **New `scripts/main_summary.py`,** derived from `pilot_summary.py`, which is unchanged:
  - results per process and cohort, never pooled;
  - typed comparison;
  - rule A explicit.
- **Dry run** (oracle only, no model calls) on two programs: the pipeline works end to end.
  - Loan Sonnet b2, directed: coverage 0.792, precision 1.000 (native: 0.868 / 0.913).
  - IT Sonnet b1: correct on all 60, directed coverage 0.733. The declines are justified: the program prints unmatched task starts under machine removal; 3 are Untestable failure removals.
- **Dev rescore in progress:**
  - wf_dev reuses the pilot's 112 interpretations (raw replies, so identical requests);
  - ml_dev interpreted fresh with Haiku: 108 calls, $0.02;
  - 20 parallel shards, native path on.
- **Separate-agent review** of both scripts is running.
- **Runner review (separate agent), fixes applied:**
  - the summary no longer crashes on program-failure rows, and lists failures;
  - native paths are scored on every OTF interpreted row, with a missing answer counting as none, and `--no-native` rows are flagged and excluded;
  - missing interpretations and backend failures now write explicit declined rows instead of silently shrinking n;
  - coding-agent cohorts are named by model;
  - OTF programs come from accepted builds on all four documents, so B0-on-Claude builds are picked up;
  - `--registry-from` is recorded in a sidecar and checked on resume;
  - real executions are recorded again;
  - interpretation is scored from the stored requests (interpreted vs oracle);
  - reading results are reported per process.
- **Phase 2's exact checks recorded as D26.**
- **Disclosed, not changed:**
  - the MLSys front matter's chapter-list line still names other-split chapter titles (titles only, never records);
  - the policy variants' fingerprints differ from test, so test-to-policy carry-over cannot match a key; that is the design (P is a real change, H is the measured unnecessary invalidation);
  - the main-run reading prompt and view differ from the pilot's.
- **Leakage, split filtering and pilot parity** were confirmed by the reviewer: decisions are identical except where D24 applies.
- **Ashraf approved the main-run cuts (D27, 2026-11-10).**
  - Ollama models on OTF only.
  - Coding agent: Haiku and Sonnet, 2 builds per domain.
  - Judges on stratified subsets: Haiku answer-level about 3,000 rows, Haiku ReAct about 1,000, program-level on all programs, Sonnet answer-level on 150, no Sonnet ReAct.
  - Policy set on Claude programs only.
  - Code freeze at the end of Nov 11.
- **Coding-agent smoke:** one Haiku Loan build for $0.016, which passes replay on all 4 dev runs.
- **Builds started (2026-11-10, D27):**
  - Coding agent: 16 builds, Haiku and Sonnet, 2 per domain (coding-agent session).
  - DEVS-Gen `Manufacturing` and `ITOperations`: 12 builds, Haiku and Sonnet, 3 per task, with builder isolation (domain-readiness session).
  - B0 on Claude: Haiku and Sonnet, 3 builds per dev document on all four documents, run by the coordinating session into `runs/build_test_b0_claude/`. B0 is pinned, unpatched and native-only.
  - The Claude ledger stood at $7.56 under the $25 stop before these.

## 2026-11-10: DEVS-Gen Manufacturing and ITOperations builds (D27): isolation ready, builds not run

- **Builder isolation for DEVS-Gen, set up and verified** (`scripts/wsl_devs_gen_isolated_generate.sh`, `scripts/allow_one_host_proxy.py`, launcher `scripts/devs_gen_mlsys_build.py`).
  - **Sandbox:** bubblewrap with `--tmpfs /mnt --tmpfs /home` and `--clearenv`. Read-only binds of the DEVS-Gen code and venv; `benchmark/`, `generated/` and `results/` are emptied and only the task folder is bound back. DEVS-Gen's own `devs_app/persistent_storage`, which holds the earlier workflow builds' agent logs, is replaced by an empty writable folder per build. The workspace is mounted at a neutral path, `~/ws`.
  - **Network:** `--unshare-net`, with one way out, a Unix-socket proxy that honours only `CONNECT api.anthropic.com:443`, logged.
  - **`scripts/check_builder_isolation.py` extended** with the MLSys test material (test questions' hash file, splits, test-side soundness, blind-review keys and scores, gold and generator code, test documents) and with the other DEVS-Gen tasks and release outputs. Positive control: 45 of 45 visible.
  - **Inside the build sandbox:**
    - one finding, the documented model-API key (name only);
    - the proxy returns 403 for github.com and raw.githubusercontent.com and 200 for api.anthropic.com;
    - direct network is blocked;
    - /home shows only the code, the Python home, the workspace and the stage folder;
    - the persistent-storage folder is empty.
- **First launch:** 4 attempts failed in 3–5 s before any model call, because DEVS-Gen writes agent logs into its code tree, which the sandbox mounted read-only (OSError 30). No tokens were used, so spend is $0.
  - The 4 index lines were removed from `runs/devs_gen/generation_index.jsonl` and recorded in `runs/devs_gen/mlsys_build_log.jsonl`. The workspaces were deleted, and the sandbox fixed.
  - The launcher now stops at the first failure that happens before any model call. (Correction, later on 2026-11-10: this stop had not actually been applied to `scripts/devs_gen_mlsys_build.py` when this line was written. It was added during the hardening below.)
- **Relaunch blocked:** the permission system refused the relaunch as a paid action. No build has run. It needs the user's go-ahead.

## 2026-11-10: DEVS-Gen build sandbox hardened against the /run escape (before any MLSys build)

All checks below ran with a dummy key value and no paid model call. No build has run in any form, and $0 is spent.

- **Verified finding: the DEVS-Gen build sandbox above was escapable.** It used the `--ro-bind / / --tmpfs /mnt --tmpfs /home --unshare-net` form that the judges session's reviewer escaped (shared note `sandbox_escape_finding.md`). Inside it, the extended check found 42 findings:
  - `/run` and `/var/run` visible, with 34 Unix sockets, including the user session bus `/run/user/1000/bus` and the WSL interop sockets;
  - `systemd-run --user` over that bus started a process outside the sandbox (exit 0);
  - the host PID namespace (pid 1 is systemd): a detached background child kept running after the sandbox exited;
  - a reachable controlling terminal; and, when launched from a terminal, an inherited descriptor (fd 7 → `/dev/ptmx`);
  - AF_VSOCK sockets can be created; `--unshare-net` does not cover vsock, which reaches the Windows host;
  - the old check had reported only the API-key name.
- **Hardened launcher** (`scripts/wsl_devs_gen_isolated_generate.sh`): the form of `bwrap()` in `scripts/judges.py`, plus what a build needs:
  - **Process start:**
    - a Python closer closes descriptors above 2 and gives bubblewrap its whole environment;
    - the key is copied by name from the launcher's environment, so it is never on a command line (review 1: it had been visible in `/proc/*/cmdline`);
    - stdin is `/dev/null`;
    - `timeout -k 30` bounds the sandbox to the build timeout plus 10 minutes.
  - **Mounts:**
    - `/usr` read-only with the linker files;
    - the only `/etc` files are TLS roots, `passwd`, `group`, `nsswitch.conf`, `localtime` and `alternatives`, plus a `hosts` file of our own. None of these is secret;
    - `/usr/lib/wsl` is covered, and there is no `/run`, `/var` or `/mnt`;
    - an empty `/home` with the same binds as before: DEVS-Gen code and venv read-only, one task, the workspace at `~/ws`, an empty log folder, and the stage folder read-only except its socket folder.
  - **Isolation:**
    - `--unshare-all` (user, PID, IPC, UTS, cgroup and network namespaces), with `--hostname sandbox`, `--new-session` and `--die-with-parent`;
    - a seccomp filter (`scripts/make_seccomp_filter_builder.py`, new). It allows socket families unix, inet, inet6 and netlink, which the build needs for its loopback proxy, and refuses all others, vsock included. It also refuses `io_uring_setup`, `io_uring_enter` and `io_uring_register`. Other architectures and the x32 ABI are killed.
  - **Proxy** (`scripts/allow_one_host_proxy.py`):
    - it dies with the launcher (`PR_SET_PDEATHSIG`, and a trap on a normal exit);
    - it logs bytes per tunnel;
    - each mode has its own log, so a build's counts hold only its own traffic.
  - **litellm's tokenizer:** `TIKTOKEN_CACHE_DIR` now points at litellm's bundled tokenizers. The new smoke test found that litellm fetched `cl100k_base` from openaipublic.blob.core.windows.net, which the proxy refuses, so every isolated build would have failed. The bundled file matches tiktoken's expected sha256 (`223921b7…`).
  - **Check mode:** every line from the harness carries a fresh nonce, and the /home tree is printed as JSON. Workspace file names therefore cannot pose as harness lines.
  - **After a build:** the build's files are searched for the key, and the result is a count only.
  - **Smoke mode (new, no paid call):** checks the release starts, the writable places, TLS, a litellm call made with the literal key "invalid" (sync and async), and leftover processes.
- **`scripts/check_builder_isolation.py` extended (WSL):**
  - `/run` and `/var/run` are on the hidden list.
  - **New probes:**
    - Unix sockets anywhere in the tree, except one named with `--allow-socket`;
    - `systemd-run --user` through every `/run/user/*/bus`;
    - the host PID namespace;
    - inherited descriptors above 2; a terminal on descriptors 0–2; a reachable `/dev/tty`;
    - the network by IP as well as by name;
    - AF_VSOCK socket creation;
    - an io_uring `IORING_OP_SOCKET` that creates an AF_VSOCK socket without `socket()`.
  - `--nonce` prints one JSON summary line.
  - With `--expect-visible`, these probes must fire outside the sandbox, or the positive control fails.
- **`scripts/devs_gen_mlsys_build.py`:**
  - **Check parsing:** `judge_check` trusts only nonce lines, and any parse error fails the check. The post-check no longer requires an empty log folder, which a real build fills (review 1).
  - **Program folder:** `program_dir` refuses any folder name that is not plain, and paths are shell-quoted. Review 1 had shown injection: a builder-chosen folder name ran a command outside the sandbox with `/mnt/c` visible.
  - **Token log:** it is read with `O_NOFOLLOW|O_NONBLOCK`, as a regular file only, with a size cap. A missing log while the proxy carried traffic is charged at twice the largest cost so far, so the cap still holds.
  - **Replay:** it runs only if the isolation check, run inside the library's own program sandbox (`assurance.backends.sandbox_command`), reports 0 findings. Otherwise it is deferred and recorded, and `devs_gen_mlsys_build.py replay` runs it later (review 1: replay had run built programs in the old, escapable library form).
  - **Stopping:** the loop stops on a post-check failure, on the key found in files, and on a failure before any model call. That last stop had been recorded earlier but was missing from the script.
- **Results:**
  - **Positive control, outside:** 45 of 45 project paths visible, and every escape probe fires. That includes a real `systemd-run --user` start, the host PID namespace, vsock, and an io_uring-created vsock socket.
  - **Old form, inside:** 42 findings. `judge_check` fails it.
  - **Hardened form, inside:**
    - 62 paths checked, 1 finding (`CREDENTIAL VARIABLE ANTHROPIC_API_KEY`, documented and allowed);
    - the proxy returns 403 for github.com and raw.githubusercontent.com and 200 for api.anthropic.com; direct network is blocked;
    - the log folder is empty, and /home shows only the expected tree;
    - `judge_check` passes in both the pre and post phases.
    - A forged summary line without the nonce is ignored, and a second nonce summary fails the check.
  - **Smoke, hardened:**
    - `--help` exits 0; the user is `aashraf`, and the host is `sandbox`;
    - the workspace, log folder, `/tmp` and `/dev/shm` are writable;
    - TLS gives HTTP 404, and litellm sync and async give `AuthenticationError 401` for the invalid key;
    - the proxy refused nothing; 0 processes were left running, while the same child under the old form stayed running.
  - **Injection test:** a folder named `a';echo INJECTED;'` holding a `run.py` is refused, and a plain `devs_project` folder is accepted.
- **Verified finding for the library and judges sandboxes (not changed here; other owners):**
  - The unix-only seccomp filter (`scripts/make_seccomp_filter.py`), used by `assurance.backends.sandbox_command` and `scripts/judges.py` `bwrap`, is bypassed through io_uring: inside both sandboxes, `IORING_OP_SOCKET` created an AF_VSOCK socket. This WSL kernel is 6.18.33.2 with `io_uring_disabled = 0`.
  - The fix is to refuse `io_uring_setup`, `io_uring_enter` and `io_uring_register`, as the builder filter does.
  - Until then:
    - the extended check reports 1 finding in both sandboxes;
    - `scripts/test_judges_offline.py`, which expects ", 0 findings", will fail;
    - this script defers replay.
- **Also not changed:** `scripts/coding_agent_build.py` and the form printed in `manifests/builder_isolation.md` still use the old form, so the extended check now refuses that pipeline's builds.
- **Known limit:** code the builder writes runs during the build with the key in its environment. It could make API calls that the release's call log does not show; the proxy's connection and byte counts are recorded beside the log as a check. Only a provider-side spend limit on a dedicated key would make the $8 cap enforceable. That is Ashraf's decision.
- **Reviews:** review 1 (separate agent) found 15 items; all in this session's files were fixed. The rest belong to other owners and are listed above.
  - **Review 2 confirmed:** it decoded the 21-instruction filter and every jump is correct. Inside the sandbox, vsock, packet and io_uring are refused, inet, inet6, netlink and unix work, x32 is killed, and fd 10 is not leaked.
  - **Review 2 found 8 defects, all fixed:**
    - **Blocker:** `TIKTOKEN_CACHE_DIR` was flagged as a credential, because its name contains TOKEN, so every pre-check would have failed. It is now an allowed finding: a folder path, not a secret. The launcher refuses to start if litellm's bundled tokenizer is missing.
    - **Replay:** it no longer runs, now or deferred, after a failed post-check or when the key was found.
    - **Proxy counts:** they come from the parsed log, so a denied request whose text is "allowed" is no longer counted as allowed.
    - **Key search:** it now looks inside `.gz` files (test: found in a gzip, 0 for a non-matching key, links not followed).
    - **Byte counts:** the launcher waits 2 s before stopping the proxy, so open tunnels' counts are logged.
    - **/home allowlist:** prefixes are matched on whole path components.
    - **Token log:** reading is capped at 512 MB decompressed and 1 MB per line, and negative counts are clamped to 0.
    - **Proxy socket:** the proxy removes a planted dangling link at its socket path.
  - **Also fixed from review 2:** the release's `.git` (which holds the release's `generated/` tree and results) is now covered with a tmpfs.
- **Final record (same day, all files as they now stand):**
  - **Positive control:** 45 of 45 visible; escape probes fire.
  - **Hardened check:** 2 findings, both allowed: `ANTHROPIC_API_KEY` and `TIKTOKEN_CACHE_DIR`. The proxy returns 403/403/200, direct network is blocked, the log folder is empty, and `.git` is empty. `judge_check` passes pre and post.
  - **Smoke:** as above, with litellm sync and async returning 401 and 0 processes left.
  - Probe folders are removed, and no proxy is left running.
- **Builds run before the filter:** none. No DEVS-Gen Manufacturing or ITOperations build has run in any form.
- **Library io_uring fix confirmed (same day):** the shared filter `seccomp_unix_only.bpf` (sha256 `fc5e2ee5c92ecd8c…`) now refuses io_uring. Run inside `assurance.backends.sandbox_command`, the isolation check gives 62 paths checked and 0 findings, so the build script's replay gate passes. Replay will run right after each build, not deferred.

## 2026-11-10: DEVS-Gen Manufacturing and ITOperations builds (D27): 12 of 12 run, $2.72

Approved by Ashraf in this session ("Yes, run the builds"). Command: `scripts/devs_gen_mlsys_build.py` with an $8 cap, in the hardened sandbox above. Settings: `--max-output-tokens 64000`, timeout 3600, the provider hook. Index: 12 lines in `runs/devs_gen/generation_index.jsonl`, with the same fields as the workflow builds. Details: `runs/devs_gen/mlsys_build_log.jsonl`, `runs/devs_gen/mlsys_replay_v1.jsonl` and `runs/devs_gen/mlsys_build_console.log`. Nothing was selected by result; failed builds are kept.

| Model | Task | Run | Exit | Program | Seconds | Prompt / completion tokens | USD | History check (dev) |
|---|---|---|---|---|---|---|---|---|
| Haiku 5.5 | Manufacturing | 01 | 0 | yes | 74 | 100,805 / 15,881 | 0.0180 | 12 / 12 |
| Haiku 5.5 | ITOperations | 01 | 1 | no | 36 | 70,714 / 6,753 | 0.0104 | build failed |
| Haiku 5.5 | Manufacturing | 02 | 0 | yes | 74 | 99,542 / 16,217 | 0.0181 | 12 / 12 |
| Haiku 5.5 | ITOperations | 02 | 0 | yes | 158 | 110,463 / 35,717 | 0.0289 | 16 / 16 |
| Haiku 5.5 | Manufacturing | 03 | 0 | yes | 93 | 147,247 / 19,014 | 0.0242 | 0 / 12 |
| Haiku 5.5 | ITOperations | 03 | 0 | yes | 158 | 109,608 / 35,054 | 0.0285 | 16 / 16 |
| Sonnet 5.5 | Manufacturing | 01 | 0 | yes | 82 | 84,221 / 11,404 | 0.2825 | 12 / 12 |
| Sonnet 5.5 | ITOperations | 01 | 0 | yes | 138 | 139,033 / 21,942 | 0.4975 | 15 / 16 |
| Sonnet 5.5 | Manufacturing | 02 | 0 | yes | 109 | 111,974 / 20,614 | 0.4301 | 12 / 12 |
| Sonnet 5.5 | ITOperations | 02 | 0 | yes | 152 | 127,107 / 25,518 | 0.5094 | 16 / 16 |
| Sonnet 5.5 | Manufacturing | 03 | 0 | yes | 89 | 109,700 / 15,850 | 0.3779 | 12 / 12 |
| Sonnet 5.5 | ITOperations | 03 | 0 | yes | 154 | 124,017 / 24,895 | 0.4970 | 5 / 16 |

- **Totals:**
  - 11 of 12 builds produced a program;
  - 8 programs pass the history check on every dev chapter or window, and 3 fail it on some or all;
  - estimated spend $2.72 (the release's call log, priced at the runner's list prices).
- **Every build:**
  - pre-check and post-check passed: only the two allowed variables;
  - the proxy refused nothing, with 1–3 tunnels to api.anthropic.com per build and their bytes logged;
  - the key was found in no file;
  - no test chapter or window names appear in any program;
  - replay ran right after the build, through `assurance.mlsys.DEVSDomain`. Its sandbox passed the isolation check with 0 findings after the library's io_uring fix.
- **Failures, with their causes** (all natural, none from the sandbox):
  - **Haiku ITOperations 01, failed build.** The model wrapped its plan as `{"content": {"detailed_plan": …}}`. DEVS-Gen's pydantic check (`_RawCoupledResponse`: `detailed_plan` required) rejected it three times, so "All root detailed-plan drafts failed". The unsandboxed Haiku WorkflowLoan run_04 failed with the same error, and the same validation error appears in all 7 earlier Haiku workflow builds. No sandbox error appears in the logs. Diagnosis recorded in the build log.
  - **Haiku Manufacturing 03: Failed history check on 12 of 12 chapters.** Every ledger cell differs. The program runs, but its values are systematically wrong.
  - **Sonnet ITOperations 01: Failed history check on 1 of 16 windows** (window 30, 26 task-log events differ).
  - **Sonnet ITOperations 03: crashes on 11 of 16 windows** (`TypeError: ClusterScheduler.deltcon() missing 1 required positional argument: 'e'`). xdevs calls `deltcon()` with no argument, so the program fails whenever an internal and an external event coincide.
- **Harness problems during the run** (each caught by a fail-closed gate; no model call was made, nothing was built, and each is logged as a `restart` event):
  1. The API probe in the pre-check timed out after 10 s, because connecting from WSL to api.anthropic.com took about 11 s (IPv6 first). The probe now waits 60 s and records a failure as a line; the proxy tries IPv4 first.
  2. The pre-check ran before the "already built" skip, and the finished run's log folder rightly failed it. Already-built runs are now skipped before the pre-check.

  The cap was lowered to $7.98 on restart to cover the $0.018 already spent.
- **Not done here:** the probe-soundness and main runs on these programs belong to the coordinator's runner.

## 2026-11-10: Coding-agent build matrix (D27): 16 of 16 built, 16 of 16 replay on dev

Run by `scripts/coding_agent_matrix.py` (new). It builds one program at a time with the unchanged generator (`coding_agent_build.py`, sha256 24d4acac…; every `build.json` records this hash). Haiku 5.5 and Sonnet 5.5, 2 builds per domain, four domains. The Haiku Loan smoke is b1: it was made with the same generator. Nothing is committed.

**Results (Verified):**

| model | domain | build | replies (calls) | output tokens | cost | build time | dev replay |
|---|---|---|---|---|---|---|---|
| Haiku | Loan | b1, b2 | 2 (2), 2 (2) | 29.6k, 29.8k | $0.0160, $0.0173 | 133 s, 132 s | 4/4, 4/4 |
| Haiku | Pharmacy | b1, b2 | 2 (2), 2 (2) | 24.8k, 24.6k | $0.0142, $0.0133 | 115 s, 108 s | 4/4, 4/4 |
| Haiku | Manufacturing | b1, b2 | 2 (2), 2 (2) | 4.5k, 4.3k | $0.0032, $0.0028 | 23 s, 21 s | 4/4, 4/4 |
| Haiku | IT operations | b1, b2 | 2 (2), 2 (2) | 16.8k, 19.7k | $0.0095, $0.0105 | 79 s, 92 s | 4/4, 4/4 |
| Sonnet | Loan | b1, b2 | 2 (2), 2 (2) | 6.3k, 6.3k | $0.1061, $0.0842 | 52 s, 51 s | 4/4, 4/4 |
| Sonnet | Pharmacy | b1, b2 | 2 (2), 2 (2) | 5.8k, 5.6k | $0.0916, $0.0745 | 46 s, 44 s | 4/4, 4/4 |
| Sonnet | Manufacturing | b1, b2 | 2 (2), 2 (2) | 1.7k, 1.7k | $0.0371, $0.0310 | 15 s, 15 s | 4/4, 4/4 |
| Sonnet | IT operations | b1, b2 | 2 (2), 2 (2) | 4.4k, 4.5k | $0.0629, $0.0567 | 34 s, 34 s | 4/4, 4/4 |

- **Every build:**
  - wrote a program on its first reply, and that program ran the example with exit 0;
  - answered DONE on its second reply, so no build revised its program;
  - ran with exit 0 under `--horizon` (the record-only run).
- **Failed builds:** 0, and no build was selected. The labelled 16k-cap smoke (outside the matrix) fails Run 04, so the history check does tell programs apart.
- **Replay** runs through the adapters unchanged: `DEVSBackend` with `ProbeRunner.replay` for workflow, and `DEVSDomain` with `mlsys.ProbeRunner.replay` for manufacturing and IT. Each domain has 4 dev runs. The result for each build is in `replay_dev.json`.
- **Spend:** $0.631 for the matrix, of the $8 allowed. The shared Claude ledger had $7.57 of the runner's $25 stop before the matrix. The matrix gave each build `--max-usd` set to the budget left. No stop was hit.
- **Runner index:** `runs/coding_agent/index.jsonl` lists 16 programs, one per built program, in the format `scripts/main_runner.py` reads (`model`, `name` = `<Task>/b<k>`, `process`, `dir`, `task`). The 16k smoke is not listed.

**Builder isolation, every build (Verified, in each `build.json` and its `isolation_*.txt`):**
- Positive control: 35 of 35.
- `check_builder_isolation.py` inside the sandbox: 0 findings before and after.
- `/home` probe: 0 entries outside the program folder, the interpreter and the check.
- The WSL `run.py` is byte-identical to the recorded one.
- The workflow pattern scan of each build folder finds 0 test names and 0 test draws.

**After the matrix (Verified):**
- `patterns`: unchanged.
- A grep of every coding-agent WSL program: 0 names and 0 draws in all 17 (16 plus the smoke).
- `wsl_scan_workflow_programs.sh`: 15 DEVS-Gen programs, 0 hits.
- `splits`: 0 violations. It rewrote `manifests/workflow_splits_v1.json`, whose counts changed because other sessions added programs since the earlier run: maps 58 → 65, OTF programs 48 → 54, DEVS-Gen programs 13 → 15, plus the new scan hash.
- **For the DEVS-Gen owner:** the two new DEVS-Gen folders, `haiku/Manufacturing/run_01` and `sonnet/ITOperations/run_01`, have the same file hash, `abcfa6a9d4df344d`. They are probably empty or still being built.

**To report in the paper:**
- **Every build passes on dev.** All 16 coding-agent programs reproduce the dev records exactly. On dev, this platform shows no history-check failures for the gate to catch. Its wrong answers, if any, would come from intervention handling, which the replay does not test.
- **Haiku uses far more output tokens than Sonnet,** mostly thinking: about 25k against 6k for Loan.
- **The example input is published.** The model ran its program on the spec's published example input but never saw any recorded output.

## 2026-11-10: LLM-based trust-judge baselines built and smoke-run on dev (session `judges`)

Implements `manifests/baseline_judges_design.md` (D22) and the subsets of D27. **Development only: nothing here is evidence, and nothing was run on test.** Nothing is committed.

**Files.**
- `scripts/judges.py` (new): the answer-level LLM judge, the program-level LLM judge and the raw ReAct judge; what each judge sees; the WSL sandbox; the D27 subset draw; `smoke`, `draw`, `run` and `summary` stages.
- `scripts/b0_build_test.py` (changed client): text blocks with their own cache breakpoints; `prompt_chars` counts characters for block content; stop sequences; an output cap per client (`MAX_OUTPUT_PER_QUESTION = 64000`, builds stay at 16,384); `auto_cache` switch; `Ledger.spent` skips a half-written line. The Claude stop is unchanged at $25. Default (build) requests are byte-for-byte what they were, on the Claude, Ollama and OpenRouter paths (tested).
- `scripts/test_judges_offline.py` (new): 188 checks, 0 failures, including real WSL sandbox runs. `scripts/test_assurance_offline.py` and `scripts/test_coding_agent_offline.py` still report 0 failures.
- Hashes at hand-over: `judges.py` 9b921654…, `b0_build_test.py` a6fc7458…, `test_judges_offline.py` 38c0f8f7…. Prompt version `judges-v2`, prompt hash `ed45fe10bab7c96c` (stored in every judgment row).

**What a judge sees** (built only by `make_view`, from explicit arguments):
- the document's front matter plus the one chapter the interpreted request names;
- the program's own code: OTF the `code` field only; DEVS-Gen `devs_project/**/*.py`; coding agent `run.py` only;
- the question text and the main runner's interpreted request (`runs/main_v1/<set>/interpret.jsonl`), so it is the request the gate gets;
- answer level and ReAct: the scored structured answer from `runs/main_v1/<set>/programs/*.jsonl` (computed by the same adapter call where that row does not exist yet), and the program's own factual answer;
- never gold, bindings, labels, the reference, other programs, other chapters, native verdicts or build history. Rows with no answer are not judged (rule A) and cost nothing.

**Additions beyond the design text (to disclose in the paper).**
- A short note on how the platform runs the program, for OTF as well as the stdin platforms, including one sentence on how a what-if change is applied.
- In the ReAct sandbox: a launcher `program/otf_run.py` (scope and map only) with the OTF runtime package, which includes the code of OTF's own check; the run's input object `document/input.json` for stdin programs; DEVS-Gen's launcher `run.py`; a line saying how many turns are used.
- Rule on the last turn: a verdict given together with a code action stands; an action alone is out of turns.
- A verdict that disagrees with its own probability (TRUST below 50, DECLINE above 50) is kept as given and flagged `inconsistent`.

**Reviews (two rounds, separate agents).**
- Round 1 found one blocker and 11 lower items; all applied. **Blocker: the bubblewrap form `--ro-bind / / --tmpfs /mnt --tmpfs /home --unshare-net` can be escaped.** `/run` stays visible, and code inside reached the session bus and started a process outside with `systemd-run --user`; that process saw `~/trust2027/gen`, `/mnt/c` and the network (verified by the reviewer). There was also no PID namespace.
- Round 2 confirmed the fix and found two more gaps, both fixed: an inherited terminal file descriptor was open inside; the harness files were writable by the code under test.
- The judges' sandbox now mounts only `/usr`, three linker files, the interpreter and the row's folder; unshares every namespace; closes inherited descriptors; keeps the harness on a read-only mount. Tested: no `/run`, `/var`, `/mnt`; `systemd-run` fails; no network; no leftover process; no open descriptor above 2.
- **Open, not mine to change:** the same weak form is still in `assurance/backends.py`, `assurance/mlsys.py`, `scripts/coding_agent_build.py` and `manifests/builder_isolation.md`, and `scripts/check_builder_isolation.py` reports 0 findings on it because it never probes `/run`. Details: shared note `sandbox_escape_finding.md`. Needs a decision by the coordinating session and Ashraf.

**Checks without a model.**
- Each program's factual run inside the judge sandbox equals the platform's run outside it: 35 of 35 Claude-built OTF and DEVS-Gen dev programs and 16 of 16 coding-agent programs (the sandbox uses Python 3.10 and the one-chapter document). The same check runs per program and chapter before every ReAct row and is recorded (`sandbox_parity*.jsonl`).
- OTF programs on the one-chapter view against the full document: 184 of 192 program-and-chapter pairs identical, 0 differ, 8 where the full-document run itself fails (48 programs, all builder models).

**Dev smoke (`runs/judges_smoke_v1/`, summary in `manifests/judges_smoke_v1.json`).** 20 answered rows drawn round-robin over 12 strata (Claude-built OTF and DEVS-Gen, four processes); 29 rows were drawn to get 20 with an answer. Seed 20261110.

| Judge, model | Rows | Cost per row (mean; median; max) | Turns | Output tokens per row | Seconds per row | Verdicts | Failures |
|---|---|---|---|---|---|---|---|
| Answer, Haiku | 20 | $0.0053; $0.0046; $0.0149 | 1 | 5,720 | 26 | 18 TRUST, 2 DECLINE | 0 (1 inconsistent) |
| Program, Haiku | 20 | $0.0063; $0.0060; $0.0104 | 1 | 7,700 | 37 | 17 TRUST, 3 DECLINE | 0 |
| ReAct, Haiku | 20 | $0.0052; $0.0041; $0.0201 | mean 1.85; 12 rows used 1, 5 used 2, 1 each used 3, 5 and 7 | 4,490 | 23 | 20 TRUST | 0; none hit the cap |
| Answer, Sonnet | 6 | $0.077; range $0.034 to $0.120 | 1 | 1,720 | 14 | 6 TRUST | 0 |

- ReAct: 0.85 sandbox calls and 0.75 counted program executions per row; 12 of 20 rows gave a verdict without running anything, which the design allows. Sandbox time is under 1 second per call.
- Caching in the smoke was weak by construction (20 scattered rows): 70% of prompt tokens were cache writes. Reads appeared wherever rows shared a document view.
- Verdicts were not scored against gold here. The scorer does that.
- A second small run (`runs/judges_devcheck_v1/`) exercised the main-run path on dev: a frozen draw of 12, 6 and 3 rows, each judge from the frozen file, the program-level judge on every chapter for one program, and two shards.
- **Spend:** smoke $0.80, path check $0.11, total $0.91 of the $3 allowed. Ledger `runs/build_test_judges/`, inside the shared Claude stop.

**D27 subsets.** `judges.py draw <root> <sets> --subsets FILE` reads the answered rows of `runs/main_v1/<set>/programs/*.jsonl`, draws 3,000 rows for the Haiku answer judge, 1,000 of those for ReAct and 150 of those for Sonnet (seed 20261110, row ids only, stratified by process, cohort and family), and writes the ids with their sha256 plus a sidecar hash and time. A later draw that differs is refused. Every judgment records the subset name and the file's hash. Not drawn yet: the test rows do not exist.

**Cost projection for D27** (from the smoke; 20 rows per judge and 6 for Sonnet, so rough):

| Run | Rows | At the smoke's rate | Expected with shared caching |
|---|---|---|---|
| Haiku answer | 3,000 | $16 | about $12 |
| Haiku ReAct | 1,000 | $5 | $4 to $8 (depends on turns used) |
| Haiku program, every program and chapter | about 1,800 | $11 | about $9 |
| Sonnet answer | 150 | $11.5 | about $10.5 |
| Total | | about $44 | about $37 (range $32 to $47) |

- **The program-level count is about 1,800, not the design's 140.** Counted today: 1,444 program-and-chapter pairs on the three test sets with the 75 programs that exist, the 16 coding-agent programs included (344 workflow test, 172 policy, 928 manufacturing and IT). The DEVS-Gen manufacturing and IT programs still to be built would add about 350.
- **Time.** One process would need about 50 hours for these subsets. `--shard K/N` splits the rows by document chapter over N processes with separate output files and one shared spending limit; 8 shards bring the answer and program judges to about 3 hours each.

**Limits and follow-ups.**
- The `run` loop (draw, resume, spending stop, shards) has no offline test; it was exercised by the two dev runs.
- Program executions are counted from a log written inside the sandbox: a lower bound, and not tamper-proof.
- `SETUPS` prices Sonnet cache reads at $0.20 per million; the API reference lists $0.10. This overcounts slightly and was left unchanged.
- `scripts/main_runner.py` builds its per-question client at the 16k cap; pass `max_output=bt.MAX_OUTPUT_PER_QUESTION` there if the 64k cap is wanted for interpretation and reading.
- The $25 Claude stop will not cover D27 (ledger at $12.44 now); the coordinating session raises it, as D27 says.

## 2026-11-10: Dev rescore on the frozen library (main runner; dev only, not evidence)

`runs/main_v1/{wf_dev,ml_dev}`; summaries in `runs/main_v1/*_summary.{json,txt}`. 4,197 workflow rows (the pilot's count) and 2,880 MLSys rows, interpreted and oracle sources, with the native path.

**Interpretation:** 112 of 112 exact on workflow; 106 of 108 on MLSys.

**Workflow, OTF Claude, interpreted structured path, directed gate vs native** (coverage, precision):

| Cohort | Directed | Native |
|---|---|---|
| Loan Haiku | 0.799 / 1.000 | 0.868 / 0.920 |
| Loan Sonnet | 0.685 / 0.945 | 0.868 / 0.819 |
| Pharmacy Haiku | 0.735 / 1.000 | 0.898 / 0.855 |
| Pharmacy Sonnet | 0.746 / 1.000 | 0.898 / 0.868 |

DEVS-Gen workflow: directed equals replay in precision, so its gain comes from the history check alone.

**IT, OTF Claude:** the programs are correct on every dev question (native precision 1.000), so the gate only costs coverage. Directed coverage: Haiku 0.500, Sonnet 0.733. Every decline is a right answer. Causes:
- the history check fails on some windows;
- machine removal is Caught in window 15 or 30 and then Already caught everywhere (47 rows);
- Untestable failure removal (15);
- the blind-spot split is unusable because machine removal is broken (10).

**Manufacturing, OTF Claude:** directed equals native, with no errors and no loss.

**Ollama OTF:** most programs fail the history check. Gemma IT directed is 0.094 / 1.000 against native 0.333 / 0.933.
- **B0 on Claude built (2026-11-10, D22/D27):** pinned, unpatched B0 code; only the model connection is replaced, as in D13.
  - Haiku: 10 of 12 accepted (one manufacturing and one IT build rejected).
  - Sonnet: 12 of 12 accepted.
  - List-price cost $3.40 ($0.43 Haiku, $2.97 Sonnet), in `runs/build_test_b0_claude/`.
  - `main_runner.programs_list` picks these up as native-only B0 programs; they were not part of the dev rescore.
- **Ashraf (2026-11-10): IT's Already caught blocking is kept as designed (D20).** A program caught on a capability is not trusted on it anywhere. The IT coverage cost on correct-looking programs (47 dev rows) is reported, not tuned away.
- **Coding-agent matrix done:** 16 of 16 built, all 16 replay their domain's 4 dev runs exactly, for $0.63. Index at `runs/coding_agent/index.jsonl`.

## 2026-11-10: Program sandbox hardened (review finding from the judges session)

- **The finding.** The judges' reviewer showed the library's bubblewrap form (`--ro-bind / / --tmpfs /mnt --tmpfs /home --unshare-net`) could be escaped. With `/run` visible, code reached the user session bus and `systemd-run --user` started a process outside the sandbox. That process saw `/mnt/c` (reference code and gold) and the network.
- **The fix.** `assurance/backends.py` now has `sandbox_command`, used by `DEVSBackend` and `mlsys.DEVSDomain`. It uses the judges' reviewed form:
  - only `/usr`, the linker files, the interpreter and the program's own read-only folder are mounted;
  - every namespace is unshared;
  - a new session and an empty environment;
  - inherited descriptors are closed.
  Pre-fix copies are in the coordinating session's scratchpad.
- **Checks:**
  - 27 of 27 stdin programs (11 DEVS-Gen workflow, 16 coding agent) give byte-identical output on dev under the old and new forms;
  - an in-sandbox probe finds no `/run`, no `/mnt/c`, `systemd-run` failing, no network, and the sandbox as PID 1;
  - both offline suites: 0 failures;
  - a separate-agent review is running.
- **Disclosure.**
  - Earlier runs used the old form: the pilot, the dev rescore, the coding-agent builds' example runs, and the DEVS-Gen workflow builds' smoke runs.
  - A scan of every generated program in `~/trust2027/gen` and `~/trust2027/coding_agent` finds no code that reaches outside. The only match is DEVS-Gen's fixed release launcher `run.py`, two identical variants, which uses `subprocess` to start its own simulator.
  - The DEVS-Gen Manufacturing and IT build sandbox was hardened by the domain-readiness session before any build.
- **Main runner:** per-question calls now use the 64k output cap (`MAX_OUTPUT_PER_QUESTION`).
- **Second sandbox review, fixed (2026-11-10).**
  - **The finding.** `--unshare-net` does not block AF_VSOCK on the WSL2 kernel. From inside the sandbox, a program connected to the Windows host (CID 2), and port 50002 answered a 9P handshake (the protocol serving `/mnt/c`). Reading files was not proven, but this is treated as an escape.
  - **The fix.**
    - A seccomp filter (`scripts/make_seccomp_filter.py`, installed at `$HOME/trust2027/tools/seccomp_unix_only.bpf`, sha256 2a9e46b1…) refuses socket() and socketpair() for every family except AF_UNIX, and kills non-x86_64 and x32 calls.
    - `sandbox_command` loads it with `--seccomp`. It fails closed: no filter file means no run.
    - Soft limits: address space 8 GiB, 4,096 processes, file size 4 GiB.
    - The program folder is shell-quoted.
  - **Verified.**
    - vsock, inet, inet6 and netlink sockets give EPERM, while AF_UNIX works.
    - 27 of 27 programs give byte-identical output.
    - Both offline suites: 0 failures.
  - **Also sent:** the same fix to the judges session (its `bwrap()`) and the domain-readiness session (the DEVS-Gen build sandbox).
  - **Noted by the reviewer:** the WSL VM shut down about 30 s after its first vsock probe; idle shutdown is the likely cause, but it is not confirmed.

## 2026-11-10: The judges' sandbox gets the socket filter; io_uring still gets past it (session `judges`)

Follow-up to the vsock finding in the library sandbox. No model calls; nothing committed; nothing run on test.

**Changed.**
- `scripts/judges.py` `bwrap()`: loads the shared seccomp filter `$HOME/trust2027/tools/seccomp_unix_only.bpf` (the file `assurance.backends.sandbox_command` uses) on descriptor 10 with `--seccomp 10`; sets the soft limits `ulimit -S -v 8388608 -u 4096 -f 4194304`; refuses a folder or command that would need shell quoting. Without the filter file no sandbox is created and the command exits 97.
- `scripts/test_judges_offline.py`: 7 new checks (195 in all).

**Verified in the judge sandbox.**
- Before the change a vsock socket could be created inside (my connect attempts to CID 2 timed out; I did not reproduce the 9P handshake).
- After it: vsock (stream, datagram, socketpair), inet, inet6, netlink and packet sockets give EPERM; AF_UNIX sockets and socket pairs work; a call through the x32 numbering is killed; the three soft limits are set; no descriptor above 2 is open inside.
- Sandbox parity under the filter: 51 of 51 Claude-built dev programs give the platform's records (12 + 12 OTF, 11 DEVS-Gen, 16 coding agent).
- `test_assurance_offline.py` and `test_coding_agent_offline.py`: 0 failures.

**Failed: 1 of 195 checks.** `scripts/check_builder_isolation.py` (its 17:15 version, with an io_uring probe), run inside the judge sandbox, reports "IO_URING created an AF_VSOCK socket without socket()". The filter covers `socket()` and `socketpair()` only; `io_uring_setup` succeeds inside, so a vsock socket to the Windows host can still be opened. The library sandbox reads the same filter and has the same gap.

**Proposal, tested in the judge sandbox only.** A candidate filter that also refuses `io_uring_setup`, `io_uring_enter` and `io_uring_register` (425 to 427) with EPERM: the isolation checker then reports 0 findings, and asyncio, a multiprocessing pool and a stdin program still run. The shared filter and `scripts/make_seccomp_filter.py` belong to the coordinating session and were not edited. The 16 instructions are in the shared note `io_uring_bypass_finding.md`. Once the shared filter is rebuilt, `judges.py` needs no change; rerun `scripts/test_judges_offline.py`.

**Hashes.** `judges.py` ab971e9d…, `test_judges_offline.py` 57217389…. The prompt hash is unchanged (`ed45fe10bab7c96c`).
- **io_uring gap closed (2026-11-10).** The judges' and builder sandbox checks found that io_uring can create a vsock socket without calling socket(). The shared filter now refuses `io_uring_setup`, `io_uring_enter` and `io_uring_register` with EPERM: 18 instructions, sha256 fc5e2ee5…
  - Verified in the library sandbox: `io_uring_setup` gives EPERM; vsock, inet, inet6 and netlink give EPERM; AF_UNIX works; 27 of 27 programs give byte-identical output; offline suites 0 failures.
  - The DEVS-Gen builder sandbox has its own filter. It also refuses io_uring, and allows AF_INET for its in-sandbox loopback forwarder (no outside network: the network namespace is unshared). No DEVS-Gen build had run before or after the filter.

## 2026-11-10: Judges' sandbox rechecked against the rebuilt socket filter: 195 of 195 checks pass (session `judges`)

Closes the failed check in "The judges' sandbox gets the socket filter; io_uring still gets past it". No model calls; nothing committed; nothing run on test. `scripts/judges.py` and `scripts/test_judges_offline.py` are unchanged since that entry (ab971e9d…, 57217389…).

- **Filter:** `$HOME/trust2027/tools/seccomp_unix_only.bpf`, rebuilt by the coordinating session at 17:22 CST, 18 instructions, sha256 `fc5e2ee5…`. It now also refuses `io_uring_setup`, `io_uring_enter` and `io_uring_register` with EPERM.
- **Judges offline suite:** 195 checks, 0 failures, 0 skipped. `scripts/check_builder_isolation.py` inside the judge sandbox reports 0 findings; `io_uring_setup` gives EPERM; a vsock socket gives EPERM.
- **Sandbox parity under the rebuilt filter:** 51 of 51 Claude-built dev programs give the platform's records (24 OTF, 11 DEVS-Gen, 16 coding agent).
- **Other suites:** `test_assurance_offline.py` and `test_coding_agent_offline.py`, 0 failures.
- **Limit:** the checks cover the escape routes found so far (session bus, inherited descriptors, vsock, io_uring). They do not show that no other route exists.

## 2026-11-10: Last sanity check before the freeze

- **Dev pass on the 49 new programs** (16 coding agent, 11 DEVS-Gen manufacturing/IT, 22 B0 on Claude): no program failures. wf_dev now has 5,765 rows (60 programs) and ml_dev 5,460 rows (58).
  - Coding agent: directed precision is 1.000 everywhere, with coverage 0.93–1.00 and no errors to catch.
  - DEVS-Gen manufacturing/IT: no errors; directed coverage 0.62–0.96.
- **Found: B0 native answers on IT were empty.** The pinned B0 reader leaves the records' `src` empty, so the IT projection learned no record kinds.
  - **Fix in `assurance/mlsys.py` `kind_map`:** an IT-only fallback, used only when the learned map is empty, that maps a kind to an event only if its name is exactly the event or `task_<event>`.
  - **Programs affected:** 8 of 21 OTF IT programs, 7 B0 and 1 R1 Qwen. Every other map is unchanged. Pre-change copy is in the coordinating session's scratchpad.
  - The affected programs' dev rows were moved to `runs/main_v1/ml_dev/superseded_kindmap/` and rerun. A separate-agent review is running.
- **Checks:**
  - all four offline suites: 0 failures;
  - every question and blind-review hash file passes;
  - coverage: workflow test 0 of 240, policy 0 of 91, MLSys 324 of 324 pass;
  - the WSL seccomp filter is sha256 fc5e2ee5…
- **Hash refresh:** two hash entries in `manifests/workflow_questions_test_v1.sha256` (`workflow_splits_v1.json` and `runs/workflow_test_v1/devs_gen_scan.txt`) were refreshed. Both were deliberately regenerated after the new builds, with 0 violations; the questions are unchanged. The old hash file is in the scratchpad.
- **Kind-map fix, final form (after a separate-agent review).**
  - **Corrected cause:** the pinned B0 reader does not leave `src` empty. It writes 2-element `[node, row]` sources, which the map skipped.
  - **The fix:** the name-based fallback is replaced by grounded voting. IT accepts `[node, row]` sources. Every task-log event votes, including submit, so a kind that points at rows of two events is ambiguous and unmapped. Only kinds whose single event is in `EVENTS` are mapped.
  - **Effect on dev, 21 OTF IT programs × 4 chapters:**
    - the same 8 programs gain grounded maps, identical to the fallback's (7 B0, 1 R1 Qwen, whose native numbers change);
    - `otf/r1_claude/claude-haiku-5-5/itops_dev/b3` loses a wrong mapping (`wait_to_first_start` → start; its rows mix submit and start), and its dev rows were rerun;
    - nothing else changes.
  - **Tests:** 4 new `kindmap_tests` in `scripts/test_assurance_mlsys_offline.py`; both suites 0 failures.
  - **B0 IT native path on dev** (coverage / precision; with the binding check in brackets):
    - Claude Haiku 0.60 / 0.85 (0.49 / 0.90);
    - Claude Sonnet 0.60 / 0.83 (0.48 / 0.90);
    - gpt-oss 0.36 / 0.35;
    - Gemma 0.43 / 0.73.
- **Haiku IT b3 rerun with the corrected map.** IT Haiku cohort, dev: replay coverage 0.661 → 0.994, directed 0.500 → 0.744, precision unchanged at 1.000. Much of the earlier IT coverage cost was this adapter bug, not the gate.
- **FREEZE (D28):** `manifests/freeze_v1.md` and `manifests/freeze_v1.json` (sha256 3f270c5a…): 30 files and 118 programs. The main run is handed to a fresh session.
- **D29 (Ashraf, 2026-11-10):** gpt-oss, Gemma (cloud) and Qwen (local) judge the shared 150-row subset with the answer-level and ReAct judges. This is a logged addition after the freeze, with no code or program change. Estimated about $18 of Ollama credit; Qwen is free but slow.
- **D29 addition (Ashraf, 2026-11-10):** a Sonnet ReAct judge on 50 of the shared 150 rows (fixed-seed draw by row id), about $15. The projected Claude total becomes about $83 of $100.

## 2026-11-10: Main (test) run: freeze verified; post-freeze change 1, the Claude stop

- **Freeze verified before any test call.** `scripts/make_freeze_record.py` into a scratch file: 30 of 30 file hashes and the 118-program list (names and sorted-name hash) equal `manifests/freeze_v1.json` (sha256 3f270c5a…). WSL filter `$HOME/trust2027/tools/seccomp_unix_only.bpf` is sha256 fc5e2ee5c92ecd8c…, as recorded.
- **Offline suites:** `test_assurance_offline.py`, `test_assurance_mlsys_offline.py`, `test_judges_offline.py` (0 skipped) and `test_coding_agent_offline.py`: 0 failures each.
- **Ledger before the main run:** Claude $13.84 on the runner ledgers (`runs/build_test_*/calls_claude*.jsonl`; the handoff's $12.63 predates later dev calls), plus about $7.80 of DEVS-Gen builds the ledger does not see, so about $21.6 in all. Ollama ledger $1.91 (+ $0.03 earlier spend).
- **Post-freeze change 1 (instructed by Ashraf, D27 and D29):** `scripts/b0_build_test.py` `CLAUDE_CAP_USD` 25.00 → 80.00. One line; reverting it gives back the frozen hash a6fc7458… exactly. New hash 24dac3c8b811a0f7…. No behaviour changes except where the runner stops. The stop is on the ledger only, so with the off-ledger DEVS-Gen spend the account total can reach about $88 before it trips; Ashraf is asked before the ledger passes $80.
- **Post-freeze change 2 (Ashraf, D29):** Ashraf reported an Ollama Cloud balance of $20 or more. `scripts/b0_build_test.py` `CAP_USD` 5.00 → 21.00, so the Ollama ledger (now $1.94 with the earlier $0.03) stops at $20.75, about $18.8 of new spend, inside the balance. Reverting both cap lines gives back the frozen hash a6fc7458… exactly; the file is now sha256 f1c02b20ad0a696b…. No other line changed.
- **Judge-subset pool (Ashraf, 2026-11-10):** the frozen subsets are drawn from the answered rows of all three test sets, wf_test, wf_policy and ml_test.
- **Shared stage started** (`runs/main_v1/logs/run_shared_test.sh`): per set, interpret, then vanilla and RAG side by side (each reads only `interpret.jsonl`); the three sets in parallel. Haiku, 64k cap.

- **Program stage started** (`runs/main_v1/logs/run_programs_test.sh`): wf_test and ml_test, all 118 programs, `main_shard.py` with 12 shards per set (24 processes), each set as soon as its interpretation finished.
- **Policy set (Study C), how it is restricted (D27):** `runs/main_v1/logs/policy_programs.py` lists the 43 Claude-built workflow programs (OTF R1 and B0 with a Claude builder setup, DEVS-Gen haiku/sonnet, coding agent claude-*), each checked to be a unique `--filter` substring, in `policy_programs.txt`. `run_programs_policy.sh` runs `main_runner.py programs . wf_policy --filter <name> --registry-from wf_test` for each, 12 at a time, only after every wf_test shard has finished with no traceback, so each copied registry is final.
- **New analysis script `scripts/main_analysis.py`** (not frozen; written before any test label was read, checked on dev and synthetic data): per-cell matched coverage with expected precision over ties, two-level bootstrap with the match redone per resample, paired differences, disagreement-only, matched random refusal, natural-error terms, interpretation, Study C, agreement, cost. On dev it reproduces the frozen `main_summary.py` exactly (every interpreted/structured cell and config).
  - **Review 1 (separate agent):** the math was confirmed (matched coverage against brute force on 3,000 random cases; bootstrap structure; rule A everywhere). 15 findings, all fixed: prefixed "capability failed earlier" reasons now map to Already caught; judge runs report expected vs judged rows; per-cell judge results are emitted; disagreement is "not available" where no reading rows exist; effectful and no-effect controls are split; the matching cell includes the set; binary kappa; Study C checks (scope names disjoint, test registry present). A confirmation round is running.
- **New `scripts/draw_react50.py`:** the Sonnet ReAct 50 rows as the next level of `judges.draw_subsets` with the same seed, after checking the first three levels equal the frozen subsets file. Checked on dev (a scratch draw): deterministic, nested.
- **Ollama judge path check on dev (no test rows):** `judges.py smoke` with gpt-oss-120b, 2 rows (`runs/judges_smoke_ollama_v1/`), to confirm the Ollama client path works before the main judges. Answer-level: 2 of 2 judged, $0.007.

- **Ollama judge path check, ReAct (dev, 1 row so far):** gpt-oss-120b used 3 turns and gave no parsable action or verdict (turn 1 "Action: run_code to cat file." with no code; turn 3 empty), so it is DECLINE at confidence 0, `unparsable`, as designed. Wall time 822 s, almost all of it Ollama Cloud HTTP 500 retries (7 retried errors), not the model. The prompts are not truncated: 44k characters, about 16.4k tokens; earlier gpt-oss build calls carried 41–53k tokens. Nothing changed: the prompt is frozen, and this is reported as the judge's behaviour.
- **Analysis script, review 2 (confirmation):** original findings closed except the class-level pooling question (kept as a secondary view, per-cell results emitted). Two new bugs fixed: the completeness check now takes the union of a run's nested subset names, and the 50-row narrowing applies to the Sonnet ReAct judge by judge and model, not by folder name. The remaining `wf_policy` hardcodes now use the policy-set argument. The `--only-rows` input for the Sonnet ReAct run is a plain id list (`run_judges.sh` writes it from the draw file). Dev check: still 0 mismatches against the frozen scorer.

- **Ollama ReAct path checks on dev, final:** gpt-oss-120b 2 of 2 rows unparsable (row 2: 8 turns; in 7 the visible reply only described an action, e.g. "We need to list files.", or was empty; the one code action came mid-line on the last turn), 0 code runs, 822 s and 1,233 s per row, mostly Ollama Cloud HTTP 500 retries; $0.044. Gemma (`runs/judges_smoke_ollama_gemma_v1/`): 2 of 2 parsed verdicts in 1 turn each, no code run, 6–9 s per row, 0 retried errors, $0.007. The failure is specific to gpt-oss under the frozen ReAct format (stop sequence and plain-text transcript), and may reflect that setup more than the model.
- **Decision (Ashraf, 2026-11-10): run gpt-oss ReAct as frozen** on the 150 shared rows. Report its failure rate with this dev diagnosis, labelled as a failure of the setup with this model, not as a measure of its ability. No change to `judges.py`.

- **Shared stage, 2026-11-10:** interpret and rag completed for all three sets (wf_test 240, wf_policy 91, ml_test 216 rows each); wf_policy vanilla completed (91). Vanilla reading stopped early in wf_test (203 of 240) and ml_test (119 of 216). In both, the connection closed mid-stream (`httpx2.RemoteProtocolError: peer closed connection without sending complete message body`), and the frozen retry loop in `b0_build_test.py` does not catch that error, so the process exited. This is an infrastructure fault, not model behaviour. **Resumed** with the same unchanged command (`main_runner.py shared . <set> vanilla`). It skips questions already recorded, and the interrupted question was never written. No code change. Logs: `shared_<set>_vanilla.log` (crash) and `shared_<set>_vanilla_resume1.log`.

- **Program stage, complete (2026-11-10):** wf_test 12,360 rows (60 programs), ml_test 10,920 rows (58 programs); all 24 shards ended "done", no traceback in any shard log. **wf_policy:** 43 of 43 Claude-built programs ended `exit 0`, no traceback, 3,368 rows. The per-program structure matches wf_test: 31 gated programs give 2 rows per question (interpreted, oracle), and the 12 B0 programs are native-only (1 row, no registry), as in wf_test.
- **Judge subsets drawn before any judging (2026-11-11 04:53 UTC):** `judges.py draw . wf_test,wf_policy,ml_test` gives `manifests/judge_subsets_main_v1.json`, sha256 `236c7028ea46b7d4d910d446c0b9bb04734ecf3d07a38b4fce73a2de783c7767` (population 9,345 answered rows; answer_haiku 3,000, react_haiku 1,000, answer_sonnet 150, nested, seed 20261110). `draw_react50.py` gives `manifests/judge_subsets_main_v1_react_sonnet50.json`, sha256 `f9714d5ca7f01aa1d4f43a749bf9572d0c47c8915cbeb827fb19585f73dc2418` (50 of the 150, next nested level, same seed; the first three levels were checked to equal the frozen file). The draw reads only program rows. Vanilla reading was still resuming and does not enter the draw.
- **Spend before judges:** Claude ledger $25.36 of $80, Ollama ledger $1.97 (+ $0.03 earlier) of $21. Local Qwen blobs: all 8 match their sha256 digests and sizes. Local Ollama is serving `qwen3.5:9b` on 127.0.0.1:11535.
- **Note:** the session scratch folder holding helper scripts (freeze comparison, ledger sum, dev cross-check) was cleared by temp cleanup. No result depends on those files; the checks they made are recorded in entries above.

- **Ollama Cloud judges (2026-11-11):** answer-level gpt-oss-120b 150 of 150 and Gemma 150 of 150; ReAct Gemma 150 of 150; no traceback. **gpt-oss ReAct stopped after 19 of 150 rows.** Ollama Cloud returned HTTP 500 seven times in a row, and `b0_build_test.InfrastructureFailure` ended the process. Infrastructure failures are not recorded as judge verdicts by design; the run is resumable. **Resumed** with the same unchanged command (log `judges/main_react_gptoss150_s0of1_resume1.log`). At the stop, 8 of the 19 rows were `unparsable` (DECLINE at confidence 0) and the mean was 326 s per row, as seen on dev (entries 4–5). wf_test vanilla reading finished (240 of 240, exit 0); ml_test vanilla is still resuming.

- **Judge resumes (2026-11-11), same unchanged commands, no code change:**
  - gpt-oss ReAct stopped again on Ollama Cloud HTTP 500 after 10 more rows (29 of 150). `runs/main_v1/logs/resume_gptoss_react.sh` resumes it repeatedly. It stops when all 150 are judged, when two resumes in a row add no row, or when the run's spend limit is reached. Logs are `judges/main_react_gptoss150_s0of1_resume<i>.log`.
  - Haiku answer-level shard 0 of 6 stopped after 104 rows on the same dropped-stream error as the vanilla reading (`httpx2.RemoteProtocolError`). Resumed; log `judges/main_answer_haiku_s0of6_resume1.log`.
  - Claude ledger at this point: $53.57 of $80. ReAct Haiku (1,000), the Haiku repeat (150) and Sonnet answer-level (150) are complete.

- **PC restart (2026-11-11, about 04:20 CST).** All running jobs stopped: ml_test vanilla (214 of 216), Haiku answer-level shard 0 (2,852 of 3,000 in total), Qwen answer-level (110 of 150), gpt-oss ReAct (56 of 150), and local Ollama. Checks after the restart:
  - All 680 JSONL outputs and ledgers read cleanly. The one exception, line 3814 of `runs/build_test_main_claude/calls_claude-haiku-5-5.jsonl`, is a fragment written at 01:05 UTC during the dev run, before the restart: two writers overlapped. `Ledger.spent()` skips unreadable lines, so the ledger undercounts by about one Haiku call (under $0.01). Left as is.
  - The WSL sandbox filter sha256 is still `fc5e2ee5…`.
  - The Qwen model is served again from the verified blobs.
- **Resumed** with `runs/main_v1/logs/resume_after_restart.sh`: the same frozen commands, each skipping rows already written. Two log-only fixes: the gpt-oss resume loop now continues its log numbering instead of overwriting earlier logs, and the earlier Qwen logs were copied to `*_part1.log` before `run_judges.sh qwen` rewrote them. No code that produces results changed.

- **New `scripts/report_tables.py` (not frozen):** it formats `main_analysis.json` into Markdown tables. The only new computation is the expected number of wrong answers for a judge at the gate's coverage, k = round(n x coverage), then k x (1 - precision), shown as a whole number.
  - **Review 1 (separate agent):** 76 of 77 spot-checked cells matched the JSON. It found 6 bugs, all fixed: the random-refusal column in the yield table was empty; four crashes on edge cases (interpretation with no parsed request, groups with no answered rows, a missing config in the cost table, no policy set); and the rule judges on the shared rows were never rendered. It also fixed labels and hard-coded group lists.
  - **Review 2 (confirmation):** 79 of 79 cells match, every JSON group is rendered, and all 8 synthetic edge cases render. The last two points (whole-number expected counts, docstring) are fixed.
  - The frozen scorer `main_summary.py` ran on all three sets (`runs/main_v1/{wf_test,wf_policy,ml_test}_summary.json`), exit 0.
- **Correction to a chat report:** the Sonnet ReAct judge (50 rows) cost $3.19 (the sum of row costs), not $8.62.
