# Third-party material and notices

The code, question files, manifests and documentation written for this project are under the MIT licence (`LICENSE`,
holder "Anonymous Authors"). The material below is not ours and keeps its own licence.

## Data the documents and questions are built from

| Material | Where it appears here | Licence | Source |
|---|---|---|---|
| Business-process models, event logs and simulation parameters (loan and pharmacy workflows) | Not redistributed. Derived: `runs/workflow_docs/` (rendered process documents), the `validation/` scenario files that name its models, and the question files in `manifests/` | CC BY 4.0 | Zenodo record 10435849 (DOI 10.5281/zenodo.10435849), version 4.0, "Evaluation datasets and results for the paper *Enhancing Business Process Simulation Models with Extraneous Activity Delays*", D. Chapela-Campa and M. Dumas. <https://zenodo.org/records/10435849> |
| SupplyGraph (manufacturing production and orders) | Not redistributed. Derived: the manufacturing documents `runs/mlsys_docs/mfg_*` | LGPL-2.1 (the licence shown on the upstream repository; the repository states no separate licence for the dataset) | <https://github.com/CIOL-SUST/SupplyGraph>, Wasi et al. 2024. The derived documents are distributed under the terms of the LGPL-2.1 |
| Google cluster-usage trace 2011 (IT operations) | Not redistributed. Derived: the IT-operations documents `runs/mlsys_docs/itops_*` | CC BY 4.0 | <https://github.com/google/cluster-data>, Reiss, Wilkes and Hellerstein, "Google cluster-usage traces: format + schema", 2011. Trace bucket: `clusterdata-2011-2` |

Changes we made to this material: process models and trace excerpts were rendered into PDF process documents with
reading maps, parameters were varied for the policy set, and questions were written against them.
Hashes of the upstream files are in `manifests/hashes_p0.txt` and `manifests/mlsys_raw_hashes_v1.json`.

## Software

| Material | Where | Licence |
|---|---|---|
| DEVS-Gen (release `f7461b9f9d23`) | Not redistributed (clone it with `scripts/wsl_setup_devs_gen.sh`). The 22 generated programs in `programs/devs_gen/` may embed DEVS-Gen template code | Apache-2.0 |
| xDEVS (Python), used by the DEVS-Gen programs at run time | Not redistributed | see its repository |
| OTF-Tools implementation (pinned) | **Withheld during review** for anonymity; see `README.md` | not distributed here |
| Python and npm dependencies | Not redistributed; versions in `manifests/requirements_*.lock` and `acmtrust_paper/figures/src/history_gap/package-lock.json` | their own licences (the figure source takes Source Sans 3 from `@fontsource/source-sans-3`, SIL OFL 1.1) |

## Model outputs

Programs, question readings and judge verdicts in `runs/` and `programs/` were produced by Anthropic Claude models,
models served through Ollama (gpt-oss, Gemma, Qwen) and TypeSafe Jev. They are included as research evidence.
The providers' terms of use for outputs apply to them; check those terms before reusing the outputs for anything else.
No API keys or account details are in this artifact.
