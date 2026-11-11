# Baselines that judge trust: design proposal (2026-11-08, revised after review 1)

Status: **design settled by Ashraf on 2026-11-08 and 11-09 (see "Decisions"; recorded as D22). Not implemented yet: no judge code, no coding-agent platform, nothing run.** Written after the Nov 8 meeting with Dr. Roy (`meeting/nov_8_part_1.docx`). One independent review is done and its fixes are applied (listed at the end). Becomes D22 once Ashraf settles the open decisions.

## Why the baselines change

Dr. Roy's point: OTF-Tools and DEVS-Gen *produce* programs and answers. They are the platforms our library runs on, not baselines for it. A true baseline is another method that does the same job as our library: decide whether to trust a generated simulator. Whether the platforms build good or bad programs is irrelevant to the story. Only the component that judges them matters.

He named two things a judge can assess (5:35, 15:24): **(A)** whether the program itself is correct, and **(B)** whether the answer it gives to a particular question can be trusted. Our library does both: the history check and program-wide probes speak to (A), and directed probes per request speak to (B). Each baseline below is defined at the level it judges.

So the paper's main comparison is between **trust judges**, all deciding on the same fixed programs, questions and answers.

## What counts as what

| Role | Methods | Status |
|---|---|---|
| **Platforms** (produce programs and answers; not compared with each other) | OTF-Tools (R1 programs; B0 kept as a pinned native reference) and DEVS-Gen. The third platform is a plain reason-and-code agent (decision 1). | Built |
| **Our method** | The library's `directed` gate | Built, piloted |
| **Baselines: other trust judges** | 1. **Native check**: each platform's own single pass-or-fail verdict. This is the "current checks" of the abstract. | Built (`native`) |
| | 2. **LLM-as-a-judge, answer level**: one model call reads the records, the program, the question and the answer, and says whether to trust the answer. | **New** |
| | 3. **LLM-as-a-judge, program level**: one call per program and run, which says whether the program can be trusted for what-if questions on that run. Compared with `native`, `replay` and `program_wide`. | **New** |
| | 4. **ReAct judge**: a raw ReAct agent whose one tool runs code in a sandbox holding the program. It decides what, if anything, to run. | **New** (optional in D16, promoted here) |
| | 5. The history check alone (`replay`), generic behavior tests (`generic`), and disagreement with a reading answer | Built; kept as simpler judges |
| **Ablations of our own method** | `schema`, `program_wide`, form (b) with and without the no-switch check, the oracle request source | Built |
| **Answers without a program** | Vanilla LLM reading and RAG reading | Built; kept as reference answerers and as the fallback, not as judges |

LLM-as-a-judge and the ReAct judge answer a reviewer's first question: "why not just ask an LLM whether the answer is right?" The ReAct judge is the harder one to beat, because it can run the program as our probes do. If our library beats it at matched coverage and cost, the gain comes from *which* checks are run (family-directed and deterministic, with recorded evidence), not just from running the program. If it doesn't, that is a reported result.

At 12:08 Dr. Roy calls the LLM judge "basically your pass or fail verdict". The paper should say how the two relate: the native check is a pass-or-fail verdict on the program, and the LLM judge is a model-made verdict on the answer.

## What every judge sees

**Common inputs:**
- The document's front matter (process rules and stated policy) and the records of the run the interpreted request names. The gate's history check also uses only that run (`ProbeRunner.replay(scope)`), so this is parity.
- The generated program's own code, and nothing else from its build folder:
  - OTF: the `code` field of `program.json` only. Not `passed`, `mean_f1` or `attempts`, which carry the native verdict and the build history.
  - DEVS-Gen: the generated model files under `devs_project/` (`*.py`, about 34–44k characters), plus a description of the generic input format. Not `run.py`, which is a 1 KB launcher, and not the smoke-test output, logs or `gen_meta.json`, which carry native results.
