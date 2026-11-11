# Blind spots in the directed gate, every family (Phase 2)

Session `cpu-mem-blindspot`, Phase 2, started 2026-11-09 20:05 local. The IT CPU/memory work (Phase 1) is in
`manifests/it_blindspot.md`, kept unchanged; this note covers every family. Baselines for every "unchanged"
comparison: `assurance/mlsys.py` sha256 `e06dd8be...` (the frozen IT result), `assurance/probes.py`
`5b528a61...`, `assurance/policy.py` `d1bd8cc9...`; copies in the session scratchpad (`phase2/`).

## What today's gate checks, per family (read from the code before any measurement)

| domain | family | directed today |
|---|---|---|
| workflow | activity_duration, timer_delay, routing_outcome | 2 same-target witnesses on other cases (+3600 s, or a draw in another stated route), each: the witness case's records change and nothing before the first use moves; then a no-op on an unreached visit |
| workflow | routing_probability | with decision events: the stated route rule on every recorded decision, the first switched decision, the prefix, and case paths; without: the switched case's records change and the prefix holds (form b) |
| workflow | resource_availability | the request's own change: no starts on unavailable workers in the interval; added workers: prefix before the first waiting task, and that task changes |
| workflow | case_set | removing another case: its records vanish, the prefix before its arrival holds |
| manufacturing | all four | 1 witness (the changed day's ledger changes, earlier days unchanged; capacity: the first day where recorded shipments no longer fit changes), then the request's own change against the stock and backorder balances, nonnegativity and the capacity limit, then an order-book no-op |
| IT | all five | 1 witness (job: no records left; failure: no fail; priority: a free-tier evicted task set to 5 is not evicted; request: never starts / starts; machine: nothing on it), then the request's own change against completeness and the capacity and down-time invariants |

Two kinds of evidence: **reaction** (records change, prefix holds) shows the program uses the input; **rule**
evidence (balances, invariants, route rule) checks a stated consequence. Reaction evidence cannot tell a correct
change from one applied to the wrong place or with the wrong size, as long as something changes after the change
point. That is the general blind spot this phase measures.

## Confusion catalog (written before any measurement)

Derived from the request format (target, case or product or task, visit or day, value, resource) and the stated
rules; not from test data. "Planted" marks the confusions built as broken programs on dev. Each planted program is
the reference run as a program with the request's change rewritten before the reference sees it (the same
machinery as `validation/probe_soundness_mlsys.py` and `validation/probe_soundness_workflow_test.py`); a factual
run is never altered.

### Workflow (Loan, Pharmacy)

| family | id | confusion | planted |
|---|---|---|---|
| activity_duration | AD-visit | the work is written to the next visit of the same case and activity (dropped if that visit is not printed) | yes |
| | AD-activity | the work is written to another activity of the same case and visit (the next one in Work plan order) | yes |
| | AD-case | the work is written to the next case (same activity and visit) | yes |
| | AD-add | the value is added to the planned work instead of replacing it | yes |
| | AD-allvisits | the value is written to every printed visit of that case and activity | yes |
| | AD-units | the value is read in minutes (x60) | no (a magnitude error like AD-add) |
| timer_delay | TD-visit, TD-wait, TD-case, TD-add | as for activity_duration, on the Wait plan | yes |
| routing_outcome | RO-visit | the draw is written to the next visit of the same decision | yes |
| | RO-decision | the draw is written to another decision of the same case (next in Route draws order) | yes |
| | RO-case | the draw is written to the next case | yes |
| | RO-complement | the program uses 1 - draw | yes |
| routing_probability | RP-decision | the probabilities are applied to another decision (next in label order) | yes |
| | RP-reverse | the probabilities are assigned to the routes in reverse label order | yes |
| | RP-redraw | the draws are re-sampled (the stated rule keeps them) | no (needs an RNG choice; a program that ignores the printed draws fails replay) |
| resource_availability | RA-pool | the workers are added to, or made unavailable in, another pool | yes |
| | RA-count | one worker more than asked | yes |
| | RA-low | the lowest-numbered workers are made unavailable instead of the highest | yes |
| | RA-shift | the unavailable interval is shifted by one hour | yes |
| case_set | CS-next | the next case is removed instead | yes |
| | CS-both | the case and the next case are removed | yes |

### Manufacturing

