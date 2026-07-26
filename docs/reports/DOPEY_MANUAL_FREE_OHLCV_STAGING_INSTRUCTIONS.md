# DOPEY Manual Free OHLCV Staging Instructions

## Allowed Raw Folders
- `dopey_data/real/raw/daily_ohlcv/`
- `dopey_data/real/raw/market_context/`
- `dopey_data/real/raw/corporate_actions/`
- `dopey_data/real/manifests/`

## Valid Daily OHLCV Header
```csv
date,symbol,open,high,low,close,adjusted_close,volume,source
```

## Invalid Blocked Sample Row
```csv
2026-01-01,SAMPLE_ONLY,1,1,1,1,1,0,fixture
```

## Manifest Draft
- Run `python -m dopey_data_ingestion.run_manual_ohlcv_manifest_draft` to compute local hashes and counts.
- The draft writes `dopey_data/real/manifests/real_data_manifest.draft.json` and never overwrites `real_data_manifest.json`.
- The draft is not evidence and not import approval.

## Manifest Finalization Checklist
- Complete provider, terms review, license status, redistribution status, local paths, hashes, counts, date ranges, source references, export dates, and safety assertions.
- Unknown or unreviewed license remains blocked.

## Rerun
- Draft helper: `python -m dopey_data_ingestion.run_manual_ohlcv_manifest_draft`
- Preflight: `python -m dopey_data_ingestion.run_manual_ohlcv_preflight_linter`
- Validator: `python -m dopey_data_ingestion.run_local_ohlcv_import_validator`
- Combined stack: `python -m dopey_data_ingestion.run_local_free_ohlcv_validation_and_activation_stack`

## Boundaries
- No API keys.
- No Alpha Vantage.
- No broker data.
- No `.env`.
- No network fetch or scrape.
- No strategy promotion, profitability, options edge, or live readiness claim.
