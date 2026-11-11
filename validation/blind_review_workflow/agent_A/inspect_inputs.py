"""Check which sections each chapter file contains and write answers.json.

All chapter files in this folder turned out to be truncated, so no simulation
is possible; this script documents that and records factual case ends.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SECTIONS = ["Cases", "Work plan", "Wait plan", "Route draws",
            "Task log", "Wait log", "Decision log"]


def read_chapter(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        lines = f.read().splitlines()
    present = []
    cases = {}
    work_cases = set()
    sec = None
    for ln in lines:
        m = re.match(r"Run \d+: (.+)$", ln)
        if m:
            sec = m.group(1).strip()
            present.append(sec)
            continue
        parts = ln.split()
        if sec == "Cases" and parts and re.fullmatch(r"c\d{4}", parts[0]):
            cases[parts[0]] = (int(parts[1]), int(parts[2]))
        if sec == "Work plan" and parts and re.fullmatch(r"c\d{4}", parts[0]):
            work_cases.add(parts[0])
    return {"lines": len(lines), "sections": present, "cases": cases,
            "work_plan_cases": sorted(work_cases), "last_line": lines[-1]}


def main():
    chapters = sorted(f for f in os.listdir(HERE) if "_chapter_" in f)
    info = {c: read_chapter(c) for c in chapters}
    for c, d in info.items():
        missing = [s for s in SECTIONS if s not in d["sections"]]
        print(f"{c}: {d['lines']} lines; sections={d['sections']}; "
              f"missing={missing}; work-plan cases={d['work_plan_cases']}; "
              f"last line={d['last_line']!r}")

    with open(os.path.join(HERE, "questions.json"), encoding="utf-8") as f:
        questions = json.load(f)
    answers = []
    for q in questions:
        d = info[q["chapter_file"]]
        m = re.search(r"would case (c\d{4}) end", q["question"])
        cid = m.group(1)
        arr, end = d["cases"][cid]
        answers.append({
            "qid": q["qid"],
            "answer": None,
            "factual_reproduced": False,
            "confidence": "low",
            "note": (f"Factual end of {cid} in the Cases table is {end} "
                     f"(arrival {arr}). Not simulated: {q['chapter_file']} is "
                     "truncated (no Wait plan, Route draws or logs; Work plan "
                     "only for c0000-c0001), so the change could not be applied."),
        })
    with open(os.path.join(HERE, "answers.json"), "w", encoding="utf-8") as f:
        json.dump(answers, f, indent=1)
    for a in answers:
        print(a["qid"], a["note"][:60])


if __name__ == "__main__":
    main()
