import os, json
HERE = os.path.dirname(os.path.abspath(__file__))
d = {r['qid']: r for r in json.load(open(os.path.join(HERE, 'answer_details.json')))}
notes = {
 'W01': 'Return work 1895->1 makes c0009 reach the applicant step earlier, but its second completeness check still waits for Wednesday 09:00, so the end is unchanged from the recorded 293096.',
 'W02': 'c0004 removed from Run 07; with other cases rescheduled, c0014 ends at 56971 (recorded 56620).',
 'W03': 'Added Appraiser_2 with the same Mon-Fri 09:00-17:00 hours; c0011 ends at 134022 (recorded 134148).',
 'W04': 'Draw 0.100000 < 0.2 sends c0011 to D1-a (return to applicant); visit-2 draw 0.997084 then gives D1-b, and D2 rejects; end 215479 (recorded 52875).',
 'W05': 'D5 cumulative 0.7 > draw 0.517267, so c0007 cancels on its first D5 visit; end 59158 (recorded 126373).',
 'W06': 'W2 3261->6861 for c0002 delays Assess loan risk; routes unchanged; end 58166 (recorded 54566).',
 'W07': 'Pick-up work 130->260 for c0013; Pick-up starts at 31583 as before and ends 31843 (recorded 31713).',
 'W08': 'c0007 removed from Run 08; c0006 ends at 30804, one second earlier than recorded 30805.',
 'W09': 'Added Pharmacist_1 with the same hours; c0011 ends at 31507 (recorded 31601).',
 'W10': 'Draw 0.025 < 0.05 gives D7-a back to D6; D6 visit-2 draw 0.016552 gives D6-a to W3 at the same time 29696, so the end is unchanged at 30198.',
 'W11': 'c0000 D1 draw 0.140082 < 0.3 so its own route is unchanged, but other cases re-route and delay its Pick-up start to 30074; end 30235 (recorded 30198).',
 'W12': 'W2 183->0 for c0014; Pack starts immediately at 32259; end 32941 (recorded 33124).',
}
out = []
for qid in sorted(d):
    r = d[qid]
    out.append({'qid': qid, 'answer': r['answer'], 'factual_reproduced': r['reproduced'],
                'confidence': 'high' if r['reproduced'] and r['answer'] is not None else 'low',
                'note': notes[qid]})
json.dump(out, open(os.path.join(HERE, 'answers.json'), 'w'), indent=1)
print(json.dumps(out, indent=1))
