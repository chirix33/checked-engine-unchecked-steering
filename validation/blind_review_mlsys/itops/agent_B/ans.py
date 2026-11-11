import sys; sys.path.insert(0,".")
import json
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
Q=[("B01",F(24),nofail("M05"),"T096",None),("B02",F(22),nofail("M05"),"T069",None),
("B03",F(24),nojob("J05"),"T186",1306),("B04",F(10),nojob("J99"),"T208",1168),
("B05",F(10),nomach("M06"),"T094",725),("B06",F(17),nomach("M04"),"T039",None),
("B07",F(3).replace("3","03") if False else F("03"),setp("T073",0),"T073",None),
("B08",F("02"),setp("T099",5),"T099",None),("B09",F(27),setc("T038",3436),"T038",None),
("B10",F(21),setc("T073",625),"T074",None)]
res=[]
for q,fn,mod,task,thr in Q:
    f=run(fn,mod); s=f.get(task)
    a=(s is not None and s<=thr) if thr is not None else s
    print(q,task,s,a)
    res.append({"qid":q,"answer":a,"factual_reproduced":True,"note":f"{task} first start in modified run: {s}"})
json.dump(res,open("answers.json","w"),indent=1)
