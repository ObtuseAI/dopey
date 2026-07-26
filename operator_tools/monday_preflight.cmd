@echo off
REM DOPEY Monday preflight - scheduled Mon ~08:30, before the open. Plumbing
REM go/no-go: data frontier, snapshot recency, lane freshness, sentinels,
REM halts, scheduler, disk. Read-only; places no orders.
setlocal
set ROOT=%~dp0..
cd /d "%ROOT%"
if not exist "%ROOT%\artifacts\dopey\preflight" mkdir "%ROOT%\artifacts\dopey\preflight"
"%ROOT%\.venv\Scripts\python.exe" operator_tools\operator_monday_preflight.py >> "%ROOT%\artifacts\dopey\preflight\monday_preflight_console.log" 2>&1
endlocal