| family | id | confusion | planted |
|---|---|---|---|
| production_quantity | PQ-add | the value is added to the planned production | yes |
| | PQ-nextday | the value is written to the next day | yes |
| | PQ-product | the value is written to another product (next in code order) | yes |
| production_timing | PT-extra | the production moves one day further than asked | yes |
| | PT-copy | the production is added to the later day but also kept on the original day | yes |
| order_removal | OR-nextday | the order of the next day is removed | yes |
| | OR-half | half the order is removed | yes |
| dispatch_capacity | DC-start | the factor is applied from the first day of the period | yes |
| | DC-inverse | the capacity is divided by the factor | yes |

(The existing planted programs `ignores_input`, `wrong_field`, `moves_prefix`, `ignores_capacity` stay as they are.)

### IT operations

| family | id | confusion | planted |
|---|---|---|---|
| task_request | cpu/mem | done in Phase 1 | (Phase 1) |
| | TR-add | the value is added to the current request | yes |
| task_priority | TP-add | the value is added to the current priority | yes |
| | TP-task | the priority is written to the next task id | yes |
| job_removal | JR-first | only the job's first task is removed | yes |
| | JR-job | another job is removed (next in id order) | yes |
| failure_removal | FR-machine | another machine's failure is removed | yes |
| | FR-return | the machine still fails but returns at once | yes |
| machine_removal | MR-machine | another machine is removed | yes |
| | MR-idle | the machine is kept but marked failed at time 0 with no return | yes (equivalent under the stated rules? to be checked: if equivalent, it is not a confusion and is reported as such) |

## Success bar per family (written before any measurement)

For each family, on dev only (dev questions and scenarios generated on dev documents):
1. The correct reference, run as a program, is never Caught (all shapes of records), and dev soundness stays at 0
   rejections (`probe_soundness_mlsys.py` on dev; `probe_soundness_workflow_test.py` on the dev questions).
2. Rows without a blind spot keep exactly today's decision, shown row by row against the baselines above. Rows
   that today's method declines (Caught, Untestable, Can't express) keep the same decision: an added check may
   only run where today's method would permit.
3. Every planted bug Caught today stays Caught (holds by 2).
4. Adopted only if it loses none of the reference's Trusted rows, and Catches at least one planted confusion that
   today's method Trusts. Ranked by planted wrong answers removed, then planted rows Caught, then cost (extra
   program executions; 0 preferred).
5. Offline suites at 0 failures; other configurations (`generic`, `program_wide`, `native`, `replay`, `schema`)
   unchanged.

For a confusion that stays unresolved: the cost of an Untestable fallback is measured on dev (the reference's
Trusted rows lost, the planted wrong answers removed), and not applied.

Up to 10 attempts in total for this phase. Deadline Nov 10, 23:59 local.

## Attempts

(Each: hypothesis, implementation, dev result.)

### Baseline: what each planted confusion does today (dev, before any attempt)

Scorers (session scratchpad `phase2/`): `p2_wf.py` (workflow: the 112 dev questions of
`runs/fingerprint_check_v1/dev_valid112.json`, the set the dev soundness run used, plus 306 scenarios generated
from the dev documents' tables; both record shapes; generated scenarios the reference cannot answer from the
document are skipped, 6 per shape) and `p2_ml.py` (manufacturing and IT: the 108 dev questions plus 270
generated scenarios on dev chapters and windows). Today's gate, directed, budget 3, a fresh registry per row.
Reference: **never Caught**, in either scorer.

Wrong answers Trusted today (rows, both record shapes counted for workflow):

