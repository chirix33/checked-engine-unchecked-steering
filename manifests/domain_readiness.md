# Domain readiness: manufacturing and IT operations (Phase 1 review, 2026-11-08)

Status: **readiness review only. Nothing implemented, nothing built, no model calls.** The read-only checks below ran existing programs and the pinned reference code on development documents, with scripts kept outside the repo (session scratchpad). Phase 2 waits for a go-ahead.

Labels: **Verified** = checked on files or by running code here. **Proposal** = not done. **Decision** = needs Ashraf.

## 1. What exists, per domain

### Loan and pharmacy (business workflows)
Pilot-ready for development: 112 valid dev questions, reference engine plus independent checker, library support for 6 families, OTF and DEVS-Gen adapters (`manifests/pilot_report.md`). **No final-test questions exist yet for any domain** (pilot report, line 3). This review does not change the workflow domains.

### Manufacturing (SupplyGraph orders and production, daily stock and dispatch)
- **Documents (Verified).** Six MLSys PDFs: `mfg_dev` (4 chapters: every plant, period 01) and `mfg_d01`–`mfg_d05` (56 chapters). Together they cover all 60 chapters: 4 plants x 15 periods. Each chapter prints opening stock, weights, capacity, a 14-day ledger whose `produced` and `ordered` columns are the inputs, and 7 order-book days.
- **Reference (Verified).** `sim.py` is deterministic: integer units and grams, no randomness. `validate.py`'s `ref_run` is a separate runner fed only from numbers parsed back out of the PDF. Both accept the four input changes. `parse_pdf` runs on `mfg_dev` here.
- **Deterministic realization (Verified by reading the code).** Nothing is random. Every input the reference reads for days `first..last` is printed in the ledger, and days after that are printed in the order book. `ref_run` uses nothing else, so a PDF-only gold path exists by construction.
- **Provenance.** A chapter's order book is the first 7 days of the same plant's next period, so periods k and k+1 of one plant share source days. Plants share no products and have separate capacities. Opening stock for every period comes from days 1–14. That is a printed constant, not an outcome, and is disclosed only.
- **Families (sim.py `INPUT_KINDS`), 4:** order removal (`remove_order`), production quantity (`set_production`), production timing (`delay_production`), dispatch capacity (`scale_capacity` from a day).
- **MLSys questions** are multiple-choice "would" statements and are not reused.

### IT operations (Google 2011 trace, cluster scheduler)
- **Documents (Verified).** Six MLSys PDFs: `itops_dev` (windows 08, 17, 27, 30) and `itops_d01`–`d05` (26 windows), 30 windows in all. Each prints machines (capacity, failure, return) and a task log whose submit rows carry job, priority, CPU, memory and run time for every task.
- **Reference (Verified).** `sim.py` is deterministic. `validate.py`'s `ref_engine` is a second scheduler fed only from the parsed PDF. Both accept the five input changes. `parse_pdf` runs on `itops_dev` here.
- **Deterministic realization (Verified by reading the code).** Every task submitted in the window has a printed submit row with its run time, no task arrives after the window, and the after-window rule is stated in the front matter. `window_run` reads only the parsed PDF.
- **Provenance (Verified from `build_config.json` provenance).** A job joins a window only if its submit time lies inside the window, so two windows can share jobs only if they overlap in time. Grouping windows by time overlap gives **6 groups**. Every MLSys IT document mixes groups, so the split unit must be the window, not the document:

  | group | windows |
  |---|---|
  | 0 | 01, 02, 03, 04 |
  | 1 | 05, 06, 07, **08** |
  | 2 | 09, 10, 11, 12, 13, 14 |
  | 3 | 15, 16, **17**, 18 |
  | 4 | 19, 20, 21, 22 |
  | 5 | 23, 24, 25, 26, **27**, 28, 29, **30** |

  `itops_dev`'s windows (bold) fall in groups 1, 3 and 5. No real machine is reused across kept windows (MLSys `scopes.py`).
- **Families (sim.py `INPUT_KINDS`), 5:** job removal, failure removal, task priority, task resource request, machine removal.

## 2. Platforms

