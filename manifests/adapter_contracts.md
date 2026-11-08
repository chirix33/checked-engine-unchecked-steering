# Adapter contracts and information parity

What each backend, policy and comparator sees at runtime, and what stays evaluation-only. Written 2026-11-08, before the pilot's program stage. Categories follow D16: 1 is environment repair, 2 a shared task adapter, 3 an assurance method component, 4 R1.

## Information available at runtime

| Item | OTF programs | DEVS-Gen programs | Assurance library | Vanilla LLM / RAG | Interpreter |
|---|---|---|---|---|---|
| Document (policy text and records), as the document map | Read by the program's own reader | Built into the generic stdin input from the same tables (Category 2) | Yes, to build the schema, witnesses and edits | Whole text / top 8 BM25 chunks | Names only: runs, case ids, activities, waits, decisions with route labels, pools with sizes |
| Question text | Native patch step only | No (gets structured input) | No (gets the structured request) | Yes | Yes |
| Structured request | No | Applied by the adapter | Yes | No | Produces it |
| Gold answers, hidden bindings, effect labels | No | No | No | No | No |
| Reference engine and spec code | No (the sandbox runs only the program) | No: `/mnt` and `/home` are hidden by the sandbox, network cut | No imports, checked by review | No | No |
| Task spec text given at build time | OTF build prompt (pinned) | DEVS-Gen task YAML in `adapters/devs_gen_tasks/` (Category 2, hashed in `hashes_devs_gen_tasks.txt`) | n/a | n/a | n/a |

The `oracle` request source in the pilot is the only deliberate exception. It passes the question's hidden binding to the library as its structured request, to measure the gate apart from interpretation. It is labeled a diagnostic and never reported as a method result.

## What each adapter can express

| Family / operation | OTF structured path (probes and pilot answers) | OTF native path | DEVS-Gen |
|---|---|---|---|
| Activity duration, timer delay, route draw (one case, one visit) | Edit one plan cell in the document map, only if the plan lists that visit | LLM patch over the program's own input records | Edit one entry of `work`, `waits` or `draws` |
| Route probabilities | Edit the stated probabilities in the policy text | LLM patch, if the program exposes them | `route_probabilities` |
| Add workers throughout | A params key naming the pool with the stated size, else edit the pool sentence in the policy text | LLM patch on params | `workers` |
| Workers unavailable for an interval | Not expressible | LLM patch, if the program has such an input | `unavailable` |
| Remove a case | Delete the case's rows from every table of the run | LLM patch | Drop the case from every list |

A change the adapter cannot express is reported as "inexpressible", which is separate from a program failure and from a probe failure.

## Checks applied by configuration

| Configuration | Contract | Factual replay | Probes | Registry reuse | Binding check |
|---|---|---|---|---|---|
| `native` | no | no | no | no | reported separately (`native+binding` path) |
| `schema` | yes | no | no | no | same |
| `replay` | yes | yes | no | no | same |
| `generic` | yes | yes | input use on random families and targets, 3 executions | no | same |
| `program_wide` | yes | yes | one input-use probe per case-level family | no | same |
| `directed` | yes | yes | requested family, operation and target, at most 3 executions | same key, target and scope only; any failure blocks | same |

Researcher-supplied runtime material, disclosed and costed:
- The contract's family list and value rules (`assurance/request.py`, `contract.py`).
- The probe templates (`assurance/probes.py`).
- The calendar and route parsing of the policy text.

Every configuration gets the same material. The vanilla and RAG comparators get the document and the question, and no structured request.
