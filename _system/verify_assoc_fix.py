import re

src = open(
    r'C:\Users\AL70683\OneDrive - Elevance Health\IGNITE PROJECTS\ORBIT\ORBIT DASH\orbit-app.js',
    encoding='utf-8'
).read()

checks = [
    ('DD rebuildAssocSelect: Q() primary source',
     "const qaRows = Q().filter(r =>\n      (S.month   === 'all' || r.d.startsWith(S.month)) &&\n      (S.manager === 'all' || r.m === S.manager)\n    );\n    const prodRows = P().filter(r =>\n      (S.month   === 'all' || r.ym === S.month) &&\n      (S.manager === 'all' || r.m  === S.manager)\n    );\n    const fromData = [...new Set([...qaRows.map(r => r.a), ...prodRows.map(r => r.a)].filter(Boolean))].sort();\n    // Fallback to roster when function has no data rows yet\n    const assocs = fromData.length\n      ? fromData\n      : DIM_FN().map(d => d.n).filter(Boolean).sort();"),
    ('MP rebuildAssocSelect: Q() primary source',
     "const qaRows = Q().filter(r =>\n      (S.month   === 'all' || r.d.startsWith(S.month)) &&\n      (S.manager === 'all' || r.m === S.manager)\n    );\n    const prodRows = P().filter(r =>\n      (S.month   === 'all' || r.ym === S.month) &&\n      (S.manager === 'all' || r.m  === S.manager)\n    );\n    const fromData = [...new Set([...qaRows.map(r => r.a), ...prodRows.map(r => r.a)].filter(Boolean))].sort();\n    // Fallback to roster when function has no rows yet\n    const assocs = fromData.length\n      ? fromData\n      : DIM_FN().map(d => d.n).filter(Boolean).sort();"),
    ('DD reset() calls rebuildAssocSelect',
     'rebuildAssocSelect();   // repopulate from Q()/DIM_FN() for the new function\n  }\n\n  function render() {'),
    ('MP reset() calls rebuildAssocSelect',
     'rebuildAssocSelect();   // repopulate from Q()/DIM_FN() for the new function\n  }\n\n  /* \u2500\u2500 Filter controls'),
    ('DD rebuildAssocSelect: DIM_FN() fallback',
     "DIM_FN().map(d => d.n).filter(Boolean).sort();\n    sel.innerHTML = '<option value=\"all\">All Associates</option>';\n    assocs.forEach(a => {\n      const opt = document.createElement('option');"),
    ('MP rebuildAssocSelect: DIM_FN() fallback',
     "DIM_FN().map(d => d.n).filter(Boolean).sort();\n    sel.innerHTML = '<option value=\"all\">All Associates</option>';\n    assocs.forEach(a => {\n      const o = document.createElement('option');"),
]

print('=== Associate dropdown fix verification ===')
all_ok = True
for label, needle in checks:
    found = needle in src
    status = 'OK  ' if found else 'FAIL'
    print('  %s  %s' % (status, label))
    if not found:
        all_ok = False
        # Show first 40 chars of needle to help locate
        idx = src.find(needle[:40])
        print('       (looking for: %r...)' % needle[:60])
        if idx >= 0:
            print('       found partial at line ~%d' % (src[:idx].count('\n') + 1))

print()
print('Result:', 'ALL PASS' if all_ok else 'SOME FAILED')
