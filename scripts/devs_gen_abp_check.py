"""Is the DEVS-Gen ABP failure a program defect or an invalid change? Read the failing case, its settings and the spec."""
import gzip
import json
import os
import re
import sys

home = os.path.expanduser("~/trust2027")
for model, run in (("glm", "run_01"), ("glm", "run_03")):
    path = f"{home}/screen/out/{model}/{run}/delays_x0.5"
    res = json.load(open(f"{path}/scenario_result.json", encoding="utf-8"))["result"]
    print("==", model, run, "case_operational", res["case_operational"])
    print("  diagnostics", json.dumps(res["diagnostics"])[:700])
    bad = [k for k, v in res["case_operational"].items() if not v]
    manifest = json.load(open(f"{home}/screen/benchmark_delays_x0.5/ABP/manifest.json", encoding="utf-8"))
    for c in manifest["test_cases"]:
        if c["case_id"] in bad:
            print("  settings", c["sim_args"], c["checker_config"])
    for case in bad:
        ex = json.load(open(f"{path}/{case}/execution.json", encoding="utf-8"))
        print("  execution", json.dumps({k: v for k, v in ex.items() if not isinstance(v, (list, dict))})[:400])
        err = gzip.open(f"{path}/{case}/stderr.log.gz", "rt", errors="replace").read()
        print("  stderr tail", err[-500:].replace("\n", " | "))
        out = gzip.open(f"{path}/{case}/stdout.jsonl.gz", "rt", errors="replace").read()
        print("  stdout lines", out.count("\n"))
spec = open(f"{home}/devs_gen_code/benchmark/ABP/ABP_D1.yaml", encoding="utf-8").read()
for m in re.finditer(r"(?i)[^\n]*(sender_delay|receiver_delay)[^\n]*", spec):
    print("SPEC:", m.group(0).strip()[:200])
values = sorted({(c["sim_args"]["sender_delay"], c["sim_args"]["receiver_delay"]) for c in json.load(open(f"{home}/devs_gen_code/benchmark/ABP/manifest.json"))["test_cases"]})
print("native delay values", values)
src = open(f"{home}/devs_gen_code/generated/devs_gen/glm/ABP/run_01/run.py", encoding="utf-8", errors="replace").read()
for m in re.finditer(r"[^\n]*(sender_delay|receiver_delay)[^\n]*add_argument[^\n]*|add_argument[^\n]*(sender_delay|receiver_delay)[^\n]*", src):
    print("PROGRAM:", m.group(0).strip()[:180])
