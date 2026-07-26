# DOPEY Cross-Underlying V3 Multi-Day Swing 0DTE Hybrid Replay Corpus Report

## Objective

`DOPEY_CROSS_UNDERLYING_V3_MULTI_DAY_SWING_0DTE_HYBRID_REPLAY_CORPUS_V1` adds an offline, deterministic replay layer that compares 0DTE candidates against multi-day long-call/long-put swing alternatives for the same synthetic signal.

This is fixture-only, paper-only, advisory evidence. It does not enable live trading, broker execution, market-data access, credentials, real sizing, scheduling, or live threshold mutation.

## Corpus Summary

- Hybrid opportunity pairs: `192`
- Synthetic underlying families: `12`
- Hybrid pairs per family: `16`
- Regime families covered: `16`
- Call/put distribution: `call=96`, `put=96`
- Swing candidates: `192`
- Multi-day paths: `192`
- Replay outcomes: `192`
- Hybrid completeness score: `1.0`
- Underlying-family coverage score: `1.0`
- Regime-family coverage score: `1.0`
- Call/put balance score: `1.0`

## Preference Distribution

- `prefer_swing`: `84`
- `prefer_zero_dte`: `36`
- `prefer_no_trade`: `36`
- `prefer_delayed_rotation`: `24`
- `inconclusive_needs_more_fixture_coverage`: `12`

The corpus includes 0DTE-preferred, swing-preferred, delayed-rotation, no-trade, special-close, next-day-close, overnight-gap, and inconclusive-more-fixtures cases in every underlying family.

## Swing Lifecycle

Swing candidates are restricted to long calls and long puts with `buy_to_open` entry and `sell_to_close` exit. Same-day normal swing closes are blocked. Next-trading-day and later closes are allowed in the fixture lifecycle. Unsupported structures and live paths are rejected.

## Hybrid Replay

The replay engine writes deterministic outcomes comparing:

- 0DTE premium outcome and max adverse excursion
- swing premium outcome and max adverse excursion
- theta decay and gamma instability
- liquidity and spread penalty
- expiry risk
- no-day-trade result
- rotation plan result
- threshold feedback
- proof-only capital allocator tags

All replay, preference, and allocator-tag expectations match.

## Optimizer Impact

The threshold optimizer consumes hybrid V3 evidence and records post-hybrid advisory state:

- stricter gamma/theta profile remains paper-shadow only
- later-expiry preference is strengthened advisory-only when swing evidence supports it
- zero-DTE-only paper-shadow candidates are downgraded when swing or delayed rotation is preferred
- research-default promotion remains blocked
- live threshold mutation remains blocked

## Audit And Reporting

The active-policy audit recognizes all hybrid V3 artifacts and validates synthetic-only symbols, paper-only/live-blocked flags, no live market-data references, no broker references, no credential references, long-call/long-put-only swing candidates, same-day normal swing-close blocks, delayed-rotation proof, and no real sizing.

Reporting and export review include a `hybrid_swing_0dte_v3_summary` section. Export selection includes every hybrid artifact and this report.

## Validation

Targeted validation:

- `python -m pytest tests/test_hybrid_swing_0dte_v3.py -q`: `107 passed`

The full suite remains a bounded validation step and any timeout is recorded as inconclusive, not pass.

## Limitations

- Synthetic fixture evidence only.
- No live market-data calibration.
- No broker capability or order-routing proof.
- No legal PDT determination.
- No real capital sizing; allocator tags are proof-only.

## Next Recommended Build Target

`hybrid_v4_portfolio_level_rotation_and_exposure_replay`
## Proof-Weighted Paper Allocation Integration

Hybrid V3 allocator tags are now consumed by the proof-weighted paper allocator under `dopey_allocation`. The allocator translates hybrid preferences into abstract paper attention and paper premium-at-risk units while preserving paper-only, live-blocked, no-broker, no-real-sizing boundaries.

The allocation output keeps swing allocation above 0DTE allocation when hybrid replay favors swing:

- swing paper premium risk units: `32.4`
- 0DTE paper premium risk units: `17.9`
- 0DTE exposure share: `0.342256`
- 0DTE share status: `within_cap`

Delayed rotation preferences become advisory reserves only. No hybrid allocator tag can force same-day close, broker execution, live orders, or real capital sizing.
