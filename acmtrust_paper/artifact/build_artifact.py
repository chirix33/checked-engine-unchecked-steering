#!/usr/bin/env python3
"""Build the anonymized artifact export for the TRUST 2027 submission.

Run from anywhere:   python -X utf8 acmtrust_paper/artifact/build_artifact.py [--out DIR] [--skip-wsl]

What it does (details in BUILD_REPORT.md):
  1. Plans the file list from `git ls-files` (working-tree contents, so uncommitted edits are included) plus an explicit
     list of ignored items (scrub_rules.json), plus the 22 DEVS-Gen programs streamed out of WSL.
  2. Copies them into the export folder (default: <repo>/../vouch_artifact; the only folder this script deletes).
  3. Scrubs text files (names, dates, local paths, a few prose lines, three small code patches). Binary files are copied
     byte for byte.
  4. Re-hashes: updates hash lists and code pins that name a scrubbed file, writes freeze_v1_anonymized.json and
     anonymization_map.json.
  5. Adds the new files (README, LICENSE, NOTICE, data/README.md, program_list.csv, b0_results.md, .gitignore,
     .gitattributes, artifact_files.sha256).

It never edits the working repository. This folder (acmtrust_paper/artifact/) is not copied into the export: its rules
name the strings that are removed.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RULES = json.loads((HERE / "scrub_rules.json").read_text(encoding="utf-8"))
if (HERE / "prose_fixes.json").exists():                 # hand-written sentence edits, kept apart from the structural rules
    _prose = json.loads((HERE / "prose_fixes.json").read_text(encoding="utf-8"))
    RULES["line_fixes"].extend(_prose.get("pre_fixes", []))
    RULES.setdefault("post_fixes", []).extend(_prose.get("post_fixes", []))
TEMPLATES = HERE / "templates"


# ----------------------------------------------------------------------------------------------- helpers
def lp(p: Path | str) -> str:
    """Long-path-safe string for Windows file calls."""
    s = os.path.abspath(str(p))
    return "\\\\?\\" + s if os.name == "nt" and not s.startswith("\\\\?\\") else s


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_bytes(p: Path) -> bytes:
    with open(lp(p), "rb") as f:
        return f.read()


def write_bytes(p: Path, data: bytes) -> None:
    os.makedirs(lp(p.parent), exist_ok=True)
    with open(lp(p), "wb") as f:
        f.write(data)


def rm_readonly(func, path, exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-c", "core.quotepath=off", "-C", str(REPO), *args], check=True, capture_output=True).stdout


def wsl_bash(cmd: str) -> bytes:
    r = subprocess.run(["wsl.exe", "-d", RULES["wsl"]["distro"], "--", "bash", "-c", cmd], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"wsl command failed ({r.returncode}): {cmd[:80]}: {r.stderr.decode('utf-8', 'replace')[-300:]}")
    return r.stdout


# ----------------------------------------------------------------------------------------------- planning
class Plan:
    def __init__(self):
        self.items: dict[str, tuple[str, object]] = {}      # dest_rel -> ("file", Path) | ("bytes", bytes)
        self.origin: dict[str, str] = {}

    def add_file(self, rel: str, path: Path, why: str):
        rel = rel.replace("\\", "/")
        if rel not in self.items:
            self.items[rel] = ("file", path)
            self.origin[rel] = why

    def add_bytes(self, rel: str, data: bytes, why: str):
        rel = rel.replace("\\", "/")
        if rel not in self.items:
            self.items[rel] = ("bytes", data)
            self.origin[rel] = why


def walk(base: Path, skip_names=()):
    for dp, dns, fns in os.walk(lp(base)):
        dns[:] = [d for d in dns if d not in skip_names and d != ".git"]
        for fn in fns:
            full = Path(dp.replace("\\\\?\\", "")) / fn
            yield full


def plan_files(skip_wsl: bool) -> Plan:
    plan = Plan()
    ex_prefix = RULES["tracked_exclude_prefixes"]
    ex_exact = set(RULES["tracked_exclude_exact"])
    paper = RULES["paper"]
    tracked = [n for n in git("ls-files", "-z").decode("utf-8").split("\0") if n]

    # 1. tracked files outside the paper folder
    for n in tracked:
        if n in ex_exact or any(n.startswith(p) for p in ex_prefix) or "__pycache__" in n or n.endswith(".pyc"):
            continue
        src = REPO / n
        if src.exists():
            plan.add_file(n, src, "tracked")

    # 2. tracked paper files, allow-listed
    for n in tracked:
        if not n.startswith("acmtrust_paper/"):
            continue
        ok = n in paper["tracked_include_exact"] or any(n.startswith(p) for p in paper["tracked_include_prefixes"])
        for base, sufs in paper["tracked_include_suffixes_under"].items():
            if n.startswith(base) and n.count("/") == base.count("/") and any(n.endswith(s) for s in sufs):
                ok = True
        if ok and (REPO / n).exists():
            plan.add_file(n, REPO / n, "paper (tracked)")
    for pat in paper.get("extra_globs", []):                     # figure files that are not tracked yet (for example a new pipeline.pdf)
        for f in sorted(REPO.glob(pat)):
            rel = f.relative_to(REPO).as_posix()
            if rel not in paper.get("exclude_exact", []):
                plan.add_file(rel, f, "paper figure (glob)")
    for rel in paper.get("exclude_exact", []):
        plan.items.pop(rel, None)
    for d in paper["extra_dirs"]:
        base = REPO / d
        if base.is_dir():
            for f in walk(base, paper["extra_dir_skip_names"]):
                if f.suffix.lower() in paper.get("extra_dir_skip_suffixes", []):
                    continue
                plan.add_file(f.relative_to(REPO).as_posix(), f, "paper (ignored/untracked, listed)")

    # 3. ignored markdown notes inside the code and validation folders
    for d in RULES["ignored_md_dirs"]:
        for f in walk(REPO / d, ("__pycache__",)):
            if f.suffix == ".md":
                plan.add_file(f.relative_to(REPO).as_posix(), f, "ignored .md (listed)")

    # 4. run evidence
    runs = RULES["runs"]
    skip = set(runs["dir_skip_names"])
    for d in runs["dirs"]:
        base = REPO / d
        if not base.is_dir():
            raise SystemExit(f"missing run folder {d}")
        for f in walk(base, skip):
            if f.suffix == ".pyc":
                continue
            plan.add_file(f.relative_to(REPO).as_posix(), f, "runs (listed)")
    for fl in runs["files"]:
        plan.add_file(fl, REPO / fl, "runs (listed)")
    excl = [re.compile(x) for x in runs["logs_exclude_regex"]]
    logs = REPO / runs["logs_dir"]
    for f in walk(logs, skip):
        rel_in = f.relative_to(logs).as_posix()
        if any(x.search(rel_in) for x in excl):
            continue
        plan.add_file(f.relative_to(REPO).as_posix(), f, "runs logs (listed)")

    # 5. DEVS-Gen programs from WSL
    if not skip_wsl:
        freeze = json.loads((REPO / "manifests/freeze_v1.json").read_text(encoding="utf-8"))
        dirs = []
        for name in freeze["programs"]["names"]:
            if name.startswith("devs/"):
                _, label, task, run = name.split("/")
                task = DEVS_TASK.get(task, task)
                for part in (label, task, run):
                    assert re.fullmatch(r"[A-Za-z0-9_.-]+", part), part
                dirs.append(f"{label}/{task}/{run}")
        w = RULES["wsl"]
        cmd = (f"cd {w['gen_dir']} && tar -cf - " + " ".join(f"--exclude='{x}'" for x in
               [f"*{s}" for s in w["skip_suffixes"]] + w["skip_dir_names"]) + " " + " ".join(dirs))
        data = wsl_bash(cmd)
        n = 0
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                fobj = tf.extractfile(m)
                plan.add_bytes(f"{w['dest']}/{m.name}", fobj.read(), "WSL DEVS-Gen program")
                n += 1
        plan.add_bytes(w["lock_dest"], wsl_bash(f"cat {w['lock_file']}"), "WSL environment lock")
        print(f"WSL: {len(dirs)} programs, {n} files")
    return plan


# ----------------------------------------------------------------------------------------------- scrubbing
GENERIC = [(r["name"], re.compile(r["pattern"]), r["repl"], r["mode"], set(r.get("skip", [])), tuple(r.get("skip_prefix", [])))
           for r in RULES["generic"]]
PROSE_SKIP_PREFIX = ("runs/", "programs/")      # evidence rows and generated programs: only names and paths are rewritten there


def _cap_ctx(s: str, i: int) -> bool:
    j = i
    while j > 0 and s[j - 1] in " \t*_`\"'([>#|-":
        j -= 1
    return j == 0 or s[j - 1] in "\r\n.!?:"


def apply_generic(rel: str, text: str, stats: Counter) -> str:
    for name, rx, repl, mode, skip, skip_prefix in GENERIC:
        if rel in skip or (skip_prefix and rel.startswith(skip_prefix)):
            continue
        if mode == "plain":
            text, n = rx.subn(repl, text)
        else:
            def cb(m, repl=repl):
                lead = "The " if _cap_ctx(m.string, m.start()) else "the "
                return lead + repl
            text, n = rx.subn(cb, text)
        if n:
            stats[name] += n
    return text


VERBS = {"has": "have", "is": "are", "was": "were", "owns": "own", "wants": "want", "says": "say", "reports": "report",
         "prefers": "prefer", "asks": "ask", "requires": "require", "needs": "need", "decides": "decide", "approves": "approve",
         "accepts": "accept", "confirms": "confirm", "handles": "handle", "reviews": "review", "chooses": "choose", "sets": "set",
         "keeps": "keep", "gives": "give", "does": "do", "doesn't": "don't", "hasn't": "haven't", "isn't": "aren't",
         "registers": "register", "provides": "provide", "supplies": "supply", "pays": "pay", "runs": "run", "uses": "use",
         "expects": "expect", "reads": "read", "writes": "write", "checks": "check", "finds": "find", "changes": "change",
         "adds": "add", "objects": "object", "agrees": "agree", "thinks": "think", "believes": "believe", "knows": "know",
         "sees": "see", "picks": "pick", "selects": "select", "rejects": "reject", "plans": "plan", "intends": "intend",
         "notes": "note", "verifies": "verify", "judges": "judge", "rules": "rule", "signs": "sign", "authorises": "authorise"}
VERB_RX = re.compile(r"\b([Tt]he authors)( \w+ly)? (" + "|".join(sorted(VERBS, key=len, reverse=True)) + r")\b")


def fix_plural_verbs(text: str, stats: Counter) -> str:
    def cb(m):
        stats["verb-agreement"] += 1
        return f"{m.group(1)}{m.group(2) or ''} {VERBS[m.group(3)]}"
    return VERB_RX.sub(cb, text)


FIX_BY_FILE: dict[str, list[dict]] = defaultdict(list)
for fx in RULES["line_fixes"]:
    FIX_BY_FILE[fx["file"]].append(fx)
POST_BY_FILE: dict[str, list[dict]] = defaultdict(list)
for fx in RULES.get("post_fixes", []):
    POST_BY_FILE[fx["file"]].append(fx)
PATCH_BY_FILE: dict[str, list[dict]] = defaultdict(list)
for pt in RULES["patches"]:
    PATCH_BY_FILE[pt["file"]].append(pt)


def apply_manual(rel: str, text: str, stats: Counter, problems: list, manual_log: list, post: bool = False) -> str:
    crlf = "\r\n" in text
    for fx in (POST_BY_FILE if post else FIX_BY_FILE).get(rel, []):
        typ = fx.get("type", "literal")
        if typ == "literal":
            n = text.count(fx["old"])
            if n:
                text = text.replace(fx["old"], fx["new"])
        elif typ == "block":
            rx = re.compile(re.escape(fx["start"]) + r".*?" + re.escape(fx["end"]), re.S)
            text, n = rx.subn(lambda m: fx["new"], text)
        elif typ == "regex":
            text, n = re.subn(fx["pattern"], lambda m: fx["new"], text)
        elif typ == "delete_line":
            rx = re.compile(fx["pattern"])
            lines = text.splitlines(keepends=True)
            keep = [ln for ln in lines if not rx.search(ln.rstrip("\r\n"))]
            n = len(lines) - len(keep)
            text = "".join(keep)
        else:
            raise ValueError(typ)
        if n < 1:
            problems.append(f"line fix did not apply in {rel}: {fx.get('old') or fx.get('pattern') or fx.get('start')!r:.80}")
        else:
            stats["manual:" + rel] += n
            manual_log.append({"file": rel, "kind": "prose/line fix", "times": n})
    for pt in ([] if post else PATCH_BY_FILE.get(rel, [])):
        new = pt["new"].replace("\n", "\r\n") if crlf else pt["new"]
        n = text.count(pt["old"])
        if n < 1:
            problems.append(f"code patch did not apply in {rel}: {pt['old']!r:.80}")
            continue
        if pt.get("occurrence") == "first":
            text = text.replace(pt["old"], new, 1)
            n = 1
        else:
            text = text.replace(pt["old"], new)
        stats["patch:" + rel] += n
        manual_log.append({"file": rel, "kind": "code patch", "times": n})
    return text


BIN_SUF = set(RULES["binary_suffixes"])


def decode_text(rel: str, data: bytes):
    if Path(rel).suffix.lower() in BIN_SUF:
        return None
    if b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scrub(rel: str, txt: str, stats: Counter, problems: list, manual_log: list) -> str:
    t = apply_manual(rel, txt, stats, problems, manual_log)
    t = apply_generic(rel, t, stats)
    if not rel.startswith(PROSE_SKIP_PREFIX):
        t = fix_plural_verbs(t, stats)
    return apply_manual(rel, t, stats, problems, manual_log, post=True)


def process(rel: str, data: bytes, stats: Counter, problems: list, manual_log: list) -> bytes:
    """Return the bytes to ship for this file."""
    if rel.endswith(".gz") and rel.startswith(RULES["wsl"]["dest"]):
        try:
            raw = gzip.decompress(data)
        except OSError:
            return data
        txt = decode_text(rel[:-3], raw)
        if txt is None:
            return data
        new = scrub(rel, txt, stats, problems, manual_log)
        if new == txt:
            return data
        stats["gz-recompressed"] += 1
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
            g.write(new.encode("utf-8"))
        return buf.getvalue()
    txt = decode_text(rel, data)
    if txt is None:
        return data
    new = scrub(rel, txt, stats, problems, manual_log)
    return data if new == txt else new.encode("utf-8")


# ----------------------------------------------------------------------------------------------- templates
def render(name: str, mapping: dict[str, str]) -> bytes:
    t = (TEMPLATES / name).read_text(encoding="utf-8")
    for k, v in mapping.items():
        t = t.replace("{{" + k + "}}", str(v))
    left = re.findall(r"\{\{[A-Z0-9_]+\}\}", t)
    if left:
        raise SystemExit(f"{name}: unfilled placeholders {sorted(set(left))}")
    return t.encode("utf-8")


def process_of(doc: str) -> str:
    d = doc.lower()
    if "loan" in d:
        return "loan"
    if "pharmacy" in d:
        return "pharmacy"
    if d.startswith("mfg"):
        return "manufacturing"
    if d.startswith("itops"):
        return "it_ops"
    return "?"


TASK_PROCESS = {"WorkflowLoan": "loan", "WorkflowPharmacy": "pharmacy", "Manufacturing": "manufacturing", "ITOperations": "it_ops"}
OTF_FOLDER = {"b0": "build_test_v1", "r1": "build_test_r1", "r1_claude": "build_test_r1_claude", "b0_claude": "build_test_b0_claude"}
DEVS_MODEL = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}
DEVS_TASK = {"workflow_loan_dev": "WorkflowLoan", "workflow_pharmacy_dev": "WorkflowPharmacy"}   # program names use the document, WSL folders the task


def program_rows(out: Path):
    freeze = json.loads((REPO / "manifests/freeze_v1.json").read_text(encoding="utf-8"))
    rows, bad = [], []
    for name in freeze["programs"]["names"]:
        p = name.split("/")
        if p[0] == "otf":
            system, setup, doc, build = p[1:5]
            plat = "OTF-Tools B0 (unchanged original)" if system.startswith("b0") else "OTF-Tools R1 (revised path)"
            path = f"runs/{OTF_FOLDER[system]}/{setup}/{doc}/{build}/program.json"
            rows.append([name, plat, setup, "claude" if setup.startswith("claude-") else "ollama", process_of(doc), doc, build, path])
        elif p[0] == "devs":
            label, doc, run = p[1:4]
            task = DEVS_TASK.get(doc, doc)
            model = DEVS_MODEL.get(label, label)
            rows.append([name, "DEVS-Gen", model, "claude" if model.startswith("claude-") else "ollama", TASK_PROCESS[task], doc, run,
                         f"programs/devs_gen/{label}/{task}/{run}/run.py"])
        elif p[0] == "agent":
            model, task, b = p[1], p[2], p[3]
            rows.append([name, "plain reason-and-code agent", model, "claude" if model.startswith("claude-") else "ollama",
                         TASK_PROCESS[task], task, b, f"runs/coding_agent/{model}/{task}/{b}/run.py"])
        else:
            bad.append(name)
    for r in rows:
        if not (out / r[-1]).exists():
            bad.append(f"{r[0]} -> missing {r[-1]}")
    return rows, bad


def b0_results(out: Path):
    lines, total, acc = [], 0, 0
    per = defaultdict(lambda: [0, 0, 0.0, 0.0])
    per_doc = defaultdict(lambda: [0, 0])
    for folder in ("build_test_v1", "build_test_b0_claude"):
        for f in sorted((out / "runs" / folder).glob("builds_*.jsonl")):
            for ln in f.read_text(encoding="utf-8").splitlines():
                if not ln.strip():
                    continue
                b = json.loads(ln)
                setup, doc, _ = b["build"].split("/")
                total += 1
                a = bool(b.get("accepted"))
                acc += a
                row = per[(folder, setup)]
                row[0] += 1
                row[1] += a
                row[2] += float(b.get("mean_f1") or 0)
                row[3] += float(b.get("usd_list_price") or 0)
                d = per_doc[(process_of(doc), doc)]
                d[0] += 1
                d[1] += a
    bench = (REPO / "acmtrust_paper/sections/04_benchmark.tex").read_text(encoding="utf-8")      # the paper source is not in the output
    m = re.search(r"accepted (\d+) of (\d+) builds", bench)
    paper = f"{m.group(1)} of {m.group(2)}" if m else "(sentence not found)"
    matches = bool(m) and int(m.group(1)) == acc and int(m.group(2)) == total
    return total, acc, per, per_doc, paper, matches


PACK_GROUPS = ["runs/main_v1/wf_test", "runs/main_v1/ml_test", "runs/main_v1/wf_policy", "runs/main_v1/logs", "runs/judges_main_v1",
               "runs/build_test_main_claude", "runs/build_test_judges", "runs/build_test_pilot_claude", "runs/build_test_assurance_claude",
               "runs/build_test_coding_agent", "runs/build_test_b0_claude", "runs/build_test_v1", "runs/build_test_r1",
               "runs/build_test_r1_claude", "runs/coding_agent", "programs/devs_gen"]


def pack_groups(out: Path) -> str:
    """Replace the big evidence folders by deterministic .tar.gz archives (fallback for hosts with size or file-count limits)."""
    archives, contents = [], []
    for g in PACK_GROUPS:
        base = out / g
        if not base.is_dir():
            continue
        files = sorted(walk(base), key=lambda p: p.relative_to(out).as_posix())
        arc = out / (g + ".tar.gz")
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tf:
                for f in files:
                    rel = f.relative_to(out).as_posix()
                    data = read_bytes(f)
                    ti = tarfile.TarInfo(rel)
                    ti.size, ti.mtime, ti.mode, ti.uid, ti.gid, ti.uname, ti.gname = len(data), 0, 0o644, 0, 0, "", ""
                    tf.addfile(ti, io.BytesIO(data))
        write_bytes(arc, buf.getvalue())
        contents.extend(f"{sha256_bytes(read_bytes(f))} *{f.relative_to(out).as_posix()}" for f in files)
        unpacked = sum(f.stat().st_size for f in files)
        shutil.rmtree(lp(base), onerror=rm_readonly)
        archives.append({"archive": arc.relative_to(out).as_posix(), "folder": g, "files": len(files), "bytes_unpacked": unpacked,
                         "bytes_archive": len(buf.getvalue())})
    write_bytes(out / "PACKED.json", (json.dumps({"what": "Archives that replace large folders. Run `python scripts/unpack_evidence.py` from the artifact root to restore them.",
                                                  "archives": archives}, indent=1) + "\n").encode("utf-8"))
    write_bytes(out / "packed_contents.sha256", ("\n".join(contents) + "\n").encode("utf-8"))
    write_bytes(out / "scripts/unpack_evidence.py", render("unpack_evidence.py", {}))
    return ("> **This copy is packed.** The large evidence folders are stored as `.tar.gz` archives (listed in `PACKED.json`) because the host "
            "limits file size, total size or file count. Run `python scripts/unpack_evidence.py` once from this folder before any command below; "
            "it restores the folders, and `sha256sum -c packed_contents.sha256` checks every restored file. The archive files themselves are "
            "covered by `artifact_files.sha256`.\n")


def b0_row_files(out: Path):
    res = {}
    for s in ("wf_test", "ml_test", "wf_policy"):
        d = out / "runs/main_v1" / s / "programs"
        res[s] = sorted(f.name for f in d.glob("otf_b0*")) if d.is_dir() else []
    return res


# ----------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO.parent / RULES["out_dir_name"]))
    ap.add_argument("--skip-wsl", action="store_true")
    ap.add_argument("--pack", action="store_true",
                    help="fallback for hosts with small size or file-count limits: replace the large evidence folders by .tar.gz "
                         "archives (scripts/unpack_evidence.py restores them)")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    if out.name != RULES["out_dir_name"] or out == REPO or REPO in out.parents or out in REPO.parents:
        raise SystemExit(f"refusing to delete {out}: it must be a folder named {RULES['out_dir_name']} outside the repository")
    t0 = time.time()
    problems: list[str] = []
    stats: Counter = Counter()
    manual_log: list = []

    plan = plan_files(a.skip_wsl)
    print(f"planned {len(plan.items)} files")

    if out.exists():                                  # empty the export folder but keep a .git folder if the user has made one
        for name in os.listdir(lp(out)):
            if name == ".git":
                continue
            child = out / name
            if child.is_dir():
                shutil.rmtree(lp(child), onerror=rm_readonly)
            else:
                os.chmod(lp(child), stat.S_IWRITE)
                os.remove(lp(child))
    os.makedirs(lp(out), exist_ok=True)

    changed: dict[str, tuple[str, str]] = {}
    unchanged_count = 0
    for rel in sorted(plan.items):
        kind, src = plan.items[rel]
        data = read_bytes(src) if kind == "file" else src
        new = process(rel, data, stats, problems, manual_log)
        write_bytes(out / rel, new)
        if new != data:
            changed[rel] = (sha256_bytes(data), sha256_bytes(new))
        else:
            unchanged_count += 1
    print(f"copied; {len(changed)} files changed by scrubbing, {unchanged_count} copied as they were")

    # ---- hash lists and code pins that name a scrubbed file
    evidence_prefix = ("runs/", RULES["wsl"]["dest"] + "/")
    old2new = {o: n for rel, (o, n) in changed.items() if not rel.startswith(evidence_prefix)}
    hl_updated: dict[str, list] = {}
    hl_stale: list[str] = []
    import fnmatch
    all_rels = sorted(plan.items)
    for glob in RULES["hash_list_globs"]:
        for rel in all_rels:
            if not fnmatch.fnmatch(rel, glob):
                continue
            p = out / rel
            text = read_bytes(p).decode("utf-8")
            lines, ch = text.splitlines(keepends=True), []
            for i, ln in enumerate(lines):
                m = re.match(r"^([0-9a-f]{64})(\s+\*?)(.*?)(\s*)$", ln.rstrip("\r\n"))
                if not m:
                    continue
                path = m.group(3).split("  drawn ")[0].strip()
                if path in changed and m.group(1) == changed[path][0]:
                    eol = ln[len(ln.rstrip("\r\n")):]
                    lines[i] = changed[path][1] + ln.rstrip("\r\n")[64:] + eol
                    ch.append({"path": path, "old": changed[path][0], "new": changed[path][1]})
                elif path in plan.items and (out / path).is_file():
                    actual = sha256_bytes(read_bytes(out / path))
                    if actual != m.group(1):
                        hl_stale.append(f"{rel}: {path}")
            if ch:
                write_bytes(p, "".join(lines).encode("utf-8"))
                hl_updated[rel] = ch
    pins: dict[str, list] = {}
    for glob in RULES["code_pin_globs"]:
        for rel in all_rels:
            if not fnmatch.fnmatch(rel, glob):
                continue
            p = out / rel
            text = read_bytes(p).decode("utf-8")
            hit = [o for o in old2new if o in text]
            if hit:
                for o in hit:
                    text = text.replace(o, old2new[o])
                write_bytes(p, text.encode("utf-8"))
                pins[rel] = [{"old": o, "new": old2new[o]} for o in hit]
    # the files a hash list or pin touched changed too: refresh their entry in `changed`
    for rel in list(hl_updated) + list(pins):
        src_kind, src = plan.items[rel]
        orig = read_bytes(src) if src_kind == "file" else src
        changed[rel] = (sha256_bytes(orig), sha256_bytes(read_bytes(out / rel)))

    # ---- freeze record and map
    orig_freeze = json.loads((REPO / RULES["keep_original_freeze"]).read_text(encoding="utf-8"))
    frozen_map, new_files = {}, {}
    for p, oldh in orig_freeze["files"].items():
        f = out / p
        if not f.is_file():
            problems.append(f"frozen file missing in export: {p}")
            continue
        newh = sha256_bytes(read_bytes(f))
        new_files[p] = newh
        frozen_map[p] = {"original_sha256": oldh, "anonymized_sha256": newh, "changed": newh != oldh}
    anon_freeze = {
        "frozen_at_utc": orig_freeze["frozen_at_utc"],
        "anonymized_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": ("Same record as manifests/freeze_v1.json, with sha256 recomputed on the anonymized files. Only names, dates and "
                 "local paths differ (see anonymization_map.json). Program names are unchanged."),
        "original_record": RULES["keep_original_freeze"],
        "files": new_files,
        "missing": [],
        "programs": orig_freeze["programs"],
        "seccomp_filter_wsl": orig_freeze["seccomp_filter_wsl"],
    }
    write_bytes(out / "manifests/freeze_v1_anonymized.json", (json.dumps(anon_freeze, indent=1) + "\n").encode("utf-8"))
    amap = {
        "what": ("Old sha256 (the files in the authors' working tree) to new sha256 (the files in this artifact), for every file the "
                 "anonymization changed. Changes are: author and advisor names, local file paths, a few prose lines, and three small code "
                 "edits; the exact list is under `manual_edits`."),
        "generic_rules": [{"name": r["name"], "pattern": "(listed in the builder, not shown for anonymity)"} for r in RULES["generic"]],
        "generic_rule_counts": {k: v for k, v in sorted(stats.items()) if not k.startswith(("manual:", "patch:"))},
        "frozen_files": frozen_map,
        "hash_lists_updated": hl_updated,
        "code_pins_updated": pins,
        "manual_edits": manual_log,
        "changed_files_outside_runs": {rel: {"original_sha256": o, "anonymized_sha256": n}
                                       for rel, (o, n) in sorted(changed.items()) if not rel.startswith(evidence_prefix)},
        "changed_run_files": {rel: {"original_sha256": o, "anonymized_sha256": n}
                              for rel, (o, n) in sorted(changed.items()) if rel.startswith(evidence_prefix)},
    }
    write_bytes(out / "anonymization_map.json", (json.dumps(amap, indent=1) + "\n").encode("utf-8"))

    # ---- new files
    rows, bad = program_rows(out)
    problems += [f"program list: {b}" for b in bad]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["name", "platform", "builder_model", "builder_class", "process", "document_or_task", "build_or_run", "path_in_artifact"])
    w.writerows(rows)
    write_bytes(out / "program_list.csv", buf.getvalue().encode("utf-8"))
    by_plat = Counter(r[1] for r in rows)

    total, acc, per, per_doc, paper, matches = b0_results(out)
    b0_files = b0_row_files(out)
    md = ["# B0 results: the unchanged original OTF-Tools builds", ""]
    md.append(f"**{acc} of {total} builds were accepted** by the platform's own acceptance check "
              f"(a build is accepted when its program reproduces the hidden recorded outcomes closely enough). "
              f"Derived from `runs/build_test_v1/builds_*.jsonl` and `runs/build_test_b0_claude/builds_*.jsonl`.")
    md.append("")
    md.append(f"The paper says: \"accepted {paper} builds\". "
              + ("This matches the count derived here." if matches else "**This does NOT match the count derived here.**"))
    md.append("")
    md.append("The 60 builds are 12 per builder model: 3 builds on each of the 4 development documents "
              "(loan, pharmacy, manufacturing, IT operations). The 32 accepted builds are the 32 B0 programs in `program_list.csv`.")
    md.append("")
    md.append("| builder model | run folder | builds | accepted | mean F1 on hidden outcomes | list-price cost (USD) |")
    md.append("|---|---|---:|---:|---:|---:|")
    for (folder, setup), (n, ac, f1, usd) in sorted(per.items(), key=lambda kv: (kv[0][1])):
        md.append(f"| {setup} | `runs/{folder}/` | {n} | {ac} | {f1 / n:.3f} | {usd:.2f} |")
    md.append("")
    md.append("By development document:")
    md.append("")
    md.append("| process | document | builds | accepted |")
    md.append("|---|---|---:|---:|")
    for (proc, doc), (n, ac) in sorted(per_doc.items()):
        md.append(f"| {proc} | {doc} | {n} | {ac} |")
    md.append("")
    md.append("B0 programs answer only through OTF-Tools' own path (native-only). Their decision rows are the files named "
              "`otf_b0_*` and `otf_b0_claude_*` under `runs/main_v1/<set>/programs/`: "
              + ", ".join(f"{s}: {len(v)} files" for s, v in b0_files.items()) + ".")
    md.append("")
    md.append("B0 and R1 import the pinned OTF-Tools implementation at run time. That code is withheld during review (see `README.md`), "
              "so the builds above cannot be re-executed from this artifact; the build records, programs and decision rows are included.")
    write_bytes(out / "b0_results.md", ("\n".join(md) + "\n").encode("utf-8"))

    write_bytes(out / "scripts/wsl_install_programs.sh", render("wsl_install_programs.sh", {}))
    write_bytes(out / "scripts/verify_files.py", render("verify_files.py", {}))
    write_bytes(out / "LICENSE", render("LICENSE", {}))
    write_bytes(out / "NOTICE.md", render("NOTICE.md", {}))
    write_bytes(out / "data/README.md", render("data_README.md", {}))
    write_bytes(out / ".gitignore", render("gitignore", {}))
    write_bytes(out / ".gitattributes", render("gitattributes", {}))
    pack_note = pack_groups(out) if a.pack else ""

    # size figures for the README need the export so far
    def tree_stats():
        n = size = 0
        for f in walk(out):
            n += 1
            size += f.stat().st_size
        return n, size
    n, size = tree_stats()
    mapping = {
        "N_PROGRAMS": len(rows),
        "N_OTF": sum(v for k, v in by_plat.items() if k.startswith("OTF")),
        "N_R1": by_plat["OTF-Tools R1 (revised path)"],
        "N_B0": by_plat["OTF-Tools B0 (unchanged original)"],
        "N_DEVS": by_plat["DEVS-Gen"],
        "N_AGENT": by_plat["plain reason-and-code agent"],
        "B0_ACC": acc,
        "B0_TOTAL": total,
        "APPROX_MB": f"{size / 1e6:.0f}",
        "N_FROZEN_CHANGED": sum(1 for v in frozen_map.values() if v["changed"]),
        "PACK_NOTE": pack_note,
    }
    big = max(walk(out), key=lambda f: f.stat().st_size)
    per_dir = Counter(f.parent for f in walk(out))
    bigdir, bign = per_dir.most_common(1)[0]
    mapping["LARGEST_FILE"] = f"`{big.relative_to(out).as_posix()}` ({big.stat().st_size / 1e6:.1f} MB)"
    mapping["LARGEST_FOLDER"] = f"`{bigdir.relative_to(out).as_posix()}/` ({bign} files)"
    mapping.update(json.loads((TEMPLATES / "notes.json").read_text(encoding="utf-8")))
    write_bytes(out / "README.md", render("README.md", mapping))

    # file manifest last
    lines = []
    for f in sorted(walk(out), key=lambda p: p.relative_to(out).as_posix()):
        rel = f.relative_to(out).as_posix()
        if rel == "artifact_files.sha256":
            continue
        lines.append(f"{sha256_bytes(read_bytes(f))} *{rel}")
    write_bytes(out / "artifact_files.sha256", ("\n".join(lines) + "\n").encode("utf-8"))

    n, size = tree_stats()
    summary = {
        "built_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "out": str(out),
        "files": n,
        "bytes": size,
        "scrub_changed_files": len(changed),
        "scrub_rule_counts": dict(stats),
        "hash_lists_updated": {k: len(v) for k, v in hl_updated.items()},
        "hash_list_entries_not_matching_files_in_export": hl_stale,
        "code_pins_updated": {k: len(v) for k, v in pins.items()},
        "frozen_files_changed": sorted(p for p, v in frozen_map.items() if v["changed"]),
        "programs": len(rows),
        "b0": [acc, total, paper, matches],
        "problems": problems,
        "seconds": round(time.time() - t0, 1),
        "origin_counts": dict(Counter(plan.origin.values())),
    }
    (HERE / "last_build.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("scrub_rule_counts",)}, indent=1))
    if problems:
        print("PROBLEMS:", *problems, sep="\n  ")
        sys.exit(2)


if __name__ == "__main__":
    main()
