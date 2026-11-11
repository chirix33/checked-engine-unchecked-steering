import re, heapq, json, sys, glob
DAY = 86400


def parse_chapter(path):
    txt = open(path, encoding='utf-8').read()
    run = re.search(r'Run (\d+): Cases', txt).group(1)
    names = ['Cases', 'Work plan', 'Wait plan', 'Route draws', 'Task log', 'Wait log', 'Decision log']
    pos = sorted((txt.index('Run %s: %s' % (run, n)), n) for n in names)
    secs = {}
    for i, (p, n) in enumerate(pos):
        e = pos[i + 1][0] if i + 1 < len(pos) else len(txt)
        body = txt[p:e].split('\n', 1)[1]
        body = re.sub(r'case (activity|wait|decision) visit 1(?: visit \d+)*', ' ', body)
        body = re.sub(r'case activity visit enabled start end worker', ' ', body)
        body = re.sub(r'case wait visit start end', ' ', body)
        body = re.sub(r'case decision visit time route', ' ', body)
        body = re.sub(r'case arrival end', ' ', body)
        secs[n] = ' '.join(body.split())
    d = {}
    d['cases'] = {c: (int(a), int(b)) for c, a, b in re.findall(r'(c\d{4}) (\d+) (\d+)', secs['Cases'])}
    wp = {}
    order = []
    for c, name, nums in re.findall(r'(c\d{4}) ([A-Za-z][^\d]*?) ((?:\d+ ?)+?)(?= c\d{4} |$)', secs['Work plan']):
        wp[(c, name.strip())] = [int(x) for x in nums.split()]
        if name.strip() not in order:
            order.append(name.strip())
    d['work'] = wp
    d['actorder'] = order
    wt = {}
    for c, name, nums in re.findall(r'(c\d{4}) (W\d+) ((?:\d+ ?)+?)(?= c\d{4} |$)', secs['Wait plan']):
        wt[(c, name)] = [int(x) for x in nums.split()]
    d['wait'] = wt
    dr = {}
    for c, name, nums in re.findall(r'(c\d{4}) (D\d+) ((?:\d\.\d+ ?)+?)(?= c\d{4} |$)', secs['Route draws']):
        dr[(c, name)] = [float(x) for x in nums.split()]
    d['draw'] = dr
    d['tasklog'] = [(c, n.strip(), int(v), int(e), int(s), int(en), w) for c, n, v, e, s, en, w in
                    re.findall(r'(c\d{4}) ([A-Za-z][^\d]*?) (\d+) (\d+) (\d+) (\d+) ([A-Za-z ]+_\d+)', secs['Task log'])]
    d['waitlog'] = [(c, w, int(v), int(s), int(e)) for c, w, v, s, e in
                    re.findall(r'(c\d{4}) (W\d+) (\d+) (\d+) (\d+)', secs['Wait log'])]
    d['declog'] = [(c, w, int(v), int(t), r) for c, w, v, t, r in
                   re.findall(r'(c\d{4}) (D\d+) (\d+) (\d+) (D\d+-\w+)', secs['Decision log'])]
    return d


H = 3600
HOURS = {
    'loan': {'Applicant': (20, 0, 24 * H - 60, 7), 'Senior Officer': (3, 9 * H, 17 * H, 5),
             'Appraiser': (2, 9 * H, 17 * H, 5), 'AML Investigator': (4, 9 * H, 17 * H, 5),
             'Loan Officer': (9, 9 * H, 17 * H, 5), 'Clerk': (9, 9 * H, 17 * H, 5)},
    'pharmacy': {'Pharmacy System': (1, 8 * H, 20 * H, 5), 'Technician': (8, 8 * H, 20 * H, 5),
                 'Pharmacist': (1, 8 * H, 20 * H, 5)},
}


def T(pool, nxt):
    return ('task', pool, nxt)


