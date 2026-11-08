#!/bin/bash
# Copy the workflow tasks into the pinned DEVS-Gen release (Category 2 additions) and check they load.
SRC="$1"
cd "$HOME/trust2027/devs_gen_code" || exit 1
for t in WorkflowLoan WorkflowPharmacy; do
  rm -rf "benchmark/$t" && mkdir -p "benchmark/$t" && cp "$SRC/$t/"* "benchmark/$t/"
done
.venvs/devs-gen/bin/python - <<'PY'
import yaml
for t in ("WorkflowLoan", "WorkflowPharmacy"):
    d = yaml.safe_load(open(f"benchmark/{t}/{t}.yaml"))
    print(t, list(d), {k: len(v) for k, v in d["requirements"].items()})
PY
cd src/generation && ../../.venvs/devs-gen/bin/python run_generation.py --list-benchmarks 2>&1 | tail -14
