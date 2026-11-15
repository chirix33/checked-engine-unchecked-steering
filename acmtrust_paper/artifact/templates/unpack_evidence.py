#!/usr/bin/env python3
"""Restore the evidence folders from the .tar.gz archives listed in PACKED.json.

Usage (from the artifact root):  python scripts/unpack_evidence.py
Afterwards:                      sha256sum -c packed_contents.sha256
"""
import json
import sys
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
packed = json.loads((root / "PACKED.json").read_text(encoding="utf-8"))
for a in packed["archives"]:
    arc = root / a["archive"]
    with tarfile.open(arc, "r:gz") as tf:
        for m in tf.getmembers():                         # refuse anything that would leave the artifact folder
            target = (root / m.name).resolve()
            if root not in target.parents:
                sys.exit(f"unsafe path in {arc}: {m.name}")
        try:
            tf.extractall(root, filter="data")            # Python 3.12+ / 3.11.4+
        except TypeError:
            tf.extractall(root)
    print(f"restored {a['folder']}/ ({a['files']} files)")
