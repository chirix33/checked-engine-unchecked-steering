import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim, glob
for chf in sorted(glob.glob('*_chapter_*.txt')):
    proc = sim.LOAN if chf.startswith('loan') else sim.PHARM
    ch = sim.parse_chapter(chf, set(proc['act']))
    zeros = [(k, v) for k, v in ch['work'].items() if 0 in v]
    wz = [(k, v) for k, v in ch['wait'].items() if 0 in v]
    # same-time ties within a pool queue in the recorded task log
    from collections import Counter
    cnt = Counter((r[3], proc['act'][r[1]][0]) for r in ch['tasklog'])
    ties = sum(1 for k, n in cnt.items() if n > 1)
    # tasks that waited for a worker (start > enabled) during working hours
    print(chf, 'zero work entries:', zeros, 'zero waits:', wz, 'same-enabled-time same-pool groups:', ties,
          'tasks delayed:', sum(1 for r in ch['tasklog'] if r[4] > r[3]))
