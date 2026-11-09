"""Adapter smoke run on dev data: existing OTF programs through `assurance.mlsys` (no model calls, no builds).

For each built program for manufacturing or IT operations: the learned record projection, the history check on
every dev chapter or window (seen at build and unseen), and the directed decision on a fixed subset of dev
questions (the first 2 per family, by id). Gold is read only to report whether the program's diagnostic-path
answer to the question's own change is right; it is never passed to the library. Development evidence only: it
checks that the adapter path runs, it is not a result.

Usage: python -X utf8 scripts/mlsys_otf_smoke.py <out_jsonl> [cohort ...]   (cohorts: r1_claude r1 b0)
"""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "redesign")]
from assurance import mlsys as M  # noqa: E402
from assurance.registry import Registry  # noqa: E402

FOLDERS = {"r1_claude": "build_test_r1_claude", "r1": "build_test_r1", "b0": "build_test_v1"}
DOMAIN_DOC = {M.MFG: "mfg_dev", M.IT: "itops_dev"}


def main(out_path, *cohorts):
    cohorts = cohorts or ("r1_claude",)
    navs = {}

    def nav(doc):
        if doc not in navs:
            navs[doc] = json.loads((ROOT / "runs" / "mlsys_docs" / doc / "navmap.json").read_text())
        return navs[doc]
    splits = json.loads((ROOT / "manifests" / "mlsys_splits_v1.json").read_text(encoding="utf-8"))
    qs = json.loads((ROOT / "manifests" / "mlsys_questions_dev_v1.json").read_text(encoding="utf-8"))
    subset = {}
    for q in sorted(qs, key=lambda q: q["id"]):
        subset.setdefault((q["domain"], q["family"]), [])
        if len(subset[(q["domain"], q["family"])]) < 2:
            subset[(q["domain"], q["family"])].append(q)
    done = set()
    out = Path(out_path)
    if out.exists():
        done = {(r["cohort"], r["program"], r["row"]) for r in map(json.loads, out.read_text(encoding="utf-8").splitlines()) if r}
    with out.open("a", encoding="utf-8") as f:
        for cohort in cohorts:
            builds = json.loads("[]")
            for led in sorted((ROOT / "runs" / FOLDERS[cohort]).glob("builds_*.jsonl")):
                builds += [json.loads(l) for l in led.read_text(encoding="utf-8").splitlines() if l.strip()]
            for b in builds:
                doc = b["build"].split("/")[1]
                if doc not in DOMAIN_DOC.values() or not b.get("accepted"):
                    continue
                dom = M.MFG if doc == "mfg_dev" else M.IT
                prog = ROOT / "runs" / FOLDERS[cohort] / b["build"] / "program.json"
                system = "b0" if cohort == "b0" else "r1"
                for title, v in splits[dom].items():
                    if v["split"] != "dev" or (cohort, b["build"], "replay " + title) in done:
                        continue
                    be = M.OTFDomain(prog, system, ROOT, nav=nav(v["doc"]))
                    t0 = time.time()
                    ok, why = M.ProbeRunner(be, be.nav, be.schema).replay(title)
                    f.write(json.dumps({"cohort": cohort, "program": b["build"], "row": "replay " + title, "seen_at_build": v["seen_at_build"],
                                        "replay": ok, "detail": why, "kind_map": be.kind_map(title), "secs": round(time.time() - t0, 1)}) + "\n")
                    f.flush()
                for (d, fam), rows in subset.items():
                    if d != dom:
                        continue
                    for q in rows:
                        if (cohort, b["build"], q["id"]) in done:
                            continue
                        be = M.OTFDomain(prog, system, ROOT, nav=nav(q["doc"]))
                        runner = M.ProbeRunner(be, be.nav, be.schema)
                        req = M.request_from_binding(q["scope"], q["binding"], q["query"])
                        t0 = time.time()
                        with tempfile.TemporaryDirectory() as t:
                            dec = M.decide("directed", req, be.schema, runner, Registry(Path(t) / "r.jsonl"), be)
                        ex = runner.execute(q["scope"], req.interventions[0])
                        a = M.answer(req.query, runner.canon(ex))[0] if ex is not None and ex.status == "ran" else None
                        f.write(json.dumps({"cohort": cohort, "program": b["build"], "row": q["id"], "family": fam,
                                            "seen_at_build": q["seen_at_build"], "permit": dec.permit, "reason": dec.reason,
                                            "untested": dec.untested, "inexpressible": dec.inexpressible,
                                            "diagnostic_answer_right": None if ex is None else a == q["gold"],
                                            "probes_run": dec.probes_run, "secs": round(time.time() - t0, 1)}) + "\n")
                        f.flush()
    print("done")


if __name__ == "__main__":
    main(*sys.argv[1:])
