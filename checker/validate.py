"""Validator for workflow_semantics_v1 run outputs (independent of run.py).
Usage: python -I checker/validate.py <scenario.json> <run_output.json> [<base_run_output.json>]
Prints a JSON report. Standard library only.
"""
import sys, os, json, re, math, hashlib, heapq, bisect
import xml.etree.ElementTree as ET
from fractions import Fraction

WEEK = 7 * 86400
DAYIDX = {'MONDAY': 0, 'TUESDAY': 1, 'WEDNESDAY': 2, 'THURSDAY': 3, 'FRIDAY': 4, 'SATURDAY': 5, 'SUNDAY': 6}
ERR_CODES = {'unsupported_model', 'invalid_scenario', 'invalid_intervention', 'conflicting_interventions',
             'visit_limit_exceeded', 'deadlock'}
MAXV = 5


# ------------------------------------------------------------------ result collector
class Report:
    def __init__(self):
        self.props = {}

    def ensure(self, name):
        return self.props.setdefault(name, {'status': 'pass', 'violations': [], 'n_violations': 0, 'checked': 0})

    def na(self, name, why):
        self.props[name] = {'status': 'not_applicable', 'reason': why}

    def ok(self, name):
        self.ensure(name)['checked'] += 1

    def fail(self, name, msg):
        p = self.ensure(name)
        p['status'] = 'fail'
        p['n_violations'] += 1
        if len(p['violations']) < MAXV:
            p['violations'].append(msg)


# ------------------------------------------------------------------ calendars as explicit intervals
def clock_seconds(s):
    h, m, rest = s.split(':')
    return int(h) * 3600 + int(m) * 60 + int(rest.split('.')[0])


def weekly_windows(periods):
    w = []
    for p in periods:
        for d in range(DAYIDX[p['from']], DAYIDX[p['to']] + 1):
            a = d * 86400 + clock_seconds(p['beginTime'])
            b = d * 86400 + clock_seconds(p['endTime'])
            if a < b:
                w.append((a, b))
    return w


