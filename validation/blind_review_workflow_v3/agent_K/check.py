import os, sys, glob
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sim import MODELS, parse_chapter, simulate, compare

for f in sorted(glob.glob(os.path.join(HERE, '*_chapter_Run_*.txt'))):
    proc = os.path.basename(f).split('_')[0]
    ch = parse_chapter(f)
    res = simulate(MODELS[proc], ch)
    d = compare(ch, res)
    print(os.path.basename(f), 'cases', len(ch['cases']), 'tasks', len(ch['task_log']), 'waits', len(ch['wait_log']),
          'decs', len(ch['dec_log']), '->', 'EXACT MATCH' if not d else f'{len(d)} diffs')
    for x in d[:15]:
        print('   ', x)
