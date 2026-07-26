@echo off
rem DOPEY daily ritual (operator-side automation; not part of the pipeline).
rem 1. Snapshot public option chains + earnings dates (skips weekends/holidays itself).
rem 2. Refresh the governed history validation and live-source thesis artifacts.
rem 3. Write a machine-readable heartbeat the data-freshness sentinel checks, so a
rem    silently failing scheduled task gets caught by the next supervisor run.
rem The multi-hour research supervisor has its own no-overlap research schedule. Keeping
rem it out of this market-data ritual prevents Task Scheduler timeout/orphan overlap.
rem Remove anytime: schtasks /delete /tn DOPEY_DailyRitual /f
setlocal
cd /d "%~dp0.."
set LOGFILE=operator_tools\daily_ritual.log
.venv\Scripts\python.exe -m operator_tools.operational_run_marker acquire daily_ritual >> %LOGFILE% 2>&1
if not "%errorlevel%"=="0" exit /b 2
rem cap the log: keep the previous generation once it passes ~1MB
for %%A in ("%LOGFILE%") do if %%~zA GTR 1048576 move /y "%LOGFILE%" "%LOGFILE%.old" >nul
echo ==== DOPEY daily ritual %date% %time% ==== >> %LOGFILE%
.venv\Scripts\python.exe operator_tools\operator_fetch_daily_ohlcv.py >> %LOGFILE% 2>&1
set OHLCV_RC=%errorlevel%
if not "%OHLCV_RC%"=="0" echo ==== OHLCV SPINE UPDATE FAILED rc=%OHLCV_RC% ==== >> %LOGFILE%
.venv\Scripts\python.exe -m dopey_data.run_history_dataset_validation >> %LOGFILE% 2>&1
set HISTORY_VALIDATION_RC=%errorlevel%
if not "%HISTORY_VALIDATION_RC%"=="0" echo ==== HISTORY VALIDATION FAILED rc=%HISTORY_VALIDATION_RC% ==== >> %LOGFILE%
.venv\Scripts\python.exe operator_tools\operator_fetch_option_chains.py >> %LOGFILE% 2>&1
set FETCH_RC=%errorlevel%
if not "%FETCH_RC%"=="0" echo ==== CHAIN FETCH FAILED rc=%FETCH_RC% ==== >> %LOGFILE%
.venv\Scripts\python.exe operator_tools\operator_fetch_macro_context.py >> %LOGFILE% 2>&1
set MACRO_RC=%errorlevel%
if not "%MACRO_RC%"=="0" echo ==== MACRO FETCH FAILED rc=%MACRO_RC% ==== >> %LOGFILE%
.venv\Scripts\python.exe -m operator_tools.operator_fetch_quant_context --sec-symbol-limit 250 >> %LOGFILE% 2>&1
set QUANT_CONTEXT_RC=%errorlevel%
if not "%QUANT_CONTEXT_RC%"=="0" echo ==== QUANT CONTEXT FETCH FAILED rc=%QUANT_CONTEXT_RC% ==== >> %LOGFILE%
.venv\Scripts\python.exe operator_tools\operator_fetch_cross_asset_context.py >> %LOGFILE% 2>&1
set CROSS_ASSET_RC=%errorlevel%
if not "%CROSS_ASSET_RC%"=="0" echo ==== CROSS-ASSET FETCH FAILED rc=%CROSS_ASSET_RC% ==== >> %LOGFILE%
.venv\Scripts\python.exe operator_tools\operator_fetch_news_context.py >> %LOGFILE% 2>&1
set NEWS_RC=%errorlevel%
if not "%NEWS_RC%"=="0" echo ==== NEWS FETCH FAILED rc=%NEWS_RC% ==== >> %LOGFILE%
rem Universe expansion is intentionally separate from the time-bounded market-data
rem ritual. Revalidate the final history generation immediately before consumers so
rem another governed writer can never leave settlement paired with a stale hash.
.venv\Scripts\python.exe -m dopey_data.run_history_dataset_validation >> %LOGFILE% 2>&1
set FINAL_HISTORY_VALIDATION_RC=%errorlevel%
if not "%FINAL_HISTORY_VALIDATION_RC%"=="0" echo ==== FINAL HISTORY VALIDATION FAILED rc=%FINAL_HISTORY_VALIDATION_RC% ==== >> %LOGFILE%
.venv\Scripts\python.exe -m dopey_equity_swing.run_equity_first_swing_engine >> %LOGFILE% 2>&1
set SWING_RC=%errorlevel%
if not "%SWING_RC%"=="0" echo ==== EQUITY SWING ENGINE FAILED rc=%SWING_RC% ==== >> %LOGFILE%
.venv\Scripts\python.exe -m operator_tools.update_context_decision_outcomes >> %LOGFILE% 2>&1
set CONTEXT_SETTLEMENT_RC=%errorlevel%
if not "%CONTEXT_SETTLEMENT_RC%"=="0" echo ==== CONTEXT OUTCOME SETTLEMENT FAILED rc=%CONTEXT_SETTLEMENT_RC% ==== >> %LOGFILE%
.venv\Scripts\python.exe -m operator_tools.operator_forward_evidence_cycle >> %LOGFILE% 2>&1
set FORWARD_EVIDENCE_RC=%errorlevel%
if not "%FORWARD_EVIDENCE_RC%"=="0" echo ==== FORWARD EVIDENCE CYCLE FAILED rc=%FORWARD_EVIDENCE_RC% ==== >> %LOGFILE%
.venv\Scripts\python.exe -m operator_tools.operational_run_marker release daily_ritual >> %LOGFILE% 2>&1
set RUN_MARKER_RELEASE_RC=%errorlevel%
if not "%RUN_MARKER_RELEASE_RC%"=="0" echo ==== DAILY RUN MARKER RELEASE FAILED rc=%RUN_MARKER_RELEASE_RC% ==== >> %LOGFILE%
set RITUAL_STATUS=complete
if not "%OHLCV_RC%"=="0" set RITUAL_STATUS=complete_with_failures
if not "%HISTORY_VALIDATION_RC%"=="0" set RITUAL_STATUS=complete_with_failures
if not "%FETCH_RC%"=="0" set RITUAL_STATUS=complete_with_failures
if not "%MACRO_RC%"=="0" set RITUAL_STATUS=complete_with_failures
if not "%QUANT_CONTEXT_RC%"=="0" set RITUAL_STATUS=complete_with_failures
if not "%CROSS_ASSET_RC%"=="0" set RITUAL_STATUS=complete_with_failures
if not "%NEWS_RC%"=="0" set RITUAL_STATUS=complete_with_failures
if not "%FINAL_HISTORY_VALIDATION_RC%"=="0" set RITUAL_STATUS=complete_with_failures
if not "%SWING_RC%"=="0" set RITUAL_STATUS=complete_with_failures
if not "%CONTEXT_SETTLEMENT_RC%"=="0" set RITUAL_STATUS=complete_with_failures
if not "%FORWARD_EVIDENCE_RC%"=="0" set RITUAL_STATUS=complete_with_failures
if not "%RUN_MARKER_RELEASE_RC%"=="0" set RITUAL_STATUS=complete_with_failures
if not exist artifacts\dopey\observability mkdir artifacts\dopey\observability
> artifacts\dopey\observability\ritual_heartbeat.json (
  echo {"artifact_type": "ritual_heartbeat", "ran_at_local": "%date% %time%", "ritual_status": "%RITUAL_STATUS%", "ohlcv_exit_code": %OHLCV_RC%, "initial_history_validation_exit_code": %HISTORY_VALIDATION_RC%, "option_chain_exit_code": %FETCH_RC%, "macro_exit_code": %MACRO_RC%, "quant_context_exit_code": %QUANT_CONTEXT_RC%, "cross_asset_exit_code": %CROSS_ASSET_RC%, "news_exit_code": %NEWS_RC%, "final_history_validation_exit_code": %FINAL_HISTORY_VALIDATION_RC%, "swing_exit_code": %SWING_RC%, "context_settlement_exit_code": %CONTEXT_SETTLEMENT_RC%, "forward_evidence_exit_code": %FORWARD_EVIDENCE_RC%, "run_marker_release_exit_code": %RUN_MARKER_RELEASE_RC%, "universe_growth_status": "separate_acceleration_lane", "research_supervisor_status": "separate_no_overlap_schedule"}
)
echo ==== ritual status=%RITUAL_STATUS% ohlcv_rc=%OHLCV_RC% initial_validation_rc=%HISTORY_VALIDATION_RC% final_validation_rc=%FINAL_HISTORY_VALIDATION_RC% chain_rc=%FETCH_RC% settlement_rc=%CONTEXT_SETTLEMENT_RC% %time% ==== >> %LOGFILE%
if not "%RITUAL_STATUS%"=="complete" exit /b 1
endlocal
