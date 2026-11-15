# data/: pointers to the public sources

No source data is stored in this folder. The documents the programs read are shipped as derived files in
`runs/workflow_docs/` and `runs/mlsys_docs/`. You need the raw data only to regenerate those documents, to rerun the
reference simulators, or to recompute gold.

## Business workflows (loan, pharmacy)

- Source: Zenodo record 10435849, version 4.0, licence CC BY 4.0. <https://zenodo.org/records/10435849> (DOI 10.5281/zenodo.10435849).
- File used: `inputs.zip` (`outputs.zip` is not used).
  - MD5 `4328addf237dd05dc631e5e7b341552b` (matches the Zenodo record).
  - SHA-256 `42d5764b1cf69c19560fbb95d794eddfbd2412567251043cf00a5b7a5fa84ad9` (`manifests/hashes_p0.txt`).
- Place it as `data/zenodo_10435849/download/inputs.zip` and extract it to `data/zenodo_10435849/inputs/`. The scripts read
  `data/zenodo_10435849/inputs/synthetic/<model>.bpmn` and `<model>.json`.
- `manifests/workflow_model_inventory.json` lists the models used and `manifests/workflow_test_set.md` explains how documents and
  questions were drawn. `scripts/workflow_test_set.py docs` regenerates the process documents byte for byte
  (hashes in `manifests/workflow_questions_test_v1.sha256` and `manifests/workflow_questions_policy_v1.sha256`).

## Manufacturing and IT operations

- Manufacturing: SupplyGraph, <https://github.com/CIOL-SUST/SupplyGraph> (LGPL-2.1).
- IT operations: Google cluster-usage trace 2011, bucket `clusterdata-2011-2` (`storage.googleapis.com/clusterdata-2011-2`), documentation at <https://github.com/google/cluster-data> (CC BY 4.0).
- Put both under one folder and point the environment variable `MLSYS_RAW` at it:

  ```
  $MLSYS_RAW/supplygraph/Raw Dataset/Homogenoeus/...
  $MLSYS_RAW/google-trace-2011/...
  ```

- `manifests/mlsys_raw_hashes_v1.json` lists the sha256 of all 79 files that were read. The trace folder also carries the publisher's `SHA256SUM`.
- `scripts/mlsys_gold.py` (evaluation-only gold) is the only script that reads these raw files, and it also needs the withheld OTF-Tools
  reference simulators (see `README.md`, section 2).

## Shipped derived documents and their hashes

| Documents | Folder | Hash list |
|---|---|---|
| manufacturing and IT operations (12 PDFs with reading maps) | `runs/mlsys_docs/` | `manifests/mlsys_docs_v1.sha256` |
| workflow documents (loan, pharmacy; test and policy sets) | `runs/workflow_docs/` | `manifests/workflow_questions_test_v1.sha256`, `manifests/workflow_questions_policy_v1.sha256` |
| development documents the builders read | `runs/build_test_v1/docs/` | `pdf_sha256` in each `builds_*.jsonl` record |
