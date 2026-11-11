"""IT questions are numeric only (decision of 2026-11-09). This check now asserts that no manufacturing or IT
question is a yes/no (`task_starts_by`) question. Given an earlier file pair, it also lists the ids whose content
changed, so a blind re-check can be limited to them. The earlier deadline checks (equality with either start,
unprinted times in the text, yes/no mix) were retired together with the yes/no questions; why they were dropped is
in manifests/domain_readiness.md. Exits nonzero on any yes/no question.

Usage: python -X utf8 validation/mlsys_deadline_check.py <dev.json> <test.json> [<old_dev.json> <old_test.json> <changed_ids_out.json>]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def main(dev, test, old_dev=None, old_test=None, out=None):
    load = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))
    qs = load(dev) + load(test)
    yn = [q["id"] for q in qs if q["query"]["kind"] == "task_starts_by"]
    print(len(qs), "questions;", len(yn), "yes/no", yn[:5], "| query kinds", dict(Counter(q["query"]["kind"] for q in qs)))
    if old_dev:
        old = {q["id"]: q for q in load(old_dev) + load(old_test)}
        new = {q["id"]: q for q in qs}
        # fields added after the earlier files (e.g. the beyond_window label) are not content changes
        changed = sorted(k for k in new if k not in old or {f: v for f, v in new[k].items() if f in old[k]} != old[k])
        print("changed against the earlier files:", len(changed), "of", len(new),
              dict(Counter("-".join(k.split("-")[:3]) for k in changed)))
        if out:
            Path(out).write_text(json.dumps(changed, indent=1), encoding="utf-8")
    return 1 if yn else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:6]))
