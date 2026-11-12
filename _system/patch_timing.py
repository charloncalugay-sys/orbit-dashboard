"""
Patch Refresh_ORBIT.ps1 with granular Mark-Time probes.
Run once; idempotent if the marks are already present.
"""
import re, os, sys

SYS  = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.dirname(SYS)
PS1  = os.path.join(SYS, 'Refresh_ORBIT.ps1')

src = open(PS1, encoding='utf-8').read()

# Helper: only patch if old string exists and new string is not already there
def patch(old, new, label=""):
    global src
    if old not in src:
        print(f"  [SKIP] already patched or not found: {label or old[:60]!r}")
        return False
    if new in src:
        print(f"  [SKIP] already applied: {label or old[:60]!r}")
        return False
    src = src.replace(old, new, 1)
    print(f"  [PATCHED] {label or old[:60]!r}")
    return True


# ── STEP 2 PT builds — add Mark-Time after each ─────────────
patch(
    'Log ("    Rows: " + $ptP.TableRange1.Rows.Count) Gray\n\n# PT-QA',
    'Log ("    PT_PROD rows: " + $ptP.TableRange1.Rows.Count) Gray\nMark-Time "PT_PROD build"\n\n# PT-QA',
    'PT_PROD build mark'
)

patch(
    'Log ("    Rows: " + $ptQ.TableRange1.Rows.Count) Gray\n\n# PT-ASSOC',
    'Log ("    PT_QA rows: " + $ptQ.TableRange1.Rows.Count) Gray\nMark-Time "PT_QA build"\n\n# PT-ASSOC',
    'PT_QA build mark'
)

patch(
    'Log ("    Rows: " + $ptA.TableRange1.Rows.Count) Gray\n\n$wb.Save()',
    'Log ("    PT_ASSOC rows: " + $ptA.TableRange1.Rows.Count) Gray\nMark-Time "PT_ASSOC build"\n\n$wb.Save()',
    'PT_ASSOC build mark'
)

# ── Paste timing ─────────────────────────────────────────────
patch(
    '$ptP.TableRange1.Copy(); $ps.Cells.Item(2,1).PasteSpecial(-4163); $xl.CutCopyMode = $false\n$lastRowP = $ps.Cells.Item(1,1).SpecialCells(11).Row\n$ps.Cells.Item($lastRowP+2, 1).Value2 = "QA_START"\n$ptQ.TableRange1.Copy(); $ps.Cells.Item($lastRowP+3, 1).PasteSpecial(-4163); $xl.CutCopyMode = $false\n$lastRowQ = $ps.Cells.Item(1,1).SpecialCells(11).Row\n$ps.Cells.Item($lastRowQ+2, 1).Value2 = "ASSOC_START"\n$ptA.TableRange1.Copy(); $ps.Cells.Item($lastRowQ+3, 1).PasteSpecial(-4163); $xl.CutCopyMode = $false',
    '$ptP.TableRange1.Copy(); $ps.Cells.Item(2,1).PasteSpecial(-4163); $xl.CutCopyMode = $false\n$lastRowP = $ps.Cells.Item(1,1).SpecialCells(11).Row\nMark-Time "PT_PROD paste"\n$ps.Cells.Item($lastRowP+2, 1).Value2 = "QA_START"\n$ptQ.TableRange1.Copy(); $ps.Cells.Item($lastRowP+3, 1).PasteSpecial(-4163); $xl.CutCopyMode = $false\n$lastRowQ = $ps.Cells.Item(1,1).SpecialCells(11).Row\nMark-Time "PT_QA paste"\n$ps.Cells.Item($lastRowQ+2, 1).Value2 = "ASSOC_START"\n$ptA.TableRange1.Copy(); $ps.Cells.Item($lastRowQ+3, 1).PasteSpecial(-4163); $xl.CutCopyMode = $false\nMark-Time "PT_ASSOC paste"',
    'paste marks'
)

# ── Workbook save + range read ───────────────────────────────
patch(
    '$wb.Save()\n\n# Read PLAIN_DATA and convert to CSVs',
    '$wb.Save()\nMark-Time "Workbook save (post-paste)"\n\n# Read PLAIN_DATA and convert to CSVs',
    'save mark'
)

# ── Range read to array ──────────────────────────────────────
patch(
    '$allData = $ps.Range($ps.Cells.Item(1,1), $ps.Cells.Item($lastRow,$lastCol)).Value2\nLog ("  Sheet dimensions: $lastRow rows x $lastCol cols") Gray',
    '$allData = $ps.Range($ps.Cells.Item(1,1), $ps.Cells.Item($lastRow,$lastCol)).Value2\nLog ("  Sheet dimensions: $lastRow rows x $lastCol cols") Gray\nMark-Time "PLAIN_DATA range read"',
    'range read mark'
)

# ── Section-To-CSV calls ─────────────────────────────────────
patch(
    '$prodCsv  = Section-To-CSV $allData $prodStart  $prodEnd  8\n$qaCsv    = Section-To-CSV $allData $qaStart    $qaEnd    8\n$assocCsv = Section-To-CSV $allData $assocStart $assocEnd 8',
    '$prodCsv  = Section-To-CSV $allData $prodStart  $prodEnd  8\nMark-Time "prod_raw Section-To-CSV"\n$qaCsv    = Section-To-CSV $allData $qaStart    $qaEnd    8\nMark-Time "qa_raw Section-To-CSV"\n$assocCsv = Section-To-CSV $allData $assocStart $assocEnd 8\nMark-Time "assoc_raw Section-To-CSV"',
    'Section-To-CSV marks'
)

