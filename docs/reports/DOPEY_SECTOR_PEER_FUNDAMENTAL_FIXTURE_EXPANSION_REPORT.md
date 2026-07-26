# DOPEY Sector / Peer / Fundamental Fixture Expansion Report

## Purpose

`DOPEY_SECTOR_PEER_FUNDAMENTAL_FIXTURE_EXPANSION_V1` broadens DOPEY's deterministic
fundamental intelligence with sector, peer-relative, fundamental, valuation,
earnings-quality, balance-sheet, sentiment-proxy, and rotation-context layers so
strategy-family consistency can be evaluated on a wider fundamental surface. The bundle
is fully offline, fixture-based, paper-only, deterministic, and live-blocked. It is
**not** real fundamentals, SEC data, analyst data, or live market evidence.

## Sector context model

`SectorContext` is a deterministic 0..1 score envelope for a sector's momentum, relative
strength, dispersion, volatility, rotation, defensive/cyclical bias, growth/value bias,
and liquidity context. It is fed by sector-style fixture scores only — no real sector
ETF prices, no real sector index data.

`SectorContext` fields:

* `sector_id`, `sector_name`, `sector_regime`
* `sector_momentum_score`, `sector_relative_strength_score`
* `sector_dispersion_score`, `sector_volatility_score`
* `sector_rotation_score`
* `defensive_cyclical_bias`, `growth_value_bias`
* `liquidity_context`
* `notes`, `version`

## Peer-relative context model

`PeerRelativeContext` is a deterministic 0..1 score envelope for a peer group
(confirmation, dispersion, leadership, breakdown pressure, contradiction, crowding).
It is not a real peer-group composition or live dispersion measurement.

`PeerRelativeContext` fields:

* `peer_group_id`, `peer_count`
* `peer_relative_strength_score`, `peer_dispersion_score`
* `peer_leadership_score`, `peer_breakdown_pressure`
* `peer_confirmation_score`, `peer_contradiction_score`
* `crowding_proxy_score`
* `notes`, `version`

## Fundamental fixture model

`FundamentalFixture` is a deterministic 0..1 proxy for a symbol's fundamental posture.
Every value is a fixture score; nothing here is a real SEC filing, real analyst number,
or real institutional flow.

`FundamentalFixture` fields:

* `fundamental_id`, `symbol`, `sector_id`
* `revenue_growth_proxy`, `margin_quality_proxy`
* `earnings_quality_proxy`, `balance_sheet_risk_proxy`
* `cash_flow_quality_proxy`, `valuation_stretch_proxy`
* `revision_momentum_proxy`, `event_catalyst_quality_proxy`
* `short_interest_pressure_proxy`
* `fundamental_trend_score`, `fundamental_fragility_score`
* `notes`, `version`

## Valuation / earnings-quality context

`ValuationContext` is derived from the fundamental + sector context and exposes
`valuation_regime`, `relative_valuation_score`, `valuation_stretch_score`,
`multiple_compression_risk`, `multiple_expansion_support`,
`growth_adjusted_value_score`, and `valuation_trap_score`.

`EarningsQualityContext` is derived from the fundamental fixture and exposes earnings,
margin, cash-flow, revenue-growth, revision-momentum, event-catalyst-quality, balance-
sheet-risk, short-interest-pressure, and fragility scores.

`FundamentalRiskSummary` is derived from the sector + peer + fundamental + valuation +
earnings-quality contexts. It exposes `fundamental_confirmation_score`,
`fundamental_contradiction_score`, `quality_score`, `fragility_score`,
`valuation_risk_score`, `peer_confirmation_score`, `sector_confirmation_score`,
`event_quality_score`, `crowding_risk_score`, `risk_flags`, and a `verdict` chosen
from `strong_fundamental_confirmation`, `sector_peer_confirmed`,
`valuation_supported`, `fundamental_neutral`, `peer_contradiction`, `valuation_trap`,
`fundamental_fragility`, `crowding_danger`, or `reject`.

`FundamentalOpportunityVerdict` is a per-(scenario, family) verdict record.

## Family-specific scoring

`fundamental_family_scoring.score_family_fundamental(strategy_family, scenario)` returns
a `FamilyFundamentalScore` with:

* `fundamental_fit_score`, `family_fundamental_fit_score`
* `sector_fit_score`, `peer_confirmation_score`
* `fundamental_confirmation_score`
* `valuation_risk_score`, `earnings_quality_score`
* `crowding_risk_score`
* `fundamental_contradiction_penalty`, `fragility_penalty`
* `risk_flags`, `verdict`

Family behavior:

### Directional convexity

* Reward: sector leadership, peer confirmation, fundamental trend, revision momentum,
  reasonable valuation, breadth/sector alignment.
* Penalize: peer contradiction, valuation trap, crowded fakeout, weak sector leadership,
  fundamental contradiction against breakout/breakdown.

### Volatility expansion

* Reward: high peer dispersion, uncertain earnings quality, margin pressure,
  revision shock, crowding unwind, event catalyst quality.
* Penalize: low dispersion, clean post-event clarity, low catalyst quality, premium
  overpayment without fundamental catalyst.

### Volatility compression

* Reward: post-event clarity, low peer dispersion, quality confirmation, stable
  defensive sector context, valuation normalization.
* Penalize: high peer dispersion, margin shock, revision shock, crowding unwind,
  sector rotation shock, valuation trap.

### Short-duration defined-risk

* Reward: clear sector/peer confirmation, low peer contradiction, adequate
  liquidity context, stable intraday sector behavior.
* Penalize: low-liquidity peer group, crowded fakeout, sector rotation late-day
  liquidity fade, high dispersion with bad fill pressure.

