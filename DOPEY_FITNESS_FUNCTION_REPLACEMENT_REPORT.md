# DOPEY Fitness Function Replacement Report

## Objective
Replace proxy/theater fitness with a truth-gated diagnostic fitness layer that cannot promote strategies while statistical truth blocks promotion.

## Input Sources
- `artifacts/dopey/stats/statistical_truth_summary.json`
- `artifacts/dopey/stats/statistical_truth_decision.json`
- `artifacts/dopey/stats/backtest_metric_set.json`
- `artifacts/dopey/stats/bootstrap_confidence_intervals.json`
- `artifacts/dopey/stats/baseline_comparisons.jsonl`
- `artifacts/dopey/backtest/backtest_trade_records.jsonl`
- `artifacts/dopey/backtest/backtest_run_summary.json`

## Score Components
- win-rate, expectancy, drawdown-control, payoff-ratio, consistency/streak, total model-unit P&L, bootstrap CI diagnostic, and baseline delta diagnostic components.

## Penalties
- fixture-only, missing real history, missing options chain, insufficient real sample, no quote-priced data, truth-gate block, multiple-testing block, no-significance, no-profitability, no-live-readiness, full-pytest-inconclusive, and promotion-block penalties.

## Promotion Gate
- promotion_allowed: `false`
- strategy_promoted: `false`
- fitness_decision: `hold_no_promotion`
- The diagnostic score cannot override the statistical truth layer.

## Proxy Fitness Quarantine
- old_proxy_fitness_quarantined: `true`
- blocked_active_proxy_promotion_count: `0`
- manual_review_proxy_reference_count: `387`

## Truth-Gated Decision Logic
- truth_status: `fixture_model_statistics_only`
- truth_decision: `hold_fixture_validation_only`
- statistical_promotion_allowed: `false`

## Current Fixture/Model-Only Limitation
- real_sample_size: `0`
- fixture_model_sample_size: `82880`
- Current fitness is diagnostic-only and is not real statistical evidence.

## Claim-Blocking Policy
- significance_claim_allowed: `false`
- real_alpha_claim_allowed: `false`
- profitability_claim_allowed: `false`
- live_readiness_claim_allowed: `false`

## Safety State
- paper_only: `true`
- live_blocked: `true`
- no broker, credentials, scheduler, real sizing, orders, network market data, or live path created

## Validation Summary
- diagnostic_score: `0.0`
- score_component_count: `8`
- penalty_count: `12`
- quality_flags: `['fixture_model_diagnostic_only', 'fixture_model_statistics_only', 'full_pytest_inconclusive', 'insufficient_real_sample', 'live_readiness_claim_blocked', 'manual_review_proxy_reference', 'missing_real_history', 'missing_real_option_chain', 'no_quote_priced_data', 'not_live_ready', 'not_profitability_claim', 'not_real_backtest_evidence', 'not_real_fitness_evidence', 'not_real_statistical_evidence', 'old_proxy_fitness_quarantined', 'profitability_claim_blocked', 'promotion_blocked', 'real_alpha_claim_blocked', 'significance_claim_blocked', 'statistical_truth_promotion_false']`
- targeted fitness runner/test validation is external to this deterministic artifact writer
- full pytest timeout remains an inconclusive state and is not treated as pass

## Limitations
- No real OHLCV or real options-chain evidence exists in the current run.
- No real edge, real alpha, profitability, live readiness, or strategy promotion is claimed.

## Next Target
- `DOPEY_REAL_DATA_INGESTION_PLAN_V1`
