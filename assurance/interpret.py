"""Request interpreter: question to structured intervention and query, using only the document's permitted names.

The model sees the question, the stated policy's names and the scope's case ids. It never sees gold answers,
reference code or hidden bindings. Its output is untrusted and goes through contract validation.
"""
from __future__ import annotations

import json
import re

from .request import FAMILIES, Intervention, ProcessSchema, Query, Request

PROMPT = """Turn a what-if question about a business process into a structured request. Reply with only JSON.

NAMES THE DOCUMENT USES
Runs (scopes): {scopes}
Cases in each run: {cases}
Activities: {activities}
Waits: {waits}
Decisions and their routes: {decisions}
Worker pools and sizes: {pools}
Time: whole seconds from time 0, a Monday at 00:00.

REQUEST FORMAT
{{"scope": run title,
  "interventions": [one or more of:
    {{"family": "activity_duration", "op": "set", "case": id, "target": activity, "visit": n, "value": seconds}}
    {{"family": "timer_delay", "op": "set", "case": id, "target": wait label, "visit": n, "value": seconds}}
    {{"family": "routing_outcome", "op": "set_draw", "case": id, "target": decision label, "visit": n, "value": draw}}
    {{"family": "routing_probability", "op": "set", "target": decision label, "routes": {{route label: probability}}}}
    {{"family": "resource_availability", "op": "add_workers", "target": pool, "value": count}}
    {{"family": "resource_availability", "op": "unavailable", "target": pool, "value": count, "effective_from": t1, "effective_to": t2}}
    {{"family": "case_set", "op": "remove", "case": id}}],
  "query": {{"kind": "case_end_time" or "case_ends_by", "case": id, "deadline": t or null}},
  "unresolved": null, or a short reason if the question cannot be written in this format}}
Use the visit number the question gives; if it gives none, use 1. Convert hours and minutes to seconds.

QUESTION
{question}"""


def interpret(question: str, schema: ProcessSchema, llm) -> tuple[Request, str]:
    text = llm([{"role": "user", "content": PROMPT.format(
        scopes=", ".join(schema.scopes), cases=json.dumps(schema.cases), activities="; ".join(schema.activities),
        waits=", ".join(schema.waits), decisions=json.dumps(schema.decisions), pools=json.dumps(schema.pools),
        question=question)}])
    return parse(text), text


def _first_json(text: str):
    """The first JSON object in a reply: a fenced block if present, else the first decodable object."""
    text = text or ""
    for block in re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.S):
        try:
            return json.loads(block)
        except ValueError:
            pass
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(text[i:])
                return obj
            except ValueError:
                continue
    return None


def parse(text: str) -> Request:
    d = _first_json(text)
    if not isinstance(d, dict):
        return Request("", [], Query("invalid", ""), unresolved="malformed reply: no JSON object")
    q = d.get("query") or {}
    try:
        query = Query(str(q.get("kind")), str(q.get("case")), None if q.get("deadline") is None else int(q["deadline"]))
    except (TypeError, ValueError):
        query = Query("invalid", "")
    ivs = []
    for x in d.get("interventions") or []:
        if not isinstance(x, dict):
            continue
        try:
            ivs.append(Intervention(
                family=str(x.get("family")), op=str(x.get("op")), case=x.get("case"), target=x.get("target"),
                visit=None if x.get("visit") is None else int(x["visit"]),
                value=None if x.get("value") is None else float(x["value"]),
                routes={str(k): float(v) for k, v in x["routes"].items()} if isinstance(x.get("routes"), dict) else None,
                effective_from=None if x.get("effective_from") is None else int(x["effective_from"]),
                effective_to=None if x.get("effective_to") is None else int(x["effective_to"])))
        except (TypeError, ValueError):
            return Request(str(d.get("scope")), [], query, unresolved="malformed intervention")
    unresolved = d.get("unresolved") or None
    return Request(str(d.get("scope")), ivs, query, unresolved=unresolved)
