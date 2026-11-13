# Jev as an answer-level trust judge: design and fairness (D30)

Ashraf added TypeSafe Jev on 2026-11-12, after the freeze (D28) and after the main run had finished. This file fixes how Jev is used before any Jev call is made. The code is `scripts/jev_judge.py`, and the offline checks are `scripts/test_jev_judge_offline.py`. The run itself is done by the main-run session.

## What Jev is

Jev is TypeSafe's hosted "System One" decision model. It has no published weights and cannot be self-hosted.

- **Input and output:** it reads a `state` and answers typed questions. For a yes/no question (`noul`) it returns the probability of yes.
- **What it cannot do:** it writes no text, uses no tools, and cannot be fine-tuned on customer data. The same weights serve every account.
- **Context limits** (docs.typesafe.ai, read 2026-11-12):
  - by default, 64k tokens per request and 32k for the state plus any one question;
  - with the header `TypeSafe-Danger-Zone-Long-Context: true`, 262k for both. The docs call this "slower and less accurate."
- **Price:** $0.042 per million input tokens. Output is free.

## Rule: Jev gets exactly what the answer-level LLM judges got, and no more

| Item | Answer-level LLM judges (frozen `judges.py`) | Jev |
|---|---|---|
| Document view | front matter + the chapter the interpreted request names (`make_view`) | the same text |
| Program | its own code + the platform note (`base_blocks`) | the same text |
| Question, structured request, answer with and without the change | `_answer_task` | the same text |
| Output-format lines (VERDICT / CONFIDENCE / REASON) | present | dropped: Jev returns a probability, not text |
| The decision asked | "Decide whether the program's answer with the change is exactly right." | the same sentence in the state, plus one noul question: "Is the program's answer with the change exactly right for the question?" |
| Criteria, hints, examples, sub-questions | none | none. The docs suggest criteria and splitting into atomic questions. We use neither, because the LLM judges got neither. |
| Gold, bindings, labels, reference, other runs, native verdicts, build history, gate or probe results, other judges' outputs | never | never. Checked by sentinels in the offline tests. |
| Tools / code execution | none (answer level) | none |
| Rows | frozen D27 subsets | `answer_haiku`, the same 3,000 rows as Haiku's answer-level judge. They contain the shared 150 rows, read with the file's sha256. |
| Rows with no answer | not judged (rule A) | not judged |
| Prompt or wording changes after seeing results | none | none. The wording is fixed here, before any call. The dev run checks only that the path works; it reads no accuracy. |
| Threshold, temperature or calibration fitted on labels | none | none. Verdict is TRUST when p ≥ 0.5; confidence = 100·p. |

**Equality is tested, not assumed.** The offline test checks byte for byte that Jev's state equals the LLM judge's prompt text minus the output-format lines. The frozen `scripts/judges.py` still has its freeze hash `ab971e9d…`, and its prompt hash `ed45fe10bab7c96c` is the one recorded in every main-run answer-judge file.

## Choices that could favour or penalise Jev, and how they are fixed

1. **Long context.** By Haiku's own prompt-token counts, 858 of the 3,000 rows are over 32k tokens: 495 Loan, 296 Pharmacy and 67 IT. Jev's tokenizer differs, so its count will not match exactly.
   - **Rule:** send every request first with the default limits. Only if the service answers `400 max_tokens_exceeded` is the identical request resent once with the long-context header.
   - **Why this rule:** it depends on input length only, never on labels. It also gives Jev its documented best setting on every row.
   - **Reporting:**
     - Each row records `long_context`.
     - The mode goes with the process (Loan and Pharmacy rows are long), so results are reported by process × mode.
     - `main_analysis.py` has no such grouping, so this is a separate small table from the judgment rows, and the analysis is not changed.
2. **Confidence resolution.** LLM judges report whole numbers, so they have ties. Jev's probability is kept unrounded (100·p), at the model's own resolution. Matched coverage resolves ties by expected value, so this neither helps nor hurts beyond the model's real output.
3. **Verdict threshold 0.5.** The LLM judges report "your probability that the answer … is exactly right," and their verdict is checked against 50 (`inconsistent`). Jev's p is the same quantity, so 0.5 is the matching rule. The docs suggest 0.7 as a starting point, but that is a deployment choice.
   - The matched-coverage comparison ranks rows by confidence and does not use the verdict.
   - Jev's own-verdict numbers (`judge_own_verdict`, `gate_minus_judge_own_yield`) do depend on 0.5. Report them as such and point to the risk-coverage curve, which needs no threshold.
   - Jev's `inconsistent` is always false by construction. Report it as "n/a", not 0, so it is not read as better calibrated.