- The question text and the interpreted structured request. This is the same request the gate gets, so interpretation stays fixed across judges.
- Answer-level judges also see the program's answer: the queried case's end time under the change, and without it.

**Never sees:** gold answers, the reference engine, hidden bindings, effect labels, other judges' verdicts, or any other program's results. The question row is whitelisted to its text, and the run is taken from the interpreted request, as in `pilot_runner.py`.

**Disclosed asymmetry:** the gate decides from the structured request alone, before any answer is produced. The answer-level judges also see the question text and the answer value, so only they can notice a misread question or an implausible number. This favors the judges.

## Baseline 2: LLM-as-a-judge, answer level

- **Says:** `TRUST` or `DECLINE`, a confidence from 0 to 100 that the answer is exactly right, and a one-line reason.
- **Failures:** an unparsable reply, an output cutoff or a refusal counts as `DECLINE` at the lowest confidence, and is reported apart.
- **Model:** Haiku 5.5, the fixed per-question model (D18), with adaptive thinking at medium effort and the same output cap as the other per-question calls. Sonnet 5.5 and the other models judge a shared random subset (decisions 5 and 6).
- **Self-preference:** Claude judging Claude-built programs may favor them, which is disclosed. The Ollama-built programs give a partial check.

## Baseline 3: LLM-as-a-judge, program level

One call per (program, run), about 140 calls. The judge gets the common inputs, minus the question and answer, and says whether this program can be trusted to answer what-if questions on this run, with a confidence. Each verdict applies to every question on that run.

## Baseline 4: ReAct judge (raw, Ashraf 2026-11-08)

A plain text ReAct loop (Thought, Action, Observation) through the same client, ledger and spending cap as every other call. It is kept deliberately raw: no tools beyond running code, and no hints about how to test.

**One tool:** `run_code(python)`. It runs a Python snippet in a sandbox and returns stdout and stderr, truncated to a fixed length. The sandbox holds only:
- the program, exactly as its platform runs it (the OTF program with its runtime; the DEVS-Gen model files under WSL with `bwrap`);
- the same document view the LLM judge gets, as files.

It holds no gold, reference engine, hidden bindings, other programs or build history, and has no network access.

**Instructions:** the inputs listed under "What every judge sees", one line on what the tool does, and the output we record (`TRUST` or `DECLINE`, a confidence from 0 to 100, a one-line reason). Nothing about which tests to run. The judge may run the program however it likes, change its inputs or not run it at all.

**Budget:** at most 8 turns per question (Ashraf kept 8 on 2026-11-08). Running code costs a turn, so it isn't free.
- Why 8: a judgment call, not a measurement. It allows a few code runs, some reading of the output, and a verdict, while keeping the per-question cost bounded. The smoke run reports how many turns each row used. If many rows hit the cap without a verdict, that is brought to Ashraf before the freeze.
- A single snippet can run the program many times, so "3 changed runs" can't be matched exactly. Sandbox calls, program executions where they can be counted, and wall time are all logged and reported as its cost.
- Running out of turns without a verdict counts as `DECLINE` at the lowest confidence, reported apart.

**Why it isn't reasoning-only:** a ReAct agent that never acts is the answer-level LLM judge, which is already baseline 2. The three judges form a ladder:
- the LLM judge reasons only;
- the ReAct judge reasons and runs code;
- our library runs fixed, family-directed checks with recorded evidence.

**Equal access:** the sandbox gives the ReAct judge at least as much execution access as our library has. Our probe types are the method under test, so they are not given to it.

## Scoring

- Same metrics as the pilot, per cohort, never pooled across platforms or model cohorts: coverage, precision of trusted answers, correct-answer yield, false permits and false rejections.
- Cost: model calls, tokens and dollars, program executions and wall time.
- **Matched coverage:** our gate gives a yes or no. For each cohort, each judge is reported three ways:
  - precision at the gate's coverage, by threshold on confidence;
  - precision at its own `TRUST` verdict;
  - its full risk-coverage curve.
