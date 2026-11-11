# For each question, rerun with the pending-queue tie order reversed (same enabled time only)
# to see whether the answer depends on the same-time tie-break rule.
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim, json, runpy, io, contextlib
orig_assign = sim.Sim.assign
def rev_assign(self):
    self.pending.sort(key=lambda p: (p[0], [-x for x in (p[1], int(p[2][1:]), p[3], p[4])]))
    keep = list(self.pending)
    self.pending.sort = lambda *a, **k: None  # keep reversed order
    orig_assign(self)
class L(list):
    pass
def rev_assign2(self):
    pend = sorted(self.pending, key=lambda p: (p[0], -p[1], -int(p[2][1:]), -p[3], -p[4]))
    self.pending = L(pend); self.pending.sort = lambda *a, **k: None
    orig_assign(self)
sim.Sim.assign = rev_assign2
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    runpy.run_path('answer.py')
alt = json.load(open('answer_details.json'))
sim.Sim.assign = orig_assign
with contextlib.redirect_stdout(io.StringIO()):
    runpy.run_path('answer.py')
base = json.load(open('answer_details.json'))
for a, b in zip(base, alt):
    print(a['qid'], a['answer'], b['answer'], 'SAME' if a['answer'] == b['answer'] else 'DEPENDS ON TIE ORDER', 'fact_ok(rev)=', b['fact_ok'])
