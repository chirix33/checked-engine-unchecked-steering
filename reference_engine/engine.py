"""Deterministic reference engine for spec/workflow_semantics_v1.md.

This is evaluation-only code. It must never be exposed to a system under test. It implements section 8 as
written: a sequential dispatch loop over activations ordered by key. Standard library only.

Usage: python -I reference_engine/engine.py <scenario.json> <out.json>
"""
import hashlib
import heapq
import json
import math
import os
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction

WEEK = 7 * 86400
DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
VISIT_LIMIT = 100
NORMAL = statistics.NormalDist()
FLOW_TYPES = {"startEvent", "endEvent", "task", "intermediateCatchEvent", "exclusiveGateway", "parallelGateway"}
FORBIDDEN_KEYS = ["batch_processing", "prioritisation_rules", "case_attributes", "event_attributes",
                  "global_attributes", "branch_rules", "multitask"]


class RunError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def local(tag):
    return tag.split("}")[-1]


def is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def decimal_fraction(text, code):
    """Exact rational from a decimal string."""
    if not isinstance(text, str) or not re.fullmatch(r"\s*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?\s*", text):
        raise RunError(code)
    return Fraction(text.strip())


# ---- Calendars (section 3) ----

def parse_time(text):
    h, m, s = text.split(".")[0].split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def parse_periods(periods):
    windows = []
    if not isinstance(periods, list):
        raise RunError("unsupported_model")
    for p in periods:
        try:
            a, b = DAYS.index(p["from"]), DAYS.index(p["to"])
            begin, end = parse_time(p["beginTime"]), parse_time(p["endTime"])
        except (KeyError, ValueError, AttributeError, TypeError):
            raise RunError("unsupported_model")
        if a > b:
            raise RunError("unsupported_model")
        for d in range(a, b + 1):
            if end > begin:
                windows.append((d * 86400 + begin, d * 86400 + end))
    windows.sort()
    merged = []
    for lo, hi in windows:
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    if not merged:
        raise RunError("unsupported_model")
    return merged


class WorkingSet:
    """Weekly windows, minus finite removed intervals, from a lower bound onward."""

    def __init__(self, windows, lower=0):
        self.windows = windows
        self.lower = lower
        self.removed = []

    def remove(self, lo, hi):
        self.removed.append((lo, hi))
        self.removed.sort()

    def pieces(self, t):
        """Yield working intervals in time order, clipped to start at or after t."""
        t = max(t, self.lower)
        week = t // WEEK
        while True:
            base = week * WEEK
            for a, b in self.windows:
                lo, hi = max(base + a, t), base + b
                if hi <= lo:
                    continue
                cursor = lo
                for r0, r1 in self.removed:
                    if r1 <= cursor:
                        continue
                    if r0 >= hi:
                        break
                    if r0 > cursor:
                        yield cursor, r0
                    cursor = max(cursor, r1)
                    if cursor >= hi:
                        break
                if cursor < hi:
                    yield cursor, hi
            week += 1

    def next_open(self, t):
        return next(self.pieces(t))[0]

    def work_end(self, s, d):
        if d == 0:
            return s
        remaining = d
        for lo, hi in self.pieces(s):
            length = hi - lo
            if remaining <= length:
                return lo + remaining
            remaining -= length
        raise AssertionError("unreachable")


# ---- Distributions (section 5) ----

class Dist:
    def __init__(self, name, params, code):
        self.name = name
        self.params = params
        if name == "fix":
            if len(params) != 1 or params[0] < 0:
                raise RunError(code)
        elif name == "expon":
            if len(params) != 3:
                raise RunError(code)
            mean, lo, hi = params
            if not (lo >= 0 and mean > lo and hi > lo):
                raise RunError(code)
        elif name == "norm":
            if len(params) != 4:
                raise RunError(code)
            mean, std, lo, hi = params
            if not (std > 0 and hi > max(lo, 0)):
                raise RunError(code)
        else:
            raise RunError(code)

    def quantile(self, u):
        u = float(u)
        if self.name == "fix":
            return math.floor(self.params[0] + 0.5)
        if self.name == "expon":
            mean, lo, hi = self.params
            s = mean - lo
            f = 1 - math.exp(-(hi - lo) / s)
            x = lo - s * math.log(1 - u * f)
            lower = lo
        else:
            mean, std, lo, hi = self.params
            lower = max(lo, 0)
            a, b = NORMAL.cdf((lower - mean) / std), NORMAL.cdf((hi - mean) / std)
            p = a + u * (b - a)
            if p <= 0:
                x = lower
            elif p >= 1:
                x = hi
            else:
                x = mean + std * NORMAL.inv_cdf(p)
        return max(math.ceil(lower), min(math.floor(hi), math.floor(x + 0.5)))


