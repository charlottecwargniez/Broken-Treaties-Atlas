"""Build the Broken Treaties Atlas: merge the sources into data/data.json and render index.html.

Inputs (all under data/)
  raw/atop/atop5_1a.csv, atop5_1m.csv        ATOP 5.1 alliance- and member-level data (Leeds et al.)
  raw/cow/cow_war_inter.csv, cow_states.csv  COW Inter-State War v4.0 (dyad-year) and state list
  atop_names.json                            common names for well-known ATOP alliances
  curated/*.json                             hand-curated treaties and wars (1648-1815, 1816-2026)

Usage:  python scripts/build.py
"""
import json, itertools, os, sys
from collections import defaultdict
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
RAW = os.path.join(DATA, 'raw')
CUR = os.path.join(DATA, 'curated')


def load(name, default=None):
    p = os.path.join(CUR, name)
    if not os.path.exists(p):
        print('MISSING', name, file=sys.stderr); return default
    return json.load(open(p))


# ---------------------------------------------------------------- countries
st = pd.read_csv(os.path.join(RAW, 'cow', 'cow_states.csv'))
ab = dict(zip(st.ccode.astype(int), st.stateabb))
countries = {}
for abb, g in st.groupby('stateabb'):
    cc = int(g.ccode.iloc[0])
    reg = 'Americas' if cc < 200 else 'Europe' if cc < 400 else 'Africa' if cc < 600 else 'Middle East' if cc < 700 else 'Asia & Oceania'
    if cc in (600, 615, 616, 620, 625): reg = 'Africa'  # Morocco, Algeria, Tunisia, Libya, Sudan
    countries[abb] = {'name': g.statenme.iloc[0], 'start': int(g.styear.min()), 'end': int(g.endyear.max()), 'region': reg}
NAME_FIX = {
    'GMY': 'Germany (Prussia)', 'AUH': 'Austria (Austria-Hungary)', 'TUR': 'Turkey (Ottoman Empire)',
    'RUS': 'Russia (USSR)', 'YUG': 'Serbia (Yugoslavia)', 'ITA': 'Italy (Sardinia)', 'UKG': 'United Kingdom',
    'USA': 'United States', 'DRV': 'Vietnam (North Vietnam)', 'RVN': 'South Vietnam', 'GFR': 'West Germany',
    'GDR': 'East Germany', 'SIC': 'Two Sicilies (Naples)', 'PAP': 'Papal States', 'ROK': 'South Korea',
    'PRK': 'North Korea', 'TAW': 'Taiwan', 'CHN': 'China', 'IRN': 'Iran (Persia)', 'NTH': 'Netherlands',
    'DRC': 'DR Congo', 'YAR': 'Yemen (North)', 'YPR': 'South Yemen', 'CZE': 'Czechoslovakia',
    'CZR': 'Czech Republic', 'BOS': 'Bosnia and Herzegovina', 'MYA': 'Myanmar', 'ETH': 'Ethiopia',
}
for k, v in NAME_FIX.items():
    if k in countries: countries[k]['name'] = v
EXTRA_REGION = {'MRT': 'Asia & Oceania', 'MYS': 'Asia & Oceania', 'PLO': 'Middle East', 'PRG': 'Asia & Oceania', 'M23': 'Africa'}
for fn in ('countries_extra.json', 'countries_extra_1816.json'):
    for c in load(fn, []) or []:
        code = c.get('code')
        if not code: continue
        if code in countries:
            if c.get('note'): countries[code]['note'] = c['note']
            if c.get('start') and c['start'] < countries[code]['start']: countries[code]['start'] = c['start']
            continue
        countries[code] = {'name': c.get('name', code).split(' (as a body')[0], 'start': c.get('start'), 'end': c.get('end'), 'note': c.get('note'),
                           'region': c.get('region') or EXTRA_REGION.get(code, 'Europe')}

