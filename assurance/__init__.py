"""Intervention-level assurance for reusable generated process models (D16).

A library that wraps existing executable-process systems. It decides whether a particular program is suitable
for a particular requested intervention, using structured requests, contract checks, conditional per-family
capability evidence and oracle-free probes, and it rechecks that evidence when a program is reused.

Nothing in this package may read reference-engine code, gold answers or test labels. Evaluation code lives in
`scripts/`, outside this package.
"""

__version__ = "0.1.0"