def model_dist(entry):
    try:
        params = [float(p["value"]) for p in entry["distribution_params"]]
        return Dist(entry["distribution_name"], params, "unsupported_model")
    except (KeyError, TypeError, ValueError):
        raise RunError("unsupported_model")


def intervention_dist(iv):
    name, params = iv.get("distribution_name"), iv.get("distribution_params")
    if not isinstance(name, str) or not isinstance(params, list) or not all(is_number(p) for p in params):
        raise RunError("invalid_intervention")
    return Dist(name, [float(p) for p in params], "invalid_intervention")


# ---- Model (section 2) ----

class Model:
    def __init__(self, bpmn_path, params_path):
        try:
            root = ET.parse(bpmn_path).getroot()
        except ET.ParseError:
            raise RunError("unsupported_model")
        try:
            with open(params_path, encoding="utf-8") as f:
                self.params = json.load(f)
        except ValueError:
            raise RunError("unsupported_model")
        self.kind = {}
        self.flows = {}
        self.incoming = {}
        self.outgoing = {}
        seen = {}
        for process in root.iter():
            if local(process.tag) != "process":
                continue
            for el in process:
                name = local(el.tag)
                seen[el.get("id")] = name
                if name == "sequenceFlow":
                    self.flows[el.get("id")] = (el.get("sourceRef"), el.get("targetRef"))
                elif name in FLOW_TYPES:
                    if name == "intermediateCatchEvent" and not any(local(c.tag) == "timerEventDefinition" for c in el):
                        raise RunError("unsupported_model")
                    self.kind[el.get("id")] = name
        for fid, (src, tgt) in self.flows.items():
            if src not in self.kind or tgt not in self.kind:
                raise RunError("unsupported_model")
            self.outgoing.setdefault(src, []).append(fid)
            self.incoming.setdefault(tgt, []).append(fid)
        self._check_structure()
        self._read_params()

    def _check_structure(self):
        starts = [e for e, k in self.kind.items() if k == "startEvent"]
        ends = [e for e, k in self.kind.items() if k == "endEvent"]
        if len(starts) != 1 or not ends:
            raise RunError("unsupported_model")
        self.start = starts[0]
        for e, k in self.kind.items():
            n_in, n_out = len(self.incoming.get(e, [])), len(self.outgoing.get(e, []))
            ok = {
                "startEvent": n_in == 0 and n_out == 1,
                "endEvent": n_in >= 1 and n_out == 0,
                "task": n_in >= 1 and n_out == 1,
                "intermediateCatchEvent": n_in >= 1 and n_out == 1,
                "exclusiveGateway": n_in >= 1 and n_out >= 1,
                "parallelGateway": n_in >= 1 and n_out >= 1,
            }[k]
            if not ok:
                raise RunError("unsupported_model")

    def _read_params(self):
        p = self.params
        if any(p.get(key) for key in FORBIDDEN_KEYS) or p.get("model_type") == "FUZZY":
            raise RunError("unsupported_model")
        try:
            calendars = {c["id"]: parse_periods(c["time_periods"]) for c in p["resource_calendars"]}
            self.pools = {}
            self.pool_by_resource = {}
            for prof in p["resource_profiles"]:
                for r in prof["resource_list"]:
                    if r["name"] in self.pools or int(r["amount"]) < 1:
                        raise RunError("unsupported_model")
                    self.pools[r["name"]] = {"amount": int(r["amount"]), "windows": calendars[r["calendar"]]}
                    self.pool_by_resource[r["id"]] = r["name"]
            self.task_pool, self.task_dist = {}, {}
            for t in p["task_resource_distribution"]:
                if len(t["resources"]) != 1:
                    raise RunError("unsupported_model")
                entry = t["resources"][0]
                self.task_pool[t["task_id"]] = self.pool_by_resource[entry["resource_id"]]
                self.task_dist[t["task_id"]] = model_dist(entry)
            self.timer_dist = {e["event_id"]: model_dist(e) for e in p.get("event_distribution") or []}
            self.branch = {}
            for g in p.get("gateway_branching_probabilities") or []:
                self.branch[g["gateway_id"]] = [(x["path_id"], decimal_fraction(str(x["value"]), "unsupported_model"))
                                                for x in g["probabilities"]]
            self.arrival_dist = model_dist(p["arrival_time_distribution"])
            self.arrival_windows = parse_periods(p["arrival_time_calendar"])
        except (KeyError, TypeError, ValueError):
            raise RunError("unsupported_model")
        for e, k in self.kind.items():
            if k == "task" and e not in self.task_dist:
                raise RunError("unsupported_model")
            if k == "intermediateCatchEvent" and e not in self.timer_dist:
                raise RunError("unsupported_model")
            if k == "exclusiveGateway" and len(self.outgoing[e]) >= 2:
                listed = [f for f, _ in self.branch.get(e, [])]
                if sorted(listed) != sorted(self.outgoing[e]) or sum(v for _, v in self.branch[e]) != 1:
                    raise RunError("unsupported_model")

    def is_branching(self, element):
        return self.kind.get(element) == "exclusiveGateway" and len(self.outgoing[element]) >= 2


