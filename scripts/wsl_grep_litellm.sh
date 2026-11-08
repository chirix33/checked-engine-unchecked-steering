#!/bin/bash
# Search the DEVS-Gen environment's LiteLLM Anthropic transformation. Usage: wsl_grep_litellm.sh <regex>
F="$HOME/trust2027/devs_gen_code/.venvs/devs-gen/lib/python3.10/site-packages/litellm/llms/anthropic/chat/transformation.py"
grep -n -E "$1" "$F" | cut -c1-200 | head -40
