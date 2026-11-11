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
        if lab != current and b > a and target not in seen and _flip_usable(nav, schema, scope, w, (a + b) / 2):
            return replace(w, value=(a + b) / 2)
    return None


def _flow(schema: ProcessSchema):
    """The control flow the document's front matter states, as {element: node}, plus the start element:
    ("act", next), ("wait", next), ("split", [targets]), ("join", n, next), ("decision", {route: target}).
    None if the text cannot be read. Built from the document only."""
    text = _policy(schema)
    i = text.find("Process. ")
    if i < 0:
        return None
    text = text[i + len("Process. "):]
    m = re.match(r"A new case goes to ([^.]+)\. ", text)
    if not m:
        return None
    start, flow = m.group(1).strip(), {}
    for mm in re.finditer(r"\): then ([^.]+)\.", text):
        close, depth, j = mm.start(), 0, mm.start()
        while j >= 0:                                  # the "(" that opens this element's attribute group
            depth += {")": 1, "(": -1}.get(text[j], 0)
            if depth == 0:
                break
            j -= 1
        if j < 0:
            return None
        k = text.rfind(". ", 0, j)
        name = text[k + 2 if k >= 0 else 0:j].strip()
        nxt = mm.group(1).strip()
        attrs = text[j + 1:close]
        if attrs.startswith("published delay") and name.startswith("Wait "):
            flow[name[5:].strip()] = ("wait", nxt)
        elif attrs.startswith("pool "):
            flow[name] = ("act", nxt)
        else:
            return None
    for mm in re.finditer(r"Split (\w+): starts all of these at the same time: ([^.]+)\.", text):
        flow[mm.group(1)] = ("split", [s.strip() for s in mm.group(2).split(", ")])
    for mm in re.finditer(r"Join (\w+): waits until all its (\d+) incoming paths have finished, then ([^.]+)\.", text):
        flow[mm.group(1)] = ("join", int(mm.group(2)), mm.group(3).strip())
    for d, routes in stated_routes(schema).items():
        flow[d] = ("decision", {lab: tgt for lab, (_, tgt) in routes.items()})
    return flow, start


def _plan_cells(nav, scope, section, case) -> dict:
    """{element: [value or None per printed visit]} for one case from a plan table."""
    node = next((n for n in nav["nodes"] if n["title"] == f"{scope}: {section}" and n["kind"] == "table"), None)
    out = {}
    if node:
        for r in node["table"]["rows"]:
            if r[0] == case:
                out[r[1]] = [None if v == "" else v for v in r[2:]]
    return out


def flow_walk(nav, schema, scope, case, override: dict | None = None, limit: int = 2000, probs: dict | None = None):
    """The control-flow path of one case from arrival to End, from the stated flow and the printed plans and draws,
    ignoring time (route choices depend only on draws). `override` maps (decision, visit) to a replacement draw;
    `probs` replaces the stated route probabilities ({decision: {route: p}}) for the decisions it names.
    Returns (sorted [(element, visit)] of activities and waits, complete): complete is False when the path needs a
    work, delay or draw the document does not print, or leaves the stated flow."""
    parsed = _flow(schema)
    if parsed is None:
        return None, False
    flow, start = parsed
    probs = {**stated_probabilities(schema), **(probs or {})}
    work = _plan_cells(nav, scope, "Work plan", case)
    delay = _plan_cells(nav, scope, "Wait plan", case)
    draw = _plan_cells(nav, scope, "Route draws", case)
    visits, arrivals, items, stack, steps = {}, {}, [], [start], 0
    while stack:
        steps += 1
        if steps > limit:
            return sorted(items), False
        el = stack.pop()
        if el == "End":
            continue
        node = flow.get(el)
        if node is None:
            return sorted(items), False
        kind = node[0]
        if kind == "join":
            arrivals[el] = arrivals.get(el, 0) + 1
            if arrivals[el] % node[1] == 0:
                stack.append(node[2])
            continue
        if kind == "split":
            stack.extend(reversed(node[1]))
            continue
        v = visits[el] = visits.get(el, 0) + 1
        if kind == "decision":
            u = (override or {}).get((el, v))
            if u is None:
                cells = draw.get(el, [])
                if v > len(cells) or cells[v - 1] is None:
                    return sorted(items), False
                u = float(cells[v - 1])
            lab = _route_of(probs.get(el, {}), u)
            if lab is None or lab not in node[1]:
                return sorted(items), False
            stack.append(node[1][lab])
            continue
        cells = (work if kind == "act" else delay).get(el)
        if cells is None or v > len(cells) or cells[v - 1] is None:
            return sorted(items), False
        items.append((el, v))
        stack.append(node[1])
    return sorted(items), True


