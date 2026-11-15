#!/usr/bin/env python3
"""Scan the artifact export for identity strings, local paths, unexpected links and secrets; report sizes.

Usage: python -X utf8 acmtrust_paper/artifact/verify_artifact.py [--out DIR] [--show 25]

Identity, path, link and secret hits are printed as file:line. Literal values from the project's .env are searched for
in every file, and only key names and counts are printed, never a value.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RULES = json.loads((HERE / "scrub_rules.json").read_text(encoding="utf-8"))
V = RULES["verify"]


def lp(p):
    s = os.path.abspath(str(p))
    return "\\\\?\\" + s if os.name == "nt" and not s.startswith("\\\\?\\") else s


def walk(base: Path):
    for dp, dns, fns in os.walk(lp(base)):
        dns[:] = [d for d in dns if d != ".git"]
        for fn in fns:
            yield Path(dp.replace("\\\\?\\", "")) / fn


def git_state(out: Path) -> dict:
    """If the export has been turned into a repository, report who the commits and the remote name (names, not secrets)."""
    if not (out / ".git").exists():
        return {"repository": "none yet"}
    def g(*a):
        return subprocess.run(["git", "-C", str(out), *a], capture_output=True, text=True).stdout.strip()
    return {"repository": "present", "commit_identities": sorted(set(g("log", "--all", "--format=%an <%ae> | %cn <%ce>").splitlines())),
            "commits": len(g("rev-list", "--all").splitlines()), "remotes": g("remote", "-v").splitlines(),
            "branches": g("branch", "-a").splitlines()}


def git_identities() -> list[str]:
    """Names and e-mail local parts from the repository's commits and config, to search for as well."""
    out = set()
    try:
        raw = subprocess.run(["git", "-C", str(REPO), "log", "--format=%an%n%ae%n%cn%n%ce"], capture_output=True, text=True).stdout
        raw += subprocess.run(["git", "-C", str(REPO), "config", "user.name"], capture_output=True, text=True).stdout
        raw += subprocess.run(["git", "-C", str(REPO), "config", "user.email"], capture_output=True, text=True).stdout
        for tok in set(raw.split("\n")):
            tok = tok.strip()
            if not tok or tok.lower() in ("github", "noreply@github.com"):
                continue
            out.add(tok)
            if "@" in tok:
                out.add(tok.split("@")[0].split("+")[-1])
            else:
                out.update(t for t in re.split(r"[\s-]+", tok) if len(t) >= 4)
    except Exception:
        pass
    return sorted(t for t in out if len(t) >= 4)


def env_values() -> dict[str, bytes]:
    vals = {}
    envf = REPO / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if len(v) >= 8:
                vals[k.strip()] = v.encode("utf-8")
    return vals


