#!/bin/bash
# List a DEVS-Gen generation's model calls (phase, tokens, status) and the end of its build progress log.
W="$HOME/trust2027/gen/$1/$2/$3/devs_project/_analysis_logs"
zcat "$W/llm_calls/llm_calls_summary.jsonl.gz" 2>/dev/null | cut -c1-400 | tail -n "${4:-40}"
echo "--- build progress"
zcat "$W/build_progress.log.gz" 2>/dev/null | tail -n 30 | cut -c1-300
