import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim
pools, _ = sim.parse_front_matter('loan_policyP_front_matter.txt')
ch = sim.parse_chapter('loan_policyP_chapter_Run_14.txt', set(sim.LOAN['act']))
s = sim.Sim(sim.LOAN, pools, ch, unavail={'AML Investigator_2': [(39600, 68400)], 'AML Investigator_3': [(39600, 68400)]}).run()
b = sim.Sim(sim.LOAN, pools, ch).run()
print('AML tasks factual:'); [print(' ', r) for r in sorted(b.tasklog, key=lambda r: r[4]) if r[1] == 'AML Check']
print('AML tasks changed:'); [print(' ', r) for r in sorted(s.tasklog, key=lambda r: r[4]) if r[1] == 'AML Check']
print('c0012 changed:'); [print(' ', r) for r in s.tasklog if r[0] == 'c0012']
