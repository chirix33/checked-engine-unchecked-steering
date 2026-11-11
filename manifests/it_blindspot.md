# IT CPU-versus-memory blind spot in the directed gate

Session `cpu-mem-blindspot`, started 2026-11-09. Scope: `assurance/mlsys.py` (the IT `task_request` blind-spot
branch and its router only) and tests in `scripts/test_assurance_mlsys_offline.py`. Pre-change copy of
`mlsys.py`: sha256 `20eaa46fa165571c9c23d32da6a3718f962f158d58637db52e3cc5cc75a48500` (kept in the session
scratchpad as `mlsys_prechange.py`).

## The problem (verified before any attempt)

- `task_request` asks "what if task T requested v units of CPU (or memory)?". The directed gate runs one
  same-family witness (budget 3: `cap - 2 = 1` witness), then the request's own change (the rule probe).
- A witness *discriminates* when the stated rules give different outcomes for "the change written into the
  right resource" and "the change written into the other one". Today's witnesses: `sharp` (value above every
  machine in the asked resource, but some machine could hold it as the other resource) and `pos` (the reverse).
- On dev (checked over every started task and both resources), 5 of the 16 IT windows have no discriminating
  witness at all: Cell windows 05, 25, 26, 27 and 30. Each has one 12500/12500 machine, largest in both
  resources with the same number. In the other 11 windows the selected witness always discriminates (the
  discriminating ones are drawn first). In the 5, the witness falls back to "value above every machine: never
  starts", which both readings satisfy, and the evidence is labelled `(cannot tell cpu from mem)`.
- Today that label changes nothing: the row is Trusted if the witness and the rule probe pass.

## Success bar (written before the first attempt)

Router: (1) no blind spot -> today's method, unchanged; (2) blind spot -> the new method; (3) blind spot and
the new method cannot separate the two resources -> Untestable, never Trusted. "Blind spot" = the witnesses
today's method selects (same rng draw) are non-empty and none of them `discriminates`; in the registry-reuse
path, every reused passing input-use row carries the `(cannot tell cpu from mem)` label.

Data: dev only. Dev questions (`manifests/mlsys_questions_dev_v1.json`) and **generated dev scenarios**: for each
of the 16 dev IT windows in `manifests/mlsys_splits_v1.json`, both resources, a fixed-seed sample of started
tasks, values 0.5x and 2x of the current request (the question generator's rule: a value that some machine can
hold), query `task_start_time` of the changed task. Scoring uses the evaluation-side reference-as-program and
broken programs of `validation/probe_soundness_mlsys.py` (never inside the method), plus a scorer-only mirror
defect (memory change written into CPU) as a generality check that is reported, not gated.

Hard requirements (every one must hold):

1. **Reference never Caught**: 0 Caught for the reference run as a program, on every dev question (all
   families, `probe_soundness_mlsys.py` on dev: 0 rejections) and on every generated dev scenario.
2. **No-blind-spot rows unchanged**: on every dev question (both domains, all families) and every generated
   scenario, for the reference and every broken program, rows the router sends to today's method have the same
   decision, reason and evidence as the pre-change `mlsys.py`. Must hold by construction; shown row by row.
3. **Caught stays Caught**: every planted broken program row that is Caught today (dev questions and generated
   scenarios) is still Caught.
4. **Primary measure** (blind-spot generated scenarios):
   - 4a (hard): the CPU-into-memory broken program is never Trusted with a wrong answer.
   - 4b (hard): the reference is Trusted on at least 50% of blind-spot scenarios. Below that, the method gains
     too little over the plain fallback (Untestable for every blind spot) to justify the added code.
   - 4c (reported, used to rank attempts that pass 4a and 4b): the number of blind-spot scenarios where the
     CPU-into-memory program is Caught, and where the reference is Trusted. Ranking = reference Trusted +
     broken Caught, then fewer probe executions.
   - Cost: probe executions per blind-spot row are reported; at most 2 x `cap(budget)` (6 at budget 3).
5. **Nothing else changes**: every non-`task_request` row and every manufacturing row is identical to the
   pre-change decision (part of 2); workflow code is untouched; both offline suites stay at 0 failures.

Runtime boundary for the method: the document, its map, the schema, executions of the program under test. No
reference code, gold, hidden fields or test questions. Test windows and test questions are never run while
iterating. After the winner is frozen and reviewed, `validation/probe_soundness_mlsys.py` runs once on test and
is reported as it comes out.

## Attempts

(Each: hypothesis, implementation, dev result against the bar.)

### Why no single change can work here (derived before attempt 1)

