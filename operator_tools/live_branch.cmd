@echo off
rem DOPEY Live Branch production cycle. This launcher is intentionally separate
rem from every paper-research command and control surface.
setlocal
set ROOT=%~dp0..
cd /d "%ROOT%"
set LOG_DIR=artifacts\dopey\live_branch
set LOG_FILE=%LOG_DIR%\live_branch_scheduler.log
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
for %%A in ("%LOG_FILE%") do if %%~zA GTR 1048576 move /y "%LOG_FILE%" "%LOG_FILE%.old" >nul
echo ==== DOPEY Live Branch %date% %time% ==== >> "%LOG_FILE%"
"%ROOT%\.venv\Scripts\python.exe" -m operator_tools.operator_live_branch --execute >> "%LOG_FILE%" 2>&1
set LIVE_RC=%errorlevel%
echo ==== Live Branch complete rc=%LIVE_RC% %time% ==== >> "%LOG_FILE%"
exit /b %LIVE_RC%
