r"""
ingest_data_daily.py
====================
Incrementally appends daily production rows from the ORBIT DAILY PROD VIRT
landing folder into D_PROD_EXT in orbit-data.js.

Design: immutable archive
-------------------------
  * Watermark = latest Shift Date already stored in D_PROD_EXT (per run,
    recomputed from orbit-data.js).
  * Rows with Shift Date <= watermark are skipped -- history is never
    rewritten.  No correction mode (intentionally deferred).
  * Dedup key = (OPR ID, Shift Date, Function).  This guards against
    ingesting the same file twice even if dates are within the window.

Source
------
  Folder : ORBIT DAILY PROD VIRT\*.xlsx
  Sheet  : Sheet1 ONLY (Nov_16 and MTD are summary pivots -- ignored).
  Columns bind BY POSITION (A-I) with a header sanity warning:

      A  Department / Function        (payment_integrity[r_dept])
      B  Manager                      (payment_integrity[r_asst_mgr])
      C  Associate Name               (payment_integrity[r_name])
      D  OPR ID                       (payment_integrity[r_domain])
      E  Shift Date                   (payment_integrity[shift_date])
      F  Prod Count                   ([Sumcpt_prod_count])
      G  Review + Rework              ([Sumcpt_prod_count_review_rework])
      H  Target                       ([Sumcpt_prod_internal_target])
      I  AHT                          (unused -- reserved)

Business rules (identical to ingest_data_prod.py)
-------------------------------------------------
  * Skip functions: Disputes and Intakes / Disputes & Intakes / ITS Host
    (D&I prod stays authoritative on the D_PROD PivotTable path).
  * Cash Control: act = F + G.  All others: act = F.
  * tgt = null when H is blank/None/<=0, else rounded numeric.
  * Roster join via D_DIM (OPR ID): canonical name, current-AM manager,
    CURRENT function attribution.  Unmatched IDs keep source name
    (title-cased) and source function.
  * Week label: 'Week N' Monday-anchored, same algorithm as D_PROD.
  * Date formats: d = 'M/D/YYYY', ym = 'YYYY-MM'.

After appending
---------------
  * Rewrites const D_PROD_EXT=[...] in place inside orbit-data.js.
  * Patches D_FN_META states (same logic as ingest_data_prod.py):
    any function with prod rows becomes 'full' (qa>0) or 'prod'.

Report
------
  Watermark, Rows Read, Rows Added, Rows Skipped (by reason),
  Latest Date Ingested, per-file breakdown.
"""

import openpyxl, json, re, os, sys, hashlib
from datetime import datetime, date
from collections import Counter, defaultdict

# ── Paths ────────────────────────────────────────────────────────────
SYS          = os.path.dirname(os.path.abspath(__file__))
DAILY_DIR    = os.path.join(os.path.dirname(SYS), 'ORBIT DAILY PROD VIRT')
DATA_JS_PATH = os.path.join(os.path.dirname(SYS), 'orbit-data.js')

SHEET = 'Sheet1'          # only this sheet is real per-day data
SKIP_SHEETS_NOTE = 'Nov_16 / MTD are summary pivots -- ignored by design'

SKIP_FNS = {'Disputes and Intakes', 'Disputes & Intakes', 'ITS Host', 'Total', ''}
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

# ── Helpers (mirrors ingest_data_prod.py) ────────────────────────────
def to_date_str(v):
    if isinstance(v, datetime):
        return '%d/%d/%d' % (v.month, v.day, v.year)
    return ''

def to_ym(v):
    if isinstance(v, datetime):
        return v.strftime('%Y-%m')
    return ''

