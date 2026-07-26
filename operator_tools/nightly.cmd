@echo off
REM DOPEY nightly effectiveness harness - scheduled ~02:00 daily, clear of the
REM 16:45 ritual. Full regression suite + stack-stability + fitness-determinism.
setlocal
set ROOT=%~dp0..
cd /d "%ROOT%"
"%ROOT%\.venv\Scripts\python.exe" operator_tools\operator_nightly.py >> "%ROOT%\artifacts\dopey\nightly\nightly_console.log" 2>&1
set NIGHTLY_RC=%errorlevel%
endlocal & exit /b %NIGHTLY_RC%
