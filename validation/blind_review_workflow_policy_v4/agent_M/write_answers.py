import json
D = {d['qid']: d for d in json.load(open('answer_details.json'))}
notes = {
 'W01': 'Design loan offer visit 2 work 1888->3776; c0008 ends 1984 s later after downstream re-queueing.',
 'W02': 'c0000 ends at 42771, before c0013 arrives (44100), so removing c0013 cannot affect it.',
 'W03': 'Added Senior Officer_3 (same hours); c0008 avoids a Senior Officer queue and ends 232 s earlier.',
 'W04': 'Draw 0.75 at D4 visit 2 sends c0007 to D4-b (Consider re-design loan offer) instead of W3.',
 'W05': 'c0002 D4 draw 0.541281 still exceeds 0.3, so it takes D4-b as in the record (then D5-a Cancel); end unchanged.',
 'W06': 'W2 delay 2871->6471 shifts c0007 by exactly 3600 s; no off-hours or queue effects.',
 'W07': 'Longer Assess loan risk still finishes Monday; c0004 still waits for W3 then next-day Approve application, end unchanged.',
 'W08': 'Removing c0009 changes which workers c0011 gets but none of its times (it never waited for a worker); end unchanged.',
 'W09': 'AML Investigator_2/3 off 39600-68400 (rest of Monday); c0012 AML Check queues on AML_1 and the case ends 355 s later. In-progress task of c0005 pauses and is held per rule 3 (does not affect c0012).',
 'W10': 'Draw 0.75 at D2 sends c0012 to D2-b (loan offer path) instead of rejection; ends Tuesday.',
 'W11': 'With D4-a at 0.9, c0009 draw 0.713556 takes D4-a (W3 then Approve application on Tuesday) instead of D4-b then Cancel.',
 'W12': 'W2 longer by 3600 s pushes the approve tasks past Monday 17:00; they finish Tuesday, then W3 and Approve application.',
 'W13': 'Check Insurance 1->2 s shifts c0012 by 1 s.',
 'W14': 'Without c0003, c0001 Quality Assurance no longer queues 17 s for the single Pharmacist, so it ends 17 s earlier.',
 'W15': 'Extra Pharmacy System workers only change worker names for c0013 (it never waited); no case end changes.',
 'W16': 'Draw 0.915 at D5 sends c0014 to D5-b (Resolve insurance issues manually).',
 'W17': 'D6-a prob 0.7: c0002 D6 draw now selects Out of stock (W3 then Pick-up), skipping packing; ends earlier.',
 'W18': 'W2 0 s for c0007; Pack enabled immediately, case ends 107 s earlier.',
 'W19': 'Check Insurance 1->2 s shifts c0014 by 1 s.',
 'W20': 'Without c0011, c0014 Quality Assurance no longer queues for Pharmacist_0 (16 s), so it ends 16 s earlier.',
 'W21': 'With two extra Pharmacists, c0011 Quality Assurance starts without queueing and the case ends 41 s earlier.',
 'W22': 'Draw 0.9 at D3 sends c0000 to D3-b then D4 (D4-a, Resolve DUR manually by a Pharmacist).',
 'W23': 'c0012 D3 draw 0.504507 gives D3-a under both 0.8 and 0.9; no case end in the run changes.',
 'W24': 'W2 0 s for c0008; Pack enabled immediately, case ends 131 s earlier.',
}
out = []
for qid in sorted(D):
    d = D[qid]
    out.append(dict(qid=qid, answer=d['answer'], factual_reproduced=d['fact_ok'], confidence='high', note=notes[qid]))
json.dump(out, open('answers.json', 'w'), indent=1)
print(json.dumps([(o['qid'], o['answer']) for o in out]))
