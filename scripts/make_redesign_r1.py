"""Generate redesign/otf_r1 from the pinned OTF-Tools package, applying generation fixes only.

The pinned clone is read, never changed. Every replacement must match exactly once or the script stops. Both
acceptance checks (check_parsers and check_model) stay byte-identical, and this script verifies that. The fixes
address mechanical failures, where a model breaks the code contract. No fix tells a model about process logic,
and nothing names a domain.

Usage: python -I scripts/make_redesign_r1.py <project_root>
"""
import ast
import difflib
import os
import shutil
import sys

R1_TAG = "r1"

READER_HELPER = '''
class Reader:
    """Reads table cells and list lines and records where each came from. Use one new Reader per record."""
    def __init__(self):
        self.src = []

    def cell(self, node, row_index, column):
        columns = node["table"]["columns"]
        value = node["table"]["rows"][row_index][columns.index(column)]
        self.src.append([node["node_id"], row_index, [column]])
        return value

    def line(self, node, line_index):
        value = node["lines"][line_index]
        self.src.append([node["node_id"], line_index])
        return value
'''

SANDBOX_EDITS = [(
    """    return [(i, dict(zip(cols, r))) for i, r in enumerate(node.get("table", {}).get("rows", []))]
'''""",
    """    return [(i, dict(zip(cols, r))) for i, r in enumerate(node.get("table", {}).get("rows", []))]
""" + READER_HELPER + "'''",
)]

PROMPT_EDITS = [
    # The location rule stated once, unambiguously, where the map schema is described.
    ("""[node_id, row_index, [column names]] (some cells of a row) or [node_id, line_index] (a list line).
{schema}""",
     """[node_id, row_index, [column names]] (some cells of a row) or [node_id, line_index] (a list line).
A record's "src" is ALWAYS a list of locations, even for one: "src": [[node_id, 3]], never "src": [node_id, 3].
Reader() is also defined: it reads a value and records its location. r.cell(node, row_index, column) reads a table
cell, r.line(node, line_index) reads a list line, and r.src is the finished list of locations.
{schema}"""),
    # A pattern that makes src correct by construction.
    ("""`src` lists every location the record was read from, including the cells that give its time and its entities
(an input and an outcome may share such cells, for example the time cell of one row).""",
     """`src` lists every location the record was read from, including the cells that give its time and its entities
(an input and an outcome may share such cells, for example the time cell of one row).
THE SAFE WAY TO FILL src: use one new Reader per record and read every value of that record through it:
    for i, _ in table_rows(node):
        r = Reader()
        time = float(r.cell(node, i, "some time column"))
        amount = float(r.cell(node, i, "some amount column"))
        records.append({{"time": time, "value": amount, "src": r.src}})
Then a function reads only what its src declares, so hiding the outcomes cannot change inputs(). In inputs(), never
read a cell that holds an outcome, not even to skip a row or to find a time, because hidden cells become "". """),
    # Failures come back with the fix for that kind of failure, before the old code.
    ("""YOUR PREVIOUS ATTEMPT (shown below) FAILED THE CHECK. Fix it.
Check result: {report}
Previous code:""",
     """YOUR PREVIOUS ATTEMPT (shown below) FAILED THE CHECK. Fix it.
{hints}Check result: {report}
Previous code:"""),
    ("""PATCH = \"\"\"A question supposes""",
     """SYNTAX_REPAIR = \"\"\"YOUR REPLY CANNOT BE USED: {problem}
{cut_off}Reply with the complete corrected code in one fenced block.\"\"\"

CUT_OFF = \"\"\"The reply appears to have been cut off before the code ended. Write shorter code: no comments, no \
explanation.
\"\"\"

PATCH = \"\"\"A question supposes"""),
]