- **Answered means trusted and an answer exists** (Ashraf, 2026-11-09). A row that a judge trusts but where the program produced no answer is recorded as Can't express, never as covered. The rule is the same for every judge.
- **Ties:** confidences will be coarse. At the matched point, report expected precision over the tied rows. That is exact, so no random tie-break is needed.
- **Uncertainty:** the two-level bootstrap (programs, then questions). The coverage match is redone inside each resample. Gate-minus-judge differences are reported as paired. Matching to the gate's coverage is the same analysis step for every judge, not tuning on labels.
- **Results** per program and per family.

**Dev results don't count as evidence.** Form (b) and the no-switch check were designed after seeing these 112 questions (D21), so a dev comparison favors the gate. Dev runs exist only to debug the judges and fix their prompts. Prompts may be revised on dev only, and are frozen with everything else on Nov 11.

## Code changes needed

All of these are routine. They get a separate-agent review before any paid run.
- **Block-level prompt caching:** document, then program, then question, with a cache breakpoint after the program. Today each prompt is one string, so nothing is shared between rows. The vanilla calls were mostly cache writes: 7.38M tokens written against 1.71M read. With list content, `prompt_chars` must count characters, not blocks.
- **Stop sequences** for the ReAct loop, so the model can't write its own observations.
- **Output cap raised to 64k**, already planned before the freeze. 17 of 120 vanilla calls hit the 16k cap.
- New `scripts/judges.py`: the three judges, offline tests with a fake model and fake programs, and the scorer's additions.

## Cost (Haiku list price, estimated from measured pilot calls; reviewer's recomputation)

| Run | Rows | Per row | Total |
|---|---|---|---|
| Answer-level LLM judge, dev, with caching (all 35 programs, 1,758 answered rows) | 1,758 | about $0.005 | about $9 ($17 without caching) |
| Program-level LLM judge, dev | about 140 | about $0.006 | about $1 |
| ReAct judge, dev, Claude cohorts (1,171 answered rows) | 1,171 | $0.01–0.03 | $12–35 |
| Sonnet answer-level judge, 200 rows | 200 | $0.09–0.19 | $18–38 |

Running everything on all dev rows could cost $39–90. That is too much, since dev results don't count as evidence, and $88.93 is left. **Proposed dev spend:**
- a 20-row smoke run per judge;
- then a stratified subset of about 300 rows, by cohort and family;
- the program-level judge in full.

That comes to about $8–12. The rest is kept for the test set. The test sets now exist (2026-11-09: workflow 240, manufacturing 96, IT 120, plus 96 policy-variant questions in progress). **The test-run cost estimate from actual row counts is still owed**, and goes to Ashraf before any paid run.

The runner's Claude stop is now $25 (decision 2). With $5.99 on that ledger, about $18.76 can still be spent before it stops. DEVS-Gen's estimated $5.08 is tracked apart.

## Decisions (Ashraf, 2026-11-08)

1. **Third platform: ReCode.** Ashraf calls it "the ReCode agent (Reasoning and Coding)". The one published ReCode found (checked 2026-11-08) is a different thing: "ReCode: Unify Plan and Action for Universal Granularity Control" (arXiv 2510.23564, github.com/FoundationAgents/ReCode). It is an agent that writes plans as placeholder functions and expands them recursively into executable actions. It was built and evaluated for interactive environments (ALFWorld, WebShop, ScienceWorld), not for writing simulators, and its license has not been checked yet. **Decided:** a plain reason-and-code agent. In the paper it is named generically (for example "a plain coding agent"), not "ReCode", so it isn't confused with the published method.
2. **Spend:** approved. The runner's Claude stop goes from $15 to $25.
3. **Sonnet judge:** not run on dev, apart from smoke rows. On the test set, see decision 5.
4. **ReAct judge stays raw:** one sandbox code tool and instructions on what to return, nothing more. The same rule holds for the ReCode platform: no added checks or fallbacks.