# ---- Interventions (section 9) ----

class Selector:
    def __init__(self, raw):
        if raw is None:
            raw = {}
        if not isinstance(raw, dict) or set(raw) - {"case", "visit", "from", "to"}:
            raise RunError("invalid_intervention")
        self.case, self.visit = raw.get("case"), raw.get("visit")
        self.lo, self.hi = raw.get("from"), raw.get("to")
        if self.case is not None and not isinstance(self.case, str):
            raise RunError("invalid_intervention")
        for v in (self.visit, self.lo, self.hi):
            if v is not None and not is_int(v):
                raise RunError("invalid_intervention")
        if self.lo is not None and self.hi is not None and self.lo >= self.hi:
            raise RunError("invalid_intervention")

    def matches(self, case, visit, time):
        return ((self.case is None or self.case == case) and (self.visit is None or self.visit == visit)
                and (self.lo is None or time >= self.lo) and (self.hi is None or time < self.hi))


class Rule:
    def __init__(self, op, selector, value):
        self.op, self.selector, self.value = op, selector, value


def valid_case_id(text):
    return isinstance(text, str) and re.fullmatch(r"[a-z0-9_-]+", text) is not None


class Plan:
    """All parsed interventions."""

    def __init__(self, model, entries, base_cases):
        if not isinstance(entries, list):
            raise RunError("invalid_scenario")
        self.duration, self.timer, self.routing = {}, {}, {}
        self.unavailable, self.added = [], []
        self.cases_added, self.cases_removed = {}, set()
        selectors = []
        for iv in entries:
            if not isinstance(iv, dict):
                raise RunError("invalid_intervention")
            kind = iv.get("type")
            if kind == "resource_unavailable":
                self._unavailable(model, iv)
            elif kind == "resource_add":
                self._add(model, iv)
            elif kind in ("duration_set", "duration_scale", "duration_distribution"):
                target = iv.get("task")
                if model.kind.get(target) != "task":
                    raise RunError("invalid_intervention")
                selectors.append(self._value_rule(iv, kind.split("_")[1], self.duration, target))
            elif kind in ("timer_set", "timer_scale", "timer_distribution"):
                target = iv.get("timer")
                if model.kind.get(target) != "intermediateCatchEvent":
                    raise RunError("invalid_intervention")
                selectors.append(self._value_rule(iv, kind.split("_")[1], self.timer, target))
            elif kind == "routing_set":
                selectors.append(self._routing(model, iv))
            elif kind == "case_add":
                if not valid_case_id(iv.get("case")) or not is_int(iv.get("arrival")) or iv["arrival"] < 0:
                    raise RunError("invalid_intervention")
                if iv["case"] in base_cases or iv["case"] in self.cases_added:
                    raise RunError("invalid_intervention")
                self.cases_added[iv["case"]] = iv["arrival"]
            elif kind == "case_remove":
                if iv.get("case") not in base_cases or iv["case"] in self.cases_removed:
                    raise RunError("invalid_intervention")
                self.cases_removed.add(iv["case"])
            else:
                raise RunError("invalid_intervention")
        existing = (set(base_cases) - self.cases_removed) | set(self.cases_added)
        for sel in selectors:
            if sel.case is not None and sel.case not in existing:
                raise RunError("invalid_intervention")

    def _unavailable(self, model, iv):
        pool, lo, hi = iv.get("pool"), iv.get("from"), iv.get("to")
        if pool not in model.pools or not is_int(lo) or not is_int(hi) or lo >= hi:
            raise RunError("invalid_intervention")
        amount = model.pools[pool]["amount"]
        has_count, has_list = "count" in iv, "instances" in iv
        if has_count == has_list:
            raise RunError("invalid_intervention")
        if has_count:
            count = iv["count"]
            if not is_int(count) or count < 1 or count > amount:
                raise RunError("invalid_intervention")
            names = [f"{pool}_{k}" for k in range(amount - count, amount)]
        else:
            names = iv["instances"]
            legal = {f"{pool}_{k}" for k in range(amount)}
            if not isinstance(names, list) or not names or not all(n in legal for n in names):
                raise RunError("invalid_intervention")
        self.unavailable.append((names, lo, hi))

    def _add(self, model, iv):
        pool, count, lo = iv.get("pool"), iv.get("count"), iv.get("from")
        if pool not in model.pools or not is_int(count) or count < 1 or not is_int(lo) or lo < 0:
            raise RunError("invalid_intervention")
        self.added.append((pool, count, lo))

    def _value_rule(self, iv, op, table, target):
        selector = Selector(iv.get("selector"))
        if op == "set":
            if not is_int(iv.get("seconds")) or iv["seconds"] < 0:
                raise RunError("invalid_intervention")
            value = iv["seconds"]
        elif op == "scale":
            value = decimal_fraction(iv.get("factor"), "invalid_intervention")
            if value < 0:
                raise RunError("invalid_intervention")
        else:
            value = intervention_dist(iv)
        table.setdefault(target, []).append(Rule(op, selector, value))
        return selector

    def _routing(self, model, iv):
        gateway, probs = iv.get("gateway"), iv.get("probabilities")
        if not model.is_branching(gateway) or not isinstance(probs, dict):
            raise RunError("invalid_intervention")
        if set(probs) != set(model.outgoing[gateway]):
            raise RunError("invalid_intervention")
        parsed = {f: decimal_fraction(v, "invalid_intervention") for f, v in probs.items()}
        if any(v < 0 for v in parsed.values()) or sum(parsed.values()) != 1:
            raise RunError("invalid_intervention")
        selector = Selector(iv.get("selector"))
        ordered = [(f, parsed[f]) for f, _ in model.branch[gateway]]
        self.routing.setdefault(gateway, []).append(Rule("set", selector, ordered))
        return selector


