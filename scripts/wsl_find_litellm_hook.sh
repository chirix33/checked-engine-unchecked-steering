#!/bin/bash
# Find where LiteLLM maps OpenAI-style parameters for Anthropic, in the pinned DEVS-Gen environment.
cd "$HOME/trust2027/devs_gen_code" || exit 1
SITE=$(.venvs/devs-gen/bin/python -c "import litellm, os; print(os.path.dirname(litellm.__file__))")
echo "litellm at $SITE"
grep -n "def map_openai_params\|class AnthropicConfig\|def get_supported_openai_params" "$SITE/llms/anthropic/chat/transformation.py" | head
grep -n "\"temperature\"\|'temperature'\|top_p" "$SITE/llms/anthropic/chat/transformation.py" | head -12
