# Development pilot v1: results (2026-11-07)

Status: **development data only**. These numbers are for deciding the freeze. They are not final results and must not be quoted as such. Nothing here was tuned on final-test labels; no final-test data exists yet.

Sources:
- As run (120 questions): `runs/pilot_v1/summary_v1.json` (from `scripts/pilot_summary.py`) and `runs/pilot_v1/attribution_v1.json` (from `scripts/pilot_attribution.py`).
- Valid set (112 questions): `summary_v1_valid112.json` and `attribution_v1_valid112.json`, made with the exclusion list `manifests/pilot_excluded_v1.json`. The list was checked by `validation/question_draw_coverage.py`.
- Disagreement-only: `scripts/pilot_disagreement.py`.
- Raw rows: `runs/pilot_v1/`.

## Terms used in this report

Each question the gate declines is put in one class, named for what the gate did. These are Ashraf's terms (2026-11-07).

| Term | Meaning |
|---|---|
| **Caught** | The gate tested the program and saw it get this kind of change wrong. |
| **Already caught** | The program failed this test on an earlier question, so it isn't trusted again. |
| **Untestable** | The gate had no way to test this kind of change on this program, so it declined. |
| **Failed history check** | The program couldn't reproduce the recorded history (factual replay), so it isn't trusted on that run. |
| **Can't express** | The program has no input that could represent the requested change. |
| **Trusted** | The gate let the program's answer through. |

The gate configurations keep their names (`native`, `replay`, `schema`, `generic`, `directed`, `program_wide`): `replay` is the gate that applies only the history check. Raw rows and the library still use the internal reason strings ("no probe could be run", "capability failed earlier", `untested`, `inexpressible`).

## Question validity: 8 of the 120 questions are invalid (found in review, verified)

Under the change they ask about, 8 questions need random draws (work, wait or route draws at visits beyond the printed columns) that the document does not give. Their gold therefore cannot be derived from the document. This breaks the deterministic-realization rule in AGENTS.md.

| Question | Undocumented draws | Of which for the query case |
|---|---|---|
| loa-routing_outcome-05 | 3 | 3 |
| loa-routing_probability-02 | 18 | 0 |
| loa-routing_probability-03 | 6 | 0 |
| loa-routing_probability-04 | 3 | 0 |
| loa-routing_probability-07 | 6 | 0 |
| loa-routing_probability-08 | 18 | 0 |
| loa-routing_probability-09 | 158 | 2 |
| pha-routing_probability-01 | 26 | 0 |

How this was checked:
- The reviewer's script compared against the document's own tables.
- `validation/question_draw_coverage.py`, using the renderer's printing rule, flags the same 8 questions with the same counts. Draws for other cases can still reach the query case through shared workers.

What changed:
- The generator `scripts/make_pilot_questions.py` now rejects any such question (`undocumented_draws`), so the final question set cannot contain them.
- The pilot was re-scored without them: `manifests/pilot_excluded_v1.json`, giving `summary_v1_valid112.json` and `attribution_v1_valid112.json`. With no exclusions, both scripts reproduce the earlier outputs exactly.

**The valid-set numbers (112 questions) are the ones to use.** The tables further down are as-run on all 120 and are kept for the record.

| Cohort | Gate | n | Coverage | Precision | Wrong | Yield | +vanilla |
|---|---|---|---|---|---|---|---|
| OTF Claude Haiku | native / replay | 336 | 0.884 | 0.886 | 34 | 0.783 | 0.836 |
| | generic | 336 | 0.881 | 0.885 | 34 | 0.780 | 0.836 |
| | directed | 336 | 0.738 | 1.000 | 0 | 0.738 | 0.842 |
| OTF Claude Sonnet | native | 336 | 0.884 | 0.845 | 46 | 0.747 | 0.801 |
| | replay | 336 | 0.818 | 0.876 | 34 | 0.717 | 0.818 |
| | generic | 336 | 0.813 | 0.883 | 32 | 0.717 | 0.818 |
| | directed | 336 | 0.690 | 0.974 | 6 | 0.673 | 0.813 |
| DEVS-Gen Haiku | native | 283 | 0.979 | 0.975 | 7 | 0.954 | 0.975 |
| | replay | 283 | 0.940 | 0.989 | 3 | 0.929 | 0.979 |
| | directed | 283 | 0.912 | 0.988 | 3 | 0.901 | 0.951 |
| DEVS-Gen Sonnet | native | 336 | 0.893 | 0.953 | 14 | 0.851 | 0.905 |
| | replay | 336 | 0.798 | 0.978 | 6 | 0.780 | 0.881 |
| | directed | 336 | 0.786 | 0.977 | 6 | 0.768 | 0.869 |
| OTF R1 gemma | native | 277 | 0.881 | 0.418 | 142 | 0.368 | 0.430 |
| | replay | 277 | 0.191 | 0.868 | 7 | 0.166 | 0.747 |
| | directed | 277 | 0.152 | 1.000 | 0 | 0.152 | 0.744 |
| OTF R1 gpt-oss | native | 283 | 0.887 | 0.279 | 181 | 0.247 | 0.293 |
| OTF R1 qwen | native | 106 | 0.868 | 0.000 | 92 | 0 | 0.094 |

