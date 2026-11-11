"""Own simulator for the blind policy check (standard library only).

Usage: python -I sim.py   (run from this folder)
Reproduces every chapter, then answers questions.json -> answers.json, results.txt
"""
import re, json, heapq, os
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
DAY = 86400
WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

# ---------------- process graphs (hand-encoded; checked against each front matter text) -------------
# node kinds: ('act', name) ('wait', W) ('dec', D) ('split', [nodes]) ('join', J) ('end',)
LOAN = {
    'start': ('act', 'Check application form completeness'),
    'next': {
        ('act', 'Check application form completeness'): ('dec', 'D1'),
        ('act', 'Return application back to applicant'): ('wait', 'W1'),
        ('wait', 'W1'): ('act', 'Applicant completes form'),
        ('act', 'Applicant completes form'): ('act', 'Check application form completeness'),
        ('split', 'S1'): [('act', 'Appraise property'), ('act', 'Check credit history'), ('act', 'AML Check')],
        ('act', 'Appraise property'): ('join', 'J1'),
        ('act', 'AML Check'): ('join', 'J1'),
        ('act', 'Check credit history'): ('join', 'J1'),
        ('join', 'J1'): ('wait', 'W2'),
        ('wait', 'W2'): ('act', 'Assess loan risk'),
        ('act', 'Assess loan risk'): ('dec', 'D2'),
        ('act', 'Reject application'): ('end',),
        ('act', 'Design loan offer'): ('act', 'Approve Loan Offer'),
        ('act', 'Approve Loan Offer'): ('dec', 'D3'),
        ('split', 'S2'): [('act', 'Prepare acceptance pack'), ('act', 'Prepare home insurance quote')],
        ('act', 'Prepare acceptance pack'): ('act', 'Approve and send acceptance pack'),
        ('act', 'Prepare home insurance quote'): ('act', 'Approve and post home insurance quote'),
        ('act', 'Approve and send acceptance pack'): ('join', 'J2'),
        ('act', 'Approve and post home insurance quote'): ('join', 'J2'),
        ('join', 'J2'): ('dec', 'D4'),
        ('act', 'Consider re-design loan offer'): ('dec', 'D5'),
        ('wait', 'W3'): ('act', 'Approve application'),
        ('act', 'Approve application'): ('end',),
        ('act', 'Cancel application'): ('end',),
    },
    'joins': {'J1': 3, 'J2': 2},
    'routes': {
        'D1': [('D1-a', ('act', 'Return application back to applicant')), ('D1-b', ('split', 'S1'))],
        'D2': [('D2-a', ('act', 'Reject application')), ('D2-b', ('act', 'Design loan offer'))],
        'D3': [('D3-a', ('act', 'Design loan offer')), ('D3-b', ('split', 'S2'))],
        'D4': [('D4-a', ('wait', 'W3')), ('D4-b', ('act', 'Consider re-design loan offer'))],
        'D5': [('D5-a', ('act', 'Cancel application')), ('D5-b', ('act', 'Design loan offer'))],
    },
    'pools': {
        'Check application form completeness': 'Clerk', 'Return application back to applicant': 'Clerk',
        'Appraise property': 'Appraiser', 'AML Check': 'AML Investigator', 'Check credit history': 'Clerk',
        'Applicant completes form': 'Applicant', 'Assess loan risk': 'Loan Officer',
        'Reject application': 'Clerk', 'Design loan offer': 'Loan Officer', 'Approve Loan Offer': 'Senior Officer',
        'Prepare acceptance pack': 'Loan Officer', 'Prepare home insurance quote': 'Clerk',
        'Approve and send acceptance pack': 'Loan Officer', 'Approve and post home insurance quote': 'Loan Officer',
        'Consider re-design loan offer': 'Senior Officer', 'Approve application': 'Clerk',
        'Cancel application': 'Clerk',
    },
}
PHARM = {
    'start': ('act', 'Process drop-off'),
    'next': {
        ('act', 'Process drop-off'): ('wait', 'W1'),
        ('wait', 'W1'): ('act', 'Enter prescription details'),
        ('act', 'Enter prescription details'): ('act', 'Check if refill is allowed'),
        ('act', 'Check if refill is allowed'): ('dec', 'D1'),
        ('act', 'Contact Doctor about refill'): ('dec', 'D2'),
        ('act', 'Check DUR'): ('dec', 'D3'),
        ('act', 'Check Insurance'): ('dec', 'D5'),
        ('act', 'Contact customer / doctor'): ('act', 'Check Insurance'),
        ('act', 'Resolve DUR manually'): ('act', 'Check Insurance'),
        ('act', 'Resolve insurance issues manually'): ('dec', 'D6'),
        ('wait', 'W2'): ('act', 'Pack the drugs (Production)'),
        ('act', 'Pack the drugs (Production)'): ('act', 'Check for Quality Assurance'),
        ('wait', 'W3'): ('act', 'Pick-up'),
        ('act', 'Check for Quality Assurance'): ('dec', 'D7'),
        ('act', 'Pick-up'): ('end',),
    },
    'joins': {},
    'routes': {
        'D1': [('D1-a', ('act', 'Check DUR')), ('D1-b', ('act', 'Contact Doctor about refill'))],
        'D2': [('D2-a', ('act', 'Check DUR')), ('D2-b', ('end',))],
        'D3': [('D3-a', ('act', 'Check Insurance')), ('D3-b', ('dec', 'D4'))],
        'D4': [('D4-a', ('act', 'Resolve DUR manually')), ('D4-b', ('act', 'Contact customer / doctor'))],
        'D5': [('D5-a', ('dec', 'D6')), ('D5-b', ('act', 'Resolve insurance issues manually'))],
        'D6': [('D6-a', ('wait', 'W3')), ('D6-b', ('wait', 'W2'))],
        'D7': [('D7-a', ('dec', 'D6')), ('D7-b', ('wait', 'W3'))],
    },
    'pools': {
        'Process drop-off': 'Technician', 'Enter prescription details': 'Technician',
        'Check if refill is allowed': 'Pharmacy System', 'Contact Doctor about refill': 'Technician',
        'Check DUR': 'Pharmacy System', 'Check Insurance': 'Pharmacy System',
        'Contact customer / doctor': 'Pharmacy System', 'Resolve DUR manually': 'Pharmacist',
        'Resolve insurance issues manually': 'Technician', 'Pack the drugs (Production)': 'Technician',
        'Check for Quality Assurance': 'Pharmacist', 'Pick-up': 'Technician',
    },
}


