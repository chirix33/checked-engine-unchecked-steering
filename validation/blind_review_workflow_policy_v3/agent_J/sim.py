import re, heapq, json, sys, copy, glob
DAY = 86400


def parse_chapter(path):
    txt = open(path, encoding='utf-8').read()
    secs = {}
    cur = None
    for line in txt.split('\n'):
        m = re.match(r'^Run \d+: (.+)$', line.strip())
        if m:
            cur = m.group(1)
            secs[cur] = []
            continue
        if cur is None:
            continue
        if re.match(r'^case (activity|wait|decision|arrival)', line.strip()):
            continue
        secs[cur].append(line.strip())

    def recs(name):
        toks = ' '.join(secs[name]).split()
        out = []
        c = None
        for t in toks:
            if re.fullmatch(r'c\d{4}', t):
                c = [t]
                out.append(c)
            else:
                c.append(t)
        return out
    ch = {}
    ch['cases'] = {r[0]: (int(r[1]), int(r[2])) for r in recs('Cases')}
    wp = {}
    order = []
    for r in recs('Work plan'):
        i = 1
        name = []
        while not r[i].isdigit():
            name.append(r[i])
            i += 1
        name = ' '.join(name)
        if name not in order:
            order.append(name)
        wp[(r[0], name)] = [int(x) for x in r[i:]]
    ch['work'] = wp
    ch['actorder'] = order
    ch['wait'] = {(r[0], r[1]): [int(x) for x in r[2:]] for r in recs('Wait plan')}
    ch['draw'] = {(r[0], r[1]): [float(x) for x in r[2:]] for r in recs('Route draws')}
    tl = []
    for r in recs('Task log'):
        i = 1
        name = []
        while not r[i].isdigit():
            name.append(r[i])
            i += 1
        tl.append((r[0], ' '.join(name), int(r[i]), int(r[i+1]), int(r[i+2]), int(r[i+3]), ' '.join(r[i+4:])))
    ch['tasklog'] = tl
    ch['waitlog'] = [(r[0], r[1], int(r[2]), int(r[3]), int(r[4])) for r in recs('Wait log')]
    ch['declog'] = [(r[0], r[1], int(r[2]), int(r[3]), r[4]) for r in recs('Decision log')]
    return ch


def parse_front(path):
    t = ' '.join(open(path, encoding='utf-8').read().split())
    pools = {}
    m = re.search(r'Workers\. (.*?) Process\.', t)
    w = m.group(1)
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for pm in re.finditer(r'([A-Z][A-Za-z ]*?): (\d+) workers? \(.*?\), working (\w+) to (\w+) (\d\d):(\d\d) to (\d\d):(\d\d)', w):
        name = pm.group(1).strip()
        d0 = days.index(pm.group(3))
        d1 = days.index(pm.group(4))
        s = int(pm.group(5)) * 3600 + int(pm.group(6)) * 60
        e = int(pm.group(7)) * 3600 + int(pm.group(8)) * 60
        pools[name] = dict(n=int(pm.group(2)), days=list(range(d0, d1 + 1)), s=s, e=e)
    probs = {}
    for dm in re.finditer(r'route (D\d-\w)(?: \((?:[^()]|\([^()]*\))*\))?, probability ([\d.]+)', t):
        probs[dm.group(1)] = float(dm.group(2))
    return pools, probs


LOAN = dict(
    act={'Check application form completeness': ('Clerk', 'D1'), 'Return application back to applicant': ('Clerk', 'W1'),
         'Appraise property': ('Appraiser', 'J1'), 'AML Check': ('AML Investigator', 'J1'), 'Check credit history': ('Clerk', 'J1'),
         'Applicant completes form': ('Applicant', 'Check application form completeness'),
         'Assess loan risk': ('Loan Officer', 'D2'), 'Reject application': ('Clerk', 'END'), 'Design loan offer': ('Loan Officer', 'Approve Loan Offer'),
         'Approve Loan Offer': ('Senior Officer', 'D3'), 'Prepare acceptance pack': ('Loan Officer', 'Approve and send acceptance pack'),
         'Prepare home insurance quote': ('Clerk', 'Approve and post home insurance quote'),
         'Approve and send acceptance pack': ('Loan Officer', 'J2'), 'Approve and post home insurance quote': ('Loan Officer', 'J2'),
         'Consider re-design loan offer': ('Senior Officer', 'D5'), 'Approve application': ('Clerk', 'END'), 'Cancel application': ('Clerk', 'END')},
    wait={'W1': 'Applicant completes form', 'W2': 'Assess loan risk', 'W3': 'Approve application'},
    dec={'D1': [('D1-a', 'Return application back to applicant'), ('D1-b', 'S1')],
         'D2': [('D2-a', 'Reject application'), ('D2-b', 'Design loan offer')],
         'D3': [('D3-a', 'Design loan offer'), ('D3-b', 'S2')],
         'D4': [('D4-a', 'W3'), ('D4-b', 'Consider re-design loan offer')],
         'D5': [('D5-a', 'Cancel application'), ('D5-b', 'Design loan offer')]},
    split={'S1': ['Appraise property', 'Check credit history', 'AML Check'], 'S2': ['Prepare acceptance pack', 'Prepare home insurance quote']},
    join={'J1': (3, 'W2'), 'J2': (2, 'D4')}, start='Check application form completeness')
