# DOPEY Macro-Event Scenario Ledger

All macro scenarios are deterministic offline fixtures. They are used only for paper replay,
tournament scoring, mutation-compatible rows, failure-mode mining, and feedback recommendations.

| Scenario | Regime | Preferred Families | Penalized Families | Risk Flags | Verdict |
| --- | --- | --- | --- | --- | --- |
| `pre_fomc_vol_expansion` | `event_vol_expansion` | volatility_expansion | volatility_compression, short_duration_defined_risk | vol_expansion_supported, event_gap_risk | `vol_expansion_supported` |
| `post_fomc_iv_crush` | `post_event_iv_crush` | volatility_compression, short_duration_defined_risk | volatility_expansion | compression_macro_danger (low) | `macro_neutral` / compression supported |
| `hot_cpi_rate_shock` | `macro_shock_risk_off` | volatility_expansion, directional_convexity | volatility_compression, short_duration_defined_risk | macro_shock_danger, compression_macro_danger, event_gap_risk | `macro_shock_danger` |
| `cool_cpi_risk_on_rebound` | `bullish_breakout` | directional_convexity, short_duration_defined_risk | volatility_compression | directional_confirmed | `directional_confirmed` |
| `ppi_inflation_pressure` | `event_vol_expansion` | volatility_expansion | volatility_compression, directional_convexity | vol_expansion_supported, directional_fakeout_risk | `macro_fakeout_risk` / vol supported |
| `jobs_growth_shock` | `trend_vol_expansion` | directional_convexity, volatility_expansion | volatility_compression | directional_confirmed | `directional_confirmed` |
| `dollar_squeeze_risk_off` | `macro_shock_risk_off` | volatility_expansion, directional_convexity | volatility_compression, short_duration_defined_risk | macro_shock_danger, short_duration_bad_fill_risk | `macro_shock_danger` |
| `vix_vvix_spike` | `event_vol_expansion` | volatility_expansion | volatility_compression, short_duration_defined_risk, directional_convexity | vol_expansion_supported, short_duration_bad_fill_risk | `vol_expansion_supported` |
| `breadth_breakdown` | `bearish_breakdown` | directional_convexity, volatility_expansion | volatility_compression, short_duration_defined_risk | macro_shock_danger, directional_confirmed | `macro_shock_danger` / directional confirmed |
| `sector_rotation_growth_to_value` | `chop_vol_compression` | volatility_compression, short_duration_defined_risk | directional_convexity | directional_fakeout_risk, macro_contradiction | `macro_fakeout_risk` |
| `liquidity_contraction_bad_fill` | `low_liquidity_decay` | volatility_expansion | short_duration_defined_risk, volatility_compression, directional_convexity | short_duration_bad_fill_risk | `short_duration_bad_fill_risk` |
| `overnight_gap_risk` | `gap_reversal` | volatility_expansion | directional_convexity, short_duration_defined_risk | directional_fakeout_risk, event_gap_risk | `macro_fakeout_risk` |
| `risk_on_breakout_confirmation` | `bullish_breakout` | directional_convexity, short_duration_defined_risk | volatility_expansion, volatility_compression | directional_confirmed | `directional_confirmed` |
| `risk_off_breakdown_confirmation` | `bearish_breakdown` | directional_convexity, volatility_expansion | volatility_compression, short_duration_defined_risk | macro_shock_danger | `macro_shock_danger` |

## Expected effects

| Scenario | Expected IV effect | Expected slippage effect | Expected pattern effect | Expected failure modes |
|---|---|---|---|---|
| `pre_fomc_vol_expansion` | iv_expansion_expected | wider_spreads_event_vol | vol_expansion_pattern_preferred | premium_overpayment, macro_fakeout_against_directional |
| `post_fomc_iv_crush` | iv_crush_expected | tighter_spreads_post_event | range_pin_pattern_preferred | post_event_crush_against_vol_expansion |
| `hot_cpi_rate_shock` | iv_spike_and_skew_shift | wide_spreads_bad_fills | breakdown_continuation_risk_off | rate_shock_against_compression, macro_shock_danger |
| `cool_cpi_risk_on_rebound` | iv_compression_relief | clean_fills | bullish_breakout_continuation | none |
| `ppi_inflation_pressure` | iv_expansion_from_inflation_fear | widening_spreads | macro_shock_vol_transition | macro_fakeout_against_directional |
| `jobs_growth_shock` | iv_lift_with_trend | moderate_spread_widening | trend_vol_continuation | breadth_contradiction_against_directional |
| `dollar_squeeze_risk_off` | iv_risk_premium_expansion | severe_bad_fill_pressure | risk_off_breakdown | liquidity_contraction_bad_fill_failure |
| `vix_vvix_spike` | iv_expansion_and_skew_steepening | wide_spreads | vol_expansion_stress | vix_spike_against_compression, short_duration_bad_fill_risk |
| `breadth_breakdown` | iv_lift_from_breadth_stress | widening_spreads | bearish_breakdown_breadth | breadth_contradiction_against_directional |
| `sector_rotation_growth_to_value` | range_bound_iv | moderate_dispersion_spreads | chop_fakeout | sector_rotation_mismatch, macro_fakeout_against_directional |
| `liquidity_contraction_bad_fill` | iv_lift_from_liquidity_stress | severe_bad_fills | liquidity_trap | liquidity_contraction_bad_fill_failure |
| `overnight_gap_risk` | gap_iv_jump | gap_slippage | gap_reversal_fakeout | overnight_gap_slippage_failure, macro_fakeout_against_directional |
| `risk_on_breakout_confirmation` | iv_floor_low | tight_spreads | bullish_breakout_confirmation | none |
| `risk_off_breakdown_confirmation` | iv_spike_risk_off | wide_spreads_breakdown | bearish_breakdown_confirmation | macro_shock_danger |

## Intended test coverage

- Serialization determinism for `MacroEventFixture`, `MacroRegimeContext`, `MacroEventRiskSummary`,
  `MacroEventScenario`, and `FamilyMacroEventScore`
- Scenario inventory coverage for all 14 required fixtures
- `summarize_macro_risk` identifies macro-shock danger, directional confirmation, and
  short-duration bad-fill risk
- Family-specific reward/penalty behavior for directional, expansion, compression, and
  short-duration structures across macro scenarios
- `fuse_analysis` changes when a `MacroEventScenario` and strategy family are supplied
- Tournament score integration and `combined_score` formula include macro fit/risk
- Mutation scorecard uses the `macro_event_guard` parameter
- Failure-mode miner detects macro event failures
- Feedback optimizer recommends macro guards
- Champion registry and ProofLedger macro-event evidence
- Live safety regression tests (no live promotion, live stubs still block, PaperBroker refuses
  live, config stays RESEARCH, Blunder integrity preserved)
