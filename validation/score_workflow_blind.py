"""Score the workflow blind sampled check against gold (evaluation-only). Agents never saw gold; this runs afterwards.

`factual_reproduced` is the agent's own claim; its simulator and notes are kept beside its answers.

Usage: python -X utf8 validation/score_workflow_blind.py <blind_dir> <key_json> <out_json> <agent> [<agent> ...]
       (each agent's answers are read from <blind_dir>/<agent>/answers.json)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(blind_dir, key_path, out_path, *agents):
    if not agents:
        raise SystemExit("name at least one agent")
    import hashlib
    k = json.loads(Path(key_path).read_text(encoding="utf-8"))
    qbytes = (ROOT / k["questions"]).read_bytes()
    if k.get("questions_sha256") and hashlib.sha256(qbytes).hexdigest() != k["questions_sha256"]:
        raise SystemExit("the questions file changed since the sample was drawn")
    gold = {q["id"]: q for q in json.loads(qbytes.decode("utf-8"))}
    report = {"key": key_path, "agents": {}}
    for agent in agents:
        p = Path(blind_dir) / agent / "answers.json"
        rows = []
        if not p.exists():
            report["agents"][agent] = {"missing": True}
            print(agent, "missing")
            continue
        got = {a["qid"]: a for a in json.loads(p.read_text(encoding="utf-8"))}
        for qid, qname in k["key"].items():
            q, a = gold[qname], got.get(qid, {})
            ans = a.get("answer")
            try:                                     # compare as numbers ("55987" and 55987.0 are 55987)
                num = None if ans is None or isinstance(ans, bool) else float(ans)
            except (TypeError, ValueError):
                num = None
            rows.append({"qid": qid, "id": qname, "family": q["family"], "effectful": q["effectful"], "answer": ans,
                         "gold": q["gold"], "match": num is not None and num == q["gold"], "answered": ans is not None,
                         "factual_reproduced": a.get("factual_reproduced"), "confidence": a.get("confidence"),
                         "note": a.get("note")})
        report["agents"][agent] = {"rows": rows, "matches": sum(r["match"] for r in rows), "of": len(rows),
                                   "answered": sum(r["answered"] for r in rows),
                                   "factual_reproduced": sum(r["factual_reproduced"] is True for r in rows)}
        s = report["agents"][agent]
        print(agent, s["matches"], "of", s["of"], "match gold;", s["answered"], "answered;", s["factual_reproduced"], "on reproduced chapters")
        for r in rows:
            if not r["match"]:
                print("  mismatch", r["qid"], r["id"], r["answer"], "gold", r["gold"], r["note"])
    Path(out_path).write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])
