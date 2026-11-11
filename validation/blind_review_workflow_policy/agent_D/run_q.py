import sys, os; sys.path.insert(0, os.getcwd())
import json, re
from sim import *
qs=json.load(open('questions.json'))
cache={}
res=[]
for q in qs:
    key=(q['front_matter_file'],q['chapter_file'])
    if key not in cache:
        pools=parse_pools(q['front_matter_file']); chap=parse_chapter(q['chapter_file'])
        base=simulate(q['process'],pools,chap)
        cache[key]=(pools,chap,not compare(chap,base))
    pools,chap,ok=cache[key]
    t=q['question']; m={}
    x=re.search(r'case (c\d{4}) needed (\d+) seconds of work for the activity \'(.*?)\' on visit (\d+)',t)
    if x: m['work']={(x[1],x[3],int(x[4])):int(x[2])}; asked=x[1]
    x=re.search(r'case (c\d{4}) had never arrived. At what time.*case (c\d{4}) end',t)
    if x: m['remove']=[x[1]]; asked=x[2]
    x=re.search(r'suppose (\d+) ([A-Za-z ]+?) workers? (?:\((.*?)\) )?(?:were|was) unavailable from time (\d+) to time (\d+)\. .*case (c\d{4})',t)
    if x:
        pool=x[2]; k=int(x[1])
        idxs=[int(n.rsplit('_',1)[1]) for n in x[3].split(', ')] if x[3] else list(range(k))
        m['unavail']=[(pool,idxs,int(x[4]),int(x[5]))]; asked=x[6]
    x=re.search(r'route draw for case (c\d{4}) at decision (D\d) on visit (\d+) were (\d\.\d+)',t)
    if x: m['draw']={(x[1],x[2],int(x[3])):float(x[4])}; asked=x[1]
    x=re.search(r'decision (D\d) used the probabilities (.*?)\. At what time.*case (c\d{4}) end',t)
    if x: m['probs']={x[1]:{r:float(p) for r,p in re.findall(r'route (D\d-[a-z]) ([\d.]+)',x[2])}}; asked=x[3]
    x=re.search(r'wait (W\d) for case (c\d{4}) lasted (\d+) seconds on visit (\d+)',t)
    if x: m['wait']={(x[2],x[1],int(x[4])):int(x[3])}; asked=x[2]
    x=re.search(r'pool ([A-Za-z ]+?) had (\d+) more workers',t)
    if x: m['addworkers']={x[1]:int(x[2])}; asked=re.search(r'case (c\d{4}) end',t)[1]
    assert m,t
    log=simulate(q['process'],pools,chap,m)
    ans=log['end'][asked]
    fact=chap['cases'][asked][1]
    print(q['qid'],asked,ans,'factual',fact,'chg' if ans!=fact else 'same',m)
    res.append(dict(qid=q['qid'],answer=ans,factual_reproduced=ok,confidence='high',note='' ,_fact=fact))
json.dump(res,open('_res.json','w'))