Vanilla reading answers 78 of the 112 valid questions correctly (yield 0.696).

Directed declines on the valid set, as wrong answers removed / right answers lost:

| Cohort | Caught | Failed history check | Untestable |
|---|---|---|---|
| OTF Claude Haiku | 4 / 0 | 0 / 0 | 30 / 15 |
| OTF Claude Sonnet | 2 / 0 | 12 / 10 | 26 / 15 |
| DEVS-Gen Haiku | 0 / 0 | 4 / 7 | 0 / 6 |
| DEVS-Gen Sonnet | 0 / 0 | 8 / 24 | 0 / 2 |

**Carry-over from excluded questions.** Leaving questions out after the run does not remove effects that pass through the evidence registry.
- All 4 blocked right answers that remain on the valid set are loa-routing_probability-05. Each was blocked by a failure recorded on the excluded question loa-routing_probability-02, in four programs: DEVS-Gen Haiku Loan run_02 (after a timeout) and run_03 (after a rule failure), and DEVS-Gen Sonnet Loan run_02 and run_03 (after timeouts).
- So on the valid set, directed is understated by up to 2 right answers for each DEVS-Gen cohort. A real 112-question rerun would probe -05 itself.
- Reuse is clean: every kept "reused evidence" decision has at least one valid source.
- In the final runs, invalid questions are filtered out before any evidence is recorded, so this cannot recur.

The reviewer checked this by replaying each program's rows in order and tracing every kept "capability failed earlier" decision back to the question that recorded the failure.

**The exclusion changes the family balance.**
- routing_probability drops from 20 questions to 13 (Loan from 10 to 4), and one excluded question (-04) is a no-effect control.
- The excluded questions are the loop-heavy ones, where programs did badly, which is part of why valid-set precision is higher (OTF Claude Haiku native 0.832 becomes 0.886).
- The exclusion rule is fixed and uses no labels. The final question set is generated with the filter, so its balance is set at generation time.

Three conclusions change on the valid set:
- `generic` removes no errors for OTF Haiku. Its 2 earlier removals were both on invalid questions.
- DEVS-Gen Haiku has no routing-rule probe failures. The run_03 failures in Finding 2 were all on invalid questions.
- On OTF Claude, routing_probability is 9 of 39 correct with no gate, and directed declines all 39. For Haiku all 39 are Untestable. For Sonnet 35 are Untestable and 4 failed the history check, because Run 04 fails replay in two of its programs.

The main conclusion does not change: replay does the program-level filtering, and on OTF Claude most of the directed gain is abstention on a family the probes cannot observe, not detection.

## Form (b): record-comparison route-probability probe (pilot v1b, 112 valid questions)

Ashraf chose form (b) on 2026-11-07 (D21). It was designed on development data after seeing v1, and must be disclosed as such.

**What it does** (`ProbeRunner.route_change`):
- From the document's Decision log and Route draws, it takes the earliest recorded decision whose printed draw picks a different route under the requested probabilities.
- The program must change that case's records and leave every record before that decision's time unchanged.
- If the change switches no recorded decision, the realization is the factual run, so the program's records must not change at all (the no-switch check).
- If a printed draw lies within rounding of a route boundary, the probe is not run.
- Directed uses it only when the program's records name no decisions (OTF). DEVS-Gen keeps the rule probe.
- Route-probability passes are never reused across requests.

