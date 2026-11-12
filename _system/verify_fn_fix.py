import re

src = open(
    r'C:\Users\AL70683\OneDrive - Elevance Health\IGNITE PROJECTS\ORBIT\ORBIT DASH\orbit-app.js',
    encoding='utf-8'
).read()

checks = [
    ('DD reset() defined',          'S.date    = \'\';'),
    ('DD exports reset',            'return { init, render, reset };\n})();\n\n/* \u2500\u2500 Attach DD init'),
    ('MP reset() defined',          'function reset() {\n    S.month   = STATE.month;\n    S.manager = \'all\';\n    S.assoc   = \'all\';\n    // Rebuild pills'),
    ('MP exports reset',            'return { init, render, reset };\n})();\n\ndocument.addEventListener(\'DOMContentLoaded\', () => {\n  MP.init()'),
    ('FN calls DD.reset()',         'DD.reset();'),
    ('FN calls MP.reset()',         'MP.reset();'),
    ('FN re-registers DD',          "PAGE_NAV.register('daily',   () => DD.render());"),
    ('FN re-registers MP',          "PAGE_NAV.register('monthly', () => MP.render());"),
    ('DD pills clear innerHTML',    "container.innerHTML = '';   // clear before rebuild"),
    ('MP pills clear innerHTML',    "container.innerHTML = '';   // clear before rebuild"),
    ('MP pills onclick (not add)',   'container.onclick = e => {'),
    ('DD mgr sel.onchange',         'sel.onchange = () => {\n      S.manager = sel.value;\n      S.assoc   = \'all\';\n      rebuildAssocSelect();\n      render();\n    };\n  }\n\n  /* \u2500\u2500 Build associate'),
    ('MP mgr sel.onchange',         'sel.onchange = () => {\n      S.manager = sel.value;\n      S.assoc   = \'all\';\n      rebuildAssocSelect();\n      render();\n    };\n  }\n\n  function buildAssocSelect'),
    ('DD render syncs S.month',     'S.month = STATE.month;   // single global Timeline drives all pages\n    if (S.month !== \'all\') syncDateToMonth();\n    rebuildAssocSelect();'),
    ('MP render syncs S.month',     'S.month = STATE.month;   // single global Timeline drives all pages\n    const rows       = computeRows();'),
]

print('=== FN-switch stale-state fix verification ===')
all_ok = True
for label, needle in checks:
    found = needle in src
    status = 'OK  ' if found else 'FAIL'
    print('  %s  %s' % (status, label))
    if not found:
        all_ok = False
        # Show what's near where we expected it
        idx = src.find(needle[:30])
        if idx >= 0:
            print('       near: %r' % src[idx:idx+80])

print()
print('Result:', 'ALL PASS' if all_ok else 'SOME FAILED')
