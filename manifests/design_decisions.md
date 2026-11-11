# Design decision log

Status labels: **Decided** (made or confirmed), **Proposed** (awaiting evidence or Ashraf), **Open**.

## D1. Role of OTF-Tools: Decided (Ashraf, 2026-11-04)

This is not a build-on-OTF-Tools project. The system under test may be redesigned freely if the research question can be answered. The pinned clone exists only as baseline B0 in an isolated comparison, as `AGENTS.md` requires. Nothing else needs preserving, and the redesigned system does not have to keep its interface.

## D2. Overlap and dual submission: Owned by Ashraf (2026-11-04)

Not an agent decision. No chair contact.

## D3. Paper identity: Decided (Ashraf, 2026-11-04)

`otf-tools.pdf` is treated as the original `main.pdf`.

## D4. Dependencies: Decided (Ashraf, 2026-11-04)

The agent installs what is needed, in project-local environments, and records versions in the manifest.

## D5. Workflow reference engine: Decided (Ashraf, 2026-11-04)

Use our own deterministic reference engine for workflow gold answers. Prosimos stays a factual comparison, not the counterfactual oracle; comparisons can check selected factual behavior but cannot establish equivalence or validate what-if answers. The paper describes the benchmark as deterministic realizations of published workflow models under explicitly documented semantics.

Conditions set by Ashraf:

1. Semantics are written before either the engine or the checker: resource allocation, calendars, priorities, simultaneous events, timers, routing and loops.
2. Exogenous randomness is fixed by stable identity: case, activity or gateway, visit number and variable. Adding or removing a case preserves other cases' draws. Any dependence of duration on the assigned resource is explicit.
3. Distribution changes do not freeze outcomes. A routing-probability change keeps the underlying draw and applies the new probability.
4. The checker is independently implemented from the spec and I/O formats, without engine code or generated gold outputs. This reduces implementation coupling but does not remove shared misunderstandings.
5. Hand-worked cases are a minimum check: one per family, plus resource contention, simultaneous events, a loop and a valid no-effect intervention. One case may cover several conditions.

Evidence behind the decision, verified in Prosimos 2.1.0:

- All draws for durations, routing, timers and arrivals come from process-wide random streams, in execution order. Task duration is drawn when the task runs.
- `run_simulation` accepts fixed arrival times, but has no input for per-case durations or routing outcomes.
- One event-gateway tie-break uses `secrets.choice`, which seeding cannot control.
- A shared seed repeats a run exactly, but adding one case changed earlier cases' routes (see the manifest).

Rejected alternative: patching Prosimos to read a table. The patched copy is no longer the published simulator and would need redistributing, and neither PyPI nor the GitHub page shows a license.

## D6. Candidate processes and families: Proposed; Ashraf finds the two processes sensible, lock after confirming queues and distinct families

Four distinct synthetic structures exist. Timer variants are not counted as separate processes.

| Process | Tasks | XOR / AND | Loops | Pool sizes | Durations |
|---|---|---|---|---|---|
| Insurance_Claims | 7 | 3 / 2 | no | 100, 30 | exponential |
| Loan_Application | 17 | 7 / 4 | yes | 20, 3, 2, 4, 9, 9 | exponential, 1 fixed |
| Pharmacy | 12 | 12 / 0 | yes | 1, 8, 1 | exponential, normal, fixed |
| Procure_to_Pay | 24 | 7 / 0 | yes | 9, 1, 8, 1, 2 | all fixed |

Choice, tentative until the freeze: Loan_Application and Pharmacy, in their `_3_timers` versions. Those match the base models in every parameter except timers, and they contain the timer events the timer family needs. The `_5_timers_after` variants have no JSON parameter file.

Checks on the reference engine (see the manifest):

- **Queues:** Loan_Application has large queues, led by the Appraiser pool. Pharmacy's are short: about 1 working minute at the Pharmacist and almost none at Technician.
- **Families:** resource availability, activity duration, timer delay and routing probability all change outcomes in both processes. Case set works too, as a fifth family or as coupling evidence only.
- **Weak spot:** in Pharmacy, the single-resource interventions tried changed 13 to 51 of 120 case end times, with a mean cycle change of about 1 minute or less. Those questions need case-level or short-window outcomes, because averages would barely move.

Procure_to_Pay is the alternative if Pharmacy proves too insensitive at the pilot. It queues heavily, but all its durations are fixed.

## D7. Model lineup: Tentative until the Nov 9 freeze (Ashraf, 2026-11-04). Superseded in part by D22: all five models on every platform

Replaces the earlier gpt-oss-20b, Qwen3.6-27B and Gemma-4-31B plan.

| Slot | Setup | Tag or id (checked 2026-11-04 against the public catalogues) |
|---|---|---|
| gpt-oss | Ollama cloud | `gpt-oss:120b-cloud` |
| Qwen | Local through Ollama | `qwen3.5:9b`, 6.55 GB download |
| Gemma | Ollama cloud | `gemma4:31b-cloud`, called as `gemma4:31b` on the direct API |

Free OpenRouter Gemma is dropped (Ashraf, 2026-11-05), because it was unstable: every attempt was rate-limited upstream (see the manifest). It ran no builds, so it is not compared.

Qwen stays `qwen3.5:9b` (Ashraf, 2026-11-05), after seeing the evidence: 0 of 12 accepted builds on B0 and 3 of 12 on R1. `qwen3.5:27b` is not an option, because it is very slow on this machine and no hosted alternative is available. Consequence: Qwen will contribute few programs, and likely none under B0. The paper reports that as a result, with its failed builds. Qwen cells must not be presented as equal evidence to the other two models.