### OTF-Tools R1 and B0 (Verified)
- **Programs on dev documents.** These are already built, and no new build is needed for dev.

  | cohort | mfg_dev accepted | itops_dev accepted |
  |---|---|---|
  | R1 Claude Sonnet | 3/3 | 3/3 |
  | R1 Claude Haiku | 3/3 | 3/3 |
  | R1 gpt-oss | 3/3 | 2/3 |
  | R1 Gemma | 3/3 | 3/3 |
  | R1 Qwen | 0/3 | 1/3 |
  | B0 gpt-oss | 1/3 | 3/3 |
  | B0 Gemma | 0/3 | 1/3 |
  | B0 Qwen | 0/3 | 0/3 |

  B0 has no Claude builds yet (decision 7, not run).
- **Records.** They are free-form, and kind names differ per program: `stock` and `stock_level`; `task_start` and `start`. Every factual record carries `src` pointing at the document table row and column it came from. That lets an adapter learn each program's projection from the factual record alone.
- **Changed inputs.** One read-only test was run per program on the 6 Claude R1 programs of each domain. It is one dev change, a check of the path, not a result:
  - **Manufacturing, broken as is.** 5 of 6 programs time out (20 s), because the adapter's `HORIZON = 10**8` is a workflow seconds horizon, and manufacturing programs loop over days up to it. With the horizon set to the last ledger day, **all 6 run**. They match `ref_run` on 12 of 12 stock cells, both factually and with one production cell raised by 5,000 units (4 cells move in the reference).
  - **IT.** All 6 run. They match `window_run` first starts on 85 of 85 tasks, factually and with the longest-waiting task raised to priority 11. In both, 10 tasks move.
- **Reuse on another document.** The navmap is built deterministically from the PDF (`otf_r1.navmap.build_map`). All programs ran on a chapter of `mfg_d01` and a window of `itops_d02` (the mfg ones needed the horizon fix).
- **Native answer path.** The Haiku patch step is unchanged and paid at run time; it was not run here.

### DEVS-Gen
- **What exists (Verified).** Tasks exist only for `WorkflowLoan` and `WorkflowPharmacy`, installed in WSL at `~/trust2027/devs_gen_code/benchmark`. There are no manufacturing or IT tasks and no builds.
- **Conversion (assessment).** Both convert cleanly. The policy prose is the front matter (`render.intro`), already exact, deterministic and integer. The generic stdin format needs no per-family keys:
  - **manufacturing:** products (weight, opening stock), a per-day capacity list, and per-day production and orders;
  - **IT:** machines (capacity, fail and return times) and tasks (job, priority, CPU, memory, submit, run time).

  Every change type is then an edit of a listed value or a removal from a list. The output format is ours to define (ledger rows; task start, finish, evict and fail events), so the projection is exact.
- **Model-independent.** A DEVS-Gen program is built from the task spec, not from a document's records, so one program serves every chapter or window. Test use is reuse by construction.
- **Risk.** IT's reservation and backfilling rule is long. DEVS-Gen may build few exact IT programs, which is a reported outcome, not a blocker.

### Plain coding agent (built by another session)
It needs the same generic input format and the same prose. **Proposal:** one shared spec per domain (prose, input and output format, one example), from which the DEVS-Gen YAML is generated, so the two platforms get identical text.

## 3. Library support (`assurance/`)

Everything is workflow-shaped today. **Verified missing for the new domains:**

| component | today | needed |
|---|---|---|
| `request.py` | families and queries are workflow-only; `Query` is `case_end_time`/`case_ends_by` | 9 new families; queries such as stock or backorder at end of day (product, day) and first start of a task |
| `schema_from_map` | reads Cases, Work plan and Decision log tables | schemas built from Products/Daily ledger and Machines/Task log |
| `contract.py` | workflow checks only | target, day, value and unit checks per new family; "queried task removed" is unsupported |
| `answer.py` | case ends only | per-query projection |
| `interpret.py` | workflow prompt | per-domain prompt (Haiku at run time) |
| `binding.py` | workflow families; anything else is Can't express | per-family rules on the record diff |
| `probes.py` | replay compares case ends; witnesses and edits use workflow sections | domain replay projection, witnesses, edits and rule probes |
| `backends.py` | fixed horizon; `edit_plan`, `stdin_from_map` and `apply` workflow-only | per-domain horizon (**this is the timeout bug**), edits, a learned projection and DEVS stdin |
| `scripts/pilot_runner.py` | workflow docs and `case_end_time` only | domain dispatch. Not in this task's Phase 2 list; it belongs to whoever runs the main experiment |

**Constraint found (Verified):** `policy.request_seed` hashes `Query.__dict__` and `Intervention.__dict__`. Adding even a None-valued field to those classes would change every workflow seed, and so the generic witnesses. New domains must use new subclasses or types, leaving the workflow classes untouched. `scripts/test_assurance_offline.py` must stay at 0 failures.

