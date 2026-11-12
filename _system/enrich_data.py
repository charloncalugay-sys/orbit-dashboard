# Enrichment: append D_FN / D_DIM / D_FN_META / D_HIST to orbit-data.js
# Roster is the AUTHORITATIVE identity source.
# Join hierarchy per record (D_QA and D_PROD):
#   1. ASSOCIATE OPR ID  (primary — matches 'id' field emitted by Refresh_ORBIT.ps1)
#   2. Normalized Name   (fallback — exact match, then unique-last + first-token)
#
# When an OPR ID resolves to a roster row, all display attributes (name, fn,
# am, mgr, pos, tower) are taken from the ROSTER, never the source system.
# D_QA rows are re-emitted with enriched fields so the JS layer can display
# official values without runtime lookups.

import csv, json, re, os, sys
from datetime import date

def read_rows(path):
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            with open(path, encoding=enc, newline='') as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    return []

SYS        = os.path.dirname(os.path.abspath(__file__))
DASH       = os.path.dirname(SYS)
ROSTER_CSV = os.path.join(SYS, 'roster_dump.csv')
PREV_CSV   = os.path.join(SYS, 'roster_prev.csv')
HIST_CSV   = os.path.join(SYS, 'assoc_history.csv')
DATA_JS    = os.path.join(DASH, 'orbit-data.js')

FN_KEYS = {
    'Cash Control':         'cash-control',
    'COB':                  'cob',
    'Collections':          'collections',
    'DISPUTE TRIAGE':       'dispute-triage',
    'Disputes and Intakes': 'disputes-intakes',
    'IQT':                  'iqt',
    'NON COB':              'non-cob',
    'Prepay':               'prepay',
}
FN_ORDER = list(FN_KEYS.values())

# QA source volumes for functions whose audit rows are in Fact_QA_AllFunctions
# but had zero extract rows in earlier pipeline runs; retained as a minimum
# for maturity-state detection only.
FN_QA_SRC = {'cob': 1461, 'iqt': 1144, 'non-cob': 4012, 'prepay': 2194}

def norm(s): return (s or '').strip()

# ── roster → D_FN + D_DIM ────────────────────────────────────
# Keyed on ASSOCIATE OPR ID (the authoritative join key).
# by_id  : OPR_ID -> fn key
# by_name: canonical roster name -> fn key  (fallback only)
# dim    : enriched associate list (D_DIM)
# dim_map: OPR_ID -> dim row (for fast lookup)
by_id, by_name, dim, dim_map = {}, {}, [], {}
for r in read_rows(ROSTER_CSV):
    rid = norm(r['ASSOCIATE OPR ID'])
    nm  = norm(r['ASSOCIATES'])
    fn  = FN_KEYS.get(norm(r['Function']))
    if not (rid and fn):
        continue
    d = {
        'id':    rid,
        'n':     nm,
        'fn':    fn,
        'am':    norm(r['Assistant Manager']),
        'mgr':   norm(r['Manager']),
        'pos':   norm(r['POSITION']),
        'tower': norm(r['TOWER']),
        'hire':  norm(r['HIRE DATE']),
    }
    by_id[rid]  = fn
    dim_map[rid] = d
    if nm:
        by_name[nm] = fn
    dim.append(d)

# Name-fallback indexes
last_idx = {}
for n, fn in by_name.items():
    last_idx.setdefault(n.split(',')[0].strip().lower(), []).append((n, fn))

def fn_of(r):
    """Resolve function key for a D_QA or D_PROD row using the join hierarchy."""
    # 1. OPR ID (most reliable)
    if r.get('id') and r['id'] in by_id:
        return by_id[r['id']]
    # 2. Exact roster name
    nm = norm(r.get('a') or r.get('n') or '')
    if nm in by_name:
        return by_name[nm]
    # 3. Unique last-name + matching first-token
    cands = last_idx.get(nm.split(',')[0].strip().lower())
    if cands and len(cands) == 1:
        tok  = (nm.split(',')[1].strip().split() or [''])[0] if ',' in nm else ''
        ctok = (cands[0][0].split(',')[1].strip().split() or [''])[0] if ',' in cands[0][0] else ''
        if tok and tok == ctok:
            return cands[0][1]
    return 'un'

# ── read current D_QA and D_PROD from orbit-data.js ──────────
src = open(DATA_JS, encoding='utf-8').read()
def arr(name):
    m = re.search(r'const %s=(\[.*?\]);' % name, src, re.S)
    return json.loads(m.group(1)) if m else []

prod = arr('D_PROD')
qa   = arr('D_QA')

# ── Enrich D_QA rows with roster data ────────────────────────
# For every QA row where the OPR ID exists in the roster:
#   - Replace 'a' (associate name) with the official roster name
#   - Add 'fn', 'am', 'mgr', 'pos', 'tower' from the roster row
# For unmatched IDs keep 'a' as-is and set fn='un'.
# This eliminates:
#   - Duplicate identities caused by name variants / maiden vs married names
#   - Unclassified records where OPR ID is on the roster but name didn't match
#   - Noise from QA-system name formatting inconsistencies
enriched_qa = []
n_resolved = 0
n_unmatched = 0
unmatched_ids = set()
for r in qa:
    rid = r.get('id', '')
    d   = dim_map.get(rid)
    if d:
        # Full roster resolution — authoritative values only
        enriched_qa.append({
            'm':     r['m'],
            'id':    rid,
            'a':     d['n'],     # official roster name (not QA-system name)
            'fn':    d['fn'],
            'am':    d['am'],
            'mgr':   d['mgr'],
            'pos':   d['pos'],
            'tower': d['tower'],
            'd':     r['d'],
            'cnt':   r['cnt'],
            'scr':   r['scr'],
        })
        n_resolved += 1
    else:
        # OPR ID not on roster — keep raw values, classify as unclassified
        enriched_qa.append({
            'm':   r['m'],
            'id':  rid,
            'a':   r.get('a', ''),
            'fn':  'un',
            'd':   r['d'],
            'cnt': r['cnt'],
            'scr': r['scr'],
        })
        n_unmatched += 1
        unmatched_ids.add(rid)

