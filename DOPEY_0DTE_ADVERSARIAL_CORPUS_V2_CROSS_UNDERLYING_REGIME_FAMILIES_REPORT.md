# DOPEY 0DTE Adversarial Corpus V2 Cross-Underlying Regime Families Report

## Objective

`DOPEY_0DTE_ADVERSARIAL_CORPUS_V2_CROSS_UNDERLYING_REGIME_FAMILIES_V1` expands the offline 0DTE adversarial proof environment from single-scenario fixture stress into synthetic underlying families, regime families, liquidity/spread archetypes, IV behavior, gamma/theta behavior, event/macro sensitivity, and policy-loophole probes.

This is deterministic fixture evidence only. It is not live profitability evidence, market accuracy proof, broker readiness, deployment authorization, or live threshold promotion.

## Corpus Summary

- Baseline fixture cases: `24`
- Adversarial v1 fixture cases: `99`
- Cross-underlying v2 fixture cases: `192`
- Combined v1/v2 fixture cases: `315`
- Synthetic underlying families: `12`
- Regime families covered: `16`
- Call/put distribution: `call=96`, `put=96`
- Replay expectations matched: `true`
- Feedback expectations matched: `true`
- Optimizer effect expectations matched: `true`
- Policy loophole block rate by family: `1.0`
- Cross-underlying completeness score: `1.0`

## Underlying Families

Each family uses a synthetic fixture symbol only:

- `index_like_etf`
- `megacap_liquid_equity`
- `high_beta_momentum_equity`
- `event_sensitive_equity`
- `low_liquidity_options_equity`
- `sector_rotation_equity`
- `gap_prone_equity`
- `mean_reversion_equity`
- `trend_persistence_equity`
- `volatility_crush_equity`
- `macro_sensitive_equity`
- `pin_risk_heavy_equity`

Every family has `16` cases, both calls and puts, all 16 regime families represented globally, policy-loophole coverage, later-expiry coverage, special-close coverage, and expiry-management coverage.

## Regime Families

Each regime family has `12` cases:

- `bull_trend`
- `bear_trend`
- `chop_decay`
- `false_breakout`
- `false_breakdown`
- `gap_and_fade`
- `gap_and_go`
- `iv_expansion`
- `iv_crush`
- `macro_shock`
- `event_whipsaw`
- `late_day_liquidity_decay`
- `pin_near_strike`
- `mean_reversion`
- `trend_persistence`
- `range_bound`

## Path Builder

`dopey_options/zero_dte_cross_underlying_path_builder.py` generates deterministic intraday paths with no randomness, market data, or external calls. Each path includes underlying price, option bid/mid/ask, spread, slippage, liquidity score, delta/gamma/theta/vega, IV, event/macro stress, close signal, special-close signal, expiry pressure, and pin-risk state.

## Optimizer Impact

The threshold optimizer now records cross-underlying v2 evidence in its summary. `stricter_gamma_theta_profile` survives only as paper-shadow with no research-default promotion. Non-gamma/theta paper-shadow candidates are recorded as advisory-only under cross-underlying pressure. The negative-control profile remains rejected.

No live/default threshold mutation is allowed.

## V3 Hybrid Continuation

The next corpus layer is `DOPEY_CROSS_UNDERLYING_V3_MULTI_DAY_SWING_0DTE_HYBRID_REPLAY_CORPUS_V1`. It keeps the same 12 synthetic underlying families and 16 regime families, then compares each 0DTE candidate against a multi-day long-call/long-put swing alternative. V3 adds 192 hybrid pairs with balanced call/put coverage, no-day-trade swing lifecycle checks, delayed rotation, special close, next-day close, overnight gap stress, proof-only allocator tags, and post-hybrid threshold survival evidence.

## Coverage And Audit

Coverage outputs include underlying-family coverage, regime-family coverage, call/put balance, archetype distributions, risk-vector distribution, per-family policy loophole coverage, per-family special close coverage, per-family expiry management coverage, per-family later-expiry coverage, highest-risk family/regime combinations, and next corpus recommendations.

Audit integration recognizes all v2 artifacts and validates synthetic-only symbols, paper-only/live-blocked flags, no real market-data references, no broker references, no credential references, policy loophole blocks by family, live-path rejection by family, unsupported-structure rejection by family, same-day churn rejection by family, and no unsafe research-default promotion.

## Validation

- `python -m pytest tests/test_zero_dte_cross_underlying_v2.py -q` -> `91 passed`

Broader validation and smoke status are recorded in `DOPEY_VALIDATION_REPORT.md`.

## Safety State

- live trading: `disabled`
- broker execution: `absent`
- credentials: `not created`
- real market data: `not used`
- scheduler: `not created`
- same-day churn loophole: `not introduced`
- original Blunder: `untouched by this bundle`

## Limitations

This corpus is fixture-empirical only. It increases adversarial structural coverage but cannot prove live performance, predictive power, market realism, fill quality, or broker readiness.
