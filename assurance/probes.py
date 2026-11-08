"""Oracle-free probes. Each runs the program on permitted inputs and checks a justified property.

No probe consults a reference implementation or gold answer. Expectations come only from the document's stated
rules and records, and from the written semantics (spec sections 3, 7 and 8):

- **Replay:** the program's factual run reproduces the recorded case ends (this is also the strict-replay
  comparator, and the check that the case-end projection is valid for this program).
- **Input use, with prefix invariance:** changing an input that the record shows was used (a reached plan visit)
  must change that case's records, and must not change any record earlier than the point where the changed input
  is first used. A crash is a failed probe, never evidence of input use.
- **No-op:** changing an input for a visit the record shows never happened must change nothing.
- **Route rule:** under a changed route probability, the stated rule and the recorded draws fix which cases take
  which route at a recorded decision, so the program's decision records must agree.
- **Resource rules:** a worker made unavailable starts no task inside the interval. With added workers, nothing
  changes before the first recorded task of that pool that waited for a worker, and that task then starts earlier.

Every probe returns `(passed, detail)`, where `passed` is True, False, or None. None means the probe could not be
run (no witness, or no input that can express the change) and is never counted as a pass or a failure.
"""
from __future__ import annotations

import copy
import random
import re
from dataclasses import replace

from .request import Intervention, ProcessSchema

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEK = 7 * 86400


def _key(r):
    return tuple(sorted((k, str(v)) for k, v in r.items() if k != "src"))


def _times_before(records, t):
    return sorted(_key(r) for r in records if r.get("time") is not None and float(r["time"]) < t)


def _case_records(records, case):
    def has(r):
        ents = r.get("entities")
        if ents is not None:
            return case in [str(e) for e in ents]
        return str(r.get("case")) == case
    return sorted(_key(r) for r in records if has(r))


def _strip_workers(records, pool):
    """Replace this pool's worker names with a placeholder, wherever they appear."""
    pat = re.compile(rf"^{re.escape(pool)}_\d+$")

    def s(v):
        if isinstance(v, str) and pat.match(v):
            return "*"
        if isinstance(v, list):
            return [s(x) for x in v]
        return v
    return [{k: s(v) for k, v in r.items()} for r in records]


# -- reading the stated policy ----------------------------------------------------------------------------------

def _policy(schema: ProcessSchema) -> str:
    return " ".join(schema.policy_text.split())


def _skip_parens(text: str, i: int) -> int:
    """If text[i:] starts with ' (', return the index after the balanced closing parenthesis; else i."""
    if not text.startswith(" (", i):
        return i
    depth, j = 0, i + 1
    while j < len(text):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return i


def stated_routes(schema: ProcessSchema) -> dict:
    """{decision: {route: (probability, target)}} as the document states them. Labels may hold nested parentheses."""
    text = _policy(schema)
    out = {}
    for m in re.finditer(r"route ([A-Z]\d+)-([a-z])", text):
        j = _skip_parens(text, m.end())
        tail = re.match(r", probability ([0-9.]+), to ([^;.]+)", text[j:])
        if tail:
            out.setdefault(m.group(1), {})[f"{m.group(1)}-{m.group(2)}"] = (float(tail.group(1)), tail.group(2).strip())
    return out


def stated_probabilities(schema: ProcessSchema) -> dict:
    return {d: {r: p for r, (p, _) in routes.items()} for d, routes in stated_routes(schema).items()}


def stated_pools(schema: ProcessSchema) -> dict:
    """{pool: (size, first day, last day, open seconds, close seconds)} from 'P: n workers (...), working D1 to D2
    HH:MM to HH:MM'. Only pools the schema knows are returned."""
    text = _policy(schema)
    out = {}
    for pool in schema.pools:
        m = re.search(rf"(?<![\w]){re.escape(pool)}: (\d+) workers? \([^)]*\), working (\w+) to (\w+) "
                      rf"(\d\d):(\d\d) to (\d\d):(\d\d)", text)
        if m and m.group(2) in DAYS and m.group(3) in DAYS:
            out[pool] = (int(m.group(1)), DAYS.index(m.group(2)), DAYS.index(m.group(3)),
                         int(m.group(4)) * 3600 + int(m.group(5)) * 60, int(m.group(6)) * 3600 + int(m.group(7)) * 60)
    return out