**Validation:**
- `validation/probe_soundness_route_records.py`: the reference passes all 204 cases, in both free-form and event record shapes.
- The stated rule reproduces all 549 recorded routes.
- 14 offline checks, including programs that ignore the change, programs whose records change, programs whose prefix moves, no-reuse, and the decimal boundary.
- Five independent review rounds.

**How v1b was made** (`scripts/pilot_rerun_routing_b.py`):
- Only the directed routing_probability decisions were re-decided, for OTF and DEVS-Gen, with fresh registries, after dropping the 8 invalid questions.
- Every other row is identical to v1. The reviewer checked all 4,197 rows.
- Two variants were run: with the no-switch check (`runs/pilot_v1b/`) and without it (`runs/pilot_v1b_nocheck/`).

**Directed gate, structured path, interpreted requests:**

| Cohort | Gate | Coverage | Precision | Wrong | Yield | +vanilla | Probe runs/q | No-effect correct |
|---|---|---|---|---|---|---|---|---|
| OTF Claude Haiku | native | 0.884 | 0.886 | 34 | 0.783 | 0.836 | 0 | 69/69 |
| | generic | 0.881 | 0.885 | 34 | 0.780 | 0.836 | 2.99 | 69/69 |
| | directed, form (a), v1 | 0.738 | 1.000 | 0 | 0.738 | 0.842 | 1.16 | 57/69 |
| | directed, form (b), no-switch check off | 0.738 | 1.000 | 0 | 0.738 | 0.842 | 1.22 | 57/69 |
| | **directed, form (b)** | **0.765** | **1.000** | **0** | **0.765** | **0.842** | 1.24 | 66/69 |
| OTF Claude Sonnet | native | 0.884 | 0.845 | 46 | 0.747 | 0.801 | 0 | 65/69 |
| | generic | 0.813 | 0.883 | 32 | 0.717 | 0.818 | 2.80 | 63/69 |
| | directed, form (a), v1 | 0.690 | 0.974 | 6 | 0.673 | 0.813 | 1.06 | 51/69 |
| | **directed, form (b)** | **0.717** | **0.975** | **6** | **0.699** | **0.813** | 1.13 | 60/69 |
| DEVS-Gen Haiku | native | 0.979 | 0.975 | 7 | 0.954 | 0.975 | 0 | |
| | directed, v1b | 0.919 | 0.989 | 3 | 0.908 | 0.958 | 1.28 | 46/58 |
| DEVS-Gen Sonnet | native | 0.893 | 0.953 | 14 | 0.851 | 0.905 | 0 | |
| | directed, v1b | 0.792 | 0.977 | 6 | 0.774 | 0.875 | 1.14 | 48/69 |

**Why directed declined, form (b), as wrong answers removed / right answers lost:**

| Cohort | Caught | Already caught | Failed history check | Untestable | Trusted |
|---|---|---|---|---|---|
| OTF Claude Haiku | 22 / 0 | 12 / 0 | 0 / 0 | 0 / 6 | 0 / 257 |
| OTF Claude Sonnet | 18 / 0 | 10 / 0 | 12 / 10 | 0 / 6 | 6 / 235 |
| OTF R1 gemma | 4 / 0 | 3 / 0 | 135 / 56 | 0 / 2 | 0 / 44 |
| DEVS-Gen Haiku | 0 / 0 | 0 / 0 | 4 / 7 | 0 / 6 | 3 / 257 |
| DEVS-Gen Sonnet | 0 / 0 | 0 / 0 | 8 / 24 | 0 / 2 | 6 / 260 |

