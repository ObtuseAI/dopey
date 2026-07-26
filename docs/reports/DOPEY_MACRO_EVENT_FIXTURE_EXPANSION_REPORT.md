# DOPEY Macro-Event Fixture Expansion Report

## Purpose

`DOPEY_MACRO_EVENT_FIXTURE_EXPANSION_BUNDLE_V1` adds deterministic macro-event, rates,
volatility-index, sector-rotation, breadth, liquidity-regime, overnight/futures-pressure, and
risk-on/risk-off fixture intelligence to DOPEY paper replay. The bundle sharpens family-level
scoring, mutation constraints, failure-mode detection, and feedback optimization without touching
live execution, real macro calendars, real FRED/VIX/futures data, or broker connections.

## Model versions

- Macro-event fixture model: `dopey-macro-event-fixture-v1`
- Macro-event scenario library: `dopey-macro-event-scenarios-v1`
- Macro family scoring: `dopey-macro-family-scoring-v1`
- Macro-event expansion: `dopey-macro-event-expansion-v1`
- Bundle runner: `dopey-macro-event-fixture-expansion-bundle-v1`

## Files added

- `dopey_analysis/macro_event_fixture.py`
- `dopey_analysis/macro_event_scenarios.py`
- `dopey_analysis/macro_family_scoring.py`
- `dopey_analysis/run_macro_event_bundle.py`
- `tests/test_macro_event_fixture_expansion.py`
- `DOPEY_MACRO_EVENT_FIXTURE_EXPANSION_REPORT.md`
- `DOPEY_MACRO_EVENT_SCENARIO_LEDGER.md`

## Files modified

- `dopey_analysis/analysis_fusion.py` — optionally accepts a `MacroEventScenario` and strategy
  family to adjust the macro layer score deterministically.
- `dopey_tournament/runner.py` — computes per-window macro event scores, blends macro fit/risk
  into the combined tournament score, and records macro summaries in ranking, ProofLedger, and
  champion registry.
- `dopey_tournament/models.py` — adds macro-event fields to `StrategyTournamentScore`,
  `TournamentResult`, and `ChampionRegistryEntry`.
- `dopey_tournament/ledger_tournament.py` — carries macro-event evidence into tournament
  ProofLedger records.
- `dopey_strategy_lab/failure_mode_miner.py` — detects macro-event-specific failure modes.
- `dopey_strategy_lab/constraint_tuning.py` — emits macro-aware feedback recommendations.
- `dopey_strategy_lab/mutation_scorecard.py` — honors the `macro_event_guard` parameter.
- `tests/test_tournament.py` and `tests/test_iv_surface_skew_expansion.py` — updated to pass
  macro fit/risk into the deterministic combined-score check.

## Macro-event fixture model

The core model introduces six deterministic dataclasses:

- `MacroEventFixture` — event type, intensity, surprise direction, risk-on/off bias, volatility
  impulse, rates/dollar/sector/breadth/liquidity/overnight pressures.
- `MacroRegimeContext` — full macro-regime score snapshot (risk-on/off, rate-shock, inflation,
  dollar, VIX/VVIX stress, breadth, sector rotation, liquidity, overnight, trend, fakeout).
- `MacroEventRiskSummary` — family-agnostic scores: macro-shock, vol-expansion support,
  compression danger, directional confirmation, directional fakeout, short-duration liquidity
  risk, macro contradiction, event-gap risk, risk flags, and verdict.
- `MacroShockProfile` and `MacroOpportunityVerdict` — diagnostic helpers.
- `MacroEventScenario` — binds an event fixture, regime context, risk summary, preferred/penalized
  families, and expected IV/slippage/pattern/failure effects.
- `FamilyMacroEventScore` — per-family deterministic macro fit, opportunity, risk, event/rate/VIX/
  breadth/liquidity scores, contradiction penalty, event-gap penalty, risk flags, and verdict.

All values are 0..1 fixture math. No real macro data is used.

## Scenario library

The bundle ships 14 deterministic scenarios:

1. `pre_fomc_vol_expansion`
2. `post_fomc_iv_crush`
3. `hot_cpi_rate_shock`
4. `cool_cpi_risk_on_rebound`
5. `ppi_inflation_pressure`
6. `jobs_growth_shock`
7. `dollar_squeeze_risk_off`
8. `vix_vvix_spike`
9. `breadth_breakdown`
10. `sector_rotation_growth_to_value`
11. `liquidity_contraction_bad_fill`
12. `overnight_gap_risk`
13. `risk_on_breakout_confirmation`
14. `risk_off_breakdown_confirmation`

See `DOPEY_MACRO_EVENT_SCENARIO_LEDGER.md` for per-scenario preferred/penalized families, risk
flags, expected IV/slippage/pattern effects, and intended test coverage.

## Family-specific macro scoring

### Directional convexity

Rewards: risk-on/breakout confirmation, risk-off/breakdown confirmation, breadth/sector
alignment, controlled event-gap risk.
Penalizes: macro fakeout, overnight gap without confirmation, volatility shock without
directional clarity, breadth contradiction.

### Volatility expansion

Rewards: pre-event uncertainty, VIX/VVIX stress, macro-shock potential, overnight/futures
pressure, rate-shock/inflation-surprise windows.
Penalizes: post-event crush, low event intensity, premium overpayment without catalyst, declining
vol regime.

