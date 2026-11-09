"""Provenance-grouped dev/test split for manufacturing and IT operations, and the build-input check.

Manufacturing: a chapter's order book is the first 7 days of the same plant's next period, so periods k and k+1
of one plant share source days. Dev = periods 01-03, period 04 is left out as the boundary, test = periods 05-15.
IT: a job joins a window only if its submit time lies in the window, so windows can share jobs only if they
overlap in time. Windows are grouped by time overlap (connected components); dev = the groups holding the build
document's windows, test = the others. Real job and machine ids from the raw rebuild confirm no sharing across
the split.

Build-input check (Ashraf, 2026-11-08: every platform builds once on dev and answers test on unseen chapters):
every built OTF program for these domains must have been built on the dev build document, whose chapters are all
dev, and no program's code may name a test chapter or window.

Usage: python -X utf8 scripts/make_mlsys_splits.py <out_json>
"""
import glob
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mlsys_gold as G  # noqa: E402

ROOT = G.ROOT


def mfg_split():
    out = {}
    seen = set(G.doc_titles("mfg_dev"))
    for title, doc in sorted(G.doc_of("manufacturing").items()):
        s = G.scope("manufacturing", title)
        split = "dev" if s.period <= 3 else "excluded_boundary" if s.period == 4 else "test"
        out[title] = {"doc": doc, "plant": s.plant, "period": s.period, "group": f"plant {s.plant}",
                      "source_days": [s.first_day, s.horizon_day], "split": split, "seen_at_build": title in seen}
    return out


def it_split():
    W = []
    for title, doc in G.doc_of("it_ops").items():
        w = G.scope("it_ops", title)
        W.append((w.meta["start_us"], title, doc, w))
    W.sort()
    groups, cur, end = [], [], -1
    for start, title, doc, w in W:
        if cur and start < end:
            cur.append(title)
            end = max(end, start + w.length * 10 ** 6)
        else:
            if cur:
                groups.append(cur)
            cur, end = [title], start + w.length * 10 ** 6
    groups.append(cur)
    gid = {t: k for k, g in enumerate(groups) for t in g}
    seen = set(G.doc_titles("itops_dev"))
    dev_groups = {gid[t] for t in seen}
    out = {}
    for start, title, doc, w in W:
        out[title] = {"doc": doc, "group": gid[title], "start_us": start, "parts": w.meta["parts"],
                      "split": "dev" if gid[title] in dev_groups else "test", "seen_at_build": title in seen,
                      "real_jobs": sorted(int(j) for j in w.meta["real_jobs"].values()),
                      "real_machines": sorted(int(m) for m in w.meta["real_machines"])}
    # sharing across the split, from real ids
    shared_jobs, shared_machines = [], []
    for a in out:
        for b in out:
            if a < b and out[a]["split"] != out[b]["split"]:
                if set(out[a]["real_jobs"]) & set(out[b]["real_jobs"]):
                    shared_jobs.append([a, b])
                if set(out[a]["real_machines"]) & set(out[b]["real_machines"]):
                    shared_machines.append([a, b])
    within = sum(1 for a in out for b in out if a < b and out[a]["group"] == out[b]["group"]
                 and set(out[a]["real_jobs"]) & set(out[b]["real_jobs"]))
    return out, {"groups": groups, "dev_groups": sorted(dev_groups), "cross_split_shared_jobs": shared_jobs,
                 "cross_split_shared_machines": shared_machines, "within_group_pairs_sharing_jobs": within}


def build_inputs(domain, splits):
    """Every built program folder for this domain: which document and chapters it was built on."""
    sys.path.insert(0, str(ROOT / "redesign"))
    from otf_r1 import navmap
    doc = G.BUILD_DOC[domain]
    ref_titles = set(G.doc_titles(doc))
    nav_doc = navmap.build_map(G.pdf(doc))
    test_titles = [t for t, v in splits.items() if v["split"] == "test"]
    rows = []
    for d in sorted(glob.glob(str(ROOT / "runs" / "build_test_*" / "*" / "*" / "b*"))):
        p = Path(d)
        if p.parent.name not in ("mfg_dev", "itops_dev") or (p.parent.name == "mfg_dev") != (domain == "manufacturing"):
            continue
        nav_p, prog_p = p / "navmap.json", p / "program.json"
        if not nav_p.exists():
            rows.append({"build": str(p.relative_to(ROOT)), "navmap": False})
            continue
        nav = json.loads(nav_p.read_text(encoding="utf-8"))
        titles = {n["title"] for n in nav["nodes"] if n["level"] == 0 and n["kind"] != "list"}
        code = json.loads(prog_p.read_text(encoding="utf-8")).get("code", "") if prog_p.exists() else ""
        rows.append({"build": str(p.relative_to(ROOT)).replace("\\", "/"), "program": prog_p.exists(),
                     "navmap_equals_build_document": nav == nav_doc,
                     "build_pdf_id": nav.get("document_id"), "chapters": sorted(titles),
                     "all_chapters_dev": all(splits[t]["split"] == "dev" for t in titles),
                     "chapters_equal_build_document": titles == ref_titles,
                     "code_names_a_test_chapter": [t for t in test_titles if t in code]})
    return rows


def main(out_path):
    mfg = mfg_split()
    it, it_info = it_split()
    res = {"version": "mlsys_splits_v1",
           "rule": {"manufacturing": "dev = periods 01-03, period 04 excluded (boundary), test = periods 05-15",
                    "it_ops": "time-overlap groups; dev = groups of the build document's windows; test = the rest"},
           "manufacturing": mfg, "it_ops": it, "it_groups": it_info,
           "build_inputs": {"manufacturing": build_inputs("manufacturing", mfg), "it_ops": build_inputs("it_ops", it)}}
    bad = [r for dom in res["build_inputs"].values() for r in dom
           if r.get("program") and not (r["all_chapters_dev"] and r["navmap_equals_build_document"]
                                        and not r["code_names_a_test_chapter"])]
    res["build_input_check"] = {"programs": sum(1 for dom in res["build_inputs"].values() for r in dom if r.get("program")),
                                "violations": bad}
    Path(out_path).write_text(json.dumps(res, indent=1), encoding="utf-8")
    for dom, s in (("manufacturing", mfg), ("it_ops", it)):
        from collections import Counter
        print(dom, Counter(v["split"] for v in s.values()), "seen at build:", sum(v["seen_at_build"] for v in s.values()))
    print("IT groups", [len(g) for g in it_info["groups"]], "dev groups", it_info["dev_groups"],
          "cross-split shared jobs", len(it_info["cross_split_shared_jobs"]), "machines", len(it_info["cross_split_shared_machines"]),
          "within-group pairs sharing jobs", it_info["within_group_pairs_sharing_jobs"])
    print("build-input check:", res["build_input_check"]["programs"], "programs,", len(bad), "violations")


if __name__ == "__main__":
    main(*sys.argv[1:2])