TOOLGEN_EDITS = [
    ("""import json
import re
from pathlib import Path
""",
     """import ast
import json
import re
from pathlib import Path
"""),
    # Parser failures dominated the pinned build test, so more tries are allowed there.
    ("""                   parser_tries: int = 3, sim_tries: int = 5, n_explore: int = 8, restarts: int = 3,""",
     """                   parser_tries: int = 5, sim_tries: int = 5, n_explore: int = 8, restarts: int = 3,"""),
    # Syntax repair before a try is used, and targeted feedback.
    ("""        code = extract_code(llm([system, {"role": "user", "content": prompts.PARSERS_USER.format(
            context=context, feedback=feedback)}]))
        rep = check_parsers(code, nav, map_path)""",
     """        ask = [system, {"role": "user", "content": prompts.PARSERS_USER.format(context=context, feedback=feedback)}]
        code = _with_syntax_repair(llm, ask, attempts, log)
        rep = check_parsers(code, nav, map_path)"""),
    ("""        feedback = prompts.FEEDBACK.format(report=rep["error"], code=code)""",
     """        feedback = prompts.FEEDBACK.format(hints=_hints(rep["error"]), report=rep["error"], code=code)"""),
    # In the simulator conversation, a cut-off reply or syntax error no longer counts as a submission.
    ("""        if not blocks:
            nudges += 1
            messages.append({"role": "user", "content": "Reply with an ```explore block or a final ```python block."})
            continue""",
     """        if not blocks:
            nudges += 1
            cut = _is_cut_off(reply)
            messages.append({"role": "user", "content": (
                prompts.SYNTAX_REPAIR.format(problem="it has no complete code block.", cut_off=prompts.CUT_OFF) if cut
                else "Reply with an ```explore block or a final ```python block.")})
            continue"""),
    ("""        code = submit[-1]
        full = parsers + "\\n\\n# ---- step 2: forward model ----\\n" + code""",
     """        code = submit[-1]
        problem = _syntax_problem(code)
        if problem and nudges < 6:
            nudges += 1
            log(f"simulate syntax repair: {problem}")
            messages.append({"role": "user", "content": prompts.SYNTAX_REPAIR.format(problem=problem, cut_off="")})
            continue
        full = parsers + "\\n\\n# ---- step 2: forward model ----\\n" + code"""),
    # New helpers, placed before the generator.
    ("""def generate_model(llm, nav: dict, map_path: Path, max_tries: int = 3, log=None,""",
     """FEEDBACK_HINTS = [
    ("bad src", "HOW TO FIX: each record's src must be a list of locations, for example \\"src\\": [[node_id, 3]]. Build it "
                "with Reader: r = Reader(); value = r.cell(node, i, column); record[\\"src\\"] = r.src."),
    ("reads differently once the outcomes are hidden",
     "HOW TO FIX: inputs() used a cell its src does not list. Read every value of each input through one Reader, and "
     "never use outcome cells to decide which rows to read."),
    ("fails on the copy in which the outcomes are hidden",
     "HOW TO FIX: inputs() read a hidden cell, which is now \\"\\". Read only cells listed in src, or skip empty cells."),
    ("still finds them", "HOW TO FIX: outcomes must come from cells that no input lists in its src, and each outcome's "
                         "src must list all the cells that hold it."),
    ("not ids from entities", "HOW TO FIX: every id in a record's entities must be an id that entities() returns. Parse "
                              "the id exactly, or remove the record's unknown entity."),
    ("malformed output", "HOW TO FIX: each function must return exactly the structure described above."),
]


def _hints(report: str) -> str:
    \"\"\"The fix for each kind of failure found in a check report.\"\"\"
    found = [text for key, text in FEEDBACK_HINTS if key in (report or "")]
    return "\\n".join(found) + "\\n" if found else ""


def _syntax_problem(code: str) -> str | None:
    try:
        ast.parse(code)
    except SyntaxError as e:
        return f"syntax error at line {e.lineno}: {e.msg}."
    return None


def _is_cut_off(reply: str) -> bool:
    return (reply or "").count("```") % 2 == 1


def _with_syntax_repair(llm, ask: list[dict], attempts: list, log, max_repairs: int = 2) -> str:
    \"\"\"Get code from the model. A syntax error or a cut-off reply is sent back before the code is checked, so it
    does not use up a try. Repairs are real calls: they are metered, and they are recorded in `attempts`.\"\"\"
    reply = llm(ask)
    code = extract_code(reply)
    for k in range(max_repairs):
        problem = _syntax_problem(code)
        if not problem:
            break
        attempts.append({"step": "syntax_repair", "try": k + 1, "problem": problem, "cut_off": _is_cut_off(reply)})
        log(f"syntax repair {k + 1}: {problem}")
        cut = prompts.CUT_OFF if _is_cut_off(reply) else ""
        reply = llm(ask + [{"role": "assistant", "content": reply or "(empty reply)"},
                           {"role": "user", "content": prompts.SYNTAX_REPAIR.format(problem=problem, cut_off=cut)}])
        code = extract_code(reply)
    return code


def generate_model(llm, nav: dict, map_path: Path, max_tries: int = 3, log=None,"""),
]


