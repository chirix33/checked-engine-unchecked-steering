"""Render the main-run results tables from `main_analysis.json` (written by scripts/main_analysis.py) as Markdown.

This script only formats; it computes nothing new except expected wrong-answer counts for a judge at the gate's coverage
(k = round(n x coverage) kept rows, then k x (1 - precision), shown as a whole number because precision is stored to 4 decimals)
and simple sums of counts already in the JSON. Every number in the output comes from the JSON it is given.

Usage: python -X utf8 scripts/report_tables.py <main_analysis.json> <out.md>
"""
import json
import sys


def f3(x):
    return "-" if x is None else f"{x:.3f}"


def ci(d):
    if not d or d.get("point") is None:
        return "-"
    lo, hi = d.get("ci95") or (None, None)
    return f"{d['point']:+.3f} [{f3(lo)}, {f3(hi)}]" if lo is not None else f"{d['point']:+.3f}"


def exp_wrong(n, part):
    if not part or part.get("coverage") is None:
        return None
    p = part.get("precision")
    k = round(n * part["coverage"])          # the gate's (and so the judge's) number of kept rows; review fix: no rounding drift
    return 0.0 if p is None or k == 0 else k * (1 - p)


def fw(x):
    return "-" if x is None else f"{x:.0f}"     # review: one decimal is not supported by 4-decimal precision


RULES = ("native", "replay", "generic", "schema", "program_wide", "disagreement", "directed")
TERMS = ("Trusted", "Caught", "Already caught", "Untestable", "Failed history check", "Can't express", "Request rejected", "Other")


def rule_table(groups, keys, out):
    out.append("| group | n | progs | " + " | ".join(f"{j} cov/prec (wrong)" for j in RULES) + " | random@gate prec/yield |")
    out.append("|" + "---|" * (4 + len(RULES)))
    for k in keys:
        g = groups.get(k)
        if not g:
            continue
        cells = []
        for j in RULES:
            p = g.get(j)
            cells.append("n/a" if p is None else f"{f3(p['coverage'])}/{f3(p['precision'])} ({p['wrong']})")
        r = g.get("matched_random_refusal") or {}
        out.append(f"| {k} | {g['n']} | {g.get('programs', '-')} | " + " | ".join(cells) + f" | {f3(r.get('precision'))}/{f3(r.get('yield'))} |")
    out.append("")
    out.append("Correct-answer yield (correct answers / rows), gate minus each judge, paired two-level bootstrap 95% interval:")
    out.append("")
    out.append("| group | gate yield | " + " | ".join(j for j in RULES if j != "directed") + " | random |")
    out.append("|" + "---|" * (2 + len(RULES)))
    for k in keys:
        g = groups.get(k)
        if not g:
            continue
        cells = []
        for j in RULES:
            if j == "directed":
                continue
            p = g.get(j)
            cells.append("n/a" if p is None else ci(p.get("gate_minus_this_yield")))
        r = g.get("matched_random_refusal") or {}
        cells.append(ci(r.get("gate_minus_this_yield")) if r else "-")
        out.append(f"| {k} | {f3(g['directed']['yield'])} | " + " | ".join(cells) + " |")
    out.append("")


