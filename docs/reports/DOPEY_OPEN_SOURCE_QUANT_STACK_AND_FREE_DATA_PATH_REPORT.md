# DOPEY Open-Source Quant Stack And Free Data Path Report

## Objective
Build an open-source-first research candidate registry and free/public data validation path while preserving strict local-data gates.

## Alpha Vantage Exclusion
Alpha Vantage is excluded from this bundle. No API-key handling, credential path, endpoint detector, fetcher, or provider integration was added.

## Open-Source Candidate Registry
- candidate_count: `12`
- reference_only_count: `9`
- sandbox_candidate_count: `2`
- adapter_candidate_count: `1`
- imported_count: `0`
- executed_count: `0`

## License And Security Gate
Candidates are gated for license compatibility, maintenance, dependency risk, live/broker risk, credential risk, network-fetch risk, import isolation, sandbox requirements, and no direct promotion authority.

## Sandbox Import Plan
The sandbox contract defines local folders only under `dopey_open_source_vendor/`. No repository was cloned, no dependency was installed, and no external code was imported or executed.

## Capability Extraction Plan
Capability extraction is limited to reference patterns and diagnostic/candidate outputs for event loops, risk models, fill/slippage, indicators, feature engineering, options math, volatility, ML/RL workflows, data quality, reporting, and audit trails.

## Adapter Boundaries
Adapter contracts block broker calls, network data fetches without separate approval, orders, credential writes, promotion gate changes, and statistical-truth or fitness gate overrides.

## Free Data-Source Candidate Gate
- free_data_candidate_count: `8`
- evidence_allowed_count: `0`
- manual_review_required_count: `8`

Free/public candidates are not evidence unless license and provenance gates pass.

## Local OHLCV Pass-Or-Fix Behavior
- local_ohlcv_status: `missing_local_ohlcv_files`
- fix_advice_status: `manual_staging_required`
- valid_real_dataset: `false`

Missing local files produce actionable staging advice and do not count as an error for plan readiness.

## History Spine Activation Gate
- history_spine_upgrade_status: `blocked_missing_local_ohlcv`
- real_history_used: `false`

Activation is blocked until local OHLCV passes schema, quality, license, provenance, and hash gates.

## Current No-Real-Data State
No real OHLCV files are present, no real data was imported, and no real history or real signal evidence is claimed.

## Safety State
- network_fetch_performed: `false`
- credentials_created: `false`
- env_created: `false`
- strategy_promotion_allowed: `false`
- paper_only: `true`
- live_blocked: `true`

## Validation Summary
Targeted and smoke validation results are recorded in the final session status. Full pytest remains timeout-sensitive and must not be treated as pass if it times out.

## Known Gaps
Manual free/public OHLCV still needs to be staged by an operator with license and provenance review before import validation can pass.

## Next Target
`DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1`