In a blind window the 12500/12500 machine M* is up at the end. Under the stated rules a task fits some machine
up at the end with (cpu v, its memory) iff M* holds it, iff v <= 12500; with (its cpu, memory v), the same. So
"never starts" and "must start and finish", the only outcomes the rules fix without simulating the schedule,
are the same under both readings for every value. Any single-change witness can at most refute the confused
reading from what the run happens to show (observation-based), not by a rule-fixed prediction.

### Attempt 1: peel the dominating machine, then use today's discriminating witness (composite change)

**Hypothesis.** The blind spot exists only because M* dominates both resources. Remove the machines that are
largest in both resources (a `machine_removal` written into the same input), repeating while one machine still
dominates, until today's `sharp` or `pos` witness exists on the remaining cluster. On that cluster the rules fix
the outcome: `sharp` (value above every remaining machine in the asked resource, but one remaining machine up at
the end could hold it as the other resource) must never start; `pos` (the reverse) must start and finish. So a
correct program passes with certainty and a program that writes the change into the other resource fails with
certainty. To keep a machine-removal defect from being reported as a `task_request` defect, a precheck first
runs the removal alone (completeness, stated invariants, nothing on the removed machines); if it fails, the row
is Untestable, never Caught. Steps: precheck, then the composite witness (same count as today's witnesses),
then the unchanged rule probe. Cost at budget 3: 3 executions (today 2). Composite inputs are written with the
backends' existing input paths (`DEVSDomain.run_input` with `apply_inputs` applied twice; `OTFDomain.run_map`
with `edit_nav` applied twice); any other backend gives Untestable. Precheck rows are not written to the
registry (a failed precheck must not block later questions); a passing composite row is written with a label
naming the resource, and the reuse path treats a row as resolving the blind spot only for that resource.

**Dev result: fails bar 3.** Scorer: two samples of generated dev scenarios (seed 11; 3 and 8 tasks per window
and resource, 0.5x and 2x values), plus the 108 dev questions, pre-change vs current, reference and every
broken program.
- Bars 1, 2 and 5 hold: reference Caught 0; all 2070 non-blind `task_request` rows and 264 other-family and
  manufacturing rows identical to the pre-change decision (8-task sample).
- Primary (8-task sample, 159 blind-spot scenarios): reference Trusted 159 of 159. CPU-into-memory program:
  CPU rows Caught 80 of 80 (17 with a wrong answer; pre-change 10 wrong answers were Trusted), memory rows
  Trusted 79 (it is correct there). Mirror defect: memory rows Caught 79 of 79.
- **Bar 3 fails** on the 3-task sample: 2 `moves_prefix` rows (Cell window 26, T001) go from Caught to Trusted.
  Today's witness is the only probe that sees records move before the change point (T001 is submitted at 0, so
  the rule probe's prefix check is empty); attempt 1 replaced that witness.
- Side effect: the `ignores_removed_machine` program goes from Trusted (right answers) to Untestable on all
  159 blind-spot rows, through the precheck, as designed.
Hypothesis discarded: replacing today's witness loses evidence that today's method collects.

### Attempt 2: today's method first, then the attempt-1 split as an added step

**Hypothesis.** Keep every probe today's method runs, in the same order, with the same records. Only where
today's method would say Trusted on a blind-spot row, add the attempt-1 step (precheck without the dominating
machines, then the composite witness). Every row Caught today is then Caught by the same probe (bar 3 by
construction); a blind-spot row can only move from Trusted to Caught or Untestable. Cost at budget 3: 4
executions on a resolved blind-spot row (today 2). Registry reuse: as in attempt 1.

**Dev result: meets the bar** (before review; numbers below are on the reviewed version where they changed).
- 3-task and 8-task samples: bars 1, 2, 3 and 5 hold (reference Caught 0; every non-blind row and every
  other-family and manufacturing row identical; no Caught row lost).
- 8-task sample, 159 blind-spot scenarios: reference Trusted 159 of 159 (bar 4b). CPU-into-memory program:
  CPU rows Caught 80 of 80 (17 wrong answers among them; pre-change, 10 wrong answers were Trusted); memory
  rows Trusted 79 of 79, where it is correct. Mirror defect: memory rows Caught 79 of 79, CPU rows Trusted.
  `moves_prefix` 159 of 159 Caught, as today. `ignores_removed_machine`: 159 Trusted (right answers) become
  Untestable through the precheck. Mean probe executions per blind-spot row: 4.0 for the reference (today 2).
- Dev questions, `validation/probe_soundness_mlsys.py` on dev: 0 reference rejections. The 3 blind-spot dev
  questions stay Trusted (reasons now name the split); every other per-question reference decision is
  unchanged. CPU-into-memory program on dev questions: right Caught 2 -> 3, right Trusted 4 -> 3.
