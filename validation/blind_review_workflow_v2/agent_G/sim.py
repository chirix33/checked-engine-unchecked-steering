"""Simulator for the Loan Application and Pharmacy processes, written from the
front-matter rules only. Standard library only."""
import heapq
import json
import re
import sys

DAY = 86400

# ---------------------------------------------------------------- models
# node kinds: ('act', name, next), ('wait', name, next),
# ('dec', name, [(route, prob, next), ...]), ('split', [next...]),
# ('join', name, n, next), ('end',)

LOAN = {
    'pools': {
        'Applicant': (20, list(range(7)), 0, DAY - 60),  # 00:00 to 23:59 -> [0, 86340)
        'Senior Officer': (3, [0, 1, 2, 3, 4], 9 * 3600, 17 * 3600),
        'Appraiser': (2, [0, 1, 2, 3, 4], 9 * 3600, 17 * 3600),
        'AML Investigator': (4, [0, 1, 2, 3, 4], 9 * 3600, 17 * 3600),
        'Loan Officer': (9, [0, 1, 2, 3, 4], 9 * 3600, 17 * 3600),
        'Clerk': (9, [0, 1, 2, 3, 4], 9 * 3600, 17 * 3600),
    },
    'acts': {
        'Check application form completeness': ('Clerk', 'D1'),
        'Return application back to applicant': ('Clerk', 'W1'),
        'Appraise property': ('Appraiser', 'J1'),
        'AML Check': ('AML Investigator', 'J1'),
        'Check credit history': ('Clerk', 'J1'),
        'Applicant completes form': ('Applicant', 'Check application form completeness'),
        'Assess loan risk': ('Loan Officer', 'D2'),
        'Reject application': ('Clerk', 'END'),
        'Design loan offer': ('Loan Officer', 'Approve Loan Offer'),
        'Approve Loan Offer': ('Senior Officer', 'D3'),
        'Prepare acceptance pack': ('Loan Officer', 'Approve and send acceptance pack'),
        'Prepare home insurance quote': ('Clerk', 'Approve and post home insurance quote'),
        'Approve and send acceptance pack': ('Loan Officer', 'J2'),
        'Approve and post home insurance quote': ('Loan Officer', 'J2'),
        'Consider re-design loan offer': ('Senior Officer', 'D5'),
        'Approve application': ('Clerk', 'END'),
        'Cancel application': ('Clerk', 'END'),
    },
    'waits': {'W1': 'Applicant completes form', 'W2': 'Assess loan risk',
              'W3': 'Approve application'},
    'decs': {
        'D1': [('D1-a', 0.2, 'Return application back to applicant'), ('D1-b', 0.8, 'S1')],
        'D2': [('D2-a', 0.5, 'Reject application'), ('D2-b', 0.5, 'Design loan offer')],
        'D3': [('D3-a', 0.2, 'Design loan offer'), ('D3-b', 0.8, 'S2')],
        'D4': [('D4-a', 0.5, 'W3'), ('D4-b', 0.5, 'Consider re-design loan offer')],
        'D5': [('D5-a', 0.45, 'Cancel application'), ('D5-b', 0.55, 'Design loan offer')],
    },
    'splits': {'S1': ['Appraise property', 'Check credit history', 'AML Check'],
               'S2': ['Prepare acceptance pack', 'Prepare home insurance quote']},
    'joins': {'J1': (3, 'W2'), 'J2': (2, 'D4')},
    'start': 'Check application form completeness',
}

