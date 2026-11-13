# Main (test) run results, v1

**Status (2026-11-11, 22:30 CST): final, from the complete run.** Numbers come from `runs/main_v1/analysis_v1/` (`main_analysis.json`, `tables.md`, B = 2000, seed 20261111). Every program stage, the frozen scorer, every rule-based judge and every LLM judge are complete; no row is pending.

**Update (2026-11-13): Jev judge added (D30, after the main run).**
- Jev's numbers come from `runs/main_v1/analysis_v2/`, the same frozen analysis with Jev's rows added. Every other value in v2 equals v1, so v1 numbers elsewhere in this report stand.
- Jev is in §3c. The per-domain tables with Jev are `runs/main_v1/domain_tables_v2/`.

The final rerun changed only Qwen ReAct's rows relative to the interim analysis (`analysis_v1_noqwenreact/`), which in turn changed only the gpt-oss ReAct and Qwen answer rows relative to the first (`analysis_v1_partial/`). Both earlier folders are superseded. The whole report was reviewed against `analysis_v1/` after the final rerun.

**Terms.** The gate's decisions are **Trusted**, **Caught**, **Already caught**, **Untestable**, **Failed history check** and **Can't express**. An LLM judge's verdict is written TRUST or DECLINE.
- *Coverage* = rows answered and Trusted (or TRUST), divided by rows.
- *Precision* = correct answers among those.
- *Yield*: defined at the first table in §1.
- "Wrong" = let through but wrong. Square brackets are paired two-level bootstrap 95% intervals (programs × questions).
- A difference whose interval includes 0 is reported as a tie or "not significant". Several such intervals end exactly at 0 (for example Sonnet ReAct's own-verdict yield, −0.094 [−0.303, 0.000]); these are borderline and should be called that in the paper.

**Pooling.** Claude-built and Ollama-built programs are never pooled. Results are given per platform first; "all Claude-built" rows pool three platforms and two builder models and are a secondary view. Unless stated, the sets are the main ones (wf_test and ml_test), with interpreted requests on the structured path.

## 1. Headline findings (verified)

**1. Per platform, Claude-built programs** (`tables.md` §1):

*Yield* = correct answers Trusted ÷ all rows = coverage × precision: the share of questions that end with a correct answer let through. It counts useful output in one number, because refusing everything gives perfect precision and trusting everything gives full coverage. Example, OTF R1: ungated 0.870 × 0.898 = 0.781; gate 0.705 × 1.000 = 0.705; so "gate − ungated yield −0.076" means the gate gives up about 8 right answers per 100 questions to remove every wrong one. In "gate − X yield", positive means the gate lets more correct answers through than X; negative means X does. Yield ignores wrong answers, so read it next to precision or the wrong count.

| platform (programs, rows) | ungated: cov/prec (wrong) | history check (wrong) | gate: cov/prec (wrong) | gate − ungated: precision; yield | gate − history check: precision; yield |
|---|---|---|---|---|---|
| OTF R1 (24, 2,736) | 0.870/0.898 (243) | 0.824/0.910 (202) | 0.705/1.000 (0) | +0.102 [0.053, 0.157]; −0.076 [−0.126, −0.034] | +0.090 [0.045, 0.138]; −0.045 [−0.078, −0.021] |
| DEVS-Gen (22, 2,496) | 0.878/0.985 (34) | 0.790/0.998 (5) | 0.782/0.997 (5) | +0.013 [0.001, 0.031]; −0.084 [−0.164, −0.024] | 0.000; −0.007 [−0.016, −0.001] |
| coding agent (16, 1,824) | 0.976/1.000 (0) | 0.976/1.000 (0) | 0.969/1.000 (0) | 0.000; −0.007 [−0.016, 0.000] | 0.000; −0.007 [−0.016, 0.000] |

- **On OTF R1** the gate removes all 243 wrong answers, against 202 left by the history check. Relative to the history check, it costs 11.9 points of coverage and 4.5 points of yield. Relative to ungated, it costs 16.5 points of coverage.
- **On DEVS-Gen** the history check already removes most errors. The gate adds nothing to it and costs 0.7 points of yield. Program-wide checks and disagreement let 4 wrong answers through against the gate's 5 (not significant).
- **On IT (Claude-built, all platforms)** the gate is beaten: the history check gives 0.918/0.998 (3 wrong) and program-wide 0.911/0.999 (2 wrong), against the gate's 0.864/0.998 (3 wrong). Gate − history check yield −0.054 [−0.100, −0.021]; gate − program-wide −0.048 [−0.092, −0.014]. The cost is the Already-caught blocking (§7, item 1).
- **On the coding agent** there are no wrong answers to remove.
- Against random refusal at the gate's coverage, the gate's yield is higher by 0.072 [0.040, 0.102] on OTF R1 and by 0.010 [0.001, 0.023] on DEVS-Gen.

**2. All Claude-built programs (secondary, pooled across the three platforms):**
- 62 programs, 7,056 rows. Ungated gives 0.900/0.956 (277 wrong); the history check 0.851/0.966 (207); the gate 0.801/0.999 [0.997, 1.000] (5).
- Gate minus ungated: precision +0.043 [0.023, 0.067], yield −0.061 [−0.095, −0.034].
- Gate minus matched random refusal: yield +0.034 [0.019, 0.052].
- Generic behaviour tests (205 wrong) and program-wide checks (206) give about what the history check gives.
- Schema-only checks decline nothing in these sets, so they equal ungated.

**3. Most wrong answers are removed by checks that ran, not by declining to test.**
- Of 277 natural wrong answers on Claude programs: Failed history check 70, **Caught 44**, **Already caught 158**, Trusted 5, Untestable 0.
- Untestable declined 43 right answers and no wrong ones (§4).

**4. The wrong answers are not interpretation errors.**
- All 277 Claude and 1,161 Ollama wrong answers have an interpreted request equal to the oracle request.
- Interpretation was exact on wf_test (240 of 240) and wf_policy (91 of 91), and on 209 of 216 ml_test questions.
- So the errors arise downstream of interpretation. This run does not separate record extraction, applying the change, simulation, restart and splicing.
- A caveat: a misread request can yield no answer at all, so "wrong answers all had exact interpretations" is partly built in. Misreads show up as lost coverage instead: ml_test Claude coverage is 0.799 interpreted against 0.843 oracle (§5).

**5. The errors are concentrated in a few families** (§9).
- Ungated, Claude-built routing_probability gives 99 wrong (Loan) and 96 (Pharmacy), and resource_availability 25 and 8. The gate Trusts 0 and 0, and 1 and 0.
- Manufacturing has no wrong answers on any configuration (ungated coverage 0.729, the gate 0.723).
- 19 of 62 Claude programs give any wrong answer ungated. The gate removes all of them in 15; the 4 that keep a wrong Trusted answer are all DEVS-Gen.

**6. LLM judges.**
- At the gate's coverage, the gate's precision is significantly higher than the Haiku answer-level, Haiku program-level and Haiku ReAct judges (pooled view), and tied with the rest. Per platform, Haiku answer-level and Haiku ReAct are ties on DEVS-Gen; the gate's advantage is on OTF R1.
- On their own verdicts, on the Claude-built main-set rows, only Haiku ReAct keeps significantly more correct answers than the gate: yield −0.056 [−0.117, −0.005], while letting 8 wrong answers through against the gate's 0. On those 101 rows Sonnet's advantages are not significant (§2, §3).
- On the smaller shared samples Sonnet's advantage is significant: shared 150 (123 Claude-built rows, policy rows included) Sonnet answer −0.130 [−0.273, −0.010] and Haiku ReAct −0.138 [−0.272, −0.038]; react50 (39 Claude-built rows) Sonnet answer −0.179 [−0.400, −0.022] and Haiku ReAct −0.205 [−0.432, −0.029], both with 0 wrong (`tables.md` §3a, §3b).

**7. Ollama-built programs (OTF R1 only, 24 programs, 2,736 rows): the gate mostly declines.**
- Ungated: 0.610/0.304 (1,161 wrong). The gate: 0.042/0.983 (2 wrong); yield 0.042 against 0.185 ungated, −0.144 [−0.239, −0.061].
- 22 of 24 programs get no Trusted answer. The 6 Ollama manufacturing programs never produce a structured answer.
- Disagreement with a reading answer does better here: 0.155/0.957 (18 wrong); gate − disagreement yield −0.106 [−0.176, −0.042] (also significant on Ollama IT, Loan and no-effect controls, `tables.md` §1).

**8. Policy reuse (Study C): on a real policy change the gate Trusts nothing, because the history check fails.**
- **Variant P** (683 rows, 31 Claude programs): every row is Failed history check, so 0 Trusted and 0 wrong. Ungated answers 93.9% at 52.9% precision, so 302 wrong.
- **Variant H** (harmless rewording, 728 rows): the gate Trusts 72.1% at 100% (0 wrong); ungated gives 49 wrong.
- **The capability recheck was not exercised.** No policy document shares a test fingerprint, so no test result could carry over to a policy row except a recorded failure with an equal key, which never occurs. "Missed invalidations: 0" therefore tests nothing.
- The gate keeps no correct answer on P. On the P rows they judged (214 and 75 answered rows), the Haiku answer-level and Haiku ReAct judges' own verdicts TRUST about half, at 97.3% and 94.9% precision (§6).
- **Disagreement with a reading answer does much better on P:** it Trusts 47.4% of P rows (324 of 683) at precision 1.000, 0 wrong; gate − disagreement yield −0.474 [−0.619, −0.327]. On H it ties the gate (0.742/1.000; −0.021 [−0.174, 0.118]) (`tables.md` §6, rule-based judges).

## 2. Where the gate wins, ties and loses

| comparison (Claude-built unless stated) | result | evidence |
|---|---|---|
| vs ungated, OTF R1 | **wins on precision** (+0.102); **loses on yield** (−0.076) | §1 |
| vs ungated, DEVS-Gen | **wins on precision** (+0.013 [0.001, 0.031]); **loses on yield** (−0.084) | §1 |
| vs ungated, coding agent | tie (no errors; yield −0.007 [−0.016, 0.000]) | §1 |
| vs history check, OTF R1 | **wins on precision** (+0.090); **loses on yield** (−0.045) | §1 |
| vs history check, DEVS-Gen | tie on precision; **loses a little yield** (−0.007 [−0.016, −0.001]) | §1 |
| vs generic tests, program-wide (all Claude) | **wins on precision** (generic +0.033 [0.016, 0.056]; program-wide +0.034 [0.016, 0.057]); **loses a little yield** (−0.020) | §1 |
| vs history check and program-wide, IT (Claude-built) | **loses on yield** (−0.054 [−0.100, −0.021]; −0.048 [−0.092, −0.014]) with no fewer wrong (3 vs 3 and 2); precision −0.001 [−0.004, 0.000] | §1 |
| vs schema-only | same as ungated (schema declines nothing here) | §1 |
| vs disagreement with a reading answer (all Claude) | **wins on yield** (+0.138 [0.074, 0.206]) and precision (+0.006 [0.001, 0.014]; 33 vs 5 wrong) | §1 |
| vs disagreement, no-effect controls | **loses on yield** (−0.076 [−0.139, −0.033]) | §1 |
| vs disagreement, Loan; DEVS-Gen | tie (−0.047 [−0.167, 0.066]; +0.099 [−0.018, 0.215]) | §1 |
| vs disagreement, Ollama-built | **loses on yield** (−0.106 [−0.176, −0.042]); disagreement 0.155/0.957 (18 wrong), the gate 0.042/0.983 (2) | §1 |
| vs matched random refusal | **wins** (all Claude yield +0.034, precision +0.043) | §1 |
| vs Haiku answer-level, matched coverage (2,028 rows) | **wins** (precision +0.009 [0.002, 0.020]; 3 vs about 20 wrong). Per platform: OTF R1 +0.023 [0.006, 0.046]; DEVS-Gen tie | §2 |
| vs Haiku answer-level, own verdict | tie (yield +0.031 [−0.027, 0.078]); it lets 10 wrong through, the gate 3 | §2 |
| vs Haiku program-level (6,352 rows) | **wins** (matched precision +0.034 [0.017, 0.056]; own verdict yield +0.149 [0.096, 0.210]; it lets 160 wrong through) | §2 |
| vs Haiku ReAct (679 Claude-built main-set rows) | matched: **wins** (+0.014 [0.004, 0.039]). Own verdict: **loses on yield** (−0.056 [−0.117, −0.005]) but lets 8 wrong through against 0. The loss is on DEVS-Gen (−0.121 [−0.250, −0.015], 3 wrong) and, by process, Loan (−0.155 [−0.316, −0.011], 5 wrong); OTF R1 is a tie | §2 |
| vs Sonnet answer-level (101 Claude-built main-set rows) | matched: tie (both 1.000). Own verdict: not significant (−0.099 [−0.234, 0.011]); 0 wrong for both. On the 123 Claude-built rows of the shared 150, policy rows included: −0.130 [−0.273, −0.010] | §2, §3a |
| vs Sonnet ReAct (32 Claude-built main-set rows) | matched: tie. Own verdict: not significant, borderline (−0.094 [−0.303, 0.000]). Thin | §2 |
| react50 (39 Claude-built rows, policy included) | own verdict: **loses on yield** to Sonnet answer (−0.179 [−0.400, −0.022]) and Haiku ReAct (−0.205 [−0.432, −0.029]), both 0 wrong; the rest tie | §3b |
| vs gpt-oss, Gemma answer-level; Gemma ReAct (101 rows) | matched: ties (+0.025 to +0.032, intervals reach 0). Own verdict: **wins** vs gpt-oss answer (+0.257 [0.062, 0.436]); ties vs Gemma | §2 |
| vs gpt-oss ReAct (101 rows) | matched: tie (+0.024 [0, 0.055]). Own verdict: **wins on yield** (+0.317 [0.111, 0.500]); it TRUSTs 53.5% of rows and lets 1 wrong through | §2 |
| vs Qwen answer-level (101 rows) | matched: tie (+0.006 [0, 0.018]). Own verdict: tie (+0.050 [−0.123, 0.226]); it lets 1 wrong through | §2 |
| vs Qwen ReAct (101 rows) | matched: tie (+0.024 [0, 0.057]). Own verdict: tie (+0.129 [−0.075, 0.326]); 0 wrong. On OTF R1 the gate **wins on yield** (+0.333 [0.103, 0.615], 33 rows) | §2 |
| Ollama-built, judges' own verdicts | **loses on yield** to Haiku answer (−0.177 [−0.297, −0.076]) and Haiku ReAct (−0.167 [−0.312, −0.058]), with similar precision on the rows they judged (0.950 vs the gate's 0.949 on 537 rows; 0.950 vs 0.900 on 174 rows). Ties with the others (intervals reach 0), several of which have much lower precision (program-level 0.358, gpt-oss answer 0.714, gpt-oss ReAct 0.375, Qwen answer 0.556, Gemma ReAct 0.750, Qwen ReAct 0.800) | §2 |
| Study C, P variant, vs disagreement | **loses on yield** (−0.474 [−0.619, −0.327]); disagreement Trusts 47.4% at 1.000, 0 wrong | §6 |
| Study C, H variant, vs disagreement | tie (−0.021 [−0.174, 0.118]); both 0 wrong | §6 |
| Study C, P variant, LLM judges | **loses on yield** to Haiku answer (−0.505 [−0.663, −0.335]), Haiku ReAct (−0.493 [−0.717, −0.270]), program-level (−0.140 [−0.236, −0.059]) and Gemma ReAct (−0.462 [−0.917, −0.048]). Ties with the rest (13 rows or fewer). On P the program-level judge lets 119 wrong through; the others 0–3 | §6 |
| Study C, H variant, LLM judges | matched precision +0.000 to +0.143; **significant only vs program-level** (+0.061 [0.018, 0.113], which lets 36 wrong through) | §6 |

