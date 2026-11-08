#!/bin/bash
# Summarize how far a DEVS-Gen generation got: files written, model calls and tokens logged, last log lines.
# Usage: wsl_generation_progress.sh <label> <task> <run>
W="$HOME/trust2027/gen/$1/$2/$3"
echo "files:"; find "$W" -type f | sed "s|$W/||" | sort | head -60
echo "file count: $(find "$W" -type f | wc -l)"
echo "--- calls and tokens in logs"
grep -rhoE '"(prompt_tokens|completion_tokens|input_tokens|output_tokens)": ?[0-9]+' "$W" 2>/dev/null \
  | awk -F: '{gsub(/[" ]/,"",$1); s[$1]+=$2; n[$1]++} END {for (k in s) print k, n[k], s[k]}'
echo "--- last lines of each log"
for f in $(find "$W/logs" -type f 2>/dev/null | head -5); do echo "== $f"; tail -n 5 "$f" | cut -c1-300; done
