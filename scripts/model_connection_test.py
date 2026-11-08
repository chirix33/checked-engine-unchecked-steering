"""One connection test per model setup: token counts, reasoning, output limits, speed and truncation.

Prompts are synthetic. No benchmark data is sent. Keys come from .env and are never written or printed.
Busy errors and retries are recorded separately from model failures.

Usage: python -I scripts/model_connection_test.py <.env> <out_json> <setup> [<setup> ...]
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request

UA = "trust-artifact-check/0.1"
LOCAL = "http://127.0.0.1:11535"
CLOUD = "https://ollama.com"
ROUTER = "https://openrouter.ai/api/v1"
START_CODE, END_CODE = "ALPHA-7Q2K-START", "OMEGA-9X4T-END"

SETUPS = {
    "gpt-oss-120b": {"kind": "ollama", "base": CLOUD, "model": "gpt-oss:120b", "key": "OLLAMA_API_KEY",
                     "think_default": "medium", "think_off": "low"},
    "qwen3.5-9b": {"kind": "ollama", "base": LOCAL, "model": "qwen3.5:9b", "key": None,
                   "think_default": True, "think_off": False},
    "gemma-31b-ollama": {"kind": "ollama", "base": CLOUD, "model": "gemma4:31b", "key": "OLLAMA_API_KEY",
                         "think_default": True, "think_off": False},
    "gemma-26b-openrouter-free": {"kind": "router", "base": ROUTER, "model": "google/gemma-4-26b-a4b-it:free",
                                  "key": "OPENROUTER_API_KEY"},
}


def load_env(path):
    env = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def post(url, body, key, timeout):
    headers = {"Content-Type": "application/json", "User-Agent": UA}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r), time.time() - started, None
    except urllib.error.HTTPError as e:
        return e.code, None, time.time() - started, e.read(500).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return None, None, time.time() - started, str(e)


def document(lines):
    rows = [f"Reference code at the start of this file: {START_CODE}"]
    rows += [f"Record {i:06d}: station {i % 37} logged {(i * 13) % 211} units in batch {(i * 7) % 509}." for i in range(lines)]
    rows.append(f"Reference code at the end of this file: {END_CODE}")
    return "\n".join(rows)


def call(setup, env, prompt, max_output, think=None, num_ctx=None, timeout=900):
    """Send one request, retrying busy errors at most twice. Returns a flat record."""
    key = env[setup["key"]] if setup["key"] else None
    if setup["kind"] == "ollama":
        url = setup["base"] + "/api/chat"
        options = {"num_predict": max_output, "temperature": 0}
        if num_ctx:
            options["num_ctx"] = num_ctx
        body = {"model": setup["model"], "stream": False, "options": options,
                "messages": [{"role": "user", "content": prompt}]}
        if think is not None:
            body["think"] = think
    else:
        url = setup["base"] + "/chat/completions"
        body = {"model": setup["model"], "max_tokens": max_output, "temperature": 0,
                "messages": [{"role": "user", "content": prompt}]}
        if think is not None:
            body["reasoning"] = {"enabled": bool(think)}
    busy = []
    for attempt in range(3):
        status, data, elapsed, error = post(url, body, key, timeout)
        if status in (429, 500, 502, 503, 504) or status is None:
            busy.append({"http": status, "seconds": round(elapsed, 2), "detail": (error or "")[:200]})
            if attempt < 2:
                time.sleep(20 * (attempt + 1))
                continue
        break
    record = {"http": status, "seconds": round(elapsed, 2), "busy_or_retry": busy}
    if data is None:
        record["error"] = (error or "")[:300]
        return record, ""
    if setup["kind"] == "ollama":
        message = data.get("message", {})
        text = message.get("content") or ""
        record.update({
            "prompt_tokens": data.get("prompt_eval_count"), "completion_tokens": data.get("eval_count"),
            "reasoning_chars": len(message.get("thinking") or ""), "finish": data.get("done_reason"),
            "server_total_seconds": round(data.get("total_duration", 0) / 1e9, 2),
            "server_gen_tokens_per_s": round(data["eval_count"] / (data["eval_duration"] / 1e9), 1)
            if data.get("eval_duration") and data.get("eval_count") else None,
        })
    else:
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage") or {}
        text = message.get("content") or ""
        record.update({
            "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "reasoning_chars": len(message.get("reasoning") or ""), "finish": choice.get("finish_reason"),
            "served_provider": data.get("provider"), "cost": usage.get("cost"),
        })
    if record.get("completion_tokens"):
        record["wall_tokens_per_s"] = round(record["completion_tokens"] / max(elapsed, 0.01), 1)
    record["text_head"] = text[:160]
    return record, text


def test_setup(name, env, num_ctx, long_lines):
    setup = SETUPS[name]
    ctx = num_ctx if setup["kind"] == "ollama" else None
    out = {"setup": name, "model": setup["model"], "base": setup["base"], "num_ctx": ctx}
    on, off = setup.get("think_default", True), setup.get("think_off", False)

    out["short_reasoning_on"], _ = call(setup, env, "Reply with exactly one word: READY", 512, think=on, num_ctx=ctx)
    out["short_reasoning_off"], _ = call(setup, env, "Reply with exactly one word: READY", 512, think=off, num_ctx=ctx)

    rec, _ = call(setup, env, "Count upward from 1 to 2000, one number per line.", 40, think=off, num_ctx=ctx)
    rec["limit_requested"] = 40
    rec["limit_respected"] = rec.get("completion_tokens") is not None and rec["completion_tokens"] <= 45
    out["output_limit"] = rec

    speed_prompt = "Write a detailed explanation, about 600 words long, of how a first-come first-served queue works."
    out["speed"], _ = call(setup, env, speed_prompt, 1200, think=off, num_ctx=ctx)

    ask = (f"\n\nThe file above has two reference codes, one on its first line and one on its last line. "
           f"Reply with only the two codes, in order, separated by a space.")
    rec, text = call(setup, env, document(long_lines) + ask, 400, think=off, num_ctx=ctx)
    rec["records_sent"] = long_lines
    rec["start_code_returned"] = START_CODE in text
    rec["end_code_returned"] = END_CODE in text
    out["long_document"] = rec

    # Control: a document larger than a small context. It shows whether truncation can be detected at all,
    # and whether this endpoint honours the requested context length.
    if setup["kind"] == "ollama":
        rec, text = call(setup, env, document(500) + ask, 200, think=off, num_ctx=2048)
        rec.update({"records_sent": 500, "num_ctx": 2048, "start_code_returned": START_CODE in text,
                    "end_code_returned": END_CODE in text})
        out["truncation_control"] = rec
    return out


def main(env_path, out_path, names):
    env = load_env(env_path)
    args = {"num_ctx": 65536, "long_lines": 2000}
    results = {"settings": args, "results": []}
    for arg in list(names):
        match = re.fullmatch(r"(num_ctx|long_lines)=(\d+)", arg)
        if match:
            args[match.group(1)] = int(match.group(2))
            names.remove(arg)
    for name in names:
        result = test_setup(name, env, args["num_ctx"], args["long_lines"])
        results["results"].append(result)
        print(json.dumps(result, indent=1), flush=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
