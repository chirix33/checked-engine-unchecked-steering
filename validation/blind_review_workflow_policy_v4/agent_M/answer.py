import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim, json, re, copy
Q = json.load(open('questions.json', encoding='utf-8'))
out = []; details = []
for q in Q:
    proc = sim.LOAN if q['process'] == 'loan' else sim.PHARM
    pools, _ = sim.parse_front_matter(q['front_matter_file'])
    ch = sim.parse_chapter(q['chapter_file'], set(proc['act']))
    base = sim.Sim(proc, pools, ch).run()
    fact_ok = not sim.compare(base, ch)
    text = q['question']
    target = re.search(r'would case (c\d{4}) end', text).group(1)
    ch2 = copy.deepcopy(ch); kw = {}; change = None
    if m := re.search(r"case (c\d{4}) needed (\d+) seconds of work for the activity '([^']+)' on visit (\d+)", text):
        c, w, a, v = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        old = ch2['work'][(c, a)][v - 1]; ch2['work'][(c, a)][v - 1] = w
        change = f'work {c}/{a}/v{v}: {old} -> {w}'
        used = any(r[0] == c and r[1] == a and r[2] == v for r in ch['tasklog'])
        change += f' (visit performed in factual run: {used})'
    elif m := re.search(r'case (c\d{4}) had never arrived', text):
        kw['removed'] = {m.group(1)}; change = f'remove {m.group(1)}'
    elif m := re.search(r'the pool ([A-Za-z ]+?) had (\d+) more workers? throughout', text):
        kw['extra_workers'] = {m.group(1): int(m.group(2))}; change = f'+{m.group(2)} {m.group(1)}'
    elif m := re.search(r'route draw for case (c\d{4}) at decision (D\d+) on visit (\d+) were ([0-9]+.[0-9]+)', text):
        c, d, v, u = m.group(1), m.group(2), int(m.group(3)), float(m.group(4))
        old = ch2['draws'][(c, d)][v - 1]; ch2['draws'][(c, d)][v - 1] = u
        used = any(r[0] == c and r[1] == d and r[2] == v for r in ch['declog'])
        change = f'draw {c}/{d}/v{v}: {old} -> {u} (visit reached in factual run: {used})'
    elif m := re.search(r'decision (D\d+) used the probabilities (.*)\. At what', text):
        d = m.group(1); ps = dict((rid, float(p)) for rid, p in re.findall(r'route (D\d+-[a-z]) ([0-9.]+)', m.group(2)))
        kw['prob'] = {d: ps}; change = f'prob {d}: {ps}'
    elif m := re.search(r'the wait (W\d+) for case (c\d{4}) lasted (\d+) seconds on visit (\d+)', text):
        w, c, s, v = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
        old = ch2['wait'][(c, w)][v - 1]; ch2['wait'][(c, w)][v - 1] = s
        used = any(r[0] == c and r[1] == w and r[2] == v for r in ch['waitlog'])
        change = f'wait {c}/{w}/v{v}: {old} -> {s} (visit reached in factual run: {used})'
    elif m := re.search(r'(\d+) ([A-Za-z ]+?) workers \(([^)]*)\) were unavailable from time (\d+) to time (\d+)', text):
        names = [x.strip() for x in m.group(3).split(',')]
        kw['unavail'] = {n: [(int(m.group(4)), int(m.group(5)))] for n in names}
        change = f'unavailable {names} [{m.group(4)},{m.group(5)})'
    else:
        raise SystemExit('unparsed ' + q['qid'])
    s = sim.Sim(proc, pools, ch2, **kw).run()
    ans = s.end.get(target)
    fact_end = ch['cases'][target][1]
    n_changed = sum(1 for c in s.end if s.end[c] != ch['cases'][c][1])
    print(q['qid'], q['chapter_file'], change, '| target', target, 'factual', fact_end, '-> answer', ans, '| cases whose end changed:', n_changed, '| unfinished:', [c for c in s.cases if c not in s.end])
    details.append(dict(qid=q['qid'], change=change, target=target, factual_end=fact_end, answer=ans, fact_ok=fact_ok, n_changed=n_changed))
json.dump(details, open('answer_details.json', 'w'), indent=1)