PHARM = {
    'pools': {
        'Pharmacy System': (1, [0, 1, 2, 3, 4], 8 * 3600, 20 * 3600),
        'Technician': (8, [0, 1, 2, 3, 4], 8 * 3600, 20 * 3600),
        'Pharmacist': (1, [0, 1, 2, 3, 4], 8 * 3600, 20 * 3600),
    },
    'acts': {
        'Process drop-off': ('Technician', 'W1'),
        'Enter prescription details': ('Technician', 'Check if refill is allowed'),
        'Check if refill is allowed': ('Pharmacy System', 'D1'),
        'Contact Doctor about refill': ('Technician', 'D2'),
        'Check DUR': ('Pharmacy System', 'D3'),
        'Check Insurance': ('Pharmacy System', 'D5'),
        'Contact customer / doctor': ('Pharmacy System', 'Check Insurance'),
        'Resolve DUR manually': ('Pharmacist', 'Check Insurance'),
        'Resolve insurance issues manually': ('Technician', 'D6'),
        'Pack the drugs (Production)': ('Technician', 'Check for Quality Assurance'),
        'Check for Quality Assurance': ('Pharmacist', 'D7'),
        'Pick-up': ('Technician', 'END'),
    },
    'waits': {'W1': 'Enter prescription details', 'W2': 'Pack the drugs (Production)',
              'W3': 'Pick-up'},
    'decs': {
        'D1': [('D1-a', 0.94, 'Check DUR'), ('D1-b', 0.06, 'Contact Doctor about refill')],
        'D2': [('D2-a', 0.99, 'Check DUR'), ('D2-b', 0.01, 'END')],
        'D3': [('D3-a', 0.8, 'Check Insurance'), ('D3-b', 0.2, 'D4')],
        'D4': [('D4-a', 0.95, 'Resolve DUR manually'), ('D4-b', 0.05, 'Contact customer / doctor')],
        'D5': [('D5-a', 0.83, 'D6'), ('D5-b', 0.17, 'Resolve insurance issues manually')],
        'D6': [('D6-a', 0.07, 'W3'), ('D6-b', 0.93, 'W2')],
        'D7': [('D7-a', 0.05, 'D6'), ('D7-b', 0.95, 'W3')],
    },
    'splits': {},
    'joins': {},
    'start': 'Process drop-off',
}

MODELS = {'loan': LOAN, 'pharmacy': PHARM}


# ---------------------------------------------------------------- parsing
def parse_chapter(path, model):
    lines = open(path, encoding='utf-8').read().splitlines()
    sections = {}
    cur = None
    for ln in lines:
        m = re.match(r'^Run \d+: (.+)$', ln.strip())
        if m:
            cur = m.group(1)
            sections[cur] = []
            continue
        if cur is None:
            continue
        if ln.startswith('case '):
            continue  # header (repeated at page breaks)
        sections[cur].append(ln.strip())
    names = sorted(model['acts'], key=len, reverse=True)
    namere = '|'.join(re.escape(n) for n in names)

    def stream(sec):
        return ' '.join(sections[sec]) + ' '

    ch = {}
    cases = {}
    for m in re.finditer(r'(c\d{4}) (\d+) (\d+) ', stream('Cases')):
        cases[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    ch['cases'] = cases
    work = {}
    act_order = []
    for m in re.finditer(r'(c\d{4}) (' + namere + r')((?: \d+)+)(?= |$)', stream('Work plan')):
        c, a = m.group(1), m.group(2)
        vals = [int(x) for x in m.group(3).split()]
        work[(c, a)] = vals
        if a not in act_order:
            act_order.append(a)
    ch['work'] = work
    ch['act_order'] = act_order
    waits = {}
    for m in re.finditer(r'(c\d{4}) (W\d+)((?: \d+)+)(?= |$)', stream('Wait plan')):
        waits[(m.group(1), m.group(2))] = [int(x) for x in m.group(3).split()]
    ch['waitplan'] = waits
    draws = {}
    for m in re.finditer(r'(c\d{4}) (D\d+)((?: [01]\.\d{6})+)(?= |$)', stream('Route draws')):
        draws[(m.group(1), m.group(2))] = [float(x) for x in m.group(3).split()]
    ch['draws'] = draws
    tl = []
    for m in re.finditer(r'(c\d{4}) (' + namere + r') (\d+) (\d+) (\d+) (\d+) ([A-Za-z ]+?_\d+)(?= |$)',
                         stream('Task log')):
        tl.append((m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5)),
                   int(m.group(6)), m.group(7)))
    ch['tasklog'] = tl
    wl = []
    for m in re.finditer(r'(c\d{4}) (W\d+) (\d+) (\d+) (\d+)(?= |$)', stream('Wait log')):
        wl.append((m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5))))
    ch['waitlog'] = wl
    dl = []
    for m in re.finditer(r'(c\d{4}) (D\d+) (\d+) (\d+) (D\d+-[a-z])(?= |$)', stream('Decision log')):
        dl.append((m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), m.group(5)))
    ch['declog'] = dl
    # sanity counts: number of data rows per section vs parsed
    ch['_raw'] = {k: len(v) for k, v in sections.items()}
    return ch


