# DOPEY IV Surface Scenario Ledger

All scenarios are deterministic offline fixtures. They are used only for paper replay, tournament
scoring, mutation-compatible rows, failure-mode mining, and feedback recommendations.

| Scenario | Regime | Preferred Families | Penalized Families | Risk Flags | Verdict |
| --- | --- | --- | --- | --- | --- |
| `pre_event_vol_expansion` | `event_vol_expansion` | volatility_expansion, directional_convexity | volatility_compression, short_duration_defined_risk | iv_expansion_opportunity, front_expiry_event_bump, wing_elevation, backwardation | `excellent_expansion_setup` |
| `post_event_iv_crush` | `post_event_iv_crush` | volatility_compression | volatility_expansion | iv_crush_danger, contango | `iv_crush_danger` |
| `macro_shock_backwardation` | `macro_shock_risk_off` | volatility_expansion | volatility_compression, short_duration_defined_risk | iv_expansion_opportunity, front_expiry_event_bump, wing_elevation, surface_instability, backwardation | `good_expansion_setup` |
| `range_bound_compression` | `range_bound_pin` | volatility_compression | volatility_expansion | iv_crush_danger | `iv_crush_danger` |
| `bullish_call_skew_breakout` | `bullish_breakout` | directional_convexity, short_duration_defined_risk | volatility_compression | none | `neutral_surface` |
| `bearish_put_skew_breakdown` | `bearish_breakdown` | directional_convexity, volatility_expansion | volatility_compression | none | `neutral_surface` |
| `premium_overpayment_trap` | `liquidity_decay` | none | directional_convexity, volatility_expansion, volatility_compression, short_duration_defined_risk | iv_crush_danger, premium_overpayment_trap, wing_elevation | `premium_overpayment_trap` |
| `stable_low_iv_breakout` | `trend_vol_expansion` | directional_convexity, short_duration_defined_risk | volatility_compression | none | `neutral_surface` |
| `unstable_surface_fakeout` | `gap_reversal` | none | directional_convexity, short_duration_defined_risk | wing_elevation, surface_instability | `reject` |
| `low_liquidity_wide_skew` | `low_liquidity_decay` | none | directional_convexity, volatility_compression, short_duration_defined_risk | wing_elevation, surface_instability, contango | `fragile_surface` |
| `front_expiry_event_bump` | `high_spread_bad_fill` | volatility_expansion | volatility_compression, short_duration_defined_risk | iv_expansion_opportunity, front_expiry_event_bump, wing_elevation, backwardation | `good_expansion_setup` |
| `normal_contango_chop` | `chop_vol_compression` | volatility_compression, short_duration_defined_risk | volatility_expansion | contango | `neutral_surface` |

## Intended Test Coverage

- Serialization determinism for `IVSurfacePoint`
- Scenario inventory coverage for all 12 required fixtures
- IV crush danger, expansion setup, and premium overpayment trap summaries
- Put-skew vs call-skew profile separation
- Front-event-bump and backwardation term-state detection
- Skew/term score influence on family fit
- Family-specific reward and penalty behavior for directional, expansion, compression, and
  short-duration structures
- Tournament score integration
- Mutation scoring IV surface guard
- Failure-mode mining and feedback recommendations
- Champion registry and ProofLedger IV surface evidence
- Live safety regression tests

