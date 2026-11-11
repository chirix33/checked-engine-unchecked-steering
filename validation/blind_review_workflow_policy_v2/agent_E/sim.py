"""Own simulator for the blind check. Standard library only.

Rules implemented from the front matters (Process sections are identical between the
policyP and policyH documents of each process; worker counts differ and are parsed per document).
"""
import re, heapq, copy
from fractions import Fraction

DAY = 86400
WEEK = 7 * DAY

# ---------------------------------------------------------------- front matter

def parse_front_matter(fn):
    t = re.sub(r'\s+', ' ', open(fn, encoding='utf-8').read())
    w = t[t.index('Workers.'):t.index('Process.')]
    pools = {}
    for m in re.finditer(r'([A-Z][A-Za-z ]*?): (\d+) workers \((.+?)_0 to .+?_(\d+)\), working (\w+) to (\w+) (\d\d):(\d\d) to (\d\d):(\d\d)', w):
        name, n, pref, last, d0, d1, h0, m0, h1, m1 = m.groups()
        name = name.strip()
        # strip leading sentence words such as 'Workers.' handled by regex start
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        assert int(last) == int(n) - 1, (name, n, last)
        pools[name] = dict(n=int(n), days=list(range(days.index(d0), days.index(d1) + 1)),
                           open=int(h0) * 3600 + int(m0) * 60, close=int(h1) * 3600 + int(m1) * 60)
    return pools

# ---------------------------------------------------------------- process models
# node kinds: ('task', pool, next) ('wait', next) ('dec', [(route, prob, target)]) ('split', [targets]) ('join', n, next) ('end',)

LOAN = {
    'START': 'Check application form completeness',
    'Check application form completeness': ('task', 'Clerk', 'D1'),
    'D1': ('dec', [('D1-a', '0.2', 'Return application back to applicant'), ('D1-b', '0.8', 'S1')]),
    'Return application back to applicant': ('task', 'Clerk', 'W1'),
    'S1': ('split', ['Appraise property', 'Check credit history', 'AML Check']),
    'W1': ('wait', 'Applicant completes form'),
    'Appraise property': ('task', 'Appraiser', 'J1'),
    'AML Check': ('task', 'AML Investigator', 'J1'),
    'Check credit history': ('task', 'Clerk', 'J1'),
    'Applicant completes form': ('task', 'Applicant', 'Check application form completeness'),
    'J1': ('join', 3, 'W2'),
    'W2': ('wait', 'Assess loan risk'),
    'Assess loan risk': ('task', 'Loan Officer', 'D2'),
    'D2': ('dec', [('D2-a', '0.5', 'Reject application'), ('D2-b', '0.5', 'Design loan offer')]),
    'Reject application': ('task', 'Clerk', 'END'),
    'Design loan offer': ('task', 'Loan Officer', 'Approve Loan Offer'),
    'Approve Loan Offer': ('task', 'Senior Officer', 'D3'),
    'D3': ('dec', [('D3-a', '0.2', 'Design loan offer'), ('D3-b', '0.8', 'S2')]),
    'S2': ('split', ['Prepare acceptance pack', 'Prepare home insurance quote']),
    'Prepare acceptance pack': ('task', 'Loan Officer', 'Approve and send acceptance pack'),
    'Prepare home insurance quote': ('task', 'Clerk', 'Approve and post home insurance quote'),
    'Approve and send acceptance pack': ('task', 'Loan Officer', 'J2'),
    'Approve and post home insurance quote': ('task', 'Loan Officer', 'J2'),
    'J2': ('join', 2, 'D4'),
    'D4': ('dec', [('D4-a', '0.5', 'W3'), ('D4-b', '0.5', 'Consider re-design loan offer')]),
    'Consider re-design loan offer': ('task', 'Senior Officer', 'D5'),
    'W3': ('wait', 'Approve application'),
    'D5': ('dec', [('D5-a', '0.45', 'Cancel application'), ('D5-b', '0.55', 'Design loan offer')]),
    'Approve application': ('task', 'Clerk', 'END'),
    'Cancel application': ('task', 'Clerk', 'END'),
    'END': ('end',),
}