# ── WriteAllText CSV files ───────────────────────────────────
patch(
    '[System.IO.File]::WriteAllText("$SYS_DIR\\prod_raw.csv",  $prodCsv,  [System.Text.Encoding]::UTF8)\n[System.IO.File]::WriteAllText("$SYS_DIR\\qa_raw.csv",    $qaCsv,    [System.Text.Encoding]::UTF8)\n[System.IO.File]::WriteAllText("$SYS_DIR\\assoc_raw.csv", $assocCsv, [System.Text.Encoding]::UTF8)',
    '[System.IO.File]::WriteAllText("$SYS_DIR\\prod_raw.csv",  $prodCsv,  [System.Text.Encoding]::UTF8)\n[System.IO.File]::WriteAllText("$SYS_DIR\\qa_raw.csv",    $qaCsv,    [System.Text.Encoding]::UTF8)\n[System.IO.File]::WriteAllText("$SYS_DIR\\assoc_raw.csv", $assocCsv, [System.Text.Encoding]::UTF8)\nMark-Time "CSV WriteAllText"',
    'CSV write mark'
)

# ── Excel close ──────────────────────────────────────────────
patch(
    'Log "  Excel closed. $(Elapsed)" Green',
    'Mark-Time "Excel close + GC"\nLog "  Excel closed. $(Elapsed)" Green',
    'Excel close mark'
)

# ── Leadership export ────────────────────────────────────────
patch(
    'Log "STEP 2.5: Exporting leadership roster..." Cyan\n& "$SYS_DIR\\Export_ORBIT_Leadership.ps1"',
    'Log "STEP 2.5: Exporting leadership roster..." Cyan\n& "$SYS_DIR\\Export_ORBIT_Leadership.ps1"\nMark-Time "Leadership export (orbit-auth.js)"',
    'leadership export mark'
)

# ── STEP 3 parse sections ────────────────────────────────────
# Parse QA — find after "QA: ...rows, ...managers"
patch(
    'Log ("  QA: " + $qaRows.Count + " rows, " + $qaMgrs.Count + " managers") Gray',
    'Log ("  QA: " + $qaRows.Count + " rows, " + $qaMgrs.Count + " managers") Gray\nMark-Time "Parse qa_raw.csv"',
    'parse QA mark'
)

# Parse PROD
patch(
    'Log ("  PROD: " + $prodRows.Count + " rows") Gray',
    'Log ("  PROD: " + $prodRows.Count + " rows") Gray\nMark-Time "Parse prod_raw.csv"',
    'parse PROD mark'
)

# Parse ASSOC
patch(
    'Log ("  ASSOC: " + $assocRows.Count + " rows") Gray',
    'Log ("  ASSOC: " + $assocRows.Count + " rows") Gray\nMark-Time "Parse assoc_raw.csv"',
    'parse ASSOC mark'
)

# ── orbit-data.js WriteAllText ───────────────────────────────
patch(
    '[System.IO.File]::WriteAllText("$DASH_DIR\\orbit-data.js", $sb.ToString(), [System.Text.Encoding]::UTF8)\n\n# ── Roster-authoritative D_QA enrichment',
    '[System.IO.File]::WriteAllText("$DASH_DIR\\orbit-data.js", $sb.ToString(), [System.Text.Encoding]::UTF8)\nMark-Time "orbit-data.js write (raw)"\n\n# ── Roster-authoritative D_QA enrichment',
    'orbit-data.js write mark'
)

# ── enrich_data.py ───────────────────────────────────────────
patch(
    'Log "  D_QA enrichment complete." Green\n} else {',
    'Mark-Time "enrich_data.py (roster join)"\n    Log "  D_QA enrichment complete." Green\n} else {',
    'enrich mark'
)

# ── STEP 5 git timing ────────────────────────────────────────
patch(
    '& $GIT -C $DASH_DIR commit -m $commitMsg 2>&1 | ForEach-Object { Log "  $_" Gray }',
    '& $GIT -C $DASH_DIR commit -m $commitMsg 2>&1 | ForEach-Object { Log "  $_" Gray }\n        Mark-Time "git commit"',
    'git commit mark'
)

patch(
    '& $GIT -C $DASH_DIR push origin main 2>&1 | ForEach-Object { Log "  $_" Gray }\n            if ($LASTEXITCODE -eq 0) {',
    '& $GIT -C $DASH_DIR push origin main 2>&1 | ForEach-Object { Log "  $_" Gray }\n            Mark-Time "git push"\n            if ($LASTEXITCODE -eq 0) {',
    'git push mark'
)

# ── Final profile dump — right before STEP 6 ────────────────
patch(
    '# STEP 6 — Open / reload ORBIT.html in the default browser',
    '# ── Timing profile ──────────────────────────────────────────\nMark-Time "TOTAL (before browser open)"\nShow-Profile\n\n# STEP 6 — Open / reload ORBIT.html in the default browser',
    'Show-Profile call'
)

# Write patched file
open(PS1, 'w', encoding='utf-8').write(src)
print('\nDone. Refresh_ORBIT.ps1 patched with timing instrumentation.')