GRAPH = {
    'loan': {
        'start': 'Check application form completeness',
        'Check application form completeness': T('Clerk', 'D1'),
        'D1': ('dec', [('D1-a', 0.2, 'Return application back to applicant'), ('D1-b', 0.8, 'S1')]),
        'Return application back to applicant': T('Clerk', 'W1'),
        'W1': ('wait', 'Applicant completes form'),
        'Applicant completes form': T('Applicant', 'Check application form completeness'),
        'S1': ('split', ['Appraise property', 'Check credit history', 'AML Check']),
        'Appraise property': T('Appraiser', 'J1'), 'AML Check': T('AML Investigator', 'J1'),
        'Check credit history': T('Clerk', 'J1'),
        'J1': ('join', 3, 'W2'),
        'W2': ('wait', 'Assess loan risk'),
        'Assess loan risk': T('Loan Officer', 'D2'),
        'D2': ('dec', [('D2-a', 0.5, 'Reject application'), ('D2-b', 0.5, 'Design loan offer')]),
        'Reject application': T('Clerk', 'End'),
        'Design loan offer': T('Loan Officer', 'Approve Loan Offer'),
        'Approve Loan Offer': T('Senior Officer', 'D3'),
        'D3': ('dec', [('D3-a', 0.2, 'Design loan offer'), ('D3-b', 0.8, 'S2')]),
        'S2': ('split', ['Prepare acceptance pack', 'Prepare home insurance quote']),
        'Prepare acceptance pack': T('Loan Officer', 'Approve and send acceptance pack'),
        'Prepare home insurance quote': T('Clerk', 'Approve and post home insurance quote'),
        'Approve and send acceptance pack': T('Loan Officer', 'J2'),
        'Approve and post home insurance quote': T('Loan Officer', 'J2'),
        'J2': ('join', 2, 'D4'),
        'D4': ('dec', [('D4-a', 0.5, 'W3'), ('D4-b', 0.5, 'Consider re-design loan offer')]),
        'Consider re-design loan offer': T('Senior Officer', 'D5'),
        'W3': ('wait', 'Approve application'),
        'D5': ('dec', [('D5-a', 0.45, 'Cancel application'), ('D5-b', 0.55, 'Design loan offer')]),
        'Approve application': T('Clerk', 'End'), 'Cancel application': T('Clerk', 'End'),
    },
    'pharmacy': {
        'start': 'Process drop-off',
        'Process drop-off': T('Technician', 'W1'),
        'W1': ('wait', 'Enter prescription details'),
        'Enter prescription details': T('Technician', 'Check if refill is allowed'),
        'Check if refill is allowed': T('Pharmacy System', 'D1'),
        'D1': ('dec', [('D1-a', 0.94, 'Check DUR'), ('D1-b', 0.06, 'Contact Doctor about refill')]),
        'Contact Doctor about refill': T('Technician', 'D2'),
        'D2': ('dec', [('D2-a', 0.99, 'Check DUR'), ('D2-b', 0.01, 'End')]),
        'Check DUR': T('Pharmacy System', 'D3'),
        'D3': ('dec', [('D3-a', 0.8, 'Check Insurance'), ('D3-b', 0.2, 'D4')]),
        'D4': ('dec', [('D4-a', 0.95, 'Resolve DUR manually'), ('D4-b', 0.05, 'Contact customer / doctor')]),
        'Check Insurance': T('Pharmacy System', 'D5'),
        'Contact customer / doctor': T('Pharmacy System', 'Check Insurance'),
        'Resolve DUR manually': T('Pharmacist', 'Check Insurance'),
        'D5': ('dec', [('D5-a', 0.83, 'D6'), ('D5-b', 0.17, 'Resolve insurance issues manually')]),
        'Resolve insurance issues manually': T('Technician', 'D6'),
        'D6': ('dec', [('D6-a', 0.07, 'W3'), ('D6-b', 0.93, 'W2')]),
        'W2': ('wait', 'Pack the drugs (Production)'),
        'Pack the drugs (Production)': T('Technician', 'Check for Quality Assurance'),
        'W3': ('wait', 'Pick-up'),
        'Check for Quality Assurance': T('Pharmacist', 'D7'),
        'Pick-up': T('Technician', 'End'),
        'D7': ('dec', [('D7-a', 0.05, 'D6'), ('D7-b', 0.95, 'W3')]),
    }}


class Worker:
    def __init__(s, o, c, nd, unav):
        s.o, s.c, s.nd = o, c, nd
        s.free = 0
        s.unav = sorted(unav)

    def next_work(s, t):
        """first working window piece (lo,hi) with hi>lo and hi>t, lo>=t"""
        while True:
            day = t // DAY
            if day % 7 < s.nd:
                a = day * DAY + s.o
                b = day * DAY + s.c
                if t < b:
                    lo = max(t, a)
                    hi = b
                    moved = True
                    while moved:
                        moved = False
                        for ua, ub in s.unav:
                            if ua <= lo < ub:
                                lo = ub
                                moved = True
                    if lo < hi:
                        for ua, ub in s.unav:
                            if lo < ua < hi:
                                hi = ua
                        return lo, hi
                    t = max(hi, lo)
                    continue
            t = (day + 1) * DAY

    def run(s, start, work):
        t = start
        rem = work
        while True:
            lo, hi = s.next_work(t)
            if rem <= hi - lo:
                return lo + rem
            rem -= hi - lo
            t = hi

    def earliest(s, t):
        return s.next_work(max(t, s.free))[0]


