import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim
# sensitivity: Applicant close 24h; and swapped docs' worker counts
for ac in (23*3600+59*60, 86400):
    sim.APPLICANT_CLOSE = ac
    r = []
    for doc, runs in (('policyP',(13,14)),('policyH',(15,16))):
        for run in runs:
            m,cfg,ch = sim.load('loan',doc,run); r.append(not sim.compare(sim.simulate(m,cfg,ch),ch))
    print('applicant close', ac, r)
sim.APPLICANT_CLOSE = 23*3600+59*60
# wrong-doc config
for proc, runs, d_ok, d_bad in (('loan',(15,16),'policyH','policyP'),('loan',(13,14),'policyP','policyH'),('pharmacy',(15,16),'policyH','policyP'),('pharmacy',(13,14),'policyP','policyH')):
    for run in runs:
        m,cfg,ch = sim.load(proc,d_ok,run)
        cfg2 = sim.doc_config(proc,d_bad)
        print(proc,d_ok,run,'with other doc config exact:', not sim.compare(sim.simulate(m,cfg2,ch),ch))
