"""Blind sampled check, inputs only: a fixed random sample of manufacturing and IT questions (dev and test), with
the document text the agents may use, written to a folder outside the repo. No gold, binding, change dict or
reference output is written there. The key (question ids) is kept in the repo for scoring.

Manufacturing: 2 questions per family, answered by hand. IT: 2 per family, answered with the agent's own scheduler
written from the front matter alone (a third independent implementation, Ashraf 2026-11-08).

Usage: python -X utf8 scripts/make_mlsys_blind_sample.py <out_dir> <key_json> <seed>
"""
import json
import random
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mlsys_gold as G  # noqa: E402


def page_text(doc, first, last):
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(G.pdf(doc)))
    return "\n".join(pdf[i].get_textpage().get_text_range().replace("\r", "") for i in range(first - 1, last))


def main(out_dir, key_path, seed):
    rng = random.Random(int(seed))
    qs = []
    for split in ("dev", "test"):
        qs += json.loads((G.ROOT / "manifests" / f"mlsys_questions_{split}_v1.json").read_text(encoding="utf-8"))
    out = Path(out_dir)
    key = {}
    for dom, short in (("manufacturing", "mfg"), ("it_ops", "itops")):
        d = out / short
        d.mkdir(parents=True, exist_ok=True)
        pick = []
        for fam in sorted({q["family"] for q in qs if q["domain"] == dom}):
            pool = sorted((q for q in qs if q["family"] == fam), key=lambda q: q["id"])
            pick += rng.sample(pool, 2)
        manifests = {doc: json.loads((G.RUNS / doc / "manifest.json").read_text()) for doc in G.DOCS[dom]}
        first_ch = min(s["start_page"] for s in manifests[G.DOCS[dom][0]]["scopes"])
        (d / "front_matter.txt").write_text(page_text(G.DOCS[dom][0], 1, first_ch - 1), encoding="utf-8")
        chapters = {}
        for q in pick:
            sc = next(s for s in manifests[q["doc"]]["scopes"] if s["title"] == q["scope"])
            fname = "chapter_" + q["scope"].replace(",", "").replace(" ", "_") + ".txt"
            if fname not in chapters:
                (d / fname).write_text(page_text(q["doc"], sc["start_page"], sc["end_page"]), encoding="utf-8")
                chapters[fname] = q["scope"]
        rows = [{"qid": f"B{k + 1:02d}", "chapter_file": next(f for f, t in chapters.items() if t == q["scope"]),
                 "question": q["question"]} for k, q in enumerate(pick)]
        (d / "questions.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        key[short] = {r["qid"]: q["id"] for r, q in zip(rows, pick)}
    Path(key_path).write_text(json.dumps(key, indent=1), encoding="utf-8")
    print({k: len(v) for k, v in key.items()}, "questions; folders under", out)


if __name__ == "__main__":
    main(*sys.argv[1:4])
