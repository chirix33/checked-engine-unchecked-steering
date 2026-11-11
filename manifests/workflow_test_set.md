# Workflow test set: Loan Application and Pharmacy (2026-11-09)

Status (2026-11-09, revised):
- **Accepted by the coordinating session.** Ashraf's decisions (section 8) are applied.
- **Regenerated after the external review:** the test and policy sets were regenerated with stricter validity rules (section 3, rules 4–6). Coverage, checker and blind checks were rerun on the new files.
- **Probe soundness rerun with the coordinating session's final library:** 0 Caught on dev, test and the policy set (section 13).

No paid model calls and no builds. Unchanged: `scripts/pilot_runner.py`, the dev set, the manufacturing and IT files, and `baseline/`. The library changed only as recorded in section 11 (by this task) and in the coordinating session's own fix.

Labels: **Verified** = checked here by running code. **Proposal** = not done. **Decision** = needs Ashraf.

## 1. What was made

| item | file | how |
|---|---|---|
| Test documents | `runs/workflow_docs/workflow_{loan,pharmacy}_test/document.pdf` (+ `document_meta.json`) | `scripts/workflow_test_set.py docs`: the unchanged renderer (`render_workflow_doc.render`, D14 layout, `MIN_VISITS = 3`), 8 runs per process, 15 cases per run |
| Test maps | `runs/workflow_docs/<doc>/navmap.json` | `otf_r1.navmap.build_map` on the PDF, the builder the OTF programs use |
| Split file | `manifests/workflow_splits_v1.json` | `scripts/workflow_test_set.py splits` |
| Questions | `manifests/workflow_questions_test_v1.json`, hashes in `manifests/workflow_questions_test_v1.sha256` | `scripts/make_workflow_test_questions.py test` (seed 20271109) |
| Checker gold | `manifests/workflow_test_checker_v1.json` | `validation/workflow_test_checker.py` |
| Probe soundness | `manifests/probe_soundness_workflow_test_v1.json` | `validation/probe_soundness_workflow_test.py` |
| Blind check | `validation/blind_review_workflow/`, key `validation/blind_review_workflow_key_v1.json`, score `validation/blind_review_workflow/score_v1.json` | `scripts/make_workflow_blind_sample.py`, `validation/score_workflow_blind.py` |

## 2. Runs, seeds and provenance

- **Dev (unchanged):** `workflow_{loan,pharmacy}_dev`, Run 01–04, seeds `dev-loan-01..04`, `dev-pharmacy-01..04` (rendered 2026-11-04, `runs/build_test_v1/docs/`).
- **Test:** `workflow_{loan,pharmacy}_test`, Run 05–12, seeds `test-loan-05..12`, `test-pharmacy-05..12`.
- **Provenance group = the run.** Each run is one independent deterministic realization with its own seed, so the split is by full run. All runs of a process share the published process model and the front matter. That is the reuse condition: dev-built programs answer test questions on test records.
- **Chapter titles continue the dev numbering (Run 05–12).** The library keys evidence reuse by scope title. If dev and test shared titles, dev evidence on "Run 01" would be reused as if it were test evidence.
- **Byte reproducibility.** The PDFs are rendered in reportlab `invariant` mode, which fixes the timestamp and file id only; layout and text are the renderer's own. Two renders give identical bytes (Verified). Without it, the dev documents re-render with identical content (identical map, apart from `document_id`) but different bytes (Verified).

**Verified (`workflow_splits_v1.json`):**
- Seeds and titles are disjoint from dev. The process model files (BPMN, JSON) are byte-identical between dev and test.
- All seven printed sections of every dev and test run equal the reference's factual run for that seed.
- The stored maps equal `build_map` rerun on the PDFs, for dev and test.
- Overlap with dev: 0 identical tables in any section. The few identical rows are published constants (the fixed 86 400 s "Applicant completes form", the 1 s Pharmacy system tasks) and coincidental short values from narrow Pharmacy distributions, plus first tasks of `c0000` at opening time. None are route draws.
- **What existing programs read:** 58 stored workflow maps under `runs/` (48 OTF programs: B0 and R1 Ollama, R1 Claude Sonnet and Haiku, 3 builds each per document; plus 10 intervention-probe maps). Every program's map equals a dev map exactly. Every map holds dev chapters only. No map or program code names a test chapter or a test seed.
- **Spec-built platforms** (DEVS-Gen, plain coding agent): the 10 files under `adapters/devs_gen_tasks/Workflow*` and `adapters/generic_tasks/Workflow*` name no test chapter or seed, and share no route draw with any test run. Their programs are built from these files only. No coding-agent workflow builds exist in this checkout at the time of the check.

**Hashes (sha256):**

| file | sha256 |
|---|---|
| `runs/workflow_docs/workflow_loan_test/document.pdf` | `354d4847a9a791b4a6982698623b4634ad2cf27a7276731e867ae09d04346299` |
| `runs/workflow_docs/workflow_pharmacy_test/document.pdf` | `e4888ad6efad987dd2fa0d2c9c815044c34861f67e3911bdc66d4654f815f00f` |
| `runs/workflow_docs/workflow_loan_test/navmap.json` | `5ecbd0c5a854e1c3c03ac7eac2300698cc8744d979cb12da127e0510a331a933` |
| `runs/workflow_docs/workflow_pharmacy_test/navmap.json` | `9c3e80c3c0775eb2ffdbbafa5456d6db45841f6e71e728f737fd144b91d26980` |