**Reading this:**
- On the 101 Claude-built main-set rows of the shared sample, the gate, Sonnet answer-level and Qwen ReAct let no wrong answer through (Sonnet ReAct: 0 on its 32 rows). On the larger Haiku samples the gate lets 3 of 2,028 and 5 of 6,352 through; over all rows, 5 on Claude-built programs and 2 on Ollama-built ones.
- At matched coverage, the gate is significantly better than the Haiku answer-level, program-level and ReAct judges, and ties with the rest.
- Its weakness is coverage. It refuses right answers that some LLM judges accept: significantly so for Haiku ReAct on DEVS-Gen and Loan, Sonnet and Haiku ReAct on the shared samples, on Ollama-built programs, and on a real policy change, where the history check fails and nothing can be Trusted.
- Rule-based baselines also beat it on yield in places: the history check and program-wide checks on IT; disagreement on no-effect controls, on Ollama-built programs, and on policy change P (47.4% kept with no wrong answer).
- Its added value over the history check is concentrated on OTF R1 programs.

## 3. LLM judges against the gate (detail)

Matching is within cells (set | process | cohort). The judge keeps the gate's number of rows per cell, by descending confidence, with expected precision over ties. The match is redone in every resample, and the differences are paired. n counts answered rows only (rule A).

| judge (main sets, Claude-built) | n | gate cov/prec (wrong) | judge at gate's coverage: prec (exp. wrong) | gate − judge prec | judge own cov/prec (wrong) | gate − own yield | AUROC |
|---|---|---|---|---|---|---|---|
| Haiku answer | 2,028 | 0.884/0.998 (3) | 0.989 (20) | +0.009 [0.002, 0.020] | 0.857/0.994 (10) | +0.031 [−0.027, 0.078] | 0.858 |
| Haiku program-level | 6,352 | 0.889/0.999 (5) | 0.965 (196) | +0.034 [0.017, 0.056] | 0.764/0.967 (160) | +0.149 [0.096, 0.210] | 0.582 |
| Haiku ReAct | 679 | 0.863/1.000 (0) | 0.986 (8) | +0.014 [0.004, 0.039] | 0.931/0.987 (8) | −0.056 [−0.117, −0.005] | 0.770 |
| Sonnet answer | 101 | 0.842/1.000 (0) | 1.000 (0) | 0.000 | 0.941/1.000 (0) | −0.099 [−0.234, 0.011] | 0.997 |
| Sonnet ReAct | 32 | 0.781/1.000 (0) | 1.000 (0) | 0.000 | 0.875/1.000 (0) | −0.094 [−0.303, 0.000] | 0.966 |
| Haiku answer (repeat, 150) | 101 | 0.842/1.000 (0) | 0.988 (1) | +0.012 [0, 0.036] | 0.842/0.988 (1) | +0.010 [−0.132, 0.141] | 0.604 |
| gpt-oss answer | 101 | 0.842/1.000 (0) | 0.968 (3) | +0.032 [0, 0.062] | 0.604/0.967 (2) | +0.257 [0.062, 0.436] | 0.455 |
| Gemma answer | 101 | 0.842/1.000 (0) | 0.973 (2) | +0.027 [0, 0.054] | 0.812/0.988 (1) | +0.040 [−0.107, 0.184] | 0.438 |
| Gemma ReAct | 101 | 0.842/1.000 (0) | 0.975 (2) | +0.025 [0, 0.050] | 0.901/0.989 (1) | −0.050 [−0.202, 0.099] | 0.557 |
| Qwen answer | 101 | 0.842/1.000 (0) | 0.994 (1) | +0.006 [0, 0.018] | 0.802/0.988 (1) | +0.050 [−0.123, 0.226] | 0.769 |
| gpt-oss ReAct | 101 | 0.842/1.000 (0) | 0.977 (2) | +0.024 [0, 0.055] | 0.535/0.982 (1) | +0.317 [0.111, 0.500] | 0.572 |
| Qwen ReAct | 101 | 0.842/1.000 (0) | 0.977 (2) | +0.024 [0, 0.057] | 0.713/1.000 (0) | +0.129 [−0.075, 0.326] | 0.717 |

