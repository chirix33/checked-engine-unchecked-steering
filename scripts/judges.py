"""Trust-judge baselines that use a model (manifests/baseline_judges_design.md, D22):

- `answer`:  LLM-as-a-judge, answer level. One call per (program, question).
- `program`: LLM-as-a-judge, program level. One call per (program, run).
- `react`:   a raw text ReAct judge with one tool, `run_code(python)`, at most 8 turns.

Each returns TRUST or DECLINE, a confidence from 0 to 100 and a one-line reason. An unparsable reply, an output
cutoff, a refusal or running out of turns is DECLINE at confidence 0, with the kind recorded in `failure`:
- `unparsable`: no verdict could be read (single call), or the last allowed reply had neither an action nor a verdict;
- `cutoff`: the reply hit the output cap; `refusal`: the model refused;
- `out_of_turns`: the last allowed turn asked for another code run and gave no verdict.
A service failure or the spending stop is raised, never turned into a verdict.

What a judge sees is built by `make_view` from explicit arguments only, never from a question row:
- the document's front matter plus the chapter (run) the interpreted request names;
- the program's own code (OTF: the `code` field of program.json; DEVS-Gen: `devs_project/**/*.py`; coding agent:
  its run.py), and a short note on how its platform runs it;
- the question text and the interpreted structured request (the same one the gate gets);
- answer level and ReAct: the program's answer with the change and without it.
Gold, hidden bindings, the reference, other programs, build history and native verdicts never enter a view.

The ReAct sandbox is WSL bubblewrap for every platform. It is stricter than the form in `assurance.backends`
(review, 2026-11-10: that form leaves /run visible, and code inside can reach the user's session bus and start a
process outside). Here only /usr, three linker files, the interpreter and the row's own folder are mounted, with
new user, PID, IPC and network namespaces. The folder holds the program (with what it needs to run) and the
document view as files, and nothing else.

Additions beyond the design text, all disclosed in the run manifest: the note on how the platform runs the program
(for OTF too), the `otf_run.py` launcher and the OTF runtime package in the sandbox, the run's input object for
stdin programs (`document/input.json`), DEVS-Gen's launcher run.py in the sandbox, and the turn counter line.

All model calls go through the client in `b0_build_test.py` (ledger, spending stop, retries). Prompt layout for
caching: document block, program block (each ends in a cache breakpoint), then the per-row task.

Evaluation side only. Rows come from the main runner's outputs (`runs/main_v1/<set>/`): its interpretation of each
question and, when the program rows exist, the structured answer that gets scored. Question files are read for
the question text, the document name and (for the stratified draw) the family label. Gold and bindings are never read.

Usage:
  python -X utf8 scripts/judges.py smoke <root> [--model claude-haiku-5-5] [--rows 20] [--subset N] [--max-usd 3.0]
                                         [--judges answer,program,react] [--out runs/judges_smoke_v1]
  python -X utf8 scripts/judges.py draw <root> <set>[,<set>...] --subsets manifests/judge_subsets_v1.json
        the D27 subsets (3,000 answer rows, 1,000 of them for ReAct, 150 of those for Sonnet), drawn from the answered
        rows of the main run and frozen with their sha256, before any judging
  python -X utf8 scripts/judges.py run <root> <set>[,<set>...] --out DIR --judges answer --subsets FILE --subset-name answer_haiku
  python -X utf8 scripts/judges.py run <root> <set>[,<set>...] --out DIR --judges react  --subsets FILE --subset-name react_haiku
  python -X utf8 scripts/judges.py run <root> <set>[,<set>...] --out DIR --judges answer --subsets FILE --subset-name answer_sonnet
                                         --model claude-sonnet-5-5
  python -X utf8 scripts/judges.py run <root> <set>[,<set>...] --out DIR --judges program --all-program-runs [--all-cohorts]
        (every run takes --max-usd X, default 3.0, --model, default claude-haiku-5-5, and --shard K/N to split the
        rows over N processes: start one process for each K from 0 to N-1)
  python -X utf8 scripts/judges.py summary <root> [--out runs/judges_smoke_v1]
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT_VERSION = "judges-v2"
JUDGE_NAMES = ("answer", "program", "react")
TURN_CAP = 8                    # Ashraf, 2026-11-08
OBS_CHARS = 4000                # a sandbox result is cut to this many characters (head and tail kept)
SANDBOX_TIMEOUT_S = 120         # wall-clock limit of one run_code call
LOWEST_CONFIDENCE = 0
STOP = ["\nObservation:"]       # so the model cannot write its own observations
FAILURES = ("unparsable", "cutoff", "refusal", "out_of_turns")
PROGRAM_CHAR_LIMIT = 400_000    # a program view above this is refused, never cut silently
WSL = ["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c"]
BW = "$HOME/trust2027/tools/usr/bin/bwrap"
VENV = "$HOME/trust2027/devs_gen_code/.venvs/devs-gen"
PY_HOME = "$HOME/.local/share/uv/python"
SBX_BASE = "$HOME/trust2027/judge_sandbox"
BPF = "$HOME/trust2027/tools/seccomp_unix_only.bpf"     # written by scripts/make_seccomp_filter.py; shared with assurance.backends
LIMITS = "-v 8388608 -u 4096 -f 4194304"                # soft: 8 GB address space, 4,096 processes, 4 GB per file
SBX = "/home/sandbox"           # where the row's folder appears inside bubblewrap (/home is an empty tmpfs there)
RT = "/home/rt"                 # the harness (two files), mounted read-only beside it
TASKS = {"Loan Application Process Records": "WorkflowLoan", "Pharmacy Process Records": "WorkflowPharmacy",
         "Plant Stock and Dispatch Records": "Manufacturing", "Compute Cell Scheduling Records": "ITOperations"}
# Never part of a program view or a sandbox: build history, native results, logs.
FORBIDDEN_NAME_PARTS = ("_analysis_logs", "gen_meta", "quick_smoke", "build_log", "gen_stdout", "gen_stderr",
                        "model_summary_cache", "timing_debug", "__pycache__", "program.json", "raw_simulation_output",
                        "attempt_", "prompt_log", "example_runs", "isolation_", "build.json", "stopped.json", "replay_dev")


# ---------------------------------------------------------------- views
@dataclass(frozen=True)
class Program:
    platform: str                  # "otf", "devs_gen" or "coding_agent"
    shown: dict                    # relative path -> source text: the program's own code, shown to every judge
    runtime: dict = field(default_factory=dict)   # extra files the program needs to run (sandbox only)
    package: str | None = None     # OTF: the runtime package name ("otf_r1" or "otf")


@dataclass(frozen=True)
class View:
    """Everything a judge may see for one row."""
    document: str                  # front matter plus the queried chapter, as text
    nav: dict                      # the same view as a document map
    scope: str
    program: Program
    note: str                      # how the platform runs the program (input and output format)
    horizon: float | int | None    # the horizon the platform runs it with
    question: str | None = None
    request: dict | None = None
    answer_changed: object = None
    answer_factual: object = None
    stdin: dict | None = None      # stdin platforms: the run's input object, built from the chapter's tables


class ViewError(Exception):
    """A view that may not or cannot be built. The row is recorded as skipped, never judged on a partial view."""


def _children(nodes_by_id, node):
    out = []
    for cid in node.get("children") or []:
        c = nodes_by_id.get(cid)
        if c is not None:
            out.append(c)
            out.extend(_children(nodes_by_id, c))
    return out


def _node_text(n) -> str:
    if n["kind"] == "table":
        t = n["table"]
        return f"## {n['title']}\n" + " | ".join(map(str, t["columns"])) + "\n" + "\n".join(" | ".join(map(str, r)) for r in t["rows"])
    if n["kind"] == "list":
        lines = n.get("lines") if isinstance(n.get("lines"), list) else []
        return f"## {n['title']}\n" + "\n".join(map(str, lines))
    return f"## {n['title']}\n{n.get('text') or ''}"


def document_view(nav: dict, scope: str) -> tuple[str, dict]:
    """The front matter and the one chapter titled `scope`, as text and as a document map. A scope the document
    does not have gives the front matter alone."""
    nodes = nav["nodes"]
    by_id = {n["node_id"]: n for n in nodes}
    front = [n for n in nodes if n.get("level") == 0 and n["kind"] == "list"]
    head = next((n for n in nodes if n.get("level") == 0 and n["kind"] != "list" and n["title"] == scope), None)
    chapter = [head] + _children(by_id, head) if head is not None else []
    keep = {n["node_id"] for n in front + chapter}
    kept = [n for n in nodes if n["node_id"] in keep]            # document order
    text = "\n\n".join(_node_text(n) for n in kept)
    if head is None:
        text += f"\n\n(The document has no chapter titled {scope!r}.)"
    view = {"document_id": nav.get("document_id"), "source_files": [], "intro_text": nav.get("intro_text", ""), "nodes": kept}
    return text, view


def _check_names(files: dict):
    for name in files:
        low = name.replace("\\", "/").lower()
        if any(part.lower() in low for part in FORBIDDEN_NAME_PARTS) or low.startswith(("/", "..")) or "/../" in low:
            raise ViewError(f"file {name!r} may not enter a judge's view")


def otf_program(program_json: Path, system: str, root: Path = ROOT) -> Program:
    """An OTF-Tools program: only the `code` field. `passed`, `mean_f1` and `attempts` carry the native verdict and
    the build history, and are never read. The runtime is the platform package the program runs under."""
    code = json.loads(Path(program_json).read_text(encoding="utf-8"))["code"]
    pkg = "otf_r1" if system.startswith("r1") else "otf"
    src = (Path(root) / "redesign" / pkg) if pkg == "otf_r1" else (Path(root) / "baseline" / "otf-tools-10f5401" / "implementation-1" / pkg)
    runtime = {f"otf_runtime/{pkg}/{p.name}": p.read_text(encoding="utf-8") for p in sorted(src.glob("*.py"))}
    return Program("otf", {"program.py": code}, runtime, pkg)


def _wsl(cmd: str, data: bytes | None = None, timeout: int = 120):
    return subprocess.run(WSL + [cmd], input=data, capture_output=True, timeout=timeout, env={**os.environ, "MSYS_NO_PATHCONV": "1"})


def _safe_wsl_path(path: str):
    if not re.fullmatch(r"[A-Za-z0-9_./$-]+", path) or ".." in path:
        raise ViewError(f"unexpected WSL path {path!r}")


def read_wsl_py(wsl_dir: str) -> dict:
    """Every *.py file under a WSL folder (logs and caches left out), as {relative path: text}."""
    _safe_wsl_path(wsl_dir)
    p = _wsl(f"cd '{wsl_dir}' && find . -type f -name '*.py' -not -path '*/_analysis_logs/*' -not -path '*/__pycache__/*' "
             f"-not -path '*/logs/*' -print0 | sort -z | tar -cf - --null -T -")
    if p.returncode != 0:
        raise ViewError(f"cannot read program at {wsl_dir}: {p.stderr.decode('utf-8', 'replace')[-300:]}")
    out = {}
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as tar:
        for m in tar.getmembers():
            if m.isfile():
                out[m.name.removeprefix("./")] = tar.extractfile(m).read().decode("utf-8", "replace")
    return out


def devs_program(wsl_dir: str, files: dict | None = None) -> Program:
    """A DEVS-Gen program: the generated model files under devs_project/ are shown. run.py, the 1 KB launcher, is
    not shown but is in the sandbox, because the program cannot start without it."""
    files = read_wsl_py(wsl_dir) if files is None else files
    shown = {k: v for k, v in files.items() if k.startswith("devs_project/")}
    runtime = {k: v for k, v in files.items() if k == "run.py"}
    if not shown or not runtime:
        raise ViewError(f"{wsl_dir}: expected run.py and devs_project/*.py")
    return Program("devs_gen", shown, runtime)


def coding_agent_program(folder: str, wsl: bool = True, files: dict | None = None) -> Program:
    """A plain coding agent's program: the one file it writes, run.py (scripts/coding_agent_build.py), shown in
    full. Its build folder also holds the prompt log, example runs and earlier attempts; none of that is read."""
    if files is None:
        if wsl:
            _safe_wsl_path(folder)
            p = _wsl(f"cat '{folder}/run.py'")
            if p.returncode != 0:
                raise ViewError(f"{folder}: no run.py")
            files = {"run.py": p.stdout.decode("utf-8", "replace")}
        else:
            files = {"run.py": (Path(folder) / "run.py").read_text(encoding="utf-8", errors="replace")}
    if set(files) != {"run.py"}:
        raise ViewError(f"{folder}: a coding-agent program is run.py alone, got {sorted(files)}")
    return Program("coding_agent", dict(files))


OTF_NOTE = """HOW ITS PLATFORM RUNS THIS PROGRAM (OTF-Tools)
The document is loaded as `doc`, a dict {{"nodes": [...]}}. Each node has node_id, title, level, children, and kind
"table" (table: columns, rows), "list" (lines) or "text" (text). A top-level node with children is a scope (here, the
run). The platform defines the helpers node_by_title, node_by_id, children, scope_nodes, table_rows and Reader, then
calls the program's functions. entities, recorded_end, inputs, outcomes and (if defined) params read one scope's
records. simulate(doc, scope, inputs, params, start, horizon) returns the outcome records after `start`. The platform
calls simulate with `start` just before the scope's first recorded outcome, on a copy of the document in which that
scope's outcomes after `start` are hidden, with horizon {horizon}.
To answer a what-if question, the change is written into the document (a planned value in the scope's tables, a
number in the front matter's stated rules, or the removal of rows) or into the constants params() returns. simulate
is then run as above, and the answer is read from the records it returns."""

STDIN_NOTE = """HOW ITS PLATFORM RUNS THIS PROGRAM ({platform})
`python run.py --horizon {horizon}`, with one JSON object on standard input. It prints one JSON record per line.
To answer a what-if question, the change is written into that input object. The program is then run as above, and
the answer is read from the records it prints.
{spec}"""


def stdin_spec(task: str, root: Path = ROOT) -> str:
    """The input and output format section of the shared task spec, without its long example."""
    text = (Path(root) / "adapters" / "generic_tasks" / task / "spec.md").read_text(encoding="utf-8")
    m = re.search(r"^## Command line, input and output\s*$", text, flags=re.M)
    if not m:
        raise ViewError(f"task spec for {task} has no input format section")
    section = text[m.end():]
    nxt = re.search(r"^## ", section, flags=re.M)
    if nxt:
        section = section[:nxt.start()]
    section = re.sub(r"^Example input[^\n]*\n```json\n.*?\n```\n", "", section, flags=re.S | re.M)
    return section.strip()


def platform_note(program: Program, nav: dict, horizon, root: Path = ROOT) -> str:
    if program.platform == "otf":
        return OTF_NOTE.format(horizon=horizon)
    front = next((n for n in nav["nodes"] if n.get("level") == 0 and n["kind"] == "list"), None)
    task = TASKS.get(front["title"] if front else "")
    if task is None:
        raise ViewError("no task spec for this document")
    name = "DEVS-Gen" if program.platform == "devs_gen" else "a plain coding agent"
    return STDIN_NOTE.format(platform=name, horizon=horizon, spec=stdin_spec(task, root))


def _plain(x):
    """Dataclasses, request objects and containers as plain JSON values, with None fields dropped."""
    if is_dataclass(x) and not isinstance(x, type):
        x = asdict(x)
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items() if v is not None}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    return x


def make_view(nav: dict, scope: str, program: Program, horizon, question: str | None = None, request=None,
              answer_changed=None, answer_factual=None, stdin: dict | None = None, root: Path = ROOT) -> View:
    """The only way a view is built. `nav` is the question document's map; only its front matter and the chapter
    `scope` are kept. `request` is the interpreted request (a dict or dataclass), never a hidden binding."""
    _check_names(program.shown)
    _check_names(program.runtime)
    size = sum(len(v) for v in program.shown.values())
    if size > PROGRAM_CHAR_LIMIT:
        raise ViewError(f"program view is {size} characters, above the limit of {PROGRAM_CHAR_LIMIT}")
    text, view_nav = document_view(nav, scope)
    return View(text, view_nav, scope, program, platform_note(program, nav, horizon, root), horizon,
                question, None if request is None else _plain(request), answer_changed, answer_factual, stdin)


# ---------------------------------------------------------------- prompts
EPHEMERAL = {"type": "ephemeral"}
VERDICT_FORMAT = """VERDICT: TRUST or DECLINE
CONFIDENCE: a whole number from 0 to 100: your probability that {what} (so a low number when you decline)
REASON: one line"""

DOCUMENT_HEAD = "DOCUMENT (its front matter: the process rules and stated policy; then the records of one run)\n\n"
PROGRAM_HEAD = "PROGRAM (a simulator that was generated for this document's process)\n\n"

ANSWER_TASK = """You are judging whether to trust an answer that the program above gave to a what-if question about the run in the document above.

QUESTION
{question}

THE QUESTION AS A STRUCTURED REQUEST (made from the question text by a separate step, and used to run the program)
{request}

THE PROGRAM'S ANSWER
With the change: {changed}
Without the change (the program's own run of the recorded inputs): {factual}

Decide whether the program's answer with the change is exactly right for the question."""

ANSWER_END = """
End your reply with these three lines:
""" + VERDICT_FORMAT.format(what="the answer with the change is exactly right")

PROGRAM_TASK = """You are judging whether to trust the program above to answer what-if questions about the run in the document above ({scope}). A what-if question changes something about the run's inputs or stated rules and asks what one of its recorded outcomes would then have been.

Decide whether the program's answers to such questions about this run would be exactly right.

End your reply with these three lines:
""" + VERDICT_FORMAT.format(what="the program's answers to such questions about this run are exactly right")

REACT_TOOL = """
You have one tool, run_code(python). It runs a Python snippet in a sandbox and returns what it printed (standard output and standard error, cut to {obs_chars} characters). The sandbox has no network. Each snippet runs as a new process with the working directory {sbx}; files you write there stay for later snippets. It holds only:
{layout}
- .rt/: the tool's own files (your snippets).
You may run the program however you like, change its inputs, or not run it at all.

You have at most {turns} turns. Each reply is one turn, and running code uses a turn. Your last turn must be your verdict.

To run code, reply in exactly this form and then stop:
Thought: <your reasoning>
Action: run_code
```python
<code>
```
The result comes back under a line "Observation:".

When you have decided, reply in exactly this form:
Thought: <your reasoning>
""" + VERDICT_FORMAT.format(what="the answer with the change is exactly right") + """

Your transcript so far follows. Continue it with your next reply.

"""

OTF_LAYOUT = """- document/document.txt: the document text shown above; document/navmap.json: the same content as the `doc` map;
- program/program.py: the program shown above;
- otf_runtime/: the platform's own code that runs the program;
- program/otf_run.py: runs the program as its platform does and prints the outcome records, one JSON object per line: `python program/otf_run.py --scope "{scope}" --map document/navmap.json`."""

STDIN_LAYOUT = """- document/document.txt: the document text shown above; document/navmap.json: the same content as a JSON map of its tables;
- document/input.json: this run's recorded inputs in the program's input format;
- program/: {files}. Run it from that folder as its platform does: `python run.py --horizon {horizon} < ../document/input.json`."""

PROMPT_HASH = hashlib.sha256("\x1e".join(
    [OTF_NOTE, STDIN_NOTE, VERDICT_FORMAT, DOCUMENT_HEAD, PROGRAM_HEAD, ANSWER_TASK, ANSWER_END, PROGRAM_TASK, REACT_TOOL,
     OTF_LAYOUT, STDIN_LAYOUT, str(TURN_CAP), str(OBS_CHARS), repr(STOP)]).encode("utf-8")).hexdigest()[:16]


def _program_text(view: View) -> str:
    p = view.program
    parts = [PROGRAM_HEAD + view.note]
    for name in sorted(p.shown):
        parts.append(f"--- file: {name} ---\n{p.shown[name]}")
    return "\n\n".join(parts)


def _show(value) -> str:
    return "no answer" if value is None else json.dumps(value)


def base_blocks(view: View) -> list:
    """Document block, then program block. Each ends in a cache breakpoint, so rows that share a document view
    (or a document view and a program) read them from the cache. Every block carries its own closing blank line:
    the client joins blocks as they are, so every model gets the same text."""
    return [{"type": "text", "text": DOCUMENT_HEAD + view.document.rstrip() + "\n\n", "cache_control": EPHEMERAL},
            {"type": "text", "text": _program_text(view).rstrip() + "\n\n", "cache_control": EPHEMERAL}]


def _answer_task(view: View) -> str:
    return ANSWER_TASK.format(question=view.question, request=json.dumps(view.request, indent=1),
                              changed=_show(view.answer_changed), factual=_show(view.answer_factual))


def answer_prompt(view: View) -> list:
    return [{"role": "user", "content": base_blocks(view) + [{"type": "text", "text": _answer_task(view) + "\n" + ANSWER_END}]}]


def program_prompt(view: View) -> list:
    return [{"role": "user", "content": base_blocks(view) + [{"type": "text", "text": PROGRAM_TASK.format(scope=view.scope)}]}]


def react_prompt(view: View, scratch: list, turn_cap: int = TURN_CAP) -> list:
    p = view.program
    if p.platform == "otf":
        layout = OTF_LAYOUT.format(scope=view.scope)
    else:
        files = "the program files shown above, and its launcher run.py" if p.platform == "devs_gen" else "the program run.py shown above"
        layout = STDIN_LAYOUT.format(files=files, horizon=view.horizon)
    task = _answer_task(view) + "\n" + REACT_TOOL.format(obs_chars=OBS_CHARS, sbx=SBX, layout=layout, turns=turn_cap)
    return [{"role": "user", "content": base_blocks(view) + [{"type": "text", "text": task}] + [{"type": "text", "text": s} for s in scratch]}]


def prompt_text(messages) -> str:
    return "".join(b["text"] for m in messages for b in m["content"])


# ---------------------------------------------------------------- parsing
_LEAD = r"^[ \t>*_#-]*"
_SEP = r"[*_ \t]*:[*_ \t`'\"]*"


def parse_verdict(text: str):
    """(verdict, confidence, reason) from the last VERDICT and CONFIDENCE lines, or None if either is missing or
    the confidence is not a whole number from 0 to 100. An echo of the format line ("TRUST or DECLINE") is not a verdict."""
    text = text or ""
    v = re.findall(_LEAD + r"VERDICT" + _SEP + r"(TRUST|DECLINE)\b(?![ \t]*(?:or|/)[ \t]*(?:TRUST|DECLINE))", text, flags=re.M | re.I)
    c = re.findall(_LEAD + r"CONFIDENCE" + _SEP + r"([0-9]+)(?![0-9]|\.[0-9])", text, flags=re.M | re.I)
    r = re.findall(_LEAD + r"REASON" + _SEP + r"(.*)$", text, flags=re.M | re.I)
    if not v or not c:
        return None
    conf = int(c[-1])
    if not 0 <= conf <= 100:
        return None
    return v[-1].upper(), conf, (r[-1].strip() if r else "")[:300]


def inconsistent(verdict, confidence) -> bool:
    """A verdict that disagrees with its own probability: TRUST below 50, or DECLINE above 50. Recorded, never
    corrected: the verdict and the confidence are both kept as the model gave them."""
    return (verdict == "TRUST" and confidence < 50) or (verdict == "DECLINE" and confidence > 50)


def parse_action(text: str):
    """(text up to and including the Action line, code) of a run_code action, or None. The code is the first fenced
    block after the Action line (or, with no fence, the rest of the reply). Text after that block is ignored."""
    m = re.search(r"^[ \t>*_#-]*Action[*_ \t]*:[*_ \t`]*run_code\b[^\n]*(?:\n|\Z)", text or "", flags=re.M | re.I)
    if not m:
        return None
    rest = text[m.end():]
    fenced = re.search(r"```[A-Za-z0-9_]*[ \t]*\n(.*?)(?:\n```|\Z)", rest, flags=re.S)
    code = fenced.group(1) if fenced else rest
    return (text[:m.end()].rstrip(), code.strip("\n")) if code.strip() else None


def clip(text: str, limit: int = OBS_CHARS) -> str:
    if len(text) <= limit:
        return text
    head, tail = limit * 5 // 8, limit * 3 // 8
    return text[:head] + f"\n... [{len(text) - head - tail} characters cut] ...\n" + text[-tail:]


# ---------------------------------------------------------------- judges
def _cost(calls: list) -> dict:
    good = [c for c in calls if not c.get("failed")]
    return {"model_calls": len(calls), "failed_calls": len(calls) - len(good),
            "usd": round(sum(c.get("usd") or 0.0 for c in calls), 6),
            "prompt_tokens": sum(c.get("prompt_tokens") or 0 for c in good),
            "output_tokens": sum(c.get("output_tokens") or 0 for c in good),
            "cache_read_tokens": sum(c.get("cache_read_tokens") or 0 for c in good),
            "cache_write_tokens": sum(c.get("cache_write_tokens") or 0 for c in good),
            "model_seconds": round(sum(c.get("seconds") or 0.0 for c in calls), 2)}


def _failure_of(text: str, finish) -> str | None:
    if finish == "refusal":
        return "refusal"
    if finish in ("max_tokens", "length"):
        return "cutoff"
    if not (text or "").strip():
        return "unparsable"
    return None


def _result(judge, verdict, confidence, reason, failure, calls, t0, **more) -> dict:
    return {"judge": judge, "prompt_version": PROMPT_VERSION, "prompt_hash": PROMPT_HASH, "verdict": verdict, "confidence": confidence,
            "reason": reason, "failure": failure, "inconsistent": failure is None and inconsistent(verdict, confidence),
            "wall_seconds": round(time.time() - t0, 2), **_cost(calls), **more}


def _declined(judge, failure, calls, t0, **more) -> dict:
    return _result(judge, "DECLINE", LOWEST_CONFIDENCE, f"judge failure: {failure}", failure, calls, t0, **more)


def _single_call(judge: str, client, messages) -> dict:
    t0, n0 = time.time(), len(client.calls)
    text = client.llm(messages, auto_cache=False)
    calls = client.calls[n0:]
    finish = calls[-1].get("finish") if calls else None
    failure = _failure_of(text, finish)
    parsed = None if failure else parse_verdict(text)
    if failure is None and parsed is None:
        failure = "unparsable"
    more = {"turns": 1, "finish": finish, "reply": text or ""}
    if failure:
        return _declined(judge, failure, calls, t0, **more)
    return _result(judge, *parsed, None, calls, t0, **more)


def judge_answer(client, view: View) -> dict:
    """Baseline 2. One call: is the program's answer to this question exactly right?"""
    if view.question is None or view.request is None:
        raise ValueError("the answer-level judge needs the question and the interpreted request")
    return _single_call("answer", client, answer_prompt(view))


def judge_program(client, view: View) -> dict:
    """Baseline 3. One call per (program, run): can this program be trusted for what-if questions on this run?
    The view's question, request and answers are not used."""
    return _single_call("program", client, program_prompt(view))


def judge_react(client, view: View, sandbox, turn_cap: int = TURN_CAP) -> dict:
    """Baseline 4. A text ReAct loop. `sandbox.run(code)` returns {"output", "seconds", ...}; `sandbox.counts()`
    returns what could be counted of the program's executions. Every model reply is one turn."""
    if view.question is None or view.request is None:
        raise ValueError("the ReAct judge needs the question and the interpreted request")
    t0, n0 = time.time(), len(client.calls)
    scratch, transcript, sandbox_seconds = [], [], 0.0

    def done(verdict=None, failure=None, finish=None, **extra):
        calls = client.calls[n0:]
        try:
            counts = sandbox.counts()
        except Exception as e:                          # a paid row is never lost to a bookkeeping failure
            counts = {"program_executions": None, "python_starts": None, "counts_error": f"{type(e).__name__}: {e}"[:200]}
        more = {"turns": len(transcript), "turn_cap": turn_cap, "sandbox_calls": sum(1 for t in transcript if "code" in t),
                "sandbox_seconds": round(sandbox_seconds, 2), **counts, "finish": finish, **extra, "transcript": transcript}
        if failure:
            return _declined("react", failure, calls, t0, **more)
        return _result("react", *verdict, None, calls, t0, **more)

    for turn in range(1, turn_cap + 1):
        n1 = len(client.calls)
        text = client.llm(react_prompt(view, scratch, turn_cap), stop=STOP, auto_cache=True)
        calls = client.calls[n1:]
        finish = calls[-1].get("finish") if calls else None
        step = {"turn": turn, "reply": text, "finish": finish}
        transcript.append(step)
        failure = _failure_of(text, finish)
        if failure:
            return done(failure=failure, finish=finish)
        action = parse_action(text)
        verdict = parse_verdict(text)
        if action is not None and turn == turn_cap:
            # No turn is left to read a result. A verdict in the same reply stands; without one the row is out of turns.
            step["ignored_action"] = True
            if verdict is not None:
                return done(verdict=verdict, finish=finish, last_turn_action_ignored=True)
            return done(failure="out_of_turns", finish=finish)
        if action is not None:                                         # before the last turn, an action wins over a verdict
            head, code = action
            r = sandbox.run(code)
            sandbox_seconds += r.get("seconds") or 0.0
            obs = clip(r["output"])
            step.update({"code": code, "observation": obs, "exit": r.get("exit"), "timed_out": r.get("timed_out"),
                         "sandbox_seconds": r.get("seconds")})
            # anything the model wrote after its code is dropped from the transcript it sees next
            scratch.append(f"{head}\n```python\n{code}\n```\nObservation:\n[turn {turn} of {turn_cap} used]\n{obs}\n\n")
            continue
        if verdict is not None:
            return done(verdict=verdict, finish=finish)
        if turn == turn_cap:
            return done(failure="unparsable", finish=finish)
        step["observation"] = "no action or verdict found"
        scratch.append(f"{text.rstrip()}\nObservation:\n[turn {turn} of {turn_cap} used]\nNo run_code action and no verdict "
                       f"were found in that reply. Reply with an Action or with your verdict, in the form given above.\n\n")
    raise AssertionError("unreachable: every turn returns or continues, and the last turn always returns")


# ---------------------------------------------------------------- sandbox
SITECUSTOMIZE = '''import json, sys
try:
    with open("__SBX__/.rt/starts.jsonl", "a") as _f:
        _f.write(json.dumps({"argv": list(getattr(sys, "orig_argv", []))}) + "\\n")
except Exception:
    pass
'''

EXEC_SH = '''#!/bin/bash
mkdir -p __SBX__/.rt/snippets
n=$(ls __SBX__/.rt/snippets | wc -l)
f=__SBX__/.rt/snippets/snippet_$(printf %02d $((n + 1))).py
cat > "$f"
exec timeout -k 5 __TIMEOUT__ python "$f" < /dev/null
'''

OTF_RUN = '''"""Runs the program as its platform does: read the scope, hide its outcomes after the first one, simulate."""
import argparse, json, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "otf_runtime"))
from __PKG__ import records, sandbox, toolgen  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--scope", required=True)
ap.add_argument("--map", default=str(HERE.parent / "document" / "navmap.json"))
a = ap.parse_args()
HORIZON = __HORIZON__
code = (HERE / "program.py").read_text(encoding="utf-8")
nav = json.loads(Path(a.map).read_text(encoding="utf-8"))
with tempfile.TemporaryDirectory() as tmp:
    m = Path(tmp) / "map.json"
    m.write_text(json.dumps(nav))
    try:
        r = toolgen.read_scope(code, m, a.scope)
    except Exception as e:
        sys.exit(f"read failed: {e}")
    cut = toolgen._cut(r)
    blind = toolgen.blinded_map(nav, m, a.scope, r, cut)
    ok, out = sandbox.run(code, "simulate", blind, [a.scope], {"inputs": r["inputs"], "params": dict(r["params"]), "start": cut, "horizon": HORIZON})
if not ok or not isinstance(out, list):
    sys.exit("simulate failed: " + str(out)[-1500:])
kept = [o for o in r["outcomes"] if cut is not None and records.rtime(o) is not None and records.rtime(o) <= cut]
for o in kept + out:
    print(json.dumps({k: v for k, v in o.items() if k != "src"}, default=str))
'''


def sandbox_files(view: View, timeout_s: int = SANDBOX_TIMEOUT_S) -> dict:
    """Every file of a row's sandbox: the document view, the program with what it needs to run, and the two
    harness's two files (kept in a folder of their own, mounted read-only at /home/rt). Nothing else is ever copied
    in. Names starting with `box/` are the judge's writable folder."""
    p = view.program
    files = {"document/document.txt": view.document, "document/navmap.json": json.dumps(view.nav)}
    if p.platform == "otf":
        files["program/program.py"] = p.shown["program.py"]
        files["program/otf_run.py"] = OTF_RUN.replace("__PKG__", p.package).replace("__HORIZON__", repr(view.horizon))
        files.update(p.runtime)
    else:
        if view.stdin is None:
            raise ViewError("a stdin program's sandbox needs the run's input object")
        files["document/input.json"] = json.dumps(view.stdin)
        for name, text in {**p.shown, **p.runtime}.items():
            files[f"program/{name}"] = text
    _check_names(files)
    files = {f"box/{k}": v for k, v in files.items()}
    files["rt/sitecustomize.py"] = SITECUSTOMIZE.replace("__SBX__", SBX)
    files["rt/exec.sh"] = EXEC_SH.replace("__SBX__", SBX).replace("__TIMEOUT__", str(int(timeout_s)))
    return files


def bwrap(folder: str, inner: str) -> str:
    """The bubblewrap command. Only /usr (read-only), three linker files, the interpreter and the row's folder are
    mounted: no /run (session bus, WSL interop sockets), /var, /mnt or host /home. /usr/lib/wsl (Windows driver
    programs) is covered. New user, PID, IPC, UTS, cgroup and network namespaces, a new session, an empty
    environment. The row's `box` folder is the only writable place besides /tmp and the empty /home; the harness
    is a read-only mount of its own, so a snippet cannot remove its own time limit. Every inherited file descriptor above 2 is closed
    before bubblewrap starts (review 2: the launching terminal's descriptor was otherwise open inside).

    Review 3 (2026-11-10): `--unshare-net` does not cover AF_VSOCK on the WSL2 kernel, so a snippet could open a
    socket to the Windows host. The seccomp filter written by `scripts/make_seccomp_filter.py` (the same file
    `assurance.backends.sandbox_command` uses) refuses socket() and socketpair() for every family except AF_UNIX
    and kills other architectures and the x32 ABI. The closer opens it on descriptor 10 for bubblewrap to read;
    without the filter file the command does not start (exit 97). Soft limits on address space, processes and
    file size keep a snippet from exhausting the WSL VM; they guard against accidents, a program can raise them."""
    _safe_wsl_path(folder)
    if '"' in inner or "'" in inner or "$" in inner or "`" in inner or "\\" in inner:
        raise ValueError(f"unexpected sandbox command {inner!r}")
    closer = (f"{VENV}/bin/python -c 'import os, sys; os.closerange(3, 65536); fd = os.open(sys.argv[1], os.O_RDONLY); "
              f"os.dup2(fd, 10); os.close(fd); os.execv(sys.argv[2], sys.argv[2:])' {BPF}")
    inner = f'/bin/bash -c "ulimit -S {LIMITS} && exec {inner}"'
    return (f"[ -s {BPF} ] || {{ echo 'the seccomp filter is missing: run scripts/make_seccomp_filter.py in WSL' >&2; exit 97; }}; "
            f"{closer} {BW} --seccomp 10 --ro-bind /usr /usr --symlink usr/lib /lib --symlink usr/lib64 /lib64 --symlink usr/bin /bin --symlink usr/sbin /sbin "
            f"--ro-bind-try /etc/ld.so.cache /etc/ld.so.cache --ro-bind-try /etc/ld.so.conf /etc/ld.so.conf "
            f"--ro-bind-try /etc/ld.so.conf.d /etc/ld.so.conf.d $([ -d /usr/lib/wsl ] && echo --tmpfs /usr/lib/wsl) "
            f"--proc /proc --dev /dev --tmpfs /tmp --tmpfs /home --ro-bind {VENV} {VENV} --ro-bind-try {PY_HOME} {PY_HOME} "
            f"--bind {folder}/box {SBX} --ro-bind {folder}/rt {RT} --unshare-all --die-with-parent --new-session --clearenv "
            f"--setenv PATH {VENV}/bin:/usr/bin:/bin --setenv HOME {SBX} --setenv PYTHONPATH {RT} "
            f"--setenv PYTHONDONTWRITEBYTECODE 1 --setenv LANG C.UTF-8 --chdir {SBX} {inner}")


def count_executions(platform: str, starts: list) -> int:
    """Program executions that can be counted: starts of the platform's entry point. A snippet that imports the
    program and calls it in its own process is not seen, so this is a lower bound. The log is written by the
    processes inside the sandbox, in the row's writable folder, so it is a record, not a tamper-proof meter."""
    n = 0
    for argv in starts:
        names = [str(a).replace("\\", "/") for a in argv]
        if platform == "otf":
            n += any(a.rsplit("/", 1)[-1] == "otf_run.py" for a in names)
        elif platform == "devs_gen":
            n += any(re.match(r"(.*/)?devs_project[./]run_", a) for a in names)
        else:
            n += any(a.rsplit("/", 1)[-1] == "run.py" for a in names)
    return n


class WslSandbox:
    """One row's sandbox: a fresh folder in WSL, removed on close. Each `run` is one bubblewrap process."""

    def __init__(self, view: View, timeout_s: int = SANDBOX_TIMEOUT_S):
        self.platform, self.timeout_s = view.program.platform, timeout_s
        self.id = uuid.uuid4().hex
        self.folder = f"{SBX_BASE}/{self.id}"
        self.log = []
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for name, text in sorted(sandbox_files(view, timeout_s).items()):
                data = text.replace("\r\n", "\n").encode("utf-8")
                info = tarfile.TarInfo(name)
                info.size, info.mode, info.mtime = len(data), 0o644, int(time.time())
                tar.addfile(info, io.BytesIO(data))
        p = _wsl(f"[ -s {BPF} ] || {{ echo 'the seccomp filter {BPF} is missing: run scripts/make_seccomp_filter.py in WSL' >&2; exit 97; }}; "
                 f"mkdir -p {self.folder} && tar -xf - -C {self.folder}", buf.getvalue())
        if p.returncode != 0:
            raise RuntimeError(f"cannot create the sandbox: {p.stderr.decode('utf-8', 'replace')[-300:]}")

    def run(self, code: str) -> dict:
        t0 = time.time()
        timed_out = False
        try:
            p = _wsl(bwrap(self.folder, f"bash {RT}/exec.sh"), code.replace("\r\n", "\n").encode("utf-8"),
                     timeout=self.timeout_s + 30)
            out, err, rc = p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace"), p.returncode
        except subprocess.TimeoutExpired as e:
            out, err, rc, timed_out = (e.stdout or b"").decode("utf-8", "replace"), (e.stderr or b"").decode("utf-8", "replace"), None, True
        elapsed = time.time() - t0
        if rc in (124, 137) and elapsed >= self.timeout_s - 1:      # `timeout` exits 124, or 137 after its kill
            timed_out = True
        text = out
        if err.strip():
            text += ("\n" if text and not text.endswith("\n") else "") + "[standard error]\n" + err
        if timed_out:
            text += f"\n[stopped: the snippet ran longer than {self.timeout_s} seconds]"
        elif rc not in (0, None):
            text += f"\n[exit code {rc}]"
        if not text.strip():
            text = "[no output]"
        r = {"output": text, "exit": rc, "timed_out": timed_out, "seconds": round(elapsed, 2)}
        self.log.append({k: v for k, v in r.items() if k != "output"} | {"output_chars": len(text)})
        return r

    def read(self, name: str) -> str:
        """A file of the sandbox folder, read from outside (harness use: never offered to the judge)."""
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", name) or ".." in name:
            raise ValueError(name)
        path = f"{self.folder}/box/{name}"               # a link is never followed: a snippet could point it outside
        return _wsl(f"test -f {path} -a ! -L {path} && cat {path} 2>/dev/null").stdout.decode("utf-8", "replace")

    def counts(self) -> dict:
        starts = []
        for line in self.read(".rt/starts.jsonl").splitlines():
            try:
                starts.append(json.loads(line)["argv"])
            except (ValueError, KeyError, TypeError):
                pass
        return {"program_executions": count_executions(self.platform, starts), "python_starts": len(starts),
                "sandbox_log": list(self.log)}

    def close(self):
        if re.fullmatch(r"[0-9a-f]{32}", self.id):
            _wsl(f"rm -rf {SBX_BASE}/{self.id}")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _canon_records(lines) -> list:
    out = []
    for line in lines:
        if isinstance(line, str):
            try:
                line = json.loads(line)
            except ValueError:
                continue
        if isinstance(line, dict):
            out.append(json.dumps({k: v for k, v in line.items() if k != "src"}, sort_keys=True, default=str))
    return out


def sandbox_matches_platform(view: View, platform_records: list | None, sandbox_factory=None) -> dict:
    """Does the program's factual run inside the sandbox (through the entry point the prompt names) give the same
    records as the platform's factual run outside it? The interpreters differ (WSL Python 3.10 inside), and the
    sandbox document is the one-chapter view, so this is checked and recorded per program and run, not assumed."""
    if view.program.platform == "otf":
        code = (f"import subprocess\np = subprocess.run(['python', 'program/otf_run.py', '--scope', {view.scope!r}, '--map', 'document/navmap.json'], "
                "capture_output=True, text=True)\nopen('.rt/parity.jsonl', 'w').write(p.stdout)\nprint('RC', p.returncode)\n")
    else:
        code = (f"import subprocess\np = subprocess.run(['python', 'run.py', '--horizon', '{view.horizon}'], stdin=open('document/input.json'), "
                "capture_output=True, text=True, cwd='program')\nopen('.rt/parity.jsonl', 'w').write(p.stdout)\nprint('RC', p.returncode)\n")
    with (sandbox_factory or WslSandbox)(view) as sb:
        r = sb.run(code)
        got = _canon_records(sb.read(".rt/parity.jsonl").splitlines())
    ran = "RC 0" in r["output"]
    if platform_records is None:
        return {"same": not ran, "platform_ran": False, "sandbox_ran": ran}
    want = _canon_records(platform_records)
    return {"same": ran and got == want, "platform_ran": True, "sandbox_ran": ran, "records": len(want), "sandbox_records": len(got)}


# ---------------------------------------------------------------- the shared subset
def subset(rows: list, n: int, seed: int) -> list:
    """Row ids of the shared random subset (decision 5): drawn from row ids only, stratified by cohort and family,
    with a fixed seed. `rows` are dicts with `row_id`, `cohort` and `family`; nothing else is read, so no label can
    enter. Each stratum's share is proportional (largest remainders); within a stratum, rows are taken in the order
    of sha256(seed, row id). A row id must appear once."""
    def h(s):
        return hashlib.sha256(f"{seed}|{s}".encode()).hexdigest()
    strata, seen = {}, set()
    for r in rows:
        if r["row_id"] in seen:
            raise ValueError(f"row id {r['row_id']!r} appears twice")
        seen.add(r["row_id"])
        strata.setdefault((str(r["cohort"]), str(r["family"])), []).append(r["row_id"])
    total = len(seen)
    n = min(n, total)
    if n <= 0:
        return []
    exact = {k: n * len(v) / total for k, v in strata.items()}
    take = {k: int(x) for k, x in exact.items()}
    left = n - sum(take.values())
    for k in sorted(strata, key=lambda k: (-(exact[k] - take[k]), h("stratum|" + "|".join(k))))[:left]:
        take[k] += 1
    out = []
    for k in sorted(strata):
        out += sorted(strata[k], key=h)[:take[k]]
    return sorted(out)


# D27 (Ashraf, 2026-11-10): the judges run on nested stratified subsets of the answered rows. Each subset is drawn
# from the one before it, so every judge sees the last one.
SUBSET_SIZES = (("answer_haiku", 3000), ("react_haiku", 1000), ("answer_sonnet", 150))
SUBSET_SEED = 20261110


def draw_subsets(rows: list, sizes=SUBSET_SIZES, seed: int = SUBSET_SEED) -> dict:
    """{name: row ids}, each drawn by `subset` from the rows of the one before. The hash order within a stratum is
    the same at every level, so the subsets are nested."""
    pool, out = list(rows), {}
    for name, n in sizes:
        ids = subset(pool, n, seed)
        out[name] = ids
        keep = set(ids)
        pool = [r for r in pool if r["row_id"] in keep]
    return out


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- rows from the main runner's outputs
def read_jsonl(path: Path) -> list:
    """Rows of a JSON-lines file. A line that does not decode (a half-written last line of a run in progress) is skipped."""
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def append(path: Path, row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def shard_of(qset: str, doc: str, scope, n: int) -> int:
    """Which of n parts a (set, document, run) belongs to. Fixed by a hash, so it is the same in every process."""
    return int(hashlib.sha256(f"{qset}|{doc}|{scope}".encode("utf-8")).hexdigest(), 16) % n


def cohort_of(name: str) -> str:
    """Platform cohort of a program name: otf/<system>/<builder>, devs/<builder>, agent/<builder>."""
    parts = name.split("/")
    return "/".join(parts[:3]) if parts[0] == "otf" else "/".join(parts[:2])


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def answered_rows(root: Path, qsets) -> list:
    """Rows of main-run sets where a program gave an answer (rule A), from `runs/main_v1/<set>/programs/*.jsonl`:
    the interpreted request source, programs that are not native-only, a structured run that ended with an answer.
    Each row carries only its id (`set|program|question`) and the three stratum labels: process, cohort and the
    question's family. Nothing about correctness is read."""
    import main_runner as mr
    out, seen = [], set()
    for s in qsets:
        family = {q["id"]: q["family"] for q in mr.questions(root, s)}
        for p in mr.programs_list(root):
            if p["native_only"]:
                continue
            for r in read_jsonl(mr.OUT / s / "programs" / f"{_safe(p['name'])}.jsonl"):
                st = r.get("structured") or {}
                rid = f"{s}|{p['name']}|{r.get('question')}"
                if r.get("source") == "interpreted" and st.get("status") == "ran" and st.get("answer") is not None \
                        and r.get("question") in family and rid not in seen:
                    seen.add(rid)
                    out.append({"row_id": rid, "set": s, "program": p["name"], "question": r["question"], "process": p["process"],
                                "cohort": f"{p['process']}|{cohort_of(p['name'])}", "family": family[r["question"]]})
    return out


def freeze_subsets(root: Path, qsets, path: Path, sizes=SUBSET_SIZES, seed: int = SUBSET_SEED) -> dict:
    """Draw the D27 subsets from the answered rows of these sets and store the ids with their sha256. The file has
    no timestamp, so the same inputs always give the same bytes; a sidecar `.sha256` holds the file's hash and the
    time of the draw. An existing file is never overwritten: the draw is redone and compared, and a difference is
    an error (the population changed after the freeze)."""
    rows = answered_rows(root, qsets)
    drawn = draw_subsets(rows, sizes, seed)
    count = {}
    for r in rows:
        count[r["cohort"]] = count.get(r["cohort"], 0) + 1
    doc = {"what": "judge subsets of the main run (D27): row ids set|program|question, drawn before any judging",
           "seed": seed, "sets": list(qsets), "stratified_by": ["process", "cohort", "family"], "nested": [n for n, _ in sizes],
           "population": {"rule": "answered rows only: interpreted source, structured run with an answer, program not native-only",
                          "rows": len(rows), "sha256": _sha("\n".join(sorted(r["row_id"] for r in rows))),
                          "by_set": {s: sum(r["set"] == s for r in rows) for s in qsets}, "by_process_and_cohort": dict(sorted(count.items()))},
           "subsets": {name: {"asked": n, "n": len(drawn[name]), "sha256": _sha("\n".join(drawn[name])), "ids": drawn[name]} for name, n in sizes}}
    text = json.dumps(doc, indent=1, sort_keys=True) + "\n"
    side = path.with_name(path.name + ".sha256")
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise SystemExit(f"{path} exists and a fresh draw differs from it: the answered rows changed after the draw. Nothing was written.")
        return {"status": "unchanged", "file_sha256": _sha(text), **{k: v["n"] for k, v in doc["subsets"].items()}, "population": len(rows)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    side.write_text(f"{_sha(text)}  {path.name}  drawn {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n", encoding="utf-8")
    return {"status": "written", "file_sha256": _sha(text), **{k: v["n"] for k, v in doc["subsets"].items()}, "population": len(rows)}


def load_subset(path: Path, name: str) -> tuple[set, str]:
    """(row ids, file sha256) of one frozen subset. The file must still match its own recorded hashes."""
    text = path.read_text(encoding="utf-8")
    doc = json.loads(text)
    sub = doc["subsets"][name]
    if _sha("\n".join(sub["ids"])) != sub["sha256"]:
        raise SystemExit(f"{path}: subset {name} does not match its sha256")
    side = path.with_name(path.name + ".sha256")
    if side.exists() and side.read_text(encoding="utf-8").split()[0] != _sha(text):
        raise SystemExit(f"{path} does not match {side.name}")
    return set(sub["ids"]), _sha(text)


class Rows:
    """Views for the (program, question) rows of one main-run question set, from the main runner's own outputs:
    its interpretation of each question (the request the gate gets) and, where its program rows exist, the
    structured answer that is scored. Where they do not exist yet, the answer is computed by the same adapter call
    (`structured`), which is deterministic. The answer without the change is the program's own factual run."""

    def __init__(self, root: Path, qset: str):
        import main_runner as mr
        self.root, self.qset, self.mr = root, qset, mr
        self.split = mr.SETS[qset][2]
        # Question rows are cut down at once to id, document, text and the family label (stratification only).
        self.questions = [{"id": q["id"], "doc": q["doc"], "question": q["question"], "family": q["family"]} for q in mr.questions(root, qset)]
        self.interp = {r["key"]: r["raw"] for r in read_jsonl(mr.OUT / qset / "interpret.jsonl") if "raw" in r}
        self.programs = [p for p in mr.programs_list(root) if not p["native_only"]]
        self._navs, self._ctx, self._progs, self._rows, self._reqs = {}, {}, {}, {}, {}

    def nav(self, doc):
        if doc not in self._navs:
            self._navs[doc] = self.mr.split_nav(self.root, doc, self.split)
        return self._navs[doc]

    def request(self, q):
        """(request, schema, adapter) of a question, from the main runner's interpretation. None if it has none or it does not parse."""
        if q["id"] not in self._reqs:
            ad = self.mr.adapter(self.mr.process_of(q["doc"]))
            schema = ad.schema(self.nav(q["doc"]))
            req = None
            if q["id"] in self.interp:
                try:
                    req = ad.parse(self.interp[q["id"]], schema)
                except Exception:
                    req = None
            self._reqs[q["id"]] = (req, schema, ad)
        return self._reqs[q["id"]]

    def scope(self, q):
        req, schema, ad = self.request(q)
        return req.scope if req is not None and ad.scope_ok(req, schema) else None

    def pairs(self):
        for p in self.programs:
            for q in self.questions:
                if self.mr.process_of(q["doc"]) == p["process"]:
                    yield p, q

    def program(self, prog) -> Program:
        if prog["name"] not in self._progs:
            if prog["backend"] == "otf":
                self._progs[prog["name"]] = otf_program(Path(prog["path"]), prog["system"].replace("_claude", ""), self.root)
            elif prog["name"].startswith("agent/"):
                self._progs[prog["name"]] = coding_agent_program(prog["dir"])
            else:
                self._progs[prog["name"]] = devs_program(prog["dir"])
        return self._progs[prog["name"]]

    def scored_row(self, prog, q):
        if prog["name"] not in self._rows:
            self._rows[prog["name"]] = {r["key"]: r for r in read_jsonl(self.mr.OUT / self.qset / "programs" / f"{_safe(prog['name'])}.jsonl") if "key" in r}
        return self._rows[prog["name"]].get(f"{q['id']}|interpreted")

    def program_runs(self):
        """Every (program, document, chapter) of this set: each program on each chapter of its process's documents."""
        docs = sorted({q["doc"] for q in self.questions})
        for p in self.programs:
            for doc in docs:
                if self.mr.process_of(doc) != p["process"]:
                    continue
                for n in self.nav(doc)["nodes"]:
                    if n.get("level") == 0 and n["kind"] != "list":
                        yield p, doc, n["title"]

    def program_view(self, prog, doc: str, scope: str) -> View:
        """The view of a program on one chapter, with no question, request or answer (the program-level judge)."""
        from assurance.backends import HORIZON
        nav = self.nav(doc)
        horizon = HORIZON
        if self.mr.is_mlsys(prog["process"]):
            ad = self.mr.adapter(prog["process"])
            key = (prog["name"], doc)
            if key not in self._ctx:
                schema = ad.schema(nav)
                backend = ad.backend(prog, self.root, nav, schema)
                self._ctx[key] = (backend, ad.runner(backend, nav, schema))
            horizon = self._ctx[key][0].horizon(scope)
        return make_view(nav, scope, self.program(prog), horizon, root=self.root)

    def view(self, prog, q) -> tuple[View, dict]:
        """(view, info). `info` says where the answer came from, or why there is none, and holds the platform's
        factual records for the sandbox check."""
        from assurance.backends import HORIZON
        mr = self.mr
        req, schema, ad = self.request(q)
        if req is None:
            raise ViewError("no interpreted request for this question")
        nav = self.nav(q["doc"])
        ml = mr.is_mlsys(prog["process"])
        key = (prog["name"], q["doc"])
        if key not in self._ctx:
            backend = ad.backend(prog, self.root, nav, schema)
            self._ctx[key] = (backend, ad.runner(backend, nav, schema))
        backend, runner = self._ctx[key]
        c = ad.validate(req, schema)
        info = {"contract": c.status, "scope": req.scope}
        changed = factual = stdin = horizon = None
        if ad.scope_ok(req, schema):
            row = self.scored_row(prog, q)
            if row is not None:
                st = row.get("structured") or {}
                info.update({"answer_source": "main run row", "structured": st.get("status")})
                changed = st.get("answer") if st.get("status") == "ran" else None
            elif c.ok:
                try:
                    st = ad.structured(runner, req)
                except Exception as e:
                    st = {"status": f"error {type(e).__name__}: {e}"[:200]}
                info.update({"answer_source": "computed (no main run row yet)", "structured": st.get("status")})
                changed = st.get("answer") if st.get("status") == "ran" else None
            try:
                base = runner.base(req.scope)
                if base is not None and base.status == "ran":
                    factual = ad.M.answer(req.query, base.case_ends["canon"])[0] if ml else ad.answer.answer(req.query, base.case_ends)[0]
                    info["platform_records"] = base.records
                else:
                    info["factual"] = getattr(base, "status", "none")
            except Exception as e:
                info["factual"] = f"error {type(e).__name__}: {e}"[:200]
            horizon = backend.horizon(req.scope) if ml else HORIZON
            if prog["backend"] != "otf":
                stdin = ad.M.inputs_from_schema(schema, req.scope) if ml else backend.stdin_from_map(nav, req.scope)
        view = make_view(nav, req.scope, self.program(prog), horizon, q["question"], req, changed, factual, stdin, self.root)
        return view, info


def judge_row(judge: str, client, view: View, sandbox_factory=WslSandbox) -> dict:
    """One judgment. Answer-level and ReAct rows without an answer are not judged (rule A: a row with no answer is
    Can't express whatever a judge says), and cost nothing."""
    if judge in ("answer", "react") and view.answer_changed is None:
        return {"judge": judge, "prompt_version": PROMPT_VERSION, "prompt_hash": PROMPT_HASH, "status": "no_answer", "verdict": None,
                "confidence": None, "reason": "the program produced no answer", "failure": None, "model_calls": 0, "usd": 0.0}
    if judge == "answer":
        r = judge_answer(client, view)
    elif judge == "program":
        r = judge_program(client, view)
    elif judge == "react":
        with sandbox_factory(view) as sandbox:
            r = judge_react(client, view, sandbox)
    else:
        raise ValueError(f"unknown judge {judge}")
    return {"status": "judged", **r}


# ---------------------------------------------------------------- runs
def run(root: Path, qsets: tuple, model: str, judges: tuple, out: Path, max_usd: float, n_rows: int | None = None,
        subset_n: int | None = None, name_filter: str | None = None, only_rows: set | None = None,
        claude_only: bool = True, seed: int = 20261110, subsets_file: Path | None = None, subset_name: str | None = None,
        all_program_runs: bool = False, shard: tuple | None = None):
    """Judge rows of main-run question sets. Resumable: a finished judgment is never repeated.

    Which rows:
    - `subsets_file` and `subset_name` (the main run, D27): exactly the rows of that frozen subset, of any cohort.
      Each judgment records the subset's name and the file's sha256.
    - `n_rows` (the smoke run): draw that many rows with an answer, round-robin over (cohort, process) strata in a
      fixed hash order. `subset_n` or `only_rows` then keep a part of them.
    - neither: every row of the sets.
    The program-level judge takes one (program, run) per run that its rows name; with `all_program_runs` it takes
    every program on every chapter of the sets' documents instead, and needs no rows.
    Spend is read from the call ledgers by this run's tag and checked against `max_usd` before every row.

    `shard` = (k, n) keeps the rows whose (set, document, run) falls in part k of n, and writes to files of its own,
    so n processes can run side by side. A document view stays within one shard, which keeps its cache shared.
    All shards of one output folder share the folder's spending limit."""
    sys.path[:0] = [str(root), str(root / "scripts")]
    sys.dont_write_bytecode = True
    import b0_build_test as bt
    env = bt.load_env(root / ".env")
    folder = root / "runs" / "build_test_judges"
    client = bt.Client(model, env, bt.Ledger(folder, model), max_output=bt.MAX_OUTPUT_PER_QUESTION)
    tag = f"judges/{out.name}/"

    def spent():
        total = 0.0
        for p in folder.glob("calls_*.jsonl"):
            total += sum(c.get("usd") or 0.0 for c in read_jsonl(p) if str(c.get("build") or "").startswith(tag))
        return total

    def check_budget():
        s = spent()
        if s >= max_usd:
            raise bt.CapReached(f"this run's spend {s:.2f} reached its limit of {max_usd:.2f}")

    def h(s):
        return hashlib.sha256(f"{seed}|{s}".encode()).hexdigest()

    sets = {s: Rows(root, s) for s in qsets}
    by_prog = {(s, p["name"]): p for s, rows in sets.items() for p in rows.programs}
    by_q = {(s, q["id"]): q for s, rows in sets.items() for q in rows.questions}

    def wanted(p):
        return not ((claude_only and "claude" not in p["name"] and not p["name"].startswith(("devs/haiku", "devs/sonnet")))
                    or (name_filter and name_filter not in p["name"]))

    def cand(s, p, q):
        return {"row_id": f"{p['name']}|{q['id']}", "set": s, "program": p["name"], "question": q["id"], "cohort": cohort_of(p["name"]),
                "process": p["process"], "family": q["family"], "doc": q["doc"], "scope": sets[s].scope(q)}

    frozen = None
    if subsets_file is not None:
        ids, frozen = load_subset(subsets_file, subset_name)
        claude_only, cands, missing = False, [], []
        for rid in sorted(ids):
            s, prog, qid = rid.split("|")
            if (s, prog) in by_prog and (s, qid) in by_q:
                cands.append(cand(s, by_prog[(s, prog)], by_q[(s, qid)]))
            else:
                missing.append(rid)
        if missing:
            raise SystemExit(f"{len(missing)} rows of subset {subset_name} are not in sets {qsets} (first: {missing[0]})")
    elif all_program_runs and judges == ("program",):
        cands = []                                           # the program-level judge on every chapter needs no rows
    else:
        cands = [cand(s, p, q) for s, rows in sets.items() for p, q in rows.pairs() if wanted(p)]
    views = {}

    def get_view(r):
        if r["row_id"] not in views:
            views.clear()                                    # one view in memory at a time; runners are cached in Rows
            try:
                views[r["row_id"]] = sets[r["set"]].view(by_prog[(r["set"], r["program"])], by_q[(r["set"], r["question"])])
            except ViewError as e:
                views[r["row_id"]] = (None, {"view_error": str(e)[:300]})
        return views[r["row_id"]]

    picked_path = out / "rows.jsonl"
    picked = read_jsonl(picked_path)
    try:
        if n_rows is not None:
            # The smoke draw: round-robin over strata until n_rows rows have an answer. Rows without one stay in the record.
            strata = {}
            for r in cands:
                strata.setdefault((r["cohort"], r["process"]), []).append(r)
            for k in strata:
                strata[k].sort(key=lambda r: h(r["row_id"]))
            order = sorted(strata, key=lambda k: h("stratum|" + "|".join(k)))
            seen = {r["row_id"] for r in picked}
            pos = {k: 0 for k in order}
            while sum(r["has_answer"] for r in picked) < n_rows and any(pos[k] < len(strata[k]) for k in order):
                for k in order:
                    if sum(r["has_answer"] for r in picked) >= n_rows:
                        break
                    while pos[k] < len(strata[k]):
                        r = strata[k][pos[k]]
                        pos[k] += 1
                        if r["row_id"] in seen:
                            continue
                        view, info = get_view(r)
                        row = {**r, "has_answer": view is not None and view.answer_changed is not None,
                               "info": {a: b for a, b in info.items() if a != "platform_records"}}
                        append(picked_path, row)
                        picked.append(row)
                        seen.add(r["row_id"])
                        print("row", r["row_id"], "answer" if row["has_answer"] else f"no answer {row['info']}", flush=True)
                        if row["has_answer"]:
                            break
            rows = [r for r in picked if r["has_answer"]][:n_rows]
        else:
            rows = cands
        if only_rows is not None:
            rows = [r for r in rows if r["row_id"] in only_rows or f"{r['set']}|{r['row_id']}" in only_rows]
        if subset_n is not None:            # the shared subset for a second model: from row ids, cohort and family only
            keep = set(subset(rows, subset_n, seed))
            rows = [r for r in rows if r["row_id"] in keep]
        # Cache-friendly order: rows that share a document view, then a program, run next to each other.
        rows = sorted(rows, key=lambda r: (r["set"], r["doc"], str(r["scope"]), r["program"], r["question"]))
        part = "" if shard is None else f".s{shard[0]}of{shard[1]}"
        if shard is not None:
            rows = [r for r in rows if shard_of(r["set"], r["doc"], r["scope"], shard[1]) == shard[0]]
        result_path = out / f"judgments_{model}{part}.jsonl"
        have = {r["key"] for p in out.glob(f"judgments_{model}*.jsonl") for r in read_jsonl(p) if "key" in r}     # any shard layout
        parity_path = out / f"sandbox_parity{part}.jsonl"
        parity = {r["key"]: r for p in out.glob("sandbox_parity*.jsonl") for r in read_jsonl(p) if "key" in r}
        for judge in judges:
            todo = rows
            if judge == "program" and all_program_runs:      # every program on every chapter of the sets' documents (D27)
                todo = [{"set": s, "program": p["name"], "doc": doc, "scope": scope, "cohort": cohort_of(p["name"]), "process": p["process"],
                         "question": None, "family": None, "program_run": True}
                        for s, rws in sets.items() for p, doc, scope in rws.program_runs() if wanted(p)]
                todo.sort(key=lambda r: (r["set"], r["doc"], r["scope"], r["program"]))
                if shard is not None:
                    todo = [r for r in todo if shard_of(r["set"], r["doc"], r["scope"], shard[1]) == shard[0]]
            elif judge == "program":        # one judgment per (program, run): every run that a row of this program names
                first = {}
                for r in rows:
                    if r["scope"] is not None:
                        first.setdefault((r["set"], r["program"], r["scope"]), r)
                todo = list(first.values())
            for r in todo:
                rid = f"{r['program']}|{r['scope']}" if judge == "program" else r["row_id"]
                key = f"{judge}|{model}|{r['set']}|{rid}"
                if key in have:
                    continue
                check_budget()
                if r.get("program_run"):
                    try:
                        view, info = sets[r["set"]].program_view(by_prog[(r["set"], r["program"])], r["doc"], r["scope"]), {}
                    except ViewError as e:
                        view, info = None, {"view_error": str(e)[:300]}
                else:
                    view, info = get_view(r)
                meta = {"key": key, "model": model, "set": r["set"], "row_id": rid, "program": r["program"], "doc": r["doc"], "scope": r["scope"],
                        "question": None if judge == "program" else r["question"], "cohort": r["cohort"], "process": r["process"],
                        "family": None if judge == "program" else r["family"]}
                if frozen is not None and judge != "program":
                    meta.update({"subset": subset_name, "subsets_sha256": frozen})
                if view is None:
                    append(result_path, {**meta, "judge": judge, "status": "skipped", "verdict": None, "confidence": None,
                                         "reason": info.get("view_error"), "failure": None, "model_calls": 0, "usd": 0.0})
                    have.add(key)
                    continue
                if judge == "react" and view.answer_changed is not None:
                    pk = f"{r['set']}|{r['program']}|{r['scope']}"
                    if pk not in parity:
                        parity[pk] = {"key": pk, **sandbox_matches_platform(view, info.get("platform_records"))}
                        append(parity_path, parity[pk])
                    meta["sandbox_matches_platform"] = parity[pk]["same"]
                client.build_id = f"{tag}{judge}/{r['set']}/{rid}"
                res = judge_row(judge, client, view)
                append(result_path, {**meta, **res})
                have.add(key)
                print(judge, rid, res.get("verdict"), res.get("confidence"), res.get("failure"), f"turns={res.get('turns')}",
                      f"usd={res.get('usd'):.4f}", flush=True)
    except bt.CapReached as e:
        print("stopped:", e, flush=True)
    kind = "Claude" if model.startswith("claude") else "Ollama"
    print(f"this run's spend so far: ${spent():.4f}; shared {kind} ledger total: ${bt.Ledger(folder, model).spent():.2f}", flush=True)


def _stats(xs: list) -> dict | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    mid = len(xs) // 2
    return {"n": len(xs), "mean": round(sum(xs) / len(xs), 5), "median": xs[mid] if len(xs) % 2 else round((xs[mid - 1] + xs[mid]) / 2, 5),
            "min": xs[0], "max": xs[-1], "total": round(sum(xs), 5)}


def summarize(root: Path, out: Path) -> dict:
    """Cost and turns per judge and model, from a run's judgment files and the call ledgers. No correctness: this
    reads no gold."""
    res = {}
    by_model = {}
    for path in sorted(out.glob("judgments_*.jsonl")):                 # one file per model, or one per model and shard
        for r in read_jsonl(path):
            by_model.setdefault(r.get("model"), []).append(r)
    for rows in by_model.values():
        for judge in JUDGE_NAMES:
            mine = [r for r in rows if r.get("judge") == judge]
            rs = [r for r in mine if r.get("status") == "judged"]
            if not rs:
                continue
            turns = {}
            for r in rs:
                turns[str(r.get("turns"))] = turns.get(str(r.get("turns")), 0) + 1
            tokens = max(1, sum(r["prompt_tokens"] for r in rs))
            s = {"rows": len(rs), "not_judged_no_answer": sum(r.get("status") == "no_answer" for r in mine),
                 "skipped_no_view": sum(r.get("status") == "skipped" for r in mine),
                 "verdicts": {v: sum(r["verdict"] == v for r in rs) for v in ("TRUST", "DECLINE")},
                 "failures": {f: sum(r.get("failure") == f for r in rs) for f in FAILURES if any(r.get("failure") == f for r in rs)},
                 "inconsistent_verdict_and_confidence": sum(bool(r.get("inconsistent")) for r in rs),
                 "confidence": _stats([r["confidence"] for r in rs]), "usd_per_row": _stats([r["usd"] for r in rs]),
                 "model_calls_per_row": _stats([r["model_calls"] for r in rs]), "turns_per_row": _stats([r.get("turns") for r in rs]),
                 "turns_histogram": dict(sorted(turns.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 99)),
                 "prompt_tokens_per_row": _stats([r["prompt_tokens"] for r in rs]), "output_tokens_per_row": _stats([r["output_tokens"] for r in rs]),
                 "cache_read_share": round(sum(r["cache_read_tokens"] for r in rs) / tokens, 3),
                 "cache_write_share": round(sum(r["cache_write_tokens"] for r in rs) / tokens, 3),
                 "wall_seconds_per_row": _stats([r["wall_seconds"] for r in rs])}
            if judge == "react":
                s.update({"sandbox_calls_per_row": _stats([r.get("sandbox_calls") for r in rs]),
                          "program_executions_per_row": _stats([r.get("program_executions") for r in rs]),
                          "sandbox_seconds_per_row": _stats([r.get("sandbox_seconds") for r in rs]),
                          "hit_turn_cap_without_verdict": sum(r.get("failure") == "out_of_turns" for r in rs),
                          "verdict_on_last_turn": sum(r.get("turns") == r.get("turn_cap") and not r.get("failure") for r in rs),
                          "sandbox_differs_from_platform": sum(r.get("sandbox_matches_platform") is False for r in rs),
                          "usd_per_row_by_platform": {p: _stats([r["usd"] for r in rs if r["program"].split("/")[0] == p])
                                                      for p in sorted({r["program"].split("/")[0] for r in rs})}})
            res[f"{judge}|{rows[0]['model']}"] = s
    tag = f"judges/{out.name}/"
    ledger = {}
    for p in sorted((root / "runs" / "build_test_judges").glob("calls_*.jsonl")):
        for c in read_jsonl(p):
            b = str(c.get("build") or "")
            if b.startswith(tag):
                k = f"{b[len(tag):].split('/')[0]}|{p.stem.removeprefix('calls_')}"
                ledger[k] = round(ledger.get(k, 0.0) + (c.get("usd") or 0.0), 6)
    res["ledger_usd"] = {**ledger, "total": round(sum(ledger.values()), 6)}     # every call, including rows that failed midway
    return res


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["smoke", "run", "draw", "summary"])
    ap.add_argument("root")
    ap.add_argument("sets", nargs="?", default="wf_dev,ml_dev")
    ap.add_argument("--subsets", default=None, help="the frozen subsets file (draw writes it; run reads it)")
    ap.add_argument("--subset-name", default=None, help="run: which frozen subset to judge (answer_haiku, react_haiku, answer_sonnet)")
    ap.add_argument("--all-program-runs", action="store_true", help="run: the program-level judge on every program and chapter")
    ap.add_argument("--shard", default=None, help="run: K/N, judge only part K (from 0) of N; one process per part")
    ap.add_argument("--sizes", default=None, help="draw: three sizes instead of 3000,1000,150 (for a small check of the path only)")
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--rows", type=int, default=20, help="smoke: rows with an answer to draw")
    ap.add_argument("--subset", type=int, default=None, help="judge only the shared subset of this size")
    ap.add_argument("--only-rows", default=None, help="a JSON file listing the row ids to judge")
    ap.add_argument("--filter", default=None, help="only programs whose name contains this text")
    ap.add_argument("--all-cohorts", action="store_true", help="also programs built by non-Claude models")
    ap.add_argument("--max-usd", type=float, default=3.0)
    ap.add_argument("--judges", default="answer,program,react")
    ap.add_argument("--out", default="runs/judges_smoke_v1")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    if a.stage == "summary":
        sys.path[:0] = [str(root), str(root / "scripts")]
        print(json.dumps(summarize(root, root / a.out), indent=1))
        return
    sys.path[:0] = [str(root), str(root / "scripts")]
    qsets = tuple(a.sets.split(","))
    if a.stage == "draw":
        if not a.subsets:
            raise SystemExit("give --subsets FILE for a draw")
        sizes = SUBSET_SIZES
        if a.sizes:
            sizes = tuple((name, int(n)) for (name, _), n in zip(SUBSET_SIZES, a.sizes.split(",")))
        print(json.dumps(freeze_subsets(root, qsets, root / a.subsets, sizes), indent=1))
        return
    only = set(json.loads(Path(a.only_rows).read_text(encoding="utf-8"))) if a.only_rows else None
    judges = tuple(a.judges.split(","))
    if any(j not in JUDGE_NAMES for j in judges):
        raise SystemExit(f"judges are {JUDGE_NAMES}")
    if a.stage == "run" and a.out == "runs/judges_smoke_v1":
        raise SystemExit("give --out for a run")
    if bool(a.subsets) != bool(a.subset_name) and not (a.all_program_runs and judges == ("program",)):
        raise SystemExit("--subsets and --subset-name go together")
    run(root, qsets, a.model, judges, root / a.out, a.max_usd, n_rows=a.rows if a.stage == "smoke" else None,
        subset_n=a.subset, name_filter=a.filter, only_rows=only, claude_only=not a.all_cohorts,
        subsets_file=root / a.subsets if a.subsets and a.subset_name else None, subset_name=a.subset_name, all_program_runs=a.all_program_runs,
        shard=tuple(int(x) for x in a.shard.split("/")) if a.shard else None)


if __name__ == "__main__":
    main(sys.argv[1:])