Consequences:

- Saved MLSys programs become a historical audit only. Every model needs fresh builds. The audit supplies no programs to the main experiment.
- B0 stays the pinned OTF-Tools code, run on the new models. Any change needed to reach the new endpoints must be configuration or an adapter recorded outside the pinned tree.

### Gemma selection rule, written before any Gemma test (2026-11-04): closed

Ashraf chose the Ollama cloud setup directly on 2026-11-05, so this rule no longer selects anything. It is kept as a record. The single-setup requirement below still applies, and the three requirements remain things to report for the chosen setup. Against requirement 3, on the first three specifications: under B0, Gemma 31B had 1 accepted build of 9, on one specification, which is below the requirement. Under R1 it had 9 of 9, on all three. Its behavior on effective interventions is untested.

Ashraf set the three requirements and the single-setup rule. The agent proposed the numeric thresholds below, and they apply unless Ashraf changes them before testing starts.

Run both options through the same connection test and the same development build test. Use development data only: one manufacturing, one IT and one workflow specification, and the same number of independent builds per specification for both. No question-answering accuracy or test label is used.

An option passes only if all three hold:

1. **Token counts:** every successful call reports prompt and completion tokens.
2. **Three-day fit:** projected main-run wall-clock time for this model is at most 48 hours of the 72-hour window, leaving 24 hours for retries. The projection uses measured sustained throughput including busy errors and retries, and the call count from the frozen plan. Option A is also limited by its measured daily request limit from the key endpoint. Option B must be measured with `gpt-oss:120b-cloud` running at the same time, because they may share one plan.
3. **Usable programs:** at least one accepted build in at least two of the three specifications, using the same acceptance check as every other model.

Choice:

- If both pass, choose the one with more accepted builds. If tied, choose the lower wall-clock time per accepted build. If still tied, choose option B, because a plan limit that can be measured directly is less likely to change mid-run than a free tier.
- If one passes, choose it.
- If neither passes, do not relax a threshold. Bring the evidence to Ashraf.

The chosen setup is used for the entire main run. If it fails during the main run, record that as a failure and tell Ashraf. Do not switch setups silently, and do not mix them in one reported result.

## D8. Spending caps: Decided (Ashraf, 2026-11-05)

$20 for pilots and $150 overall on Ollama cloud, enforced by the runner at list prices, with the overall figure re-estimated after the pilots.

The account's credit balance was $8.73 on 2026-11-05 (Ashraf). That is below both caps, so it is the binding limit until topped up. Pilot runs stop at $8.00 of new list-price use unless Ashraf reports a new balance. The $150 main run can't proceed on this balance: before the freeze, either Ashraf adds credits or the matrix shrinks to fit, and that is his decision. Running out shows up as an account error, logged as an infrastructure failure, not a model failure.

The earlier $50 and $500 proposal was withdrawn because it rested on the old Qwen cost. Tokens and latency are the main shared cost measure across models, because the setups have different billing (plan, free tier, local hardware). Dollars are reported where they exist.

The D7 and D11 checks are done and the cap is set, so pilots may run once their inputs are ready.

Published prices, read from ollama.com/pricing on 2026-11-04, per million tokens (input, cached input, output): `gpt-oss:120b` $0.15, $0.014, $0.60; `gemma4` $0.14, $0.05, $0.40. Ollama now bills cloud models per token, with different off-peak pricing, plus monthly credits and concurrency limits by plan: 3 concurrent requests on pay-as-you-go, 10 on Max. So gpt-oss and Gemma on Ollama share credits and a concurrency limit.

The key belongs to a free Ollama account with credits on it (Ashraf, 2026-11-04). The published page lists 3 concurrent requests on pay-as-you-go. The balance can't be read from the API, so Ashraf has to report it.

Build-test cap: $5 on Ollama cloud at list prices (Ashraf, 2026-11-04), enforced by the runner, which stops at $4.75. List-price use was $1.94, including connection tests.

Basis for the caps: R1 builds cost about $0.05 each on both cloud models. Question answering is the larger unknown. A rough figure is about $10 per 1,000 evaluations per cloud model, assuming 3 calls per question at 15k prompt tokens each, and pilots will replace that assumption. Local Qwen has no dollar cost; its limit is about 180 output tokens per second on one GPU.

## D11. Checks required before pilots (Ashraf, 2026-11-04)

1. All three model tags or endpoints exist.
2. The Gemma selection rule is written before testing (D7).
3. One connection test per model confirms token counts, reasoning settings, output limits and speed. Ollama's context length is set explicitly, and a long-document test confirms no truncation.
4. A small development-only build test: a few independent builds per model on one manufacturing, one IT and one workflow specification, recording acceptance rate, cost and time per build.

Risks tracked:

- gpt-oss and Gemma may share one Ollama plan. Its limits are not documented in anything read so far.
- Free OpenRouter is stated as 20 requests a minute and 1,000 a day with at least 10 credits purchased. The actual limit must be confirmed from the key endpoint.
- Busy errors, retries and the served provider are logged separately from model failures.

Connection-test findings that bind later work:

