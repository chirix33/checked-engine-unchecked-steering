#!/bin/bash
# Generate one DEVS-Gen program with the release's own method. The API key arrives as an environment variable only.
# For Anthropic models, a startup hook drops sampling parameters those models reject (adapters/devs_gen_hooks).
# Usage: wsl_devs_gen_generate.sh <task> <litellm model id> <label> <run> <hooks dir in WSL> [max output tokens] [timeout s]
set -u
TASK="$1"; MODEL="$2"; LABEL="$3"; RUN="$4"; HOOKS="$5"; MAXTOK="${6:-16384}"; TOUT="${7:-1800}"
WS="$HOME/trust2027/gen/$LABEL/$TASK/$RUN"
if [ -n "$(find "$WS" -name run.py -print -quit 2>/dev/null)" ]; then echo "{\"skip\": \"$WS exists\"}"; exit 0; fi
rm -rf "$WS" "$WS.log"; mkdir -p "$WS"
cd "$HOME/trust2027/devs_gen_code/src/generation" || exit 1
START=$(date +%s)
PYTHONPATH="$HOOKS" ../../.venvs/devs-gen/bin/python run_generation.py --framework devs_gen --model "$MODEL" --benchmark "$TASK" \
  --workspace "$WS" --timeout "$TOUT" --max-output-tokens "$MAXTOK" > "$WS.log" 2>&1
CODE=$?
END=$(date +%s)
echo "{\"task\": \"$TASK\", \"model\": \"$MODEL\", \"label\": \"$LABEL\", \"run\": \"$RUN\", \"max_output_tokens\": $MAXTOK, \"timeout\": $TOUT, \"exit\": $CODE, \"seconds\": $((END-START)), \"has_run_py\": $( [ -n "$(find "$WS" -name run.py -print -quit)" ] && echo true || echo false )}"
