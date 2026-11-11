# One-off enrichment: append D_FN / D_DIM / D_FN_META / D_HIST to orbit-data.js
# Mirrors the logic baked into Refresh_ORBIT.ps1 (roster = function authority).
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

SYS = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.dirname(SYS)
ROSTER_CSV = os.path.join(SYS, 'roster_dump.csv')
PREV_CSV   = os.path.join(SYS, 'roster_prev.csv')
HIST_CSV   = os.path.join(SYS, 'assoc_history.csv')
DATA_JS    = os.path.join(DASH, 'orbit-data.js')

FN_KEYS = {
    'Cash Control': 'cash-control', 'COB': 'cob', 'Collections': 'collections',
    'DISPUTE TRIAGE': 'dispute-triage', 'Disputes and Intakes': 'disputes-intakes',
    'IQT': 'iqt', 'NON COB': 'non-cob', 'Prepay': 'prepay',
}
FN_ORDER = list(FN_KEYS.values())

# QA exists in the source QA platform for these functions but is not yet
# wired into the workbook's Fact_QA extract. Values = reported source-system
# audit volumes; state overridden to 'qa' when the extract shows no data.
FN_QA_SRC = {'cob': 1461, 'iqt': 1144, 'non-cob': 4012, 'prepay': 2194}

def norm(s): return (s or '').strip()

# ── roster -> D_FN + D_DIM ──────────────────────────────────
by_id, by_name, dim = {}, {}, []
for r in read_rows(ROSTER_CSV):
    rid, nm = norm(r['ASSOCIATE OPR ID']), norm(r['ASSOCIATES'])
    fn = FN_KEYS.get(norm(r['Function']))
    if not (rid and fn): continue
    by_id[rid] = fn
    if nm: by_name[nm] = fn
    dim.append({
        'id': rid, 'n': nm, 'fn': fn,
        'am': norm(r['Assistant Manager']), 'mgr': norm(r['Manager']),
        'pos': norm(r['POSITION']), 'tower': norm(r['TOWER']),
        'hire': norm(r['HIRE DATE']),
    })

# ── parse current orbit-data.js arrays for meta counts ──────
src = open(DATA_JS, encoding='utf-8').read()
def arr(name):
    m = re.search(r'const %s=(\[.*?\]);' % name, src, re.S)
    return json.loads(m.group(1)) if m else []
prod, qa = arr('D_PROD'), arr('D_QA')

# fn resolution mirror (id -> exact name -> unique-last+first-token)
last_idx = {}
for n, fn in by_name.items():
    last_idx.setdefault(n.split(',')[0].strip().lower(), []).append((n, fn))
def fn_of(r):
    if r.get('id') and r['id'] in by_id: return by_id[r['id']]
    nm = (r.get('a') or r.get('n') or '').strip()
    if nm in by_name: return by_name[nm]
    cands = last_idx.get(nm.split(',')[0].strip().lower())
    if cands and len(cands) == 1:
        tok  = (nm.split(',')[1].strip().split() or [''])[0] if ',' in nm else ''
        ctok = (cands[0][0].split(',')[1].strip().split() or [''])[0] if ',' in cands[0][0] else ''
        if tok and tok == ctok: return cands[0][1]
    return 'un'

# Production rows are D&I-tracker work by definition — they always score to
# Disputes & Intakes regardless of the associate's current roster function.
prod_c, qa_c = {k: 0 for k in FN_ORDER}, {k: 0 for k in FN_ORDER}
prod_c['disputes-intakes'] = len(prod)
for r in qa:
    k = fn_of(r)
    if k in qa_c: qa_c[k] += r.get('cnt') or 1

meta = []
for label, k in FN_KEYS.items():
    members = [d for d in dim if d['fn'] == k]
    p, q = prod_c[k], qa_c[k]
    q_src = FN_QA_SRC.get(k)
    state = 'full' if (p and q) else ('qa' if (q or q_src) else ('prod' if p else 'uc'))
    meta.append({
        'key': k, 'name': label, 'state': state,
        'prod': p, 'qa': q, 'qa_src': q_src, 'assoc': len(members),
        'ams': sorted({d['am'] for d in members if d['am']}),
        'mgrs': sorted({d['mgr'] for d in members if d['mgr']}),
    })

# ── associate movement history ──────────────────────────────
# Compare current roster vs roster_prev.csv snapshot; append any
# fn/am/mgr changes to assoc_history.csv, then emit D_HIST keyed by id.
HIST_FIELDS = {'fn': 'Function', 'am': 'Assistant Manager', 'mgr': 'Manager'}
hist = read_rows(HIST_CSV) if os.path.exists(HIST_CSV) else []
today = date.today().isoformat()
if os.path.exists(PREV_CSV):
    prev = {norm(r['ASSOCIATE OPR ID']): r for r in read_rows(PREV_CSV)}
    cur_by_id = {d['id']: d for d in dim}
    FIELD_TO_DIM = {'fn': 'fn', 'am': 'am', 'mgr': 'mgr'}
    for rid, d in cur_by_id.items():
        p = prev.get(rid)
        if not p: continue
        for fld, col in HIST_FIELDS.items():
            old = norm(p.get(col)); new = d[FIELD_TO_DIM[fld]]
            if fld == 'fn': old = FN_KEYS.get(old, old)   # prev stores labels; dim stores keys
            if old and new and old != new:
                hist.append({'id': rid, 'n': d['n'], 'field': fld,
                             'prev': old, 'until': today})
    # dedupe identical entries
    seen, dedup = set(), []
    for h in hist:
        t = (h['id'], h['field'], h['prev'], h['until'])
        if t not in seen: seen.add(t); dedup.append(h)
    hist = dedup

d_hist = {}
for h in hist:
    d_hist.setdefault(h['id'], {}).setdefault(h['field'], []).append(
        {'v': h['prev'], 'until': h['until']})

with open(HIST_CSV, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['id', 'n', 'field', 'prev', 'until'])
    w.writeheader(); w.writerows(hist)

# snapshot current roster for next-run diffing
with open(PREV_CSV, 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['ASSOCIATE OPR ID', 'ASSOCIATES', 'Assistant Manager',
                'Function', 'Manager', 'POSITION', 'TOWER', 'HIRE DATE'])
    for d in dim:
        w.writerow([d['id'], d['n'], d['am'], next(k for k, v in FN_KEYS.items() if v == d['fn']),
                    d['mgr'], d['pos'], d['tower'], d['hire']])

# ── append/replace constants in orbit-data.js ───────────────
src = re.sub(r'\n?const D_(FN|DIM|FN_META|HIST)=[^\n]*\n', '\n', src)
src += "const D_FN=%s;\n" % json.dumps({'byId': by_id, 'byName': by_name},
                                      ensure_ascii=False, separators=(',', ':'))
src += "const D_DIM=%s;\n" % json.dumps(dim, ensure_ascii=False, separators=(',', ':'))
src += "const D_FN_META=%s;\n" % json.dumps(meta, ensure_ascii=False, separators=(',', ':'))
src += "const D_HIST=%s;\n" % json.dumps(d_hist, ensure_ascii=False, separators=(',', ':'))
open(DATA_JS, 'w', encoding='utf-8').write(src)

print('D_FN ids:', len(by_id), '| names:', len(by_name))
for m in meta:
    print(' %-18s %-5s prod=%-6d qa=%-5d assoc=%-3d' %
          (m['key'], m['state'], m['prod'], m['qa'], m['assoc']))
print('history entries:', len(hist))
