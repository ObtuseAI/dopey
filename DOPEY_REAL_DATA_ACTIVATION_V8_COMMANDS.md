# DOPEY Real Data Activation V8 Commands

All commands use the repo venv Python from the repo root:
`C:\Users\CH\dopey\.venv\Scripts\python`

## Data staging (operator lane, rerun only to refresh data)

1. Fetch outside the repo (operator script, not a DOPEY module) and stage cleaned CSVs into:
   - `dopey_data/real/raw/daily_ohlcv/` (equities/ETFs) and `dopey_data/real/raw/market_context/` (VIX)
   - `dopey_data/history/raw/` (all 24 symbols)
2. `python -m dopey_data_ingestion.run_manual_ohlcv_manifest_draft`
3. Finalize `dopey_data/real/manifests/real_data_manifest.json` (license/provenance/hashes) and
   `dopey_data/history/history_dataset_manifest.json` (sha256 pins).

## Validation gates

- `python -m dopey_data.run_history_dataset_validation`
- `python -m dopey_data_ingestion.run_local_free_ohlcv_validation_and_activation_stack`

## Real-history honest lane (order matters)

1. `python -m dopey_analysis.run_real_history_signal_engine`
2. `python -m dopey_backtest.run_real_history_honest_backtester`
3. `python -m dopey_stats.run_statistical_truth_layer`
4. `python -m dopey_fitness.run_fitness_function_replacement`

Note: running the fixture-lane runners (`dopey_analysis.run_real_signal_engines`,
`dopey_backtest.run_honest_backtester`) or their test suites overwrites the shared artifact
files with fixture-lane output; rerun the four commands above to restore the real-data state.

## Targeted tests

- `python -m pytest tests/test_real_history_lane.py -q`
- `python -m pytest tests/test_local_free_ohlcv_import_validator_and_history_activation.py -q`
- `python -m pytest tests/test_public_signal_research_breakthrough_v7.py -q`
- `python -m pytest tests/test_real_signal_engines.py tests/test_honest_backtester.py -q`
- `python -m pytest tests/test_statistical_truth_layer.py tests/test_fitness_function_replacement.py -q`