## Scenarios added

Eighteen deterministic scenarios are provided by
`dopey_analysis.sector_peer_scenarios`:

1. `tech_leadership_breakout_confirmed` (directional)
2. `semiconductor_peer_fakeout` (directional trap)
3. `financials_rate_tailwind_breakout` (directional)
4. `consumer_discretionary_peer_breakdown` (directional)
5. `healthcare_defensive_rotation_confirmed` (directional)
6. `earnings_quality_uncertainty_vol_expansion` (vol expansion)
7. `high_peer_dispersion_event_vol` (vol expansion)
8. `margin_pressure_gap_risk` (vol expansion)
9. `revision_shock_vol_expansion` (vol expansion)
10. `crowded_growth_unwind_vol_expansion` (vol expansion)
11. `post_earnings_quality_confirmed_iv_crush` (vol compression)
12. `low_dispersion_range_compression` (vol compression)
13. `valuation_normalization_compression` (vol compression)
14. `defensive_sector_stability_compression` (vol compression)
15. `small_cap_low_liquidity_peer_decay` (short-duration / liquidity trap)
16. `wide_peer_dispersion_bad_fill` (short-duration / liquidity trap)
17. `crowded_trade_intraday_fakeout` (short-duration / liquidity trap)
18. `sector_rotation_late_day_liquidity_fade` (short-duration / liquidity trap)

Each scenario includes a deterministic scenario hash (sorted-key SHA256 over its
fixture content) so the audit harness can verify reproducibility without recomputing
the whole registry.

## Integration impact

* `dopey_analysis.run_sector_peer_fundamental_bundle` runs the full bundle, writes the
  fundamental registry, the coverage artifact, the failure-mode registry, the
  fundamental ProofLedger record, and prints a concise JSON summary.
* `dopey_tournament.runner` consumes the fundamental scenario library per window by
  regime tag and adds `average_fundamental_fit_score`,
  `average_sector_fit_score`, `average_peer_confirmation_score`,
  `average_fundamental_confirmation_score`, `average_valuation_risk_score`,
  `average_earnings_quality_score`, `average_crowding_risk_score`,
  `average_fundamental_contradiction_penalty`, `average_fragility_penalty`,
  `family_fundamental_fit_score`, `best_fundamental_scenario`,
  `worst_fundamental_scenario`, `best_fundamental_regime`,
  `worst_fundamental_regime`, and `fundamental_risk_flags` to
  `StrategyTournamentScore`. The combined score now includes a small
  `0.03 * fundamental_fit - 0.02 * fundamental_contradiction` term.
* `dopey_tournament.models.TournamentResult` adds `fundamental_expansion_version`,
  `fundamental_summary`, and `family_fundamental_scores`.
* `dopey_tournament.models.ChampionRegistryEntry` records
  `average_fundamental_fit_score`, `average_sector_fit_score`,
  `average_peer_confirmation_score`, `average_valuation_risk_score`,
  `average_earnings_quality_score`, `average_crowding_risk_score`,
  `average_fundamental_contradiction_penalty`, `average_fragility_penalty`,
  `fundamental_risk_flags`, `best_fundamental_scenario`,
  `worst_fundamental_scenario`, and `fundamental_summary`.
* `dopey_strategy_lab.failure_mode_miner` adds ten new fundamental failure modes
  (`peer_contradiction_against_directional`, `valuation_trap_against_directional`,
  `low_dispersion_against_vol_expansion`, `post_event_clarity_against_vol_expansion`,
  `high_dispersion_against_compression`, `revision_shock_against_compression`,
  `crowded_fakeout_against_short_duration`, `small_cap_liquidity_decay_against_short_duration`,
  `sector_rotation_late_day_bad_fill`, `fundamental_event_overfit`).
* `dopey_strategy_lab.constraint_tuning` automatically surfaces the new
  recommendations via the existing failure-mode-driven feedback loop.
* `dopey_audit.artifact_loader` recognizes the new
  `fundamental_registry`, `fundamental_coverage`, and `fundamental_ledger` artifact
  types. `dopey_audit.hash_auditor.STRICT_HASH_TYPES` includes
  `fundamental_registry`. `dopey_audit.evidence_gap_planner` records new
  `weak_sector_peer_fundamental_evidence` and `sector_peer_fundamental_missing` gap
  categories and recommends `deterministic_sector_peer_fundamental_fixture_expansion`
  as the next build target.
* `dopey_governor.proof_evidence_loader.EVIDENCE_PATHS` and
  `EvidenceBundle` carry a new `fundamental_fixtures` layer. The meta-governor
  proof-quality layer list adds `sector_peer_fundamental_fixtures`.

## Limitations

* All sector/peer/fundamental/valuation/crowding scores are deterministic 0..1
  fixture proxies. They are not real sector ETF prices, real sector index data, real
  peer-group compositions, real SEC filings, real analyst estimates, or real
  institutional flow.
* The fundamental expansion remains fixture-based, paper-only, offline, and
  live-blocked. It is not empirical performance evidence, not profit evidence, and
  not a claim about live trading.
* Live trading is impossible from this path; no broker connection, credentials, or
  network access is involved.

## Safety state

* `mode=RESEARCH`
* `live_trading_enabled=false`
* `funded_broker_connections_enabled=false`
* `allow_unofficial_robinhood_api=false`
* `paper_only_fundamental_bundle=true`
* `live_blocked=true`
* PaperBroker refuses `live_allowed=true`
* Robinhood / Alpaca / Tradier adapters raise `LiveTradingDisabledError`
* No broker connection, credentials, network access, scheduled run, or live promotion
* Blunder source manifest verified when available