**What changed, verified:**
- **On OTF Claude, the directed gate's errors are now removed by detection, not abstention.** All 34 (Haiku) and 28 (Sonnet) errors outside the history check are Caught or Already caught, at the cost of no right answers. Under form (a), 30 and 26 of them were Untestable, at a cost of 15 right answers each.
- **What the detections are:** the programs' route probabilities are fixed constants. The reviewer ran them directly: Haiku Pharmacy b1 keeps 0.95/0.05 whatever the document says. So changing the stated probabilities leaves the records byte-identical, and the probe says so.
- **The answering path agrees.** The structured path changes route probabilities the same way, by editing the document's policy text. Editing program parameters directly would be a better-execution-path change and would have to be reported apart from assurance (AGENTS.md).
- **Already caught does real work.** 12 of Haiku's 34 removals and 10 of Sonnet's 28 are Already caught: the program failed the test earlier, on another question, a different scope or different probabilities. That is defensible here, because every failure was "the program ignores the input".
- **The no-switch check** recovers the no-effect controls that form (a) and form (b) without the check both declined: 9 per Claude cohort, plus 2 for gemma. All are correct, and the reviewer checked three of them by direct runs. The check was added after seeing that these questions were declined, and decides only the request at hand. Both variants are reported.
- **The remaining Untestable declines** are routing_outcome questions with no usable witness flip, all correct answers lost: 6 for each Claude cohort.
- **DEVS-Gen directed improves slightly over v1 valid112:** coverage 0.912 to 0.919 for Haiku, and 0.786 to 0.792 for Sonnet. Fresh registries removed the carry-over from excluded questions, and fresh probes replaced reuse. DEVS-Gen's precision gain still comes only from replay.
- **Cost:** form (b) adds about 0.05 to 0.08 probe runs per question for the Claude OTF cohorts. Directed stays below generic (about 1.1 to 1.3 runs against 2.8 to 3.0).

Limits that still apply:
- Development data only.
- The new probe shows only that the case's records change: a program that changes them in the wrong way would pass. It catches programs that ignore the input, which is what the pilot's OTF programs do.
- The prefix check has only decided reference-shaped records; no real OTF row reached it, because every changed OTF output equalled its base.

## What was run

- **Questions:** 120 counterfactual questions on two development specifications (Loan, Pharmacy), 60 each. There are 6 families × 10 questions per specification, and in each family 2 of the 10 are valid no-effect controls. Gold comes from the reference engine. The questions are templated (see Limits).
- **Programs:** 40 built programs, every one that built:

  | Cohort | Programs |
  |---|---|
  | OTF R1, gemma-31b | 5 |
  | OTF R1, gpt-oss-120b | 5 |
  | OTF R1, qwen3.5-9b | 2 |
  | OTF R1, Claude Haiku 5.5 | 6 |
  | OTF R1, Claude Sonnet 5.5 | 6 |
  | DEVS-Gen, Haiku 5.5 | 5 |
  | DEVS-Gen, Sonnet 5.5 | 6 |
  | B0 (pinned OTF, native path only) | 5 |

  Each program saw the 60 questions of its own specification. All 40 output files are complete, with no duplicate rows.
- **Interpretation:** one Haiku 5.5 call per question turns the question into a structured request. Every program shares these requests.
- **Answer paths:**
  - *structured*: our adapter runs the program with the structured change.
  - *native*: OTF's own LLM patch (OTF only).
  - *native+binding*: the native path plus our record-level binding check.
- **Gates:**

  | Gate | What it checks |
  |---|---|
  | `native` | no checks |
  | `schema` | request contract only |
  | `replay` | contract, then factual replay of recorded case ends |
  | `generic` | replay, then 3 input-use probes on random families |
  | `directed` | replay, then probes on the requested family, operation and target, with evidence reuse |
  | `program_wide` | replay, then one probe per case-level family |

- **Reading comparators:** both use Haiku 5.5 with the same prompt and an answer line.
  - *vanilla*: the full document in context.
  - *RAG*: the top 8 BM25 chunks.
- **Correctness:** the answer equals the gold case end to within 1 second.

## Main table (structured path, interpreted requests)

n = number of questions × programs in the cohort. "Wrong" counts permitted answers that are wrong. "Yield" is the share of all questions answered correctly when declined questions get no answer. "+vanilla" is the same yield when declined questions fall back to the vanilla reading answer. "Probe runs/q" counts probe executions only; the one factual base run per program and scope is not included.

