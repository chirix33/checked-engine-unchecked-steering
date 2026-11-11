"""History check (replay) of coding-agent programs on the dev documents, through the library's own adapters, unchanged.

Workflow programs run through assurance.backends.DEVSBackend and assurance.probes.ProbeRunner.replay; manufacturing
and IT programs through assurance.mlsys.DEVSDomain and assurance.mlsys.ProbeRunner.replay. The program folder is the
WSL folder recorded in the build's build.json. Dev documents only; evaluation-side (this script is not a builder).

Usage: python -X utf8 scripts/coding_agent_replay.py <setup> <Domain> <k> [<k> ...]
Writes runs/coding_agent/<setup>/<Domain>/b<k>/replay_dev.json and prints one line per run.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
sys.dont_write_bytecode = True

DEV_NAV = {"WorkflowLoan": ROOT / "runs/build_test_r1_claude/claude-sonnet-5-5/workflow_loan_dev/b2/navmap.json",
           "WorkflowPharmacy": ROOT / "runs/build_test_r1_claude/claude-sonnet-5-5/workflow_pharmacy_dev/b2/navmap.json",
           "Manufacturing": ROOT / "runs/mlsys_docs/mfg_dev/navmap.json",
           "ITOperations": ROOT / "runs/mlsys_docs/itops_dev/navmap.json"}   # the same dev maps the pilot runners use


def replay(setup, domain, k):
    folder = ROOT / "runs" / "coding_agent" / setup / domain / f"b{k}"
    rec = json.loads((folder / "build.json").read_text(encoding="utf-8"))
    if not rec.get("wsl_dir"):
        return {"build": f"b{k}", "status": rec["status"], "detail": "no program"}
    nav = json.loads(DEV_NAV[domain].read_text(encoding="utf-8"))
    if domain.startswith("Workflow"):
        from assurance.backends import DEVSBackend
        from assurance.probes import ProbeRunner
        from assurance.request import schema_from_map
        schema = schema_from_map(nav)
        backend = DEVSBackend(rec["wsl_dir"], domain, ROOT)
        scopes = sorted({n["title"].rsplit(": ", 1)[0] for n in nav["nodes"] if n["title"].endswith(": Cases")})
    else:
        from assurance import mlsys as M
        schema = M.schema_from_map(nav)
        backend = M.DEVSDomain(rec["wsl_dir"], schema)
        ProbeRunner = M.ProbeRunner
        scopes = list(schema.chapters)
    runner = ProbeRunner(backend, nav, schema)
    out = {"build": f"b{k}", "setup": setup, "domain": domain, "program_hash": backend.program_hash(),
           "program_sha256": rec["program_sha256"], "nav": str(DEV_NAV[domain].relative_to(ROOT)), "runs": {}}
    for s in scopes:
        t0 = time.time()
        ok, detail = runner.replay(s)
        ex = runner.base(s)
        out["runs"][s] = {"replay": ok, "detail": detail[:400], "status": getattr(ex, "status", None),
                          "events": len(getattr(ex, "records", None) or []), "seconds": round(time.time() - t0, 1)}
        print(f"{setup}/{domain}/b{k} {s}: {'PASS' if ok else 'FAIL'} - {detail[:200]}")
    out["replay_all"] = all(r["replay"] for r in out["runs"].values())
    (folder / "replay_dev.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    setup, domain, *ks = sys.argv[1:]
    for k in ks:
        replay(setup, domain, int(k))
