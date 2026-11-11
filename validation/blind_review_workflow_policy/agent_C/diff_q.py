import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json, sim
qs={q['qid']:q for q in json.load(open('questions.json'))}
for qid in sys.argv[1:]:
    q=qs[qid]
    proc = sim.LOAN if q['front_matter_file'].startswith('loan') else sim.PHARM
    ps, pr = sim.load_front(q['front_matter_file'], proc)
    ch = sim.load_chapter(q['chapter_file'])
    change, target = sim.parse_question(q, ps)
    b = sim.simulate(proc, ps, pr, ch); n = sim.simulate(proc, ps, pr, ch, change)
    print('==',qid,target,'base',b['ends'][target],'new',n['ends'][target])
    B=set(b['tasklog']); N=set(n['tasklog'])
    for r in sorted(B-N, key=lambda r:(r[3],r[0])): print('  -',r)
    for r in sorted(N-B, key=lambda r:(r[3],r[0])): print('  +',r)
    print('  target rows new:'); [print('   ',r) for r in n['tasklog'] if r[0]==target]
    print('  ends changed:',{c:(b['ends'].get(c),n['ends'].get(c)) for c in set(b['ends'])|set(n['ends']) if b['ends'].get(c)!=n['ends'].get(c)})
