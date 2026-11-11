# ACM Trust 2027 paper: concept and narrative plan

Status: working plan for review (2026-11-11). Written while the main (test) run is still going. Every number below is from **development data** (pilot v1/v1b, dev rescore on the frozen library, planted-program checks). These numbers are guides to what the story will probably look like. They must not appear in the paper as results. Where the main run could change the story, the plan gives the alternative framing.

Sources read: `manifests/design_decisions.md` (D1–D29), `manifests/run_manifest.md`, `manifests/pilot_report.md`, `manifests/blindspots.md`, `manifests/it_blindspot.md` (by reference), `manifests/baseline_judges_design.md`, `manifests/domain_readiness.md`, `manifests/workflow_test_set.md`, `manifests/abstract_draft.md`, `manifests/freeze_v1.md`, `README.md`.

---

## 0. The paper in one paragraph

LLMs can now write simulators of operational processes, and those simulators get reused to answer what-if questions. The usual check asks one question of the program: does it reproduce recorded history? That check covers the **engine** (the dynamics on inputs history already exercised). It does not cover the **steering**: whether a requested change reaches the right inputs, whether the program actually reads those inputs, and whether earlier evidence still holds once the program is reused on new records or a new policy. We present a library that judges trust **per answer, for the specific change requested**. It turns the question into a checked structured request, runs small oracle-free probes chosen by the family of the change, checks that the executed change matches the request, and keeps a per-program record of capabilities that is rechecked on reuse. When it declines, it says why. We compare it against other *trust judges* (platform-native checks, history replay, generic tests, LLM-as-a-judge at answer and program level, and a ReAct agent that can run the program). All judges see the same programs and answers from three generation platforms in four domains, and all are scored against independently checked gold at matched answer coverage.

**Internal tagline** (it matches the repo name; whether it goes in the paper is your call): *checked engine, unchecked steering.*

---

## 1. Framing decisions to lock before drafting

| # | Decision | Recommendation | Why |
|---|---|---|---|
| F1 | What is the unit of trust? | **The answer to one intervention**, not the program. | This is the whole contribution. Every later section has to come back to it. Dr. Roy's distinction (A: is the program correct, B: can this answer be trusted) gives the frame. We do both, but B is the new part. |
| F2 | What are OTF-Tools, DEVS-Gen and the coding agent? | **Hosts / platforms**, never competitors. | D22. The paper never ranks platforms. Platform differences show up only as "the gate works across hosts with different record formats". |
| F3 | What are the baselines? | **Other trust judges** deciding on the same fixed programs, questions and answers. | D22. This keeps the comparison fair and lets every judge be scored at matched coverage. |
| F4 | What counts as success? | **More correct answers kept at the same wrong-acceptance rate** (or fewer wrong answers at the same coverage), with an explanation for each decline, at a stated execution cost. | Rejecting almost everything is not success (D17). Matched coverage stops the gate from winning just by declining. |
| F5 | Where does the paper put declining? | **Selective answering is a feature.** A typed decline routes the question to a fallback (a reading answer or a human). | Dev shows vanilla reading is strong (yield about 0.70 on dev workflow). The "+vanilla" yield column makes declining useful instead of a loss. |
| F6 | Claim strength | **Hypothesis-testing tone. No "first", no "portable", no "guarantees".** | D16 says novelty and benefit are hypotheses, and a null result is reported. Probes are oracle-free and sound on the reference, but they are not complete. |
| F7 | Venue track | EA Track 8 (Operational Boundary Assurance) first, Symposium 5 second. | Already decided in the previous session; still needs your confirmation (see section 8 of this plan). The framing word for Track 8 is **operational boundary**: the gate draws the boundary of what a generated simulator may be trusted to answer. |

**Track 8 vocabulary map** (use these words in the intro and discussion):
- "operational boundary" = the set of (program, family of change, scope) on which evidence supports trust;
- "assurance case" = the evidence record per answer (the probes run, the binding check, the registry state);
- "runtime assurance / monitoring" = the recheck on reuse;
- "graceful degradation" = a typed decline plus a fallback answerer.

---

## 2. Proposed title and abstract

**Title (recommended, from the previous session):** *Beyond Pass or Fail: Checking When LLM-Generated Simulators Can Answer What-If Questions*

