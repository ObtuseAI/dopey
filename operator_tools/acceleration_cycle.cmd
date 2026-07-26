@echo off
REM DOPEY research acceleration cycle. The Python planner self-gates every
REM allowlisted lane by interval and market window. Paper-only; no broker tools.
setlocal
cd /d "%~dp0.."
"%CD%\.venv\Scripts\python.exe" -m dopey_acceleration.run_acceleration_cycle --mode execute
set RC=%errorlevel%
endlocal & exit /b %RC%