PHARM = {
    'START': 'Process drop-off',
    'Process drop-off': ('task', 'Technician', 'W1'),
    'W1': ('wait', 'Enter prescription details'),
    'Enter prescription details': ('task', 'Technician', 'Check if refill is allowed'),
    'Check if refill is allowed': ('task', 'Pharmacy System', 'D1'),
    'D1': ('dec', [('D1-a', '0.94', 'Check DUR'), ('D1-b', '0.06', 'Contact Doctor about refill')]),
    'Contact Doctor about refill': ('task', 'Technician', 'D2'),
    'D2': ('dec', [('D2-a', '0.99', 'Check DUR'), ('D2-b', '0.01', 'END')]),
    'Check DUR': ('task', 'Pharmacy System', 'D3'),
    'D3': ('dec', [('D3-a', '0.8', 'Check Insurance'), ('D3-b', '0.2', 'D4')]),
    'D4': ('dec', [('D4-a', '0.95', 'Resolve DUR manually'), ('D4-b', '0.05', 'Contact customer / doctor')]),
    'Check Insurance': ('task', 'Pharmacy System', 'D5'),
    'Contact customer / doctor': ('task', 'Pharmacy System', 'Check Insurance'),
    'Resolve DUR manually': ('task', 'Pharmacist', 'Check Insurance'),
    'D5': ('dec', [('D5-a', '0.83', 'D6'), ('D5-b', '0.17', 'Resolve insurance issues manually')]),
    'Resolve insurance issues manually': ('task', 'Technician', 'D6'),
    'D6': ('dec', [('D6-a', '0.07', 'W3'), ('D6-b', '0.93', 'W2')]),
    'W2': ('wait', 'Pack the drugs (Production)'),
    'Pack the drugs (Production)': ('task', 'Technician', 'Check for Quality Assurance'),
    'W3': ('wait', 'Pick-up'),
    'Check for Quality Assurance': ('task', 'Pharmacist', 'D7'),
    'Pick-up': ('task', 'Technician', 'END'),
    'D7': ('dec', [('D7-a', '0.05', 'D6'), ('D7-b', '0.95', 'W3')]),
    'END': ('end',),
}

# ---------------------------------------------------------------- chapter parsing

def parse_chapter(fn):
    lines = open(fn, encoding='utf-8').read().splitlines()
    secs = {}
    cur = None
    for ln in lines:
        m = re.match(r'Run \d+: (.+)$', ln)
        if m:
            cur = m.group(1); secs[cur] = []; continue
        if cur is None or ln.startswith('case '):
            continue
        secs[cur].append(ln)
    ch = {}
    ch['cases'] = {}
    order = []
    for ln in secs['Cases']:
        c, a, e = ln.split()
        ch['cases'][c] = (int(a), int(e)); order.append(c)
    ch['case_order'] = order

    def rows(seclines):
        # join continuation lines: a row starts with a case id
        out = []
        for ln in seclines:
            if re.match(r'c\d{4} ', ln):
                out.append(ln)
            else:
                out[-1] += ' ' + ln
        return out

    work = {}
    act_order = []
    for r in rows(secs['Work plan']):
        toks = r.split()
        c = toks[0]
        i = len(toks)
        while re.fullmatch(r'\d+', toks[i - 1]):
            i -= 1
        act = ' '.join(toks[1:i])
        vals = [int(x) for x in toks[i:]]
        work[(c, act)] = vals
        if act not in act_order:
            act_order.append(act)
    ch['work'] = work
    ch['act_order'] = act_order
    # check activity order consistent per case
    for c in order:
        seq = [a for (cc, a) in work if cc == c]
        assert seq == act_order, (fn, c, seq)
    wait = {}
    for r in rows(secs['Wait plan']):
        toks = r.split()
        wait[(toks[0], toks[1])] = [int(x) for x in toks[2:]]
    ch['wait'] = wait
    draws = {}
    for r in rows(secs['Route draws']):
        toks = r.split()
        draws[(toks[0], toks[1])] = [Fraction(x) for x in toks[2:]]
    ch['draws'] = draws
    tl = []
    for r in rows(secs['Task log']):
        m = re.fullmatch(r'(c\d{4}) (.+?) (\d+) (\d+) (\d+) (\d+) ([A-Za-z ]+_\d+)', r.strip())
        assert m, r
        c, a, v, en, st, e, w = m.groups()
        tl.append((c, a, int(v), int(en), int(st), int(e), w))
    ch['task_log'] = tl
    wl = []
    for r in rows(secs['Wait log']):
        c, w, v, s, e = r.split()
        wl.append((c, w, int(v), int(s), int(e)))
    ch['wait_log'] = wl
    dl = []
    for r in rows(secs['Decision log']):
        c, d, v, t, rt = r.split()
        dl.append((c, d, int(v), int(t), rt))
    ch['dec_log'] = dl
    return ch

