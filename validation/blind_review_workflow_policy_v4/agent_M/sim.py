"""Independent simulator for the loan and pharmacy record documents.
Standard library only. Built from the front-matter rules in this folder."""
import re, heapq, copy

DAYS = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6}

# ---------------------------------------------------------------- front matter
def parse_front_matter(path):
    txt = open(path, encoding='utf-8').read()
    flat = re.sub(r'\s+', ' ', txt)
    wseg = flat[flat.index('Workers.'):flat.index('Process.')]
    pools = {}
    for m in re.finditer(r'([A-Z][A-Za-z ]*?): (\d+) workers \(([^)]*)\), working (\w+) to (\w+) (\d\d):(\d\d) to (\d\d):(\d\d)', wseg):
        name = m.group(1).strip()
        if name.startswith('Workers. '):
            name = name[len('Workers. '):]
        # names like "... needs. Clerk" -> take after last '. '
        name = name.split('. ')[-1]
        pools[name] = dict(n=int(m.group(2)), d0=DAYS[m.group(4)], d1=DAYS[m.group(5)],
                           open=int(m.group(6)) * 3600 + int(m.group(7)) * 60,
                           close=int(m.group(8)) * 3600 + int(m.group(9)) * 60)
    return pools, flat

# ---------------------------------------------------------------- process graphs (hand-coded from the Process sections,
# which are word-for-word identical between policyP and policyH of each process)
LOAN = {
    'start': ('act', 'Check application form completeness'),
    'act': {
        'Check application form completeness': ('Clerk', ('dec', 'D1')),
        'Return application back to applicant': ('Clerk', ('wait', 'W1')),
        'Appraise property': ('Appraiser', ('join', 'J1')),
        'AML Check': ('AML Investigator', ('join', 'J1')),
        'Check credit history': ('Clerk', ('join', 'J1')),
        'Applicant completes form': ('Applicant', ('act', 'Check application form completeness')),
        'Assess loan risk': ('Loan Officer', ('dec', 'D2')),
        'Reject application': ('Clerk', ('end',)),
        'Design loan offer': ('Loan Officer', ('act', 'Approve Loan Offer')),
        'Approve Loan Offer': ('Senior Officer', ('dec', 'D3')),
        'Prepare acceptance pack': ('Loan Officer', ('act', 'Approve and send acceptance pack')),
        'Prepare home insurance quote': ('Clerk', ('act', 'Approve and post home insurance quote')),
        'Approve and send acceptance pack': ('Loan Officer', ('join', 'J2')),
        'Approve and post home insurance quote': ('Loan Officer', ('join', 'J2')),
        'Consider re-design loan offer': ('Senior Officer', ('dec', 'D5')),
        'Approve application': ('Clerk', ('end',)),
        'Cancel application': ('Clerk', ('end',)),
    },
    'dec': {
        'D1': [('D1-a', 0.2, ('act', 'Return application back to applicant')), ('D1-b', 0.8, ('split', 'S1'))],
        'D2': [('D2-a', 0.5, ('act', 'Reject application')), ('D2-b', 0.5, ('act', 'Design loan offer'))],
        'D3': [('D3-a', 0.2, ('act', 'Design loan offer')), ('D3-b', 0.8, ('split', 'S2'))],
        'D4': [('D4-a', 0.5, ('wait', 'W3')), ('D4-b', 0.5, ('act', 'Consider re-design loan offer'))],
        'D5': [('D5-a', 0.45, ('act', 'Cancel application')), ('D5-b', 0.55, ('act', 'Design loan offer'))],
    },
    'wait': {'W1': ('act', 'Applicant completes form'), 'W2': ('act', 'Assess loan risk'), 'W3': ('act', 'Approve application')},
    'split': {'S1': [('act', 'Appraise property'), ('act', 'Check credit history'), ('act', 'AML Check')],
              'S2': [('act', 'Prepare acceptance pack'), ('act', 'Prepare home insurance quote')]},
    'join': {'J1': (3, ('wait', 'W2')), 'J2': (2, ('dec', 'D4'))},
}
PHARM = {
    'start': ('act', 'Process drop-off'),
    'act': {
        'Process drop-off': ('Technician', ('wait', 'W1')),
        'Enter prescription details': ('Technician', ('act', 'Check if refill is allowed')),
        'Check if refill is allowed': ('Pharmacy System', ('dec', 'D1')),
        'Contact Doctor about refill': ('Technician', ('dec', 'D2')),
        'Check DUR': ('Pharmacy System', ('dec', 'D3')),
        'Check Insurance': ('Pharmacy System', ('dec', 'D5')),
        'Contact customer / doctor': ('Pharmacy System', ('act', 'Check Insurance')),
        'Resolve DUR manually': ('Pharmacist', ('act', 'Check Insurance')),
        'Resolve insurance issues manually': ('Technician', ('dec', 'D6')),
        'Pack the drugs (Production)': ('Technician', ('act', 'Check for Quality Assurance')),
        'Check for Quality Assurance': ('Pharmacist', ('dec', 'D7')),
        'Pick-up': ('Technician', ('end',)),
    },
    'dec': {
        'D1': [('D1-a', 0.94, ('act', 'Check DUR')), ('D1-b', 0.06, ('act', 'Contact Doctor about refill'))],
        'D2': [('D2-a', 0.99, ('act', 'Check DUR')), ('D2-b', 0.01, ('end',))],
        'D3': [('D3-a', 0.8, ('act', 'Check Insurance')), ('D3-b', 0.2, ('dec', 'D4'))],
        'D4': [('D4-a', 0.95, ('act', 'Resolve DUR manually')), ('D4-b', 0.05, ('act', 'Contact customer / doctor'))],
        'D5': [('D5-a', 0.83, ('dec', 'D6')), ('D5-b', 0.17, ('act', 'Resolve insurance issues manually'))],
        'D6': [('D6-a', 0.07, ('wait', 'W3')), ('D6-b', 0.93, ('wait', 'W2'))],
        'D7': [('D7-a', 0.05, ('dec', 'D6')), ('D7-b', 0.95, ('wait', 'W3'))],
    },
    'wait': {'W1': ('act', 'Enter prescription details'), 'W2': ('act', 'Pack the drugs (Production)'), 'W3': ('act', 'Pick-up')},
    'split': {}, 'join': {},
}

