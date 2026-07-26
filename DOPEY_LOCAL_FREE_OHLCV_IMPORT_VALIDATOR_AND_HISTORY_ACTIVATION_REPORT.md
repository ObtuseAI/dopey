# DOPEY Local Free OHLCV Import Validator And History Activation Report

## Objective
Build the local-only free/public OHLCV validation, provenance, history activation, and real signal pass/block path.

## Alpha Vantage Exclusion
- Alpha Vantage, API-key handling, credential setup, endpoint detection, and fetcher code are excluded.

## Local OHLCV Inventory
- real_data_files_present: `false`

## Schema Validator
- Validates CSV/JSONL daily OHLCV, market context, and corporate actions schemas.

## Quality Validator
- Blocks bad dates, future dates, SAMPLE_ONLY, sample_only, not_real_data, bad OHLC, bad volume, duplicates, credentials, broker/live/order/scheduler, and real-sizing markers.

## License And Provenance Validator
- Requires reviewed license, provenance, source/provider, manifest references, file hashes, and safety assertions.

## Import Decision And Fix Advisor
- local_ohlcv_status: `missing_local_ohlcv_files`
- local_ohlcv_import_decision: `blocked_missing_local_ohlcv`
- local_ohlcv_fix_advice_status: `manual_staging_required`

## Manual Staging Instructions
- See `DOPEY_MANUAL_FREE_OHLCV_STAGING_INSTRUCTIONS.md` and `DOPEY_MANUAL_REAL_OHLCV_STAGING_INSTRUCTIONS.md`.

## Free/Open Data Provenance Gate
- free_data_candidate_count: `8`
- free_data_evidence_allowed_count: `0`

## History Spine Activation Gate
- history_spine_activation_status: `blocked_missing_local_ohlcv`
- real_history_used: `false`

## Real Signal Validation Gate
- real_signal_validation_status: `blocked_missing_valid_real_history`
- real_signal_evidence: `false`

## Combined Stack Summary
- valid_real_dataset: `false`
- validation pass is not options evidence, profitability, or live readiness.

## Safety State
- network_fetch_performed: `false`
- credentials_created: `false`
- env_created: `false`
- broker_connection_used: `false`
- strategy_promotion_allowed: `false`
- paper_only: `true`
- live_blocked: `true`

## Validation Summary
- `python -m pytest tests/test_local_free_ohlcv_import_validator_and_history_activation.py -q`: `9 passed`.
- Requested targeted pytest lanes passed: real data ingestion plan, fitness, statistical truth, honest backtester, real signal engines, model repricer, real data backtest spine, active option lifecycle, active policy integration, and active trading policy.
- Stack smokes passed for local OHLCV validator, free data provenance gate, history activation, real signal validation, real data ingestion plan, fitness, statistical truth, honest backtester, real signal engines, model repricer, history dataset validation, offline audit rerun, reporting, export review, and full-suite stabilizer.
- `python -m dopey_export.run_artifact_compaction_export_verifier`: `inconclusive_timeout` at the local 180 second cap; not counted as pass.
- `python -m pytest --collect-only`: `2936 tests collected`.
- `python -m pytest`: `inconclusive_timeout` at the local 300 second cap while in `tests/test_artifact_compaction_export_verifier.py`; not counted as pass.
- Full-suite stabilizer recorded `full_suite_status=inconclusive_timeout` and `timeout_recorded_as_pass=false`.
- Reports were copied to `C:\Users\chris\Desktop\Shared Folder\DOPEY_LOCAL_FREE_OHLCV_IMPORT_VALIDATOR_AND_HISTORY_ACTIVATION_STACK_V1`.

## Known Gaps
- No real OHLCV files are present unless an operator manually stages reviewed files.
- OHLCV evidence is not options evidence and does not establish profitability.

## Next Target
- `DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1`
