"""
Validate D_QA enrichment quality after enrich_data.py runs.
Checks:
  1. All resolved rows have fn/am/mgr/pos/tower from roster
  2. Names match official roster exactly
  3. Duplicate identity collapse (same person, different raw names -> one canonical name)
  4. Unclassified breakdown
"""
import json, re, csv, os

SYS  = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.dirname(SYS)

src = open(os.path.join(DASH, 'orbit-data.js'), encoding='utf-8').read()
def arr(name):
    m = re.search(r'const %s=(\[.*?\]);' % name, src, re.S)
    return json.loads(m.group(1)) if m else []

qa  = arr('D_QA')
dim = arr('D_DIM')
dim_map = {d['id']: d for d in dim}

# Load roster for ground-truth check
roster = {}
for r in csv.DictReader(open(os.path.join(SYS, 'roster_dump.csv'), encoding='cp1252')):
    rid = r['ASSOCIATE OPR ID'].strip()
    if rid: roster[rid] = r

# 1. Enrichment completeness
resolved   = [r for r in qa if r.get('fn') and r['fn'] != 'un']
unresolved = [r for r in qa if not r.get('fn') or r['fn'] == 'un']
print('=== Enrichment completeness ===')
print(f'  Resolved (OPR ID in roster): {len(resolved):,} / {len(qa):,}')
print(f'  Unclassified (OPR ID not on roster): {len(unresolved):,}')
uniq_un = set(r['id'] for r in unresolved)
print(f'  Unique unclassified OPR IDs: {len(uniq_un)}')

# 2. Name quality — resolved rows should have official roster name
name_ok, name_mismatch = 0, []
for r in resolved:
    ros = roster.get(r['id'])
    if ros:
        expected = ros['ASSOCIATES'].strip()
        actual   = r.get('a', '')
        if actual == expected:
            name_ok += 1
        else:
            name_mismatch.append((r['id'], actual, expected))
print('\n=== Name quality (resolved rows) ===')
print(f'  Exact match to roster: {name_ok:,}')
print(f'  Mismatch: {len(name_mismatch)}')
for m in name_mismatch[:5]:
    print(f'    {m[0]}: got {m[1]!r} expected {m[2]!r}')

# 3. Duplicate identity collapse
# Count unique (id, name) combos before and after enrichment
names_in_resolved = {}
for r in resolved:
    names_in_resolved.setdefault(r['id'], set()).add(r.get('a',''))
multi_name = {rid: nms for rid, nms in names_in_resolved.items() if len(nms) > 1}
print('\n=== Duplicate identity collapse ===')
print(f'  OPR IDs with multiple names in D_QA: {len(multi_name)}')
for rid, nms in sorted(multi_name.items())[:5]:
    print(f'    {rid}: {nms}')

# 4. Roster fields on enriched rows
missing_fields = []
for r in resolved[:100]:
    for fld in ('fn', 'am', 'mgr', 'pos', 'tower'):
        if fld not in r:
            missing_fields.append((r['id'], fld))
print('\n=== Roster fields on enriched rows (first 100) ===')
print(f'  Missing fields: {len(missing_fields)}' if missing_fields else '  All fields present.')

# 5. Function distribution
from collections import Counter
fn_dist = Counter(r.get('fn', 'un') for r in qa)
print('\n=== Function distribution ===')
for fn, cnt in sorted(fn_dist.items(), key=lambda x: -x[1]):
    print(f'  {fn:25s}: {cnt:5,} rows')

print('\nDone.')
