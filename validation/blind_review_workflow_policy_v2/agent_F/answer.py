import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim

Q = json.load(open('questions.json'))
HOUR = 3600

def mods_for(qid):
    m = {
     'W01': dict(work=[('c0001', 'Approve and post home insurance quote', 4, 5491)]),
     'W02': dict(remove=['c0005']),
     'W03': dict(unavail=[('Appraiser', 1, 39600, 54000)]),
     'W04': dict(draw=[('c0007', 'D4', 2, '0.750000')]),
     'W05': dict(probs={'D4': {'D4-a': '0.3', 'D4-b': '0.7'}}),
     'W06': dict(wait=[('c0003', 'W1', 1, 39680)]),
     'W07': dict(work=[('c0000', 'Approve application', 3, 3768)]),
     'W08': dict(remove=['c0004']),
     'W09': dict(unavail=[('AML Investigator', 2, 39600, 68400), ('AML Investigator', 3, 39600, 68400)]),
     'W10': dict(draw=[('c0012', 'D2', 1, '0.750000')]),
     'W11': dict(probs={'D4': {'D4-a': '0.9', 'D4-b': '0.1'}}),
     'W12': dict(wait=[('c0011', 'W2', 1, 6970)]),
     'W13': dict(work=[('c0012', 'Check Insurance', 1, 2)]),
     'W14': dict(remove=['c0003']),
     'W15': dict(extra={'Pharmacy System': 2}),
     'W16': dict(draw=[('c0001', 'D3', 1, '0.900000')]),
     'W17': dict(probs={'D6': {'D6-a': '0.7', 'D6-b': '0.3'}}),
     'W18': dict(wait=[('c0003', 'W2', 1, 0)]),
     'W19': dict(work=[('c0014', 'Check Insurance', 1, 2)]),
     'W20': dict(remove=['c0003']),
     'W21': dict(unavail=[('Pharmacist', 0, 28800, 57600), ('Pharmacist', 1, 28800, 57600)]),
     'W22': dict(draw=[('c0008', 'D6', 1, '0.035000')]),
     'W23': dict(probs={'D6': {'D6-a': '0.7', 'D6-b': '0.3'}}),
     'W24': dict(wait=[('c0004', 'W2', 1, 420)]),
    }
    return m[qid]

import re
def target(q):
    # case asked about = last "case cNNNN would end"
    return re.findall(r'case (c\d{4}) end', q['question'])[-1]

cache = {}
out = []
lines = []
for q in Q:
    proc = q['process']
    doc = 'policyP' if 'policyP' in q['chapter_file'] else 'policyH'
    run = int(re.search(r'Run_(\d+)', q['chapter_file']).group(1))
    assert q['front_matter_file'].startswith(f'{proc}_{doc}'), q
    model, cfg, ch = sim.load(proc, doc, run)
    base = sim.simulate(model, cfg, ch)
    exact = not sim.compare(base, ch)
    c = target(q)
    res = sim.simulate(model, cfg, ch, mods_for(q['qid']))
    ans = res['ends'].get(c)
    fact = ch['cases'][c][1]
    note = f"Factual end {fact} -> counterfactual {ans} (delta {None if ans is None else ans - fact})."
    out.append(dict(qid=q['qid'], answer=ans, factual_reproduced=exact, confidence='high' if exact else 'low', note=note))
    print(q['qid'], proc, doc, run, c, 'factual', fact, 'cf', ans)
json.dump(out, open('answers.json', 'w'), indent=1)