| Cohort | n | Gate | Coverage | Precision | Wrong | Yield | +vanilla | Probe runs/q |
|---|---|---|---|---|---|---|---|---|
| OTF Claude Haiku | 360 | native | 0.892 | 0.832 | 54 | 0.742 | 0.792 | 0 |
| | | replay | 0.892 | 0.832 | 54 | 0.742 | 0.792 | 0 |
| | | generic | 0.883 | 0.837 | 52 | 0.739 | 0.794 | 2.99 |
| | | directed | 0.689 | 1.000 | 0 | 0.689 | 0.803 | 1.09 |
| OTF Claude Sonnet | 360 | native | 0.889 | 0.800 | 64 | 0.711 | 0.761 | 0 |
| | | replay | 0.822 | 0.831 | 50 | 0.683 | 0.778 | 0 |
| | | generic | 0.817 | 0.837 | 48 | 0.683 | 0.778 | 2.80 |
| | | directed | 0.644 | 0.974 | 6 | 0.628 | 0.775 | 0.99 |
| DEVS-Gen Haiku | 300 | native | 0.950 | 0.965 | 10 | 0.917 | 0.943 | 0 |
| | | replay | 0.913 | 0.978 | 6 | 0.893 | 0.947 | 0 |
| | | generic | 0.910 | 0.978 | 6 | 0.890 | 0.943 | 2.88 |
| | | directed | 0.870 | 0.977 | 6 | 0.850 | 0.910 | 1.22 |
| DEVS-Gen Sonnet | 360 | native | 0.856 | 0.945 | 17 | 0.808 | 0.869 | 0 |
| | | replay | 0.767 | 0.967 | 9 | 0.742 | 0.847 | 0 |
| | | generic | 0.761 | 0.967 | 9 | 0.736 | 0.842 | 2.47 |
| | | directed | 0.756 | 0.967 | 9 | 0.731 | 0.836 | 1.09 |
| OTF R1 gemma | 300 | native | 0.887 | 0.391 | 162 | 0.347 | 0.403 | 0 |
| | | replay | 0.180 | 0.852 | 8 | 0.153 | 0.710 | 0 |
| | | directed | 0.140 | 1.000 | 0 | 0.140 | 0.707 | 0.20 |
| OTF R1 gpt-oss | 300 | native | 0.893 | 0.261 | 198 | 0.233 | 0.277 | 0 |
| | | replay (all gates) | 0 | — | 0 | 0 | 0.657 | 0 |
| OTF R1 qwen | 120 | native | 0.883 | 0.000 | 106 | 0 | 0.083 | 0 |
| | | replay (all gates) | 0 | — | 0 | 0 | 0.717 | 0 |

`schema` equals `native` for every cohort: no interpreted request failed the contract. `program_wide` is never better than `generic`; it is in `summary_v1.json`.

Program-clustered 95% bootstrap intervals for precision. These are descriptive only: builds of one model on one specification are not independent.

| Cohort | native | directed |
|---|---|---|
| OTF Claude Haiku | [0.748, 0.904] | [1.0, 1.0] |
| OTF Claude Sonnet | [0.695, 0.888] | [0.914, 1.0] |
| DEVS-Gen Haiku | [0.907, 1.0] | [0.935, 1.0] |
| DEVS-Gen Sonnet | [0.871, 1.0] | [0.911, 1.0] |

Matched random refusal has an expected precision equal to the native precision at any coverage, so a gate that does no better than its cohort's native precision is no better than refusing at random.

**Reading alone (120 questions):**

| Reader | Answered | Correct | Yield | Precision | Cost/q | Model time/q |
|---|---|---|---|---|---|---|
| Vanilla | 100 | 80 | 0.667 | 0.80 | $0.0157 | 55 s |
| RAG | 55 | 32 | 0.267 | 0.58 | $0.0027 | 17 s |

Cost and time per question include retries. The runner retried calls that hit the 16,384-token output cap, but the rows record only the last call, so these figures come from the ledger:
- **Vanilla:** 153 calls for 120 questions; 50 of the 153 calls hit the cap. 17 questions were still truncated after retries and gave no answer, which handicaps vanilla (see Decisions).
- **RAG:** 123 calls, of which 3 were truncated retries.
- **Interpretation:** 120 calls, $0.0002 per question.

**Disagreement-only comparator** (preliminary; computed from the existing rows by `scripts/pilot_disagreement.py`, not yet in `pilot_summary.py`). It permits the structured answer only when the vanilla answer exists and agrees with it to within 1 s.

| Cohort | Coverage | Precision | Yield |
|---|---|---|---|
| OTF Claude Haiku | 0.619 | 0.946 | 0.586 |
| OTF Claude Sonnet | 0.608 | 0.936 | 0.569 |
| DEVS-Gen Haiku | 0.620 | 0.995 | 0.617 |
| DEVS-Gen Sonnet | 0.589 | 0.991 | 0.583 |
| OTF R1 gemma | 0.300 | 0.933 | 0.280 |
| OTF R1 gpt-oss | 0.210 | 0.984 | 0.207 |
| OTF R1 qwen | 0 | — | 0 |