PHARM = dict(
    act={'Process drop-off': ('Technician', 'W1'), 'Enter prescription details': ('Technician', 'Check if refill is allowed'),
         'Check if refill is allowed': ('Pharmacy System', 'D1'), 'Contact Doctor about refill': ('Technician', 'D2'),
         'Check DUR': ('Pharmacy System', 'D3'), 'Check Insurance': ('Pharmacy System', 'D5'),
         'Contact customer / doctor': ('Pharmacy System', 'Check Insurance'), 'Resolve DUR manually': ('Pharmacist', 'Check Insurance'),
         'Resolve insurance issues manually': ('Technician', 'D6'), 'Pack the drugs (Production)': ('Technician', 'Check for Quality Assurance'),
         'Check for Quality Assurance': ('Pharmacist', 'D7'), 'Pick-up': ('Technician', 'END')},
    wait={'W1': 'Enter prescription details', 'W2': 'Pack the drugs (Production)', 'W3': 'Pick-up'},
    dec={'D1': [('D1-a', 'Check DUR'), ('D1-b', 'Contact Doctor about refill')],
         'D2': [('D2-a', 'Check DUR'), ('D2-b', 'END')],
         'D3': [('D3-a', 'Check Insurance'), ('D3-b', 'D4')],
         'D4': [('D4-a', 'Resolve DUR manually'), ('D4-b', 'Contact customer / doctor')],
         'D5': [('D5-a', 'D6'), ('D5-b', 'Resolve insurance issues manually')],
         'D6': [('D6-a', 'W3'), ('D6-b', 'W2')],
         'D7': [('D7-a', 'D6'), ('D7-b', 'W3')]},
    split={}, join={}, start='Process drop-off')


def is_open(t, pool, un):
    d = t // DAY
    tod = t - d * DAY
    if (d % 7) not in pool['days'] or not (pool['s'] <= tod < pool['e']):
        return False
    for a, b in un:
        if a <= t < b:
            return False
    return True


def working_start(t, pool, un):
    # first time >= t within working hours and not unavailable
    while True:
        d = t // DAY
        tod = t - d * DAY
        if (d % 7) in pool['days']:
            if tod < pool['s']:
                t = d * DAY + pool['s']
                continue
            if tod < pool['e']:
                hit = False
                for a, b in un:
                    if a <= t < b:
                        t = b
                        hit = True
                        break
                if hit:
                    continue
                return t
        t = (d + 1) * DAY


def do_work(s, w, pool, un):
    t = working_start(s, pool, un)
    rem = w
    if rem == 0:
        return t
    while True:
        t = working_start(t, pool, un)
        d = t // DAY
        c = d * DAY + pool['e']
        for a, b in un:
            if t < a < c:
                c = a
        if c - t >= rem:
            return t + rem
        rem -= c - t
        t = c