print('D_QA enrichment: %d resolved / %d unmatched (%d unique unmatched IDs)' % (
    n_resolved, n_unmatched, len(unmatched_ids)))
if unmatched_ids:
    print('  Unmatched OPR IDs:', sorted(unmatched_ids)[:20],
          ('...' if len(unmatched_ids) > 20 else ''))

# ── function counts ───────────────────────────────────────────
# Production rows are D&I-tracker work by definition.
prod_c = {k: 0 for k in FN_ORDER}
prod_c['disputes-intakes'] = len(prod)

# QA counts now use the pre-resolved 'fn' field on enriched rows.
qa_c = {k: 0 for k in FN_ORDER}
for r in enriched_qa:
    k = r.get('fn', 'un')
    if k in qa_c:
        qa_c[k] += r.get('cnt') or 1

meta = []
for label, k in FN_KEYS.items():
    members = [d for d in dim if d['fn'] == k]
    p, q    = prod_c[k], qa_c[k]
    q_src   = FN_QA_SRC.get(k)
    state   = 'full' if (p and q) else ('qa' if (q or q_src) else ('prod' if p else 'uc'))
    meta.append({
        'key':   k, 'name':  label, 'state': state,
        'prod':  p, 'qa':    q,     'qa_src': q_src,
        'assoc': len(members),
        'ams':   sorted({d['am']  for d in members if d['am']}),
        'mgrs':  sorted({d['mgr'] for d in members if d['mgr']}),
    })

# ── associate movement history ────────────────────────────────
HIST_FIELDS  = {'fn': 'Function', 'am': 'Assistant Manager', 'mgr': 'Manager'}
FIELD_TO_DIM = {'fn': 'fn', 'am': 'am', 'mgr': 'mgr'}
hist  = read_rows(HIST_CSV) if os.path.exists(HIST_CSV) else []
today = date.today().isoformat()

if os.path.exists(PREV_CSV):
    prev       = {norm(r['ASSOCIATE OPR ID']): r for r in read_rows(PREV_CSV)}
    cur_by_id  = {d['id']: d for d in dim}
    for rid, d in cur_by_id.items():
        p = prev.get(rid)
        if not p:
            continue
        for fld, col in HIST_FIELDS.items():
            old = norm(p.get(col))
            new = d[FIELD_TO_DIM[fld]]
            if fld == 'fn':
                old = FN_KEYS.get(old, old)   # prev stores labels; dim stores keys
            if old and new and old != new:
                hist.append({'id': rid, 'n': d['n'], 'field': fld,
                             'prev': old, 'until': today})
    seen, dedup = set(), []
    for h in hist:
        t = (h['id'], h['field'], h['prev'], h['until'])
        if t not in seen:
            seen.add(t)
            dedup.append(h)
    hist = dedup

d_hist = {}
for h in hist:
    d_hist.setdefault(h['id'], {}).setdefault(h['field'], []).append(
        {'v': h['prev'], 'until': h['until']})

with open(HIST_CSV, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['id', 'n', 'field', 'prev', 'until'])
    w.writeheader()
    w.writerows(hist)

# Snapshot current roster for next-run diffing
with open(PREV_CSV, 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['ASSOCIATE OPR ID', 'ASSOCIATES', 'Assistant Manager',
                'Function', 'Manager', 'POSITION', 'TOWER', 'HIRE DATE'])
    for d in dim:
        label = next(k for k, v in FN_KEYS.items() if v == d['fn'])
        w.writerow([d['id'], d['n'], d['am'], label,
                    d['mgr'], d['pos'], d['tower'], d['hire']])

# ── Write updated constants back to orbit-data.js ────────────
# Replace D_QA with the enriched version; also refresh D_FN/D_DIM/D_FN_META/D_HIST.
src = re.sub(r'\n?const D_(QA|FN|DIM|FN_META|HIST)=[^\n]*\n', '\n', src)
src += "const D_QA=%s;\n"      % json.dumps(enriched_qa, ensure_ascii=False, separators=(',', ':'))
src += "const D_FN=%s;\n"      % json.dumps({'byId': by_id, 'byName': by_name},
                                             ensure_ascii=False, separators=(',', ':'))
src += "const D_DIM=%s;\n"     % json.dumps(dim,  ensure_ascii=False, separators=(',', ':'))
src += "const D_FN_META=%s;\n" % json.dumps(meta, ensure_ascii=False, separators=(',', ':'))
src += "const D_HIST=%s;\n"    % json.dumps(d_hist, ensure_ascii=False, separators=(',', ':'))
open(DATA_JS, 'w', encoding='utf-8').write(src)

# ── Summary ───────────────────────────────────────────────────
print('D_FN ids:', len(by_id), '| names:', len(by_name))
print('D_QA total rows:', len(enriched_qa))
print()
print('%-20s %-5s %6s %6s %5s' % ('function', 'state', 'prod', 'qa', 'assoc'))
for m in meta:
    print('%-20s %-5s %6d %6d %5d' % (m['key'], m['state'], m['prod'], m['qa'], m['assoc']))
print('history entries:', len(hist))
