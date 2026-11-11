import re, heapq, json, sys

DAY = 86400

# ---------------- process graphs (hand-transcribed from the front matters) -------------
# node kinds: ('act', pool, next) ; ('wait', next) ; ('dec', [(route, next)...]) ; ('split',[nexts]) ; ('join', n, next) ; ('end',)
LOAN = {
    'start': 'Check application form completeness',
    'acts': {
        'Check application form completeness': ('Clerk', 'D1'),
        'Return application back to applicant': ('Clerk', 'W1'),
        'Appraise property': ('Appraiser', 'J1'),
        'AML Check': ('AML Investigator', 'J1'),
        'Check credit history': ('Clerk', 'J1'),
        'Applicant completes form': ('Applicant', 'Check application form completeness'),
        'Assess loan risk': ('Loan Officer', 'D2'),
        'Reject application': ('Clerk', 'End'),
        'Design loan offer': ('Loan Officer', 'Approve Loan Offer'),
        'Approve Loan Offer': ('Senior Officer', 'D3'),
        'Prepare acceptance pack': ('Loan Officer', 'Approve and send acceptance pack'),
        'Prepare home insurance quote': ('Clerk', 'Approve and post home insurance quote'),
        'Approve and send acceptance pack': ('Loan Officer', 'J2'),
        'Approve and post home insurance quote': ('Loan Officer', 'J2'),
        'Consider re-design loan offer': ('Senior Officer', 'D5'),
        'Approve application': ('Clerk', 'End'),
        'Cancel application': ('Clerk', 'End'),
    },
    'waits': {'W1': 'Applicant completes form', 'W2': 'Assess loan risk', 'W3': 'Approve application'},
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
}
PHARM = {
    'start': 'Process drop-off',
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
        'Pick-up': ('Technician', 'End'),
    },
    'waits': {'W1': 'Enter prescription details', 'W2': 'Pack the drugs (Production)', 'W3': 'Pick-up'},
    'decs': {
        'D1': [('D1-a', 0.94, 'Check DUR'), ('D1-b', 0.06, 'Contact Doctor about refill')],
        'D2': [('D2-a', 0.99, 'Check DUR'), ('D2-b', 0.01, 'End')],
        'D3': [('D3-a', 0.8, 'Check Insurance'), ('D3-b', 0.2, 'D4')],
        'D4': [('D4-a', 0.95, 'Resolve DUR manually'), ('D4-b', 0.05, 'Contact customer / doctor')],
        'D5': [('D5-a', 0.83, 'D6'), ('D5-b', 0.17, 'Resolve insurance issues manually')],
        'D6': [('D6-a', 0.07, 'W3'), ('D6-b', 0.93, 'W2')],
        'D7': [('D7-a', 0.05, 'D6'), ('D7-b', 0.95, 'W3')],
    },
    'splits': {}, 'joins': {},
}
GRAPHS = {'loan': LOAN, 'pharmacy': PHARM}


# ---------------- front matter: pools ----------------
def parse_pools(path):
    txt = ' '.join(open(path, encoding='utf-8').read().split())
    m = re.search(r'Workers\.\s(.*?)(?:Process\.|Any worker|Workers in a pool)', txt)
    # take the sentence block with pool lists up to 'Process.'
    blk = txt[txt.index('Workers.') + 8: txt.index('Process.')]
    pools = {}
    for mm in re.finditer(r'([A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*)*): (\d+) workers? \(.*?\), working (\w+) to (\w+) (\d\d):(\d\d) to (\d\d):(\d\d)', blk):
        name, n, d1, d2, h1, m1, h2, m2 = mm.groups()
        days = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6}
        pools[name] = dict(n=int(n), d1=days[d1], d2=days[d2], open=int(h1) * 3600 + int(m1) * 60,
                           close=int(h2) * 3600 + int(m2) * 60)
    return pools


