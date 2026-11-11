"""Deterministic replay simulator for the Loan and Pharmacy process records.

Written from the front-matter rules only. Standard library only.
"""
import heapq
import re
from fractions import Fraction

DAY = 86400

# ---------------------------------------------------------------- models
# node kinds: ('act', pool, next) ('wait', next) ('dec', [(route, prob, next)])
#             ('split', [next...]) ('join', n, next) ('end',)


def loan_model():
    P = lambda s: Fraction(s)
    n = {
        "Check application form completeness": ("act", "Clerk", "D1"),
        "D1": ("dec", [("D1-a", P("0.2"), "Return application back to applicant"),
                       ("D1-b", P("0.8"), "S1")]),
        "Return application back to applicant": ("act", "Clerk", "W1"),
        "S1": ("split", ["Appraise property", "Check credit history", "AML Check"]),
        "W1": ("wait", "Applicant completes form"),
        "Appraise property": ("act", "Appraiser", "J1"),
        "AML Check": ("act", "AML Investigator", "J1"),
        "Check credit history": ("act", "Clerk", "J1"),
        "Applicant completes form": ("act", "Applicant", "Check application form completeness"),
        "J1": ("join", 3, "W2"),
        "W2": ("wait", "Assess loan risk"),
        "Assess loan risk": ("act", "Loan Officer", "D2"),
        "D2": ("dec", [("D2-a", P("0.5"), "Reject application"),
                       ("D2-b", P("0.5"), "Design loan offer")]),
        "Reject application": ("act", "Clerk", "End"),
        "Design loan offer": ("act", "Loan Officer", "Approve Loan Offer"),
        "Approve Loan Offer": ("act", "Senior Officer", "D3"),
        "D3": ("dec", [("D3-a", P("0.2"), "Design loan offer"),
                       ("D3-b", P("0.8"), "S2")]),
        "S2": ("split", ["Prepare acceptance pack", "Prepare home insurance quote"]),
        "Prepare acceptance pack": ("act", "Loan Officer", "Approve and send acceptance pack"),
        "Prepare home insurance quote": ("act", "Clerk", "Approve and post home insurance quote"),
        "Approve and send acceptance pack": ("act", "Loan Officer", "J2"),
        "Approve and post home insurance quote": ("act", "Loan Officer", "J2"),
        "J2": ("join", 2, "D4"),
        "D4": ("dec", [("D4-a", P("0.5"), "W3"),
                       ("D4-b", P("0.5"), "Consider re-design loan offer")]),
        "Consider re-design loan offer": ("act", "Senior Officer", "D5"),
        "W3": ("wait", "Approve application"),
        "D5": ("dec", [("D5-a", P("0.45"), "Cancel application"),
                       ("D5-b", P("0.55"), "Design loan offer")]),
        "Approve application": ("act", "Clerk", "End"),
        "Cancel application": ("act", "Clerk", "End"),
        "End": ("end",),
    }
    wd = (32400, 61200, range(5))           # Mon-Fri 09:00-17:00
    pools = {
        "Applicant": (20, (0, 86340, range(7))),   # 00:00 to 23:59
        "Senior Officer": (3, wd), "Appraiser": (2, wd),
        "AML Investigator": (4, wd), "Loan Officer": (9, wd), "Clerk": (9, wd),
    }
    return {"nodes": n, "start": "Check application form completeness", "pools": pools}


def pharmacy_model():
    P = lambda s: Fraction(s)
    n = {
        "Process drop-off": ("act", "Technician", "W1"),
        "W1": ("wait", "Enter prescription details"),
        "Enter prescription details": ("act", "Technician", "Check if refill is allowed"),
        "Check if refill is allowed": ("act", "Pharmacy System", "D1"),
        "D1": ("dec", [("D1-a", P("0.94"), "Check DUR"),
                       ("D1-b", P("0.06"), "Contact Doctor about refill")]),
        "Contact Doctor about refill": ("act", "Technician", "D2"),
        "D2": ("dec", [("D2-a", P("0.99"), "Check DUR"), ("D2-b", P("0.01"), "End")]),
        "Check DUR": ("act", "Pharmacy System", "D3"),
        "D3": ("dec", [("D3-a", P("0.8"), "Check Insurance"), ("D3-b", P("0.2"), "D4")]),
        "D4": ("dec", [("D4-a", P("0.95"), "Resolve DUR manually"),
                       ("D4-b", P("0.05"), "Contact customer / doctor")]),
        "Check Insurance": ("act", "Pharmacy System", "D5"),
        "Contact customer / doctor": ("act", "Pharmacy System", "Check Insurance"),
        "Resolve DUR manually": ("act", "Pharmacist", "Check Insurance"),
        "D5": ("dec", [("D5-a", P("0.83"), "D6"),
                       ("D5-b", P("0.17"), "Resolve insurance issues manually")]),
        "Resolve insurance issues manually": ("act", "Technician", "D6"),
        "D6": ("dec", [("D6-a", P("0.07"), "W3"), ("D6-b", P("0.93"), "W2")]),
        "W2": ("wait", "Pack the drugs (Production)"),
        "Pack the drugs (Production)": ("act", "Technician", "Check for Quality Assurance"),
        "W3": ("wait", "Pick-up"),
        "Check for Quality Assurance": ("act", "Pharmacist", "D7"),
        "Pick-up": ("act", "Technician", "End"),
        "D7": ("dec", [("D7-a", P("0.05"), "D6"), ("D7-b", P("0.95"), "W3")]),
        "End": ("end",),
    }
    wd = (28800, 72000, range(5))           # Mon-Fri 08:00-20:00
    pools = {"Pharmacy System": (1, wd), "Technician": (8, wd), "Pharmacist": (1, wd)}
    return {"nodes": n, "start": "Process drop-off", "pools": pools}