**Per platform** (Claude-built; `main_analysis.json` `llm_judges.*.groups["platform=…"]`, rendered in `tables.md` §2):

| judge | platform | n | gate − judge matched precision | judge own cov/prec (wrong) | gate − own yield |
|---|---|---|---|---|---|
| Haiku answer | OTF R1 | 775 | +0.023 [0.006, 0.046] | 0.808/0.992 (5) | +0.012 [−0.061, 0.076] |
| Haiku answer | DEVS-Gen | 690 | +0.004 [−0.005, 0.018] | 0.891/0.992 (5) | −0.013 [−0.125, 0.080] |
| Haiku answer | coding agent | 563 | 0.000 | 0.883/1.000 (0) | +0.110 [0.064, 0.166] |
| Haiku ReAct | OTF R1 | 261 | +0.033 [0.006, 0.095] | 0.854/0.978 (5) | −0.031 [−0.120, 0.050] |
| Haiku ReAct | DEVS-Gen | 232 | +0.005 [0.000, 0.037] | 0.966/0.987 (3) | −0.121 [−0.250, −0.015] |
| Haiku ReAct | coding agent | 186 | 0.000 | 0.995/1.000 (0) | −0.011 [−0.056, 0.023] |
| Haiku program-level | OTF R1 | 2,380 | +0.089 [0.048, 0.135] | 0.655/0.903 (151) | +0.219 [0.125, 0.315] |
| Haiku program-level | DEVS-Gen | 2,192 | +0.010 [0.001, 0.025] | 0.767/0.995 (9) | +0.126 [0.032, 0.234] |
| Haiku program-level | coding agent | 1,780 | 0.000 | 0.908/1.000 (0) | +0.085 [0.028, 0.155] |
| Sonnet answer | OTF R1 / DEVS-Gen / agent | 33 / 37 / 31 | 0.000 each | 0.909 / 0.919 / 1.000, all 1.000 precision | −0.030 / −0.216 / −0.032, all intervals reach 0 |

