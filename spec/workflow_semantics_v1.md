# Workflow reference semantics, version 1

This document defines one deterministic realization of a published business-process simulation model, and how an intervention changes it. Two separate programs must implement it and agree on every output field. If a rule below is ambiguous, that is a defect in this document: report it rather than guessing silently.

These are controlled benchmark semantics. They are not a claim about real operations, and they are not a re-implementation of any published simulator.

Keywords: "must" is mandatory. An `error` code means the program writes the error output in section 11 and stops.

## 1. Time

All times are integer seconds from `t = 0`, which is a Monday at 00:00:00 UTC. The weekday of `t` is `floor(t / 86400) mod 7`, where 0 is Monday and 6 is Sunday. There are no time zones and no daylight saving. Intervals written `[a, b)` include `a` and exclude `b`.

## 2. Model input

A model is a BPMN 2.0 XML file plus a JSON parameter file.

### 2.1 BPMN elements

Read every element inside `process`. These types take part in execution:

| BPMN type | Requirements |
|---|---|
| `startEvent` | Exactly one in the model, no incoming flow, exactly one outgoing flow. Any event definition inside it is ignored. |
| `endEvent` | At least one in the model, at least one incoming flow, no outgoing flow. |
| `task` | At least one incoming flow, exactly one outgoing flow. |
| `intermediateCatchEvent` | Must contain a `timerEventDefinition`. At least one incoming flow, exactly one outgoing flow. The delay comes from the JSON file, never from the XML. |
| `exclusiveGateway` | At least one incoming flow, at least one outgoing flow. |
| `parallelGateway` | At least one incoming flow, at least one outgoing flow. |
| `sequenceFlow` | Connects `sourceRef` to `targetRef`. |

Ignore annotations, associations, diagram data, flow names, condition expressions and `default` attributes. If a `sequenceFlow` touches any other element type, or a requirement above fails, the error is `unsupported_model`.

### 2.2 JSON parameters

| Key | Meaning |
|---|---|
| `task_resource_distribution` | For each task: `task_id` and a list `resources`. Each entry gives `resource_id`, `distribution_name` and `distribution_params`. Every task must have exactly one entry. |
| `resource_profiles` | Each profile has `resource_list`. Each entry in that list is a **pool**, with `id`, `name`, `amount` (integer, possibly written as a string) and `calendar`. |
| `resource_calendars` | Calendars, each with `id` and `time_periods`. |
| `gateway_branching_probabilities` | For each gateway: `gateway_id` and an ordered list `probabilities` of `path_id` and `value`. Values are decimal strings or numbers. |
| `event_distribution` | For each timer: `event_id`, `distribution_name`, `distribution_params`. |
| `arrival_time_distribution` | `distribution_name`, `distribution_params`. |
| `arrival_time_calendar` | A list of time periods in the same form as `time_periods`. |

If any of `batch_processing`, `prioritisation_rules`, `case_attributes`, `event_attributes`, `global_attributes`, `branch_rules` or `multitask` is present and non-empty, or `model_type` is `"FUZZY"`, the error is `unsupported_model`. The same error applies if a task or timer has no distribution, or an exclusive gateway with two or more outgoing flows lacks a probability entry whose paths are exactly those flows. Probability entries for other gateways are ignored.

### 2.3 Pools and instances

A pool of `amount = n` has instances named `<pool name>_<k>` for `k = 0, ..., n-1`, even when `n = 1`. Instances are ordered by `k`. Instances of a pool share its calendar and its duration distributions.

### 2.4 Duration dependence on the resource

A task's service duration may depend on the task and the **pool** that performs it, as declared in `task_resource_distribution`. It does not depend on which instance of that pool is assigned, and the random draw behind it is not keyed by resource. Because each task has exactly one pool entry, assigning a different instance can change when a task runs, never how much work it needs.

## 3. Calendars

