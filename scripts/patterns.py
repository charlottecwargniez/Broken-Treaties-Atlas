"""Analyses for the Patterns view: survival curves and structural balance.

Both are computed from the merged dataset produced by build.py, plus two extra tables:
  data/raw/rivalries/tss_rivalries.csv  strategic rivalries 1494-2020 (Thompson, Sakuwa & Suhas 2021)
  data/raw/cow/cow_majors.csv           COW major-power status (v2016)
"""
import math, os
from collections import defaultdict
import numpy as np
import pandas as pd

NOW = 2026
PEACE = ('peace', 'armistice', 'ceasefire')
PACTS = ('nonaggression', 'neutrality')


# ------------------------------------------------------------------ survival
def km(times, events, tmax=100):
    """Kaplan-Meier estimate on integer years. Returns list of [t, S, lo, hi] at each year 0..tmax
    (stops when fewer than 5 treaties remain at risk), plus the number at risk at 0."""
    times = np.asarray(times, dtype=int); events = np.asarray(events, dtype=bool)
    S, var, out = 1.0, 0.0, [[0, 1.0, 1.0, 1.0]]
    for t in range(0, tmax + 1):
        at_risk = int((times >= t).sum())
        if at_risk < 5: break
        d = int(((times == t) & events).sum())
        if d:
            S *= 1 - d / at_risk
            if at_risk > d: var += d / (at_risk * (at_risk - d))
        # log-log CI is better behaved near 0 and 1
        if 0 < S < 1 and var > 0:
            se = math.sqrt(var) / abs(math.log(S))
            lo, hi = S ** math.exp(1.96 * se), S ** math.exp(-1.96 * se)
        else:
            lo = hi = S
        out.append([t + 1, round(S, 4), round(lo, 4), round(hi, 4)])
    return out


def at(curve, y):
    for t, s, *_ in curve:
        if t >= y: return s
    return None


def survival(out):
    C = out['countries']; W = {w['id']: w for w in out['wars']}

    def alive_until(a, b):
        ea = C.get(a, {}).get('end') or NOW; eb = C.get(b, {}).get('end') or NOW
        return min(ea, eb, NOW)

    rows = []
    for t in out['treaties']:
        if t['type'] in PEACE and len(t['sides']) == 2 and t['sides'][0] and t['sides'][1]:
            pairs = [(x, y) for x in t['sides'][0] for y in t['sides'][1] if x != y]
        else:
            ps = t['parties']; pairs = [(ps[i], ps[j]) for i in range(len(ps)) for j in range(i + 1, len(ps))]
        if not pairs: continue
        horizon = max(alive_until(a, b) for a, b in pairs) - t['year']
        if horizon <= 0: continue
        ew = W.get(t.get('ends_war'))
        r = {'id': t['id'], 'type': t['type'], 'year': t['year'], 'n': len(t['parties']), 'src': t['src'],
             'major_end': bool(ew and ew['major'])}
        for key, cond in (('war', lambda h: True), ('major', lambda h: W[h['w']]['major'])):
            hits = [h['gap'] for h in t['conflicts'] if cond(h)]
            if hits and min(hits) <= horizon: r[key] = (max(min(hits), 0), True)
            else: r[key] = (horizon, False)
        # documented breach: censored at the treaty's end, 2018 for ATOP alliances still in force, today otherwise
        if t.get('violated') and t['violated'].get('year'):
            r['breach'] = (max(int(t['violated']['year']) - t['year'], 0), True)
        else:
            end = t.get('end') or (2018 if t['src'] == 'ATOP 5.1' else NOW)
            r['breach'] = (max(end - t['year'], 0), False)
        rows.append(r)

    def era(y, cuts):
        for lab, a, b in cuts:
            if a <= y <= b: return lab

    groups = {
        'kind': {
            'label': 'Treaty type',
            'series': [
                ('Peace treaties & armistices', lambda r: r['type'] in PEACE),
                ('Alliances', lambda r: r['type'] == 'alliance'),
                ('Non-aggression & neutrality pacts', lambda r: r['type'] in PACTS),
            ]},
        'peace_era': {
            'label': 'Peace treaties by era',
            'series': [(lab, (lambda a, b: lambda r: r['type'] in PEACE and a <= r['year'] <= b)(a, b))
                       for lab, a, b in (('1648–1814', 1648, 1814), ('1815–1913', 1815, 1913), ('1914–1945', 1914, 1945), ('1946–today', 1946, NOW))]},
        'alliance_era': {
            'label': 'Alliances by era',
            'series': [(lab, (lambda a, b: lambda r: r['type'] == 'alliance' and a <= r['year'] <= b)(a, b))
                       for lab, a, b in (('1648–1814', 1648, 1814), ('1815–1913', 1815, 1913), ('1914–1945', 1914, 1945), ('1946–2018', 1946, 2018))]},
        'war_size': {
            'label': 'Peace treaties by the war they ended',
            'series': [
                ('Ended a major war', lambda r: r['type'] in PEACE and r['major_end']),
                ('Ended a smaller war, or none recorded', lambda r: r['type'] in PEACE and not r['major_end']),
            ]},
        'size': {
            'label': 'Alliances by size',
            'series': [
                ('Bilateral', lambda r: r['type'] == 'alliance' and r['n'] == 2),
                ('3–5 members', lambda r: r['type'] == 'alliance' and 3 <= r['n'] <= 5),
                ('6 or more members', lambda r: r['type'] == 'alliance' and r['n'] >= 6),
            ]},
    }
    res = {}
    for gk, g in groups.items():
        res[gk] = {'label': g['label'], 'series': []}
        for lab, f in g['series']:
            sub = [r for r in rows if f(r)]
            if len(sub) < 8: continue
            s = {'label': lab, 'n': len(sub)}
            for outcome in ('war', 'major', 'breach'):
                T = [r[outcome][0] for r in sub]; E = [r[outcome][1] for r in sub]
                curve = km(T, E)
                med = next((t for t, sv, *_ in curve if sv <= 0.5), None)
                s[outcome] = {'curve': curve, 'events': int(sum(E)), 'median': med,
                              'at10': at(curve, 10), 'at20': at(curve, 20), 'at50': at(curve, 50)}
            res[gk]['series'].append(s)
    return res


