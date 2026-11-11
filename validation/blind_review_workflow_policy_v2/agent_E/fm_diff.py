import difflib,re
def sec(fn):
    t=open(fn,encoding='utf-8').read().replace('\n',' ')
    t=re.sub(r'\s+',' ',t)
    # split into sections
    keys=['Time.','Arrivals.','Workers.','Process.','Rules.','Units.','Chapters in this document']
    out={}
    idx=[(t.find(k),k) for k in keys]
    idx.sort()
    out['intro']=t[:idx[0][0]]
    for i,(p,k) in enumerate(idx):
        e=idx[i+1][0] if i+1<len(idx) else len(t)
        out[k]=t[p:e]
    return out
for proc in ['loan','pharmacy']:
    a=sec(f'{proc}_policyP_front_matter.txt'); b=sec(f'{proc}_policyH_front_matter.txt')
    print('=====',proc)
    for k in a:
        if a[k]==b[k]: print(k,'IDENTICAL'); continue
        print(k,'DIFFERS')
        if k in ('Process.','Workers.','Arrivals.','Time.','Units.'):
            sm=difflib.SequenceMatcher(None,a[k].split(),b[k].split())
            for op in sm.get_opcodes():
                if op[0]!='equal':
                    print('  ',op[0],'P:',' '.join(a[k].split()[op[1]:op[2]]),'| H:',' '.join(b[k].split()[op[3]:op[4]]))
print('cross checks')
for d in ['P','H']:
    a=sec(f'loan_policy{d}_front_matter.txt'); b=sec(f'pharmacy_policy{d}_front_matter.txt')
    for k in ['Rules.','Units.','Time.']:
        print(d,k,a[k]==b[k])
    ia=a['intro'].replace('Loan Application','X'); ib=b['intro'].replace('Pharmacy','X')
    print(d,'intro same mod name', ia==ib)
    print(repr(a['Chapters in this document']), repr(b['Chapters in this document']))
