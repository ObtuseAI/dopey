# DOPEY Real Signal Engines Report

## Objective
Build deterministic computed signal engines for offline long-call/long-put strategy research without broker access, credentials, live orders, real sizing, or market-data fetching.

## Signal Families Implemented
- momentum
- breakout and breakdown
- failed breakout / fakeout
- trend pullback continuation
- volatility expansion/compression
- relative strength
- market regime classifier
- long-call/long-put directional setup mapper

## Formulas And Definitions
- momentum: weighted 5-day, 10-day, 20-day returns plus 20-day close slope.
- breakout: close versus prior N-day high/low, with 20-day average-volume confirmation and distance score.
- fakeout: prior bar outside the N-day range followed by the signal bar closing back inside that range.
- trend pullback: 20-day and 50-day moving average trend state, moving-average touch, and continuation close confirmation.
- volatility: annualized realized volatility from daily close returns, short/long realized-vol ratio, and rolling range compression.
- relative strength: symbol N-day return minus benchmark N-day return, with missing-benchmark flags.
- regime: trend state, volatility state, drawdown state, and risk proxy mapped to the fixed regime label set.
- directional setup: bullish records map only to long-call candidates, bearish records map only to long-put candidates, neutral or low-confidence records map to no trade.

## Data-Source Tier Policy
- Allowed tiers: fixture_only, local_real_history, missing_real_history.
- local_real_history is forbidden unless the history spine reports valid_real_dataset.
- Fixture records are labeled fixture_only=true, real_history_used=false, not_real_signal_evidence=true.

## Current Limitation
- history_dataset_status: `valid_real_dataset`
- signal_engine_status: `local_real_history_signal_computation_ready`
- real_history_used: `true`
- The current run is math validation only and is not real signal evidence.

## Sample Fixture Validation
- fixture_only_case_count: `80`
- signal_family_distribution: `{'breakout': 20, 'directional_setup': 80, 'fakeout': 10, 'market_regime': 10, 'momentum': 10, 'relative_strength': 10, 'trend_pullback': 10, 'volatility_regime': 10}`
- direction_distribution: `{'bearish': 70, 'bullish': 70, 'neutral': 20}`

## Long-Call / Long-Put Setup Mapping
- long_call_candidate_count: `25`
- long_put_candidate_count: `30`
- no_trade_count: `25`
- No spreads, short-volatility structures, naked selling, same-day churn, broker dependency, or real sizing are created.

## Safety State
- paper_only: `true`
- live_blocked: `true`
- broker_connection: `none`
- credentials: `none`
- scheduler: `none`
- real_sizing: `none`
- live_orders: `false`
- not_real_edge_evidence: `true`

## Validation Summary
- Targeted tests are recorded in the session final status.
- Full pytest timeout, if observed, remains inconclusive_timeout and is not a pass.

## Limitations
- No real OHLCV evidence exists while the history spine remains missing_real_dataset.
- No profitability, edge, backtest validity, or live readiness is claimed.
- Fixture series are toy math cases only.

## Next Target
- `DOPEY_HONEST_BACKTESTER_V1`
