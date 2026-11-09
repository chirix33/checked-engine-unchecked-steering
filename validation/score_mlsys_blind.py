"""Score the blind sampled check against gold (evaluation-only). Agents never saw gold; this runs afterwards.

Usage: python -X utf8 validation/score_mlsys_blind.py <blind_dir> <key_json> <out_json>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(blind_dir, key_path, out_path):
    key = json.loads(Path(key_path).read_text(encoding="utf-8"))
    gold = {}
    for split in ("dev", "test"):
        for q in json.loads((ROOT / "manifests" / f"mlsys_questions_{split}_v1.json").read_text(encoding="utf-8")):
            gold[q["id"]] = q
    files = {"mfg": {"A": "answers_A.json", "B": "answers_B.json"},
             "itops": {"A": "agent_A/answers.json", "B": "agent_B/answers.json"}}
    report = {}
    for dom, agents in files.items():
        rows = []
        for agent, rel in agents.items():
            p = Path(blind_dir) / dom / rel
            if not p.exists():
                rows.append({"agent": agent, "missing": True})
                continue
            for a in json.loads(p.read_text(encoding="utf-8")):
                q = gold[key[dom][a["qid"]]]
                ans = a.get("answer")
                if isinstance(q["gold"], bool) and isinstance(ans, str):
                    ans = ans.strip().lower() in ("yes", "true")
                rows.append({"agent": agent, "qid": a["qid"], "id": q["id"], "family": q["family"], "answer": ans,
                             "gold": q["gold"], "match": ans == q["gold"], "confidence": a.get("confidence"),
                             "factual_reproduced": a.get("factual_reproduced"), "note": a.get("note")})
        report[dom] = {"rows": rows, "matches": sum(r.get("match", False) for r in rows),
                       "answered": sum(1 for r in rows if "match" in r)}
        print(dom, report[dom]["matches"], "of", report[dom]["answered"], "match gold")
        for r in rows:
            if not r.get("match", True) or r.get("missing"):
                print("  mismatch", r)
    Path(out_path).write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:4])
