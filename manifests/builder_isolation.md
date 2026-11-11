# What builders must not see (adopted 2026-11-09; revised after review the same day)

This applies to every **build** of a program that will answer benchmark questions: DEVS-Gen generation, the plain coding agent, and any further OTF build. A builder needs only its own inputs:
- DEVS-Gen: its task folder `~/trust2027/devs_gen_code/benchmark/<Task>/`, plus the DEVS-Gen code and venv;
- coding agent: `adapters/generic_tasks/<Task>/`, copied into its workspace;
- OTF: the one dev document PDF it is built on, copied.

Everything else here is evaluation-side: gold, hidden bindings, test and variant documents and their seeds, reference implementations, other programs, and transcripts. AGENTS.md: "Reference implementations, hidden intervention bindings, labels, and grading adapters are evaluation-only."

## Rule

Hide everything, then give back only the inputs. Operating-system isolation is required. Tool deny-lists inside an agent are not enough: the same folders are reachable under other spellings (8.3 names, `\\localhost\c$`, `\\?\`, `\\wsl.localhost`), and the check below treats a deny-list setup as visible.

**WSL (DEVS-Gen, or a coding agent run in WSL).** This bubblewrap form passed the check with 0 findings:

```bash
bwrap --ro-bind / / --tmpfs /mnt --tmpfs /home \
  --ro-bind <DEVS-Gen code and venv> <same> --ro-bind <task folder> <same> --bind <output folder> <same> \
  --dev /dev --proc /proc --tmpfs /tmp --unshare-net --die-with-parent \
  --clearenv --setenv PATH /usr/bin:/bin --setenv HOME "$HOME" <builder command>
```

- `--tmpfs /mnt` hides every Windows drive.
- `--tmpfs /home` hides `~/trust2027/gen` and the other built programs, `~/trust2027/screen`, and credentials such as `~/.ssh`, `~/.config/gh` and `~/.git-credentials`.
- `--unshare-net` removes the network, and with it GitHub, where the identified repository lives.
- `--clearenv` drops API keys and tokens from the environment.
- **A builder that needs a model API** (DEVS-Gen generation calls a model) cannot use `--unshare-net`. It must then reach only the model endpoint, with only that key set: for example through a proxy that allows that one host. Record what was allowed. The check reports the network as a finding in that case; keep the finding, with the reason, in the build log.

**Windows (a coding agent run on Windows).** Use a separate local user, a container or a VM that has no access to the project, the MLSys folder, the Claude folders or WSL. Copy in the inputs, and give the agent no git or gh credentials.

## Paths that must be hidden or absent

Project root: `C:\Users\aashraf\Desktop\Work\2026\ACM Trust 2027`. In WSL: `/mnt/c/Users/aashraf/Desktop/Work/2026/ACM Trust 2027`.

| path (relative to the project root unless absolute) | why |
|---|---|
| `manifests/` | every question file with gold and bindings (dev, test and policy variants, all four domains), splits, checker and soundness reports, pilot results |
| `runs/` | test and variant documents and their `document_meta.json` (which list the seeds), maps, pilot outputs, registries, other builds |
| `validation/` | blind-check keys, answers and agents' simulators, fuzz scenarios, soundness scripts |
| `reference_engine/`, `checker/`, `spec/` | the workflow reference engine, the independent checker, and hand-worked expected outputs |
| `scripts/` | question generators, gold code (`mlsys_gold.py`), reference wrappers |
| `baseline/` | the pinned OTF-Tools clone, which holds the manufacturing and IT reference simulators |
| `assurance/` | the library's probes; a builder that sees them could fit to the checks |
| `adapters/` | other tasks' specs and hooks (give a builder only its own task, as a copy) |
| `data/`, `redesign/`, `papers/`, `meeting/`, `.tools/` | raw data, OTF R1 code, papers, meeting notes, environments |
| `.git/` | history, which contains every committed question file with gold |
| `AGENTS.md`, `RESEARCH_DIRECTION.md`, `.env` | the research design, and API keys |
| `C:\Users\aashraf\Desktop\Work\2026\MLSystem 2027` | MLSys raw records and the MLSys reference code |
| `C:\Users\aashraf\.claude\` | Claude transcripts and memory for this project |
| `C:\Users\aashraf\AppData\Local\Temp\claude\` and `C:\Users\aashraf\AppData\Local\Claude-Data\` | session scratchpads, which hold blind-check work and regenerated gold, and session notes |
| WSL `~/trust2027/` other than the bound task, code and venv | built programs (`gen/`), screens, recheck files |
| `\\wsl.localhost\…` and `\\wsl$\…` (from Windows) | the same WSL files |
| network and credentials | GitHub (the identified repository), and `~/.ssh`, gh and git credentials |

## Check

`scripts/check_builder_isolation.py` uses only the standard library. It never reads file contents, and it names credential variables without printing their values.

1. **Positive control, outside the sandbox, first.** Run `python3 check_builder_isolation.py --wsl --expect-visible` in WSL, or `python check_builder_isolation.py --windows --expect-visible` on Windows. It must report every project path visible (35 of 35). Otherwise the list or the root is wrong, and a later pass means nothing.
2. **Inside the sandbox, just before the build.** Copy the script into the workspace, since the project's `scripts/` folder is hidden. Run it with the builder's interpreter and isolation: `python3 check_builder_isolation.py --wsl --workspace <workspace>`. It must exit 0, apart from a documented model-API network finding. It reports:
   - any listed path that exists and is not empty;
   - a permission error, which counts as visible;
   - known files, probed by name;
   - other Windows spellings of the root;
   - reachable host mounts (drvfs or 9p);
   - interop with reachable Windows programs;
   - the network;
   - credential variables;
   - links or mounts that lead out of the workspace.
3. Keep both outputs with the build log.

Tested 2026-11-09:

| case | result |
|---|---|
| WSL, positive control | 35 of 35 |
| WSL, no isolation | 44 findings |
| WSL, the bubblewrap form above | 0 findings |
| WSL, the same plus a symlink to `/mnt/c` in the workspace | caught |
| WSL, without `--tmpfs /mnt` | 40 findings |
| Windows, positive control | 35 of 35 |
| Windows, no isolation | 153 findings |
| A mistyped `--root` | fails the positive control |

**After every build**, rerun the provenance checks:
- `python -X utf8 scripts/workflow_test_set.py patterns runs/workflow_test_v1/scan_patterns`
- `scripts/wsl_scan_workflow_programs.sh`, to `runs/workflow_test_v1/devs_gen_scan.txt`
- `python -X utf8 scripts/workflow_test_set.py splits manifests/workflow_splits_v1.json`

For a coding-agent build, also grep its output folder with the same pattern files (`grep -rIl -F -f test_names.txt`, and `-f test_draws.txt`). The patterns cover the test and the policy-variant documents: titles Run 05–16, their seeds, and their route draws that no dev run has.