Risk-coverage points for each judge and group, with the gate's point, are in `main_analysis.json` (`risk_coverage`). Among the Haiku judges, program-level is the weakest (AUROC 0.58); the gpt-oss and Gemma judges are as low or lower (0.44–0.57). On these 101 main-set rows, Haiku ReAct is the only judge whose own verdict significantly out-yields the gate on Claude-built programs; on the shared 150 and react50 samples Sonnet answer-level does too (§1, item 6). Sonnet answer-level has the highest AUROC (0.997); Sonnet is tied with the gate and its sample is thin.

## 3c. Jev, a non-generative answer-level judge (D30; added after the main run)

**What it is.** TypeSafe's hosted decision model `jev-1.14.0`.
- **How it decides:** it writes no text and runs no code; it returns a probability p for one yes/no question.
- **Its input:** the answer-level LLM judges' prompt, minus their output-format lines (checked byte for byte), plus "Is the program's answer with the change exactly right for the question?".
- **Verdict:** TRUST if p ≥ 0.5. Confidence is 100·p, and the service returns p to two decimals, so confidences tie.
- **Rows:** the same frozen 3,000 rows as the Haiku answer-level judge: 2,028 Claude-built main, 537 Ollama-built main and 435 policy rows. Every row was judged, with 0 failures.

**Sources.**
- Numbers come from `runs/main_v1/analysis_v2/` (same frozen `main_analysis.py` and arguments as v1). Every non-Jev value there equals `analysis_v1` (recursive JSON diff: 6 added Jev keys, 0 other differences).
- Run-clustered intervals come from `acmtrust_paper/sensitivity/analysis_v2_runclustered/`; its non-Jev values equal `analysis_v1_runclustered`.

**Against the gate** (main sets). "runs" is the run-clustered interval. "At gate's coverage" means Jev keeps its most confident answers, up to the gate's count in each cell.

| group | n | gate cov/prec (wrong) | Jev at gate's coverage: prec (exp. wrong) | gate − Jev precision | Jev own cov/prec (wrong) | gate − own yield | AUROC Jev / Haiku answer |
|---|---|---|---|---|---|---|---|
| Claude-built | 2,028 | 0.884/0.998 (3) | 0.977 (42) | +0.022 [0.008, 0.042]; runs [0.007, 0.043] | 0.735/0.969 (46) | +0.170 [0.108, 0.236]; runs [0.093, 0.249] | 0.625 / 0.858 |
| OTF R1, Claude-built | 775 | 0.813/1.000 (0) | 0.940 (38) | +0.060 [0.025, 0.105]; runs [0.020, 0.109] | 0.723/0.927 (41) | +0.143 [0.054, 0.237]; runs [0.035, 0.258] | 0.608 / 0.870 |
| DEVS-Gen | 690 | 0.875/0.995 (3) | 0.993 (4) | +0.002 [−0.009, 0.015] | 0.709/0.990 (5) | +0.170 [0.064, 0.266]; runs [0.041, 0.277] | 0.752 / 0.803 |
| coding agent | 563 | 0.993/1.000 (0) | 1.000 (0) | 0.000 | 0.785/1.000 (0) | +0.208 [0.131, 0.295]; runs [0.121, 0.310] | - |
| Ollama-built (OTF R1) | 537 | 0.073/0.949 (2) | 0.923 (3) | +0.026 [−0.750, 0.149] | 0.276/0.716 (42) | **−0.129 [−0.233, −0.045]; runs [−0.234, −0.042]** | 0.868 / 0.949 |

**By domain** (Claude-built):

| domain | n | gate − Jev precision at gate's coverage | Jev own cov/prec (wrong) | gate − own yield | AUROC Jev / Haiku |
|---|---|---|---|---|---|
| Manufacturing | 359 | 0.000 | 0.763/1.000 (0) | +0.228 [0.130, 0.346] | - |
| IT | 532 | +0.000 [0.000, 0.004] | 0.605/0.994 (2) | +0.327 [0.219, 0.441] | 0.585 / 0.701 (3 wrong answers only) |
| Loan | 554 | +0.040 [0.006, 0.089]; runs [0.005, 0.091] | 0.715/0.952 (19) | +0.058 [−0.068, 0.189] | 0.699 / 0.849 |
| Pharmacy | 583 | +0.043 [0.011, 0.092]; runs [0.012, 0.091] | 0.856/0.950 (25) | +0.098 [0.044, 0.168]; runs [0.030, 0.165] | 0.536 / 0.843 |

