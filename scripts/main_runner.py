"""Main runner: every domain, question set and platform, on the frozen library (D22-D25).

Evaluation side. Gold, hidden bindings and effect labels in the question files never reach the library, a program
or a model: they are read only by `scripts/main_summary.py`. The one labelled exception is the `oracle` request
source, which hands the library the question's hidden binding as its structured request (a diagnostic that removes
interpretation error, never a method result). The dev pilot's runner, `scripts/pilot_runner.py`, is kept unchanged as
the pilot's record; this runner reuses its tested pieces.

What the system under test sees:
- the question text only (never the question row's scope, family or binding);
- the document map of the question's document. For the mixed MLSys documents, the map keeps only the chapters of
  the question set's own split (`manifests/mlsys_splits_v1.json`), so a dev run never holds test records and a test
  run never holds dev records (review finding, 2026-11-09). Workflow documents hold one split each.
- Reading comparators (vanilla, RAG) see the front matter plus the chapter the shared interpretation names; when the
  interpretation names no known chapter, the whole (split-filtered) document. This replaces the pilot's whole-
  document view, which would exceed 100k tokens on the larger MLSys documents (5x Haiku price); it is the same view
  the LLM judges get.

Stages, each resumable (a finished row is never recomputed):
1. `shared` per question: the interpreter's reply (domain prompt, Haiku), and two reading answers (vanilla, RAG).
2. `programs` per program and question of the same process, for each request source (`interpreted`, `oracle`): the
   decision of every policy configuration, the structured answer, and on OTF the native answer with its binding
   check. Evidence accumulates per program and source in question-file order. `--registry-from SET` starts each
   registry from that set's final registry (Study C: e.g. the policy set continues from the test set).

Sets: wf_dev (pilot v1 minus its 8 exclusions), wf_test, wf_policy, ml_dev, ml_test. Output: runs/main_v1/<set>/.

Usage:
  python -X utf8 scripts/main_runner.py shared   <root> <set> [interpret|vanilla|rag]
  python -X utf8 scripts/main_runner.py programs <root> <set> [--filter TEXT] [--no-native] [--registry-from SET]
                                                             [--sources interpreted,oracle] [--dry]
`--dry` makes no model call: it uses only the oracle source and skips native answers.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
sys.dont_write_bytecode = True

import pilot_runner as pr                                                      # noqa: E402

OUT = ROOT / "runs" / "main_v1"
SETS = {
    "wf_dev": ("manifests/pilot_questions_v1.json", "manifests/pilot_excluded_v1.json", "dev"),
    "wf_test": ("manifests/workflow_questions_test_v1.json", None, "test"),
    "wf_policy": ("manifests/workflow_questions_policy_v1.json", None, "policy"),
    "ml_dev": ("manifests/mlsys_questions_dev_v1.json", None, "dev"),
    "ml_test": ("manifests/mlsys_questions_test_v1.json", None, "test"),
}
CONFIGS = ("native", "replay", "schema", "generic", "directed", "program_wide")
BUDGET = 3
READ_PROMPT = """You are given process records and a what-if question about them. Work out the answer from the records and
the stated rules. End your reply with one line: ANSWER: <whole number>, or ANSWER: unknown.

RECORDS
{records}