5. **Models, the same everywhere (Ashraf, 2026-11-08):**
   - **Platforms:** all three build with Claude Sonnet 5.5 and Claude Haiku 5.5. That covers OTF-Tools R1, DEVS-Gen and the plain coding agent. OTF-Tools programs built by the Ollama models (gpt-oss, Gemma, Qwen) and B0 stay as extra, labeled OTF-only cohorts, never pooled.
   - **LLM-based judges:** the answer-level LLM judge, the program-level LLM judge and the ReAct judge all run on Haiku for every row. All three also run on Sonnet for one fixed random subset of rows, the same subset for every judge.
   - **The subset** is drawn with a fixed seed from row ids only, stratified by platform cohort and family, before anything is scored. No correctness labels are used. Its size is set by budget once the test set's size is known.
   - **Shared per-question work stays Haiku:** request interpretation, vanilla and RAG reading, and OTF's native patch step. The answer path then never changes between platforms or judges (D18).
   - Our library and the rule-based judges use no model.

6. **All five models on every platform and judge (Ashraf, 2026-11-08; supersedes the model part of decision 5):**
   - **Platforms:** DEVS-Gen and the plain coding agent also build with gpt-oss:120b and Gemma 4 31B (Ollama cloud) and Qwen 3.5 9B (local). OTF-Tools R1 already has all five. B0 stays as it is: gpt-oss and Gemma, no Qwen, because Qwen built 0 of 12 under B0.
   - **Judges:** Haiku judges every row. Sonnet, gpt-oss, Gemma and Qwen each judge the same shared random subset, with all three LLM-based judges. Every model then sits in every judge column on the same rows.
   - **Measured speed** (call ledgers, 2026-11-08):

     | Model | Median s per call | Output tokens/s | Note |
     |---|---|---|---|
     | Qwen local | 16 | about 190 | a 79k-token prompt took 34 s |
     | gpt-oss cloud | 5 | about 350 | |
     | Gemma cloud | 13 | about 300 | |

     Qwen isn't too slow for builds or the LLM judges. A Qwen ReAct judge needs about 4 minutes per row, so about 7 hours for 100 rows, run overnight one at a time.
   - **DEVS-Gen on Ollama:** its LiteLLM 1.81.3 has the `ollama_chat` provider, but this is untested. DEVS-Gen runs 8 calls at once by default, while Ollama cloud allows 3, so it must run with 3. For Qwen, the local Ollama server isn't running now, and WSL has to be able to reach it on the Windows host. Both are setup work.
   - **Cost:**
     - A DEVS-Gen build measured 220k input and 52k output tokens, about $0.06 on gpt-oss or Gemma.
     - A gpt-oss or Gemma judge costs about $0.009 per row as an LLM judge, and about $0.05 per row as a ReAct judge (8 turns, no prompt caching assumed).
     - On a 100-row subset, the Ollama total comes to about $15–20 including builds. The Ollama credit was $8.73 at last report, so it needs topping up.
     - Sonnet on the same 100 rows costs about $45, most of it the ReAct judge. The subset's size controls both totals.
   - **Qwen evidence:** Qwen built 3 of 12 OTF programs under R1, so it may build few or no DEVS-Gen or coding-agent programs. Failed builds are reported, and its cells are not presented as equal evidence (D7).

7. **B0 also builds with Sonnet and Haiku (Ashraf, 2026-11-08):** so the original-tool reference covers every builder model.
   - B0 was never run on Claude; only R1 was. The runner already supports it (`BUILD_SYSTEM=b0` with a Claude setup writes to `runs/build_test_b0_claude`). The pinned code stays unchanged, and only the model connection is replaced, as in D13.
   - **Cost:** the R1 Claude build test cost $2.87 for four documents. B0 should cost about the same, or about $1.50 for loan and pharmacy only.
   - **Qwen under B0** was tried and built 0 of 12, so it appears in B0 as tried, with no programs.
   - B0 stays a native-only reference (D16).

