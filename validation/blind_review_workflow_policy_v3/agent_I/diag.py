import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import load_doc, load_chapter, simulate
def show(fm, chn, change, case, pool=None):
    doc = load_doc(fm); ch = load_chapter(chn, doc)
    b = simulate(doc, ch); r = simulate(doc, ch, change)
    sb = set(b['task_log']); 
    print('---', chn, change)
    for x in sorted(r['task_log'], key=lambda x: x[4]):
        if x not in sb and (pool is None or x[6].startswith(pool) or x[0] == case):
            print('  new', x)
    for x in sorted(b['task_log'], key=lambda x: x[4]):
        if x[0] == case: print('  base', x)
show('loan_policyH_front_matter.txt', 'loan_policyH_chapter_Run_16.txt', {'unavail': {'Appraiser_1': [(39600, 54000)]}}, 'c0013', 'Appraiser')
show('loan_policyP_front_matter.txt', 'loan_policyP_chapter_Run_14.txt', {'unavail': {'AML Investigator_2': [(39600, 68400)], 'AML Investigator_3': [(39600, 68400)]}}, 'c0012', 'AML')
show('pharmacy_policyP_front_matter.txt', 'pharmacy_policyP_chapter_Run_13.txt', {'unavail': {'Technician_6': [(28800, 57600)], 'Technician_7': [(28800, 57600)]}}, 'c0012', 'XX')
