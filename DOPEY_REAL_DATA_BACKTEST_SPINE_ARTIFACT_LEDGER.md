# DOPEY Real-Data Backtest Spine Artifact Ledger

## Source Files

- `dopey_data/history_models.py`
- `dopey_data/history_store.py`
- `dopey_data/history_validator.py`
- `dopey_data/run_history_dataset_validation.py`
- `dopey_data/history/history_dataset_manifest.json`
- `dopey_data/fixtures/history/sample_history_dataset_manifest.json`
- `tests/test_real_data_backtest_spine.py`

## Output Artifacts

- `artifacts/dopey/history/history_dataset_manifest.json`
- `artifacts/dopey/history/history_dataset_validation.json`
- `artifacts/dopey/history/history_symbol_coverage.jsonl`
- `artifacts/dopey/history/history_quality_flags.jsonl`
- `artifacts/dopey/history/history_loader_proof.jsonl`
- `artifacts/dopey/history/history_spine_summary.json`

## Integration Surfaces

- audit artifact loader recognizes all history artifacts
- reporting bundle exposes `history_spine_summary`
- export selector includes history artifacts and report docs
- export review packet renders the history spine summary
- validation stabilizer includes `tests/test_real_data_backtest_spine.py`

## Current Dataset Result

- dataset_status: `missing_real_dataset`
- reason: no operator-supplied local historical OHLCV files are present under `dopey_data/history/raw/`
- fake real-data pass allowed: `false`

## Session Copy

- shared copy root: `Z:\DOPEY_REAL_DATA_BACKTEST_SPINE_20260705-125542`
- copy manifest: `Z:\DOPEY_REAL_DATA_BACKTEST_SPINE_20260705-125542\SESSION_COPY_MANIFEST.json`
- copied files: `9`
