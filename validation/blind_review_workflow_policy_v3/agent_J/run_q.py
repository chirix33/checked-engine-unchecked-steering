import sys, os; sys.path.insert(0, os.getcwd())
import json, re
from sim import *

Q = json.load(open('questions.json'))
out = []
cache = {}
for q in Q:
    G = LOAN if q['process'] == 'loan' else PHARM
    pools, probs = parse_front(q['front_matter_file'])
    ch = parse_chapter(q['chapter_file'])
    ok = not check(G, ch, pools, probs)
    t = q['question']
    mods = {}
    target = re.search(r'case (c\d{4}) (?:would end|end)', t)
    m = re.search(r'would case (c\d{4}) end|would case (c\d{4})', t)
    target = (m.group(1) or m.group(2))
    if m := re.search(r'suppose case (c\d{4}) needed (\d+) seconds of work for the activity \'(.+?)\' on visit (\d+)', t):
        mods['work'] = {(m.group(1), m.group(3), int(m.group(4))): int(m.group(2))}
    elif m := re.search(r'suppose case (c\d{4}) had never arrived', t):
        mods['remove'] = [m.group(1)]
    elif m := re.search(r'suppose \d+ ([A-Za-z ]+?) workers? \((.+?)\) (?:was|were) unavailable from time (\d+) to time (\d+)', t):
        mods['unavail'] = {w.strip(): [(int(m.group(3)), int(m.group(4)))] for w in m.group(2).split(',')}
    elif m := re.search(r'route draw for case (c\d{4}) at decision (D\d) on visit (\d+) were (\d\.\d+)', t):
        mods['draw'] = {(m.group(1), m.group(2), int(m.group(3))): float(m.group(4))}
    elif m := re.search(r'decision (D\d) used the probabilities route (D\d-\w) (\d\.\d+), route (D\d-\w) (\d\.\d+)', t):
        mods['probs'] = {m.group(2): float(m.group(3)), m.group(4): float(m.group(5))}
    elif m := re.search(r'wait (W\d) for case (c\d{4}) lasted (\d+) seconds on visit (\d+)', t):
        mods['wait'] = {(m.group(2), m.group(1), int(m.group(4))): int(m.group(3))}
    elif m := re.search(r'pool ([A-Za-z ]+?) had (\d+) more workers', t):
        mods['extra'] = {m.group(1): int(m.group(2))}
    else:
        raise Exception(t)
    base = simulate(G, ch, pools, probs)
    r = simulate(G, ch, pools, probs, mods)
    ans = r['ends'][target]
    print(q['qid'], target, 'factual', ch['cases'][target][1], 'new', ans, 'delta', ans - ch['cases'][target][1], mods, ok)
    out.append(dict(qid=q['qid'], answer=ans, factual_reproduced=ok, factual=ch['cases'][target][1]))
json.dump(out, open('raw_answers.json', 'w'), indent=1)
