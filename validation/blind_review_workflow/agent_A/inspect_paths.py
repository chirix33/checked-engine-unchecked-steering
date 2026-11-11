"""Print one case's factual vs changed path for a question (debug aid)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import sim, answer_questions as aq, json
qs = {q["qid"]: q for q in json.load(open(os.path.join(HERE, "questions.json")))}
for qid in sys.argv[1:]:
    q = qs[qid]; cid, chg = aq.CHANGES[qid]
    ch = sim.parse_chapter(os.path.join(HERE, q["chapter_file"]))
    print("==", qid, cid, "draws:", {k[1]: [str(float(x)) for x in v[:2]] for k, v in ch["draw"].items() if k[0] == cid})
    for lab, r in (("fact", sim.simulate(q["process"], ch)), ("chg", sim.simulate(q["process"], ch, chg))):
        print(" ", lab, r["ends"][cid])
        for row in aq.path_of(r, cid): print("    ", row[1:])