def edit(text, edits, name):
    for old, new in edits:
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"{name}: expected one match, found {count}: {old[:70]!r}")
        text = text.replace(old, new)
    return text


def functions(source, names):
    tree = ast.parse(source)
    return {n.name: ast.get_source_segment(source, n) for n in tree.body
            if isinstance(n, ast.FunctionDef) and (names is None or n.name in names)}


def constants(source):
    """Module-level simple assignments, by name, as source text."""
    tree = ast.parse(source)
    out = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            out[n.targets[0].id] = ast.get_source_segment(source, n)
    return out


def main(root):
    root = os.path.abspath(root)
    pinned = os.path.join(root, "baseline", "otf-tools-10f5401", "implementation-1", "otf")
    target = os.path.join(root, "redesign", "otf_r1")
    if os.path.exists(target):
        shutil.rmtree(target)
    shutil.copytree(pinned, target, ignore=shutil.ignore_patterns("__pycache__"))
    diffs = []
    for name, edits in (("sandbox.py", SANDBOX_EDITS), ("prompts.py", PROMPT_EDITS), ("toolgen.py", TOOLGEN_EDITS)):
        path = os.path.join(target, name)
        with open(path, encoding="utf-8") as f:  # Universal newlines: the pinned files use CRLF.
            before = f.read()
        after = edit(before, edits, name)
        ast.parse(after)
        with open(path, "w", encoding="utf-8") as f:
            f.write(after)
        diffs += difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"pinned/otf/{name}", f"redesign/otf_r1/{name}")
        if name == "toolgen.py":
            # Review fix: every pinned function except the generation loop must be unchanged, and so must every
            # module-level constant. New helpers are allowed only if they did not exist before.
            generation = {"generate_model", "_simulator_agent"}
            pinned = {n: s for n, s in functions(before, None).items() if n not in generation}
            now = functions(after, None)
            if any(now.get(n) != s for n, s in pinned.items()):
                raise SystemExit("acceptance code changed")
            if constants(before) != {k: v for k, v in constants(after).items() if k in constants(before)}:
                raise SystemExit("acceptance constants changed")
        if name == "sandbox.py":
            strip = lambda c: {k: v for k, v in c.items() if k != "HELPERS"}
            if functions(before, None) != functions(after, None) or strip(constants(before)) != strip(constants(after)):
                raise SystemExit("sandbox code or constants changed beyond the helper text")
    with open(os.path.join(root, "manifests", "redesign_r1.diff"), "w", encoding="utf-8", newline="\n") as f:
        f.writelines(diffs)
    print("redesign/otf_r1 written; acceptance functions identical to pinned;", len(diffs), "diff lines")


if __name__ == "__main__":
    main(sys.argv[1])
