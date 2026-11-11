"""Write answers.json from raw_results.json plus hand-written notes."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
raw = {r["qid"]: r for r in json.load(open(os.path.join(HERE, "raw_results.json")))}
NOTES = {
 "W01": "Factual end of c0005 is 215354; its Reject application visit 1 ran 213522-215354 on Clerk_1, and with 1 s of work it ends at 213523, which is the case end.",
 "W02": "Factual end of c0003 is 45859; without c0001 the shared worker queues change (worker assignments differ from c0003's first task on), and c0003 ends 260 s earlier.",
 "W03": "Factual end of c0005 is 47253; its Appraise property (started 38826) pauses at 39600 and resumes at 54000, ending 55034, so W2 and Assess loan risk slip past closing into the next day.",
 "W04": "Factual end of c0011 is 52875 (D1-b at visit 1); draw 0.1 < 0.2 sends it to D1-a (return to applicant), adding W1, Applicant completes form and a second completeness check before the rest of the process.",
 "W05": "Factual end of c0007 is 126373 (D5-b at visit 1, re-design loop); with D5-a=0.7 its D5 draw now selects D5-a, so it goes to Cancel application and ends at 59158.",
 "W06": "Factual end of c0002 is 54566 (W2 visit 1 lasted 3261 s); with 6861 s W2 ends 3600 s later and every following step shifts by exactly 3600 s.",
 "W07": "Factual end of c0002 is 30466; Check DUR on the single Pharmacy System worker now runs 29456-33057, delaying c0002 by 3589 s (other cases' system tasks also queue behind it).",
 "W08": "Factual end of c0006 is 31661; removing c0004 changes worker assignments and queueing for later cases, and c0006 ends 99 s earlier.",
 "W09": "Factual end of c0007 is 31613; Pharmacist_0 (the only pharmacist) cannot work until 36000, so c0007's Check for Quality Assurance waits behind the backlog and the case ends at 37688.",
 "W10": "Factual end of c0007 is 31116; draw 0.9 makes D3-b then D4-a (Resolve DUR manually, 30098-30223), but its Quality Assurance still starts at 30615 behind the Pharmacist queue, so the end is unchanged.",
 "W11": "Factual end of c0000 is 30198; c0000's own D1 draw 0.140082 still gives D1-a, but other cases switch to Contact Doctor about refill and occupy Technicians, so its Pick-up starts 37 s later.",
 "W12": "Factual end of c0009 is 31457 (W3 visit 1 lasted 336 s); with 672 s Pick-up starts 336 s later and the case ends at 31793.",
}
out = []
for qid in sorted(raw):
    r = raw[qid]
    out.append({"qid": qid, "answer": r["answer"], "factual_reproduced": r["factual_reproduced"],
                "confidence": "high" if r["factual_reproduced"] else "low", "note": NOTES[qid]})
json.dump(out, open(os.path.join(HERE, "answers.json"), "w", encoding="utf-8"), indent=1)
print(json.dumps([(o["qid"], o["answer"]) for o in out]))
