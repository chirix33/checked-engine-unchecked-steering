import sys; sys.path.insert(0, ".")
import json, re, sys
from sim import simulate, check

qs = json.load(open('questions.json'))
res = []
repro = {}
for q in qs:
    doc, ch, t = q['front_matter_file'], q['chapter_file'], q['question']
    if ch not in repro:
        repro[ch] = check(doc, ch)[0]
    m = {}
    if (x := re.search(r"case c(\d+) needed (\d+) seconds of work for the activity '(.+?)' on visit (\d+)", t)):
        m['work'] = {(int(x[1]), x[3], int(x[4])): int(x[2])}
        target = int(x[1])
    elif (x := re.search(r"case c(\d+) had never arrived\. .*would case c(\d+) end", t)):
        m['remove'] = [int(x[1])]
        target = int(x[2])
    elif (x := re.search(r"pool (.+?) had (\d+) more workers? throughout\. .*case c(\d+) end", t)):
        m['addworkers'] = {x[1]: int(x[2])}
        target = int(x[3])
    elif (x := re.search(r"route draw for case c(\d+) at decision (D\d) on visit (\d+) were ([\d.]+)", t)):
        m['draw'] = {(int(x[1]), x[2], int(x[3])): float(x[4].rstrip('.'))}
        target = int(x[1])
    elif (x := re.search(r"decision (D\d) used the probabilities route D\d-a ([\d.]+), route D\d-b ([\d.]+)\. .*case c(\d+) end", t)):
        m['probs'] = {x[1]: [float(x[2]), float(x[3])]}
        target = int(x[4])
    elif (x := re.search(r"wait (W\d) for case c(\d+) lasted (\d+) seconds on visit (\d+)", t)):
        m['wait'] = {(int(x[2]), x[1], int(x[4])): int(x[3])}
        target = int(x[2])
    elif (x := re.search(r"suppose \d+ (.+?) workers \((.+?)\) were unavailable from time (\d+) to time (\d+)\..*case c(\d+) end", t)):
        m['unavail'] = {n.strip(): [(int(x[3]), int(x[4]))] for n in x[2].split(',')}
        target = int(x[5])
    else:
        raise Exception('unparsed ' + t)
    r = simulate(doc, ch, m)
    base = simulate(doc, ch)
    ans = r['ends'][target]
    res.append(dict(qid=q['qid'], answer=ans, factual_reproduced=repro[ch], confidence='high' if repro[ch] else 'low',
                    note=f"base end {base['ends'][target]} -> {ans}; mod {m}"))
    print(q['qid'], ans, 'base', base['ends'][target], m)
json.dump(res, open('answers.json', 'w'), indent=1)