# ---------------------------------------------------------------- calendars

class Calendar:
    def __init__(self, days, open_s, close_s, unavail=()):
        self.days = set(days); self.o = open_s; self.c = close_s
        self.unavail = sorted(unavail)

    def _base_intervals(self, t):
        """yield weekly working intervals [a,b) with b > t, in time order."""
        d = t // DAY
        while True:
            if (d % 7) in self.days:
                a, b = d * DAY + self.o, d * DAY + self.c
                if b > t:
                    yield (a, b)
            d += 1

    def intervals(self, t):
        for a, b in self._base_intervals(t):
            segs = [(a, b)]
            for u0, u1 in self.unavail:
                ns = []
                for s, e in segs:
                    if u1 <= s or u0 >= e:
                        ns.append((s, e))
                    else:
                        if s < u0: ns.append((s, u0))
                        if u1 < e: ns.append((u1, e))
                segs = ns
            for s, e in segs:
                if e > t:
                    yield (max(s, t), e)

    def next_start(self, t):
        for s, e in self.intervals(t):
            return s

    def finish(self, start, work):
        """start is a working instant. Return end time after `work` working seconds."""
        if work == 0:
            return start
        rem = work
        for s, e in self.intervals(start):
            if e - s >= rem:
                return s + rem
            rem -= (e - s)

# ---------------------------------------------------------------- simulation

