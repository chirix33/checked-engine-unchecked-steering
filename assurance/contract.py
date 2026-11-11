"""Contract validation: is a structured request well formed and bound to things the document actually has?

Outcomes are kept apart, as the handoff requires: unknown target, ambiguous binding, unsupported operation,
invalid units, invalid time, and unresolved meaning. Type checks do not establish that the request means what the
question meant; interpretation is evaluated separately.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .request import FAMILIES, ProcessSchema, Request

OK = "ok"


@dataclass
class ContractResult:
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == OK


def validate(req: Request, schema: ProcessSchema) -> ContractResult:
    if req.unresolved:
        return ContractResult("unresolved_meaning", req.unresolved)
    if req.scope not in schema.scopes:
        return ContractResult("unknown_target", f"scope {req.scope!r}")
    cases = schema.cases.get(req.scope, [])
    q = req.query
    if q.kind not in ("case_end_time", "case_ends_by"):
        return ContractResult("unsupported_operation", f"query {q.kind}")
    if q.case not in cases:
        return ContractResult("unknown_target", f"query case {q.case!r}")
    if q.kind == "case_ends_by" and (q.deadline is None or q.deadline < 0):
        return ContractResult("invalid_time", "deadline")
    if q.deadline is not None and not _finite(q.deadline):
        return ContractResult("invalid_time", "deadline is not a finite number")
    if not req.interventions:
        return ContractResult("unresolved_meaning", "no intervention")
    if len(req.interventions) > 1:
        return ContractResult("unsupported_operation", "only one change per request is supported")
    for iv in req.interventions:
        # NaN and infinite values are malformed, not values (guard added 2026-11-09, as in `mlsys`).
        nums = [iv.value, iv.effective_from, iv.effective_to] + list((iv.routes or {}).values())
        if any(x is not None and not _finite(x) for x in nums):
            return ContractResult("invalid_units", "a value is not a finite number")
        if iv.family not in FAMILIES or iv.op not in FAMILIES[iv.family]:
            return ContractResult("unsupported_operation", f"{iv.family}/{iv.op}")
        if iv.case is not None and iv.case not in cases:
            return ContractResult("unknown_target", f"case {iv.case!r}")
        if iv.effective_from is not None and iv.effective_to is not None and iv.effective_from >= iv.effective_to:
            return ContractResult("invalid_time", "empty interval")
        if iv.family in ("activity_duration", "timer_delay"):
            names = schema.activities if iv.family == "activity_duration" else schema.waits
            if iv.target not in names:
                return ContractResult("unknown_target", f"{iv.target!r}")
            if iv.case is None or iv.visit is None:
                return ContractResult("ambiguous_binding", "case and visit are required")
            if iv.value is None or iv.value < 0 or iv.value != int(iv.value):
                return ContractResult("invalid_units", "seconds must be a whole number of at least 0")
        elif iv.family == "routing_outcome":
            if iv.target not in schema.decisions or iv.case is None or iv.visit is None:
                return ContractResult("unknown_target" if iv.target not in schema.decisions else "ambiguous_binding", f"{iv.target}")
            if iv.value is None or not 0 <= iv.value < 1:
                return ContractResult("invalid_units", "a draw is in [0, 1)")
        elif iv.family == "routing_probability":
            if iv.case is not None or iv.effective_from is not None or iv.effective_to is not None:
                return ContractResult("unsupported_operation", "a probability change applies to the whole run")
            if iv.target not in schema.decisions:
                return ContractResult("unknown_target", f"{iv.target!r}")
            routes = iv.routes or {}
            if set(routes) != set(schema.decisions[iv.target]) or any(v < 0 for v in routes.values()) \
                    or abs(sum(routes.values()) - 1) > 1e-9:
                return ContractResult("invalid_units", "probabilities must cover every route and sum to 1")
        elif iv.family == "resource_availability":
            if iv.target not in schema.pools:
                return ContractResult("unknown_target", f"pool {iv.target!r}")
            if iv.value is None or iv.value < 1 or iv.value != int(iv.value):
                return ContractResult("invalid_units", "worker count must be a whole number of at least 1")
            if iv.op == "add_workers" and (iv.effective_from not in (None, 0) or iv.effective_to is not None):
                return ContractResult("unsupported_operation", "added workers are available throughout")
            if iv.op == "unavailable":
                if iv.value > schema.pools[iv.target]:
                    return ContractResult("invalid_units", "more workers than the pool has")
                if iv.effective_from is None or iv.effective_to is None:
                    return ContractResult("invalid_time", "an unavailable interval needs both ends")
        elif iv.family == "case_set":
            if iv.case is None:
                return ContractResult("ambiguous_binding", "which case")
            if iv.case == q.case:
                return ContractResult("unsupported_operation", "the queried case is the one removed")
    return ContractResult(OK)


def _finite(x) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError, OverflowError):
        return False
