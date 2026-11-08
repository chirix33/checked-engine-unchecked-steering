# Abstract draft for registration

Status: draft for Ashraf to edit and register by Nov 8, 2026, 11:59 PM Pacific. It claims no results, because the study has not run. Development numbers are left out on purpose. The title is provisional. Check in the submission system whether the abstract can be edited after registration. The GenAI disclosure is required at submission, not here.

**Title:** Portable Intervention-Level Assurance for Reusable LLM-Generated Process Models

**Abstract:**

LLM-generated executable process models can answer what-if questions about operational systems, and can be reused across records and policies. Matching recorded outcomes, however, does not establish that a program supports a particular requested change. A model may reproduce history and still mishandle an intervention, misbind it to current records, or lose validity when reused under a changed policy. A single pass-or-fail verdict hides these differences.

We present a portable assurance method that connects structured user interventions to executable checks and conditional, per-family capability evidence, and that rechecks this evidence on reuse. The method is a library that wraps existing generated-simulator systems rather than replacing them, and it retains their native validation. We evaluate it on manufacturing, IT operations, and business workflow processes, using deterministic realizations of published process models under a documented specification with independently checked reference answers. We compare it with native checks, stricter factual replay, schema-only validation, and generic behavioral testing at equal budget, separating better request interpretation from better selection on fixed programs. We report coverage, correct-answer yield, false permits, false rejections, and full cost, including null results.
