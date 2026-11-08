"""Independent implementation of workflow_semantics_v1 (time-stepped DES scheduler).
Usage: python -I checker/run.py <scenario.json> <out.json>
Standard library only.
"""
import sys, os, json, re, hashlib, math, heapq
import xml.etree.ElementTree as ET
from fractions import Fraction
from statistics import NormalDist

WEEK = 604800
DAY = 86400
DAYS = {'MONDAY': 0, 'TUESDAY': 1, 'WEDNESDAY': 2, 'THURSDAY': 3, 'FRIDAY': 4,
        'SATURDAY': 5, 'SUNDAY': 6}
ND = NormalDist()
DEC_RE = re.compile(r'^(\d+\.?\d*|\.\d+)$')
ID_RE = re.compile(r'^[a-z0-9_-]+$')


class WfError(Exception):
    def __init__(self, code):
        Exception.__init__(self, code)
        self.code = code


# ---------------------------------------------------------------- helpers
def is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def dec_fraction(s):
    if not isinstance(s, str) or not DEC_RE.match(s):
        raise ValueError('decimal')
    return Fraction(s)


def parse_clock(s):
    m = re.match(r'^(\d{1,2}):(\d{2}):(\d{2})(\.\d+)?$', s)
    if not m:
        raise ValueError('time')
    h, mi, se = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if h > 24 or mi > 59 or se > 59:
        raise ValueError('time')
    v = h * 3600 + mi * 60 + se
    if v > DAY:
        raise ValueError('time')
    return v


def parse_periods(periods):
    """list of time periods -> merged sorted windows within [0, WEEK)"""
    if not isinstance(periods, list):
        raise WfError('unsupported_model')
    wins = []
    try:
        for p in periods:
            f = DAYS[p['from']]
            t = DAYS[p['to']]
            if f > t:
                raise ValueError('days')
            b = parse_clock(p['beginTime'])
            e = parse_clock(p['endTime'])
            if b > e:
                raise ValueError('window')
            if b == e:
                continue
            for d in range(f, t + 1):
                wins.append((d * DAY + b, d * DAY + e))
    except (KeyError, ValueError, TypeError, AttributeError):
        raise WfError('unsupported_model')
    wins.sort()
    merged = []
    for a, b in wins:
        if merged and a <= merged[-1][1]:
            if b > merged[-1][1]:
                merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


class WSet:
    """Working-time set: weekly windows, intersected with [lo, inf), minus removals."""

    def __init__(self, windows, lo=0, removals=()):
        self.windows = windows
        self.lo = lo
        rem = sorted(removals)
        m = []
        for f, t in rem:
            if m and f <= m[-1][1]:
                if t > m[-1][1]:
                    m[-1] = (m[-1][0], t)
            else:
                m.append((f, t))
        self.removals = m

    def pieces(self, t):
        w = t // WEEK
        while True:
            base = w * WEEK
            for a, b in self.windows:
                A = base + a
                B = base + b
                if B <= t:
                    continue
                if A < self.lo:
                    A = self.lo
                if A >= B:
                    continue
                cur = A
                for f, to in self.removals:
                    if to <= cur:
                        continue
                    if f >= B:
                        break
                    if f > cur:
                        yield (cur, f)
                    if to > cur:
                        cur = to
                    if cur >= B:
                        break
                if cur < B:
                    yield (cur, B)
            w += 1

    def next_open(self, t):
        for a, b in self.pieces(t):
            if b > t:
                return a if a > t else t

    def work_end(self, s, d):
        if d == 0:
            return s
        rem = d
        for a, b in self.pieces(s):
            if b <= s:
                continue
            if a < s:
                a = s
            L = b - a
            if rem <= L:
                return a + rem
            rem -= L


# ---------------------------------------------------------------- distributions
def make_dist(name, params):
    """params: list of floats. raises ValueError when invalid."""
    if name == 'fix':
        if len(params) != 1 or params[0] < 0:
            raise ValueError('fix')
        return ('fix', params[0])
    if name == 'expon':
        if len(params) != 3:
            raise ValueError('expon')
        mean, mn, mx = params
        if not (mn >= 0 and mean > mn and mx > mn):
            raise ValueError('expon')
        return ('expon', mean, mn, mx)
    if name == 'norm':
        if len(params) != 4:
            raise ValueError('norm')
        mean, std, mn, mx = params
        lo = max(mn, 0)
        if not (std > 0 and mx > lo):
            raise ValueError('norm')
        return ('norm', mean, std, mn, mx)
    raise ValueError('name')


