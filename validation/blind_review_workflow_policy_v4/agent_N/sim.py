import re, heapq, json, sys, glob

DAYS = {'Monday to Friday': 5, 'Monday to Sunday': 7}


def norm(s):
    return re.sub(r'\s+', ' ', s)


# ---------- front matter ----------
def parse_front(path):
    txt = norm(open(path, encoding='utf-8').read())
    wtxt = txt[txt.index('Workers. ') + 9: txt.index(' Process. ')]
    pools = {}
    for m in re.finditer(r"([A-Z][A-Za-z ]*?): (\d+) workers \([^)]*\), working (Monday to \w+) (\d\d):(\d\d) to (\d\d):(\d\d)", wtxt):
        name, n, days, h1, m1, h2, m2 = m.groups()
        pools[name] = dict(n=int(n), ndays=DAYS[days], s=int(h1) * 3600 + int(m1) * 60, e=int(h2) * 3600 + int(m2) * 60)
    ptxt = txt[txt.index(' Process. '): txt.index(' Rules. ')]
    probs = {}
    for m in re.finditer(r"route (D\d+)-([a-z])\b.*?probability ([0-9.]+), to", ptxt):
        probs.setdefault(m.group(1), []).append((m.group(1) + '-' + m.group(2), float(m.group(3))))
    return txt, pools, ptxt, probs


def act_pool(ptxt, name):
    m = re.search(re.escape(name) + r" \(pool ([A-Za-z ]+?), published", ptxt)
    return m.group(1) if m else None


# ---------- chapter ----------
def parse_chapter(path):
    lines = open(path, encoding='utf-8').read().split('\n')
    secs = {}
    cur = None
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        m = re.match(r"Run \d+: (Cases|Work plan|Wait plan|Route draws|Task log|Wait log|Decision log)$", ln)
        if m:
            cur = m.group(1)
            secs[cur] = []
            continue
        if cur is None:
            continue
        if ln.startswith('case ') and ('arrival' in ln or 'visit' in ln or 'enabled' in ln or 'route' in ln or 'start' in ln or 'time' in ln):
            continue
        if re.match(r"c\d{4} ", ln) or not secs[cur]:
            secs[cur].append(ln)
        else:
            secs[cur][-1] += ' ' + ln
    return secs


def isint(t):
    return re.fullmatch(r"\d+", t) is not None


def parse_inputs(secs):
    cases = {}
    for r in secs['Cases']:
        t = r.split()
        cases[int(t[0][1:])] = (int(t[1]), int(t[2]))
    work = {}
    actorder = []
    for r in secs['Work plan']:
        t = r.split()
        c = int(t[0][1:])
        i = 1
        while not isint(t[i]):
            i += 1
        a = ' '.join(t[1:i])
        vals = [int(x) for x in t[i:]]
        if a not in actorder:
            actorder.append(a)
        for v, x in enumerate(vals, 1):
            work[(c, a, v)] = x
    wait = {}
    for r in secs['Wait plan']:
        t = r.split()
        c = int(t[0][1:])
        w = t[1]
        for v, x in enumerate(t[2:], 1):
            wait[(c, w, v)] = int(x)
    draws = {}
    for r in secs['Route draws']:
        t = r.split()
        c = int(t[0][1:])
        d = t[1]
        for v, x in enumerate(t[2:], 1):
            draws[(c, d, v)] = float(x)
    return cases, work, actorder, wait, draws


def parse_logs(secs):
    tasks = []
    for r in secs['Task log']:
        t = r.split()
        c = int(t[0][1:])
        i = 1
        while not isint(t[i]):
            i += 1
        a = ' '.join(t[1:i])
        v, e, s, en = map(int, t[i:i + 4])
        w = ' '.join(t[i + 4:])
        tasks.append((c, a, v, e, s, en, w))
    waits = []
    for r in secs['Wait log']:
        t = r.split()
        waits.append((int(t[0][1:]), t[1], int(t[2]), int(t[3]), int(t[4])))
    decs = []
    for r in secs['Decision log']:
        t = r.split()
        decs.append((int(t[0][1:]), t[1], int(t[2]), int(t[3]), t[4]))
    ends = {}
    for r in secs['Cases']:
        t = r.split()
        ends[int(t[0][1:])] = int(t[2])
    return tasks, waits, decs, ends


