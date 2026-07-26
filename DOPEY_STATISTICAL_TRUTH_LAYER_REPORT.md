# DOPEY Statistical Truth Layer Report

## Objective
Build a deterministic paper-only truth layer that decides which statistical conclusions are allowed, blocked, incomplete, or manual-review-only.

## Input Sources
- backtest summary: `C:\Users\CH\dopey\artifacts\dopey\backtest\backtest_run_summary.json`
- backtest trade records: `C:\Users\CH\dopey\artifacts\dopey\backtest\backtest_trade_records.jsonl`
- backtest quality flags: `C:\Users\CH\dopey\artifacts\dopey\backtest\backtest_quality_flags.jsonl`

## Sample Profile
- sample_count: `82880`
- real_sample_size: `0`
- fixture_model_sample_size: `82880`
- real_evidence_thresholds_met: `false`

## Metric Definitions
- Metrics use abstract model-unit premium P&L only.
- Win rate, expectancy, payoff ratio, profit factor, Sharpe-like, Sortino-like, and drawdown are diagnostics, not real profitability.
- average_model_unit_pnl: `-0.22897`
- median_model_unit_pnl: `-0.179631`
- total_model_unit_pnl: `-18977.036834`
- max_drawdown_model_units: `-19032.744433`

## Bootstrap Method
- fixed_seed: `8675309`
- iterations: `1000`
- mean_pnl_ci: `[-0.254492, -0.20136]`
- win_rate_ci: `[0.36332, 0.369584]`
- Bootstrap intervals are fixture/model diagnostics only.

## Baseline Comparisons
- comparison_count: `6`
- Baselines include zero-return, random-direction fixture, always-long-call, always-long-put, no-trade, and shuffled-signal diagnostics.
- No superiority or real alpha claim is allowed.

## Multiple-Testing Guard
- strategy_family_count: `2`
- tested_signal_family_count: `6`
- P-values are blocked because the current run is not real statistical evidence.

## Deflated Sharpe Diagnostic
- observed_sharpe_like_model_units: `-0.058079`
- deflated_sharpe_model_units: `-0.063862`
- Diagnostic-only placeholder; no significance claim is reported.

## Truth Decision Gate
- truth_status: `fixture_model_statistics_only`
- truth_decision: `hold_fixture_validation_only`
- blocked_reason_codes: `['bootstrap_insufficient_real_sample', 'deflated_sharpe_diagnostic_only', 'insufficient_real_sample_blocks_significance', 'missing_real_history_blocks_real_evidence', 'missing_real_option_chain', 'missing_real_options_chain_blocks_real_options_edge', 'multiple_testing_p_values_blocked', 'not_profitability_claim_blocks_profitability_claim', 'not_real_backtest_evidence_blocks_promotion']`

## Current Fixture/Model-Only Limitation
- Real OHLCV and real options-chain data remain absent.
- Current statistics are not real statistical evidence.

## Claim-Blocking Policy
- significance_claim_allowed: `false`
- real_alpha_claim_allowed: `false`
- profitability_claim_allowed: `false`
- live_readiness_claim_allowed: `false`
- promotion_allowed: `false`

## Safety State
- paper_only: `true`
- live_blocked: `true`
- broker_connection: `none`
- credentials: `none`
- scheduler: `none`
- real_sizing: `none`
- live_orders: `false`

## Validation Summary
- quality_flags: `['fixture_model_statistics_only', 'insufficient_real_sample', 'live_readiness_claim_blocked', 'missing_real_history', 'missing_real_option_chain', 'not_real_statistical_evidence', 'profitability_claim_blocked', 'promotion_blocked', 'real_alpha_claim_blocked', 'significance_claim_blocked']`
- run_hash: `acce3ad853a90c46fcf7103bed324d93afd39ac146e64084a0c84acac019ddec`

## Limitations
- Model-unit P&L is not money and not profitability.
- Fixture/model statistics cannot promote strategies.
- Real evidence thresholds currently fail with real_sample_size=0.

## Next Target
- `DOPEY_FITNESS_FUNCTION_REPLACEMENT_V1`