- The direct Ollama cloud API ignores `num_ctx`: a limit of 2048 did not truncate a 13,072-token prompt. Truncation on cloud setups must be detected from returned prompt tokens and start and end markers, not prevented by the setting.
- Local Ollama does honor `num_ctx`, and it truncates by dropping the start of the prompt. The test keeps 131072, matching the MLSys setting. Ollama's OpenAI-compatible route may not accept `num_ctx`, so B0 must set the context through the server and verify it.
- `gpt-oss:120b` cannot turn reasoning off. The lowest setting still produces reasoning, so runs must record the level used and count reasoning tokens.
- `qwen3.5:9b` has a default `presence_penalty` of 1.5, which may hurt code generation. Sampling settings must be explicit and recorded for all models.

## D12. Workflow reference validation: Established for the tested scope (2026-11-04)

Three separately derived sources agree: hand-worked cases, the reference engine and the independent checker. See the manifest for counts. Limits:

- The agent derived the hand-worked cases, and it also wrote the spec and the engine. Ashraf has not reviewed them. Shared misreadings of the spec remain possible, and agreement says nothing about whether the semantics are the right ones.
- Prosimos comparisons show similar factual aggregates only. They do not establish equivalence or validate what-if answers.
- The time-stepped checker and the sequential engine use different scheduling algorithms, but both were written from the same section 8.

Ashraf delegated the hand-check to two blind agents and will also check by hand, using `hand_check_guide.md`. Their semantic concerns are open for Ashraf to judge:

- A task can start just before closing and stay paused over a weekend, holding its worker, even if another worker is idle.
- Worker choice uses earliest start, not earliest finish.
- Timers ignore calendars, while tasks follow them.
- Added cases may arrive outside the arrival calendar.
- `count` always removes the highest-numbered workers.
- The JSON order of routes decides which cases flip when a probability changes, so case-level routing answers rest on a convention.
- Interarrival gaps are not carried across closed hours.
- Same-instant ties within a pool fall back to task id order.

## D13. B0 on the new models (2026-11-04)

B0 runs the pinned `otf` package unchanged, imported from the clone by `scripts/b0_build_test.py`, with its library off for fresh builds. The runner replaces only the model connection, using Ollama's native API so the context length and token counts are available. It keeps the pinned adapter's retry of empty replies. Sampling is explicit: output cap 16384 and context 131072, as in MLSys; gpt-oss at reasoning medium and temperature 1.0; Qwen and Gemma with thinking on, temperature 1.0, top-p 0.95 and top-k 20 or 64. Qwen's library default `presence_penalty` of 1.5 is overridden to 0, to match the MLSys sampling. No fixed seeds, because builds are meant to be independent.

## D14. Workflow document format (2026-11-04)

Layout follows the manufacturing and IT documents: front matter stating the process and rules, then one chapter per independent run. The front matter is available to every system, and is the runtime disclosure of the semantics. Plans list work, delays and route draws for visits that did not happen, because a change could make them happen. Work and delays are listed as seconds, not as underlying draws, so the runtime benchmark can use set and scale changes for durations and timers, but not changes of distribution. The reference engine still supports those. Route draws are shown to 6 decimal places, so a question must not depend on a draw within rounding distance of a threshold. Proposed for the freeze; used now for the development build test only.

## D15. Generation fixes in the redesigned path, R1 (Ashraf, 2026-11-05)

B0 stays pinned and unpatched. R1 is a separate configuration, generated from the pinned code by `scripts/make_redesign_r1.py`, with the exact changes in `redesign_r1.diff`. The acceptance check is unchanged, and the script verifies that.

Evidence for the fixes: in the B0 build test, mechanical contract failures dominated. Gemma's most common failure was a malformed record location, 18 of 27 reading attempts, with one build stuck on the same error for all tries.

R1 changes generation only:

- A `Reader` helper that makes record locations correct by construction, with a stated location rule and example.
- Reading tries raised from 3 to 5.
- Failure feedback leads with the fix for that kind of failure.
- Syntax errors and cut-off replies go back to the model without using a try. Those calls are still metered and recorded.

R1 gives no hints about process logic, names no domain, and applies to all three models identically. If a baseline also compiles programs, the same changes are available to it. Natural defects in R1 programs still count as natural.

### Keep-or-drop rule, written before R1 was run (2026-11-05)

Compare B0 and R1 at 3 builds per model per specification, on the three diagnosed specifications and on Pharmacy, which played no part in designing the fixes. No question-answering accuracy or test label is used.

Keep R1 only if all of these hold:

1. Total accepted builds across models rise by at least 4 of 36.
2. Pharmacy alone does not get worse. The three diagnosed specifications can't show this, because the fixes were designed on them.
3. Prompt and output tokens per accepted build do not rise for gpt-oss, the one model with enough B0 acceptances to compare.
4. A sample of newly accepted R1 programs still fails on some interventions. If every extra program were correct, or the extra programs were trivial, that would be reported.

Otherwise drop R1 and report that. These are small samples, so this is a screening decision and not a claim of improvement. The manufacturing, IT and Loan numbers are optimistic, because the fixes were designed on them.

Results under both systems go to Ashraf, including how the chosen Gemma setup performs against D7's usable-programs requirement.

### Decision: keep R1 for the redesigned path (2026-11-05)

All four conditions held. Details are in the manifest.

1. Accepted builds rose from 10 to 24 of 36, against a required gain of 4.
2. Pharmacy did not get worse: 3 to 5 of 9.
3. gpt-oss tokens per accepted build fell: prompt 297k to 235k, output 48k to 39k.
4. Newly accepted R1 programs still fail on interventions. For example, gpt-oss Pharmacy b3 passed acceptance at F1 0.95, but only 2 of 10 truly changed cases were exact under a duration change.