# ---------------- chapter parsing ----------------
def parse_chapter(path):
    lines = open(path, encoding='utf-8').read().splitlines()
    secs = {}
    cur = None
    for ln in lines:
        m = re.match(r'^Run \d+: (Cases|Work plan|Wait plan|Route draws|Task log|Wait log|Decision log)$', ln.strip())
        if m:
            cur = m.group(1); secs[cur] = []; continue
        if cur is None:
            continue
        if ln.startswith('case '):
            continue
        secs[cur].append(ln.strip())
    out = {}
    cid = re.compile(r'(?=\bc\d{4}\b)')

    def recs(sec):
        txt = ' '.join(secs[sec])
        return [r.strip() for r in re.split(r'(?=\bc\d{4}\s)', txt) if r.strip()]

    cases = {}
    for r in recs('Cases'):
        c, a, e = r.split()
        cases[c] = (int(a), int(e))
    out['cases'] = cases
    work = {}
    order = {}
    for r in recs('Work plan'):
        toks = r.split()
        c = toks[0]
        i = 1
        while not toks[i].isdigit():
            i += 1
        name = ' '.join(toks[1:i]); vals = [int(x) for x in toks[i:]]
        work[(c, name)] = vals
        order.setdefault(c, []).append(name)
    out['work'] = work
    out['order'] = order
    wait = {}
    for r in recs('Wait plan'):
        toks = r.split(); wait[(toks[0], toks[1])] = [int(x) for x in toks[2:]]
    out['wait'] = wait
    draws = {}
    for r in recs('Route draws'):
        toks = r.split(); draws[(toks[0], toks[1])] = [float(x) for x in toks[2:]]
    out['draws'] = draws
    tl = []
    for r in recs('Task log'):
        toks = r.split(); c = toks[0]; i = 1
        while not toks[i].isdigit():
            i += 1
        name = ' '.join(toks[1:i]); v, en, st, ed = map(int, toks[i:i + 4]); w = ' '.join(toks[i + 4:])
        tl.append((c, name, v, en, st, ed, w))
    out['tasklog'] = tl
    wl = []
    for r in recs('Wait log'):
        t = r.split(); wl.append((t[0], t[1], int(t[2]), int(t[3]), int(t[4])))
    out['waitlog'] = wl
    dl = []
    for r in recs('Decision log'):
        t = r.split(); dl.append((t[0], t[1], int(t[2]), int(t[3]), t[4]))
    out['declog'] = dl
    return out


# ---------------- simulator ----------------
class Worker:
    def __init__(self, pool, idx, p, unavail):
        self.pool = pool; self.idx = idx; self.p = p; self.free = 0; self.unavail = unavail  # sorted list (a,b)

    def segs_from(self, t):
        p = self.p
        d = t // DAY
        for dd in range(d, d + 800):
            wd = dd % 7
            if not (p['d1'] <= wd <= p['d2']):
                continue
            a = dd * DAY + p['open']; b = dd * DAY + p['close']
            pieces = [(a, b)]
            for ua, ub in self.unavail:
                np_ = []
                for x, y in pieces:
                    if ub <= x or ua >= y:
                        np_.append((x, y))
                    else:
                        if x < ua: np_.append((x, ua))
                        if ub < y: np_.append((ub, y))
                pieces = np_
            for x, y in pieces:
                if y > t and y > x:
                    yield (max(x, t), y)
        raise RuntimeError('no window')

    def first_start(self, t):
        for s, e in self.segs_from(t):
            return s

    def run(self, t, work):
        start = None
        for s, e in self.segs_from(t):
            if start is None:
                start = s
                if work == 0:
                    return start, start
            if work <= e - s:
                return start, s + work
            work -= e - s
        raise RuntimeError


