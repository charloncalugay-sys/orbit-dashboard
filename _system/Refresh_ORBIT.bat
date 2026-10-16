@echo off
title ORBIT Refresh + Publish
echo.
echo  ================================================
echo   PROJECT ORBIT -- One-Click Refresh + Publish
echo  ================================================
echo.
echo  Step 0: Backup ORBIT.html / orbit-app.js / orbit.css
echo  Step 1: Refresh Excel data model
echo  Step 2: Export DATA_EXTRACT to CSVs
echo  Step 2.5: Export leadership roster to orbit-auth.js
echo  Step 3: Rebuild orbit-data.js  (data ONLY - app files never touched)
echo  Step 4: Verify deployment folder + integrity check
echo  Step 5: Git commit + push -> GitHub Pages auto-publishes
echo  Step 6: Reload ORBIT in browser
echo.
echo  Starting... (Excel will open briefly, then close)
echo.

powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0Refresh_ORBIT.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [ERROR] Refresh failed. Check the output above.
    pause
) else (
    echo.
    echo  Refresh complete. This window will close in 5 seconds.
    timeout /t 5 /nobreak >nul
)