MODELS = {"loan": loan_model, "pharmacy": pharmacy_model}

# ---------------------------------------------------------------- parsing
SEC_RE = re.compile(r"^Run \d+: (.+)$")
CASE_RE = re.compile(r"^c\d{4}$")


def parse_chapter(path):
    secs = {}
    cur = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            ln = raw.strip()
            m = SEC_RE.match(ln)
            if m:
                cur = m.group(1)
                secs.setdefault(cur, [])
                continue
            if cur and ln and CASE_RE.match(ln.split()[0]):
                secs[cur].append(ln)
            elif cur and ln and re.match(r"^\d+ \d+ \d+ \d+ .+_\d+$", ln) and secs[cur]:
                # PDF extraction wrapped a log row: "cNNNN activity" / "visit ... worker"
                secs[cur][-1] = secs[cur][-1] + " " + ln
    ch = {"cases": {}, "work": {}, "wait": {}, "draw": {}, "act_order": [],
          "tasks": {}, "waits": {}, "decs": {}}
    for ln in secs["Cases"]:
        c, a, e = ln.split()
        ch["cases"][c] = (int(a), int(e))

    def plan_rows(lines, conv):
        out = {}
        for ln in lines:
            t = ln.split()
            vals = []
            while t and re.fullmatch(r"[0-9.]+", t[-1]):
                vals.append(t.pop())
            vals.reverse()
            out[(t[0], " ".join(t[1:]))] = [conv(v) for v in vals]
        return out

    ch["work"] = plan_rows(secs["Work plan"], int)
    ch["wait"] = plan_rows(secs["Wait plan"], int)
    ch["draw"] = plan_rows(secs["Route draws"], Fraction)
    first = secs["Work plan"][0].split()[0]
    for (c, a) in ch["work"]:
        if c == first:
            ch["act_order"].append(a)
    tre = re.compile(r"^(c\d{4}) (.+?) (\d+) (\d+) (\d+) (\d+) (.+_\d+)$")
    for ln in secs["Task log"]:
        m = tre.match(ln)
        c, a, v, en, st, ed, w = m.groups()
        ch["tasks"][(c, a, int(v))] = (int(en), int(st), int(ed), w)
    for ln in secs["Wait log"]:
        c, w, v, s, e = ln.split()
        ch["waits"][(c, w, int(v))] = (int(s), int(e))
    for ln in secs["Decision log"]:
        c, d, v, t, r = ln.split()
        ch["decs"][(c, d, int(v))] = (int(t), r)
    return ch

# ---------------------------------------------------------------- workers


class Worker:
    def __init__(self, name, hours, unavailable):
        self.name = name
        self.open, self.close, self.days = hours
        self.unav = sorted(unavailable)      # list of [a, b)
        self.free_at = 0                     # time the worker became free
        self.used = False

    def day_intervals(self, d):
        if d % 7 not in self.days:
            return []
        ivs = [(d * DAY + self.open, d * DAY + self.close)]
        for (ua, ub) in self.unav:
            nxt = []
            for (a, b) in ivs:
                if ub <= a or ua >= b:
                    nxt.append((a, b))
                else:
                    if a < ua:
                        nxt.append((a, ua))
                    if ub < b:
                        nxt.append((ub, b))
            ivs = nxt
        return ivs

    def intervals_from(self, t):
        d = t // DAY
        while True:
            for (a, b) in self.day_intervals(d):
                if b > t:
                    yield (max(a, t), b)
            d += 1

    def earliest_start(self, t):
        for (a, b) in self.intervals_from(t):
            return a

    def finish(self, s, work):
        left = work
        for (a, b) in self.intervals_from(s):
            if left <= b - a:
                return a + left
            left -= b - a

# ---------------------------------------------------------------- simulate


