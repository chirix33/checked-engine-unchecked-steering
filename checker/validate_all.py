"""Run validate.py on every checker/out/*.json and write checker/validation_summary.json.
Usage: python -I checker/validate_all.py   (run from the project root)
"""
import os, sys, json, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate as V  # validator module only; never imports run.py

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
scen_dir = os.path.join(root, 'spec', 'scenarios')
out_dir = os.path.join(root, 'checker', 'out')
summary = {'scenarios': {}, 'totals': {}}
tot = {}
for sp in sorted(glob.glob(os.path.join(scen_dir, '*.json'))):
    sid = os.path.basename(sp)[:-5]
    op = os.path.join(out_dir, sid + '.json')
    if sid.startswith('P_'):
        base_id = sid.rsplit('_', 1)[0]
        # P_<model>_<seed>_<kind>: base is P_<model>_<seed>_factual
        parts = sid.split('_')
        base_id = '_'.join(parts[:3]) + '_factual'
    elif sid == 'H01_factual_contention_ties_loop' or sid.startswith('H15'):
        base_id = None
    else:
        base_id = 'H01_factual_contention_ties_loop'
    bp = os.path.join(out_dir, base_id + '.json') if base_id and base_id != sid else None
    rep = V.validate(sp, op, bp)
    rep['base'] = base_id if bp else None
    summary['scenarios'][sid] = rep
    for name, p in rep['properties'].items():
        tot.setdefault(name, {'pass': 0, 'fail': 0, 'not_applicable': 0})[p['status']] += 1
summary['totals'] = tot
summary['failing'] = {sid: {n: p['violations'] for n, p in r['properties'].items() if p['status'] == 'fail'}
                      for sid, r in summary['scenarios'].items()
                      if any(p['status'] == 'fail' for p in r['properties'].values())}
with open(os.path.join(root, 'checker', 'validation_summary.json'), 'w', encoding='utf-8') as fh:
    json.dump(summary, fh, indent=1)
print(json.dumps(tot, indent=1))
print('failing scenarios:', len(summary['failing']))
for sid, d in summary['failing'].items():
    print(sid, json.dumps(d)[:600])
