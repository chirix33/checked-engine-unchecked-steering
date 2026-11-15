#!/usr/bin/env python3
"""Check every file against artifact_files.sha256 (works on Windows, macOS and Linux).

Usage (from the artifact root):  python scripts/verify_files.py
Exit status 0 means every listed file is present with the listed sha256 and no unlisted file was found
(`.git/` and `__pycache__/` are ignored).
"""
import hashlib
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
listed = {}
for line in (root / "artifact_files.sha256").read_text(encoding="utf-8").splitlines():
    if line.strip():
        h, _, rel = line.partition(" *")
        listed[rel] = h
bad = []
for rel, h in listed.items():
    p = root / rel
    if not p.is_file():
        bad.append(f"missing  {rel}")
    elif hashlib.sha256(p.read_bytes()).hexdigest() != h:
        bad.append(f"changed  {rel}")
extra = []
for dp, dns, fns in os.walk(root):
    dns[:] = [d for d in dns if d not in (".git", "__pycache__")]
    for fn in fns:
        rel = (Path(dp) / fn).relative_to(root).as_posix()
        if rel not in listed and rel != "artifact_files.sha256":
            extra.append(f"unlisted {rel}")
for b in bad + extra:
    print(b)
print(f"{len(listed)} files listed; {len(bad)} missing or changed, {len(extra)} unlisted")
sys.exit(1 if bad or extra else 0)
