"""
Patch remaining timing marks into Refresh_ORBIT.ps1.
"""
import os

SYS  = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.dirname(SYS)
PS1  = os.path.join(SYS, 'Refresh_ORBIT.ps1')

src = open(PS1, encoding='utf-8').read()

def patch(old, new, label):
    global src
    if old not in src:
        print(f'  [SKIP - not found] {label}')
        return
    if new in src:
        print(f'  [SKIP - already applied] {label}')
        return
    src = src.replace(old, new, 1)
    print(f'  [PATCHED] {label}')

# 1. orbit-data.js write (raw) + enrich block
OLD_WRITE = (
    '[System.IO.File]::WriteAllText("$DASH_DIR\\orbit-data.js", $sb.ToString(), [System.Text.Encoding]::UTF8)\n'
    '\n'
    '$newSize = (Get-Item "$DASH_DIR\\orbit-data.js").Length\n'
    '$newRows = $prodRows.Count\n'
    'Log ("  orbit-data.js: " + [Math]::Round($newSize/1KB,1) + " KB") Green\n'
    'Log ("  D_PROD rows: $prevRows -> $newRows  (delta: +$($newRows - $prevRows))") $(if(($newRows-$prevRows) -ge 0){"Green"}else{"Yellow"})'
)
NEW_WRITE = (
    '[System.IO.File]::WriteAllText("$DASH_DIR\\orbit-data.js", $sb.ToString(), [System.Text.Encoding]::UTF8)\n'
    'Mark-Time "orbit-data.js write (raw)"\n'
    '\n'
    '# \u2500\u2500 Roster-authoritative D_QA enrichment \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '# enrich_data.py re-reads D_QA from orbit-data.js, joins every row to\n'
    '# the roster by ASSOCIATE OPR ID, and rewrites:\n'
    '#   D_QA[a]      -> official roster name  (never raw QA-system name)\n'
    '#   D_QA[fn]     -> function key (pre-attached; fnOf() checks this first)\n'
    '#   D_QA[am/mgr/pos/tower] -> roster values\n'
    '# Also refreshes D_FN, D_DIM, D_FN_META, D_HIST (roster_prev diff).\n'
    'Log "  Enriching D_QA rows from roster (OPR ID join)..." Gray\n'
    '$pyOut = & python -X utf8 "$SYS_DIR\\enrich_data.py" 2>&1\n'
    'if ($LASTEXITCODE -eq 0) {\n'
    '    foreach ($line in $pyOut) { Log ("    " + $line) Gray }\n'
    '    Log "  D_QA enrichment complete." Green\n'
    '} else {\n'
    '    foreach ($line in $pyOut) { Log ("  [WARN] enrich: " + $line) Yellow }\n'
    '    Log "  [WARN] enrich_data.py exited $LASTEXITCODE \u2014 orbit-data.js may be unenriched." Yellow\n'
    '}\n'
    'Mark-Time "enrich_data.py (roster join)"\n'
    '\n'
    '$newSize = (Get-Item "$DASH_DIR\\orbit-data.js").Length\n'
    '$newRows = $prodRows.Count\n'
    'Log ("  orbit-data.js: " + [Math]::Round($newSize/1KB,1) + " KB") Green\n'
    'Log ("  D_PROD rows: $prevRows -> $newRows  (delta: +$($newRows - $prevRows))") $(if(($newRows-$prevRows) -ge 0){"Green"}else{"Yellow"})'
)
patch(OLD_WRITE, NEW_WRITE, 'orbit-data.js write + enrich block')

open(PS1, 'w', encoding='utf-8').write(src)
print('\nDone.')