## 4. Proposed question design (Proposal)

**Manufacturing:**
- Queries: units in stock, or units backordered, of product p at the end of day d (a whole number), on a ledger day so the factual projection can be checked.
- Interventions: `remove_order(p, d)`, `set_production(p, d, v)` (v in {0, x0.5, x2, +k}), `delay_production(p, d, k)` (k in 1–3), `scale_capacity(f, from_day)` (f in {0.5, 0.8, 1.2}, from day 1 or mid-period).

**IT:**
- Queries: first start time of task T, and "does T start by time X" (the workflow pattern).
- Interventions: `remove_job(J)` (never the queried task's job), `remove_failure(M)`, `set_priority(T, p)`, `set_request(T, cpu|mem, v)` (it must still fit some machine), `remove_machine(M)`.

**Both:**
- About 1 in 5 per family is a valid no-effect control, drawn by the same rule, as in `make_pilot_questions.py`.
- Gold is kept only if `sim.py` and `validate.py` agree exactly.
- Each question carries a hidden binding in library request style, an effect label and both golds.

**Directed probes per family** follow the workflow pattern, designed now, before any mfg or IT result:
- **History check:** the program's factual records reproduce the ledger, or the task log.
- **Input use with prefix invariance:** change another permitted input of the same family. That product's or task's records must change, and nothing before the change point may move.
- **No-op:** a change that by the stated rules cannot act. Manufacturing uses the same kind of change on an order-book day, which cannot reach any ledger day. *Correction (Phase 2):* the IT example first proposed here (removing the failure of a machine that ran nothing at or after its failure) is not sound, because the machine stays up and can then run tasks. No IT no-op is defined.
- **Stated-rule invariants** checked on the program's changed run:
  - manufacturing: stock and backorder balance hold, and shipped weight is at most that day's capacity;
  - IT: no machine exceeds its capacity, a removed machine or job leaves no records, and no task runs on a down machine.

**Binding rules (OTF native patch).** Exactly the (product, day) or task record changes, in the right field, to the requested value:
- a delay changes two cells;
- a job removal removes exactly that job's task records;
- a machine removal removes its record and its failure;
- a capacity scale from day 1 is a constant change. From a later day it is **Can't express** for programs with one capacity constant, the same treatment as workflow `unavailable`.

## 5. Proposed split (Proposal)

**Manufacturing, by plant-period chains:**
- dev = periods 01–03 of every plant;
- period 04 is left out as the boundary;
- test = periods 05–15 (44 chapters).

Dev questions sit on `mfg_dev`, where programs exist. Periods 02–03 are used for dev reuse checks.

**IT, by the time-overlap groups above:**
- dev = groups 1, 3 and 5 (16 windows, including all of `itops_dev`);
- test = groups 0, 2 and 4 (14 windows).

The split is by window, because every MLSys document mixes groups.

**Sizes, proposed:**
- dev: 48 manufacturing questions (12 per family) and 60 IT questions (12 per family), comparable with the workflow pilot's 60 per document;
- test: twice that.

Paraphrases and reuse variants stay with their parent chapter or window.

## 6. Plan with hours, against the Nov 11 freeze (Proposal)

| # | item | hours |
|---|---|---|
| 1 | Gold module: `sim.py` on scopes rebuilt from raw data (read-only from the MLSys folder) and `validate.py` from the PDF; agreement on every printed row of all 60 + 30 scopes | 2.5 |
| 2 | Split file with provenance groups and hashes | 1 |
| 3 | Question generator (families, bindings, no-effect quota, effect label, dual gold); dev and test files with sha256 | 4 |
| 4 | Realization check (`validation/`): every input the reference reads is printed in that document, and PDF-only gold equals raw-data gold; run on both files | 1.5 |
| 5 | Library extensions: request subclasses, schemas, contract, answers, interpreter prompts, binding rules, probes, backend horizon, projection, edits, DEVS stdin; offline tests; workflow regression at 0 failures | 9 |
| 6 | Separate-agent review of items 3–5 and 7, and fixes | 3.5 |
| 7 | Shared generic task specs, DEVS-Gen YAML and test configs, WSL install, `--list-benchmarks` check, no builds | 3 |
| 8 | Blind sampled check, 2 agents (about 10 questions per domain each) | 2.5 |
| 9 | Run manifest, this file, hashes | 1 |
| | **total** | **about 28** |

Order: 1, 2, 3 and 4 first, because they fix the question files. Then 5 and 7 can proceed in parallel, then 6, with 8 alongside. That fits by the evening of Nov 10, leaving Nov 11 for the freeze. If time runs short, cut test volume first, then the boundary-period reuse checks.

## 7. Decisions for Ashraf

1. **Test programs.** Which programs answer the test questions?
   - (a) New OTF builds on one test document per domain: `mfg_d01` has 11 test chapters, `itops_d02` has 4 test windows. These are paid builds, larger than the dev documents (62 and 54 pages).
   - (b) The existing dev-built programs, run on test chapters and windows (reuse on new records, no build cost).

   Recommended: (a) for Study B and (b) for Study C, because then (b) is free evidence of reuse. DEVS-Gen and the coding agent build from the spec, so their test use is (b) either way.
2. **IT blind check method.** Recommended: by hand for manufacturing. For IT, let the agents write their own code from the document alone, with no reference code, and record that. IT windows hold 70–230 tasks under a reservation rule, so by-hand answers would either be infeasible or force a sample of easy, early-effect questions, which would bias it. The alternative is by hand on a small, disclosed subset.
3. **Test-set size.** The proposed 96 manufacturing and 120 IT questions drive judge cost (see `baseline_judges_design.md`).

Routine and decided here, unless Ashraf objects:
- the projection is learned from `src`;
- mid-period capacity changes count as Can't express on single-constant programs;
- numeric queries replace MLSys's multiple choice;
- opening stock linking every period to days 1–14 is disclosed only.

## 8. Risks to record
- The reference code and MLSys documents are public (GitHub, `chirix33/otf-tools`), so there is a memorization risk for all builder and judge models.
- MLSys IT sampling scales capacity, enriches failures and free-tier load, and lets windows share jobs.
- Raw data is absent from the pinned clone. It is read only from `MLSystem 2027/implementation-1/data/domains/raw`.
- The single changed-input test above is one change per program. It shows the path works, nothing about rates.

---

# Phase 2: implementation (2026-11-08)

## Decisions applied (Ashraf, via the coordinating session)
- **Test programs:** reuse the dev-built programs on all four domains and all platforms; no test builds.
- **Test chapters and windows:** none was seen at build time (verified, see the split section).
- **IT blind check:** separate agents write their own scheduler from the document. This counts as a third implementation, not a hand check. Manufacturing is checked by hand.
- **Sizes:** dev 48 manufacturing and 60 IT; test 96 and 120.
- **Routine choices kept:** the projection is learned from `src`, numeric queries are used, and opening stock is disclosed only.
- **Mid-period capacity (final, after review 1):** OTF's diagnostic path cannot write a capacity change from a later day into a program that has one capacity constant. The request's own rule probe therefore cannot run, and directed declines it as **Can't express**. This matches the approved routine choice.
  - OTF's native patch language could express it (a constant patch with `"from": day` makes `_what_if` restart at that day). For completeness, `check_otf` accepts such a patch only when the restart time equals the requested day.
  - For a first-day request it rejects a later restart.

## Interface for the runner (entry points in `assurance/mlsys.py`)
Use these for domain `manufacturing` (navmap front node "Plant Stock and Dispatch Records") and `it_ops` ("Compute Cell Scheduling Records"). `M.domain_of(nav)` returns which one, or None for workflow maps.

| step | call |
|---|---|
| schema from the map | `schema = M.schema_from_map(nav)` (nav = the document's map; for test chapters, `runs/mlsys_docs/<doc>/navmap.json`) |
| request and query types | `M.Change`, `M.DQuery`, `M.DRequest`; oracle request source: `M.request_from_binding(q["scope"], q["binding"], q["query"])` |
| interpreter prompt | `req, raw = M.interpret(question, schema, llm)` (prompt text: `M.prompt_for(question, schema)`; parser: `M.parse(text, schema.domain)`) |
| contract | `M.validate(req, schema)` returns a `contract.ContractResult` |
| backend, OTF | `be = M.OTFDomain(program_json_path, "r1" or "b0", ROOT, nav=nav)`, with `nav` set to the question document's map for reuse on new records |
| backend, stdin (DEVS-Gen, coding agent) | `be = M.DEVSDomain(wsl_program_dir, schema)` (it runs `run.py --horizon H` under bubblewrap, like `DEVSBackend`) |
| execute | `be.execute(scope, change_or_None)` returns `Execution`; canonical outcomes in `ex.case_ends["canon"]`; `None` means Can't express |
| native answer (OTF) | `ex, binding = be.native_what_if(scope, question, llm)` (the unchanged OTF patch, restart and replay path) |
| binding check | `ok, why = M.check_otf(iv, binding, schema, scope)`; reject the answer if `ok` is False |
| answer | `value, why = M.answer(req.query, ex.case_ends["canon"])` (int, bool or None) |
| probes and decision | `runner = M.ProbeRunner(be, nav, schema)`; `d = M.decide(config, req, schema, runner, registry, be, budget=3, seed=0)`, with the same configs and `Decision` fields as `policy.decide` |

Notes for the runner:
- **Scoring:** question rows carry `gold`, `query` and `binding`. `factual_end` is the factual answer, kept under that name for one shared scorer. For IT it can be past the window end (see "IT answers past the window").
- **Workflow:** workflow code paths are unchanged, so keep calling `policy.decide` and `request.schema_from_map` for workflow maps.
- **Horizon:** `OTFDomain` uses the last ledger day as its manufacturing horizon. That fixes the Phase 1 timeout without changing `backends.py`.

## Provenance
- **Documents.** The pinned clone was checked out with `core.autocrlf=true`, which rewrote line endings inside its binary PDFs:
  - pdfium still reads them, but pdfplumber (which OTF's navmap builder uses) fails on some;
  - every document used here is written byte-exact from the pinned commit's blob (`git show`) to `runs/mlsys_docs/<doc>/document.pdf` by `scripts/mlsys_gold.py materialize_docs`;
  - the 12 sha256 values equal the MLSys working copy's PDFs and the copies the dev builds read, and are in `manifests/mlsys_raw_hashes_v1.json`;
  - the pinned clone is not changed.
- **Raw records** are read only from `MLSystem 2027/implementation-1/data/domains/raw`. The sha256 of all 79 files under `supplygraph/` and `google-trace-2011/` are in `manifests/mlsys_raw_hashes_v1.json`. The trace also matches its own `SHA256SUM` (`data.verify()`, 0 problems).
- **Licenses:**
  - SupplyGraph: LGPL-2.1 (`supplygraph/LICENSE`; Wasi et al., arXiv 2401.15299);
  - Google cluster trace 2011 (clusterdata-2011-2): CC-BY 4.0 (`google-cluster-data/ClusterData2011_2.md`);
  - OTF-Tools (pinned at `10f5401`): reference code used for gold only.
- **Memorization risk:** the reference code and MLSys documents are public on GitHub, so builder and judge models may have seen them.

## Phase 2 results (development; nothing here is a main result)

| item | file(s) | result |
|---|---|---|
| Gold, two routes | `scripts/mlsys_gold.py` | `sim.py` on raw-rebuilt chapters reproduces every printed row of all 60 chapters and 30 windows. `validate.py` from the PDF alone does too. Inputs are identical. |
| Split and build-input check | `scripts/make_mlsys_splits.py`, giving `manifests/mlsys_splits_v1.json` | Manufacturing: dev 12, boundary 4, test 44. IT: dev 16, test 14. Across the split, 0 real jobs and 0 machines are shared. 48 of 48 existing programs were built on dev documents only. Their stored navmaps equal the committed PDFs' maps. 0 programs name a test chapter in their code. |
| Questions | `scripts/make_mlsys_questions.py` (seed 20271108), giving `manifests/mlsys_questions_{dev,test}_v1.json`; hashes in `manifests/mlsys_questions_v1.sha256` | Dev 108 (48 + 60), test 216 (96 + 120), 12 or 24 per family, with one in five a no-effect control (18 + 36). 0 disagreements between the two golds. Byte-reproducible. |
| Realization check | `validation/mlsys_input_coverage.py` | 324 of 324 pass. |
| Library | `assurance/mlsys.py` (new; no shared file changed) | Offline tests in `scripts/test_assurance_mlsys_offline.py`: 118 PASS, 0 failures. Workflow `scripts/test_assurance_offline.py`: 0 failures. |
| Probe soundness | `validation/probe_soundness_mlsys.py`, giving `manifests/probe_soundness_mlsys_v1.json` | **Reference passes, 0 Caught** on 28 history checks, 778 input-use witnesses, 108 rule probes and 43 no-ops. Directed: 106 Trusted, 2 Untestable (no witness). The reference's answer through the library equals gold on 108 of 108. **Broken programs:** Caught on every defect except IT "writes the CPU change into memory", where 1 wrong answer is Trusted and 5 are Caught (see the limit below). |
| Blind check | `scripts/make_mlsys_blind_sample.py`, `validation/blind_review_mlsys/`, `validation/score_mlsys_blind.py`, giving `score_v1.json`; key `validation/blind_review_mlsys_key_v1.json` | Manufacturing by hand, 2 agents (Opus, Sonnet), 8 questions: **16 of 16 match gold**. IT, 2 agents each wrote their own scheduler from the document alone (a third and fourth implementation): both reproduced all 8 printed logs on the first attempt, **20 of 20 match gold**. The agents never saw gold or code. |
| Shared specs | `scripts/make_generic_task_specs.py`, giving `adapters/generic_tasks/{WorkflowLoan,WorkflowPharmacy,Manufacturing,ITOperations}/` | The workflow specs re-assemble into byte-identical copies of the existing DEVS-Gen YAML, whose files are unchanged. |
| DEVS-Gen tasks | `adapters/devs_gen_tasks/{Manufacturing,ITOperations}/`; `scripts/wsl_install_devs_gen_mlsys_tasks.sh` | Installed in `~/trust2027/devs_gen_code/benchmark`. Both load, and both appear in `--list-benchmarks`. No builds. |

**Adapter smoke on dev** (`scripts/mlsys_otf_smoke.py`, giving `runs/mlsys_smoke/otf_smoke_v2.jsonl`; summary `scripts/summarize_mlsys_smoke.py`).
- **Scope:** 29 existing OTF programs (R1 Claude, R1 Ollama, B0). Each ran the history check on every dev chapter or window, seen and unseen, and the directed decision on a fixed subset of 2 dev questions per family. 676 rows, no model calls.
- **Every Trusted decision was right:** 102 Trusted rows, 0 false permits.
- **R1 Claude Sonnet** is Trusted on all of them except 3 mid-period capacity rows, which are Can't express.
- **R1 Claude Haiku:** some programs fail the history check on some chapters.
- **Ollama R1 and B0:** most fail the history check. The exceptions are the B0 gpt-oss manufacturing program and some Gemma IT rows.
- **Status:** development data that checks the path. It is not a result, and the subset is too small for rates.

**Reviews.** One separate reviewer agent, two rounds, all fixes applied.
- **Round 1:** 13 findings. The worst:
  - IT probes passed an empty output. A completeness invariant was added.
  - Rule-only permits. A permit now needs an input-use pass.
  - Binding holes: a later restart was accepted for a first-day capacity request, and a change inside a record shared by two entities was accepted.
  - The policy fingerprint differed per document, which broke cross-document carry-over.
  - Several crash paths.
- **Round 2:** all fixed, no new hole. It added:
  - a positive `task_request` witness, and labels for permits that rest only on witnesses which cannot tell CPU from memory;
  - gram tolerance in the capacity binding check;
  - an adapter version bump to `0.2`.

**Known limits, to report:**
- **CPU/memory confusion is untested in many windows.** No single change can separate the two resources in about 25 of 60 window and resource pairs (reviewer's count), because one machine is largest in both. On the reference, 21 of 36 Trusted `task_request` decisions rest only on such witnesses. They are labelled `(cannot tell cpu from mem)` in the evidence.
- **IT `failure_removal` is Untestable** where the failure stopped no task, because no witness exists.
- **History check window:** the IT history check covers times up to the window end only. 25 of 60 dev and 60 of 120 test IT questions ask about starts after it, which the document's after-window rule defines.
- **Evidence carry-over:** IT evidence is family-level, because ids are local to a window. Manufacturing evidence is per product. One IT failure blocks that family for that program everywhere, including test documents. This is the intended Study C carry-over.
- **Dev windows sharing jobs:** unseen IT dev windows 05–07 share jobs with build window 08 (same time group). Dev reuse there is not fully new records.
- **List-line edits:** the IT list-line edits work per PDF line. A mention wrapped across lines is not removed. Those lines are outcomes, hidden after the cut.
- **Coverage depends on the program:** 31 dev and test manufacturing capacity questions start after the first day. On OTF programs with one capacity constant they are Can't express.

**Not done here (by design):** no runner changes (the coordinating session owns `pilot_runner.py`), no workflow test questions, no builds and no paid calls.
