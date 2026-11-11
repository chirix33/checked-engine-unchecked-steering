import re, heapq, json, sys, copy
DAY = 86400


def H(h, m=0):
    return h * 3600 + m * 60


def loan_model():
    return dict(
        acts={
            'Check application form completeness': ('Clerk', 'D1'),
            'Return application back to applicant': ('Clerk', 'W1'),
            'Appraise property': ('Appraiser', 'J1'), 'AML Check': ('AML Investigator', 'J1'),
            'Check credit history': ('Clerk', 'J1'),
            'Applicant completes form': ('Applicant', 'Check application form completeness'),
            'Assess loan risk': ('Loan Officer', 'D2'), 'Reject application': ('Clerk', 'End'),
            'Design loan offer': ('Loan Officer', 'Approve Loan Offer'),
            'Approve Loan Offer': ('Senior Officer', 'D3'),
            'Prepare acceptance pack': ('Loan Officer', 'Approve and send acceptance pack'),
            'Prepare home insurance quote': ('Clerk', 'Approve and post home insurance quote'),
            'Approve and send acceptance pack': ('Loan Officer', 'J2'),
            'Approve and post home insurance quote': ('Loan Officer', 'J2'),
            'Consider re-design loan offer': ('Senior Officer', 'D5'),
            'Approve application': ('Clerk', 'End'), 'Cancel application': ('Clerk', 'End')},
        waits={'W1': 'Applicant completes form', 'W2': 'Assess loan risk', 'W3': 'Approve application'},
        decs={'D1': [('D1-a', .2, 'Return application back to applicant'), ('D1-b', .8, 'S1')],
              'D2': [('D2-a', .5, 'Reject application'), ('D2-b', .5, 'Design loan offer')],
              'D3': [('D3-a', .2, 'Design loan offer'), ('D3-b', .8, 'S2')],
              'D4': [('D4-a', .5, 'W3'), ('D4-b', .5, 'Consider re-design loan offer')],
              'D5': [('D5-a', .45, 'Cancel application'), ('D5-b', .55, 'Design loan offer')]},
        splits={'S1': ['Appraise property', 'Check credit history', 'AML Check'],
                'S2': ['Prepare acceptance pack', 'Prepare home insurance quote']},
        joins={'J1': (3, 'W2'), 'J2': (2, 'D4')},
        start='Check application form completeness',
        pools={'Applicant': (20, range(7), 0, 86340), 'Senior Officer': (3, range(5), H(9), H(17)),
               'Appraiser': (2, range(5), H(9), H(17)), 'AML Investigator': (4, range(5), H(9), H(17)),
               'Loan Officer': (9, range(5), H(9), H(17)), 'Clerk': (9, range(5), H(9), H(17))})


def pharm_model():
    return dict(
        acts={'Process drop-off': ('Technician', 'W1'),
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
              'Pick-up': ('Technician', 'End')},
        waits={'W1': 'Enter prescription details', 'W2': 'Pack the drugs (Production)', 'W3': 'Pick-up'},
        decs={'D1': [('D1-a', .94, 'Check DUR'), ('D1-b', .06, 'Contact Doctor about refill')],
              'D2': [('D2-a', .99, 'Check DUR'), ('D2-b', .01, 'End')],
              'D3': [('D3-a', .8, 'Check Insurance'), ('D3-b', .2, 'D4')],
              'D4': [('D4-a', .95, 'Resolve DUR manually'), ('D4-b', .05, 'Contact customer / doctor')],
              'D5': [('D5-a', .83, 'D6'), ('D5-b', .17, 'Resolve insurance issues manually')],
              'D6': [('D6-a', .07, 'W3'), ('D6-b', .93, 'W2')],
              'D7': [('D7-a', .05, 'D6'), ('D7-b', .95, 'W3')]},
        splits={}, joins={}, start='Process drop-off',
        pools={'Pharmacy System': (1, range(5), H(8), H(20)), 'Technician': (8, range(5), H(8), H(20)),
               'Pharmacist': (1, range(5), H(8), H(20))})


