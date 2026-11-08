"""Capability records: conditional, per-family evidence keyed to the exact program, adapter and policy.

States are `failed`, `untested` and `tested_under_conditions`. Passing a finite set of probes never yields a
universal guarantee: a record lists the conditions it was tested under, and a request outside them is untested.
History is append-only; a later pass never erases an earlier failure.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Evidence:
    probe: str
    family: str
    target: str | None
    scope: str
    passed: bool
    detail: str
    cost: dict = field(default_factory=dict)
    at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


@dataclass
class Key:
    backend: str
    program: str          # hash of program code
    adapter: str          # adapter version
    policy: str           # fingerprint of the stated policy
    family: str
    op: str = ""

    def text(self) -> str:
        return "|".join((self.backend, self.program, self.adapter, self.policy, self.family, self.op))


class Registry:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _rows(self):
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def add(self, key: Key, evidence: Evidence) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key.text(), **asdict(evidence)}) + "\n")

    def history(self, key: Key) -> list[dict]:
        return [r for r in self._rows() if r["key"] == key.text()]

    def state(self, key: Key, target: str | None) -> tuple[str, list[dict]]:
        """`failed` if any probe on this target failed, `tested_under_conditions` if probes on it passed, else
        `untested`. A record for a different program, adapter or policy never counts."""
        rows = [r for r in self.history(key) if r["target"] == target and r["passed"] is not None]
        if any(not r["passed"] for r in rows):
            return "failed", rows
        if rows:
            return "tested_under_conditions", rows
        return "untested", rows