# ---------------------------------------------------------------- chapter parsing
def parse_chapter(path, act_names):
    lines = open(path, encoding='utf-8').read().splitlines()
    secs = {}
    cur = None
    for ln in lines:
        m = re.match(r'Run \d+: (.*)$', ln)
        if m:
            cur = m.group(1).strip(); secs[cur] = []; continue
        if cur is None or ln.startswith('case ') or not ln.strip():
            continue
        secs[cur].append(ln)
    def records(name):
        toks = ' '.join(secs[name]).split()
        recs, r = [], None
        for t in toks:
            if re.fullmatch(r'c\d{4}', t):
                if r: recs.append(r)
                r = [t]
            else:
                r.append(t)
        if r: recs.append(r)
        return recs
    def split_name(tokens):
        i = 0
        while i < len(tokens) and not re.fullmatch(r'-?\d+(\.\d+)?', tokens[i]):
            i += 1
        return ' '.join(tokens[:i]), tokens[i:]
    ch = {}
    ch['cases'] = {r[0]: (int(r[1]), int(r[2])) for r in records('Cases')}
    ch['order'] = list(ch['cases'].keys())
    work = {}
    for r in records('Work plan'):
        nm, rest = split_name(r[1:])
        assert nm in act_names, (path, nm)
        work[(r[0], nm)] = [int(x) for x in rest]
    ch['work'] = work
    wait = {}
    for r in records('Wait plan'):
        wait[(r[0], r[1])] = [int(x) for x in r[2:]]
    ch['wait'] = wait
    draws = {}
    for r in records('Route draws'):
        draws[(r[0], r[1])] = [float(x) for x in r[2:]]
    ch['draws'] = draws
    tl = []
    for r in records('Task log'):
        nm, rest = split_name(r[1:])
        assert nm in act_names, (path, nm)
        tl.append((r[0], nm, int(rest[0]), int(rest[1]), int(rest[2]), int(rest[3]), ' '.join(rest[4:])))
    ch['tasklog'] = tl
    ch['waitlog'] = [(r[0], r[1], int(r[2]), int(r[3]), int(r[4])) for r in records('Wait log')]
    ch['declog'] = [(r[0], r[1], int(r[2]), int(r[3]), r[4]) for r in records('Decision log')]
    # activity id order = position in Work plan table (first case's block)
    first = ch['order'][0]
    ch['act_order'] = [a for (c, a) in work.keys() if c == first]
    return ch

# ---------------------------------------------------------------- calendars
class Worker:
    def __init__(self, pool, idx, spec, unavail=()):
        self.name = f'{pool}_{idx}'; self.idx = idx; self.spec = spec
        self.unavail = sorted(unavail); self.free = 0
    def _day_intervals(self, t):
        d = t // 86400
        while True:
            wd = d % 7
            if self.spec['d0'] <= wd <= self.spec['d1']:
                a, b = d * 86400 + self.spec['open'], d * 86400 + self.spec['close']
                segs = [(a, b)]
                for (u0, u1) in self.unavail:
                    ns = []
                    for (x, y) in segs:
                        if u1 <= x or u0 >= y: ns.append((x, y)); continue
                        if x < u0: ns.append((x, u0))
                        if u1 < y: ns.append((u1, y))
                    segs = ns
                for s in segs:
                    if s[1] > t:
                        yield (max(s[0], t), s[1])
            d += 1
    def next_start(self, t):
        for (a, b) in self._day_intervals(t):
            return a
    def finish(self, start, work):
        if work == 0:
            return start
        rem = work
        for (a, b) in self._day_intervals(start):
            if b - a >= rem:
                return a + rem
            rem -= b - a

