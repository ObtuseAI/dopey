# DOPEY Real History Signal Engine Report

## Objective
Compute the DOPEY signal families over validated, hash-pinned local real OHLCV history and emit dated directional setups for the honest backtester.

## Data Source
- history_dataset_status: `valid_real_dataset`
- real_history_used: `true`
- data_source_tier: `local_real_history`
- No fixtures, no synthetic rows, no network market data.

## Evaluation Grid
- evaluation_start_date: `2015-01-01`
- cadence: every `3` trading days
- lookback_window: `20`
- benchmark_symbol: `SPY`
- context_only_symbols (no options signals): `['VIX']`
- symbols_evaluated: `66`
- evaluation_point_count: `57584`

## Leak Policy
- Signals at a date use bars through that date only.

## Output
- directional_setup_count: `403088`
- long_call_candidate_count: `38108`
- long_put_candidate_count: `44851`
- no_trade_count: `320129`

## Boundaries
- Signals are research inputs, not edge evidence, profitability, or live readiness.
- paper_only: `true`; live_blocked: `true`.
