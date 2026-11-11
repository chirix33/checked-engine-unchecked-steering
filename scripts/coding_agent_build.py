"""Third program-generation platform: a plain reason-and-code agent (decision 1, manifests/baseline_judges_design.md).

In the paper it is named generically ("a plain coding agent"). One model reads a domain's shared task spec
(adapters/generic_tasks/<Domain>/spec.md: the rules, the generic stdin input format and the JSONL output format),
reasons, and writes one Python program, run.py. The program is then run on the spec's own example input
(example_input.json) and the model sees what it printed: exit code, wall time, the first and last lines of standard
output and the tail of standard error, as raw text. It may revise, up to a fixed number of model replies. Nothing
else: no checker, no reference, no expected output, no test documents, no format checks, no hints about what is
wrong. The last program it writes is the build's program, whatever its example run did (the platform has no
acceptance check of its own).

Platform scaffolding, disclosed: the system prompt says the program runs with Python 3.10 and the spec's libraries,
with no network and no file writes (all true of the sandbox). The example run uses no options, as the spec's defaults
describe. A separate record-only run with `--horizon` (the way the evaluation adapters call programs) is made after
the build and never shown to the model.

What the builder can see:
- the model sees only the messages in the build's prompt_log.jsonl (system prompt, spec text, then the example runs'
  raw output); it has no tools. The shared client keeps reply text only, not thinking content;
- the code it writes runs only inside WSL under bubblewrap (no network, /mnt and /home hidden apart from its own
  read-only folder and the interpreter, empty environment), the form in manifests/builder_isolation.md.
  scripts/check_builder_isolation.py runs inside that same sandbox before and after every build and must report
  0 findings; its positive control runs outside the sandbox first. A second probe lists everything under /home that
  the sandbox can see and fails on anything other than the program folder, the interpreter and the check itself
  (sibling builds and DEVS-Gen code, which the check script's own list does not name).
After a workflow build, the build folder is searched for the test-only names and draws
(runs/workflow_test_v1/scan_patterns), as builder_isolation.md asks.

Outputs: runs/coding_agent/<setup>/<Domain>/b<k>/ holds run.py, prompt_log.jsonl (every message sent and reply
received, in full), example_runs.jsonl, isolation_*.txt and build.json (status, turns, tokens, cost, hashes, settings).
The program also lives in WSL at /home/aashraf/trust2027/coding_agent/<setup>/<Domain>/b<k>/run.py (byte-identical;
both hashes are recorded), which is the folder assurance.backends.DEVSBackend / assurance.mlsys.DEVSDomain run
unchanged. Model calls go through the shared client in scripts/b0_build_test.py (its ledger and spending stop), with
the ledger at runs/build_test_coding_agent/calls_<setup>.jsonl, so the shared Claude cap counts these calls. Before
each call the shared spend plus the largest possible cost of that call is also checked against the cap.

A finished build (build.json) is skipped on rerun. A build stopped by the cap, a service failure or a harness error
writes stopped.json instead and is retried on rerun; the earlier attempt's files are moved to attempt_<n>/ and kept,
and every attempt has its own build id in the ledger.

Usage: python -X utf8 scripts/coding_agent_build.py <setup> <Domain> <k> [--turns N] [--max-usd X]
           [--max-output N] [--fake-replies FILE --out-root DIR --wsl-base DIR]
   --fake-replies: a JSON list of reply strings used instead of a model (offline tests; no ledger, no cost).
   Run with .tools/b0_env (it has the anthropic SDK) and PYTHONDONTWRITEBYTECODE=1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_VERSION = "coding-agent-0.2"
DOMAINS = ("WorkflowLoan", "WorkflowPharmacy", "Manufacturing", "ITOperations")
WORKFLOW = {"WorkflowLoan", "WorkflowPharmacy"}
TURNS = 3                       # model replies per build: one first program and up to two revisions
MAX_OUTPUT = 32000              # output-token cap per reply (thinking included); recorded in build.json
RUN_TIMEOUT = 60                # seconds per example run (the spec asks for under 10)
OUTPUT_LIMIT = 20_000_000       # bytes of standard output kept from one run
HEAD_LINES, TAIL_LINES, LINE_CHARS, STDERR_CHARS = 40, 15, 400, 3000
HORIZON = {"WorkflowLoan": 10 ** 8, "WorkflowPharmacy": 10 ** 8, "ITOperations": 10 ** 8}   # as the adapters pass it

WSL_DISTRO = "Ubuntu-24.04"
WSL_BASE = "/home/aashraf/trust2027/coding_agent"
BWRAP = "$HOME/trust2027/tools/usr/bin/bwrap"
VENV = "$HOME/trust2027/devs_gen_code/.venvs/devs-gen"   # the interpreter DEVSBackend runs programs with
PY_HOME = "$HOME/.local/share/uv/python"
PATTERNS = ROOT / "runs" / "workflow_test_v1" / "scan_patterns"
CUT = ("max_tokens", "length")

SYSTEM = """You are an expert Python programmer. You write one complete, self-contained Python program, run.py, that \
implements the task specification the user gives you.

