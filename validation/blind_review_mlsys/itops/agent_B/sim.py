import re, json, sys, copy
D = ".."
def tid(t): return int(t[1:])
def parse(fn):
    L = open(f"{D}/{fn}").read().split("\n")
    machines = {}; tasks = {}; log = []
    sec = None
    for l in L:
        if l.endswith(": Machines"): sec="m"; continue
        if l.endswith(": Task log"): sec="t"; continue
        if l.endswith(": Events"): sec="e"; continue
        if sec=="m":
            p=l.split()
            if p and p[0].startswith("M") and len(p)==5:
                machines[p[0]]=dict(cpu=int(p[1]),mem=int(p[2]),fail=None if p[3]=='-' else int(p[3]),ret=None if p[4]=='-' else int(p[4]))
        elif sec=="t":
            p=l.split()
            if len(p)>=9 and p[0].isdigit():
                t=int(p[0]); ev=p[7]; mc=p[8]
                log.append((t,p[1],ev,mc))
                if ev=="submit":
                    tasks[p[1]]=dict(id=p[1],sub=t,job=p[2],pri=int(p[3]),cpu=int(p[4]),mem=int(p[5]),run=int(p[6]))
    return machines,tasks,log

def simulate(machines,tasks,tmax=10**7):
    ids=sorted(machines)
    up={m:True for m in ids}
    running={m:{} for m in ids}  # task->(start,end)
    waiting=set(); first={}; out=[]
    sub={}
    for k,t in tasks.items(): sub.setdefault(t['sub'],[]).append(k)
    fails={}; rets={}
    for m,v in machines.items():
        if v['fail'] is not None: fails.setdefault(v['fail'],[]).append(m)
        if v['ret'] is not None: rets.setdefault(v['ret'],[]).append(m)
    pending_ends={}
    def key(k): t=tasks[k]; return (-t['pri'],t['sub'],tid(k))
    def free(m):
        c=machines[m]['cpu']-sum(tasks[k]['cpu'] for k in running[m])
        r=machines[m]['mem']-sum(tasks[k]['mem'] for k in running[m])
        return c,r
    now=-1
    while True:
        cand=set(sub)|set(fails)|set(rets)
        for m in ids:
            for k,(s,e) in running[m].items(): cand.add(e)
        cand={t for t in cand if t>now}
        if not cand: break
        now=min(cand)
        if now>tmax: break
        # finishes
        fin=[]
        for m in ids:
            for k,(s,e) in list(running[m].items()):
                if e==now: fin.append((tid(k),k,m))
        for _,k,m in sorted(fin):
            del running[m][k]; out.append((now,k,'finish',m))
        # failures
        fl=[]
        for m in sorted(fails.get(now,[])):
            if m in up and up[m]:
                up[m]=False
                for k in sorted(running[m],key=tid):
                    fl.append((now,k,'fail',m)); waiting.add(k)
                running[m]={}
        out+=fl
        for m in rets.get(now,[]): up[m]=True
        for k in sorted(sub.get(now,[]),key=tid):
            waiting.add(k); out.append((now,k,'submit','-'))
        # round
        last=None; resv=None  # (m,R,cpu,mem)
        while True:
            c=[k for k in waiting if last is None or key(k)>last]
            if not c: break
            k=min(c,key=key); last=key(k); T=tasks[k]
            started=False
            for m in ids:
                if not up[m]: continue
                fc,fm=free(m)
                if fc<T['cpu'] or fm<T['mem']: continue
                if resv and resv[0]==m:
                    R=resv[1]
                    if now+T['run']<=R: pass
                    else:
                        lc=machines[m]['cpu']-sum(tasks[x]['cpu'] for x,(s,e) in running[m].items() if e>R)-resv[2]
                        lm=machines[m]['mem']-sum(tasks[x]['mem'] for x,(s,e) in running[m].items() if e>R)-resv[3]
                        if not(lc>=T['cpu'] and lm>=T['mem']): continue
                running[m][k]=(now,now+T['run']); waiting.discard(k); out.append((now,k,'start',m)); first.setdefault(k,now); started=True; break
            if started: continue
            if resv is None and T['pri']>=9:
                for m in ids:
                    if not up[m]: continue
                    fc,fm=free(m)
                    fr=[x for x in running[m] if tasks[x]['pri']<=1]
                    fr.sort(key=lambda x:(tasks[x]['pri'],-running[m][x][0],-tid(x)))
                    ev=[]
                    for x in fr:
                        if fc>=T['cpu'] and fm>=T['mem']: break
                        ev.append(x); fc+=tasks[x]['cpu']; fm+=tasks[x]['mem']
                    if fc>=T['cpu'] and fm>=T['mem'] and ev:
                        for x in ev:
                            del running[m][x]; waiting.add(x); out.append((now,x,'evict',m))
                        running[m][k]=(now,now+T['run']); waiting.discard(k); out.append((now,k,'start',m)); first.setdefault(k,now); started=True
                        break
                if started: continue
            if resv is None:
                best=None
                for m in ids:
                    if not up[m]: continue
                    if machines[m]['cpu']<T['cpu'] or machines[m]['mem']<T['mem']: continue
                    fc,fm=free(m); ends=sorted(set(e for s,e in running[m].values()))
                    R=None
                    for e in ends:
                        for x,(s,ee) in running[m].items():
                            pass
                        uc=sum(tasks[x]['cpu'] for x,(s,ee) in running[m].items() if ee>e)
                        um=sum(tasks[x]['mem'] for x,(s,ee) in running[m].items() if ee>e)
                        if machines[m]['cpu']-uc>=T['cpu'] and machines[m]['mem']-um>=T['mem']: R=e;break
                    if R is not None and (best is None or R<best[1]): best=(m,R,T['cpu'],T['mem'])
                resv=best
    return out,first

def apply(machines,tasks,ch):
    return copy.deepcopy(machines),copy.deepcopy(tasks)

if __name__=="__main__":
    import glob,os
    for fn in sorted(os.listdir(D)):
        if not fn.startswith("chapter"): continue
        m,t,log=parse(fn)
        out,_=simulate(m,t)
        o=[x for x in out if x[0]<=1200]
        # normalize for compare
        print(fn,len(log),len(o),o==log)
        if o!=log:
            for i,(a,b) in enumerate(zip(o,log)):
                if a!=b: print(i,a,b); break
