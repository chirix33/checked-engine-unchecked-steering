"""Workflow test documents, maps and the dev/test split for Loan Application and Pharmacy (evaluation-side).

Test documents are rendered by `render_workflow_doc.render`, unchanged (same layout, D14, and the same printing rule,
MIN_VISITS), from runs disjoint from every dev run:

  dev   workflow_{loan,pharmacy}_dev   Run 01-04   seeds dev-<process>-01..04   (rendered 2026-11-04, unchanged)
  test  workflow_{loan,pharmacy}_test  Run 05-12   seeds test-<process>-05..12  (this script)

Each run is one independent deterministic realization with its own seed, so the provenance group is the run (split
by full run). Test chapter titles continue the dev numbering, so no test scope has a dev scope's title; the
library's evidence registry keys reuse by scope title, and a shared title would let dev evidence pass as test
evidence. reportlab's `invariant` mode is set only to make the PDF bytes reproducible (it fixes the timestamp and
file id); layout and text are the renderer's own.

Maps are built with the deterministic builder the OTF programs use (`otf_r1.navmap.build_map`), as in
`manifests/domain_readiness.md`. The split step checks that no existing program could have seen a test run.

Built DEVS-Gen programs live in WSL. `patterns` writes the test titles, seeds and test-only route draws to a folder;
`scripts/wsl_scan_workflow_programs.sh` searches every built program for them, and `splits` reads that scan's output
(`runs/workflow_test_v1/devs_gen_scan.txt`) and fails if it is missing, empty or finds anything.
Rerun `patterns`, the scan and `splits` after every new build (coding agent, more DEVS-Gen or OTF builds).

Usage: python -X utf8 scripts/workflow_test_set.py docs               (render test documents and maps; refuses to overwrite)
       python -X utf8 scripts/workflow_test_set.py patterns <dir>     (pattern files for the WSL scan)
       python -X utf8 scripts/workflow_test_set.py splits <out_json>  (provenance checks and the split file)
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for sub in ("redesign", "reference_engine", "scripts"):
    if str(ROOT / sub) not in sys.path:
        sys.path.insert(0, str(ROOT / sub))

N_CASES = 15                                   # same as replay_screen.N_CASES (dev)
TEST_RUNS = [f"Run {k:02d}" for k in range(5, 13)]
DEV_RUNS = ["Run 01", "Run 02", "Run 03", "Run 04"]
TEST_DOCS = {"workflow_loan_test": {"model": "Loan_Application_3_timers", "seed_prefix": "test-loan"},
             "workflow_pharmacy_test": {"model": "Pharmacy_3_timers", "seed_prefix": "test-pharmacy"}}
DEV_OF = {"workflow_loan_test": "workflow_loan_dev", "workflow_pharmacy_test": "workflow_pharmacy_dev"}
DOC_DIR = ROOT / "runs" / "workflow_docs"
DEV_PDF = {d: ROOT / "runs" / "build_test_v1" / "docs" / d / "document.pdf" for d in DEV_OF.values()}
# The map the pilot runner gives programs for dev questions (scripts/pilot_runner.py NAV_OF), read only.
DEV_NAV = {d: ROOT / f"runs/build_test_r1_claude/claude-sonnet-5-5/{d}/b2/navmap.json" for d in DEV_OF.values()}
SECTIONS = ["Cases", "Work plan", "Wait plan", "Route draws", "Task log", "Wait log", "Decision log"]


def register(rs):
    """Make replay_screen's lookups (model_files, seed_of, reference) know the test documents. It changes rs.DOCS
    for the whole process, so never call it in a process that also iterates rs.DOCS (make_pilot_questions.main,
    replay_screen's own targets and score steps)."""
    for doc, v in TEST_DOCS.items():
        rs.DOCS.setdefault(doc, v)
    return rs


def pdf(doc):
    return DOC_DIR / doc / "document.pdf" if doc in TEST_DOCS else DEV_PDF[doc]


def nav_path(doc):
    return DOC_DIR / doc / "navmap.json" if doc in TEST_DOCS else DEV_NAV[doc]


def load_nav(doc):
    return json.loads(nav_path(doc).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seed(doc, run):
    prefix = TEST_DOCS[doc]["seed_prefix"] if doc in TEST_DOCS else {"workflow_loan_dev": "dev-loan", "workflow_pharmacy_dev": "dev-pharmacy"}[doc]
    return f"{prefix}-{run.split()[1]}"


def docs():
    import render_workflow_doc as render
    from reportlab import rl_config
    from otf_r1 import navmap
    rl_config.invariant = 1
    for doc, v in TEST_DOCS.items():
        out = DOC_DIR / doc
        if (out / "document.pdf").exists():
            raise SystemExit(f"{out / 'document.pdf'} exists; remove it by hand to re-render")
        chapters = [(run, seed(doc, run), []) for run in TEST_RUNS]
        render.render(str(ROOT), v["model"], str(out), chapters, N_CASES)
        nav = navmap.build_map(out / "document.pdf")
        (out / "navmap.json").write_text(json.dumps(nav, indent=1), encoding="utf-8")
        print(doc, "pdf", sha(out / "document.pdf"), "navmap", sha(out / "navmap.json"))


# ---------------------------------------------------------------- provenance checks
def _tables(nav):
    out = {}
    for n in nav["nodes"]:
        if n["kind"] == "table" and ": " in n["title"]:
            scope, section = n["title"].split(": ", 1)
            out[(scope, section)] = [tuple(r) for r in n["table"]["rows"]]
    return out


def _chapters(nav):
    return [n["title"] for n in nav["nodes"] if n["level"] == 0 and n["kind"] != "list"]


def overlap(dev_nav, test_nav):
    """Per section: identical whole tables between any dev and any test run, and identical rows, excluding rows
    that are the same in every dev run (published constants such as a fixed-duration activity)."""
    a, b = _tables(dev_nav), _tables(test_nav)
    out = {}
    for sec in SECTIONS:
        dev_runs = {s: set(rows) for (s, x), rows in a.items() if x == sec}
        test_runs = {s: set(rows) for (s, x), rows in b.items() if x == sec}
        common = set.intersection(*dev_runs.values()) if dev_runs else set()
        same_tables = [[d, t] for d, dr in dev_runs.items() for t, tr in test_runs.items() if dr == tr]
        shared = sorted({r for tr in test_runs.values() for dr in dev_runs.values() for r in (tr & dr) - common})
        out[sec] = {"identical_tables": same_tables, "rows_in_every_dev_run": len(common),
                    "other_shared_rows": len(shared), "examples": [list(r) for r in shared[:3]]}
    return out


def program_inputs(test_titles, test_seeds, dev_maps):
    """Every OTF program folder for a workflow document, and every other stored workflow map: what it read."""
    by_id = {nav["document_id"]: doc for doc, nav in dev_maps.items()}
    rows = []
    for p in sorted(glob.glob(str(ROOT / "runs" / "**" / "navmap.json"), recursive=True)):
        p = Path(p)
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        # evaluation-side folders made by these scripts (test/variant documents, superseded variant renders)
        if "workflow_" not in rel or rel.startswith(("runs/workflow_docs/", "runs/workflow_policy_v1/", "runs/workflow_test_v1/")):
            continue
        nav = json.loads(p.read_text(encoding="utf-8"))
        prog = p.parent / "program.json"
        code = json.loads(prog.read_text(encoding="utf-8")).get("code", "") if prog.exists() else ""
        doc = by_id.get(nav.get("document_id"))
        rows.append({"path": rel, "program": prog.exists(), "built_on": doc,
                     "map_equals_dev_map": doc is not None and nav == dev_maps[doc],
                     "chapters": _chapters(nav),
                     "names_a_test_chapter": [t for t in test_titles if t in json.dumps(nav) or t in code],
                     "names_a_test_seed": [s for s in test_seeds if s in json.dumps(nav) or s in code]})
    return rows


def _draw_rows(maps):
    out = set()
    for nav in maps.values():
        for (scope, sec), rows in _tables(nav).items():
            if sec == "Route draws":
                out |= {(r[0], r[1], v) for r in rows for v in r[2:] if v}
    return out


def _json_draws(data):
    """Every {"case", "decision", "draw"} object anywhere in a JSON value (task configs nest them in lists and strings)."""
    found = set()
    if isinstance(data, dict):
        if {"case", "decision", "draw"} <= set(data):
            found.add((data["case"], data["decision"], f"{float(data['draw']):.6f}"))
        for v in data.values():
            found |= _json_draws(v)
    elif isinstance(data, list):
        for v in data:
            found |= _json_draws(v)
    elif isinstance(data, str) and data.lstrip()[:1] in ("{", "["):
        try:
            found |= _json_draws(json.loads(data))
        except ValueError:
            pass
    return found


def spec_inputs(test_titles, test_seeds, test_maps, dev_maps):
    """Files every spec-built platform (DEVS-Gen, plain coding agent) builds from: no test title, seed or route draw."""
    import re
    test_rows, dev_rows = _draw_rows(test_maps), _draw_rows(dev_maps)
    rows = []
    for folder in ("adapters/devs_gen_tasks", "adapters/generic_tasks"):
        for p in sorted((ROOT / folder).glob("Workflow*/**/*")):
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            draws = set()
            if p.suffix == ".json":
                draws = _json_draws(json.loads(text))
            else:
                for m in re.finditer(r'"case": "(c[0-9]+)", "decision": "(D[0-9]+)", "visit": [0-9]+, "draw": ([0-9.]+)', text):
                    draws.add((m.group(1), m.group(2), f"{float(m.group(3)):.6f}"))
            rows.append({"path": str(p.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(p),
                         "names_a_test_chapter": [t for t in test_titles if t in text],
                         "names_a_test_seed": [s for s in test_seeds if s in text],
                         "route_draws_found": len(draws), "route_draws_shared_with_dev": len(draws & dev_rows),
                         "route_draws_shared_with_test": len(draws & test_rows)})
    return rows


def splits(out_path):
    from otf_r1 import navmap
    import engine
    import render_workflow_doc as render
    import replay_screen as rs
    register(rs)
    from assurance.request import schema_from_map
    dev_maps = {d: json.loads(DEV_NAV[d].read_text(encoding="utf-8")) for d in DEV_OF.values()}
    test_maps = {d: load_nav(d) for d in TEST_DOCS}
    res = {"version": "workflow_splits_v1",
           "rule": "split by full run. Each run is one independent deterministic realization of the published process "
                   "model with its own seed; the provenance group is the run. All runs of a process share the process "
                   "model and front matter, which is the reuse condition (dev-built programs answer test questions on "
                   "test records).",
           "n_cases_per_run": N_CASES, "docs": {}, "checks": {}}
    for doc_t, doc_d in DEV_OF.items():
        for doc, split, runs in ((doc_d, "dev", DEV_RUNS), (doc_t, "test", TEST_RUNS)):
            nav = dev_maps.get(doc) or test_maps.get(doc)
            rebuilt = navmap.build_map(pdf(doc))
            meta_p = pdf(doc).parent / "document_meta.json"
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            bpmn, params = rs.model_files(str(ROOT), doc)
            res["docs"][doc] = {
                "split": split, "process": TEST_DOCS.get(doc, rs.DOCS.get(doc))["model"],
                "pdf": str(pdf(doc).relative_to(ROOT)).replace("\\", "/"), "pdf_sha256": sha(pdf(doc)),
                "navmap": str(nav_path(doc).relative_to(ROOT)).replace("\\", "/"), "navmap_sha256": sha(nav_path(doc)),
                "document_meta_sha256": sha(meta_p), "pages": meta["pages"],
                "map_rebuilt_from_pdf_equals_stored": rebuilt == nav,
                "model_files_sha256": {Path(bpmn).name: sha(bpmn), Path(params).name: sha(params)},
                "policy_fingerprint": schema_from_map(nav).policy_fingerprint(),
                "runs": [{"title": r, "seed": seed(doc, r), "group": f"{doc}/{r}", "split": split,
                          **{k: v for k, v in next(s for s in meta["scopes"] if s["title"] == r).items() if k != "title"}}
                         for r in runs]}
            assert _chapters(nav) == runs, (doc, _chapters(nav))
            # every printed section equals the renderer's tables for the reference's factual run with this seed
            model = engine.Model(bpmn, params)
            labels, cycles, tabs = render.Labels(model, bpmn), render.in_cycle(model), _tables(nav)
            for r in runs:
                expect, _ = render.chapter_tables(engine, model, labels, cycles, rs.scenario(doc, r, {}), seed(doc, r))
                assert [x[0] for x in expect] == SECTIONS, (doc, r)
                for section, rows, _w in expect:
                    assert [tuple(x) for x in rows[1:]] == tabs[(r, section)], (doc, r, section)
        dev_doc, test_doc = res["docs"][doc_d], res["docs"][doc_t]
        res["checks"][doc_t] = {
            "seeds_disjoint": not ({x["seed"] for x in dev_doc["runs"]} & {x["seed"] for x in test_doc["runs"]}),
            "titles_disjoint": not (set(_chapters(dev_maps[doc_d])) & set(_chapters(test_maps[doc_t]))),
            "factual_sections_checked": SECTIONS,
            "same_process_model": dev_doc["model_files_sha256"] == test_doc["model_files_sha256"],
            "same_policy_fingerprint_as_dev": dev_doc["policy_fingerprint"] == test_doc["policy_fingerprint"],
            "table_overlap_with_dev": overlap(dev_maps[doc_d], test_maps[doc_t])}
    titles = [f"{r}" for r in TEST_RUNS]
    seeds = [seed(d, r) for d in TEST_DOCS for r in TEST_RUNS]
    progs = program_inputs(titles, seeds, dev_maps)
    specs = spec_inputs(titles, seeds, test_maps, dev_maps)
    scan_p = ROOT / "runs" / "workflow_test_v1" / "devs_gen_scan.txt"
    scan = scan_p.read_text(encoding="utf-8").splitlines() if scan_p.exists() else []
    devs = [dict(zip(("program", "files_hash"), ln.split()[:2]), **{k: int(v) for k, v in (x.split("=") for x in ln.split()[2:])})
            for ln in scan if ln.strip() and not ln.startswith("program_dirs=")]
    res["devs_gen_programs"] = {"scan": "runs/workflow_test_v1/devs_gen_scan.txt",
                                "scan_sha256": sha(scan_p) if scan_p.exists() else None, "programs": devs}
    res["program_inputs"] = progs
    res["spec_inputs"] = specs
    # every stored map: dev chapters only and no test title or seed; a program's map must also be a dev map exactly
    bad = [p for p in progs if not (set(p["chapters"]) <= set(DEV_RUNS) and not p["names_a_test_chapter"]
                                    and not p["names_a_test_seed"] and (not p["program"] or (p["built_on"] and p["map_equals_dev_map"])))]
    bad_specs = [s for s in specs if s["names_a_test_chapter"] or s["names_a_test_seed"] or s["route_draws_shared_with_test"]]
    bad_devs = [d for d in devs if d["files_naming_test"] or d["test_draw_strings"]]
    empty = [what for what, n in (("maps", len(progs)), ("spec files", len(specs)), ("DEVS-Gen scan", len(devs))) if n == 0]
    res["checks"]["program_input_check"] = {"maps": len(progs), "programs": sum(p["program"] for p in progs),
                                            "violations": bad, "spec_files": len(specs), "spec_violations": bad_specs,
                                            "devs_gen_programs": len(devs), "devs_gen_violations": bad_devs,
                                            "nothing_found": empty}
    Path(out_path).write_text(json.dumps(res, indent=1), encoding="utf-8")
    for doc_t, c in res["checks"].items():
        if doc_t.startswith("workflow_"):
            tab = {s: (len(v["identical_tables"]), v["other_shared_rows"]) for s, v in c["table_overlap_with_dev"].items()}
            print(doc_t, {k: v for k, v in c.items() if k != "table_overlap_with_dev"}, "overlap (tables, rows):", tab)
    for doc, d in res["docs"].items():
        print(doc, d["split"], d["pages"], "pages, map rebuilt equals stored:", d["map_rebuilt_from_pdf_equals_stored"],
              "fingerprint", d["policy_fingerprint"])
    pc = res["checks"]["program_input_check"]
    print("program inputs:", pc["maps"], "maps,", pc["programs"], "programs,", len(pc["violations"]), "violations;",
          pc["spec_files"], "spec files,", len(pc["spec_violations"]), "violations;",
          pc["devs_gen_programs"], "DEVS-Gen programs,", len(bad_devs), "violations; empty:", empty)
    return 1 if bad or bad_specs or bad_devs or empty else 0


if __name__ == "__main__":
    if sys.argv[1] == "docs":
        docs()
    elif sys.argv[1] == "patterns":
        out = Path(sys.argv[2])
        out.mkdir(parents=True, exist_ok=True)
        import workflow_policy_set as wp          # the policy-variant documents are held out from builders too
        tmaps = {d: load_nav(d) for d in TEST_DOCS}
        tmaps.update({d: wp.load_nav(d) for d in wp.VARIANTS})
        dmaps = {d: json.loads(DEV_NAV[d].read_text(encoding="utf-8")) for d in DEV_OF.values()}
        only = sorted({v for _, _, v in _draw_rows(tmaps)} - {v for _, _, v in _draw_rows(dmaps)})
        (out / "test_draws.txt").write_bytes(("\n".join(only) + "\n").encode())
        names = TEST_RUNS + [seed(d, r) for d in TEST_DOCS for r in TEST_RUNS]
        names += sorted({r for v in wp.VARIANTS.values() for r in v["runs"]}) + [wp.seed(d, r) for d, v in wp.VARIANTS.items() for r in v["runs"]]
        (out / "test_names.txt").write_bytes(("\n".join(names) + "\n").encode())
        print(len(only), "test-only draw strings,", len(names), "names ->", out)
    elif sys.argv[1] == "splits":
        sys.exit(splits(sys.argv[2]))
    else:
        raise SystemExit(__doc__)