QUESTION
{question}"""


# ---------------------------------------------------------------- questions, documents, processes
def questions(root: Path, qset: str) -> list[dict]:
    path, excl, _ = SETS[qset]
    qs = json.loads((root / path).read_text(encoding="utf-8"))
    if excl:
        drop = set(json.loads((root / excl).read_text(encoding="utf-8")))
        qs = [q for q in qs if q["id"] not in drop]
    return qs


def process_of(doc: str) -> str:
    if doc.startswith("workflow_loan"):
        return "loan"
    if doc.startswith("workflow_pharmacy"):
        return "pharmacy"
    if doc.startswith("mfg"):
        return "manufacturing"
    if doc.startswith("itops"):
        return "it_ops"
    raise ValueError(doc)


def raw_nav(root: Path, doc: str) -> dict:
    if doc in pr.NAV_OF:
        p = pr.NAV_OF[doc]
    elif doc.startswith("workflow_"):
        p = root / "runs" / "workflow_docs" / doc / "navmap.json"
    else:
        p = root / "runs" / "mlsys_docs" / doc / "navmap.json"
    return json.loads(p.read_text(encoding="utf-8"))


def split_nav(root: Path, doc: str, split: str) -> dict:
    """The document map with only the chapters of this split (MLSys documents mix splits); workflow maps as they are.
    The policy set counts as test for this purpose."""
    nav = raw_nav(root, doc)
    proc = process_of(doc)
    if proc in ("loan", "pharmacy"):
        return nav
    splits = json.loads((root / "manifests" / "mlsys_splits_v1.json").read_text(encoding="utf-8"))[
        "manufacturing" if proc == "manufacturing" else "it_ops"]
    want = "test" if split == "policy" else split
    keep = {t for t, v in splits.items() if v["split"] == want}
    out = copy.deepcopy(nav)
    chapters = [n["title"] for n in nav["nodes"] if n["level"] == 0 and n["kind"] != "list"]
    drop = [c for c in chapters if c not in keep]
    out["nodes"] = [n for n in nav["nodes"] if not any(n["title"] == c or n["title"].startswith(c + ": ") for c in drop)]
    return out


def view(nav: dict, scope: str | None) -> dict:
    """Front matter plus one chapter, or the whole map when the chapter is not known."""
    titles = {n["title"] for n in nav["nodes"] if n["level"] == 0 and n["kind"] != "list"}
    if scope not in titles:
        return nav
    out = copy.deepcopy(nav)
    out["nodes"] = [n for n in nav["nodes"] if (n["level"] == 0 and n["kind"] == "list") or n["title"] == scope
                    or n["title"].startswith(scope + ": ")]
    return out


def is_mlsys(proc: str) -> bool:
    return proc in ("manufacturing", "it_ops")


# ---------------------------------------------------------------- programs
def programs_list(root: Path) -> list[dict]:
    """Every program the main run uses: OTF R1 (and B0, native-only) on the four processes, DEVS-Gen, and the plain
    coding agent once its index exists. Each entry names its process; it answers only that process's questions."""
    out = []
    for p in pr.programs_list(root):                          # the pilot's DEVS-Gen workflow programs
        if p["backend"] == "devs":
            out.append({**p, "process": process_of(p["doc"])})
    # OTF: every accepted build on the four dev documents (equal to the pilot's replay-screen list for the workflow
    # builds that existed then; review fix: B0 on Claude must be picked up too). B0 is native-only.
    folders = {"build_test_v1": "b0", "build_test_r1": "r1", "build_test_r1_claude": "r1_claude", "build_test_b0_claude": "b0_claude"}
    for folder, system in folders.items():
        for f in sorted((root / "runs" / folder).glob("builds_*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                b = json.loads(line)
                setup, doc, build = b["build"].split("/")
                if doc not in ("workflow_loan_dev", "workflow_pharmacy_dev", "mfg_dev", "itops_dev") or not b.get("accepted"):
                    continue
                path = root / "runs" / folder / setup / doc / build / "program.json"
                if path.exists():
                    out.append({"name": f"otf/{system}/{setup}/{doc}/{build}", "backend": "otf", "system": system,
                                "doc": doc, "path": str(path), "native_only": system.startswith("b0"),
                                "process": process_of(doc)})
    # DEVS-Gen programs on manufacturing and IT (tasks Manufacturing, ITOperations), once built
    idx = root / "runs" / "devs_gen" / "generation_index.jsonl"
    seen = {p["name"] for p in out}
    task_proc = {"Manufacturing": "manufacturing", "ITOperations": "it_ops"}
    for line in idx.read_text(encoding="utf-8").splitlines() if idx.exists() else []:
        try:
            g = json.loads(line)
        except ValueError:
            continue
        if not g.get("has_run_py") or g.get("task") not in task_proc:
            continue
        name = f"devs/{g['label']}/{g['task']}/{g['run']}"
        if name not in seen:
            seen.add(name)
            out.append({"name": name, "backend": "devs", "process": task_proc[g["task"]], "native_only": False,
                        "dir": f"/home/aashraf/trust2027/gen/{g['label']}/{g['task']}/{g['run']}", "task": g["task"]})
    # plain coding agent: runs/coding_agent/index.jsonl, one line per built program
    # {"model": "...", "name": "...", "process": "loan|pharmacy|manufacturing|it_ops", "dir": "<WSL dir>", "task": "..."}
    # The cohort is agent/<model> (review fix), so `model` is required.
    ca = root / "runs" / "coding_agent" / "index.jsonl"
    for line in ca.read_text(encoding="utf-8").splitlines() if ca.exists() else []:
        if line.strip():
            c = json.loads(line)
            out.append({"name": f"agent/{c['model']}/{c['name']}", "backend": "devs", "process": c["process"], "native_only": False,
                        "dir": c["dir"], "task": c.get("task")})
    return out


# ---------------------------------------------------------------- domain adapters (thin; the library does the work)
class WF:
    """Workflow path: `assurance.policy`, unchanged from the pilot."""

    def __init__(self):
        from assurance import answer, contract, interpret, policy
        from assurance.binding import check_otf
        from assurance.probes import plan_value
        from assurance.request import schema_from_map
        self.answer, self.contract, self.interpret_mod, self.policy = answer, contract, interpret, policy
        self.check_otf, self.plan_value, self.schema_from_map = check_otf, plan_value, schema_from_map

    def schema(self, nav):
        return self.schema_from_map(nav)

    def interpret(self, question, schema, llm):
        return self.interpret_mod.interpret(question, schema, llm)[1]

    def parse(self, raw, schema):
        return self.interpret_mod.parse(raw)

    def oracle(self, q):
        return pr.oracle_request(q)

    def validate(self, req, schema):
        return self.contract.validate(req, schema)

    def backend(self, prog, root, nav, schema):
        from assurance.backends import DEVSBackend, OTFBackend
        if prog["backend"] == "otf":
            b = OTFBackend(Path(prog["path"]), prog["system"].replace("_claude", ""), root)
            b.nav = nav                                     # reuse on this document's records
            return b
        return DEVSBackend(prog["dir"], prog["task"], root)

    def runner(self, backend, nav, schema):
        return pr.make_runner(backend, nav, schema)

    def decide(self, cfg, req, schema, runner, registry, backend):
        return self.policy.decide(cfg, req, schema, runner, registry, backend, budget=BUDGET)

    def structured(self, runner, req):
        ex = runner.execute(req.scope, req.interventions[0])
        if ex is None:
            return {"status": "inexpressible"}
        if ex.status != "ran":
            return {"status": ex.status, "detail": ex.detail[:200]}
        a, why = self.answer.answer(req.query, ex.case_ends)
        return {"status": "ran", "answer": a, "detail": why}

    def native(self, backend, req, schema, nav, c, question, llm):
        if req.scope not in schema.scopes:
            return {"status": "no_scope", "detail": f"interpreted scope {req.scope!r} is not in the document"}
        ex, binding = backend.native_what_if(req.scope, question, llm)
        if ex.status != "ran":
            return {"status": ex.status, "detail": ex.detail[:300]}
        ok_case = req.query.case in schema.cases.get(req.scope, [])
        a, why = self.answer.answer(req.query, ex.case_ends) if ok_case else (None, "no valid query case")
        bound = None
        if c.ok:
            iv = req.interventions[0]
            pv = self.plan_value(nav, req.scope, iv) if iv.family in ("activity_duration", "timer_delay", "routing_outcome") else None
            bound = self.check_otf(iv, binding, plan_value=pv, pool_size=schema.pools.get(iv.target))
        return {"status": "ran", "answer": a, "binding_check": bound, "patches": binding.get("patches"),
                "t_star": binding.get("t_star")}

    @staticmethod
    def scope_ok(req, schema):
        return req.scope in schema.scopes


class ML:
    """Manufacturing and IT path: `assurance.mlsys` (entry points in `manifests/domain_readiness.md`)."""

    def __init__(self):
        from assurance import mlsys
        self.M = mlsys

    def schema(self, nav):
        return self.M.schema_from_map(nav)

    def interpret(self, question, schema, llm):
        return self.M.interpret(question, schema, llm)[1]

    def parse(self, raw, schema):
        return self.M.parse(raw, schema.domain)

    def oracle(self, q):
        return self.M.request_from_binding(q["scope"], q["binding"], q["query"])

    def validate(self, req, schema):
        return self.M.validate(req, schema)

    def backend(self, prog, root, nav, schema):
        if prog["backend"] == "otf":
            return self.M.OTFDomain(Path(prog["path"]), prog["system"].replace("_claude", ""), root, nav=nav)
        return self.M.DEVSDomain(prog["dir"], schema)

    def runner(self, backend, nav, schema):
        return cached(self.M.ProbeRunner)(backend, nav, schema)

    def decide(self, cfg, req, schema, runner, registry, backend):
        return self.M.decide(cfg, req, schema, runner, registry, backend, budget=BUDGET, seed=0)

    def structured(self, runner, req):
        ex = runner.execute(req.scope, req.interventions[0])
        if ex is None:
            return {"status": "inexpressible"}
        if ex.status != "ran":
            return {"status": ex.status, "detail": ex.detail[:200]}
        a, why = self.M.answer(req.query, ex.case_ends["canon"])
        return {"status": "ran", "answer": a, "detail": why}

    def native(self, backend, req, schema, nav, c, question, llm):
        if req.scope not in schema.chapters:
            return {"status": "no_scope", "detail": f"interpreted scope {req.scope!r} is not in the document"}
        ex, binding = backend.native_what_if(req.scope, question, llm)
        if ex.status != "ran":
            return {"status": ex.status, "detail": ex.detail[:300]}
        a, why = self.M.answer(req.query, ex.case_ends["canon"])
        bound = self.M.check_otf(req.interventions[0], binding, schema, req.scope) if c.ok else None
        return {"status": "ran", "answer": a, "binding_check": bound, "patches": binding.get("patches"),
                "t_star": binding.get("t_star")}

    @staticmethod
    def scope_ok(req, schema):
        return req.scope in schema.chapters


def cached(cls):
    """A probe runner whose executions are cached by (scope, change); logical executions are still counted per
    configuration, as in the pilot."""
    class Cached(cls):
        actual = 0

        def __init__(self, *a):
            super().__init__(*a)
            self._cache = {}

        def execute(self, scope, iv):
            key = (scope, repr(iv))
            if key not in self._cache:
                before = self.executions
                self._cache[key] = (super().execute(scope, iv), self.executions - before)
                if self._cache[key][0] is not None:
                    Cached.actual += 1
                return self._cache[key][0]
            ex, counted = self._cache[key]
            self.executions += counted
            return ex
    return Cached


def declined_row(key, q, src, prog, doc, status, detail, native, phash=None) -> dict:
    """A question the program could not be asked: every configuration declines (`native` permits, with no answer),
    and on OTF the native path has no answer, so rule A counts it as not answered (review fix)."""
    row = {"key": key, "question": q["id"], "source": src, "program": prog["name"], "program_hash": phash, "doc": doc,
           "process": prog["process"], "contract": status, "contract_detail": str(detail)[:300], "decisions": {
               cfg: {"permit": cfg == "native", "reason": f"{status}: {str(detail)[:200]}", "probes_run": 0,
                     "executions": 0, "untested": False, "inexpressible": False, "evidence": []}
               for cfg in (("native",) if prog["native_only"] else CONFIGS)}}
    if prog["backend"] == "otf" and src == "interpreted":
        if native:
            row["native"] = {"status": status, "detail": str(detail)[:300]}
        else:
            row["native_skipped"] = True
    return row


def adapter(proc: str):
    return ML() if is_mlsys(proc) else WF()


def req_json(req) -> dict:
    def plain(x):
        if hasattr(x, "__dict__"):
            return {k: plain(v) for k, v in x.__dict__.items()}
        if isinstance(x, list):
            return [plain(v) for v in x]
        return x
    return plain(req)


# ---------------------------------------------------------------- stage 1
def client(root: Path):
    import b0_build_test as bt
    env = bt.load_env(root / ".env")
    ledger = bt.Ledger(root / "runs" / "build_test_main_claude", "claude-haiku-5-5")
    return bt, bt.Client("claude-haiku-5-5", env, ledger, max_output=bt.MAX_OUTPUT_PER_QUESTION)  # 64k per-question cap


def shared(root: Path, qset: str, only: str | None = None):
    bt, cl = client(root)
    out = OUT / qset
    split = SETS[qset][2]
    navs, schemas, interp_rows = {}, {}, {}
    ip = out / "interpret.jsonl"
    for kind in ("interpret", "vanilla", "rag"):
        if only and kind != only:
            continue
        path = out / f"{kind}.jsonl"
        have = pr.done_ids(path)
        if kind != "interpret":
            interp_rows = {json.loads(l)["key"]: json.loads(l) for l in ip.read_text(encoding="utf-8").splitlines()
                           if l.strip()} if ip.exists() else {}
        for q in questions(root, qset):
            if q["id"] in have:
                continue
            doc, proc = q["doc"], process_of(q["doc"])
            if doc not in navs:
                navs[doc] = split_nav(root, doc, split)
                schemas[doc] = adapter(proc).schema(navs[doc])
            t0 = time.time()
            cl.build_id = f"main/{qset}/{kind}/{q['id']}"
            if kind == "interpret":
                raw = adapter(proc).interpret(q["question"], schemas[doc], cl.llm)
                row = {"raw": raw}
            else:
                scope = None
                if q["id"] in interp_rows:
                    try:
                        scope = adapter(proc).parse(interp_rows[q["id"]]["raw"], schemas[doc]).scope
                    except Exception:
                        scope = None
                v = view(navs[doc], scope)
                if kind == "vanilla":
                    records = pr.doc_text(v)
                else:
                    pieces = pr.chunks(v)
                    idx = pr.bm25(q["question"], pieces)
                    records = "\n\n".join(pieces[i] for i in sorted(idx))
                raw = cl.llm([{"role": "user", "content": READ_PROMPT.format(records=records, question=q["question"])}])
                row = {"answer": pr.parse_answer(raw), "raw_tail": (raw or "")[-400:], "view_scope": scope}
            pr.append(path, {"key": q["id"], **row, "seconds": round(time.time() - t0, 1), "calls": cl.calls[-1:] if cl.calls else []})
            print(qset, kind, q["id"], flush=True)


# ---------------------------------------------------------------- stage 2
def run_programs(root: Path, qset: str, name_filter=None, native=True, registry_from=None, sources=("interpreted", "oracle"), dry=False):
    from assurance.registry import Registry
    out = OUT / qset
    split = SETS[qset][2]
    qs = questions(root, qset)
    if dry:
        sources, native = tuple(s for s in sources if s == "oracle") or ("oracle",), False
    interp = {}
    ip = out / "interpret.jsonl"
    if "interpreted" in sources:
        interp = {json.loads(l)["key"]: json.loads(l) for l in ip.read_text(encoding="utf-8").splitlines() if l.strip()}
    bt = cl = None
    if native:
        bt, cl = client(root)
    docs = sorted({q["doc"] for q in qs})
    navs = {d: split_nav(root, d, split) for d in docs}
    for prog in programs_list(root):
        if name_filter and name_filter not in prog["name"]:
            continue
        mine = [q for q in qs if process_of(q["doc"]) == prog["process"]]
        if not mine:
            continue
        ad = adapter(prog["process"])
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", prog["name"])
        path = out / "programs" / f"{safe}.jsonl"
        have = pr.done_ids(path)
        regs = {}
        for src in sources:
            rp = out / "registries" / f"{safe}_{src}.jsonl"
            side = rp.with_suffix(".source.json")
            want = {"registry_from": registry_from}
            if rp.exists():
                got = json.loads(side.read_text(encoding="utf-8")) if side.exists() else {"registry_from": None}
                if got != want:      # review fix: never resume a registry started from a different source
                    raise SystemExit(f"{rp} was started with {got}, not {want}")
            else:
                rp.parent.mkdir(parents=True, exist_ok=True)
                if registry_from:
                    prev = OUT / registry_from / "registries" / f"{safe}_{src}.jsonl"
                    if prev.exists():
                        shutil.copyfile(prev, rp)
                side.write_text(json.dumps(want), encoding="utf-8")
            regs[src] = pr.Deferred(Registry(rp))
        per_doc = {}
        for q in mine:
            doc = q["doc"]
            if doc not in per_doc:
                nav = navs[doc]
                schema = ad.schema(nav)
                try:
                    backend = ad.backend(prog, root, nav, schema)
                    phash = backend.program_hash()
                except Exception as e:
                    per_doc[doc] = f"backend failed: {type(e).__name__}: {e}"[:300]
                    if f"__program__|{doc}" not in have:
                        pr.append(path, {"key": f"__program__|{doc}", "program": prog["name"], "error": per_doc[doc]})
                    continue
                per_doc[doc] = (nav, schema, backend, phash, {s: ad.runner(backend, nav, schema) for s in sources})
            if isinstance(per_doc[doc], str):
                # review fix: the program still owes every question; record each as declined with no answer
                for src in sources:
                    key = f"{q['id']}|{src}"
                    if key not in have and not (prog["native_only"] and src == "oracle"):
                        pr.append(path, declined_row(key, q, src, prog, doc, "backend_failed", per_doc[doc], native))
                continue
            nav, schema, backend, phash, runners = per_doc[doc]
            for src in sources:
                key = f"{q['id']}|{src}"
                if key in have or (prog["native_only"] and src == "oracle"):
                    continue
                t0 = time.time()
                if src == "interpreted":
                    if q["id"] not in interp:
                        pr.append(path, declined_row(key, q, src, prog, doc, "no_interpretation", "no shared interpretation row", native))
                        continue
                    try:
                        req = ad.parse(interp[q["id"]]["raw"], schema)
                    except Exception as e:
                        req = None
                        parse_err = f"{type(e).__name__}: {e}"[:200]
                else:
                    req = ad.oracle(q)
                runner, registry = runners[src], regs[src]
                row = {"key": key, "question": q["id"], "source": src, "program": prog["name"], "program_hash": phash,
                       "doc": doc, "process": prog["process"]}
                if req is None:
                    pr.append(path, declined_row(key, q, src, prog, doc, "unparsable", parse_err, native, phash))
                    continue
                c = ad.validate(req, schema)
                decisions = {}
                for cfg in (("native",) if prog["native_only"] else CONFIGS):
                    start = runner.executions
                    try:
                        d = ad.decide(cfg, req, schema, runner, registry if cfg == "directed" else None, backend)
                    except Exception as e:
                        from assurance.policy import Decision
                        d = Decision(False, f"policy error {type(e).__name__}: {e}"[:300])
                    decisions[cfg] = {"permit": d.permit, "reason": d.reason[:300], "probes_run": d.probes_run,
                                      "executions": runner.executions - start, "untested": d.untested,
                                      "inexpressible": d.inexpressible, "evidence": d.evidence}
                row.update({"contract": c.status, "contract_detail": c.detail, "request": req_json(req), "decisions": decisions})
                if not prog["native_only"] and c.ok:
                    try:
                        row["structured"] = ad.structured(runner, req)
                    except Exception as e:
                        row["structured"] = {"status": "error", "detail": f"{type(e).__name__}: {e}"[:200]}
                if native and prog["backend"] == "otf" and src == "interpreted":
                    cl.build_id = f"main/{qset}/native/{prog['name']}/{q['id']}"
                    try:
                        row["native"] = ad.native(backend, req, schema, nav, c, q["question"], cl.llm)
                    except (bt.InfrastructureFailure, bt.CapReached):
                        raise
                    except Exception as e:
                        row["native"] = {"status": "error", "detail": f"{type(e).__name__}: {e}"[:300]}
                if prog["backend"] == "otf" and src == "interpreted" and not native:
                    row["native_skipped"] = True
                row["seconds"] = round(time.time() - t0, 1)
                row["actual_runs_so_far"] = type(runner).actual
                pr.append(path, row)
                registry.commit()
                print(prog["name"], key, {k: v["permit"] for k, v in decisions.items()},
                      row.get("structured", {}).get("answer"), row.get("native", {}).get("answer"), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("shared", "programs"))
    ap.add_argument("root")
    ap.add_argument("set", choices=sorted(SETS))
    ap.add_argument("kind", nargs="?")
    ap.add_argument("--filter")
    ap.add_argument("--no-native", action="store_true")
    ap.add_argument("--registry-from")
    ap.add_argument("--sources", default="interpreted,oracle")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    if a.stage == "shared":
        shared(root, a.set, a.kind)
    else:
        run_programs(root, a.set, a.filter, native=not a.no_native, registry_from=a.registry_from,
                     sources=tuple(a.sources.split(",")), dry=a.dry)
