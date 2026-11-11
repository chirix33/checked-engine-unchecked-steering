# Freeze record v1 (2026-11-10)

Frozen for the main run. The library, runner, scorer, judges, client, sandbox-filter source, question files, splits and program indexes are fixed by the sha256 values below. The machine-readable copy is `manifests/freeze_v1.json` (sha256 3f270c5a…). Decisions are D16–D28 in `manifests/design_decisions.md`.

**Any change after this point** is a post-freeze change. It must be logged as such in `run_manifest.md`, with its reason, and disclosed. No method, prompt, threshold or probe may change because of test results.

Programs: 118 (sha256 of the sorted names b24453c3dcb25153…).
The seccomp filter in WSL is `$HOME/trust2027/tools/seccomp_unix_only.bpf`, sha256 fc5e2ee5c92ecd8c5b9d99eabf975ee5667129972d7698ee2ab97f2d56af91e1.

| File | sha256 |
|---|---|
| `assurance/__init__.py` | ca3f3c4057c44362… |
| `assurance/answer.py` | fd4d450f57161b9e… |
| `assurance/backends.py` | d499fef08b2b4103… |
| `assurance/binding.py` | 2bab3e2111427db6… |
| `assurance/contract.py` | a6a4a014d5ec73b4… |
| `assurance/interpret.py` | 134ff1490efb13c9… |
| `assurance/mlsys.py` | dace20dfb28352a3… |
| `assurance/policy.py` | 619052b9444b7a70… |
| `assurance/probes.py` | 42a86e3199831f1c… |
| `assurance/registry.py` | fbdb7cf15748e659… |
| `assurance/request.py` | 49a090620d28847f… |
| `manifests/mlsys_questions_dev_v1.json` | f9c582628b0a0be7… |
| `manifests/mlsys_questions_test_v1.json` | d9f5ff821b18e739… |
| `manifests/mlsys_splits_v1.json` | 2a2e51407616ac64… |
| `manifests/pilot_excluded_v1.json` | fdcc1002ca4bea62… |
| `manifests/pilot_questions_v1.json` | 7f0d560dd92e8520… |
| `manifests/workflow_questions_policy_v1.json` | fc79f0db1c8e92c2… |
| `manifests/workflow_questions_test_v1.json` | fe754f44bb8b586b… |
| `manifests/workflow_splits_v1.json` | be2c930da705c928… |
| `runs/coding_agent/index.jsonl` | 9ff996ce8a6b2566… |
| `runs/devs_gen/generation_index.jsonl` | bbb97df91a34a599… |
| `scripts/b0_build_test.py` | a6fc7458fb531e19… |
| `scripts/check_builder_isolation.py` | 6c8dd525151f073e… |
| `scripts/coding_agent_build.py` | 24d4acac1ec97a05… |
| `scripts/judges.py` | ab971e9df2c1728a… |
| `scripts/main_runner.py` | 1acb2c98aaa4bda8… |
| `scripts/main_shard.py` | 1dc48282dcfe3cd9… |
| `scripts/main_summary.py` | 7a86d88653e5d315… |
| `scripts/make_seccomp_filter.py` | 4271697260b889f5… |
| `scripts/pilot_runner.py` | c7a4387ce278e702… |
