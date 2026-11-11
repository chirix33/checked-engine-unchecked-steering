import sys, os, re, difflib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import load_doc, load_chapter, read, CHAPTERS
def part(flat, a, b):
    return flat[flat.index(a):flat.index(b)]
for p in ('loan', 'pharmacy'):
    A = ' '.join(read(p + '_policyP_front_matter.txt').split()); B = ' '.join(read(p + '_policyH_front_matter.txt').split())
    print('=====', p)
    for a, b in (('Arrivals.', 'Workers.'), ('Workers.', 'Process.'), ('Process.', 'Rules.')):
        sa, sb = part(A, a, b), part(B, a, b)
        print(a, 'identical' if sa == sb else 'DIFFERS')
        if sa != sb:
            for d in difflib.ndiff(re.split(r'(?<=\.) ', sa), re.split(r'(?<=\.) ', sb)):
                if d[0] in '+-?': print('  ', d)
    da, db = load_doc(p + '_policyP_front_matter.txt'), load_doc(p + '_policyH_front_matter.txt')
    print('nodes equal:', da['nodes'] == db['nodes'], 'start equal:', da['start'] == db['start'])
    for k in da['pools']:
        if da['pools'][k] != db['pools'][k]: print('  pool diff', k, da['pools'][k], db['pools'][k])
orders = {}
for fm, ch in CHAPTERS:
    c = load_chapter(ch, load_doc(fm)); orders.setdefault(fm.split('_')[0], set()).add(tuple(c['act_order']))
for k, v in orders.items(): print(k, 'activity order same across chapters:', len(v) == 1, list(v)[0])
