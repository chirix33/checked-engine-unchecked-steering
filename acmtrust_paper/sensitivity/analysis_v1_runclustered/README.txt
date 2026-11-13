Run-clustered bootstrap: a disclosed sensitivity check on the frozen main analysis.

The frozen analysis (scripts/main_analysis.py, B = 2000, seed 20261111) resamples programs, then individual
questions. Questions on the same run share records and random draws: the 240 workflow test questions come from
16 runs. This script reruns the same analysis with one change: the second level resamples whole runs
(document + scope, e.g. "workflow_loan_test | Run 12") instead of single questions, and every question of a run
gets that run's weight. Programs are still resampled at the first level, as before.

Nothing else changes: same rows, same matching, same seed, same B. Point estimates are therefore identical to
the frozen ones by construction (the first weight row is all ones); only the intervals move. The script imports
the reviewed main_analysis.py and replaces its boot_weights function at run time; no project file is modified.

Usage (from the project root):
  python -X utf8 acmtrust_paper/sensitivity/run_clustered.py . acmtrust_paper/sensitivity/analysis_v1_runclustered
