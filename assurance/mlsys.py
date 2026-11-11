"""Assurance for the manufacturing and IT operations domains (the MLSys documents), on the library's pattern.

Separate from the workflow modules on purpose: the workflow `Intervention`, `Query` and `Request` classes, and the
seeds `policy.request_seed` derives from their `__dict__`, are untouched. Everything here is built from the
document (its document map) and the structured request only. No reference code, gold or hidden binding is read.

Families (sim.py's input changes in the MLSys reference, written here in the library's request style):

| family | op | target | day | value | resource |
|---|---|---|---|---|---|
| order_removal | remove | product | day the order was placed | | |
| production_quantity | set | product | production day | units | |
| production_timing | delay | product | production day | days of delay | |
| dispatch_capacity | scale | | first day of the change | factor | |
| job_removal | remove | job | | | |
| failure_removal | remove | machine | | | |
| task_priority | set | task | | priority | |
| task_request | set | task | | units | "cpu" or "mem" |
| machine_removal | remove | machine | | | |

Queries: `stock_end_of_day` and `backordered_end_of_day` (product, day; whole units), `task_start_time` (task;
seconds) and `task_starts_by` (task, deadline; yes or no).

Every execution is reduced to one canonical outcome form, so probes and answers do not depend on a program's own
record names:
- manufacturing: {(column, product, day): units} for the ledger columns shipped, backordered and stock;
- IT: a list of (time, event, task, machine) events, event one of start, finish, evict, fail.
An OTF program's own record kinds are mapped to these from its factual records' `src` (which document table cell
each record was read from), learned per program and chapter from the document alone. If that mapping does not
reproduce the printed record, the history check fails, as in the workflow adapter.
"""
from __future__ import annotations

import copy
import hashlib
import math
import json
import os
import random
import re
import subprocess
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from .backends import Execution, OTFBackend, _count_by_case, _record_diff
from .contract import ContractResult, OK
from .policy import Decision
from .registry import Evidence, Key, Registry

MFG, IT = "manufacturing", "it_ops"
FAMILIES = {
    "order_removal": (MFG, {"remove"}), "production_quantity": (MFG, {"set"}), "production_timing": (MFG, {"delay"}),
    "dispatch_capacity": (MFG, {"scale"}),
    "job_removal": (IT, {"remove"}), "failure_removal": (IT, {"remove"}), "task_priority": (IT, {"set"}),
    "task_request": (IT, {"set"}), "machine_removal": (IT, {"remove"}),
}
QUERIES = {"stock_end_of_day": MFG, "backordered_end_of_day": MFG, "task_start_time": IT, "task_starts_by": IT}
LEDGER_COLS = ("shipped", "backordered", "stock")
EVENTS = ("start", "finish", "evict", "fail")
FREE_MAX, MAX_PRIORITY = 1, 11
IT_HORIZON = 10 ** 8
CONFIGS = ("native", "replay", "schema", "generic", "directed", "program_wide")


# ---------------------------------------------------------------- request types
@dataclass(frozen=True)
class Change:
    family: str
    op: str
    target: str | None = None
    day: int | None = None
    value: float | None = None
    resource: str | None = None


@dataclass(frozen=True)
class DQuery:
    kind: str
    entity: str                  # product or task
    day: int | None = None       # manufacturing: end of this day
    deadline: int | None = None  # task_starts_by