4. **Version.** Fixed at `jev-1.14.0`. A reply naming another version stops the run. Aliases move when a release ships.
5. **Failures.**
   - **DECLINE at confidence 0,** as for the LLM judges:
     - `unparsable`: a 200 reply that is not JSON, has no model field, has no answer, or has a value outside [0, 1];
     - `too_long`: a request still too long with long context.
   - **Retried with backoff, then raised** (never a verdict; the run is resumable): rate limits, overload, any 5xx, and network or protocol errors.
   - **The run stops:** authentication errors, validation errors, any other 4xx including 413, a redirect, or a reply from another model version.
6. **Answers.** The answer judged is the main run's own row. A row whose answer would have to be recomputed stops the run, so Jev cannot see an answer the other judges did not.
7. **The frozen prompt.** A run first checks that `scripts/judges.py` has its freeze hash and its recorded prompt hash, and stops otherwise. Byte-for-byte equality with the LLM judges' input therefore cannot drift silently.
8. **The key.**
   - It is sent only in the Authorization header.
   - Redirects are never followed, because urllib would forward the header.
   - Every error text is masked: the key and any 8-character piece of it are replaced before anything is logged, printed or raised. The offline test has the service echo the key back and checks that it never appears.

## What Jev is not, and what to disclose

- **Its role:** a cheap, calibrated decision model as a trust judge. It is an answer-level comparator only, with no ReAct and no program-level judge.
- **What it cannot do:** run code, compute, or reason step by step. TypeSafe and third parties report weakness on counting, dates, numeric closeness and multi-step questions, and "context rot" as the state grows. All of its accuracy claims are reported by the vendor.
- **When it was added:** after the main run, as a post-freeze addition (D30), with no change to frozen files.
- **Data sent to TypeSafe:**
  - What goes: the document chapter, the program code, the question, the interpreted request and the two answers. Nothing personal, and no gold.
  - TypeSafe says it does not train on customer data. Its retention terms are in its Data Processing Agreement; zero data retention is available only to enterprise customers.
  - Ashraf approved sending this.
- **Key handling:** the API key is Ashraf's, kept in `.env` as `TYPESAFE_API_KEY`. The code never prints or logs it, and the test checks this.

## Cost and time

- **Cost:** about 3,000 calls at roughly 15k–60k tokens each, so about 100M input tokens, about $4. The run's stop is `--max-usd 6.0`.
- **Time:** default calls take about 0.15 s, long-context calls longer. Expect under an hour sequentially; `--shard K/N` splits it.

## How the results enter the analysis

Rows go to `runs/judges_main_v1/main_answer_jev/judgments_jev-1.14.0.jsonl`.

- **Format:** the same fields as the other judges, with `judge = "answer"`, `model = "jev-1.14.0"`, `subset = "answer_haiku"` and the subsets file's sha256.
- **Analysis:** `scripts/main_analysis.py` reads any `judgments_*.jsonl` there, so Jev is compared with the gate at matched coverage like every other judge, with no change to the analysis code. The shared-150 and policy-set views pick it up too.
- **Ledger:** `runs/judges_jev_ledger/calls_jev-1.14.0.jsonl`, under the `judges/<folder>/` tag.
  - It is deliberately outside `runs/build_test_*`. Otherwise the runner's shared-ledger stop would count Jev's spend against the Ollama `CAP_USD`.
  - As a result, `section_cost`'s ledger-by-folder total omits Jev. Its per-judge cost comes from the judgment rows, which carry `usd` and tokens.
  - **The spending stop (`--max-usd`) is shared by shards running side by side,** as in `judges.py`. Before every row, each process reads the ledger lines every process has added since its last read.
- **Labels:** the self-judging and builder-class views treat Jev as a model that built no programs (`own_family` is always false).
- **Per-domain tables:** `scripts/domain_tables.py` (not frozen) lists its LLM runs by name (`LLM_RUNS`), so Jev is absent until `main_answer_jev|answer|jev-1.14.0` is added. It is judged on the same 3,000 rows as Haiku's answer judge, so adding it is like for like. Disclose that the line was added after the run.
- **Size:** Jev's confidence is continuous, so its risk-coverage curves have up to one point per row. That only makes `main_analysis.json` larger.
