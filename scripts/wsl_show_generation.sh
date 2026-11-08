#!/bin/bash
# Show a DEVS-Gen generation's log and outputs. Usage: wsl_show_generation.sh <label> <task> <run> [lines]
W="$HOME/trust2027/gen/$1/$2/$3"
echo "workspace: $W"
ls -la "$W" | head -20
find "$W" -name run.py | head -3
echo "--- log tail"
tail -c "${4:-3000}" "$W.log"
echo
echo "--- token lines"
grep -i -m8 "token\|total\|calls" "$W.log"