def next_open(cal, t: float) -> float:
    """Smallest t' >= t in the weekly calendar (time 0 is Monday 00:00; a window's end is not working time)."""
    _, d1, d2, a, b = cal
    base = (t // WEEK) * WEEK
    for week in (0, 1):
        for d in range(7):
            if not d1 <= d <= d2:
                continue
            lo, hi = base + week * WEEK + d * 86400 + a, base + week * WEEK + d * 86400 + b
            if hi > t and hi > lo:
                return max(lo, t)
    raise ValueError("calendar has no working time")


# -- the record ------------------------------------------------------------------------------------------------

def _table_rows(nav, scope, section):
    node = next((n for n in nav["nodes"] if n["title"] == f"{scope}: {section}" and n["kind"] == "table"), None)
    return node["table"]["rows"] if node else []


def _task_log(nav, scope):
    return _table_rows(nav, scope, "Task log")


def first_use_time(nav, scope, iv: Intervention) -> float | None:
    """When the record first uses the changed input: the task's start, the wait's start, or the decision time."""
    if iv.family == "activity_duration":
        rows = [r for r in _task_log(nav, scope) if r[0] == iv.case and r[1] == iv.target and int(r[2]) == iv.visit]
        return float(rows[0][4]) if rows else None
    if iv.family == "timer_delay":
        rows = [r for r in _table_rows(nav, scope, "Wait log") if r[0] == iv.case and r[1] == iv.target and int(r[2]) == iv.visit]
        return float(rows[0][3]) if rows else None
    if iv.family == "routing_outcome":
        rows = [r for r in _table_rows(nav, scope, "Decision log") if r[0] == iv.case and r[1] == iv.target and int(r[2]) == iv.visit]
        return float(rows[0][3]) if rows else None
    if iv.family == "case_set":
        rows = [r for r in _table_rows(nav, scope, "Cases") if r[0] == iv.case]
        return float(rows[0][1]) if rows else None
    return None


def _visited_before(nav, scope, case, t) -> set:
    """Names of elements (activities, waits, decisions) the record shows this case reached before time t."""
    names = {r[1] for r in _task_log(nav, scope) if r[0] == case and float(r[3]) < t}
    names |= {r[1] for r in _table_rows(nav, scope, "Wait log") if r[0] == case and float(r[3]) < t}
    names |= {r[1] for r in _table_rows(nav, scope, "Decision log") if r[0] == case and float(r[3]) < t}
    return names


def plan_value(nav, scope, iv: Intervention):
    section = {"activity_duration": "Work plan", "timer_delay": "Wait plan", "routing_outcome": "Route draws"}[iv.family]
    node = next(n for n in nav["nodes"] if n["title"] == f"{scope}: {section}" and n["kind"] == "table")
    col = f"visit {iv.visit}"
    if col not in node["table"]["columns"]:
        return None
    j = node["table"]["columns"].index(col)
    for r in node["table"]["rows"]:
        if r[0] == iv.case and r[1] == iv.target and r[j] != "":
            return float(r[j])
    return None


def perturb(nav, schema, scope, w: Intervention) -> Intervention | None:
    """A changed value for a witness: +3600 s of work or delay, or a draw that takes a different stated route.
    A route flip that leads back to an element the case already reached is not used: the loop it starts may need
    plan visits the document does not list, and a correct program has no defined input for them."""
    old = plan_value(nav, scope, w)
    if old is None:
        return None
    if w.family in ("activity_duration", "timer_delay"):
        return replace(w, value=old + 3600)
    routes = stated_routes(schema).get(w.target, {})
    if len(routes) < 2:
        return None
    t = first_use_time(nav, scope, w)
    seen = _visited_before(nav, scope, w.case, t) if t is not None else set()
    low, bands = 0.0, []
    for lab in sorted(routes):
        p, target = routes[lab]
        bands.append((lab, low, low + p, target))
        low += p
    current = next((lab for lab, a, b, _ in bands if a <= old < b), None)
    for lab, a, b, target in bands:
        if lab != current and b > a and target not in seen:
            return replace(w, value=(a + b) / 2)
    return None


def witnesses(nav, schema: ProcessSchema, scope: str, iv: Intervention, k: int, rng: random.Random,
              same_target: bool = True) -> list[Intervention]:
    """Up to k reached inputs of the same family (and target, unless `same_target` is False) that have a usable
    changed value. Other cases come first; the request's own case is used only if too few others exist."""
    section, op = {"activity_duration": ("Task log", "set"), "timer_delay": ("Wait log", "set"),
                   "routing_outcome": ("Decision log", "set_draw")}.get(iv.family, (None, None))
    if section is None:
        return []
    rows = [r for r in _table_rows(nav, scope, section) if r[1] == iv.target or not same_target]
    others = [r for r in rows if r[0] != iv.case]
    own = [r for r in rows if r[0] == iv.case]
    rng.shuffle(others)
    rng.shuffle(own)
    out, seen = [], set()
    for r in others + own:
        key = (r[0], r[1], int(r[2]))
        if key in seen:
            continue
        seen.add(key)
        w = Intervention(iv.family, op, case=r[0], target=r[1], visit=int(r[2]), value=None)
        if perturb(nav, schema, scope, w) is not None:
            out.append(w)
        if len(out) == k:
            break
    return out


def unreached(nav, schema, scope, iv: Intervention) -> Intervention | None:
    """The same target at a visit the record shows never happened, for any case, if the plan lists it."""
    if iv.family not in ("activity_duration", "timer_delay", "routing_outcome"):
        return None
    section = {"activity_duration": "Work plan", "timer_delay": "Wait plan", "routing_outcome": "Route draws"}[iv.family]
    node = next(n for n in nav["nodes"] if n["title"] == f"{scope}: {section}" and n["kind"] == "table")
    cols = node["table"]["columns"]
    seen = schema.reached.get(scope, set())
    for r in node["table"]["rows"]:
        if r[1] != iv.target:
            continue
        for j, c in enumerate(cols[2:], start=2):
            v = int(c.split()[1])
            if r[j] != "" and (r[0], r[1], v) not in seen:
                old = float(r[j])
                value = (old + 0.5) % 1 if iv.family == "routing_outcome" else old + 3600
                return Intervention(iv.family, iv.op, case=r[0], target=r[1], visit=v, value=value)
    return None


# -- document edits for families with no plan cell ---------------------------------------------------------------

def _edit_policy(nav: dict, pattern: str, repl) -> dict | None:
    """A copy of the map with one match of `pattern` (spaces match any whitespace, including line breaks) replaced
    in the front-matter text. None if it does not match exactly once."""
    out = copy.deepcopy(nav)
    node = next((n for n in out["nodes"] if n["level"] == 0 and n["kind"] == "list"), None)
    if node is None or not isinstance(node.get("lines"), list):
        return None
    joined = "\n".join(node["lines"])
    rx = re.compile(pattern.replace(r"\ ", r"\s+").replace(" ", r"\s+"))
    if len(rx.findall(joined)) != 1:
        return None
    node["lines"] = rx.sub(repl, joined).split("\n")
    return out


def policy_with_pool(nav, pool, n, added) -> dict | None:
    pat = rf"(?<![\w]){re.escape(pool)}: {n} workers? \({re.escape(pool)}_0 to {re.escape(pool)}_{n - 1}\)"
    return _edit_policy(nav, pat, lambda m: f"{pool}: {n + added} workers ({pool}_0 to {pool}_{n + added - 1})")


def policy_with_routes(nav, schema, decision, routes) -> dict | None:
    text = _policy(schema)
    out = nav
    for m in re.finditer(rf"route ({re.escape(decision)}-[a-z])", text):
        j = _skip_parens(text, m.end())
        tail = re.match(r", probability ([0-9.]+), to ", text[j:])
        if not tail or m.group(1) not in routes:
            return None
        label = text[m.start():j]
        pat = re.escape(label) + r", probability " + re.escape(tail.group(1)) + r", to "
        out = _edit_policy(out, pat, lambda _m, lab=label, p=routes[m.group(1)]: f"{lab}, probability {_fixed(p)}, to ")
        if out is None:
            return None
    return out


class ProbeRunner:
    """Runs probes through one backend's deterministic diagnostic path."""

    def __init__(self, backend, nav, schema: ProcessSchema):
        self.backend, self.nav, self.schema = backend, nav, schema
        self._base = {}
        self.executions = 0                   # program runs made by probes, excluding the factual base run
        self.no_switch_check = True           # route_change: check a no-switch change exactly (False: report not run)

    def execute(self, scope, iv: Intervention | None):
        """Run the program with `iv` applied. None if this backend has no input that can express it."""
        b = self.backend
        if iv is not None:
            self.executions += 1
        if b.name == "otf":
            from .backends import edit_plan, remove_case
            if iv is None:
                return b.run_map(self.nav, scope)
            if iv.family == "case_set":
                return b.run_map(remove_case(self.nav, scope, iv.case), scope)
            if iv.family == "resource_availability" and iv.op == "add_workers":
                n = self.schema.pools[iv.target]
                keys = [k for k, v in b.params(scope).items() if _norm(iv.target) in _norm(k) and _num(v) == n]
                if len(keys) == 1:
                    return b.run_map(self.nav, scope, params_edit={keys[0]: n + int(iv.value)})
                nav = policy_with_pool(self.nav, iv.target, n, int(iv.value))
            elif iv.family == "routing_probability":
                nav = policy_with_routes(self.nav, self.schema, iv.target, iv.routes)
            else:
                nav = edit_plan(self.nav, scope, iv)
            if nav is None:
                self.executions -= 1
                return None
            return b.run_map(nav, scope)
        data = b.stdin_from_map(self.nav, scope)
        if iv is not None:
            data = b.apply(data, iv, self.schema)
            if data is None:
                self.executions -= 1
                return None
        return b.run_input(data)

    def base(self, scope):
        if scope not in self._base:
            self._base[scope] = self.execute(scope, None)
        return self._base[scope]

    def replay(self, scope) -> tuple[bool, str]:
        from .backends import recorded_case_ends
        ex = self.base(scope)
        if ex is None or ex.status != "ran":
            return False, f"factual run {getattr(ex, 'status', 'none')}: {getattr(ex, 'detail', '')}"
        rec = recorded_case_ends(self.nav, scope)
        wrong = sorted(c for c, t in rec.items() if abs(ex.case_ends.get(c, -1) - t) >= 1)
        return (not wrong), (f"{len(wrong)} of {len(rec)} case ends differ" if wrong else "all case ends match")

    def input_use(self, scope, w: Intervention) -> tuple[bool | None, str]:
        ex0 = self.base(scope)
        changed = perturb(self.nav, self.schema, scope, w)
        if changed is None:
            return None, "no usable witness value"
        ex1 = self.execute(scope, changed)
        if ex1 is None:
            return None, "the backend has no input for this change"
        if ex1.status != "ran":
            return False, f"crashed: {ex1.detail}"
        t = first_use_time(self.nav, scope, changed)
        if _case_records(ex1.records, changed.case) == _case_records(ex0.records, changed.case):
            return False, f"changing {changed.target} for {changed.case} visit {changed.visit} changed nothing for that case"
        if t is not None and _times_before(ex1.records, t) != _times_before(ex0.records, t):
            return False, f"records before the change point {t:g} moved"
        return True, f"{changed.case} {changed.target} visit {changed.visit}: case changed, prefix unchanged"

    def route_rule(self, scope, iv: Intervention) -> tuple[bool | None, str]:
        """Under changed route probabilities, each case's first recorded decision at this gateway is fixed by its
        recorded draw and the stated rule (first route whose running total exceeds the draw)."""
        base = self.base(scope)
        if base is None or base.status != "ran" or not any(e.get("event") == "decision" for e in base.records):
            return None, "the program's records have no decision events to check"
        ex = self.execute(scope, iv)
        if ex is None:
            return None, "the backend has no input for route probabilities"
        if ex.status != "ran":
            return False, f"crashed: {ex.detail}"
        node = next((n for n in self.nav["nodes"] if n["title"] == f"{scope}: Route draws" and n["kind"] == "table"), None)
        j = node["table"]["columns"].index("visit 1") if node and "visit 1" in node["table"]["columns"] else None
        draws = {r[0]: float(r[j]) for r in (node["table"]["rows"] if node else []) if j is not None and r[1] == iv.target and r[j] != ""}
        order = sorted(iv.routes)
        expected = {}
        for case, u in draws.items():
            total = 0.0
            for lab in order:
                total += iv.routes[lab]
                if u < total:
                    expected[case] = lab
                    break
        seen = {}
        for e in ex.records:
            if e.get("event") == "decision" and e.get("name") == iv.target and int(e.get("visit", 0)) == 1:
                seen.setdefault(str(e.get("case")), e.get("route"))
        if not seen:
            return None, "the program's records have no decision events to check"
        reached = {c for (c, el, v) in self.schema.reached.get(scope, set()) if el == iv.target and v == 1}
        wrong = sorted(c for c in reached if c in expected and seen.get(c) != expected[c])
        return (not wrong), (f"{len(wrong)} first decisions disagree with the stated rule" if wrong else "first decisions follow the rule")

    def has_decision_events(self, scope) -> bool:
        base = self.base(scope)
        return base is not None and base.status == "ran" and any(e.get("event") == "decision" for e in base.records)

    def route_change(self, scope, iv: Intervention) -> tuple[bool | None, str]:
        """Record-comparison form of the route-probability check, for programs whose records name no decisions
        (form (b), added 2026-11-07 on development data). From the document's Decision log and Route draws, find the
        earliest recorded decision at this gateway whose draw picks a different route under the changed probabilities
        than under the stated ones. A correct program must change that case's records, and must leave every record
        before that decision's time unchanged (nothing earlier can depend on the change)."""
        stated = stated_probabilities(self.schema).get(iv.target)
        if not stated or not iv.routes or set(stated) != set(iv.routes):
            return None, "the stated or requested routes for this decision are not known"
        draws = {}
        node = next((n for n in self.nav["nodes"] if n["title"] == f"{scope}: Route draws" and n["kind"] == "table"), None)
        if node:
            cols = node["table"]["columns"]
            for r in node["table"]["rows"]:
                if r[1] != iv.target:
                    continue
                for j, h in enumerate(cols[2:], start=2):
                    if r[j] != "":
                        draws[(r[0], int(h.split()[1]))] = float(r[j])
        switched = []
        for r in _table_rows(self.nav, scope, "Decision log"):
            if r[1] != iv.target:
                continue
            u = draws.get((r[0], int(r[2])))
            if u is None:
                continue
            if _near_boundary(stated, u) or _near_boundary(iv.routes, u):
                # The printed draw is rounded to 6 decimals; this close to a boundary the exact draw may pick
                # another route, so which decisions switch is not known (review 5).
                return None, f"the printed draw for {r[0]} visit {r[2]} is within rounding of a route boundary"
            if _route_of(iv.routes, u) != _route_of(stated, u):
                switched.append((float(r[3]), r[0], int(r[2])))
        ex0 = self.base(scope)
        if ex0 is None or ex0.status != "ran":
            return None, "no factual run to compare with"
        if not switched and not self.no_switch_check:
            return None, "the change switches no recorded decision"
        ex1 = self.execute(scope, iv)
        if ex1 is None:
            return None, "the backend has no input for route probabilities"
        if ex1.status != "ran":
            return False, f"crashed: {ex1.detail}"
        if not switched:
            # No recorded decision changes route, so under the document's semantics the run under the change is the
            # factual run (same draws, same routes). A correct program's records must not change at all. This
            # decides only this request: it does not show that the program reads route probabilities.
            if sorted(_key(r) for r in ex1.records) != sorted(_key(r) for r in ex0.records):
                return False, "the change switches no recorded decision, but the program's records changed"
            return True, "the change switches no recorded decision and the records are unchanged"
        t0, case, visit = min(switched)
        if _case_records(ex1.records, case) == _case_records(ex0.records, case):
            return False, f"{case} takes a different route at {iv.target} visit {visit} (time {t0:g}) but its records did not change"
        if _times_before(ex1.records, t0) != _times_before(ex0.records, t0):
            return False, f"records before the first switched decision ({t0:g}) moved"
        return True, f"{case} {iv.target} visit {visit}: case changed, prefix before {t0:g} unchanged"

    def resource_rule(self, scope, iv: Intervention) -> tuple[bool | None, str]:
        ex = self.execute(scope, iv)
        if ex is None:
            return None, "the backend has no input for worker changes"
        if ex.status != "ran":
            return False, f"crashed: {ex.detail}"
        if iv.op == "unavailable":
            n = self.schema.pools[iv.target]
            names = {f"{iv.target}_{k}" for k in range(n - int(iv.value), n)}
            starts = [e for e in ex.records if e.get("event") == "task_start" and e.get("worker") is not None]
            if not starts:
                return None, "the program's records name no workers"
            bad = [e for e in starts if e.get("worker") in names and iv.effective_from <= float(e["time"]) < iv.effective_to]
            return (not bad), (f"{len(bad)} tasks start on an unavailable worker" if bad else "no starts on unavailable workers")
        return self._added_workers(scope, iv, ex)

    def _added_workers(self, scope, iv, ex1) -> tuple[bool | None, str]:
        """Added instances share the pool's calendar and start free at 0 (spec 8, 9). Until the first recorded task
        of the pool that could not start when it was enabled because every worker was busy, the extra workers change
        no start or end, only which worker is named. That task then starts at next_open(enabled), strictly earlier."""
        cal = stated_pools(self.schema).get(iv.target)
        if cal is None:
            return None, "the document states no calendar for this pool"
        ex0 = self.base(scope)
        pool = iv.target
        arrival = {r[0]: float(r[1]) for r in _table_rows(self.nav, scope, "Cases")}
        rows = [r for r in _task_log(self.nav, scope) if re.match(rf"^{re.escape(pool)}_\d+$", r[6] or "")]
        rows.sort(key=lambda r: (float(r[3]), arrival.get(r[0], 0), r[0], r[1], int(r[2])))
        waited = [r for r in rows if float(r[4]) > next_open(cal, float(r[3])) + 1e-9]
        a, b = _strip_workers(ex0.records, pool), _strip_workers(ex1.records, pool)
        if not waited:
            same = sorted(map(_key, a)) == sorted(map(_key, b))
            return same, ("no task of this pool waited, and nothing but worker names changed" if same
                          else "no task of this pool waited for a worker, yet the output changed")
        t_c = float(waited[0][3])
        if _times_before(a, t_c) != _times_before(b, t_c):
            return False, f"records before the first wait for a {pool} worker ({t_c:g}) moved"
        cases = {r[0] for r in waited if float(r[3]) == t_c}
        if all(_case_records(a, c) == _case_records(b, c) for c in cases):
            return False, f"the first task that waited for a {pool} worker, at {t_c:g}, did not change"
        return True, f"prefix before {t_c:g} unchanged, and the first waiting task changed"

    def case_removal(self, scope, iv: Intervention, w_case: str) -> tuple[bool | None, str]:
        """Removing another case: its records vanish, and nothing before its arrival moves."""
        ex0 = self.base(scope)
        w = Intervention("case_set", "remove", case=w_case)
        ex1 = self.execute(scope, w)
        if ex1 is None:
            return None, "the backend has no input for removing a case"
        if ex1.status != "ran":
            return False, f"removal crashed: {ex1.detail}"
        if _case_records(ex1.records, w_case):
            return False, f"removed case {w_case} still has records"
        t = first_use_time(self.nav, scope, w)
        if t is not None and _times_before(ex1.records, t) != _times_before(ex0.records, t):
            return False, f"records before {w_case}'s arrival moved"
        return True, f"{w_case} removed cleanly"

    def no_op(self, scope, iv: Intervention) -> tuple[bool | None, str]:
        n = unreached(self.nav, self.schema, scope, iv)
        if n is None:
            return None, "no unreached visit in the plan"
        ex0, ex1 = self.base(scope), self.execute(scope, n)
        if ex1 is None:
            return None, "the backend has no input for this change"
        if ex1.status != "ran":
            return False, f"no-op change crashed: {ex1.detail}"
        same = sorted(map(_key, ex1.records)) == sorted(map(_key, ex0.records))
        return same, ("unchanged" if same else f"changing unreached {n.case} {n.target} visit {n.visit} changed the output")


def _route_of(probs: dict, u: float):
    """The document's rule: routes in listed (label) order, the first whose running total exceeds the draw.
    Exact decimal arithmetic, so a total of exactly 1 is never short of a draw just below 1."""
    from decimal import Decimal
    total, d = Decimal(0), Decimal(str(u))
    for lab in sorted(probs):
        total += Decimal(_fixed(probs[lab]))
        if d < total:
            return lab
    return None


def _near_boundary(probs: dict, u: float, tol: str = "5e-7") -> bool:
    from decimal import Decimal
    total, d = Decimal(0), Decimal(str(u))
    for lab in sorted(probs):
        total += Decimal(_fixed(probs[lab]))
        if abs(d - total) <= Decimal(tol):
            return True
    return False


def _fixed(p: float) -> str:
    """A probability in fixed-point decimal, never exponent form."""
    s = f"{float(p):.12f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None
