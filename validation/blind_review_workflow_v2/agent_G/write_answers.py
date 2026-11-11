import json
d = json.load(open('answer_detail.json'))
notes = {
 'W01': "c0009's Return task ends 1894 s earlier, but its second form check still waits for Wednesday 09:00, and from there the path is unchanged, so the end time is the same as recorded.",
 'W02': "Removed c0001 from the run (all other inputs unchanged); c0003 ends earlier because shared workers become available sooner.",
 'W03': "Both Appraisers are non-working in [39600, 54000); c0005's Appraise property pauses at 39600 and resumes at 54000, which pushes Reject application past 17:00 to the next day.",
 'W04': "Draw 0.1 at D1 visit 1 gives D1-a (form incomplete), so the return/W1/applicant loop runs before the rest of the process.",
 'W05': "With D5-a at 0.7, c0007's D5 visit-1 draw now picks D5-a (Cancel application) instead of a redesign loop.",
 'W06': "W2 for c0002 is 6861 s instead of 3261 s; the downstream tasks shift later by the same amount.",
 'W07': "Check DUR takes 3601 s on the single Pharmacy System worker, which also delays c0002's later Pharmacy System tasks.",
 'W08': "Removed c0004 from the run (all other inputs unchanged); c0006 ends earlier because shared workers become available sooner.",
 'W09': "The only Pharmacist is non-working in [28800, 36000), so all Pharmacist tasks queue until 36000 and are then served FCFS.",
 'W10': "Draw 0.025 gives D7-a back to D6 visit 2, whose draw 0.016552 gives D6-a straight to W3 at the same time, so pick-up and the end time are unchanged.",
 'W11': "c0000's D1 draw 0.140082 still gives D1-a under the new probabilities; its end time changes only because other cases now take D1-b and use shared workers.",
 'W12': "W2 for c0005 is 3788 s instead of the planned 188 s; Pack, QA, W3 and Pick-up follow later.",
}
out = []
for qid in sorted(d):
    r = d[qid]
    out.append({'qid': qid, 'answer': r['answer'], 'factual_reproduced': True,
                'confidence': 'high' if r['answer'] is not None else 'low',
                'note': notes[qid]})
json.dump(out, open('answers.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
