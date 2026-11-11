"""Replay every chapter in this folder and compare with its printed records."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

for f in sorted(os.listdir(HERE)):
    if "_chapter_" not in f:
        continue
    process = f.split("_")[0]
    ch = sim.parse_chapter(os.path.join(HERE, f))
    res = sim.simulate(process, ch)
    d = sim.compare(ch, res)
    n = len(ch["tasks"]) + len(ch["waits"]) + len(ch["decs"]) + len(ch["cases"])
    print(f"{f}: records={n} (tasks {len(ch['tasks'])}, waits {len(ch['waits'])}, "
          f"decisions {len(ch['decs'])}, cases {len(ch['cases'])}) "
          f"diffs={len(d)} -> {'EXACT' if not d else 'MISMATCH'}")
    for x in d[:10]:
        print("   ", x)
