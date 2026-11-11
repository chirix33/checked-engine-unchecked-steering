import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim, glob
# Sensitivity: run each chapter with the OTHER document's front matter of the same process
pairs = {'loan_policyP': 'loan_policyH', 'loan_policyH': 'loan_policyP', 'pharmacy_policyP': 'pharmacy_policyH', 'pharmacy_policyH': 'pharmacy_policyP'}
for doc, other in pairs.items():
    pools, _ = sim.parse_front_matter(other + '_front_matter.txt')
    proc = sim.LOAN if doc.startswith('loan') else sim.PHARM
    for chf in sorted(glob.glob(doc + '_chapter_*.txt')):
        ch = sim.parse_chapter(chf, set(proc['act']))
        s = sim.Sim(proc, pools, ch).run()
        d = sim.compare(s, ch)
        nend = sum(1 for x in d if x[0] == 'case end')
        print(chf, 'with', other, 'front matter:', 'EXACT' if not d else f'DIFF ({nend} case ends differ; log diffs: {[x[0] for x in d if x[0] != "case end"]})')
