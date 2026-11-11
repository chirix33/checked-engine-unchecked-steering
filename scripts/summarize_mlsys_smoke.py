"""Summarize the adapter smoke run (development data; not a result). Usage: python -X utf8 scripts/summarize_mlsys_smoke.py <jsonl>"""
import json
import sys
from collections import Counter, defaultdict

rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
rep = defaultdict(Counter)
for r in rows:
    dom = "mfg" if "mfg_dev" in r["program"] else "itops"
    model = r["program"].split("/")[0]
    key = f"{r['cohort']}/{model}/{dom}"
    if r["row"].startswith("replay"):
        rep[key][f"history {'seen' if r['seen_at_build'] else 'unseen'} {'pass' if r['replay'] else 'fail'}"] += 1
    else:
        label = "Trusted" if r["permit"] else "Can't express" if r["inexpressible"] else "Untestable" if r["untested"] else \
            "Failed history check" if r["reason"].startswith("replay") else "Caught"
        right = {True: "right", False: "wrong", None: "no answer"}[r["diagnostic_answer_right"]]
        rep[key][f"{label} ({right})"] += 1
for k in sorted(rep):
    print(k, dict(sorted(rep[k].items())))