def matching_rule(table, target, case, visit, time):
    found = [r for r in table.get(target, []) if r.selector.matches(case, visit, time)]
    if len(found) > 1:
        raise RunError("conflicting_interventions")
    return found[0] if found else None


def apply_value(rule, base_dist, u):
    if rule is None:
        return base_dist.quantile(u)
    if rule.op == "set":
        return rule.value
    if rule.op == "distribution":
        return rule.value.quantile(u)
    return math.floor(Fraction(base_dist.quantile(u)) * rule.value + Fraction(1, 2))


# ---- Execution (sections 4 to 8) ----

class Instance:
    def __init__(self, name, k, working, free_at):
        self.name, self.k, self.working, self.free_at = name, k, working, free_at


class Run:
    def __init__(self, model, scenario):
        self.model = model
        self.seed = scenario["seed"]
        self.overrides = {}
        for o in scenario.get("draw_overrides") or []:
            try:
                key = (o["case"], o["element"], o["visit"], o["variable"])
                u = decimal_fraction(o["u"], "invalid_scenario")
            except (KeyError, TypeError):
                raise RunError("invalid_scenario")
            if not 0 <= u < 1:
                raise RunError("invalid_scenario")
            self.overrides[key] = u
        base_ids = ["c%04d" % k for k in range(scenario["n_cases"])]
        self.plan = Plan(model, scenario.get("interventions") or [], set(base_ids))
        self.arrival = self._arrivals(base_ids)
        self.instances = self._instances()
        self.heap = []
        self.state = {}
        self.tasks, self.timers, self.branches, self.draws, self.ends = [], [], [], [], {}

    def u(self, case, element, visit, variable):
        key = (case, element, visit, variable)
        if key in self.overrides:
            return self.overrides[key]
        text = f"{self.seed}|{case}|{element}|{visit}|{variable}"
        n = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        return Fraction(2 * (n >> 12) + 1, 2 ** 53)

    def _arrivals(self, base_ids):
        calendar = WorkingSet(self.model.arrival_windows)
        arrival = {}
        last = None
        for case in base_ids:
            if last is None:
                last = calendar.next_open(0)
            else:
                gap = self.model.arrival_dist.quantile(self.u(case, self.model.start, 1, "interarrival"))
                last = calendar.next_open(last + gap)
            arrival[case] = last
        for case in self.plan.cases_removed:
            del arrival[case]
        arrival.update(self.plan.cases_added)
        return arrival

    def _instances(self):
        pools = {}
        for name, info in self.model.pools.items():
            pools[name] = [Instance(f"{name}_{k}", k, WorkingSet(info["windows"]), 0) for k in range(info["amount"])]
        by_name = {i.name: i for group in pools.values() for i in group}
        for names, lo, hi in self.plan.unavailable:
            for name in names:
                by_name[name].working.remove(lo, hi)
        for pool, count, lo in self.plan.added:
            for _ in range(count):
                k = len(pools[pool])
                pools[pool].append(Instance(f"{pool}_{k}", k, WorkingSet(self.model.pools[pool]["windows"], lo), lo))
        return pools

    def next_visit(self, case, element):
        visits = self.state[case]["visits"]
        visits[element] = visits.get(element, 0) + 1
        if visits[element] > VISIT_LIMIT:
            raise RunError("visit_limit_exceeded")
        return visits[element]

    def record_draw(self, case, element, visit, variable, u):
        self.draws.append({"case": case, "element": element, "visit": visit, "variable": variable,
                           "u": format(float(u), ".12f")})

    def send(self, case, flow, time):
        """Move one token along a flow, following zero-time elements (section 7)."""
        pending = [(flow, time)]
        model = self.model
        while pending:
            fid, t = pending.pop()
            element = model.flows[fid][1]
            kind = model.kind[element]
            if kind == "task":
                visit = self.next_visit(case, element)
                self.record_draw(case, element, visit, "service", self.u(case, element, visit, "service"))
                heapq.heappush(self.heap, (t, self.arrival[case], case, element, visit))
            elif kind == "intermediateCatchEvent":
                visit = self.next_visit(case, element)
                u = self.u(case, element, visit, "timer")
                self.record_draw(case, element, visit, "timer", u)
                rule = matching_rule(self.plan.timer, element, case, visit, t)
                delay = apply_value(rule, model.timer_dist[element], u)
                self.timers.append({"case": case, "timer": element, "visit": visit, "start": t, "end": t + delay,
                                    "delay": delay})
                pending.append((model.outgoing[element][0], t + delay))
            elif kind == "exclusiveGateway":
                if not model.is_branching(element):
                    pending.append((model.outgoing[element][0], t))
                    continue
                visit = self.next_visit(case, element)
                u = self.u(case, element, visit, "branch")
                self.record_draw(case, element, visit, "branch", u)
                rule = matching_rule(self.plan.routing, element, case, visit, t)
                probabilities = rule.value if rule else model.branch[element]
                cumulative = Fraction(0)
                chosen = None
                for f, p in probabilities:
                    cumulative += p
                    if u < cumulative:
                        chosen = f
                        break
                self.branches.append({"case": case, "gateway": element, "visit": visit, "time": t, "flow": chosen})
                pending.append((chosen, t))
            elif kind == "parallelGateway":
                waiting = self.state[case]["waiting"]
                waiting.setdefault(fid, []).append(t)
                if all(waiting.get(f) for f in model.incoming[element]):
                    fired = 0
                    for f in model.incoming[element]:
                        earliest = min(waiting[f])
                        waiting[f].remove(earliest)
                        fired = max(fired, earliest)
                    for f in model.outgoing[element]:
                        pending.append((f, fired))
            elif kind == "endEvent":
                current = self.ends.get(case)
                if current is None or t >= current[0]:
                    self.ends[case] = (t, element)
            else:
                raise AssertionError(kind)

    def dispatch(self, activation):
        enabled, _, case, task, visit = activation
        best = None
        for r in self.instances[self.model.task_pool[task]]:
            s = r.working.next_open(max(enabled, r.free_at))
            rank = (s, r.free_at, r.k)
            if best is None or rank < best[0]:
                best = (rank, r)
        (start, _, _), r = best
        u = self.u(case, task, visit, "service")
        rule = matching_rule(self.plan.duration, task, case, visit, start)
        service = apply_value(rule, self.model.task_dist[task], u)
        end = r.working.work_end(start, service)
        r.free_at = end
        self.tasks.append({"case": case, "task": task, "visit": visit, "enabled": enabled, "start": start, "end": end,
                           "resource": r.name, "service": service})
        self.send(case, self.model.outgoing[task][0], end)

    def execute(self):
        for case, time in self.arrival.items():
            self.state[case] = {"visits": {}, "waiting": {}}
        for case, time in self.arrival.items():
            self.send(case, self.model.outgoing[self.model.start][0], time)
        while self.heap:
            self.dispatch(heapq.heappop(self.heap))
        for case in self.arrival:
            if case not in self.ends or any(self.state[case]["waiting"].values()):
                raise RunError("deadlock")
        cases = [{"case": c, "arrival": a, "end": self.ends[c][0], "end_event": self.ends[c][1]}
                 for c, a in self.arrival.items()]
        cases.sort(key=lambda x: (x["arrival"], x["case"]))
        self.tasks.sort(key=lambda x: (x["case"], x["enabled"], x["task"], x["visit"]))
        self.timers.sort(key=lambda x: (x["case"], x["start"], x["timer"], x["visit"]))
        self.branches.sort(key=lambda x: (x["case"], x["time"], x["gateway"], x["visit"]))
        self.draws.sort(key=lambda x: (x["case"], x["element"], x["visit"], x["variable"]))
        return {"status": "ok", "cases": cases, "tasks": self.tasks, "timers": self.timers,
                "branches": self.branches, "draws": self.draws}


