"""
Simulate the new computeAssocTable (OPR-ID keyed, with fallback merge)
against the current orbit-data.js and verify the validation criteria.
"""
import json, re
from collections import defaultdict

src = open(
    r'C:\Users\AL70683\OneDrive - Elevance Health\IGNITE PROJECTS\ORBIT\ORBIT DASH\orbit-data.js',
    encoding='utf-8'
).read()

def arr(name):
    m = re.search(r'const %s=(\[.*?\]);' % name, src, re.S)
    return json.loads(m.group(1)) if m else []

prod = arr('D_PROD')
qa   = arr('D_QA')
dim  = arr('D_DIM')

dim_by_id   = {d['id']: d for d in dim}
dim_by_name = {d['n']: d['id'] for d in dim if d.get('n')}
id_to_name  = {}

def dim_am(oid):
    d = dim_by_id.get(oid, {})
    return d.get('am') or d.get('mgr') or ''

def group_by(rows, key):
    result = defaultdict(list)
    for r in rows:
        result[r.get(key, '')].append(r)
    return dict(result)

assoc_map = {}

# 1. D_PROD
prod_by_assoc = group_by(prod, 'a')
for name, rows in prod_by_assoc.items():
    if not name: continue
    act    = sum(r.get('act', 0) for r in rows)
    tgt    = sum(r.get('tgt', 0) for r in rows)
    oid    = dim_by_name.get(name)
    mapKey = oid or ('n:' + name)
    sorted_rows = sorted(rows, key=lambda r: r.get('ym', ''), reverse=True)
    manager = (dim_am(oid) if oid else '') or sorted_rows[0].get('m', '')
    assoc_map[mapKey] = dict(id=mapKey, name=name, manager=manager,
                              act=act, tgt=tgt, qaCnt=0, qaScr=0.0)

# 2. D_QA keyed by OPR ID, with fallback-name merge
qa_by_id = group_by(qa, 'id')
for oid, rows in qa_by_id.items():
    if not oid: continue
    is_matched = rows[0].get('fn') and rows[0].get('fn') != 'un'
    dim_entry  = dim_by_id.get(oid)
    name       = (dim_entry['n'] if dim_entry else
                  (rows[0].get('a') if is_matched else
                   (id_to_name.get(oid) or rows[0].get('a') or oid)))
    map_key    = oid
    fallback_key = 'n:' + name

    # Merge into existing prod fallback entry if name matches
    if map_key in assoc_map:
        target_key = map_key
    elif fallback_key in assoc_map:
        target_key = fallback_key
    else:
        target_key = map_key

    cnt  = sum(r.get('cnt', 0) for r in rows)
    wscr = sum(r.get('cnt', 0) * r.get('scr', 0) for r in rows)
    if target_key not in assoc_map:
        sorted_q = sorted(rows, key=lambda r: r.get('d', ''), reverse=True)
        manager  = dim_am(oid) or sorted_q[0].get('m', '')
        assoc_map[target_key] = dict(id=target_key, name=name, manager=manager,
                                      act=None, tgt=None, qaCnt=0, qaScr=0.0)
    else:
        if dim_entry and dim_entry.get('n'):
            assoc_map[target_key]['name'] = dim_entry['n']
    assoc_map[target_key]['qaCnt'] += cnt
    assoc_map[target_key]['qaScr'] += wscr

# ── Validation ─────────────────────────────────────────────────
rows_out = list(assoc_map.values())

opr_id_keys  = [k for k in assoc_map if not k.startswith('n:')]
fallback_keys = [k for k in assoc_map if k.startswith('n:')]

print('=' * 60)
print('VALIDATION RESULTS')
print('=' * 60)
print('Total grid rows rendered:      %d' % len(rows_out))
print('Rows keyed by OPR ID:          %d' % len(opr_id_keys))
print('Rows keyed by name (fallback): %d' % len(fallback_keys))
print()

name_counts = defaultdict(list)
for r in rows_out:
    name_counts[r['name']].append(r['id'])

dupes = {n: ids for n, ids in name_counts.items() if len(ids) > 1}
if dupes:
    print('DUPLICATE NAMES REMAINING (%d):' % len(dupes))
    for n, ids in sorted(dupes.items())[:20]:
        print('  %-40s -> keys: %s' % (n, ids))
else:
    print('PASS: No duplicate associate names in the grid.')

EXAMPLES = [
    'Cuntapay, Raymart',
    'Erram, Kristine Anne',
    'Espectacion, Magic Jongee',
    'Ontoria, Mary Nixcelle Pearl',
    'Udarbe, Maricel',
    'Tamano-Ombra, Jhonaida Manan',
    'Tamano-Ombra, Jhonaida',
]
print()
print('=== Example associates ===')
for ex in EXAMPLES:
    matching = [r for r in rows_out if r['name'] == ex or ex in r['name']]
    if not matching:
        matching = [r for r in rows_out if ex.split(',')[0].strip().lower() in r['name'].lower()]
    seen_ids = set()
    for r in matching:
        if r['id'] not in seen_ids:
            seen_ids.add(r['id'])
            print('  FOUND id=%-12s name=%-40s mgr=%s' % (r['id'], r['name'], r['manager']))

print()
print('=== COB example managers ===')
for oid in ['AL86935', 'AL86929', 'AL86936', 'AL86930', 'AL69201']:
    r = assoc_map.get(oid)
    expected_am = dim_by_id.get(oid, {}).get('am', '?')
    if r:
        status = 'OK' if r['manager'] == expected_am else 'MISMATCH'
        print('  %s [%s] %-30s mgr=%r' % (oid, status, r['name'], r['manager']))

print()
print('=== Summary ===')
print('  D_QA distinct OPR IDs:  %d' % len(qa_by_id))
print('  Grid rows:               %d' % len(rows_out))
print('  Duplicate-free:          %s' % ('YES' if not dupes else 'NO (%d)' % len(dupes)))
