#!/usr/bin/env bash
# Rerun the 1,944 rows whose frozen decision depended on the capability record, each with an empty record (12 shards).
cd "/c/Users/aashraf/Desktop/Work/2026/ACM Trust 2027"
PY=.tools/b0_env/Scripts/python.exe
D=acmtrust_paper/sensitivity/fresh_record
mkdir -p "$D"
for i in $(seq 0 11); do
  $PY -X utf8 acmtrust_paper/sensitivity/fresh_record_rerun.py rerun . acmtrust_paper/sensitivity/fresh_record_rows.json "$D" $i 12 > "$D/rerun_shard$i.log" 2>&1 &
done
wait
echo "rerun finished"