# ---------------------------------------------------------------- simulation
class Sim:
    def __init__(self, proc, pools, ch, removed=(), extra_workers=None, unavail=None, prob=None):
        self.P = proc; self.ch = ch
        self.prob = prob or {}
        extra_workers = extra_workers or {}
        unavail = unavail or {}
        self.workers = {}
        for p, spec in pools.items():
            n = spec['n'] + extra_workers.get(p, 0)
            self.workers[p] = [Worker(p, i, spec, unavail.get(f'{p}_{i}', ())) for i in range(n)]
        self.aid = {a: i for i, a in enumerate(ch['act_order'])}
        self.cases = [c for c in ch['order'] if c not in removed]
        self.arr = {c: ch['cases'][c][0] for c in self.cases}
        self.visits = {}; self.joins = {}
        self.tasklog = []; self.waitlog = []; self.declog = []; self.end = {}
        self.ev = []; self.seq = 0; self.pending = []
        self.active = {c: 0 for c in self.cases}   # open paths

    def visit(self, c, node):
        k = (c, node); self.visits[k] = self.visits.get(k, 0) + 1; return self.visits[k]

    def push(self, t, kind, data):
        self.seq += 1; heapq.heappush(self.ev, (t, self.seq, kind, data))

    def reach(self, c, node, t):
        typ = node[0]
        if typ == 'act':
            v = self.visit(c, node[1])
            self.pending.append((t, self.arr[c], c, self.aid[node[1]], v, node[1]))
        elif typ == 'wait':
            v = self.visit(c, node[1])
            d = self.ch['wait'][(c, node[1])][v - 1]
            self.waitlog.append((c, node[1], v, t, t + d))
            self.push(t + d, 'wait', (c, node[1]))
        elif typ == 'dec':
            v = self.visit(c, node[1])
            u = self.ch['draws'][(c, node[1])][v - 1]
            routes = self.P['dec'][node[1]]
            ps = self.prob.get(node[1])
            tot = 0.0; chosen = None
            for (rid, p, nxt) in routes:
                p = ps[rid] if ps else p
                tot += p
                if tot > u + 1e-12 and chosen is None:
                    chosen = (rid, nxt)
            if chosen is None:
                chosen = (routes[-1][0], routes[-1][2])
            self.declog.append((c, node[1], v, t, chosen[0]))
            self.reach(c, chosen[1], t)
        elif typ == 'split':
            branches = self.P['split'][node[1]]
            self.active[c] += len(branches) - 1
            for b in branches:
                self.reach(c, b, t)
        elif typ == 'join':
            n, nxt = self.P['join'][node[1]]
            k = (c, node[1]); self.joins[k] = self.joins.get(k, 0) + 1
            if self.joins[k] == n:
                self.joins[k] = 0
                self.reach(c, nxt, t)
            else:
                self.active[c] -= 1
        elif typ == 'end':
            self.active[c] -= 1
            if self.active[c] == 0:
                self.end[c] = t

    def assign(self):
        self.pending.sort()
        for (t, _a, c, _aid, v, act) in self.pending:
            pool, _ = self.P['act'][act]
            work = self.ch['work'][(c, act)][v - 1]
            best = None
            for w in self.workers[pool]:
                s = w.next_start(max(t, w.free))
                key = (s, w.free, w.idx)
                if best is None or key < best[0]:
                    best = (key, w)
            (s, _, _), w = best
            e = w.finish(s, work)
            w.free = e
            self.tasklog.append((c, act, v, t, s, e, w.name))
            self.push(e, 'task', (c, act))
        self.pending = []

    def run(self):
        for c in self.cases:
            self.push(self.arr[c], 'arr', (c,))
        while self.ev:
            t = self.ev[0][0]
            while self.ev and self.ev[0][0] == t:
                _, _, kind, data = heapq.heappop(self.ev)
                c = data[0]
                if kind == 'arr':
                    self.active[c] = 1
                    self.reach(c, self.P['start'], t)
                elif kind == 'task':
                    self.reach(c, self.P['act'][data[1]][1], t)
                elif kind == 'wait':
                    self.reach(c, self.P['wait'][data[1]], t)
            if self.pending:
                self.assign()
        return self

def compare(sim, ch):
    diffs = []
    for c in ch['order']:
        if sim.end.get(c) != ch['cases'][c][1]:
            diffs.append(('case end', c, ch['cases'][c][1], sim.end.get(c)))
    for name, a, b in (('task', sim.tasklog, ch['tasklog']), ('wait', sim.waitlog, ch['waitlog']), ('decision', sim.declog, ch['declog'])):
        sa, sb = sorted(a), sorted(b)
        if sa != sb:
            only_sim = sorted(set(sa) - set(sb)); only_doc = sorted(set(sb) - set(sa))
            diffs.append((name, 'sim-only', only_sim[:5], 'doc-only', only_doc[:5], len(sa), len(sb)))
    return diffs