def norm(t):
    return re.sub(r'\s+', ' ', t)


def load_front(fn, proc):
    """Parse workers and decision probabilities from the document's own front matter;
    verify the hand-encoded graph against its text."""
    t = norm(open(os.path.join(HERE, fn), encoding='utf-8').read())
    ws = t[t.index('Workers.'):t.index('Process.')]
    pools = {}
    for m in re.finditer(r'([A-Z][A-Za-z ]+?): (\d+) workers \(([^)]*)\), working (\w+) to (\w+) (\d\d):(\d\d) to (\d\d):(\d\d)', ws):
        name = m.group(1).strip()
        if name.startswith('Workers. '):
            name = name[len('Workers. '):]
        n = int(m.group(2))
        d0, d1 = WEEKDAYS.index(m.group(4)), WEEKDAYS.index(m.group(5))
        open_s = int(m.group(6)) * 3600 + int(m.group(7)) * 60
        close_s = int(m.group(8)) * 3600 + int(m.group(9)) * 60
        pools[name] = {'n': n, 'days': list(range(d0, d1 + 1)), 'open': open_s, 'close': close_s}
    pt = t[t.index('Process.'):t.index('Rules.')].strip()
    probs = {}
    for m in re.finditer(r'Decision (D\d+): (.*?)(?=\. [A-Z]|\.$)', pt):
        d = m.group(1)
        probs[d] = {}
        for r in re.finditer(r'route (D\d+-[a-z]).*?probability ([0-9.]+)', m.group(2)):
            probs[d][r.group(1)] = Decimal(r.group(2))
    # checks
    for act, pool in proc['pools'].items():
        assert f'{act} (pool {pool},' in pt, (fn, act)
        assert pool in pools, (fn, pool)
    for d, rs in proc['routes'].items():
        assert set(probs[d]) == {r for r, _ in rs}, (fn, d, probs.get(d))
        for r, tgt in rs:
            name = tgt[1] if len(tgt) > 1 else 'End'
            seg = re.search(r'route ' + r + r'.*?probability [0-9.]+, to ([^;]*?)(?:;|$)', m_text(pt, d))
            assert seg and seg.group(1).strip().rstrip('.') == name, (fn, d, r, seg and seg.group(1), name)
    return pools, probs


def m_text(pt, d):
    m = re.search(r'Decision ' + d + r': (.*?)(?=\. [A-Z]|\.$)', pt)
    return m.group(1)


# ---------------- chapter parsing ----------------
SECTIONS = ['Cases', 'Work plan', 'Wait plan', 'Route draws', 'Task log', 'Wait log', 'Decision log']