Alternatives that fit the "boundary" frame of Track 8:
- *Where a Generated Simulator Stops Being Trustworthy: Per-Intervention Assurance for What-If Answers*
- *Trusting the Answer, Not Just the Program: Intervention-Level Assurance for LLM-Built Simulators*

**Abstract:** keep the registered text (`manifests/abstract_draft.md`) as the base. Its claims and the plan below line up. At submission, update only:
1. the last sentence, replacing "We measure…" with the headline result once the main run is in;
2. one clause naming that declines are typed and can fall back to a reading answer (if F5 is accepted).

Check that every commitment in the registered abstract is covered: three platforms ✔, five builder models ✔ (true through OTF-Tools only, D27), four domains ✔, native checks ✔, LLM-as-a-judge ✔, ReAct agent ✔, the four measures (correct kept, wrong accepted, correct wrongly rejected, cost) ✔.

---

## 3. Narrative arc (the story the reader should come away with)

1. **Setup.** Generated simulators are attractive because they can be reused for many what-if questions without rebuilding them.
2. **Tension.** The usual check (replay history, maybe one pass/fail score) certifies the program, but a what-if answer depends on three more things that replay never exercises.
3. **Evidence that the tension is real** (motivating examples from development, presented as illustrations, not rates):
   - a program that replays history exactly but hardcodes a task's fixed duration, so it ignores any change to it (Haiku Loan b2: 86,400 s hardcoded; replay cannot see it because the value never varies in history);
   - a program that replays exactly and has correct dynamics, but whose native patch step applies a change to one visit across all 17 of a case's work records. The answer is wrong, and in one reuse it was right *only by accident*;
   - programs that fix routing probabilities as constants, so a probability change does nothing.
4. **Idea.** Judge each answer for the change actually being asked about: check the request, probe the family of change on *other* cases (no oracle needed), check that the executed change is the requested one, and remember what each program has been shown to handle.
5. **Test.** Same programs, same questions, same answers; many judges; independent gold; matched coverage.
6. **Finding (to be filled from the main run).** Expected shape from dev, in §7.
7. **Lesson.** Assurance for generated simulators has to sit at the level of the intervention, and its declines must be explainable, because the failures cluster in the steering, not the engine.

---

## 4. Section-by-section plan

Page budget: unknown until the CFP format is confirmed (see section 8 of this plan). The split below assumes an ACM two-column paper of about 10 pages plus references. Rescale proportionally.

### §1 Introduction (≈1 page)

Paragraph plan:
1. **Hook:** LLM-generated simulators are being used for operational what-if analysis (manufacturing, IT operations, business workflows). Reuse is the selling point.
2. **Gap:** current platforms certify a program once, with a single verdict (replay, a fit score, a smoke test). Reusing a program means trusting many *answers*, each about a different change.
3. **Three failure modes**, the conceptual core, each with a one-line example (see §3 above):
   - *Mis-applied change (dynamics):* the program ignores or mis-handles the input being changed;
   - *Mis-attached change (binding/steering):* the change lands on the wrong record, visit, case or pool;
   - *Stale trust (reuse):* evidence gathered on one set of records or one policy is carried to another without rechecking.