# ------------------------------------------------------------------ structural balance
GP_NAMES = {2: 'USA', 200: 'UKG', 220: 'FRN', 255: 'GMY', 300: 'AUH', 325: 'ITA', 365: 'RUS', 710: 'CHN', 740: 'JPN'}


def balance(out, raw, y0=1816, y1=2018):
    countries = out['countries']; W = {w['id']: w for w in out['wars']}
    st = pd.read_csv(os.path.join(raw, 'cow', 'cow_states.csv'))
    ab = dict(zip(st.ccode.astype(int), st.stateabb))
    riv = pd.read_csv(os.path.join(raw, 'rivalries', 'tss_rivalries.csv'))
    maj = pd.read_csv(os.path.join(raw, 'cow', 'cow_majors.csv'))
    maj.loc[maj.endyear >= 2016, 'endyear'] = y1  # COW list ends 2016; assume status unchanged to 2018
    cw = pd.read_csv(os.path.join(raw, 'cow', 'cow_war_inter.csv'))
    codes = sorted(countries); ix = {c: i for i, c in enumerate(codes)}; n = len(codes)

    def key(a, b): return (a, b) if a < b else (b, a)

    # positive ties: alliance-type agreements in force, by year (members' own entry/exit years)
    pos_def = defaultdict(lambda: defaultdict(list))  # year -> pair -> [treaty names]   (defence/offence pacts)
    pos_any = defaultdict(lambda: defaultdict(list))  # any ATOP agreement (incl. non-aggression, neutrality, consultation)
    for t in out['treaties']:
        if t['src'] != 'ATOP 5.1': continue
        strong = 'defence' in (t.get('obl') or []) or 'offensive' in (t.get('obl') or [])
        mem = t['members']
        for i in range(len(mem)):
            for j in range(i + 1, len(mem)):
                a, b = mem[i], mem[j]
                s = max(a['in'], b['in']); e = min(a['out'] or y1, b['out'] or y1)
                for y in range(max(s, y0), min(e, y1) + 1):
                    k = key(a['c'], b['c'])
                    pos_any[y][k].append(t['name'])
                    if strong: pos_def[y][k].append(t['name'])
    # negative ties: active strategic rivalry, or at war that year
    neg = defaultdict(lambda: defaultdict(list))
    for r in riv.itertuples():
        a, b = ab.get(int(r.ccode1)), ab.get(int(r.ccode2))
        if not a or not b: continue
        for y in range(max(int(r.start), y0), min(int(r.end), y1) + 1):
            neg[y][key(a, b)].append('Rivalry: ' + str(r.rivalry))
    for r in cw.itertuples():
        a, b = ab[int(r.ccode1)], ab[int(r.ccode2)]
        if a < b and y0 <= r.year <= y1:
            neg[int(r.year)][key(a, b)].append('War: ' + W[f'cow_{int(r.warnum)}']['name'])
    for w in W.values():
        if w['src'] != 'curated' or w['start'] < 2004: continue
        for a, b in w['pairs']:
            for y in range(w['start'], min(w['end'] or y1, y1) + 1):
                if y0 <= y <= y1: neg[y][key(a, b)].append('War: ' + w['name'])

    def counts(P, N):
        PP = P @ P; NN = N @ N
        ppp = int(np.trace(PP @ P) // 6); nnn = int(np.trace(NN @ N) // 6)
        ppn = int((N * PP).sum() // 2); pnn = int((P * NN).sum() // 2)
        return ppp, ppn, pnn, nnn

    series = {'all_def': [], 'all_any': [], 'gp': []}
    snaps = {}
    for y in range(y0, y1 + 1):
        gp = sorted({GP_NAMES[int(m.ccode)] for m in maj.itertuples() if m.styear <= y <= m.endyear})
        for mode, pos in (('all_def', pos_def), ('all_any', pos_any)):
            P = np.zeros((n, n), dtype=np.int64); N = np.zeros((n, n), dtype=np.int64)
            for (a, b) in neg[y]: N[ix[a], ix[b]] = N[ix[b], ix[a]] = 1
            for (a, b) in pos[y]:
                if N[ix[a], ix[b]]: continue  # a pair that is both allied and hostile is treated as hostile
                P[ix[a], ix[b]] = P[ix[b], ix[a]] = 1
            series[mode].append([y, *counts(P, N), int(P.sum() // 2), int(N.sum() // 2)])
        # great-power subsystem: any agreement counts as a positive tie
        g = {c: i for i, c in enumerate(gp)}; m = len(gp)
        P = np.zeros((m, m), dtype=np.int64); N = np.zeros((m, m), dtype=np.int64); edges = []
        for i in range(m):
            for j in range(i + 1, m):
                k = key(gp[i], gp[j])
                if k in neg[y]:
                    N[i, j] = N[j, i] = 1; edges.append([gp[i], gp[j], -1, sorted(set(neg[y][k]))[:3]])
                elif k in pos_any[y]:
                    P[i, j] = P[j, i] = 1; edges.append([gp[i], gp[j], 1, sorted(set(pos_any[y][k]))[:3]])
        tri = []
        for i in range(m):
            for j in range(i + 1, m):
                for k2 in range(j + 1, m):
                    sg = [P[i, j] - N[i, j], P[i, k2] - N[i, k2], P[j, k2] - N[j, k2]]
                    if 0 in sg: continue
                    tri.append([gp[i], gp[j], gp[k2], int(np.prod(sg) > 0), int(sum(1 for s in sg if s < 0))])
        series['gp'].append([y, *counts(P, N), int(P.sum() // 2), int(N.sum() // 2)])
        snaps[y] = {'nodes': gp, 'edges': edges, 'tri': tri}
    return {'range': [y0, y1], 'series': series, 'snaps': snaps,
            'cols': ['year', 'ppp', 'ppn', 'pnn', 'nnn', 'pos_edges', 'neg_edges']}


def compute(out, raw):
    return {'survival': survival(out), 'balance': balance(out, raw)}