A time period has `from` and `to` weekdays (`MONDAY` to `SUNDAY`, inclusive, `from` not after `to`) and `beginTime` and `endTime` as `HH:MM:SS.mmm`. Drop fractional seconds by truncation, so `09:00:00.646` means `09:00:00`. Each listed day has the working window `[begin, end)`, repeating every week. Overlapping windows merge. Use published values as written, including an end of `23:59:00`, which leaves that minute non-working.

For a set of working times `W`:

- `next_open(W, t)` is the smallest `t' >= t` with `t'` in `W`. A window's end is not working time.
- `work_end(W, s, d)`, for `s` in `W`, is `s` when `d = 0`. Otherwise it is the smallest `e > s` such that the length of `W` intersected with `[s, e)` equals `d`. A task finishing exactly at the end of a window has `e` equal to that end, not the next opening.

The instance working set `W(r)` starts as its pool's calendar and is changed only by the interventions in section 9.

## 4. Exogenous draws

Every random quantity comes from a uniform draw fixed by its identity and independent of execution order:

```text
text   = seed + "|" + case + "|" + element + "|" + visit + "|" + variable
digest = SHA-256 of text encoded as UTF-8
n      = first 8 bytes of digest as a big-endian unsigned integer
k      = n >> 12
u      = (2k + 1) / 2^53
```

`u` is an exact rational strictly between 0 and 1, and is exactly representable as an IEEE-754 double. `visit` is written in decimal.

| Variable | Element | Visit | Used for |
|---|---|---|---|
| `interarrival` | Start event id | 1 | The gap before this case arrives |
| `service` | Task id | Visit number | Service duration |
| `timer` | Timer event id | Visit number | Timer delay |
| `branch` | Exclusive gateway id | Visit number | Route choice |

The `visit` of a task, timer or exclusive gateway with two or more outgoing flows is 1 plus the number of earlier activations of that element in that case. Other elements have no visit number. In supported models, activations of one element within one case are causally ordered, so this count is well defined.

If a case exceeds 100 visits of any element, the error is `visit_limit_exceeded`.

A scenario may list `draw_overrides`. An override replaces `u` for exactly the identity it names. Its `u` is a decimal string, read as an exact rational in `[0, 1)`. Overrides that are never used have no effect and are not errors.

Interventions never change a draw. They only change what is computed from it.

## 5. Quantiles and durations

`Q(D, u)` gives an integer number of seconds. Floating-point arithmetic is IEEE-754 double. `round_half_up(x) = floor(x + 0.5)`. `Phi` is the standard normal CDF and `Phi_inv` its inverse, each accurate to at least 1e-9 absolute error. The parameters are listed in order, taken from each entry's `value` in the model file:

| Name | Parameters | `x` |
|---|---|---|
| `fix` | `[v]` | `x = v` |
| `expon` | `[mean, min, max]` | With `s = mean - min` and `F = 1 - exp(-(max - min) / s)`: `x = min - s * ln(1 - u * F)` |
| `norm` | `[mean, std, min, max]` | With `lo = max(min, 0)`, `a = Phi((lo - mean) / std)`, `b = Phi((max - mean) / std)`: `x = mean + std * Phi_inv(a + u * (b - a))` |

Then `Q = round_half_up(x)`. For `expon` and `norm`, also clamp `Q` to `[ceil(lower), floor(max)]`, where `lower` is `min` for `expon` and `lo` for `norm`. So truncated distributions are sampled by inverse CDF.

Validity: `expon` needs `min >= 0` and `mean > min` and `max > min`. `norm` needs `std > 0` and `max > lo`. `fix` needs `v >= 0`. Any other distribution name is unsupported. In a model file a violation is `unsupported_model`. In an intervention it is `invalid_intervention`.

## 6. Cases and arrivals

A scenario has `n_cases` base cases, with ids `c0000`, `c0001`, and so on: `"c"` plus the zero-based index, padded to at least 4 digits. Base arrival times are computed once, over all base cases, before any intervention applies:

```text
a_0 = next_open(A, 0)
a_k = next_open(A, a_(k-1) + Q(arrival distribution, u(case_k, start event, 1, "interarrival")))
```

`A` is the arrival calendar. Removing a case does not change any other case's arrival. An added case arrives at exactly the stated time, which need not be in `A`. All its draws come from section 4 using its own id, so existing cases keep all their draws.

The `arrival` of a case is its arrival time. At that time one token leaves the start event on its outgoing flow.

## 7. Token flow

Tokens move along flows and take no time. Tokens of different cases never interact except through resources.

- **Task, timer or end event with several incoming flows:** each arriving token activates it independently.
- **Exclusive gateway:** each arriving token is handled independently. With one outgoing flow the token passes through, with no draw and no record. With two or more, it is a branch evaluation (section 7.1).
- **Parallel gateway:** it fires when every incoming flow holds at least one token. Firing consumes one token per incoming flow, using the earliest on each, and emits one token on every outgoing flow. Its firing time is the largest arrival time among the consumed tokens.
- **End event:** the token is consumed. A case's `end` is the latest time any of its tokens reached an end event, and `end_event` is that event's id.

If a case finishes with tokens waiting at a parallel gateway, the error is `deadlock`.

### 7.1 Routing

The evaluation time is the token's arrival time. Take the gateway's flows in the order of its JSON `probabilities` list, with their probabilities as exact rationals, and any active `routing_set` applied. Choose the first flow `i` with `u < p_1 + ... + p_i`, where `u` is the draw for this visit.

An intervention that changes the probabilities keeps the same `u`. A case then changes route only if its draw falls between the old and new thresholds.

### 7.2 Timers

A timer starts when its token arrives, ends `d` seconds later, and then emits its token. `d = Q(D, u)`, subject to section 9. Timers use no resource and ignore all calendars.

### 7.3 Loops

A loop is an ordinary path back through an earlier element. Each pass is a new visit with new draws. A case rerouted by an intervention uses the draws its new visits are keyed to. No draw is copied from another visit.

## 8. Task scheduling

A token reaching a task creates an **activation** with `enabled` equal to the token's arrival time, and a key:

```text
key = (enabled, arrival of the case, case id, task id, visit)
```

Compare numbers numerically and strings by Unicode code point.

Scheduling follows this definition. Keep a set of undispatched activations. Repeatedly take the one with the smallest key and dispatch it:

1. For every instance `r` of the task's pool, compute `s(r) = next_open(W(r), max(enabled, free_at(r)))`. `free_at` starts at 0, or at `from` for an added instance.
2. Assign the instance with the smallest `(s(r), free_at(r), k)`. This means the earliest start, then the instance free for longest, then the lowest index.
3. Set `start = s(r)`. Compute the service duration `d` (section 9) using `start`. Set `end = work_end(W(r), start, d)` and `free_at(r) = end`.
4. At time `end`, a token leaves on the task's outgoing flow. Follow it through section 7, creating any new activations.

Consequences that an implementation must reproduce:

- **Queue discipline:** first come, first served by key, across all tasks sharing a pool. A later key never takes an instance in a way that delays an earlier key.
- **Non-preemption:** an instance holds one task from `start` to `end`. Work pauses when `W(r)` has no working time and resumes on the same instance. A paused task is never reassigned and no other task uses that instance meanwhile.
- **Simultaneous events:** the key decides the order. Earlier-arrived cases go first, then lower case id, task id and visit. A new activation created during dispatch is compared with the rest by the same key, even if it sorts before the activation just dispatched.

Any algorithm may be used if its output matches this definition, including a time-stepped simulation that assigns work as instances become free.

## 9. Interventions

`interventions` is a list applied together. Each entry has a `type`. Base scenarios have none. An intervention that matches nothing is valid and has no effect. Five families exist:

| Family | Types |
|---|---|
| Resource availability | `resource_unavailable`, `resource_add` |
| Activity duration | `duration_set`, `duration_scale`, `duration_distribution` |
| Timer delay | `timer_set`, `timer_scale`, `timer_distribution` |
| Routing probability | `routing_set` |
| Case set | `case_add`, `case_remove` |