Limits: most of the gain, 7 to 19 of 27, is on the specifications the fixes were designed on, so 3 to 5 of 9 on Pharmacy is the fairer signal. Condition 4 rests on gpt-oss programs. Gemma's programs could not be changed by the mechanical mapping for duration and timer tests, so its effective-intervention behavior is untested. R1 is a keep for development. It is still subject to the freeze, and B0 is still reported.

## D16. Direction revised to a portable assurance library (Ashraf, 2026-11-06)

Ashraf's implementation handoff supersedes conflicting earlier design proposals. `AGENTS.md`, `RESEARCH_DIRECTION.md` and the pinned baseline stay unchanged. The method is a standalone Python library that decides whether a particular executable process model is suitable for a particular intervention, including after reuse. There is no new QA pipeline and no new answer model. Studies A to D and the required ablations replace the B0 to B7 matrix. Empirical benefit and novelty remain hypotheses. A null result is reported, not worked around.

Decisions accepted by Ashraf on 2026-11-06:

1. **Fixed-program cohort:** the paired assurance comparison uses R1-built programs, with native B0 kept as a separate external reference. R1 is an adaptation Category 4, a named treatment.
2. **DEVS-Gen inputs:** one generic input format for records, plans, schedules and probabilities, with no per-family hints. Disclosed as a shared task adapter (Category 2).
3. **Binding to OTF programs:** an LLM patch step, whose errors count as interpretation.
4. **DEVS-Gen scope:** workflows required, manufacturing if its spec converts cleanly, IT optional. A cross-backend claim from one domain is weaker and is reported as such.
5. **G-Sim:** capped at 3 hours and $1, then labeled by evidence.
6. **Required:** Study A, Study B analyzed offline from shared runs, a small reuse study, ablations reusing that evidence, and vanilla LLM and RAG. **Optional:** ReAct, disagreement beyond the shared reading candidate, and paraphrase volume.
7. **Credits:** Claude cohorts added because Ollama credits are short. See D18.
8. **Dates and semantics:** freeze moves to Nov 10 (later moved to Nov 11, see D23). Active-case cancellation stays out of the benchmark and is disclosed. Ashraf's hand-check and rulings on route order and paused tasks should arrive before the freeze.

Current outside facts checked on 2026-11-06: CFP dates are Nov 8 and Nov 15, 11:59 PM Pacific. DEVS-Gen release `czyarl/devs_gen_code` at `f7461b9f9d23`, Apache-2.0 with bundled GPLv3 xDEVS, Linux tools required (WSL Ubuntu-24.04 is present). G-Sim `samholt/generative-simulations` at `72b5d51a7790`, MIT.

## D17. Replay screen evidence bar, written before any program was scored (2026-11-06)

**Question:** do programs exist that replay history exactly and still answer a valid intervention wrongly? This is a development screen at no model cost. It informs the pilot and does not decide the thesis. Narrowing the claim rests on the planned pilot across both backends.

**Case C, program level:** a program whose simulation exactly matches the factual records on all 4 runs of a document, and which, on an effectful change on one of those runs, runs without a crash and gives a result that doesn't exactly match. Exact means the same kind, entities and whole-second time, scored in the program's own format.

Two weaker levels, reported separately and never merged with that one:

- **Run level:** exact factually on that run, wrong under a change on that run.
- **Case level:** a case exact factually, truly changed by the intervention according to the reference, and not exact afterward. Cases share workers, so this is not an independent count.

Crashes, unreadable documents, unmappable changes and no-effect controls are each counted apart. A wrong answer on a no-effect control is reported as its own failure.

**How changes reach a program:** a changed plan is written into the program's own document map, and the program reads it with its own reader. A pool-size change uses a program's `params` when a key names that pool, and otherwise counts as not mappable. Gold changes are supplied directly, so this tests dynamics only, as a diagnostic substitution. It says nothing about interpretation.

**Targets:** chosen by a fixed rule from the reference's factual run, without looking at any program's code, and written to `screen_targets_v1.json` before scoring. They include paths the history didn't exercise, by flipping route draws.

**Bar for reading anything into a rate:** at least 8 replay-exact programs, from at least 2 models and 2 specifications, across at least 3 families, with effectful changes and a no-effect control. Builds of one model on one specification are not independent of each other.

**Interpretation, fixed now:**

- Any confirmed case C shows the behavior exists. Inspect a sample by hand before relying on it.
- Finding none among 8 programs does not show it is rare: the true program-level rate could still be as high as about 31%, and about 14% with 20 programs.
- Below the bar, the result is insufficient. That is a sample-size problem, so build more programs (D18) before reading a rate.
- If exact programs stay rare even with more builds, strict replay leaves few programs to answer with. Report that as a finding, and compare replay at matched coverage. Rejecting nearly everything is not the same as catching failures.
- If replay catches nearly everything across the wider set, report it. Any shift of emphasis to interpretation, binding or reuse is logged as a change made after seeing data, and must still beat its own controls: schema-only checks and factual rechecks.

**DEVS-Gen release programs** are reported in a separate column and never pooled, because they have no recorded history to replay, no reference answers for their scenarios, and were built by different models. The nearest analogue is passing the native checker on its test inputs, then breaking its rules on new inputs. This catches rule violations only, not wrong values that still look valid.

These programs are development data. Nothing from this screen counts as a main result.

## D18. Claude cohorts (Ashraf, 2026-11-06)

