#!/bin/bash
# Copy the manufacturing and IT operations tasks into the pinned DEVS-Gen release (Category 2 additions) and check
# they load. Leaves every other benchmark folder, including WorkflowLoan and WorkflowPharmacy, untouched. No builds.
SRC="$1"
cd "$HOME/trust2027/devs_gen_code" || exit 1
for t in Manufacturing ITOperations; do
  rm -rf "benchmark/$t" && mkdir -p "benchmark/$t" && cp "$SRC/$t/"* "benchmark/$t/"
  sha256sum "benchmark/$t/"*
done
.venvs/devs-gen/bin/python - <<'PY'
import json, yaml
for t in ("Manufacturing", "ITOperations"):
    d = yaml.safe_load(open(f"benchmark/{t}/{t}.yaml"))
    c = json.load(open(f"benchmark/{t}/{t.lower()}_test_config.json"))
    print(t, list(d), {k: len(v) for k, v in d["requirements"].items()}, "config cases", len(c[0]["cases"]))
PY
cd src/generation && ../../.venvs/devs-gen/bin/python run_generation.py --list-benchmarks 2>&1 | tail -16