# ---------------------------------------------------------------- wars
wars = {}
cw = pd.read_csv(os.path.join(RAW, 'cow', 'cow_war_inter.csv'))
cow_names = load('cow_war_names.json', {}) or {}
for wn, g in cw.groupby('warnum'):
    wn = int(wn); key = str(wn)
    info = cow_names.get(key, {})
    a = sorted({ab[int(c)] for c in g[g.sidea1 == 1].ccode1})
    b = sorted({ab[int(c)] for c in g[g.sidea1 == 2].ccode1})
    pairs = {}
    for r in g.itertuples():
        p = tuple(sorted((ab[int(r.ccode1)], ab[int(r.ccode2)])))
        pairs[p] = min(pairs.get(p, 9999), int(r.year))
    deaths = int(g.groupby('ccode1').batdeath1.max().clip(lower=0).sum())
    major_default = deaths >= 10000
    wars[f'cow_{wn}'] = {
        'id': f'cow_{wn}', 'name': info.get('name', f'COW war #{wn}'), 'start': int(g.year.min()), 'end': int(g.year.max()),
        'sides': [a, b], 'deaths': deaths, 'major': bool(info.get('major', major_default)), 'src': 'COW Inter-State War v4.0',
        'pairs': [list(p) for p in pairs], 'pair_years': {f'{p[0]}|{p[1]}': y for p, y in pairs.items()},
    }
for fn in ('wars_1648_1815.json', 'wars_2004_2026.json'):
    for w in load(fn, []) or []:
        A, B = w.get('sideA', []), w.get('sideB', [])
        pairs = sorted({tuple(sorted((x, y))) for x in A for y in B if x != y})
        wars[w['id']] = {'id': w['id'], 'name': w['name'], 'start': int(w['start']), 'end': int(w.get('end') or w['start']),
                         'sides': [A, B], 'deaths': w.get('deaths_est'), 'major': bool(w.get('major')),
                         'src': 'curated', 'note': w.get('note'), 'pairs': [list(p) for p in pairs]}

# pair -> list of (war id, start year)
pair_wars = defaultdict(list)
for w in wars.values():
    for p in w['pairs']:
        pair_wars[tuple(p)].append((w['id'], w.get('pair_years', {}).get(f'{p[0]}|{p[1]}', w['start'])))

# ---------------------------------------------------------------- ATOP alliances
names = json.load(open(os.path.join(DATA, 'atop_names.json')))
A = pd.read_csv(os.path.join(RAW, 'atop', 'atop5_1a.csv'))
M = pd.read_csv(os.path.join(RAW, 'atop', 'atop5_1m.csv'))
OBL = [('defense', 'defence'), ('offense', 'offensive'), ('neutral', 'neutrality'), ('nonagg', 'non-aggression'), ('consul', 'consultation')]
TERMCAUS = {1: 'replaced by new agreement', 2: 'member lost independence', 3: 'aim achieved', 4: 'policy dispute',
            5: 'dispute over alliance management', 6: 'members fought each other', 7: 'war ended it', 8: 'violation short of war'}