def Q(dist, u):
    """u: float in [0,1)."""
    k = dist[0]
    if k == 'fix':
        return math.floor(dist[1] + 0.5)
    if k == 'expon':
        _, mean, mn, mx = dist
        s = mean - mn
        F = 1 - math.exp(-(mx - mn) / s)
        x = mn - s * math.log(1 - u * F)
        q = math.floor(x + 0.5)
        return min(max(q, math.ceil(mn)), math.floor(mx))
    _, mean, std, mn, mx = dist
    lo = max(mn, 0)
    a = 0.5 * math.erfc(-((lo - mean) / std) / math.sqrt(2))
    b = 0.5 * math.erfc(-((mx - mean) / std) / math.sqrt(2))
    p = a + u * (b - a)
    lo_i, hi_i = math.ceil(lo), math.floor(mx)
    if p <= 0.0:
        return lo_i
    if p >= 1.0:
        return hi_i
    x = mean + std * ND.inv_cdf(p)
    q = math.floor(x + 0.5)
    return min(max(q, lo_i), hi_i)


def hash_u(seed, case, element, visit, variable):
    text = seed + '|' + case + '|' + element + '|' + str(visit) + '|' + variable
    d = hashlib.sha256(text.encode('utf-8')).digest()
    n = int.from_bytes(d[:8], 'big')
    k = n >> 12
    return Fraction(2 * k + 1, 2 ** 53)


# ---------------------------------------------------------------- model
class Model:
    pass


def localname(tag):
    return tag.split('}')[-1] if isinstance(tag, str) else ''


