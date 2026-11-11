import sys, glob
sys.path.insert(0, '.')
from sim import *
for fn in sorted(glob.glob('*_chapter_*.txt')):
    doc = fn.split('_chapter_')[0]
    other = doc.replace('policyP','X').replace('policyH','policyP').replace('X','policyH')
    model = LOAN if fn.startswith('loan') else PHARM
    ch = parse_chapter(fn)
    r = simulate(model, parse_front_matter(other + '_front_matter.txt'), ch)
    d = compare(ch, r)
    print(fn, 'with', other, 'EXACT' if not d else f'DIFF ({sum(1 for x in d if x.startswith("case end"))} case ends, {len(d)} diff lines)')
