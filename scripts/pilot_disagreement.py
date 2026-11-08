"""Disagreement-only gate (preliminary): permit the structured answer only if the vanilla reading answer exists and
agrees within 1 s. Also directed AND agreement. Structured path, interpreted requests."""
import collections, glob, json
qs = {q["id"]: q for q in json.load(open("manifests/pilot_questions_v1.json", encoding="utf-8"))}
van = {json.loads(l)["key"]: json.loads(l)["answer"] for l in open("runs/pilot_v1/vanilla.jsonl", encoding="utf-8")}
ok = lambda a, g: a is not None and g is not None and abs(a - g) < 1
agg = collections.defaultdict(collections.Counter)
for f in glob.glob("runs/pilot_v1/programs/*.jsonl"):
    for l in open(f, encoding="utf-8"):
        r = json.loads(l)
        if r["source"] != "interpreted" or "structured" not in r:
            continue
        p = r["program"].split("/")
        co = "/".join(p[:3]) if p[0] == "otf" else f"devs/{p[1]}"
        q = qs[r["question"]]
        a = r["structured"].get("answer") if r["structured"].get("status") == "ran" else None
        v = van.get(q["id"])
        agree = a is not None and v is not None and abs(a - v) < 1
        for name, permit in (("disagreement_only", agree), ("directed", r["decisions"]["directed"]["permit"] and a is not None),
                             ("directed_and_agree", agree and r["decisions"]["directed"]["permit"])):
            c = agg[(co, name)]
            c["n"] += 1
            if permit:
                c["ans"] += 1
                c["ok"] += ok(a, q["gold"])
            # fallback to vanilla when declined
            c["fb"] += ok(a, q["gold"]) if permit else ok(v, q["gold"])
for (co, name), c in sorted(agg.items()):
    print(f"{co:32} {name:20} n={c['n']:4} cov={c['ans']/c['n']:.3f} prec={(c['ok']/c['ans'] if c['ans'] else float('nan')):.3f} "
          f"yield={c['ok']/c['n']:.3f} +van={c['fb']/c['n']:.3f}")
