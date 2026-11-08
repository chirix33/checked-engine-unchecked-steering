"""Assurance policy: decide whether to rely on a program's execution for this request.

The decision is taken before the answering execution is used, as the handoff requires:
1. interpret and validate the request;
2. look up conditional evidence for this exact program, adapter, policy, family and operation;
3. run any permitted probes needed;
4. decide: permit, or decline (to reading or abstention, decided by the caller's fallback rule).

Configurations select which evidence counts, so comparators share one code path:
- `native`: no checks beyond the program's own acceptance.
- `replay`: strict factual replay of recorded case ends only.
- `schema`: contract validation only.
- `generic`: replay and contract, plus input-use probes on randomly chosen families and targets. Its budget is a
  number of probe executions, set to the directed cap (`budget`), so generic never has less probe budget than
  directed on any request, including requests where directed reuses evidence and runs nothing.
- `directed`: replay and contract, plus probes on the requested family, operation and target.
- `program_wide`: one verdict per program, from one input-use probe on each case-level family.

A probe result of None (could not be run) is never counted as a pass. A policy that probes permits only if at
least one probe actually ran and none failed. A change the backend cannot express is reported as such, never
recorded as a capability failure.

Reuse: passing evidence is reused only for the same key, target and scope. On a new scope (new records) or a new
policy fingerprint the relevant probes are rerun. A recorded failure under the same key blocks use anywhere.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field

from . import contract
from .probes import ProbeRunner, witnesses
from .registry import Evidence, Key, Registry
from .request import Intervention, Request

CONFIGS = ("native", "replay", "schema", "generic", "directed", "program_wide")
CASE_LEVEL = ("activity_duration", "timer_delay", "routing_outcome")


@dataclass
class Decision:
    permit: bool
    reason: str
    evidence: list = field(default_factory=list)
    probes_run: int = 0                 # program executions made by probes, excluding the factual base run
    untested: bool = False              # declined because no probe could be run
    inexpressible: bool = False         # declined because the backend has no input for the change


def request_seed(req: Request, seed: int) -> int:
    text = json.dumps({"seed": seed, "scope": req.scope, "query": req.query.__dict__,
                       "iv": [i.__dict__ for i in req.interventions]}, sort_keys=True, default=str)
    return int(hashlib.sha256(text.encode()).hexdigest()[:12], 16)


def decide(config: str, req: Request, schema, runner: ProbeRunner, registry: Registry | None, backend,
           budget: int = 3, seed: int = 0) -> Decision:
    if config not in CONFIGS:
        raise ValueError(config)
    if config == "native":
        return Decision(True, "native: no added checks")
    c = contract.validate(req, schema)
    if config == "schema" or not c.ok:
        return Decision(c.ok, f"contract {c.status}: {c.detail}".strip())
    ok, why = runner.replay(req.scope)
    ev = [("replay", ok, why)]
    if config == "replay" or not ok:
        return Decision(ok, f"replay: {why}", ev)
    rng = random.Random(request_seed(req, seed))
    iv = req.interventions[0]
    start = runner.executions
    if config == "directed":
        d = _directed(req, iv, schema, runner, registry, backend, budget, rng, ev)
    elif config == "generic":
        d = _probe_set(_random_witnesses(runner, schema, req.scope, max(budget, 1), rng), runner, req.scope, ev, "generic")
    else:
        picks = []
        for fam in CASE_LEVEL:
            target = _first_target(runner, fam, req.scope)
            if target:
                picks += witnesses(runner.nav, schema, req.scope, Intervention(fam, "set", target=target), 1, rng)
        d = _probe_set(picks, runner, req.scope, ev, "program-wide")
    d.probes_run = runner.executions - start
    return d


def _first_target(runner, family, scope):
    section = {"activity_duration": "Task log", "timer_delay": "Wait log", "routing_outcome": "Decision log"}[family]
    node = next((n for n in runner.nav["nodes"] if n["title"] == f"{scope}: {section}" and n["kind"] == "table"), None)
    return node["table"]["rows"][0][1] if node and node["table"]["rows"] else None


def _random_witnesses(runner, schema, scope, budget, rng):
    out, tries = [], 0
    while len(out) < budget and tries < 20 * max(budget, 1):
        tries += 1
        fam = rng.choice(CASE_LEVEL)
        got = witnesses(runner.nav, schema, scope, Intervention(fam, "set", target=None), 1, rng, same_target=False)
        out += got
    return out


def _probe_set(ws, runner, scope, ev, label):
    ran = 0
    for w in ws:
        ok, why = runner.input_use(scope, w)
        ev.append((f"input_use {w.family}", ok, why))
        if ok is False:
            return Decision(False, f"{label}: {why}", ev)
        ran += ok is True
    if ran == 0:
        return Decision(False, f"{label}: no probe could be run", ev, untested=True)
    return Decision(True, f"{label}: {ran} probes passed", ev)


def _directed(req, iv, schema, runner, registry, backend, budget, rng, ev):
    key = Key(backend.name, backend.program_hash(), backend.adapter_version, schema.policy_fingerprint(), iv.family, iv.op)
    if registry is not None:
        state, rows = registry.state(key, iv.target)
        if state == "failed":
            bad = next(r for r in rows if r["passed"] is False)
            return Decision(False, f"capability failed earlier for {iv.family}/{iv.op}/{iv.target} on {bad['scope']}", ev)
        # Only a passing input-use or rule probe can be reused; a no-op alone never permits, here or fresh.
        # Route-probability probes test the request's own probabilities, so their passes are never reused for a
        # different request; a recorded failure still blocks (review 4).
        here = [r for r in rows if r["scope"] == req.scope and r["passed"] is True and r["probe"] != "no_op"
                and iv.family != "routing_probability"]
        if here:
            ev.append(("reused", True, f"{len(here)} earlier passing probes for {iv.target} on this scope"))
            return Decision(True, f"reused evidence for {iv.family}/{iv.op}/{iv.target} on {req.scope}", ev)
    results = []
    start_exec = runner.executions
    if iv.family == "routing_probability":
        # Records that name decisions are checked against the stated rule. Records that do not (OTF's free-form
        # records) get the record-comparison form instead (form (b), Ashraf 2026-11-07).
        if runner.has_decision_events(req.scope):
            results.append(("rule routing_probability", *runner.route_rule(req.scope, iv)))
        else:
            results.append(("records routing_probability", *runner.route_change(req.scope, iv)))
    elif iv.family == "resource_availability":
        results.append((f"rule {iv.op}", *runner.resource_rule(req.scope, iv)))
    elif iv.family == "case_set":
        others = [c for c in schema.cases.get(req.scope, []) if c not in (iv.case, req.query.case)]
        if others:
            results.append(("rule case_removal", *runner.case_removal(req.scope, iv, rng.choice(others))))
    else:
        # Input use must be shown by at least one witness; a passing no-op alone never permits. Witnesses run first,
        # the no-op only if budget remains, and probing stops at the first failure.
        ws = witnesses(runner.nav, schema, req.scope, iv, max(budget - 1, 1), rng)
        for w in ws:
            results.append((f"input_use {w.family}", *runner.input_use(req.scope, w)))
            if results[-1][1] is False:
                break
        used = runner.executions - start_exec
        if not any(ok is False for _, ok, _ in results) and used < budget:
            noop = runner.no_op(req.scope, iv)
            if noop[0] is not None:
                results.append(("no_op", *noop))
    for name, ok, why in results:
        ev.append((name, ok, why))
        _record(registry, key, iv, req.scope, name, ok, why)
        if ok is False:
            return Decision(False, f"directed: {why}", ev)
    ran = sum(1 for name, ok, _ in results if ok is True and name != "no_op")
    if ran == 0:
        cannot = any("no input" in why for _, ok, why in results if ok is None)
        return Decision(False, "directed: no probe could be run" + (" (the backend cannot express the change)" if cannot else ""),
                        ev, untested=not cannot, inexpressible=cannot)
    return Decision(True, f"directed: {ran} probes passed", ev)


def _record(registry, key, iv, scope, probe, ok, detail):
    if registry is not None:
        registry.add(key, Evidence(probe, iv.family, iv.target, scope, ok, detail))
