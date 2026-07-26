@echo off
REM DOPEY weekend soak - scheduled Sat ~10:00, markets closed. Repeated
REM full-stack runs, journal regression diffs, fitness-determinism checks.
REM NO fabricated market evidence on closed markets - stability only.
setlocal
set ROOT=%~dp0..
cd /d "%ROOT%"
if not exist "%ROOT%\artifacts\dopey\soak" mkdir "%ROOT%\artifacts\dopey\soak"
"%ROOT%\.venv\Scripts\python.exe" operator_tools\operator_weekend_soak.py >> "%ROOT%\artifacts\dopey\soak\weekend_soak_console.log" 2>&1
set SOAK_RC=%errorlevel%
endlocal & exit /b %SOAK_RC%
