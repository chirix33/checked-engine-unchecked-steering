"""Own simulator for the Loan and Pharmacy processes, written from the front-matter rules only."""
import re, heapq, copy
from fractions import Fraction as F

DAY = 86400

# ---------------- process models (transcribed from front matter) ----------------
def H(h, m=0):
    return h * 3600 + m * 60

LOAN = {
    'start': 'Check application form completeness',
    'pools': {  # name: (count, weekdays, open, close)
        'Applicant': (20, range(7), 0, H(23, 59)),
        'Senior Officer': (3, range(5), H(9), H(17)),
        'Appraiser': (2, range(5), H(9), H(17)),
        'AML Investigator': (4, range(5), H(9), H(17)),
        'Loan Officer': (9, range(5), H(9), H(17)),
        'Clerk': (9, range(5), H(9), H(17)),
    },
    'nodes': {
        'Check application form completeness': ('act', 'Clerk', 'D1'),
        'D1': ('dec', [('D1-a', '0.2', 'Return application back to applicant'), ('D1-b', '0.8', 'S1')]),
        'Return application back to applicant': ('act', 'Clerk', 'W1'),
        'S1': ('split', ['Appraise property', 'Check credit history', 'AML Check']),
        'W1': ('wait', 'Applicant completes form'),
        'Appraise property': ('act', 'Appraiser', 'J1'),
        'AML Check': ('act', 'AML Investigator', 'J1'),
        'Check credit history': ('act', 'Clerk', 'J1'),
        'Applicant completes form': ('act', 'Applicant', 'Check application form completeness'),
        'J1': ('join', 3, 'W2'),
        'W2': ('wait', 'Assess loan risk'),
        'Assess loan risk': ('act', 'Loan Officer', 'D2'),
        'D2': ('dec', [('D2-a', '0.5', 'Reject application'), ('D2-b', '0.5', 'Design loan offer')]),
        'Reject application': ('act', 'Clerk', 'End'),
        'Design loan offer': ('act', 'Loan Officer', 'Approve Loan Offer'),
        'Approve Loan Offer': ('act', 'Senior Officer', 'D3'),
        'D3': ('dec', [('D3-a', '0.2', 'Design loan offer'), ('D3-b', '0.8', 'S2')]),
        'S2': ('split', ['Prepare acceptance pack', 'Prepare home insurance quote']),
        'Prepare acceptance pack': ('act', 'Loan Officer', 'Approve and send acceptance pack'),
        'Prepare home insurance quote': ('act', 'Clerk', 'Approve and post home insurance quote'),
        'Approve and send acceptance pack': ('act', 'Loan Officer', 'J2'),
        'Approve and post home insurance quote': ('act', 'Loan Officer', 'J2'),
        'J2': ('join', 2, 'D4'),
        'D4': ('dec', [('D4-a', '0.5', 'W3'), ('D4-b', '0.5', 'Consider re-design loan offer')]),
        'Consider re-design loan offer': ('act', 'Senior Officer', 'D5'),
        'W3': ('wait', 'Approve application'),
        'D5': ('dec', [('D5-a', '0.45', 'Cancel application'), ('D5-b', '0.55', 'Design loan offer')]),
        'Approve application': ('act', 'Clerk', 'End'),
        'Cancel application': ('act', 'Clerk', 'End'),
        'End': ('end',),
    },
}

