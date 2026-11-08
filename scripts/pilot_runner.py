"""Development pilot (handoff Stage 3): every policy configuration, on both backends, over the frozen pilot questions.

Evaluation side. Gold, hidden bindings and effect labels in `pilot_questions_v1.json` never reach the library or
any program: they are read only when a row is scored, in `pilot_summary.py`. The one exception is labeled: the
`oracle` request source hands the library the question's hidden binding as its structured request. It is a
diagnostic that removes interpretation error, never a method result.

Stages, each resumable (a finished row is never recomputed):
1. Shared per question: the interpreter's structured request (Haiku), and two reading answers used as fallback
   and as the vanilla and RAG comparators (Haiku).
2. Per program and question, for each request source (`interpreted`, `oracle`): the decision of every policy
   configuration, and the answers each execution path gives:
   - `structured`: the request applied to the program's inputs by the adapter (both backends);
   - `native` (OTF only, interpreted source only): the program's own LLM patch and restart/replay, with the
     binding check's verdict recorded beside the raw answer.
   Directed evidence accumulates in a registry per program and source, in the fixed question order, so later
   questions can reuse earlier evidence under the D20 reuse rule.

Generic probes get a budget of 3 executions per request, the directed cap, so the generic comparator never has
less probe budget than directed. Executions are counted per configuration.

Usage:
  python -X utf8 scripts/pilot_runner.py shared <project_root> [interpret|vanilla|rag]
  python -X utf8 scripts/pilot_runner.py programs <project_root> [name filter]
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "pilot_v1"
QUESTIONS = ROOT / "manifests" / "pilot_questions_v1.json"
DOCS = {"workflow_loan_dev": "WorkflowLoan", "workflow_pharmacy_dev": "WorkflowPharmacy"}
NAV_OF = {d: ROOT / f"runs/build_test_r1_claude/claude-sonnet-5-5/{d}/b2/navmap.json" for d in DOCS}
CONFIGS = ("native", "replay", "schema", "generic", "directed", "program_wide")
BUDGET = 3


def setup_paths():
    sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
    sys.dont_write_bytecode = True


def done_ids(path: Path, key="key"):
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {json.loads(line)[key] for line in f if line.strip()}


def append(path: Path, row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


# ---------------------------------------------------------------- the document as text, for reading
def doc_text(nav: dict) -> str:
    parts = []
    for n in nav["nodes"]:
        if n["kind"] == "table":
            t = n["table"]
            parts.append(f"## {n['title']}\n" + " | ".join(t["columns"]) + "\n" + "\n".join(" | ".join(map(str, r)) for r in t["rows"]))
        else:
            lines = n.get("lines") if isinstance(n.get("lines"), list) else []
            parts.append(f"## {n['title']}\n" + " ".join(lines))
    return "\n\n".join(parts)


def chunks(nav: dict, rows_per_chunk=40):
    out = []
    for n in nav["nodes"]:
        if n["kind"] == "table":
            t = n["table"]
            head = " | ".join(t["columns"])
            for i in range(0, max(len(t["rows"]), 1), rows_per_chunk):
                body = "\n".join(" | ".join(map(str, r)) for r in t["rows"][i:i + rows_per_chunk])
                out.append(f"## {n['title']} (rows {i + 1}-{i + rows_per_chunk})\n{head}\n{body}")
        else:
            lines = n.get("lines") if isinstance(n.get("lines"), list) else []
            text = " ".join(lines)
            for i in range(0, max(len(text), 1), 3000):
                out.append(f"## {n['title']}\n{text[i:i + 3000]}")
    return out


def bm25(query: str, docs: list[str], k: int = 8) -> list[int]:
    tok = lambda s: re.findall(r"[a-z0-9]+", s.lower())
    dt = [tok(d) for d in docs]
    avg = sum(map(len, dt)) / len(dt)
    df = {}
    for d in dt:
        for w in set(d):
            df[w] = df.get(w, 0) + 1
    n = len(dt)
    scores = []
    for i, d in enumerate(dt):
        tf = {}
        for w in d:
            tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for w in set(tok(query)):
            if w in tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * len(d) / avg))
        scores.append(s)
    return sorted(range(n), key=lambda i: -scores[i])[:k]


READ_PROMPT = """You are given process records and a what-if question about them. Work out the answer from the records and
the stated rules. End your reply with one line: ANSWER: <whole number of seconds>, or ANSWER: unknown.