treaties = []
for aid, x in M.groupby('atopid'):
    mem = []
    for r in x.itertuples():
        c = ab.get(int(r.member))
        if c is None: continue
        mem.append({'c': c, 'in': int(r.yrent), 'out': None if r.ineffect == 1 else int(r.yrexit),
                    'mode': int(r.termmode), 'cause': None if pd.isna(r.termcaus) else int(r.termcaus)})
    # merge phases per member (keep earliest entry / latest exit)
    mm = {}
    for e in mem:
        if e['c'] not in mm: mm[e['c']] = dict(e)
        else:
            o = mm[e['c']]; o['in'] = min(o['in'], e['in'])
            o['out'] = None if (o['out'] is None or e['out'] is None) else max(o['out'], e['out'])
            o['mode'], o['cause'] = e['mode'], e['cause']
    mem = list(mm.values())
    parties = sorted(mm)
    obl = [lab for k, lab in OBL if x[k].max() == 1]
    term = int(A[A.atopid == aid].term.iloc[-1])
    yr = int(x.yrent.min())
    if obl == ['non-aggression'] or obl == ['non-aggression', 'consultation']: typ = 'nonaggression'
    elif obl == ['consultation']: typ = 'consultation'
    elif obl == ['neutrality'] or obl == ['neutrality', 'consultation'] or obl == ['neutrality', 'non-aggression'] or obl == ['neutrality', 'non-aggression', 'consultation']: typ = 'neutrality'
    else: typ = 'alliance'
    nm = names.get(str(aid))
    if not nm:
        lab = {'alliance': 'Defence pact' if 'defence' in obl else ('Offensive pact' if 'offensive' in obl else 'Alliance'),
               'nonaggression': 'Non-aggression pact', 'consultation': 'Consultation pact', 'neutrality': 'Neutrality pact'}[typ]
        cn = [countries.get(p, {}).get('name', p) for p in parties]
        cn = [n.split(' (')[0] for n in cn]
        nm = f"{lab}: {' – '.join(cn)}" if len(cn) <= 3 else f"{lab}: {', '.join(cn[:3])} +{len(cn)-3}"
    ends = [e['out'] for e in mem if e['out'] is not None]
    end = None if any(e['out'] is None for e in mem) else (max(ends) if ends else None)
    causes = sorted({TERMCAUS[e['cause']] for e in mem if e['cause'] in (6, 7, 8)})
    viol = None
    if term == 2:
        vy = min([e['out'] for e in mem if e['mode'] == 3 and e['out']] or [end or yr])
        viol = {'is': True, 'year': vy, 'by': [], 'basis': 'ATOP',
                'how': 'ATOP codes this alliance as ending through violation or abrogation before its scheduled end'
                       + ((' (' + '; '.join(causes) + ')') if causes else '') + '.'}
    treaties.append({'id': f'atop_{aid}', 'name': nm, 'year': yr, 'date': f"{yr}-{int(x.moent.min()):02d}", 'end': end,
                     'type': typ, 'obl': obl, 'src': 'ATOP 5.1', 'parties': parties, 'members': mem, 'sides': [],
                     'violated': viol, 'judgment': None, 'summary': None, 'url': 'http://www.atopdata.org/', 'atopid': int(aid)})

atop_by_key = {}
for t in treaties:
    atop_by_key.setdefault((t['year'], tuple(t['parties'])), t)

# ---------------------------------------------------------------- curated treaties
DUP = {}  # curated id -> atop id it duplicates (merged into the ATOP record)
for fn in ('treaties_1648_1815.json', 'treaties_1816_2026.json'):
    for t in load(fn, []) or []:
        rec = {'id': t['id'], 'name': t['name'], 'year': int(t['year']), 'date': t.get('date'), 'end': None,
               'type': t.get('type', 'other'), 'src': 'curated', 'parties': sorted(set(t.get('parties', []))),
               'sides': t.get('sides') or [], 'ends_war': t.get('ends_war'),
               'violated': None, 'judgment': t.get('judgment'), 'summary': t.get('summary'), 'url': t.get('source_url')}
        v = t.get('violated')
        if v and v.get('is'):
            rec['violated'] = {'is': True, 'year': v.get('year'), 'by': v.get('by') or [], 'how': v.get('how'), 'basis': 'curated'}
        # merge with an ATOP alliance if same signature year and same membership
        hit = atop_by_key.get((rec['year'], tuple(rec['parties'])))
        if hit and rec['type'] not in ('peace', 'armistice', 'ceasefire'):
            DUP[rec['id']] = hit['id']
            hit['name'] = rec['name'] if hit['name'].split(':')[0] in ('Defence pact', 'Offensive pact', 'Alliance', 'Non-aggression pact', 'Consultation pact', 'Neutrality pact') else hit['name']
            hit['summary'] = hit['summary'] or rec['summary']; hit['url'] = rec['url'] or hit['url']
            hit['judgment'] = hit['judgment'] or rec['judgment']
            if rec['violated'] and not hit['violated']: hit['violated'] = rec['violated']
            continue
        treaties.append(rec)

