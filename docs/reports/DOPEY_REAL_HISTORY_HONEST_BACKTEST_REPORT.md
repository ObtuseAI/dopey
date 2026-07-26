# DOPEY Real History Honest Backtest Report

## What This Is
The honest backtester running on validated, hash-pinned real OHLCV history for the first time.
Underlying paths are real; option marks are Black-Scholes model marks (no real options chain).

## Entry / Exit Policy
- entry: `next_trading_day_open_after_signal_date`
- option model: `{"dividend_yield": 0.0, "iv_multiplier_provenance": "chain_calibrated_2026-07-22", "iv_proxy": "realized_vol_20d_x_1.1171", "per_symbol_multipliers_active": 189, "price_units": "adjusted_close_units", "risk_free_rate": 0.037599999999999995, "risk_free_source": "us_treasury_par_yield_curve_30d", "strike_policy": "at_the_money_entry_open_adjusted_units", "tenor_calendar_days": 30}`
- exits: premium_stop -50%, premium_target +100%, time_stop 3 steps.

## Run
- backtest_status: `valid_real_history_model_priced_backtest_complete`
- trade_intent_count: `1430674`
- trade_record_count: `321416`
- long_call / long_put: `147586` / `173830`
- no_trade intents: `1108906`
- skipped (no forward bars / missing symbol): `352` / `0`
- total_path_pnl_model_units: `-136440.479317`
- average_path_pnl_model_units: `-0.424498`
- max_drawdown_model_units: `-136528.578019`
- win / loss: `115892` / `205524`

## Cohorts (signal_family x strategy, model units)
- `trend_pullback|long_put`: n=`11` win_rate=`0.363636` PF=`0.32578` net=`-4.27523`
- `trend_pullback|long_call`: n=`55` win_rate=`0.236364` PF=`0.074001` net=`-714.107132`
- `market_regime|long_call`: n=`817` win_rate=`0.365973` PF=`0.668858` net=`-1383.798121`
- `fakeout|long_put`: n=`2878` win_rate=`0.355803` PF=`0.649897` net=`-1556.246041`
- `fakeout|long_call`: n=`2380` win_rate=`0.468487` PF=`0.609036` net=`-1857.496819`
- `breakout|long_put`: n=`6530` win_rate=`0.348698` PF=`0.779982` net=`-2420.783459`
- `breakout|long_call`: n=`8007` win_rate=`0.382041` PF=`0.629026` net=`-5042.792629`
- `market_regime|long_put`: n=`43126` win_rate=`0.32994` PF=`0.756103` net=`-15910.839013`
- `momentum|long_put`: n=`42569` win_rate=`0.333341` PF=`0.715238` net=`-21643.380294`
- `relative_strength|long_put`: n=`78716` win_rate=`0.336857` PF=`0.78273` net=`-21886.291758`
- `relative_strength|long_call`: n=`75409` win_rate=`0.393521` PF=`0.768441` net=`-28597.995406`
- `momentum|long_call`: n=`60918` win_rate=`0.385617` PF=`0.674534` net=`-35422.473415`

## Honest Limits
- No real options chain: marks are model-priced; this is NOT real options-market evidence.
- path_pnl is NET of a modeled cost stack (half-spread, slippage, commission); mid-based gross kept alongside.
- Model-unit P&L is not account equity and not a profitability claim.
- paper_only: `true`; live_blocked: `true`; promotion remains blocked upstream.
