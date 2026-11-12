# ============================================================
# PROJECT ORBIT - One-Click Refresh + GitHub Publish
# Steps:
#   0. Timestamped backup: ORBIT.html / orbit-app.js / orbit.css
#      -> ORBIT DASH\_system\BACKUP\YYYYMMDD_HHMM\
#   1. Refresh Excel data model (RefreshAll)
#   2. Export DATA_EXTRACT -> prod_raw.csv / qa_raw.csv / assoc_raw.csv
#   2.5. Export leadership roster -> orbit-auth.js
#   3. Rebuild orbit-data.js
#   4. Verify deployment folder + confirm app files untouched
#   5. Git commit + push -> Vercel deploys orbit-two-silk.vercel.app
#      5b. git pull --ff-only syncs the SharePoint mirror clone (Folder B)
#      5c. optional Vercel deploy-hook + version.json freshness poll
#   6. Open (or reload) the production URL in the default browser
#
# GUARANTEE: this script writes ONLY data files
#   (orbit-data.js, orbit-auth.js, prod_raw.csv, qa_raw.csv, assoc_raw.csv).
# It NEVER writes or overwrites ORBIT.html / orbit-app.js / orbit.css.
#
# FOLDER LAYOUT:
#   ORBIT DASH\              -- git repository root (GitHub Pages source)
#     ORBIT.html             -- the application
#     orbit-app.js, orbit.css, chart.umd.min.js
#     orbit-data.js          -- generated; committed on every refresh
#     orbit-auth.js          -- generated; committed on every refresh
#     assets\logos\          -- logo images
#     _system\               -- admin-only scripts + raw data (gitignored data)
#       Refresh_ORBIT.ps1    -- this script
#       BACKUP\              -- timestamped app-file backups (gitignored)
#       .versions\           -- VCS snapshots (gitignored)
#       prod_raw.csv, qa_raw.csv, assoc_raw.csv (gitignored)
# ============================================================

# ── SOURCE OF TRUTH  -  Folder A ──────────────────────────────────────────────
# The ONLY place Refresh_ORBIT may run. Folder B (SharePoint team-site sync
# under T-Payment Integrity\Cha\ORBIT) is a read-only mirror that receives
# published artifacts via git pull after every successful push (see STEP 5).
$WORKBOOK  = "C:\Users\AL70683\OneDrive - Elevance Health\IGNITE PROJECTS\ORBIT\PI DI Dashboard.xlsx"
$ROSTER    = "C:\Users\AL70683\OneDrive - Elevance Health\IGNITE PROJECTS\TEMPUS\CGS SBF PI Roster 08.10.26.xlsx"
$DASH_DIR  = "C:\Users\AL70683\OneDrive - Elevance Health\IGNITE PROJECTS\ORBIT\ORBIT DASH"
$SYS_DIR   = "$DASH_DIR\_system"   # backend/admin files - not exposed to end users
$HTML_FILE = "$DASH_DIR\ORBIT.html"

# Mirror clone (Folder B)  -  pulled after each push; NEVER refreshed locally.
$MIRROR_ORBIT = "C:\Users\AL70683\Elevance Health\T-Payment Integrity 2025 - 2026 - IGNITE\Cha\ORBIT"
$MIRROR_DASH  = "$MIRROR_ORBIT\ORBIT DASH"
$MIRROR_ROOT_FILES = @(
    "ORBIT_Leadership.xlsx",
    "PI DI Dashboard.xlsx",
    "Refresh_ORBIT.bat",
    "Refresh_ORBIT.ps1"
)

# Safety guard: refuse to run inside the mirror copy.
if ($PSScriptRoot -like "*T-Payment Integrity*") {
    Write-Host "[ABORT] This ORBIT folder is the SharePoint MIRROR copy." -ForegroundColor Red
    Write-Host "        Run Refresh_ORBIT.bat from the source-of-truth folder:" -ForegroundColor Red
    Write-Host "        ...\IGNITE PROJECTS\ORBIT\ORBIT DASH\_system\" -ForegroundColor Yellow
    exit 1
}

# ── Git executable (GitHub Desktop ships its own copy) ────────────────────────
$GIT = "C:\Users\AL70683\AppData\Local\Programs\Git\bin\git.exe"

# ── Canonical live URL ────────────────────────────────────────────────────────
# Official production endpoint (Vercel).
$ORBIT_URL   = "https://orbit-two-silk.vercel.app/ORBIT.html"
$ORBIT_BASE  = "https://orbit-two-silk.vercel.app"
# GitHub Pages remains live as an automatic fallback mirror.
$PAGES_URL   = "https://charloncalugay-sys.github.io/orbit-dashboard/ORBIT.html"
#
# OPTIONAL: Vercel Deploy Hook. Create one in Vercel project
# Settings -> Git -> Deploy Hooks, then put the URL in
# _system\vercel_hook.txt (NOT committed). If present, every refresh
# fires the hook directly - deployment no longer depends on the
# Git->Vercel integration staying healthy.
$VERCEL_HOOK_FILE = "$DASH_DIR\_system\vercel_hook.txt"
# ─────────────────────────────────────────────────────────────────────────────

$T0 = Get-Date
function Log($msg, $color="White") {
    $ts = (Get-Date).ToString("HH:mm:ss")
    Write-Host "[$ts] $msg" -ForegroundColor $color
}
function Elapsed { $sec = [int]((Get-Date)-$T0).TotalSeconds; return "[$sec s elapsed]" }

