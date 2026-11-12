"""
Diagnose duplicate associates in the performance grid.
Checks D_PROD and D_QA for the named examples and shows
exactly why each produces multiple rows in computeAssocTable.
"""
import json, re, os
from collections import defaultdict

SYS  = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.dirname(SYS)

src = open(os.path.join(DASH, 'orbit-data.js'), encoding='utf-8').read()
def arr(name):
    m = re.search(r'const %s=(\[.*?\]);' % name, src, re.S)
    return json.loads(m.group(1)) if m else []

prod = arr('D_PROD')
qa   = arr('D_QA')
dim  = arr('D_DIM')

EXAMPLES = [
    'Cuntapay, Raymart',
    'Erram, Kristine Anne',
    'Espectacion, Magic Jongee',
    'Ontoria, Mary Nixcelle Pearl',
    'Udarbe, Maricel',
    'Tamano-Ombra, Jhonaida Manan',
]

dim_map = {d['id']: d for d in dim}

print('=' * 70)
print('DUPLICATE ASSOCIATE DIAGNOSIS')
print('=' * 70)

for name in EXAMPLES:
    print(f'\n--- {name} ---')

    # D_PROD: how many unique (name) keys?  What managers appear?
    prod_rows = [r for r in prod if r.get('a') == name]
    prod_mgrs = sorted(set(r['m'] for r in prod_rows if r.get('m')))
    prod_yms  = sorted(set(r.get('ym','') for r in prod_rows))
    print(f'  D_PROD rows: {len(prod_rows)} | managers: {prod_mgrs} | months: {prod_yms[:6]}{"..." if len(prod_yms)>6 else ""}')

    # D_QA: grouped by OPR ID — what names do those IDs carry?
    qa_ids = sorted(set(r['id'] for r in qa if r.get('a') == name))
    for oid in qa_ids:
        qa_rows = [r for r in qa if r['id'] == oid]
        names_on_id = sorted(set(r.get('a','') for r in qa_rows))
        qa_mgrs = sorted(set(r.get('m','') for r in qa_rows))
        print(f'  D_QA id={oid}: names={names_on_id} | managers={qa_mgrs} | rows={len(qa_rows)}')

    # D_DIM entry
    dim_entries = [d for d in dim if d.get('n') == name]
    for d in dim_entries:
        print(f'  D_DIM: id={d["id"]} fn={d["fn"]} mgr={d["mgr"]!r} am={d["am"]!r}')

# ── Global duplicate analysis ────────────────────────────────
print('\n' + '=' * 70)
print('GLOBAL: D_PROD name grouping vs D_QA OPR ID grouping')
print('=' * 70)

# In computeAssocTable, the map key is `name` (string).
# D_PROD groups by r.a — count unique names
prod_names = defaultdict(list)
for r in prod:
    if r.get('a'):
        prod_names[r['a']].append(r['m'])

# Associates with multiple distinct managers in D_PROD
multi_mgr_prod = {n: sorted(set(ms)) for n, ms in prod_names.items() if len(set(ms)) > 1}
print(f'\nD_PROD: associates with 2+ distinct managers: {len(multi_mgr_prod)}')
for n, mgrs in sorted(multi_mgr_prod.items())[:10]:
    print(f'  {n}: {mgrs}')

# D_QA groups by id — check if any id maps to multiple names
qa_id_names = defaultdict(set)
for r in qa:
    if r.get('id'):
        qa_id_names[r['id']].add(r.get('a', ''))
multi_name_ids = {oid: sorted(ns) for oid, ns in qa_id_names.items() if len(ns) > 1}
print(f'\nD_QA: OPR IDs with 2+ distinct names: {len(multi_name_ids)}')
for oid, names in sorted(multi_name_ids.items())[:10]:
    print(f'  {oid}: {names}')

# The real issue: computeAssocTable uses `name` as key for BOTH prod and qa.
# If D_PROD[a] != D_QA[a] for the same person, they create two entries.
# Check this overlap.
prod_name_set = set(r.get('a','') for r in prod if r.get('a'))
qa_name_set   = set(r.get('a','') for r in qa  if r.get('a'))
only_in_prod  = prod_name_set - qa_name_set
only_in_qa    = qa_name_set  - prod_name_set
both           = prod_name_set & qa_name_set

print(f'\nName overlap (D_PROD vs D_QA):')
print(f'  Names in both:       {len(both)}')
print(f'  Only in D_PROD:      {len(only_in_prod)}')
print(f'  Only in D_QA:        {len(only_in_qa)}')

# Check example names specifically
print('\nExample names in D_PROD vs D_QA:')
for name in EXAMPLES:
    in_p = name in prod_name_set
    in_q = name in qa_name_set
    print(f'  {name}: PROD={in_p} QA={in_q}')

# ── What would OPR-ID keying look like? ─────────────────────
print('\n' + '=' * 70)
print('OPR-ID KEYED SIMULATION')
print('=' * 70)

# Simulate: group D_PROD by OPR ID via D_DIM lookup
# (D_PROD has no id field — name is the only join to dim)
dim_name_to_id = {d['n']: d['id'] for d in dim}
print(f'D_DIM name->id entries: {len(dim_name_to_id)}')

prod_names_no_id = [n for n in prod_name_set if n not in dim_name_to_id]
print(f'D_PROD names with no D_DIM entry: {len(prod_names_no_id)} (sample: {sorted(prod_names_no_id)[:5]})')

# How many unique rows would OPR-ID keying produce vs name keying?
id_keyed = set()
name_keyed = set()
for r in prod:
    if r.get('a'):
        name_keyed.add(r['a'])
        oid = dim_name_to_id.get(r['a'])
        id_keyed.add(oid if oid else r['a'])   # fall back to name if no id

print(f'D_PROD unique entries: name-keyed={len(name_keyed)}, id-keyed={len(id_keyed)}')