PHARM = {
    'start': 'Process drop-off',
    'pools': {
        'Pharmacy System': (1, range(5), H(8), H(20)),
        'Technician': (8, range(5), H(8), H(20)),
        'Pharmacist': (1, range(5), H(8), H(20)),
    },
    'nodes': {
        'Process drop-off': ('act', 'Technician', 'W1'),
        'W1': ('wait', 'Enter prescription details'),
        'Enter prescription details': ('act', 'Technician', 'Check if refill is allowed'),
        'Check if refill is allowed': ('act', 'Pharmacy System', 'D1'),
        'D1': ('dec', [('D1-a', '0.94', 'Check DUR'), ('D1-b', '0.06', 'Contact Doctor about refill')]),
        'Contact Doctor about refill': ('act', 'Technician', 'D2'),
        'D2': ('dec', [('D2-a', '0.99', 'Check DUR'), ('D2-b', '0.01', 'End')]),
        'Check DUR': ('act', 'Pharmacy System', 'D3'),
        'D3': ('dec', [('D3-a', '0.8', 'Check Insurance'), ('D3-b', '0.2', 'D4')]),
        'D4': ('dec', [('D4-a', '0.95', 'Resolve DUR manually'), ('D4-b', '0.05', 'Contact customer / doctor')]),
        'Check Insurance': ('act', 'Pharmacy System', 'D5'),
        'Contact customer / doctor': ('act', 'Pharmacy System', 'Check Insurance'),
        'Resolve DUR manually': ('act', 'Pharmacist', 'Check Insurance'),
        'D5': ('dec', [('D5-a', '0.83', 'D6'), ('D5-b', '0.17', 'Resolve insurance issues manually')]),
        'Resolve insurance issues manually': ('act', 'Technician', 'D6'),
        'D6': ('dec', [('D6-a', '0.07', 'W3'), ('D6-b', '0.93', 'W2')]),
        'W2': ('wait', 'Pack the drugs (Production)'),
        'Pack the drugs (Production)': ('act', 'Technician', 'Check for Quality Assurance'),
        'W3': ('wait', 'Pick-up'),
        'Check for Quality Assurance': ('act', 'Pharmacist', 'D7'),
        'Pick-up': ('act', 'Technician', 'End'),
        'D7': ('dec', [('D7-a', '0.05', 'D6'), ('D7-b', '0.95', 'W3')]),
        'End': ('end',),
    },
}
MODELS = {'loan': LOAN, 'pharmacy': PHARM}

# ---------------- working-time arithmetic ----------------
class Shift:
    def __init__(self, days, op, cl, unavail=()):
        self.days, self.op, self.cl = set(days), op, cl
        self.unavail = sorted(unavail)  # list of (a,b) non-working intervals

    def _base_next(self, t):
        """first t' >= t inside base working hours; return (t', close of that interval)"""
        while True:
            d = t // DAY
            if (d % 7) in self.days:
                o, c = d * DAY + self.op, d * DAY + self.cl
                if t < o:
                    t = o
                if t < c:
                    return t, c
            t = (d + 1) * DAY

    def next_interval(self, t):
        """first working instant >= t and the end of the working stretch containing it"""
        while True:
            t, c = self._base_next(t)
            moved = False
            for a, b in self.unavail:
                if a <= t < b:
                    t = b; moved = True; break
                if t < a < c:
                    c = a
            if not moved:
                return t, c

    def finish(self, start, work):
        t, c = self.next_interval(start)
        rem = work
        while True:
            if rem <= c - t:
                return t + rem
            rem -= c - t
            t, c = self.next_interval(c)

# ---------------- parsing ----------------
ROW = re.compile(r'^c\d{4} ')

def parse_chapter(path):
    secs = {}
    cur = None
    for raw in open(path, encoding='utf-8'):
        line = raw.rstrip('\n').strip()
        if not line:
            continue
        m = re.match(r'^Run \d+: (.+)$', line)
        if m:
            cur = m.group(1); secs[cur] = []; continue
        if cur is None or line.startswith('case '):
            continue
        if ROW.match(line):
            secs[cur].append(line)
        else:
            secs[cur][-1] += ' ' + line  # continuation of a split row
    out = {}
    cases = {}
    for l in secs['Cases']:
        c, a, e = l.split()
        cases[c] = (int(a), int(e))
    out['cases'] = cases

    def plan(lines):
        d, order = {}, []
        for l in lines:
            toks = l.split()
            c = toks[0]
            vals = []
            while toks and re.fullmatch(r'\d+(\.\d+)?', toks[-1]):
                vals.insert(0, toks.pop())
            name = ' '.join(toks[1:])
            d[(c, name)] = vals
            if name not in order:
                order.append(name)
        return d, order
    w, order = plan(secs['Work plan'])
    out['work'] = {k: [int(x) for x in v] for k, v in w.items()}
    out['act_order'] = order
    wt, _ = plan(secs['Wait plan'])
    out['waits'] = {k: [int(x) for x in v] for k, v in wt.items()}
    dr, _ = plan(secs['Route draws'])
    out['draws'] = {k: list(v) for k, v in dr.items()}
    tl = []
    for l in secs['Task log']:
        m = re.match(r'^(c\d{4}) (.+?) (\d+) (\d+) (\d+) (\d+) ([A-Za-z ]+_\d+)$', l)
        assert m, l
        tl.append((m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6)), m.group(7)))
    out['task_log'] = tl
    wl = []
    for l in secs['Wait log']:
        c, wn, v, s, e = l.split()
        wl.append((c, wn, int(v), int(s), int(e)))
    out['wait_log'] = wl
    dl = []
    for l in secs['Decision log']:
        c, dn, v, t, r = l.split()
        dl.append((c, dn, int(v), int(t), r))
    out['dec_log'] = dl
    return out

