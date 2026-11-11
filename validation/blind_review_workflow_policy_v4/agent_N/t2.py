import re,difflib
def sents(p):
    t=re.sub(r'\s+',' ',open(p).read())
    return t
for proc in ('loan','pharmacy'):
    a=sents(f'{proc}_policyP_front_matter.txt'); b=sents(f'{proc}_policyH_front_matter.txt')
    # compare process paragraph exactly
    pa=a[a.index(' Process. '):a.index(' Rules. ')]; pb=b[b.index(' Process. '):b.index(' Rules. ')]
    print(proc,'process paragraph identical:',pa==pb)
    wa=a[a.index('Workers. '):a.index(' Process. ')]; wb=b[b.index('Workers. '):b.index(' Process. ')]
    sa=wa.split('. '); sb=wb.split('. ')
    print(' workers diff:')
    for l in difflib.unified_diff(re.split(r'(?<=\d:\d\d)\. ',wa),re.split(r'(?<=\d:\d\d)\. ',wb),lineterm='',n=0): print('   ',l)
    print(' rules/intro tokens diff (P vs H) skipped; numbers in rules/intro:')
    na=re.findall(r'\d[\d.:]*',a[:a.index(' Process. ')]+a[a.index(' Rules. '):]); nb=re.findall(r'\d[\d.:]*',b[:b.index(' Process. ')]+b[b.index(' Rules. '):])
    print('  ',na==nb, [x for x in na if x not in nb],[x for x in nb if x not in na])