def load_model(bpmn_path, params_path):
    M = Model()
    try:
        tree = ET.parse(bpmn_path)
    except Exception:
        raise WfError('unsupported_model')
    root = tree.getroot()
    SUP = {'startEvent', 'endEvent', 'task', 'intermediateCatchEvent',
           'exclusiveGateway', 'parallelGateway'}
    ntype = {}
    timer_ok = {}
    flows = []  # (id, src, tgt) in document order
    for proc in root.iter():
        if localname(proc.tag) != 'process':
            continue
        for ch in proc:
            ln = localname(ch.tag)
            if ln in SUP:
                i = ch.get('id')
                if not i or i in ntype:
                    raise WfError('unsupported_model')
                ntype[i] = ln
                if ln == 'intermediateCatchEvent':
                    timer_ok[i] = any(localname(g.tag) == 'timerEventDefinition' for g in ch)
            elif ln == 'sequenceFlow':
                i, s, t = ch.get('id'), ch.get('sourceRef'), ch.get('targetRef')
                if not i or not s or not t:
                    raise WfError('unsupported_model')
                flows.append((i, s, t))
    out = {n: [] for n in ntype}
    inc = {n: [] for n in ntype}
    fsrc, ftgt = {}, {}
    for i, s, t in flows:
        if i in fsrc or i in ntype:
            raise WfError('unsupported_model')
        if s not in ntype or t not in ntype:
            raise WfError('unsupported_model')
        fsrc[i], ftgt[i] = s, t
        out[s].append(i)
        inc[t].append(i)
    starts = [n for n, t in ntype.items() if t == 'startEvent']
    if len(starts) != 1:
        raise WfError('unsupported_model')
    if not any(t == 'endEvent' for t in ntype.values()):
        raise WfError('unsupported_model')
    for n, t in ntype.items():
        ni, no = len(inc[n]), len(out[n])
        if t == 'startEvent':
            ok = ni == 0 and no == 1
        elif t == 'endEvent':
            ok = ni >= 1 and no == 0
        elif t == 'task':
            ok = ni >= 1 and no == 1
        elif t == 'intermediateCatchEvent':
            ok = timer_ok[n] and ni >= 1 and no == 1
        else:
            ok = ni >= 1 and no >= 1
        if not ok:
            raise WfError('unsupported_model')
    M.ntype, M.out, M.inc, M.fsrc, M.ftgt, M.start = ntype, out, inc, fsrc, ftgt, starts[0]

    try:
        with open(params_path, 'r', encoding='utf-8') as fh:
            P = json.load(fh)
    except Exception:
        raise WfError('unsupported_model')
    if not isinstance(P, dict):
        raise WfError('unsupported_model')
    for key in ('batch_processing', 'prioritisation_rules', 'case_attributes',
                'event_attributes', 'global_attributes', 'branch_rules', 'multitask'):
        if key in P and P[key]:
            raise WfError('unsupported_model')
    if P.get('model_type') == 'FUZZY':
        raise WfError('unsupported_model')

    def model_dist(name, plist):
        try:
            vals = []
            for p in plist:
                v = p['value']
                if isinstance(v, str):
                    v = float(v)
                if not is_num(v):
                    raise ValueError('num')
                vals.append(float(v))
            return make_dist(name, vals)
        except (ValueError, KeyError, TypeError):
            raise WfError('unsupported_model')

    try:
        cals = {}
        for c in P['resource_calendars']:
            cals[c['id']] = parse_periods(c['time_periods'])
        pools = {}       # name -> dict
        pool_by_rid = {}
        for prof in P['resource_profiles']:
            for e in prof['resource_list']:
                name = e['name']
                amt = e['amount']
                if isinstance(amt, str):
                    if not re.match(r'^\d+$', amt):
                        raise WfError('unsupported_model')
                    amt = int(amt)
                if not is_int(amt) or amt < 1:
                    raise WfError('unsupported_model')
                if e['calendar'] not in cals or not cals[e['calendar']]:
                    raise WfError('unsupported_model')
                if not isinstance(name, str) or name in pools or e['id'] in pool_by_rid:
                    raise WfError('unsupported_model')
                pool = {'name': name, 'id': e['id'], 'amount': amt, 'windows': cals[e['calendar']]}
                pools[name] = pool
                pool_by_rid[e['id']] = pool
        task_dist, task_pool = {}, {}
        for ent in P['task_resource_distribution']:
            tid = ent['task_id']
            if tid not in ntype or ntype[tid] != 'task':
                continue
            if tid in task_dist:
                raise WfError('unsupported_model')
            res = ent['resources']
            if not isinstance(res, list) or len(res) != 1:
                raise WfError('unsupported_model')
            r = res[0]
            if r['resource_id'] not in pool_by_rid:
                raise WfError('unsupported_model')
            task_pool[tid] = pool_by_rid[r['resource_id']]['name']
            task_dist[tid] = model_dist(r['distribution_name'], r['distribution_params'])
        timer_dist = {}
        for ent in P['event_distribution']:
            eid = ent['event_id']
            if eid not in ntype or ntype[eid] != 'intermediateCatchEvent':
                continue
            if eid in timer_dist:
                raise WfError('unsupported_model')
            timer_dist[eid] = model_dist(ent['distribution_name'], ent['distribution_params'])
        for n, t in ntype.items():
            if t == 'task' and n not in task_dist:
                raise WfError('unsupported_model')
            if t == 'intermediateCatchEvent' and n not in timer_dist:
                raise WfError('unsupported_model')
        gprob = {}
        for ent in P['gateway_branching_probabilities']:
            gid = ent['gateway_id']
            plist = [(x['path_id'], x['value']) for x in ent['probabilities']]
            if gid in gprob:
                raise WfError('unsupported_model')
            gprob[gid] = plist
        M.route = {}
        for n, t in ntype.items():
            if t == 'exclusiveGateway' and len(out[n]) >= 2:
                if n not in gprob:
                    raise WfError('unsupported_model')
                pl = gprob[n]
                paths = [p for p, _ in pl]
                if len(set(paths)) != len(paths) or set(paths) != set(out[n]):
                    raise WfError('unsupported_model')
                lst = []
                for p, v in pl:
                    if isinstance(v, str) and DEC_RE.match(v):
                        fr = Fraction(v)
                    elif is_num(v) and v >= 0:
                        fr = Fraction(repr(v))
                    else:
                        raise WfError('unsupported_model')
                    lst.append((p, fr))
                if sum(x for _, x in lst) != 1:
                    raise WfError('unsupported_model')
                M.route[n] = lst
        ad = P['arrival_time_distribution']
        M.arr_dist = model_dist(ad['distribution_name'], ad['distribution_params'])
        awin = parse_periods(P['arrival_time_calendar'])
        if not awin:
            raise WfError('unsupported_model')
        M.arr_cal = WSet(awin)
    except WfError:
        raise
    except (KeyError, TypeError, AttributeError, ValueError):
        raise WfError('unsupported_model')
    M.pools, M.task_dist, M.task_pool, M.timer_dist = pools, task_dist, task_pool, timer_dist
    return M


