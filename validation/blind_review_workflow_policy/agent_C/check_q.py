import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json, sim
qs=json.load(open('questions.json'))
for q in qs:
    proc = sim.LOAN if q['front_matter_file'].startswith('loan') else sim.PHARM
    ps, pr = sim.load_front(q['front_matter_file'], proc)
    ch = sim.load_chapter(q['chapter_file'])
    change, target = sim.parse_question(q, ps)
    base = sim.simulate(proc, ps, pr, ch)
    info=''
    for (c,a,v,val) in change.get('work',[]):
        rows=[r for r in base['tasklog'] if r[0]==c and r[1]==a]
        info=f"plan={ch['work'][(c,a)]} baseline visits={[r[2:] for r in rows]}"
    for (c,w,v,val) in change.get('wait',[]):
        rows=[r for r in base['waitlog'] if r[0]==c and r[1]==w]
        info=f"plan={ch['waits'][(c,w)]} baseline={rows}"
    for (c,d,v,val) in change.get('draw',[]):
        rows=[r for r in base['declog'] if r[0]==c and r[1]==d]
        info=f"plan={ch['draws'][(c,d)]} baseline={rows}"
    if 'probs' in change:
        d=list(change['probs'])[0]
        rows=[r for r in base['declog'] if r[0]==target and r[1]==d]
        info=f"target baseline {d} rows={rows}; base probs={pr[d]}"
    if 'remove' in change:
        c=change['remove'][0]
        info=f"removed arrival {ch['cases'][c]} target arrival {ch['cases'][target]}"
    print(q['qid'], target, info)
