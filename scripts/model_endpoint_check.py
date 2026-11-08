"""Read-only endpoint checks: no model is called. Reads keys from .env and never prints them.

Usage: python -I scripts/model_endpoint_check.py <.env> <out_json>
"""
import json
import sys
import urllib.error
import urllib.request

UA = {"User-Agent": "trust-artifact-check/0.1"}
KEEP = ("limit", "limit_remaining", "limit_reset", "usage", "usage_daily", "is_free_tier", "expires_at", "free_model_daily_requests", "rate_limit")
WANTED = ["gpt-oss:120b", "gpt-oss:120b-cloud", "gemma4:31b", "gemma4:31b-cloud"]


def load_env(path):
    env = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get(url, key):
    req = urllib.request.Request(url, headers={**UA, "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, {"error_body": e.read(300).decode("utf-8", "replace")}
    except (urllib.error.URLError, TimeoutError) as e:
        return None, {"error": str(e)}


def main(env_path, out_path):
    env = load_env(env_path)
    out = {}
    status, body = get("https://openrouter.ai/api/v1/key", env["OPENROUTER_API_KEY"])
    data = body.get("data", {}) if isinstance(body, dict) else {}
    # Only limit fields are kept: labels and account identifiers stay out of the record.
    out["openrouter_key"] = {"http": status, **{k: v for k, v in data.items() if k in KEEP}}
    if status != 200:
        out["openrouter_key"]["error"] = body
    status, body = get("https://openrouter.ai/api/v1/credits", env["OPENROUTER_API_KEY"])
    out["openrouter_credits"] = {"http": status, "data": body.get("data") if isinstance(body, dict) else None}
    status, body = get("https://ollama.com/api/tags", env["OLLAMA_API_KEY"])
    names = [m.get("name") for m in body.get("models", [])] if isinstance(body, dict) else []
    out["ollama_cloud_tags"] = {"http": status, "count": len(names), "wanted_present": {w: w in names for w in WANTED},
                                "gemma_gpt_names": [n for n in names if n and ("gemma" in n or "gpt-oss" in n)]}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
