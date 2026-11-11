import re, json, heapq, sys
DAY = 86400


def P_loan():
    N = {}

    def act(n, pool, nxt):
        N[n] = ('act', pool, nxt)
    act('Check application form completeness', 'Clerk', 'D1')
    N['D1'] = ('dec', [('D1-a', .2, 'Return application back to applicant'), ('D1-b', .8, 'S1')])
    act('Return application back to applicant', 'Clerk', 'W1')
    N['S1'] = ('split', ['Appraise property', 'Check credit history', 'AML Check'])
    N['W1'] = ('wait', 'Applicant completes form')
    act('Appraise property', 'Appraiser', 'J1')
    act('AML Check', 'AML Investigator', 'J1')
    act('Check credit history', 'Clerk', 'J1')
    act('Applicant completes form', 'Applicant', 'Check application form completeness')
    N['J1'] = ('join', 3, 'W2')
    N['W2'] = ('wait', 'Assess loan risk')
    act('Assess loan risk', 'Loan Officer', 'D2')
    N['D2'] = ('dec', [('D2-a', .5, 'Reject application'), ('D2-b', .5, 'Design loan offer')])
    act('Reject application', 'Clerk', 'END')
    act('Design loan offer', 'Loan Officer', 'Approve Loan Offer')
    act('Approve Loan Offer', 'Senior Officer', 'D3')
    N['D3'] = ('dec', [('D3-a', .2, 'Design loan offer'), ('D3-b', .8, 'S2')])
    N['S2'] = ('split', ['Prepare acceptance pack', 'Prepare home insurance quote'])
    act('Prepare acceptance pack', 'Loan Officer', 'Approve and send acceptance pack')
    act('Prepare home insurance quote', 'Clerk', 'Approve and post home insurance quote')
    act('Approve and send acceptance pack', 'Loan Officer', 'J2')
    act('Approve and post home insurance quote', 'Loan Officer', 'J2')
    N['J2'] = ('join', 2, 'D4')
    N['D4'] = ('dec', [('D4-a', .5, 'W3'), ('D4-b', .5, 'Consider re-design loan offer')])
    act('Consider re-design loan offer', 'Senior Officer', 'D5')
    N['W3'] = ('wait', 'Approve application')
    N['D5'] = ('dec', [('D5-a', .45, 'Cancel application'), ('D5-b', .55, 'Design loan offer')])
    act('Approve application', 'Clerk', 'END')
    act('Cancel application', 'Clerk', 'END')
    W = {'Applicant': (20, 0, 86340, range(7)), 'Senior Officer': (3, 32400, 61200, range(5)),
         'Appraiser': (2, 32400, 61200, range(5)), 'AML Investigator': (4, 32400, 61200, range(5)),
         'Loan Officer': (9, 32400, 61200, range(5)), 'Clerk': (9, 32400, 61200, range(5))}
    return 'Check application form completeness', N, W


def P_ph():
    N = {}

    def act(n, pool, nxt):
        N[n] = ('act', pool, nxt)
    act('Process drop-off', 'Technician', 'W1')
    N['W1'] = ('wait', 'Enter prescription details')
    act('Enter prescription details', 'Technician', 'Check if refill is allowed')
    act('Check if refill is allowed', 'Pharmacy System', 'D1')
    N['D1'] = ('dec', [('D1-a', .94, 'Check DUR'), ('D1-b', .06, 'Contact Doctor about refill')])
    act('Contact Doctor about refill', 'Technician', 'D2')
    N['D2'] = ('dec', [('D2-a', .99, 'Check DUR'), ('D2-b', .01, 'END')])
    act('Check DUR', 'Pharmacy System', 'D3')
    N['D3'] = ('dec', [('D3-a', .8, 'Check Insurance'), ('D3-b', .2, 'D4')])
    N['D4'] = ('dec', [('D4-a', .95, 'Resolve DUR manually'), ('D4-b', .05, 'Contact customer / doctor')])
    act('Check Insurance', 'Pharmacy System', 'D5')
    act('Contact customer / doctor', 'Pharmacy System', 'Check Insurance')
    act('Resolve DUR manually', 'Pharmacist', 'Check Insurance')
    N['D5'] = ('dec', [('D5-a', .83, 'D6'), ('D5-b', .17, 'Resolve insurance issues manually')])
    act('Resolve insurance issues manually', 'Technician', 'D6')
    N['D6'] = ('dec', [('D6-a', .07, 'W3'), ('D6-b', .93, 'W2')])
    N['W2'] = ('wait', 'Pack the drugs (Production)')
    act('Pack the drugs (Production)', 'Technician', 'Check for Quality Assurance')
    N['W3'] = ('wait', 'Pick-up')
    act('Check for Quality Assurance', 'Pharmacist', 'D7')
    act('Pick-up', 'Technician', 'END')
    N['D7'] = ('dec', [('D7-a', .05, 'D6'), ('D7-b', .95, 'W3')])
    W = {'Pharmacy System': (1, 28800, 72000, range(5)), 'Technician': (8, 28800, 72000, range(5)),
         'Pharmacist': (1, 28800, 72000, range(5))}
    return 'Process drop-off', N, W


