# Vouch with its capability record vs retesting every question (fresh record)

Rows that depended on the record and were rerun: 1944. Program executions on the main sets: record 11056, fresh 13807.

| group | n | record: cov / prec (wrong) | fresh: cov / prec (wrong) | record - fresh kept (pp), questions | runs | record - fresh precision (pp), questions | runs |
|---|---|---|---|---|---|---|---|
| class=claude | 7056 | 80.1 / 0.999 (5) | 81.1 / 0.999 (5) | -1.0 [-2.1, -0.2] | [-2.4, -0.2] | -0.0 [-0.0, 0.0] | [-0.0, 0.0] |
| class=ollama | 2736 | 4.2 / 0.983 (2) | 4.2 / 0.983 (2) | +0.0 [0.0, 0.0] | [0.0, 0.0] | +0.0 [0.0, 0.0] | [0.0, 0.0] |
| platform=otf_r1|class=claude | 2736 | 70.5 / 1.000 (0) | 73.1 / 1.000 (0) | -2.6 [-5.3, -0.6] | [-5.7, -0.4] | +0.0 [0.0, 0.0] | [0.0, 0.0] |
| platform=devs|class=claude | 2496 | 78.2 / 0.997 (5) | 78.3 / 0.997 (5) | -0.0 [-0.5, 0.4] | [-0.6, 0.4] | -0.0 [-0.0, 0.0] | [-0.0, 0.0] |
| platform=agent|class=claude | 1824 | 96.9 / 1.000 (0) | 96.9 / 1.000 (0) | +0.0 [0.0, 0.0] | [0.0, 0.0] | +0.0 [0.0, 0.0] | [0.0, 0.0] |
| process=it_ops|class=claude | 1800 | 86.4 / 0.998 (3) | 90.3 / 0.998 (3) | -3.9 [-7.8, -1.2] | [-7.9, -1.1] | -0.0 [-0.0, 0.0] | [-0.0, 0.0] |
| process=loan|class=claude | 1800 | 73.3 / 0.999 (2) | 73.1 / 0.999 (2) | +0.2 [-0.2, 1.0] | [-0.2, 0.9] | +0.0 [-0.0, 0.0] | [-0.0, 0.0] |
| process=pharmacy|class=claude | 1920 | 86.7 / 1.000 (0) | 86.9 / 1.000 (0) | -0.2 [-0.8, 0.0] | [-0.8, 0.0] | +0.0 [0.0, 0.0] | [0.0, 0.0] |
| process=manufacturing|class=claude | 1536 | 72.3 / 1.000 (0) | 72.3 / 1.000 (0) | +0.0 [0.0, 0.0] | [0.0, 0.0] | +0.0 [0.0, 0.0] | [0.0, 0.0] |

Decision terms on answered rows (record vs fresh):

- claude right fresh: Caught 39, Failed history check 277, Trusted 5716, Untestable 43
- claude right record: Already caught 85, Caught 25, Failed history check 277, Trusted 5645, Untestable 43
- claude wrong fresh: Caught 202, Failed history check 70, Trusted 5
- claude wrong record: Already caught 158, Caught 44, Failed history check 70, Trusted 5
- ollama right fresh: Caught 1, Failed history check 391, Trusted 114, Untestable 1
- ollama right record: Caught 1, Failed history check 391, Trusted 114, Untestable 1
- ollama wrong fresh: Caught 16, Failed history check 1143, Trusted 2
- ollama wrong record: Already caught 12, Caught 4, Failed history check 1143, Trusted 2