| family | confusion | wrong Trusted | Caught | note |
|---|---|---|---|---|
| activity_duration | AD-visit | 0 | 104 | the witness case changes nowhere (next visit often unreached) or later |
| | AD-activity | 14 | 84 | |
| | AD-case | 16 | 82 | |
| | AD-add | **80** | 0 | blind: something always changes after the change point |
| | AD-allvisits | 12 | 32 | |
| timer_delay | TD-visit | 0 | 104 | |
| | TD-wait | 36 | 68 | |
| | TD-case | 18 | 82 | |
| | TD-add | **94** | 0 | blind |
| routing_outcome | RO-visit / RO-decision / RO-case / RO-complement | 0 / 6 / 4 / 12 | 94 / 88 / 90 / 76 | |
| routing_probability | RP-decision / RP-reverse | 4 / 2 | 99 / 77 | |
| resource_availability | RA-pool / RA-count / RA-low / RA-shift | 10 / **16** / 0 / 0 | 154 / 0 / 54 / 84 | RA-count blind |
| case_set | CS-next / CS-both | 0 / **20** | 72 / 12 | CS-both blind when the extra case arrives later |
| production_quantity | PQ-add / PQ-nextday / PQ-product | 0 / 0 / 0 | 31 / 48 / 48 | the rule probe's balances catch every wrong answer |
| production_timing | PT-extra / PT-copy | 0 / 0 | 41 / 48 | |
| order_removal | OR-nextday / OR-half | 0 / 0 | 48 / 48 | |
| dispatch_capacity | DC-start / DC-inverse | 0 / 2 | 24 / 20 | DC-inverse under-ships for factors above 1 |
| task_request | TR-add | **14** | 18 | |
| task_priority | TP-add / TP-task | **5** / 0 | 0 / 60 | |
| job_removal | JR-first / JR-job | 0 / 0 | 15 / 28 | |
| failure_removal | FR-machine / FR-return | 0 / 0 | 22 / 22 | |
| machine_removal | MR-machine | 0 | 44 | |
| | MR-idle | 0 | 0 | **equivalent** under the stated rules (a machine down from time 0 with no return runs nothing): 0 answers differ; not a confusion |

### Phase 2 attempt 1: exact stated-rule checks on the workflow runs the gate already makes

**Hypothesis.** The workflow rules fix more than "something changes": rule 3 fixes each task's end from its
start, its work and its pool's working hours; rule 4 fixes each wait's end from its start and delay; rule 5 and
the printed draws fix each case's path; rule 6 says every case ends; rule 2 names workers only from the pool.
Checking these on the witness or rule runs the gate already makes (no extra execution) separates a change applied
correctly from one applied to the wrong place or with the wrong size:
- activity_duration, timer_delay: on each passing witness run, every task whose work the input fixes ends exactly
  when that work is done in its pool's working hours, and every wait ends exactly its delay after it starts;
- routing_outcome: on each passing witness run, every case whose path the document fully prints performs exactly
  that path's activities and waits (the witness case under its flipped draw);
- routing_probability, records without decisions (form b): the same path check under the requested
  probabilities, as the decision-event form already does;
- resource_availability: added workers: no worker of the pool beyond the new count is named; unavailable workers
  that the factual record never uses inside the interval: the run equals the factual run;
- case_set: every case other than the removed one still ends.
Each check runs only where today's method would permit, after today's probes, and is skipped (today's decision
stands) when the program's records do not name what it needs (e.g. OTF's own records). Expected: the reference
never fails (the rules are exact); AD-add, TD-add, AD/TD-case/activity/wait, RO-*, RP-*, RA-count (added),
CS-both are Caught. Not expected to help: RA-count on unavailability, AD-allvisits only where the extra visits are
reached.

**Dev result (attempt 1): adopted as a step; meets bars 1-5, with residues.** 3,120 workflow rows (both shapes).
Reference: Caught 0; every reference decision unchanged (613 Trusted rows gain exact evidence rows, labels and
reasons unchanged); no Caught row lost; no extra execution. Wrong answers Trusted, before -> after: AD-add 80 -> 0,
AD-activity 14 -> 0, AD-case 16 -> 0, AD-allvisits 12 -> 10, TD-add 94 -> 0, TD-wait 36 -> 0, TD-case 18 -> 0,
RO-decision 6 -> 0, RO-case 4 -> 0, RO-complement 12 -> 12, RP-decision 4 -> 0, RP-reverse 2 -> 0, RA-count
16 -> 14, RA-pool 10 -> 10, CS-both 20 -> 0. Offline workflow suite: one test read the last evidence row as the
rule row; it now looks the row up by name (test-only change in `scripts/test_assurance_offline.py`).
Residues: RO-complement (the witness draw sits mid-band, and 1 - draw stays in the band for these decisions),
RA-pool and RA-count on unavailability where the record uses the workers in the interval (the unused-workers
check does not apply), AD-allvisits (witness cases never reach a second visit).

### Phase 2 attempt 2: timing on every checked run, unavailability as non-working time, and the request's own change