# ---------------------------------------------------------------- calendars
class Calendar:
    """Working intervals for one worker: weekly schedule minus unavailable intervals."""

    def __init__(self, days, open_s, close_s, unavail=()):
        self.days = set(days)
        self.open = open_s
        self.close = close_s
        self.unavail = sorted(unavail)
        self._cache = None

    def intervals(self, horizon_days=400):
        if self._cache is None:
            ivs = []
            for d in range(horizon_days):
                if d % 7 in self.days:
                    a, b = d * DAY + self.open, d * DAY + self.close
                    if ivs and ivs[-1][1] == a:
                        ivs[-1] = (ivs[-1][0], b)
                    else:
                        ivs.append((a, b))
            for (ua, ub) in self.unavail:
                new = []
                for (a, b) in ivs:
                    if ub <= a or ua >= b:
                        new.append((a, b))
                    else:
                        if a < ua:
                            new.append((a, ua))
                        if ub < b:
                            new.append((ub, b))
                ivs = new
            self._cache = ivs
        return self._cache

    def next_start(self, t):
        for (a, b) in self.intervals():
            if t < b:
                return max(t, a)
        raise RuntimeError('horizon')

    def finish(self, start, work):
        rem = work
        t = start
        for (a, b) in self.intervals():
            if t >= b:
                continue
            t = max(t, a)
            avail = b - t
            if rem <= avail:
                return t + rem
            rem -= avail
            t = b
        raise RuntimeError('horizon')


