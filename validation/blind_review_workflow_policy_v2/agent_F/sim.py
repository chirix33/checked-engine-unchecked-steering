import re, json, heapq, sys
from fractions import Fraction

DAY = 86400

# ---------------- process models (transcribed from front matter; identical text in P and H) ----------------
def loan_model():
    A = {}  # activity -> (pool, next)
    A['Check application form completeness'] = ('Clerk', 'D1')
    A['Return application back to applicant'] = ('Clerk', 'W1')
    A['Appraise property'] = ('Appraiser', 'J1')
    A['AML Check'] = ('AML Investigator', 'J1')
    A['Check credit history'] = ('Clerk', 'J1')
    A['Applicant completes form'] = ('Applicant', 'Check application form completeness')
    A['Assess loan risk'] = ('Loan Officer', 'D2')
    A['Reject application'] = ('Clerk', 'End')
    A['Design loan offer'] = ('Loan Officer', 'Approve Loan Offer')
    A['Approve Loan Offer'] = ('Senior Officer', 'D3')
    A['Prepare acceptance pack'] = ('Loan Officer', 'Approve and send acceptance pack')
    A['Prepare home insurance quote'] = ('Clerk', 'Approve and post home insurance quote')
    A['Approve and send acceptance pack'] = ('Loan Officer', 'J2')
    A['Approve and post home insurance quote'] = ('Loan Officer', 'J2')
    A['Consider re-design loan offer'] = ('Senior Officer', 'D5')
    A['Approve application'] = ('Clerk', 'End')
    A['Cancel application'] = ('Clerk', 'End')
    W = {'W1': 'Applicant completes form', 'W2': 'Assess loan risk', 'W3': 'Approve application'}
    D = {'D1': [('D1-a', '0.2', 'Return application back to applicant'), ('D1-b', '0.8', 'S1')],
         'D2': [('D2-a', '0.5', 'Reject application'), ('D2-b', '0.5', 'Design loan offer')],
         'D3': [('D3-a', '0.2', 'Design loan offer'), ('D3-b', '0.8', 'S2')],
         'D4': [('D4-a', '0.5', 'W3'), ('D4-b', '0.5', 'Consider re-design loan offer')],
         'D5': [('D5-a', '0.45', 'Cancel application'), ('D5-b', '0.55', 'Design loan offer')]}
    S = {'S1': ['Appraise property', 'Check credit history', 'AML Check'],
         'S2': ['Prepare acceptance pack', 'Prepare home insurance quote']}
    J = {'J1': (3, 'W2'), 'J2': (2, 'D4')}
    return dict(start='Check application form completeness', A=A, W=W, D=D, S=S, J=J)

def pharm_model():
    A = {}
    A['Process drop-off'] = ('Technician', 'W1')
    A['Enter prescription details'] = ('Technician', 'Check if refill is allowed')
    A['Check if refill is allowed'] = ('Pharmacy System', 'D1')
    A['Contact Doctor about refill'] = ('Technician', 'D2')
    A['Check DUR'] = ('Pharmacy System', 'D3')
    A['Check Insurance'] = ('Pharmacy System', 'D5')
    A['Contact customer / doctor'] = ('Pharmacy System', 'Check Insurance')
    A['Resolve DUR manually'] = ('Pharmacist', 'Check Insurance')
    A['Resolve insurance issues manually'] = ('Technician', 'D6')
    A['Pack the drugs (Production)'] = ('Technician', 'Check for Quality Assurance')
    A['Check for Quality Assurance'] = ('Pharmacist', 'D7')
    A['Pick-up'] = ('Technician', 'End')
    W = {'W1': 'Enter prescription details', 'W2': 'Pack the drugs (Production)', 'W3': 'Pick-up'}
    D = {'D1': [('D1-a', '0.94', 'Check DUR'), ('D1-b', '0.06', 'Contact Doctor about refill')],
         'D2': [('D2-a', '0.99', 'Check DUR'), ('D2-b', '0.01', 'End')],
         'D3': [('D3-a', '0.8', 'Check Insurance'), ('D3-b', '0.2', 'D4')],
         'D4': [('D4-a', '0.95', 'Resolve DUR manually'), ('D4-b', '0.05', 'Contact customer / doctor')],
         'D5': [('D5-a', '0.83', 'D6'), ('D5-b', '0.17', 'Resolve insurance issues manually')],
         'D6': [('D6-a', '0.07', 'W3'), ('D6-b', '0.93', 'W2')],
         'D7': [('D7-a', '0.05', 'D6'), ('D7-b', '0.95', 'W3')]}
    return dict(start='Process drop-off', A=A, W=W, D=D, S={}, J={})

# ---------------- workers / calendars ----------------
APPLICANT_CLOSE = 23*3600 + 59*60   # literal reading; see notes

