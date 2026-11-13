"""List the main-set rows whose frozen Vouch decision depended on the capability record.

A decision depends on the record when it was declined because of an earlier failure (Already caught) or trusted on
evidence reused from an earlier question. Every other decision was reached by tests run on the question itself.
Usage: python -X utf8 acmtrust_paper/sensitivity/fresh_record_rows.py <root> <out.json>
"""
import json
import sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path[:0] = [str(root), str(root / "scripts")]
import main_analysis as ma  # noqa: E402
import main_runner as mr  # noqa: E402
import main_summary as ms  # noqa: E402

rows, _, _, _, _ = ma.load_rows(root, ["wf_test", "ml_test"], mr, ms)
kinds = Counter()
out = []
for r in rows:
    d = r["decisions"]["directed"]
    reason = d.get("reason") or ""
    t = ma.term(d, r["has"])
    if t == "Already caught":
        kind = "already_caught"
    elif d["permit"] and "reused evidence" in reason:
        kind = "trusted_on_reuse"
    elif "reused" in reason or "earlier" in reason:
        kind = "other_record:" + reason[:40]
    else:
        continue
    kinds[(r["class"], kind, "wrong" if (r["has"] and not r["correct"]) else ("right" if r["has"] else "no answer"))] += 1
    out.append({"set": r["set"], "program": r["program"], "question": r["question"], "class": r["class"], "kind": kind,
                "has": r["has"], "correct": r["correct"], "reason": reason[:200]})
for k, v in sorted(kinds.items()):
    print(k, v)
print("rows:", len(out))
Path(sys.argv[2]).write_text(json.dumps(out, indent=1), encoding="utf-8")