- Real OTF R1 programs (Claude Sonnet and Haiku, `itops_dev`): window 27 blind rows Trusted through the split
  (M04 and M05 removed). Window 30 blind rows become Untestable: removing M03 alone breaks both programs ("T048
  has 2 starts, 1 ends"); today's gate already Catches both on a plain `machine_removal` of M03 there.

## Chosen method: attempt 2, with review fixes

Router, in `_directed` (`assurance/mlsys.py`):
1. **No blind spot** (the selected witnesses include one that `discriminates`; in the reuse path, the window
   and resource have a discriminating witness kind): today's method, unchanged.
2. **Blind spot**: today's probes run unchanged, and today's reuse path runs unchanged. Only where today's
   method would say Trusted, `_blind_spot` decides: split off the machines largest in both resources
   (`_split_cluster`), precheck the removal alone, run today's kind of discriminating witness on the rest
   (`_without`). Witness fails: Caught. Passes: Trusted.
3. **Unresolved** (no split gives a witness, the precheck fails, or the backend cannot run several changes):
   Untestable.

Code: `_blind`, `_scope_blind`, `_kinds`, `_split_cluster`, `_split_key`, `_run_changes`, `_without`,
`_blind_spot`; two router lines in `_directed`. Final `mlsys.py` sha256
`e06dd8be284a157d8698410f4658ff98adfaab35089c8c607c179223be3372c0`. Tests: `blindspot_tests` in
`scripts/test_assurance_mlsys_offline.py` (router, split edge cases, both input paths, real OTF R1 program
Trusted and the same program with the confusion added Caught, a failed precheck, shared-registry isolation,
reuse per resource). Both offline suites: 0 failures.

Related ideas (for credit, not used as code): choosing an input on which a planted fault must change the
output, as in constraint-based test data generation for mutation testing (DeMillo and Offutt, "Constraint-Based
Automatic Test Data Generation", IEEE TSE 17(9), 1991). Here the planted fault is the CPU/memory confusion,
and the changed context is the cluster without the dominating machine.

## Review (separate agent, on attempt 2)

No soundness hole found. The reviewer's stress run: 16 dev windows plus 20 random variants each (planted one or
two dominating machines, a second dominating layer, failures returning in, after, or never), 672 cases, 214
splits: reference failures 0 on every precheck and composite; CPU-into-memory program passes 0. Findings and
what was done:
1. **Medium, confirmed: a shared registry broke "non-blind rows unchanged".** A failed split witness was written
   under today's family key, so a later non-blind row (another window, the other resource) became Already
   caught. **Fixed:** the split step keeps its own registry key per resource (`_split_key`); its failures block
   only later blind-spot rows of that resource. While fixing it I found the same kind of gap in my reuse
   change (a blind row skipped today's reuse and re-ran today's probes, which could write new failures under
   today's key). **Fixed:** today's reuse path now runs unchanged and the split step decides only where it
   would permit, so today's registry rows evolve exactly as before. Both checked with shared-registry tests and
   a shared-registry dev run (below).
2. Low, confirmed: on OTF, window 30 blind rows are Untestable because the R1 programs fail the removal alone
   (today's gate already Catches them on `machine_removal` M03). Sound; stated as a limit. A test now covers it.
3. Low, reasoning, not introduced here: outside the blind spot, a reused witness row from one resource still
   permits a request on the other resource (today's behaviour, kept by rule 3). Stated as a limit.
4. Tests: a mislabelled test renamed; added the untested split branches (identical machines, no dominating
   machine), the DEVS input path, precheck failure, and shared registries.

## Final dev results (frozen code, sha256 e06dd8be...)

Generated dev scenarios, exhaustive: every started task in the 16 dev IT windows, both resources, 0.5x and 2x
(5,483 scenarios, 2,191 in the blind spot, all in windows 05, 25, 26, 27, 30), plus the 108 dev questions;
pre-change vs final; reference and 5 broken programs (40,800 rows). Run twice: a fresh registry per row, and
one registry per program shared across all rows in order (as the main runner keeps it).

| bar | fresh registry | shared registry |
|---|---|---|
| 1. reference Caught | 0 | 0 |
| 2. non-blind rows identical (27,378 `task_request`, 264 other family and manufacturing) | all | all |
| 3. Caught rows lost | 0 | 0 |
| 4a. CPU-into-memory wrong answers Trusted on blind rows | 75 -> 0 | 0 -> 0 |
| 4b. reference Trusted on blind rows | 2,191 of 2,191 | 2,191 of 2,191 |
| 5. other families, manufacturing, workflow | unchanged | unchanged |

Blind-spot rows, fresh registry (pre -> final; probe executions per row, pre -> final):

| program | resource | rows | pre-change | final | probes |
|---|---|---|---|---|---|
| reference | cpu | 1,098 | Trusted 1,098 | **Trusted 1,098** | 2.00 -> 4.00 |
| reference | mem | 1,093 | Trusted 1,093 | **Trusted 1,093** | 2.00 -> 4.00 |
| CPU into memory | cpu | 1,098 | Trusted 665 (75 wrong), Caught 433 | **Caught 1,098** (159 wrong) | 2.00 -> 3.21 |
| CPU into memory | mem (correct there) | 1,093 | Trusted 1,093 | Trusted 1,093 | 2.00 -> 4.00 |
| memory into CPU (scorer-only) | mem | 1,093 | Trusted 248 (21 wrong), Caught 845 | **Caught 1,093** (154 wrong) | 2.00 -> 2.45 |
| memory into CPU | cpu (correct there) | 1,098 | Trusted 1,098 | Trusted 1,098 | 2.00 -> 4.00 |
| moves prefix | both | 2,191 | Caught 2,191 | Caught 2,191 | 1.01 -> 1.01 |
| ignores removed machine | both | 2,191 | Trusted 2,191 (all right) | **Untestable 2,191** | 2.00 -> 3.00 |
| ignores priority | both | 2,191 | Trusted 2,191 (all right) | Trusted 2,191 | 2.00 -> 4.00 |

With a shared registry the CPU-into-memory program is already Caught on every blind row before the change
(Already caught, from a failed witness in a non-blind window), so there the split adds evidence but changes no
decision. The gain is for programs whose first `task_request` evidence comes from a blind window, and for the
fresh-registry decisions the probe-soundness scripts report.

Dev questions (`validation/probe_soundness_mlsys.py`, saved as `manifests/probe_soundness_mlsys_v3_dev.json`):
0 reference rejections; the 3 blind-spot dev questions stay Trusted; IT `wrong_field` right Caught 2 -> 3, right
Trusted 4 -> 3 (no wrong answer was Trusted on dev before or after); every other row unchanged.

## Single test run (after freezing; not iterated on)

`python -X utf8 validation/probe_soundness_mlsys.py manifests/probe_soundness_mlsys_v3_test.json
manifests/mlsys_questions_test_v1.json`, on `mlsys.py` sha256 e06dd8be..., compared with the stored pre-change
run `manifests/probe_soundness_mlsys_v2_test.json`:
- Reference rejections: **0**. Reference directed: IT Trusted 119, Untestable 1; manufacturing Trusted 95,
  Untestable 1 (both as before).
- IT `task_request` reference rows: **24 of 24 Trusted**. 11 of them are blind-spot rows (the 11 the plain
  Untestable fallback would have cost); all 11 are resolved by the split and stay Trusted. These are the only
  per-question changes (reasons only).
- CPU-into-memory program on test: before right Caught 5, right Trusted 5, wrong Caught 9, **wrong Trusted 5**;
  after right Caught 7, right Trusted 3, wrong Caught 14, **wrong Trusted 0**. All 5 wrong answers are now
  Caught; 2 right answers move from Trusted to Caught.
- Every other broken program, both domains: unchanged.
- Probe executions are not stored in the report; on dev a resolved blind-spot row costs 4 executions instead
  of 2.

## Limits

- **Cost:** 2 extra executions (precheck, composite) per blind-spot row that today would permit; 4 instead of 2
  at budget 3. Directed then spends more than `generic` on these rows; report it with the cost comparison.
- **Cross-family dependency:** the split needs the program to handle `machine_removal` of the dominating
  machine(s). If it does not, the row is Untestable (not Caught). On dev, the two Claude R1 OTF programs fail
  this in window 30, so their blind rows there are Untestable; a program that ignores removed machines loses all
  its (right) blind-spot Trusted rows.
- **Coverage of the confusion model:** the split refutes "the change is written into the other resource". Other
  wrong readings of a request change are covered only by today's probes.
- **Reuse across resources outside the blind spot** (today's behaviour, unchanged): a reused witness row from
  one resource can permit a request on the other.
- **Baselines:** `generic` and `program_wide` are unchanged and keep the blind spot.
- **Shared registry:** with family-level registry evidence the planted program is usually already Caught by a
  non-blind window, so the measured gain is mainly in fresh-registry decisions.
- Dev blind windows all have a 12500/12500 machine; a blind spot of another shape (e.g. a discriminating machine
  down at the end) is handled by the same code but was only exercised in the reviewer's synthetic variants.