def llm_rows(runs, keys, out, label_runs=True):
    out.append("| judge run | group | n | wrong answers (all) | gate cov/prec (wrong) | judge at gate's coverage: prec (exp. wrong) | gate - judge precision | gate - judge yield | judge own verdict cov/prec (wrong Trusted) | gate - own yield | AUROC |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for run, r in runs.items():
        for k in keys:
            g = (r.get("groups") or {}).get(k)
            if not g:
                continue
            n = g["n"]
            gate, jm, own = g["gate"], g["judge_matched"], g["judge_own_verdict"]
            out.append(
                f"| {run} | {k} | {n} | {g['wrong_rows']} | {f3(gate['coverage'])}/{f3(gate['precision'])} ({g.get('gate_wrong_trusted')}) | "
                f"{f3(jm['precision'])} ({fw(exp_wrong(n, jm))}) | {ci(g.get('gate_minus_judge_matched_precision'))} | "
                f"{ci(g.get('gate_minus_judge_matched_yield'))} | {f3(own['coverage'])}/{f3(own['precision'])} ({own.get('wrong_trusted')}) | "
                f"{ci(g.get('gate_minus_judge_own_yield'))} | {f3(g.get('auroc'))} |")
    out.append("")


def completeness_shared(runs, out):
    out.append("| judge run | judged | without judgment |")
    out.append("|---|---|---|")
    for run, r in runs.items():
        out.append(f"| {run} | {r.get('rows_with_judgment')} | {r.get('rows_without_judgment')} |")
    out.append("")


def completeness(runs, out):
    out.append("| judge run | expected rows (main sets) | judged | without judgment | duplicates | prompt hashes |")
    out.append("|---|---|---|---|---|---|")
    for run, r in runs.items():
        out.append(f"| {run} | {r.get('expected_rows_in_main_sets')} | {r.get('rows_with_judgment')} | {r.get('rows_without_judgment')} | "
                   f"{r.get('duplicates')} | {', '.join(h[:12] for h in (r.get('prompt_hashes') or []))} |")
    out.append("")


def term_table(terms, keys, out):
    out.append("| group | side | rows | " + " | ".join(TERMS) + " |")
    out.append("|" + "---|" * (3 + len(TERMS)))
    for k in keys:
        t = terms.get(k)
        if not t:
            continue
        for side in ("wrong", "right"):
            c = t.get(side) or {}
            out.append(f"| {k} | {side} | {sum(c.values())} | " + " | ".join(str(c.get(x, 0)) for x in TERMS) + " |")
    out.append("")
    out.append("Wrong answers by whether the interpreted request equals the oracle request:")
    out.append("")
    out.append("| group | wrong answers | by interpretation |")
    out.append("|---|---|---|")
    for k in keys:
        wi = (terms.get(k) or {}).get("wrong_interp") or {}
        if wi:
            out.append(f"| {k} | {sum(wi.values())} | " + "; ".join(f"{a}: {b}" for a, b in sorted(wi.items())) + " |")
    out.append("")


def main():
    src, dst = sys.argv[1], sys.argv[2]
    d = json.load(open(src, encoding="utf-8"))
    out = [f"# Main-run results tables (generated by scripts/report_tables.py from `{src}`)", "",
           f"Sets {d['sets']}; rows {d['rows']}; bootstrap B={d['bootstrap']}, seed {d['seed']}; program failures {len(d['program_failures'])}.",
           "Claude-built and Ollama-built programs are never pooled. Coverage = answered and trusted / rows; precision = correct / "
           "answered; yield = correct / rows. 'wrong' = answered and trusted but wrong.", ""]

    rj = d["rule_judges"]
    cls = ["class=claude", "class=ollama"]
    sub = [k for k in rj if not k.startswith("cell=") and k not in cls]
    out += ["## 1. Rule-based judges and the gate, every row (main sets: interpreted requests, structured path)", ""]
    rule_table(rj, cls + sorted(sub), out)

    out += ["## 2. LLM judges against the gate, matched within cells (set | process | cohort)", "",
            "The judge keeps the gate's number of rows per cell, by descending confidence, with expected precision over ties. "
            "n counts answered rows only, because LLM judges see only rows with an answer.", "", "### Completeness", ""]
    completeness(d["llm_judges"], out)
    # review fix: every non-cell group in the JSON, not a hard-coded list
    gk = cls + sorted({k for r in d["llm_judges"].values() for k in (r.get("groups") or {}) if not k.startswith("cell=") and k not in cls})
    out += ["### By class", ""]
    llm_rows(d["llm_judges"], cls, out)
    out += ["### By platform, process and effect (secondary views)", ""]
    llm_rows(d["llm_judges"], gk[2:], out)

    for sname in ("shared150", "react50"):
        s = d["shared_rows"].get(sname)
        if not s:
            continue
        out += [f"## 3{'a' if sname == 'shared150' else 'b'}. Same rows, every model: `{sname}` ({s['ids']} ids, {s['rows_found_with_answer']} found with an answer)", ""]
        out += ["Rule-based judges on the same rows:", ""]
        rule_table(s.get("rule_judges") or {}, cls, out)
        out += ["LLM judges on the same rows (matched within cells):", ""]
        llm_rows(s["runs"], cls, out)
        completeness_shared(s["runs"], out)

    ne = d["natural_errors"]
    out += ["## 4. Natural errors: what the gate did with each wrong and right answer (main sets)", ""]
    keys = cls + sorted(k for k in ne["terms"] if k not in cls)
    term_table(ne["terms"], keys, out)
    out += ["### Wrong answers the gate Trusted", "", "| set | program | question | family | answer | gold | interpretation exact | reason |", "|---|---|---|---|---|---|---|---|"]
    for r in ne["wrong_trusted_rows"]:
        out.append(f"| {r['set']} | {r['program']} | {r['question']} | {r['family']} | {r['answer']} | {r['gold']} | {r['interpretation_exact']} | {r['reason'][:110]} |")
    out.append("")

    it = d["interpretation"]
    out += ["## 5. Interpretation", "", "| set or set|family | questions with a parsed request | interpreted request equals oracle | no parsable request |", "|---|---|---|---|"]
    for k, v in it["exact"].items():
        out.append(f"| {k} | {v.get('of', 0)} | {v.get('exact', 0)} | {v.get('no_request', 0)} |")
    out += ["", "Gate on interpreted vs oracle requests (structured path):", "", "| set|class|source | n | answered | correct | coverage | precision |", "|---|---|---|---|---|---|"]
    for k, v in it["gate_by_source"].items():
        out.append(f"| {k} | {v['n']} | {v.get('answered', 0)} | {v.get('correct', 0)} | {f3(v.get('coverage'))} | {f3(v.get('precision'))} |")
    out.append("")

    sc = d.get("study_c")
    if sc:
        study_c(sc, out)
    else:
        out += ["## 6. Study C: not in this JSON (made without a policy set)", ""]
    agreement_cost_breakdowns(d, out)
    open(dst, "w", encoding="utf-8").write("\n".join(out))
    print("wrote", dst, len(out), "lines")


def study_c(sc, out):
    out += ["## 6. Study C: policy reuse (wf_policy, Claude-built workflow programs, registries copied from wf_test)", "",
            "| document | fingerprint | equals a test fingerprint |", "|---|---|---|"]
    for k, v in sc["fingerprints"].items():
        out.append(f"| {k} | {v['fingerprint']} | {sc['policy_fingerprint_equals_a_test_fingerprint'].get(k, '-')} |")
    reg = sc["policy_registry_starts_with_test_registry"]
    out += ["", f"Policy registries that start with the final test registry: {sum(1 for v in reg.values() if v)} of {len(reg)}; "
            f"test registries missing: {len(sc['test_registry_missing'])}.", "",
            f"Missed invalidations on P (a test pass reused on a real policy change): `{json.dumps(sc['missed_invalidations_P'])}`", "",
            "| variant group | n | answered | correct | wrong Trusted | ungated wrong | coverage | precision | executions/row | reused (same run) | cites test scope | capability failed on test | of those Trusted (right/wrong) |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in sc["by_variant"].items():
        out.append(f"| {k} | {v['n']} | {v['answered']} | {v['correct']} | {v['wrong_trusted']} | {v['ungated_wrong']} | {f3(v['coverage'])} | "
                   f"{f3(v['precision'])} | {f3(v['executions_per_row'])} | {v.get('reused_same_run', 0)} | {v.get('cites_test_scope', 0)} | "
                   f"{v.get('test_failed', 0)} | {v.get('test_failed trusted right', 0)}/{v.get('test_failed trusted wrong', 0)} |")
    out += ["", "Terms by variant:", "", "| variant group | " + " | ".join(TERMS) + " |", "|" + "---|" * (1 + len(TERMS))]
    for k, v in sc["by_variant"].items():
        out.append(f"| {k} | " + " | ".join(str(v.get(f"term {x}", 0)) for x in TERMS) + " |")
    out += ["", "### Study C, rule-based judges", ""]
    rule_table(sc["rule_judges"], sorted(sc["rule_judges"].keys()), out)
    out += ["### Study C, LLM judges (matched within cells)", ""]
    # Study C keeps each run's groups at the top level of the run entry (no "groups" key).
    llm_rows({run: {"groups": g} for run, g in sc["llm_judges"].items()},
             sorted({k for g in sc["llm_judges"].values() for k in g}), out)


def agreement_cost_breakdowns(d, out):
    ag = d["agreement"]
    out += ["## 7. Judge agreement", "", "| pair | rows | verdict agreement | kappa | trust rates | mean abs confidence diff | Pearson | Spearman |", "|---|---|---|---|---|---|---|---|"]
    for k, v in ag["repeat"].items():
        out.append(f"| {k} | {v['rows']} | {f3(v['verdict_agreement'])} | {f3(v['kappa'])} | {', '.join(f3(x) for x in v['trust_rate'])} | "
                   f"{f3(v['confidence_mean_abs_diff'])} | {f3(v['confidence_pearson'])} | {f3(v['confidence_spearman'])} |")
    out += ["", "Self-judging: trust rate on right and on wrong answers, by the builder of the judged program:", "",
            "| judge run | builder group | n | right | wrong | trusted right | trusted wrong | trust rate on right | trust rate on wrong |", "|---|---|---|---|---|---|---|---|---|"]
    for run, groups in ag["self_judging"].items():
        for k, v in groups.items():
            out.append(f"| {run} | {k} | {v['n']} | {v['right']} | {v['wrong']} | {v['trust_right']} | {v['trust_wrong']} | "
                       f"{f3(v.get('trust_rate_on_right'))} | {f3(v.get('trust_rate_on_wrong'))} |")
    out.append("")

    c = d["cost"]
    out += ["## 8. Cost", "", "Gate and rule-judge program executions:", "", "| set|class | " + " | ".join(("native", "replay", "schema", "generic", "directed", "program_wide")) + " |", "|---|---|---|---|---|---|---|"]
    for k, v in c["gate_executions"].items():
        out.append(f"| {k} | " + " | ".join(f"{v[j]['per_row']:.2f}/row ({v[j]['total']})" if j in v else "-" for j in ("native", "replay", "schema", "generic", "directed", "program_wide")) + " |")
    out += ["", "LLM judges:", "", "| judge run | rows | skipped | model calls | failed calls | prompt tokens | output tokens | USD | USD/row | wall s/row | failures |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in c["judges"].items():
        out.append(f"| {k} | {v['rows']} | {v['skipped']} | {v['model_calls']} | {v['failed_calls']} | {v['prompt_tokens']} | {v['output_tokens']} | "
                   f"{v['usd']:.2f} | {v['usd_per_row']:.4f} | {v['wall_seconds_per_row']:.1f} | {json.dumps(v.get('failures') or {})} |")
    out += ["", "Shared stage (interpretation, readers, native answers) from the main runner's ledger:", "", "| set|kind | calls | USD | prompt tokens | output tokens | seconds |", "|---|---|---|---|---|---|"]
    for k, v in c["shared_stage_ledger"].items():
        out.append(f"| {k} | {v['calls']} | {v['usd']:.2f} | {v['prompt_tokens']} | {v['output_tokens']} | {v['seconds']:.0f} |")
    out += ["", "Judges ledger by folder and model (USD, includes smoke and dev checks):", ""]
    for k, v in c["judges_ledger_usd_by_folder_and_model"].items():
        out.append(f"- {k}: {v:.2f}")
    out.append("")

    pf = d["breakdowns"]["per_family"]
    out += ["## 9. Per family (main sets)", "", "| class|process|family | n | " + " | ".join(f"{j} cov/prec (wrong)" for j in RULES) + " |", "|" + "---|" * (2 + len(RULES))]
    for k in sorted(pf):
        v = pf[k]
        out.append(f"| {k} | {v['n']} | " + " | ".join("n/a" if v.get(j) is None else f"{f3(v[j]['coverage'])}/{f3(v[j]['precision'])} ({v[j]['wrong']})" for j in RULES) + " |")
    out.append("")

    pp = d["breakdowns"]["per_program"]
    out += ["## 10. Per program (main sets)", "", "| program | n | " + " | ".join(f"{j} cov/prec (wrong)" for j in RULES) + " |", "|" + "---|" * (2 + len(RULES))]
    for k in sorted(pp):
        v = pp[k]
        out.append(f"| {k} | {v['n']} | " + " | ".join("n/a" if v.get(j) is None else f"{f3(v[j]['coverage'])}/{f3(v[j]['precision'])} ({v[j]['wrong']})" for j in RULES) + " |")
    out.append("")

    npth = d["native_path"]
    out += ["## 11. OTF native path (B0 is native-only; R1 native shown for reference)", "",
            "| process|cohort | mode | n | answered | correct | coverage | precision | gated coverage | gated precision |", "|---|---|---|---|---|---|---|---|---|---|"]
    for k in sorted(npth):
        for m, v in npth[k].items():
            out.append(f"| {k} | {m} | {v['n']} | {v['answered']} | {v['correct']} | {f3(v['coverage'])} | {f3(v['precision'])} | "
                       f"{f3(v.get('gated_coverage'))} | {f3(v.get('gated_precision'))} |")
    out.append("")


if __name__ == "__main__":
    main()
