import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODELS, parse_chapter, simulate
def show(proc, f, chg, case):
    m = MODELS[proc]; ch = parse_chapter(f, m)
    for lab, c in (('factual', None), ('changed', chg)):
        r = simulate(m, ch, c)
        print('--', lab, r['ends'].get(case))
        for row in r['tasklog']:
            if row[0] == case: print('  T', row)
        for row in r['waitlog']:
            if row[0] == case: print('  W', row)
show('loan', 'loan_chapter_Run_06.txt', {'work': [('c0009', 'Return application back to applicant', 1, 1)]}, 'c0009')
show('loan', 'loan_chapter_Run_05.txt', {'unavail': {'Appraiser': [(0, 39600, 54000), (1, 39600, 54000)]}}, 'c0005')