Added for now because Ollama credits are short, using Ashraf's $100 in Anthropic credits. `claude-sonnet-5-5` and `claude-haiku-5-5` build programs; Haiku handles per-question work, so the answer path stays fixed. Claude cohorts are labeled and never pooled with Ollama models. If Ollama credits arrive after the freeze, those models form an added cohort under the same protocol, not a replacement.

Spending: first build test stops at $15 of list-price use on Claude, then re-estimated from measured tokens. Rough plan is about $50 of the $100. Sampling parameters can't be set on these models, so temperature and top-p do not match the Ollama runs. Effort is set explicitly and recorded. No server-side model fallback is used, because a refusal must not silently change the model in a cohort. Refusals are logged as their own outcome.

Disclosure: Claude models wrote the spec, engine and hand cases, and Sonnet wrote the checker and one blind check. Testing Claude-built programs against that reference could hide a shared misreading. Ashraf's hand-check matters more as a result, and this is stated in the paper's GenAI disclosure.

## D19. Post-hoc follow-up on inputs that history never varied (2026-11-06)

Written after inspecting the one program-level case C from the D17 screen, and before scoring this follow-up. That program hardcoded a task's published fixed value and ignored the plan it read, which replay cannot reveal because the value never varies in history.

**Hypothesis, formed after seeing data:** a change to an input with no variance in the recorded history is more likely to expose case C than the D17 targets.

**Targets:** for each document and run, each task with a `fix` distribution in the published model, on the first case reaching it for which the reference says a case end moves, work set to the plan value plus 600 s. Fixed by rule and hashed before scoring, in `screen_targets_v2.json`.

**Status:** exploratory development evidence, labeled post-hoc. It can motivate a probe template for the pilot. It cannot support a claim about the method, because the hypothesis came from the same programs. The pilot must test it on newly built programs, against random valid probes of equal budget.

D17 addendum (2026-11-07, after review): "effectful" means the reference moves at least one case end. A change that alters records but moves no end is excluded from every case C level and reported separately. On replay-exact programs there were 88 such changes, all exact.

## D20. Library structure and the binding check (2026-11-07)

The library `assurance/` follows the handoff's components:
- **Request and schema** (`request.py`): the schema is built from the document only.
- **Interpreter** (`interpret.py`): a model call, with untrusted output.
- **Contract validator** (`contract.py`): separate outcomes for unknown target, ambiguous binding, unsupported operation, invalid units, invalid time and unresolved meaning.
- **Capability registry** (`registry.py`): append-only, keyed to program, adapter, policy fingerprint and family, with states `failed`, `untested` and `tested_under_conditions`.
- **Probes** (`probes.py`): oracle-free, using permitted inputs only.
- **Policy** (`policy.py`): configurations `native`, `replay`, `schema`, `generic`, `directed` and `program_wide`, sharing one code path.
- **Binding check** (`binding.py`), **deterministic answers** (`answer.py`) and **backends** (`backends.py`).

**Binding check, added after the Stage 2 slice showed the need, on development data:** after the answering execution and before its answer is used, compare what the backend actually changed with the structured request. A case-level change must alter exactly one input record, for the requested case and target, holding the requested value, with no constants changed. A failed check rejects the answer even if it happens to equal gold, so an invalid patch is never rewarded.

This is Category 3, an assurance method component. It is enabled only in method configurations. As designed after one observed failure, its value must be measured in the pilot against comparators.

**Probe placement:** probes exercise the program's direct simulation of edited documents, while OTF answers come through the native patch-and-replay path. The binding check covers the gap in the patch step. The pilot must report whether native restart and replay ever differ from direct simulation on permitted changes, so that probes don't certify a path the answer doesn't use. DEVS-Gen has one path, so its probes and answers use the same execution.

D20 addendum (2026-11-07, after library review 2, before any pilot data):
- **Binding check:** it now compares records before and after, as described in the run manifest. The earlier check accepted wrong patches.
- **Reuse:** evidence is reused only on the same scope. New records or a new policy fingerprint mean probing again. This follows AGENTS.md: "recheck relevant capabilities during reuse".
- **Probe outcomes:** a probe that cannot run counts as untested, never as a pass. The directed policy declines when nothing could be tested.
- **Budget matching:** generic probes get the same number of program executions as directed probes used on the same request.
- **Changes the backend cannot express:** reported as their own outcome, separate from capability failure.

These are fixes to match the stated design, made before the pilot. None was tuned on results.

