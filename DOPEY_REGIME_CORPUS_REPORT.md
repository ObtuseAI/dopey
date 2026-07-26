# DOPEY Regime Corpus Report

## Purpose

The expanded offline regime fixture corpus lets the DOPEY multi-strategy tournament
meaningfully separate strategy families across distinct market regimes. Prior to this
build pass the tournament replayed only 4 walk-forward windows and every strategy family
constructed the same long-call vertical, so all four genomes produced identical replay
outcomes and ranking collapsed to a stable insertion-order tie.

This pass introduces a larger deterministic fixture corpus (12 windows, 12 regime tags)
and a family-aware deterministic outcome model so different strategy families construct
different paper structures and respond differently by regime. Everything remains
**offline, paper-only, fixture-based, deterministic, and live-blocked**.

This is an engineering fixture corpus. It is **not** real market data and makes **no
performance or profit claims**. All outcomes are deterministic fixture simulations.

## Window count

12 deterministic walk-forward windows (`window_001_train` ... `window_012_holdout`),
each with a matching analysis-context fixture (`<window_id>_analysis.json`).

Window-type split: 4 train, 4 validation, 3 holdout (plus 1 holdout macro-shock window).

## Regime tags covered

All 12 required regime tags are present, each exactly once:

| # | regime_tag | window_type | design intent |
|---|---|---|---|
| 1 | `trend_vol_expansion` | train | risk-on uptrend + vol expansion favors long convexity |
| 2 | `chop_vol_compression` | train | chop + IV compression favors defined-risk compression |
| 3 | `gap_reversal` | train | gap fades/reverses; punishes short-duration directional |
| 4 | `liquidity_decay` | train | liquidity decays through session; long vol suffers |
| 5 | `event_vol_expansion` | validation | event shock expands IV; long strangle wins |
| 6 | `post_event_iv_crush` | validation | IV crush after event; compression structures win |
| 7 | `bearish_breakdown` | validation | bearish breakdown; long put vertical wins |
| 8 | `bullish_breakout` | validation | clean bullish breakout; call vertical + short-DTE win |
| 9 | `range_bound_pin` | validation | pin to mid; iron condor wins |
| 10 | `high_spread_bad_fill` | holdout | wide spreads + bad fills punish all, short-DTE worst |
| 11 | `low_liquidity_decay` | holdout | thin book decays; short-DTE defined-risk punished |
| 12 | `macro_shock_risk_off` | holdout | macro shock risk-off; long vol expansion wins, compression loses |

## Fixture fields

Each window includes:

- `window_id`, `window_type` (train | validation | holdout), `sequence_id`, `timestamp`
- `regime_tag`
- `underlying_snapshot` (symbol SPY_FIXTURE, price, prev_close, realized_vol_20d, regime_score)
- `option_chain` snapshot (6 contracts: calls + puts at 3 strikes, deterministic bid/ask/IV/Greeks)
- `expected_outcome` (next_underlying_price, next_iv, days_to_exit, exit_reason, favorable_move, adverse_move_pct)
- `family_outcome_hints` (per-family 0..1 fit hint for this regime)
- `regime_context` (liquidity_quality, spread_penalty, slippage_penalty, iv_effect, macro_contradiction, technical_fakeout, pattern_confidence, invalidation_quality, direction, vol_bias)
- `notes`

Each matching `<window_id>_analysis.json` carries the five analysis layers (macro,
microstructure, technical, fundamental, patterns) as deterministic contexts.

## Strategy-family outcome design

The deterministic outcome model (`dopey_walk_forward.family_outcome.compute_family_outcome`)
encodes the design intent via `REGIME_FAMILY_HINTS`:

| Family | Structure | Wins in | Loses in |
|---|---|---|---|
| directional convexity | long call vertical (bullish) / long put vertical (bearish) | bullish_breakout, bearish_breakdown, trend_vol_expansion | chop_vol_compression, range_bound_pin, high_spread_bad_fill |
| volatility expansion | long strangle (buy OTM call + buy OTM put) | event_vol_expansion, macro_shock_risk_off, trend_vol_expansion | post_event_iv_crush, chop_vol_compression, liquidity_decay |
| volatility compression | iron condor (defined-risk credit pair) | chop_vol_compression, range_bound_pin, post_event_iv_crush | event_vol_expansion, macro_shock_risk_off, breakout/breakdown |
| short-duration defined-risk | call butterfly (defined-risk debit) | clean trend / breakout windows | high_spread_bad_fill, low_liquidity_decay, gap_reversal |

All structures are defined-risk. No naked / undefined-risk selling exists in any family.

## Deterministic outcome model

The family-aware outcome model replaces the prior crude one-size exit model. Inputs:

- direction match, volatility match, regime match (family hint)
- liquidity quality, spread penalty, slippage penalty
- IV crush/expansion effect (signed)
- macro contradiction penalty, technical fakeout penalty
- pattern confidence, invalidation trigger quality

Outputs (per window per family):

- deterministic paper PnL proxy
- max favorable / adverse excursion proxy
- invalidation result
- regime match score, family fit score

The regime-fit term is the dominant driver so the tournament can cleanly separate which
families suit which regimes. The structure payoff (deterministic from terminal price vs
strikes) is a secondary contributor. This is explicitly a **deterministic fixture
simulation**, not real execution quality.

## Limitations

- Fixture data is synthetic and deterministic; it is not market data and makes no empirical claims.
- The outcome model is a simple engineering scoring function, not a Greeks/IV model or market-impact model.
- Liquidity/slippage are deterministic proxies, not a calibrated slippage/liquidity model.
- Pattern signals are placeholder deterministic fixtures, not a large ML pattern-recognition model.
- No real broker integration, no credentials, no network, no scheduled runs.

## Safety state

- Mode: `RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- PaperBroker is the only execution adapter; refuses `live_allowed=true`
- Robinhood/Alpaca/Tradier stubs raise `LiveTradingDisabledError`
- Promotion decisions limited to: `rejected`, `research_only`, `paper_candidate`, `tournament_champion_paper_only`
- Forbidden (impossible from this path): `live_candidate`, `micro_live`, `adaptive_live`, any live state
- Original Blunder source unchanged (SHA256 baseline verified)