# ---------- process graphs ----------
LOAN = {
    'Check application form completeness': ('act', 'D1'),
    'D1': ('dec', {'D1-a': 'Return application back to applicant', 'D1-b': 'S1'}),
    'Return application back to applicant': ('act', 'W1'),
    'S1': ('split', ['Appraise property', 'Check credit history', 'AML Check']),
    'W1': ('wait', 'Applicant completes form'),
    'Appraise property': ('act', 'J1'), 'AML Check': ('act', 'J1'), 'Check credit history': ('act', 'J1'),
    'Applicant completes form': ('act', 'Check application form completeness'),
    'J1': ('join', 3, 'W2'),
    'W2': ('wait', 'Assess loan risk'),
    'Assess loan risk': ('act', 'D2'),
    'D2': ('dec', {'D2-a': 'Reject application', 'D2-b': 'Design loan offer'}),
    'Reject application': ('act', 'End'),
    'Design loan offer': ('act', 'Approve Loan Offer'),
    'Approve Loan Offer': ('act', 'D3'),
    'D3': ('dec', {'D3-a': 'Design loan offer', 'D3-b': 'S2'}),
    'S2': ('split', ['Prepare acceptance pack', 'Prepare home insurance quote']),
    'Prepare acceptance pack': ('act', 'Approve and send acceptance pack'),
    'Prepare home insurance quote': ('act', 'Approve and post home insurance quote'),
    'Approve and send acceptance pack': ('act', 'J2'),
    'Approve and post home insurance quote': ('act', 'J2'),
    'J2': ('join', 2, 'D4'),
    'D4': ('dec', {'D4-a': 'W3', 'D4-b': 'Consider re-design loan offer'}),
    'Consider re-design loan offer': ('act', 'D5'),
    'W3': ('wait', 'Approve application'),
    'D5': ('dec', {'D5-a': 'Cancel application', 'D5-b': 'Design loan offer'}),
    'Approve application': ('act', 'End'), 'Cancel application': ('act', 'End'),
}
LOAN_START = 'Check application form completeness'
PHARM = {
    'Process drop-off': ('act', 'W1'),
    'W1': ('wait', 'Enter prescription details'),
    'Enter prescription details': ('act', 'Check if refill is allowed'),
    'Check if refill is allowed': ('act', 'D1'),
    'D1': ('dec', {'D1-a': 'Check DUR', 'D1-b': 'Contact Doctor about refill'}),
    'Contact Doctor about refill': ('act', 'D2'),
    'D2': ('dec', {'D2-a': 'Check DUR', 'D2-b': 'End'}),
    'Check DUR': ('act', 'D3'),
    'D3': ('dec', {'D3-a': 'Check Insurance', 'D3-b': 'D4'}),
    'D4': ('dec', {'D4-a': 'Resolve DUR manually', 'D4-b': 'Contact customer / doctor'}),
    'Check Insurance': ('act', 'D5'),
    'Contact customer / doctor': ('act', 'Check Insurance'),
    'Resolve DUR manually': ('act', 'Check Insurance'),
    'D5': ('dec', {'D5-a': 'D6', 'D5-b': 'Resolve insurance issues manually'}),
    'Resolve insurance issues manually': ('act', 'D6'),
    'D6': ('dec', {'D6-a': 'W3', 'D6-b': 'W2'}),
    'W2': ('wait', 'Pack the drugs (Production)'),
    'Pack the drugs (Production)': ('act', 'Check for Quality Assurance'),
    'W3': ('wait', 'Pick-up'),
    'Check for Quality Assurance': ('act', 'D7'),
    'Pick-up': ('act', 'End'),
    'D7': ('dec', {'D7-a': 'D6', 'D7-b': 'W3'}),
}
PHARM_START = 'Process drop-off'


# ---------- calendar ----------
class Cal:
    def __init__(self, ndays, s, e, unavail=()):
        self.nd, self.s, self.e, self.un = ndays, s, e, sorted(unavail)

    def segs_from(self, t):
        d = t // 86400
        while True:
            if d % 7 < self.nd:
                segs = [(d * 86400 + self.s, d * 86400 + self.e)]
                for (ua, ub) in self.un:
                    ns = []
                    for (a, b) in segs:
                        if ub <= a or ua >= b:
                            ns.append((a, b))
                        else:
                            if a < ua:
                                ns.append((a, ua))
                            if ub < b:
                                ns.append((ub, b))
                    segs = ns
                for a, b in segs:
                    if b > t:
                        yield (max(a, t), b)
            d += 1

    def next_work(self, t):
        return next(self.segs_from(t))[0]

    def finish(self, start, w):
        rem = w
        if rem == 0:
            return start
        for a, b in self.segs_from(start):
            a = max(a, start)
            if b - a >= rem:
                return a + rem
            rem -= b - a


