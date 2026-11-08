"""Deterministic answers from an execution's case-end projection. No model is involved."""
from __future__ import annotations

from .request import Query


def answer(query: Query, case_ends: dict):
    """Returns (answer, detail). Answer is an int for case_end_time, a bool for case_ends_by, or None."""
    end = case_ends.get(query.case)
    if end is None:
        return None, f"no end recorded for {query.case}"
    if query.kind == "case_end_time":
        return int(round(end)), ""
    if query.kind == "case_ends_by":
        return bool(end <= query.deadline), ""
    return None, f"query {query.kind} not supported"