**Hypothesis.** (a) Rule 3 also fixes the end of a task held by a worker declared unavailable: the interval counts
as non-working time for that worker. So the timing check applies to the rule run of an unavailability request,
and catches a change applied to the wrong pool or to one worker too many whenever an affected worker holds or
starts a task in the interval. (b) The same timing check is exact on every other run the gate makes (route,
case-removal and added-worker runs, route-flip witnesses). (c) For the case-level families, run the request's own
change once and check it exactly (timing, and for a route draw the case paths). This catches confusions that the
witnesses cannot reach (later visits, symmetric draws) on the very row asked; it costs one execution where today's
method would permit (the same run the structured answer needs). Expected: AD-allvisits and RO-complement wrong
answers removed; RA-pool and RA-count reduced; reference unchanged.

**Dev result (attempt 2): adopted; meets bars 1-5.** 3,120 workflow rows. Reference: Caught 0; every reference
decision unchanged (668 Trusted rows gain evidence rows). No Caught row lost. Wrong answers Trusted after
attempt 2 (attempt 1 in brackets): RO-complement 0 (12), AD-allvisits 4 (10); the 4 are questions whose visit is
not printed, which no program can answer through the structured input (the reference has the same 4 "wrong"
rows, answer None), so AD-allvisits is resolved. Every other confusion stays at 0 except RA-pool 10 and RA-count
14, all on unavailability rows where the record uses the workers inside the interval: the confused program blocks
another pool (or one more worker), cases simply never reach the asked pool in the interval, and no stated local
rule is violated; catching it needs each task's enabled time, which the records do not give. **Unresolved.**
Cost: +1 execution on case-level rows that today's method would permit (the request's own change).

### Phase 2 attempt 3: manufacturing dispatch completeness and an IT "fill" witness

**Hypothesis.** (a) Manufacturing rule 3 ships each order as far as stock and remaining capacity allow, oldest
first. So at the end of every day, a product that is still backordered either has no stock left or the unused
capacity is below one unit of it. Checked on the rule probe's run of the request's own change (no extra run),
this catches a capacity change applied too small (DC-inverse for factors above 1). (b) IT `task_request`: one more
witness on a started task whose other resource fits the largest machine, with the value set to the largest
machine's capacity in the asked resource (that machine up at the end). A correct program must start and finish
it (completeness); a program that adds the value to the current request asks for more than any machine has and
never starts it. Run only where today's method would permit; +1 execution.

**Dev result (attempt 3): adopted; meets bars 1-5.** 1,876 manufacturing and IT rows. Reference: Caught 0;
every reference decision unchanged (60 `task_request` rows gain the fill row; manufacturing rows pass the
dispatch check silently). No Caught row lost. Wrong answers Trusted: DC-inverse 2 -> 0, TR-add 14 -> 0. TP-add
stays at 5: no witness the rules fix tells "priority set to v" from "v added to the priority" (both keep an
evicted free-tier task out of the free tier, and the order among other tiers needs the schedule). **Unresolved.**
Cost: +1 execution on `task_request` rows that today's method would permit.
Offline mlsys suite: two Phase 1 tests read the last evidence row as the split row; they now look it up by name.

## Unresolved confusions: cost of an Untestable fallback (measured on dev, not applied)