### Volatility compression

Rewards: post-event normalization, risk-on stabilization, lower VIX/VVIX, range-bound macro
neutrality, liquidity normalization.
Penalizes: macro-shock danger, event-gap risk, VIX/VVIX spike, rate shock, breadth breakdown.

### Short-duration defined-risk

Rewards: clean intraday directional confirmation, high liquidity, low event-gap risk after an
event, stable VIX/VVIX.
Penalizes: event-gap windows, liquidity contraction, overnight pressure, macro fakeout, VIX/VVIX
spike, bad-fill macro regimes.

## Integration

Macro-event scoring flows through:

- `fuse_analysis()` — macro score is adjusted by family/scenario fit.
- `run_fixture_tournament()` — per-window scenario matching, per-family macro scores, macro
  fit/risk blended into combined score.
- `mine_failure_modes()` — emits macro-specific failure modes.
- `build_constraint_tuning_recommendations()` — emits macro guard recommendations.
- `_weight_adjustment()` — applies `macro_event_guard` mutation scorecard adjustment.
- Champion registry and ProofLedger — record average macro fit, best/worst macro regimes,
  macro failure modes, event-risk robustness, VIX/VVIX stress robustness, breadth/sector
  confirmation, and macro-contradiction score.

## Bundle result

Latest `python -m dopey_analysis.run_macro_event_bundle` result:

- Bundle status: `ok`
- Macro scenarios loaded: `14`
- Families scored: `directional_convexity`, `short_duration_defined_risk`,
  `volatility_compression`, `volatility_expansion`
- Best macro fit family: `volatility_expansion`
- Worst macro risk family: `volatility_compression`
- Tournament champion: `genome-directional-convexity-spy-fixture-v1`
- Champion score after macro-event integration: `0.554815`
- Runner-up delta: `0.017632`
- New macro failure modes detected:
  - `breadth_contradiction_against_directional`
  - `event_gap_against_short_duration`
  - `liquidity_contraction_bad_fill_failure`
  - `macro_fakeout_against_directional`
  - `overnight_gap_slippage_failure`
  - `post_event_crush_against_vol_expansion`
  - `rate_shock_against_compression`
  - `sector_rotation_mismatch`
  - `vix_spike_against_compression`
- Macro registry: `artifacts/dopey/macro_events/macro_event_registry.jsonl`
- Macro ProofLedger: `artifacts/dopey/macro_events/macro_event_bundle.jsonl`
- Failure-mode registry refreshed: `artifacts/dopey/failure_modes/failure_mode_registry.jsonl`

## Family macro ranking

| Family | Avg macro fit | Avg macro opportunity | Avg macro risk | Best macro regime | Worst macro regime |
|---|---|---|---|---|---|
| volatility_expansion | 0.481580 | 0.551756 | 0.487963 | event_vol_expansion | bullish_breakout |
| short_duration_defined_risk | 0.262657 | 0.497599 | 0.514630 | bullish_breakout | macro_shock_risk_off |
| directional_convexity | 0.240256 | 0.522782 | 0.505741 | bullish_breakout | low_liquidity_decay |
| volatility_compression | 0.229920 | 0.483681 | 0.523519 | post_event_iv_crush | macro_shock_risk_off |

## New feedback recommendations

The macro bundle adds recommendations such as:

- `macro_fakeout_penalty`
- `macro_contradiction_penalty`
- `event_gap_guard`
- `short_duration_event_bump_penalty`
- `rate_shock_avoidance`
- `compression_macro_term_guard`
- `vix_vvix_stress_guard`
- `compression_vol_stress_penalty`
- `post_event_crush_avoidance`
- `breadth_confirmation_guard`
- `macro_breadth_penalty`
- `liquidity_contraction_guard`
- `overnight_risk_penalty`
- `sector_alignment_guard`
- `macro_holdout_weighting`

All recommendations are advisory or replay-only.

## Validation

- `python -m pytest` -> `255 passed` (227 prior + 28 macro-event tests)
- Macro-event focused tests -> `28 passed`
- Import smoke -> `MACRO_EVENT_IMPORT_OK`
- Macro scenario import smoke -> `MACRO_SCENARIOS_IMPORT_OK scenarios=14 families=4`
- Tournament smoke -> `tournament_status: ok`
- Mutation population smoke -> `bundle_status: ok`
- Feedback optimizer smoke -> `optimizer_status: ok`
- IV surface bundle smoke -> `bundle_status: ok`
- Macro event bundle smoke -> `bundle_status: ok`
- Blunder integrity -> `BLUNDER_INTEGRITY_OK checked=78`

## Safety state

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- PaperBroker still rejects `live_allowed=true`
- Robinhood/Alpaca/Tradier stubs still raise `LiveTradingDisabledError`
- No broker connection, credentials, network market data, live trades, live promotion,
  autonomous scheduled run, heavy dependency, commit, or Blunder source modification

## Limitations

- Macro-event scores are deterministic fixture math, not calibrated live macro data.
- Scores are paper replay evidence, not profit claims or live readiness.
- Scenarios intentionally stress failure-mode detection; they are not market forecasts.
- No real CPI/PPI/FOMC calendar, FRED data, VIX feed, futures data, or broker execution is used.

## Next recommended build target

Offline ensemble strategy allocator.
