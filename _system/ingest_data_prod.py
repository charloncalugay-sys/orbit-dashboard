"""
ingest_data_prod.py
====================
Builds D_PROD_EXT from data_prod.xlsx and injects it into orbit-data.js.

Business rules implemented
--------------------------
Rule 1 — D&I exclusion:
    Skip all rows where Function = 'Disputes and Intakes' or 'Disputes & Intakes'.
    Existing D_PROD remains authoritative and is never touched.

Rule 2 — ITS Host exclusion:
    Skip all rows where Function = 'ITS Host'.

Rule 3 — Cash Control actual:
    act = Prod Count + Review + Rework (CC)
    The act formula uses the SOURCE function tag from data_prod, not the
    D_DIM function, so a Cash Control source row always applies Rule 3
    regardless of where the associate currently sits in the roster.

Rule 4 — All other functions actual:
    act = Prod Count

Rule 5 — Target handling:
    tgt = None when Prod Target is None, blank, OR zero.
    tgt = round(Prod Target, 2) only when Prod Target > 0.

Rule 6 — Roster join (OPR ID) + CURRENT-FUNCTION ATTRIBUTION:
    name    = D_DIM[id].n  (roster-canonical)
    manager = D_DIM[id].am (current TL)
    fn      = D_DIM[id].fn (CURRENT function — roster-authoritative)

    For unmatched IDs (not yet in D_DIM):
    name    = title_case(data_prod name)
    manager = ''
    fn      = source function from data_prod column

    Architectural note — why D_DIM fn, not source fn:
    Dashboard populations must reflect current organisational ownership.
    An associate who worked IQT and is now in NON-COB should have ALL their
    production attributed to NON-COB on the NON-COB dashboard.  Historical
    function movement is preserved in D_HIST / Associate Records / Timeline
    View but never alters dashboard attribution.

Rule 7 — Week label:
    'Week N' where N = week-of-month (Monday-anchored, same as D_PROD).

Output schema (identical to D_PROD for drop-in compatibility)
--------------------------------------------------------------
{fn, m, a, id, ym, w, d, act, tgt}

   fn  — CURRENT function slug from D_DIM (roster-authoritative)
   m   — current AM / TL (from D_DIM[am]) or '' for unmatched
   a   — roster-canonical associate name (or title-cased fallback)
   id  — OPR ID (Domain column)
   ym  — 'YYYY-MM'
   w   — 'Week N'
   d   — 'M/D/YYYY'  (matches D_PROD date format exactly)
   act — numeric (int if whole, float rounded to 2dp otherwise)
   tgt — numeric > 0, or null
"""

import openpyxl, json, re, sys
from datetime import datetime
from collections import defaultdict

# ── Paths ──────────────────────────────────────────────────────────────
XLSX_PATH     = r'C:\Users\AL70683\OneDrive - Elevance Health\IGNITE PROJECTS\ORBIT\data_prod.xlsx'
DATA_JS_PATH  = r'C:\Users\AL70683\OneDrive - Elevance Health\IGNITE PROJECTS\ORBIT\ORBIT DASH\orbit-data.js'

# ── Function mapping ────────────────────────────────────────────────────
SKIP_FNS = {'Disputes and Intakes', 'Disputes & Intakes', 'ITS Host'}

FN_SLUG = {
    'Cash Control':  'cash-control',
    'COB':           'cob',
    'Collections':   'collections',
    'Dispute Triage':'dispute-triage',
    'IQT':           'iqt',
    'NON COB':       'non-cob',
    'Prepay':        'prepay',
}

FN_DISPLAY = {v: k for k, v in FN_SLUG.items()}

# ── Helpers ────────────────────────────────────────────────────────────
def to_date_str(v):
    """Convert Excel datetime / string to M/D/YYYY (matches D_PROD format)."""
    if isinstance(v, datetime):
        return '%d/%d/%d' % (v.month, v.day, v.year)
    if isinstance(v, str) and v:
        try:
            dt = datetime.strptime(v[:10], '%Y-%m-%d')
            return '%d/%d/%d' % (dt.month, dt.day, dt.year)
        except ValueError:
            pass
    return ''

def to_ym(v):
    """Convert Excel datetime / string to YYYY-MM."""
    if isinstance(v, datetime):
        return v.strftime('%Y-%m')
    if isinstance(v, str) and len(v) >= 7:
        return v[:7]
    return ''

def week_of_month(v):
    """'Week N' — same algorithm as existing D_PROD (Monday-anchored)."""
    if isinstance(v, datetime):
        dt = v
    else:
        return ''
    first_weekday = dt.replace(day=1).weekday()   # 0 = Monday
    n = (dt.day + first_weekday - 1) // 7 + 1
    return 'Week %d' % n