def simulate(G, ch, pools, probs, mods=None):
    mods = mods or {}
    work = copy.deepcopy(ch['work'])
    wait = copy.deepcopy(ch['wait'])
    draw = copy.deepcopy(ch['draw'])
    probs = dict(probs)
    probs.update(mods.get('probs', {}))
    cases = dict(ch['cases'])
    for c in mods.get('remove', []):
        cases.pop(c)
    for (c, a, v), val in mods.get('work', {}).items():
        work[(c, a)][v - 1] = val
    for (c, w, v), val in mods.get('wait', {}).items():
        wait[(c, w)][v - 1] = val
    for (c, d, v), val in mods.get('draw', {}).items():
        draw[(c, d)][v - 1] = val
    pools = {k: dict(v) for k, v in pools.items()}
    for p, n in mods.get('extra', {}).items():
        pools[p]['n'] += n
    unavail = mods.get('unavail', {})
    actid = {a: i for i, a in enumerate(ch['actorder'])}
    free = {}
    for p, v in pools.items():
        for i in range(v['n']):
            free[(p, i)] = 0
    visits = {}
    joins = {}
    heap = []
    tasklog = []
    waitlog = []
    declog = []
    ends = {}

    def nv(c, n):
        visits[(c, n)] = visits.get((c, n), 0) + 1
        return visits[(c, n)]

    def arrive(c, node, t):
        if node == 'END':
            ends[c] = max(ends.get(c, 0), t)
            return
        if node in G['act']:
            v = nv(c, node)
            heapq.heappush(heap, (t, cases[c][0], c, actid[node], v, node))
            return
        if node in G['wait']:
            v = nv(c, node)
            d = wait[(c, node)][v - 1]
            waitlog.append((c, node, v, t, t + d))
            arrive(c, G['wait'][node], t + d)
            return
        if node in G['dec']:
            v = nv(c, node)
            dr = draw[(c, node)][v - 1]
            cum = 0.0
            chosen = None
            for rid, nxt in G['dec'][node]:
                cum += probs[rid]
                if cum > dr + 1e-12:
                    chosen = (rid, nxt)
                    break
            if chosen is None:
                chosen = G['dec'][node][-1]
            declog.append((c, node, v, t, chosen[0]))
            arrive(c, chosen[1], t)
            return
        if node in G['split']:
            for n2 in G['split'][node]:
                arrive(c, n2, t)
            return
        if node in G['join']:
            cnt, nxt = G['join'][node]
            k = (c, node)
            st = joins.setdefault(k, [0, 0])
            st[0] += 1
            st[1] = max(st[1], t)
            if st[0] == cnt:
                del joins[k]
                arrive(c, nxt, st[1])
            return
        raise Exception(node)
    for c in sorted(cases):
        arrive(c, G['start'], cases[c][0])
    while heap:
        t, arr, c, aid, v, node = heapq.heappop(heap)
        pool, nxt = G['act'][node]
        P = pools[pool]
        w = work[(c, node)][v - 1]
        best = None
        for i in range(P['n']):
            name = f'{pool}_{i}'
            un = unavail.get(name, [])
            st = working_start(max(t, free[(pool, i)]), P, un)
            key = (st, free[(pool, i)], i)
            if best is None or key < best[0]:
                best = (key, i, st, un)
        _, i, st, un = best
        end = do_work(st, w, P, un)
        free[(pool, i)] = end
        tasklog.append((c, node, v, t, st, end, f'{pool}_{i}'))
        arrive(c, nxt, end)
    return dict(ends=ends, tasklog=tasklog, waitlog=waitlog, declog=declog)


def check(G, ch, pools, probs):
    r = simulate(G, ch, pools, probs)
    out = []
    for c, (a, e) in ch['cases'].items():
        if r['ends'].get(c) != e:
            out.append(('end', c, e, r['ends'].get(c)))
    for key in ('tasklog', 'waitlog', 'declog'):
        a = sorted(ch[key])
        b = sorted(r[key])
        if a != b:
            sa = set(a)
            sb = set(b)
            out.append((key, 'printed-only', sorted(sa - sb)[:4], 'sim-only', sorted(sb - sa)[:4], len(sa - sb), len(sb - sa)))
    return out


if __name__ == '__main__':
    for doc, G in (('loan_policyP', LOAN), ('loan_policyH', LOAN), ('pharmacy_policyP', PHARM), ('pharmacy_policyH', PHARM)):
        pools, probs = parse_front(doc + '_front_matter.txt')
        print(doc, {k: (v['n'], v['days'][0], v['days'][-1], v['s'] / 3600, v['e'] / 3600) for k, v in pools.items()}, len(probs))
        for f in sorted(glob.glob(doc + '_chapter_Run_*.txt')):
            ch = parse_chapter(f)
            print(f, len(ch['cases']), len(ch['tasklog']), len(ch['waitlog']), len(ch['declog']))
            res = check(G, ch, pools, probs)
            print('  ', res or 'MATCH')
