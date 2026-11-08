"""Binding check: did the native change do exactly what the structured request says, and nothing else?

Run after the answering execution and before its answer is used, as handoff step 6 allows; it can only reject.
It works on a record-level diff of the backend's inputs before and after the change: records added, removed and
modified (paired by id), constants changed, and outcome overrides. A case-level change must modify exactly one
record, for the requested case and exactly the requested target, in the field for the requested visit, to the
requested value. A correct-looking answer from a wrongly bound change is rejected, so an invalid patch is never
rewarded because its answer happened to match.
"""
from __future__ import annotations

import re

from .request import Intervention


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def _names_target(rec: dict, target: str) -> bool:
    """Exact match on a field value, or on one underscore-separated token of the record id. Never a substring."""
    want = _norm(target)
    for v in (rec.get("fields") or {}).values():
        if isinstance(v, str) and _norm(v) == want:
            return True
    for key in ("activity", "name", "task", "wait", "decision"):
        if isinstance(rec.get(key), str) and _norm(rec[key]) == want:
            return True
    for e in rec.get("entities") or []:
        if isinstance(e, str) and ":" in e and _norm(e.split(":", 1)[1]) == want:
            return True
    return any(_norm(tok) == want for tok in str(rec.get("id", "")).split("_"))


def _changed_fields(old: dict, new: dict) -> dict:
    a, b = old.get("fields") or {}, new.get("fields") or {}
    out = {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}
    for k in set(old) | set(new):
        if k not in ("fields", "src") and old.get(k) != new.get(k):
            out[f"@{k}"] = (old.get(k), new.get(k))
    return out


def _visit_ok(rec: dict, key: str, visit: int) -> bool:
    fields = rec.get("fields") or {}
    for name in ("visit", "Visit"):
        if name in fields:
            try:
                return int(float(fields[name])) == visit
            except (TypeError, ValueError):
                return False
    return re.search(rf"(?<!\d){visit}(?!\d)", key) is not None


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def check_otf(iv: Intervention, binding: dict, plan_value: float | None = None, pool_size: int | None = None) -> tuple[bool, str]:
    """`binding` holds `modified` ([old, new] pairs), `added`, `removed`, `params_changed` ({name: [old, new]}),
    `overrides` and `errors`, as `OTFBackend.native_what_if` reports them."""
    if binding.get("errors"):
        return False, "patch errors: " + "; ".join(binding["errors"])[:200]
    modified = binding.get("modified") or []
    added, removed = binding.get("added") or [], binding.get("removed") or []
    params, overrides = binding.get("params_changed") or {}, binding.get("overrides") or []
    if overrides:
        return False, f"{len(overrides)} outcome overrides"
    if iv.family in ("activity_duration", "timer_delay", "routing_outcome"):
        if params or added or removed:
            return False, f"extra changes: {len(params)} constants, {len(added)} added, {len(removed)} removed"
        if not modified:
            if plan_value is not None and iv.value is not None and abs(plan_value - iv.value) < 1e-6:
                return True, "the request equals the recorded plan value, so nothing needed changing"
            return False, "no input record changed"
        if len(modified) != 1:
            return False, f"{len(modified)} input records changed, expected exactly 1"
        if binding.get("order_changed"):
            return False, "the order of the input records changed"
        old, new = modified[0]
        if iv.case not in [str(e) for e in new.get("entities") or []]:
            return False, "the changed record is not the requested case"
        if not _names_target(new, iv.target):
            return False, f"the changed record is not exactly {iv.target!r}"
        changes = _changed_fields(old, new)
        if len(changes) != 1:
            return False, f"{len(changes)} fields changed in the record: {sorted(changes)}"
        key, (_, value) = next(iter(changes.items()))
        if key.startswith("@"):
            return False, f"the record's {key[1:]!r} attribute changed, not a plan field"
        if _num(value) is None or abs(_num(value) - float(iv.value)) > 1e-6:
            return False, f"field {key} was set to {value!r}, not {iv.value}"
        if not _visit_ok(new, key, iv.visit):
            return False, f"cannot confirm the change is for visit {iv.visit} (field {key!r})"
        return True, "exactly the requested record and field changed"
    if iv.family == "case_set" and iv.op == "remove":
        if params or added or modified:
            return False, "a removal must only remove records"
        if not removed or any(iv.case not in [str(e) for e in r.get("entities") or []] for r in removed):
            return False, "removed records are not all the requested case's"
        expected = binding.get("case_input_count", {}).get(iv.case)
        if expected is not None and len(removed) != expected:
            return False, f"removed {len(removed)} of the case's {expected} inputs"
        return True, "all of the case's inputs removed, nothing else"
    if iv.family == "resource_availability" and iv.op == "add_workers":
        if added or removed or modified:
            return False, "inputs changed as well as constants"
        want = _norm(iv.target)
        keys = [k for k in params if want and want in _norm(k)]
        if len(keys) != 1 or len(params) != 1:
            return False, f"constants changed: {sorted(params)}"
        old, new = params[keys[0]]
        base = pool_size if pool_size is not None else _num(old)
        if _num(new) is None or base is None or abs(_num(new) - (base + iv.value)) > 1e-9:
            return False, f"{keys[0]} set to {new}, expected {base} + {iv.value}"
        return True, f"{keys[0]} increased by {iv.value}"
    return False, f"this backend has no input that can express {iv.family}/{iv.op}"
