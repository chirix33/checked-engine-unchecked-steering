#!/usr/bin/env bash
# Validation: rerun 48 random rows that did not depend on the record (4 shards). Decisions must equal the frozen ones.
cd "/c/Users/aashraf/Desktop/Work/2026/ACM Trust 2027"
PY=.tools/b0_env/Scripts/python.exe
D=acmtrust_paper/sensitivity/fresh_record
mkdir -p "$D"
for i in 0 1 2 3; do
  $PY -X utf8 acmtrust_paper/sensitivity/fresh_record_rerun.py check . "$D" $i 4 48 20261112 > "$D/check_shard$i.log" 2>&1 &
done
wait
echo "check finished"