def doc_config(proc, doc):
    wk = set(range(5))
    if proc == 'loan':
        h = (9*3600, 17*3600)
        pools = {'Applicant': (20, set(range(7)), 0, APPLICANT_CLOSE),
                 'Senior Officer': (3, wk) + h, 'AML Investigator': (4, wk) + h,
                 'Loan Officer': (9, wk) + h, 'Clerk': (9, wk) + h}
        pools['Appraiser'] = ((3 if doc == 'policyP' else 2), wk) + h
    else:
        h = (8*3600, 20*3600)
        pools = {'Pharmacy System': (1, wk) + h, 'Technician': (8, wk) + h}
        pools['Pharmacist'] = ((2 if doc == 'policyP' else 1), wk) + h
    return pools

class Worker:
    def __init__(self, name, days, op, cl):
        self.name = name; self.days = days; self.op = op; self.cl = cl
        self.unavail = []; self.free = 0
    def segs_day(self, d):
        if (d % 7) not in self.days: return []
        segs = [(d*DAY+self.op, d*DAY+self.cl)]
        for (a, b) in self.unavail:
            ns = []
            for (s, e) in segs:
                if b <= s or a >= e: ns.append((s, e)); continue
                if a > s: ns.append((s, a))
                if b < e: ns.append((b, e))
            segs = ns
        return segs
    def next_work(self, t):
        d = t // DAY
        for dd in range(d, d+400):
            for (s, e) in self.segs_day(dd):
                if e > t: return max(s, t)
        raise Exception('no work time')
    def run(self, start, work):
        t = start; rem = work
        while True:
            seg = None
            for (s, e) in self.segs_day(t // DAY):
                if s <= t < e: seg = (s, e)
            assert seg, (self.name, t)
            if t + rem <= seg[1]: return t + rem
            rem -= seg[1] - t
            t = self.next_work(seg[1])

# ---------------- parsing ----------------
def sections(path):
    lines = open(path).read().split('\n')
    sec = {}; cur = None
    for ln in lines:
        m = re.match(r'^Run \d+: (.*)$', ln.strip())
        if m: cur = m.group(1); sec[cur] = []; continue
        if cur is None: continue
        if re.match(r'^case (activity|wait|decision|arrival)', ln): continue
        if ln.strip(): sec[cur].append(ln.strip())
    return sec

def rows(lines):
    out = []
    for ln in lines:
        if re.match(r'^c\d{4}\s', ln): out.append(ln)
        else: out[-1] += ' ' + ln   # continuation of a split row
    return [r.split() for r in out]

def split_name_ints(toks):
    i = 0
    while i < len(toks) and not re.fullmatch(r'-?\d+(\.\d+)?', toks[i]): i += 1
    return ' '.join(toks[:i]), toks[i:]

def parse_chapter(path):
    sec = sections(path)
    cases = {}
    for r in rows(sec['Cases']): cases[r[0]] = (int(r[1]), int(r[2]))
    work = {}; order = []
    for r in rows(sec['Work plan']):
        n, v = split_name_ints(r[1:])
        work.setdefault(r[0], {})[n] = [int(x) for x in v]
        if n not in order: order.append(n)
    wait = {}
    for r in rows(sec['Wait plan']):
        n, v = split_name_ints(r[1:]); wait.setdefault(r[0], {})[n] = [int(x) for x in v]
    draws = {}
    for r in rows(sec['Route draws']):
        n, v = split_name_ints(r[1:]); draws.setdefault(r[0], {})[n] = [Fraction(x) for x in v]
    tasks = []
    for r in rows(sec['Task log']):
        n, v = split_name_ints(r[1:])
        nn = len(n.split())
        tasks.append((r[0], n, int(v[0]), int(v[1]), int(v[2]), int(v[3]), ' '.join(r[1+nn+4:])))
    waits = []
    for r in rows(sec['Wait log']):
        waits.append((r[0], r[1], int(r[2]), int(r[3]), int(r[4])))
    decs = []
    for r in rows(sec['Decision log']):
        decs.append((r[0], r[1], int(r[2]), int(r[3]), r[4]))
    return dict(cases=cases, work=work, order=order, wait=wait, draws=draws, tasks=tasks, waits=waits, decs=decs)

# ---------------- simulation ----------------
def simulate(model, pools_cfg, ch, mods=None):
    mods = mods or {}
    removed = set(mods.get('remove', []))
    work = {c: {a: list(v) for a, v in d.items()} for c, d in ch['work'].items()}
    wait = {c: {a: list(v) for a, v in d.items()} for c, d in ch['wait'].items()}
    draws = {c: {a: list(v) for a, v in d.items()} for c, d in ch['draws'].items()}
    for (c, a, vis, val) in mods.get('work', []):
        if vis-1 < len(work[c][a]): work[c][a][vis-1] = val
        else: print('NOTE: visit', vis, 'not in plan for', c, a)
    for (c, a, vis, val) in mods.get('wait', []):
        if vis-1 < len(wait[c][a]): wait[c][a][vis-1] = val
        else: print('NOTE: visit', vis, 'not in plan for', c, a)
    for (c, a, vis, val) in mods.get('draw', []):
        if vis-1 < len(draws[c][a]): draws[c][a][vis-1] = Fraction(val)
        else: print('NOTE: visit', vis, 'not in plan for', c, a)
    probs = {d: [(r, Fraction(p), t) for (r, p, t) in lst] for d, lst in model['D'].items()}
    for d, newp in mods.get('probs', {}).items():
        probs[d] = [(r, Fraction(newp[r]), t) for (r, p, t) in probs[d]]
    order = {n: i for i, n in enumerate(ch['order'])}
    workers = {}
    for pool, (cnt, days, op, cl) in pools_cfg.items():
        cnt += mods.get('extra', {}).get(pool, 0)
        workers[pool] = [Worker(f'{pool}_{i}', days, op, cl) for i in range(cnt)]
    for (pool, idx, a, b) in mods.get('unavail', []):
        workers[pool][idx].unavail.append((a, b))
    cases = {c: v for c, v in ch['cases'].items() if c not in removed}
    arrival_rank = {c: (v[0], c) for c, v in cases.items()}
    visits = {}; jcount = {}
    heap = []; seq = [0]
    T = []; Wl = []; Dl = []; ends = {}
    def push_flow(t, case, node):
        seq[0] += 1
        heapq.heappush(heap, (t, 0, seq[0], case, node))
    for c, (arr, _) in cases.items(): push_flow(arr, c, model['start'])
    A = model['A']
    def reach(t, c, node):
        if node == 'End': ends[c] = t; return
        if node in A:
            v = visits[(c, node)] = visits.get((c, node), 0) + 1
            seq[0] += 1
            heapq.heappush(heap, (t, 1, arrival_rank[c], order[node], v, seq[0], c, node)); return
        if node in model['W']:
            v = visits[(c, node)] = visits.get((c, node), 0) + 1
            d = wait[c][node][v-1]
            Wl.append((c, node, v, t, t + d)); push_flow(t + d, c, model['W'][node]); return
        if node in probs:
            v = visits[(c, node)] = visits.get((c, node), 0) + 1
            dr = draws[c][node][v-1]; run = Fraction(0); chosen = None
            for (r, p, tgt) in probs[node]:
                run += p
                if run > dr: chosen = (r, tgt); break
            if chosen is None: chosen = (probs[node][-1][0], probs[node][-1][2])
            Dl.append((c, node, v, t, chosen[0])); reach(t, c, chosen[1]); return
        if node in model['S']:
            for n in model['S'][node]: reach(t, c, n)
            return
        if node in model['J']:
            need, nxt = model['J'][node]
            k = jcount[(c, node)] = jcount.get((c, node), 0) + 1
            if k == need: jcount[(c, node)] = 0; reach(t, c, nxt)
            return
        raise Exception('unknown node ' + node)
    while heap:
        it = heapq.heappop(heap)
        if it[1] == 0:
            reach(it[0], it[3], it[4])
        else:
            t, _, arank, aid, v, _, c, node = it
            pool, nxt = A[node]
            w = work[c][node][v-1]
            best = None
            for i, wk in enumerate(workers[pool]):
                st = wk.next_work(max(t, wk.free))
                key = (st, wk.free, i)
                if best is None or key < best[0]: best = (key, wk)
            wk = best[1]; st = best[0][0]
            en = wk.run(st, w); wk.free = en
            T.append((c, node, v, t, st, en, wk.name))
            push_flow(en, c, nxt)
    return dict(ends=ends, tasks=T, waits=Wl, decs=Dl)

def compare(res, ch):
    diffs = []
    for c, (a, e) in ch['cases'].items():
        if res['ends'].get(c) != e: diffs.append(('end', c, e, res['ends'].get(c)))
    for name, mine, ref in (('task', res['tasks'], ch['tasks']), ('wait', res['waits'], ch['waits']), ('dec', res['decs'], ch['decs'])):
        sm = set(mine); sr = set(ref)
        if len(sm) != len(mine): diffs.append((name, 'dups in mine'))
        for x in sorted(sr - sm): diffs.append((name + '-missing', x))
        for x in sorted(sm - sr): diffs.append((name + '-extra', x))
    return diffs

def load(proc, doc, run):
    ch = parse_chapter(f'{proc}_{doc}_chapter_Run_{run}.txt')
    model = loan_model() if proc == 'loan' else pharm_model()
    return model, doc_config(proc, doc), ch

if __name__ == '__main__':
    for proc in ('loan', 'pharmacy'):
        for doc, runs in (('policyP', (13, 14)), ('policyH', (15, 16))):
            for run in runs:
                model, cfg, ch = load(proc, doc, run)
                res = simulate(model, cfg, ch)
                d = compare(res, ch)
                print(proc, doc, run, 'rows', len(ch['tasks']), len(ch['waits']), len(ch['decs']), 'EXACT' if not d else f'DIFFS {len(d)}')
                for x in d[:6]: print('   ', x)
