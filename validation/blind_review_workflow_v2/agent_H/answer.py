import sys; sys.path.insert(0, ".")
import json
from sim import *

Q = {
 'W01': ('loan', 'loan_chapter_Run_06.txt', {'work': {('c0009', 'Return application back to applicant', 1): 1}}, 'c0009'),
 'W02': ('loan', 'loan_chapter_Run_07.txt', {'drop': ['c0001']}, 'c0003'),
 'W03': ('loan', 'loan_chapter_Run_05.txt', {'unavail': [('Appraiser', 2, 39600, 54000)]}, 'c0005'),
 'W04': ('loan', 'loan_chapter_Run_11.txt', {'draw': {('c0011', 'D1', 1): 0.1}}, 'c0011'),
 'W05': ('loan', 'loan_chapter_Run_12.txt', {'probs': {'D5': {'D5-a': 0.7, 'D5-b': 0.3}}}, 'c0007'),
 'W06': ('loan', 'loan_chapter_Run_05.txt', {'wait': {('c0002', 'W2', 1): 6861}}, 'c0002'),
 'W07': ('pharmacy', 'pharmacy_chapter_Run_06.txt', {'work': {('c0002', 'Check DUR', 1): 3601}}, 'c0002'),
 'W08': ('pharmacy', 'pharmacy_chapter_Run_09.txt', {'drop': ['c0004']}, 'c0006'),
 'W09': ('pharmacy', 'pharmacy_chapter_Run_12.txt', {'unavail': [('Pharmacist', 1, 28800, 36000)]}, 'c0007'),
 'W10': ('pharmacy', 'pharmacy_chapter_Run_09.txt', {'draw': {('c0000', 'D7', 1): 0.025}}, 'c0000'),
 'W11': ('pharmacy', 'pharmacy_chapter_Run_09.txt', {'probs': {'D1': {'D1-a': 0.3, 'D1-b': 0.7}}}, 'c0000'),
 'W12': ('pharmacy', 'pharmacy_chapter_Run_11.txt', {'wait': {('c0005', 'W2', 1): 3788}}, 'c0005'),
}
for q, (proc, f, mods, case) in Q.items():
    d = parse_chapter(f)
    base = simulate(d, proc)
    out = simulate(d, proc, mods)
    # sanity: did the changed input get used?
    print(q, 'factual', base['ends'][case], 'changed', out['ends'][case], 'nends', len(out['ends']))