Reason carefully about every rule in the specification before you write code. Then reply with exactly one fenced code \
block, ```python ... ```, holding the complete contents of run.py.

The program will be run as `python run.py [options]` with Python 3.10 and the libraries the specification lists, with \
its input on standard input. It has no network access and cannot write files."""

FIRST = """Task specification:

{spec}

After you reply, your program will be run once as `python run.py`, with no options, on the full example input the \
specification refers to (example_input.json, {example_bytes} bytes) on standard input, and you will be shown what it \
printed. Write run.py now."""

FEEDBACK = """Your program was run as `python run.py` with example_input.json on standard input.

Exit code: {exit}
Wall time, including sandbox start-up: {seconds} s
Standard output:
{stdout}
Standard error (last {stderr_chars} characters):
{stderr}

You have {left} more {replies}. If you want to change the program, reply with the complete revised run.py in one \
```python code block. If the program is finished, reply with the single word DONE."""

NO_CODE = """Your reply did not contain a complete ```python code block{why}. {state}

You have {left} more {replies}. Reply with the complete run.py in one ```python code block{or_done}."""

FENCE = re.compile(r"```[ \t]*(python3?|py)?[ \t]*\r?\n(.*?)```", re.S | re.I)


def sha(data) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def extract_code(reply: str):
    """(code or None, number of python blocks). Python-tagged blocks are used; a bare fence only when it is the
    reply's one block. Among several, the longest wins (a short usage snippet after the program is not the program)."""
    found = FENCE.findall(reply or "")
    tagged = [body for tag, body in found if tag]
    blocks = tagged or ([found[0][1]] if len(found) == 1 else [])
    blocks = [b for b in blocks if b.strip()]
    if not blocks:
        return None, len(tagged)
    return max(blocks, key=len).strip("\n") + "\n", len(tagged) or 1


def is_done(reply: str) -> bool:
    return (reply or "").strip().strip(".").upper() == "DONE"


def summarize_run(code: int | None, stdout: str, stderr: str, seconds: float, killed: bool = False) -> dict:
    """The raw view the model gets (head, tail, stderr tail) plus counts that are recorded but never shown."""
    lines = stdout.splitlines()
    bad = 0
    for l in lines:
        if l.strip():
            try:
                json.loads(l)
            except ValueError:
                bad += 1
    return {"exit": code, "killed_by_timeout": killed, "seconds": round(seconds, 2), "stdout_lines": len(lines),
            "nonempty_lines": sum(1 for l in lines if l.strip()), "bad_lines": bad, "stdout_bytes": len(stdout.encode("utf-8")),
            "stdout_sha256": sha(stdout), "stdout_head": [l[:LINE_CHARS] for l in lines[:HEAD_LINES]],
            "stdout_tail": [l[:LINE_CHARS] for l in lines[HEAD_LINES:][-TAIL_LINES:]],
            "stdout_skipped": max(0, len(lines) - HEAD_LINES - TAIL_LINES), "stderr_tail": (stderr or "")[-STDERR_CHARS:]}


def feedback_text(r: dict, left: int) -> str:
    parts = []
    if r["stdout_head"]:
        parts.append("\n".join(r["stdout_head"]))
    if r["stdout_skipped"]:
        parts.append(f"[{r['stdout_skipped']} lines not shown]")
    if r["stdout_tail"]:
        parts.append("\n".join(r["stdout_tail"]))
    if r["killed_by_timeout"]:
        exit_text = f"none: stopped after the time limit of {RUN_TIMEOUT} s"
    else:
        exit_text = str(r["exit"])
    return FEEDBACK.format(exit=exit_text, seconds=r["seconds"], stdout="\n".join(parts) if parts else "(nothing)",
                           stderr_chars=STDERR_CHARS, stderr=r["stderr_tail"] or "(nothing)", left=left,
                           replies="reply" if left == 1 else "replies")


def plural(n):
    return "reply" if n == 1 else "replies"


# ---------------------------------------------------------------------------------------------------------------
def wsl_bash(cmd: str, stdin: bytes | None = None, timeout: int = 120):
    """Bytes in and out, so no newline translation on the way into WSL."""
    p = subprocess.run(["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-c", cmd], input=stdin, capture_output=True,
                       timeout=timeout, env={**os.environ, "MSYS_NO_PATHCONV": "1"})
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


class WSLSandbox:
    """Writes the program into its WSL folder and runs it under bubblewrap, as DEVSBackend runs built programs."""

    def __init__(self, wsl_dir: str, check_dir: str):
        assert wsl_dir.startswith(WSL_BASE + "/") and ".." not in wsl_dir and "'" not in wsl_dir, wsl_dir
        self.dir, self.check_dir = wsl_dir, check_dir

    def _bwrap(self, extra_binds: str, command: str) -> str:
        d = shlex.quote(self.dir)
        return (f"{BWRAP} --ro-bind / / --tmpfs /mnt --tmpfs /home --ro-bind {VENV} {VENV} --ro-bind-try {PY_HOME} {PY_HOME} "
                f"--ro-bind {d} {d} {extra_binds} --dev /dev --proc /proc --tmpfs /tmp --unshare-net --die-with-parent "
                f"--clearenv --setenv PATH /usr/bin:/bin --setenv HOME \"$HOME\" --chdir {d} {command}")

    def reset(self):
        """A fresh, empty program folder (an earlier attempt's WSL copy is removed; its Windows copy is kept)."""
        d = shlex.quote(self.dir)
        rc, _, err = wsl_bash(f"rm -rf {d} && mkdir -p {d}")
        if rc != 0:
            raise RuntimeError(f"cannot prepare {self.dir}: {err[-300:]}")

    def write(self, code: str):
        d = shlex.quote(self.dir)
        rc, _, err = wsl_bash(f"find {d} -mindepth 1 -delete && cat > {d}/run.py", stdin=code.encode("utf-8"))
        if rc != 0:
            raise RuntimeError(f"cannot write program: {err[-300:]}")

    def file_sha256(self) -> str:
        rc, out, err = wsl_bash(f"sha256sum {shlex.quote(self.dir)}/run.py")
        return out.split()[0] if rc == 0 and out else f"error: {err[-200:]}"

    def run(self, stdin: str, args: str = ""):
        inner = self._bwrap("", f"timeout --verbose -k 5 {RUN_TIMEOUT} {VENV}/bin/python run.py {args}".rstrip())
        # wsl.exe hands the command to an outer shell first, so PIPESTATUS would be expanded too early; pipefail
        # gives the program's own exit code (or 141 if it was cut off at the output limit)
        cmd = f"set -o pipefail; cd {shlex.quote(self.dir)} && {inner} | head -c {OUTPUT_LIMIT}"
        t0 = time.time()
        try:
            rc, out, err = wsl_bash(cmd, stdin=stdin.encode("utf-8"), timeout=RUN_TIMEOUT + 60)
        except subprocess.TimeoutExpired:
            return None, "", "", time.time() - t0, True
        killed = "timeout: sending signal" in err
        return (None if killed else rc), out, err, time.time() - t0, killed

    def install_check(self, script: Path):
        c = shlex.quote(self.check_dir)
        rc, _, err = wsl_bash(f"mkdir -p {c} && cat > {c}/check_builder_isolation.py", stdin=script.read_bytes())
        if rc != 0:
            raise RuntimeError(f"cannot install isolation check: {err[-300:]}")

    def positive_control(self) -> dict:
        rc, out, err = wsl_bash(f"python3 {shlex.quote(self.check_dir)}/check_builder_isolation.py --wsl --expect-visible")
        return {"exit": rc, "output": out + err}

    def isolation_check(self) -> dict:
        c = shlex.quote(self.check_dir)
        rc, out, err = wsl_bash(self._bwrap(f"--ro-bind {c} {c}", f"{VENV}/bin/python {c}/check_builder_isolation.py --wsl "
                                                                  f"--workspace {shlex.quote(self.dir)}"))
        # second probe: everything under /home the sandbox can see, outside the interpreter trees
        rc2, tree, err2 = wsl_bash(self._bwrap(f"--ro-bind {c} {c}", f"/usr/bin/find /home -mindepth 1 "
                                                                     f"\\( -path {VENV} -o -path {PY_HOME} \\) -prune -o -print"))
        home = os.path.dirname(os.path.dirname(WSL_BASE))           # /home/aashraf
        allowed = [self.dir, self.check_dir]
        venv, py_home = VENV.replace("$HOME", home), PY_HOME.replace("$HOME", home)
        allowed += [venv, py_home]
        extra = []
        for p in tree.splitlines():
            ok = any(p == a or p.startswith(a + "/") or a.startswith(p + "/") for a in allowed)
            if not ok:
                extra.append(p)
        findings = (rc != 0) or rc2 != 0 or bool(extra)
        text = out + err + f"\n/home probe: {len(tree.splitlines())} visible entries, {len(extra)} outside the allowed " \
                           f"folders\n" + "\n".join(f"VISIBLE {p}" for p in extra[:50]) + (err2[-300:] if rc2 else "")
        return {"exit": 1 if findings else 0, "check_exit": rc, "home_extra": len(extra), "output": text}


class FakeClient:
    """Scripted replies in place of a model (offline tests). Same surface as b0_build_test.Client."""

    def __init__(self, replies: list[str]):
        self.replies, self.calls, self.build_id, self.name = list(replies), [], None, "fake"

    def llm(self, messages):
        text = self.replies.pop(0) if self.replies else ""
        self.calls.append({"build": self.build_id, "fake": True, "usd": 0.0, "prompt_chars": sum(len(m["content"]) for m in messages),
                           "prompt_tokens": 0, "output_tokens": 0, "seconds": 0.0, "finish": "end_turn", "reply_chars": len(text)})
        return text


class Stop(Exception):
    """The build stopped for a reason that is not the model's (cap, service, harness)."""

    def __init__(self, status, detail):
        super().__init__(detail)
        self.status, self.detail = status, detail


# ---------------------------------------------------------------------------------------------------------------
def build(spec: str, example: str, client, sandbox, out: Path, turns: int, guard=None, stop_errors=()) -> dict:
    """The agent loop. Returns the build record; writes prompt_log.jsonl and example_runs.jsonl as it goes.
    `guard(messages)` returns a reason string to stop before a call, or None. `stop_errors` maps exception types
    from the client to a status (cap or service failure)."""
    log, runs_log = out / "prompt_log.jsonl", out / "example_runs.jsonl"

    def write_log(path, rec):
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": FIRST.format(spec=spec, example_bytes=len(example.encode("utf-8")))}]
    for m in messages:
        write_log(log, {"turn": 0, **m})
    program, program_turn, history, stop, stopped = None, None, [], "turn_limit", None

    def say(turn, msg):
        messages.append({"role": "user", "content": msg})
        write_log(log, {"turn": turn, "role": "user", "content": msg})

    for turn in range(1, turns + 1):
        reason = guard(messages) if guard else None
        if reason:
            stopped = ("stopped_at_cap", reason)
            break
        n_before = len(client.calls)
        try:
            reply = client.llm(messages)
        except tuple(stop_errors) as e:
            stopped = (stop_errors[type(e)] if type(e) in stop_errors else "infrastructure_failure", f"{type(e).__name__}: {str(e)[:300]}")
            break
        call = client.calls[-1] if len(client.calls) > n_before else {}
        messages.append({"role": "assistant", "content": reply})
        write_log(log, {"turn": turn, "role": "assistant", "content": reply, "finish": call.get("finish")})
        code, blocks = extract_code(reply)
        step = {"turn": turn, "calls": len(client.calls) - n_before, "finish": call.get("finish"), "python_blocks": blocks,
                "reply_chars": len(reply)}
        left = turns - turn
        if code is None and is_done(reply) and program is not None:
            step["action"] = "done"
            history.append(step)
            stop = "done"
            break
        if code is None:
            cut = call.get("finish") in CUT
            step["action"] = "cut_off" if cut else ("empty" if not reply.strip() else "no_code")
            history.append(step)
            if left:
                why = " (the reply stopped at the output limit)" if cut else (" (the reply was empty)" if not reply.strip() else "")
                state = ("The program from your earlier reply is still the current one." if program is not None
                         else "There is no program yet.")
                say(turn, NO_CODE.format(why=why, state=state, left=left, replies=plural(left),
                                         or_done=", or DONE to keep the current program" if program is not None else ""))
            continue
        program, program_turn = code, turn
        sandbox.write(code)
        rc, so, se, secs, killed = sandbox.run(example)
        r = summarize_run(rc, so, se, secs, killed)
        write_log(runs_log, {"turn": turn, "program_sha256": sha(code), **r})
        step.update(action="program", program_sha256=sha(code), example_exit=rc, example_killed=killed,
                    example_lines=r["nonempty_lines"], example_bad_lines=r["bad_lines"], example_seconds=r["seconds"])
        history.append(step)
        if left:
            say(turn, feedback_text(r, left))
    final_run = next((h for h in reversed(history) if h.get("action") == "program"), None)
    if stopped:
        status, stop = stopped
    else:
        status = "built" if program else "no_program"
    return {"status": status, "stop": stop, "turns_used": len(history),
            "final_turn": program_turn, "program": program, "steps": history,
            "final_example_exit": final_run["example_exit"] if final_run else None,
            "final_example_killed": final_run["example_killed"] if final_run else None,
            "final_example_lines": final_run["example_lines"] if final_run else None,
            "final_example_bad_lines": final_run["example_bad_lines"] if final_run else None}


def pattern_scan(folder: Path) -> dict:
    """Test-only titles, seeds and route draws (workflow) anywhere in the build folder (builder_isolation.md)."""
    names = PATTERNS / "test_names.txt"
    draws = PATTERNS / "test_draws.txt"
    if not (names.exists() and draws.exists()):
        return {"ran": False, "detail": f"pattern files missing under {PATTERNS}"}
    pn = [l for l in names.read_text(encoding="utf-8").splitlines() if l.strip()]
    pd = [l for l in draws.read_text(encoding="utf-8").splitlines() if l.strip()]
    hit_names, hit_draws = {}, set()
    for f in sorted(folder.rglob("*")):
        if not f.is_file() or f.name in ("build.json", "stopped.json"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        n = [p for p in pn if p in text]
        if n:
            hit_names[f.name] = n
        hit_draws |= {p for p in pd if p in text}
    return {"ran": True, "files_naming_test": hit_names, "test_draw_strings": sorted(hit_draws),
            "patterns": {"names": len(pn), "draws": len(pd)}}


def horizon_arg(domain, example: str) -> str:
    if domain in HORIZON:
        return f"--horizon {HORIZON[domain]}"
    days = [d["day"] for d in json.loads(example)["days"]]      # manufacturing: the adapter passes the last day
    return f"--horizon {max(days)}"


def file_sha(path: Path) -> str:
    return sha(path.read_bytes()) if path.exists() else None


def git_head():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("setup")
    ap.add_argument("domain", choices=DOMAINS)
    ap.add_argument("k", type=int)
    ap.add_argument("--turns", type=int, default=TURNS)
    ap.add_argument("--max-usd", type=float, default=None, help="local stop on this build's own spend")
    ap.add_argument("--max-output", type=int, default=MAX_OUTPUT)
    ap.add_argument("--fake-replies", default=None)
    ap.add_argument("--out-root", default=str(ROOT / "runs" / "coding_agent"))
    ap.add_argument("--wsl-base", default=WSL_BASE)
    a = ap.parse_args(argv)
    if a.wsl_base != WSL_BASE and not a.wsl_base.startswith(WSL_BASE + "/"):
        raise SystemExit("the WSL base must sit under " + WSL_BASE)

    task = ROOT / "adapters" / "generic_tasks" / a.domain
    spec = (task / "spec.md").read_text(encoding="utf-8")
    example = (task / "example_input.json").read_text(encoding="utf-8")
    out = Path(a.out_root) / a.setup / a.domain / f"b{a.k}"
    if (out / "build.json").exists():
        print(f"{out} already finished; skipped")
        return 0
    attempt = 1
    if out.exists():                    # an earlier attempt that stopped or crashed: keep its files, start afresh
        attempt = 1 + sum(1 for p in out.iterdir() if p.is_dir() and p.name.startswith("attempt_"))
        loose = [f for f in out.iterdir() if f.is_file()]
        if loose:
            keep = out / f"attempt_{attempt}"
            keep.mkdir()
            for f in loose:
                f.rename(keep / f.name)
            attempt += 1
    out.mkdir(parents=True, exist_ok=True)
    wsl_dir = f"{a.wsl_base}/{a.setup}/{a.domain}/b{a.k}"
    sandbox = WSLSandbox(wsl_dir, f"{WSL_BASE}/_isolation")

    sys.path[:0] = [str(ROOT / "scripts"), str(ROOT)]
    sys.dont_write_bytecode = True
    stop_errors, guard, setup_snapshot, sdk = {}, None, None, None
    if a.fake_replies:
        client = FakeClient(json.loads(Path(a.fake_replies).read_text(encoding="utf-8")))
        model = "fake"
    else:
        import b0_build_test as bt
        env = bt.load_env(ROOT / ".env")
        ledger = bt.Ledger(ROOT / "runs" / "build_test_coding_agent", a.setup)
        try:
            client = bt.Client(a.setup, env, ledger, max_output=a.max_output)
        except TypeError:                        # an older client without the parameter: the module global
            bt.MAX_OUTPUT = a.max_output         # (this process only; b0_build_test.py itself is unchanged)
            client = bt.Client(a.setup, env, ledger)
        # the 2026-11-10 smoke ran on a half-edited client and got 16384; refuse to build unless the cap took effect
        if getattr(client, "max_output", None) != a.max_output:
            raise SystemExit(f"the client's output cap is {getattr(client, 'max_output', None)}, not {a.max_output}")
        s = bt.SETUPS[a.setup]
        model = s.get("model")
        setup_snapshot = {k: v for k, v in s.items() if k != "key"}
        if s["kind"] == "claude":
            import anthropic
            sdk = anthropic.__version__
        cap = bt.CLAUDE_CAP_USD if s["kind"] == "claude" else bt.CAP_USD
        in_price, out_price = s["price_per_million"]

        def guard(messages, _client=client):
            # the largest this call can cost: every prompt char a token at the highest price tier, full output
            chars = sum(len(m["content"]) for m in messages)
            scale = 5.0 if s.get("model") == "claude-haiku-5-5" else 1.0
            worst = (chars * in_price * 1.25 + a.max_output * out_price) * scale / 1e6
            spent = _client.ledger.spent()
            if spent + worst > cap - bt.CAP_MARGIN_USD:
                return f"shared spend {spent:.2f} + worst-case call {worst:.2f} would pass the cap {cap:.2f}"
            mine = sum(c.get("usd") or 0.0 for c in _client.calls)
            if a.max_usd is not None and mine + worst > a.max_usd:
                return f"this build's spend {mine:.3f} + worst-case call {worst:.3f} would pass --max-usd {a.max_usd}"
            return None
        stop_errors = {bt.CapReached: "stopped_at_cap", bt.InfrastructureFailure: "infrastructure_failure"}
    client.build_id = f"coding_agent/{a.setup}/{a.domain}/b{a.k}/attempt{attempt}"

    started = time.time()
    base = {"generator": GENERATOR_VERSION, "platform": "plain coding agent", "setup": a.setup, "model": model,
            "domain": a.domain, "build": a.k, "attempt": attempt,
            "build_id": client.build_id, "turns_allowed": a.turns, "max_output_tokens": a.max_output,
            "client_max_output": getattr(client, "max_output", None), "empty_reply_retries": "client default (2)",
            "run_timeout_s": RUN_TIMEOUT, "max_usd": a.max_usd, "setup_settings": setup_snapshot, "anthropic_sdk": sdk,
            "code": {"git_head": git_head(), "coding_agent_build_sha256": file_sha(Path(__file__)),
                     "b0_build_test_sha256": file_sha(ROOT / "scripts" / "b0_build_test.py"),
                     "check_builder_isolation_sha256": file_sha(ROOT / "scripts" / "check_builder_isolation.py")},
            "inputs": {"spec_sha256": sha(spec), "example_sha256": sha(example), "system_sha256": sha(SYSTEM),
                       "first_template_sha256": sha(FIRST), "feedback_template_sha256": sha(FEEDBACK),
                       "no_code_template_sha256": sha(NO_CODE)}}

    def cost():
        calls = client.calls
        return {"calls": len(calls), "failed_calls": sum(1 for c in calls if c.get("failed")),
                "usd": round(sum(c.get("usd") or 0.0 for c in calls), 6),
                "prompt_tokens": sum(c.get("prompt_tokens") or 0 for c in calls),
                "output_tokens": sum(c.get("output_tokens") or 0 for c in calls),
                "cache_read_tokens": sum(c.get("cache_read_tokens") or 0 for c in calls),
                "model_seconds": round(sum(c.get("seconds") or 0.0 for c in calls), 1)}

    def stopped(status, detail, **extra):
        rec = {**base, "status": status, "detail": detail, **extra, "cost": cost(), "call_records": client.calls,
               "wall_seconds": round(time.time() - started, 1), "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        (out / "stopped.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{client.build_id}: {status}: {detail} (${rec['cost']['usd']:.4f}); retried on rerun")
        return 2

    try:
        sandbox.install_check(ROOT / "scripts" / "check_builder_isolation.py")
        sandbox.reset()
        control = sandbox.positive_control()
        before = sandbox.isolation_check()
        (out / "isolation_positive_control.txt").write_text(control["output"], encoding="utf-8")
        (out / "isolation_before.txt").write_text(before["output"], encoding="utf-8")
        if control["exit"] != 0 or before["exit"] != 0:
            return stopped("isolation_failed", "isolation check failed; no model call made",
                           positive_control_exit=control["exit"], before_exit=before["exit"])
        result = build(spec, example, client, sandbox, out, a.turns, guard, stop_errors)
        for c in client.calls:
            c.setdefault("max_output_tokens", a.max_output)
        program = result.pop("program")
        if result["status"] not in ("built", "no_program"):
            return stopped(result["status"], result["stop"], partial=result)
        if program:
            (out / "run.py").write_bytes(program.encode("utf-8"))
        wsl_sha = sandbox.file_sha256() if program else None
        program_hash = None
        if program:
            from assurance.backends import DEVSBackend
            program_hash = DEVSBackend(wsl_dir, a.domain, ROOT).program_hash()
        # record-only: the program run the way the evaluation adapters call it, never shown to the model
        horizon_run = None
        if program:
            rc, so, se, secs, killed = sandbox.run(example, horizon_arg(a.domain, example))
            r = summarize_run(rc, so, se, secs, killed)
            horizon_run = {"args": horizon_arg(a.domain, example), **{k: r[k] for k in ("exit", "killed_by_timeout",
                           "seconds", "nonempty_lines", "bad_lines", "stdout_sha256", "stderr_tail")}}
        after = sandbox.isolation_check()
        (out / "isolation_after.txt").write_text(after["output"], encoding="utf-8")
    except Exception as e:                                  # harness error: keep the record of paid calls
        return stopped("harness_error", f"{type(e).__name__}: {str(e)[:400]}")
    except KeyboardInterrupt:
        stopped("harness_error", "interrupted")
        raise
    scan = pattern_scan(out) if a.domain in WORKFLOW else {"ran": False, "detail": "no test pattern files for this domain"}
    rec = {
        **base, **result,
        "program_sha256": sha(program) if program else None, "wsl_run_py_sha256": wsl_sha,
        "wsl_matches_local": (wsl_sha == sha(program)) if program else None,
        "program_hash": program_hash, "wsl_dir": wsl_dir if program else None, "horizon_run": horizon_run,
        "cost": cost(), "call_records": client.calls, "wall_seconds": round(time.time() - started, 1),
        "isolation": {"positive_control_exit": control["exit"], "before_exit": before["exit"], "after_exit": after["exit"],
                      "after_home_extra": after["home_extra"], "files": ["isolation_positive_control.txt",
                                                                        "isolation_before.txt", "isolation_after.txt"]},
        "pattern_scan": scan, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (out / "build.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    leak = scan.get("ran") and (scan["files_naming_test"] or scan["test_draw_strings"])
    print(f"{client.build_id}: {rec['status']} ({rec['stop']}), turns {rec['turns_used']}, example exit "
          f"{rec['final_example_exit']}, {rec['final_example_lines']} lines; horizon run exit "
          f"{(horizon_run or {}).get('exit')}; ${rec['cost']['usd']:.4f}; isolation after {after['exit']}; "
          f"wsl copy identical {rec['wsl_matches_local']}; pattern hits {'YES' if leak else 'none'}")
    return 0 if after["exit"] == 0 and not leak and rec["wsl_matches_local"] is not False else 3


if __name__ == "__main__":
    sys.exit(main())
