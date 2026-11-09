"""Independent scheduler written from front_matter.txt only."""
import re, sys, os, json

ROW = re.compile(r'^(\d+) (T\d+) (J\d+) (\d+) (\d+) (\d+) (\d+) (submit|start|finish|evict|fail) (M\d+|-)$')
MROW = re.compile(r'^(M\d+) (\d+) (\d+) (\S+) (\S+)$')
WINDOW = 1200


def parse(path):
    machines = []  # list of dicts in id order
    tasks = {}     # tid -> dict
    log = []
    sec = None
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if line.endswith(': Machines'):
            sec = 'm'; continue
        if line.endswith(': Task log'):
            sec = 't'; continue
        if line.endswith(': Events'):
            sec = None; continue
        if sec == 'm':
            m = MROW.match(line)
            if m:
                mid, c, mem, f, r = m.groups()
                machines.append(dict(id=mid, cpu=int(c), mem=int(mem),
                                     fail=None if f == '-' else int(f),
                                     ret=None if r == '-' else int(r)))
        elif sec == 't':
            m = ROW.match(line)
            if m:
                t, tid, job, pr, c, mem, rt, ev, mach = m.groups()
                row = (int(t), tid, job, int(pr), int(c), int(mem), int(rt), ev, mach)
                log.append(row)
                if ev == 'submit':
                    tasks[tid] = dict(id=tid, num=int(tid[1:]), job=job, pri=int(pr),
                                      cpu=int(c), mem=int(mem), rt=int(rt), sub=int(t))
    machines.sort(key=lambda m: m['id'])
    return machines, tasks, log


