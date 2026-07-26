# DOPEY Test Shard Plan

- fixture_only: `true`
- paper_only: `true`
- live_blocked: `true`
- full_suite_status: `inconclusive_timeout`
- timeout_recorded_as_pass: `false`
- recommended_long_timeout_seconds: `900`

## Slow-Test Allowlist
- `tests/test_artifact_compaction_export_verifier.py`
- `tests/test_export_bundle_review_assistant.py`

## 0DTE Risk And Replay Test Shards
- `tests/test_portfolio_stress_ladder.py`

## Adversarial Corpus Test Shards

## Cross-Underlying V2 Corpus Test Shards

## Hybrid Swing 0DTE V3 Test Shards

## Proof-Weighted Allocation Test Shards

## Portfolio Replay Test Shards

## Portfolio Stress Ladder Test Shards
- `tests/test_portfolio_stress_ladder.py`

## Kill-Switch Incident Response Test Shards

## Manual Approval Packet Test Shards

## Read-Only Detector Dry-Run Validator Test Shards

## Approval Intake Validator Test Shards

## Approval-To-Run Handoff Gate Test Shards

## Pre-Run Safety Scanner Test Shards

## Real-Data Backtest Spine Test Shards

## Model Repricer Test Shards

## Real Data Ingestion Plan Test Shards

## Real Data Validation Stack Test Shards

## Local Free OHLCV Stack Test Shards

## Open-Source Free-Data Path Test Shards

## Wealth Engine Test Shards

## Artifact-Writing Tests Run Sequentially
- `tests/test_portfolio_stress_ladder.py`

## Export Review Slow Shard
- `C:\Users\CH\dopey\.venv\Scripts\python.exe -m pytest tests/test_export_bundle_review_assistant.py -q`

## Split Suite Commands
- `pytest-file-001`: `C:\Users\CH\dopey\.venv\Scripts\python.exe -m pytest tests/test_portfolio_stress_ladder.py -q`
