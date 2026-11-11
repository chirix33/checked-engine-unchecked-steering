"""Backend adapters. Each runs an existing program unchanged and reports what it exposes.

`Execution.case_ends` is the query-relevant projection: each case's end time. An adapter must also say whether
that projection is valid for a program, using only the factual record: if a program's own factual run does not
reproduce the recorded case ends through this projection, the projection is `unmappable` for that program.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .request import Intervention, ProcessSchema

HORIZON = 10 ** 8


@dataclass
class Execution:
    status: str                       # "ran", "crashed", "unsupported", "read_failed", "binding_failed"
    case_ends: dict = field(default_factory=dict)
    records: list = field(default_factory=list)
    detail: str = ""
    cost: dict = field(default_factory=dict)


def _table(nav, title):
    return next((n for n in nav["nodes"] if n["title"] == title and n["kind"] == "table"), None)


def recorded_case_ends(nav, scope) -> dict:
    node = _table(nav, f"{scope}: Cases")
    return {r[0]: int(r[2]) for r in node["table"]["rows"]} if node else {}


def edit_plan(nav: dict, scope: str, iv: Intervention) -> dict | None:
    """A copy of the document map with one plan cell changed. Returns None if the change has no plan cell.
    This is an assurance-side diagnostic edit of permitted inputs, used by probes, not the native answer path."""
    out = copy.deepcopy(nav)
    section = {"activity_duration": "Work plan", "timer_delay": "Wait plan", "routing_outcome": "Route draws"}.get(iv.family)
    if section is None:
        return None
    node = _table(out, f"{scope}: {section}")
    if node is None:
        return None
    col = f"visit {iv.visit}"
    cols = node["table"]["columns"]
    if col not in cols:
        return None
    j = cols.index(col)
    for row in node["table"]["rows"]:
        if row[0] == iv.case and row[1] == iv.target:
            row[j] = f"{iv.value:.6f}" if iv.family == "routing_outcome" else str(int(iv.value))
            return out
    return None


def remove_case(nav: dict, scope: str, case: str) -> dict:
    out = copy.deepcopy(nav)
    for n in out["nodes"]:
        if n["title"].startswith(f"{scope}: ") and n["kind"] == "table":
            n["table"]["rows"] = [r for r in n["table"]["rows"] if r[0] != case]
    return out


def _canon(rec):
    return json.dumps({k: v for k, v in rec.items() if k != "src"}, sort_keys=True, default=str)


def _record_diff(before: list, after: list) -> dict:
    """Records added, removed and modified (paired by id) between two input lists."""
    from collections import Counter
    b, a = Counter(_canon(x) for x in before), Counter(_canon(x) for x in after)
    gone = [json.loads(k) for k, n in (b - a).items() for _ in range(n)]
    new = [json.loads(k) for k, n in (a - b).items() for _ in range(n)]
    by_id_gone = {}
    for x in gone:
        by_id_gone.setdefault(x.get("id"), []).append(x)
    modified, added = [], []
    for x in new:
        pool = by_id_gone.get(x.get("id")) if x.get("id") is not None else None
        if pool:
            modified.append([pool.pop(0), x])
        else:
            added.append(x)
    removed = [x for xs in by_id_gone.values() for x in xs]
    ids_b = [x.get("id") for x in before]
    ids_a = [x.get("id") for x in after]
    common = set(ids_b) & set(ids_a)
    order_changed = [i for i in ids_b if i in common] != [i for i in ids_a if i in common]
    return {"modified": modified, "added": added, "removed": removed, "order_changed": order_changed}


def _count_by_case(inputs):
    out = {}
    for x in inputs:
        for e in x.get("entities") or []:
            out[str(e)] = out.get(str(e), 0) + 1
    return out


class OTFBackend:
    """An OTF-Tools program, run with its own pinned (B0) or R1 engine code. Its code is never changed."""

    name = "otf"
    adapter_version = "otf-adapter-0.2"

    def __init__(self, program_path: Path, system: str, root: Path):
        self.program_path = Path(program_path)
        self.program = json.loads(self.program_path.read_text(encoding="utf-8"))
        self.code = self.program["code"]
        self.nav = json.loads(self.program_path.with_name("navmap.json").read_text())
        self.system = system
        self.root = Path(root)
        self.adapter_version = f"{OTFBackend.adapter_version}/{'r1' if system.startswith('r1') else 'b0'}"
        if system.startswith("r1"):
            sys.path.insert(0, str(self.root / "redesign"))
            from otf_r1 import records, sandbox, toolgen
        else:
            sys.path.insert(0, str(self.root / "baseline" / "otf-tools-10f5401" / "implementation-1"))
            from otf import records, sandbox, toolgen
        self.records, self.sandbox, self.toolgen = records, sandbox, toolgen

    def program_hash(self) -> str:
        return hashlib.sha256(self.code.encode()).hexdigest()[:16]

    # -- deterministic diagnostic path, used by probes --
    def run_map(self, nav: dict, scope: str, params_edit: dict | None = None) -> Execution:
        """Simulate from just before the first outcome, outcomes hidden, as the program's own check does."""
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
                                       {"inputs": r["inputs"], "params": params, "start": cut, "horizon": HORIZON})
            blind.unlink(missing_ok=True)
        if not ok or not isinstance(out, list):
            return Execution("crashed", detail=str(out)[-200:])
        kept = [o for o in r["outcomes"] if self.records.rtime(o) is not None and self.records.rtime(o) <= cut]
        return Execution("ran", case_ends=self._ends(kept + out), records=out)

    @staticmethod
    def _ends(records) -> dict:
        ends = {}
        for o in records:
            t = o.get("time")
            if t is None:
                continue
            for e in o.get("entities") or []:
                ends[str(e)] = max(ends.get(str(e), float("-inf")), float(t))
        return ends

    def params(self, scope: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            m = Path(tmp) / "map.json"
            m.write_text(json.dumps(self.nav))
            return dict(self.toolgen.read_scope(self.code, m, scope)["params"])

    # -- native answer path: the program's own engine, with its LLM patch step and restart/replay --
    def native_what_if(self, scope: str, question: str, llm) -> tuple[Execution, dict]:
        engine_mod = self.toolgen.__name__.rsplit(".", 1)[0] + ".engine"
        OTFEngine = __import__(engine_mod, fromlist=["OTFEngine"]).OTFEngine
        with tempfile.TemporaryDirectory() as tmp:
            engine = OTFEngine(llm, Path(tmp), 3)
            engine.nav, engine.map_path = self.nav, Path(tmp) / "navmap.json"
            engine.map_path.write_text(json.dumps(self.nav))
            engine.scopes = sorted(self.toolgen.scopes(self.nav), key=len, reverse=True)
            engine.model = self.program
            try:
                r = engine._records(scope)
                patches = engine._patches(r, question)
                applied = self.records.apply_patches(r["inputs"], r["params"], r["outcomes"], patches,
                                                     engine._names(r), r["t0"])
                w = engine._what_if(scope, r, patches)
            except Exception as e:
                if type(e).__name__ in ("InfrastructureFailure", "CapReached"):
                    raise                                   # review fix: service failures are not program failures
                return Execution("crashed", detail=f"{type(e).__name__}: {e}"[:300]), {}
        binding = {"patches": patches, "touched": sorted(map(str, applied["touched"])), "errors": applied["errors"],
                   "t_star": w.get("t_star"), "overrides": applied.get("overrides") or [],
                   "params_changed": {k: [r["params"].get(k), v] for k, v in applied["params"].items() if r["params"].get(k) != v},
                   "case_input_count": _count_by_case(r["inputs"]), **_record_diff(r["inputs"], applied["inputs"])}
        return Execution("ran", case_ends=self._ends(w["trace"]), records=w["trace"]), binding


def sandbox_command(program_dir: str, inner: str) -> str:
    """The bubblewrap command every generated stdin program (DEVS-Gen, the plain coding agent) runs under.

    Hardened on 2026-11-10, in two steps after two reviews:
    1. The earlier form (`--ro-bind / / --tmpfs /mnt --tmpfs /home --unshare-net`) was escapable: with /run visible,
       code reached the user session bus and started a process outside with `systemd-run --user`, which saw /mnt/c
       (reference code and gold) and the network. Now only /usr (read-only), the linker files, the interpreter and
       the program's own read-only folder are mounted; no /run, /var, /mnt or host /home; /usr/lib/wsl is hidden;
       every namespace is unshared; a new session; an empty environment; inherited descriptors above 2 are closed.
    2. `--unshare-net` does not cover AF_VSOCK on the WSL2 kernel: a program could connect to the Windows host,
       where a port answered the 9P handshake that serves /mnt/c. A seccomp filter
       (`scripts/make_seccomp_filter.py`, installed at $HOME/trust2027/tools/seccomp_unix_only.bpf) now refuses
       socket() and socketpair() for every family except AF_UNIX, and kills other architectures and the x32 ABI.
       Soft limits on address space, processes and file size keep a program from exhausting the WSL VM.
    The program folder is shell-quoted. Same isolation as `scripts/judges.py` `bwrap`."""
    import shlex
    bw = "$HOME/trust2027/tools/usr/bin/bwrap"
    venv = "$HOME/trust2027/devs_gen_code/.venvs/devs-gen"
    py_home = "$HOME/.local/share/uv/python"
    bpf = "$HOME/trust2027/tools/seccomp_unix_only.bpf"
    d = shlex.quote(str(program_dir))
    # close every inherited descriptor, then open only the seccomp filter on descriptor 10 for bubblewrap to read
    closer = (f"{venv}/bin/python -c 'import os, sys; os.closerange(3, 65536); fd = os.open(sys.argv[1], os.O_RDONLY); "
              f"os.dup2(fd, 10); os.close(fd); os.execv(sys.argv[2], sys.argv[2:])' {bpf}")
    limited = f'/bin/bash -c "ulimit -S -v 8388608 -u 4096 -f 4194304 && exec {inner}"'
    return (f"[ -s {bpf} ] && {closer} {bw} --seccomp 10 --ro-bind /usr /usr --symlink usr/lib /lib "
            f"--symlink usr/lib64 /lib64 --symlink usr/bin /bin --symlink usr/sbin /sbin "
            f"--ro-bind-try /etc/ld.so.cache /etc/ld.so.cache --ro-bind-try /etc/ld.so.conf /etc/ld.so.conf "
            f"--ro-bind-try /etc/ld.so.conf.d /etc/ld.so.conf.d $([ -d /usr/lib/wsl ] && echo --tmpfs /usr/lib/wsl) "
            f"--proc /proc --dev /dev --tmpfs /tmp --tmpfs /home --ro-bind {venv} {venv} --ro-bind-try {py_home} {py_home} "
            f"--ro-bind {d} {d} --unshare-all --die-with-parent --new-session --clearenv "
            f"--setenv PATH {venv}/bin:/usr/bin:/bin --setenv HOME /tmp --setenv LANG C.UTF-8 "
            f"--setenv PYTHONDONTWRITEBYTECODE 1 --chdir {d} {limited}")


class DEVSBackend:
    """A DEVS-Gen program, run unchanged inside WSL under the release's bubblewrap isolation tool."""

    name = "devs_gen"
    adapter_version = "devs-adapter-0.1"

    def __init__(self, wsl_program_dir: str, task: str, root: Path):
        self.dir = wsl_program_dir
        self.task = task
        self.root = Path(root)
        self._hash = None

    def program_hash(self) -> str:
        if self._hash is None:
            out = subprocess.run(["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c",
                                  f"set -o pipefail; cd '{self.dir}' && test -f run.py && find . -type f -not -path '*/__pycache__/*' "
                                  f"-not -name '*.pyc' -print0 | sort -z | xargs -0 sha256sum | sha256sum"],
                                 capture_output=True, text=True, timeout=120, env={**os.environ, "MSYS_NO_PATHCONV": "1"})
            digest = (out.stdout.strip().split() or [""])[0]
            if out.returncode != 0 or len(digest) != 64:
                raise RuntimeError(f"cannot hash program at {self.dir}: {out.stderr[-200:]}")
            self._hash = digest[:16]
        return self._hash

    @staticmethod
    def stdin_from_map(nav: dict, scope: str) -> dict:
        """The generic input object, built from the document's own tables (the same permitted information)."""
        def rows(section):
            node = _table(nav, f"{scope}: {section}")
            return node["table"]["columns"], node["table"]["rows"]

        def plan(section, key):
            head, body = rows(section)
            out = []
            for r in body:
                for j, h in enumerate(head[2:], start=2):
                    if r[j] != "":
                        out.append({"case": r[0], key: r[1], "visit": int(h.split()[1]),
                                    ("draw" if key == "decision" else "seconds"): float(r[j]) if key == "decision" else int(r[j])})
            return out
        cases = [{"case": r[0], "arrival": int(r[1])} for r in rows("Cases")[1]]
        return {"cases": cases, "work": plan("Work plan", "activity"), "waits": plan("Wait plan", "wait"),
                "draws": plan("Route draws", "decision")}

    @staticmethod
    def apply(data: dict, iv: Intervention, schema: ProcessSchema) -> dict | None:
        """Write a structured intervention into the generic input. None if the input format has no place for it."""
        d = copy.deepcopy(data)
        if iv.family in ("activity_duration", "timer_delay", "routing_outcome"):
            key, name, val = {"activity_duration": ("work", "activity", "seconds"), "timer_delay": ("waits", "wait", "seconds"),
                              "routing_outcome": ("draws", "decision", "draw")}[iv.family]
            hit = [x for x in d[key] if x["case"] == iv.case and x[name] == iv.target and x["visit"] == iv.visit]
            if not hit:
                return None
            hit[0][val] = float(iv.value) if val == "draw" else int(iv.value)
        elif iv.family == "routing_probability":
            d.setdefault("route_probabilities", {})[iv.target] = dict(iv.routes)
        elif iv.family == "resource_availability" and iv.op == "add_workers":
            d.setdefault("workers", {})[iv.target] = schema.pools[iv.target] + int(iv.value)
        elif iv.family == "resource_availability" and iv.op == "unavailable":
            n = schema.pools[iv.target]
            names = [f"{iv.target}_{k}" for k in range(n - int(iv.value), n)]
            d.setdefault("unavailable", []).extend({"worker": w, "from": iv.effective_from, "to": iv.effective_to} for w in names)
        elif iv.family == "case_set" and iv.op == "remove":
            for key in ("cases", "work", "waits", "draws"):
                d[key] = [x for x in d[key] if x["case"] != iv.case]
        else:
            return None
        return d

    def run_input(self, data: dict, timeout: int = 60) -> Execution:
        venv = "$HOME/trust2027/devs_gen_code/.venvs/devs-gen"
        # The program sees /usr, its interpreter and its own folder, read-only; see `sandbox_command`.
        import shlex
        cmd = f"cd {shlex.quote(str(self.dir))} && " + sandbox_command(self.dir, f"{venv}/bin/python run.py --horizon {HORIZON}")
        try:
            p = subprocess.run(["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c", cmd], input=json.dumps(data),
                               capture_output=True, text=True, timeout=timeout, env={**os.environ, "MSYS_NO_PATHCONV": "1"})
        except subprocess.TimeoutExpired:
            return Execution("crashed", detail="timeout")
        events, bad = [], 0
        for line in p.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                bad += 1
        if p.returncode != 0:
            return Execution("crashed", detail=f"exit {p.returncode}, {len(events)} events: " + (p.stderr or "")[-300:])
        ends = {}
        for e in events:
            if e.get("event") == "case_end" and e.get("case") is not None:
                ends[str(e["case"])] = float(e["time"])
        return Execution("ran", case_ends=ends, records=events, detail=f"unparsed lines {bad}" if bad else "")
