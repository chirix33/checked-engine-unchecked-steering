import sys; sys.path.insert(0,".")
import json,os
from sim import *
def run(fn,mod):
    m,t,_=parse(fn); mod(m,t); return simulate(m,t)[1]
def nofail(mc):
    def f(m,t): m[mc]['fail']=None; m[mc]['ret']=None
    return f
def nojob(j):
    def f(m,t):
        for k in [k for k,v in t.items() if v['job']==j]: del t[k]
    return f
def nomach(mc):
    def f(m,t): del m[mc]
    return f
def setp(k,p):
    def f(m,t): t[k]['pri']=p
    return f
def setc(k,c):
    def f(m,t): t[k]['cpu']=c
    return f
F=lambda n:f"chapter_Cell_window_{n}.txt"
def setm(k,c):
    def f(m,t): t[k]['mem']=c
    return f
Q=[("B01",F("18"),nofail("M05"),"T065",None),("B02",F("09"),nofail("M01"),"T127",None),
("B03",F("06"),nojob("J10"),"T058",None),("B04",F("04"),nojob("J37"),"T094",None),
("B05",F("20"),nomach("M01"),"T059",None),("B06",F("30"),nomach("M04"),"T090",None),
("B07",F("02"),setp("T058",9),"T058",None),("B08",F("09"),setp("T041",5),"T041",None),
("B09",F("30"),setm("T100",1932),"T120",None),("B10",F("13"),setc("T072",4974),"T072",None)]
fr={}
for fn in sorted(os.listdir("..")):
    if fn.startswith("chapter"):
        m,t,log=parse(fn); o=[x for x in simulate(m,t)[0] if x[0]<=1200]; fr[fn]=(o==log); print(fn,o==log)
res=[]
for q,fn,mod,task,thr in Q:
    f=run(fn,mod); s=f.get(task)
    a=(s is not None and s<=thr) if thr is not None else s
    print(q,task,s,a)
    res.append({"qid":q,"answer":a,"factual_reproduced":fr[fn],"note":f"{task} first start in modified run: {s}"})
json.dump(res,open("answers.json","w"),indent=1)
