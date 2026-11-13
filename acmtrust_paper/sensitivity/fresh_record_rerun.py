"""Retest every question: rerun Vouch's directed decision with an EMPTY capability record for each question.

The frozen main run carried one record per program through the questions in file order: a failure blocked later
questions on the same kind of change and target (Already caught), and a pass could be reused on the same run.
This script asks what the decisions would have been without that record, by giving each question a fresh, empty
record. Nothing else changes: same programs, documents, shared question interpretations, adapter and policy code,
budget and seed. The answer of each row is fixed by the frozen run and is not recomputed (the record never affects
the answer, only whether it is released). No model is called; only programs are executed, in the same sandbox.

It imports the frozen scripts/main_runner.py and the assurance package unchanged; no project file is modified.

Modes:
  rerun  <root> <rows.json> <out_dir> <shard> <nshards>     rerun the rows that depended on the record
  check  <root> <out_dir> <shard> <nshards> <n> <seed>      rerun n random rows that did NOT depend on the record
                                                            (their decisions must equal the frozen ones)
Run from the project root with .tools/b0_env/Scripts/python.exe -X utf8.
"""
import json
import random
import sys
import time
from pathlib import Path

mode = sys.argv[1]
root = Path(sys.argv[2]).resolve()
sys.dont_write_bytecode = True
sys.path[:0] = [str(root), str(root / "scripts")]
import main_runner as mr  # noqa: E402
import pilot_runner as pr  # noqa: E402
from assurance.registry import Registry  # noqa: E402

EMPTY = Path(__file__).resolve().parent / "fresh_record" / "_never_written_registry.jsonl"
assert not EMPTY.exists()


def frozen_rows(qset):
    """Frozen interpreted-source rows by (program, question)."""
    out = {}
    for p in (mr.OUT / qset / "programs").glob("*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("source") == "interpreted" and "decisions" in r:
                out[(r["program"], r["question"])] = r
    return out


def select(mode):
    if mode == "rerun":
        rows = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
        out_dir, shard, n = Path(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
        targets = [(r["set"], r["program"], r["question"]) for r in rows]
    else:
        out_dir, shard, n, k, seed = Path(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7])
        dep = json.loads((Path(__file__).resolve().parent / "fresh_record_rows.json").read_text(encoding="utf-8"))
        dep = {(r["set"], r["program"], r["question"]) for r in dep}
        pool = []
        for qset in ("wf_test", "ml_test"):
            for (prog, qid), r in frozen_rows(qset).items():
                if (qset, prog, qid) not in dep and not prog.startswith("otf/b0"):
                    pool.append((qset, prog, qid))
        pool.sort()
        targets = random.Random(seed).sample(pool, k)
    progs = sorted({t[1] for t in targets})
    mine = set(progs[shard::n])
    return out_dir, [t for t in targets if t[1] in mine]


out_dir, targets = select(mode)
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / f"{mode}_shard{sys.argv[-2] if mode == 'rerun' else sys.argv[4]}.jsonl"
done = set()
if out_path.exists():
    for line in out_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            done.add((r["set"], r["program"], r["question"]))

programs = {p["name"]: p for p in mr.programs_list(root)}
by_set = {}
for t in targets:
    by_set.setdefault(t[0], []).append(t)

for qset, ts in sorted(by_set.items()):
    split = mr.SETS[qset][2]
    qs = {q["id"]: q for q in mr.questions(root, qset)}
    interp = {}
    for line in (mr.OUT / qset / "interpret.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            interp[r["key"]] = r
    frozen = frozen_rows(qset)
    cache = {}
    for (_, prog_name, qid) in sorted(ts, key=lambda t: (t[1], t[2])):
        if (qset, prog_name, qid) in done:
            continue
        q, prog = qs[qid], programs[prog_name]
        ad = mr.adapter(prog["process"])
        ck = (prog_name, q["doc"])
        if ck not in cache:
            nav = mr.split_nav(root, q["doc"], split)
            schema = ad.schema(nav)
            backend = ad.backend(prog, root, nav, schema)
            cache = {ck: (nav, schema, backend, ad.runner(backend, nav, schema))}   # one program and document at a time
        nav, schema, backend, runner = cache[ck]
        req = ad.parse(interp[qid]["raw"], schema)
        empty = pr.Deferred(Registry(EMPTY))        # never committed: every question starts with no record
        t0, start = time.time(), runner.executions
        try:
            d = ad.decide("directed", req, schema, runner, empty, backend)
            dec = {"permit": d.permit, "reason": d.reason[:300], "untested": d.untested,
                   "inexpressible": d.inexpressible, "evidence": d.evidence}
        except Exception as e:
            dec = {"permit": False, "reason": f"policy error {type(e).__name__}: {e}"[:300], "untested": False,
                   "inexpressible": False, "evidence": []}
        fr = frozen[(prog_name, qid)]["decisions"]["directed"]
        rec = {"set": qset, "program": prog_name, "question": qid, "fresh": dec,
               "fresh_executions": runner.executions - start, "seconds": round(time.time() - t0, 1),
               "frozen_permit": fr["permit"], "frozen_reason": fr["reason"], "frozen_executions": fr.get("executions")}
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        assert not EMPTY.exists(), "the empty record was written to"
        print(prog_name, qid, "frozen", fr["permit"], "fresh", dec["permit"], dec["reason"][:80], flush=True)
print("done", len(targets))
