# DOPEY Manual Free OHLCV Staging Or Local Import Fix Report

## Objective
Build a local-only operator staging and repair path for manually supplied free/public OHLCV files.

## Alpha Vantage Exclusion
- Alpha Vantage is excluded. No Alpha Vantage candidate, API key path, fetcher, or credential workflow was added.

## No-Fetch Policy
- DOPEY does not fetch, scrape, download, or credential market data in this bundle.
- Network fetch, broker connection, `.env`, credentials, scheduler, live orders, and real sizing remain blocked.

## Source Candidate Guide
- source_candidate_count: `8`
- evidence_allowed_count: `0`
- Every source candidate requires manual license/provenance review before evidence use.

## Operator Staging Checklist
- required_folders: `dopey_data/real/raw/daily_ohlcv/, dopey_data/real/raw/market_context/, dopey_data/real/raw/corporate_actions/, dopey_data/real/manifests/`
- required_daily_ohlcv_columns: `date, symbol, open, high, low, close, adjusted_close, volume, source`
- required_manifest_fields: `manifest_id, created_at, dataset_family, provider_name, provider_terms_reviewed, license_status, redistribution_allowed, local_file_paths, file_hashes, row_counts, symbol_counts, date_ranges, schema_version, ingested_by, manual_operator_note, not_broker_data, not_credentials, not_live_data, not_network_fetched_by_dopey, paper_only, live_blocked, source_urls_or_reference_names, download_or_export_dates`

## Manifest Draft Helper
- manifest_draft_status: `manifest_draft_ready`
- hash_record_count: `225`
- The draft computes local hashes/counts only; it is not import approval or evidence.

## Preflight Linter
- preflight_status: `preflight_fail`
- Blocks sample/template rows, SAMPLE_ONLY, credentials/tokens, broker/live/order/scheduler/real-sizing markers, future dates, high/low inconsistency, duplicates, and missing source/manifest references.

## Import Fix Engine
- fix_plan_status: `local_files_detected_repair_required`
- Groups fixes into staging, manifest, schema, quality, license/provenance, sample removal, live-marker removal, hash mismatch, manual review, and ready states.

## Fixing The No-Files State
- Manually place reviewed CSV/JSONL files under `dopey_data/real/raw/daily_ohlcv/`, rerun the draft helper, complete the final manifest, then rerun the stack.

## Fixing Schema Errors
- Use the required OHLCV header exactly: `date,symbol,open,high,low,close,adjusted_close,volume,source`.

## Fixing Quality Errors
- Remove future dates, duplicate date/symbol rows, bad OHLC ranges, nonpositive prices, negative volume, and missing source values.

## Fixing Manifest/License/Provenance Errors
- Complete provider, terms review, license status, local paths, hashes, row counts, symbol counts, date ranges, source references, export dates, and safety assertions manually.

## Sample Rows Are Blocked
- Template rows, sample_only rows, not_real_data rows, and SAMPLE_ONLY symbols are fixtures only and cannot appear in real raw paths.

## Evidence Boundaries
- Valid OHLCV is not options evidence.
- OHLCV validation is not profitability, strategy promotion, or live readiness.

## Current Stack State
- manual_staging_status: `local_files_detected_repair_required`
- manual_staging_decision: `operator_must_fix_license_provenance`
- local_ohlcv_status: `local_ohlcv_validation_fail`
- valid_real_dataset: `false`
- history_spine_activation_status: `blocked_local_ohlcv_validator_not_passed`
- real_signal_validation_status: `blocked_missing_valid_real_history`
- real_signal_evidence: `false`

## Safety State
- network_fetch_performed: `false`
- credentials_created: `false`
- env_created: `false`
- broker_connection_used: `false`
- strategy_promotion_allowed: `false`
- paper_only: `true`
- live_blocked: `true`

## Validation Summary
- Targeted tests are in `tests/test_manual_free_ohlcv_staging_or_local_import_fix.py`.
- Full pytest timeout must remain `inconclusive_timeout`, not pass.
- prior_export_verifier_status: `inconclusive_timeout`

## Known Gaps
- No operator-reviewed real OHLCV files are currently accepted unless files pass schema, quality, manifest, license, provenance, and history activation gates.

## Next Target
- `DOPEY_MANUAL_STAGE_FREE_OHLCV_FILES_AND_RERUN_VALIDATOR`
