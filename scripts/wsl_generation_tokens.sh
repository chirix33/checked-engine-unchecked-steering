#!/bin/bash
# Print one JSON line per DEVS-Gen generation workspace: model calls and token usage from the release's own call log.
for d in "$HOME"/trust2027/gen/*/*/run_*; do
  [ -d "$d" ] || continue
  f="$d/devs_project/_analysis_logs/llm_calls/llm_calls_summary.jsonl.gz"
  if [ -f "$f" ]; then
    zcat "$f" | python3 -c '
import sys, json
calls = p = c = big = 0
for line in sys.stdin:
    try: r = json.loads(line)
    except ValueError: continue
    u = r.get("token_usage") or {}
    calls += 1; pt = u.get("prompt_tokens") or 0; p += pt; c += u.get("completion_tokens") or 0
    big += pt > 100000
print(json.dumps({"workspace": sys.argv[1], "calls": calls, "prompt_tokens": p, "completion_tokens": c, "calls_over_100k": big}))' "$d"
  else
    echo "{\"workspace\": \"$d\", \"calls\": null}"
  fi
done
