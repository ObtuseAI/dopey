# DOPEY Real Data Ingestion Plan Report

## Objective
Define the offline acquisition contract for future manually staged real market data. This bundle does not fetch, ingest, or validate real data.

## Current Blocker Summary
- real_data_files_present: `false`
- real_data_ingested: `false`
- real_data_validated: `false`
- import_readiness_decision: `plan_ready_import_not_started`

## Required Datasets
- `daily_ohlcv`: Required for real signal validation and real backtest date paths.
- `corporate_actions`: Required for adjusted price validation.
- `historical_options_chain`: Required for real options backtesting.
- `historical_options_quotes`: Required for spread and slippage realism.
- `fundamentals`: Required for fundamental analysis.
- `earnings_calendar`: Required for catalyst and event gates.
- `market_context`: Required for market regimes.
- `benchmark_and_universe_metadata`: Required for survivorship and coverage tracking.

## Provider Candidate Registry
- `Polygon` status=`manual_review_required` credential_required=`true`
- `Cboe DataShop` status=`manual_review_required` credential_required=`true`
- `ORATS` status=`manual_review_required` credential_required=`true`
- `OptionMetrics` status=`manual_review_required` credential_required=`true`
- `Nasdaq Data Link` status=`manual_review_required` credential_required=`true`
- `Alpha Vantage` status=`manual_review_required` credential_required=`true`
- `Tiingo` status=`manual_review_required` credential_required=`true`
- `Stooq` status=`manual_review_required` credential_required=`false`
- `Yahoo Finance manual download` status=`manual_review_required` credential_required=`false`
- `SEC EDGAR` status=`manual_review_required` credential_required=`false`
- `FRED` status=`manual_review_required` credential_required=`false`

## Local Staging Folder Contract
- Raw local-only folders are under `dopey_data/real/raw/`.
- Manifest template is `dopey_data/real/manifests/real_data_manifest.json`.
- Validated outputs, when a later bundle exists, are under `dopey_data/real/validated/`.

## Schema Contracts
- `daily_ohlcv` required_columns=8
- `corporate_actions` required_columns=7
- `historical_options_chain` required_columns=14
- `historical_options_quotes` required_columns=14
- `fundamentals` required_columns=13
- `earnings_calendar` required_columns=8
- `market_context` required_columns=8
- `benchmark_and_universe_metadata` required_columns=10

## License And Provenance Requirements
- license_provenance_requirement_count: `8`
- Unknown, unreviewed, missing, or unlicensed data blocks import readiness.

## Quality Gate Plan
- quality_gate_count: `137`
- All gates are `gate_defined_not_run` in this planning bundle.

## Import Readiness Decision
- ingestion_status: `real_data_ingestion_plan_ready`
- import_readiness_decision: `plan_ready_import_not_started`
- reason_codes: `['plan_ready_no_real_files_present']`

## What This Bundle Does Not Do
- It does not fetch market data, scrape market data, connect to brokers, create credentials, create `.env`, place orders, create schedulers, size real capital, promote strategies, or claim real edge.

## Current No-Real-Data Limitation
- Sample templates are schema examples only and are not evidence.
- The next bundle may validate manually staged local OHLCV only.

## Safety State
- paper_only: `true`
- live_blocked: `true`
- not_real_data_ingested: `true`

## Validation Summary
- Targeted test: `tests/test_real_data_ingestion_plan.py`
- Full pytest timeout, if encountered, remains `inconclusive_timeout` and is not pass.

## Limitations
- Provider approval is not claimed.
- License review is not completed by this bundle.
- No data-quality gate has run against real market data.

## Next Target
- `DOPEY_LOCAL_OHLCV_IMPORT_VALIDATOR_V1`