# ---------------------------------------------------------------- scenario / interventions
def validate_scenario(S):
    if not isinstance(S, dict):
        raise WfError('invalid_scenario')
    if S.get('schema') != 'wf-scenario/1':
        raise WfError('invalid_scenario')
    if not isinstance(S.get('scenario_id'), str):
        raise WfError('invalid_scenario')
    m = S.get('model')
    if not isinstance(m, dict) or not isinstance(m.get('bpmn'), str) or not isinstance(m.get('params'), str):
        raise WfError('invalid_scenario')
    if not isinstance(S.get('seed'), str):
        raise WfError('invalid_scenario')
    if not is_int(S.get('n_cases')) or S['n_cases'] < 0:
        raise WfError('invalid_scenario')
    ov = {}
    dov = S.get('draw_overrides', [])
    if dov is None:
        dov = []
    if not isinstance(dov, list):
        raise WfError('invalid_scenario')
    for o in dov:
        if not isinstance(o, dict):
            raise WfError('invalid_scenario')
        if not (isinstance(o.get('case'), str) and isinstance(o.get('element'), str)
                and is_int(o.get('visit')) and isinstance(o.get('variable'), str)):
            raise WfError('invalid_scenario')
        try:
            u = dec_fraction(o.get('u'))
        except (ValueError, TypeError):
            raise WfError('invalid_scenario')
        if not (0 <= u < 1):
            raise WfError('invalid_scenario')
        ov[(o['case'], o['element'], o['visit'], o['variable'])] = u
    ivs = S.get('interventions', [])
    if ivs is None:
        ivs = []
    return ov, ivs


class Plan:
    pass


def case_id(i):
    return 'c' + str(i).zfill(4)


