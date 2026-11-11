import sys; sys.path.insert(0,'.')
from sim import *
d,c='loan_policyP_front_matter.txt','loan_policyP_chapter_Run_13.txt'
for m in ({}, {'work':{(4,'Assess loan risk',1):3864}}):
    r=simulate(d,c,m)
    print([t for t in r['tasks'] if t[0]==4 and t[1] in('Assess loan risk','Reject application','Design loan offer')],r['ends'][4])
# cross-document application
import glob
for ch in sorted(glob.glob('*_chapter_*.txt')):
    base=ch.split('_chapter_')[0]
    proc=base.split('_')[0]
    for pol in 'PH':
        doc=f'{proc}_policy{pol}_front_matter.txt'
        try: ok,_=check(doc,ch)
        except Exception as e: ok='ERR '+repr(e)[:60]
        print(ch,'with',doc,ok)