# hand merges where membership differs slightly between sources
MANUAL_DUP = {'t_locarno_1925': 'atop_2130', 't_soviet_japanese_neutrality_1941': 'atop_2525', 't_helsinki_1975': 'atop_3740',
              't_london_1915': 'atop_2025', 't_quadruple_alliance_1815': 'atop_1035'}
byid = {t['id']: t for t in treaties}
for cid, aid in MANUAL_DUP.items():
    if cid in byid and aid in byid:
        c, a = byid[cid], byid[aid]
        a['summary'] = a['summary'] or c['summary']; a['url'] = c['url'] or a['url']; a['judgment'] = a['judgment'] or c['judgment']
        if c['violated'] and not a['violated']: a['violated'] = c['violated']
        elif c['violated'] and a['violated']:
            a['violated']['how'] = (c['violated'].get('how') or '') + ' ' + (a['violated'].get('how') or '')
        treaties.remove(c); DUP[cid] = aid

# ---------------------------------------------------------------- conflicts after signature
for t in treaties:
    if t['sides'] and len(t['sides']) == 2 and t['sides'][0] and t['sides'][1]:
        pairs = {tuple(sorted((x, y))) for x in t['sides'][0] for y in t['sides'][1] if x != y}
    else:
        pairs = {tuple(sorted(p)) for p in itertools.combinations(t['parties'], 2)}
    mem = {e['c']: e for e in t.get('members', [])}
    hits = {}
    for p in pairs:
        for wid, start in pair_wars.get(p, []):
            w = wars[wid]
            if wid == t.get('ends_war'): continue
            # both members must have joined before the war started
            if mem:
                if start < max(mem[p[0]]['in'], mem[p[1]]['in']): continue
            elif start < t['year']:
                continue
            during = False
            if mem:
                outs = [mem[p[0]]['out'], mem[p[1]]['out']]
                during = all(o is None or o >= start for o in outs)
            h = hits.setdefault(wid, {'w': wid, 'y': start, 'gap': start - t['year'], 'pairs': [], 'during': False})
            h['pairs'].append(list(p)); h['during'] = h['during'] or during
    t['conflicts'] = sorted(hits.values(), key=lambda h: h['y'])

# drop internal helper fields
for w in wars.values():
    w.pop('pair_years', None)

out = {'countries': countries, 'wars': list(wars.values()), 'treaties': sorted(treaties, key=lambda t: (t['year'], t['name'])),
       'meta': {'built': pd.Timestamp.now().strftime('%Y-%m-%d'), 'merged_duplicates': DUP}}
json.dump(out, open(os.path.join(DATA, 'data.json'), 'w'), ensure_ascii=False, separators=(',', ':'))

# ---------------------------------------------------------------- report
codes_used = {c for t in treaties for c in t['parties']} | {c for w in wars.values() for s in w['sides'] for c in s}
missing = sorted(codes_used - set(countries))
print('countries', len(countries), 'missing codes', missing)
print('wars', len(wars), 'treaties', len(treaties), pd.Series([t['type'] for t in treaties]).value_counts().to_dict())
print('dups merged', DUP)
bad_w = [(t['id'], t.get('ends_war')) for t in treaties if t.get('ends_war') and t['ends_war'] not in wars]
print('bad ends_war', bad_w)
print('bad judgment', [(t['id'], t['judgment'].get('led_to')) for t in treaties if t.get('judgment') and t['judgment'].get('led_to') not in wars])

# ---------------------------------------------------------------- render explorer
tpl = open(os.path.join(ROOT, 'scripts', 'template.html')).read()
payload = json.dumps(out, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
open(os.path.join(ROOT, 'index.html'), 'w').write(tpl.replace('/*__DATA__*/null', payload))
print('wrote explorer', os.path.getsize(os.path.join(ROOT, 'index.html')) // 1024, 'KB')