# ── Helpers shared by extract + rebuild ──────────────────────────────────────
function ParseCsvLine($line) {
    $fields = [System.Collections.Generic.List[string]]::new()
    $inQ = $false; $cur = [System.Text.StringBuilder]::new()
    for ($i = 0; $i -lt $line.Length; $i++) {
        $ch = $line[$i]
        if ($ch -eq '"') {
            if ($inQ -and $i+1 -lt $line.Length -and $line[$i+1] -eq '"') {
                $cur.Append('"') | Out-Null; $i++
            } else { $inQ = -not $inQ }
        } elseif ($ch -eq ',' -and -not $inQ) {
            $fields.Add($cur.ToString()); $cur.Clear() | Out-Null
        } else { $cur.Append($ch) | Out-Null }
    }
    $fields.Add($cur.ToString()); return $fields.ToArray()
}
function IsDateSerial($s) {
    $n = 0.0
    if ([double]::TryParse($s,[System.Globalization.NumberStyles]::Any,
        [System.Globalization.CultureInfo]::InvariantCulture,[ref]$n)) {
        return $n -gt 40000 -and $n -lt 60000
    }; return $false
}
function ToDouble($s) {
    $n = 0.0
    [double]::TryParse($s,[System.Globalization.NumberStyles]::Any,
        [System.Globalization.CultureInfo]::InvariantCulture,[ref]$n) | Out-Null
    return $n
}
function IsDomainID($s)  { return $s -match '^[A-Z]{1,3}[0-9]+$' }
function Col0($line)     { return (ParseCsvLine $line)[0] }
function NextC0($lines,$from) {
    for ($j = $from; $j -le ([Math]::Min($lines.Length-1,$from+5)); $j++) {
        $l = $lines[$j]; if ($l -ne "") { return Col0 $l }
    }; return ""
}
function EscJ($s) {
    $s2 = [string]$s
    $s2 = $s2.Replace('\','\\').Replace('"','\"')
    return $s2
}

# ════════════════════════════════════════════════════════════════
# STEP 0  -  Timestamped backup of application files
# This script ONLY ever writes: orbit-data.js, prod_raw.csv,
# qa_raw.csv, assoc_raw.csv. Application files (ORBIT.html,
# orbit-app.js, orbit.css) are NEVER written or overwritten.
# Backup guarantees instant recovery if anything else touches them.
# ════════════════════════════════════════════════════════════════
Log "STEP 0: Backing up application files..." Cyan

$APP_FILES = @("ORBIT.html","orbit-app.js","orbit.css")
$backupDir = "$SYS_DIR\BACKUP\$(Get-Date -Format 'yyyyMMdd_HHmm')"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

foreach ($f in $APP_FILES) {
    $p = "$DASH_DIR\$f"
    if (Test-Path $p) {
        Copy-Item $p "$backupDir\$f" -Force
        Log ("  [BACKED UP]  $f -> _system\BACKUP\$(Split-Path $backupDir -Leaf)") Gray
    } else {
        Log ("  [SKIP]  $f not present in ORBIT DASH") Yellow
    }
}

# Record app-file fingerprints  -  verified again in STEP 4 to prove
# the refresh only touched data files.
$appHashBefore = @{}
foreach ($f in $APP_FILES) {
    $p = "$DASH_DIR\$f"
    if (Test-Path $p) { $appHashBefore[$f] = (Get-FileHash $p -Algorithm SHA256).Hash }
}
Log "  Application files backed up to _system\BACKUP\$(Split-Path $backupDir -Leaf)" Green

# ════════════════════════════════════════════════════════════════
# STEP 1  -  Open workbook and RefreshAll (data model + Power Query)
# ════════════════════════════════════════════════════════════════
Log "STEP 1: Opening Excel and refreshing data model..." Cyan

Stop-Process -Name EXCEL -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Mark-Time "Excel kill + wait"

$xl = New-Object -ComObject Excel.Application
$xl.Visible        = $true
$xl.DisplayAlerts  = $false
$xl.ScreenUpdating = $false

$wb = $xl.Workbooks.Open($WORKBOOK)
Mark-Time "Workbook open"

# ── Active-wait for RefreshAll ────────────────────
# RefreshAll() fires all connections asynchronously and returns
# immediately. We poll WorkbookConnection.OLEDBConnection.Refreshing
# every 5s until all connections finish, up to a 20-min hard cap.
# This gives the EXACT refresh duration instead of a blind sleep.
Log "  Issuing RefreshAll..." Gray
$T_REFRESH_START = Get-Date
try { $wb.RefreshAll() } catch { Log ("  RefreshAll warning: " + $_.Exception.Message) Yellow }
Start-Sleep -Seconds 3   # brief pause before first poll

Log "  Polling connections for refresh completion..." Gray
$pollSec      = 0
$maxPollSec   = 1200   # 20-min hard cap
$pollInterval = 5      # seconds between polls
do {
    Start-Sleep -Seconds $pollInterval
    $pollSec += $pollInterval
    $stillRunning = @()
    try {
        foreach ($conn in $wb.Connections) {
            try {
                $ole = $conn.OLEDBConnection
                if ($ole -ne $null -and $ole.Refreshing) { $stillRunning += $conn.Name }
            } catch {}
            try {
                $pq = $conn.ODBCConnection
                if ($pq -ne $null -and $pq.Refreshing) { $stillRunning += $conn.Name }
            } catch {}
        }
    } catch {}
    if ($stillRunning.Count -gt 0) {
        Log ("    still refreshing ($pollSec s): " + ($stillRunning -join ", ")) DarkGray
    }
} while ($stillRunning.Count -gt 0 -and $pollSec -lt $maxPollSec)

$refreshDur = [Math]::Round(($T_REFRESH_START - (Get-Date)).TotalSeconds * -1, 1)
if ($pollSec -ge $maxPollSec) {
    Log "  [WARN] RefreshAll poll timed out at ${maxPollSec}s  -  connections may still be loading." Yellow
} else {
    Log ("  All connections finished. Refresh duration: ${refreshDur}s") Green
}
Mark-Time "RefreshAll complete"

# Extra settle time for the in-process Analysis Services engine
# (DAX recalc runs after Power Query finishes; 5s is usually enough).
Log "  Settling data model (DAX recalc)..." Gray
Start-Sleep -Seconds 5
Mark-Time "Data model settle"
Log "  Data model refresh complete. $(Elapsed)" Green

# ════════════════════════════════════════════════════════════════
# STEP 2  -  Build DATA_EXTRACT PivotTables and export CSVs
# ════════════════════════════════════════════════════════════════
Log "STEP 2: Building DATA_EXTRACT PivotTables..." Cyan

$dmConn = $wb.Connections.Item("ThisWorkbookDataModel")

# Remove old extraction sheets
foreach ($sh in @($wb.Sheets | Where-Object { $_.Name -eq "DATA_EXTRACT" -or $_.Name -eq "PLAIN_DATA" })) {
    try { $sh.Delete() } catch {}
}

$xs = $wb.Sheets.Add(); $xs.Name = "DATA_EXTRACT"

$xlRow  = 1   # xlRowField
$xlData = 4   # xlDataField

function New-PT($row, $col, $name) {
    return $wb.PivotCaches().Create(2, $dmConn).CreatePivotTable($xs.Cells.Item($row,$col), $name)
}
function F($pt, $mdx, $orient) {
    foreach ($cf in $pt.CubeFields) {
        if ($cf.Name -eq $mdx) { $cf.Orientation = $orient; return }
    }
    Log ("  Field not found: $mdx") Yellow
}

# PT-PROD
Log "  Building PT_PROD..." Gray
$ptP = New-PT 1 1 "PT_PROD"
F $ptP "[Fact_Productivity].[Manager]"        $xlRow
F $ptP "[Fact_Productivity].[Associate Name]" $xlRow
F $ptP "[Fact_Productivity].[Date]"           $xlRow
F $ptP "[Fact_Productivity].[WEEK]"           $xlRow
F $ptP "[Measures].[Actual Production]"       $xlData
F $ptP "[Measures].[Production Target]"       $xlData
Log ("    PT_PROD rows: " + $ptP.TableRange1.Rows.Count) Gray
Mark-Time "PT_PROD build"

# PT-QA
Log "  Building PT_QA..." Gray
$ptQ = New-PT 1 9 "PT_QA"
F $ptQ "[Fact_QA_AllFunctions].[Manager]"         $xlRow
F $ptQ "[Fact_QA_AllFunctions].[US Domain ID]"    $xlRow
F $ptQ "[Fact_QA_AllFunctions].[Associate]"       $xlRow
F $ptQ "[Fact_QA_AllFunctions].[Process Date]"    $xlRow
F $ptQ "[Measures].[QA Audit Count]" $xlData
F $ptQ "[Measures].[Avg QA Score]"   $xlData
Log ("    PT_QA rows: " + $ptQ.TableRange1.Rows.Count) Gray
Mark-Time "PT_QA build"

# PT-ASSOC
Log "  Building PT_ASSOC..." Gray
$ptA = New-PT 1 17 "PT_ASSOC"
F $ptA "[Dim_Associate].[Manager]"        $xlRow
F $ptA "[Dim_Associate].[Domain ID]"      $xlRow
F $ptA "[Dim_Associate].[Associate Name]" $xlRow
F $ptA "[Measures].[Actual Production]"   $xlData
Log ("    PT_ASSOC rows: " + $ptA.TableRange1.Rows.Count) Gray
Mark-Time "PT_ASSOC build"

$wb.Save()
Start-Sleep -Seconds 2

# Copy PT values to plain sheet (values-only paste to strip PT formatting)
Log "  Copying PT values to PLAIN_DATA sheet..." Gray
$ps = $wb.Sheets.Add(); $ps.Name = "PLAIN_DATA"
$ps.Cells.Item(1,1).Value2 = "PROD_START"

$ptP.TableRange1.Copy(); $ps.Cells.Item(2,1).PasteSpecial(-4163); $xl.CutCopyMode = $false
$lastRowP = $ps.Cells.Item(1,1).SpecialCells(11).Row
Mark-Time "PT_PROD paste"
$ps.Cells.Item($lastRowP+2, 1).Value2 = "QA_START"
$ptQ.TableRange1.Copy(); $ps.Cells.Item($lastRowP+3, 1).PasteSpecial(-4163); $xl.CutCopyMode = $false
$lastRowQ = $ps.Cells.Item(1,1).SpecialCells(11).Row
Mark-Time "PT_QA paste"
$ps.Cells.Item($lastRowQ+2, 1).Value2 = "ASSOC_START"
$ptA.TableRange1.Copy(); $ps.Cells.Item($lastRowQ+3, 1).PasteSpecial(-4163); $xl.CutCopyMode = $false
Mark-Time "PT_ASSOC paste"

$wb.Save()
Mark-Time "Workbook save (post-paste)"

# Read PLAIN_DATA and convert to CSVs
$lastRow = $ps.Cells.Item(1,1).SpecialCells(11).Row
$lastCol = $ps.Cells.Item(1,1).SpecialCells(11).Column
$allData = $ps.Range($ps.Cells.Item(1,1), $ps.Cells.Item($lastRow,$lastCol)).Value2
Log ("  Sheet dimensions: $lastRow rows x $lastCol cols") Gray
Mark-Time "PLAIN_DATA range read"

$prodStart = $null; $qaStart = $null; $assocStart = $null
$prodEnd   = $null; $qaEnd   = $null

for ($r = 1; $r -le $lastRow; $r++) {
    $v = $allData[$r,1]
    if ($v -eq "PROD_START")  { $prodStart  = $r+1 }
    if ($v -eq "QA_START")    { $qaStart    = $r+1; if ($prodStart  -ne $null) { $prodEnd  = $r-2 } }
    if ($v -eq "ASSOC_START") { $assocStart = $r+1; if ($qaStart    -ne $null) { $qaEnd    = $r-2 } }
}
$assocEnd = $lastRow

function Section-To-CSV($data, $rStart, $rEnd, $nCols) {
    $lines = [System.Collections.ArrayList]::new()
    for ($r = $rStart; $r -le $rEnd; $r++) {
        $hasData = $false
        for ($c = 1; $c -le $nCols; $c++) { if ($data[$r,$c] -ne $null) { $hasData=$true; break } }
        if (-not $hasData) { continue }
        $cells = @(1..$nCols | ForEach-Object {
            $v = $data[$r,$_]
            if ($v -eq $null) { "" } else {
                $s = "$v"; $s = $s -replace '"','""'
                if ($s -match '[,"\r\n]') { '"' + $s + '"' } else { $s }
            }
        })
        $null = $lines.Add(($cells -join ","))
    }
    return $lines -join "`n"
}

$prodCsv  = Section-To-CSV $allData $prodStart  $prodEnd  8
Mark-Time "prod_raw Section-To-CSV"
$qaCsv    = Section-To-CSV $allData $qaStart    $qaEnd    8
Mark-Time "qa_raw Section-To-CSV"
$assocCsv = Section-To-CSV $allData $assocStart $assocEnd 8
Mark-Time "assoc_raw Section-To-CSV"

[System.IO.File]::WriteAllText("$SYS_DIR\prod_raw.csv",  $prodCsv,  [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText("$SYS_DIR\qa_raw.csv",    $qaCsv,    [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText("$SYS_DIR\assoc_raw.csv", $assocCsv, [System.Text.Encoding]::UTF8)
Mark-Time "CSV WriteAllText"

# Report max date captured
$prodLines = $prodCsv -split "`n"
$maxSerial = 0
foreach ($l in $prodLines) {
    if ($l -match '^\d{5}(,|$)') {
        $s = [int]$l.Split(',')[0]; if ($s -gt $maxSerial) { $maxSerial = $s }
    }
}
$maxDate = if ($maxSerial -gt 0) { [DateTime]::FromOADate($maxSerial).ToString("yyyy-MM-dd") } else { "unknown" }

Log ("  prod_raw.csv : " + [Math]::Round(([System.IO.FileInfo]"$SYS_DIR\prod_raw.csv").Length/1KB,1) + " KB  |  Max date: $maxDate (serial $maxSerial)") Green
Log ("  qa_raw.csv   : " + [Math]::Round(([System.IO.FileInfo]"$SYS_DIR\qa_raw.csv").Length/1KB,1)   + " KB") Green
Log ("  assoc_raw.csv: " + [Math]::Round(([System.IO.FileInfo]"$SYS_DIR\assoc_raw.csv").Length/1KB,1) + " KB") Green

# Close Excel
$wb.Close($false)
$xl.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($xl) | Out-Null
[GC]::Collect()
Mark-Time "Excel close + GC"
Log "  Excel closed. $(Elapsed)" Green

# ════════════════════════════════════════════════════════════════
# STEP 2.5  -  Export leadership roster -> orbit-auth.js
# ORBIT_Leadership.xlsx is the single source of truth for
# Leadership Portal authorization (DOMAIN = security key).
# ════════════════════════════════════════════════════════════════
Log "STEP 2.5: Exporting leadership roster..." Cyan
& "$SYS_DIR\Export_ORBIT_Leadership.ps1"
Mark-Time "Leadership export (orbit-auth.js)"

# ════════════════════════════════════════════════════════════════
# STEP 3  -  Parse CSVs and rebuild orbit-data.js
# ════════════════════════════════════════════════════════════════
Log "STEP 3: Rebuilding orbit-data.js..." Cyan

$prevItem = Get-Item "$DASH_DIR\orbit-data.js" -ErrorAction SilentlyContinue
$prevSize = if ($prevItem) { $prevItem.Length } else { 0 }
$prevRows = if (Test-Path "$DASH_DIR\orbit-data.js") {
    ([regex]::Matches([System.IO.File]::ReadAllText("$DASH_DIR\orbit-data.js"),'\"act\":')).Count
} else { 0 }

# Parse PROD
$rawP = [System.IO.File]::ReadAllLines("$SYS_DIR\prod_raw.csv",[System.Text.Encoding]::UTF8)
$prodRows = [System.Collections.ArrayList]::new()
$m = ""; $a = ""; $ym = ""; $d = ""
for ($i = 1; $i -lt $rawP.Length; $i++) {
    $l = $rawP[$i]; if ($l -eq "") { continue }
    $c = Col0 $l
    if ($c -match "^Week ") {
        $f = ParseCsvLine $l
        $null = $prodRows.Add([PSCustomObject]@{
            m=$m; a=$a; ym=$ym; w=$c; d=$d
            act=[Math]::Round((ToDouble $f[1]),2)
            tgt=[Math]::Round((ToDouble $f[2]),2)
        })
    } elseif (IsDateSerial $c) {
        # Retain both the month (for filtering) and the specific calendar date (for Daily Detail display)
        try {
            $dt = [DateTime]::FromOADate((ToDouble $c))
            $ym = $dt.ToString("yyyy-MM")
            $d  = $dt.ToString("M/d/yyyy")   # e.g. 9/1/2026
        } catch { $ym = ""; $d = "" }
    } elseif ($c -ne "") {
        $nxt = NextC0 $rawP ($i+1)
        if ($nxt -match "^[A-Za-z]" -and -not(IsDomainID $nxt) -and
            -not(IsDateSerial $nxt) -and -not($nxt -match "^Week ")) {
            $m = $c; $a = ""; $ym = ""; $d = ""
        } else { $a = $c; $ym = ""; $d = "" }
    }
}
$orgMgrs = $prodRows | Select-Object -ExpandProperty m | Sort-Object -Unique | Where-Object { $_ -ne "" }
Log ("  PROD: " + $prodRows.Count + " rows, " + $orgMgrs.Count + " managers") Gray
Mark-Time "Parse prod_raw.csv"

# Parse QA
$rawQ = [System.IO.File]::ReadAllLines("$SYS_DIR\qa_raw.csv",[System.Text.Encoding]::UTF8)
$qaRows = [System.Collections.ArrayList]::new()
$mq = ""; $iq = ""; $aq = ""
for ($i = 1; $i -lt $rawQ.Length; $i++) {
    $l = $rawQ[$i]; if ($l -eq "") { continue }
    $c = Col0 $l
    if (IsDateSerial $c) {
        $f = ParseCsvLine $l; $cnt = ToDouble $f[1]; $scr = ToDouble $f[2]
        if ($cnt -gt 0) {
            try { $d = [DateTime]::FromOADate((ToDouble $c)).ToString("yyyy-MM-dd") } catch { $d = $c }
            $null = $qaRows.Add([PSCustomObject]@{
                m=$mq; id=$iq; a=$aq; d=$d
                cnt=[Math]::Round($cnt,4); scr=[Math]::Round($scr,6)
            })
        }
    } elseif (IsDomainID $c) { $iq = $c; $aq = "" }
    elseif ($c -ne "") {
        $nxt = NextC0 $rawQ ($i+1)
        if (IsDomainID $nxt) { $mq = $c; $iq = ""; $aq = "" } else { $aq = $c }
    }
}
$qaMgrs = $qaRows | Select-Object -ExpandProperty m | Sort-Object -Unique | Where-Object { $_ -ne "" }
Log ("  QA: " + $qaRows.Count + " rows, " + $qaMgrs.Count + " managers") Gray
Mark-Time "Parse qa_raw.csv"

# Parse ASSOC
$rawA = [System.IO.File]::ReadAllLines("$SYS_DIR\assoc_raw.csv",[System.Text.Encoding]::UTF8)
$assocRows = [System.Collections.ArrayList]::new()
$ma = ""; $ia = ""
for ($i = 1; $i -lt $rawA.Length; $i++) {
    $l = $rawA[$i]; if ($l -eq "") { continue }
    $f = ParseCsvLine $l; $c = $f[0].Trim(); if ($c -eq "") { continue }
    if (IsDomainID $c) { $ia = $c; continue }
    if ($f[1].Trim() -eq "") { $ma = $c; $ia = "" }
    elseif ($ia -ne "") { $null = $assocRows.Add([PSCustomObject]@{id=$ia; n=$c}); $ia = "" }
}
Log ("  ASSOC: " + $assocRows.Count + " rows") Gray
Mark-Time "Parse assoc_raw.csv"

# Write orbit-data.js
$sb = [System.Text.StringBuilder]::new()
[void]$sb.Append("// PROJECT ORBIT`n")
[void]$sb.Append("// Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm')`n")
[void]$sb.Append("// Max date captured: $maxDate (serial $maxSerial)`n")
[void]$sb.Append("// Zero-production rows included so all associates appear in table`n")

[void]$sb.Append("const D_PROD=[")
$fi = $true
foreach ($r in $prodRows) {
    if (-not $fi) { [void]$sb.Append(",") }; $fi = $false
    [void]$sb.Append("{`"m`":`"$(EscJ $r.m)`",`"a`":`"$(EscJ $r.a)`",`"ym`":`"$($r.ym)`",`"w`":`"$(EscJ $r.w)`",`"d`":`"$($r.d)`",`"act`":$($r.act),`"tgt`":$($r.tgt)}")
}
[void]$sb.Append("];`n")

[void]$sb.Append("const D_QA=[")
$fi = $true
foreach ($r in $qaRows) {
    if (-not $fi) { [void]$sb.Append(",") }; $fi = $false
    [void]$sb.Append("{`"m`":`"$(EscJ $r.m)`",`"id`":`"$(EscJ $r.id)`",`"a`":`"$(EscJ $r.a)`",`"d`":`"$($r.d)`",`"cnt`":$($r.cnt),`"scr`":$($r.scr)}")
}
[void]$sb.Append("];`n")

[void]$sb.Append("const D_ASSOC=[")
$fi = $true
foreach ($r in $assocRows) {
    if (-not $fi) { [void]$sb.Append(",") }; $fi = $false
    [void]$sb.Append("{`"id`":`"$(EscJ $r.id)`",`"n`":`"$(EscJ $r.n)`"}")
}
[void]$sb.Append("];`n")

$allMgrs = ($orgMgrs + $qaMgrs) | Sort-Object -Unique | Where-Object { $_ -ne "" }
$mparts  = ($allMgrs | ForEach-Object { "`"$(EscJ $_)`"" }) -join ","
[void]$sb.Append("const D_MANAGERS=[$mparts];`n")

# ==========================================================================
# ROSTER = FUNCTION AUTHORITY
# Reads CGS SBF PI Roster (Table1: OPR ID | ASSOCIATES | Assistant Manager |
# Function | Manager | POSITION | TOWER | HIRE DATE) and emits:
#   D_FN      {byId,byName}  - record -> function classification
#   D_DIM     [enriched Dim_Associate] - CURRENT fn/am/mgr/pos/tower/hire
#   D_FN_META [per-function maturity] - full | qa | prod | uc
#   D_HIST    {id:{field:[{v,until}]}} - movement history, display-only
# ==========================================================================
$FN_KEYS = @{
    'Cash Control'          = 'cash-control'
    'COB'                   = 'cob'
    'Collections'           = 'collections'
    'DISPUTE TRIAGE'        = 'dispute-triage'
    'Disputes and Intakes'  = 'disputes-intakes'
    'IQT'                   = 'iqt'
    'NON COB'               = 'non-cob'
    'Prepay'                = 'prepay'
}
$FN_LABEL = @{}; foreach ($k in $FN_KEYS.Keys) { $FN_LABEL[$FN_KEYS[$k]] = $k }
$fnById   = @{}
$fnByName = @{}
$dimRows  = [System.Collections.ArrayList]::new()   # enriched Dim_Associate
$rosterRead = $false
if (Test-Path $ROSTER) {
    $rxl = $null; $rb = $null
    try {
        $rxl = New-Object -ComObject Excel.Application
        $rxl.Visible = $false; $rxl.DisplayAlerts = $false
        $rxl.ScreenUpdating = $false; $rxl.EnableEvents = $false
        $rb  = $rxl.Workbooks.Open($ROSTER, 0, $true)
        $rws = $rb.Worksheets.Item("Table1")
        $ur  = $rws.UsedRange.Value2
        for ($rr = 2; $rr -le $ur.GetLength(0); $rr++) {
            $rid = "$($ur[$rr,1])".Trim()
            $rnm = "$($ur[$rr,2])".Trim()
            $ram = "$($ur[$rr,3])".Trim()
            $rfn = "$($ur[$rr,4])".Trim()
            $rmg = "$($ur[$rr,5])".Trim()
            $rps = "$($ur[$rr,6])".Trim()
            $rtw = "$($ur[$rr,7])".Trim()
            $rhd = "$($ur[$rr,8])".Trim()
            if ($rid -and $FN_KEYS.ContainsKey($rfn)) {
                $fnKey = $FN_KEYS[$rfn]
                $fnById[$rid] = $fnKey
                if ($rnm) { $fnByName[$rnm] = $fnKey }
                $null = $dimRows.Add([PSCustomObject]@{
                    id=$rid; n=$rnm; fn=$fnKey; am=$ram; mgr=$rmg
                    pos=$rps; tower=$rtw; hire=$rhd
                })
            }
        }
        $rosterRead = $true
        Log ("  D_FN: " + $fnById.Count + " associates mapped from roster") Green
    } catch {
        Log "  [WARN] Roster read failed: $($_.Exception.Message)" Yellow
        Log "  D_FN will be empty - app falls back to unclassified." Yellow
    } finally {
        if ($rb)  { $rb.Close($false) }
        if ($rxl) { $rxl.Quit(); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($rxl) }
    }
} else {
    Log "  [WARN] Roster not found: $ROSTER" Yellow
    Log "  D_FN will be empty - app falls back to unclassified." Yellow
}

# -- fnOf mirror: id -> exact name -> unique-last-name+first-token ----------
$fnLastIdx = @{}
foreach ($n in $fnByName.Keys) {
    $last = ($n -split ',')[0].Trim().ToLower()
    if (-not $fnLastIdx.ContainsKey($last)) { $fnLastIdx[$last] = [System.Collections.ArrayList]::new() }
    $null = $fnLastIdx[$last].Add(@($n, $fnByName[$n]))
}
function FnOfRow($id, $name) {
    if ($id -and $fnById.ContainsKey($id)) { return $fnById[$id] }
    $nm = "$name".Trim()
    if ($nm -and $fnByName.ContainsKey($nm)) { return $fnByName[$nm] }
    if (-not $nm) { return 'un' }
    $cand = $fnLastIdx[($nm -split ',')[0].Trim().ToLower()]
    if ($cand -and $cand.Count -eq 1) {
        $tok  = (($nm -split ',')[1]).Trim().Split(' ')[0]
        $ctok = (($cand[0][0] -split ',')[1]).Trim().Split(' ')[0]
        if ($tok -and $tok -eq $ctok) { return $cand[0][1] }
    }
    return 'un'
}

# -- D_FN_META: per-function maturity (full | qa | prod | uc) ---------------
# QA exists in source system but not yet in the Fact_QA extract (reported volumes)
$FN_QA_SRC = @{ 'cob'=1461; 'iqt'=1144; 'non-cob'=4012; 'prepay'=2194 }
$fnMeta = @()
foreach ($k in $FN_KEYS.Values | Sort-Object -Unique) {
    $members = @($dimRows | Where-Object { $_.fn -eq $k })
    # Prod rows = DI Consolidated tracker = D&I work regardless of roster fn
    $p = if ($k -eq 'disputes-intakes') { $prodRows.Count } else { 0 }
    $q = 0
    foreach ($r in $qaRows) { if ((FnOfRow $r.id $r.a) -eq $k) { $q += [Math]::Max(1,$r.cnt) } }
    $qSrc = $FN_QA_SRC[$k]
    $state = if ($p -and $q) { 'full' } elseif ($q -or $qSrc) { 'qa' } elseif ($p) { 'prod' } else { 'uc' }
    $fnMeta += [ordered]@{
        key=$k; name=$FN_LABEL[$k]
        state=$state; prod=$p; qa=$q; qa_src=$qSrc; assoc=$members.Count
        ams=@($members | Select-Object -ExpandProperty am -Unique | Where-Object { $_ } | Sort-Object)
        mgrs=@($members | Select-Object -ExpandProperty mgr -Unique | Where-Object { $_ } | Sort-Object)
    }
}
Log "  D_FN_META: " + (($fnMeta | ForEach-Object { "$($_.key)=$($_.state)" }) -join ', ') Gray

# -- Unclassified diagnostic ------------------------------------------------
$fnUnNames = @{}
foreach ($r in $prodRows) {
    $n = $r.a
    if (-not $n -or (FnOfRow $null $n) -ne 'un') { continue }
    $fnUnNames[$n] = ($fnUnNames[$n] + 1)
}
$fnUnIds = @($assocRows | Where-Object { $_.id -and -not $fnById.ContainsKey($_.id) })
[ordered]@{
    generated        = (Get-Date -Format 'yyyy-MM-dd HH:mm')
    rosterFound      = $rosterRead
    rosterMapped     = $fnById.Count
    unclassifiedProd = ($fnUnNames.GetEnumerator() | ForEach-Object { @{ name = $_.Key; rows = $_.Value } })
    unclassifiedIds  = ($fnUnIds | ForEach-Object { @{ id = $_.id; name = $_.n } })
} | ConvertTo-Json -Depth 4 | Set-Content "$SYS_DIR\fn_unclassified.json" -Encoding UTF8
Log ("  Unclassified: " + $fnUnNames.Count + " prod names, " + $fnUnIds.Count + " assoc ids  (_system\fn_unclassified.json)") Yellow

# -- Associate movement history (D_HIST) -------------------------------------
# assoc_history.csv accumulates fn/am/mgr changes detected between roster
# snapshots. Current assignment (D_DIM) always wins; history is display-only.
$HIST_CSV = "$SYS_DIR\assoc_history.csv"
$PREV_CSV = "$SYS_DIR\roster_prev.csv"
$histRows = [System.Collections.ArrayList]::new()
if (Test-Path $HIST_CSV) {
    Import-Csv $HIST_CSV | ForEach-Object { $null = $histRows.Add($_) }
}
if (Test-Path $PREV_CSV) {
    $prev = @{}
    Import-Csv $PREV_CSV | ForEach-Object { $prev[$_.'ASSOCIATE OPR ID'.Trim()] = $_ }
    $today = Get-Date -Format 'yyyy-MM-dd'
    $newMoves = 0
    foreach ($d in $dimRows) {
        $p = $prev[$d.id]
        if (-not $p) { continue }
        $checks = @(
            @{ fld='fn';  old=$FN_KEYS["$($p.Function)".Trim()];    new=$d.fn },
            @{ fld='am';  old="$($p.'Assistant Manager')".Trim(); new=$d.am },
            @{ fld='mgr'; old="$($p.Manager)".Trim();             new=$d.mgr }
        )
        foreach ($c in $checks) {
            if ($c.old -and $c.new -and $c.old -ne $c.new) {
                $exists = $histRows | Where-Object {
                    $_.id -eq $d.id -and $_.field -eq $c.fld -and $_.prev -eq $c.old -and $_.until -eq $today }
                if (-not $exists) {
                    $null = $histRows.Add([PSCustomObject]@{ id=$d.id; n=$d.n; field=$c.fld; prev=$c.old; until=$today })
                    $newMoves++
                }
            }
        }
    }
    if ($newMoves -gt 0) { Log "  D_HIST: $newMoves workforce movement(s) recorded" Yellow }
}
$histRows | Export-Csv $HIST_CSV -NoTypeInformation -Encoding UTF8
# Snapshot current roster for next-run diffing
$dimRows | ForEach-Object {
    [PSCustomObject]@{
        'ASSOCIATE OPR ID'=$_.id; 'ASSOCIATES'=$_.n; 'Assistant Manager'=$_.am
        'Function'=$FN_LABEL[$_.fn]
        'Manager'=$_.mgr; 'POSITION'=$_.pos; 'TOWER'=$_.tower; 'HIRE DATE'=$_.hire
    }
} | Export-Csv $PREV_CSV -NoTypeInformation -Encoding UTF8

# -- Emit roster-driven constants -------------------------------------------
$fnJs = @{ byId = $fnById; byName = $fnByName } | ConvertTo-Json -Compress -Depth 3
[void]$sb.Append("const D_FN=$fnJs;`n")

$dimJs = $dimRows | ConvertTo-Json -Compress -Depth 2
if ($dimRows.Count -eq 1) { $dimJs = "[$dimJs]" }
[void]$sb.Append("const D_DIM=$dimJs;`n")

[void]$sb.Append("const D_FN_META=" + ($fnMeta | ConvertTo-Json -Compress -Depth 3) + ";`n")

$histById = @{}
foreach ($h in $histRows) {
    if (-not $histById.ContainsKey($h.id)) { $histById[$h.id] = @{} }
    if (-not $histById[$h.id].ContainsKey($h.field)) { $histById[$h.id][$h.field] = @() }
    $histById[$h.id][$h.field] += @{ v=$h.prev; until=$h.until }
}
[void]$sb.Append("const D_HIST=" + ($histById | ConvertTo-Json -Compress -Depth 4) + ";`n")

[System.IO.File]::WriteAllText("$DASH_DIR\orbit-data.js", $sb.ToString(), [System.Text.Encoding]::UTF8)
Mark-Time "orbit-data.js write (raw)"

# ── Roster-authoritative D_QA enrichment ─────────────────────
# enrich_data.py re-reads D_QA from orbit-data.js, joins every row to
# the roster by ASSOCIATE OPR ID, and rewrites:
#   D_QA[a]      -> official roster name  (never raw QA-system name)
#   D_QA[fn]     -> function key (pre-attached; fnOf() checks this first)
#   D_QA[am/mgr/pos/tower] -> roster values
# Also refreshes D_FN, D_DIM, D_FN_META, D_HIST (roster_prev diff).
Log "  Enriching D_QA rows from roster (OPR ID join)..." Gray
$pyOut = & python -X utf8 "$SYS_DIR\enrich_data.py" 2>&1
if ($LASTEXITCODE -eq 0) {
    foreach ($line in $pyOut) { Log ("    " + $line) Gray }
    Log "  D_QA enrichment complete." Green
} else {
    foreach ($line in $pyOut) { Log ("  [WARN] enrich: " + $line) Yellow }
    Log "  [WARN] enrich_data.py exited $LASTEXITCODE  -  orbit-data.js may be unenriched." Yellow
}
Mark-Time "enrich_data.py (roster join)"

$newSize = (Get-Item "$DASH_DIR\orbit-data.js").Length
$newRows = $prodRows.Count
Log ("  orbit-data.js: " + [Math]::Round($newSize/1KB,1) + " KB") Green
Log ("  D_PROD rows: $prevRows -> $newRows  (delta: +$($newRows - $prevRows))") $(if(($newRows-$prevRows) -ge 0){"Green"}else{"Yellow"})

# ════════════════════════════════════════════════════════════════
# STEP 4  -  Verify ORBIT DASH deployment folder
# ════════════════════════════════════════════════════════════════
Log "STEP 4: Verifying deployment folder..." Cyan

# All files are written directly to ORBIT DASH  -  no copy needed.
# Just verify all required runtime files are present.
$required = @(
    "ORBIT.html","orbit.css","orbit-app.js","orbit-data.js","chart.umd.min.js",
    "assets\logos\carelon.png","assets\logos\ignite.png","assets\logos\pi.png",
    "assets\logos\orbit-symbol.svg","assets\logos\orbit-logo-lockup.svg"
)
$missing = 0
foreach ($f in $required) {
    $p = "$DASH_DIR\$f"
    if (Test-Path $p) {
        Log ("  [OK]  $f  (" + [Math]::Round((Get-Item $p).Length/1KB,1) + " KB)") Gray
    } else {
        Log ("  [MISSING]  $f") Red
        $missing++
    }
}
if ($missing -eq 0) {
    Log "  All deployment files verified. $(Elapsed)" Green
} else {
    Log "  WARNING: $missing file(s) missing from deployment folder." Yellow
}

# ── Application-file integrity guard ──────────────────────────
# Confirm ORBIT.html / orbit-app.js / orbit.css were NOT modified
# by this refresh run (hashes compared against STEP 0 snapshot).
$appTouched = @()
foreach ($f in $APP_FILES) {
    $p = "$DASH_DIR\$f"
    if ((Test-Path $p) -and $appHashBefore.ContainsKey($f)) {
        if ((Get-FileHash $p -Algorithm SHA256).Hash -ne $appHashBefore[$f]) {
            $appTouched += $f
        }
    }
}
if ($appTouched.Count -eq 0) {
    Log "  Integrity check PASSED: application files untouched (data-only refresh)." Green
} else {
    Log "  INTEGRITY WARNING: these app files changed during refresh: $($appTouched -join ', ')" Red
    Log "  Restore from backup: _system\BACKUP\$(Split-Path $backupDir -Leaf)" Red
}

# ════════════════════════════════════════════════════════════════
# STEP 5  -  Git commit + push -> GitHub Pages auto-publishes
#
# Stages ALL tracked deployment files that have changed:
#   orbit-data.js   orbit-auth.js          (generated on every refresh)
#   ORBIT.html      orbit-app.js  orbit.css (committed only when edited)
#
# Commit message reflects what actually changed:
#   "data: refresh ..."             -  data files only
#   "data + code: refresh ..."      -  data files + one or more app files
#   "code: ..."                     -  app files only (manual push scenario)
#
# If nothing has changed since the last commit, step is skipped silently.
# ════════════════════════════════════════════════════════════════
Log "STEP 5: Publishing via git -> GitHub -> Vercel..." Cyan

if (-not (Test-Path $GIT)) {
    Log "  [SKIP] git not found at: $GIT" Yellow
    Log "  Install Git for Windows and re-run to enable auto-publish." Yellow
} else {
    # Deploy beacon: version.json lets us verify the live deployment
    # actually picked up this refresh (staleness detector).
    $refreshStamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
    $verJson = @{
        refreshed = $refreshStamp
        prodRows  = $newRows
        maxDate   = $maxDate
    } | ConvertTo-Json -Compress
    [System.IO.File]::WriteAllText("$DASH_DIR\version.json", $verJson, [System.Text.Encoding]::UTF8)

    # Stage all deployment artifacts (git ignores files that haven't changed)
    $filesToStage = @(
        "version.json",
        "orbit-data.js",
        "orbit-auth.js",
        "ORBIT.html",
        "orbit-app.js",
        "orbit.css"
    )
    & $GIT -C $DASH_DIR add @filesToStage 2>&1 | ForEach-Object { if ($_) { Log "  git: $_" Gray } }

    # Determine what is actually staged to build an accurate commit message
    $staged     = & $GIT -C $DASH_DIR diff --name-only --cached 2>&1
    $dataFiles  = @("orbit-data.js","orbit-auth.js")
    $codeFiles  = @("ORBIT.html","orbit-app.js","orbit.css")
    $hasData    = ($staged | Where-Object { $dataFiles -contains $_ }).Count -gt 0
    $hasCode    = ($staged | Where-Object { $codeFiles -contains $_ }).Count -gt 0
    $codeList   = ($staged | Where-Object { $codeFiles -contains $_ }) -join ", "

    if ($staged) {
        $dataDate  = if ($maxDate) { $maxDate } else { (Get-Date -Format 'yyyy-MM-dd') }

        if ($hasData -and $hasCode) {
            $commitMsg = "data + code: refresh $dataDate ($newRows prod rows) [$codeList]"
        } elseif ($hasData) {
            $commitMsg = "data: refresh $dataDate ($newRows prod rows)"
        } else {
            $commitMsg = "code: publish $dataDate [$codeList]"
        }

        & $GIT -C $DASH_DIR commit -m $commitMsg 2>&1 | ForEach-Object { Log "  $_" Gray }
        Mark-Time "git commit"

        if ($LASTEXITCODE -eq 0) {
            Log "  Committed: $commitMsg" Green
            & $GIT -C $DASH_DIR push origin main 2>&1 | ForEach-Object { Log "  $_" Gray }
            Mark-Time "git push"
            if ($LASTEXITCODE -eq 0) {
                Log "  Pushed to GitHub. Pages will update within ~60 seconds." Green
                Log "  Live URL: $ORBIT_URL" Cyan

                # ── STEP 5b: mirror to SharePoint copy (Folder B) ─────────────
                # B is a read-only clone. git pull --ff-only updates it to
                # origin/main and REFUSES if B has diverged  -  that refusal is
                # the drift detector (means someone ran refresh inside B).
                Log "  Syncing SharePoint mirror (Folder B)..." Cyan
                if (Test-Path "$MIRROR_DASH\.git") {
                    & $GIT -C $MIRROR_DASH fetch origin 2>&1 | ForEach-Object {
                        if ($_) { Log "    git: $_" Gray }
                    }
                    & $GIT -C $MIRROR_DASH pull --ff-only origin main 2>&1 |
                        ForEach-Object { if ($_) { Log "    git: $_" Gray } }
                    if ($LASTEXITCODE -eq 0) {
                        Log "  Mirror updated to origin/main." Green
                    } else {
                        Log "  [DRIFT] Mirror pull failed (non-fast-forward)." Red
                        Log "  Folder B has diverged - someone committed inside it." Red
                        Log "  Inspect: git -C `"$MIRROR_DASH`" log --oneline -5" Yellow
                    }
                } else {
                    Log "  [SKIP] Mirror clone not found at $MIRROR_DASH" Yellow
                }

                # Root-level source files (workbooks + scripts) - copy A -> B
                # only when the hash differs. Keeps the mirror inputs aligned.
                foreach ($rf in $MIRROR_ROOT_FILES) {
                    $pa = Join-Path (Split-Path $DASH_DIR -Parent) $rf
                    $pb = Join-Path $MIRROR_ORBIT $rf
                    if ((Test-Path $pa) -and (Test-Path $MIRROR_ORBIT)) {
                        $need = -not (Test-Path $pb) -or
                                ((Get-FileHash $pa).Hash -ne (Get-FileHash $pb).Hash)
                        if ($need) {
                            Copy-Item $pa $pb -Force
                            Log "    Mirrored root file: $rf" Gray
                        }
                    }
                }

                # ── STEP 5c: Vercel deploy trigger + freshness verification ──
                # If a Deploy Hook URL exists in _system\vercel_hook.txt
                # (gitignored, not committed), fire it so deployment does not
                # depend on the Git->Vercel integration staying connected.
                if (Test-Path $VERCEL_HOOK_FILE) {
                    $hook = (Get-Content $VERCEL_HOOK_FILE -Raw).Trim()
                    if ($hook -match '^https://') {
                        try {
                            Invoke-RestMethod -Uri $hook -Method Post -TimeoutSec 20 | Out-Null
                            Log "  Vercel deploy hook fired." Green
                        } catch {
                            Log "  [WARN] Deploy hook call failed: $($_.Exception.Message)" Yellow
                        }
                    }
                }

                # Poll the live deployment until version.json matches this
                # refresh (or timeout). This is the staleness guarantee.
                Log "  Verifying Vercel picked up this refresh..." Cyan
                $live = $false
                for ($i = 0; $i -lt 12 -and -not $live; $i++) {
                    Start-Sleep -Seconds 20
                    try {
                        $vj = Invoke-RestMethod "$ORBIT_BASE/version.json?ts=$([DateTime]::Now.Ticks)" `
                              -UseBasicParsing -TimeoutSec 20 -ErrorAction Stop
                        if ($vj.refreshed -eq $refreshStamp) { $live = $true }
                    } catch { }
                }
                if ($live) {
                    Log "  VERIFIED: Vercel is serving refresh $refreshStamp." Green
                } else {
                    Log "  [STALE] Vercel did not update within 4 minutes." Red
                    Log "  Check Vercel project -> Git integration, or create a" Red
                    Log "  Deploy Hook and save it to _system\vercel_hook.txt" Yellow
                    Log "  Fallback live copy: $PAGES_URL" Yellow
                }
            } else {
                Log "  [WARN] Push failed. Changes committed locally; push manually." Yellow
                Log "  Run: git -C `"$DASH_DIR`" push origin main" Yellow
            }
        } else {
            Log "  [WARN] git commit failed. Check output above." Yellow
        }
    } else {
        Log "  Nothing changed since last commit - skipping." Gray
    }
}

# ════════════════════════════════════════════════════════════════
# ── Timing profile ──────────────────────────────────────────
Mark-Time "TOTAL (before browser open)"
Show-Profile

# STEP 6  -  Open / reload ORBIT.html in the default browser
# ════════════════════════════════════════════════════════════════
Log "STEP 6: Opening ORBIT in browser..." Cyan

# If Edge has ORBIT open, send F5 to reload; otherwise open fresh
$edgeProc = Get-Process msedge -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -match "ORBIT" } |
    Select-Object -First 1

if ($edgeProc) {
    Add-Type -AssemblyName Microsoft.VisualBasic
    [Microsoft.VisualBasic.Interaction]::AppActivate($edgeProc.Id)
    Start-Sleep -Milliseconds 400
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.SendKeys]::SendWait("{F5}")
    Log "  ORBIT tab reloaded (F5 sent to Edge)." Green
} else {
    Start-Process $ORBIT_URL
    Log "  ORBIT opened in default browser (Vercel production URL)." Green
}

# ════════════════════════════════════════════════════════════════
# DONE
# ════════════════════════════════════════════════════════════════
$total = [int]((Get-Date) - $T0).TotalSeconds
$delta = $newRows - $prevRows
Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  ORBIT REFRESH + PUBLISH COMPLETE" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ("  Max date   : $maxDate  (serial $maxSerial)") -ForegroundColor Green
Write-Host ("  D_PROD rows: $newRows  (+$delta new)") -ForegroundColor Green
Write-Host ("  Duration   : ${total}s") -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  DATA IS LIVE on Vercel (verified via version.json beacon)." -ForegroundColor Cyan
Write-Host "  GitHub Pages fallback: $PAGES_URL" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Live URL:" -ForegroundColor Yellow
Write-Host "  $ORBIT_URL" -ForegroundColor White
Write-Host ""