def parse_interventions(ivs, M, n_cases):
    bad = WfError('invalid_intervention')
    if not isinstance(ivs, list):
        raise bad
    base_ids = set(case_id(i) for i in range(n_cases))
    removed, added = set(), {}
    for iv in ivs:
        if not isinstance(iv, dict) or not isinstance(iv.get('type'), str):
            raise bad
        t = iv['type']
        if t == 'case_add':
            c, a = iv.get('case'), iv.get('arrival')
            if not isinstance(c, str) or not ID_RE.match(c) or not is_int(a) or a < 0:
                raise bad
            if c in base_ids or c in added:
                raise bad
            added[c] = a
        elif t == 'case_remove':
            c = iv.get('case')
            if not isinstance(c, str) or c not in base_ids:
                raise bad
            removed.add(c)
    run_cases = (base_ids - removed) | set(added)

    def selector(sel):
        if sel is None:
            return {}
        if not isinstance(sel, dict):
            raise bad
        out = {}
        if 'case' in sel:
            if not isinstance(sel['case'], str) or sel['case'] not in run_cases:
                raise bad
            out['case'] = sel['case']
        if 'visit' in sel:
            if not is_int(sel['visit']):
                raise bad
            out['visit'] = sel['visit']
        for k in ('from', 'to'):
            if k in sel:
                if not is_int(sel[k]):
                    raise bad
                out[k] = sel[k]
        if 'from' in out and 'to' in out and out['from'] >= out['to']:
            raise bad
        return out

    def idist(iv):
        nm, pr = iv.get('distribution_name'), iv.get('distribution_params')
        if not isinstance(nm, str) or not isinstance(pr, list) or not all(is_num(x) for x in pr):
            raise bad
        try:
            return make_dist(nm, [float(x) for x in pr])
        except ValueError:
            raise bad

    P = Plan()
    P.dur, P.tim, P.rout = [], [], []
    P.unavail, P.add = [], []
    P.removed, P.added = removed, added
    for iv in ivs:
        t = iv['type']
        if t in ('case_add', 'case_remove'):
            continue
        if t in ('duration_set', 'duration_scale', 'duration_distribution'):
            tgt = iv.get('task')
            if not isinstance(tgt, str) or M.ntype.get(tgt) != 'task':
                raise bad
            e = {'type': t, 'target': tgt, 'sel': selector(iv.get('selector'))}
            lst = P.dur
        elif t in ('timer_set', 'timer_scale', 'timer_distribution'):
            tgt = iv.get('timer')
            if not isinstance(tgt, str) or M.ntype.get(tgt) != 'intermediateCatchEvent':
                raise bad
            e = {'type': t, 'target': tgt, 'sel': selector(iv.get('selector'))}
            lst = P.tim
        elif t == 'routing_set':
            g = iv.get('gateway')
            if not isinstance(g, str) or g not in M.route:
                raise bad
            pr = iv.get('probabilities')
            if not isinstance(pr, dict) or set(pr.keys()) != set(M.out[g]):
                raise bad
            try:
                fr = {k: dec_fraction(v) for k, v in pr.items()}
            except (ValueError, TypeError):
                raise bad
            if sum(fr.values()) != 1:
                raise bad
            P.rout.append({'target': g, 'sel': selector(iv.get('selector')),
                           'probs': [(f, fr[f]) for f, _ in M.route[g]]})
            continue
        elif t == 'resource_unavailable':
            pool = iv.get('pool')
            if not isinstance(pool, str) or pool not in M.pools:
                raise bad
            fr_, to_ = iv.get('from'), iv.get('to')
            if not is_int(fr_) or not is_int(to_) or fr_ >= to_:
                raise bad
            size = M.pools[pool]['amount']
            if ('count' in iv) == ('instances' in iv):
                raise bad
            if 'count' in iv:
                c = iv['count']
                if not is_int(c) or c < 1 or c > size:
                    raise bad
                ks = list(range(size - c, size))
            else:
                ins = iv['instances']
                if not isinstance(ins, list) or not ins:
                    raise bad
                names = {pool + '_' + str(k): k for k in range(size)}
                ks = []
                for n in ins:
                    if not isinstance(n, str) or n not in names:
                        raise bad
                    ks.append(names[n])
            P.unavail.append((pool, set(ks), fr_, to_))
            continue
        elif t == 'resource_add':
            pool = iv.get('pool')
            if not isinstance(pool, str) or pool not in M.pools:
                raise bad
            c, fr_ = iv.get('count'), iv.get('from')
            if not is_int(c) or c < 1 or not is_int(fr_) or fr_ < 0:
                raise bad
            P.add.append((pool, c, fr_))
            continue
        else:
            raise bad
        # value fields
        if t.endswith('_set'):
            s = iv.get('seconds')
            if not is_int(s) or s < 0:
                raise bad
            e['seconds'] = s
        elif t.endswith('_scale'):
            try:
                e['factor'] = dec_fraction(iv.get('factor'))
            except (ValueError, TypeError):
                raise bad
        else:
            e['dist'] = idist(iv)
        lst.append(e)
    return P, run_cases


def sel_match(sel, case, visit, ref):
    if 'case' in sel and sel['case'] != case:
        return False
    if 'visit' in sel and sel['visit'] != visit:
        return False
    if 'from' in sel and ref < sel['from']:
        return False
    if 'to' in sel and ref >= sel['to']:
        return False
    return True


# ---------------------------------------------------------------- simulation
class Inst:
    __slots__ = ('name', 'k', 'W', 'free_at')

    def __init__(self, name, k, W, free_at):
        self.name, self.k, self.W, self.free_at = name, k, W, free_at


