import csv, json, re, os
from collections import defaultdict

SYS  = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.dirname(SYS)

roster = {}
for r in csv.DictReader(open(os.path.join(SYS, 'roster_dump.csv'), encoding='cp1252')):
    rid = r['ASSOCIATE OPR ID'].strip()
    if rid:
        roster[rid] = r

src = open(os.path.join(DASH, 'orbit-data.js'), encoding='utf-8').read()
def arr(name):
    m = re.search(r'const %s=(\[.*?\]);' % name, src, re.S)
    return json.loads(m.group(1)) if m else []

qa = arr('D_QA')

# Check the example IDs
CHECK = ['AL86935', 'AL86929', 'AL69201', 'AL87274', 'AL86936', 'AL86930']
print('=== Roster lookup for duplicate-example IDs ===')
for oid in CHECK:
    if oid in roster:
        r = roster[oid]
        print('  %s: IN roster | name=%r fn=%r' % (oid, r['ASSOCIATES'], r['Function']))
    else:
        print('  %s: NOT IN ROSTER' % oid)

# Check D_QA fn field for these IDs
print('\n=== D_QA fn field for these IDs ===')
for oid in CHECK:
    rows = [r for r in qa if r.get('id') == oid]
    fn_vals = set(r.get('fn', 'MISSING') for r in rows)
    print('  %s: D_QA fn values = %s | rows=%d' % (oid, fn_vals, len(rows)))

# The problem: fn='' means the enrichment didn't fire.
# Check how many D_QA rows have fn='' vs fn set
no_fn  = [r for r in qa if not r.get('fn')]
has_fn = [r for r in qa if r.get('fn')]
print('\n=== D_QA fn coverage ===')
print('  Rows with fn set:   %d' % len(has_fn))
print('  Rows with fn empty: %d' % len(no_fn))

# IDs in no_fn group — are they in roster?
no_fn_ids = set(r.get('id','') for r in no_fn)
in_roster  = [oid for oid in no_fn_ids if oid in roster]
not_roster = [oid for oid in no_fn_ids if oid not in roster]
print('  no-fn IDs in roster: %d | NOT in roster: %d' % (len(in_roster), len(not_roster)))
print('  sample in_roster (should have been enriched!): %s' % sorted(in_roster)[:10])

# How many unique names do the no_fn rows produce in the assocMap?
no_fn_names = set(r.get('a','') for r in no_fn if r.get('a'))
print('  no-fn unique names (= extra grid rows): %d' % len(no_fn_names))

# Spot check: what are the fn values for in_roster IDs in D_QA?
print('\n=== Spot check: D_QA rows for roster-matched IDs that got fn empty ===')
for oid in sorted(in_roster)[:5]:
    rows = [r for r in qa if r.get('id') == oid]
    names = set(r.get('a','') for r in rows)
    fn_vals = set(r.get('fn', 'MISSING') for r in rows)
    ros_name = roster[oid]['ASSOCIATES']
    print('  %s: D_QA names=%s fn=%s roster_name=%r' % (oid, sorted(names), fn_vals, ros_name))
