"""Run-clustered bootstrap: a disclosed sensitivity check on the frozen main analysis.

The frozen analysis (scripts/main_analysis.py, B = 2000, seed 20261111) resamples programs, then individual
questions. Questions on the same run share records and random draws: the 240 workflow test questions come from
16 runs. This script reruns the same analysis with one change: the second level resamples whole runs
(document + scope, e.g. "workflow_loan_test | Run 12") instead of single questions, and every question of a run
gets that run's weight. Programs are still resampled at the first level, as before.

Nothing else changes: same rows, same matching, same seed, same B. Point estimates are therefore identical to
the frozen ones by construction (the first weight row is all ones); only the intervals move. The script imports
the reviewed main_analysis.py and replaces its boot_weights function at run time; no project file is modified.

Usage (from the project root):
  python -X utf8 acmtrust_paper/sensitivity/run_clustered.py . acmtrust_paper/sensitivity/analysis_v1_runclustered
"""
import json
import sys
from pathlib import Path

import numpy as np

root = Path(sys.argv[1]).resolve()
out_dir = Path(sys.argv[2])
B = int(sys.argv[3]) if len(sys.argv) > 3 else 2000
sys.dont_write_bytecode = True
sys.path[:0] = [str(root), str(root / "scripts")]

import main_analysis as ma  # noqa: E402
import main_runner as mr  # noqa: E402

SETS = ("wf_test", "ml_test", "wf_policy")
CLUSTER = {}
for s in SETS:
    for q in mr.questions(root, s):
        CLUSTER[f"{s}|{q['id']}"] = f"{s}|{q['doc']}|{q['scope']}"

frozen_boot_weights = ma.boot_weights


def run_clustered_boot_weights(prog: np.ndarray, qid: np.ndarray, B: int, seed: int):
    """(B, n) row weights: programs resampled, then runs resampled; a question takes its run's weight."""
    rng = np.random.default_rng(seed)
    up, pi = np.unique(prog, return_inverse=True)
    runs = np.array([CLUSTER[q] for q in qid], dtype=object)
    ur, ri = np.unique(runs, return_inverse=True)
    wp = rng.multinomial(len(up), np.full(len(up), 1 / len(up)), size=B).astype(float)
    wr = rng.multinomial(len(ur), np.full(len(ur), 1 / len(ur)), size=B).astype(float)
    return wp[:, pi] * wr[:, ri]


missing = [k for k in CLUSTER if not k]
assert not missing
ma.boot_weights = run_clustered_boot_weights

idsets = {k: v["ids"] for k, v in json.loads((root / "manifests/judge_subsets_main_v1.json").read_text(encoding="utf-8"))["subsets"].items()}
idsets["react50"] = json.loads((root / "manifests/judge_subsets_main_v1_react_sonnet50.json").read_text(encoding="utf-8"))["ids"]
ma.main(root, out_dir, root / "runs/judges_main_v1", ["wf_test", "ml_test"], "wf_policy", B, idsets)
(out_dir / "README.txt").write_text(__doc__, encoding="utf-8")
