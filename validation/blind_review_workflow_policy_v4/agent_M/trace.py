import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim, runpy, io, contextlib, json
# capture Sim instances created by answer.py
made = []
orig_run = sim.Sim.run
def run(self):
    r = orig_run(self); made.append(self); return r
sim.Sim.run = run
with contextlib.redirect_stdout(io.StringIO()):
    runpy.run_path('answer.py')
det = json.load(open('answer_details.json'))
for i, d in enumerate(det):
    b, s = made[2*i], made[2*i+1]
    t = d['target']
    print('==', d['qid'], d['change'])
    bt = set((r for r in b.tasklog if r[0] == t)); st = set((r for r in s.tasklog if r[0] == t))
    for r in sorted(bt - st, key=lambda r: r[4]): print('   old', r)
    for r in sorted(st - bt, key=lambda r: r[4]): print('   new', r)
    bd = set(r for r in b.declog if r[0] == t); sd = set(r for r in s.declog if r[0] == t)
    for r in sorted(bd ^ sd, key=lambda r: r[3]): print('   dec', 'new' if r in sd else 'old', r)
