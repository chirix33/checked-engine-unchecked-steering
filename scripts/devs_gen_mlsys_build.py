"""DEVS-Gen builds for the Manufacturing and ITOperations tasks (D27: Claude Haiku 5.5 and Sonnet 5.5, 3 each).

For every build, in order:
1. isolation check inside the exact build sandbox (`scripts/wsl_devs_gen_isolated_generate.sh check`): the builder
   isolation script must report no finding except the one documented model-API credential, the proxy must refuse
   github.com and raw.githubusercontent.com and allow only api.anthropic.com, direct network must be blocked, and
   /home must show only the DEVS-Gen code (with this task alone under benchmark/), the Python home, the workspace and
   the stage folder. If anything else shows, the build is not run.
2. the build itself, with the release's command and the workflow settings (--max-output-tokens 64000, timeout 3600,
   the provider hook); one line appended to runs/devs_gen/generation_index.jsonl with the same fields as before;
3. the same isolation check again, recorded (only lines carrying the run's fresh nonce are trusted);
4. tokens from the release's own call log, priced at the runner's list prices (scripts/b0_build_test.py), with the
   proxy's connection and byte counts beside them; a missing log with proxy traffic is charged conservatively;
   a search of the build's files for the key (result: a count only);
5. a scan of the program folder for test chapter or window names (the folder name must be plain, or it is refused);
6. the history check (replay) through `assurance.mlsys.DEVSDomain` on every dev chapter or window, only if the
   library's program sandbox passes the isolation check itself; otherwise replay is deferred and recorded, and
   `devs_gen_mlsys_build.py replay` runs it later (no model call).
Failed builds are kept; nothing is selected by result. Spending stops before a build that would pass the cap; the
loop also stops on a failed post-check, the key found in files, or a failure before any model call.
The API key is read from .env by code and passed to WSL in the environment only; it is never printed or logged.

A positive control (`check_builder_isolation.py --expect-visible` outside any sandbox) runs once first.

Usage: python -X utf8 scripts/devs_gen_mlsys_build.py [cap_usd=8]
       python -X utf8 scripts/devs_gen_mlsys_build.py replay
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
WSL_PROJ = "/mnt/c/Users/aashraf/Desktop/Work/2026/ACM Trust 2027"
SCRIPT = f"{WSL_PROJ}/scripts/wsl_devs_gen_isolated_generate.sh"
INDEX = ROOT / "runs" / "devs_gen" / "generation_index.jsonl"
LOG = ROOT / "runs" / "devs_gen" / "mlsys_build_log.jsonl"
REPLAY = ROOT / "runs" / "devs_gen" / "mlsys_replay_v1.jsonl"
MODELS = {"haiku": "anthropic/claude-haiku-5-5", "sonnet": "anthropic/claude-sonnet-5-5"}
SETUP = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}
TASKS = {"Manufacturing": "manufacturing", "ITOperations": "it_ops"}
MAXTOK, TOUT = 64000, 3600
# the model key the build needs, and TIKTOKEN_CACHE_DIR (a folder path, not a secret; the check flags any name with
# TOKEN in it), which points tiktoken at litellm's bundled encodings
ALLOWED_FINDINGS = {"CREDENTIAL VARIABLE ANTHROPIC_API_KEY", "CREDENTIAL VARIABLE TIKTOKEN_CACHE_DIR"}
DEFAULT_COST = {"haiku": 0.3, "sonnet": 1.6}


def env_with_key():
    import b0_build_test as bt
    key = bt.load_env(ROOT / ".env").get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("no ANTHROPIC_API_KEY in .env")
    return {**os.environ, "ANTHROPIC_API_KEY": key, "WSLENV": "ANTHROPIC_API_KEY/u", "MSYS_NO_PATHCONV": "1"}


def wsl(cmd, env=None, timeout=600):
    try:
        p = subprocess.run(["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c", cmd], capture_output=True, text=True,
                           timeout=timeout, env=env or {**os.environ, "MSYS_NO_PATHCONV": "1"})
    except subprocess.TimeoutExpired as e:
        return None, (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), "timeout"
    return p.returncode, p.stdout, p.stderr


def judge_check(out: str, label: str, task: str, run: str, phase: str = "pre") -> tuple[bool, dict]:
    """Read the launcher's check output. Only lines that start with the run's fresh nonce (the launcher's first output
    line) come from the harness; anything a workspace name could print lacks it. Any parse problem fails the check."""
    try:
        lines = out.splitlines()
        if not lines or not lines[0].startswith("NONCE ") or len(lines[0].split()) != 2:
            return False, {"error": "no nonce line"}
        n = lines[0].split()[1]
        mine = [l[len(n) + 1:] for l in lines[1:] if l.startswith(n + " ")]
        summ = [l for l in mine if l.startswith("CHECK_SUMMARY ")]
        exits = [l for l in mine if l.startswith("CHECK_EXIT ")]
        if len(summ) != 1 or len(exits) != 1:
            return False, {"error": f"{len(summ)} summary and {len(exits)} exit lines"}
        findings = json.loads(summ[0][len("CHECK_SUMMARY "):])["findings"]
        probes = {}
        for l in mine:
            if l.startswith("PROXY_PROBE "):
                host = l.split()[1]
                if host in probes:
                    return False, {"error": f"two probe lines for {host}"}
                probes[host] = " ".join(l.split()[2:])
        direct = next((l for l in mine if l.startswith("DIRECT_NET ")), "")
        pstore = json.loads(next(l for l in mine if l.startswith("PERSISTENT_STORAGE "))[len("PERSISTENT_STORAGE "):])
        tree = [json.loads(l[len("HOME "):]) for l in mine if l.startswith("HOME ")]
    except (ValueError, KeyError, StopIteration, TypeError) as e:
        return False, {"error": f"unparsable check output: {type(e).__name__}"}
    home = "/home/aashraf"
    code = f"{home}/trust2027/devs_gen_code"
    ok_prefix = (f"{code}/benchmark/{task}", f"{code}/.venvs", f"{code}/src", f"{home}/.local/share/uv/python",
                 f"{home}/ws", f"{home}/trust2027/stage/{label}-{task}-{run}")
    parents = {home, f"{home}/trust2027", code, f"{code}/benchmark", f"{home}/.local", f"{home}/.local/share",
               f"{home}/.local/share/uv", f"{home}/trust2027/stage", f"{code}/generated", f"{code}/results"}
    # files of the release itself (LICENSE, README, pyproject, build/, envs/, figures/) are code, not evaluation data
    release = (f"{code}/LICENSE", f"{code}/README.md", f"{code}/pyproject.toml", f"{code}/build", f"{code}/envs",
               f"{code}/figures", f"{code}/.git", f"{code}/.gitignore", f"{code}/.python-version", f"{code}/uv.lock",
               f"{code}/.env.example")   # the release's template, no secrets
    # whole path components only: {home}/ws must not also admit {home}/ws2, nor .git admit .git-credentials
    def under(p, roots):
        return any(p == r or p.startswith(r + "/") for r in roots)
    unexpected = [p for p in tree if p not in parents and not under(p, ok_prefix) and not under(p, release)]
    # src/ is release code and is not listed, except DEVS-Gen's own log folder: it must start empty for each build (so
    # earlier builds' logs are not visible); after the build it holds this build's own agent logs, which are recorded
    if phase == "pre" and pstore:
        unexpected.append(f"persistent_storage entries: {len(pstore)}")
    ok = (set(findings) <= ALLOWED_FINDINGS and probes.get("github.com", "").find("403") >= 0
          and probes.get("raw.githubusercontent.com", "").find("403") >= 0 and probes.get("api.anthropic.com", "").find("200") >= 0
          and direct.startswith("DIRECT_NET blocked") and not unexpected)
    return ok, {"findings": findings, "probes": probes, "direct": direct, "home_unexpected": unexpected[:20],
                "home_entries": len(tree), "persistent_storage": pstore[:50]}


def tokens(label, task, run):
    """Tokens from the release's call log. The log is in the builder's workspace, so it is read with care: every path
    component must be a real folder (no link), the file a regular file below 64 MB, opened without following links
    and without blocking (a FIFO in its place cannot hang the read). It is still a record the builder could edit;
    the proxy's connection and byte counts are kept beside it as a check."""
    ws = f"/home/aashraf/trust2027/gen/{label}/{task}/{run}"
    py = ("import sys,json,gzip,os,stat\nws=sys.argv[1]\nparts=['devs_project','_analysis_logs','llm_calls']\n"
          "d=ws\nfor q in parts:\n  d=os.path.join(d,q)\n  st=os.lstat(d) if os.path.lexists(d) else None\n"
          "  if st is None or not stat.S_ISDIR(st.st_mode):\n    print(json.dumps({'calls':None,'why':'no log folder'})); sys.exit()\n"
          "f=os.path.join(d,'llm_calls_summary.jsonl.gz')\n"
          "try:\n  fd=os.open(f,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)\nexcept OSError:\n  print(json.dumps({'calls':None,'why':'no log file'})); sys.exit()\n"
          "st=os.fstat(fd)\nif not stat.S_ISREG(st.st_mode) or st.st_size>64*2**20:\n  print(json.dumps({'calls':None,'why':'not a regular file'})); sys.exit()\n"
          "def num(x):\n  return x if isinstance(x,int) and x>0 else 0\n"
          "calls=p=c=0; seen=0\ntry:\n  g=gzip.open(os.fdopen(fd,'rb'),'rb')\n  while True:\n"
          "    line=g.readline(2**20)\n    if not line: break\n    seen+=len(line)\n"
          "    if seen>512*2**20:\n      print(json.dumps({'calls':None,'why':'log over 512 MB decompressed'})); sys.exit()\n"
          "    try: r=json.loads(line)\n    except ValueError: continue\n"
          "    if not isinstance(r,dict): continue\n"
          "    u=r.get('token_usage') or {}\n    if not isinstance(u,dict): u={}\n"
          "    calls+=1; p+=num(u.get('prompt_tokens')); c+=num(u.get('completion_tokens'))\n"
          "except (OSError, EOFError) as e:\n  print(json.dumps({'calls':None,'why':type(e).__name__})); sys.exit()\n"
          "print(json.dumps({'calls':calls,'prompt_tokens':p,'completion_tokens':c}))\n")
    rc, out, _ = wsl(f"python3 -c \"$PYCODE\" {shlex.quote(ws)}", timeout=120,
                     env={**os.environ, "MSYS_NO_PATHCONV": "1", "PYCODE": py, "WSLENV": "PYCODE/u"})
    try:
        return json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError, AttributeError):
        return {"calls": None, "why": "unreadable"}