def simulate(S, ov, M, P, run_cases):
    seed = S['seed']
    n_cases = S['n_cases']

    def U(case, element, visit, variable):
        key = (case, element, visit, variable)
        if key in ov:
            return ov[key]
        return hash_u(seed, case, element, visit, variable)

    # arrivals over all base cases (before interventions)
    arrivals = {}
    prev = None
    for i in range(n_cases):
        cid = case_id(i)
        if i == 0:
            a = M.arr_cal.next_open(0)
        else:
            d = Q(M.arr_dist, float(U(cid, M.start, 1, 'interarrival')))
            a = M.arr_cal.next_open(prev + d)
        prev = a
        if cid in run_cases:
            arrivals[cid] = a
    for c, a in P.added.items():
        arrivals[c] = a

    # resources
    pools = {}
    for name, p in M.pools.items():
        insts = []
        for k in range(p['amount']):
            rem = []
            for (pn, ks, f, t) in P.unavail:
                if pn == name and k in ks:
                    rem.append((f, t))
            insts.append(Inst(name + '_' + str(k), k, WSet(p['windows'], 0, rem), 0))
        for (pn, cnt, frm) in P.add:
            if pn == name:
                for _ in range(cnt):
                    k = len(insts)
                    insts.append(Inst(name + '_' + str(k), k, WSet(p['windows'], frm), frm))
        pools[name] = {'insts': insts, 'wait': []}

    cases_out, tasks_out, timers_out, branches_out, draws_out = [], [], [], [], []
    visits = {}
    joins = {}
    cstate = {c: {'arr': arrivals[c], 'end': None, 'end_event': None} for c in arrivals}
    events = []
    seq = [0]

    def push(t, case, node, flow):
        seq[0] += 1
        heapq.heappush(events, (t, seq[0], case, node, flow))

    for c, a in arrivals.items():
        f = M.out[M.start][0]
        push(a, c, M.ftgt[f], f)

    def visit_of(case, el):
        v = visits.get((case, el), 0) + 1
        if v > 100:
            raise WfError('visit_limit_exceeded')
        visits[(case, el)] = v
        return v

    def one_match(lst, case, tgt, visit, ref):
        m = [e for e in lst if e['target'] == tgt and sel_match(e['sel'], case, visit, ref)]
        if len(m) > 1:
            raise WfError('conflicting_interventions')
        return m[0] if m else None

    hops = [0]

    def handle(t, case, node, flow):
        hops[0] += 1
        if hops[0] > 20000000:
            raise WfError('visit_limit_exceeded')
        typ = M.ntype[node]
        if typ == 'task':
            v = visit_of(case, node)
            key = (t, cstate[case]['arr'], case, node, v)
            heapq.heappush(pools[M.task_pool[node]]['wait'], key)
        elif typ == 'intermediateCatchEvent':
            v = visit_of(case, node)
            u = U(case, node, v, 'timer')
            base = Q(M.timer_dist[node], float(u))
            iv = one_match(P.tim, case, node, v, t)
            d = base
            if iv is not None:
                if iv['type'] == 'timer_set':
                    d = iv['seconds']
                elif iv['type'] == 'timer_scale':
                    d = math.floor(base * iv['factor'] + Fraction(1, 2))
                else:
                    d = Q(iv['dist'], float(u))
            timers_out.append({'case': case, 'timer': node, 'visit': v, 'start': t, 'end': t + d, 'delay': d})
            draws_out.append({'case': case, 'element': node, 'visit': v, 'variable': 'timer',
                              'u': '%.12f' % float(u)})
            f = M.out[node][0]
            push(t + d, case, M.ftgt[f], f)
        elif typ == 'exclusiveGateway':
            outs = M.out[node]
            if len(outs) == 1:
                push(t, case, M.ftgt[outs[0]], outs[0])
                return
            v = visit_of(case, node)
            u = U(case, node, v, 'branch')
            probs = M.route[node]
            iv = one_match(P.rout, case, node, v, t)
            if iv is not None:
                probs = iv['probs']
            acc = Fraction(0)
            chosen = None
            for f, p in probs:
                acc += p
                if u < acc:
                    chosen = f
                    break
            branches_out.append({'case': case, 'gateway': node, 'visit': v, 'time': t, 'flow': chosen})
            draws_out.append({'case': case, 'element': node, 'visit': v, 'variable': 'branch',
                              'u': '%.12f' % float(u)})
            push(t, case, M.ftgt[chosen], chosen)
        elif typ == 'parallelGateway':
            st = joins.setdefault((case, node), {f: [] for f in M.inc[node]})
            st[flow].append(t)
            if all(st[f] for f in M.inc[node]):
                firsts = {f: min(st[f]) for f in M.inc[node]}
                tf = max(firsts.values())
                for f in M.inc[node]:
                    st[f].remove(firsts[f])
                for f in M.out[node]:
                    push(tf, case, M.ftgt[f], f)
        else:  # end event
            cs = cstate[case]
            if cs['end'] is None or t > cs['end'] or (t == cs['end'] and node < cs['end_event']):
                cs['end'], cs['end_event'] = t, node

    def pool_options(pool, now):
        res = []
        for r in pool['insts']:
            s = r.W.next_open(max(now, r.free_at))
            res.append((s, r.free_at, r.k, r))
        return res

    now = 0
    while True:
        cand = []
        if events:
            cand.append(events[0][0])
        for pool in pools.values():
            if pool['wait']:
                cand.append(min(o[0] for o in pool_options(pool, now)))
        if not cand:
            break
        t = max(min(cand), now)
        now = t
        while True:
            while events and events[0][0] <= t:
                _, _, case, node, flow = heapq.heappop(events)
                handle(t, case, node, flow)
            best = None
            for name, pool in pools.items():
                if not pool['wait']:
                    continue
                opts = pool_options(pool, t)
                mn = min((o[0], o[1], o[2]) for o in opts)
                if mn[0] != t:
                    continue
                head = pool['wait'][0]
                if best is None or head < best[0]:
                    inst = [o[3] for o in opts if (o[0], o[1], o[2]) == mn][0]
                    best = (head, name, inst)
            if best is None:
                break
            key, name, r = best
            heapq.heappop(pools[name]['wait'])
            enabled, _arr, case, task, v = key
            u = U(case, task, v, 'service')
            base = Q(M.task_dist[task], float(u))
            iv = one_match(P.dur, case, task, v, t)
            d = base
            if iv is not None:
                if iv['type'] == 'duration_set':
                    d = iv['seconds']
                elif iv['type'] == 'duration_scale':
                    d = math.floor(base * iv['factor'] + Fraction(1, 2))
                else:
                    d = Q(iv['dist'], float(u))
            end = r.W.work_end(t, d)
            r.free_at = end
            tasks_out.append({'case': case, 'task': task, 'visit': v, 'enabled': enabled, 'start': t,
                              'end': end, 'resource': r.name, 'service': d})
            draws_out.append({'case': case, 'element': task, 'visit': v, 'variable': 'service',
                              'u': '%.12f' % float(u)})
            f = M.out[task][0]
            push(end, case, M.ftgt[f], f)

    for st in joins.values():
        if any(st[f] for f in st):
            raise WfError('deadlock')
    for c, cs in cstate.items():
        if cs['end'] is None:
            raise WfError('deadlock')
        cases_out.append({'case': c, 'arrival': cs['arr'], 'end': cs['end'], 'end_event': cs['end_event']})

    cases_out.sort(key=lambda r: (r['arrival'], r['case']))
    tasks_out.sort(key=lambda r: (r['case'], r['enabled'], r['task'], r['visit']))
    timers_out.sort(key=lambda r: (r['case'], r['start'], r['timer'], r['visit']))
    branches_out.sort(key=lambda r: (r['case'], r['time'], r['gateway'], r['visit']))
    draws_out.sort(key=lambda r: (r['case'], r['element'], r['visit'], r['variable']))
    return cases_out, tasks_out, timers_out, branches_out, draws_out


def main():
    scen_path, out_path = sys.argv[1], sys.argv[2]
    sid = None
    try:
        try:
            with open(scen_path, 'r', encoding='utf-8') as fh:
                S = json.load(fh)
        except Exception:
            raise WfError('invalid_scenario')
        if isinstance(S, dict) and isinstance(S.get('scenario_id'), str):
            sid = S['scenario_id']
        ov, ivs = validate_scenario(S)
        base = os.path.dirname(os.path.abspath(scen_path))
        M = load_model(os.path.join(base, S['model']['bpmn']), os.path.join(base, S['model']['params']))
        P, run_cases = parse_interventions(ivs, M, S['n_cases'])
        c, t, tm, b, d = simulate(S, ov, M, P, run_cases)
        result = {'schema': 'wf-run/1', 'scenario_id': sid, 'status': 'ok', 'cases': c, 'tasks': t,
                  'timers': tm, 'branches': b, 'draws': d}
    except WfError as e:
        result = {'schema': 'wf-run/1', 'scenario_id': sid, 'status': 'error', 'error': e.code}
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(result, fh, indent=1)
        fh.write('\n')


if __name__ == '__main__':
    main()