**What "reuse" means now (recorded at the reviewer's request):** reuse no longer skips probes on new records. Study C (reuse) therefore measures three things:
1. **Rechecking cost:** probe executions when a program is reused on new runs or under a changed policy.
2. **Failure carry-over:** whether a failure found on one run correctly blocks the same capability on later runs.
3. **Same-run reuse:** evidence reused for repeated questions on the same run, at zero added probe cost.

Skipping probes on new records was the bug, and it contradicts AGENTS.md. This change is not a narrowing of the claim, but Ashraf should know Study C is defined this way.

**Round 3 (re-review of the fixes):**
- A passing no-op probe alone no longer permits. At least one input-use probe must pass.
- Witnesses run before the no-op, and probing stops at the first failure.
- Generic's budget is the directed cap, never directed's actual count, so it does not drop to 0 when directed reuses evidence.
- The binding check rejects changes to top-level record attributes (such as `time`) and reordered inputs. It accepts targets named in `entities` (`activity:Name`).
- Removing the queried case is now `unsupported_operation`.
- OTF routing-probability probes return "not run" without spending an execution when the program's records have no decision events.
- Round 3 re-check: a no-op pass recorded during a decline could later permit through reuse. Only passing input-use or rule probes are reused now. Route probabilities are written in fixed-point decimal.

## D21. Record-comparison route-probability probe, form (b) (Ashraf, 2026-11-07)

**The problem.** In pilot v1, the route-probability rule probe could never run on OTF programs, because their records name no decisions. As a result, most of directed's gain on OTF Claude came from declining questions it could not check, not from detecting errors (`manifests/pilot_report.md`).

**The options.** Option (a) kept the rule and reported the gain as abstention. Option (b) added a record-comparison form. Ashraf chose (b).

**What form (b) does** (`ProbeRunner.route_change`):
- From the document's Decision log and Route draws, it takes the earliest recorded decision at the gateway whose printed draw picks a different route under the requested probabilities.
- A correct program must change that case's records, and must leave every record before that decision's time unchanged.
- It returns "not run" when the change switches no recorded decision.
- Directed uses it only when the base run has no decision events. Records that name decisions keep the rule probe, so DEVS-Gen behaves as before.

**Disclosure.** The probe was designed on development data, after seeing v1 results, and must be reported as such. It is fixed before the freeze and is not tuned on final-test labels.

**Validation:**
- `validation/probe_soundness_route_records.py`: 169 reference cases per record shape, 0 rejections.
- 6 offline checks, including an input-ignoring free-form program, which is rejected.
- The stated rule reproduces all 549 recorded routes.

**Changes after review 4:**
- Route-probability passes are never reused across requests, because the probe tests the request's own probabilities. Failures still block.
- The route rule uses exact decimals.
- **No-switch check.** When the change switches no recorded decision, the realization equals the factual run, so the program's records must not change at all. This is checked by running the program, not assumed. It decides only that request.
  - It was added after seeing that the first version declined exactly these questions, all correct no-effect controls (9 per Claude cohort).
  - Results are therefore reported with and without it (`runs/pilot_v1b/` and `runs/pilot_v1b_nocheck/`).
- Soundness: 204 of 204 reference cases pass per record shape.

**Decided (Ashraf, 2026-11-07): keep the no-switch check** in the frozen method. Report it as added after seeing v1b without it, and keep the no-check variant's numbers in the record.

**Terms (Ashraf, 2026-11-07).** In reports and the paper, declines are named for what the gate did:

| Term | Replaces |
|---|---|
| Caught | "probe failed" |
| Already caught | "blocked by an earlier failure" |
| Untestable | "no probe could run" |
| Failed history check | "replay failed" |
| Can't express | "inexpressible" |
| Trusted | "permitted" |

`scripts/pilot_attribution.py` uses these labels. Library reason strings are unchanged, so the raw rows stay readable.

**Re-scoring.** Pilot v1b (`scripts/pilot_rerun_routing_b.py`) re-decides only the directed routing_probability decisions, for OTF and DEVS-Gen, on the 112 valid questions, with fresh registries.

## D22. Platforms, trust-judge baselines and models (Ashraf, 2026-11-08 and 11-09)

After the Nov 8 meeting with Dr. Roy. The full design and its review are in `manifests/baseline_judges_design.md`, decisions 1 to 7.

**Platforms.** OTF-Tools, DEVS-Gen and a plain reason-and-code agent (named generically in the paper, not "ReCode") produce programs and answers. They are not baselines.

**Baselines are other trust judges:**
- the native check;
- an answer-level and a program-level LLM-as-a-judge;
- a raw ReAct judge: one sandbox code tool, at most 8 turns;
- history-only, generic tests and disagreement.

**Ablations of the library.** This supersedes D16.6, where ReAct was optional.

**Models:**
- All five models (Sonnet 5.5, Haiku 5.5, gpt-oss, Gemma, Qwen) build on every platform. B0 also builds with Sonnet and Haiku, and B0 stays native-only.
- Haiku judges every row. The other four models judge one shared random subset.
- Per-question work stays on Haiku.

**Claude stop** raised to $25.

**Abstract** re-registered on 2026-11-08 with these platforms, models and domains (`manifests/abstract_draft.md`).

## D23. Domains, test sets, freeze and scoring (Ashraf, 2026-11-08 and 11-09)

**Domains.** Manufacturing, IT operations, Loan and Pharmacy.
- Manufacturing and IT reuse the MLSys documents and simulators, with new questions.
- Their gold is OTF's simulator plus its re-implementation, with a sampled blind check (`manifests/domain_readiness.md`).
- This supersedes D16.4, which made manufacturing and IT optional for DEVS-Gen.

**Test programs.** Dev-built programs are reused on unseen test records, for all platforms and domains. There are no test builds.

**Sizes:**

| | Manufacturing | IT | Workflows |
|---|---|---|---|
| Dev | 48 | 60 | pilot v1, 112 valid |
| Test | 96 | 120 | 240 |

**Freeze** moved to Nov 11. Completion stays Nov 13.

**Policy fingerprint.** It drops the document's chapter list (option (a)), as `mlsys.py` already does, so dev evidence carries over to test. This is a library change made after the pilot, disclosed and reviewed.

**Policy-variant reuse.** 96 workflow questions on a real policy change (P) and a harmless rewording (H), in the workflow test-set session's files.

**Scoring rule A.** A row counts as answered only if it is trusted and an answer exists; otherwise it is Can't express. The rule is the same for every judge.

**Builder isolation.** Test material is hidden from builders during DEVS-Gen and coding-agent builds.

**Disclosure.** Probe soundness was run on test documents with the reference only, and rule A was chosen with test-side counts in view. No probe, threshold or prompt was changed because of either.

## D24. Library fixes after the full review (Ashraf approved, 2026-11-09; made after the development pilot)

A full independent review found ways for the gate to trust a wrong answer, and to reject a correct program. Every change below was made after seeing development data and the policy-variant soundness check. All are disclosed. None was made on test labels or on any system's results on test questions.

**Fixes:**

1. **Route rule, for programs whose records name decisions (DEVS-Gen).**
   - The old rule compared visit-1 decisions only, so a program that ignored a change acting on a later visit passed.
   - It now checks every recorded decision with a printed draw.
   - The earliest switched decision must appear with its new route, and nothing before it may move.
   - Every factual case end must still be recorded.
   - Every case whose path under the change is fully printed must perform exactly that path's activities (and waits, if the program prints them).
   - If no altered path is fully printed, the result is Untestable.
   - The no-switch check (D21, first made for the record form) and the near-boundary guard now also apply to the rule form.
2. **Reuse.**
   - Reused passes: input-use witnesses and case removal (a different case).
   - Never reused: route-probability and worker-change rules, which test the request's own values or interval. Before, a pass on one unavailable interval was reused for another.
   - A recorded failure still blocks.
3. **NaN and infinite values** are rejected by the contract and the parser, as `mlsys` already did.
4. **`program_wide`** is seeded by program and scope, so one program gets one verdict per scope (also in `mlsys`).
5. **Generic tests never repeat a witness** (also in `mlsys`). This makes the baseline fairer.
6. **Route-flip witnesses.**
   - The library reads the control flow the document states and walks a case's path from the printed plans and draws.
   - A flip is used only if the whole path after it is printed and at least one activity or wait changes.
   - If the flow cannot be read, no flip is used.
   - Effect: no witness removed on dev; 2 removed on the test documents (the known deep ones); 4 removed on the policy variants (the misfires).
7. The `replay` configuration's docstring now says the contract applies first.

**Evidence:**
- Offline tests: 0 failures, with new checks for each fix in `review3_tests` and `review4_tests`.
- Dev soundness: 0 rejections of the reference on the route rule (184 cases), route records (204 per shape), route flips (433) and added workers (72).
- The stated-flow walker reproduces all 480 recorded case paths on dev, test and policy documents. Path check against the reference: 2,610 paths, 0 mismatches.
- The reviewer's adversarial programs (right decisions only, truncated output, dropped case ends) are now never Trusted.
- Review: two rounds by a separate agent.

**Review 5** (the confirmation round) found two more gaps, both fixed:
- The route rule now returns Untestable, never Trusted, when the program prints no task records or the flow cannot be read. It uses task ends when no task starts are printed.
- If a program's own factual records do not list each case's path, the shape cannot be compared, and the result is Untestable rather than Caught.

**Limit to report:** after the first switched decision, the route rule checks routes, case ends and paths, but not timing. A program with the right paths and wrong times after the switch would pass this probe; only the history check and other probes bear on timing.

**Consequence:** dev pilot decisions change where these bugs applied, mainly DEVS-Gen routing-probability and resource-availability decisions. The pilot is rescored with the fixed library before the freeze.

## D25. IT CPU/memory blind spot resolved (Ashraf approved the search, 2026-11-09)

**The blind spot.** `task_request` witnesses could not tell CPU from memory when one machine was largest in both. A planted CPU-into-memory program then had 5 wrong answers Trusted on test.

**The method** (`manifests/it_blindspot.md`) is a deterministic router in `mlsys._directed`:
- Where no blind spot exists, today's method runs unchanged.
- In a blind spot, today's probes still run first. Only where they would permit does a split step run: it removes the dominating machine(s), prechecks that removal alone, then runs a discriminating witness on the remaining cluster.
- If that split step cannot resolve the case, the result is Untestable.

**How it was developed.**
- Designed and iterated on dev only: attempt 1 failed the bar and was discarded; attempt 2 was adopted.
- Reviewed by a separate agent, with fixes applied for registry isolation.
- Then run once on test.

**Results.**
- On 40,800 dev rows, with fresh and shared registries:
  - every non-blind row is identical to before;
  - the reference is Caught 0 times;
  - no Caught row is lost.
- Test: reference `task_request` stays 24 of 24 Trusted; CPU-into-memory wrong answers Trusted fall from 5 to 0.
- The Untestable fallback, also approved, was not needed.

**Credit.** DeMillo and Offutt (1991), constraint-based test data generation.

**Limits.**
- A resolved row costs 4 executions instead of 2.
- It depends on the program handling machine removal; where it doesn't, the row is Untestable.
- The generic and program-wide baselines keep the blind spot.

**Disclosure.** Made after seeing test diagnostics from planted bugs; no real system results were seen.

## D26. Blind-spot checks for every family (Ashraf approved the extension, 2026-11-09; made after the development pilot)

Details are in `manifests/blindspots.md`.

**Method.**
- Today's method runs first and is unchanged; every decline keeps its decision, reason and evidence.
- Where it would permit, exact stated-rule checks run:
  - workflow: task and wait timing, case paths from printed draws, worker names and unused workers, other cases' ends, and the request's own change;
  - manufacturing: dispatch completeness;
  - IT: a fill witness, plus the D25 split.
- A failed check gives Caught, under its own registry key.

**Development.**
- Designed on dev with a confusion catalog written before any measurement; 3 attempts were adopted.
- Reviewed by a separate agent.
- Run once on test.

**Results.**
- On test, the reference is never Caught, and every directed term and reason is unchanged.
- Planted wrong answers Trusted fall to 0 for every confusion except three: the RA residue (pool and count on used workers' unavailability) and TP-add. These are kept as reported limits (Ashraf, 2026-11-10).

**Cost.** Workflow directed executions on test rose from 644 to 882, and DEVS rows add about one execution each.

**Limits.**
- The checks need generic-format records that name tasks, waits, workers and visits.
- On OTF's free-form records they do not apply. They add Untestable-labelled evidence but change no permit.

**Disclosure.** Made after seeing test diagnostics from planted programs; no real system results were seen.

## D27. Main-run cuts (Ashraf, 2026-11-10)

Approved because the full plan was several times over the remaining credit (about $89 Claude, $8.73 Ollama) and could not finish before the freeze.

1. **Ollama models (gpt-oss, Gemma, Qwen) stay on OTF-Tools only,** where their programs already exist. No DEVS-Gen or coding-agent builds on them, and no Ollama judges. This supersedes the platform and judge parts of D22 decision 6. The abstract's "programs built by five language models" stays true through OTF-Tools.
2. **The plain coding agent builds with Haiku 5.5 and Sonnet 5.5,** 2 builds per domain on all four domains (16 programs).
3. **Judges run on stratified subsets,** with row ids drawn with a fixed seed and stratified by process, cohort and family:
   - Haiku answer-level judge on about 3,000 answered rows;
   - Haiku ReAct judge on about 1,000;
   - the program-level judge on every program;
   - Sonnet answer-level judge on a shared 150 rows, also judged by Haiku;
   - no Sonnet ReAct judge.
4. **Policy-reuse questions run on Claude-built programs only.**
5. **Timing:** code freezes at the end of Nov 11; main runs Nov 11-12; analysis and the paper Nov 12-13.

Our library and the rule-based judges run on every row (no model cost). DEVS-Gen manufacturing and IT tasks are built on Claude (Haiku and Sonnet), and B0 builds on Claude as decided in D22.

**Estimated total spend** is about $75-80 of Claude credit. The runner's Claude stop ($25) will be raised before the main run, and the raise reported.

## D28. Freeze (2026-11-10, ahead of the Nov 11 deadline)

**What is frozen.** The library, runner, scorer, judges, client, sandbox filter, question files, splits and the 118-program list, recorded in `manifests/freeze_v1.md` and `manifests/freeze_v1.json`.

**Last pre-freeze changes,** all made on dev data and all disclosed:
- **Program sandbox hardened:** `/run`, vsock and io_uring were closed by the seccomp filter, with byte-identical program output.
- **OTF IT record mapping grounded in table cells:** B0's `[node, row]` sources are now read, and ambiguous kinds stay unmapped. This gives B0 its IT native answers, and fixes one R1 Haiku program whose wrong mapping had made its history check fail.
  - Effect on IT Haiku, dev: replay coverage 0.661 → 0.994; directed 0.500 → 0.744.
- **Main runner:** the 64k per-question output cap.

**Dev results** are in `runs/main_v1/{wf_dev,ml_dev}_summary.*`: 118 programs, 11,225 rows, no program failures. They are development data, not evidence.

**Stays as decided:**
- the D27 cuts;
- rule A;
- IT Already-caught blocking;
- the two unresolved blind spots kept as reported limits.

**Open.** Ashraf topped up the Ollama credit. Under D27 the main run needs no Ollama calls, so any use of it is a new decision for him.

## D29. Ollama models as judges on the shared subset (Ashraf, 2026-11-10; a logged addition after the freeze)

Ashraf topped up the Ollama Cloud credit and chose the cheapest use of it, which restores the same models across the judges on one shared set of rows.

**What is added.** gpt-oss:120b and gemma4:31b (Ollama cloud), and qwen3.5:9b (local, free), judge the same shared 150-row subset Sonnet judges (D27). Each runs:
- the answer-level LLM judge;
- the ReAct judge.

**Coverage on the shared 150 rows:**
- answer-level judge: all five models (Haiku, Sonnet, gpt-oss, Gemma, Qwen);
- ReAct judge: Haiku and the three Ollama models on all 150 rows, plus Sonnet on 50 of them. Ashraf added the Sonnet ReAct judge on 2026-11-10, at about $15; the 50 rows are drawn from the 150 with a fixed seed, by row id only, before any judging;
- program-level judge: Haiku only (D27).

**Nothing else changes.** No new programs, no change to the library, runner, scorer or `judges.py`, which already takes any setup in `scripts/b0_build_test.py` through `--model`. The frozen files are unchanged.

**Cost, estimated from the dev smoke and Ollama prices:**
- per Ollama cloud model, about $1.40 answer-level and about $7.50 ReAct, so about $18 for both;
- Qwen costs no money but about 10 hours for ReAct on 150 rows, run one at a time.

The runner's Ollama stop (`CAP_USD`, $5) is raised to match the balance Ashraf reports, and the raise is logged.

**Caveats to report:**
- Ollama cloud offers no prompt caching through this client.
- Qwen 9B is a weak judge and thin evidence (D7).
- The Ollama models also built some of the OTF programs they judge. Report self-judging by cohort, as for Claude.

## D9. Independent checker: Decided (Ashraf, 2026-11-04)

A separately started agent writes the checker from the written spec and I/O formats alone. See D5, condition 4. Implementations are compared on small scenarios and boundary cases.

## D10. Approval at freeze: Open, needs Ashraf

Proposed: one short stop at the freeze, now Nov 11 (D23). Still open on 2026-11-09.