def price(label, t):
    import b0_build_test as bt
    s = next(v for k, v in bt.SETUPS.items() if k == SETUP[label]) if hasattr(bt, "SETUPS") else None
    pin, pout = (s or {}).get("price_per_million", (2.0, 10.0) if label == "sonnet" else (0.10, 0.50))
    if not t.get("calls"):
        return None
    return round((t["prompt_tokens"] * pin + t["completion_tokens"] * pout) / 1e6, 4)


SAFE_PATH = re.compile(r"[A-Za-z0-9_./-]+")


def program_dir(label, task, run):
    """The folder of the build's run.py (a regular file, links not followed). The folder name is chosen by the builder,
    and later goes into shell commands (here and in the library's sandbox), so only plain names under this build's
    workspace are accepted; anything else is refused and recorded, never used."""
    ws = f"/home/aashraf/trust2027/gen/{label}/{task}/{run}"
    rc, out, _ = wsl(f"find {shlex.quote(ws)} -name run.py -type f -printf '%h\\0' | sort -z | head -z -n 1 | tr -d '\\0'")
    d = (out or "").strip("\n")
    if not d:
        return None, None
    if not SAFE_PATH.fullmatch(d) or "/../" in d + "/" or not (d == ws or d.startswith(ws + "/")):
        return None, f"refused program folder name: {d[:200]!r}"
    return d, None