def week_of_month(v):
    if not isinstance(v, datetime):
        return ''
    first_weekday = v.replace(day=1).weekday()
    return 'Week %d' % ((v.day + first_weekday - 1) // 7 + 1)

def title_name(s):
    if not s:
        return s
    s = s.strip()
    if any(c.islower() for c in s):
        return s
    parts = []
    for word in s.split():
        if len(word) > 1 and word[0].isalpha():
            parts.append(word[0].upper() + word[1:].lower())
        else:
            parts.append(word)
    return ' '.join(parts)

def to_num(v):
    if v is None:
        return 0
    n = float(v)
    return int(n) if n == int(n) else round(n, 2)

def tgt_val(v):
    if v is None:
        return None
    n = float(v)
    if n <= 0:
        return None
    return int(n) if n == int(n) else round(n, 2)

def parse_d(s):
    p = s.split('/')
    return date(int(p[2]), int(p[0]), int(p[1]))

# ── Load current orbit-data.js ───────────────────────────────────────
print('Loading orbit-data.js...')
js_src = open(DATA_JS_PATH, encoding='utf-8').read()

def arr(name):
    m = re.search(r'const %s=(\[.*?\]);' % name, js_src, re.S)
    return json.loads(m.group(1)) if m else []

dim      = arr('D_DIM')
dim_by_id = {d['id']: d for d in dim}
ext      = arr('D_PROD_EXT')
print('  D_DIM entries: %d | D_PROD_EXT rows: %d' % (len(dim_by_id), len(ext)))

# ── Watermark + existing dedup key set ───────────────────────────────
existing_keys = set()
watermark = None
for r in ext:
    try:
        dd = parse_d(r['d'])
    except Exception:
        continue
    existing_keys.add((r.get('id', ''), dd, r.get('fn', '')))
    if watermark is None or dd > watermark:
        watermark = dd

print('  Watermark (latest date in D_PROD_EXT): %s' % watermark)
print('  Existing dedup keys: %d' % len(existing_keys))

# ── Scan daily landing folder ────────────────────────────────────────
if not os.path.isdir(DAILY_DIR):
    print('[ABORT] Landing folder not found: %s' % DAILY_DIR)
    sys.exit(1)

xlsx_files = sorted(f for f in os.listdir(DAILY_DIR)
                    if f.lower().endswith('.xlsx') and not f.startswith('~$'))
print('\nDaily files found: %d' % len(xlsx_files))
for f in xlsx_files:
    print('  %s' % f)

# ── Ingest ───────────────────────────────────────────────────────────
rows_read       = 0
rows_added      = 0
rows_skip_old   = 0     # <= watermark
rows_skip_dup   = 0     # dedup key already present
rows_skip_fn    = Counter()   # excluded/unknown function
rows_skip_bad   = 0     # missing OPR ID or unparsable date
latest_ingested = None
per_file        = {}

new_rows = []

for fname in xlsx_files:
    fp = os.path.join(DAILY_DIR, fname)
    file_added = 0
    wb = openpyxl.load_workbook(fp, read_only=True, data_only=True)
    if SHEET not in wb.sheetnames:
        print('  [WARN] %s has no Sheet1 -- skipped (%s)' % (fname, wb.sheetnames))
        wb.close()
        continue
    ws = wb[SHEET]
    it = ws.iter_rows(values_only=True)
    hdr = next(it, None)
    # Header sanity check (positional contract A-I)
    if hdr and 'shift_date' not in str(hdr[4] or '').lower():
        print('  [WARN] %s header col E is %r -- expected shift_date. '
              'Positional binding still applied; verify column drift!' % (fname, hdr[4]))
    for r in it:
        if r is None or len(r) < 6:
            continue
        rows_read += 1
        fn_raw = str(r[0]).strip() if r[0] else ''
        if fn_raw in SKIP_FNS or fn_raw not in FN_SLUG:
            rows_skip_fn[fn_raw or '(blank)'] += 1
            continue
        oid = str(r[3]).strip() if r[3] else ''
        d   = r[4]
        if not isinstance(d, datetime) or not oid:
            rows_skip_bad += 1
            continue
        dd = d.date()

        # Rule: append ONLY rows newer than watermark
        if dd <= watermark:
            rows_skip_old += 1
            continue
        key = (oid, dd, FN_SLUG[fn_raw])
        if key in existing_keys:
            rows_skip_dup += 1
            continue

        prod = to_num(r[5])
        rr   = to_num(r[6])
        tgt  = tgt_val(r[7])
        act  = prod + rr if FN_SLUG[fn_raw] == 'cash-control' else prod

        dim_entry = dim_by_id.get(oid)
        if dim_entry:
            name    = dim_entry['n']
            manager = dim_entry.get('am') or dim_entry.get('mgr') or ''
            fn_dim  = dim_entry['fn']
        else:
            name    = title_name(r[2])
            manager = ''
            fn_dim  = FN_SLUG[fn_raw]

        new_rows.append({
            'fn':  fn_dim,
            'm':   manager,
            'a':   name,
            'id':  oid,
            'ym':  to_ym(d),
            'w':   week_of_month(d),
            'd':   to_date_str(d),
            'act': act,
            'tgt': tgt,
        })
        existing_keys.add(key)
        rows_added += 1
        file_added += 1
        if latest_ingested is None or dd > latest_ingested:
            latest_ingested = dd
    wb.close()
    per_file[fname] = file_added

# ── Write D_PROD_EXT back ────────────────────────────────────────────
print()
print('=' * 76)
print('DAILY INGEST REPORT')
print('=' * 76)
print('  Watermark (D_PROD_EXT latest date) : %s' % watermark)
print('  Rows read                          : %d' % rows_read)
print('  Rows added                         : %d' % rows_added)
print('  Rows skipped -- <= watermark       : %d' % rows_skip_old)
print('  Rows skipped -- duplicate key      : %d' % rows_skip_dup)
print('  Rows skipped -- excluded function  : %d  %s' % (sum(rows_skip_fn.values()), dict(rows_skip_fn)))
print('  Rows skipped -- bad/missing fields : %d' % rows_skip_bad)
print('  Latest date ingested               : %s' % latest_ingested)
print()
print('  Per-file:')
for f, c in per_file.items():
    print('    %-70s +%d rows' % (f, c))

if rows_added == 0:
    print('\n  Nothing to append -- D_PROD_EXT already current.')
else:
    ext_all = ext + new_rows
    json_str = json.dumps(ext_all, ensure_ascii=False, separators=(',', ':'))
    if 'const D_PROD_EXT=' in js_src:
        new_js = re.sub(r'const D_PROD_EXT=\[.*?\];',
                        'const D_PROD_EXT=' + json_str + ';', js_src, flags=re.S)
    else:
        ins = re.search(r'(const D_PROD=\[.*?\];)', js_src, re.S)
        if not ins:
            print('ERROR: could not locate D_PROD in orbit-data.js'); sys.exit(1)
        new_js = js_src[:ins.end()] + '\nconst D_PROD_EXT=' + json_str + ';\n' + js_src[ins.end():]
    with open(DATA_JS_PATH, 'w', encoding='utf-8') as f:
        f.write(new_js)
    print('\n  D_PROD_EXT updated: %d -> %d rows' % (len(ext), len(ext_all)))

    # Per-function append summary
    by_fn = Counter(r['fn'] for r in new_rows)
    for fn, c in sorted(by_fn.items(), key=lambda x: -x[1]):
        print('    %-16s +%d' % (fn, c))

# ── Patch D_FN_META ──────────────────────────────────────────────────
print()
print('=' * 76)
print('PATCHING D_FN_META STATES')
print('=' * 76)
js_now  = open(DATA_JS_PATH, encoding='utf-8').read()
ext_now = json.loads(re.search(r'const D_PROD_EXT=(\[.*?\]);', js_now, re.S).group(1))
ext_counts = Counter(r['fn'] for r in ext_now)

meta_m = re.search(r'const D_FN_META=(\[.*?\]);', js_now, re.S)
if not meta_m:
    print('  [WARN] D_FN_META not found -- skipping badge patch.')
else:
    meta = json.loads(meta_m.group(1))
    changed = 0
    for entry in meta:
        k = entry['key']
        if k == 'disputes-intakes':
            continue
        ext_p = ext_counts.get(k, 0)
        if ext_p == 0:
            continue
        new_state = 'full' if entry.get('qa', 0) or entry.get('qa_src') else 'prod'
        if entry['state'] != new_state:
            print('  %-20s %s -> %s (%d prod rows)' % (k, entry['state'], new_state, ext_p))
            entry['state'] = new_state
            changed += 1
        entry['prod'] = ext_p
    if changed == 0:
        print('  All D_FN_META states already correct.')
    patched = json.dumps(meta, ensure_ascii=False, separators=(',', ':'))
    js_now = re.sub(r'const D_FN_META=\[.*?\];',
                    'const D_FN_META=' + patched + ';', js_now, flags=re.S)
    with open(DATA_JS_PATH, 'w', encoding='utf-8') as f:
        f.write(js_now)
    print()
    print('  Final states:')
    for entry in meta:
        print('    %-20s %-6s prod=%-7d qa=%-6d' % (
            entry['key'], entry['state'], entry.get('prod', 0), entry.get('qa', 0)))

print('\nDone.')