Dev PDFs, dev maps and model files are hashed in the split file. All hashes for this set are in `manifests/workflow_questions_test_v1.sha256`; `sha256sum -c` passes. That file also hashes the dev exclusion list `manifests/pilot_excluded_v1.json`.

`runs/` is git-ignored (`.gitignore`, owned by Ashraf), so the test PDFs, maps and the DEVS-Gen scan are not tracked. The MLSys documents are in the same position. `workflow_test_set.py docs` regenerates them byte for byte.

**Kept from builders.** `document_meta.json` beside each test PDF lists the seeds. With the reference's draw rule, those give every draw. No runner reads it, but it must not be handed to a builder or agent. Builds still to come (coding agent, more DEVS-Gen or OTF) happen while the test PDFs and gold sit in this checkout, and DEVS-Gen generation can see `/mnt/c`. **Adopted (Ashraf, 2026-11-09):** builders see none of this. The path list and check are in `manifests/builder_isolation.md` and section 12. After every build, rerun `patterns`, `scripts/wsl_scan_workflow_programs.sh` and `splits`.

## 3. Questions

`manifests/workflow_questions_test_v1.json`: **240 questions, 120 per process, 20 per family**, with 4 no-effect controls per family per process (48 in all, one in five). Seed 20271109. Every test run is used (8 to 23 questions per run). Regenerated after the external reviews with rules 4–7 below.

**Generator.** `scripts/make_workflow_test_questions.py` reuses `make_pilot_questions.draft` and `undocumented_draws` and replicates its selection loop, with documents, runs, size and id as parameters. `make_pilot_questions.py` is unchanged. Proof that the loop equals the dev generator (Verified, and rerun by the reviewer):
- `regen-dev 20261107` (filter off, as when the dev set was made) reproduces `pilot_questions_v1.json` byte for byte (`7f0d560d…`, the hash in `pilot_questions_v1.sha256`). The dev seed 20261107 was not recorded anywhere before; it was found this way.
- `regen-dev-filtered 20261107` is byte-identical to `make_pilot_questions.py . out 10 20261107` (`2f81ac6f…`).
- `test` twice gives byte-identical output (`fe754f44…`; the version before rules 4–7 was `b5fb5bec…`). The file is written with LF endings, so the hash does not depend on the platform.