def _flip_usable(nav, schema, scope, w: Intervention, value: float) -> bool:
    """A route-flip witness is usable only if (1) everything the case needs after the flip is printed, so a
    program that reads only the document has a defined input, and (2) the flip changes at least one activity or
    wait of the case, so a correct program's non-decision records must change. Added 2026-11-09 after the policy-
    variant soundness check found both kinds (a loop needing unprinted visits; a flip through zero-time decisions
    that rejoins the same path). If the stated flow cannot be read, or the factual path cannot be followed, no
    route-flip witness is used: a misfiring witness would record a capability failure for a correct program
    (review 4)."""
    base, ok0 = flow_walk(nav, schema, scope, w.case)
    if base is None or not ok0:
        return False
    flipped, ok1 = flow_walk(nav, schema, scope, w.case, {(w.target, w.visit): value})
    return ok1 and flipped != base


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
        self.runs = {}                        # the changed runs probes made, for the exact checks (blindspots.md)

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
        self.runs[("witness", w.family, w.case, w.target, w.visit)] = (changed, ex1)
        t = first_use_time(self.nav, scope, changed)
        if _case_records(ex1.records, changed.case) == _case_records(ex0.records, changed.case):
            return False, f"changing {changed.target} for {changed.case} visit {changed.visit} changed nothing for that case"
        if t is not None and _times_before(ex1.records, t) != _times_before(ex0.records, t):
            return False, f"records before the change point {t:g} moved"
        return True, f"{changed.case} {changed.target} visit {changed.visit}: case changed, prefix unchanged"

    def _route_draws(self, scope, target) -> dict:
        """{(case, visit): printed draw} for one decision gateway, from the document's Route draws table."""
        draws = {}
        node = next((n for n in self.nav["nodes"] if n["title"] == f"{scope}: Route draws" and n["kind"] == "table"), None)
        if node:
            cols = node["table"]["columns"]
            for r in node["table"]["rows"]:
                if r[1] != target:
                    continue
                for j, h in enumerate(cols[2:], start=2):
                    if r[j] != "":
                        draws[(r[0], int(h.split()[1]))] = float(r[j])
        return draws

    def _switched(self, scope, iv, stated, draws):
        """Recorded decisions at this gateway whose printed draw picks another route under the requested
        probabilities: ([(time, case, visit)], None), or (None, reason) if a draw is within rounding of a boundary."""
        switched = []
        for r in _table_rows(self.nav, scope, "Decision log"):
            if r[1] != iv.target:
                continue
            u = draws.get((r[0], int(r[2])))
            if u is None:
                continue
            if _near_boundary(stated, u) or _near_boundary(iv.routes, u):
                return None, f"the printed draw for {r[0]} visit {r[2]} is within rounding of a route boundary"
            if _route_of(iv.routes, u) != _route_of(stated, u):
                switched.append((float(r[3]), r[0], int(r[2])))
        return switched, None

    def route_rule(self, scope, iv: Intervention) -> tuple[bool | None, str]:
        """Rule form of the route-probability check, for programs whose records name decisions. Under the requested
        probabilities every decision the program records at this gateway, for any case and any visit whose draw the
        document prints, must take the route the stated rule gives for that draw. The earliest recorded decision
        whose route switches must appear with its new route, and nothing before it may move; if no recorded decision
        switches, the records must equal the factual run's (no-switch check). Rewritten 2026-11-09 after review:
        the earlier version compared visit-1 decisions only, so a program that ignored a change acting on a later
        visit passed."""
        base = self.base(scope)
        if base is None or base.status != "ran" or not any(e.get("event") == "decision" for e in base.records):
            return None, "the program's records have no decision events to check"
        stated = stated_probabilities(self.schema).get(iv.target)
        if not stated or not iv.routes or set(stated) != set(iv.routes):
            return None, "the stated or requested routes for this decision are not known"
        draws = self._route_draws(scope, iv.target)
        switched, why = self._switched(scope, iv, stated, draws)
        if switched is None:
            return None, why
        if not switched and not self.no_switch_check:
            return None, "the change switches no recorded decision"
        ex = self.execute(scope, iv)
        if ex is None:
            return None, "the backend has no input for route probabilities"
        if ex.status != "ran":
            return False, f"crashed: {ex.detail}"
        self.runs[("rule", scope)] = (iv, ex)
        if not switched:
            if sorted(_key(r) for r in ex.records) != sorted(_key(r) for r in base.records):
                return False, "the change switches no recorded decision, but the program's records changed"
            return True, "the change switches no recorded decision and the records are unchanged"
        compared, wrong, seen = 0, [], {}
        for e in ex.records:
            if e.get("event") != "decision" or e.get("name") != iv.target:
                continue
            try:
                key = (str(e.get("case")), int(e.get("visit")))
            except (TypeError, ValueError):
                continue
            u = draws.get(key)
            if u is None or _near_boundary(iv.routes, u):
                continue
            compared += 1
            seen[key] = e.get("route")
            if e.get("route") != _route_of(iv.routes, u):
                wrong.append(key)
        if compared == 0:
            return None, "no recorded decision at this gateway could be compared with the stated rule"
        if wrong:
            c, v = wrong[0]
            return False, f"{len(wrong)} recorded decisions disagree with the stated rule (first: {c} visit {v})"
        t0, case, visit = min(switched)
        if seen.get((case, visit)) != _route_of(iv.routes, draws[(case, visit)]):
            return False, f"{case} must take a different route at {iv.target} visit {visit} (time {t0:g}), but no such decision is recorded"
        if _times_before(ex.records, t0) != _times_before(base.records, t0):
            return False, f"records before the first switched decision ({t0:g}) moved"
        # Beyond the decisions: every case that ends in the factual run must still end, and every case whose path
        # under the requested probabilities the document fully determines must perform exactly that path's
        # activities (review 4: decision records alone let a program that got everything else wrong pass).
        ended = {str(e.get("case")) for e in ex.records if e.get("event") == "case_end"}
        missing = sorted({str(e.get("case")) for e in base.records if e.get("event") == "case_end"} - ended)
        if missing:
            return False, f"{len(missing)} cases have no end record under the change (first: {missing[0]})"
        parsed = _flow(self.schema)
        if parsed is None:
            return None, "the document's stated flow could not be read, so case paths cannot be checked"
        acts = {el for el, node in parsed[0].items() if node[0] == "act"}
        waits = {el for el, node in parsed[0].items() if node[0] == "wait"}
        kinds = {e.get("event") for e in base.records}
        tkind = "task_start" if "task_start" in kinds else ("task_end" if "task_end" in kinds else None)
        wkind = "wait_start" if "wait_start" in kinds else ("wait_end" if "wait_end" in kinds else None)
        if tkind is None:
            # Decision records alone cannot show that the program acts on the new routes (review 5).
            return None, "the program's records name no tasks, so case paths cannot be checked"

        def performed(records, c):
            # Sets, not lists: a task resumed after a pause may print a second start for the same visit.
            return {(str(e.get("name")), _int(e.get("visit"))) for e in records
                    if e.get("event") in (tkind, wkind) and str(e.get("case")) == c}

        def expected(path):
            return {(el, v) for el, v in path if el in acts or (wkind is not None and el in waits)}

        cases = self.schema.cases.get(scope, [])
        factual = {}
        for c in cases:
            path0, ok0 = flow_walk(self.nav, self.schema, scope, c)
            factual[c] = path0
            # The program's own factual records must list each case's path; if they list only some activities, the
            # record shape cannot be compared, which is not a failure of the program (review 5).
            if ok0 and performed(base.records, c) != expected(path0):
                return None, f"the program's factual records do not list {c}'s activities, so case paths cannot be compared"
        req = {iv.target: dict(iv.routes)}
        verified = 0
        for c in cases:
            path, complete = flow_walk(self.nav, self.schema, scope, c, probs=req)
            if not complete:
                continue
            verified += path != factual[c]
            if performed(ex.records, c) != expected(path):
                return False, f"{c} does not perform the activities and waits the stated rule gives under the change"
        if verified == 0:
            # No case whose path the change alters is fully printed, so nothing beyond the decision records can be
            # checked; a program that records the new routes but does not act on them would pass (review 4).
            return None, "no case whose path the change alters is fully determined by the document"
        return True, f"{compared} recorded decisions follow the stated rule; {case} visit {visit} switched, prefix unchanged, case paths match"

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
        draws = self._route_draws(scope, iv.target)
        switched, why = self._switched(scope, iv, stated, draws)
        if switched is None:
            # The printed draw is rounded to 6 decimals; this close to a boundary the exact draw may pick another
            # route, so which decisions switch is not known (review 5).
            return None, why
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
        self.runs[("rule", scope)] = (iv, ex1)
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
        self.runs[("rule", scope)] = (iv, ex)
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
        self.runs[("rule", scope)] = (w, ex1)
        if _case_records(ex1.records, w_case):
            return False, f"removed case {w_case} still has records"
        t = first_use_time(self.nav, scope, w)
        if t is not None and _times_before(ex1.records, t) != _times_before(ex0.records, t):
            return False, f"records before {w_case}'s arrival moved"
        return True, f"{w_case} removed cleanly"

    # -- exact stated-rule checks on runs the probes above already made (manifests/blindspots.md, Phase 2) -----
    # Each returns (passed, detail); None when the program's records do not name what the check needs, or the
    # document does not fix the outcome. They run only in `directed`, only where today's probes would permit.

    def exact_witness(self, scope, w: Intervention) -> tuple[bool | None, str]:
        """A passing witness run of a case-level family: work and waits end exactly as the rules fix (rules 3, 4),
        or, for a route flip, every fully printed case performs exactly its path (rule 5)."""
        hit = self.runs.get(("witness", w.family, w.case, w.target, w.visit))
        if hit is None:
            return None, "no witness run to check"
        changed, ex = hit
        if w.family == "routing_outcome":
            ok, why = self._paths(scope, ex, {changed.case: {(changed.target, changed.visit): changed.value}}, None)
            if ok is False:
                return ok, why
            ok2, why2 = self._timing(scope, ex, None)
            return (ok2, why2) if ok2 is False or ok is None else (ok, why + ("; " + why2 if ok2 else ""))
        return self._timing(scope, ex, changed)

    def exact_own(self, scope, iv: Intervention) -> tuple[bool | None, str]:
        """The request's own change, run once and checked exactly: timing (rules 3, 4) and, for a route draw, the
        case paths (rule 5). One execution, the run the structured answer also needs."""
        if iv.family not in ("activity_duration", "timer_delay", "routing_outcome"):
            return None, "no exact check for this family"
        if iv.family == "routing_outcome":
            _, complete = flow_walk(self.nav, self.schema, scope, iv.case, {(iv.target, iv.visit): iv.value})
            if not complete:
                # the flipped path needs values the document does not print: a correct program has no defined
                # input for it (review of Phase 2: such a change crashed a correct program and was Caught)
                return None, "the requested draw leads to visits the document does not print"
        if self._factual_timing(scope)[0] is not True:
            return None, "the program's factual records cannot be checked for timing"
        ex = self.execute(scope, iv)
        if ex is None:
            return None, "the backend has no input for this change"
        if ex.status != "ran":
            return False, f"the requested change crashed: {ex.detail}"
        if iv.family == "routing_outcome":
            ok, why = self._paths(scope, ex, {iv.case: {(iv.target, iv.visit): iv.value}}, None)
            if ok is False:
                return ok, "the requested change: " + why
            ok2, why2 = self._timing(scope, ex, None)
            if ok2 is False:
                return ok2, "the requested change: " + why2
            return (ok if ok is not None else ok2), "the requested change: " + (why if ok is not None else why2)
        ok, why = self._timing(scope, ex, iv, require=False)
        return ok, "the requested change: " + why

    def exact_rule(self, scope, iv: Intervention) -> tuple[bool | None, str]:
        """Timing on the run a rule probe made for this request (route probabilities, worker changes, case removal)."""
        hit = self.runs.get(("rule", scope))
        if hit is None or (hit[0] is not iv and iv.family != "case_set"):
            return None, "no run under the change to check"
        blocks = {}
        if iv.family == "resource_availability" and iv.op == "unavailable":
            n = self.schema.pools.get(iv.target)
            if n is None:
                return None, "the pool size is not known"
            blocks = {f"{iv.target}_{k}": [(float(iv.effective_from), float(iv.effective_to))] for k in range(n - int(iv.value), n)}
        return self._timing(scope, hit[1], None, blocks=blocks)

    def _timing(self, scope, ex, changed, require=True, blocks=None) -> tuple[bool | None, str]:
        """Every task whose work the input fixes ends when that work is done in its pool's working hours, outside
        any interval its worker is declared unavailable (rule 3); every wait ends its delay after it starts (rule 4).
        `changed` (a duration or delay change) overrides one plan value; with `require`, its task or wait must appear."""
        if changed is not False:
            base_ok, base_why = self._factual_timing(scope)
            if base_ok is not True:
                return None, f"the program's factual records cannot be checked for timing ({base_why})"
        work = {(r[0], r[1], v): float(x) for r, v, x in _plan_items(self.nav, scope, "Work plan")}
        delay = {(r[0], r[1], v): float(x) for r, v, x in _plan_items(self.nav, scope, "Wait plan")}
        key = None
        if changed not in (None, False) and changed.family in ("activity_duration", "timer_delay"):
            key = (changed.case, changed.target, changed.visit)
            (work if changed.family == "activity_duration" else delay)[key] = float(changed.value)
        pool_of, cals = activity_pools(self.schema), stated_pools(self.schema)
        spans, who = _spans(ex.records), _workers(ex.records)
        if not spans["task"] and not spans["wait"]:
            return None, "the program's records name no task or wait starts and ends"
        if blocks and not who:
            return None, "the program's records name no workers, so unavailable intervals cannot be placed"
        checked = 0
        for (c, a, v), (t0, t1) in sorted(spans["task"].items()):
            need, cal = work.get((c, a, v)), cals.get(pool_of.get(a))
            if need is None or cal is None:
                continue
            checked += 1
            want = work_end(cal, t0, need, (blocks or {}).get(who.get((c, a, v)), ()))
            if abs(t1 - want) >= 1:
                return False, f"{c} {a} visit {v} ends at {t1:g}; {need:g} s of work from {t0:g} end at {want:g}"
        for (c, a, v), (t0, t1) in sorted(spans["wait"].items()):
            need = delay.get((c, a, v))
            if need is None:
                continue
            checked += 1
            if abs(t1 - (t0 + need)) >= 1:
                return False, f"{c} wait {a} visit {v} lasts {t1 - t0:g} s, not its delay {need:g} s"
        if checked == 0:
            return None, "no task or wait whose work or delay the input fixes is in the program's records"
        if require and key is not None and key not in spans["task" if changed.family == "activity_duration" else "wait"]:
            return None, "the changed task or wait is not in the program's records"
        return True, f"{checked} tasks and waits end as their work and delays fix"

    def _factual_timing(self, scope) -> tuple[bool | None, str]:
        """The timing check on the program's own factual run (cached). Unless it passes there, the program's records
        are not in a shape the check can read (other visit numbering, units or names), and timing is not checked."""
        key = ("factual timing", scope)
        if key not in self.runs:
            base = self.base(scope)
            self.runs[key] = (None, (None, "no factual run") if base is None or base.status != "ran"
                              else self._timing(scope, base, False))
        return self.runs[key][1]

    def _paths(self, scope, ex, override, probs) -> tuple[bool | None, str]:
        parsed = _flow(self.schema)
        base = self.base(scope)
        if parsed is None or base is None or base.status != "ran":
            return None, "the stated flow or the factual run is not available"
        acts = {el for el, node in parsed[0].items() if node[0] == "act"}
        waits = {el for el, node in parsed[0].items() if node[0] == "wait"}
        kinds = {e.get("event") for e in base.records}
        tkind = "task_start" if "task_start" in kinds else ("task_end" if "task_end" in kinds else None)
        wkind = "wait_start" if "wait_start" in kinds else ("wait_end" if "wait_end" in kinds else None)
        if tkind is None:
            return None, "the program's records name no tasks"

        def performed(records, c):
            return {(str(e.get("name")), _int(e.get("visit"))) for e in records
                    if e.get("event") in (tkind, wkind) and str(e.get("case")) == c}

        def expected(path):
            return {(el, v) for el, v in path if el in acts or (wkind is not None and el in waits)}
        checked = 0
        for c in self.schema.cases.get(scope, []):
            path0, ok0 = flow_walk(self.nav, self.schema, scope, c)
            if ok0 and performed(base.records, c) != expected(path0):
                return None, f"the program's factual records do not list {c}'s activities"
            path, ok = flow_walk(self.nav, self.schema, scope, c, override.get(c), probs=probs)
            if not ok:
                continue
            checked += 1
            if performed(ex.records, c) != expected(path):
                return False, f"{c} does not perform the activities and waits its printed draws give"
        if checked == 0:
            return None, "no case path is fully printed"
        return True, f"{checked} case paths follow the printed draws"

    def route_paths(self, scope, iv: Intervention) -> tuple[bool | None, str]:
        """Form (b): under the requested probabilities, every fully printed case performs exactly its path."""
        hit = self.runs.get(("rule", scope))
        if hit is None or hit[0] is not iv:
            return None, "no run under the change to check"
        return self._paths(scope, hit[1], {}, {iv.target: dict(iv.routes)})

    def resource_exact(self, scope, iv: Intervention) -> tuple[bool | None, str]:
        """Added workers: no worker beyond the new count is named (rule 2 assigns only the pool's workers).
        Unavailable workers the record never uses inside the interval: nothing changes."""
        hit = self.runs.get(("rule", scope))
        if hit is None or hit[0] is not iv:
            return None, "no run under the change to check"
        ex = hit[1]
        n = self.schema.pools.get(iv.target)
        if n is None:
            return None, "the pool size is not known"
        pat = re.compile(rf"^{re.escape(iv.target)}_(\d+)$")
        if iv.op == "add_workers":
            named = {int(m.group(1)) for e in ex.records for m in [pat.match(str(e.get("worker") or ""))] if m}
            if not named:
                return None, "the program's records name no workers of this pool"
            top = n + int(iv.value) - 1
            return (max(named) <= top), (f"{iv.target}_{max(named)} is named, beyond the {n + int(iv.value)} workers"
                                         if max(named) > top else "only the pool's workers are named")
        names = {f"{iv.target}_{k}" for k in range(n - int(iv.value), n)}
        a, b = iv.effective_from, iv.effective_to
        used = [r for r in _task_log(self.nav, scope) if r[6] in names and float(r[4]) < b and (float(r[5]) > a or float(r[4]) >= a)]
        if used:
            return None, "the record uses these workers inside the interval"
        base = self.base(scope)
        same = sorted(_key(r) for r in ex.records) == sorted(_key(r) for r in base.records)
        return same, ("workers the record never uses in the interval: nothing changed" if same
                      else "workers the record never uses in the interval were made unavailable, yet the output changed")

    def case_exact(self, scope, w_case) -> tuple[bool | None, str]:
        """Every case other than the removed one still ends (rule 6)."""
        hit = self.runs.get(("rule", scope))
        if hit is None or hit[0].case != w_case:
            return None, "no removal run to check"
        ex, base = hit[1], self.base(scope)
        ends = lambda x: {str(e.get("case")) for e in x.records if e.get("event") == "case_end"}
        want = ends(base) - {w_case}
        if not want:
            return None, "the program's records name no case ends"
        miss = sorted(want - ends(ex))
        return (not miss), (f"{len(miss)} other cases no longer end (first: {miss[0]})" if miss else "every other case still ends")

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


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError, OverflowError):
        return None


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _plan_items(nav, scope, section):
    node = next((n for n in nav["nodes"] if n["title"] == f"{scope}: {section}" and n["kind"] == "table"), None)
    if not node:
        return []
    cols = node["table"]["columns"]
    return [(r, int(h.split()[1]), r[j]) for r in node["table"]["rows"] for j, h in enumerate(cols[2:], start=2) if r[j] != ""]


