# DOPEY Honest Backtester Report

## Objective
Build a deterministic paper-only offline backtester spine that consumes computed signal outputs, model repricer marks, history-spine status, and long-call/long-put policy rules.

## Data-Source Tier Policy
- Fixture/sample/model validation records are labeled fixture_only=true and real_history_used=false.
- local_real_history is not used unless the history spine reports valid_real_dataset.
- current history_dataset_status: `valid_real_dataset`

## Pricing-Source Tier Policy
- long_call and long_put validation trades use model_priced marks only.
- no_trade records use fixture_only pricing tier.
- quote_priced remains zero because no real options chain is present.

## Signal-To-Trade Mapping
- bullish directional setup -> long call intent only.
- bearish directional setup -> long put intent only.
- neutral/no-edge setup -> no trade.

## Long-Call / Long-Put Only Policy
- No spreads, short-volatility structures, naked selling, undefined-risk positions, real sizing, broker dependency, orders, or scheduler loop are created.
- Same-day churn is blocked; current fixture/model path requires at least one holding step.

## Exit Logic
- premium_stop_pct: `-0.50`
- premium_target_pct: `1.00`
- max_holding_steps: `3`
- exits: premium_stop, premium_target, time_stop, terminal_path_mark, invalid_no_trade_block.

## Model-Priced P&L Limitations
- P&L is expressed only in abstract premium model units.
- It is not account equity, buying power, real capital sizing, or a profitability claim.

## Current Missing-Real-History Limitation
- backtest_status: `valid_real_history_backtest_ready`
- real_history_used: `false`
- Current outputs are not real backtest evidence.

## Safety State
- paper_only: `true`
- live_blocked: `true`
- not_real_backtest_evidence: `true`
- not_profitability_claim: `true`
- not_live_ready: `true`
- broker_connection: `none`
- credentials: `none`
- scheduler: `none`
- real_sizing: `none`
- live_orders: `false`

## Validation Summary
- trade_intent_count: `80`
- trade_record_count: `55`
- long_call_trade_count: `25`
- long_put_trade_count: `30`
- no_trade_count: `25`
- pricing_source_tier_distribution: `{'fixture_only': 25, 'model_priced': 55, 'quote_priced': 0}`
- data_source_tier_distribution: `{'fixture_only': 80}`
- total_path_pnl_model_units: `35.539623`
- max_drawdown_model_units: `-4.472074`
- quality_flags: `['fixture_model_validation_only', 'missing_real_option_chain', 'not_live_ready', 'not_profitability_claim', 'not_real_backtest_evidence']`

## Limitations
- No real OHLCV or real options-chain evidence exists in the current run.
- No real edge, backtest validity, profitability, or live readiness is claimed.
- Fixture validation cases are deterministic math/policy checks only.

## Next Target
- `DOPEY_STATISTICAL_TRUTH_LAYER_V1`
