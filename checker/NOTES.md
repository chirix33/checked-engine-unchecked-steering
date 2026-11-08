# Checker notes

Python 3.12, standard library only. Run from the project root.

```
.venv\Scripts\python.exe -I checker\run.py <scenario.json> <out.json>
.venv\Scripts\python.exe -I checker\validate.py <scenario.json> <run_output.json> [<base_run_output.json>]
.venv\Scripts\python.exe -I checker\validate_all.py     # validates checker\out\*.json -> checker\validation_summary.json
```

`checker\out\<scenario_id>.json` holds `run.py` output for all 64 scenarios. `validate_all.py` uses `P_<model>_<seed>_factual` as the base for the other `P_*` scenarios and `H01_factual_contention_ties_loop` as the base for H02 to H14 and H16 (H01 and H15 have no base). `checker\tests\` has small extra models: `tie` (zero-length tie that breaks property 5), `dl` (deadlock), and scenarios for visit limit, conflict, invalid intervention and invalid scenario.

## run.py design

- Parses BPMN and parameter JSON itself (ElementTree only for XML). Draws use `hashlib.sha256`; `u` is an exact `Fraction`, converted to float for the quantile.
- Calendars are weekly window lists plus a lower bound (added instances) and a list of removed intervals. `next_open` and `work_end` walk windows week by week.
- Scheduling is a time-stepped discrete-event loop. It repeatedly jumps to the next time that is either a token event or the earliest time any waiting pool has an instance able to start. At that instant it first processes all token events (arrivals, gateways, timers, task completions), then starts waiting activations: per pool the head (smallest key) starts if some instance has `next_open(max(t, free_at)) = t`, the instance chosen by `(free_at, k)`. Among pools the smallest head key starts first. After each start (which can create events at the same instant through zero-length tasks or timers) events are processed again before the next start. This reproduces section 8 including simultaneous events, because a newly created activation enters the key-ordered waiting queue immediately, and an already-started activation is never displaced.
- Task completion tokens and timer expiry are future events; the end of a task is computed at its start from the (fixed) calendar.
- Errors: validation order is scenario, model, interventions, then dynamic errors; see `AMBIGUITIES.md` item 20.

## validate.py design

Independent code: calendars are expanded to explicit interval lists up to a horizon, quantiles use `erf` plus bisection, and routing and values are recomputed from the scenario. It replays tokens per case from the output records (properties 1, 2, 6), recomputes draws and values, checks occupancy, work, queue order and idle capacity (5), and compares with the base output for 8, 9 and 10. It also runs a literal section 8 replay as an extra property.

## Result

All 64 scenarios run with status ok and pass every applicable property. See `validation_summary.json`. The only specification problem found with a concrete counterexample is property 5 in the zero-length tie case (AMBIGUITIES.md item 1).