def run_scenario(path):
    """Return the output object for a scenario file (section 11)."""
    scenario_id = None
    try:
        try:
            with open(path, encoding="utf-8") as f:
                scenario = json.load(f)
        except (OSError, ValueError):
            raise RunError("invalid_scenario")
        if not isinstance(scenario, dict):
            raise RunError("invalid_scenario")
        scenario_id = scenario.get("scenario_id")
        model_ref = scenario.get("model")
        if (scenario.get("schema") != "wf-scenario/1" or not isinstance(scenario_id, str)
                or not isinstance(model_ref, dict) or not isinstance(scenario.get("seed"), str)
                or not is_int(scenario.get("n_cases")) or scenario["n_cases"] < 0):
            raise RunError("invalid_scenario")
        folder = os.path.dirname(os.path.abspath(path))
        bpmn, params = os.path.join(folder, model_ref["bpmn"]), os.path.join(folder, model_ref["params"])
        if not os.path.exists(bpmn) or not os.path.exists(params):
            raise RunError("invalid_scenario")
        body = Run(Model(bpmn, params), scenario).execute()
        return {"schema": "wf-run/1", "scenario_id": scenario_id, **body}
    except RunError as e:
        return {"schema": "wf-run/1", "scenario_id": scenario_id, "status": "error", "error": e.code}


def main(scenario_path, out_path):
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(run_scenario(scenario_path), f, indent=0)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
