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
Q=[("B01",F("06"),nofail("M02"),"T105",1407),("B02",F("14"),nofail("M05"),"T183",2222),
("B03",F("06"),nojob("J10"),"T058",631),("B04",F("11"),nojob("J10"),"T105",2307),
("B05",F("10"),nomach("M04"),"T127",1405),("B06",F("17"),nomach("M04"),"T039",None),
("B07",F("03"),setp("T104",11),"T104",None),("B08",F("13"),setp("T071",11),"T071",None),
("B09",F("27"),setc("T038",3436),"T038",None),("B10",F("20"),setc("T004",1874),"T004",2259)]
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
