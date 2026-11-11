import json
raw = {r['qid']: r for r in json.load(open('raw_results.json'))}
notes = {
 'W01': "Visit 4 of 'Approve and post home insurance quote' is never reached by c0001 (only 2 visits occur), so the change has no effect; answer equals the recorded end.",
 'W02': "Removing c0005 frees capacity but does not alter any task of c0011; its end is unchanged.",
 'W03': "Appraiser_1's unavailable interval is treated as non-working time (in-progress task pauses); the resulting delays push c0013 later. Unavailability is not exercised by the factual records.",
 'W04': "Draw 0.75 at D4 visit 2 now selects D4-b (Consider re-design loan offer) instead of D4-a; simulated forward with the listed plans.",
 'W05': "c0002's D4 visit-1 draw is at least 0.5, so it takes D4-b under both the old and new probabilities; other cases' rerouting does not touch its tasks, so the end is unchanged.",
 'W06': "Longer W1 delays the second form check and everything after it.",
 'W07': "'Approve application' leads directly to End, so a third visit can never happen; the change has no effect and the answer equals the recorded end.",
 'W08': "Removing c0004 does not change any task of c0014; end unchanged.",
 'W09': "Two AML Investigators unavailable 11:00-19:00 Monday; remaining workers plus pausing make c0012 end 355 s later. Unavailability is not exercised by the factual records.",
 'W10': "Draw 0.75 at D2 selects D2-b (Design loan offer) instead of Reject; the offer path ends the next working day.",
 'W11': "With D4-a at 0.9, the draw 0.713556 now selects D4-a (W3 then Approve application) instead of re-design/cancel.",
 'W12': "Longer W2 delays Assess loan risk and the following chain; c0011 crosses into later working periods.",
 'W13': "Check Insurance takes 1 s longer on the single Pharmacy System worker, shifting c0012 by 1 s.",
 'W14': "Removing c0003 reduces queueing, so c0001 finishes 17 s earlier.",
 'W15': "Two extra Pharmacy System workers (same calendar) do not change c0013's end in this run.",
 'W16': "Draw 0.9 at D3 selects D3-b; D4 (its own draw 0.915059) then takes D4-a, adding Resolve DUR manually before Check Insurance.",
 'W17': "With D6-a at 0.7, c0002's D6 draw now routes to W3 directly (skipping packing and QA).",
 'W18': "Zero-second W2 lets packing start immediately after D6.",
 'W19': "Check Insurance takes 1 s longer; c0014 ends 1 s later.",
 'W20': "Removing c0003 lets c0004 get workers earlier; it ends 19 s earlier.",
 'W21': "Both Pharmacists unavailable 08:00-16:00 Monday, so Check for Quality Assurance waits until 16:00. Unavailability is not exercised by the factual records.",
 'W22': "Draw 0.035 at D6 selects D6-a (W3 then Pick-up), skipping packing and QA.",
 'W23': "With D6-a at 0.7, c0007's D6 draw now routes directly to W3.",
 'W24': "W2 lasts 420 s instead of 210 s, delaying packing, QA and pick-up.",
}
medium = {'W03', 'W09', 'W21'}
out = []
for qid in sorted(raw):
    r = raw[qid]
    assert not r['errors']
    out.append(dict(qid=qid, answer=int(r['answer']), factual_reproduced=bool(r['repro']),
                    confidence='medium' if qid in medium else 'high', note=notes[qid]))
json.dump(out, open('answers.json', 'w'), indent=1)
for o in out: print(o['qid'], o['answer'], o['confidence'])