| confusion | fallback rule measured | reference Trusted rows lost | of which dev questions | planted wrong answers removed | planted right answers lost |
|---|---|---|---|---|---|
| RA-pool, RA-count (workflow, unavailability) | Untestable when the record uses the unavailable workers inside the interval (the unused-workers check cannot apply) | 88 of 184 `resource_availability` (88 of 98 unavailability rows) | 26 | 24 (10 + 14) | 108 (RA-count 68, RA-low 40) |
| TP-add (IT) | Untestable for every `task_priority` row (no row's evidence tells set from add) | 60 of 60 | 12 | 5 | 55 |

Both counts are over both record shapes for workflow (each row counted once per shape).

## Cost of the adopted checks (reference, dev, mean probe executions per row, before -> after)

activity_duration 2.60 -> 3.56, timer_delay 2.31 -> 3.31, routing_outcome 2.35 -> 3.27 (the request's own change);
task_request 2.60 -> 3.60 (fill witness); routing_probability, resource_availability, case_set and every
manufacturing family unchanged (the checks reuse runs the gate already makes).

## Dev soundness and shared registries (after attempt 3, before review)

- `validation/probe_soundness_workflow_test.py` on the 112 dev questions: 0 blockers; directed Trusted 110,
  Untestable 2 in both record shapes, as stored in `manifests/probe_soundness_workflow_dev_v1.json`. Every
  directed term and reason identical; `generic` and `program_wide` identical in every field (evidence and probe
  counts included).
- `validation/probe_soundness_mlsys.py` on dev: 0 reference rejections; broken-program counts identical to
  `manifests/probe_soundness_mlsys_v3_dev.json`.
- Scorers with one registry per program and record shape, kept across rows: reference never rejected, no Caught
  row lost; planted rows move from Trusted to Caught or Already caught (466 workflow rows, 3 manufacturing/IT
  rows; one DC-inverse row moves from Caught to Already caught, still a decline).

## Review (separate agent, on attempts 1-3) and fixes

Confirmed by the reviewer with code, and fixed:
1. **High: the request's own change could Catch a correct program.** A route flip whose path needs draws the
   document does not print cannot be run by a document-only program (the reference wrapper refuses it), and
   `exact_own` turned that into Caught (dev: Pharmacy Run 04 c0014 D7 visit 2; Loan Run 04 c0014 D4 visit 2). My
   scorer skipped such scenarios, so it never saw them. **Fixed:** `exact_own` returns None, without running,
   when the flipped path is not fully printed (the guard the witnesses already had). Rerun of the reviewer's case
   list: both Trusted again, as before Phase 2.
2. **High: exact-check failures were written under today's registry key**, so with a shared registry a failure
   changed later rows that today's method declines (Untestable or Caught -> Already caught). **Fixed:** the exact
   checks keep their own key (op `<op>|exact`, workflow and manufacturing; `<op>|fill <resource>` for the IT fill
   witness), consulted only on rows today's method permits. `policy._directed` now wraps today's method
   unchanged (`_directed_today`, which only records the witnesses and the removed case it used).
3. **Medium: the dispatch check ran inside the rule probe**, so it could decide rows today's method leaves
   Untestable. **Fixed:** the rule probe only keeps its run; the check runs after a permit (`_dispatch_check`).
Lower, fixed: the timing check first runs on the program's own factual run and is skipped unless it passes there
(records in another shape are never judged); `exact_own` is skipped, with no execution, when the factual records
cannot be checked (the reviewer found 4 dev OTF programs gaining nothing while their directed runs rose 556 ->
734); a zero-length task at the interval start counts as using the worker; the route-rule run is kept, so timing
also applies to records with decision events; registry reuse on case-level families now also runs the request's
own exact check. Found sound by the reviewer: `work_end` (calendars, all-week pools, exactly-the-time-left, blocks
across days and closing time, zero work), the waits rule, case paths through splits, joins and loops, the
unused-workers and added-worker-name checks, every-other-case-ends, dispatch completeness with whole grams, the
fill witness's "must start", the run cache, and no change to `generic` or `program_wide`.

## Chosen method (frozen) and final dev results

Frozen library: `probes.py` sha256 `42a86e31...`, `policy.py` `619052b9...`, `mlsys.py` `cfb85128...`.

Router, every family (one structure, no model involved):
1. **Today's method runs unchanged.** Every row it declines (Caught, Already caught, Untestable, Can't express)
   keeps exactly today's decision, reason and evidence; shown row by row on dev, fresh and shared registries
   (0 such rows changed in 9,992 rows).
2. **Where today's method would permit, the exact stated-rule checks run** (`policy._directed` and
   `mlsys._directed` wrap today's method): workflow timing (rules 3, 4), case paths (rule 5), unused-worker and
   worker-name checks (rule 2), every other case ends (rule 6), the request's own change for case-level families;
   manufacturing dispatch completeness; the IT fill witness; and the Phase 1 CPU/memory split. A check that fails
   gives Caught; one that cannot apply leaves today's decision. Their registry rows have their own keys.
3. **Unresolved** confusions (RA-pool and RA-count on used workers' unavailability; TP-add) keep today's decision.
   The Untestable fallback for them is measured above and not applied (Ashraf to decide).

Final dev, fresh registry (shared in brackets where different), wrong answers Trusted before -> after:

| confusion | before | after |
|---|---|---|
| AD-add / AD-activity / AD-case / AD-allvisits | 80 / 14 / 16 / 12 | 0 / 0 / 0 / 4 (inexpressible questions; the reference has the same 4) |
| TD-add / TD-wait / TD-case | 94 / 36 / 18 | 0 / 0 / 0 |
| RO-decision / RO-case / RO-complement | 6 / 4 / 12 | 0 / 0 / 0 |
| RP-decision / RP-reverse | 4 / 2 | 0 / 0 |
| CS-both | 20 | 0 |
| RA-pool / RA-count | 10 / 16 | 10 / 14 (unresolved) |
| DC-inverse | 2 (1) | 0 |
| TR-add | 14 | 0 |
| moves_prefix on task_request | 1 | 0 |
| TP-add | 5 | 5 (unresolved) |

Reference: Caught 0 in every run; every reference decision label and reason unchanged (668 workflow and 228
manufacturing/IT Trusted rows gain exact-check evidence rows). Dev soundness:
`manifests/probe_soundness_workflow_dev_v2.json` (0 blockers; directed terms and reasons, and `generic` and
`program_wide` in every field, identical to `..._dev_v1.json`) and `manifests/probe_soundness_mlsys_v4_dev.json`
(0 rejections; identical to v3). Offline suites: 0 failures (new tests: `phase2_tests` in both suites).

## Single test run (frozen code; not iterated on)

Run once, after the review fixes, on `probes.py` 42a86e31, `policy.py` 619052b9, `mlsys.py` cfb85128.
1. **Soundness, the repo's scripts:**
   - `validation/probe_soundness_workflow_test.py manifests/workflow_questions_test_v1.json` gives
     `manifests/probe_soundness_workflow_test_v2.json`: 0 blockers; directed Trusted 239, Untestable 1 in both
     shapes. All 480 rows have the same directed term and reason as `..._test_v1.json`; `generic` and
     `program_wide` are identical in every field. Every exact check on the reference passed or could not apply
     (`exact unavailable` not applicable on all 40 unavailability rows). Directed probe executions 644 -> 882.
   - `validation/probe_soundness_mlsys.py` on the test questions gives `manifests/probe_soundness_mlsys_v4_test.json`:
     0 rejections; every reference label and reason, and every broken-program count, identical to v3.
2. **Planted confusions, on the test questions only** (the frozen dev scorers with `--no-gen`, no generated
   scenarios): reference never Caught; reference Trusted unchanged (workflow 478 of 480, mlsys 214 of 216); 0 rows
   that today's method declines changed. Wrong answers Trusted, before -> after:

| confusion | before | after | right answers Trusted, before -> after |
|---|---|---|---|
| AD-add / AD-activity / AD-case / AD-allvisits | 66 / 26 / 20 / 2 | 0 / 0 / 0 / 0 | 14 / 4 / 4 / 60 -> 0 / 0 / 0 / 58 |
| TD-add / TD-wait / TD-case | 62 / 24 / 20 | 0 / 0 / 0 | 18 / 0 / 4 -> 0 / 0 / 0 |
| RO-decision / RO-case / RO-complement | 6 / 10 / 4 | 0 / 0 / 0 | 0 / 0 / 14 -> 0 / 0 / 8 |
| RP-decision / RP-reverse | 4 / 7 | 0 / 0 | 1 / 14 -> 0 / 12 |
| CS-both | 22 | 0 | 54 -> 0 |
| RA-count | 18 | 6 | 62 -> 26 |
| RA-pool | 12 | 12 | 2 -> 2 |
| TR-add | 11 | 0 | 1 -> 0 |
| DC-inverse | 1 | 0 | 0 -> 0 |
| TP-add | 5 | 5 | 19 -> 19 |

(Workflow rows count both record shapes. "Right answers Trusted" falling is a planted program, defective in its
handling of the change, now Caught although that row's answer happened to be right.)

## Limits

- The checks need records that name tasks, waits, workers and visits in the generic format. On OTF's free-form
  records they do not apply (the reviewer re-decided 4 dev OTF programs: no permit changed), and `exact_own` is now
  skipped there without a run.
- Unresolved: RA-pool and RA-count on unavailability where the record uses the workers in the interval; TP-add.
  Fallback costs above; not applied.
- Cost: +1 execution on case-level workflow rows and on IT `task_request` rows that today's method permits.
- The planted programs are my construction from the request format and stated rules; natural programs may
  confuse requests in other ways. The workflow scorer skips generated scenarios that the reference cannot answer
  from the document (6 per shape on dev).
- `generic` and `program_wide` are unchanged and keep every blind spot.

**Correction (after the test run).** After the review fixes, the workflow offline suite crashed in my own
`phase2_tests`: it built a probe runner with no program, and the fixed timing check now looks at the factual run
first. I had read the mlsys suite's "0 failures" line as covering both. The library was not involved, so the
frozen code and the test run are unaffected. The test now supplies the printed record as the factual run. Both
suites: 0 failures.