MODELS = {'loan': P_loan, 'pharmacy': P_ph}


def parse(fn):
    txt = open(fn, encoding='utf8').read().split('\n')
    secs = {}
    cur = None
    for l in txt:
        m = re.match(r'^Run \d+: (.+)$', l.strip())
        if m:
            cur = m.group(1)
            secs[cur] = []
            continue
        if cur:
            secs[cur].append(l.strip())
    out = {}
    for k, ls in secs.items():
        toks = ' '.join(l for l in ls if not l.startswith('case ') and not re.match(r'^(Run \d+ has|\d+$)',l)).split()
        rows = []
        r = None
        for t in toks:
            if re.fullmatch(r'c\d{4}', t):
                r = [t]
                rows.append(r)
            else:
                r.append(t)
        out[k] = rows
    return out


def isnum(t):
    return re.fullmatch(r'-?\d+(\.\d+)?', t) is not None


def split_name(r):
    i = 1
    while i < len(r) and not isnum(r[i]):
        i += 1
    return ' '.join(r[1:i]), r[i:]


def load(fn):
    s = parse(fn)
    D = {}
    D['cases'] = {r[0]: (int(r[1]), int(r[2])) for r in s['Cases']}
    wp = {}
    order = []
    for r in s['Work plan']:
        n, v = split_name(r)
        wp[(r[0], n)] = [int(x) for x in v]
        if n not in order:
            order.append(n)
    D['work'] = wp
    D['order'] = order
    D['wait'] = {}
    for r in s['Wait plan']:
        D['wait'][(r[0], r[1])] = [int(x) for x in r[2:]]
    D['draw'] = {}
    for r in s['Route draws']:
        D['draw'][(r[0], r[1])] = [float(x) for x in r[2:]]
    D['tasklog'] = []
    for r in s['Task log']:
        n, v = split_name(r)
        D['tasklog'].append((r[0], n, int(v[0]), int(v[1]), int(v[2]), int(v[3]), ' '.join(v[4:])))
    D['waitlog'] = [(r[0], r[1], int(r[2]), int(r[3]), int(r[4])) for r in s['Wait log']]
    D['declog'] = [(r[0], r[1], int(r[2]), int(r[3]), r[4]) for r in s['Decision log']]
    return D


def segs(cfg, unav, t):
    n, o, c, days = cfg
    d = t // DAY
    while True:
        if d % 7 in days:
            a = max(d * DAY + o, t)
            b = d * DAY + c
            if b > a:
                pieces = [(a, b)]
                for (ua, ub) in unav:
                    np_ = []
                    for (x, y) in pieces:
                        if ub <= x or ua >= y:
                            np_.append((x, y))
                        else:
                            if x < ua:
                                np_.append((x, ua))
                            if ub < y:
                                np_.append((ub, y))
                    pieces = np_
                for p in pieces:
                    yield p
        d += 1
        if d > t // DAY + 4000:
            return


def first_start(cfg, unav, t):
    for a, b in segs(cfg, unav, t):
        return a


def finish(cfg, unav, t, w):
    for a, b in segs(cfg, unav, t):
        if b - a >= w:
            return a + w
        w -= b - a