def merge(ints):
    ints = sorted(ints)
    out = []
    for a, b in ints:
        if out and a <= out[-1][1]:
            if b > out[-1][1]:
                out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def expand(windows, horizon, lo=0, removals=()):
    """explicit merged working intervals up to horizon, intersected with [lo,inf) minus removals"""
    ints = []
    for wk in range(horizon // WEEK + 2):
        for a, b in windows:
            ints.append((wk * WEEK + a, wk * WEEK + b))
    ints = merge(ints)
    res = []
    for a, b in ints:
        a = max(a, lo)
        if a >= b:
            continue
        pieces = [(a, b)]
        for f, t in removals:
            nxt = []
            for pa, pb in pieces:
                if t <= pa or f >= pb:
                    nxt.append((pa, pb))
                else:
                    if f > pa:
                        nxt.append((pa, f))
                    if t < pb:
                        nxt.append((t, pb))
            pieces = nxt
        res.extend(pieces)
    return merge(res)


class Cal:
    def __init__(self, ints):
        self.ints = ints
        self.starts = [a for a, _ in ints]

    def contains(self, t):
        i = bisect.bisect_right(self.starts, t) - 1
        return i >= 0 and self.ints[i][0] <= t < self.ints[i][1]

    def measure(self, a, b):
        if b <= a:
            return 0
        i = max(bisect.bisect_right(self.starts, a) - 1, 0)
        tot = 0
        while i < len(self.ints) and self.ints[i][0] < b:
            x, y = self.ints[i]
            lo, hi = max(x, a), min(y, b)
            if hi > lo:
                tot += hi - lo
            i += 1
        return tot

    def next_open(self, t):
        i = bisect.bisect_right(self.starts, t) - 1
        if i >= 0 and self.ints[i][0] <= t < self.ints[i][1]:
            return t
        j = bisect.bisect_right(self.starts, t)
        return self.ints[j][0]

    def work_end(self, s, d):
        if d == 0:
            return s
        rem = d
        i = max(bisect.bisect_right(self.starts, s) - 1, 0)
        while True:
            x, y = self.ints[i]
            lo = max(x, s)
            if y > lo:
                if rem <= y - lo:
                    return lo + rem
                rem -= y - lo
            i += 1

    def pieces_in(self, a, b):
        res = []
        i = max(bisect.bisect_right(self.starts, a) - 1, 0)
        while i < len(self.ints) and self.ints[i][0] < b:
            x, y = self.ints[i]
            lo, hi = max(x, a), min(y, b)
            if hi > lo:
                res.append((lo, hi))
            i += 1
        return res


# ------------------------------------------------------------------ distributions and draws
def phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def phi_inv(p):
    lo, hi = -40.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if phi(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def quantile(name, params, u):
    u = float(u)
    if name == 'fix':
        return math.floor(params[0] + 0.5)
    if name == 'expon':
        mean, mn, mx = params
        s = mean - mn
        F = 1 - math.exp(-(mx - mn) / s)
        x = mn - s * math.log(1 - u * F)
        return max(math.ceil(mn), min(math.floor(mx), math.floor(x + 0.5)))
    mean, std, mn, mx = params
    lo = max(mn, 0)
    a, b = phi((lo - mean) / std), phi((mx - mean) / std)
    p = a + u * (b - a)
    if p <= 0:
        x = -1e18
    elif p >= 1:
        x = 1e18
    else:
        x = mean + std * phi_inv(p)
    if x <= -1e17:
        return math.ceil(lo)
    if x >= 1e17:
        return math.floor(mx)
    return max(math.ceil(lo), min(math.floor(mx), math.floor(x + 0.5)))


def hash_u(seed, case, element, visit, variable):
    s = '|'.join([seed, case, element, str(visit), variable])
    n = int.from_bytes(hashlib.sha256(s.encode('utf-8')).digest()[:8], 'big')
    return Fraction(2 * (n >> 12) + 1, 1 << 53)


# ------------------------------------------------------------------ model
def tag(e):
    return e.tag.rsplit('}', 1)[-1]


class Model:
    pass


def load_model(bpmn, params):
    M = Model()
    root = ET.parse(bpmn).getroot()
    M.type = {}
    flows = []
    for pr in [e for e in root.iter() if tag(e) == 'process']:
        for e in pr:
            t = tag(e)
            if t in ('startEvent', 'endEvent', 'task', 'intermediateCatchEvent', 'exclusiveGateway', 'parallelGateway'):
                M.type[e.get('id')] = t
            elif t == 'sequenceFlow':
                flows.append((e.get('id'), e.get('sourceRef'), e.get('targetRef')))
    M.out = {n: [] for n in M.type}
    M.inc = {n: [] for n in M.type}
    M.target = {}
    for f, s, t in flows:
        M.out[s].append(f)
        M.inc[t].append(f)
        M.target[f] = t
    M.start = [n for n, t in M.type.items() if t == 'startEvent'][0]
    P = json.load(open(params, encoding='utf-8'))
    cals = {c['id']: weekly_windows(c['time_periods']) for c in P['resource_calendars']}
    M.pools = {}
    rid2pool = {}
    for prof in P['resource_profiles']:
        for e in prof['resource_list']:
            M.pools[e['name']] = {'amount': int(e['amount']), 'windows': cals[e['calendar']]}
            rid2pool[e['id']] = e['name']

    def dist(name, plist):
        return (name, [float(p['value']) for p in plist])
    M.task_dist, M.task_pool = {}, {}
    for e in P['task_resource_distribution']:
        r = e['resources'][0]
        M.task_dist[e['task_id']] = dist(r['distribution_name'], r['distribution_params'])
        M.task_pool[e['task_id']] = rid2pool[r['resource_id']]
    M.timer_dist = {e['event_id']: dist(e['distribution_name'], e['distribution_params']) for e in P['event_distribution']}
    M.gw = {}
    for g in P['gateway_branching_probabilities']:
        M.gw[g['gateway_id']] = [(p['path_id'], Fraction(str(p['value']))) for p in g['probabilities']]
    M.arr_dist = dist(P['arrival_time_distribution']['distribution_name'], P['arrival_time_distribution']['distribution_params'])
    M.arr_windows = weekly_windows(P['arrival_time_calendar'])
    return M


# ------------------------------------------------------------------ interventions (lenient parse)
def sel_ok(sel, case, visit, ref):
    sel = sel or {}
    if 'case' in sel and sel['case'] != case:
        return False
    if 'visit' in sel and sel['visit'] != visit:
        return False
    if 'from' in sel and ref < sel['from']:
        return False
    if 'to' in sel and ref >= sel['to']:
        return False
    return True


def apply_value(ivs, kind, target_key, target, case, visit, ref, base_value, u, report=None):
    """returns (value, number_of_matches)"""
    fams = ('duration_set', 'duration_scale', 'duration_distribution') if kind == 'task' else \
        ('timer_set', 'timer_scale', 'timer_distribution')
    m = [iv for iv in ivs if iv['type'] in fams and iv.get(target_key) == target and sel_ok(iv.get('selector'), case, visit, ref)]
    if not m:
        return base_value, 0
    iv = m[0]
    t = iv['type']
    if t.endswith('_set'):
        return iv['seconds'], len(m)
    if t.endswith('_scale'):
        return math.floor(Fraction(base_value) * Fraction(iv['factor']) + Fraction(1, 2)), len(m)
    return quantile(iv['distribution_name'], [float(x) for x in iv['distribution_params']], u), len(m)


def routing_flows(M, ivs, gw, case, visit, t):
    m = [iv for iv in ivs if iv['type'] == 'routing_set' and iv['gateway'] == gw and sel_ok(iv.get('selector'), case, visit, t)]
    order = [f for f, _ in M.gw[gw]]
    if m:
        pr = m[0]['probabilities']
        return [(f, Fraction(pr[f])) for f in order], len(m)
    return M.gw[gw], 0


def pick(flows, u):
    acc = Fraction(0)
    for f, p in flows:
        acc += p
        if u < acc:
            return f
    return None


# ------------------------------------------------------------------ main validation
def case_name(i):
    return 'c%04d' % i


def validate(scen_path, out_path, base_path=None):
    R = Report()
    out = json.load(open(out_path, encoding='utf-8'))
    S = json.load(open(scen_path, encoding='utf-8'))
    base = json.load(open(base_path, encoding='utf-8')) if base_path else None
    ALL = ['P1_flow', 'P2_precedence', 'P3_occupancy', 'P4_work', 'P5_queue_order', 'P6_timers', 'P7_routing',
           'P8_draw_stability', 'P9_case_isolation', 'P10_no_effect']
    EXTRA = ['X_format', 'X_draws_recomputed', 'X_values_recomputed', 'X_arrivals_and_case_set',
             'X_section8_definition_replay']

    # format of error outputs
    if out.get('status') == 'error':
        okf = set(out.keys()) == {'schema', 'scenario_id', 'status', 'error'} and out['schema'] == 'wf-run/1' \
            and out['error'] in ERR_CODES
        R.ok('X_format')
        if not okf:
            R.fail('X_format', 'bad error output shape')
        for n in ALL + EXTRA[1:]:
            R.na(n, 'run output is an error output')
        return finalize(R, ALL + EXTRA, out)

    # ----- format
    keys = ['schema', 'scenario_id', 'status', 'cases', 'tasks', 'timers', 'branches', 'draws']
    if list(out.keys()) != keys:
        R.fail('X_format', 'top-level keys %s' % list(out.keys()))
    if out.get('schema') != 'wf-run/1' or out.get('scenario_id') != S.get('scenario_id') or out.get('status') != 'ok':
        R.fail('X_format', 'schema/scenario_id/status wrong')
    spec = {
        'cases': (['case', 'arrival', 'end', 'end_event'], lambda r: (r['arrival'], r['case'])),
        'tasks': (['case', 'task', 'visit', 'enabled', 'start', 'end', 'resource', 'service'],
                  lambda r: (r['case'], r['enabled'], r['task'], r['visit'])),
        'timers': (['case', 'timer', 'visit', 'start', 'end', 'delay'], lambda r: (r['case'], r['start'], r['timer'], r['visit'])),
        'branches': (['case', 'gateway', 'visit', 'time', 'flow'], lambda r: (r['case'], r['time'], r['gateway'], r['visit'])),
        'draws': (['case', 'element', 'visit', 'variable', 'u'], lambda r: (r['case'], r['element'], r['visit'], r['variable'])),
    }
    strf = {'case', 'task', 'end_event', 'resource', 'timer', 'gateway', 'flow', 'element', 'variable', 'u'}
    for sec, (fields, keyf) in spec.items():
        recs = out.get(sec)
        if not isinstance(recs, list):
            R.fail('X_format', sec + ' not a list')
            continue
        for r in recs:
            R.ok('X_format')
            if set(r.keys()) != set(fields):
                R.fail('X_format', '%s fields %s' % (sec, sorted(r.keys())))
                continue
            for f in fields:
                v = r[f]
                if f in strf:
                    if not isinstance(v, str):
                        R.fail('X_format', '%s.%s not string' % (sec, f))
                elif not (isinstance(v, int) and not isinstance(v, bool)):
                    R.fail('X_format', '%s.%s not int' % (sec, f))
            if sec == 'draws' and isinstance(r.get('u'), str) and not re.match(r'^\d\.\d{12}$', r['u']):
                R.fail('X_format', 'u format %r' % r['u'])
        try:
            ks = [keyf(r) for r in recs]
            if ks != sorted(ks):
                R.fail('X_format', sec + ' not sorted')
            if len(set(ks)) != len(ks) and sec != 'cases':
                pass
        except Exception as e:  # malformed
            R.fail('X_format', sec + ' unsortable: %s' % e)
    if R.props.get('X_format', {}).get('status') == 'fail':
        for n in ALL + EXTRA[1:]:
            R.na(n, 'format failure prevents analysis')
        return finalize(R, ALL + EXTRA, out)

    # ----- model and scenario
    sdir = os.path.dirname(os.path.abspath(scen_path))
    M = load_model(os.path.join(sdir, S['model']['bpmn']), os.path.join(sdir, S['model']['params']))
    seed = S['seed']
    ivs = S.get('interventions') or []
    ov = {(o['case'], o['element'], o['visit'], o['variable']): Fraction(o['u']) for o in (S.get('draw_overrides') or [])}

    def U(case, el, visit, var):
        k = (case, el, visit, var)
        return ov[k] if k in ov else hash_u(seed, case, el, visit, var)

    # ----- case set and arrivals
    removed = {iv['case'] for iv in ivs if iv['type'] == 'case_remove'}
    added = {iv['case']: iv['arrival'] for iv in ivs if iv['type'] == 'case_add'}
    arr_ints = expand(M.arr_windows, 20 * WEEK + max([0] + list(added.values())))
    # arrivals may need a longer horizon: extend while needed
    n = S['n_cases']
    ac = Cal(arr_ints)
    exp_arr = {}
    prev = None
    for i in range(n):
        cn = case_name(i)
        if i == 0:
            a = ac.next_open(0)
        else:
            d = quantile(M.arr_dist[0], M.arr_dist[1], U(cn, M.start, 1, 'interarrival'))
            t = prev + d
            while t >= ac.ints[-1][1]:
                ac = Cal(expand(M.arr_windows, (ac.ints[-1][1] // WEEK + 20) * WEEK))
            a = ac.next_open(t)
        prev = a
        if cn not in removed:
            exp_arr[cn] = a
    exp_arr.update(added)
    got_arr = {r['case']: r['arrival'] for r in out['cases']}
    R.ok('X_arrivals_and_case_set')
    if set(got_arr) != set(exp_arr):
        R.fail('X_arrivals_and_case_set', 'case set differs: missing %s extra %s' %
               (sorted(set(exp_arr) - set(got_arr))[:3], sorted(set(got_arr) - set(exp_arr))[:3]))
    for c, a in exp_arr.items():
        R.ok('X_arrivals_and_case_set')
        if got_arr.get(c) != a:
            R.fail('X_arrivals_and_case_set', 'arrival %s expected %s got %s' % (c, a, got_arr.get(c)))
    if len(got_arr) != len(out['cases']):
        R.fail('X_arrivals_and_case_set', 'duplicate case records')

    # ----- draws recomputed
    tasks, timers, branches, draws = out['tasks'], out['timers'], out['branches'], out['draws']
    need = set()
    for r in tasks:
        need.add((r['case'], r['task'], r['visit'], 'service'))
    for r in timers:
        need.add((r['case'], r['timer'], r['visit'], 'timer'))
    for r in branches:
        need.add((r['case'], r['gateway'], r['visit'], 'branch'))
    have = {}
    for r in draws:
        k = (r['case'], r['element'], r['visit'], r['variable'])
        if k in have:
            R.fail('X_draws_recomputed', 'duplicate draw record %s' % (k,))
        have[k] = r['u']
    R.ok('X_draws_recomputed')
    if set(have) != need:
        R.fail('X_draws_recomputed', 'draw set differs from activations: missing %s extra %s' %
               (sorted(need - set(have))[:2], sorted(set(have) - need)[:2]))
    for k, u in have.items():
        R.ok('X_draws_recomputed')
        exp = '%.12f' % float(U(*k))
        if u != exp:
            R.fail('X_draws_recomputed', 'draw %s u=%s expected %s' % (k, u, exp))

    # ----- resources
    horizon = max([0] + [r['end'] for r in tasks] + [r['end'] for r in out['cases']] + list(added.values())) + 6 * WEEK
    for iv in ivs:
        for k in ('from', 'to'):
            if k in iv and isinstance(iv[k], int):
                horizon = max(horizon, iv[k] + 2 * WEEK)
    inst = {}  # name -> (pool, k, Cal, free0)
    for pname, p in M.pools.items():
        for k in range(p['amount']):
            rem = []
            for iv in ivs:
                if iv['type'] == 'resource_unavailable' and iv['pool'] == pname:
                    if 'count' in iv:
                        sel = k >= p['amount'] - iv['count']
                    else:
                        sel = (pname + '_' + str(k)) in iv['instances']
                    if sel:
                        rem.append((iv['from'], iv['to']))
            inst[pname + '_' + str(k)] = (pname, k, Cal(expand(p['windows'], horizon, 0, rem)), 0)
        nxt = p['amount']
        for iv in ivs:
            if iv['type'] == 'resource_add' and iv['pool'] == pname:
                for _ in range(iv['count']):
                    inst[pname + '_' + str(nxt)] = (pname, nxt, Cal(expand(p['windows'], horizon, iv['from'])), iv['from'])
                    nxt += 1

    # ----- values recomputed (service, delay, routing)
    for r in tasks:
        R.ok('X_values_recomputed')
        u = U(r['case'], r['task'], r['visit'], 'service')
        base_v = quantile(M.task_dist[r['task']][0], M.task_dist[r['task']][1], u)
        v, nm = apply_value(ivs, 'task', 'task', r['task'], r['case'], r['visit'], r['start'], base_v, u)
        if nm > 1:
            R.fail('X_values_recomputed', 'conflicting duration interventions matched %s but no error' % ((r['case'], r['task'], r['visit']),))
        if v != r['service']:
            R.fail('X_values_recomputed', 'service %s expected %s got %s' % ((r['case'], r['task'], r['visit']), v, r['service']))
    for r in timers:
        R.ok('X_values_recomputed')
        u = U(r['case'], r['timer'], r['visit'], 'timer')
        base_v = quantile(M.timer_dist[r['timer']][0], M.timer_dist[r['timer']][1], u)
        v, nm = apply_value(ivs, 'timer', 'timer', r['timer'], r['case'], r['visit'], r['start'], base_v, u)
        if nm > 1:
            R.fail('X_values_recomputed', 'conflicting timer interventions matched but no error')
        if v != r['delay']:
            R.fail('X_values_recomputed', 'delay %s expected %s got %s' % ((r['case'], r['timer'], r['visit']), v, r['delay']))

    # ----- P7 routing
    for r in branches:
        R.ok('P7_routing')
        u = U(r['case'], r['gateway'], r['visit'], 'branch')
        flows, nm = routing_flows(M, ivs, r['gateway'], r['case'], r['visit'], r['time'])
        if nm > 1:
            R.fail('P7_routing', 'conflicting routing interventions matched but no error')
        f = pick(flows, u)
        if f != r['flow']:
            R.fail('P7_routing', 'branch %s expected %s got %s' % ((r['case'], r['gateway'], r['visit']), f, r['flow']))

    # ----- P1/P2/P6 token replay
    trec = {(r['case'], r['task'], r['visit']): r for r in tasks}
    mrec = {(r['case'], r['timer'], r['visit']): r for r in timers}
    brec = {(r['case'], r['gateway'], r['visit']): r for r in branches}
    used = set()
    case_end = {r['case']: r for r in out['cases']}
    for c in case_end:
        R.ok('P1_flow')
        cnt = {}
        joins = {}
        ends = []
        ev = []
        sq = [0]

        def push(t, flow):
            sq[0] += 1
            heapq.heappush(ev, (t, sq[0], flow))
        f0 = M.out[M.start][0]
        push(case_end[c]['arrival'], f0)
        steps = 0
        bad = False
        while ev and not bad:
            t, _, fl = heapq.heappop(ev)
            steps += 1
            if steps > 100000:
                R.fail('P1_flow', 'case %s replay does not terminate' % c)
                bad = True
                break
            node = M.target[fl]
            typ = M.type[node]
            if typ == 'task':
                v = cnt.get(node, 0) + 1
                cnt[node] = v
                rec = trec.get((c, node, v))
                if rec is None:
                    R.fail('P1_flow', 'case %s missing task record %s visit %d' % (c, node, v))
                    bad = True
                    break
                used.add(('t', c, node, v))
                R.ok('P2_precedence')
                if rec['enabled'] != t:
                    R.fail('P2_precedence', 'enabled of %s is %s, token time %s' % ((c, node, v), rec['enabled'], t))
                push(rec['end'], M.out[node][0])
            elif typ == 'intermediateCatchEvent':
                v = cnt.get(node, 0) + 1
                cnt[node] = v
                rec = mrec.get((c, node, v))
                if rec is None:
                    R.fail('P1_flow', 'case %s missing timer record %s visit %d' % (c, node, v))
                    bad = True
                    break
                used.add(('m', c, node, v))
                R.ok('P6_timers')
                if rec['start'] != t:
                    R.fail('P6_timers', 'timer %s start %s token %s' % ((c, node, v), rec['start'], t))
                if rec['end'] != rec['start'] + rec['delay']:
                    R.fail('P6_timers', 'timer %s end != start+delay' % ((c, node, v),))
                push(rec['end'], M.out[node][0])
            elif typ == 'exclusiveGateway':
                outs = M.out[node]
                if len(outs) == 1:
                    push(t, outs[0])
                else:
                    v = cnt.get(node, 0) + 1
                    cnt[node] = v
                    rec = brec.get((c, node, v))
                    if rec is None:
                        R.fail('P1_flow', 'case %s missing branch record %s visit %d' % (c, node, v))
                        bad = True
                        break
                    used.add(('b', c, node, v))
                    if rec['time'] != t:
                        R.fail('P1_flow', 'branch %s time %s token %s' % ((c, node, v), rec['time'], t))
                    if rec['flow'] not in outs:
                        R.fail('P1_flow', 'branch %s flow %s not an outgoing flow' % ((c, node, v), rec['flow']))
                        bad = True
                        break
                    push(t, rec['flow'])
            elif typ == 'parallelGateway':
                st = joins.setdefault(node, {f: [] for f in M.inc[node]})
                st[fl].append(t)
                if all(st[f] for f in st):
                    firsts = {f: min(st[f]) for f in st}
                    for f in st:
                        st[f].remove(firsts[f])
                    tf = max(firsts.values())
                    for f in M.out[node]:
                        push(tf, f)
            elif typ == 'endEvent':
                ends.append((t, node))
        if bad:
            continue
        if any(any(v for v in st.values()) for st in joins.values()):
            R.fail('P1_flow', 'case %s leaves tokens at a parallel gateway' % c)
        if not ends:
            R.fail('P1_flow', 'case %s reaches no end event' % c)
        else:
            mt = max(t for t, _ in ends)
            cands = {n for t, n in ends if t == mt}
            if case_end[c]['end'] != mt or case_end[c]['end_event'] not in cands:
                R.fail('P1_flow', 'case %s end %s/%s expected %s/%s' % (c, case_end[c]['end'], case_end[c]['end_event'], mt, sorted(cands)))
    for tag_, recs in (('t', trec), ('m', mrec), ('b', brec)):
        for (c, node, v) in recs:
            if c not in case_end:
                R.fail('P1_flow', 'record for unknown case %s' % c)
            elif (tag_, c, node, v) not in used:
                R.fail('P1_flow', 'record not reached by token replay: %s %s %s visit %s' % (tag_, c, node, v))

    # ----- P2 ordering
    for r in tasks:
        R.ok('P2_precedence')
        if not (r['enabled'] <= r['start'] <= r['end']):
            R.fail('P2_precedence', 'task %s enabled<=start<=end violated' % ((r['case'], r['task'], r['visit']),))
        if r['task'] not in M.task_pool:
            R.fail('P2_precedence', 'unknown task %s' % r['task'])

    # ----- P3/P4 per record resource checks
    by_res = {}
    for r in tasks:
        R.ok('P3_occupancy')
        R.ok('P4_work')
        if r['resource'] not in inst:
            R.fail('P3_occupancy', 'unknown resource %s' % r['resource'])
            continue
        pool, k, cal, _ = inst[r['resource']]
        if pool != M.task_pool.get(r['task']):
            R.fail('P3_occupancy', 'task %s ran on resource %s of another pool' % (r['task'], r['resource']))
        by_res.setdefault(r['resource'], []).append(r)
        if not cal.contains(r['start']):
            R.fail('P3_occupancy', 'task %s starts outside working time of %s at %s' % ((r['case'], r['task'], r['visit']), r['resource'], r['start']))
        m = cal.measure(r['start'], r['end'])
        if m != r['service']:
            R.fail('P4_work', 'task %s working time %s != service %s' % ((r['case'], r['task'], r['visit']), m, r['service']))
        elif r['service'] == 0:
            if r['end'] != r['start']:
                R.fail('P4_work', 'zero-service task %s has end != start' % ((r['case'], r['task'], r['visit']),))
        elif not cal.contains(r['end'] - 1):
            R.fail('P4_work', 'task %s end %s is not the earliest completion (last second not working)' % ((r['case'], r['task'], r['visit']), r['end']))
    for rn, lst in by_res.items():
        lst.sort(key=lambda r: (r['start'], r['end']))
        for a, b in zip(lst, lst[1:]):
            if b['start'] < a['end']:
                R.fail('P3_occupancy', 'resource %s overlaps %s and %s' % (rn, (a['case'], a['task'], a['visit'], a['start'], a['end']),
                                                                      (b['case'], b['task'], b['visit'], b['start'], b['end'])))

    # ----- P5 queue order
    key = lambda r: (r['enabled'], case_end[r['case']]['arrival'], r['case'], r['task'], r['visit'])
    by_pool = {}
    for r in tasks:
        by_pool.setdefault(M.task_pool[r['task']], []).append(r)
    for pname, lst in by_pool.items():
        R.ok('P5_queue_order')
        lst.sort(key=key)
        mx = None
        for r in lst:
            if mx is not None and r['start'] < mx[0]:
                R.fail('P5_queue_order', 'pool %s: key %s starts at %s, earlier than smaller key %s starting %s' %
                       (pname, key(r), r['start'], mx[1], mx[0]))
            if mx is None or r['start'] > mx[0]:
                mx = (r['start'], key(r))
        # idle check
        names = [n for n, v in inst.items() if v[0] == pname]
        busy = {n: sorted((x['start'], x['end']) for x in by_res.get(n, []) if x['end'] > x['start']) for n in names}
        for r in lst:
            if r['enabled'] >= r['start']:
                continue
            for n in names:
                cal = inst[n][2]
                for (pa, pb) in cal.pieces_in(r['enabled'], r['start']):
                    # subtract busy
                    cur = [(pa, pb)]
                    for (ba, bb) in busy[n]:
                        if bb <= pa or ba >= pb:
                            continue
                        nxt = []
                        for (x, y) in cur:
                            if bb <= x or ba >= y:
                                nxt.append((x, y))
                            else:
                                if ba > x:
                                    nxt.append((x, ba))
                                if bb < y:
                                    nxt.append((bb, y))
                        cur = nxt
                    if cur:
                        R.fail('P5_queue_order', 'instance %s idle in working time %s while %s waited (enabled %s, start %s)' %
                               (n, cur[0], (r['case'], r['task'], r['visit']), r['enabled'], r['start']))
                        break

    # ----- extra: literal section 8 definition replay over recorded activations
    acts = sorted(tasks, key=key)
    free = {n: v[3] for n, v in inst.items()}
    for r in acts:
        R.ok('X_section8_definition_replay')
        pname = M.task_pool[r['task']]
        best = None
        for n, v in inst.items():
            if v[0] != pname:
                continue
            s = v[2].next_open(max(r['enabled'], free[n]))
            cand = (s, free[n], v[1], n)
            if best is None or cand < best:
                best = cand
        s, _, _, n = best
        e = inst[n][2].work_end(s, r['service'])
        free[n] = e
        if (n, s, e) != (r['resource'], r['start'], r['end']):
            R.fail('X_section8_definition_replay', 'activation %s: definition gives %s start %s end %s; output has %s %s %s' %
                   ((r['case'], r['task'], r['visit']), n, s, e, r['resource'], r['start'], r['end']))

    # ----- comparisons with base
    if base is None or base.get('status') != 'ok':
        for n in ('P8_draw_stability', 'P9_case_isolation', 'P10_no_effect'):
            R.na(n, 'no (valid) base output supplied')
    else:
        bd = {(r['case'], r['element'], r['visit'], r['variable']): r['u'] for r in base['draws']}
        R.ensure('P8_draw_stability')
        shared = 0
        for r in draws:
            k = (r['case'], r['element'], r['visit'], r['variable'])
            if k in bd:
                if k in ov and bd[k] != r['u']:
                    # premise "same overrides" fails: this run overrides the identity, the base evidently does not
                    R.ensure('P8_draw_stability').setdefault('skipped_overridden_here_only', []).append(list(k))
                    continue
                shared += 1
                R.ok('P8_draw_stability')
                if bd[k] != r['u']:
                    R.fail('P8_draw_stability', 'draw %s differs from base: %s vs %s' % (k, bd[k], r['u']))
        if shared == 0:
            R.na('P8_draw_stability', 'no shared draw identities')
        # P9
        case_ivs = [iv for iv in ivs if iv['type'] in ('case_add', 'case_remove')]
        if not case_ivs:
            R.na('P9_case_isolation', 'no case_add/case_remove intervention')
        else:
            R.ensure('P9_case_isolation')
            barr = {r['case']: r['arrival'] for r in base['cases']}
            for c, a in got_arr.items():
                if c in barr:
                    R.ok('P9_case_isolation')
                    if barr[c] != a:
                        R.fail('P9_case_isolation', 'arrival of %s changed %s -> %s' % (c, barr[c], a))
            exp_set = (set(barr) - removed) | set(added)
            if set(got_arr) != exp_set:
                R.fail('P9_case_isolation', 'case set not base - removed + added')
            for k, u in have.items():
                if k[0] in barr and k in bd:
                    R.ok('P9_case_isolation')
                    if bd[k] != u:
                        R.fail('P9_case_isolation', 'draw %s of a surviving case changed' % (k,))
        # P10
        if not ivs or case_ivs:
            R.na('P10_no_effect', 'no interventions or case-set interventions present' if case_ivs else 'no interventions')
        else:
            noop = True
            why = None
            for iv in ivs:
                t = iv['type']
                if t in ('duration_set', 'duration_scale', 'duration_distribution'):
                    for r in tasks:
                        if r['task'] == iv['task'] and sel_ok(iv.get('selector'), r['case'], r['visit'], r['start']):
                            u = U(r['case'], r['task'], r['visit'], 'service')
                            b = quantile(M.task_dist[r['task']][0], M.task_dist[r['task']][1], u)
                            one, _ = apply_value([iv], 'task', 'task', r['task'], r['case'], r['visit'], r['start'], b, u)
                            if one != b:
                                noop = False
                elif t in ('timer_set', 'timer_scale', 'timer_distribution'):
                    for r in timers:
                        if r['timer'] == iv['timer'] and sel_ok(iv.get('selector'), r['case'], r['visit'], r['start']):
                            u = U(r['case'], r['timer'], r['visit'], 'timer')
                            b = quantile(M.timer_dist[r['timer']][0], M.timer_dist[r['timer']][1], u)
                            one, _ = apply_value([iv], 'timer', 'timer', r['timer'], r['case'], r['visit'], r['start'], b, u)
                            if one != b:
                                noop = False
                elif t == 'routing_set':
                    for r in branches:
                        if r['gateway'] == iv['gateway'] and sel_ok(iv.get('selector'), r['case'], r['visit'], r['time']):
                            u = U(r['case'], r['gateway'], r['visit'], 'branch')
                            order = [f for f, _ in M.gw[iv['gateway']]]
                            new = [(f, Fraction(iv['probabilities'][f])) for f in order]
                            if pick(new, u) != pick(M.gw[iv['gateway']], u):
                                noop = False
                elif t == 'resource_unavailable':
                    pname = iv['pool']
                    size = M.pools[pname]['amount']
                    ks = range(size - iv['count'], size) if 'count' in iv else \
                        [int(n.rsplit('_', 1)[1]) for n in iv['instances']]
                    for k in ks:
                        base_cal = Cal(expand(M.pools[pname]['windows'], horizon))
                        if base_cal.measure(iv['from'], iv['to']) > 0:
                            noop = False
                elif t == 'resource_add':
                    mx = max([r['start'] for r in by_pool.get(iv['pool'], [])] + [-1])
                    if iv['from'] <= mx:
                        noop = False
                else:
                    noop = False
            if not noop:
                R.na('P10_no_effect', 'interventions have effect candidates (static test could not show a no-op)')
            else:
                R.ensure('P10_no_effect')
                R.ok('P10_no_effect')
                for sec in ('cases', 'tasks', 'timers', 'branches', 'draws'):
                    if out[sec] != base[sec]:
                        R.fail('P10_no_effect', 'section %s differs from base although interventions provably have no effect' % sec)
    return finalize(R, ALL + EXTRA, out)


def finalize(R, names, out):
    res = {}
    for n in names:
        if n in R.props:
            res[n] = R.props[n]
        else:
            res[n] = {'status': 'pass', 'violations': [], 'n_violations': 0, 'checked': 0}
    summary = {'pass': 0, 'fail': 0, 'not_applicable': 0}
    for v in res.values():
        summary[v['status']] += 1
    return {'scenario_id': out.get('scenario_id'), 'run_status': out.get('status'), 'summary': summary, 'properties': res}


if __name__ == '__main__':
    rep = validate(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    print(json.dumps(rep, indent=1))
