# DOPEY Family Mutation Limits Report

## Scope

Family mutation limits keep offline strategy mutation inside each strategy family's intended
shape. The validator rejects family drift before scoring and never permits live promotion.

## Implemented module

- `dopey_strategy_lab/family_mutation_limits.py`

## Model version

- Family mutation limits version: `dopey-family-mutation-limits-v1`

## Family envelopes

- `directional_convexity`: allows directional delta, vertical-shape, breakout, fakeout,
  Greek-fit, pattern-confidence, holdout, and liquidity-threshold mutations. It rejects
  compression-only drift, direction removal, and iron-condor drift.
- `volatility_expansion`: allows long-vol, positive-vega, IV-expansion, strangle-proxy, theta,
  slippage, bad-fill, and holdout mutations. It rejects short-vol drift, IV-crush-only drift, and
  removal of positive vega.
- `volatility_compression`: allows condor, range, IV-crush, theta-carry, slippage-credit,
  bad-fill, pattern-confidence, and holdout mutations. It rejects unlimited risk, undefined risk,
  and positive-vega expansion drift.
- `short_duration_defined_risk`: allows short-DTE, theta-balance, intraday-pattern,
  strict-liquidity, strict-slippage, short-DTE spread, bad-fill, and holdout mutations. It rejects
  low-liquidity drift, wide illiquid structures, and live scalping drift.

## Hard rejections

The validator rejects any mutation that attempts to set live behavior or leave defined-risk paper
research:

- `live_allowed=true`
- `defined_risk=false`
- `structure_risk` other than `defined`
- `live_candidate`, `micro_live`, `adaptive_live`, or `live`
- naked, undefined-risk, or unlimited-risk structure drift

## Latest proof

- Generated population: `36`
- Valid family-preserving mutations: `32`
- Unsafe family-drift probes rejected: `4`
- Families covered: `directional_convexity`, `volatility_expansion`,
  `volatility_compression`, `short_duration_defined_risk`

## Tests

The 35-test bundle includes direct rejection tests for directional non-directional drift,
vol-expansion short-vol drift, compression unlimited-risk drift, short-duration low-liquidity
drift, and valid family-preserving mutations.

## Safety state

Family limits are an offline guardrail only. They do not place orders, call brokers, schedule
jobs, or promote any strategy beyond paper research categories.
