import sys, glob
sys.path.insert(0, '.')
from sim import *
for fm in sorted(glob.glob('*_front_matter.txt')):
    print(fm, parse_front_matter(fm))
for fn in sorted(glob.glob('*_chapter_*.txt')):
    doc = fn.split('_chapter_')[0]
    pools = parse_front_matter(doc + '_front_matter.txt')
    model = LOAN if fn.startswith('loan') else PHARM
    ch = parse_chapter(fn)
    res = simulate(model, pools, ch)
    d = compare(ch, res)
    print(fn, 'cases', len(ch['cases']), 'tasks', len(ch['task_log']), 'EXACT' if not d else 'DIFF', res['errors'][:3])
    for x in d[:15]: print('   ', x)