def scan(pdir, test_names):
    pat = "\\|".join(test_names)
    rc, out, _ = wsl(f"grep -rIl --exclude-dir=_analysis_logs -e {shlex.quote(pat)} {shlex.quote(pdir)} 2>/dev/null | head -5")
    return [l for l in (out or "").splitlines() if l.strip()]


def library_sandbox_hardened():
    """Replay runs the built program through the library (`assurance.mlsys.DEVSDomain`). Only do that once the
    library's program sandbox is the hardened one; the earlier `--ro-bind / /` form is escapable."""
    import inspect
    from assurance import backends, mlsys as M
    src_dom = inspect.getsource(M.DEVSDomain)
    src_box = inspect.getsource(backends.sandbox_command) if hasattr(backends, "sandbox_command") else ""
    # (the docstrings quote the old form, so source text is not searched for it; the test below decides)
    if not ("sandbox_command(" in src_dom and "--unshare-all" in src_box):
        return False, "library DEVSDomain does not use sandbox_command"
    # and by test: the isolation check, run inside the library's own program sandbox, must report nothing
    d = "/home/aashraf/trust2027/sandbox_probe_lib"
    venv = "$HOME/trust2027/devs_gen_code/.venvs/devs-gen"
    cmd = (f"mkdir -p {d} && cp '{WSL_PROJ}/scripts/check_builder_isolation.py' {d}/ && cd {d} && "
           + backends.sandbox_command(d, f"{venv}/bin/python {d}/check_builder_isolation.py --wsl"))
    rc, out, err = wsl(cmd, timeout=300)
    last = [l for l in (out or "").splitlines() if l.strip()]
    if rc != 0 or not last or not last[-1].endswith(", 0 findings"):
        return False, "isolation check inside the library sandbox: " + " | ".join(last[-4:])[:400]
    return True, last[-1]