def records(lines):
    toks = []
    for ln in lines:
        if ln.startswith('case '):
            continue
        toks += ln.split()
    recs, cur = [], None
    for tk in toks:
        if re.fullmatch(r'c\d{4}', tk):
            if cur:
                recs.append(cur)
            cur = [tk]
        else:
            cur.append(tk)
    if cur:
        recs.append(cur)
    return recs


def isint(s):
    return re.fullmatch(r'-?\d+', s) is not None


def isnum(s):
    return re.fullmatch(r'-?\d+(\.\d+)?', s) is not None


def load_chapter(fn):
    lines = open(os.path.join(HERE, fn), encoding='utf-8').read().splitlines()
    sec, cur = {}, None
    for ln in lines:
        m = re.fullmatch(r'Run \d+: (.+)', ln.strip())
        if m and m.group(1) in SECTIONS:
            cur = m.group(1)
            sec[cur] = []
            continue
        if cur:
            sec[cur].append(ln)
    ch = {}
    ch['cases'] = {r[0]: (int(r[1]), int(r[2])) for r in records(sec['Cases'])}

    def plan(lines, conv):
        out, order = {}, []
        for r in records(lines):
            i = 1
            while not isnum(r[i]):
                i += 1
            name = ' '.join(r[1:i])
            out[(r[0], name)] = [conv(x) for x in r[i:]]
            if name not in order:
                order.append(name)
        return out, order
    ch['work'], ch['act_order'] = plan(sec['Work plan'], int)
    ch['waits'], _ = plan(sec['Wait plan'], int)
    ch['draws'], _ = plan(sec['Route draws'], Decimal)
    tl = []
    for r in records(sec['Task log']):
        i = 1
        while not isint(r[i]):
            i += 1
        tl.append((r[0], ' '.join(r[1:i]), int(r[i]), int(r[i + 1]), int(r[i + 2]), int(r[i + 3]), ' '.join(r[i + 4:])))
    ch['tasklog'] = tl
    ch['waitlog'] = [(r[0], r[1], int(r[2]), int(r[3]), int(r[4])) for r in records(sec['Wait log'])]
    ch['declog'] = [(r[0], r[1], int(r[2]), int(r[3]), r[4]) for r in records(sec['Decision log'])]
    for r in records(sec['Wait log']):
        assert len(r) == 5, r
    for r in records(sec['Decision log']):
        assert len(r) == 5, r
    return ch


# ---------------- calendar ----------------
class Worker:
    def __init__(self, name, spec, unavail=()):
        self.name = name
        self.idx = int(name.rsplit('_', 1)[1])
        self.spec = spec
        self.unavail = sorted(unavail)
        self.free = None  # time last task ended; None = never used

    def intervals(self, frm):
        """Yield working intervals [a,b) with b > frm, in time order."""
        day = frm // DAY
        while True:
            if (day % 7) in self.spec['days']:
                a, b = day * DAY + self.spec['open'], day * DAY + self.spec['close']
                pieces = [(a, b)]
                for (u0, u1) in self.unavail:
                    np_ = []
                    for (x, y) in pieces:
                        if u1 <= x or u0 >= y:
                            np_.append((x, y))
                        else:
                            if x < u0:
                                np_.append((x, u0))
                            if u1 < y:
                                np_.append((u1, y))
                    pieces = np_
                for (x, y) in pieces:
                    if y > frm:
                        yield (max(x, frm), y)
            day += 1
            if day > frm // DAY + 400:
                raise RuntimeError('no working time')

    def start_at(self, t):
        for a, b in self.intervals(t):
            return a

    def finish(self, s, w):
        rem = w
        if rem == 0:
            return s
        for a, b in self.intervals(s):
            if rem <= b - a:
                return a + rem
            rem -= b - a


