"""Provider compatibility for DEVS-Gen on Claude 5.5 models (disclosed, applies to Claude cohorts only).

1. DEVS-Gen hardcodes sampling temperatures between 0.0 and 0.5. Claude 5.5 models reject any temperature or top-p
   setting. This hook makes LiteLLM drop those two parameters for Anthropic models, at the point where it maps
   parameters for Anthropic, so every generator call goes through it. The release's own code is not edited.
   It changes sampling for these models: they run at their default. That is the same treatment our OTF builds on
   Claude get, so both backends' Claude cohorts are sampled alike.

2. For structured output, LiteLLM forces a call to one JSON tool (`tool_choice` of type "tool"). Claude Sonnet 5.5
   rejects forced tool choice ("tool_choice: type tool and any are not supported for this model"). For models that
   reject it, the hook sends `tool_choice: auto` instead, with the same single tool, so the model may still answer
   in plain text; DEVS-Gen's own parsing then handles the reply. Haiku 5.5 accepts forced tool choice and is left
   unchanged, so the Haiku cohort built before this change is unaffected.

Other providers are untouched.
"""
REJECTS_FORCED_TOOL = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1")

try:
    from litellm.llms.anthropic.chat import transformation as _t

    _original = _t.AnthropicConfig.map_openai_params

    def _map_openai_params(self, non_default_params, optional_params, model, drop_params, *args, **kwargs):
        cleaned = {k: v for k, v in dict(non_default_params).items() if k not in ("temperature", "top_p")}
        out = _original(self, cleaned, optional_params, model, drop_params, *args, **kwargs)
        if isinstance(out, dict):
            out.pop("temperature", None)
            out.pop("top_p", None)
            tc = out.get("tool_choice")
            if any(m in str(model) for m in REJECTS_FORCED_TOOL) and isinstance(tc, dict) and tc.get("type") in ("tool", "any"):
                out["tool_choice"] = {"type": "auto"}
        return out

    _t.AnthropicConfig.map_openai_params = _map_openai_params
except Exception:  # LiteLLM missing or changed: leave everything as it is, so failures stay visible
    pass
