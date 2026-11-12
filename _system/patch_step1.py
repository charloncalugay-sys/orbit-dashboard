import os

SYS = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(SYS, 'Refresh_ORBIT.ps1')
src = open(PS1, encoding='utf-8').read()

OLD = (
    'Stop-Process -Name EXCEL -Force -ErrorAction SilentlyContinue\n'
    'Start-Sleep -Seconds 2\n'
    '\n'
    '$xl = New-Object -ComObject Excel.Application\n'
    '$xl.Visible        = $true\n'
    '$xl.DisplayAlerts  = $false\n'
    '$xl.ScreenUpdating = $false\n'
    '\n'
    '$wb = $xl.Workbooks.Open($WORKBOOK)\n'
    'Log "  Workbook open. Running RefreshAll..." Gray\n'
    'try { $wb.RefreshAll() } catch { Log ("  RefreshAll warning: " + $_.Exception.Message) Yellow }\n'
    'Start-Sleep -Seconds 10   # allow data model to fully load\n'
    '\n'
    'Log "  Waiting for background queries to settle..." Gray\n'
    'Start-Sleep -Seconds 5\n'
    'Log "  Data model refresh complete. $(Elapsed)" Green'
)

NEW = (
    'Stop-Process -Name EXCEL -Force -ErrorAction SilentlyContinue\n'
    'Start-Sleep -Seconds 2\n'
    'Mark-Time "Excel kill + wait"\n'
    '\n'
    '$xl = New-Object -ComObject Excel.Application\n'
    '$xl.Visible        = $true\n'
    '$xl.DisplayAlerts  = $false\n'
    '$xl.ScreenUpdating = $false\n'
    '\n'
    '$wb = $xl.Workbooks.Open($WORKBOOK)\n'
    'Mark-Time "Workbook open"\n'
    '\n'
    '# \u2500\u2500 Active-wait for RefreshAll \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n'
    '# RefreshAll() fires all connections asynchronously and returns\n'
    '# immediately. We poll WorkbookConnection.OLEDBConnection.Refreshing\n'
    '# every 5s until all connections finish, up to a 20-min hard cap.\n'
    '# This gives the EXACT refresh duration instead of a blind sleep.\n'
    'Log "  Issuing RefreshAll..." Gray\n'
    '$T_REFRESH_START = Get-Date\n'
    'try { $wb.RefreshAll() } catch { Log ("  RefreshAll warning: " + $_.Exception.Message) Yellow }\n'
    'Start-Sleep -Seconds 3   # brief pause before first poll\n'
    '\n'
    'Log "  Polling connections for refresh completion..." Gray\n'
    '$pollSec      = 0\n'
    '$maxPollSec   = 1200   # 20-min hard cap\n'
    '$pollInterval = 5      # seconds between polls\n'
    'do {\n'
    '    Start-Sleep -Seconds $pollInterval\n'
    '    $pollSec += $pollInterval\n'
    '    $stillRunning = @()\n'
    '    try {\n'
    '        foreach ($conn in $wb.Connections) {\n'
    '            try {\n'
    '                $ole = $conn.OLEDBConnection\n'
    '                if ($ole -ne $null -and $ole.Refreshing) { $stillRunning += $conn.Name }\n'
    '            } catch {}\n'
    '            try {\n'
    '                $pq = $conn.ODBCConnection\n'
    '                if ($pq -ne $null -and $pq.Refreshing) { $stillRunning += $conn.Name }\n'
    '            } catch {}\n'
    '        }\n'
    '    } catch {}\n'
    '    if ($stillRunning.Count -gt 0) {\n'
    '        Log ("    still refreshing ($pollSec s): " + ($stillRunning -join ", ")) DarkGray\n'
    '    }\n'
    '} while ($stillRunning.Count -gt 0 -and $pollSec -lt $maxPollSec)\n'
    '\n'
    '$refreshDur = [Math]::Round(($T_REFRESH_START - (Get-Date)).TotalSeconds * -1, 1)\n'
    'if ($pollSec -ge $maxPollSec) {\n'
    '    Log "  [WARN] RefreshAll poll timed out at ${maxPollSec}s \u2014 connections may still be loading." Yellow\n'
    '} else {\n'
    '    Log ("  All connections finished. Refresh duration: ${refreshDur}s") Green\n'
    '}\n'
    'Mark-Time "RefreshAll complete"\n'
    '\n'
    '# Extra settle time for the in-process Analysis Services engine\n'
    '# (DAX recalc runs after Power Query finishes; 5s is usually enough).\n'
    'Log "  Settling data model (DAX recalc)..." Gray\n'
    'Start-Sleep -Seconds 5\n'
    'Mark-Time "Data model settle"\n'
    'Log "  Data model refresh complete. $(Elapsed)" Green'
)

if OLD not in src:
    print('OLD string not found — checking current STEP 1...')
    idx = src.find('Stop-Process -Name EXCEL')
    print(repr(src[idx:idx+400]))
else:
    src = src.replace(OLD, NEW, 1)
    open(PS1, 'w', encoding='utf-8').write(src)
    print('STEP 1 patched successfully.')