def replay(label, task, run, pdir, splits, navs):
    from assurance import mlsys as M
    dom = TASKS[task]
    rows = []
    for title, v in splits[dom].items():
        if v["split"] != "dev":
            continue
        schema = M.schema_from_map(navs[v["doc"]])
        be = M.DEVSDomain(pdir, schema)
        t0 = time.time()
        ok, why = M.ProbeRunner(be, navs[v["doc"]], schema).replay(title)
        rows.append({"task": task, "label": label, "run": run, "program_dir": pdir, "scope": title,
                     "seen_at_build": v["seen_at_build"], "replay": ok, "detail": why, "secs": round(time.time() - t0, 1)})
    with REPLAY.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return sum(r["replay"] for r in rows), len(rows)


def main(cap="8"):
    cap = float(cap)
    env = env_with_key()
    splits = json.loads((ROOT / "manifests" / "mlsys_splits_v1.json").read_text(encoding="utf-8"))
    navs = {d: json.loads((ROOT / "runs" / "mlsys_docs" / d / "navmap.json").read_text()) for d in
            {v["doc"] for dom in ("manufacturing", "it_ops") for v in splits[dom].values()}}
    test_names = [t for dom in ("manufacturing", "it_ops") for t, v in splits[dom].items() if v["split"] == "test"]
    rc, out, _ = wsl(f"python3 '{WSL_PROJ}/scripts/check_builder_isolation.py' --wsl --expect-visible")
    pos = out.strip().splitlines()[-1] if out.strip() else ""
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "positive_control", "rc": rc, "result": pos, "at": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")
    print("positive control:", pos)
    if rc != 0:
        sys.exit("positive control failed; nothing built")
    replay_ok, replay_why = library_sandbox_hardened()
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "library_sandbox_check", "ok": replay_ok, "detail": replay_why,
                            "at": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")
    print("library sandbox for replay:", "ok" if replay_ok else "NOT OK, replay deferred", "-", replay_why)
    plan = [(lab, task, f"run_{k:02d}") for lab in ("haiku", "sonnet") for k in (1, 2, 3) for task in TASKS]
    spent, costs = 0.0, {"haiku": [], "sonnet": []}
    for lab, task, run in plan:
        expect = max(costs[lab] or [DEFAULT_COST[lab]])
        if spent + expect > cap:
            print(f"STOP before {lab} {task} {run}: spent ${spent:.2f}, next about ${expect:.2f}, cap ${cap:.2f}")
            with LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"event": "stopped_by_cap", "before": [lab, task, run], "spent": round(spent, 4), "cap": cap}) + "\n")
            break
        # a run that already has a program (an earlier invocation) is skipped before its pre-check: its log folder
        # holds that build's own agent logs, which the pre-check would rightly refuse
        _, done_out, _ = wsl(f"find {shlex.quote(f'/home/aashraf/trust2027/gen/{lab}/{task}/{run}')} -name run.py -type f -print -quit")
        if (done_out or "").strip():
            print(f"{lab} {task} {run}: already built, skipped", flush=True)
            continue
        args = f"'{task}' '{MODELS[lab]}' '{lab}' '{run}' {MAXTOK} {TOUT} '{WSL_PROJ}'"
        rc1, out1, err1 = wsl(f"bash '{SCRIPT}' check {args}", env=env, timeout=600)
        pre_ok, pre = judge_check(out1, lab, task, run)
        rec = {"event": "build", "task": task, "label": lab, "run": run, "pre_check_ok": pre_ok, "pre_check": pre,
               "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        if not pre_ok:
            rec["built"] = False
            with LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"{lab} {task} {run}: PRE-CHECK FAILED, not built: {json.dumps(pre)[:400]}")
            break
        rc2, out2, err2 = wsl(f"bash '{SCRIPT}' build {args}", env=env, timeout=TOUT + 900)
        line = out2.strip().splitlines()[-1] if out2.strip() else "{}"
        try:
            res = json.loads(line)
        except ValueError:
            res = {"task": task, "model": MODELS[lab], "label": lab, "run": run, "exit": rc2, "error": (err2 or out2)[-300:]}
        if "skip" in res:
            print(f"{lab} {task} {run}: skipped ({res['skip']})")
            continue
        idx = {k: res.get(k) for k in ("task", "model", "label", "run", "max_output_tokens", "timeout", "exit", "seconds", "has_run_py")}
        with INDEX.open("a", encoding="utf-8") as f:
            f.write(json.dumps(idx) + "\n")
        rc3, out3, _ = wsl(f"bash '{SCRIPT}' check {args}", env=env, timeout=600)
        post_ok, post = judge_check(out3, lab, task, run, phase="post")
        t = tokens(lab, task, run)
        cost = price(lab, t)
        usd_basis = "call log"
        # the call log is in the builder's workspace: if it is missing or unreadable although the proxy carried
        # traffic, charge a conservative amount (twice the largest so far, or twice the default) so the cap still holds
        if cost is None and (res.get("proxy_allowed") or 0) > 0:
            cost = round(2 * max(costs[lab] or [DEFAULT_COST[lab]]), 4)
            usd_basis = "conservative estimate (no readable call log, proxy carried traffic)"
        if cost is not None:
            spent += cost
            costs[lab].append(cost)
        pdir, refused = program_dir(lab, task, run) if res.get("has_run_py") else (None, None)
        hits = scan(pdir, test_names) if pdir else []
        if pdir and (not post_ok or res.get("key_found_in_files")):
            rp, replay_state = (0, 0), "not run: post-check failed or the key was found in the build's files"
        elif pdir and replay_ok:
            rp, replay_state = replay(lab, task, run, pdir, splits, navs), "done"
        else:
            rp, replay_state = (0, 0), ("deferred: " + replay_why) if pdir else "no program"
        rec.update({"built": True, "index": idx, "proxy_allowed": res.get("proxy_allowed"), "proxy_denied": res.get("proxy_denied"),
                    "proxy_bytes_up": res.get("proxy_bytes_up"), "proxy_bytes_down": res.get("proxy_bytes_down"),
                    "key_found_in_files": res.get("key_found_in_files"), "sandbox_rc": res.get("sandbox_rc"),
                    "post_check_ok": post_ok, "post_check": post, "tokens": t, "usd": cost, "usd_basis": usd_basis,
                    "spent_so_far": round(spent, 4), "program_dir": pdir, "program_dir_refused": refused,
                    "test_name_hits": hits, "replay": replay_state, "replay_pass": rp[0], "replay_chapters": rp[1]})
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"{lab} {task} {run}: exit {idx['exit']} run.py {idx['has_run_py']} {idx['seconds']}s, ${cost} ({usd_basis}), "
              f"spent ${spent:.2f}; pre {pre_ok} post {post_ok}; proxy allowed {res.get('proxy_allowed')} denied "
              f"{res.get('proxy_denied')}; key in files {res.get('key_found_in_files')}; test-name hits {len(hits)}; "
              f"replay {replay_state} {rp[0]}/{rp[1]}" + (f"; {refused}" if refused else ""), flush=True)
        if not post_ok:
            print("POST-CHECK FAILED; stopping")
            break
        if not idx.get("has_run_py") and not (res.get("proxy_allowed") or 0) and not t.get("calls"):
            # failed before any model call: a setup problem, not a build outcome; stop instead of using up the plan
            print("FAILED BEFORE ANY MODEL CALL; stopping to fix the setup", flush=True)
            break
        if res.get("key_found_in_files"):
            print("THE KEY WAS FOUND IN BUILD OUTPUT FILES; stopping (the files are not copied anywhere)")
            break
    print(f"done; spent ${spent:.2f}")