def title_name(s):
    """Title-case a name string; handle ALL-CAPS gracefully."""
    if not s:
        return s
    s = s.strip()
    # If name contains any lowercase letter assume it's already properly cased
    if any(c.islower() for c in s):
        return s
    # ALL-CAPS: apply title case
    parts = []
    for word in s.split():
        if len(word) > 1 and word[0].isalpha():
            parts.append(word[0].upper() + word[1:].lower())
        else:
            parts.append(word)
    return ' '.join(parts)

def to_num(v):
    """Return a clean number: int if whole, else float rounded 2dp."""
    if v is None:
        return 0
    n = float(v)
    return int(n) if n == int(n) else round(n, 2)

def tgt_val(v):
    """Return target value or None per Rule 5."""
    if v is None or v == 0:
        return None
    n = float(v)
    if n <= 0:
        return None
    return int(n) if n == int(n) else round(n, 2)

# ── Load D_DIM from orbit-data.js ──────────────────────────────────────
print('Loading orbit-data.js...')
js_src = open(DATA_JS_PATH, encoding='utf-8').read()
dim    = json.loads(re.search(r'const D_DIM=(\[.*?\]);', js_src, re.S).group(1))
dim_by_id = {d['id']: d for d in dim}
print('  D_DIM entries: %d' % len(dim_by_id))

# ── Load data_prod.xlsx ───────────────────────────────────────────────
print('Loading data_prod.xlsx (may take a moment)...')
try:
    wb = openpyxl.load_workbook(XLSX_PATH, read_only=True, data_only=True)
except PermissionError:
    # Excel may have the file open — work from the temp copy
    import shutil, tempfile, os
    tmp = os.path.join(tempfile.gettempdir(), 'data_prod_ingest.xlsx')
    shutil.copy2(XLSX_PATH, tmp)
    wb = openpyxl.load_workbook(tmp, read_only=True, data_only=True)
    print('  (opened from temp copy)')

ws  = wb['Sheet1']
hdr = None
raw = []
for row in ws.iter_rows(values_only=True):
    if hdr is None:
        hdr = row
        continue
    raw.append(row)
print('  Source rows: %d' % len(raw))

col = {h: i for i, h in enumerate(hdr)}
F, A, D_COL = col['Function'], col['Associate'], col['Domain']
DT, PC, RR, PT = col['Date'], col['Prod Count'], col['Review + Rework (CC)'], col['Prod Target']

# ── Build D_PROD_EXT ──────────────────────────────────────────────────
print('Building D_PROD_EXT...')
ext_rows   = []
skip_count = 0
unmatched_ids = defaultdict(set)   # fn -> set of unmatched IDs

for r in raw:
    fn_raw = r[F]

    # Rules 1 & 2 — skip D&I and ITS Host
    if fn_raw in SKIP_FNS:
        skip_count += 1
        continue
    fn = FN_SLUG.get(fn_raw)
    if fn is None:
        skip_count += 1
        continue

    oid  = r[D_COL]
    dt   = r[DT]
    prod = to_num(r[PC])
    rr   = to_num(r[RR])
    tgt  = tgt_val(r[PT])

    # Rule 3 — Cash Control actual includes Review+Rework.
    # Use SOURCE fn for the act formula: a CC source row applies Rule 3
    # regardless of where the associate now sits in the roster.
    act = prod + rr if fn == 'cash-control' else prod

    # Rule 6 — roster join with CURRENT-FUNCTION attribution (D_DIM is authoritative).
    # fn_dim = D_DIM[id].fn  → the associate's CURRENT function assignment.
    # Production rows follow the associate to their current function so every
    # dashboard shows only the people presently assigned to that function.
    # Unmatched IDs (not yet in D_DIM) retain the source function as a fallback.
    dim_entry = dim_by_id.get(oid) if oid else None
    if dim_entry:
        name    = dim_entry['n']
        manager = dim_entry.get('am') or dim_entry.get('mgr') or ''
        fn_dim  = dim_entry['fn']   # CURRENT function — roster-authoritative
    else:
        name    = title_name(r[A])
        manager = ''
        fn_dim  = fn                # fallback: source function from data_prod
        if oid:
            unmatched_ids[fn].add((oid, name))

    date_str = to_date_str(dt)
    ym       = to_ym(dt)
    week     = week_of_month(dt)

    if not date_str or not ym:
        continue   # skip rows with unparseable dates

    ext_rows.append({
        'fn':  fn_dim,
        'm':   manager,
        'a':   name,
        'id':  oid or '',
        'ym':  ym,
        'w':   week,
        'd':   date_str,
        'act': act,
        'tgt': tgt,
    })

print('  Rows built:  %d' % len(ext_rows))
print('  Rows skipped (D&I / ITS Host / unknown fn): %d' % skip_count)

# ── Validation Report ─────────────────────────────────────────────────
print()
print('=' * 76)
print('D_PROD_EXT — VALIDATION REPORT')
print('=' * 76)

FNS_ORDER = ['cash-control','cob','collections','dispute-triage','iqt','non-cob','prepay']

by_fn = defaultdict(list)
for r in ext_rows:
    by_fn[r['fn']].append(r)

