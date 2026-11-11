"""Blind sampled check for the workflow test questions, inputs only (evaluation-side).

A fixed random sample of test questions, 1 per family per process (12), with the document text the agents may use,
written to one folder per agent outside the repo. No gold, binding, change dict, reference code or reference output
is written there. The key (question ids) is kept in the repo for scoring by `validation/score_workflow_blind.py`.

Method, as for IT operations (Ashraf, 2026-11-08): each agent writes its own simulator from the front matter alone,
must reproduce the printed logs of every chapter it is given, then answers. This makes a further independent
implementation, not a hand check.

Usage: python -X utf8 scripts/make_workflow_blind_sample.py <questions.json> <out_dir> <key_json> <seed> <agent> [<agent> ...]
"""
import json
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow_policy_set as WP  # noqa: E402
import workflow_test_set as W  # noqa: E402


def pdf_of(doc):
    return WP.pdf(doc) if doc in WP.VARIANTS else W.pdf(doc)


def page_text(doc, first, last):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(pdf_of(doc)))
    return "\n".join(pdf[i].get_textpage().get_text_range().replace("\r", "") for i in range(first - 1, last))


def file_tag(doc):
    """loan, pharmacy (dev and test documents, as before), or loan_policyP etc. for a policy-variant document."""
    parts = doc.split("_")
    return parts[1] if doc not in WP.VARIANTS else f"{parts[1]}_{parts[2]}"


def main(q_path, out_dir, key_path, seed, *agents):
    if not agents:
        raise SystemExit("name at least one agent folder")
    rng = random.Random(int(seed))
    qs = json.loads(Path(q_path).read_text(encoding="utf-8"))
    pick = []
    for doc in sorted({q["doc"] for q in qs}):
        for fam in sorted({q["family"] for q in qs}):
            pool = sorted((q for q in qs if q["doc"] == doc and q["family"] == fam), key=lambda q: q["id"])
            pick += rng.sample(pool, 1)
    files, rows = {}, []
    for doc in sorted({q["doc"] for q in pick}):
        nav = WP.load_nav(doc)
        # A chapter runs from its heading's page to the page before the next chapter's heading (the last one to the
        # end of the PDF). The map node's own "pages" covers only the heading's text, not its section tables.
        starts = sorted((n["pages"][0], n["title"]) for n in nav["nodes"] if n["level"] == 0 and n["kind"] != "list")
        last_page = max(n["pages"][1] for n in nav["nodes"])
        chapters = {t: (p, (starts[i + 1][0] - 1) if i + 1 < len(starts) else last_page) for i, (p, t) in enumerate(starts)}
        first = starts[0][0]
        short = file_tag(doc)
        files[f"{short}_front_matter.txt"] = page_text(doc, 1, first - 1)
        for title in sorted({q["scope"] for q in pick if q["doc"] == doc}):
            lo, hi = chapters[title]
            text = page_text(doc, lo, hi)
            for sec in W.SECTIONS:      # every section of the chapter, and no part of the next chapter
                assert f"{title}: {sec}" in text, (doc, title, sec)
            assert not any(f"{t}: Cases" in text for _, t in starts if t != title), (doc, title)
            files[f"{short}_chapter_{title.replace(' ', '_')}.txt"] = text
    key = {}
    for k, q in enumerate(pick):
        short = file_tag(q["doc"])
        qid = f"W{k + 1:02d}"
        rows.append({"qid": qid, "process": q["doc"].split("_")[1], "front_matter_file": f"{short}_front_matter.txt",
                     "chapter_file": f"{short}_chapter_{q['scope'].replace(' ', '_')}.txt", "question": q["question"]})
        key[qid] = q["id"]
    for a in agents:
        d = Path(out_dir) / a
        d.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (d / name).write_text(text, encoding="utf-8")
        (d / "questions.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    import hashlib
    Path(key_path).write_text(json.dumps({"seed": int(seed), "questions": q_path.replace("\\", "/"),
                                          "questions_sha256": hashlib.sha256(Path(q_path).read_bytes()).hexdigest(),
                                          "input_files_sha256": {n: hashlib.sha256(t.encode("utf-8")).hexdigest()
                                                                 for n, t in sorted(files.items())},
                                          "questions_json_sha256": hashlib.sha256(json.dumps(rows, indent=1).encode("utf-8")).hexdigest(),
                                          "key": key}, indent=1), encoding="utf-8")
    print(len(rows), "questions,", len(files), "text files, agents:", agents, "->", out_dir)


if __name__ == "__main__":
    main(*sys.argv[1:])