# ---------------- simulation ----------------
def simulate(model, ch, prob_override=None, extra_workers=None):
    """ch: parsed chapter inputs (cases, work, waits, draws, act_order). Returns logs and case ends."""
    nodes = model['nodes']
    prob_override = prob_override or {}
    extra_workers = extra_workers or {}
    actid = {a: i for i, a in enumerate(ch['act_order'])}
    # workers
    workers = {}
    for p, (n, days, op, cl) in model['pools'].items():
        n += extra_workers.get(p, 0)
        workers[p] = [{'name': f'{p}_{i}', 'idx': i, 'free': 0, 'shift': Shift(days, op, cl)} for i in range(n)]
    arrival = {c: ae[0] for c, ae in ch['cases'].items()}
    visits = {}
    joins = {}
    tokens = {}
    ends = {}
    task_log, wait_log, dec_log = [], [], []
    ev = []  # (time, seq, case, node)
    seq = [0]

    def push(t, c, node):
        seq[0] += 1
        heapq.heappush(ev, (t, seq[0], c, node))

    pending = []

    def reach(t, c, node):
        kind = nodes[node][0]
        if kind == 'end':
            tokens[c] -= 1
            if tokens[c] == 0:
                ends[c] = t
            return
        if kind == 'split':
            tokens[c] += len(nodes[node][1]) - 1
            for tg in nodes[node][1]:
                reach(t, c, tg)
            return
        if kind == 'join':
            k = (c, node)
            joins[k] = joins.get(k, 0) + 1
            tokens[c] -= 1
            if joins[k] == nodes[node][1]:
                joins[k] = 0
                tokens[c] += 1
                reach(t, c, nodes[node][2])
            return
        vk = (c, node)
        visits[vk] = visits.get(vk, 0) + 1
        v = visits[vk]
        if kind == 'dec':
            routes = nodes[node][1]
            probs = prob_override.get(node)
            draw = F(ch['draws'][(c, node)][v - 1])
            run = F(0)
            chosen = None
            for i, (rn, p, tg) in enumerate(routes):
                run += F(probs[i] if probs else p)
                if run > draw:
                    chosen = (rn, tg); break
            assert chosen, (c, node, v)
            dec_log.append((c, node, v, t, chosen[0]))
            reach(t, c, chosen[1])
            return
        if kind == 'wait':
            d = ch['waits'][(c, node)][v - 1]
            wait_log.append((c, node, v, t, t + d))
            push(t + d, c, nodes[node][1])
            return
        if kind == 'act':
            pending.append((t, arrival[c], c, actid[node], v, node))
            return

    for c, a in arrival.items():
        tokens[c] = 1
        push(a, c, model['start'])

    while ev:
        t = ev[0][0]
        while ev and ev[0][0] == t:
            _, _, c, node = heapq.heappop(ev)
            reach(t, c, node)
        pending.sort()
        for (en, _, c, _, v, node) in pending:
            pool = nodes[node][1]
            w = ch['work'][(c, node)][v - 1]
            best = None
            for wk in workers[pool]:
                st, _ = wk['shift'].next_interval(max(en, wk['free']))
                key = (st, wk['free'], wk['idx'])
                if best is None or key < best[0]:
                    best = (key, wk)
            (st, _, _), wk = best
            end = wk['shift'].finish(st, w)
            wk['free'] = end
            task_log.append((c, node, v, en, st, end, wk['name']))
            push(end, c, nodes[node][2])
        pending.clear()
    return {'ends': ends, 'task_log': task_log, 'wait_log': wait_log, 'dec_log': dec_log}


def compare(ch, res):
    diffs = []
    for c, (a, e) in ch['cases'].items():
        if res['ends'].get(c) != e:
            diffs.append(f'case {c} end printed {e} sim {res["ends"].get(c)}')
    for name in ('task_log', 'wait_log', 'dec_log'):
        P = sorted(ch[name]); S = sorted(res[name])
        sp, ss = set(P), set(S)
        for r in P:
            if r not in ss:
                diffs.append(f'{name} printed-only {r}')
        for r in S:
            if r not in sp:
                diffs.append(f'{name} sim-only {r}')
        if len(P) != len(S):
            diffs.append(f'{name} row count printed {len(P)} sim {len(S)}')
    return diffs
