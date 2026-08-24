@echo off
chcp 65001 > nul
setlocal

REM ============================================================
REM   MUAM (三菱UFJ) Daily Snapshot Sync
REM
REM   The GitHub Actions job collects 野村 and 大和 automatically,
REM   but MUAM's API returns 403 Forbidden to GitHub's overseas
REM   servers. It answers a Japanese connection fine, so this
REM   machine collects that one manager and publishes it.
REM
REM   Double-click to run by hand, or let the scheduled task
REM   "MUAM Daily Snapshot" run it (which passes "nopause").
REM ============================================================

cd /d "%~dp0"
if not exist "logs" mkdir "logs"
set "LOG=logs\muam_sync.log"

echo. >> "%LOG%"
echo ===== %DATE% %TIME% ===== >> "%LOG%"
echo   MUAM Daily Snapshot Sync
echo   Collecting from 三菱UFJアセットマネジメント...

set "PYTHONPATH=."
.venv\Scripts\python.exe scripts\daily_snapshot.py --only muam >> "%LOG%" 2>&1
if errorlevel 1 (
    echo   [FAILED] Could not collect MUAM data. See %LOG%
    echo   RESULT: collection FAILED >> "%LOG%"
    goto :done
)
echo   [OK] Snapshot collected.

REM Publish. Commit first so a git problem never loses the data --
REM these APIs only serve today's value, so a lost day is permanent.
git add data/timeseries/ >> "%LOG%" 2>&1
git diff --staged --quiet
if errorlevel 1 (
    git commit -m "chore(data): append MUAM daily snapshot [skip ci]" >> "%LOG%" 2>&1
    echo   [OK] Committed.
) else (
    echo   [--] Already up to date for today; nothing to commit.
    echo   RESULT: no new data >> "%LOG%"
    goto :done
)

REM Rebase onto anything the GitHub bot pushed, then publish.
git pull --rebase origin main >> "%LOG%" 2>&1
if errorlevel 1 (
    echo   [WARN] Could not sync with GitHub. Data is saved locally
    echo          and will publish on the next successful run.
    echo   RESULT: pull failed, commit held locally >> "%LOG%"
    goto :done
)

git push origin main >> "%LOG%" 2>&1
if errorlevel 1 (
    echo   [WARN] Push failed. Data is committed locally and will
    echo          publish on the next successful run.
    echo   RESULT: push failed, commit held locally >> "%LOG%"
    goto :done
)
echo   [OK] Published to GitHub.
echo   RESULT: success >> "%LOG%"

:done
echo.
echo   Log: %LOG%
if /i not "%~1"=="nopause" pause
endlocal