print()
print('%-18s %10s %10s %22s %12s %12s' % (
    'Function', 'Associates', 'Rows', 'Date Range', 'With Target', 'No Target'))
print('-' * 76)

totals = dict(rows=0, assoc=0, with_tgt=0, no_tgt=0)
fn_stats = {}
for fn in FNS_ORDER:
    rows = by_fn.get(fn, [])
    names   = sorted(set(r['a'] for r in rows if r['a']))
    dates   = sorted(set(r['d'] for r in rows if r['d']))
    # Sort dates properly (they're M/D/YYYY)
    def parse_d(s):
        p = s.split('/'); return (int(p[2]), int(p[0]), int(p[1]))
    dates_sorted = sorted(set(r['d'] for r in rows if r['d']), key=parse_d)
    with_tgt = sum(1 for r in rows if r['tgt'] is not None)
    no_tgt   = len(rows) - with_tgt
    dr = ('%s → %s' % (dates_sorted[0], dates_sorted[-1])) if dates_sorted else '—'
    print('%-18s %10d %10d %22s %12d %12d' % (
        FN_DISPLAY.get(fn, fn), len(names), len(rows), dr, with_tgt, no_tgt))
    totals['rows']     += len(rows)
    totals['assoc']    += len(names)
    totals['with_tgt'] += with_tgt
    totals['no_tgt']   += no_tgt
    fn_stats[fn] = dict(rows=len(rows), names=names, with_tgt=with_tgt, no_tgt=no_tgt)

print('-' * 76)
print('%-18s %10s %10d %22s %12d %12d' % (
    'TOTAL', '—', totals['rows'], '—', totals['with_tgt'], totals['no_tgt']))

# Unmatched ID report
print()
print('=' * 76)
print('UNMATCHED IDS (not in D_DIM — name sourced from data_prod, title-cased)')
print('=' * 76)
for fn in FNS_ORDER:
    um = unmatched_ids.get(fn, set())
    if not um: continue
    print()
    print('  %s (%d):' % (FN_DISPLAY.get(fn, fn), len(um)))
    for oid, name in sorted(um):
        print('    %-12s  %s' % (oid, name))

# act=0 rows summary
print()
print('=' * 76)
print('ZERO-PRODUCTION ROWS (act=0, included in D_PROD_EXT as absence days)')
print('=' * 76)
for fn in FNS_ORDER:
    rows = by_fn.get(fn, [])
    zeros = sum(1 for r in rows if r['act'] == 0)
    total = len(rows)
    pct   = 100 * zeros / total if total else 0
    print('  %-18s  zero=%d / %d  (%.1f%%)' % (
        FN_DISPLAY.get(fn, fn), zeros, total, pct))

# Cash Control RR contribution
cc_rows = by_fn.get('cash-control', [])
cc_rr_rows = [r for r in raw if r[F] == 'Cash Control' and to_num(r[RR]) > 0]
print()
print('=' * 76)
print('CASH CONTROL — Rule 3 (act = Prod Count + Review+Rework(CC))')
print('=' * 76)
print('  Rows with RR > 0: %d' % len(cc_rr_rows))
if cc_rr_rows:
    rr_vals = [to_num(r[RR]) for r in cc_rr_rows]
    print('  RR range: %.0f – %.0f  |  total RR contribution: %.0f' % (
        min(rr_vals), max(rr_vals), sum(rr_vals)))

# ── Inject D_PROD_EXT into orbit-data.js ──────────────────────────────
print()
print('=' * 76)
print('INJECTING D_PROD_EXT INTO ORBIT-DATA.JS')
print('=' * 76)

json_str = json.dumps(ext_rows, ensure_ascii=False, separators=(',', ':'))

# Check if already exists
if 'const D_PROD_EXT=' in js_src:
    print('  Replacing existing D_PROD_EXT...')
    new_js = re.sub(
        r'const D_PROD_EXT=\[.*?\];',
        'const D_PROD_EXT=' + json_str + ';',
        js_src,
        flags=re.S
    )
else:
    print('  Inserting D_PROD_EXT after D_PROD...')
    # Insert immediately after the closing of D_PROD
    insert_after = re.search(r'(const D_PROD=\[.*?\];)', js_src, re.S)
    if not insert_after:
        print('ERROR: Could not locate D_PROD in orbit-data.js')
        sys.exit(1)
    end_pos = insert_after.end()
    new_js = (
        js_src[:end_pos]
        + '\nconst D_PROD_EXT=' + json_str + ';\n'
        + js_src[end_pos:]
    )

with open(DATA_JS_PATH, 'w', encoding='utf-8') as f:
    f.write(new_js)

print('  Written: %d D_PROD_EXT rows to orbit-data.js' % len(ext_rows))
print('  File size: %.1f MB' % (len(new_js.encode('utf-8')) / 1024 / 1024))
print()
print('Done. Review the validation report above, then proceed to wire')
print('D_PROD_EXT into orbit-app.js when ready.')