**Where Jev beats the gate.** Each case is a yield difference (gate − Jev's own verdict) whose interval is below 0 under both bootstraps, and in each Jev keeps more wrong answers than the gate:
- **Ollama-built programs:** −0.129 (above), keeping 42 wrong to the gate's 2. Haiku answer-level does the same (−0.177).
- **IT, Ollama-built:** −0.200 [−0.358, −0.085]; runs [−0.368, −0.070]. Jev keeps 15 wrong, the gate 2. Two of its builder cells, IT on Gemma and IT on gpt-oss, are also below 0 under both bootstraps; they are covered by this bullet and not listed separately.
- **Loan, Ollama-built:** −0.120 [−0.282, −0.004]; runs [−0.267, −0.008]. Borderline. Jev keeps 6 wrong; the gate keeps no answers there.
- **No-effect controls, Ollama-built:** −0.308 [−0.544, −0.102]; runs [−0.582, −0.093]. Jev keeps 3 wrong, the gate 0.
- **Effectful questions, Ollama-built** (n = 430): −0.084 [−0.169, −0.014]; runs [−0.176, −0.007]. Jev's own verdict is 0.239/0.621 (39 wrong), the gate's 0.070/0.933 (2).
- **Policy change P** (Claude-built, 214 rows): the gate Trusts none. Jev's own verdict keeps 50.9% at precision 0.615 (42 wrong): −0.313 [−0.466, −0.169]; runs [−0.432, −0.164]. Disagreement keeps 47.4% at 1.000 there (§6b N1). That share is over all 683 P rows, while Jev's 50.9% is over the 214 answered P rows of its subset, so the two are not directly comparable.

**Policy H** is a tie, not a win: Jev at the gate's coverage +0.024 [0.000, 0.062]; own verdict 0.810/0.978 (4 wrong), −0.023 [−0.192, 0.140].

At the gate's coverage, Jev never has a significant precision advantage over the gate in any group.

**Shared 150** (`shared_rows`, policy rows included; same rows as every model):
- **Claude-built, 123 rows with 11 wrong.** Gate 0.748/1.000 (0). Jev at the gate's coverage 0.978 (2): +0.022 [0.000, 0.037], a tie. Own verdict 0.715/0.920 (7 wrong): +0.089 [−0.065, 0.258], a tie. AUROC 0.666, against 0.968 for Haiku answer (0.832 for its repeat), 0.995 for Sonnet answer, and 0.385 / 0.529 / 0.771 for the gpt-oss / Gemma / Qwen answer judges.
- **Ollama-built, 27 rows.** Own verdict 0.296/0.750 (2): −0.148 [−0.429, 0.000], borderline.
- **react50** (39 Claude-built rows): own verdict 0.795/0.871 (4): −0.026, a tie.

**By domain × long-context mode** (`runs/main_v1/jev_long_context_v1/jev_long_context.md`; reviewed). "long" means the default request got `400 max_tokens_exceeded` and was resent once with the long-context header: 410 rows, of which Loan 371 (275 test, 96 policy) and IT 39. The mode follows input length, so this is not a controlled comparison. Many cells rest on few wrong answers.

| set | domain | built by | mode | rows | wrong | Jev own cov/prec (wrong) | Jev AUROC | Haiku answer AUROC |
|---|---|---|---|---|---|---|---|---|
| main | Manufacturing | Claude | default | 359 | 0 | 0.763/1.000 (0) | - | - |
| main | IT | Claude | default | 497 | 2 | 0.608/0.993 (2) | 0.385 (2 wrong) | 0.698 |
| main | IT | Claude | long | 35 | 1 | 0.571/1.000 (0) | 1.000 (1 wrong) | 0.691 |
| main | Loan | Claude | default | 374 | 42 | 0.759/0.944 (16) | 0.704 | 0.869 |
| main | Loan | Claude | long | 180 | 9 | 0.622/0.973 (3) | 0.721 | 0.751 |
| main | Pharmacy | Claude | default | 583 | 37 | 0.856/0.950 (25) | 0.536 | 0.843 |
| main | IT | Ollama | default | 116 | 55 | 0.336/0.692 (12) | 0.734 | 0.861 |
| main | IT | Ollama | long | 4 | 4 | 0.750/0.000 (3) | - | - |
| main | Loan | Ollama | default | 146 | 120 | 0.171/0.840 (4) | 0.947 | 0.982 |
| main | Loan | Ollama | long | 95 | 80 | 0.105/0.800 (2) | 0.936 | 0.985 |
| main | Pharmacy | Ollama | default | 176 | 111 | 0.403/0.704 (21) | 0.873 | 0.929 |
| policy | Loan | Claude | default | 117 | 26 | 0.650/0.789 (16) | 0.549 | 0.967 |
| policy | Loan | Claude | long | 96 | 11 | 0.646/0.871 (8) | 0.483 | 0.883 |
| policy | Pharmacy | Claude | default | 222 | 68 | 0.676/0.853 (22) | 0.836 | 0.914 |

What the table shows:
- **On the main sets, the long-context mode does not explain Jev's weak ranking.** Within Loan on Claude-built programs, its AUROC is about the same in both modes (0.70 default, 0.72 long). Among main-set Claude-built cells with at least 5 wrong answers, its lowest AUROC is Pharmacy's 0.54, and no Pharmacy row used long context.
- **On the policy set the pattern differs.** Loan is lower in long mode (0.48, 11 wrong) than in default (0.55, 26 wrong); both samples are small.
- **Haiku's AUROC is lower on long Loan inputs** (0.87 default, 0.75 long), with 42 and 9 wrong answers.

**Threshold note.** 67 of the 3,000 rows have p exactly 0.50 and so count as TRUST:
- main sets, Claude-built: 46 right, 5 wrong;
- main sets, Ollama-built: 2 right, 6 wrong;
- policy: 6 right, 2 wrong.

Jev's own-verdict numbers would move under a strict p > 0.5. AUROC and the risk-coverage curve do not depend on the threshold.

**Cost and latency.**
- **Spend:** $3.163 for 3,000 rows ($0.0011 per row; Haiku answer $0.0037), 75.3M prompt tokens. The 4-row dev check cost $0.0043.
- **Calls:** 3,410, of which 410 are default calls refused for length at $0 and resent with long context. The "failed calls 410" in `tables.md` §8 are these.
- **Time:** wall 0.33 s per row on average (median 0.26), against 28.6 s for Haiku answer-level. Median model time is 0.25 s for default calls and 0.43 s for long-context calls.
- **Ledger:** 7 of 3,410 records were lost to overlapping writes from parallel shards. Cost comes from the judgment rows, which are complete; run_manifest has the details.

**Caveats to state with any Jev number:**
- Its own-verdict numbers depend on the 0.5 threshold; use the risk-coverage curve (`risk_coverage` in the JSON), which needs none.
- `inconsistent` is n/a, not 0: it is false by construction.
- It cannot run code or compute.
- Its accuracy claims (and its stated weakness on counting, numbers and long inputs) are the vendor's own.
- It was added after the freeze and after the main run (D30), with no frozen file changed.
- Jev built no programs, so there is no self-judging case.

## 4. Paper tables and their files

| paper table | content | file and section |
|---|---|---|
| T1 | rule-based judges vs the gate, per platform, process, effect; pooled class (secondary) | `runs/main_v1/analysis_v1/tables.md` §1; `main_analysis.json` → `rule_judges` (per cell: `cell=set|process|cohort`) |
| T2 | LLM judges vs the gate at matched coverage and own verdict | `tables.md` §2; `llm_judges` (Jev: `analysis_v2/`, §3c here) |
| T2b | Jev by domain × long-context mode | `runs/main_v1/jev_long_context_v1/jev_long_context.md` |
| T3 | five models on the same 150 rows (answer and ReAct) | `tables.md` §3a/§3b; `shared_rows` |
| T4 | natural errors in plain terms; wrong answers Trusted | `tables.md` §4; `natural_errors` |
| T5 | planted errors (blind-spot checks, test questions) | `manifests/blindspots.md` "Single test run"; `manifests/probe_soundness_mlsys_v4_test.json`, `probe_soundness_workflow_test_v2.json` |
| T6 | interpretation; gate on interpreted vs oracle requests | `tables.md` §5; `interpretation` |
| T7 | Study C (policy reuse) | `tables.md` §6; `study_c` |
| T8 | judge agreement, self-judging | `tables.md` §7; `agreement` |
| T9 | cost | `tables.md` §8; `cost`; ledgers `runs/build_test_*/calls_*.jsonl` |
| T10 | per family, per program, OTF native path | `tables.md` §9–§11; `breakdowns`, `native_path` |
| frozen scorer | per set summaries | `runs/main_v1/{wf_test,wf_policy,ml_test}_summary.json` |
| subsets | judge rows | `manifests/judge_subsets_main_v1.json` (sha256 236c7028…), `..._react_sonnet50.json` (f9714d5c…) |

## 5. Details by item

**a. Disagreement-only.** The gate's request plus a vanilla reading answer, Trusting when they agree.
- All Claude-built: 0.667/0.993, 33 wrong, yield 0.663. The gate is +0.138 [0.074, 0.206] higher in yield, with 5 wrong.
- Disagreement does better on no-effect controls (−0.076 [−0.139, −0.033] for the gate), on Ollama-built programs (−0.106 [−0.176, −0.042]) and on policy change P (−0.474 [−0.619, −0.327]), and ties on Loan and DEVS-Gen.
- It is weak on IT (coverage 0.438), because vanilla reading answers 93 of 120 IT questions and gets 56 right (`runs/main_v1/logs/summary_ml_test.log`).
- A reading row exists for every analysis row; a reading answer exists for 93.8%.

**b. Judges vs the gate:** §2 and §3. The matched point is a confidence threshold per cell, with expected precision over ties, redone in each two-level resample (B = 2000). Also reported: each judge's own verdict, risk-coverage points, matched random refusal, the history check and generic tests. Correct-answer yield is the main coverage-side number.

**c. Per domain, platform, cohort, family and program:**
- Platforms: §1, item 1.
- By process (all Claude-built), wrong answers ungated → gate: IT 7 → 3, Loan 166 → 2, Pharmacy 104 → 0, manufacturing 0 → 0. On IT the history check also ends at 3 and program-wide at 2, with more yield than the gate (§1, item 1).
- Per family: §1, item 5 and `tables.md` §9. Per program: `tables.md` §10. Per builder model (cells): `main_analysis.json` `rule_judges["cell=…"]`.
- Ollama-built programs: §1, item 7. Qwen built 3 programs and is thin.
- B0 is native-only, with no structured path, and appears only in `tables.md` §11.

**d. Natural vs planted errors:**
- **Natural (this run):** the gate Trusted 5 of 277 wrong answers on Claude programs and 2 of 1,161 on Ollama programs. The 7 (listed in `tables.md` §4):
  - Loan, DEVS-Gen: 1 case_set and 1 resource_availability.
  - IT, DEVS-Gen Sonnet: 1 job_removal, 1 machine_removal and 1 failure_removal.
  - IT, OTF R1 Gemma: 1 task_priority and 1 machine_removal.
  - Three of the 7 rest on reused evidence from an earlier pass. None of the 7 is one of the planted blind-spot confusions (post-hoc diagnostic, 2026-11-11, reference runners only, `run_manifest.md`): for Loan `resource_availability-05` the reference gives 121,633 with one worker too many and 60,438–132,396 in any other pool, against the program's 59,262; for IT `task_priority-04` no priority value 0–20 gives the program's 2,365 (add-vs-set gives the right answer, 2,481).
- **Planted (test questions, before this run; `manifests/blindspots.md`):** after the D26 checks, every planted confusion is Trusted 0 times except RA-count (6), RA-pool (12) and TP-add (5). These are the two unresolved blind spots.
- Planted programs are our construction. The natural errors fall mostly in routing-probability and resource-availability.

**e. Cost per judge** (`tables.md` §8):
- **Gate:** 1.36 program executions per row on wf_test and 1.75 on ml_test, against generic tests 2.70 / 2.52 and program-wide 2.70 / 3.79. No model calls.
- **LLM judges, USD per row:** Haiku answer $0.0037, program-level $0.0033, ReAct $0.0038, Sonnet answer $0.052, Sonnet ReAct $0.064, gpt-oss answer $0.0063, Gemma answer $0.0056, Gemma ReAct $0.012, gpt-oss ReAct $0.0125 ($1.87 for 150 in the judgments; the ledger shows $1.93, the difference being calls that failed with HTTP 500). Qwen runs locally for $0, at 178 s per row (answer) and 348 s per row (ReAct).
- **Totals:** Haiku answer $11.06 (3,000 rows), program-level $5.93 (1,778), Haiku ReAct $3.84 (1,000), Sonnet answer $7.86 (150), Sonnet ReAct $3.19 (50).
- **Shared stage:** native answers $5.88, vanilla $6.17, RAG $1.89, interpretation $0.14.
- **Spend to date:**
  - The Claude ledger is at $60.40 of $80. It does not include the DEVS-Gen builds, which ran before the main run and outside the ledger, at about $7.80 (estimated, `run_manifest.md`). So the project Claude total is about $68.
  - Ollama is at $7.53 of $21 (sum of the non-Claude ledgers, earlier runs included).
  - Smoke and dev-check judge runs: $0.96 in all, $0.91 on the Claude ledger and $0.05 on the Ollama ledgers (included in the totals above).
  - Appendix note: one ledger line from the dev run is torn (two writers), an undercount of about $0.01.

**f. Study C (P vs H; missed and unnecessary invalidations):**
- All 31 policy registries start from the final test registry, and no policy fingerprint equals a test fingerprint. "Missed invalidations: 0" therefore cannot fail in this design; the capability recheck was not exercised (§1, item 8).
- P: every row is Failed history check, which removes the 302 wrong ungated answers and every right one. Disagreement with a reading answer keeps 324 of 683 P rows, all right.
- H: 72.1% Trusted at 100%. Of the rest, 144 are Failed history check (96 on DEVS-Gen), 33 Caught, 6 Already caught and 20 Can't express.
- 53 H rows have a capability and target that failed on test. Of those, 8 are Trusted (all right), 27 Caught, 6 Already caught and 12 Failed history check.
- Unnecessary invalidation, read as a correct H answer declined because of the test record, is at most 33 rows. No policy row cites test-scope evidence.

**g. Interpretation accuracy:**
- Exact on wf_test (240/240) and wf_policy (91/91).
- On ml_test, 209/216; the 7 misses are in dispatch_capacity (2), production_quantity (2), production_timing (2) and order_removal (1). Oracle requests raise ml_test Claude coverage from 0.799 to 0.843 at equal precision (0.999).
- The interpreted source is the paper's setting; the oracle source is a labelled diagnostic only.

**h. Judge agreement, self-judging, five-model comparison:**
- **Haiku repeat on 150 rows:** verdict agreement 0.853, kappa 0.651, confidence Spearman 0.845.
- **Self-judging** (`tables.md` §7; every judged row, wf_policy included): Haiku answer-level TRUSTs 6.6% of wrong answers on Claude-built programs (13 of 196) and 1.9% on Ollama-built ones (7 of 370). Haiku ReAct: 13.3% (10 of 75) and 1.5% (2 of 132).
  - The Claude-built counts include wf_policy rows (main-set wrong answers alone: 91 and 34), and policy rows exist only for Claude-built programs, so the two groups also differ in population.
  - That is a real gap in favour of Claude-built programs. It is confounded with how the programs fail: Ollama-built programs fail far more often, and their wrong answers may be easier to spot (not measured here). So this does not establish self-preference, but it does not rule it out.
  - Sonnet answer-level TRUSTs 0 wrong answers on both. gpt-oss answer TRUSTs 27% of wrong answers on Claude-built programs; Gemma ReAct 36% on Claude-built and 9.5% on Ollama-built; gpt-oss ReAct 36% (4 of 11) and 24% (5 of 21); Qwen answer 18% (2 of 11) and 19% (4 of 21); Qwen ReAct 27% (3 of 11) and 4.8% (1 of 21).
  - For the Ollama models, the own-builder cells are 4–14 rows, too few to read.
- **Five-model comparison** (`tables.md` §3a; 150 shared rows, 123 Claude-built with 11 wrong, 27 Ollama-built with 21 wrong):
  - On Claude-built rows the gate is 0.748/1.000 (0 wrong). At its coverage, every judge ties it on precision (all intervals reach 0).
  - Own verdicts on Claude-built rows: Sonnet answer (−0.130 [−0.273, −0.010]) and Haiku ReAct (−0.138 [−0.272, −0.038]) out-yield the gate, with 0 and 1 wrong. The gate out-yields gpt-oss answer (+0.195 [0.023, 0.352]) and gpt-oss ReAct (+0.252 [0.058, 0.431]). The rest tie.
  - Qwen ReAct ties on both (matched +0.027 [0, 0.058]; own verdict 0.691/0.965, 3 wrong, +0.081 [−0.107, 0.255]).
  - By AUROC on Claude-built rows: Sonnet answer 0.995, Haiku answer 0.968, Haiku ReAct 0.936, Haiku repeat 0.832, Qwen answer 0.771, Qwen ReAct 0.626 (Sonnet ReAct, 39 rows of react50: 0.956); the gpt-oss and Gemma judges and program-level are 0.39–0.56, near chance.

## 6. Reviewer questions

**Home advantage and equal access.**
- The gate, its probes and the family set are ours, developed on dev data (with the post-pilot changes below).
- The answer-level and ReAct judges see more than the gate: the question text and the answer value, which the gate never sees (`baseline_judges_design.md`). This asymmetry favours them. The program-level judge sees neither, only the program and the run.
- The ReAct judge's sandbox has the program and the same document view, so at least the gate's execution access. Our probe types are the method under test and are not given to it.
- Every judge receives the same structured request. Matched coverage removes the advantage of choosing an operating point.

**Post-pilot and post-freeze changes:**

| change | what | trigger | test data seen? |
|---|---|---|---|
| D21 | record-comparison route-probability probe; no-switch check | pilot v1: the rule probe never ran on OTF, so the gain was abstention | no: dev pilot only; reported with and without the no-switch check |
| D23 | policy fingerprint drops the chapter list; scoring rule A | carrying dev evidence to test; scoring definition | **partly**: rule A was chosen with test-side counts in view; probe soundness ran on test documents with the reference only; no system results |
| D24 | library fixes (route rule, reuse, NaN, seeding, flip witnesses) | full independent review | soundness on test and policy documents with the reference only; no system results |
| D25 | IT CPU/memory split | a planted CPU-into-memory program Trusted 5 wrong on test | planted-program diagnostics on test questions; no real system results |
| D26 | blind-spot checks for every family | planted confusion catalogue | planted diagnostics on test questions, run once; no real system results |
| D27 | main-run cuts (subsets, Ollama on OTF only, policy on Claude only) | budget and time | no |
| D28 | freeze; sandbox hardening; OTF IT record mapping grounded in cells | sandbox review; dev IT results | no (dev only) |
| D29 | gpt-oss, Gemma and Qwen judge the shared 150; Sonnet ReAct on 50 of them (reverses D27's "no Sonnet ReAct", about $15 budgeted) | Ollama credit added; Ashraf's addition | no: added before any judge ran |
| post-freeze (main run) | judge subsets drawn from all three test sets, wf_policy included | Ashraf's choice before the draw | no |
| post-freeze (main run) | `CLAUDE_CAP_USD` 25 → 80, `CAP_USD` 5 → 21 (two lines of `b0_build_test.py`) | budget | no; logged |

**Abstention vs detection.**
- Of 277 natural wrong answers on Claude programs: 70 Failed history check, 44 Caught, 158 Already caught, 5 Trusted, 0 Untestable. Untestable declined 43 right answers and no wrong ones.
- So the gate's gain over the history check comes from probes that ran and failed, on the request itself or earlier on the same capability and target.
- Already caught also declined 85 right answers, 71 of them in IT.
- At the gate's coverage, random refusal gets 0.956 precision against the gate's 0.999.

**Sample size and correlation.**
- 62 Claude-built and 24 Ollama-built programs; 456 main-set questions. Rows are not independent, so every interval comes from a two-level bootstrap over programs and questions.
- Wrong answers are concentrated in 19 programs and two families. The result is mostly about OTF R1 workflow programs on routing_probability and resource_availability.
- No formal guarantee is claimed. Qwen (3 programs) and the 50-row Sonnet ReAct sample are thin.

**Planted vs natural errors:** reported separately (§5d).

**Claude wrote the reference.** Partly true, and a real limit.
- **The setup (D5, D9, D12):** the workflow semantics were written before the engine. Three separately derived sources agree: hand-worked cases, the deterministic reference engine, and a checker written independently from the spec and I/O formats.
- **What it doesn't rule out:** the same agent wrote the spec, the engine and the hand-worked cases, so shared misreadings of the spec remain possible. Agreement says nothing about whether the semantics are the right ones. D12 lists 8 open semantic concerns; for example, which cases flip when a route probability changes rests on the JSON order of routes.
- **Prosimos:** comparisons show similar factual aggregates only.
- **Manufacturing and IT gold:** OTF's simulator plus a re-implementation, with a sampled blind check (`domain_readiness.md`).
- **Not done:** Ashraf's own hand-check (`hand_check_guide.md`) is not recorded as done; two blind agents did the delegated check.

**Realism of printed draws.**
- Exact what-if answers need the exogenous randomness, so the workflow documents print the route and duration draws (the deterministic-realization protocol). Real event logs do not.
- The results hold for records that state them; the route-records probe and the stated-flow walker depend on them.

**Baseline strength.**
- Sonnet answer-level reaches AUROC 0.997 and TRUSTs no wrong answer. The ReAct judges can run the program.
- The history check and generic tests run on every row; disagreement uses a full-record reading answer.
- The gate does not significantly beat the strongest judges (Sonnet answer and ReAct). On their own verdicts, Haiku ReAct beats it on yield on DEVS-Gen and Loan, and Sonnet answer and Haiku ReAct on the shared 150 and react50 samples (§2).
- Rule-based baselines beat it on yield in places: the history check and program-wide checks on IT; disagreement on no-effect controls, Ollama-built programs and policy change P.

**Judge noise.**
- Haiku agrees with itself on 85.3% of verdicts (kappa 0.651).
- On the same 123 Claude-built rows of the shared 150, the two Haiku runs give:
  - gate − judge matched precision: +0.000 and +0.011;
  - gate − own-verdict yield: −0.065 and −0.049 (`tables.md` §3a).
- Differences between judges of about 0.01–0.02 on the shared 150 are within run-to-run noise and should not be read as real.

**Interpretation:** see §1, item 4 and §5g. The misreads cost coverage; no wrong answer came from one.

**R1 vs original OTF-Tools.**
- B0 is the pinned original, native-only and unmodified, shown on its own native path (`tables.md` §11).
- On workflows, the native path is poor for both: precision 0.13–0.26 for Claude-built B0 and R1.
- The structured path with the gate is a different answer path. Its results are not B0's, and B0 is not described as improved.

**Memorization of public MLSys material.**
- The OTF-Tools code and MLSys documents are public (`domain_readiness.md`). Manufacturing and IT reuse those documents with new questions, and the workflow processes come from the public Zenodo record. Builder and judge models may have seen them.
- No memorization test was run. This is a stated limit.

**Cost:** see §5e. The gate costs program executions only (1.4–1.8 per row), fewer than generic tests. LLM judges cost $0.003–$0.064 per row, plus wall time.

**Sandbox history.**
- Every program in the main run used the hardened sandbox: a seccomp filter that allows AF_UNIX only and refuses io_uring, sha256 `fc5e2ee5…`, verified before the run and after the PC restart.
- Earlier runs (dev builds, pilots, earlier soundness runs) used the older form and are development evidence only.

**Policy reuse:** see §1, item 8 and §5f. The history check refused every row under a real policy change. The capability recheck was not exercised, and the gate keeps no correct answers on P. Disagreement with a reading answer keeps 47.4% of P rows at precision 1.000, so a cheaper baseline does better there.

## 6b. Paper results notes (how to phrase these facts; not limitations)

These are directions for wording the paper accurately. They are not items for the Limitations section.

**N1. Capability recheck on reuse: do not claim it works, anywhere in the paper.**
- **Fact:** the step that rechecks a program's capabilities when it is reused never ran in Study C. It runs only when a policy case reuses evidence recorded on a test case, and no policy fingerprint equals a test fingerprint. "Missed invalidations: 0" therefore cannot fail in this design (§5f).
- **What P shows:** under a real policy change, ungated programs answer 641 of 683 rows, 339 right and 302 wrong. The history check fails on every row, so the gate Trusts none: it is safe (0 wrong) but useless there (yield 0).
- **A baseline does better on P:** disagreement with a reading answer keeps 324 of 683 rows at precision 1.000, 0 wrong (gate − disagreement yield −0.474 [−0.619, −0.327]). Haiku answer-level keeps about half of the P rows it judged at 0.973.
- **Safe wording:** "Under a real policy change (P), the gate's history check fails on every row, so it Trusts nothing: no wrong answer gets through, but no right one does either. A reading-disagreement baseline keeps 47% of these rows with no wrong answer, so the gate is overly conservative after a policy change. Under a harmless change (H), the gate Trusts 72.1% at precision 1.000." Present the recheck as part of the design, if at all, never as a tested result.
- **Avoid:** "the recheck catches stale capabilities"; "0 missed invalidations" stated as evidence; and any claim that refusing everything is the best possible outcome on P, or that no method could do better there.
- **Possible framing, as an untested proposal:** after a policy change, the history check could fall back to a check that needs no recorded history, such as disagreement. That is future work; it was not run.

**N2. Ollama-built programs: a result about the builders, reported with the gate's thin evidence there.**
- **Fact:** only 2 of 24 Ollama-built programs get any Trusted answer, and the 6 Ollama manufacturing programs never answer on the structured path. Most of these programs are wrong (1,161 wrong answers ungated); the gate Trusts 2 of them.
- **Safe wording:** the gate stays safe on weak builders and refuses almost everything, because the programs fail its checks. State coverage and the wrong count together.
- **Caveat to state next to the result (not in Limitations):** the gate's precision on Ollama-built programs rests on very few Trusted answers (0.983 on the program-level judge rows, 0.949 on 537 Haiku-answer rows), so do not read it as a precise estimate.

**N3. D26 checks on OTF: only needed if the paper names the D26 checks individually.**
- **Why it might matter:** if the method section lists the D26 checks as part of the gate, a careful reader could assume they run on every platform. They don't: they need structured records, so on OTF's free-form records they are recorded as Untestable.
- **Why it matters little:** it changed no decision in the main run, no main-run error depends on it, and on OTF R1 Claude-built programs the gate let 0 wrong answers through without them.
- **What to do:** if the paper names the checks, add one clause: "checks that need structured records are recorded as Untestable on free-form records." If it describes the gate's checks at a general level (likely in 9 pages), skip this note.

## 7. Known limits

1. **IT Already-caught coverage cost:** 71 right IT answers on Claude programs are Already caught (blocking is by capability and target across questions). Kept as designed.
2. **Judges:**
   - gpt-oss ReAct often fails the frozen ReAct format: 38 of 150 replies unparsable (counted as DECLINE by the frozen judge). Ashraf chose to run it as frozen; this is reported as a setup failure with this model, and part of its low coverage comes from it.
   - Qwen 9B is a weak, thin judge: in ReAct, 19 of 150 rows ran out of the 8 turns, 4 were cut off and 1 was unparsable, all counted as DECLINE. Ollama Cloud has no prompt caching.
   - A single judge run is noisy (kappa 0.651).

## 8. Run facts

- **Scorer rows** (every program, request source and path, B0 included): wf_test 12,360 (60 programs), ml_test 10,920 (58), wf_policy 3,368 (43 Claude-built). 0 program failures.
- **Analysis rows** (interpreted requests, structured path, non-B0): wf_test 5,160, ml_test 4,632, wf_policy 1,411.
- **Judged rows:**
  - Haiku answer 3,000; Haiku ReAct 1,000.
  - Program-level 1,778 (every non-B0 program × chapter; B0 is native-only and excluded by `judges.py`).
  - Sonnet answer 150; Sonnet ReAct 50.
  - gpt-oss, Gemma and Qwen answer 150 each; gpt-oss, Gemma and Qwen ReAct 150 each. gpt-oss ReAct: 64 rows from the single-shard run and its resumes, then the remaining 86 in 4 parallel shards (33/20/12/21) after repeated Ollama Cloud HTTP 500s; 5 files, 150 unique keys.
  - Jev answer (D30, added 2026-11-13): 3,000, the `answer_haiku` subset, in 4 parallel shards; 3,000 unique keys, 0 failures, 410 long-context.
- **Frozen files:** unchanged except the two disclosed cap lines.
- **New scripts after the freeze**, each reviewed by a separate agent: `scripts/main_analysis.py` (2 rounds), `scripts/draw_react50.py`, `scripts/report_tables.py` (2 rounds). Later, also reviewed: `scripts/domain_tables.py` (Jev added to its run list on 2026-11-13, a post-run reporting change), `scripts/jev_judge.py` and `scripts/jev_long_context_table.py`. This report was fact-checked by a separate agent. §3c and the Jev paper text were checked separately on 2026-11-13, and the errors that check found are fixed. The domain_tables.py Jev change was reviewed together with jev_long_context_table.py.