def simulate(process, ch, change=None):
    """change: dict with optional keys
       work: {(case, act, visit): value}; wait: {(case, wait, visit): value}
       draw: {(case, dec, visit): Fraction}; probs: {dec: [Fraction...]}
       remove: set of case ids; unavailable: {worker_name: [(a, b)]}"""
    change = change or {}
    model = MODELS[process]()
    nodes = model["nodes"]
    work = dict(ch["work"]); wait = dict(ch["wait"]); draw = dict(ch["draw"])
    over_work = change.get("work", {}); over_wait = change.get("wait", {})
    over_draw = change.get("draw", {}); probs = change.get("probs", {})
    unav = change.get("unavailable", {})
    cases = {c: v[0] for c, v in ch["cases"].items() if c not in change.get("remove", set())}
    act_id = {a: i for i, a in enumerate(ch["act_order"])}

    workers = {}
    for pool, (k, hours) in model["pools"].items():
        workers[pool] = [Worker(f"{pool}_{i}", hours, unav.get(f"{pool}_{i}", []))
                         for i in range(k)]

    visits = {}
    join_cnt = {}
    tasks, waits, decs, ends = {}, {}, {}, {}
    queues = {p: [] for p in workers}
    events = []      # (time, seq, kind, payload)
    seq = [0]

    def push(t, kind, payload):
        seq[0] += 1
        heapq.heappush(events, (t, seq[0], kind, payload))

    def visit(c, node):
        k = (c, node)
        visits[k] = visits.get(k, 0) + 1
        return visits[k]

    def reach(c, node, t):
        kind = nodes[node][0]
        if kind == "end":
            ends[c] = t if c not in ends else max(ends[c], t)
            return
        if kind == "act":
            v = visit(c, node)
            pool = nodes[node][1]
            w_need = over_work.get((c, node, v))
            if w_need is None:
                w_need = work[(c, node)][v - 1]
            queues[pool].append((t, cases[c], c, act_id[node], v, node, w_need))
        elif kind == "wait":
            v = visit(c, node)
            d = over_wait.get((c, node, v))
            if d is None:
                d = wait[(c, node)][v - 1]
            waits[(c, node, v)] = (t, t + d)
            push(t + d, "reach", (c, nodes[node][1]))
        elif kind == "dec":
            v = visit(c, node)
            x = over_draw.get((c, node, v))
            if x is None:
                x = draw[(c, node)][v - 1]
            routes = nodes[node][1]
            ps = probs.get(node, [r[1] for r in routes])
            tot = Fraction(0)
            chosen = None
            for (r, _, nxt), p in zip(routes, ps):
                tot += p
                if tot > x:
                    chosen = (r, nxt)
                    break
            if chosen is None:
                raise RuntimeError(f"no route {c} {node} {x}")
            decs[(c, node, v)] = (t, chosen[0])
            reach(c, chosen[1], t)
        elif kind == "split":
            for nxt in nodes[node][1]:
                reach(c, nxt, t)
        elif kind == "join":
            k = (c, node)
            join_cnt[k] = join_cnt.get(k, 0) + 1
            if join_cnt[k] == nodes[node][1]:
                join_cnt[k] = 0
                reach(c, nodes[node][2], t)

    def dispatch():
        for pool, q in queues.items():
            if not q:
                continue
            q.sort()
            for (en, _, c, _, v, node, wneed) in q:
                best = None
                for i, w in enumerate(workers[pool]):
                    s = w.earliest_start(max(en, w.free_at))
                    key = (s, w.free_at if w.used else -1, i)
                    if best is None or key < best[0]:
                        best = (key, w)
                s = best[0][0]
                w = best[1]
                e = w.finish(s, wneed)
                w.free_at = e
                w.used = True
                tasks[(c, node, v)] = (en, s, e, w.name)
                push(e, "done", (c, node))
            q.clear()

    for c, a in cases.items():
        push(a, "arrive", c)
    while events:
        t = events[0][0]
        while events and events[0][0] == t:
            _, _, kind, p = heapq.heappop(events)
            if kind == "arrive":
                reach(p, model["start"], t)
            elif kind == "reach":
                reach(p[0], p[1], t)
            elif kind == "done":
                reach(p[0], nodes[p[1]][2], t)
        dispatch()
    return {"tasks": tasks, "waits": waits, "decs": decs, "ends": ends}


def compare(ch, res):
    diffs = []
    for c, (a, e) in ch["cases"].items():
        if res["ends"].get(c) != e:
            diffs.append(f"end {c}: rec {e} sim {res['ends'].get(c)}")
    for name, rec, sim in (("task", ch["tasks"], res["tasks"]),
                           ("wait", ch["waits"], res["waits"]),
                           ("dec", ch["decs"], res["decs"])):
        for k in sorted(set(rec) | set(sim)):
            if rec.get(k) != sim.get(k):
                diffs.append(f"{name} {k}: rec {rec.get(k)} sim {sim.get(k)}")
    return diffs