RECORDS
{records}

QUESTION
{question}"""


def parse_answer(text: str):
    m = re.findall(r"ANSWER:\s*(-?[0-9][0-9,]*(?:\.[0-9]+)?)", text or "")
    if not m:
        return None
    try:
        return round(float(m[-1].replace(",", "")))
    except ValueError:
        return None


# ---------------------------------------------------------------- stage 1
def shared(root: Path, only: str | None = None):
    setup_paths()
    import b0_build_test as bt
    from assurance.interpret import interpret
    from assurance.request import schema_from_map
    qs = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    env = bt.load_env(root / ".env")
    ledger = bt.Ledger(root / "runs" / "build_test_pilot_claude", "claude-haiku-5-5")
    client = bt.Client("claude-haiku-5-5", env, ledger)
    navs = {d: json.loads(p.read_text(encoding="utf-8")) for d, p in NAV_OF.items()}
    schemas = {d: schema_from_map(n) for d, n in navs.items()}
    texts = {d: doc_text(n) for d, n in navs.items()}
    pieces = {d: chunks(n) for d, n in navs.items()}
    for kind in ("interpret", "vanilla", "rag"):
        if only and kind != only:
            continue
        path = OUT / f"{kind}.jsonl"
        have = done_ids(path)
        for q in qs:
            if q["id"] in have:
                continue
            t0 = time.time()
            client.build_id = f"pilot/{kind}/{q['id']}"
            if kind == "interpret":
                req, raw = interpret(q["question"], schemas[q["doc"]], client.llm)
                row = {"request": {**req.__dict__, "query": req.query.__dict__, "interventions": [i.__dict__ for i in req.interventions]},
                       "raw": raw}
            else:
                if kind == "vanilla":
                    records = texts[q["doc"]]
                else:
                    idx = bm25(q["question"], pieces[q["doc"]])
                    records = "\n\n".join(pieces[q["doc"]][i] for i in sorted(idx))
                raw = client.llm([{"role": "user", "content": READ_PROMPT.format(records=records, question=q["question"])}])
                row = {"answer": parse_answer(raw), "raw_tail": (raw or "")[-400:]}
            append(path, {"key": q["id"], **row, "seconds": round(time.time() - t0, 1), "calls": client.calls[-1:] if client.calls else []})
            print(kind, q["id"], row.get("answer", row.get("request", {}).get("unresolved")), flush=True)


# ---------------------------------------------------------------- stage 2
def programs_list(root: Path):
    """OTF programs that built, from the replay screen (R1 cohorts; B0 kept as native-only reference), and DEVS-Gen
    programs that built, from the generation index."""
    screen = json.loads((root / "manifests" / "replay_screen_v2.json").read_text(encoding="utf-8"))
    setup_paths()
    import replay_screen as rs
    out = []
    for p in screen["programs"]:
        path = root / "runs" / rs.SYSTEM_FOLDERS[p["system"]] / p["setup"] / p["doc"] / p["build"] / "program.json"
        out.append({"name": f"otf/{p['system']}/{p['setup']}/{p['doc']}/{p['build']}", "backend": "otf", "system": p["system"],
                    "doc": p["doc"], "path": str(path), "native_only": p["system"] == "b0"})
    idx = root / "runs" / "devs_gen" / "generation_index.jsonl"
    seen = set()
    for line in idx.read_text(encoding="utf-8").splitlines():
        try:
            g = json.loads(line)
        except ValueError:
            continue
        if not g.get("has_run_py") or g.get("task") not in DOCS.values():
            continue
        doc = next(d for d, t in DOCS.items() if t == g["task"])
        name = f"devs/{g['label']}/{doc}/{g['run']}"
        if name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "backend": "devs", "doc": doc, "native_only": False,
                    "dir": f"/home/aashraf/trust2027/gen/{g['label']}/{g['task']}/{g['run']}", "task": g["task"]})
    return out


def request_from(d: dict):
    from assurance.request import Intervention, Query, Request
    q = d["query"]
    ivs = [Intervention(**i) for i in d["interventions"]]
    return Request(d["scope"], ivs, Query(q["kind"], q["case"], q.get("deadline")), unresolved=d.get("unresolved"))


def oracle_request(q: dict):
    """The question's hidden binding as a structured request. Diagnostic only (removes interpretation error)."""
    from assurance.request import Intervention, Query, Request
    b = dict(q["binding"])
    fam = b.pop("family")
    op = b.pop("op", {"activity_duration": "set", "timer_delay": "set", "routing_outcome": "set_draw",
                      "routing_probability": "set"}.get(fam))
    iv = Intervention(fam, op, case=b.get("case"), target=b.get("target"), visit=b.get("visit"),
                      value=None if b.get("value") is None else float(b["value"]), routes=b.get("routes"),
                      effective_from=b.get("effective_from"), effective_to=b.get("effective_to"))
    return Request(q["scope"], [iv], Query("case_end_time", q["query_case"]))


