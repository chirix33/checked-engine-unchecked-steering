# Run manifest

Append-only record of what was run, with which inputs. Paid model use so far, at list prices from recorded tokens (not billed amounts, and not reflecting off-peak rates or credits): **Ollama cloud $1.95** (build tests $1.92, connection tests $0.03), **Anthropic $2.87** for the first Claude build test, plus later slice calls recorded in `runs/build_test_assurance_claude/`. Corrected 2026-11-07 after independent review: this line previously said $0.03.

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