@dataclass
class DRequest:
    scope: str
    interventions: list[Change]
    query: DQuery
    unresolved: str | None = None

    def key(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


def request_from_binding(scope: str, binding: dict, query: dict) -> DRequest:
    """The hidden binding of a question file row as a request (the oracle request source, for ablations)."""
    b = binding
    iv = Change(b["family"], b["op"], target=b.get("target"), day=b.get("day"),
                value=None if b.get("value") is None else float(b["value"]), resource=b.get("resource"))
    ent = query.get("product") if "product" in query else query.get("task")
    return DRequest(scope, [iv], DQuery(query["kind"], str(ent), query.get("day"), query.get("deadline")))


# ---------------------------------------------------------------- schema, from the document map only
def _node(nav, title, kind="table"):
    return next((n for n in nav["nodes"] if n["title"] == title and n["kind"] == kind), None)


def _node_prefix(nav, prefix, kind="table"):
    return next((n for n in nav["nodes"] if n["title"].startswith(prefix) and n["kind"] == kind), None)


def _rows(node):
    if node is None:
        return []
    cols = node["table"]["columns"]
    return [dict(zip(cols, r)) for r in node["table"]["rows"]]


def _int(x):
    return None if x in (None, "", "-", "never") else int(float(x))


def domain_of(nav) -> str | None:
    front = next((n for n in nav["nodes"] if n["level"] == 0 and n["kind"] == "list"), None)
    title = front["title"] if front else ""
    return MFG if title.startswith("Plant Stock") else IT if title.startswith("Compute Cell") else None


@dataclass
class DomainSchema:
    domain: str
    policy_text: str
    scopes: list
    chapters: dict            # scope -> facts printed in that chapter

    def policy_fingerprint(self) -> str:
        """Hash of the stated policy. The front matter's last line lists the document's own chapters
        ("Chapters in this document (...)"); it is not policy, and is dropped so one policy has one fingerprint
        across documents (review 1)."""
        text = re.sub(r"\s+", " ", self.policy_text).strip()
        text = re.sub(r"Chapters in this document.*$", "", text).strip()
        return hashlib.sha256(text.encode()).hexdigest()[:16]


def schema_from_map(nav: dict) -> DomainSchema:
    dom = domain_of(nav)
    if dom is None:
        raise ValueError("not a manufacturing or IT operations document map")
    front = next(n for n in nav["nodes"] if n["level"] == 0 and n["kind"] == "list")
    policy = "\n".join(front.get("lines", []))
    heads = [n for n in nav["nodes"] if n["level"] == 0 and n["kind"] != "list"]
    chapters = {}
    for h in heads:
        s = h["title"]
        if dom == MFG:
            prods = {r["product"]: (round(float(r["kg per unit"]) * 1000), int(r["opening stock"]))
                     for r in _rows(_node(nav, f"{s}: Products"))}
            ledger = {(int(r["day"]), r["product"]): {k: int(r[k]) for k in ("produced", "ordered") + LEDGER_COLS}
                      for r in _rows(_node(nav, f"{s}: Daily ledger"))}
            book = {(int(r["day"]), r["product"]): (int(r["planned production"]), int(r["ordered"]))
                    for r in _rows(_node_prefix(nav, f"{s}: Order book: Orders received"))}
            m = re.search(r"Daily dispatch capacity:\s*(\d+)\s*kg", h.get("text", ""))
            days = sorted({d for d, _ in ledger})
            chapters[s] = {"products": prods, "ledger": ledger, "book": book,
                           "capacity_kg": int(m.group(1)) if m else None,
                           "first": days[0] if days else None, "last": days[-1] if days else None,
                           "book_days": sorted({d for d, _ in book})}
        else:
            machines = {r["machine"]: {"cpu": int(r["CPU"]), "mem": int(r["memory"]), "down": _int(r["fails at"]),
                                       "back": _int(r["returns at"])} for r in _rows(_node(nav, f"{s}: Machines"))}
            log, tasks = [], {}
            for r in _rows(_node(nav, f"{s}: Task log")):
                if r["event"] == "submit":
                    tasks[r["task"]] = {"job": r["job"], "pri": int(r["priority"]), "cpu": int(r["CPU"]),
                                        "mem": int(r["memory"]), "submit": int(r["time"]), "run": int(r["run time"])}
                elif r["event"] in EVENTS:
                    log.append((int(r["time"]), r["event"], r["task"], r["machine"]))
            m = re.search(r"Times\s+0\s+to\s+(\d+)", h.get("text", ""))
            chapters[s] = {"machines": machines, "tasks": tasks, "log": log, "W": int(m.group(1)) if m else None,
                           "jobs": sorted({a["job"] for a in tasks.values()})}
    return DomainSchema(dom, policy, [h["title"] for h in heads], chapters)


# ---------------------------------------------------------------- contract
def validate(req: DRequest, schema: DomainSchema) -> ContractResult:
    if req.unresolved:
        return ContractResult("unresolved_meaning", req.unresolved)
    if req.scope not in schema.scopes:
        return ContractResult("unknown_target", f"scope {req.scope!r}")
    ch, q = schema.chapters[req.scope], req.query
    if QUERIES.get(q.kind) != schema.domain:
        return ContractResult("unsupported_operation", f"query {q.kind}")
    if not req.interventions:
        return ContractResult("unresolved_meaning", "no intervention")
    if len(req.interventions) > 1:
        return ContractResult("unsupported_operation", "only one change per request is supported")
    iv = req.interventions[0]
    if iv.value is not None and not math.isfinite(iv.value):
        return ContractResult("invalid_units", "the value is not a finite number")
    fam = FAMILIES.get(iv.family)
    if fam is None or fam[0] != schema.domain or iv.op not in fam[1]:
        return ContractResult("unsupported_operation", f"{iv.family}/{iv.op}")
    if schema.domain == MFG:
        if q.entity not in ch["products"]:
            return ContractResult("unknown_target", f"query product {q.entity!r}")
        if q.day is None or not ch["first"] <= q.day <= ch["last"]:
            return ContractResult("invalid_time", "the query day must be a day of the chapter's ledger")
        days = set(range(ch["first"], ch["last"] + 1)) | set(ch["book_days"])
        if iv.family != "dispatch_capacity":
            if iv.target not in ch["products"]:
                return ContractResult("unknown_target", f"product {iv.target!r}")
            if iv.day is None or iv.day not in days:
                return ContractResult("invalid_time", f"day {iv.day}")
        flow = ch["ledger"].get((iv.day, iv.target)) if iv.day is not None else None
        prod, order = (flow["produced"], flow["ordered"]) if flow else ch["book"].get((iv.day, iv.target), (None, None))
        if iv.family == "order_removal" and not order:
            return ContractResult("unknown_target", f"no order for {iv.target} placed on day {iv.day}")
        if iv.family == "production_quantity" and (iv.value is None or iv.value < 0 or iv.value != int(iv.value)):
            return ContractResult("invalid_units", "production is a whole number of units, at least 0")
        if iv.family == "production_timing":
            if iv.value is None or iv.value < 1 or iv.value != int(iv.value):
                return ContractResult("invalid_units", "a delay is a whole number of days, at least 1")
            if not prod:
                return ContractResult("unknown_target", f"no production of {iv.target} on day {iv.day}")
        if iv.family == "dispatch_capacity":
            if iv.value is None or iv.value <= 0:
                return ContractResult("invalid_units", "a capacity factor must be above 0")
            if iv.day is None or iv.day not in days:
                return ContractResult("invalid_time", f"day {iv.day}")
        return ContractResult(OK)
    tasks, machines = ch["tasks"], ch["machines"]
    if q.entity not in tasks:
        return ContractResult("unknown_target", f"query task {q.entity!r}")
    if q.kind == "task_starts_by" and (q.deadline is None or q.deadline < 0):
        return ContractResult("invalid_time", "deadline")
    if iv.family == "job_removal":
        if iv.target not in ch["jobs"]:
            return ContractResult("unknown_target", f"job {iv.target!r}")
        if tasks[q.entity]["job"] == iv.target:
            return ContractResult("unsupported_operation", "the queried task belongs to the removed job")
    elif iv.family in ("failure_removal", "machine_removal"):
        if iv.target not in machines:
            return ContractResult("unknown_target", f"machine {iv.target!r}")
        if iv.family == "failure_removal" and machines[iv.target]["down"] is None:
            return ContractResult("unknown_target", f"machine {iv.target} has no failure in the record")
    else:
        if iv.target not in tasks:
            return ContractResult("unknown_target", f"task {iv.target!r}")
        if iv.value is None or iv.value != int(iv.value):
            return ContractResult("invalid_units", "a whole number is required")
        if iv.family == "task_priority" and not 0 <= iv.value <= MAX_PRIORITY:
            return ContractResult("invalid_units", "priority is 0 to 11")
        if iv.family == "task_request":
            if iv.resource not in ("cpu", "mem"):
                return ContractResult("ambiguous_binding", "which resource: cpu or mem")
            if iv.value < 1:
                return ContractResult("invalid_units", "a request is at least 1 unit")
    return ContractResult(OK)


# ---------------------------------------------------------------- generic inputs (the shared stdin format)
def inputs_from_schema(schema: DomainSchema, scope: str) -> dict:
    """The generic input object for one chapter or window, built from the printed tables only."""
    ch = schema.chapters[scope]
    if schema.domain == MFG:
        flows = {k: [v["produced"], v["ordered"]] for k, v in ch["ledger"].items()}
        flows.update({k: [p, o] for k, (p, o) in ch["book"].items()})
        days = sorted({d for d, _ in flows})
        return {"products": [{"product": p, "kg_per_unit": g / 1000, "opening_stock": n}
                             for p, (g, n) in sorted(ch["products"].items())],
                "days": [{"day": d, "capacity_kg": ch["capacity_kg"]} for d in days],
                "flows": [{"day": d, "product": p, "produced": v[0], "ordered": v[1]} for (d, p), v in sorted(flows.items())]}
    return {"window_end": ch["W"],
            "machines": [{"machine": m, "cpu": a["cpu"], "memory": a["mem"], "fails_at": a["down"], "returns_at": a["back"]}
                         for m, a in sorted(ch["machines"].items())],
            "tasks": [{"task": t, "job": a["job"], "priority": a["pri"], "cpu": a["cpu"], "memory": a["mem"],
                       "submit": a["submit"], "run_time": a["run"]} for t, a in sorted(ch["tasks"].items())]}


def scaled_kg(kg, factor) -> float:
    """A scaled capacity in kg, rounded to whole grams as the stated policy computes capacity (review 1)."""
    return round(kg * 1000 * factor) / 1000


def apply_inputs(data: dict, iv: Change) -> dict | None:
    """The change written into the generic input. None if the input has no place for it."""
    d = copy.deepcopy(data)
    if iv.family in ("order_removal", "production_quantity", "production_timing"):
        hit = [x for x in d["flows"] if x["product"] == iv.target and x["day"] == iv.day]
        if not hit:
            return None
        x = hit[0]
        if iv.family == "order_removal":
            x["ordered"] = 0
        elif iv.family == "production_quantity":
            x["produced"] = int(iv.value)
        else:
            q, x["produced"] = x["produced"], 0
            to = [y for y in d["flows"] if y["product"] == iv.target and y["day"] == iv.day + int(iv.value)]
            if to:
                to[0]["produced"] += q
        return d
    if iv.family == "dispatch_capacity":
        for x in d["days"]:
            if x["day"] >= iv.day:
                x["capacity_kg"] = scaled_kg(x["capacity_kg"], iv.value)
        return d
    if iv.family == "job_removal":
        d["tasks"] = [t for t in d["tasks"] if t["job"] != iv.target]
        return d
    if iv.family == "failure_removal":
        for m in d["machines"]:
            if m["machine"] == iv.target:
                m["fails_at"] = m["returns_at"] = None
        return d
    if iv.family == "machine_removal":
        d["machines"] = [m for m in d["machines"] if m["machine"] != iv.target]
        return d
    if iv.family in ("task_priority", "task_request"):
        hit = [t for t in d["tasks"] if t["task"] == iv.target]
        if not hit:
            return None
        key = "priority" if iv.family == "task_priority" else ("cpu" if iv.resource == "cpu" else "memory")
        hit[0][key] = int(iv.value)
        return d
    return None


# ---------------------------------------------------------------- document edits, for OTF's diagnostic path
def _set_cells(table_node, match, col, fn):
    cols = table_node["table"]["columns"]
    j = cols.index(col)
    n = 0
    for r in table_node["table"]["rows"]:
        if match(dict(zip(cols, r))):
            r[j] = fn(r[j])
            n += 1
    return n


def edit_nav(nav: dict, schema: DomainSchema, scope: str, iv: Change, params: dict):
    """A copy of the document map with the change written into the printed inputs, plus any constant edit.
    Returns (nav, params_edit) or None when the change has no printed input the program could read (for example
    a capacity change from a later day, for a program whose capacity is one constant)."""
    out = copy.deepcopy(nav)
    ch = schema.chapters[scope]
    if schema.domain == MFG:
        if iv.family == "dispatch_capacity":
            keys = [k for k, v in params.items() if _num(v) is not None and abs(_num(v) - ch["capacity_kg"]) < 1e-9]
            if iv.day != ch["first"] or len(keys) != 1:
                return None
            return out, {keys[0]: scaled_kg(ch["capacity_kg"], iv.value)}
        ledger = _node(out, f"{scope}: Daily ledger")
        book = _node_prefix(out, f"{scope}: Order book: Orders received")

        def cell(day, col_ledger, col_book, fn):
            if day <= ch["last"]:
                return _set_cells(ledger, lambda r: int(r["day"]) == day and r["product"] == iv.target, col_ledger, fn)
            if book is None:
                return 0
            return _set_cells(book, lambda r: int(r["day"]) == day and r["product"] == iv.target, col_book, fn)
        if iv.family == "order_removal":
            n = cell(iv.day, "ordered", "ordered", lambda _: "0")
        elif iv.family == "production_quantity":
            n = cell(iv.day, "produced", "planned production", lambda _: str(int(iv.value)))
        else:
            flow = ch["ledger"].get((iv.day, iv.target))
            q = flow["produced"] if flow else ch["book"].get((iv.day, iv.target), (0, 0))[0]
            n = cell(iv.day, "produced", "planned production", lambda _: "0")
            cell(iv.day + int(iv.value), "produced", "planned production", lambda v: str(int(v) + q))
        return (out, None) if n == 1 else None
    log = _node(out, f"{scope}: Task log")
    mach = _node(out, f"{scope}: Machines")
    queue = [n for n in out["nodes"] if n["title"].startswith(f"{scope}: Queue at window end:") and n["kind"] == "table"]
    if iv.family == "job_removal":
        for node in [log] + queue:
            cols = node["table"]["columns"]
            j = cols.index("job")
            node["table"]["rows"] = [r for r in node["table"]["rows"] if r[j] != iv.target]
        return out, None
    if iv.family in ("task_priority", "task_request"):
        col = "priority" if iv.family == "task_priority" else ("CPU" if iv.resource == "cpu" else "memory")
        n = 0
        for node in [log] + queue:
            if col in node["table"]["columns"]:
                n += _set_cells(node, lambda r: r["task"] == iv.target, col, lambda _: str(int(iv.value)))
        return (out, None) if n else None
    if iv.family in ("failure_removal", "machine_removal"):
        pat = re.compile(rf"\b(machine|Machine) {re.escape(iv.target)} (failed|returned|is down)")
        for node in out["nodes"]:
            if node["title"].startswith(f"{scope}: ") and node["kind"] == "list":
                node["lines"] = [ln for ln in node.get("lines", []) if not pat.search(ln)]
    if iv.family == "failure_removal":
        n = _set_cells(mach, lambda r: r["machine"] == iv.target, "fails at", lambda _: "-")
        _set_cells(mach, lambda r: r["machine"] == iv.target, "returns at", lambda _: "-")
        return (out, None) if n == 1 else None
    if iv.family == "machine_removal":
        before = len(mach["table"]["rows"])
        mach["table"]["rows"] = [r for r in mach["table"]["rows"] if r[0] != iv.target]
        return (out, None) if len(mach["table"]["rows"]) == before - 1 else None
    return None


# ---------------------------------------------------------------- canonical outcomes and answers
def printed(schema: DomainSchema, scope: str):
    ch = schema.chapters[scope]
    if schema.domain == MFG:
        return {(c, p, d): v[c] for (d, p), v in ch["ledger"].items() for c in LEDGER_COLS}
    return sorted(e for e in ch["log"] if e[0] <= ch["W"])


def _ev_key(e):
    return (e[0], e[2], e[1], e[3] or "")


def answer(query: DQuery, canon):
    """(answer, detail): an int for the count and start-time queries, a bool for task_starts_by, or None."""
    if query.kind in ("stock_end_of_day", "backordered_end_of_day"):
        col = "stock" if query.kind == "stock_end_of_day" else "backordered"
        v = (canon or {}).get((col, query.entity, query.day))
        return (None, f"no {col} for {query.entity} on day {query.day}") if v is None else (int(v), "")
    starts = [e[0] for e in canon or [] if e[1] == "start" and e[2] == query.entity]
    if not starts:
        return None, f"no start recorded for {query.entity}"
    s = min(starts)
    if query.kind == "task_start_time":
        return int(s), ""
    if query.kind == "task_starts_by":
        return bool(s <= query.deadline), ""
    return None, f"query {query.kind} not supported"


def replay_ok(schema, scope, canon) -> tuple[bool, str]:
    want = printed(schema, scope)
    if schema.domain == MFG:
        wrong = [k for k, v in want.items() if (canon or {}).get(k) != v]
        return (not wrong), (f"{len(wrong)} of {len(want)} ledger cells differ" if wrong else "every ledger cell matches")
    W = schema.chapters[scope]["W"]
    mine = Counter(e for e in canon or [] if e[0] <= W)
    ref = Counter(want)
    diff = sum(((mine - ref) + (ref - mine)).values())
    return diff == 0, (f"{diff} task-log events differ" if diff else "every task-log event matches")


# ---------------------------------------------------------------- backends
def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class OTFDomain:
    """An OTF-Tools program on these domains, run unchanged with its own engine code. `nav` may be another
    document's map (reuse on new records); the program's code is never changed."""

    name = "otf"
    adapter_version = "otf-mlsys-0.2"

    def __init__(self, program_path: Path, system: str, root: Path, nav: dict | None = None):
        self.inner = OTFBackend(program_path, system, root)
        if nav is not None:
            self.inner.nav = nav
        self.nav = self.inner.nav
        self.schema = schema_from_map(self.nav)
        self.code, self.records, self.sandbox, self.toolgen = (self.inner.code, self.inner.records,
                                                                self.inner.sandbox, self.inner.toolgen)
        self.adapter_version = self.inner.adapter_version.replace("otf-adapter-0.2", OTFDomain.adapter_version)
        self._maps = {}

    def program_hash(self) -> str:
        return self.inner.program_hash()

    def horizon(self, scope):
        return self.schema.chapters[scope]["last"] if self.schema.domain == MFG else IT_HORIZON

    def params(self, scope) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            m = Path(tmp) / "map.json"
            m.write_text(json.dumps(self.nav))
            return dict(self.toolgen.read_scope(self.code, m, scope)["params"])

    def kind_map(self, scope) -> dict:
        """record kind -> ledger column or task-log event, from the factual records' `src` (document cells)."""
        if scope in self._maps:
            return self._maps[scope]
        with tempfile.TemporaryDirectory() as tmp:
            m = Path(tmp) / "map.json"
            m.write_text(json.dumps(self.nav))
            try:
                r = self.toolgen.read_scope(self.code, m, scope)
            except Exception:
                self._maps[scope] = {}
                return {}
        nodes = {n["node_id"]: n for n in self.nav["nodes"]}
        votes: dict = {}
        for o in r["outcomes"]:
            for src in o.get("src") or []:
                if not (isinstance(src, (list, tuple)) and len(src) == 3 and isinstance(src[1], int)
                        and isinstance(src[2], (list, tuple))):
                    continue                    # a list-line source, not a table cell
                nid, row, cols = src
                node = nodes.get(nid)
                if node is None or node.get("kind") != "table":
                    continue
                if self.schema.domain == MFG and node["title"] == f"{scope}: Daily ledger":
                    hit = [c for c in cols if c in LEDGER_COLS]
                    if len(hit) == 1:
                        votes.setdefault(o.get("kind"), set()).add(hit[0])
                elif self.schema.domain == IT and node["title"] == f"{scope}: Task log":
                    tcols = node["table"]["columns"]
                    ev = node["table"]["rows"][row][tcols.index("event")] if row < len(node["table"]["rows"]) else None
                    if ev in EVENTS:
                        votes.setdefault(o.get("kind"), set()).add(ev)
        self._maps[scope] = {k: next(iter(v)) for k, v in votes.items() if len(v) == 1 and k is not None}
        return self._maps[scope]

    def project(self, scope, recs):
        km = self.kind_map(scope)
        if self.schema.domain == MFG:
            prods = set(self.schema.chapters[scope]["products"])
            out = {}
            for o in recs:
                col = km.get(o.get("kind"))
                t, v = o.get("time"), _num(o.get("value"))
                ent = next((str(e) for e in o.get("entities") or [] if str(e) in prods), None)
                if col and t is not None and v is not None and ent:
                    out[(col, ent, int(round(float(t))))] = int(round(v))
            return out
        out = []
        for o in recs:
            ev = km.get(o.get("kind"))
            t = o.get("time")
            ents = [str(e) for e in o.get("entities") or []]
            task = next((e for e in ents if re.fullmatch(r"T\d+", e)), None)
            mach = next((e for e in ents if re.fullmatch(r"M\d+", e)), None)
            if ev and t is not None and task:
                out.append((int(round(float(t))), ev, task, mach))
        return sorted(out, key=_ev_key)

    def run_map(self, nav, scope, params_edit=None) -> Execution:
        """Simulate from just before the first outcome, outcomes hidden, as the program's own check does, with
        this domain's horizon (the last ledger day; a workflow seconds horizon makes day loops time out)."""
        with tempfile.TemporaryDirectory() as tmp:
            m = Path(tmp) / "map.json"
            m.write_text(json.dumps(nav))
            try:
                r = self.toolgen.read_scope(self.code, m, scope)
            except Exception as e:
                return Execution("read_failed", detail=str(e)[:200])
            cut = self.toolgen._cut(r)
            blind = self.toolgen.blinded_map(nav, m, scope, r, cut)
            params = dict(r["params"])
            if params_edit:
                params.update(params_edit)
            ok, out = self.sandbox.run(self.code, "simulate", blind, [scope],
                                       {"inputs": r["inputs"], "params": params, "start": cut,
                                        "horizon": self.horizon(scope)})
            blind.unlink(missing_ok=True)
        if not ok or not isinstance(out, list):
            return Execution("crashed", detail=str(out)[-200:])
        kept = [o for o in r["outcomes"] if self.records.rtime(o) is not None and self.records.rtime(o) <= cut]
        recs = kept + out
        return Execution("ran", case_ends={"canon": self.project(scope, recs)}, records=recs)

    def execute(self, scope, iv: Change | None) -> Execution | None:
        if iv is None:
            return self.run_map(self.nav, scope)
        e = edit_nav(self.nav, self.schema, scope, iv, self.params(scope))
        if e is None:
            return None
        nav, pe = e
        return self.run_map(nav, scope, pe)

    def native_what_if(self, scope, question, llm):
        """OTF's own answer path (its LLM patch step, restart and replay), unchanged. The execution's canonical
        outcomes are in `case_ends["canon"]`; the binding dict is the record diff for `check_otf`."""
        ex, binding = self.inner.native_what_if(scope, question, llm)
        if ex.status == "ran":
            ex = Execution("ran", case_ends={"canon": self.project(scope, ex.records)}, records=ex.records)
        return ex, binding


class DEVSDomain:
    """A DEVS-Gen (or any stdin-reading) program for these domains, run unchanged inside WSL under bubblewrap."""

    name = "devs_gen"
    adapter_version = "devs-mlsys-0.2"

    def __init__(self, wsl_program_dir: str, schema: DomainSchema, runner=None):
        self.dir, self.schema = wsl_program_dir, schema
        self._hash = None
        self.runner = runner or self._wsl          # tests pass a local runner

    def program_hash(self) -> str:
        if self._hash is None:
            from .backends import DEVSBackend
            self._hash = DEVSBackend(self.dir, "", Path(".")).program_hash()
        return self._hash

    def horizon(self, scope):
        ch = self.schema.chapters[scope]
        return ch["last"] if self.schema.domain == MFG else IT_HORIZON

    def _wsl(self, data, horizon, timeout):
        from .backends import sandbox_command
        venv = "$HOME/trust2027/devs_gen_code/.venvs/devs-gen"
        # Hardened 2026-11-10 (see `backends.sandbox_command`).
        import shlex
        cmd = f"cd {shlex.quote(str(self.dir))} && " + sandbox_command(self.dir, f"{venv}/bin/python run.py --horizon {horizon}")
        p = subprocess.run(["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c", cmd], input=json.dumps(data),
                           capture_output=True, text=True, timeout=timeout, env={**os.environ, "MSYS_NO_PATHCONV": "1"})
        return p.returncode, p.stdout, p.stderr

    def run_input(self, scope, data, timeout=60) -> Execution:
        try:
            code, stdout, stderr = self.runner(data, self.horizon(scope), timeout)
        except subprocess.TimeoutExpired:
            return Execution("crashed", detail="timeout")
        events, bad = [], 0
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                bad += 1
        if code != 0:
            return Execution("crashed", detail=f"exit {code}, {len(events)} events: " + (stderr or "")[-300:])
        return Execution("ran", case_ends={"canon": parse_events(self.schema.domain, events)}, records=events,
                         detail=f"unparsed lines {bad}" if bad else "")

    def execute(self, scope, iv: Change | None) -> Execution | None:
        data = inputs_from_schema(self.schema, scope)
        if iv is not None:
            data = apply_inputs(data, iv)
            if data is None:
                return None
        return self.run_input(scope, data)


def parse_events(domain, events) -> object:
    """Canonical outcomes from the generic output format (see the shared task specs)."""
    if domain == MFG:
        out = {}
        for e in events:
            if isinstance(e, dict) and e.get("event") == "ledger" and e.get("product") is not None and e.get("day") is not None:
                for c in LEDGER_COLS:
                    if _num(e.get(c)) is not None:
                        out[(c, str(e["product"]), int(e["day"]))] = int(round(_num(e[c])))
        return out
    out = []
    for e in events:
        if isinstance(e, dict) and e.get("event") in EVENTS and e.get("task") is not None and _num(e.get("time")) is not None:
            out.append((int(round(_num(e["time"]))), e["event"], str(e["task"]),
                        None if e.get("machine") is None else str(e["machine"])))
    return sorted(out, key=_ev_key)


# ---------------------------------------------------------------- probes
def change_time(schema, scope, iv: Change):
    """The earliest day or time at which the change can act, by the stated rules (None: from the start)."""
    ch = schema.chapters[scope]
    if schema.domain == MFG:
        return iv.day
    if iv.family == "job_removal":
        subs = [a["submit"] for a in ch["tasks"].values() if a["job"] == iv.target]
        return min(subs) if subs else None
    if iv.family == "failure_removal":
        return ch["machines"][iv.target]["down"]
    if iv.family in ("task_priority", "task_request"):
        return ch["tasks"][iv.target]["submit"]
    return None


def _before(schema, canon, t):
    if t is None:
        return None
    if schema.domain == MFG:
        return {k: v for k, v in (canon or {}).items() if k[2] < t}
    return [e for e in canon or [] if e[0] < t]


def _grams(schema, scope):
    return {p: g for p, (g, _) in schema.chapters[scope]["products"].items()}


class ProbeRunner:
    """Probes through one backend's deterministic diagnostic path. Expectations come only from the document's
    stated rules and printed records. A result of None means the probe could not be run, never a pass."""

    def __init__(self, backend, nav, schema: DomainSchema):
        self.backend, self.nav, self.schema = backend, nav, schema
        self._base = {}
        self.executions = 0

    def execute(self, scope, iv):
        if iv is not None:
            self.executions += 1
        ex = self.backend.execute(scope, iv)
        if ex is None and iv is not None:
            self.executions -= 1
        return ex

    def base(self, scope):
        if scope not in self._base:
            self._base[scope] = self.execute(scope, None)
        return self._base[scope]

    @staticmethod
    def canon(ex):
        return (ex.case_ends or {}).get("canon")

    def replay(self, scope) -> tuple[bool, str]:
        ex = self.base(scope)
        if ex is None or ex.status != "ran":
            return False, f"factual run {getattr(ex, 'status', 'none')}: {getattr(ex, 'detail', '')}"
        return replay_ok(self.schema, scope, self.canon(ex))

    # -- witnesses: other permitted inputs of the same family, with a change whose effect the rules guarantee
    def witnesses(self, scope, family, k, rng, avoid=None) -> list:
        ch, s = self.schema.chapters[scope], self.schema
        out = []
        if s.domain == MFG:
            days = range(ch["first"], ch["last"] + 1)
            prods = sorted(ch["products"])
            if family == "order_removal":
                cands = [(p, d) for d in days for p in prods if ch["ledger"][(d, p)]["ordered"] > 0]
                make = lambda p, d: Change(family, "remove", target=p, day=d)
            elif family == "production_quantity":
                cands = [(p, d) for d in days for p in prods]
                make = lambda p, d: Change(family, "set", target=p, day=d,
                                           value=float(ch["ledger"][(d, p)]["produced"] + max(100, ch["ledger"][(d, p)]["produced"])))
            elif family == "production_timing":
                cands = [(p, d) for d in days for p in prods if ch["ledger"][(d, p)]["produced"] > 0]
                make = lambda p, d: Change(family, "delay", target=p, day=d, value=1.0)
            elif family == "dispatch_capacity":
                w = Change(family, "scale", day=ch["first"], value=0.5)
                return [w] if self._first_capacity_cut(scope, w) is not None else []
            else:
                return []
            rng.shuffle(cands)
            cands.sort(key=lambda x: avoid is not None and (x[0], x[1]) == (avoid.target, avoid.day))
            return [make(p, d) for p, d in cands[:k]]
        tasks, machines, log = ch["tasks"], ch["machines"], ch["log"]
        if family == "job_removal":
            started = {e[2] for e in log if e[1] == "start"}
            cands = sorted({a["job"] for t, a in tasks.items() if t in started})
            make = lambda j: Change(family, "remove", target=j)
        elif family == "failure_removal":
            cands = sorted({e[3] for e in log if e[1] == "fail"})
            make = lambda m: Change(family, "remove", target=m)
        elif family == "task_priority":
            cands = sorted({e[2] for e in log if e[1] == "evict" and tasks[e[2]]["pri"] <= FREE_MAX})
            make = lambda t: Change(family, "set", target=t, value=5.0)
        elif family == "task_request":
            res = avoid.resource if avoid is not None and avoid.resource in ("cpu", "mem") else rng.choice(["cpu", "mem"])
            other = "mem" if res == "cpu" else "cpu"
            big = max(a[res] for a in machines.values()) + 1
            # a value no machine can hold in `res`, but that some machine could hold if it were read as `other`,
            # so a program that writes the change into the wrong resource is not let through
            up_end = [m for m in machines.values() if m["down"] is None or m["back"] is not None]
            started = sorted({e[2] for e in log if e[1] == "start"})
            sharp = [t for t in started if any(m[other] >= big and m[res] >= tasks[t][res] for m in up_end)]
            # positive witness (review 2): a value some machine up at the end can hold in `res`, but no machine could
            # hold if it were read as `other`; a correct program must then start and finish the task
            pos_v = max(a[other] for a in machines.values()) + 1
            pos = [t for t in started if any(m[res] >= pos_v and m[other] >= tasks[t][other] for m in up_end)]
            rest = [t for t in started if t not in sharp]
            for x in (sharp, pos, rest):
                rng.shuffle(x)
            disc = [Change(family, "set", target=t, value=float(big), resource=res) for t in sharp] +                    [Change(family, "set", target=t, value=float(pos_v), resource=res) for t in pos]
            rng.shuffle(disc)
            # witnesses that can tell the two resources apart come first; the others still show input use
            return (disc + [Change(family, "set", target=t, value=float(big), resource=res) for t in rest])[:k]
        elif family == "machine_removal":
            cands = sorted({e[3] for e in log if e[1] == "start"})
            make = lambda m: Change(family, "remove", target=m)
        else:
            return []
        rng.shuffle(cands)
        cands.sort(key=lambda x: avoid is not None and x == avoid.target)
        return [make(c) for c in cands[:k]]

    def _used_grams(self, scope):
        ch, g = self.schema.chapters[scope], _grams(self.schema, scope)
        return {d: sum(ch["ledger"][(d, p)]["shipped"] * g[p] for p in ch["products"]) for d in range(ch["first"], ch["last"] + 1)}

    def _first_capacity_cut(self, scope, w):
        """First day on or after the change whose recorded dispatched weight no longer fits (factor below 1)."""
        cap = self.schema.chapters[scope]["capacity_kg"] * 1000
        used = self._used_grams(scope)
        return next((d for d in sorted(used) if d >= w.day and used[d] > round(cap * w.value)), None)

    def input_use(self, scope, w: Change) -> tuple[bool | None, str]:
        ex0 = self.base(scope)
        if ex0 is None or ex0.status != "ran":
            return None, "no factual run"
        ex1 = self.execute(scope, w)
        if ex1 is None:
            return None, "the backend has no input for this change"
        if ex1.status != "ran":
            return False, f"crashed: {ex1.detail}"
        c0, c1 = self.canon(ex0), self.canon(ex1)
        s = self.schema
        t = change_time(s, scope, w)
        gaps = completeness(s, scope, apply_inputs(inputs_from_schema(s, scope), w), c1)
        if gaps:
            return False, "incomplete changed run: " + "; ".join(gaps[:2])
        if s.domain == MFG and w.family == "dispatch_capacity":
            d1 = self._first_capacity_cut(scope, w)
            if d1 is None:
                return None, "no day where the change must act"
            if _before(s, c1, d1) != _before(s, c0, d1):
                return False, f"records before day {d1} moved, although every shipment before then still fits"
            if all(c1.get(("shipped", p, d1)) == c0.get(("shipped", p, d1)) for p in s.chapters[scope]["products"]):
                return False, f"capacity x{w.value:g} from day {w.day} changed no shipment on day {d1}"
            return True, f"capacity x{w.value:g}: shipments change first on day {d1}"
        if t is not None and _before(s, c1, t) != _before(s, c0, t):
            return False, f"records before the change point {t} moved"
        if s.domain == MFG:
            same = all(c1.get((c, w.target, w.day)) == c0.get((c, w.target, w.day)) for c in ("shipped", "backordered", "stock"))
            if same:
                return False, f"{w.family} {w.target} day {w.day} changed nothing for {w.target} on day {w.day}"
            return True, f"{w.family} {w.target} day {w.day}: changed on that day, earlier days unchanged"
        if w.family == "job_removal":
            gone = {t_ for t_, a in s.chapters[scope]["tasks"].items() if a["job"] == w.target}
            left = [e for e in c1 if e[2] in gone]
            return (not left), (f"{len(left)} records of removed job {w.target}" if left else f"job {w.target} left no records")
        if w.family == "failure_removal":
            down = s.chapters[scope]["machines"][w.target]["down"]
            fails = [e for e in c1 if e[1] == "fail" and e[3] == w.target and e[0] == down]
            return (not fails), (f"tasks still fail on {w.target} at {down}" if fails else f"no failure on {w.target}")
        if w.family == "task_priority":
            ev = [e for e in c1 if e[1] == "evict" and e[2] == w.target]
            return (not ev), (f"{w.target} at priority {w.value:g} was still evicted" if ev else f"{w.target} no longer evicted")
        if w.family == "task_request":
            st = [e for e in c1 if e[1] == "start" and e[2] == w.target]
            if w.value > max(a[w.resource] for a in s.chapters[scope]["machines"].values()):
                return (not st), (f"{w.target} started although no machine can hold it" if st else f"{w.target} never starts")
            return bool(st), (f"{w.target} starts with {w.resource} {w.value:g}" if st else f"{w.target} never starts, although a machine can hold it")
        if w.family == "machine_removal":
            on = [e for e in c1 if e[3] == w.target]
            return (not on), (f"{len(on)} records on removed machine {w.target}" if on else f"nothing ran on {w.target}")
        return None, "no expectation for this family"

    def rule(self, scope, iv: Change) -> tuple[bool | None, str]:
        """The requested change itself: stated-rule invariants on the program's changed run, and no record before
        the change point moves."""
        ex0, ex1 = self.base(scope), self.execute(scope, iv)
        if ex1 is None:
            return None, "the backend has no input for this change"
        if ex1.status != "ran":
            return False, f"crashed: {ex1.detail}"
        c0, c1 = self.canon(ex0) if ex0 and ex0.status == "ran" else None, self.canon(ex1)
        s = self.schema
        t = change_time(s, scope, iv)
        if c0 is not None and t is not None and _before(s, c1, t) != _before(s, c0, t):
            return False, f"records before the change point {t} moved"
        data = apply_inputs(inputs_from_schema(s, scope), iv)
        bad = completeness(s, scope, data, c1)
        bad += mfg_invariants(s, scope, data, c1) if s.domain == MFG and not bad else []
        self.last_rule = (scope, iv, data, c1)      # for the dispatch check after a permit (Phase 2)
        bad += it_invariants(s, scope, data, c1, iv) if s.domain == IT and not bad else []
        if s.domain == IT and not bad:
            if iv.family == "failure_removal" and any(e[1] == "fail" and e[3] == iv.target for e in c1):
                bad.append(f"a task fails on {iv.target}, whose failure was removed")
            if iv.family == "task_priority" and iv.value > FREE_MAX and any(e[1] == "evict" and e[2] == iv.target for e in c1):
                bad.append(f"{iv.target} at priority {iv.value:g} is evicted")
        return (not bad), ("; ".join(bad[:3]) if bad else "stated rules hold on the changed run")

    def no_op(self, scope, iv: Change) -> tuple[bool | None, str]:
        """Manufacturing: the same kind of change on an order-book day cannot alter any ledger day."""
        s = self.schema
        if s.domain != MFG:
            return None, "no no-op change is defined for this domain"
        ch = s.chapters[scope]
        bd = ch["book_days"]
        if not bd:
            return None, "no order-book day"
        d = bd[0]
        p = iv.target or sorted(ch["products"])[0]
        prod, order = ch["book"].get((d, p), (0, 0))
        if iv.family == "order_removal":
            if not order:
                return None, "no order on the first order-book day"
            w = Change(iv.family, "remove", target=p, day=d)
        elif iv.family == "production_quantity":
            w = Change(iv.family, "set", target=p, day=d, value=float(prod + 100))
        elif iv.family == "production_timing":
            if not prod:
                return None, "no production on the first order-book day"
            w = Change(iv.family, "delay", target=p, day=d, value=1.0)
        else:
            w = Change(iv.family, "scale", day=d, value=0.5)
        ex0, ex1 = self.base(scope), self.execute(scope, w)
        if ex1 is None:
            return None, "the backend has no input for this change"
        if ex1.status != "ran":
            return False, f"crashed: {ex1.detail}"
        keep = lambda c: {k: v for k, v in (c or {}).items() if k[2] <= ch["last"]}
        same = keep(self.canon(ex1)) == keep(self.canon(ex0))
        return same, ("ledger unchanged by an order-book-day change" if same else f"a change on day {d} moved ledger days")


def discriminates(schema, scope, w: Change) -> bool:
    """Can this task_request witness tell a program that writes the change into the other resource from a correct
    one? (Review 2: permits resting only on witnesses that cannot are labelled, so CPU/memory confusion is reported
    as untested there.)"""
    if w.family != "task_request":
        return True
    ch = schema.chapters[scope]
    other = "mem" if w.resource == "cpu" else "cpu"
    t = ch["tasks"][w.target]
    up_end = [m for m in ch["machines"].values() if m["down"] is None or m["back"] is not None]
    if w.value > max(a[w.resource] for a in ch["machines"].values()):
        return any(m[other] >= w.value and m[w.resource] >= t[w.resource] for m in up_end)
    return w.value > max(a[other] for a in ch["machines"].values()) and         any(m[w.resource] >= w.value and m[other] >= t[other] for m in up_end)


def completeness(schema, scope, data, canon) -> list:
    """What every run under the stated policy must contain (review 1: an empty or partial output must not pass).
    Manufacturing: a ledger value of every column for every product on every ledger day. IT: the policy runs on
    until every task that can start has finished, so every task that fits some machine that is up at the end
    starts, every start is closed by a finish, eviction or failure, and every started task finishes."""
    if data is None:
        return ["the change has no place in the input"]
    ch = schema.chapters[scope]
    if schema.domain == MFG:
        prods = {p["product"] for p in data["products"]}
        miss = [(c, p, d) for d in range(ch["first"], ch["last"] + 1) for p in sorted(prods) for c in LEDGER_COLS
                if (canon or {}).get((c, p, d)) is None]
        return [f"{len(miss)} ledger values missing, first {miss[0]}"] if miss else []
    bad = []
    machines = data["machines"]
    end_up = [m for m in machines if m["fails_at"] is None or m["returns_at"] is not None]
    by_task: dict = {}
    for e in canon or []:
        by_task.setdefault(e[2], []).append(e)
    for t in data["tasks"]:
        evs = sorted(by_task.get(t["task"], []), key=lambda e: e[0])
        fits = any(m["cpu"] >= t["cpu"] and m["memory"] >= t["memory"] for m in end_up)
        starts = [e for e in evs if e[1] == "start"]
        closes = [e for e in evs if e[1] in ("finish", "evict", "fail")]
        if starts and len(closes) != len(starts):
            bad.append(f"{t['task']} has {len(starts)} starts, {len(closes)} ends")
        elif fits and not any(e[1] == "finish" for e in evs):
            bad.append(f"{t['task']} never {'starts' if not starts else 'finishes'}")
        if len(bad) > 3:
            break
    return bad


def mfg_invariants(schema, scope, data, canon) -> list:
    """Stock and backorder balances, nonnegative values and the day's capacity, on every ledger day."""
    ch = schema.chapters[scope]
    g = _grams(schema, scope)
    flows = {(x["day"], x["product"]): x for x in data["flows"]}
    cap = {x["day"]: x["capacity_kg"] for x in data["days"]}
    bad = []
    stock = {p: n for p, (_, n) in ch["products"].items()}
    bo = {p: 0 for p in ch["products"]}
    for d in range(ch["first"], ch["last"] + 1):
        used = 0
        for p in sorted(ch["products"]):
            vals = [canon.get((c, p, d)) for c in LEDGER_COLS]
            if None in vals:
                bad.append(f"missing ledger values for {p} day {d}")
                return bad
            sh, b, st = vals
            if min(vals) < 0:
                bad.append(f"negative value for {p} day {d}")
            if st != stock[p] + flows[(d, p)]["produced"] - sh:
                bad.append(f"stock balance fails for {p} day {d}")
            if b != bo[p] + flows[(d, p)]["ordered"] - sh:
                bad.append(f"backorder balance fails for {p} day {d}")
            stock[p], bo[p] = st, b
            used += sh * g[p]
        if used > round(cap[d] * 1000) + 1e-6:
            bad.append(f"day {d} ships {used / 1000:g} kg over capacity {cap[d]:g} kg")
    return bad


def mfg_dispatch_full(schema, scope, data, canon) -> list:
    """Dispatch ships each order as far as stock and remaining capacity allow (policy step 3). So at the end of a
    day, a product still backordered has no stock left, or the capacity left is below one unit of it (Phase 2,
    manifests/blindspots.md)."""
    ch = schema.chapters[scope]
    g = _grams(schema, scope)
    cap = {x["day"]: x["capacity_kg"] for x in data["days"]}
    bad = []
    for d in range(ch["first"], ch["last"] + 1):
        left = round(cap[d] * 1000) - sum(canon[("shipped", p, d)] * g[p] for p in ch["products"])
        for p in sorted(ch["products"]):
            if canon[("backordered", p, d)] > 0 and canon[("stock", p, d)] > 0 and left >= g[p]:
                bad.append(f"day {d}: {p} stays backordered with stock on hand and {left / 1000:g} kg of capacity unused")
                return bad
    return bad


def it_invariants(schema, scope, data, canon, iv) -> list:
    """No machine over capacity after the events at any time, nothing runs on a down or removed machine, removed
    tasks leave no records, no start before submission."""
    tasks = {t["task"]: t for t in data["tasks"]}
    machines = {m["machine"]: m for m in data["machines"]}
    bad = []
    running: dict = {}
    times = sorted({e[0] for e in canon})
    by_t: dict = {}
    for e in canon:
        by_t.setdefault(e[0], []).append(e)
    for t in times:
        for tm, ev, task, m in by_t[t]:
            if task not in tasks:
                bad.append(f"record for a task not in the input: {task}")
                continue
            if m is not None and m not in machines:
                bad.append(f"record on a machine not in the cluster: {m}")
                continue
            if ev == "start":
                if m is None:
                    bad.append(f"{task} starts on no machine")
                    continue
                if tm < tasks[task]["submit"]:
                    bad.append(f"{task} starts before its submission")
                mm = machines[m]
                if mm["fails_at"] is not None and tm >= mm["fails_at"] and (mm["returns_at"] is None or tm < mm["returns_at"]):
                    bad.append(f"{task} starts on {m} while it is down")
                running[task] = m
            elif ev in ("finish", "evict", "fail"):
                running.pop(task, None)
        for m, mm in machines.items():
            here = [x for x, y in running.items() if y == m]
            if sum(tasks[x]["cpu"] for x in here) > mm["cpu"] or sum(tasks[x]["memory"] for x in here) > mm["memory"]:
                bad.append(f"{m} over capacity at time {t}")
            if here and mm["fails_at"] is not None and t >= mm["fails_at"] and (mm["returns_at"] is None or t < mm["returns_at"]):
                bad.append(f"tasks run on {m} while it is down at time {t}")
        if len(bad) > 5:
            break
    return bad


# ---------------------------------------------------------------- policy
def request_seed(req: DRequest, seed: int) -> int:
    text = json.dumps({"seed": seed, "scope": req.scope, "query": req.query.__dict__,
                       "iv": [i.__dict__ for i in req.interventions]}, sort_keys=True, default=str)
    return int(hashlib.sha256(text.encode()).hexdigest()[:12], 16)


def decide(config: str, req: DRequest, schema: DomainSchema, runner: ProbeRunner, registry: Registry | None,
           backend, budget: int = 3, seed: int = 0) -> Decision:
    """Same configurations and meaning as `policy.decide` for the workflow domains."""
    if config not in CONFIGS:
        raise ValueError(config)
    if config == "native":
        return Decision(True, "native: no added checks")
    c = validate(req, schema)
    if config == "schema" or not c.ok:
        return Decision(c.ok, f"contract {c.status}: {c.detail}".strip())
    ok, why = runner.replay(req.scope)
    ev = [("replay", ok, why)]
    if config == "replay" or not ok:
        return Decision(ok, f"replay: {why}", ev)
    rng = random.Random(request_seed(req, seed))
    iv = req.interventions[0]
    start = runner.executions
    fams = [f for f, (d, _) in FAMILIES.items() if d == schema.domain]
    if config == "directed":
        d = _directed(req, iv, schema, runner, registry, backend, budget, rng, ev)
    elif config == "generic":
        picks, tries, seen = [], 0, set()
        while len(picks) < cap(budget) and tries < 20 * cap(budget):
            tries += 1
            for w in runner.witnesses(req.scope, rng.choice(fams), 1, rng):
                k = repr(w)                # a repeated witness adds no evidence (fixed 2026-11-09 after review)
                if k not in seen:
                    seen.add(k)
                    picks.append(w)
        d = _probe_set(picks[:cap(budget)], runner, req.scope, ev, "generic")
    else:
        # One verdict per program and scope, as in `policy` (fixed 2026-11-09 after review).
        from .policy import program_seed
        prng = random.Random(program_seed(backend, req.scope, seed))
        picks = [w for f in fams for w in runner.witnesses(req.scope, f, 1, prng)]
        d = _probe_set(picks, runner, req.scope, ev, "program-wide")
    d.probes_run = runner.executions - start
    return d


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
    """Today's directed method, then, where it permits an IT task_request, the fill witness (Phase 2)."""
    d = _directed_today(req, iv, schema, runner, registry, backend, budget, rng, ev)
    if d.permit and schema.domain == MFG:
        return _dispatch_check(req, iv, schema, runner, registry, backend, ev, d)
    if not d.permit or schema.domain != IT or iv.family != "task_request":
        return d
    key = Key(backend.name, backend.program_hash(), backend.adapter_version, schema.policy_fingerprint(), iv.family,
              f"{iv.op}|fill {iv.resource}")
    if registry is not None:
        state, rows = registry.state(key, reg_target(iv))
        if state == "failed":
            bad = next(r for r in rows if r["passed"] is False)
            return Decision(False, f"fill capability failed earlier for {iv.family}/{iv.resource} on {bad['scope']}", ev)
    ws = _fill_witnesses(schema, req.scope, iv)
    if not ws:
        return d
    w = rng.choice(ws)
    ok, why = runner.input_use(req.scope, w)
    name = f"input_use {w.family} (fill {w.resource})"
    ev.append((name, ok, why))
    _record(registry, key, iv, req.scope, name, ok, why)
    if ok is False:
        return Decision(False, f"directed: {why}", ev)
    return d


def _dispatch_check(req, iv, schema, runner, registry, backend, ev, d):
    """Manufacturing, where today's method permits: dispatch completeness on the rule probe's run of the request's
    own change (no extra execution), with its own registry rows (op `<op>|exact`)."""
    key = Key(backend.name, backend.program_hash(), backend.adapter_version, schema.policy_fingerprint(), iv.family,
              f"{iv.op}|exact")
    if registry is not None:
        state, rows = registry.state(key, reg_target(iv))
        if state == "failed":
            bad = next(r for r in rows if r["passed"] is False)
            return Decision(False, f"exact-check capability failed earlier for {iv.family}/{iv.op}/{iv.target} on {bad['scope']}", ev)
    last = getattr(runner, "last_rule", None)
    if last is None or last[0] != req.scope or last[1] is not iv:
        return d
    bad = mfg_dispatch_full(schema, req.scope, last[2], last[3])
    ok, why = (not bad), ("; ".join(bad[:2]) if bad else "every backordered product is out of stock or out of capacity")
    ev.append(("exact dispatch", ok, why))
    _record(registry, key, iv, req.scope, "exact dispatch", ok, why)
    return Decision(False, f"directed: {why}", ev) if bad else d


def _fill_witnesses(schema, scope, iv) -> list:
    """Started tasks other than the request's whose other resource fits the largest machine in the asked
    resource, with that machine up at the end, set to exactly that machine's capacity. A correct program must
    start and finish such a task (completeness); one that adds the value to the current request never can."""
    ch = schema.chapters[scope]
    res, other = iv.resource, "mem" if iv.resource == "cpu" else "cpu"
    machines, tasks = ch["machines"], ch["tasks"]
    v = max(a[res] for a in machines.values())
    top = [m for m in machines.values() if m[res] == v and (m["down"] is None or m["back"] is not None)]
    started = sorted({e[2] for e in ch["log"] if e[1] == "start"})
    return [Change("task_request", "set", target=t, value=float(v), resource=res) for t in started
            if t != iv.target and tasks[t][res] != v and any(m[other] >= tasks[t][other] for m in top)]


def _directed_today(req, iv, schema, runner, registry, backend, budget, rng, ev):
    key = Key(backend.name, backend.program_hash(), backend.adapter_version, schema.policy_fingerprint(), iv.family, iv.op)
    if registry is not None:
        state, rows = registry.state(key, reg_target(iv))
        if state == "failed":
            bad = next(r for r in rows if r["passed"] is False)
            return Decision(False, f"capability failed earlier for {iv.family}/{iv.op}/{iv.target} on {bad['scope']}", ev)
        # Only passing input-use probes are reused, on the same scope; the rule probe tests the request's own change
        # and a no-op never permits.
        here = [r for r in rows if r["scope"] == req.scope and r["passed"] is True and r["probe"].startswith("input_use")]
        if here:
            ev.append(("reused", True, f"{len(here)} earlier passing probes for {iv.target} on this scope"))
            ok, why = runner.rule(req.scope, iv)
            ev.append(("rule " + iv.family, ok, why))
            if ok is None:
                return Decision(False, f"directed: the request's own change cannot be run ({why})", ev,
                                inexpressible="no input" in why, untested="no input" not in why)
            if ok is False:
                _record(registry, key, iv, req.scope, "rule " + iv.family, ok, why)
                return Decision(False, f"directed: {why}", ev)
            if _scope_blind(schema, req.scope, iv):
                return _blind_spot(req, iv, schema, runner, registry, key, budget, rng, ev, len(here))
            return Decision(True, f"reused evidence for {iv.family}/{iv.op}/{iv.target} on {req.scope}", ev)
    results = []
    ws = runner.witnesses(req.scope, iv.family, max(cap(budget) - 2, 1), rng, avoid=iv)
    blind = _blind(schema, req.scope, iv, ws)
    for w in ws:
        label = f"input_use {w.family}" + ("" if discriminates(schema, req.scope, w) else " (cannot tell cpu from mem)")
        results.append((label, *runner.input_use(req.scope, w)))
        if results[-1][1] is False:
            break
    if not any(ok is False for _, ok, _ in results):
        results.append(("rule " + iv.family, *runner.rule(req.scope, iv)))
    used = sum(1 for name, ok, _ in results if ok is not None)
    if not any(ok is False for _, ok, _ in results) and used < cap(budget):
        noop = runner.no_op(req.scope, iv)
        if noop[0] is not None:
            results.append(("no_op", *noop))
    for name, ok, why in results:
        ev.append((name, ok, why))
        _record(registry, key, iv, req.scope, name, ok, why)
        if ok is False:
            return Decision(False, f"directed: {why}", ev)
    # Permit only if the request's own change ran (rule passed) and at least one input-use witness passed;
    # a rule pass alone, or witnesses alone, never permits (review 1).
    rule_ok = next((ok for name, ok, _ in results if name.startswith("rule ")), None)
    used_ok = sum(1 for name, ok, _ in results if ok is True and name.startswith("input_use"))
    if rule_ok is None:
        why = next((w for name, ok, w in results if name.startswith("rule ")), "")
        cannot = "no input" in why
        return Decision(False, "directed: the request's own change cannot be run" + (" (the backend cannot express it)" if cannot else ""),
                        ev, untested=not cannot, inexpressible=cannot)
    if used_ok == 0:
        return Decision(False, "directed: no input-use probe could be run", ev, untested=True)
    if blind:
        return _blind_spot(req, iv, schema, runner, registry, key, budget, rng, ev, used_ok)
    return Decision(True, f"directed: {used_ok} input-use probes and the rule probe passed", ev)


# ---------------------------------------------------------------- IT CPU/memory blind spot (manifests/it_blindspot.md)
BLIND = " (cannot tell cpu from mem)"
TOLD = "told from the other resource"


def _blind(schema, scope, iv, ws) -> bool:
    """Router: a task_request request whose selected witnesses exist and none of which can tell a program that
    writes the change into the other resource from a correct one. Everything else keeps today's method."""
    return (schema.domain == IT and iv.family == "task_request" and bool(ws)
            and not any(discriminates(schema, scope, w) for w in ws))


def _scope_blind(schema, scope, iv) -> bool:
    """Router for the registry-reuse path: a task_request whose window and resource have no discriminating
    witness (the same test as `_blind`, since today's witnesses draw the discriminating ones first). Today's reuse
    runs unchanged; only where it would permit, the blind-spot step decides, with its own registry rows
    (`_split_key`), so today's registry rows evolve exactly as before."""
    return (schema.domain == IT and iv.family == "task_request"
            and not _kinds(schema, scope, iv.resource, schema.chapters[scope]["machines"]))


def _split_key(key, iv):
    """The blind-spot step's own registry key, one per resource. Its rows never reach today's key, so a failure
    found by the split can block only later blind-spot rows of that resource, never a row today's method decides
    (review of attempt 2: a shared registry otherwise turned later non-blind rows into Already caught)."""
    return replace(key, op=f"{key.op}|split {iv.resource}")


def _kinds(schema, scope, res, machines) -> list:
    """Today's discriminating witness kinds (`sharp`, `pos` in `ProbeRunner.witnesses`) on a given machine set."""
    ch = schema.chapters[scope]
    tasks, other = ch["tasks"], "mem" if res == "cpu" else "cpu"
    started = sorted({e[2] for e in ch["log"] if e[1] == "start"})
    up_end = [m for m in machines.values() if m["down"] is None or m["back"] is not None]
    big = max(a[res] for a in machines.values()) + 1
    sharp = [Change("task_request", "set", target=t, value=float(big), resource=res) for t in started
             if any(m[other] >= big and m[res] >= tasks[t][res] for m in up_end)]
    pos_v = max(a[other] for a in machines.values()) + 1
    pos = [Change("task_request", "set", target=t, value=float(pos_v), resource=res) for t in started
           if any(m[res] >= pos_v and m[other] >= tasks[t][other] for m in up_end)]
    return sharp + pos


def _split_cluster(schema, scope, res):
    """Remove the machines largest in both resources, again while one still is, until a witness of today's kind
    exists on the rest. Returns (removed machines, witnesses) or ([], []). Only the Machines table and the printed
    task log are used."""
    left, removed = dict(schema.chapters[scope]["machines"]), []
    while len(left) > 1:
        ws = _kinds(schema, scope, res, left)
        if ws:
            return (removed, ws) if removed else ([], [])
        top = [k for k, a in sorted(left.items()) if a["cpu"] == max(x["cpu"] for x in left.values())
               and a["mem"] == max(x["mem"] for x in left.values())]
        if not top or len(top) == len(left):
            break
        for k in top:
            left.pop(k)
        removed += top
    return [], []


def _run_changes(runner, scope, changes):
    """One execution of the program under test with several changes written into its input, through the backends'
    own input paths. None when the backend has no such path or the input no place for a change."""
    b = runner.backend
    if isinstance(b, DEVSDomain):
        data = inputs_from_schema(b.schema, scope)
        for c in changes:
            data = apply_inputs(data, c)
            if data is None:
                return None
        ex = b.run_input(scope, data)
    elif isinstance(b, OTFDomain):
        nav, pe, params = b.nav, {}, b.params(scope)
        for c in changes:
            e = edit_nav(nav, b.schema, scope, c, params)
            if e is None:
                return None
            nav = e[0]
            pe.update(e[1] or {})
        ex = b.run_map(nav, scope, pe or None)
    else:
        return None
    runner.executions += 1
    return ex


def _without(runner, scope, removed, w=None) -> tuple[bool | None, str]:
    """The run with `removed` machines taken out (and the witness change `w`, if given), checked against the rules
    on that input: completeness, the stated invariants, nothing on a removed machine, and for `w` the outcome the
    rules fix: never starts if no remaining machine can hold the request, else starts (and finishes)."""
    s = runner.schema
    rm = [Change("machine_removal", "remove", target=m) for m in removed]
    changes = rm + ([w] if w is not None else [])
    data = inputs_from_schema(s, scope)
    for c in changes:
        data = apply_inputs(data, c)
    ex = _run_changes(runner, scope, changes)
    if ex is None:
        return None, "the backend has no input for this change"
    if ex.status != "ran":
        return False, f"crashed: {ex.detail}"
    c1 = runner.canon(ex)
    bad = completeness(s, scope, data, c1)
    bad = bad or it_invariants(s, scope, data, c1, w)
    on = [e for e in c1 if e[3] in removed]
    if on:
        bad.append(f"{len(on)} records on removed machine {on[0][3]}")
    if bad:
        return False, "; ".join(bad[:2])
    if w is None:
        return True, "stated rules hold"
    st = [e for e in c1 if e[1] == "start" and e[2] == w.target]
    if w.value > max(m["cpu" if w.resource == "cpu" else "memory"] for m in data["machines"]):
        return (not st), (f"{w.target} started although no remaining machine can hold it" if st else f"{w.target} never starts")
    return bool(st), (f"{w.target} starts with {w.resource} {w.value:g}" if st else
                      f"{w.target} never starts, although a remaining machine can hold it")


def _blind_spot(req, iv, schema, runner, registry, key, budget, rng, ev, used_ok):
    """The added step on a blind-spot row that today's method would permit (manifests/it_blindspot.md, attempt
    2): split the dominating machines off, check that the program handles that removal on its own, then run
    today's kind of witness on the rest. Untestable, never Trusted, when no such witness exists or the removal
    alone is not handled; Caught when the witness fails."""
    bkey = _split_key(key, iv)
    if registry is not None:
        state, rows = registry.state(bkey, reg_target(iv))
        if state == "failed":
            bad = next(r for r in rows if r["passed"] is False)
            return Decision(False, f"blind-spot capability failed earlier for {iv.family}/{iv.resource} on {bad['scope']}", ev)
        here = [r for r in rows if r["scope"] == req.scope and r["passed"] is True]
        if here:
            ev.append(("reused", True, f"{len(here)} earlier passing blind-spot probes for {iv.resource} on this scope"))
            return Decision(True, f"directed: blind spot resolved by reused evidence for {iv.family}/{iv.resource} on {req.scope}", ev)
    removed, ws = _split_cluster(schema, req.scope, iv.resource)
    if not ws:
        return Decision(False, "directed: blind spot, no witness can tell cpu from mem", ev, untested=True)
    names = ", ".join(removed)
    ok, why = _without(runner, req.scope, removed)
    ev.append((f"precheck without {names}", ok, why))
    if ok is not True:
        return Decision(False, f"directed: blind spot, the run without {names} is not usable ({why})", ev, untested=True)
    rng.shuffle(ws)
    told = 0
    for w in ws[:max(cap(budget) - 2, 1)]:
        name = f"input_use {w.family} ({iv.resource} {TOLD}, without {names})"
        ok, why = _without(runner, req.scope, removed, w)
        ev.append((name, ok, why))
        _record(registry, bkey, iv, req.scope, name, ok, why)
        if ok is False:
            return Decision(False, f"directed: {why}", ev)
        told += ok is True
    if told == 0:
        return Decision(False, "directed: blind spot, no witness could be run", ev, untested=True)
    return Decision(True, f"directed: {used_ok + told} input-use probes ({told} without {names}) and the rule probe passed", ev)


def cap(budget: int) -> int:
    """The probe-execution cap shared by directed and generic. Directed needs at least one witness and the
    request's own change, so the cap is never below 2 (review 1: budget matching, D20)."""
    return max(budget, 2)


def reg_target(iv: Change):
    """Registry target. Manufacturing product codes are real and stable across chapters; IT machine, job and task
    ids are local to a window (M01 in one window is another machine than M01 in the next), so IT evidence is
    kept at family level (review 1)."""
    return iv.target if FAMILIES[iv.family][0] == MFG else None


def _record(registry, key, iv, scope, probe, ok, detail):
    if registry is not None:
        registry.add(key, Evidence(probe, iv.family, reg_target(iv), scope, ok, detail))


# ---------------------------------------------------------------- binding check (OTF native patch)
def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def _names(rec, x) -> bool:
    return str(x) in [str(e) for e in rec.get("entities") or []]


def _fields_changed(old, new):
    a, b = old.get("fields") or {}, new.get("fields") or {}
    out = {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}
    for k in set(old) | set(new):
        if k not in ("fields", "src") and old.get(k) != new.get(k):
            out[f"@{k}"] = (old.get(k), new.get(k))
    return out


def _flow_field(field_name, rec) -> str | None:
    """Is this record field a production quantity or an order quantity? By the field's name, else, for a neutral
    name such as "units", by the record's kind ("production", "order")."""
    f, k = _norm(field_name), _norm(rec.get("kind", ""))
    if "order" in f:
        return "order"
    if "produc" in f or "planned" in f:
        return "production"
    prod_kind = "produc" in k or "planned" in k
    if "order" in k and not prod_kind:
        return "order"
    if prod_kind and "order" not in k:
        return "production"
    return None


def _rtime(rec):
    return _num(rec.get("time"))


def check_otf(iv: Change, binding: dict, schema: DomainSchema, scope: str) -> tuple[bool, str]:
    """Did the native patch change exactly what the request says? Works on the record diff that
    `OTFDomain.native_what_if` reports. It can only reject."""
    if binding.get("errors"):
        return False, "patch errors: " + "; ".join(binding["errors"])[:200]
    if binding.get("overrides"):
        return False, f"{len(binding['overrides'])} outcome overrides"
    modified, added, removed = binding.get("modified") or [], binding.get("added") or [], binding.get("removed") or []
    params = binding.get("params_changed") or {}
    if binding.get("order_changed"):
        return False, "the order of the input records changed"
    ch = schema.chapters[scope]
    if iv.family == "dispatch_capacity":
        if modified or added or removed or len(params) != 1:
            return False, f"expected one constant change, got {len(params)} constants, {len(modified)} modified, {len(added)} added, {len(removed)} removed"
        k, (old, new) = next(iter(params.items()))
        if _num(old) is None or abs(_num(old) - ch["capacity_kg"]) > 1e-6:
            return False, f"constant {k} is not the stated capacity"
        if _num(new) is None or abs(_num(new) - ch["capacity_kg"] * iv.value) > 0.0005 + 1e-9:   # gram rounding
            return False, f"{k} set to {new}, expected {ch['capacity_kg'] * iv.value:g}"
        t = binding.get("t_star")
        if iv.day == ch["first"]:
            if t is not None and float(t) > ch["first"] + 1e-6:
                return False, f"capacity changed from day {t}, not from day {iv.day}"
        elif t is None or abs(float(t) - iv.day) > 1e-6:
            return False, f"capacity changed from day {t}, not from day {iv.day}"
        return True, f"{k} scaled by {iv.value:g} from day {iv.day}"
    if params:
        return False, f"constants changed: {sorted(params)}"
    if iv.family in ("order_removal", "production_quantity", "production_timing"):
        prods = set(ch["products"])
        mine = lambda r: {str(e) for e in r.get("entities") or []} & prods == {iv.target}
        if any(not mine(r) for r in removed + added) or any(not mine(n) for _, n in modified):
            return False, "a record of another product changed"
        isprod = lambda k, rec: _flow_field(k, rec) == "production"
        isorder = lambda k, rec: _flow_field(k, rec) == "order"
        if iv.family == "order_removal":
            if added:
                return False, "records added"
            if len(removed) == 1 and not modified:
                r = removed[0]
                fields = r.get("fields") or {}
                if _rtime(r) != iv.day or any(not isorder(k, r) and _num(v) for k, v in fields.items()):
                    return False, "the removed record is not only that day's order"
                return True, f"order record for {iv.target} on day {iv.day} removed"
            if len(modified) != 1 or removed:
                return False, f"{len(modified)} modified, {len(removed)} removed; expected one order cell"
            old, new = modified[0]
            changes = _fields_changed(old, new)
            if _rtime(new) != iv.day or len(changes) != 1:
                return False, f"changed {sorted(changes)} on day {_rtime(new)}"
            k, (_, v) = next(iter(changes.items()))
            if k.startswith("@") or not isorder(k, new) or _num(v) != 0:
                return False, f"field {k} set to {v}, expected the order set to 0"
            return True, f"order of {iv.target} on day {iv.day} set to 0"
        if iv.family == "production_quantity":
            if added or removed or len(modified) != 1:
                return False, f"{len(modified)} modified, {len(added)} added, {len(removed)} removed; expected one cell"
            old, new = modified[0]
            changes = _fields_changed(old, new)
            if _rtime(new) != iv.day or len(changes) != 1:
                return False, f"changed {sorted(changes)} on day {_rtime(new)}"
            k, (_, v) = next(iter(changes.items()))
            if k.startswith("@") or not isprod(k, new) or _num(v) is None or abs(_num(v) - iv.value) > 1e-6:
                return False, f"field {k} set to {v}, expected production {iv.value:g}"
            return True, f"production of {iv.target} on day {iv.day} set to {iv.value:g}"
        # production_timing: either the day's production record shifted by k days, or cells (d: 0, d+k: +q)
        k_days = int(iv.value)
        if added or removed:
            return False, "records added or removed"
        if len(modified) == 1:
            old, new = modified[0]
            changes = _fields_changed(old, new)
            if set(changes) == {"@time"} and _rtime(old) == iv.day and _rtime(new) == iv.day + k_days:
                fields = new.get("fields") or {}
                if any(not isprod(f, new) and _num(v) for f, v in fields.items()):
                    return False, "the shifted record also carries an order"
                return True, f"production record of {iv.target} moved from day {iv.day} to {iv.day + k_days}"
        flow = ch["ledger"].get((iv.day, iv.target))
        q = flow["produced"] if flow else ch["book"].get((iv.day, iv.target), (0, 0))[0]
        want = {iv.day: 0.0}
        later = ch["ledger"].get((iv.day + k_days, iv.target)) or ({"produced": ch["book"][(iv.day + k_days, iv.target)][0]}
                                                                      if (iv.day + k_days, iv.target) in ch["book"] else None)
        if later is not None:
            want[iv.day + k_days] = float(later["produced"] + q)
        got = {}
        for old, new in modified:
            changes = _fields_changed(old, new)
            if len(changes) != 1:
                return False, f"changed {sorted(changes)}"
            f, (_, v) = next(iter(changes.items()))
            if f.startswith("@") or not isprod(f, new):
                return False, f"field {f} changed, not production"
            got[_rtime(new)] = _num(v)
        if got != want:
            return False, f"production changed to {got}, expected {want}"
        return True, f"production of {iv.target} moved from day {iv.day} to day {iv.day + k_days}"
    # IT
    tasks = ch["tasks"]

    def only(rec, pattern):
        """The record names exactly one entity of this kind (task or machine), the target (review 1)."""
        ids = {str(e) for e in rec.get("entities") or [] if re.fullmatch(pattern, str(e))}
        return ids == {iv.target}
    if iv.family == "job_removal":
        gone = {t for t, a in tasks.items() if a["job"] == iv.target}
        if modified or added:
            return False, "a removal must only remove records"
        if not removed or any(not ({str(e) for e in r.get("entities") or []} & gone) for r in removed):
            return False, "removed records are not all the job's tasks"
        counts = binding.get("case_input_count") or {}
        expected = sum(counts.get(t, 0) for t in gone)
        if expected and len(removed) != expected:
            return False, f"removed {len(removed)} of the job's {expected} input records"
        return True, f"all {len(removed)} input records of job {iv.target} removed"
    if iv.family == "machine_removal":
        if modified or added:
            return False, "a removal must only remove records"
        if not removed or any(not _names(r, iv.target) for r in removed):
            return False, "removed records are not all the machine's"
        expected = (binding.get("case_input_count") or {}).get(iv.target)
        if expected is not None and len(removed) != expected:
            return False, f"removed {len(removed)} of the machine's {expected} input records"
        return True, f"machine {iv.target} removed"
    if iv.family == "failure_removal":
        if added:
            return False, "records added"
        if len(removed) == 1 and not modified:
            r = removed[0]
            left = (binding.get("case_input_count") or {}).get(iv.target, 0) - 1
            down = ch["machines"][iv.target]["down"]
            caps = [k for k in (r.get("fields") or {}) if "cpu" in _norm(k) or "mem" in _norm(k)]
            if not only(r, r"M\d+") or left < 1 or caps or _rtime(r) != down:
                return False, "the removed record is not only the machine's failure"
            return True, f"failure record of {iv.target} removed"
        if len(modified) != 1 or removed:
            return False, f"{len(modified)} modified, {len(removed)} removed"
        old, new = modified[0]
        if not only(new, r"M\d+"):
            return False, "the changed record is not only the machine's"
        changes = _fields_changed(old, new)
        cleared = all(v in (None, "", "-", "never", "none", "None") or (k == "@time" and v is None)
                      for k, (_, v) in changes.items())
        caps = [k for k in changes if "cpu" in _norm(k) or "mem" in _norm(k)]
        if not changes or not cleared or caps:
            return False, f"failure not cleared: {sorted(changes)}"
        return True, f"failure of {iv.target} cleared"
    if iv.family in ("task_priority", "task_request"):
        if added or removed or len(modified) != 1:
            return False, f"{len(modified)} modified, {len(added)} added, {len(removed)} removed; expected one record"
        old, new = modified[0]
        if not only(new, r"T\d+"):
            return False, "the changed record is not only the task's"
        changes = _fields_changed(old, new)
        if len(changes) != 1:
            return False, f"changed {sorted(changes)}"
        k, (_, v) = next(iter(changes.items()))
        want = "prior" if iv.family == "task_priority" else ("cpu" if iv.resource == "cpu" else "mem")
        if k.startswith("@") or want not in _norm(k) or _num(v) is None or abs(_num(v) - iv.value) > 1e-6:
            return False, f"field {k} set to {v}, expected {want} {iv.value:g}"
        return True, f"{k} of {iv.target} set to {iv.value:g}"
    return False, f"no binding rule for {iv.family}"


# ---------------------------------------------------------------- interpreter
PROMPT = {MFG: """Turn a what-if question about plant stock and dispatch records into a structured request. Reply with only JSON.

NAMES THE DOCUMENT USES
Chapters (scopes) and their products: {products}
Ledger days and order-book days per chapter: {days}

REQUEST FORMAT
{{"scope": chapter title,
  "interventions": [exactly one of:
    {{"family": "order_removal", "op": "remove", "target": product, "day": day the order was placed}}
    {{"family": "production_quantity", "op": "set", "target": product, "day": production day, "value": units}}
    {{"family": "production_timing", "op": "delay", "target": product, "day": production day, "value": days of delay}}
    {{"family": "dispatch_capacity", "op": "scale", "day": first day of the change, "value": factor (0.8 for 80%)}}],
  "query": {{"kind": "stock_end_of_day" or "backordered_end_of_day", "product": product, "day": day}},
  "unresolved": null, or a short reason if the question cannot be written in this format}}

QUESTION
{question}""",
          IT: """Turn a what-if question about compute cluster scheduling records into a structured request. Reply with only JSON.

NAMES THE DOCUMENT USES
Chapters (scopes) with their machines, jobs and tasks: {names}
Times are whole seconds from the window start.

REQUEST FORMAT
{{"scope": chapter title,
  "interventions": [exactly one of:
    {{"family": "job_removal", "op": "remove", "target": job id}}
    {{"family": "failure_removal", "op": "remove", "target": machine id}}
    {{"family": "task_priority", "op": "set", "target": task id, "value": priority}}
    {{"family": "task_request", "op": "set", "target": task id, "resource": "cpu" or "mem", "value": units}}
    {{"family": "machine_removal", "op": "remove", "target": machine id}}],
  "query": {{"kind": "task_start_time", "task": task id, "deadline": null}},
  "unresolved": null, or a short reason if the question cannot be written in this format}}
"task_start_time" asks when a task first starts.

QUESTION
{question}"""}


def prompt_for(question: str, schema: DomainSchema) -> str:
    if schema.domain == MFG:
        products = {s: sorted(c["products"]) for s, c in schema.chapters.items()}
        days = {s: f"ledger {c['first']}-{c['last']}, order book {c['book_days'][0]}-{c['book_days'][-1]}" if c["book_days"]
                else f"ledger {c['first']}-{c['last']}" for s, c in schema.chapters.items()}
        return PROMPT[MFG].format(products=json.dumps(products), days=json.dumps(days), question=question)
    names = {s: {"machines": sorted(c["machines"]), "jobs": f"{c['jobs'][0]} to {c['jobs'][-1]}" if c["jobs"] else "",
                 "tasks": f"{min(c['tasks'])} to {max(c['tasks'])}" if c["tasks"] else ""} for s, c in schema.chapters.items()}
    return PROMPT[IT].format(names=json.dumps(names), question=question)


def interpret(question: str, schema: DomainSchema, llm) -> tuple[DRequest, str]:
    text = llm([{"role": "user", "content": prompt_for(question, schema)}])
    return parse(text, schema.domain), text


def _whole(x):
    """A whole number from JSON, or raise ValueError (a float day such as 3.7 is not silently cut; review 1)."""
    if isinstance(x, bool):
        raise ValueError("bool")
    v = float(x)
    if not math.isfinite(v) or v != int(v):
        raise ValueError(f"not a whole number: {x!r}")
    return int(v)


def _finite(x):
    v = float(x)
    if not math.isfinite(v) or isinstance(x, bool):
        raise ValueError(f"not a finite number: {x!r}")
    return v


def parse(text: str, domain: str) -> DRequest:
    from .interpret import _first_json
    d = _first_json(text)
    if not isinstance(d, dict):
        return DRequest("", [], DQuery("invalid", ""), unresolved="malformed reply: no JSON object")
    q = d.get("query")
    q = q if isinstance(q, dict) else {}
    try:
        ent = q.get("product") if domain == MFG else q.get("task")
        query = DQuery(str(q.get("kind")), str(ent), None if q.get("day") is None else _whole(q["day"]),
                       None if q.get("deadline") is None else _whole(q["deadline"]))
    except (TypeError, ValueError):
        query = DQuery("invalid", "")
    raw = d.get("interventions")
    ivs = []
    for x in raw if isinstance(raw, list) else []:
        if not isinstance(x, dict):
            continue
        try:
            ivs.append(Change(str(x.get("family")), str(x.get("op")),
                              target=None if x.get("target") is None else str(x["target"]),
                              day=None if x.get("day") is None else _whole(x["day"]),
                              value=None if x.get("value") is None else _finite(x["value"]),
                              resource=None if x.get("resource") is None else str(x["resource"])))
        except (TypeError, ValueError):
            return DRequest(str(d.get("scope")), [], query, unresolved="malformed intervention")
    unresolved = d.get("unresolved") or None
    return DRequest(str(d.get("scope")), ivs, query, unresolved=None if unresolved is None else str(unresolved))
