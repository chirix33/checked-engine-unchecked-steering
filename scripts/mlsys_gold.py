"""Gold for the manufacturing and IT operations domains (evaluation-only; never shown to a system under test).

Two separately written references from the pinned OTF-Tools clone, fed by two separate input routes:
- `sim.py` (the MLSys reference simulator) on chapters and windows rebuilt from the raw source records
  (SupplyGraph, Google cluster trace 2011), read-only from the MLSys working copy, because the pinned clone has no
  `data/` folder;
- `validate.py` (MLSys's independent re-implementation, written from the front-matter prose), fed only with numbers
  parsed back out of the document PDF.
A gold value is used only when both agree exactly. Agreement of the raw-data route with the PDF route also shows
that every input the reference reads is printed in the document (deterministic-realization rule).

Change dicts are the pinned simulators' own intervention format (sim.py INPUT_KINDS).
Nothing here writes into the pinned clone (bytecode writing is off).
"""
from __future__ import annotations

import hashlib
import json
import sys
from functools import lru_cache
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
IMPL = ROOT / "baseline" / "otf-tools-10f5401" / "implementation-1"
RUNS = IMPL / "runs"
# The pinned clone was checked out with core.autocrlf=true, which rewrote line endings inside its binary PDFs
# (pdfium still reads them, pdfplumber does not). The documents used here are the committed blobs of the pinned
# commit, written byte-exact to runs/mlsys_docs/<doc>/document.pdf by `materialize_docs` (git show). Their sha256
# equal the MLSys working copy's PDFs and the copies the dev builds read (runs/build_test_v1/docs/).
DOCS_DIR = ROOT / "runs" / "mlsys_docs"
RAW = Path(r"C:\Users\aashraf\Desktop\Work\2026\MLSystem 2027\implementation-1\data\domains\raw")
SUPPLYGRAPH = RAW / "supplygraph" / "Raw Dataset" / "Homogenoeus"
TRACE = RAW / "google-trace-2011"
if str(IMPL) not in sys.path:
    sys.path.insert(0, str(IMPL))

DOCS = {"manufacturing": ["mfg_dev"] + [f"mfg_d{k:02d}" for k in range(1, 6)],
        "it_ops": ["itops_dev"] + [f"itops_d{k:02d}" for k in range(1, 6)]}
