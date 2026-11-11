import os, sys, json, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sched

D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (qid, chapter, change, target task, yes/no threshold or None)
Q = [
    ('B01', 'chapter_Cell_window_06.txt', ('nofail', 'M02'), 'T105', 1407),
    ('B02', 'chapter_Cell_window_14.txt', ('nofail', 'M05'), 'T183', 2222),
    ('B03', 'chapter_Cell_window_06.txt', ('nojob', 'J10'), 'T058', 631),
    ('B04', 'chapter_Cell_window_11.txt', ('nojob', 'J10'), 'T105', 2307),
    ('B05', 'chapter_Cell_window_10.txt', ('nomachine', 'M04'), 'T127', 1405),
    ('B06', 'chapter_Cell_window_17.txt', ('nomachine', 'M04'), 'T039', None),
    ('B07', 'chapter_Cell_window_03.txt', ('pri', 'T104', 11, 4), 'T104', None),
    ('B08', 'chapter_Cell_window_13.txt', ('pri', 'T071', 11, 4), 'T071', None),
    ('B09', 'chapter_Cell_window_27.txt', ('cpu', 'T038', 3436, 6873), 'T038', None),
    ('B10', 'chapter_Cell_window_20.txt', ('cpu', 'T004', 1874, 937), 'T004', 2259),
]


def apply(machines, tasks, ch):
    machines = copy.deepcopy(machines); tasks = copy.deepcopy(tasks)
    kind = ch[0]
    if kind == 'nofail':
        m = [x for x in machines if x['id'] == ch[1]][0]
        assert m['fail'] is not None
        m['fail'] = None; m['ret'] = None
    elif kind == 'nojob':
        n = len(tasks)
        tasks = {k: v for k, v in tasks.items() if v['job'] != ch[1]}
        assert len(tasks) < n
    elif kind == 'nomachine':
        n = len(machines)
        machines = [x for x in machines if x['id'] != ch[1]]
        assert len(machines) == n - 1
    elif kind == 'pri':
        assert tasks[ch[1]]['pri'] == ch[3]
        tasks[ch[1]]['pri'] = ch[2]
    elif kind == 'cpu':
        assert tasks[ch[1]]['cpu'] == ch[3]
        tasks[ch[1]]['cpu'] = ch[2]
    return machines, tasks


out = []
for qid, chf, ch, target, thr in Q:
    path = os.path.join(D, chf)
    machines, tasks, log = sched.parse(path)
    ok, _ = sched.check(path)
    _, fs0, _ = sched.simulate(machines, tasks, stop_task=target)
    m2, t2 = apply(machines, tasks, ch)
    _, fs, st = sched.simulate(m2, t2, stop_task=target)
    s = fs.get(target)
    if thr is None:
        ans = s
        note = 'factual first start %s; counterfactual %s' % (fs0.get(target), s)
    else:
        ans = (s is not None and s <= thr)
        note = 'counterfactual first start %s (factual %s); threshold %d' % (s, fs0.get(target), thr)
    out.append(dict(qid=qid, answer=ans, factual_reproduced=ok, note=note))
    print(qid, ans, ok, note)

json.dump(out, open(os.path.join(D, 'agent_A', 'answers.json'), 'w'), indent=1)
