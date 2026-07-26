@echo off
rem Dedicated long-running paper-research supervisor. The scheduler prevents overlap,
rem while the Python supervisor's live-PID lock provides a second fail-closed guard.
setlocal
cd /d "%~dp0.."
set LOGFILE=operator_tools\research_supervisor.log
.venv\Scripts\python.exe -m operator_tools.operational_run_marker check-clear daily_ritual >> %LOGFILE% 2>&1
if not "%errorlevel%"=="0" (
  echo ==== DOPEY research supervisor deferred: daily ritual is active %date% %time% ==== >> %LOGFILE%
  exit /b 2
)
echo ==== DOPEY research supervisor start %date% %time% ==== >> %LOGFILE%
.venv\Scripts\python.exe -m dopey_autonomy.run_resilient_research_supervisor >> %LOGFILE% 2>&1
set SUPERVISOR_RC=%errorlevel%
echo ==== DOPEY research supervisor complete rc=%SUPERVISOR_RC% %date% %time% ==== >> %LOGFILE%
endlocal & exit /b %SUPERVISOR_RC%