class Deferred:
    """Registry wrapper: new evidence is held until `commit`, so a question interrupted before its row is written
    leaves no evidence behind for its own rerun (review fix)."""

    def __init__(self, registry):
        self.registry, self.pending = registry, []

    def add(self, key, evidence):
        self.pending.append((key, evidence))

    def state(self, key, target):
        return self.registry.state(key, target)

    def history(self, key):
        return self.registry.history(key)

    def commit(self):
        for key, evidence in self.pending:
            self.registry.add(key, evidence)
        self.pending = []


def make_runner(backend, nav, schema):
    """A probe runner whose executions are cached by (scope, change). Logical executions are still counted, so cost
    per configuration is reported as if nothing were shared; `actual` counts real program runs."""
    from assurance.probes import ProbeRunner

    class Cached(ProbeRunner):
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
    return Cached(backend, nav, schema)


def run_programs(root: Path, name_filter: str | None):
    setup_paths()
    import b0_build_test as bt
    from assurance import answer, contract, policy
    from assurance.backends import DEVSBackend, OTFBackend
    from assurance.binding import check_otf
    from assurance.probes import plan_value
    from assurance.registry import Registry
    from assurance.request import schema_from_map
    qs = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    interp = {json.loads(l)["key"]: json.loads(l) for l in (OUT / "interpret.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    env = bt.load_env(root / ".env")
    ledger = bt.Ledger(root / "runs" / "build_test_pilot_claude", "claude-haiku-5-5")
    client = bt.Client("claude-haiku-5-5", env, ledger)
    for prog in programs_list(root):
        if name_filter and name_filter not in prog["name"]:
            continue
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", prog["name"])
        path = OUT / "programs" / f"{safe}.jsonl"
        have = done_ids(path)
        nav = json.loads(NAV_OF[prog["doc"]].read_text(encoding="utf-8"))
        schema = schema_from_map(nav)
        if prog["backend"] == "otf":
            backend = OTFBackend(Path(prog["path"]), prog["system"], root)
        else:
            backend = DEVSBackend(prog["dir"], prog["task"], root)
        try:
            phash = backend.program_hash()
        except Exception as e:
            append(path, {"key": "__program__", "error": f"hash failed: {e}"})
            continue
        runners = {src: make_runner(backend, nav, schema) for src in ("interpreted", "oracle")}
        registries = {src: Deferred(Registry(OUT / "registries" / f"{safe}_{src}.jsonl")) for src in ("interpreted", "oracle")}
        for q in qs:
            if q["doc"] != prog["doc"]:
                continue
            for src in ("interpreted", "oracle"):
                key = f"{q['id']}|{src}"
                if key in have:
                    continue
                if prog["native_only"] and src == "oracle":
                    continue
                t0 = time.time()
                req = request_from(interp[q["id"]]["request"]) if src == "interpreted" else oracle_request(q)
                c = contract.validate(req, schema)
                runner, registry = runners[src], registries[src]
                decisions = {}
                for cfg in (("native",) if prog["native_only"] else CONFIGS):
                    start = runner.executions
                    try:
                        d = policy.decide(cfg, req, schema, runner, registry if cfg == "directed" else None, backend, budget=BUDGET)
                    except Exception as e:
                        d = policy.Decision(False, f"policy error {type(e).__name__}: {e}"[:300])
                    decisions[cfg] = {"permit": d.permit, "reason": d.reason[:300], "probes_run": d.probes_run,
                                      "executions": runner.executions - start, "untested": d.untested,
                                      "inexpressible": d.inexpressible, "evidence": d.evidence}
                row = {"key": key, "question": q["id"], "source": src, "program": prog["name"], "program_hash": phash,
                       "contract": c.status, "contract_detail": c.detail, "decisions": decisions}
                # structured execution of the request through the adapter
                if not prog["native_only"] and c.ok:
                    try:
                        ex = runner.execute(req.scope, req.interventions[0])
                        if ex is None:
                            row["structured"] = {"status": "inexpressible"}
                        elif ex.status != "ran":
                            row["structured"] = {"status": ex.status, "detail": ex.detail[:200]}
                        else:
                            a, why = answer.answer(req.query, ex.case_ends)
                            row["structured"] = {"status": "ran", "answer": a, "detail": why}
                    except Exception as e:
                        row["structured"] = {"status": "error", "detail": f"{type(e).__name__}: {e}"[:200]}
                # native OTF path: the program's own LLM patch and restart/replay
                if prog["backend"] == "otf" and src == "interpreted":
                    client.build_id = f"pilot/native/{prog['name']}/{q['id']}"
                    # Review fix: the scope comes from the shared interpretation, never from the evaluation file.
                    if req.scope not in schema.scopes:
                        row["native"] = {"status": "no_scope", "detail": f"interpreted scope {req.scope!r} is not in the document"}
                    else:
                      try:
                        ex, binding = backend.native_what_if(req.scope, q["question"], client.llm)
                        if ex.status != "ran":
                            row["native"] = {"status": ex.status, "detail": ex.detail[:300]}
                        else:
                            # The query comes from the shared interpretation, never from the evaluation file.
                            qcase_ok = req.query.case in schema.cases.get(req.scope, [])
                            a, why = answer.answer(req.query, ex.case_ends) if qcase_ok else (None, "no valid query case")
                            bound = None
                            if c.ok:
                                iv = req.interventions[0]
                                pv = plan_value(nav, req.scope, iv) if iv.family in ("activity_duration", "timer_delay", "routing_outcome") else None
                                bound = check_otf(iv, binding, plan_value=pv, pool_size=schema.pools.get(iv.target))
                            row["native"] = {"status": "ran", "answer": a, "binding_check": bound,
                                             "patches": binding.get("patches"), "t_star": binding.get("t_star")}
                      except (bt.InfrastructureFailure, bt.CapReached):
                        raise
                      except Exception as e:
                        row["native"] = {"status": "error", "detail": f"{type(e).__name__}: {e}"[:300]}
                row["seconds"] = round(time.time() - t0, 1)
                row["actual_runs_so_far"] = type(runner).actual
                append(path, row)
                registry.commit()          # evidence becomes visible only once its question's row is written
                print(prog["name"], key, {k: v["permit"] for k, v in decisions.items()},
                      row.get("structured", {}).get("answer"), row.get("native", {}).get("answer"), flush=True)


if __name__ == "__main__":
    stage, root = sys.argv[1], Path(sys.argv[2]).resolve()
    if stage == "shared":
        shared(root, sys.argv[3] if len(sys.argv) > 3 else None)
    elif stage == "programs":
        run_programs(root, sys.argv[3] if len(sys.argv) > 3 else None)
    else:
        raise SystemExit(f"unknown stage {stage}")