def simulate(d, proc, mods=None):
    mods = mods or {}
    g = GRAPH[proc]
    hours = HOURS[proc]
    cases = dict(d['cases'])
    for c in mods.get('drop', []):
        cases.pop(c, None)
    work = {k: list(v) for k, v in d['work'].items()}
    waitp = {k: list(v) for k, v in d['wait'].items()}
    draw = {k: list(v) for k, v in d['draw'].items()}
    for (c, a, v), val in mods.get('work', {}).items():
        work[(c, a)][v - 1] = val
    for (c, a, v), val in mods.get('wait', {}).items():
        waitp[(c, a)][v - 1] = val
    for (c, a, v), val in mods.get('draw', {}).items():
        draw[(c, a)][v - 1] = val
    probs = {k: list(v[1]) for k, v in g.items() if isinstance(v, tuple) and v[0] == 'dec'}
    for k, pl in mods.get('probs', {}).items():
        probs[k] = [(r, pl[r], n) for r, _, n in probs[k]]
    unav = mods.get('unavail', [])
    workers = {}
    for pool, (n, o, c, nd) in hours.items():
        workers[pool] = [Worker(o, c, nd, [(a, b) for (p, cnt, a, b) in unav if p == pool and i < cnt]) for i in range(n)]
    actid = {a: i for i, a in enumerate(d['actorder'])}
    arr = {c: a for c, (a, _) in cases.items()}
    heap = []
    visits = {}
    joins = {}
    out = dict(ends={}, tasks=[], waits=[], decs=[])

    def vis(c, n):
        visits[(c, n)] = visits.get((c, n), 0) + 1
        return visits[(c, n)]

    def enter(c, n, t):
        while True:
            if n == 'End':
                out['ends'][c] = max(out['ends'].get(c, 0), t)
                return
            node = g[n]
            k = node[0]
            if k == 'task':
                v = vis(c, n)
                heapq.heappush(heap, (t, arr[c], c, actid[n], v, n))
                return
            if k == 'wait':
                v = vis(c, n)
                dly = waitp[(c, n)][v - 1]
                out['waits'].append((c, n, v, t, t + dly))
                t += dly
                n = node[1]
                continue
            if k == 'dec':
                v = vis(c, n)
                dv = draw[(c, n)][v - 1]
                tot = 0
                ch = None
                for r, p, nx in probs[n]:
                    tot += p
                    if tot > dv + 1e-9:
                        ch = (r, nx)
                        break
                if ch is None:
                    ch = (probs[n][-1][0], probs[n][-1][2])
                out['decs'].append((c, n, v, t, ch[0]))
                n = ch[1]
                continue
            if k == 'split':
                vis(c, n)
                for x in node[1]:
                    enter(c, x, t)
                return
            if k == 'join':
                key = (c, n)
                cnt, mx = joins.get(key, (0, 0))
                cnt += 1
                mx = max(mx, t)
                if cnt < node[1]:
                    joins[key] = (cnt, mx)
                    return
                joins[key] = (0, 0)
                vis(c, n)
                t = mx
                n = node[2]
                continue

    for c in arr:
        enter(c, g['start'], arr[c])
    while heap:
        en, ar, c, ai, v, n = heapq.heappop(heap)
        pool = g[n][1]
        w = work[(c, n)][v - 1]
        best = None
        for i, wk in enumerate(workers[pool]):
            key = (wk.earliest(en), wk.free, i)
            if best is None or key < best:
                best = key
        st, _, i = best
        wk = workers[pool][i]
        e = wk.run(st, w)
        wk.free = e
        out['tasks'].append((c, n, v, en, st, e, '%s_%d' % (pool, i)))
        enter(c, g[n][2], e)
    return out


def compare(d, out):
    res = {}
    res['ends'] = sorted(set((c, a[1]) for c, a in d['cases'].items()) ^ set(out['ends'].items()))
    res['tasks'] = sorted(set(d['tasklog']) ^ set(out['tasks']))
    res['waits'] = sorted(set(d['waitlog']) ^ set(out['waits']))
    res['decs'] = sorted(set(d['declog']) ^ set(out['decs']))
    return res


if __name__ == '__main__':
    for f in sorted(glob.glob('*_chapter_Run_*.txt')):
        proc = f.split('_')[0]
        d = parse_chapter(f)
        o = simulate(d, proc)
        r = compare(d, o)
        print(f, len(d['cases']), len(d['tasklog']), len(o['tasks']), len(d['waitlog']), len(d['declog']),
              {k: len(v) for k, v in r.items()})
        if '-v' in sys.argv:
            for k, v in r.items():
                print(k, v[:6])