MODELS = {'loan': loan_model, 'pharmacy': pharm_model}


def parse_chapter(path):
    lines = open(path, encoding='utf-8').read().split('\n')
    secs = {}
    cur = None
    for ln in lines:
        s = ln.strip()
        m = re.match(r'^Run \d+: (.+)$', s)
        if m:
            cur = m.group(1)
            secs[cur] = []
            continue
        if cur is None or not s:
            continue
        if s.startswith('case ') and ('visit' in s or 'arrival' in s or 'enabled' in s):
            continue
        if re.match(r'^c\d{4} ', s):
            secs[cur].append(s)
        else:
            secs[cur][-1] += ' ' + s
    return secs


def intl(s):
    return [int(x) for x in s.split()]


def parse(path):
    S = parse_chapter(path)
    d = {'cases': {}}
    for r in S['Cases']:
        c, a, e = r.split()
        d['cases'][c] = (int(a), int(e))
    d['work'] = {}
    d['actorder'] = []
    for r in S['Work plan']:
        m = re.match(r'^(c\d{4}) ([^\d]+?) ((?:\d+ ?)+)$', r)
        assert m, r
        c, a, v = m.group(1), m.group(2).strip(), intl(m.group(3))
        d['work'][(c, a)] = v
        if a not in d['actorder']:
            d['actorder'].append(a)
    d['wait'] = {}
    for r in S['Wait plan']:
        m = re.match(r'^(c\d{4}) (W\d+) ((?:\d+ ?)+)$', r)
        assert m, r
        d['wait'][(m.group(1), m.group(2))] = intl(m.group(3))
    d['draw'] = {}
    for r in S['Route draws']:
        m = re.match(r'^(c\d{4}) (D\d+) ((?:[\d.]+ ?)+)$', r)
        assert m, r
        d['draw'][(m.group(1), m.group(2))] = [float(x) for x in m.group(3).split()]
    d['tasklog'] = set()
    for r in S['Task log']:
        m = re.match(r'^(c\d{4}) ([^\d]+?) (\d+) (\d+) (\d+) (\d+) (.+_\d+)$', r)
        assert m, r
        d['tasklog'].add((m.group(1), m.group(2).strip()) + tuple(int(m.group(i)) for i in range(3, 7)) + (m.group(7),))
    d['waitlog'] = set()
    for r in S['Wait log']:
        m = re.match(r'^(c\d{4}) (W\d+) (\d+) (\d+) (\d+)$', r)
        assert m, r
        d['waitlog'].add((m.group(1), m.group(2)) + tuple(int(m.group(i)) for i in range(3, 6)))
    d['declog'] = set()
    for r in S['Decision log']:
        m = re.match(r'^(c\d{4}) (D\d+) (\d+) (\d+) (\S+)$', r)
        assert m, r
        d['declog'].add((m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), m.group(5)))
    return d


def next_work(t, sch):
    days, o, c = sch
    while True:
        d = t // DAY
        tod = t - d * DAY
        if (d % 7) in days:
            if o <= tod < c:
                return t
            if tod < o:
                return d * DAY + o
        t = (d + 1) * DAY


def finish(start, work, sch):
    days, o, c = sch
    t = start
    r = work
    while True:
        t = next_work(t, sch)
        d = t // DAY
        close = d * DAY + c
        if t + r <= close:
            return t + r
        r -= close - t
        t = close