**ReAct and ReCode do different jobs.** Both reason and run code, but:
- **ReCode is a platform.** Like OTF-Tools and DEVS-Gen, it writes a simulator program and answers the what-if question with it. Our library and the judges then assess its program and answers.
- **ReAct is a judge.** It is given another platform's program and answer, and decides whether to trust that answer. It runs code only to test the program, never to produce the answer being judged.

## Earlier open decisions (kept for the record)

1. **Third platform.** Dr. Roy (17:21–18:01): "still include recode as a third baseline … recode does not have those checks and fallbacks", "to show generality across … simulator platforms". He means a third *platform* (a plain code-writing agent, without OTF's checks and fallbacks), and you agreed to look into implementing it.
   - (a) **Add it for loan and pharmacy.** A plain Claude coding agent writes a simulator from the document's rules, reading the generic input format we already give DEVS-Gen, with no checks. It also shows the library working where no native verdict exists. Estimated at half a day of adapter work and about $1–3 of builds per model cohort. It puts the Nov 10 freeze at risk.
   - (b) **Two platforms**, and state the limit.
   - The registered abstract says "We apply it to two such systems". Option (a) needs the abstract edited before submission, if the system allows it, or a disclosed change.
   - "ReCode" may be the name of a published agent method; that is unverified. If it is, either use that method or don't call ours by that name.
2. **Spend:** approve about $12 for the dev judges after the smoke run, and raise the runner's Claude stop from $15 to cover it (to $25). The test-set judges get a separate estimate.
3. **Sonnet judge subset:** include it ($18–38 on dev, more on test) or leave it out. I lean toward leaving it out, or running it on test only.

## What this doesn't change, and what it depends on

- **Domains:** manufacturing, IT operations, loan and pharmacy. The pilot covers loan and pharmacy only. Claude-built OTF programs for manufacturing and IT operations exist (`runs/build_test_r1_claude/*/mfg_dev`, `itops_dev`), and their dev and test questions with checked gold are done (`manifests/domain_readiness.md`).
- **DEVS-Gen scope:** Dr. Roy's Experiment 2 is DEVS-Gen on all four domains, while D16 makes manufacturing and IT optional for it. DEVS-Gen tasks now exist for all four domains; manufacturing and IT are installed but not built.
- **Unchanged:** our library, B0, the gold source, the splits rule and form (b) (D21).

## Review 1 (2026-11-08): what changed

An independent agent checked the proposal against the code, the transcript and measured costs. Changes made:
- **DEVS-Gen program view:** it is the generated model files, not `run.py`.
- **History check:** the earlier text wrongly said the gate replays all four runs. It replays only the queried run. The judges now get that run only, and the ReAct `read_records` tool was removed, because it would have given the ReAct judge more than the gate.
- **OTF view:** `code` only, so the native verdict doesn't leak.
- **ReAct output:** the run tool returned a record diff. Superseded: decision 4 replaced that tool with a raw sandbox code tool.
- **Disclosure:** that the judges see the question text and the answer.
- **Equal access:** argued explicitly; ReAct with probe tools added as an optional ablation.
- **Cost:** recomputed from measured calls. Caching needs a client change. Row counts were corrected from 1,960 and 1,290 to 1,758 and 1,171 answered rows. Dev spend was cut to a smoke run plus a subset.
- **Client gaps:** stop sequences and the output cap.
- **Scoring:** failures count as `DECLINE`; ties use expected precision; the coverage match is redone inside each bootstrap resample; differences are paired.
- **Dev labeled as non-evidential.**
- **Added:** the program-level LLM judge (Dr. Roy's option A).
- **Third-platform reading:** corrected, with the abstract conflict and the naming check.
