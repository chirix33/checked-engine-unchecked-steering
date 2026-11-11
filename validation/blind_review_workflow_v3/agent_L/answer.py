import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import json
from sim import *

Q = {
 'W01': ('loan', 'loan_chapter_Run_06.txt', {'work': {('c0009', 'Return application back to applicant', 1): 1}}, 'c0009'),
 'W02': ('loan', 'loan_chapter_Run_07.txt', {'remove': ['c0004']}, 'c0014'),
 'W03': ('loan', 'loan_chapter_Run_10.txt', {'extra': {'Appraiser': 1}}, 'c0011'),
 'W04': ('loan', 'loan_chapter_Run_11.txt', {'draw': {('c0011', 'D1', 1): 0.1}}, 'c0011'),
 'W05': ('loan', 'loan_chapter_Run_12.txt', {'probs': {'D5': [0.7, 0.3]}}, 'c0007'),
 'W06': ('loan', 'loan_chapter_Run_05.txt', {'wait': {('c0002', 'W2', 1): 6861}}, 'c0002'),
 'W07': ('pharmacy', 'pharmacy_chapter_Run_05.txt', {'work': {('c0013', 'Pick-up', 1): 260}}, 'c0013'),
 'W08': ('pharmacy', 'pharmacy_chapter_Run_08.txt', {'remove': ['c0007']}, 'c0006'),
 'W09': ('pharmacy', 'pharmacy_chapter_Run_09.txt', {'extra': {'Pharmacist': 1}}, 'c0011'),
 'W10': ('pharmacy', 'pharmacy_chapter_Run_09.txt', {'draw': {('c0000', 'D7', 1): 0.025}}, 'c0000'),
 'W11': ('pharmacy', 'pharmacy_chapter_Run_09.txt', {'probs': {'D1': [0.3, 0.7]}}, 'c0000'),
 'W12': ('pharmacy', 'pharmacy_chapter_Run_05.txt', {'wait': {('c0014', 'W2', 1): 0}}, 'c0014'),
}
res = []
for q, (m, f, mods, c) in Q.items():
    d = parse(f)
    base = simulate(m, d)
    ok = not compare(m, d, base)
    o = simulate(m, d, mods)
    ans = o['end'].get(c)
    res.append((q, ans, d['cases'][c][1], ok))
    print(q, 'answer', ans, 'factual', d['cases'][c][1], 'repro', ok)

notes = {
 'W01': 'Visit 1 Return step shortened to 1s; the case then reaches its next Clerk step after 17:00 either way and waits to the same next-morning opening, so the end is unchanged.',
 'W02': 'Case c0004 removed; other cases keep their plans; c0014 changes via freed pool capacity.',
 'W03': 'Added Appraiser_2 with the same hours.',
 'W04': 'Draw 0.1 < 0.2 sends c0011 to D1-a (return to applicant) with the rest of its plan unchanged.',
 'W05': 'D5 probabilities 0.7/0.3 with the printed draws unchanged; route re-chosen.',
 'W06': 'W2 visit 1 delay set to 6861s.',
 'W07': 'Pick-up visit 1 work set to 260s.',
 'W08': 'Case c0007 removed.',
 'W09': 'Added Pharmacist_1 with the same hours.',
 'W10': 'Draw 0.025 gives D7-a back to D6; D6 visit 2 draw 0.016552 gives D6-a to W3 visit 1, the same wait and pick-up as recorded, so the end is unchanged.',
 'W11': 'D1 probabilities 0.3/0.7 with printed draws unchanged.',
 'W12': 'W2 visit 1 delay set to 0s.',
}
json.dump([{'qid': q, 'answer': a, 'factual_reproduced': ok, 'confidence': 'high', 'note': notes[q]} for q, a, f, ok in res], open('answers.json', 'w'), indent=1)