def simulate(model, pools_spec, ch, changes=None):
    changes = changes or {}
    work = copy.deepcopy(ch['work'])
    wait = copy.deepcopy(ch['wait'])
    draws = copy.deepcopy(ch['draws'])
    cases = dict(ch['cases'])
    for c in changes.get('remove_cases', []):
        del cases[c]
    for (c, act, v), val in changes.get('work', {}).items():
        lst = work[(c, act)]
        while len(lst) < v: lst.append(None)
        lst[v - 1] = val
    for (c, w, v), val in changes.get('wait', {}).items():
        lst = wait[(c, w)]
        while len(lst) < v: lst.append(None)
        lst[v - 1] = val
    for (c, d, v), val in changes.get('draw', {}).items():
        lst = draws[(c, d)]
        while len(lst) < v: lst.append(None)
        lst[v - 1] = Fraction(val)
    model = dict(model)
    for d, probs in changes.get('probs', {}).items():
        routes = model[d][1]
        model[d] = ('dec', [(r, probs[r], tgt) for (r, p, tgt) in routes])
    act_id = {a: i for i, a in enumerate(ch['act_order'])}

    # workers
    workers = {}
    for pool, sp in pools_spec.items():
        n = sp['n'] + changes.get('extra_workers', {}).get(pool, 0)
        lst = []
        for i in range(n):
            name = f'{pool}_{i}'
            un = changes.get('unavail', {}).get(name, [])
            lst.append({'name': name, 'cal': Calendar(sp['days'], sp['open'], sp['close'], un), 'free': -1, 'idx': i})
        workers[pool] = lst

    visits = {c: {} for c in cases}
    joins = {c: {} for c in cases}
    live = {c: 0 for c in cases}
    end = {}
    task_log, wait_log, dec_log = [], [], []
    heap = []
    errors = []

    def reach(c, node, t):
        kind = model[node]
        if node == 'END':
            live[c] -= 1
            if live[c] == 0:
                end[c] = t
            return
        k = kind[0]
        if k in ('task', 'wait', 'dec'):
            visits[c][node] = visits[c].get(node, 0) + 1
            v = visits[c][node]
        if k == 'task':
            heapq.heappush(heap, (t, cases[c][0], c, act_id[node], v, node))
        elif k == 'wait':
            lst = wait[(c, node)]
            d = lst[v - 1] if v <= len(lst) else None
            if d is None:
                errors.append(f'missing wait plan {c} {node} visit {v}'); d = 0
            wait_log.append((c, node, v, t, t + d))
            reach(c, kind[1], t + d)
        elif k == 'dec':
            lst = draws[(c, node)]
            x = lst[v - 1] if v <= len(lst) else None
            if x is None:
                errors.append(f'missing draw {c} {node} visit {v}'); x = Fraction(0)
            tot = Fraction(0); chosen = None
            for r, p, tgt in kind[1]:
                tot += Fraction(p)
                if tot > x:
                    chosen = (r, tgt); break
            if chosen is None:
                chosen = (kind[1][-1][0], kind[1][-1][2]); errors.append(f'no route {c} {node}')
            dec_log.append((c, node, v, t, chosen[0]))
            reach(c, chosen[1], t)
        elif k == 'split':
            live[c] += len(kind[1]) - 1
            for tgt in kind[1]:
                reach(c, tgt, t)
        elif k == 'join':
            st = joins[c].setdefault(node, [0, t])
            st[0] += 1; st[1] = max(st[1], t)
            if st[0] == kind[1]:
                tt = st[1]
                del joins[c][node]
                live[c] -= kind[1] - 1
                reach(c, kind[2], tt)

    for c in sorted(cases, key=lambda c: (cases[c][0], c)):
        live[c] = 1
        reach(c, model['START'], cases[c][0])

    last_key = [(-1,)]
    while heap:
        t, arr, c, aid, v, node = heapq.heappop(heap)
        if (t, arr, c, aid, v) < last_key[0]:
            errors.append(f'order violation {c} {node} {v} at {t}')
        last_key[0] = (t, arr, c, aid, v)
        pool = model[node][1]
        lst = work[(c, node)]
        wk = lst[v - 1] if v <= len(lst) else None
        if wk is None:
            errors.append(f'missing work plan {c} {node} visit {v}'); wk = 0
        best = None
        for w in workers[pool]:
            s = w['cal'].next_start(max(t, w['free']))
            key = (s, w['free'], w['idx'])
            if best is None or key < best[0]:
                best = (key, w)
        s = best[0][0]; w = best[1]
        e = w['cal'].finish(s, wk)
        w['free'] = e
        task_log.append((c, node, v, t, s, e, w['name']))
        reach(c, model[node][2], e)

    return dict(end=end, task_log=task_log, wait_log=wait_log, dec_log=dec_log, errors=errors)


def compare(ch, res):
    diffs = []
    for c, (a, e) in ch['cases'].items():
        if res['end'].get(c) != e:
            diffs.append(f'case end {c}: printed {e} sim {res["end"].get(c)}')
    for name, key in (('task_log', 'task_log'), ('wait_log', 'wait_log'), ('dec_log', 'dec_log')):
        A = sorted(ch[key]); B = sorted(res[key])
        if A != B:
            sa, sb = set(A), set(B)
            for x in sorted(sa - sb)[:10]: diffs.append(f'{name} printed-only {x}')
            for x in sorted(sb - sa)[:10]: diffs.append(f'{name} sim-only {x}')
            if len(A) != len(B): diffs.append(f'{name} row count printed {len(A)} sim {len(B)}')
    return diffs
