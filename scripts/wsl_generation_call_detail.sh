#!/bin/bash
# Show one DEVS-Gen model call's metadata and the start and end of its output. Usage: <label> <task> <run> <call number>
W="$HOME/trust2027/gen/$1/$2/$3/devs_project/_analysis_logs/llm_calls"
f=$(ls "$W"/*/"$(printf %04d "$4")"_*_meta.json | head -1)
cat "$f" | cut -c1-1500; echo
o="${f%_meta.json}_output.txt.gz"
echo "--- output bytes: $(zcat "$o" | wc -c)"
zcat "$o" | head -c 600; echo; echo ...; zcat "$o" | tail -c 400