With vanilla fallback, disagreement-only equals vanilla's own yield on that cohort's mix of questions, 0.657 to 0.717: where the two agree they give the same answer, and everywhere else vanilla answers.

Disagreement-only needs a vanilla call on every question, about $0.0157 each, against $0.0002 for interpretation under the gates. Directed plus agreement costs the same extra $0.0157 per question. Requiring both directed and agreement gives precision 0.989 to 1.000 at coverage 0.52 to 0.60 on the Claude and DEVS-Gen cohorts.

**OTF's own patch path (native) and the binding check:**

| Cohort | Native path coverage / precision | With binding check |
|---|---|---|
| Claude Haiku | 0.894 / 0.242 | 0.206 / 0.311 |
| Claude Sonnet | 0.658 / 0.211 | 0.186 / 0.298 |
| B0 gpt-oss (4 programs) | 0.562 / 0.022 | 0.154 / 0.027 |
| B0 gemma (1 program) | 0.667 / 0.200 | 0.167 / 0.300 |
| R1 gemma | 0.587 / 0.131 | 0.163 / 0.184 |
| R1 gpt-oss | 0.547 / 0.091 | 0.167 / 0.140 |
| R1 qwen | 0.292 / 0.057 | 0.167 / 0.100 |

The native patch path is the weakest path in every cohort except R1 qwen. There it answers 2 of 120 questions correctly, against none for the structured path. The binding check removes most of its answers and raises precision only a little.

## Where each gate's gain comes from (verified)

This counts the native answers each gate removed, split by why it declined. "Wrong" is errors removed; "right" is correct answers lost. The source is `attribution_v1.json`: structured path, interpreted requests.

| Cohort, gate | Failed history check | Caught | Already caught | Untestable | Trusted |
|---|---|---|---|---|---|
| OTF Claude Haiku, directed | 0 / 0 | **4 / 0** | 0 / 0 | **50 / 19** | 0 / 248 |
| OTF Claude Haiku, generic | 0 / 0 | 2 / 1 | 0 / 0 | 0 / 0 | 52 / 266 |
| OTF Claude Sonnet, directed | 14 / 10 | **2 / 0** | 0 / 0 | **42 / 20** | 6 / 226 |
| OTF Claude Sonnet, generic | 14 / 10 | 2 / 0 | 0 / 0 | 0 / 0 | 48 / 246 |
| DEVS-Gen Haiku, directed | 4 / 7 | 0 / 2 | 0 / 5 | 0 / 6 | 6 / 255 |
| DEVS-Gen Sonnet, directed | 8 / 24 | 0 / 0 | 0 / 2 | 0 / 2 | 9 / 263 |
| OTF R1 gemma, directed | 154 / 58 | 0 / 0 | 0 / 0 | 8 / 4 | 0 / 42 |
| OTF R1 gpt-oss, directed | 198 / 70 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| OTF R1 qwen, directed | 106 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

## Findings

**1. Factual replay does most of the filtering, and it works at the program level.**
- Replay rejects every gpt-oss and qwen R1 program on every scope, and 4 of the 5 gemma programs.
- On the Claude and DEVS-Gen cohorts it rejects individual scopes:
  - Loan Run 04 in 5 programs across three cohorts. Each time exactly 5 of 15 case ends differ, which suggests one feature of that run that several builds implement the same wrong way.
  - Pharmacy Run 03 in two DEVS-Gen Sonnet programs, where the factual run crashes.
- For the open-model OTF cohorts, replay alone takes precision from 0.26–0.39 to 0.85 or "no answers". Directed adds almost nothing on top. Gemma loses its last 8 wrong answers along with 4 right ones, and all of these are Untestable declines, not catches.