def simulate(machines, tasks, until=None, stop_task=None, log_until=WINDOW, max_time=10**8):
    """Run the policy from time 0. Returns (log rows with time<=log_until, first_start, state)."""
    M = {m['id']: dict(m) for m in machines}
    mids = [m['id'] for m in machines]
    up = {mid: True for mid in mids}
    running = {mid: {} for mid in mids}   # mid -> tid -> (start, end)
    queue = set()
    first_start = {}
    log = []
    subs = {}
    for t in tasks.values():
        subs.setdefault(t['sub'], []).append(t['id'])
    # failures only inside the window (no machine fails after the window)
    fails, rets = {}, {}
    for m in machines:
        if m['fail'] is not None and m['fail'] <= WINDOW:
            fails.setdefault(m['fail'], []).append(m['id'])
            if m['ret'] is not None:
                rets.setdefault(m['ret'], []).append(m['id'])

    def qkey(tid):
        t = tasks[tid]
        return (-t['pri'], t['sub'], t['num'])

    def row(time, tid, ev, mach):
        if time <= log_until:
            t = tasks[tid]
            log.append((time, tid, t['job'], t['pri'], t['cpu'], t['mem'], t['rt'], ev, mach))

    def free(mid):
        c = M[mid]['cpu']; m = M[mid]['mem']
        for tid in running[mid]:
            c -= tasks[tid]['cpu']; m -= tasks[tid]['mem']
        return c, m

    def free_at(mid, R):
        c = M[mid]['cpu']; m = M[mid]['mem']
        for x, (s, e) in running[mid].items():
            if e > R:
                c -= tasks[x]['cpu']; m -= tasks[x]['mem']
        return c, m

    def start(time, tid, mid):
        running[mid][tid] = (time, time + tasks[tid]['rt'])
        queue.discard(tid)
        first_start.setdefault(tid, time)
        row(time, tid, 'start', mid)

    static_times = set(subs) | set(fails) | set(rets)
    time = None
    while True:
        cands = [x for x in static_times if time is None or x > time]
        for mid in mids:
            for tid, (s, e) in running[mid].items():
                if time is None or e > time:
                    cands.append(e)
        if not cands:
            break
        time = min(cands)
        if time > max_time or (until is not None and time > until):
            break
        # 1. finishes
        fin = []
        for mid in mids:
            for tid, (s, e) in list(running[mid].items()):
                if e == time:
                    fin.append((tasks[tid]['num'], tid, mid))
        for _, tid, mid in sorted(fin):
            del running[mid][tid]
            row(time, tid, 'finish', mid)
        # 2. failures
        for mid in sorted(fails.get(time, [])):
            up[mid] = False
            for tid in sorted(running[mid], key=lambda x: tasks[x]['num']):
                row(time, tid, 'fail', mid)
                queue.add(tid)
            running[mid] = {}
        # 3. returns
        for mid in rets.get(time, []):
            up[mid] = True
            running[mid] = {}
        # 4. submissions
        for tid in sorted(subs.get(time, []), key=lambda x: tasks[x]['num']):
            row(time, tid, 'submit', '-')
            queue.add(tid)
        # 5. scheduling round
        processed = set()
        reservation = None  # (mid, R, tid)
        while True:
            pending = sorted((x for x in queue if x not in processed), key=qkey)
            if not pending:
                break
            tid = pending[0]
            processed.add(tid)
            t = tasks[tid]
            # a. first fit (subject to reservation)
            placed = None
            for mid in mids:
                if not up[mid]:
                    continue
                fc, fm = free(mid)
                if fc < t['cpu'] or fm < t['mem']:
                    continue
                if reservation is not None and reservation[0] == mid:
                    rmid, R, rtid = reservation
                    ok = time + t['rt'] <= R
                    if not ok:
                        c, m = free_at(mid, R)
                        c -= tasks[rtid]['cpu']; m -= tasks[rtid]['mem']
                        ok = c >= t['cpu'] and m >= t['mem']
                    if not ok:
                        continue
                placed = mid
                break
            if placed:
                start(time, tid, placed)
                continue
            # b. preemption
            if reservation is None and t['pri'] >= 9:
                done = False
                for mid in mids:
                    if not up[mid]:
                        continue
                    fc, fm = free(mid)
                    victims = [x for x in running[mid] if tasks[x]['pri'] <= 1]
                    victims.sort(key=lambda x: (tasks[x]['pri'], -running[mid][x][0], -tasks[x]['num']))
                    need = []
                    c, m = fc, fm
                    for v in victims:
                        if c >= t['cpu'] and m >= t['mem']:
                            break
                        need.append(v)
                        c += tasks[v]['cpu']; m += tasks[v]['mem']
                    if c >= t['cpu'] and m >= t['mem']:
                        for v in need:
                            del running[mid][v]
                            row(time, v, 'evict', mid)
                            queue.add(v)
                        start(time, tid, mid)
                        done = True
                        break
                if done:
                    continue
            # c. reservation
            if reservation is None:
                best = None
                for mid in mids:
                    if not up[mid]:
                        continue
                    if M[mid]['cpu'] < t['cpu'] or M[mid]['mem'] < t['mem']:
                        continue
                    ends = sorted(set(e for (s, e) in running[mid].values()))
                    et = None
                    for e in ends:
                        c, m = free_at(mid, e)
                        if c >= t['cpu'] and m >= t['mem']:
                            et = e
                            break
                    if et is not None and (best is None or et < best[1]):
                        best = (mid, et)
                if best is not None:
                    reservation = (best[0], best[1], tid)
        if stop_task is not None and stop_task in first_start:
            break
    return log, first_start, dict(time=time, running=running, queue=queue, up=up)


def check(path):
    machines, tasks, log = parse(path)
    sim, fs, st = simulate(machines, tasks, until=WINDOW)
    sim = [r for r in sim if r[0] <= WINDOW]
    if sim == log:
        return True, None
    for i, (a, b) in enumerate(zip(sim, log)):
        if a != b:
            return False, dict(index=i, sim=a, printed=b, printed_ctx=log[max(0, i-4):i+3], sim_ctx=sim[max(0, i-4):i+3])
    return False, ('len', len(sim), len(log))


if __name__ == '__main__':
    d = sys.argv[1]
    for f in sorted(os.listdir(d)):
        if f.startswith('chapter_'):
            ok, info = check(os.path.join(d, f))
            print(f, ok, '' if ok else info)
