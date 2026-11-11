"""Write the freeze record: sha256 of every frozen file (library, runner, scorer, judges, client, sandbox filter
source, question files, splits) and of the program list, so the main run can show it used exactly these.

Usage: python -X utf8 scripts/make_freeze_record.py <root> <out_json>
"""
import hashlib
import json
import sys
import time
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root), str(root / "scripts")]
sys.dont_write_bytecode = True

FILES = sorted(set(
    [f"assurance/{p.name}" for p in (root / "assurance").glob("*.py")] + [
        "scripts/main_runner.py", "scripts/main_shard.py", "scripts/main_summary.py", "scripts/judges.py",
        "scripts/b0_build_test.py", "scripts/pilot_runner.py", "scripts/make_seccomp_filter.py",
        "scripts/coding_agent_build.py", "scripts/check_builder_isolation.py",
        "manifests/pilot_questions_v1.json", "manifests/pilot_excluded_v1.json",
        "manifests/workflow_questions_test_v1.json", "manifests/workflow_questions_policy_v1.json",
        "manifests/mlsys_questions_dev_v1.json", "manifests/mlsys_questions_test_v1.json",
        "manifests/workflow_splits_v1.json", "manifests/mlsys_splits_v1.json",
        "runs/coding_agent/index.jsonl", "runs/devs_gen/generation_index.jsonl",
    ]))


def sha(p):
    return hashlib.sha256((root / p).read_bytes()).hexdigest()


import main_runner as mr                                                          # noqa: E402
progs = sorted(p["name"] for p in mr.programs_list(root))
record = {
    "frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "files": {p: sha(p) for p in FILES if (root / p).exists()},
    "missing": [p for p in FILES if not (root / p).exists()],
    "programs": {"count": len(progs), "sha256_of_sorted_names": hashlib.sha256("\n".join(progs).encode()).hexdigest(),
                 "names": progs},
    "seccomp_filter_wsl": "$HOME/trust2027/tools/seccomp_unix_only.bpf",
}
Path(sys.argv[2]).write_text(json.dumps(record, indent=1), encoding="utf-8")
print(f"{len(record['files'])} files, {len(progs)} programs, missing {record['missing']}")
