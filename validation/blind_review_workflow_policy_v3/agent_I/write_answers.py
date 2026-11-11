import json, os
H = os.path.dirname(os.path.abspath(__file__))
raw = json.load(open(os.path.join(H, 'raw_answers.json')))
extra = {
 'W07': ' End unchanged because Approve application still waits for Tuesday 09:00 opening.',
 'W09': ' AML Investigator_2 was mid-task (c0005) at 39600; that task pauses and resumes Tuesday per rule 3.',
 'W15': ' New workers named Pharmacy System_1 and _2 with the same hours; no effect on c0013.',
 'W02': ' Removing c0005 does not change c0011.',
 'W05': ' The c0002 D4 draw 0.541281 (visit 1) still selects D4-b under 0.3/0.7, so no effect.',
 'W08': ' Removing c0004 does not change c0014.',
 'W23': ' c0012 draw at D3 does not change route under the new probabilities.',
}
out = []
for r in raw:
    note = 'Change applied: %s. Factual end of target case %d; changed-run end %d.' % (r['change'], r['factual_end'], r['answer'])
    note += extra.get(r['qid'], '')
    out.append({'qid': r['qid'], 'answer': r['answer'], 'factual_reproduced': r['factual_reproduced'],
                'confidence': 'high' if r['factual_reproduced'] else 'low', 'note': note})
json.dump(out, open(os.path.join(H, 'answers.json'), 'w'), indent=1)
print(len(out))
