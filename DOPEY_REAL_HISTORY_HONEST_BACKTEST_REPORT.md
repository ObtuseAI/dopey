# DOPEY Real History Honest Backtest Report

## What This Is
The honest backtester running on validated, hash-pinned real OHLCV history for the first time.
Underlying paths are real; option marks are Black-Scholes model marks (no real options chain).

## Entry / Exit Policy
- entry: `next_trading_day_open_after_signal_date`
- option model: `{"dividend_yield": 0.0, "iv_multiplier_provenance": "chain_calibrated_2026-07-14", "iv_proxy": "realized_vol_20d_x_1.0475", "per_symbol_multipliers_active": 53, "price_units": "adjusted_close_units", "risk_free_rate": 0.0373, "risk_free_source": "us_treasury_par_yield_curve_30d", "strike_policy": "at_the_money_entry_open_adjusted_units", "tenor_calendar_days": 30}`
- exits: premium_stop -50%, premium_target +100%, time_stop 3 steps.

## Run
- backtest_status: `valid_real_history_model_priced_backtest_complete`
- trade_intent_count: `403088`
- trade_record_count: `82880`
- long_call / long_put: `38072` / `44808`
- no_trade intents: `320129`
- skipped (no forward bars / missing symbol): `79` / `0`
- total_path_pnl_model_units: `-18977.036834`
- average_path_pnl_model_units: `-0.22897`
- max_drawdown_model_units: `-19032.744433`
- win / loss: `30361` / `52519`

## Cohorts (signal_family x strategy, model units)
- `market_regime|long_call`: n=`416` win_rate=`0.411058` PF=`1.13913` net=`135.705264`
- `trend_pullback|long_put`: n=`7` win_rate=`0.428571` PF=`0.380887` net=`-2.565598`
- `fakeout|long_put`: n=`746` win_rate=`0.382038` PF=`0.986631` net=`-8.149217`
- `trend_pullback|long_call`: n=`34` win_rate=`0.235294` PF=`0.134582` net=`-46.844658`
- `fakeout|long_call`: n=`667` win_rate=`0.466267` PF=`0.926271` net=`-51.496116`
- `breakout|long_call`: n=`2220` win_rate=`0.395045` PF=`0.867336` net=`-318.113245`
- `breakout|long_put`: n=`1800` win_rate=`0.354444` PF=`0.720047` net=`-465.473358`
- `relative_strength|long_call`: n=`18745` win_rate=`0.400373` PF=`0.846775` net=`-2793.390272`
- `momentum|long_call`: n=`15990` win_rate=`0.393621` PF=`0.811368` net=`-3143.315769`
- `momentum|long_put`: n=`11058` win_rate=`0.34527` PF=`0.702627` net=`-3371.038719`
- `market_regime|long_put`: n=`11247` win_rate=`0.32871` PF=`0.630607` net=`-4068.717301`
- `relative_strength|long_put`: n=`19950` win_rate=`0.338546` PF=`0.700892` net=`-4843.637845`

## Honest Limits
- No real options chain: marks are model-priced; this is NOT real options-market evidence.
- path_pnl is NET of a modeled cost stack (half-spread, slippage, commission); mid-based gross kept alongside.
- Model-unit P&L is not account equity and not a profitability claim.
- paper_only: `true`; live_blocked: `true`; promotion remains blocked upstream.
