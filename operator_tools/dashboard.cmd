@echo off
REM DOPEY operator dashboard - localhost-only (127.0.0.1:8787) paper-research
REM console: start/stop the supervisor, watch the paper book, targets, record,
REM readiness gate. No broker wiring; no order can be placed from this page.
setlocal
set ROOT=%~dp0..
cd /d "%ROOT%"
start "" http://127.0.0.1:8787
"%ROOT%\.venv\Scripts\python.exe" -m dopey_dashboard.operator_dashboard
endlocal