def simulate(proc, pools, chap, mods=None):
    g = GRAPHS[proc]
    mods = mods or {}
    cases = dict(chap['cases'])
    for c in mods.get('remove', []):
        cases.pop(c, None)
    work = {k: list(v) for k, v in chap['work'].items()}
    wait = {k: list(v) for k, v in chap['wait'].items()}
    draws = {k: list(v) for k, v in chap['draws'].items()}
    for (c, a, v), val in mods.get('work', {}).items():
        if v - 1 < len(work[(c, a)]): work[(c, a)][v - 1] = val
        else: print('NOTE: visit', v, 'of', a, 'not in plan; change is a no-op')
    for (c, w, v), val in mods.get('wait', {}).items(): wait[(c, w)][v - 1] = val
    for (c, d, v), val in mods.get('draw', {}).items(): draws[(c, d)][v - 1] = val
    decs = {d: list(r) for d, r in g['decs'].items()}
    for d, probs in mods.get('probs', {}).items():
        decs[d] = [(r, probs[r], nx) for (r, _, nx) in decs[d]]
    actid = {}
    first = sorted(chap['order'])[0]
    for i, n in enumerate(chap['order'][first]): actid[n] = i
    for c, o in chap['order'].items():
        assert o == chap['order'][first], 'activity order differs'
    pnum = {n: dict(v) for n, v in pools.items()}
    for pn, k in mods.get('addworkers', {}).items(): pnum[pn]['n'] += k
    unav = {}  # (pool,idx)->list
    for pn, idxs, a, b in mods.get('unavail', []):
        for i in idxs: unav.setdefault((pn, i), []).append((a, b))
    workers = {pn: [Worker(pn, i, p, sorted(unav.get((pn, i), []))) for i in range(p['n'])] for pn, p in pnum.items()}
    arrival = {c: v[0] for c, v in cases.items()}
    visits = {}
    joins = {}
    heap = []
    log = dict(task=[], wait=[], dec=[], end={})

    def vis(c, n):
        visits[(c, n)] = visits.get((c, n), 0) + 1
        return visits[(c, n)]

    def reach(c, node, t):
        if node == 'End':
            log['end'][c] = t; return
        if node in g['acts']:
            v = vis(c, node)
            heapq.heappush(heap, (t, arrival[c], c, actid[node], v, node))
        elif node in g['waits']:
            v = vis(c, node)
            d = wait[(c, node)][v - 1]
            log['wait'].append((c, node, v, t, t + d))
            reach(c, g['waits'][node], t + d)
        elif node in decs:
            v = vis(c, node)
            dr = draws[(c, node)][v - 1]
            tot = 0; chosen = None
            for r, p, nx in decs[node]:
                tot += p
                if tot > dr + 1e-12:
                    chosen = (r, nx); break
            if chosen is None: chosen = (decs[node][-1][0], decs[node][-1][2])
            log['dec'].append((c, node, v, t, chosen[0]))
            reach(c, chosen[1], t)
        elif node in g['splits']:
            for nx in g['splits'][node]: reach(c, nx, t)
        elif node in g['joins']:
            n, nx = g['joins'][node]
            lst = joins.setdefault((c, node), [])
            lst.append(t)
            if len(lst) == n:
                tt = max(lst); joins[(c, node)] = []
                reach(c, nx, tt)
        else:
            raise RuntimeError('unknown node ' + node)

    for c in sorted(cases, key=lambda x: (arrival[x], x)):
        reach(c, g['start'], arrival[c])
    while heap:
        en, arr, c, aid, v, node = heapq.heappop(heap)
        pool, nx = g['acts'][node]
        w = work[(c, node)][v - 1]
        best = None
        for wk in workers[pool]:
            s = wk.first_start(max(en, wk.free))
            key = (s, wk.free, wk.idx)
            if best is None or key < best[0]: best = (key, wk)
        wk = best[1]
        s, e = wk.run(max(en, wk.free), w)
        wk.free = e
        log['task'].append((c, node, v, en, s, e, '%s_%d' % (pool, wk.idx)))
        reach(c, nx, e)
    return log


def compare(chap, log):
    diffs = []
    for c, (a, e) in chap['cases'].items():
        if log['end'].get(c) != e: diffs.append(('end', c, e, log['end'].get(c)))
    for name, ref, mine in (('task', chap['tasklog'], log['task']), ('wait', chap['waitlog'], log['wait']), ('dec', chap['declog'], log['dec'])):
        a = sorted(ref); b = sorted(mine)
        if a != b:
            sa, sb = set(a), set(b)
            diffs.append((name, len(a), len(b), sorted(sa - sb)[:3], sorted(sb - sa)[:3]))
    return diffs


if __name__ == '__main__':
    qs = json.load(open('questions.json'))
    import glob
    files = []
    for ch in sorted(glob.glob('*_chapter_Run_*.txt')):
        doc = ch.split('_chapter')[0]
        files.append((doc.split('_')[0], doc + '_front_matter.txt', ch))
    for proc, fm, ch in files:
        pools = parse_pools(fm)
        chap = parse_chapter(ch)
        log = simulate(proc, pools, chap)
        d = compare(chap, log)
        print(ch, 'MATCH' if not d else 'DIFF', len(chap['cases']), 'cases', len(chap['tasklog']), 'tasks', d[:2])
