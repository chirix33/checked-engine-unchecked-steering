"""Structured interventions and queries, and the information a runtime may use to check them."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field

FAMILIES = {
    "activity_duration": {"set"},
    "timer_delay": {"set"},
    "routing_outcome": {"set_draw"},
    "routing_probability": {"set"},
    "resource_availability": {"add_workers", "unavailable"},
    "case_set": {"remove"},
}


@dataclass(frozen=True)
class Intervention:
    family: str
    op: str
    case: str | None = None          # selected case, when the change applies to one case
    target: str | None = None        # activity, wait label, decision label or pool
    visit: int | None = None
    value: float | None = None       # seconds, a draw, or a count
    routes: dict | None = None       # route label -> probability, for routing_probability
    effective_from: int | None = None
    effective_to: int | None = None
    units: str | None = None


@dataclass(frozen=True)
class Query:
    kind: str                         # "case_end_time" or "case_ends_by"
    case: str
    deadline: int | None = None


@dataclass
class Request:
    scope: str
    interventions: list[Intervention]
    query: Query
    unresolved: str | None = None     # the interpreter could not form a request

    def key(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


@dataclass
class ProcessSchema:
    """What a document permits a runtime to know: names, ids and stated policy. Built from the document only."""
    policy_text: str
    scopes: list[str]
    cases: dict[str, list[str]]                 # scope -> case ids
    activities: list[str]
    waits: list[str]
    decisions: dict[str, list[str]]             # decision label -> route labels
    pools: dict[str, int]                       # pool -> worker count
    reached: dict[str, set] = field(default_factory=dict)   # scope -> {(case, element, visit)} seen in the record

    def policy_fingerprint(self) -> str:
        """Hash of the stated policy. The front matter's last line lists the document's own chapters ("Chapters in
        this document: ..."); it is not policy, and is dropped so one policy has one fingerprint across documents, as
        in `mlsys.py` (Ashraf, 2026-11-09; changed after the development pilot)."""
        text = re.sub(r"\s+", " ", self.policy_text).strip()
        # only the exact closing chapter list ("Chapters in this document: Run 01, Run 02."), and only at the very end
        text = re.sub(r"\s*Chapters in this document: Run \d+(?:, Run \d+)*\.$", "", text).strip()
        return hashlib.sha256(text.encode()).hexdigest()[:16]


def schema_from_map(nav: dict) -> ProcessSchema:
    """Read names, case ids and worker counts from a document map's tables and front matter."""
    nodes = nav["nodes"]
    front = next(n for n in nodes if n["level"] == 0 and n["kind"] == "list")
    policy = "\n".join(front.get("lines", []))
    scopes = [n["title"] for n in nodes if n["level"] == 0 and n.get("children") and n["kind"] != "list"]

    def table(title):
        node = next((n for n in nodes if n["title"] == title and n["kind"] == "table"), None)
        return (node["table"]["columns"], node["table"]["rows"]) if node else ([], [])

    cases, activities, waits, decisions, reached = {}, set(), set(), {}, {}
    for s in scopes:
        cases[s] = [r[0] for r in table(f"{s}: Cases")[1]]
        activities |= {r[1] for r in table(f"{s}: Work plan")[1]}
        waits |= {r[1] for r in table(f"{s}: Wait plan")[1]}
        for r in table(f"{s}: Decision log")[1]:
            decisions.setdefault(r[1], set()).add(r[4])
        for r in table(f"{s}: Route draws")[1]:
            decisions.setdefault(r[1], set())
        seen = set()
        for r in table(f"{s}: Task log")[1]:
            seen.add((r[0], r[1], int(r[2])))
        for r in table(f"{s}: Wait log")[1]:
            seen.add((r[0], r[1], int(r[2])))
        for r in table(f"{s}: Decision log")[1]:
            seen.add((r[0], r[1], int(r[2])))
        reached[s] = seen
    text = " ".join(policy.split())
    pools = {m.group(1).strip(): int(m.group(2)) for m in re.finditer(r"([A-Z][A-Za-z ]+?): (\d+) workers", text)}
    # Route labels the policy states, including ones the record never shows.
    for label, opts in decisions.items():
        opts |= set(re.findall(rf"route ({re.escape(label)}-[a-z])", text))
    return ProcessSchema(policy, scopes, cases, sorted(activities), sorted(waits),
                         {k: sorted(v) for k, v in decisions.items()}, pools, reached)
