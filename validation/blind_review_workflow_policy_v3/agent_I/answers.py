import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json, re, os
from sim import load_doc, load_chapter, simulate, compare, to_micro, HERE

qs = json.load(open(os.path.join(HERE, 'questions.json'), encoding='utf-8'))
cache = {}
out = []
for q in qs:
    fm, chn, text = q['front_matter_file'], q['chapter_file'], q['question']
    if chn not in cache:
        doc = load_doc(fm)
        ch = load_chapter(chn, doc)
        base = simulate(doc, ch)
        cache[chn] = (doc, ch, base, not compare(ch, base))
    doc, ch, base, ok = cache[chn]
    run = re.search(r'In Run (\d+),', text).group(1)
    assert ('Run_%s' % run) in chn
    target = re.search(r'would case (c\d{4}) end\?', text).group(1)
    change = {}
    happened = None
    m = re.search(r"suppose case (c\d{4}) needed (\d+) seconds of work for the activity '(.+?)' on visit (\d+)\.", text)
    if m:
        c, w, a, v = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        assert (c, a) in ch['work'] and v <= len(ch['work'][(c, a)])
        change['work'] = {(c, a, v): w}
        happened = any(r[0] == c and r[1] == a and r[2] == v for r in base['task_log'])
        desc = 'work %s %s v%d %d -> %d' % (c, a, v, ch['work'][(c, a)][v - 1], w)
    m = re.search(r'suppose case (c\d{4}) had never arrived\.', text)
    if m:
        change['remove_cases'] = {m.group(1)}
        desc = 'remove %s' % m.group(1)
        happened = True
    m = re.search(r'suppose (\d+) (.+?) workers? \((.+?)\) (?:was|were) unavailable from time (\d+) to time (\d+)\.', text)
    if m:
        names = [x.strip() for x in m.group(3).split(',')]
        assert len(names) == int(m.group(1))
        a, b = int(m.group(4)), int(m.group(5))
        for nm in names:
            pool, idx = nm.rsplit('_', 1)
            assert pool == m.group(2) and int(idx) < doc['pools'][pool]['n'], nm
        change['unavail'] = {nm: [(a, b)] for nm in names}
        desc = 'unavailable %s [%d,%d)' % (names, a, b)
        happened = True
    m = re.search(r'suppose the route draw for case (c\d{4}) at decision (D\d+) on visit (\d+) were ([\d.]+)\.', text)
    if m:
        c, d, v = m.group(1), m.group(2), int(m.group(3))
        change['draw'] = {(c, d, v): to_micro(m.group(4))}
        happened = any(r[0] == c and r[1] == d and r[2] == v for r in base['dec_log'])
        desc = 'draw %s %s v%d %s -> %s' % (c, d, v, ch['draws'][(c, d)][v - 1] / 1e6, m.group(4))
    m = re.search(r'suppose decision (D\d+) used the probabilities (.+?)\. At', text)
    if m:
        d = m.group(1)
        pr = re.findall(r'route (\S+) ([\d.]+)', m.group(2))
        routes = doc['nodes'][d]['routes']
        assert [r['id'] for r in routes] == [x[0] for x in pr]
        change['prob'] = {d: [to_micro(x[1]) for x in pr]}
        desc = 'prob %s %s' % (d, pr)
        happened = True
    m = re.search(r'suppose the wait (W\d+) for case (c\d{4}) lasted (\d+) seconds on visit (\d+)\.', text)
    if m:
        w, c, val, v = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
        change['wait'] = {(c, w, v): val}
        happened = any(r[0] == c and r[1] == w and r[2] == v for r in base['wait_log'])
        desc = 'wait %s %s v%d %d -> %d' % (c, w, v, ch['waits'][(c, w)][v - 1], val)
    m = re.search(r'suppose the pool (.+?) had (\d+) more workers? throughout\.', text)
    if m:
        change['extra_workers'] = {m.group(1): int(m.group(2))}
        desc = 'pool %s +%s' % (m.group(1), m.group(2))
        happened = True
    assert change, text
    res = simulate(doc, ch, change)
    ans = res['ends'].get(target)
    fact = base['ends'][target]
    out.append({'qid': q['qid'], 'answer': ans, 'factual_end': fact, 'factual_reproduced': ok,
                'change': desc, 'change_visit_happened_in_factual': happened})
    print(q['qid'], chn, desc, '| target', target, 'factual', fact, '-> answer', ans, '| happened', happened)
json.dump(out, open(os.path.join(HERE, 'raw_answers.json'), 'w'), indent=1)
