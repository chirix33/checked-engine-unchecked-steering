"""Apply each question's change to its chapter inputs, rerun, write answers.json."""
import json
import os
import re
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim  # noqa: E402

# Changes transcribed by hand from questions.json (one per question).
CHANGES = {
    "W01": ("c0005", {"work": {("c0005", "Reject application", 1): 1}}),
    "W02": ("c0003", {"remove": {"c0001"}}),
    "W03": ("c0005", {"unavailable": {"Appraiser_0": [(39600, 54000)],
                                      "Appraiser_1": [(39600, 54000)]}}),
    "W04": ("c0011", {"draw": {("c0011", "D1", 1): Fraction("0.100000")}}),
    "W05": ("c0007", {"probs": {"D5": [Fraction("0.7"), Fraction("0.3")]}}),
    "W06": ("c0002", {"wait": {("c0002", "W2", 1): 6861}}),
    "W07": ("c0002", {"work": {("c0002", "Check DUR", 1): 3601}}),
    "W08": ("c0006", {"remove": {"c0004"}}),
    "W09": ("c0007", {"unavailable": {"Pharmacist_0": [(28800, 36000)]}}),
    "W10": ("c0007", {"draw": {("c0007", "D3", 1): Fraction("0.900000")}}),
    "W11": ("c0000", {"probs": {"D1": [Fraction("0.3"), Fraction("0.7")]}}),
    "W12": ("c0009", {"wait": {("c0009", "W3", 1): 672}}),
}


def path_of(res, c):
    rows = [(v[0], "task", k[1], k[2], v) for k, v in res["tasks"].items() if k[0] == c]
    rows += [(v[0], "wait", k[1], k[2], v) for k, v in res["waits"].items() if k[0] == c]
    rows += [(v[0], "dec", k[1], k[2], v) for k, v in res["decs"].items() if k[0] == c]
    return sorted(rows)


def main():
    with open(os.path.join(HERE, "questions.json"), encoding="utf-8") as f:
        qs = json.load(f)
    out = []
    for q in qs:
        cid, change = CHANGES[q["qid"]]
        assert re.search(rf"would case {cid} end", q["question"]), q["qid"]
        ch = sim.parse_chapter(os.path.join(HERE, q["chapter_file"]))
        base = sim.simulate(q["process"], ch)
        exact = not sim.compare(ch, base)
        res = sim.simulate(q["process"], ch, change)
        fact = ch["cases"][cid][1]
        ans = res["ends"][cid]
        bp, cp = path_of(base, cid), path_of(res, cid)
        first_diff = next((f"{a} -> {b}" for a, b in zip(bp, cp) if a != b),
                          "none" if len(bp) == len(cp) else "path length differs")
        print(f"{q['qid']} {q['chapter_file']} {cid}: factual {fact} -> {ans} "
              f"(delta {ans - fact}); reproduced={exact}")
        print(f"    first differing record for {cid}: {first_diff}")
        out.append({"qid": q["qid"], "answer": ans, "factual_reproduced": exact,
                    "_fact": fact})
    with open(os.path.join(HERE, "raw_results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