def simulate(model, d, mods=None):
    mods = mods or {}
    P = MODELS[model]()
    removed = set(mods.get('remove', []))
    work = copy.deepcopy(d['work'])
    wait = copy.deepcopy(d['wait'])
    draw = copy.deepcopy(d['draw'])
    for (c, a, v), val in mods.get('work', {}).items():
        work[(c, a)][v - 1] = val
    for (c, w, v), val in mods.get('wait', {}).items():
        wait[(c, w)][v - 1] = val
    for (c, x, v), val in mods.get('draw', {}).items():
        draw[(c, x)][v - 1] = val
    decs = copy.deepcopy(P['decs'])
    for x, pr in mods.get('probs', {}).items():
        decs[x] = [(n, p, t) for (n, _, t), p in zip(decs[x], pr)]
    pools = {}
    for pn, (n, days, o, c) in P['pools'].items():
        n += mods.get('extra', {}).get(pn, 0)
        pools[pn] = dict(sch=(days, o, c), free=[0] * n)
    actid = {a: i for i, a in enumerate(d['actorder'])}
    cases = sorted(c for c in d['cases'] if c not in removed)
    arr = {c: d['cases'][c][0] for c in cases}
    heap = []
    seq = [0]

    def push(t, c, node):
        seq[0] += 1
        heapq.heappush(heap, (t, seq[0], c, node))
    for c in cases:
        push(arr[c], c, P['start'])
    visit = {}
    joinc = {}
    pend = []
    out = dict(end={}, task=set(), wait=set(), dec=set())

    def reach(t, c, node):
        if node == 'End':
            out['end'][c] = max(out['end'].get(c, 0), t)
            return
        key = (c, node)
        visit[key] = visit.get(key, 0) + 1
        v = visit[key]
        if node in P['acts']:
            pend.append((t, arr[c], c, actid[node], v, node))
        elif node in P['waits']:
            dl = wait[(c, node)][v - 1]
            out['wait'].add((c, node, v, t, t + dl))
            push(t + dl, c, P['waits'][node])
        elif node in decs:
            dr = draw[(c, node)][v - 1]
            cum = 0
            tgt = None
            for nm, p, tg in decs[node]:
                cum += p
                if cum > dr:
                    tgt = (nm, tg)
                    break
            if tgt is None:
                tgt = (decs[node][-1][0], decs[node][-1][2])
            out['dec'].add((c, node, v, t, tgt[0]))
            reach(t, c, tgt[1])
        elif node in P['splits']:
            for x in P['splits'][node]:
                reach(t, c, x)
        elif node in P['joins']:
            n, nx = P['joins'][node]
            joinc[key] = joinc.get(key, 0) + 1
            if joinc[key] == n:
                joinc[key] = 0
                reach(t, c, nx)
        else:
            raise Exception(node)
    while heap:
        t = heap[0][0]
        while heap and heap[0][0] == t:
            _, _, c, node = heapq.heappop(heap)
            reach(t, c, node)
        pend.sort()
        for (en, _, c, aid, v, node) in pend:
            pool = P['acts'][node][0]
            pl = pools[pool]
            best = None
            for i, f in enumerate(pl['free']):
                s = next_work(max(en, f), pl['sch'])
                k = (s, f, i)
                if best is None or k < best:
                    best = k
            s, f, i = best
            w = work[(c, node)][v - 1]
            e = finish(s, w, pl['sch'])
            pl['free'][i] = e
            out['task'].add((c, node, v, en, s, e, '%s_%d' % (pool, i)))
            push(e, c, P['acts'][node][1])
        pend.clear()
    return out


def compare(model, d, o):
    diffs = []
    for c, (a, e) in d['cases'].items():
        if o['end'].get(c) != e:
            diffs.append(('end', c, e, o['end'].get(c)))
    for k, a, b in (('task', d['tasklog'], o['task']), ('wait', d['waitlog'], o['wait']), ('dec', d['declog'], o['dec'])):
        for x in a - b:
            diffs.append((k, 'printed-only', x))
        for x in b - a:
            diffs.append((k, 'sim-only', x))
    return diffs


if __name__ == '__main__':
    import glob
    for model in ('loan', 'pharmacy'):
        for f in sorted(glob.glob(model + '_chapter_Run_*.txt')):
            d = parse(f)
            o = simulate(model, d)
            df = compare(model, d, o)
            print(f, len(d['cases']), 'cases', len(d['tasklog']), 'tasks', 'MATCH' if not df else 'DIFF %d' % len(df))
            for x in df[:6]:
                print('  ', x)