### 9.1 Selector

Duration, timer and routing types have an optional `selector` with optional keys `case`, `visit`, `from` and `to`. An activation matches if its case and visit equal any given values, and its reference time is in `[from, to)`, where an absent bound is unbounded. The reference time is `start` for durations, the timer's start for timers, and the evaluation time for routing.

If two interventions of the same family and target match one activation, the error is `conflicting_interventions`.

### 9.2 Resource availability

- `resource_unavailable`: `pool`, `from`, `to` (both required and finite, `from < to`), and either `count` or `instances`. `count` selects the `count` highest-indexed original instances. `instances` lists names of original instances. `[from, to)` is removed from each selected `W(r)`.
- `resource_add`: `pool`, `count`, `from`. Adds that many instances, indexed after the existing ones, each with the pool's calendar intersected with `[from, infinity)` and initial `free_at = from`. Multiple `resource_add` entries for one pool are numbered in list order.

A task in progress when an instance becomes unavailable pauses as in section 8.

### 9.3 Durations

For each task activation at dispatch:

- Base: `d = Q(model distribution, u)`.
- `duration_distribution`: `task`, `distribution_name`, `distribution_params` (a list of numbers), optional `selector`. `d = Q(new distribution, u)` with the same `u`.
- `duration_scale`: `task`, `factor` (decimal string, at least 0), optional `selector`. `d = floor(base * factor + 1/2)` in exact rational arithmetic, where `base` is the model-distribution value.
- `duration_set`: `task`, `seconds` (integer, at least 0), optional `selector`. `d = seconds`.

### 9.4 Timers

`timer_distribution`, `timer_scale` and `timer_set` work the same way, with `timer` in place of `task`, applied to `d` in section 7.2.

### 9.5 Routing

`routing_set`: `gateway`, `probabilities` (an object from flow id to decimal string), optional `selector`. The gateway must have two or more outgoing flows. Keys must be exactly its flows, values at least 0, summing exactly to 1. Flow order stays the JSON list order from the model.

### 9.6 Case set

- `case_add`: `case`, `arrival` (integer, at least 0). The id must match `^[a-z0-9_-]+$` and differ from every other case.
- `case_remove`: `case`, which must be a base case. The case does not exist in this run.

### 9.7 Validity

Any unknown id, missing or wrongly typed field, or rule violation in this section is `invalid_intervention`. This includes `count` below 1, a `count` above the pool's size, `from >= to` in a selector, and a `selector.case` that does not exist in the run. A malformed scenario outside `interventions` is `invalid_scenario`.

## 10. Scenario input format

```json
{
  "schema": "wf-scenario/1",
  "scenario_id": "example",
  "model": {"bpmn": "relative/path.bpmn", "params": "relative/path.json"},
  "seed": "any string",
  "n_cases": 50,
  "draw_overrides": [
    {"case": "c0000", "element": "G", "visit": 1, "variable": "branch", "u": "0.1"}
  ],
  "interventions": []
}
```

Model paths are relative to the scenario file. `draw_overrides` and `interventions` may be absent, meaning empty. `n_cases` is an integer of at least 0.

## 11. Output format

```json
{
  "schema": "wf-run/1",
  "scenario_id": "example",
  "status": "ok",
  "cases":    [{"case": "c0000", "arrival": 0, "end": 0, "end_event": "id"}],
  "tasks":    [{"case": "c0000", "task": "id", "visit": 1, "enabled": 0, "start": 0, "end": 0, "resource": "Clerk_0", "service": 0}],
  "timers":   [{"case": "c0000", "timer": "id", "visit": 1, "start": 0, "end": 0, "delay": 0}],
  "branches": [{"case": "c0000", "gateway": "id", "visit": 1, "time": 0, "flow": "id"}],
  "draws":    [{"case": "c0000", "element": "id", "visit": 1, "variable": "service", "u": "0.500000000000"}]
}
```