# ---------------- simulation ----------------
def simulate(proc, pools_spec, probs, ch, change=None):
    change = change or {}
    cases = dict(ch['cases'])
    for c in change.get('remove', []):
        del cases[c]
    work = dict(ch['work'])
    waits = dict(ch['waits'])
    draws = dict(ch['draws'])
    probs = {d: dict(v) for d, v in probs.items()}
    for (c, a, v, val) in change.get('work', []):
        lst = list(work[(c, a)])
        lst[v - 1] = val
        work[(c, a)] = lst
    for (c, w, v, val) in change.get('wait', []):
        lst = list(waits[(c, w)])
        lst[v - 1] = val
        waits[(c, w)] = lst
    for (c, d, v, val) in change.get('draw', []):
        lst = list(draws[(c, d)])
        lst[v - 1] = val
        draws[(c, d)] = lst
    for d, pr in change.get('probs', {}).items():
        probs[d] = pr
    workers = {}
    for pool, sp in pools_spec.items():
        n = sp['n'] + change.get('extra', {}).get(pool, 0)
        workers[pool] = []
        for i in range(n):
            nm = f'{pool}_{i}'
            workers[pool].append(Worker(nm, sp, change.get('unavail', {}).get(nm, [])))
    act_id = {a: i for i, a in enumerate(ch['act_order'])}

    events = []  # (time, seq, kind, case, payload)
    seq = [0]

    def push(t, kind, case, payload):
        seq[0] += 1
        heapq.heappush(events, (t, seq[0], kind, case, payload))
    visits = {}
    joins = {}
    tasklog, waitlog, declog = [], [], []
    ends = {}
    enabled = []

    def visit(case, key):
        visits[(case, key)] = visits.get((case, key), 0) + 1
        return visits[(case, key)]

    def reach(case, node, t):
        kind = node[0]
        if kind == 'act':
            v = visit(case, node)
            enabled.append((t, cases[case][0], case, act_id[node[1]], v, node[1]))
        elif kind == 'wait':
            v = visit(case, node)
            d = waits[(case, node[1])][v - 1]
            waitlog.append((case, node[1], v, t, t + d))
            push(t + d, 'waitend', case, node)
        elif kind == 'dec':
            v = visit(case, node)
            dr = draws[(case, node[1])][v - 1]
            cum = Decimal(0)
            chosen = None
            for r, tgt in proc['routes'][node[1]]:
                cum += probs[node[1]][r]
                if cum > dr:
                    chosen = (r, tgt)
                    break
            if chosen is None:
                chosen = proc['routes'][node[1]][-1]
                print('WARNING: no route sum > draw', case, node, dr)
            declog.append((case, node[1], v, t, chosen[0]))
            reach(case, chosen[1], t)
        elif kind == 'split':
            for n in proc['next'][node]:
                reach(case, n, t)
        elif kind == 'join':
            k = (case, node[1])
            joins[k] = joins.get(k, 0) + 1
            if joins[k] == proc['joins'][node[1]]:
                joins[k] = 0
                reach(case, proc['next'][node], t)
        elif kind == 'end':
            ends[case] = max(ends.get(case, t), t)

    for c, (arr, _) in cases.items():
        push(arr, 'arrive', c, None)

    while events:
        t = events[0][0]
        while events and events[0][0] == t:
            _, _, kind, case, payload = heapq.heappop(events)
            if kind == 'arrive':
                reach(case, proc['start'], t)
            elif kind == 'taskend':
                reach(case, proc['next'][payload], t)
            elif kind == 'waitend':
                reach(case, proc['next'][payload], t)
        if enabled:
            enabled.sort(key=lambda e: e[:5])
            batch = enabled[:]
            enabled.clear()
            for (te, arr, case, aid, v, act) in batch:
                pool = proc['pools'][act]
                best = None
                for w in workers[pool]:
                    s = w.start_at(max(te, w.free if w.free is not None else te))
                    key = (s, w.free if w.free is not None else -1, w.idx)
                    if best is None or key < best[0]:
                        best = (key, w, s)
                _, w, s = best
                wk = work[(case, act)][v - 1]
                e = w.finish(s, wk)
                w.free = e
                tasklog.append((case, act, v, te, s, e, w.name))
                push(e, 'taskend', case, ('act', act))
    return {'ends': ends, 'tasklog': tasklog, 'waitlog': waitlog, 'declog': declog}


def compare(res, ch):
    diffs = []
    for c, (arr, end) in ch['cases'].items():
        if res['ends'].get(c) != end:
            diffs.append(f'case {c} end recorded {end} simulated {res["ends"].get(c)}')
    for nm, a, b in [('task', ch['tasklog'], res['tasklog']), ('wait', ch['waitlog'], res['waitlog']),
                     ('decision', ch['declog'], res['declog'])]:
        sa, sb = sorted(a), sorted(b)
        if sa != sb:
            A, B = set(a), set(b)
            for x in sorted(A - B)[:10]:
                diffs.append(f'{nm} recorded-only {x}')
            for x in sorted(B - A)[:10]:
                diffs.append(f'{nm} simulated-only {x}')
            if len(a) != len(b):
                diffs.append(f'{nm} rows recorded {len(a)} simulated {len(b)}')
    return diffs


