#!/bin/bash
# Read-only scan of every built DEVS-Gen workflow program (WSL, /home/aashraf/trust2027/gen/<model>/<task>/<run>).
# Per program: a hash of its files, how many files name a test chapter title or test seed, and how many distinct
# test-only route-draw strings (6 decimals, not also in a dev run) occur anywhere in it.
# The pattern files are written by: python -X utf8 scripts/workflow_test_set.py patterns <dir>
# Usage (WSL): bash scripts/wsl_scan_workflow_programs.sh <dir with test_names.txt and test_draws.txt> > runs/workflow_test_v1/devs_gen_scan.txt
S="$1"
root=/home/aashraf/trust2027/gen
n=0
for d in $(find "$root" -mindepth 3 -maxdepth 3 -type d | sort); do
  n=$((n+1))
  h=$(cd "$d" && find . -type f -not -path '*/__pycache__/*' -not -name '*.pyc' -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16)
  names=$(grep -rIl -F -f "$S/test_names.txt" "$d" 2>/dev/null | wc -l)
  draws=$(grep -rIoh -F -f "$S/test_draws.txt" "$d" 2>/dev/null | sort -u | wc -l)
  echo "${d#$root/} $h files_naming_test=$names test_draw_strings=$draws"
done
echo "program_dirs=$n"
