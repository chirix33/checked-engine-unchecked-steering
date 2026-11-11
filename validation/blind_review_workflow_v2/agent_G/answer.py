import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODELS, parse_chapter, simulate, compare

Q = json.load(open('questions.json', encoding='utf-8'))

# Changes transcribed by hand from each question's text.
CHANGES = {
    'W01': ({'work': [('c0009', 'Return application back to applicant', 1, 1)]}, 'c0009'),
    'W02': ({'remove': ['c0001']}, 'c0003'),
    'W03': ({'unavail': {'Appraiser': [(0, 39600, 54000), (1, 39600, 54000)]}}, 'c0005'),
    'W04': ({'draw': [('c0011', 'D1', 1, 0.1)]}, 'c0011'),
    'W05': ({'probs': [('D5', {'D5-a': 0.7, 'D5-b': 0.3})]}, 'c0007'),
    'W06': ({'wait': [('c0002', 'W2', 1, 6861)]}, 'c0002'),
    'W07': ({'work': [('c0002', 'Check DUR', 1, 3601)]}, 'c0002'),
    'W08': ({'remove': ['c0004']}, 'c0006'),
    'W09': ({'unavail': {'Pharmacist': [(0, 28800, 36000)]}}, 'c0007'),
    'W10': ({'draw': [('c0000', 'D7', 1, 0.025)]}, 'c0000'),
    'W11': ({'probs': [('D1', {'D1-a': 0.3, 'D1-b': 0.7})]}, 'c0000'),
    'W12': ({'wait': [('c0005', 'W2', 1, 3788)]}, 'c0005'),
}

out = []
detail = {}
for q in Q:
    qid = q['qid']
    model = MODELS[q['process']]
    ch = parse_chapter(q['chapter_file'], model)
    nacts = len(model['acts'])
    assert len(ch['work']) == len(ch['cases']) * nacts, (qid, len(ch['work']))
    base = simulate(model, ch)
    exact = compare(ch, base)['exact']
    chg, case = CHANGES[qid]
    # check that the changed element exists in the plan
    for (c, a, v, val) in chg.get('work', []):
        assert len(ch['work'][(c, a)]) >= v
    for (c, w, v, val) in chg.get('wait', []):
        assert len(ch['waitplan'][(c, w)]) >= v
    for (c, d, v, val) in chg.get('draw', []):
        assert len(ch['draws'][(c, d)]) >= v
    try:
        res = simulate(model, ch, chg)
        ans = res['ends'].get(case)
        err = None
    except (IndexError, KeyError) as e:
        ans, err = None, repr(e)
    fact = ch['cases'][case][1]
    # which planned visits were actually used by the changed element in the factual run
    used = {}
    for (c, a, v, val) in chg.get('work', []):
        used['work_visit_happened_factual'] = any(r[0] == c and r[1] == a and r[2] == v for r in base['tasklog'])
        used['work_visit_happened_changed'] = any(r[0] == c and r[1] == a and r[2] == v for r in res['tasklog'])
    for (c, w, v, val) in chg.get('wait', []):
        used['wait_visit_happened_factual'] = any(r[0] == c and r[1] == w and r[2] == v for r in base['waitlog'])
    for (c, d, v, val) in chg.get('draw', []):
        used['draw_visit_happened_factual'] = any(r[0] == c and r[1] == d and r[2] == v for r in base['declog'])
    detail[qid] = {'case': case, 'factual_end': fact, 'answer': ans, 'err': err, **used}
    print(qid, case, 'factual', fact, 'answer', ans, err, used)
    out.append((qid, ans, exact, fact, err, used))

json.dump(detail, open('answer_detail.json', 'w'), indent=1)
