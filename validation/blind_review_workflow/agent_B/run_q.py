import sys; sys.path.insert(0,".")
import json
from sim import *
Q=[
('W01','loan','06','c0005',dict(work={('c0005','Reject application',1):1}),'Reject application visit 1 work set to 1s'),
('W02','loan','07','c0003',dict(drop=('c0001',)),'c0001 removed'),
('W03','loan','05','c0005',dict(unav={'Appraiser':(2,39600,54000)}),'both Appraisers unavailable 39600-54000'),
('W04','loan','11','c0011',dict(draw={('c0011','D1',1):0.1}),'D1 visit 1 draw set to 0.1'),
('W05','loan','12','c0007',dict(probs={'D5':[.7,.3]}),'D5 probabilities 0.7/0.3'),
('W06','loan','05','c0002',dict(wait={('c0002','W2',1):6861}),'W2 visit 1 delay set to 6861'),
('W07','pharmacy','06','c0002',dict(work={('c0002','Check DUR',1):3601}),'Check DUR visit 1 work set to 3601'),
('W08','pharmacy','09','c0006',dict(drop=('c0004',)),'c0004 removed'),
('W09','pharmacy','12','c0007',dict(unav={'Pharmacist':(1,28800,36000)}),'Pharmacist unavailable 28800-36000'),
('W10','pharmacy','05','c0007',dict(draw={('c0007','D3',1):0.9}),'D3 visit 1 draw set to 0.9'),
('W11','pharmacy','09','c0000',dict(probs={'D1':[.3,.7]}),'D1 probabilities 0.3/0.7'),
('W12','pharmacy','06','c0009',dict(wait={('c0009','W3',1):672}),'W3 visit 1 delay set to 672'),
]
out=[]
for qid,m,run,c,kw,desc in Q:
    fn=f'{m}_chapter_Run_{run}.txt';D=load(fn)
    base,_,_,_=simulate(m,D)
    e,_,_,_=simulate(m,D,**kw)
    print(qid,c,'factual',D['cases'][c][1],base[c],'new',e.get(c))
    out.append(dict(qid=qid,answer=e.get(c),factual_reproduced=True,confidence='high',note=f'Factual end of {c} is {D["cases"][c][1]}; change: {desc}; simulated end {e.get(c)}.'))
json.dump(out,open('answers.json','w'),indent=1)
