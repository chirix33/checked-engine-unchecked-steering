"""Draw the 50 rows of the Sonnet ReAct judge (D29) from the shared 150, before any judging.

It continues the frozen nested draw of `judges.draw_subsets` by one level, with the same seed and the same rows
(row ids, cohort and family only; no label is read). It first checks that the draw's first three levels equal the
frozen subsets file exactly, so the 50 are the next level of the same draw. The ids and their sha256 are written to
OUT, with a sidecar `.sha256` holding the file's hash and the draw time. An existing OUT is never overwritten: the
draw is redone and must be identical.

Usage: python -X utf8 scripts/draw_react50.py <root> <sets> <frozen_subsets.json> <out.json>
"""
import hashlib
import json
import sys
import time
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sets = tuple(sys.argv[2].split(","))
frozen_path, out = root / sys.argv[3], root / sys.argv[4]
sys.path[:0] = [str(root), str(root / "scripts")]
sys.dont_write_bytecode = True
import judges  # noqa: E402

sha = lambda t: hashlib.sha256(t.encode("utf-8")).hexdigest()
frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
rows = judges.answered_rows(root, sets)
sizes = tuple((k, frozen["subsets"][k]["asked"]) for k in frozen["nested"]) + (("react_sonnet", 50),)
drawn = judges.draw_subsets(rows, sizes, frozen["seed"])
for k in frozen["nested"]:
    if drawn[k] != frozen["subsets"][k]["ids"]:
        raise SystemExit(f"level {k} differs from the frozen file: the population changed. Nothing written.")
ids = drawn["react_sonnet"]
assert set(ids) <= set(frozen["subsets"]["answer_sonnet"]["ids"]) and len(ids) == 50
doc = {"what": "Sonnet ReAct judge rows (D29): 50 of the shared 150, the next level of the frozen nested draw",
       "seed": frozen["seed"], "sets": list(sets), "from": sys.argv[3].replace("\\", "/"),
       "from_sha256": sha(frozen_path.read_text(encoding="utf-8")), "n": len(ids), "sha256": sha("\n".join(ids)), "ids": ids}
text = json.dumps(doc, indent=1, sort_keys=True) + "\n"
if out.exists():
    if out.read_text(encoding="utf-8") != text:
        raise SystemExit(f"{out} exists and a fresh draw differs from it. Nothing written.")
    print("unchanged", sha(text))
else:
    out.write_text(text, encoding="utf-8", newline="\n")
    out.with_name(out.name + ".sha256").write_text(f"{sha(text)}  {out.name}  drawn {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n", encoding="utf-8")
    print("written", sha(text), len(ids))
cnt = {}
for r in rows:
    if r["row_id"] in set(ids):
        cnt[r["cohort"]] = cnt.get(r["cohort"], 0) + 1
print(json.dumps(dict(sorted(cnt.items())), indent=0))
