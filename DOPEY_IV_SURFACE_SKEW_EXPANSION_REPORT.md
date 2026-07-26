# DOPEY IV Surface Skew Expansion Report

## Purpose

`DOPEY_IV_SURFACE_SKEW_EXPANSION_BUNDLE_V1` adds deterministic IV surface, skew,
term-structure, and volatility-regime transition intelligence to paper replay. The goal is to
make fixture scoring more sensitive to IV crush, IV expansion, skew distortion, front-expiry event
bumps, backwardation, wing elevation, unstable surfaces, compression opportunities, and premium
overpayment traps.

This bundle is offline, fixture-only, paper-only, and live-blocked. It does not use real market
data, broker connections, credentials, live trades, QuantLib, py_vollib, or scheduled execution.

## Model Versions

- IV surface expansion: `dopey-iv-surface-expansion-v1`
- IV surface scenarios: `dopey-iv-surface-scenarios-v1`
- Skew and term structure: `dopey-skew-term-structure-v1`
- Family IV scoring: `dopey-iv-family-scoring-v1`
- Volatility-regime transition: `dopey-volatility-regime-transition-v1`
- Bundle runner: `dopey-iv-surface-skew-expansion-bundle-v1`

## Files Added

- `dopey_options/iv_surface_expansion.py`
- `dopey_options/iv_surface_scenarios.py`
- `dopey_options/skew_term_structure.py`
- `dopey_options/iv_family_scoring.py`
- `dopey_options/volatility_regime.py`
- `dopey_options/run_iv_surface_skew_bundle.py`
- `tests/test_iv_surface_skew_expansion.py`
- `DOPEY_IV_SURFACE_SKEW_EXPANSION_REPORT.md`
- `DOPEY_IV_SURFACE_SCENARIO_LEDGER.md`

## IV Surface Scenario Model

The new surface layer represents deterministic scenario fixtures with:

- IV rank and percentile
- realized volatility and implied-vs-realized gap
- front-expiry event bump
- term slope
- put skew and call skew
- wing elevation
- IV crush risk
- IV expansion potential
- surface instability
- preferred and penalized strategy families

`IVSurfaceGrid` builds a deterministic front/back, ATM/wing surface for each scenario.
`IVSurfaceRiskSummary` converts each grid into risk flags and a verdict such as
`excellent_expansion_setup`, `compression_opportunity`, `iv_crush_danger`, or
`premium_overpayment_trap`.

## Skew And Term Structure

`SkewProfile` separates put-skew pressure, call-skew pressure, skew steepness, tail pressure,
skew opportunity, and skew-trap risk.

`TermStructureProfile` separates front IV, back IV, term slope, event bump score, backwardation,
contango, roll-down risk, term opportunity, and term risk. Supported term states are:

- `normal_contango`
- `flat`
- `front_event_bump`
- `backwardation`
- `post_event_collapse`
- `unstable`

## Family IV Scoring

The family scorer now evaluates:

- Directional convexity: rewards moderate IV, stable surfaces, usable skew alignment, and
  reasonable premium; penalizes premium overpayment, IV crush, skew traps, and unstable fakeouts.
- Volatility expansion: rewards IV expansion potential, event bump, backwardation, elevated
  wings, and skew/term fit; penalizes post-event crush, high IV without catalyst, premium
  overpayment, and unstable surfaces without movement confirmation.
- Volatility compression: rewards IV crush, post-event collapse, normalizing term structure,
  controlled skew, and stable surfaces; penalizes event bumps, backwardation, elevated wings, and
  unstable skew.
- Short-duration defined-risk: rewards stable front IV, low premium, low skew trap, low term
  risk, and tight surfaces; penalizes event bumps, unstable term structure, skew traps, and IV
  mismatch.

## Integration

The expanded surface metrics are carried through:

- walk-forward replay results
- walk-forward score summaries
- tournament ranking
- family scorecards
- champion registry records
- ProofLedger tournament records
- mutation/evolution rows
- mutation scorecard IV guards
- failure-mode miner
- failure-feedback recommendation generation
- IV surface bundle registry and ProofLedger records

The tournament now stores average IV surface fit, family IV fit, skew/term score, premium
overpayment score, IV crush score, IV expansion score, front-event-bump score, skew-trap score,
wing-elevation score, surface-instability penalty, term-structure risk penalty, and IV mismatch
penalty.

## Bundle Result

Latest `python -m dopey_options.run_iv_surface_skew_bundle` result:

- Bundle status: `ok`
- Surface scenarios loaded: `12`
- Families scored: `directional_convexity`, `short_duration_defined_risk`,
  `volatility_compression`, `volatility_expansion`
- Best IV fit family: `short_duration_defined_risk`
- Worst IV trap family: `directional_convexity`
- Tournament champion: `genome-directional-convexity-spy-fixture-v1`
- Champion score after IV expansion integration: `0.560797`
- Runner-up delta: `0.017781`
- IV surface registry: `artifacts/dopey/iv_surface/iv_surface_registry.jsonl`
- IV surface ProofLedger: `artifacts/dopey/iv_surface/iv_surface_skew_bundle.jsonl`
- Failure-mode registry refreshed: `artifacts/dopey/failure_modes/failure_mode_registry.jsonl`

## New Failure Modes

The IV bundle emits these deterministic surface-specific failure modes:

- `premium_overpayment_trap_failure`
- `iv_crush_after_vol_expansion_failure`
- `front_event_bump_against_compression`
- `backwardation_against_compression`
- `skew_trap_against_directional`
- `surface_instability_fakeout_failure`
- `short_duration_front_iv_instability`
- `term_structure_mismatch`
- `wing_elevation_breakout_risk`

## Feedback Recommendations

The refreshed feedback path can now recommend:

- `premium_overpayment_penalty`
- `iv_entry_value_guard`
- `post_event_crush_avoidance`
- `iv_expansion_confirmation`
- `front_event_bump_guard`
- `compression_term_guard`
- `compression_macro_term_guard`
- `term_structure_penalty`
- `directional_skew_alignment`
- `skew_trap_penalty`
- `surface_stability_guard`
- `fakeout_surface_penalty`
- `short_duration_front_iv_guard`
- `short_duration_event_bump_penalty`
- `term_structure_family_fit`
- `term_risk_penalty`
- `wing_elevation_breakout_guard`
- `skew_wing_confirmation`

## Validation

- `python -m pytest` -> `227 passed`
- IV surface focused tests -> `26 passed`
- Import smoke -> `IV_SURFACE_SKEW_IMPORT_OK scenarios=12 families=4`
- Tournament smoke -> `tournament_status: ok`
- Mutation population smoke -> `bundle_status: ok`
- Feedback optimizer smoke after IV registry refresh -> `optimizer_status: ok`,
  `failure_modes_loaded: 57`, `recommendations_generated: 83`
- IV surface bundle smoke -> `bundle_status: ok`
- Blunder integrity -> `BLUNDER_INTEGRITY_OK checked=78`

## Safety State

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- PaperBroker still rejects `live_allowed=true`
- Robinhood, Alpaca, and Tradier stubs still raise `LiveTradingDisabledError`
- No broker credentials, broker connection, network market data, live trade, live promotion,
  autonomous scheduled run, heavy dependency, commit, or Blunder source modification

## Limitations

- The model is deterministic fixture math, not calibrated live-market IV modeling.
- Scores are paper replay evidence, not profit claims or live readiness.
- Surface stress rows intentionally expose failure-mode detection; they are not market data.
- No queue position, routing, partial-fill, real quote, or live volatility-source model is added.