# ---------------------------------------------------------------- simulation
def simulate(model, ch, changes=None):
    changes = changes or {}
    work = {k: list(v) for k, v in ch['work'].items()}
    waitplan = {k: list(v) for k, v in ch['waitplan'].items()}
    draws = {k: list(v) for k, v in ch['draws'].items()}
    decs = {k: list(v) for k, v in model['decs'].items()}
    for (c, a, v, val) in changes.get('work', []):
        work[(c, a)][v - 1] = val
    for (c, w, v, val) in changes.get('wait', []):
        waitplan[(c, w)][v - 1] = val
    for (c, d, v, val) in changes.get('draw', []):
        draws[(c, d)][v - 1] = val
    for (d, probs) in changes.get('probs', []):
        decs[d] = [(r, probs[r], nxt) for (r, p, nxt) in decs[d]]
    removed = set(changes.get('remove', []))
    unavail = changes.get('unavail', {})  # pool -> list of (worker_index, a, b)

    cases = {c: v[0] for c, v in ch['cases'].items() if c not in removed}
    act_id = {a: i for i, a in enumerate(ch['act_order'])}

    workers = {}  # pool -> list of dict
    for pool, (n, days, o, cl) in model['pools'].items():
        lst = []
        for i in range(n):
            ua = [(a, b) for (wi, a, b) in unavail.get(pool, []) if wi == i]
            lst.append({'name': f'{pool}_{i}', 'free': 0, 'cal': Calendar(days, o, cl, ua)})
        workers[pool] = lst

    queues = {p: [] for p in model['pools']}
    events = []  # (time, seq, kind, data)
    seq = [0]

    def push(t, kind, data):
        seq[0] += 1
        heapq.heappush(events, (t, seq[0], kind, data))

    visits = {}
    joins = {}
    active = {}
    tasklog, waitlog, declog = [], [], []
    ends = {}

    def nextvisit(c, key):
        visits[(c, key)] = visits.get((c, key), 0) + 1
        return visits[(c, key)]

    def reach(c, node, t):
        if node == 'END':
            active[c] -= 1
            if active[c] == 0:
                ends[c] = t
            return
        if node in model['acts']:
            v = nextvisit(c, node)
            pool = model['acts'][node][0]
            queues[pool].append((t, cases[c], c, act_id[node], v, node))
            return
        if node in model['waits']:
            v = nextvisit(c, node)
            d = waitplan[(c, node)][v - 1]
            waitlog.append((c, node, v, t, t + d))
            push(t + d, 'waitend', (c, node))
            return
        if node in decs:
            v = nextvisit(c, node)
            draw = draws[(c, node)][v - 1]
            tot = 0.0
            chosen = None
            for (r, p, nxt) in decs[node]:
                tot += p
                if tot > draw + 1e-12 * 0 and tot > draw:
                    chosen = (r, nxt)
                    break
            if chosen is None:
                chosen = (decs[node][-1][0], decs[node][-1][2])
            declog.append((c, node, v, t, chosen[0]))
            reach(c, chosen[1], t)
            return
        if node in model['splits']:
            outs = model['splits'][node]
            active[c] += len(outs) - 1
            for o in outs:
                reach(c, o, t)
            return
        if node in model['joins']:
            n, nxt = model['joins'][node]
            joins[(c, node)] = joins.get((c, node), 0) + 1
            if joins[(c, node)] == n:
                joins[(c, node)] = 0
                active[c] -= n - 1
                reach(c, nxt, t)
            return
        raise KeyError(node)

    for c, arr in cases.items():
        push(arr, 'arrive', c)

    def dispatch(t):
        for pool, q in queues.items():
            if not q:
                continue
            q.sort()
            while q:
                cands = [w for w in workers[pool]
                         if w['free'] <= t and w['cal'].next_start(t) == t]
                if not cands:
                    break
                cands.sort(key=lambda w: (w['free'], int(w['name'].rsplit('_', 1)[1])))
                w = cands[0]
                en, _, c, _, v, a = q.pop(0)
                wk = work[(c, a)][v - 1]
                e = w['cal'].finish(t, wk)
                w['free'] = e
                tasklog.append((c, a, v, en, t, e, w['name']))
                push(e, 'taskend', (c, a))

    def wake_time(t):
        best = None
        for pool, q in queues.items():
            if not q:
                continue
            for w in workers[pool]:
                s = w['cal'].next_start(max(t, w['free']))
                if best is None or s < best:
                    best = s
        return best

    t = None
    while True:
        nt = events[0][0] if events else None
        if t is not None:
            wt = wake_time(t + 1)
            # wake_time accounts for workers becoming free only via events, so only
            # opening-hour wake-ups matter; keep the earliest of both.
            if wt is not None and (nt is None or wt < nt):
                nt = wt
        if nt is None:
            break
        t = nt
        while events and events[0][0] == t:
            _, _, kind, data = heapq.heappop(events)
            if kind == 'arrive':
                active[data] = 1
                reach(data, model['start'], t)
            elif kind == 'taskend':
                c, a = data
                reach(c, model['acts'][a][1], t)
            elif kind == 'waitend':
                c, wname = data
                reach(c, model['waits'][wname], t)
        dispatch(t)
    return {'ends': ends, 'tasklog': tasklog, 'waitlog': waitlog, 'declog': declog}


def compare(ch, res):
    out = {}
    ends_rec = {c: v[1] for c, v in ch['cases'].items()}
    out['ends_mismatch'] = {c: (ends_rec[c], res['ends'].get(c)) for c in ends_rec
                            if res['ends'].get(c) != ends_rec[c]}
    for key in ('tasklog', 'waitlog', 'declog'):
        a = set(ch[key])
        b = set(res[key])
        out[key] = {'recorded': len(ch[key]), 'sim': len(res[key]),
                    'missing': sorted(a - b)[:10], 'extra': sorted(b - a)[:10]}
    out['exact'] = (not out['ends_mismatch'] and all(
        not out[k]['missing'] and not out[k]['extra'] and out[k]['recorded'] == out[k]['sim']
        for k in ('tasklog', 'waitlog', 'declog')))
    return out


if __name__ == '__main__':
    import glob
    for f in sorted(glob.glob('*_chapter_Run_*.txt')):
        proc = f.split('_')[0]
        model = MODELS[proc]
        ch = parse_chapter(f, model)
        res = simulate(model, ch)
        cmp = compare(ch, res)
        print(f, 'EXACT' if cmp['exact'] else 'DIFF', 'cases', len(ch['cases']),
              'tasks', cmp['tasklog']['recorded'], cmp['tasklog']['sim'],
              'waits', cmp['waitlog']['recorded'], cmp['waitlog']['sim'],
              'decs', cmp['declog']['recorded'], cmp['declog']['sim'])
        if not cmp['exact']:
            print(json.dumps(cmp, indent=1, default=str)[:3000])
