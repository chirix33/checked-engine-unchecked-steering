"""Simulator for the business-process record documents (standard library only).

Usage: python -I sim.py   (runs factual checks for all chapters, prints report)
Import: from sim import load_doc, load_chapter, simulate
"""
import re, heapq, os, copy

HERE = os.path.dirname(os.path.abspath(__file__))
DAYS = {'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6}


def read(name):
    with open(os.path.join(HERE, name), encoding='utf-8') as f:
        return f.read()


def hm(s):
    h, m = s.split(':')
    return int(h) * 3600 + int(m) * 60


def to_micro(s):
    """decimal string -> integer millionths (exact)."""
    if '.' in s:
        a, b = s.split('.')
    else:
        a, b = s, ''
    b = (b + '000000')[:6]
    return int(a) * 1000000 + int(b)


# ---------------------------------------------------------------- front matter
def load_doc(fm_name):
    txt = read(fm_name)
    flat = ' '.join(txt.split())
    doc = {'name': fm_name}
    # workers
    wpart = flat[flat.index('Workers.') + len('Workers.'):flat.index('Process.')]
    pools = {}
    for m in re.finditer(r'([A-Za-z][A-Za-z ]*?): (\d+) workers \((.+?)_(\d+) to (.+?)_(\d+)\), working (\w+) to (\w+) (\d\d:\d\d) to (\d\d:\d\d)\.', wpart):
        name = m.group(1).strip()
        n = int(m.group(2))
        assert m.group(3) == name and m.group(5) == name, m.group(0)
        assert int(m.group(4)) == 0 and int(m.group(6)) == n - 1
        d0, d1 = DAYS[m.group(7)], DAYS[m.group(8)]
        pools[name] = {'n': n, 'days': list(range(d0, d1 + 1)), 'open': hm(m.group(9)), 'close': hm(m.group(10))}
    doc['pools'] = pools
    # process
    ppart = flat[flat.index('Process.') + len('Process.'):flat.index('Rules.')].strip()
    stmts = re.split(r'\.\s+(?=[A-Z])', ppart)
    stmts = [s.rstrip('.') for s in stmts]
    nodes = {}
    start = None
    for s in stmts:
        m = re.match(r'^A new case goes to (.+)$', s)
        if m:
            start = m.group(1); continue
        m = re.match(r'^Decision (\w+): (.+)$', s)
        if m:
            routes = []
            for r in m.group(2).split('; '):
                mm = re.match(r'^route (\S+?)(?: \((.*)\))?, probability ([\d.]+), to (.+)$', r)
                assert mm, r
                routes.append({'id': mm.group(1), 'label': mm.group(2), 'p': to_micro(mm.group(3)), 'to': mm.group(4)})
            nodes[m.group(1)] = {'kind': 'decision', 'routes': routes}
            continue
        m = re.match(r'^Split (\w+): starts all of these at the same time: (.+)$', s)
        if m:
            nodes[m.group(1)] = {'kind': 'split', 'to': m.group(2).split(', ')}
            continue
        m = re.match(r'^Wait (\w+) \(published delay (.*)\): then (.+)$', s)
        if m:
            nodes[m.group(1)] = {'kind': 'wait', 'pub': m.group(2), 'to': m.group(3)}
            continue
        m = re.match(r'^Join (\w+): waits until all its (\d+) incoming paths have finished, then (.+)$', s)
        if m:
            nodes[m.group(1)] = {'kind': 'join', 'n': int(m.group(2)), 'to': m.group(3)}
            continue
        m = re.match(r'^(.+?) \(pool (.+?), published work (.*)\): then (.+)$', s)
        if m:
            nodes[m.group(1)] = {'kind': 'act', 'pool': m.group(2), 'pub': m.group(3), 'to': m.group(4)}
            continue
        raise ValueError('unparsed statement: ' + s)
    doc['nodes'] = nodes
    doc['start'] = start
    for k, v in nodes.items():
        tos = v.get('to') if v['kind'] != 'decision' else [r['to'] for r in v['routes']]
        if isinstance(tos, str):
            tos = [tos]
        for t in tos:
            assert t == 'End' or t in nodes, (k, t)
        if v['kind'] == 'act':
            assert v['pool'] in pools, v
    return doc


# ---------------------------------------------------------------- chapter
def load_chapter(ch_name, doc):
    lines = read(ch_name).splitlines()
    secs = {}
    cur = None
    for ln in lines:
        m = re.match(r'^Run \d+: (.+)$', ln.strip())
        if m:
            cur = m.group(1); secs[cur] = []; continue
        if cur:
            secs[cur].append(ln.strip())
    acts = sorted([k for k, v in doc['nodes'].items() if v['kind'] == 'act'], key=len, reverse=True)
    pools = sorted(doc['pools'], key=len, reverse=True)

    def records(sec):
        text = ' '.join(l for l in secs[sec] if not l.startswith('case '))
        parts = re.split(r'(?=\bc\d{4}\b)', text)
        return [p.strip() for p in parts if p.strip()]

    ch = {'name': ch_name}
    cases = {}
    for r in records('Cases'):
        c, a, e = r.split()
        cases[c] = {'arrival': int(a), 'end': int(e)}
    ch['cases'] = cases

    def split_act(rest):
        for a in acts:
            if rest == a or rest.startswith(a + ' '):
                return a, rest[len(a):].split()
        raise ValueError('no activity in: ' + rest)

    work = {}
    act_order = []
    for r in records('Work plan'):
        c, rest = r.split(' ', 1)
        a, nums = split_act(rest)
        work[(c, a)] = [int(x) for x in nums]
        if a not in act_order:
            act_order.append(a)
    # verify each case lists activities in same order
    per_case = {}
    for (c, a) in work:
        per_case.setdefault(c, []).append(a)
    for c, lst in per_case.items():
        assert lst == act_order, (ch_name, c)
    ch['work'] = work
    ch['act_order'] = act_order
    waits = {}
    for r in records('Wait plan'):
        t = r.split()
        waits[(t[0], t[1])] = [int(x) for x in t[2:]]
    ch['waits'] = waits
    draws = {}
    for r in records('Route draws'):
        t = r.split()
        draws[(t[0], t[1])] = [to_micro(x) for x in t[2:]]
    ch['draws'] = draws
    tl = []
    for r in records('Task log'):
        c, rest = r.split(' ', 1)
        a, toks = split_act(rest)
        visit, en, st, et = (int(x) for x in toks[:4])
        worker = ' '.join(toks[4:])
        tl.append((c, a, visit, en, st, et, worker))
    ch['task_log'] = tl
    wl = []
    for r in records('Wait log'):
        t = r.split()
        wl.append((t[0], t[1], int(t[2]), int(t[3]), int(t[4])))
    ch['wait_log'] = wl
    dl = []
    for r in records('Decision log'):
        t = r.split()
        dl.append((t[0], t[1], int(t[2]), int(t[3]), t[4]))
    ch['dec_log'] = dl
    return ch


# ---------------------------------------------------------------- calendar
class Worker:
    def __init__(self, pool, idx, spec, unavail=()):
        self.name = '%s_%d' % (pool, idx)
        self.idx = idx
        self.spec = spec
        self.unavail = sorted(unavail)  # list of (a, b)
        self.free = 0          # time the worker is free
        self.free_since = 0    # for 'free for longest' ties

    def _shift(self, t):
        """working shift interval [a,b) that contains t or the next one after t (ignoring unavailability)."""
        sp = self.spec
        d = t // 86400
        while True:
            if (d % 7) in sp['days']:
                a = d * 86400 + sp['open']; b = d * 86400 + sp['close']
                if b > t:
                    return max(a, t), b
            d += 1

    def next_working(self, t):
        """first instant >= t in working time; returns (t0, end of contiguous working stretch)."""
        while True:
            a, b = self._shift(t)
            moved = False
            for (ua, ub) in self.unavail:
                if ua <= a < ub:
                    t = ub; moved = True; break
            if moved:
                continue
            # cut b at the start of any unavailability inside (a, b)
            for (ua, ub) in self.unavail:
                if a < ua < b:
                    b = ua
            return a, b

    def finish(self, start, work):
        t = start
        rem = work
        if rem == 0:
            return start
        while True:
            a, b = self.next_working(t)
            if b - a >= rem:
                return a + rem
            rem -= (b - a)
            t = b


# ---------------------------------------------------------------- simulation
def simulate(doc, ch, change=None):
    """change: dict with optional keys
       work: {(case, act, visit): value}
       wait: {(case, wait, visit): value}
       draw: {(case, dec, visit): micro}
       prob: {dec: [micro per route]}
       remove_cases: set
       unavail: {worker_name: [(a,b)]}
       extra_workers: {pool: k}
    """
    change = change or {}
    nodes = copy.deepcopy(doc['nodes'])
    for d, ps in change.get('prob', {}).items():
        for r, p in zip(nodes[d]['routes'], ps):
            r['p'] = p
    act_rank = {a: i for i, a in enumerate(ch['act_order'])}
    cases = {c: v['arrival'] for c, v in ch['cases'].items() if c not in change.get('remove_cases', set())}
    workers = {}
    for pool, spec in doc['pools'].items():
        n = spec['n'] + change.get('extra_workers', {}).get(pool, 0)
        workers[pool] = [Worker(pool, i, spec, change.get('unavail', {}).get('%s_%d' % (pool, i), ())) for i in range(n)]

    def work_of(c, a, v):
        key = (c, a, v)
        if key in change.get('work', {}):
            return change['work'][key]
        vals = ch['work'][(c, a)]
        if v > len(vals):
            raise RuntimeError('no work plan value for %s %s visit %d' % key)
        return vals[v - 1]

    def wait_of(c, w, v):
        key = (c, w, v)
        if key in change.get('wait', {}):
            return change['wait'][key]
        vals = ch['waits'][(c, w)]
        if v > len(vals):
            raise RuntimeError('no wait plan value for %s %s visit %d' % key)
        return vals[v - 1]

    def draw_of(c, d, v):
        key = (c, d, v)
        if key in change.get('draw', {}):
            return change['draw'][key]
        vals = ch['draws'][(c, d)]
        if v > len(vals):
            raise RuntimeError('no route draw for %s %s visit %d' % key)
        return vals[v - 1]

    visits = {}
    joincount = {}
    task_log, wait_log, dec_log = [], [], []
    ends = {}
    pending = []
    heap = []
    seq = [0]

    def push(t, kind, data):
        seq[0] += 1
        heapq.heappush(heap, (t, seq[0], kind, data))

    def reach(c, node, t):
        if node == 'End':
            ends[c] = max(ends.get(c, t), t)
            return
        nd = nodes[node]
        k = nd['kind']
        if k in ('act', 'wait', 'decision'):
            visits[(c, node)] = visits.get((c, node), 0) + 1
            v = visits[(c, node)]
        if k == 'act':
            pending.append((t, cases[c], c, act_rank[node], v, node))
        elif k == 'wait':
            dly = wait_of(c, node, v)
            wait_log.append((c, node, v, t, t + dly))
            push(t + dly, 'waitend', (c, node))
        elif k == 'decision':
            dr = draw_of(c, node, v)
            tot = 0
            chosen = None
            for r in nd['routes']:
                tot += r['p']
                if tot > dr:
                    chosen = r; break
            if chosen is None:
                raise RuntimeError('no route for draw %s %s %d' % (c, node, v))
            dec_log.append((c, node, v, t, chosen['id']))
            reach(c, chosen['to'], t)
        elif k == 'split':
            for x in nd['to']:
                reach(c, x, t)
        elif k == 'join':
            joincount[(c, node)] = joincount.get((c, node), 0) + 1
            if joincount[(c, node)] == nd['n']:
                joincount[(c, node)] = 0
                reach(c, nd['to'], t)

    for c, a in cases.items():
        push(a, 'arrive', c)

    while heap:
        t = heap[0][0]
        while heap and heap[0][0] == t:
            _, _, kind, data = heapq.heappop(heap)
            if kind == 'arrive':
                reach(data, doc['start'], t)
            elif kind == 'waitend':
                c, w = data
                reach(c, nodes[w]['to'], t)
            elif kind == 'taskend':
                c, a = data
                reach(c, nodes[a]['to'], t)
        if pending:
            pending.sort()
            for (en, arr, c, rank, v, a) in pending:
                pool = nodes[a]['pool']
                best = None
                for w in workers[pool]:
                    s, _ = w.next_working(max(en, w.free))
                    key = (s, w.free_since, w.idx)
                    if best is None or key < best[0]:
                        best = (key, w, s)
                _, w, s = best
                e = w.finish(s, work_of(c, a, v))
                w.free = e
                w.free_since = e
                task_log.append((c, a, v, en, s, e, w.name))
                push(e, 'taskend', (c, a))
            pending.clear()
    return {'ends': ends, 'task_log': task_log, 'wait_log': wait_log, 'dec_log': dec_log, 'cases': cases}


def compare(ch, res):
    diffs = []
    for c, v in ch['cases'].items():
        if res['ends'].get(c) != v['end']:
            diffs.append('case %s end printed %s sim %s' % (c, v['end'], res['ends'].get(c)))
    for key, name in (('task_log', 'task'), ('wait_log', 'wait'), ('dec_log', 'decision')):
        a = sorted(ch[key]); b = sorted(res[key])
        sa, sb = set(a), set(b)
        for x in a:
            if x not in sb:
                diffs.append('%s row printed but not simulated: %s' % (name, x))
        for x in b:
            if x not in sa:
                diffs.append('%s row simulated but not printed: %s' % (name, x))
        if len(a) != len(b):
            diffs.append('%s rows count printed %d sim %d' % (name, len(a), len(b)))
    return diffs


CHAPTERS = [
    ('loan_policyP_front_matter.txt', 'loan_policyP_chapter_Run_13.txt'),
    ('loan_policyP_front_matter.txt', 'loan_policyP_chapter_Run_14.txt'),
    ('loan_policyH_front_matter.txt', 'loan_policyH_chapter_Run_15.txt'),
    ('loan_policyH_front_matter.txt', 'loan_policyH_chapter_Run_16.txt'),
    ('pharmacy_policyP_front_matter.txt', 'pharmacy_policyP_chapter_Run_13.txt'),
    ('pharmacy_policyP_front_matter.txt', 'pharmacy_policyP_chapter_Run_14.txt'),
    ('pharmacy_policyH_front_matter.txt', 'pharmacy_policyH_chapter_Run_15.txt'),
    ('pharmacy_policyH_front_matter.txt', 'pharmacy_policyH_chapter_Run_16.txt'),
]

if __name__ == '__main__':
    for fm, chn in CHAPTERS:
        doc = load_doc(fm)
        ch = load_chapter(chn, doc)
        res = simulate(doc, ch)
        d = compare(ch, res)
        print('%-40s cases=%d tasks=%d waits=%d decs=%d  %s' % (chn, len(ch['cases']), len(ch['task_log']), len(ch['wait_log']), len(ch['dec_log']), 'EXACT' if not d else 'DIFF %d' % len(d)))
        for x in d[:15]:
            print('    ', x)