- `service` and `delay` are the values `d`. `end - start` of a task may exceed `service` because of pauses.
- `draws` holds one record per task activation (`service`), timer activation (`timer`) and branch evaluation (`branch`), including when the value is not used, such as for `fix` or `duration_set`. `interarrival` draws are not listed. `u` is the draw or override value as a double, formatted with exactly 12 decimal places.
- Sort `cases` by `(arrival, case)`, `tasks` by `(case, enabled, task, visit)`, `timers` by `(case, start, timer, visit)`, `branches` by `(case, time, gateway, visit)`, and `draws` by `(case, element, visit, variable)`.
- All cases run to completion. There is no end-of-window truncation. Questions about a time window are evaluated on these complete records.

On error, write only:

```json
{"schema": "wf-run/1", "scenario_id": "example", "status": "error", "error": "code"}
```

Error codes: `unsupported_model`, `invalid_scenario`, `invalid_intervention`, `conflicting_interventions`, `visit_limit_exceeded`, `deadlock`. If the scenario cannot be read far enough to obtain its id, `scenario_id` is `null`.

## 12. Properties every valid output must satisfy

1. **Flow:** each case's task, timer and branch records form a valid token replay of the model from the start event to an end event.
2. **Precedence:** each activation's `enabled` equals the completion or firing time that produced its token, and `enabled <= start <= end`.
3. **Occupancy:** the `[start, end)` intervals of one instance never overlap. An instance's intervals never begin outside `W(r)`.
4. **Work:** the length of `W(r)` intersected with `[start, end)` equals `service`.
5. **Queue order:** for tasks in one pool, a smaller key never starts later than a larger key, provided both activations existed when the larger key was dispatched. A zero-length task can create a smaller-key activation at the same instant, after a larger key was dispatched (amendment A1). An instance is never idle during its working time while a task of its pool has been enabled and not started.
6. **Timers:** `end = start + delay`, and `start` equals the token's arrival time.
7. **Routing:** each `flow` is the one section 7.1 selects from the recorded draw.
8. **Draw stability:** for any identity present in two runs with the same seed and overrides, `u` is identical.
9. **Case isolation:** under `case_add` or `case_remove`, other cases' arrivals and draws are unchanged.
10. **No-effect:** an intervention that matches nothing, or that does not change any evaluated value, yields output identical to the base run.

## 13. Amendments after independent implementation

The engine and checker were both written from the text above, before this section existed. These amendments come from the checker's ambiguity report. None changes the output of any validation scenario.

**A1. Property 5 corrected.** As first written, property 5 was false for zero-length tasks. Section 8 is normative, and property 5 now follows it.

**A2. Stated explicitly, as both implementations already behave:**

- Flows are read from `sequenceFlow` `sourceRef` and `targetRef`. `<incoming>` and `<outgoing>` child elements are ignored.
- `resource_id` refers to the `id` of a `resource_list` entry. Instance names use that entry's `name`, keeping any spaces.
- Model-file probabilities must sum exactly to 1, and a calendar must contain working time. Otherwise the error is `unsupported_model`.
- `amount` below 1 is `unsupported_model`.
- The visit limit allows 100 visits. The 101st is the error.
- Conflicts are detected only when two interventions match one actual activation, not from overlapping selectors alone.
- A task that would finish exactly when an unavailable interval begins does not pause.

**A3. Left unspecified.** Implementations may differ here, so benchmark scenarios must not depend on these:

- Which error is reported when a scenario has several.
- Duplicate draw overrides for one identity.
- Removing one case twice, and unknown extra keys in an intervention.
- `resource_add` with a negative `from`, and decimal strings using exponents.
- Which end event is reported if a case reaches several at the same latest time.
- Models with a cycle made only of pass-through gateways.

A rounding flip within 1e-9 of a `.5` boundary in `norm` durations is possible in principle. It did not occur in any comparison.