**Rules added for test only** (disclosed here, in the generator's docstring and in the run manifest; fixed before any method ran on these questions, and none looks at a program):
1. An exact repeat of a kept question (same run, change and query case) is skipped. Without this rule, the test draw had 7 repeats; the dev set has 3.
2. The try cap per family is 2000 instead of 400. With repeats skipped, Pharmacy routing_outcome reached only 17 within 400 tries; it needs 559.
3. When only part of a pool is unavailable, the text names the workers, e.g. "1 Appraiser worker (Appraiser_1)". The front matter does not say which workers a count means. Gold, `DEVSBackend.apply` and the resource probe all use the highest-numbered ones. This changes the text of 9 questions in the final file (10 in the earlier one) and nothing else. It was found by blind agent B. **The dev set keeps the ambiguity in 4 valid questions** (`loa-resource_availability-04`, `-08`, `-09`, `pha-resource_availability-08`). Report it; the dev set is not edited.

Added after the external review and a second generator review (2026-11-09; `rule_skip` and `rules=True`; off for the dev set, whose regeneration checks above still give the same bytes):

4. **No unknown-target controls.** An activity-duration change must be at a visit the case actually makes in the factual run.
   - The draft sometimes uses visit + 2, which never happens. That is an unknown-target request, not a no-effect change: `RESEARCH_DIRECTION.md` treats them as different failures.
   - In the earlier file (`b5fb5bec…`) it affected 6 of the 8 activity-duration controls (`loa-test-activity_duration-05`, `-07`, `-08`; `pha-test-activity_duration-06`, `-08`, `-12`). They included the 5 controls the generic input could not express.
5. **No identity changes.** A change equal to the factual work or wait at that visit, or to the published route probabilities, is skipped.
   - Example: `loa-test-routing_probability-03` set D2 to its published 0.5/0.5.
   - Most other identity drafts are 1-second work on Pharmacy's 1-second system tasks.
6. **resource_availability is stratified by operation** (added workers, unavailable workers). During the first half of the tries, each operation gets half the family's questions and half its controls; the quotas then lift. This gives both wordings the same control rate.
   - The first version of this rule balanced only the controls. The second generator review showed that the wording still predicted the label: Loan, P(control | more workers) 2/5 against 2/15 for unavailable.
   - In the earlier file, Loan "unavailable" was never a control (0 of 13).
7. **No trivial worker controls.** An "unavailable" change whose workers do no task in the factual run cannot change anything, so it is skipped. The reviewer's example: Applicant_18 and Applicant_19 of 20.

**Drafts skipped by rules 4–7** (counted by the generator, including the rule 6 quota):

| process | unreached visit | identity | unused workers | operation quota |
|---|---|---|---|---|
| Loan | 4 | 6 (route probability) | 26 | 19 |
| Pharmacy | 7 | 6 (activity) | 0 | 4 |

**resource_availability per operation**, per process (the same for both):

| op | controls | effectful |
|---|---|---|
| more workers | 2 | 8 |
| unavailable | 2 | 8 |

**What changed for anyone joining earlier results.**
- The final file is `fe754f44…`; the earlier one was `b5fb5bec…`.
- 147 of the 240 earlier questions survive by content. Only 116 keep both id and content.
- Ids are positional, so an earlier id can now name a different question. The map is `manifests/workflow_questions_test_v1.idmap_b5fb5bec.json`; join earlier results only through it.
- The checker, probe-soundness and blind-key files now record the sha256 of the questions file they used.
- The probe-soundness file in the repo was made on the earlier question file, so it is superseded (section 5).

**Dev set notes (not edited; report separately).**
- `pha-activity_duration-03` and `-04` are unknown-target requests by rule 4: no-effect controls at visits the case never makes. Report them apart from no-effect controls. No dev question is an identity change.
- After the 8 exclusions, three exact duplicate pairs remain:
  - `loa-resource_availability-04` and `-08`;
  - `loa-case_set-04` and `-08`;
  - `pha-case_set-03` and `-06`.
- Dev Loan routing_probability has only 4 valid questions, since 6 of its 10 are excluded.
- The 4 dev questions with the partial-pool ambiguity are listed under rule 3.

**Fields.** Every field of `pilot_questions_v1.json` (id, doc, scope, family, gold, factual_end, effectful, question, text, interventions, query_case, binding, and draw_overrides for routing_outcome), plus `domain`, `split`, `seen_at_build` and `query`, as in the manufacturing and IT file. Ids are `loa-test-<family>-NN` and `pha-test-<family>-NN`, so they never collide with dev ids.

## 4. Checks (all Verified on the final file)

| check | result |
|---|---|
| `validation/question_draw_coverage.py` (generator's rule; now also resolves test documents, and exits 2 on an empty file) | **0 of 240** fail. On the dev file it still flags exactly the 8 questions in `pilot_excluded_v1.json` |
| Independent checker, `validation/workflow_test_checker.py`, A: same scenario | **240 of 240**: whole output (cases, tasks, timers, branches, draws) identical to the engine, and query end = gold |
| B: printed 6-decimal route draws in place of the seed's | **240 of 240** agree with gold: rounding of route draws decides no answer |
| C: every value the checker used is printed (from the checker's own output) | **240 of 240**. On the dev file C flags exactly the 8 excluded questions, so it discriminates |
| Factual runs, both forms, against the printed Cases | **32 of 32** |
| Also on the dev file (not required) | A agrees with gold on **120 of 120** dev questions, the first per-question checker re-derivation of dev gold |
| Workflow offline tests, `scripts/test_assurance_offline.py` | **0 failures** |
| Blind check (section 6) | **24 of 24** on the final sample (agents K and L). Earlier samples: 24 of 24 (G, H) and 24 of 24 (A, B) |

## 5. Probe soundness on the test documents

**Superseded:** this section describes the earlier question file (`b5fb5bec…`) with the library before the coordinating session's fix. It is rerun on the regenerated files after that fix lands; the result is recorded in section 13.

`validation/probe_soundness_workflow_test.py`, giving `manifests/probe_soundness_workflow_test_v1.json`. **0 rejections of the reference.**

**Part 1: the four existing checks, rerun on test runs.** They use those scripts' own wrappers and helpers; their files are unchanged.

| check | test result |
|---|---|
| route rule | 368 cases, **0 rejections**, 8 not run, 16 changes the reference cannot run (all probability on a loop) |
| route records, form (b) | 408 cases per record shape (free-form and events), **0 rejections** |
| route-flip witnesses | 878 flips: 0 fail to run, 0 leave the case unchanged. **2 need visits the document does not print** (Loan Run 07 `c0013` D2 visit 1; Run 12 `c0005` D2 visit 1). Dev has 0 |
| added workers | 144 cases, **0 rejections** |

**Part 2: the full decision, with the reference run as a program.** The reference reads the generic stdin input built from the test document (`DEVSBackend.stdin_from_map` and `apply`, the input a DEVS-Gen or coding-agent program gets) and prints the generic output records. It was run in two record shapes: with decision events (route probability goes to the rule probe) and without them (form (b), as for OTF records). Requests are the questions' hidden bindings (`pilot_runner.oracle_request`), with budget 3, seed 0 and a fresh registry per document.
- After review, the wrapper fails a run if the engine used any work, wait or route value the input does not give, if the input adds a case or changes an arrival, or if the input has a key the wrapper does not read. **0 such runs.**
- Each shape gave the same results:

| | result |
|---|---|
| history check, all 16 runs | 0 failures |
| directed | **236 Trusted, 4 Untestable, 0 Caught, 0 Already caught.** The 4 Untestable are Pharmacy routing_outcome: no witness, the no-op passed |
| generic, program_wide | 240 Trusted each |
| answer equals gold | **235 of 235** expressible questions |
| no answer on the generic-input path | **5**, all no-effect controls at a visit with no plan column: `loa-test-activity_duration-07`, `-08`; `pha-test-activity_duration-06`, `-08`, `-12`. `pilot_runner` records these as "inexpressible". The dev set has 4 like them |
| decisions whose evidence used one of the 2 deep witnesses | 0 |

**Limits to report:**
- **Trusted but not executable.** Directed Trusts the 5 inexpressible controls through witness evidence, while the structured path cannot run them. For DEVS-Gen and the coding agent, these 5 of 48 controls are Trusted but give no answer.
  - **Decided (Ashraf, 2026-11-09): option A, a scoring rule.** A question counts as answered only if it is Trusted **and** an answer exists. Otherwise it is recorded as Can't express.
  - The rule applies to every judge and every domain.
  - There is no library change: `decide` is unchanged.
  - The coordinating session applies the rule in `pilot_summary.py` and the runner, which it owns.
- **Deep witnesses.** The 2 witnesses that need unprinted visits could make a correct, document-only program fail an input-use probe if one is drawn. None was drawn here; other programs or seeds could draw one.
- **What "no rejection" covers.** It is about the reference only. Whether the probes catch broken programs on test documents was not rerun here; the dev pilot and the offline tests cover that.

## 6. Blind sampled check

- **Sample** (`scripts/make_workflow_blind_sample.py`, seed 20271109): 1 question per family per process, 12 in all. One is a no-effect control (`pha-test-routing_outcome-17`).
- **Inputs:** the front matter and the full chapter text for the 9 chapters used, extracted from the test PDFs, in one folder per agent outside the repo. No gold, binding, change dict, seed or code was given.
- **Method (as for IT):** each agent wrote its own simulator from the front matter, reproduced the printed records, then answered. That makes a further independent implementation.
- **Agents:** A on Opus, B on Sonnet, started separately.
- **Result:**
  - Both agents reproduced every case end and every Task log, Wait log and Decision log row of all 9 chapters.
  - **12 of 12 match gold for each agent (24 of 24).**
  - Reproduction is the agents' own claim. Their simulators and notes are in `validation/blind_review_workflow/agent_{A,B}/`.
- **Score:** `validation/score_workflow_blind.py` compares answers as numbers and refuses to score if the questions file's sha256 differs from the one recorded in the key.
- **Incident:** the first sample cut every chapter after the Cases table. A chapter's map node spans only its heading page. Agent B stopped and reported it. The fix uses page ranges from one chapter heading to the next and asserts that all seven sections are present. Both agents redid the work on complete files; agent A discarded what it had parsed. The regenerated inputs were byte-identical to what the agents used. That applies to the earlier question file; the final file has its own sample (below).
- **Agent readings worth recording:**
  - The Applicant's "00:00 to 23:59" leaves a 60-second gap each midnight (the records confirm it).
  - In W11 a changed route probability applies to every case, so other cases' routes change and delay the query case by 37 s. Agent A reported this.
  - Agent B's reading of "N workers unavailable" was the lowest-numbered N; it did not matter for its 2 whole-pool questions. This led to rule 3 in section 3.

- **After the first regeneration** (intermediate file `110fac52…`, rules 4–6 without the full stratification): the same seed drew a sample with 3 of 12 questions changed. Two fresh agents redid it: G (Opus) and H (Sonnet), in `validation/blind_review_workflow_v2/`.
  - Both reproduced all 9 chapters and matched gold on **12 of 12 each**.
  - The earlier A/B sample remains in `validation/blind_review_workflow/` with its score.
- **On the final file** (`fe754f44…`): 6 of 12 sampled questions changed again. Two fresh agents, K (Opus) and L (Sonnet), redid it in `validation/blind_review_workflow_v3/`. Result: both reproduced all 9 chapters and matched gold on **12 of 12 each** (24 of 24). Agent L wrote no notes file; its answers and code are kept. The key `validation/blind_review_workflow_key_v1.json` describes this final sample, with input hashes.

## 7. Reviews

- **Reviewer:** one separate reviewer agent (Opus).
- **Reran and confirmed:** the dev regeneration claims, test reproducibility, the coverage, checker and splits results, the re-render, the blind page-range fix and the soundness result.
- **Findings and what was done:**
  1. **Checker form B did not show derivability.** It agreed on all 8 known non-derivable dev questions. Added form C, which reads the checker's own output, and reworded B. **Fixed.**
  2. **Dev and test policy fingerprints differ** (section 8). **Reported**; a library change.
  3. **The program-input check covered only OTF maps and spec files**, silently skipped the DEVS-Gen config (a JSON list), and passed on zero maps. Fixed:
     - JSON is parsed recursively, so the config's 255 and 165 route draws are all dev Run 01 and none is test.
     - A WSL scan (`scripts/wsl_scan_workflow_programs.sh`) of all 13 DEVS-Gen workflow run folders finds 0 test titles, 0 seeds and 0 test-only route draws. 11 of the 13 folders hold a built program (`run.py`); Haiku Loan `run_01` and `run_04` do not. The patterns now also cover the policy variants (5,497 strings).
     - It now fails on any empty input.
     - Hiding test files from future builders was adopted (section 12).
  4. **The 5 inexpressible controls are Trusted.** **Reported** (section 5).
  5. **The factual check covered 2 of 7 sections.** All seven are now compared with the renderer's tables for every dev and test run. **Fixed.**
  6. **The reference wrapper could fall back to seed values unnoticed.** It now fails such runs, with 0 found. **Fixed.**
  7. **Blind scoring**: numeric comparison and the questions hash in the key were **fixed**. Agent reproduction stays self-reported, with code kept.
  8. **Smaller items, fixed or disclosed:**
     - `titles_disjoint` now compares the maps;
     - the seeds in `document_meta.json` are disclosed (section 2);
     - the test-only rules are disclosed (section 3);
     - `register()` documents that it changes `rs.DOCS` for the process.
- **Every changed script was rerun after the fixes.**

## 8. Decisions (Ashraf, 2026-11-09)

1. **Dev evidence did not carry over to test documents. Decided: option (a), done (section 11).**
   - Before the fix, `ProcessSchema.policy_fingerprint` hashed the whole front matter, including "Chapters in this document: Run …", so dev and test fingerprints differed. Since the fingerprint is in the registry key, a capability failure recorded on dev never blocked on test.
   - It now drops that closing line, as `mlsys.py` does. Dev and test share one fingerprint per process.
2. **The 5 inexpressible no-effect controls** (section 5). **Decided (Ashraf, 2026-11-09): option A, a scoring rule.**
   - A question counts as answered only if it is Trusted and an answer exists; otherwise it is Can't express.
   - The rule applies to every judge and domain.
   - No library or `decide` change; the coordinating session applies it in `pilot_summary.py` and the runner.
3. **Policy-variant reuse. Decided: add it, workflows only, as proposed. Done (section 10).**
4. **Hide test material from builders. Adopted (section 12).**

## 9. Policy-variant reuse: what existed, and the design proposed (kept as written; implemented in section 10)

**What exists (Verified).**
- No question file in any domain has a policy-variant reuse question. This covers `pilot_questions_v1`, `mlsys_questions_{dev,test}_v1` and `workflow_questions_test_v1`: 0 of 684.
- The only policy-change reuse case run so far is one plumbing case in the Nov 7 slice: Loan Clerk 9 to 10, on two programs (`run_manifest.md`, "Minimal end-to-end slice").
- `RESEARCH_DIRECTION.md` section C lists four reuse conditions, which apply to every domain:
  1. new records, same policy;
  2. same policy, different workload;
  3. changed policy with the same table structure;
  4. harmless paraphrase.

  It calls for a fingerprint-invalidation baseline and a separate count for "reused-policy variants".
- The abstract says programs can "stop being valid when reused under a new policy". **Today only condition 1 is tested.**

**Smallest design (workflows only; the policy is the front matter, rendered from the model JSON).**
- **Variants.** Each process gets two variants, stated in the front matter (runtime-visible, as section C requires):
  - **P (changed policy, same tables):** the bottleneck pool's worker count changes in the model JSON. Loan Appraiser goes from 2 to 3; Pharmacy Pharmacist from 1 to 2.
  - **H (harmless rewrite):** the same policy with the front-matter sentences reworded or reordered, generated by a fixed script.

  The test documents already act as a natural H for the fingerprint, since only the chapter list differs.
- **Records.** 2 new runs per variant (Run 13–14, new seeds), rendered by the unchanged renderer from a params copy. Gold comes from the engine on that params file, with checker forms A, B and C and the coverage check.
- **Questions.** The same generator, 4 per family per variant per process (1 no-effect each). That is 6 × 4 × 2 variants × 2 processes = **96 questions**, reported separately, as `RESEARCH_DIRECTION.md` asks.
- **What it measures.** Dev-built programs reused on P and H, under four regimes:
  1. carry the dev capability record unchanged;
  2. factual recheck only;
  3. per-family recheck (directed);
  4. fingerprint invalidation.

  Count missed invalidations on P (a program that hard-codes 2 Appraisers fails history or answers wrongly) and unnecessary invalidations on H.
- **Depends on decision 8.1.** Without it, the fingerprint already invalidates on every document.
- **Cost.**
  - No builds and no paid calls to make the set. About 5 hours: params and front-matter variants 1, generation and checks 1.5, probe soundness 0.5, review and fixes 1.5, write-up 0.5.
  - **Run-time cost** is the runner's per-question calls: the interpreter on Haiku and, for OTF, the native patch. That is 96 more questions per program, about 40% of the workflow test set. The ledger rate per question is in `baseline_judges_design.md` and has not been recomputed here.
- **Scope note.** Workflows only keeps this inside the agreed domains. A manufacturing variant (a capacity rule change) would need an MLSys generator change and is not proposed.

## 10. Policy-variant reuse set (built 2026-11-09, after Ashraf's decision)

**Variants** (`scripts/workflow_policy_set.py`; documents in `runs/workflow_docs/workflow_{loan,pharmacy}_policy{P,H}/`; check file `manifests/workflow_policy_check_v1.json`):

| variant | change | runs, seeds | fingerprint vs dev |
|---|---|---|---|
| P, changed policy, same tables | Loan Appraiser 2 → 3; Pharmacy Pharmacist 1 → 2 (one `amount` in a copy of the published JSON) | Run 13–14, `policyP-<process>-13..14` | differs (correct: the policy changed) |
| H, harmless rewording | none: same parameter file, byte-equal to the published one; the front-matter prose is reworded by the fixed table `REWORD` (24 sentences) | Run 15–16, `policyH-<process>-15..16` | **differs**, an unnecessary invalidation |

- **Run titles.** P uses Runs 13–14 and H uses Runs 15–16, not one shared pair. Evidence reuse is keyed by run title, so if a regime ignores the fingerprint, a shared title would let P evidence stand for H. Titles are unique per process across dev, test, P and H.
- **Rendering.** The renderer is unchanged. For P it reads the variant parameter file through a copied model folder. For H, `render.intro` is wrapped so that each `REWORD` pair replaces exactly one sentence of the renderer's own text.

**Verified (`check`):**
- **P:** exactly the one pool count differs. Arrivals, calendars, durations, waits, routing and task pools are all equal to the published model. The front matter differs from dev only in that pool's line and in the chapter list.
- **H:** no parameter differs, and everything the library reads from the front matter is equal to dev: pools, calendars, stated routes and probabilities, activities, waits and decisions. Only the reworded sentences and the chapter list differ.
- Every printed section of every variant run equals the reference's factual run under that variant's own parameters. The maps equal `build_map` rerun on each PDF. The PDFs are byte-reproducible.
- **H changes no rule:**
  - The second reviewer read all 24 pairs and found two slight shifts: in rule 2 ("If several can", which could be read as letting free-for-longest decide before earliest start) and in the log descriptions. Both were reworded and H re-rendered. P was not re-rendered and is byte-unchanged.
  - Four blind agents reproduced every H chapter from the H text alone (see the blind check below).
- **Fingerprints after the section 11 fix:**

  | process | dev = test | P | H |
  |---|---|---|---|
  | Loan | `78b0ef97…` | `3c4f8656…` | differs from dev |
  | Pharmacy | `eaadfaae…` | `11d8de7b…` | differs from dev |

  H looks like a new policy to the fingerprint, although the blind agents found its rules unchanged. That is the "unnecessary invalidation" case the design measures. The fingerprint was not tuned to make H pass.

**Questions** (`scripts/make_workflow_policy_questions.py`, seed 20271110, giving `manifests/workflow_questions_policy_v1.json`; hashes in `manifests/workflow_questions_policy_v1.sha256`):
- **91 questions, not the planned 96.** 22 are no-effect controls.
  - The file is byte-reproducible (`fc79f0db…`; it was `9a2b863b…` before rules 4–7). It was regenerated with rules 4–7 of section 3.
  - 53 of the earlier 91 questions survive by content, and 48 keep both id and content (map: `manifests/workflow_questions_policy_v1.idmap_9a2b863b.json`). 6 questions name the unavailable workers.
  - Drafts skipped by the rules: 30 unreached-visit and 30 identity activity changes; 2 identity route-probability changes; 86 unused-worker changes; 103 operation-quota skips.
  - The policy set had the same unknown-target problem: `loa-polP-activity_duration-00`, `pha-polP-activity_duration-02` and `loa-polH-activity_duration-02` were controls at unreached visits. All are gone.
  - **Worker changes by operation:**
    - Each document has 2 "more workers" and 2 "unavailable" questions. Its one control uses a fixed operation (`CONTROL_OP`): more workers for Loan P and Pharmacy H, unavailable for Pharmacy P and Loan H.
    - Exception: in Loan P no "more workers" change has an effect, because the third Appraiser removes the queue. That document has 1 "more workers" control and 3 "unavailable" effectful questions.
    - Overall: more workers 2 controls and 5 effectful; unavailable 2 controls and 7 effectful.
- **Generator:** the test generator (`generate`) with all its rules (section 3, rules 1–7): repeats skipped, a cap of 2000 tries, workers named when only part of a pool is unavailable, and rules 4–7. Fields are the test file's plus `variant`, with `split` set to "policy". Ids are `loa-polP-…`, `pha-polH-…` and so on.
- **The shortfall of 5 is proven unavoidable on the decided runs.** The proof is `manifests/workflow_questions_policy_v1.shortfalls.json`: an exhaustive enumeration of the draft's whole candidate space, using the same realization filter, confirmed by the reviewer.
  - **Loan P case removal:** with 3 Appraisers, no removal changes any other case's end on Runs 13–14 (0 effectful of 420 candidates). The cell has its 1 no-effect control only, so 3 questions are missing. That is itself a result: the extra Appraiser removes the contention through which a removal acts.
  - **Pharmacy P and Pharmacy H timer changes:** every possible wait change moves the case's end (270 of 270 effectful), so each cell has 3 effectful questions and no control. 2 questions are missing.
  - Runs were not re-chosen to create the missing kinds; that would select data by outcome.
- **Checks:** realization coverage 0 of 91 fail. Independent checker forms A, B and C 91 of 91 each, with 16 of 16 factual runs (`manifests/workflow_policy_checker_v1.json`). The checker reads the variant parameter file; P chapters use Appraiser_2.

**Probe soundness on the variants** (`manifests/probe_soundness_workflow_policy_v1.json`): **superseded.** What follows describes the earlier policy file (`9a2b863b…`) with the library before the coordinating session's fix. It was **not clean**; the rerun is in section 13.

| check | result |
|---|---|
| route rule, route records (both shapes), added workers | 0 rejections |
| route-flip witnesses | 425 flips: 3 need unprinted visits (Loan H Run 16 `c0008` D4; Loan P Run 13 `c0014` D4; Loan P Run 14 `c0011` D2), and 1 changes only decision records (Pharmacy P Run 13 `c0010` D7 visit 1) |
| directed, with decision events | 89 Trusted, **2 Caught** |
| directed, without decision events | 88 Trusted, **3 Caught** |
| generic, program_wide | 91 Trusted |
| history check | 0 failures |
| answers equal to gold | 90 of 90 expressible (1 inexpressible no-effect control) |

The reference is **Caught as a correct program** on these questions:
- **`loa-polP-routing_outcome-00` and `-01`, both shapes: deep witness.** The input-use witness flips a route that sends the case into loop visits the document does not print (for example `c0014` D3 visit 5). A program that reads only the document lacks those draws. The wrapper refuses to fill them from the seed, so the witness run fails.
  - The test set has 2 such witnesses, but none was drawn there. Here they are drawn.
- **`pha-polP-routing_outcome-03`, no decision events only: zero-time witness.** Flipping D7 for `c0010` sends it straight to W3 instead of looping back through decision D6, which then also goes to W3. Tasks, waits and the end are unchanged; only decision records differ. A program whose records name no decisions, such as OTF records, therefore "changed nothing" and is Caught.
  - Part 1 now checks for this (`case_unchanged_without_decisions`): 0 on the test set, 1 here.

Both are gaps in the library's witness choice (`assurance/probes.py` `witnesses` and `perturb`), not in the questions: gold is correct, and four blind agents confirm it. The library may not be changed here, so this is **for decision**:
- (a) A library fix: skip route-flip witnesses whose flipped route can re-enter a loop or reaches the same next step through zero-time decisions. A probe change, to disclose, made after seeing variant data. It would need a soundness rerun on dev, test and the variants.
- (b) Keep the library and report it as measured probe unsoundness: 2 or 3 of 91 variant questions, 0 of 240 test, 0 of 112 dev. It would affect every program on those questions.
- (c) Drop the 3 affected questions. **Not recommended**: it hides a probe defect behind question selection.

**Blind check** (`validation/blind_review_workflow_policy/`, key `validation/blind_review_workflow_policy_key_v1.json`, seed 20271110):
- **Sample:** 1 question per family per variant document, 24 in all, over all 8 variant chapters, each with its own document's front matter. The key now records sha256 hashes of every input file and of the questions file.
- **First wording:** agents C (Opus) and D (Sonnet) reproduced all 8 chapters and matched gold on **24 of 24 each**. Both found no rule change in H, only the stated pool counts in P.
- **Corrected H wording:** two fresh agents, E (Opus) and F (Sonnet), redid the sample. Result: both reproduced all 8 chapters and matched gold on **24 of 24 each**. Both compared the front matters word by word and found no rule change in H. Agent E also reran each chapter with the other variant's worker counts: none reproduced. Files: `validation/blind_review_workflow_policy_v2/`.
- **In all, 96 of 96 answers match gold** over four agents, on the earlier question file.
- **After the first regeneration** (intermediate file `42955840…`), the same seed drew a sample with 10 of 24 questions changed. Two fresh agents redid it: I (Opus) and J (Sonnet), in `validation/blind_review_workflow_policy_v3/`.
  - Both reproduced all 8 chapters and matched gold on **24 of 24 each**.
  - Both found no rule change in H.
- **On the final file** (`fc79f0db…`): 4 of 24 sampled questions changed. Two fresh agents, M (Opus) and N (Sonnet), redid it in `validation/blind_review_workflow_policy_v4/`. Result: both reproduced all 8 chapters, found no rule change in H, and matched gold on **24 of 24 each** (48 of 48). The key file describes this final sample.
- **Note:** the agents' sessions start with the harness's project context (`AGENTS.md`, git status). That holds no gold or code, and agent C recorded it. The earlier blind agents had the same context.

## 11. Library change: policy fingerprint (Ashraf, 2026-11-09; made after the development pilot)

**Change.** `ProcessSchema.policy_fingerprint` (`assurance/request.py`) now drops the closing chapter list before hashing. It is anchored after review: only an exact "Chapters in this document: Run NN, …, Run NN." at the very end is dropped, so text after it, or an earlier mention, still counts as policy. This is the only library change in this task. (`mlsys.py:144` uses the looser `Chapters in this document.*$`; it was not changed here.)

**No dev pilot decision changes (Verified):**
- **Code argument:**
  - The fingerprint is used only in the registry key (`policy.py:119`). It is not in evidence text or in the request seed.
  - All requests on one document share one schema, so every key in a run changes by the same constant. Registry lookups compare keys for equality, so they give the same results.
  - Dev Loan and Pharmacy still differ, and no pilot run mixes documents.
  - The reviewer confirmed this argument.
- **Real pilot rows re-decided** (`validation/fingerprint_redecide.py`, no model calls):
  - **Programs:** 5 dev OTF programs, run before and after the edit: R1 Sonnet Loan b2, R1 Haiku Loan b2 (the case C program, whose directed declines use the registry), R1 Sonnet Pharmacy b1, R1 Haiku Pharmacy b2, and R1 gpt-oss Loan b1 (fails the history check).
  - **Scope:** every valid dev question, both request sources (stored interpreted requests and oracle requests), and replay, schema, generic, directed and program_wide.
  - **Result: 0 of 554 rows differ (2,770 decisions).**
  - The before decisions also equal the stored pilot v1 and v1b decisions for these 5 programs (reviewer).
  - Outputs: `runs/fingerprint_check_v1/`.
- **Reference run as a program on the 112 valid dev questions:** the before and after outputs are byte-identical. The test-set soundness rerun after the change is identical too, with 0 blockers.
- **Offline tests:** 0 failures, both workflow and mlsys. New workflow checks:
  - another chapter list, or none, gives the same fingerprint (with a guard that the edit really happened);
  - text after the list counts;
  - a worker-count edit and a route-probability edit change it;
  - Loan and Pharmacy differ.

**Fingerprints now:**
- Dev = test for both processes: Loan `78b0ef97…`, Pharmacy `eaadfaae…`.
- All 48 OTF build maps of each dev document give the dev value.
- A real policy change still changes it: P, and the library's own pool and route edits.

**Old registries.** `runs/pilot_v1*/registries/` hold the old values (`999d74c2…` Loan, `8a4f8e6a…` Pharmacy). No current script reads them for reuse, but `pilot_runner.py` appends to them on resume, and any dev-to-test carry-over seeded from them would match nothing. **For the runner's owner:**
- do not seed test or variant reuse from the pilot registries; build dev evidence afresh, or migrate with a recorded old-to-new map;
- add a guard that refuses a registry whose fingerprint for a program differs from the current schema's.

## 12. Hiding test material from builders (adopted 2026-11-09)

The rules and the full path list are in `manifests/builder_isolation.md`. The check is `scripts/check_builder_isolation.py`.

**After review:**
- **Positive control:** run once outside the sandbox with `--expect-visible`; every project path, and every extra `--root`, must be visible. A wrong root therefore cannot pass.
- **Platform guard:** the platform flag must match the system it runs on.
- **What counts as visible:**
  - only "does not exist" or "empty folder" counts as hidden, and a permission error counts as visible;
  - known files are probed by name;
  - on Windows, the UNC, long-path and 8.3 spellings of the root are probed too;
  - in WSL, reachable host mounts (drvfs or 9p) count, and so does interop when Windows programs are reachable;
  - a reachable network, and credential variables, count (by name only);
  - so do links or mounts that lead out of the workspace.

**Tested:**

| case | result |
|---|---|
| WSL, positive control | 35 of 35 visible |
| WSL, no isolation | 44 findings |
| WSL, prescribed isolation (bubblewrap `--tmpfs /mnt --tmpfs /home`, binds of the builder's inputs, `--unshare-net`, `--clearenv`) | **0 findings** |
| WSL, prescribed isolation plus a symlink from the workspace to `/mnt/c` | caught |
| WSL, drive not hidden | 40 findings |
| Windows, positive control | 35 of 35 |
| Windows, no isolation | 153 findings |
| Mistyped `--root` | fails the positive control |

**Limit:**
- Tool deny-lists inside an agent cannot pass this check. On Windows only OS-level isolation can: a separate user, a container or a VM.
- No such Windows setup was tested here.

## 13. Probe soundness with the final library (2026-11-09; coordinating session's fix, D24)

The coordinating session changed the library after two review rounds (`manifests/design_decisions.md`, D24). For this check:
- route-flip witnesses are used only when the whole path after the flip is printed and at least one activity or wait changes;
- the route rule checks every visit, case ends and fully printed case paths;
- no reuse of route-probability or worker-change rule passes;
- NaN guards, seeded program_wide, and generic dedupe.

This task did not touch `assurance/` for it. `validation/probe_soundness_workflow_test.py` was rerun unchanged. Its reference wrapper already prints the generic output format (task_start, task_end, wait and case_end events, plus decision events in one shape). Part 1 uses the existing scripts' updated wrappers. Each output file records the sha256 of its question file.

| set | file | part 1 rejections | directed (both record shapes) | generic, program_wide | answer = gold | inexpressible |
|---|---|---|---|---|---|---|
| dev, 112 valid | `manifests/probe_soundness_workflow_dev_v1.json` | 0 | 110 Trusted, 2 Untestable, **0 Caught** | all Trusted | 110 of 110 | 2 (`pha-activity_duration-03`, `-04`, the unknown-target controls) |
| test, 240 (`fe754f44…`) | `manifests/probe_soundness_workflow_test_v1.json` | 0 | 239 Trusted, 1 Untestable, **0 Caught** | all Trusted | 240 of 240 | **0** |
| policy, 91 (`fc79f0db…`) | `manifests/probe_soundness_workflow_policy_v1.json` | 0 | 90 Trusted, 1 Untestable, **0 Caught** | all Trusted | 91 of 91 | **0** |

- **Other checks:** 0 history-check failures, 0 runs where the wrapper had to use a value the input did not give, and 0 decisions on a deep witness. Route flips needing unprinted visits, and flips changing only decisions: 0 in every set (the library now excludes them).
- **The three earlier misfires:**
  - `loa-polP-routing_outcome-00` and `-01` (same content in the final file) are now **Trusted**, 2 probes passed;
  - `pha-polP-routing_outcome-03` is now **Untestable**: its only witness was the zero-time flip, which the library now excludes. Its no-op passed.
- **Untestable introduced by the fix: exactly that one.** The other Untestable decisions existed under the old library too:
  - dev `pha-routing_outcome-00` and `-08`, the same pair before the fix;
  - test `pha-test-routing_outcome-17`, whose content was `pha-test-routing_outcome-18` in the earlier file, Untestable there too.
- **Inexpressible:** with rules 4–7 the test and policy sets have none. The 5 earlier inexpressible test controls are gone.
- **Offline tests** after the fix: workflow 0 failures, mlsys 0 failures.