**2. Intervention probes detected few errors in programs that passed replay.**
- Across all cohorts, the gate Caught 6 wrong answers: 4 for OTF Haiku and 2 for OTF Sonnet. They are `add_workers` resource-rule failures plus one activity input-use failure, and they cost no right answers.
- **On DEVS-Gen, probes detected nothing. Directed probe failures cost 9 right answers**, counting the later questions they blocked:
  - DEVS-Gen Haiku, 6 lost: Loan run_03 failed the routing_probability rule probe on two questions whose answers were exactly right. The probe's message was "2 first decisions disagree with the stated rule", but in fact 2 cases produced no decision at all. Those two failures then blocked 4 more correct answers.
  - DEVS-Gen Haiku, 1 lost: blocked after a probe timeout.
  - DEVS-Gen Sonnet, 2 lost: blocked after probe timeouts.
  - Every timeout happened on a question whose own answering run also timed out, so calling the timeouts false alarms is not established.
  - The routing rule probe was then checked against the reference engine (`validation/probe_soundness_route_rule.py`). It accepted the reference in all 184 valid cases, across both documents, every run, every decision, and changes that put all the probability on one route, reverse the probabilities, or split them equally. 8 further changes could not run in the reference because they loop forever.
  - *Reviewer observation, no committed artifact:* the reviewer also ran all 20 routing_probability question changes through the rule probe on the reference's own output, and all passed.
  - **This does not show misrouting.** *Reviewer observation, no committed artifact:* the reviewer ran the run_03 program under the two questions' changes (offline, in its sandbox). It exits normally but writes no records at all for two cases each time: c0002 and c0003 in Run 03, and c0010 and c0014 in Run 04.
  - The probe counts a case with no decision record as a disagreement (`assurance/probes.py`, `seen.get(c) != expected[c]`).
  - Those cases need draws the document does not print (verified: `validation/question_draw_coverage.py`).
  - 5 of the 6 lost answers are on invalid questions. The 6th, loa-routing_probability-05, is valid but was blocked by the failure recorded on invalid -02.
  - That the program drops these cases *because* it lacks their inputs is an inference: the program's code was not read. Either way it is not evidence of a wrong routing rule.
  - The 184-case reference test cannot exercise this path, because the reference always has every draw.
- **`generic` and `program_wide` failures on DEVS-Gen** were "records before the change point moved" on routing_outcome input-use probes. They removed no errors and cost correct answers:

  | Gate | Haiku | Sonnet |
  |---|---|---|
  | `generic` | 1 | 2 |
  | `program_wide` | 5 | 10 |

- **`generic`**, at about 3 probe runs per question, removed 2 errors for OTF Haiku (losing 1 right answer) and 2 for OTF Sonnet. It removed none beyond replay elsewhere.

**3. Most of the directed gate's large gain on OTF Claude is abstention, not detection.**
- For OTF Haiku, 50 of the 54 removed errors were declined as *Untestable*; doing so cost 19 right answers. For Sonnet the split is 42 of 58, at a cost of 20.
- Almost all of these are routing_probability questions. OTF programs write free-form records (a `kind` text and an entity list) with no structured decision events, and the routing_probability probe needs decision events. So it can never run on OTF, and the rule "a probe that did not run is never a pass" declines the request.
- That family is the one these programs get wrong: native answers 12 of 60 correctly for both Claude cohorts. Declining it therefore removes far more wrong than right answers (50/19 versus about 17% wrong for random refusal).
- The credit belongs to "decline when the requested capability cannot be checked". The probe never observed the error itself.
- The remaining Untestable declines are routing_outcome questions whose decision had no usable witness flip (Haiku 9: 7 right, 2 wrong; Sonnet 8: all right). They were mostly correct answers lost.

**4. DEVS-Gen programs are the most accurate path, and gates change them little.**
- DEVS-Gen Haiku answers 0.917 of all questions correctly with no gate.
- Gates cost coverage for a small precision gain:

  | Cohort | Coverage cost (points) | Precision gain (points) |
  |---|---|---|
  | Haiku | 3.7 to 8.0 | at most 1.3 |
  | Sonnet | 8.9 to 10.0 | 2.2 |

- All of that precision gain comes from replay.

**5. Vanilla reading is a strong comparator.**
- With the whole document in context, Haiku answers 0.667 of questions correctly. That beats every open-model OTF cohort, is close to the Claude OTF cohorts' native yield (0.74 and 0.71), and is below DEVS-Gen.
- RAG is much weaker (0.267).
- The best Claude OTF policies with vanilla fallback give only small gains over native with fallback (0.792 for Haiku, 0.761 for Sonnet):
  - Haiku: directed, 0.803.
  - Sonnet: replay, generic or program_wide, 0.778. Directed reaches 0.775.
