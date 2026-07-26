# DOPEY Sector / Peer / Fundamental Scenario Ledger

All scenarios are deterministic offline fixture scenarios. No real sector, peer, or
fundamental data is used.

## 1. tech_leadership_breakout_confirmed

* sector: `tech` (Information Technology) leadership_breakout
* sector momentum: 0.85, relative strength: 0.88, dispersion: 0.30, volatility: 0.35,
  rotation: 0.45, deep liquidity
* peer group: tech_megacap (8 peers), confirmation: 0.82, contradiction: 0.15
* fundamental: AAPL, revenue: 0.65, margin: 0.78, earnings: 0.80, balance sheet risk: 0.10,
  cash flow: 0.85, valuation stretch: 0.55, revisions: 0.65
* preferred: directional_convexity, short_duration_defined_risk
* penalized: volatility_compression
* expected failure modes: valuation_stretch_against_directional
* deterministic hash: derived from `scenario_hash(scenario)`

## 2. semiconductor_peer_fakeout

* sector: `semis` (Semiconductors) exhaustion_fakeout
* sector momentum: 0.55, dispersion: 0.75, volatility: 0.70
* peer group: semis_group (12 peers), confirmation: 0.32, contradiction: 0.72,
  crowding: 0.68
* fundamental: NVDA, valuation stretch: 0.80, revisions: 0.30, fragility: 0.42
* preferred: volatility_expansion
* penalized: directional_convexity, short_duration_defined_risk
* expected failure modes: peer_contradiction_against_directional,
  valuation_trap_against_directional

## 3. financials_rate_tailwind_breakout

* sector: `financials` rate_tailwind
* peer group: banks_group (10 peers), confirmation: 0.78, contradiction: 0.18
* fundamental: JPM, margin: 0.70, earnings: 0.72, revisions: 0.75
* preferred: directional_convexity, short_duration_defined_risk
* penalized: volatility_compression
* expected failure modes: none

## 4. consumer_discretionary_peer_breakdown

* sector: `consumer_disc` peer_breakdown
* peer group: consumer_disc_group (9 peers), dispersion: 0.72, contradiction: 0.78
* fundamental: AMZN, fragility: 0.50, revisions: 0.30
* preferred: volatility_expansion, directional_convexity
* penalized: volatility_compression, short_duration_defined_risk
* expected failure modes: peer_contradiction_against_compression,
  fundamental_fragility_against_short_duration

## 5. healthcare_defensive_rotation_confirmed

* sector: `healthcare` defensive_rotation
* peer group: pharma_group (7 peers), confirmation: 0.72
* fundamental: JNJ, low fragility, low valuation stretch
* preferred: directional_convexity, volatility_compression,
  short_duration_defined_risk
* penalized: volatility_expansion
* expected failure modes: none

## 6. earnings_quality_uncertainty_vol_expansion

* sector: `blend` earnings_uncertainty
* peer group: earnings_group (10 peers), dispersion: 0.70
* fundamental: MIXED, weak revisions, fragile thesis
* preferred: volatility_expansion
* penalized: volatility_compression, directional_convexity
* expected failure modes: post_event_crush_against_vol_expansion,
  low_dispersion_against_vol_expansion

## 7. high_peer_dispersion_event_vol

* sector: `blend` high_dispersion
* peer group: high_dispersion_group (12 peers), dispersion: 0.85
* preferred: volatility_expansion
* penalized: volatility_compression, short_duration_defined_risk
* expected failure modes: post_event_clarity_against_vol_expansion

## 8. margin_pressure_gap_risk

* sector: `blend` margin_pressure, thin liquidity
* peer group: margin_pressure_group (8 peers), dispersion: 0.68
* fundamental: ABC, severe margin pressure, balance sheet risk 0.55
* preferred: volatility_expansion
* penalized: directional_convexity, volatility_compression,
  short_duration_defined_risk
* expected failure modes: fundamental_fragility_against_directional,
  margin_pressure_against_compression

## 9. revision_shock_vol_expansion

