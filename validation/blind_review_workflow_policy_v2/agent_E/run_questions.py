import sys, json, re
sys.path.insert(0, '.')
from sim import *

def parse_change(q):
    s = q['question']
    m = re.search(r"suppose case (c\d{4}) needed (\d+) seconds of work for the activity '(.+?)' on visit (\d+)", s)
    if m: return {'work': {(m[1], m[3], int(m[4])): int(m[2])}}, f"work {m[1]} {m[3]} v{m[4]}={m[2]}"
    m = re.search(r"suppose case (c\d{4}) had never arrived", s)
    if m: return {'remove_cases': [m[1]]}, f"remove {m[1]}"
    m = re.search(r"suppose (\d+) (.+?) workers? \((.+?)\) (?:was|were) unavailable from time (\d+) to time (\d+)", s)
    if m:
        names = [x.strip() for x in m[3].split(',')]
        assert len(names) == int(m[1])
        return {'unavail': {n: [(int(m[4]), int(m[5]))] for n in names}}, f"unavail {names} [{m[4]},{m[5]})"
    m = re.search(r"suppose (\d+) (.+?) workers were unavailable from time (\d+) to time (\d+)", s)
    if m:
        return {'unavail_pool': (m[2], int(m[1]), int(m[3]), int(m[4]))}, f"unavail {m[1]} of pool {m[2]} [{m[3]},{m[4]})"
    m = re.search(r"suppose the route draw for case (c\d{4}) at decision (D\d+) on visit (\d+) were ([0-9]+.[0-9]+)", s)
    if m: return {'draw': {(m[1], m[2], int(m[3])): m[4]}}, f"draw {m[1]} {m[2]} v{m[3]}={m[4]}"
    m = re.search(r"suppose decision (D\d+) used the probabilities (.+?)\. At", s)
    if m:
        probs = dict(re.findall(r"route (D\d+-[a-z]) ([0-9.]+)", m[2]))
        return {'probs': {m[1]: probs}}, f"probs {m[1]} {probs}"
    m = re.search(r"suppose the wait (W\d+) for case (c\d{4}) lasted (\d+) seconds on visit (\d+)", s)
    if m: return {'wait': {(m[2], m[1], int(m[4])): int(m[3])}}, f"wait {m[2]} {m[1]} v{m[4]}={m[3]}"
    m = re.search(r"suppose the pool (.+?) had (\d+) more workers throughout", s)
    if m: return {'extra_workers': {m[1]: int(m[2])}}, f"pool {m[1]} +{m[2]}"
    raise ValueError(s)

qs = json.load(open('questions.json'))
out = []
for q in qs:
    pools = parse_front_matter(q['front_matter_file'])
    ch = parse_chapter(q['chapter_file'])
    model = LOAN if q['process'] == 'loan' else PHARM
    base = simulate(model, pools, ch)
    repro = not compare(ch, base)
    chg, desc = parse_change(q)
    if 'unavail_pool' in chg:
        pool, n, a, b = chg.pop('unavail_pool')
        assert n == pools[pool]['n'], 'not all workers'
        chg['unavail'] = {f'{pool}_{i}': [(a, b)] for i in range(n)}
    target = re.search(r"would case (c\d{4}) end", q['question'])[1]
    res = simulate(model, pools, ch, chg)
    # was the changed item reached in the factual / changed run?
    reached = ''
    if 'work' in chg:
        (c, a, v), = chg['work'].keys()
        reached = f"factual visit reached={any(r[:3]==(c,a,v) for r in base['task_log'])}; cf reached={any(r[:3]==(c,a,v) for r in res['task_log'])}; plan len={len(ch['work'][(c,a)])}"
    if 'wait' in chg:
        (c, w, v), = chg['wait'].keys()
        reached = f"factual reached={any(r[:3]==(c,w,v) for r in base['wait_log'])}; orig={ch['wait'][(c,w)][v-1] if v<=len(ch['wait'][(c,w)]) else None}"
    if 'draw' in chg:
        (c, d, v), = chg['draw'].keys()
        fr = [r for r in base['dec_log'] if r[:3]==(c,d,v)]; cr = [r for r in res['dec_log'] if r[:3]==(c,d,v)]
        reached = f"factual {fr}; cf {cr}; orig draw={float(ch['draws'][(c,d)][v-1])}"
    if 'unavail' in chg:
        reached = f"workers {list(chg['unavail'])}"
    nchanged = sum(1 for c in ch['cases'] if c in res['end'] and res['end'][c] != base['end'][c])
    print(q['qid'], q['chapter_file'], desc, '| target', target, 'factual', base['end'][target], '-> cf', res['end'].get(target), '| repro', repro, '| errs', res['errors'], '|', reached, '| cases changed', nchanged)
    out.append(dict(qid=q['qid'], answer=res['end'].get(target), factual=base['end'][target], repro=repro, errors=res['errors'], desc=desc, reached=reached))
json.dump(out, open('raw_results.json', 'w'), indent=1, default=str)
