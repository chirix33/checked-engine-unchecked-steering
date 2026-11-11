import re,difflib
def sect(fn):
    t=open(fn,encoding='utf-8').read().replace('\n',' ')
    t=re.sub(r'\s+',' ',t)
    out={}
    for key,nxt in [('Workers.','Process.'),('Process.','Rules.'),('Arrivals.','Workers.'),('Time.','Arrivals.')]:
        a=t.index(key); b=t.index(nxt)
        out[key]=t[a:b]
    out['Rules.']=t[t.index('Rules.'):]
    return out
for d in ['loan','pharmacy']:
    P=sect(d+'_policyP_front_matter.txt'); H=sect(d+'_policyH_front_matter.txt')
    for k in P:
        if P[k]!=H[k]:
            print(d,k,'DIFFERS')
            if k in ('Workers.','Process.','Arrivals.'):
                for s in difflib.ndiff(re.split(r'(?<=\.) ',P[k]),re.split(r'(?<=\.) ',H[k])):
                    if s[0] in '+-': print('  ',s)
        else: print(d,k,'same')
