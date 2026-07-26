# DOPEY Real-Data Backtest Spine Report

Bundle: `DOPEY_REAL_DATA_BACKTEST_SPINE_V1`

## Status

- dataset_status: `missing_real_dataset`
- real local data found: `false`
- row_count: `0`
- symbols_covered: `[]`
- date_range: `{start_date: "", end_date: ""}`
- validator: `dopey-history-dataset-validator-v1`

## What Was Built

DOPEY now has an offline local daily OHLCV history-data spine for liquid optionable underlyings and market context.

The spine supports CSV and JSONL files under `dopey_data/history/raw/`, pinned by SHA-256 in `dopey_data/history/history_dataset_manifest.json`. It validates dates, required columns, duplicate symbol/date rows, OHLC integrity, nonnegative volume, positive adjusted close, symbol coverage, date coverage, missing weekdays, stale or missing symbols, file hashes, and manifest reproducibility.

No real dataset is bundled. The placeholder manifest records the expected schema only and produces `missing_real_dataset` until operator-supplied local files and hashes are added.

## Required Universe

`SPY`, `QQQ`, `IWM`, `DIA`, `AAPL`, `MSFT`, `NVDA`, `AMD`, `TSLA`, `META`, `AMZN`, `GOOGL`, `NFLX`, `JPM`, `BAC`, `XLF`, `XLK`, `XLE`, `XLY`, `XLI`, `XLU`, `XLP`, `XLV`, `VIX`

## Safety State

- broker_connection: `none`
- credentials_used: `false`
- live_trading_enabled: `false`
- scheduler_created: `false`
- real_sizing_created: `false`
- order_execution_created: `false`

## Next Target

`DOPEY_MODEL_REPRICER_V1`

## Session Validation

- `python -m pytest tests/test_real_data_backtest_spine.py -q`: `21 passed`
- broker detector safety tests: passed
- pre-run safety scanner tests: passed
- active lifecycle simulator tests: passed
- active policy tests: passed after sequential artifact repair
- `python -m dopey_data.run_history_dataset_validation`: `missing_real_dataset`
- audit/report/export/review smokes: passed with live trading blocked
- validation stabilizer: `inconclusive_timeout`, `timeout_recorded_as_pass=false`
- `python -m pytest --collect-only -q`: `2754 tests collected`
- `python -m pytest`: `inconclusive_timeout` after 360.037 seconds, not counted as pass
- shared copy: `Z:\DOPEY_REAL_DATA_BACKTEST_SPINE_20260705-125542`
