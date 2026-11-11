"""Run one shard of `main_runner.run_programs`: programs sorted by name, those with index % N == I.

Shards share nothing but read-only inputs; each program writes its own row and registry files, so shards can run
in parallel. Usage:
  python -X utf8 scripts/main_shard.py <root> <set> <I> <N> [--no-native] [--registry-from SET] [--sources ...]
"""
import argparse
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent)]
import main_runner as mr                                                        # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("root")
ap.add_argument("set", choices=sorted(mr.SETS))
ap.add_argument("i", type=int)
ap.add_argument("n", type=int)
ap.add_argument("--no-native", action="store_true")
ap.add_argument("--registry-from")
ap.add_argument("--sources", default="interpreted,oracle")
a = ap.parse_args()
root = Path(a.root).resolve()
names = sorted(p["name"] for p in mr.programs_list(root))
mine = [nm for k, nm in enumerate(names) if k % a.n == a.i]
print(f"shard {a.i}/{a.n}: {len(mine)} programs", flush=True)
for nm in mine:
    mr.run_programs(root, a.set, nm, native=not a.no_native, registry_from=a.registry_from,
                    sources=tuple(a.sources.split(",")))
print(f"shard {a.i}/{a.n} done", flush=True)
