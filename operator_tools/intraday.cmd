@echo off
REM DOPEY intraday watch - scheduled hourly; the script self-gates to regular
REM trading hours (RTH, US/Eastern) and no-ops otherwise. Read-only planning:
REM places no orders, sets no limit orders, makes no paper entries.
setlocal
set ROOT=%~dp0..
cd /d "%ROOT%"
"%ROOT%\.venv\Scripts\python.exe" operator_tools\operator_intraday.py >> "%ROOT%\artifacts\dopey\intraday\intraday_console.log" 2>&1
endlocal
