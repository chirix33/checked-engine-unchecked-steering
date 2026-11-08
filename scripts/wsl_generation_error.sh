#!/bin/bash
# Print the provider's error message from a DEVS-Gen generation log, and the call parameters the generator sends.
W="$HOME/trust2027/gen/$1/$2/$3"
grep -o 'AnthropicException - {[^}]*}[^}]*}' "$W.log" | head -3
grep -rho 'AnthropicException - {[^}]*}[^}]*}' "$W" 2>/dev/null | sort | uniq -c | head -5
cd "$HOME/trust2027/devs_gen_code/src" || exit 0
grep -rn "temperature\|top_p\|completion(" generation/devs_tools --include=*.py | grep -v "^.*#" | head -12