# ---------- simulation ----------
def simulate(doc, chap, mods=None):
    mods = mods or {}
    txt, pools, ptxt, probs = parse_front(doc)
    secs = parse_chapter(chap)
    cases, work, actorder, wait, draws = parse_inputs(secs)
    proc = 'loan' if 'Loan' in txt[:40] else 'pharmacy'
    G, START = (LOAN, LOAN_START) if proc == 'loan' else (PHARM, PHARM_START)
    actid = {a: i for i, a in enumerate(actorder)}
    for n, v in G.items():
        if v[0] == 'act':
            assert n in actid, n
    work = dict(work); wait = dict(wait); draws = dict(draws)
    probs = {k: list(v) for k, v in probs.items()}
    work.update(mods.get('work', {}))
    wait.update(mods.get('wait', {}))
    draws.update(mods.get('draw', {}))
    for d, pl in mods.get('probs', {}).items():
        probs[d] = [(f'{d}-{ch}', p) for ch, p in zip('abcdef', pl)]
    cases = dict(cases)
    for c in mods.get('remove', []):
        cases.pop(c)
    wk = {}
    for p, cfg in pools.items():
        n = cfg['n'] + mods.get('addworkers', {}).get(p, 0)
        wk[p] = []
        for i in range(n):
            nm = f'{p}_{i}'
            un = mods.get('unavail', {}).get(nm, [])
            wk[p].append(dict(name=nm, free=0, cal=Cal(cfg['ndays'], cfg['s'], cfg['e'], un)))
    pool_of = {a: act_pool(ptxt, a) for a in actorder}
    assert all(v in wk for v in pool_of.values()), pool_of
    visits = {}
    joins = {}
    pq = []
    tlog = []
    wlog = []
    dlog = []
    ends = {}

    def bump(c, n):
        visits[(c, n)] = visits.get((c, n), 0) + 1
        return visits[(c, n)]

    def enter(c, node, t):
        if node == 'End':
            ends[c] = max(ends.get(c, 0), t)
            return
        spec = G[node]
        kind = spec[0]
        if kind == 'act':
            v = bump(c, node)
            heapq.heappush(pq, (t, cases[c][0], c, actid[node], v, node))
        elif kind == 'wait':
            v = bump(c, node)
            d = wait[(c, node, v)]
            wlog.append((c, node, v, t, t + d))
            enter(c, spec[1], t + d)
        elif kind == 'dec':
            v = bump(c, node)
            dr = draws[(c, node, v)]
            run = 0
            chosen = None
            for rname, p in probs[node]:
                run += p
                if run > dr:
                    chosen = rname
                    break
            if chosen is None:
                chosen = probs[node][-1][0]
            dlog.append((c, node, v, t, chosen))
            enter(c, spec[1][chosen], t)
        elif kind == 'split':
            for nx in spec[1]:
                enter(c, nx, t)
        elif kind == 'join':
            k = (c, node)
            cnt, mt = joins.get(k, (0, 0))
            cnt += 1
            mt = max(mt, t)
            if cnt == spec[1]:
                joins[k] = (0, 0)
                enter(c, spec[2], mt)
            else:
                joins[k] = (cnt, mt)

    for c in sorted(cases, key=lambda c: (cases[c][0], c)):
        enter(c, START, cases[c][0])
    while pq:
        e, arr, c, ai, v, node = heapq.heappop(pq)
        pool = pool_of[node]
        best = None
        for idx, w in enumerate(wk[pool]):
            st = w['cal'].next_work(max(e, w['free']))
            key = (st, w['free'], idx)
            if best is None or key < best[0]:
                best = (key, w)
        (st, fr, idx), w = best
        en = w['cal'].finish(st, work[(c, node, v)])
        w['free'] = en
        tlog.append((c, node, v, e, st, en, w['name']))
        enter(c, G[node][1], en)
    return dict(ends=ends, tasks=tlog, waits=wlog, decs=dlog, cases=cases)


def check(doc, chap):
    r = simulate(doc, chap)
    secs = parse_chapter(chap)
    tasks, waits, decs, ends = parse_logs(secs)
    out = []
    ok = True
    if r['ends'] != ends:
        ok = False
        out.append('ends differ: ' + str([(c, r['ends'].get(c), ends[c]) for c in ends if r['ends'].get(c) != ends[c]][:10]))
    for nm, mine, ref in (('tasks', r['tasks'], tasks), ('waits', r['waits'], waits), ('decs', r['decs'], decs)):
        a, b = sorted(mine), sorted(ref)
        if a != b:
            ok = False
            sa, sb = set(a), set(b)
            out.append(f'{nm}: mine {len(a)} ref {len(b)}; only mine {sorted(sa - sb)[:4]}; only ref {sorted(sb - sa)[:4]}')
        else:
            out.append(f'{nm}: {len(a)} rows identical')
    return ok, out


if __name__ == '__main__':
    for ch in sorted(glob.glob('*_chapter_*.txt')):
        doc = ch.split('_chapter_')[0] + '_front_matter.txt'
        ok, out = check(doc, ch)
        print(ch, 'MATCH' if ok else 'DIFF')
        for o in out:
            print('   ', o)
