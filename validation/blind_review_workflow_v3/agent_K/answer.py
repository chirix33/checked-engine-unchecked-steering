import os, sys, json, copy
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sim import MODELS, parse_chapter, simulate, compare

def P(f):
    return os.path.join(HERE, f)

# Each change is transcribed by hand from questions.json (text of the question).
CHANGES = {
    'W01': ('loan', 'loan_chapter_Run_06.txt', 'c0009', ('work', 'c0009', 'Return application back to applicant', 1, 1)),
    'W02': ('loan', 'loan_chapter_Run_07.txt', 'c0014', ('remove', 'c0004')),
    'W03': ('loan', 'loan_chapter_Run_10.txt', 'c0011', ('worker', 'Appraiser', 1)),
    'W04': ('loan', 'loan_chapter_Run_11.txt', 'c0011', ('draw', 'c0011', 'D1', 1, '0.100000')),
    'W05': ('loan', 'loan_chapter_Run_12.txt', 'c0007', ('prob', 'D5', ['0.7', '0.3'])),
    'W06': ('loan', 'loan_chapter_Run_05.txt', 'c0002', ('wait', 'c0002', 'W2', 1, 6861)),
    'W07': ('pharmacy', 'pharmacy_chapter_Run_05.txt', 'c0013', ('work', 'c0013', 'Pick-up', 1, 260)),
    'W08': ('pharmacy', 'pharmacy_chapter_Run_08.txt', 'c0006', ('remove', 'c0007')),
    'W09': ('pharmacy', 'pharmacy_chapter_Run_09.txt', 'c0011', ('worker', 'Pharmacist', 1)),
    'W10': ('pharmacy', 'pharmacy_chapter_Run_09.txt', 'c0000', ('draw', 'c0000', 'D7', 1, '0.025000')),
    'W11': ('pharmacy', 'pharmacy_chapter_Run_09.txt', 'c0000', ('prob', 'D1', ['0.3', '0.7'])),
    'W12': ('pharmacy', 'pharmacy_chapter_Run_05.txt', 'c0014', ('wait', 'c0014', 'W2', 1, 0)),
}

qs = json.load(open(P('questions.json'), encoding='utf-8'))
results = []
for q in qs:
    qid = q['qid']
    proc, chf, target, chg = CHANGES[qid]
    assert chf == q['chapter_file'] and proc == q['process'] and target in q['question']
    ch = parse_chapter(P(chf))
    base = simulate(MODELS[proc], ch)
    repro = not compare(ch, base)
    ch2 = copy.deepcopy(ch)
    kw = {}
    kind = chg[0]
    if kind == 'work':
        _, c, a, v, val = chg; old = ch2['work'][(c, a)][v - 1]; ch2['work'][(c, a)][v - 1] = val
    elif kind == 'wait':
        _, c, w, v, val = chg; old = ch2['waits'][(c, w)][v - 1]; ch2['waits'][(c, w)][v - 1] = val
    elif kind == 'draw':
        _, c, d, v, val = chg; old = ch2['draws'][(c, d)][v - 1]; ch2['draws'][(c, d)][v - 1] = val
    elif kind == 'remove':
        old = ch2['cases'].pop(chg[1])
    elif kind == 'worker':
        kw['extra_workers'] = {chg[1]: chg[2]}; old = None
    elif kind == 'prob':
        kw['prob_override'] = {chg[1]: chg[2]}; old = None
    try:
        res = simulate(MODELS[proc], ch2, **kw)
        ans = res['ends'].get(target)
        err = None
    except Exception as e:  # e.g. a visit with no planned value
        ans, err, res = None, repr(e), None
    # did the change touch the target's own history?
    bt = [r for r in base['task_log'] if r[0] == target]
    nt = [r for r in res['task_log'] if r[0] == target] if res else []
    bd = [r for r in base['dec_log'] if r[0] == target]
    nd = [r for r in res['dec_log'] if r[0] == target] if res else []
    results.append(dict(qid=qid, chapter=chf, target=target, change=chg, old_value=old, reproduced=repro,
                        baseline_end=base['ends'][target], answer=ans, error=err,
                        target_tasks_changed=(bt != nt), target_routes_base=[r[1:] for r in bd],
                        target_routes_new=[r[1:] for r in nd]))
    print(qid, chf, target, chg, 'old=', old, 'repro=', repro, 'base_end=', base['ends'][target], '-> answer', ans, err or '')
    if res:
        for r in nt:
            print('     ', r)
        print('      routes:', [r[1:] for r in nd])
json.dump(results, open(P('answer_details.json'), 'w'), indent=1, default=str)