def check_tex_refs(out: Path) -> list[str]:
    """Files named by \\includegraphics, \\input, \\include and \\bibliography in the exported paper that are not in the export."""
    paper = out / "acmtrust_paper"
    missing = []
    if not paper.is_dir():
        return ["acmtrust_paper/ missing"]
    for tex in sorted(paper.rglob("*.tex")):
        if "figures/src" in tex.as_posix():
            continue
        text = "\n".join(ln for ln in tex.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("%"))
        refs = []
        for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", text):
            refs.append((m.group(1), ["", ".pdf", ".png", ".jpg"]))
        for m in re.finditer(r"\\(?:input|include)\{([^}]+)\}", text):
            refs.append((m.group(1), ["", ".tex"]))
        for m in re.finditer(r"\\bibliography\{([^}]+)\}", text):
            refs.extend((b, [".bib"]) for b in m.group(1).split(","))
        for m in re.finditer(r"\\bibliographystyle\{([^}]+)\}", text):
            refs.append((m.group(1), [".bst"]))
        for name, exts in refs:
            if not any((paper / (name + e)).is_file() for e in exts):
                missing.append(f"{tex.relative_to(out).as_posix()}: {name}")
    return missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO.parent / RULES["out_dir_name"]))
    ap.add_argument("--show", type=int, default=25)
    a = ap.parse_args()
    out = Path(a.out).resolve()
    ids = git_identities()
    ident_rx = re.compile(V["identity_regex"] + ("|" + "|".join(re.escape(i) for i in ids) if ids else ""), re.I)
    path_rx = re.compile(V["path_regex"])
    neutral_rx = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+user\b|/home/user\b|/mnt/c/Users/user\b")
    bin_rx = re.compile(V["binary_identity_regex"] + ("|" + "|".join(re.escape(i) for i in ids if len(i) >= 5) if ids else ""), re.I)
    secret_rx = re.compile(V["secret_regex"])
    url_rx = re.compile(r"https?://([A-Za-z0-9.-]+)(/[^\s)\"'<>`\]\\]*)?")
    envs = env_values()
    allowed_hosts = set(V["allowed_link_hosts"])
    allowed_owners = {o.lower() for o in V["allowed_github_owners"]}

    hits = {"identity": [], "path": [], "secret": []}
    env_hits: Counter = Counter()
    hosts: Counter = Counter()
    host_where: dict[str, str] = {}
    owners: Counter = Counter()
    owner_where: dict[str, str] = {}
    n_files = n_text = n_bin = 0
    neutral_lines = 0
    total = 0
    big = []
    per_dir: Counter = Counter()
    pdf_hits = []

    for f in walk(out):
        rel = f.relative_to(out).as_posix()
        n_files += 1
        size = f.stat().st_size
        total += size
        per_dir[f.parent.relative_to(out).as_posix()] += 1
        if size > 10_000_000:
            big.append((rel, size))
        data = f.read_bytes()
        if rel.endswith(".gz"):
            try:
                data = gzip.decompress(data)
            except OSError:
                pass
        for k, v in envs.items():
            if v in data:
                env_hits[k] += 1
        if rel == "artifact_files.sha256":
            continue
        try:
            text = data.decode("utf-8") if b"\0" not in data[:8192] else None
        except UnicodeDecodeError:
            text = None
        if text is None:
            n_bin += 1
            m = bin_rx.search(data.decode("latin-1"))
            if m:
                pdf_hits.append(rel)
            continue
        n_text += 1
        for i, line in enumerate(text.splitlines(), 1):
            if ident_rx.search(line):
                hits["identity"].append(f"{rel}:{i}")
            pm = path_rx.search(line)
            if pm:
                hits["path"].append(f"{rel}:{i}  [{line[max(0, pm.start() - 25):pm.end() + 25].strip()[:80]}]")
            if neutral_rx.search(line):
                neutral_lines += 1
            if secret_rx.search(line):
                hits["secret"].append(f"{rel}:{i}")
            for m in url_rx.finditer(line):
                h = m.group(1).lower().rstrip(".")
                hosts[h] += 1
                host_where.setdefault(h, f"{rel}:{i}")
                if h == "github.com" and m.group(2):
                    own = m.group(2).strip("/").split("/")[0].lower()
                    owners[own] += 1
                    owner_where.setdefault(own, f"{rel}:{i}")

    res = {
        "files": n_files, "text_files": n_text, "binary_files": n_bin, "bytes": total,
        "files_over_10MB": big, "files_over_50MB": [b for b in big if b[1] > 50_000_000],
        "max_files_in_one_folder": per_dir.most_common(3),
        "lines_with_neutral_user_paths_C_Users_user_or_home_user": neutral_lines,
        "tex_references_missing_in_export": check_tex_refs(out),
        "git": git_state(out),
        "identity_hits": len(hits["identity"]), "path_hits": len(hits["path"]), "secret_hits": len(hits["secret"]),
        "binary_files_with_identity_like_bytes": pdf_hits,
        "env_value_hits_by_key": dict(env_hits), "env_keys_checked": sorted(envs),
        "identity_terms_from_git": len(ids),
        "link_hosts_not_allowed": {h: [c, host_where[h]] for h, c in hosts.items() if h not in allowed_hosts},
        "github_owners_not_allowed": {o: [c, owner_where[o]] for o, c in owners.items() if o not in allowed_owners},
        "link_hosts_all": dict(hosts.most_common()),
        "github_owners_all": dict(owners.most_common()),
    }
    (HERE / "last_verify.json").write_text(json.dumps({**res, "hit_samples": {k: v[: a.show] for k, v in hits.items()}}, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("link_hosts_all",)}, indent=1))
    for k in ("identity", "path", "secret"):
        if hits[k]:
            print(f"-- {k} hits (first {a.show}):")
            for h in hits[k][: a.show]:
                print("   ", h)
    bad = hits["identity"] or hits["path"] or hits["secret"] or env_hits or res["files_over_50MB"] or pdf_hits or res["tex_references_missing_in_export"]
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