def activity_pools(schema: ProcessSchema) -> dict:
    """{activity: pool} from the stated process: 'NAME (pool POOL, published work'."""
    text = _policy(schema)
    out = {}
    for a in schema.activities:
        m = re.search(rf"(?<![\w]){re.escape(a)} \(pool ([^,]+), published work", text)
        if m:
            out[a] = m.group(1).strip()
    return out


def work_end(cal, start: float, work: float, blocks=()) -> float:
    """When `work` seconds of work started at `start` end, counting only the pool's working hours and not the
    worker's unavailable intervals `blocks` [(from, to)] (rule 3; a task that needs exactly the time left ends at
    closing time, or when the interval starts)."""
    _, d1, d2, a, b = cal
    t, left = float(start), float(work)
    for _ in range(10000):
        t = next_open(cal, t)
        inside = [hi for lo, hi in blocks if lo <= t < hi]
        if inside:
            t = max(inside)
            continue
        close = (t // 86400) * 86400 + b
        nxt = min([lo for lo, hi in blocks if t < lo < close] + [close])
        if left <= nxt - t:
            return t + left
        left -= nxt - t
        t = nxt
    raise ValueError("work does not end within the calendar search")


def _workers(records) -> dict:
    """{(case, activity, visit): worker} from task starts that name one."""
    out = {}
    for e in records:
        if e.get("event") == "task_start" and e.get("worker") and _int(e.get("visit")) is not None:
            out.setdefault((str(e.get("case")), str(e.get("name")), _int(e.get("visit"))), str(e["worker"]))
    return out


def _spans(records) -> dict:
    """{"task"|"wait": {(case, name, visit): (first start, last end)}} from records that name them."""
    out = {"task": {}, "wait": {}}
    st, en = {"task": {}, "wait": {}}, {"task": {}, "wait": {}}
    for e in records:
        ev = e.get("event")
        kind = "task" if ev in ("task_start", "task_end") else "wait" if ev in ("wait_start", "wait_end") else None
        if kind is None or e.get("time") is None or _int(e.get("visit")) is None:
            continue
        k = (str(e.get("case")), str(e.get("name")), _int(e.get("visit")))
        t = float(e["time"])
        if ev.endswith("start"):
            st[kind][k] = min(t, st[kind].get(k, t))
        else:
            en[kind][k] = max(t, en[kind].get(k, t))
    for kind in out:
        out[kind] = {k: (st[kind][k], en[kind][k]) for k in st[kind] if k in en[kind]}
    return out