* sector: `blend` revision_shock
* peer group: revision_shock_group (9 peers), dispersion: 0.72
* fundamental: DEF, revision_momentum: 0.10
* preferred: volatility_expansion
* penalized: volatility_compression, directional_convexity
* expected failure modes: revision_shock_against_compression,
  low_dispersion_against_vol_expansion

## 10. crowded_growth_unwind_vol_expansion

* sector: `growth` crowded_unwind
* peer group: growth_crowded_group (10 peers), dispersion: 0.80, crowding: 0.85
* fundamental: GHI, valuation stretch: 0.78, fragility: 0.55
* preferred: volatility_expansion
* penalized: directional_convexity, volatility_compression,
  short_duration_defined_risk
* expected failure modes: crowding_danger_against_directional,
  crowding_danger_against_short_duration

## 11. post_earnings_quality_confirmed_iv_crush

* sector: `blend` post_earnings_clarity
* peer group: post_earnings_group (9 peers), confirmation: 0.78
* fundamental: JKL, high quality, low fragility
* preferred: volatility_compression, short_duration_defined_risk
* penalized: volatility_expansion
* expected failure modes: post_event_clarity_against_vol_expansion

## 12. low_dispersion_range_compression

* sector: `blend` low_dispersion_range
* peer group: low_dispersion_group (8 peers), dispersion: 0.22
* fundamental: MNO, average quality
* preferred: volatility_compression, short_duration_defined_risk
* penalized: volatility_expansion
* expected failure modes: high_dispersion_against_compression

## 13. valuation_normalization_compression

* sector: `blend` valuation_normalization
* peer group: valuation_norm_group (9 peers), confirmation: 0.65
* fundamental: PQR, valuation stretch: 0.30, revisions: 0.55
* preferred: volatility_compression, short_duration_defined_risk
* penalized: volatility_expansion
* expected failure modes: high_dispersion_against_compression,
  revision_shock_against_compression

## 14. defensive_sector_stability_compression

* sector: `utilities` defensive_stability
* peer group: utilities_group (6 peers), confirmation: 0.72
* fundamental: STU, low fragility
* preferred: volatility_compression, short_duration_defined_risk,
  directional_convexity
* penalized: volatility_expansion
* expected failure modes: high_dispersion_against_compression

## 15. small_cap_low_liquidity_peer_decay

* sector: `small_cap` low_liquidity_decay
* peer group: small_cap_group (10 peers), dispersion: 0.78, contradiction: 0.72
* fundamental: VWX, fragile, low liquidity
* preferred: volatility_expansion
* penalized: short_duration_defined_risk, volatility_compression,
  directional_convexity
* expected failure modes: small_cap_liquidity_decay_against_short_duration,
  crowded_fakeout_against_short_duration

## 16. wide_peer_dispersion_bad_fill

* sector: `blend` wide_dispersion_bad_fill
* peer group: wide_dispersion_group (10 peers), dispersion: 0.80
* fundamental: YZA, average quality
* preferred: volatility_expansion
* penalized: short_duration_defined_risk, volatility_compression
* expected failure modes: small_cap_liquidity_decay_against_short_duration

## 17. crowded_trade_intraday_fakeout

* sector: `blend` crowded_intraday_fakeout
* peer group: crowded_intraday_group (9 peers), contradiction: 0.65, crowding: 0.85
* fundamental: BCD, average quality
* preferred: volatility_expansion
* penalized: short_duration_defined_risk, directional_convexity
* expected failure modes: crowded_fakeout_against_short_duration,
  crowding_danger_against_directional

## 18. sector_rotation_late_day_liquidity_fade

* sector: `blend` sector_rotation_late_day
* peer group: rotation_late_day_group (9 peers), dispersion: 0.72, contradiction: 0.68
* fundamental: EFG, average quality
* preferred: volatility_expansion
* penalized: short_duration_defined_risk, directional_convexity,
  volatility_compression
* expected failure modes: sector_rotation_late_day_bad_fill,
  small_cap_liquidity_decay_against_short_duration