4. **Why one pass/fail verdict cannot see them:** replay only exercises inputs that varied in history; it says nothing about the patch step; and it is computed once.
5. **Our approach:** a library that gives a per-answer verdict with typed declines (Caught, Already caught, Untestable, Failed history check, Can't express, Trusted).
6. **Evaluation summary:** 118 programs; three platforms; five builder models; four domains; independent gold; seven judge baselines; matched-coverage scoring.
7. **Contributions** (keep to 3–4 bullets, phrased as what we did, not as superlatives):
   - C1. A failure taxonomy for what-if answers from generated simulators that separates engine errors from steering errors and from reuse errors.
   - C2. An assurance library that decides per intervention, with oracle-free family-directed probes, a post-execution binding check and a capability registry that is rechecked on reuse.
   - C3. A benchmark design with deterministic, independently validated gold over four domains, plus planted-confusion programs to measure each probe's blind spots.
   - C4. A matched-coverage comparison against platform checks, LLM judges and a ReAct agent with the same execution access.

### §2 Problem setting and definitions (≈0.75 page)

Define precisely. Reviewers will judge rigour here.
- **Process document:** front matter (rules, stated policy) plus records per run.
- **Generated program:** executable built by a platform from the document; reads plans, schedules and probabilities as inputs.
- **Intervention (what-if) request:** target, operation, value, units, time, scope. Families per domain:
  - workflow: activity duration, timer delay, routing outcome, routing probability, resource availability, case set;
  - manufacturing: four families (production, timing, capacity, order book; check names against `mlsys_questions_*`);
  - IT: five families (job, failure removal, priority, task request, machine removal).
- **Answer:** the program's output for the queried quantity (case end time, first start, ledger value).
- **Trust judge:** a function from (document view, program, request, optionally the answer) to Trust or Decline. A judge that also gives a confidence can be thresholded.
- **Gold:** the reference outcome under the stated semantics (deterministic realization; D5, D14).
- **Scoring rule A:** an answer counts only if it is Trusted *and* exists (D23).
- **Measures:** coverage, precision among trusted answers, wrong-accepted count, correct-rejected count, yield, yield with fallback, and execution and token cost.

Make clear early that **gold never reaches any judge**, and that probes use only permitted inputs.

### §3 How what-if answers fail (≈1 page). This is the conceptual heart.

Organise by the three failure modes, and for each give: definition, why replay misses it, a dev example, and which component of the library targets it.

| Failure mode | Why history replay misses it | Dev illustration | Library component |
|---|---|---|---|
| Engine error on exercised inputs | It doesn't: replay catches these | Most Ollama-built R1 programs fail replay (native precision gpt-oss 0.28, Gemma 0.42 on dev workflow) | History check (kept, credited) |
| Ignored or hardcoded input | The input never varies in history | Haiku Loan b2 hardcodes 86,400 s; OTF Claude programs with constant route probabilities | Directed input-use witnesses; route-change probe (form b) |
| Change applied to the wrong place or size | Replay never runs the patch step | Sonnet Loan b2: one-visit change applied to all 17 records | Binding check; exact stated-rule checks (D26) |
| Stale evidence under reuse | Replay is computed once per program | Policy-variant set: real change (P) vs harmless rewording (H) | Capability registry keyed by policy fingerprint; recheck on reuse |
| Request itself is unanswerable | Not a program property at all | Unknown target, invalid units, removing the queried case | Contract validator → typed decline |

A small figure works well here: a **2×2 of "replay-exact? × answer right?"**. The off-diagonal cell (replay-exact but wrong) is the paper's premise. Dev screen: 12 of 29 workflow programs replay-exact; 1 program-level case of replay-exact-but-wrong among them (exact 95% CI 0.2%–38%). That number is a **motivating existence proof, not a rate**. Say so explicitly; reviewers will respect it.

> Logical caution: dev shows replay is a *strong* comparator (D17 reading). Do not write the intro as if replay is weak. The claim is that replay is **necessary but not sufficient**, and that what it misses is concentrated in specific families and in the patch step.

### §4 The assurance library (≈2 pages)

Present it as a pipeline per question, with one figure (request → contract → history check → directed probes → execution → binding check → verdict, with the registry on the side).

1. **Structured request and contract** (`request.py`, `contract.py`, `interpret.py`). The interpreter is an LLM and treated as untrusted; the contract rejects unknown targets, ambiguous binding, unsupported operations, invalid units or time, multi-change requests, NaN/inf.
2. **History check** (`replay`): factual replay on the request's run. Credit it as necessary.
3. **Family-directed probes** (`probes.py`, `mlsys.py`). Design principle: *oracle-free metamorphic witnesses*. Change the same target on another case, then check that the witness case reacts and the prefix before the change point does not move; then rule probes that check a stated consequence (route rule, balances, capacity invariants); then a no-op. Two evidence kinds: *reaction* and *rule*. Be explicit that reaction evidence alone cannot tell a correct change from one in the wrong place, which motivated the exact stated-rule checks (D26) and the CPU/memory split (D25, credited to DeMillo & Offutt 1991).
4. **Binding check** (`binding.py`): after execution, diff the inputs record by record; a case-level change must alter exactly one record, for the requested case, target, visit and value. A failed check rejects the answer *even if it equals gold*, so no answer is rewarded for being right by accident.
5. **Capability registry and reuse** (`registry.py`): append-only, keyed by program, adapter, policy fingerprint and family; states failed / untested / tested-under-conditions. A recorded failure blocks the capability everywhere ("Already caught"). Passes are reused only on the same scope; route-probability and worker-change passes are never reused, because they test the request's own values.
6. **Typed declines**: the six terms, with one sentence each. This is what makes the verdict actionable for an operator and is the Track 8 "explainable boundary".
7. **Host adapters**: one generic input format for DEVS-Gen and the coding agent; OTF uses its native patch path plus the binding check. Keep this short. It supports "works across hosts" without claiming portability.

Soundness statement (must be in the paper): on the reference implementation, every probe accepts the reference (0 Caught across all dev and test soundness runs). So the probes are *sound on the reference* under the stated semantics. They are not complete; the reported blind spots are RA-pool, RA-count on used workers, and TP-add.

### §5 Experimental design (≈1.5 pages)

- **Domains and documents:** Loan and Pharmacy (published process models, deterministic realizations; Zenodo record 10435849); manufacturing and IT operations (MLSys documents reused with new questions; overlap disclosed).
- **Gold:** our reference engine plus an independently written checker (workflow); OTF simulator plus independent re-implementation (manufacturing, IT); blind hand checks by separate agents; Prosimos as a factual comparison only.
- **Programs:** 118 in all, built on dev documents only and reused on unseen test records (no test builds). Platforms: OTF-Tools (B0 pinned, native-only; R1 redesigned generation path, disclosed as a named treatment, D15/D16), DEVS-Gen, a plain reason-and-code agent. Builder models: Claude Sonnet and Haiku on all platforms; gpt-oss, Gemma, Qwen on OTF only (D27).
- **Questions:** workflow test 240 (20 per family per process, 1 in 5 no-effect controls); policy-variant set (P and H) for reuse; manufacturing 96 and IT 120 test. Generation rules fixed before any method ran (unknown-target and identity changes excluded, operation-stratified resource questions, undocumented-draw filter).
- **Judges compared:**

  | Judge | Level | Model | Rows |
  |---|---|---|---|
  | Native check | program | — | all |
  | History check (`replay`) | program × run | — | all |
  | Generic tests (budget-matched) | request | — | all |
  | Disagreement with reading answer | answer | Haiku reading | all |
  | LLM judge, answer level | answer | Haiku; + Sonnet, gpt-oss, Gemma, Qwen on shared 150 | ≈3,000 |
  | LLM judge, program level | program × run | Haiku | every program and chapter |
  | ReAct judge (one sandboxed code tool, 8 turns) | answer | Haiku ≈1,000; Ollama ×3 on 150; Sonnet on 50 | subsets |
  | **Ours: `directed`** | request | — (interpreter only) | all |

  Ablations: `schema`, `program_wide`, form (b) with and without the no-switch check, oracle vs interpreted requests.
- **Scoring:** rule A; matched coverage (thresholding confidence-giving judges to directed's coverage, with expected precision over ties); two-level bootstrap (program, then question); per cell (domain × platform × builder × family), never pooled across cohorts; paired differences; matched random refusal as a sanity floor.
- **Studies:**
  - **A**: main judge comparison;
  - **B**: decline attribution (what kind of evidence removed each wrong answer);
  - **C**: reuse (rechecking cost, failure carry-over, same-run reuse, unnecessary invalidation under H);
  - **D**: planted-confusion blind-spot measurement (per probe, per family).
- **Isolation and leakage controls:** builder isolation, sandboxing (bubblewrap with seccomp), judges see only front matter plus one chapter, never gold or native verdicts. One sentence plus a pointer to the artifact.

### §6 Results (≈2 pages). Planned tables and figures, with dev guidance

| Item | Content | What dev suggests (not evidence) |
|---|---|---|
| **Table 1**: main comparison | Per cohort: coverage, precision, wrong accepted, correct rejected, yield, +fallback yield, executions per question, for each judge at matched coverage | OTF Claude workflow: directed about 0.69–0.80 coverage at 0.95–1.00 precision vs native about 0.87–0.90 coverage at 0.82–0.92 precision |
| **Figure 2**: precision–coverage curves | LLM/ReAct judges as curves (thresholded), rule-based judges and directed as points | Will show directly whether directed sits above the judge curves |
| **Table 2**: decline attribution | Wrong answers removed / right answers lost by Caught, Already caught, Untestable, Failed history check, Can't express | Pilot v1 (before form b): most of directed's gain on OTF was *Untestable*, i.e. abstention. v1b: detection (Haiku 22 Caught + 12 Already caught, no right answers lost) |
| **Table 3**: where the gate adds value over replay | Per family and per platform | DEVS-Gen: directed equals replay in precision; coding agent and IT/manufacturing: little or nothing to catch; gains concentrated in OTF workflow (routing probability, binding) |
| **Table 4**: planted confusions | Wrong answers Trusted before and after the exact checks, per confusion | Test diagnostics: to 0 for all confusions except RA-count (18→6), RA-pool (12→12), TP-add (5→5) |
| **Table 5**: reuse (Study C) | Rechecking executions; failure carry-over correctness; invalidation rate under H | Unknown yet; the IT "Already caught" blocking costs coverage on otherwise correct programs (47 dev rows); that is a design choice, reported not tuned |
| **Table 6**: cost | Executions, tokens, dollars and wall time per question, per judge | Directed: a few program executions and no model calls beyond interpretation; LLM judges: about $0.005/row (Haiku), $0.08/row (Sonnet); ReAct often runs no code (12 of 20 smoke rows) |
| Interpretation | Interpreted vs oracle requests | Dev 112/112 and 106/108 exact, so interpretation errors will be a small effect. Say so; don't oversell the contract |

### §7 Discussion (≈0.75 page)

Planned points, each grounded in a result:
1. **Where trust breaks is the steering, not the engine.** If the main run confirms that the gains concentrate where history never varies and in the patch step, this is the headline lesson for platform designers: log the decisions (route events), expose inputs explicitly, and make patches checkable.
2. **Why running the program is not enough.** The ReAct judge has the same execution access. If directed beats it at matched coverage, the gain comes from *which* checks run (family-directed, deterministic, recorded), not from execution access. If not, report that plainly.
3. **The cost of being careful.** On correct programs (IT, manufacturing, coding agent on dev) the gate only costs coverage. Present it as the price of the boundary, made acceptable by fallback answering.
4. **Record formats decide testability.** OTF free-form records keep the exact checks from applying (they become Untestable), while generic event records allow them. This is a concrete recommendation to host platforms.
5. **Operational use:** the typed decline as a routing signal (re-ask, fall back to reading, escalate to a human).

### §8 Threats to validity, limits and disclosures (≈0.75 page). Do not compress this

Reviewers at a trust venue will look here first. List all of the following:
- **Post-hoc method changes:** D19 (labelled exploratory), D21 form (b) and the no-switch check (designed after pilot v1; no-check numbers kept), D24 fixes after the full review, D25/D26 blind-spot checks (designed on dev; **made after seeing test diagnostics from planted programs**, though no real system results were seen). State the freeze date and hash, and that no change was made on test results of real systems.
- **Shared-misreading risk:** Claude models wrote the spec, engine and hand cases; Claude models also build and judge. Mitigations: independent checker, blind agents, Prosimos factual comparison, Ollama-built cohorts. Ashraf's own hand check (state whether it was completed; see section 8 of this plan).
- **Self-judging:** report Claude-judges-Claude and Ollama-judges-Ollama cells separately.
- **Benchmark semantics are conventions** (D12 list: route order decides which cases flip, highest-numbered workers removed, timers ignore calendars, etc.). Gold is exact under *these* semantics.
- **Non-independent builds:** builds of one model on one spec are correlated; bootstrap is clustered at program level, and cells are small.
- **Thin cohorts:** Qwen contributes few programs (D7); gpt-oss ReAct mostly unparsable under the frozen format (report it as a setup failure, not model ability).
- **Coverage of the probes:** reaction evidence's general blind spot; route rule checks routes but not timing after the switch; unresolved RA-pool/RA-count/TP-add.
- **Overlap with MLSys/OTF-Tools work** (manufacturing and IT documents reused): disclosure wording owned by Ashraf (D2).
- **Platform modifications:** R1 (generation fixes), Category 1/2 adapter changes to DEVS-Gen, the IT kind-map fix.
- **Generative AI use statement** (ACM policy): what was written or run by AI agents, and what was checked by humans.

### §9 Related work (≈0.75 page; could also go after §1)

Organise by the question each body of work answers, and end each cluster with how we differ. **Citations below are candidates to verify; none has been checked in this session.** Do not cite any of them before checking that it exists and says what we claim.

| Cluster | What it covers | How we differ | Candidate anchors (verify) |
|---|---|---|---|
| LLM-generated simulators | OTF-Tools, DEVS-Gen, G-Sim and similar program-synthesis-for-simulation systems | They certify programs once; we judge answers per intervention and treat them as hosts | the OTF-Tools paper (own prior work; see overlap note), DEVS-Gen (`czyarl/devs_gen_code`), G-Sim (`samholt/generative-simulations`) |
| Simulation V&V | Classical verification and validation, operational validity, face and historical validation | Classical V&V validates a model for an intended use; we operationalise "intended use" as the single requested intervention and automate it | Sargent's V&V tutorials; Balci |
| Process-mining what-if simulation | Business process simulation from logs (Prosimos, Simod), what-if analysis | They build the simulators; we judge reused LLM-built ones; Prosimos is our factual comparison only | Prosimos / Simod papers (Camargo, Dumas et al.) |
| Metamorphic and constraint-based testing | Oracle-free testing via relations between runs; constraint-based test data generation | Our probes are metamorphic witnesses chosen by intervention family, used as an online trust gate, not an offline test suite | Chen et al. metamorphic testing surveys; DeMillo & Offutt 1991 (already credited in D25); mutation testing (planted confusions are mutation-like) |
| Selective prediction and abstention | Classifiers with a reject option; risk–coverage curves | We borrow the matched-coverage evaluation; our abstention is evidence-based and typed, not confidence-based | Geifman & El-Yaniv (selective classification); Chow's reject option |
| LLM-as-a-judge and agentic verification | Using LLMs to grade outputs; ReAct-style tool use | They are our baselines; we test whether execution access alone explains any gain | Zheng et al. (LLM-as-a-judge); Yao et al. (ReAct) |
| Runtime assurance and operational design domains | Monitors that bound where an autonomous system may act | The registry plus typed declines is a runtime boundary for a generated model | Simplex architecture; ODD literature (fits Track 8) |
| Code-generation evaluation | Pass@k, unit-test-based acceptance, test-suite adequacy | Passing tests on history ≠ correct under unseen interventions; mirrors our replay-exact-but-wrong finding | HumanEval-style evaluation papers; test-adequacy literature |

### §10 Conclusion (≈0.25 page)

Three sentences: what failure modes we named, what the library does, what the matched-coverage comparison showed (from the main run). One sentence on the practical recommendation to platform builders (expose inputs, log decisions, make patches diffable).

### Appendix / artifact

Freeze record and hashes, question generation rules, probe soundness tables, the planted-confusion catalog, judge prompts (prompt hash `ed45fe10bab7c96c`), sandbox description, cost ledger.

---

## 5. Key figures (suggested)

1. **Fig. 1 (intro):** one what-if question flowing through a generated simulator, with the three failure points marked (dynamics, binding, reuse), next to what replay checks.
2. **Fig. 2 (method):** the per-question pipeline with the registry and the six verdict terms.
3. **Fig. 3 (results):** precision–coverage plot per domain, judges as curves, directed as a point with bootstrap intervals.
4. **Fig. 4 (results):** stacked bars of decline attribution per cohort (wrong removed vs right lost by term).

---

## 6. How the narrative should respond to possible main-run outcomes

| Outcome | Headline framing | What changes |
|---|---|---|
| **A.** Directed beats every judge at matched coverage, with gains concentrated in specific families and the patch step | "Per-intervention checks catch what program-level and model-based judges miss" | Story as planned |
| **B.** Directed ≈ replay overall, better only on OTF workflow and planted programs | "History replay does most of the work; per-intervention checks are needed exactly where history is silent" | Lead with the failure taxonomy and the targeted gains; Table 3 becomes the main table; emphasise cost and explanation value |
| **C.** LLM/ReAct judges match directed at matched coverage | "Execution-capable judges can approach rule-based checks, at N× the cost and without explanations" | Shift weight to cost, determinism, typed declines and reuse; report the null honestly (D16) |
| **D.** Directed's gain is mostly Untestable declines (abstention) | Report it as abstention, compare against matched random refusal | Must not be called detection; the D21 history shows how this was diagnosed |

Write §1 and §3 so that they hold under all four outcomes. Only the contribution bullets and §6/§7 should depend on the result.

---

## 7. Logical gaps and risks I see in the current story

1. **Where are the errors to catch?** On dev, the coding-agent, IT, manufacturing and DEVS-Gen programs had few or no wrong answers that replay did not already remove. The gate's added value appears almost only on OTF Claude workflow programs and on planted programs. If test looks the same, the "three failure modes" claim rests on a narrow slice. The paper must say this openly and lean on per-family and per-platform results (outcome B), not a pooled headline.
2. **Planted-program results are the method designer's own construction.** Table 4 is strong evidence of what the probes *can* detect, but it is not evidence of natural failure rates. Keep it in Study D and never pool it with natural programs.
3. **Native-check definition differs by platform.** For OTF, "native" is the platform's patch-and-replay path; for DEVS-Gen, its own smoke test; for the coding agent, it is unclear what "native" means (it has no own check beyond running the example). This needs one sentence of definition per platform, or the coding agent should be dropped from the native column.
4. **R1 is ours, but it is not the method.** R1 changes generation, and the paired comparison uses R1-built programs. Reviewers may read R1 as part of the contribution. It is a named treatment that improves build acceptance, kept separate from the gate. State it in §5 and never credit R1 gains to the library.
5. **Reuse claim depends on Study C, which has no dev result yet.** The abstract says the library "checks that record again whenever the program is reused". If Study C is thin (policy set on Claude programs only), say the reuse evidence is limited to those.
6. **Interpretation is nearly perfect on dev.** The contract validator is part of the method but will barely matter in the results. Do not spend much space on it; present it as a safety component and report the small numbers.
7. **Matched coverage needs judges with confidences.** Native, replay and directed are binary. Make sure the analysis compares binary judges by direct (coverage, precision) points plus matched random refusal, and thresholds only the confidence-giving judges (`scripts/main_analysis.py` appears to handle this; confirm before writing).
8. **"Five language models" is true only through OTF-Tools** (D27). The text must not imply that every platform used all five.
9. **Disclosure of decisions made after test-side diagnostics** (D23 rule A chosen with test counts in view; D25/D26 after planted-program test diagnostics). This is defensible but must be stated in so many words.

---

## 8. Blockers and items that need your input

1. **ACM Trust 2027 format:** page limit, template (acmart sigconf?), anonymity rules, and whether the appendix and artifact count against the limit. I could not find the CFP in the repo; please paste it or confirm. Section lengths above assume about 10 pages.
2. **Track:** confirm EA Track 8 over Symposium 5 for the final submission. The framing vocabulary in §1 depends on it.
3. **Overlap and anonymity (D2):** how to cite OTF-Tools and the MLSys work (own prior work) without breaking double-blind review, and what the overlap disclosure says. This is yours to own.
4. **Title:** pick one of the three in §2.
5. **Missing reference files:** `AGENTS.md`, `RESEARCH_DIRECTION.md`, the Nov 8 meeting notes (`meeting/nov_8_part_1.docx`) and `otf-tools.pdf` are cited by the manifests but are not in this repo. I wrote the plan without them. If they set constraints on framing (for example the exact research question wording), share them and I will align the plan.
6. **Hand check status (D12/D18):** did your own hand check of the workflow semantics happen? The validity section reads much stronger if it did, given the shared-model risk.
7. **D10 (approval at freeze)** is still "Open" in the log. Close it in the log before the paper cites the freeze.
8. **Related work:** none of the candidate citations in §9 have been verified in this session (the literature-search tool was not available). They need checking before use.
9. **Main-run results:** §6 and §7 need the test numbers; the plan marks every place that depends on them.

---

## 9. Drafting order (suggested, given the Nov 15 deadline)

1. Now (no results needed): §2 definitions, §3 failure taxonomy, §4 method, §5 design, §8 threats, §9 related work.
2. When the main run finishes: §6 tables and figures from `scripts/main_analysis.py`, then pick the outcome row in §6 of this plan.
3. Last: §1 contributions, §7 discussion, abstract's final sentence, title.