def replay_deferred():
    """Replay the builds whose replay was deferred (no model call). Runs only if the library sandbox passes."""
    ok, why = library_sandbox_hardened()
    print("library sandbox for replay:", "ok" if ok else "NOT OK", "-", why)
    if not ok:
        sys.exit("replay still deferred")
    splits = json.loads((ROOT / "manifests" / "mlsys_splits_v1.json").read_text(encoding="utf-8"))
    navs = {d: json.loads((ROOT / "runs" / "mlsys_docs" / d / "navmap.json").read_text()) for d in
            {v["doc"] for dom in ("manufacturing", "it_ops") for v in splits[dom].values()}}
    recs = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    done = {(r["label"], r["task"], r["run"]) for r in recs if r.get("event") == "replay_deferred_done"}
    for r in recs:
        key = (r.get("label"), r.get("task"), r.get("run"))
        if r.get("event") != "build" or not str(r.get("replay", "")).startswith("deferred") or key in done:
            continue
        if not r.get("post_check_ok") or r.get("key_found_in_files"):
            print(key, "post-check failed or key found; not replayed")
            continue
        pdir, refused = program_dir(*key)
        if not pdir or pdir != r.get("program_dir"):
            print(key, "program folder changed or refused; not replayed", refused)
            continue
        p, n = replay(*key, pdir, splits, navs)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "replay_deferred_done", "label": key[0], "task": key[1], "run": key[2],
                                "replay_pass": p, "replay_chapters": n, "library_check": why,
                                "at": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")
        print(key, f"replay {p}/{n}", flush=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["replay"]:
        replay_deferred()
    else:
        main(*sys.argv[1:2])