# ---------------- questions ----------------
def parse_question(q, pools_spec):
    s = q['question']
    ch = {}
    m = re.search(r"suppose case (c\d+) needed (\d+) seconds of work for the activity '(.+?)' on visit (\d+)", s)
    if m:
        ch['work'] = [(m.group(1), m.group(3), int(m.group(4)), int(m.group(2)))]
    m = re.search(r'suppose case (c\d+) had never arrived', s)
    if m:
        ch['remove'] = [m.group(1)]
    m = re.search(r'suppose (\d+) ([A-Za-z ]+?) workers? (?:\(([^)]*)\) )?(?:was|were) unavailable from time (\d+) to time (\d+)', s)
    if m:
        n, pool = int(m.group(1)), m.group(2)
        if m.group(3):
            names = [x.strip() for x in m.group(3).split(',')]
        else:
            assert n == pools_spec[pool]['n'], 'unnamed subset of pool'
            names = [f'{pool}_{i}' for i in range(n)]
        assert len(names) == n
        ch['unavail'] = {nm: [(int(m.group(4)), int(m.group(5)))] for nm in names}
    m = re.search(r'the route draw for case (c\d+) at decision (D\d+) on visit (\d+) were ([0-9]+\.[0-9]+)', s)
    if m:
        ch['draw'] = [(m.group(1), m.group(2), int(m.group(3)), Decimal(m.group(4)))]
    m = re.search(r'decision (D\d+) used the probabilities (.*?)\. At', s)
    if m:
        ch['probs'] = {m.group(1): {r: Decimal(p) for r, p in re.findall(r'route (D\d+-[a-z]) ([0-9]+(?:\.[0-9]+)?)', m.group(2))}}
    m = re.search(r'the wait (W\d+) for case (c\d+) lasted (\d+) seconds on visit (\d+)', s)
    if m:
        ch['wait'] = [(m.group(2), m.group(1), int(m.group(4)), int(m.group(3)))]
    m = re.search(r'the pool ([A-Za-z ]+?) had (\d+) more workers throughout', s)
    if m:
        ch['extra'] = {m.group(1): int(m.group(2))}
    assert ch, s
    target = re.search(r'would case (c\d+) end', s).group(1)
    return ch, target


def main():
    qs = json.load(open(os.path.join(HERE, 'questions.json'), encoding='utf-8'))
    chapters = sorted({(q['front_matter_file'], q['chapter_file']) for q in qs})
    for fn in os.listdir(HERE):
        if '_chapter_' in fn:
            fm = fn.split('_chapter_')[0] + '_front_matter.txt'
            chapters.append((fm, fn))
    chapters = sorted(set(chapters))
    out = []
    repro = {}
    for fm, cf in chapters:
        proc = LOAN if fm.startswith('loan') else PHARM
        ps, pr = load_front(fm, proc)
        ch = load_chapter(cf)
        res = simulate(proc, ps, pr, ch)
        d = compare(res, ch)
        repro[cf] = (not d, d, len(ch['tasklog']), len(ch['waitlog']), len(ch['declog']))
        out.append(f'{cf} (front matter {fm}): {"EXACT MATCH" if not d else "MISMATCH"} '
                   f'[{len(ch["cases"])} cases, {len(ch["tasklog"])} task rows, {len(ch["waitlog"])} wait rows, {len(ch["declog"])} decision rows]')
        for x in d:
            out.append('   ' + x)
    answers = []
    for q in qs:
        proc = LOAN if q['front_matter_file'].startswith('loan') else PHARM
        ps, pr = load_front(q['front_matter_file'], proc)
        ch = load_chapter(q['chapter_file'])
        change, target = parse_question(q, ps)
        base = simulate(proc, ps, pr, ch)
        try:
            res = simulate(proc, ps, pr, ch, change)
            ans = res['ends'].get(target)
            err = None
        except Exception as ex:  # e.g. a needed plan value is missing
            ans, err = None, repr(ex)
        ok = repro[q['chapter_file']][0]
        out.append(f'{q["qid"]}: change={change} target={target} baseline_end={base["ends"].get(target)} answer={ans} err={err}')
        answers.append({'qid': q['qid'], 'answer': ans, 'factual_reproduced': ok,
                        'baseline_end': base['ends'].get(target), 'change': repr(change), 'error': err})
    open(os.path.join(HERE, 'results.txt'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    json.dump(answers, open(os.path.join(HERE, 'raw_answers.json'), 'w', encoding='utf-8'), indent=1)
    print('\n'.join(out))


if __name__ == '__main__':
    main()