def simulate(model, D, drop=(), work=None, wait=None, draw=None, probs=None, unav=None):
    start, N, W = MODELS[model]()
    work = work or {}
    wait = wait or {}
    draw = draw or {}
    probs = probs or {}
    unav = unav or {}
    N = dict(N)
    for dn, pl in probs.items():
        N[dn] = ('dec', [(r, p, nx) for (r, _, nx), p in zip(N[dn][1], pl)])
    order = {n: i for i, n in enumerate(D['order'])}
    cases = [c for c in D['cases'] if c not in drop]
    arr = {c: D['cases'][c][0] for c in cases}
    free = {p: [0] * W[p][0] for p in W}
    un = {p: [] for p in W}
    unav_cnt = {}
    for p, (cnt, a, b) in unav.items():
        un[p] = [(a, b)]
        unav_cnt[p] = cnt
    visit = {}
    joinc = {}
    ends = {}
    tl = []
    wl = []
    dl = []
    ev = []
    seq = [0]

    def push(t, e):
        seq[0] += 1
        heapq.heappush(ev, (t, seq[0], e))
    queue = {p: [] for p in W}
    for c in cases:
        push(arr[c], (c, start))

    def reach(t, c, node):
        while True:
            if node == 'END':
                ends[c] = t
                return
            ty = N[node]
            if ty[0] == 'act':
                visit[(c, node)] = visit.get((c, node), 0) + 1
                queue[ty[1]].append((t, arr[c], c, order[node], visit[(c, node)], node))
                return
            if ty[0] == 'wait':
                visit[(c, node)] = visit.get((c, node), 0) + 1
                v = visit[(c, node)]
                d = wait.get((c, node, v))
                if d is None:
                    d = D['wait'][(c, node)][v - 1]
                wl.append((c, node, v, t, t + d))
                push(t + d, (c, ty[1]))
                return
            if ty[0] == 'dec':
                visit[(c, node)] = visit.get((c, node), 0) + 1
                v = visit[(c, node)]
                dr = draw.get((c, node, v))
                if dr is None:
                    dr = D['draw'][(c, node)][v - 1]
                tot = 0
                sel = None
                for r, p, nx in ty[1]:
                    tot += p
                    if tot > dr + 1e-12:
                        sel = (r, nx)
                        break
                if sel is None:
                    sel = (ty[1][-1][0], ty[1][-1][2])
                dl.append((c, node, v, t, sel[0]))
                node = sel[1]
                continue
            if ty[0] == 'split':
                for s in ty[1][1:]:
                    reach(t, c, s)
                node = ty[1][0]
                continue
            if ty[0] == 'join':
                joinc[(c, node)] = joinc.get((c, node), 0) + 1
                if joinc[(c, node)] < ty[1]:
                    return
                joinc[(c, node)] = 0
                node = ty[2]
                continue
            raise Exception(ty)
    while ev:
        t = ev[0][0]
        while ev and ev[0][0] == t:
            _, _, e = heapq.heappop(ev)
            reach(t, e[0], e[1])
        for p in W:
            q = sorted(queue[p])
            queue[p] = []
            cfg = W[p]
            for (en, a, c, ai, v, node) in q:
                w = work.get((c, node, v))
                if w is None:
                    w = D['work'][(c, node)][v - 1]
                best = None
                for i in range(cfg[0]):
                    uu = un[p] if i < unav_cnt.get(p, 0) else []
                    st = first_start(cfg, uu, max(en, free[p][i]))
                    k = (st, free[p][i], i)
                    if best is None or k < best[0]:
                        best = (k, uu)
                (st, fr, i), uu = best
                end = finish(cfg, uu, st, w)
                free[p][i] = end
                tl.append((c, node, v, en, st, end, f'{p}_{i}'))
                push(end, (c, N[node][2]))
    return ends, tl, wl, dl


def check(model, fn):
    D = load(fn)
    ends, tl, wl, dl = simulate(model, D)
    diffs = []
    for c, (a, e) in D['cases'].items():
        if ends.get(c) != e:
            diffs.append(('end', c, e, ends.get(c)))

    def cmp(name, mine, ref):
        A = sorted(mine)
        B = sorted(ref)
        if A != B:
            sa = set(A)
            sb = set(B)
            diffs.append((name, len(A), len(B), sorted(sb - sa)[:3], sorted(sa - sb)[:3]))
    cmp('task', tl, D['tasklog'])
    cmp('wait', wl, D['waitlog'])
    cmp('dec', dl, D['declog'])
    return diffs, D


if __name__ == '__main__':
    import glob
    for fn in sorted(glob.glob('*_chapter_Run_*.txt')):
        m = fn.split('_')[0]
        d, _ = check(m, fn)
        print(fn, 'OK' if not d else d[:6])