BUILD_DOC = {"manufacturing": "mfg_dev", "it_ops": "itops_dev"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def materialize_docs() -> dict:
    """Write each document's committed blob from the pinned commit; returns {doc: sha256}."""
    import subprocess
    out = {}
    for dom in DOCS.values():
        for doc in dom:
            path = DOCS_DIR / doc / "document.pdf"
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                blob = subprocess.run(["git", "-C", str(IMPL.parent), "show", f"HEAD:implementation-1/runs/{doc}/document.pdf"],
                                      capture_output=True, check=True).stdout
                path.write_bytes(blob)
            out[doc] = sha256(path)
    return out


def pdf(doc: str) -> Path:
    path = DOCS_DIR / doc / "document.pdf"
    if not path.exists():
        materialize_docs()
    return path


def doc_titles(doc: str) -> list[str]:
    return [s["title"] for s in json.loads((RUNS / doc / "manifest.json").read_text())["scopes"]]


@lru_cache(maxsize=None)
def doc_of(domain: str) -> dict:
    return {t: d for d in DOCS[domain] for t in doc_titles(d)}


@lru_cache(maxsize=None)
def parsed(doc: str) -> dict:
    """validate.py's parse of the PDF: the PDF-only input route."""
    if doc.startswith("mfg"):
        from domains.manufacturing import validate
    else:
        from domains.it_ops import validate
    return validate.parse_pdf(pdf(doc))


@lru_cache(maxsize=None)
def raw_scopes(domain: str) -> dict:
    """title -> sim.Scope or sim.Window, rebuilt from raw records with the pinned build code."""
    if domain == "manufacturing":
        from domains.manufacturing import data, scopes
        rec = data.load(SUPPLYGRAPH)
        return {s.title: s for s in scopes.all_scopes(rec)}
    from domains.it_ops import data, scopes
    data.RAW = TRACE                      # module global read at call time; the pinned file is not changed
    return {w.title: w for w in scopes.all_windows()}


def scope(domain: str, title: str):
    return raw_scopes(domain)[title]


def ps(domain: str, title: str) -> dict:
    return parsed(doc_of(domain)[title])[title]


# ---------------------------------------------------------------- manufacturing
def mfg_rows_sim(title: str, changes: list[dict]) -> dict:
    from domains.manufacturing import sim
    s = scope("manufacturing", title)
    res = sim.simulate(s, changes, through=s.last_day)
    cols = ("produced", "ordered", "shipped", "backordered", "stock")
    return {(d, p): {c: r[c] for c in cols} for (d, p), r in res.rows.items() if d <= s.last_day}


def mfg_rows_ref(title: str, changes: list[dict]) -> dict:
    from domains.manufacturing import validate
    p = ps("manufacturing", title)
    last = max(d for d, _ in p["ledger"])
    return validate.ref_run(p, changes, last)["rows"]


def mfg_value(rows: dict, query: dict):
    col = {"stock_end_of_day": "stock", "backordered_end_of_day": "backordered"}[query["kind"]]
    r = rows.get((query["day"], query["product"]))
    return None if r is None else int(r[col])


# ---------------------------------------------------------------- IT operations
def it_starts_sim(title: str, changes: list[dict]) -> dict:
    from domains.it_ops import sim
    res = sim.simulate(scope("it_ops", title), changes)
    return {t: r.first_start for t, r in res.runs.items()}


def it_starts_ref(title: str, changes: list[dict]) -> dict:
    from domains.it_ops import validate
    v = validate.window_run(ps("it_ops", title), changes)
    return {t: r.first_start for t, r in v.runs.items()}


def it_value(starts: dict, query: dict):
    if query["task"] not in starts:
        return None
    s = starts[query["task"]]
    if query["kind"] == "task_start_time":
        return s
    if query["kind"] == "task_starts_by":
        return None if s is None else bool(s <= query["deadline"])
    raise ValueError(query["kind"])


def gold(domain: str, title: str, changes: list[dict], query: dict) -> tuple:
    """(sim value, re-implementation value). None means the query has no defined answer (task removed or never
    starts, or no such ledger row)."""
    if domain == "manufacturing":
        return mfg_value(mfg_rows_sim(title, changes), query), mfg_value(mfg_rows_ref(title, changes), query)
    a, b = it_value(it_starts_sim(title, changes), query), it_value(it_starts_ref(title, changes), query)
    return a, b


# ---------------------------------------------------------------- factual agreement with the printed records
def factual_check(domain: str) -> dict:
    """Per chapter or window: does sim.py on the raw rebuild reproduce every printed outcome row, and does the
    PDF-only re-implementation? Returns {title: [problems]} (empty lists when all agree)."""
    out = {}
    if domain == "manufacturing":
        for title in doc_of(domain):
            p, probs = ps(domain, title), []
            s = scope(domain, title)
            sim_rows, ref_rows = mfg_rows_sim(title, []), mfg_rows_ref(title, [])
            for (d, prod), printed in p["ledger"].items():
                if sim_rows.get((d, prod)) != printed:
                    probs.append(f"sim day {d} {prod}")
                if ref_rows.get((d, prod)) != printed:
                    probs.append(f"ref day {d} {prod}")
            if len(p["ledger"]) != len(s.days) * len(s.products):
                probs.append("ledger size")
            for (d, prod), (pp, oo) in p["book"].items():
                if (s.production[d][prod], s.orders[d][prod]) != (pp, oo):
                    probs.append(f"book day {d} {prod}")
            if p["capacity"] != s.capacity_kg or {k: v for k, v in p["products"].items()} != \
                    {k: (s.grams_per_unit[k], s.opening_stock[k]) for k in s.products}:
                probs.append("constants")
            out[title] = probs
        return out
    from domains.it_ops import sim
    for title in doc_of(domain):
        p, probs = ps(domain, title), []
        w = scope(domain, title)
        res = sim.simulate(w)
        printed = [(r[0], r[1], r[7], None if r[8] == "-" else r[8]) for r in p["log"]]
        mine = [(t, tid, ev, m) for t, tid, ev, m in res.log if t <= w.length]
        if printed != mine:
            probs.append(f"sim log differs ({len(printed)} printed, {len(mine)} simulated)")
        tasks = {t.tid: {"job": t.job, "pri": t.priority, "cpu": t.cpu, "mem": t.mem, "submit": t.submit,
                         "run": t.duration} for t in w.tasks}
        if tasks != p["tasks"]:
            probs.append("task inputs differ")
        machines = [{"id": m.mid, "cpu": m.cpu, "mem": m.mem, "down": m.down, "back": m.back} for m in w.machines]
        if machines != p["machines"]:
            probs.append("machine inputs differ")
        if it_starts_sim(title, []) != it_starts_ref(title, []):
            probs.append("first starts: sim and re-implementation differ")
        out[title] = probs
    return out


def raw_file_hashes() -> dict:
    """sha256 of every raw file under the two source folders (read-only)."""
    out = {}
    for base in (RAW / "supplygraph", TRACE):
        for f in sorted(p for p in base.rglob("*") if p.is_file()):
            out[str(f.relative_to(RAW)).replace("\\", "/")] = sha256(f)
    return out


if __name__ == "__main__":
    for dom in ("manufacturing", "it_ops"):
        res = factual_check(dom)
        bad = {k: v for k, v in res.items() if v}
        print(dom, len(res), "scopes;", len(bad), "with problems", json.dumps(bad)[:600])
