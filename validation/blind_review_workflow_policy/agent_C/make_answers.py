import json, os
H = os.path.dirname(os.path.abspath(__file__))
raw = {r['qid']: r for r in json.load(open(os.path.join(H, 'raw_answers.json')))}
notes = {
 'W01': "c0001 reaches 'Approve and post home insurance quote' only twice in Run 15, so the planned visit-4 work is never used; end unchanged.",
 'W02': "Removing c0005 frees capacity but does not alter c0011's path or timing; end unchanged at 52791.",
 'W03': "Appraiser_1 off 39600-54000 leaves one appraiser; Appraise property queue backs up and c0013 ends 127185 (was 122014).",
 'W04': "Draw 0.75 at D4 visit 2 now takes D4-b (Consider re-design) instead of D4-a; c0007 ends 147353 (was 137860).",
 'W05': "c0002's D4 draw still selects D4-b under 0.3/0.7 and no shared-resource effect reaches it; end unchanged.",
 'W06': "W1 visit 1 lengthened from 19840 to 39680 s; c0003 ends 229720 (was 227282).",
 'W07': "'Approve application' leads to End so c0000 can reach it only once; visit 3 cannot occur (the plan lists only visit 1). The change has no effect; end stays 227149.",
 'W08': "Removing c0004 does not change c0014's path or timing; end unchanged at 134835.",
 'W09': "AML Investigator_2 and _3 off 39600-68400; c0012's AML Check is delayed slightly and it ends 54147 (was 53792).",
 'W10': "Draw 0.75 at D2 sends c0012 to Design loan offer instead of Reject; offer path ends with Approve application next day at 120685.",
 'W11': "With D4-a 0.9, c0009's draw 0.713556 now takes D4-a (W3 then Approve application) instead of re-design/cancel; ends 120637.",
 'W12': "W2 visit 1 lengthened from 3370 to 6970 s; downstream work spills to later shifts and c0011 ends 134082 (was 120715).",
 'W13': "Check Insurance takes 2 s instead of 1; c0012 ends 1 s later at 31591.",
 'W14': "Removing c0003 frees a Technician earlier; c0001 ends 30305 (was 30322).",
 'W15': "Two extra Pharmacy System workers do not change c0013's timing; end unchanged at 31678.",
 'W16': "Draw 0.9 at D3 takes D3-b (D4 then Resolve DUR manually); c0001 ends 30431 (was 30322).",
 'W17': "With D6-a 0.7, c0002 (draw at D6 visit 1) goes out-of-stock to W3 and skips packing; ends 29962 (was 30435).",
 'W18': "W2 visit 1 of 0 s makes packing start immediately; c0003 ends 31217 (was 31299).",
 'W19': "Check Insurance takes 2 s instead of 1; c0014 ends 1 s later at 31785.",
 'W20': "Removing c0003 frees a Technician; c0004 ends 30598 (was 30617).",
 'W21': "Both Pharmacists (the whole pool in this document) off 28800-57600, so c0007's Check for Quality Assurance (enabled 30453) starts only at 57792 behind the queue formed at 57600; c0007 ends 58323.",
 'W22': "Draw 0.035 at D6 visit 1 takes D6-a (out of stock, W3 then Pick-up); c0008 ends 30744 (was 31201).",
 'W23': "With D6-a 0.7, c0007's D6 draw 0.426296 takes D6-a; skips packing and ends 30529 (was 30962).",
 'W24': "W2 visit 1 lengthened from 210 to 420 s; c0004 ends 30891 (was 30681).",
}
out = []
for qid in sorted(raw):
    r = raw[qid]
    ans = r['answer']
    conf = 'high'
    if qid == 'W07':
        ans = r['baseline_end']; conf = 'medium'
    out.append({'qid': qid, 'answer': ans, 'factual_reproduced': r['factual_reproduced'], 'confidence': conf, 'note': notes[qid]})
json.dump(out, open(os.path.join(H, 'answers.json'), 'w'), indent=1)
for o in out: print(o['qid'], o['answer'], o['factual_reproduced'], o['confidence'])
