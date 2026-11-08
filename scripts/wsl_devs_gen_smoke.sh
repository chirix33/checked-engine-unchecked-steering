#!/bin/bash
# Point every hardcoded bubblewrap path at the unpacked package (Category 1), then reproduce published scores.
# Starts from the pinned file each time, so the replacement cannot apply twice.
set -u
HOME_DIR="$HOME/trust2027"
cd "$HOME_DIR/devs_gen_code" || exit 1
BW="$HOME_DIR/tools/usr/bin/bwrap"
git checkout --quiet -- src/devs_eval
grep -rl '/usr/bin/bwrap' src/devs_eval | xargs -r sed -i "s#/usr/bin/bwrap#$BW#g"
git diff > "$HOME_DIR/category1.diff"
git diff --stat | tail -2
grep -n 'bwrap' "$HOME_DIR/category1.diff" | cut -c1-110
for spec in "gpt ABP" "gpt barbershop" "qwen StoreCashier" "glm oft"; do
  set -- $spec
  rm -f "$HOME_DIR/recheck_$1_$2.csv"
  .venvs/devs-gen/bin/python src/recheck_results.py --method devs_gen --model "$1" --scenario "$2" --limit 3 \
    --output "$HOME_DIR/recheck_$1_$2.csv" 2>&1 | tail -1 | cut -c1-140
  cut -d, -f4-14 "$HOME_DIR/recheck_$1_$2.csv" | cut -c1-150
done
