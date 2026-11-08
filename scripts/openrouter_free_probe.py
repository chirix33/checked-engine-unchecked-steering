"""Measure availability of the free OpenRouter Gemma route with spaced single calls.

Busy errors are recorded as availability data, not model failures. On the first success, runs the full
connection test once. Never records keys.

Usage: python -X utf8 scripts/openrouter_free_probe.py <.env> <out_json> <samples> <seconds_between>
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model_connection_test import SETUPS, load_env, post, test_setup  # noqa: E402

NAME = "gemma-26b-openrouter-free"


def main(env_path, out_path, samples, gap):
    env = load_env(env_path)
    setup = SETUPS[NAME]
    body = {"model": setup["model"], "max_tokens": 16, "temperature": 0,
            "messages": [{"role": "user", "content": "Reply with exactly one word: READY"}]}
    log = {"setup": NAME, "seconds_between": int(gap), "samples": [], "full_test": None}
    for i in range(int(samples)):
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        status, data, elapsed, error = post(setup["base"] + "/chat/completions", body, env[setup["key"]], 120)
        sample = {"utc": started, "http": status, "seconds": round(elapsed, 2)}
        if data is not None:
            sample.update({"served_provider": data.get("provider"), "usage": data.get("usage")})
        else:
            sample["detail"] = (error or "")[:240]
        log["samples"].append(sample)
        if status == 200 and log["full_test"] is None:
            log["full_test"] = test_setup(NAME, env, None, 3300)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=1)
        print(started, status, flush=True)
        if i + 1 < int(samples):
            time.sleep(int(gap))
    ok = sum(s["http"] == 200 for s in log["samples"])
    print(f"available in {ok} of {len(log['samples'])} samples", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:5])
