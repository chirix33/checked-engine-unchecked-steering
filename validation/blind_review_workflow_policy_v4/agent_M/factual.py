import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim, glob
for fm in sorted(glob.glob('*_front_matter.txt')):
    doc = fm.replace('_front_matter.txt', '')
    pools, _ = sim.parse_front_matter(fm)
    print(doc, {k: (v['n'], v['d0'], v['d1'], v['open'], v['close']) for k, v in pools.items()})
    proc = sim.LOAN if doc.startswith('loan') else sim.PHARM
    for chf in sorted(glob.glob(doc + '_chapter_*.txt')):
        ch = sim.parse_chapter(chf, set(proc['act']))
        s = sim.Sim(proc, pools, ch).run()
        d = sim.compare(s, ch)
        print('  ', chf, 'EXACT' if not d else 'DIFF', len(ch['tasklog']), len(ch['waitlog']), len(ch['declog']))
        for x in d: print('     ', x)