- A declined question that falls back to reading costs about $0.016, counting retries. A permitted program answer costs only the $0.0002 interpretation call plus local program runs.

**6. No-effect controls.**
- Programs that ignore an input answer no-effect questions correctly by construction. With no gate, OTF Haiku answers 72 of 72 correctly and OTF Sonnet 68 of 72.
- Under the directed gate:
  - Haiku loses 15 correct answers, all Untestable.
  - Sonnet loses 17 correct answers (15 Untestable, 2 failed history check) and removes 4 wrong ones, all by replay.

**7. Interpretation was exact on all 120 questions, so this pilot cannot separate the gate from interpretation.** Rows from interpreted and oracle (hidden-binding) requests are identical. This is because the questions are templated.

## Limits

- Development data only, from two specifications and one question template per family.
- The cohorts are small: 2 to 6 programs each, built by one model on one specification, so they are not independent.
- Cohorts are reported separately and never pooled; B0 stays separate as the native reference.
- Bootstrap intervals are descriptive.
- Vanilla is handicapped by the 16,384-token output cap.
- No paraphrases, so interpretation error is untested.
- Cost covers model dollars and probe execution counts. Program run time is in the raw rows but not summarised here.
- "+vanilla" falls back to the reading answer for every question without a permitted program answer. That includes permitted questions where the program crashed or could not express the change, not only declined ones.
- The bootstrap resamples programs, then questions. Intervals such as [1.0, 1.0], from cohorts with 0 wrong answers, do not mean certainty.
- Failed builds are not in these tables: DEVS-Gen built 11 of 13 attempts, and the OTF build counts are in `run_manifest.md`. The paper must report them.
- Per-program results are in `summary_v1.json` (`per_program`) and are not reproduced here.
- Disagreement-only is preliminary and is not yet in the reviewed summary script.
- Provenance: Claude models also helped write the reference engine and the questions, so grading the Claude cohorts against that reference is a disclosed limitation.
- The DEVS-Gen build cost ($5.08) is estimated from DEVS-Gen's token log at list prices with no cache discount. It is not ledger spend.

## Decisions needed before the Nov 10 freeze

These are proposals, not yet acted on.

1. **routing_probability probe on OTF.** Decided: Ashraf chose (b) on 2026-11-07 (D21). The results are in the form (b) section near the top, and the text below is kept for the record.
   - Option (a): keep the current rule. The paper then says plainly that much of the directed gain is "decline when the capability cannot be checked".
   - Option (b): add a weaker record-comparison form for routing_probability, which works on free-form records. Change the stated probabilities so that some recorded draw would switch route, then require that case's records to change and the earlier records to stay the same. Directed's gain then rests more on detection. This would be designed on development data and disclosed as such.
   - Either way the abstention-versus-detection split above is reported.
2. **Probe timeouts and the routing rule probe.**
   - Every timeout in the pilot was on an excluded question (-02, -04, -09), so the pilot says nothing about timeouts on valid questions. Proposal: keep counting a timeout as a failure, but report timeouts separately from crashes.
   - The routing rule probe's disagreements with correct DEVS-Gen answers came from invalid questions; see Question validity. The rule itself passes the reference check.
   - Proposal: have the probe report "case produced no decision" separately from "decision disagrees". Still count both as failures, since a dropped case is a defect. Routine.
3. **Vanilla output cap.** Proposal: raise it to 64,000 for the final runs, so the comparator is not truncated. Estimated about $2 more on the final question set. Routine.
4. **Paraphrased questions.** Without them, the gate-only versus interpretation-plus-assurance comparison has nothing to measure. This is optional per the agreed scope. It costs one interpretation call per paraphrase, which is cheap.

## Spend

The pilot ledger total is $3.11 at list prices over 2,136 calls (Haiku 5.5): interpretation, reading and the native-path patches. Combined Anthropic spend to date at list prices is $11.07 of the $100 credit:

| Item | Spend |
|---|---|
| Build test | $2.87 |
| Slices | $0.01 |
| Pilot (replaces the earlier partial figure of $1.67) | $3.11 |
| DEVS-Gen builds | $5.08 |

Our own ledger accounts for $5.99 of this, against its $15 cap.
