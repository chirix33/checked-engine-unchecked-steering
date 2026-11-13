"""The paper's significance-bearing differences, frozen vs run-clustered intervals.

Usage: python -X utf8 acmtrust_paper/sensitivity/paper_claims.py <frozen.json> <clustered.json> <out.md>
Values are percentage points (gate minus judge). "sig" = the 95% interval excludes 0.
"""
import json
import sys

fz = json.load(open(sys.argv[1], encoding="utf-8"))
cl = json.load(open(sys.argv[2], encoding="utf-8"))
out = sys.argv[3]


def get(d, path):
    for k in path:
        d = d[k]
    return d


def excl(ci):
    return ci is not None and (ci[0] > 0 or ci[1] < 0)


def fmt(ci):
    return "--" if ci is None else f"[{100 * ci[0]:.1f}, {100 * ci[1]:.1f}]"


rows = []


def add(section, label, path):
    a, b = get(fz, path), get(cl, path)
    pt = a["point"]
    rows.append((section, label, "--" if pt is None else f"{100 * pt:+.1f}", fmt(a.get("ci95")), fmt(b.get("ci95")),
                 excl(a.get("ci95")), excl(b.get("ci95"))))


G3 = [("OTF R1", "platform=otf_r1|class=claude"), ("DEVS-Gen", "platform=devs|class=claude"),
      ("Coding agent", "platform=agent|class=claude"), ("All three", "class=claude"), ("Ollama OTF R1", "platform=otf_r1|class=ollama")]
J3 = [("Platform check", "native"), ("History check", "replay"), ("Generic", "generic"), ("Disagreement", "disagreement"),
      ("Schema", "schema"), ("Program-wide", "program_wide")]
for gl, g in G3:
    for jl, j in J3:
        add("Table 3 dK", f"{gl} vs {jl}", ["rule_judges", g, j, "gate_minus_this_yield"])
    add("Table 3 dK", f"{gl} vs Random refusal", ["rule_judges", g, "matched_random_refusal", "gate_minus_this_yield"])
    add("Table 3 dPrec", f"{gl} vs Platform check", ["rule_judges", g, "native", "gate_minus_this_precision"])
    add("Table 3 dPrec", f"{gl} vs History check", ["rule_judges", g, "replay", "gate_minus_this_precision"])

for pl, p in [("IT", "process=it_ops|class=claude"), ("Loan", "process=loan|class=claude"), ("Pharmacy", "process=pharmacy|class=claude"),
              ("No-effect", "effectful=False|class=claude")]:
    for jl, j in [("History check", "replay"), ("Program-wide", "program_wide"), ("Disagreement", "disagreement")]:
        add("Domain dK", f"{pl} vs {jl}", ["rule_judges", p, j, "gate_minus_this_yield"])

LLM = [("Answer Haiku", "main_answer_haiku|answer|claude-haiku-5-5"), ("Answer Sonnet", "main_answer_sonnet150|answer|claude-sonnet-5-5"),
       ("Answer gpt-oss", "main_answer_gptoss150|answer|gpt-oss-120b"), ("Answer Gemma", "main_answer_gemma150|answer|gemma-31b-ollama"),
       ("Answer Qwen", "main_answer_qwen150|answer|qwen3.5-9b"), ("Program Haiku", "main_program_haiku|program|claude-haiku-5-5"),
       ("ReAct Haiku", "main_react_haiku|react|claude-haiku-5-5"), ("ReAct Sonnet", "main_react_sonnet50|react|claude-sonnet-5-5"),
       ("ReAct gpt-oss", "main_react_gptoss150|react|gpt-oss-120b"), ("ReAct Gemma", "main_react_gemma150|react|gemma-31b-ollama"),
       ("ReAct Qwen", "main_react_qwen150|react|qwen3.5-9b")]
for grp_l, grp in [("all three", "class=claude"), ("OTF R1", "platform=otf_r1|class=claude"), ("DEVS-Gen", "platform=devs|class=claude"),
                   ("Ollama", "class=ollama")]:
    for jl, j in LLM:
        g = fz["llm_judges"][j]["groups"].get(grp)
        if g is None:
            continue
        add(f"Table 4 ({grp_l})", f"{jl} dPrec matched", ["llm_judges", j, "groups", grp, "gate_minus_judge_matched_precision"])
        add(f"Table 4 ({grp_l})", f"{jl} dKept own", ["llm_judges", j, "groups", grp, "gate_minus_judge_own_yield"])

for k, v in fz["shared_rows"].items():
    for jl, j in LLM + [("Answer Haiku repeat", "main_answer_haiku_repeat150|answer|claude-haiku-5-5")]:
        try:
            get(fz, ["shared_rows", k, "runs", j, "groups", "class=claude", "gate_minus_judge_own_yield"])
        except (KeyError, TypeError):
            continue
        add(f"Shared {k}", f"{jl} dKept own", ["shared_rows", k, "runs", j, "groups", "class=claude", "gate_minus_judge_own_yield"])

sc = fz["study_c"]
for var in ("P", "H"):
    grp = f"variant={var}|class=claude"
    for jl, j in [("Platform check", "native"), ("History check", "replay"), ("Disagreement", "disagreement")]:
        add("Policy", f"{var} vs {jl} dK", ["study_c", "rule_judges", grp, j, "gate_minus_this_yield"])

changed = [r for r in rows if r[5] != r[6]]
L = ["# Run-clustered bootstrap vs frozen: the paper's significance-bearing differences", "",
     f"{len(rows)} differences checked; significance status changed for {len(changed)}.", "",
     "| section | difference (gate minus) | point (pp) | frozen 95% | run-clustered 95% | frozen sig | clustered sig |",
     "|---|---|---|---|---|---|---|"]
for r in rows:
    flag = " **changed**" if r[5] != r[6] else ""
    L.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {'yes' if r[5] else 'no'} | {'yes' if r[6] else 'no'}{flag} |")
open(out, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
print("\n".join(L[:3]))
for r in changed:
    print(" ", r[0], "|", r[1], "|", r[2], "|", r[3], "->", r[4])
