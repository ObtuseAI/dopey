# DOPEY Market Data Provider Install And Fallback Expansion V2

Bundle: `DOPEY_MARKET_DATA_PROVIDER_INSTALL_AND_FALLBACK_EXPANSION_V2`

## Result

Dopey now loads real public/no-key daily OHLCV through the repo `.venv`, persists it to cache, promotes it into the active market lake before fixtures, and reruns the money-first paper tournament on public market history.

- real public rerun: `real_public_market_vision_paper_tournament_complete`
- active public symbols: `58`
- active fixture symbols: `0`
- active public daily rows: `524413`
- primary universe loaded: `22/22`
- expansion symbols loaded: `36`
- chart count: `58`
- signal candidates: `139`
- model-priced option candidates: `139`
- paper tournament trades: `81`
- public-vs-fixture scoreboard split: `complete`
- live trading enabled: `false`
- credentials created: `false`
- env created: `false`
- broker connection used: `false`
- real orders placed: `false`

## Prior Failure Cause

The previous wealth-engine bundle had a package/runtime mismatch. Plain `python` resolved to `C:\Users\CH\AppData\Local\Programs\Python\Python313\python.exe`, while Dopey dependencies were installed into `C:\Users\CH\dopey\.venv\Scripts\python.exe`. The V2 repair records this as `plain_python_outside_repo_venv_explicit_venv_required` and writes commands that use the explicit repo venv Python.

## Provider Status

- yfinance: `importable`, used successfully for public OHLCV.
- pandas-datareader: `importable`.
- yahooquery: `importable`.
- OpenBB: `importable`, not used as the winning OHLCV route.
- Yahoo direct chart query: diagnosed as `ok`.
- Stooq: diagnosed as `non_csv_response`; the endpoint returned a browser-verification HTML page rather than CSV.

## Market Lake

The active lake is public-first:

- cache status: `cache_available`
- active lake status: `public_data_active`
- active public symbols: `58`
- active fixture symbols: `0`
- fixture rows active: `0`
- all active symbols tiered as `paper_trading`

Fixture fallback remains available but cannot overwrite active public files when public files exist.

## Paper Tournament

The public-data tournament completed with `81` model-priced long-premium paper trades.

Top public-data strategy by net paper P&L:

- `volatility_squeeze`: net paper P&L `39.6591`, max drawdown `-873.2367`, profit factor `1.045416`

Promoted paper strategy:

- `volatility_squeeze`

Killed strategies:

- `relative_weakness`
- `breakout`
- `mean_reversion_after_exhaustion`
- `momentum_continuation`
- `failed_breakout_fakeout_reversal`
- `trend_pullback`

No public-data `paper_champion` cleared the current champion threshold in this run. That is not a failure; it means Dopey now has real public market data and a brutally separated public scoreboard, but the next work should iterate the tournament and mutation loop until public-data champions emerge.

## Validation

- collect-only: `pass`
- targeted shards: `18/18 pass`
- smokes: `17/17 pass`
- capped offline evidence replay audit: `pass`
- capped artifact compaction export verifier: `inconclusive_timeout`, not pass

## Live Gate

Live trading remains separately gated and disabled.

- live trading enabled: `false`
- broker connection enabled: `false`
- real order enabled: `false`
- credentials present: `false`
- direct live promotion allowed: `false`

## Next Target

`DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1`
