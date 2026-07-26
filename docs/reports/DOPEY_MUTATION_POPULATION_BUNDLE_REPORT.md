# DOPEY Mutation Population Bundle Report

## Scope

This report records the offline mutation-population and structure-builder bundle. The bundle is
fixture-only and paper-only. It does not fetch network data, use broker credentials, promote live
trading, start scheduled automation, or modify Blunder source code.

## Implemented modules

- `dopey_strategy_lab/mutation_population.py`
- `dopey_strategy_lab/population_sampler.py`
- `dopey_strategy_lab/family_mutation_limits.py`
- `dopey_strategy_lab/mutation_constraints.py`
- `dopey_strategy_lab/mutation_scorecard.py`
- `dopey_strategy_lab/failure_mode_miner.py`
- `dopey_strategy_lab/failure_mode_registry.py`
- `dopey_strategy_lab/run_mutation_population_bundle.py`
- `dopey_options/structure_profiles.py`
- `dopey_options/defined_risk_structures.py`
- `dopey_options/structure_builder.py`

## Mutation population proof

- Bundle version: `dopey-mutation-population-bundle-v1`
- Population version: `dopey-mutation-population-v1`
- Family mutation limits version: `dopey-family-mutation-limits-v1`
- Mutation scorecard version: `dopey-mutation-scorecard-v1`
- Mutation constraint version: `dopey-mutation-constraints-v1`
- Mutations generated: `36`
- Valid mutations: `32`
- Rejected unsafe probes: `4`
- Family coverage: `directional_convexity`, `volatility_expansion`,
  `volatility_compression`, `short_duration_defined_risk`
- Best parent: `genome-directional-convexity-spy-fixture-v1`
- Best mutated strategy: `genome-directional-convexity-spy-fixture-v1-mut-delta-bull`
- Parent score: `0.577118`
- Best mutation score: `0.591118`
- Score delta: `0.014`

The population intentionally includes one unsafe probe per family so rejection behavior is proven
inside the same offline batch. Valid mutations preserve `live_allowed=false`,
`defined_risk_only=true`, and `structure_risk=defined`.

## Mutation types covered

- `adjust_delta_preference`
- `adjust_dte_bucket`
- `adjust_liquidity_threshold`
- `adjust_slippage_tolerance`
- `adjust_iv_regime_preference`
- `adjust_pattern_preference`
- `adjust_invalidation_sensitivity`
- `adjust_regime_filter`
- `adjust_spread_structure_proxy`
- `adjust_theta_tolerance`
- `adjust_vega_tolerance`
- `adjust_overfit_penalty`
- `adjust_greek_fit_weighting`
- `adjust_pattern_confidence_weighting`
- `adjust_bad_fill_avoidance_weighting`
- `adjust_holdout_consistency_weighting`

## Promotion decisions

Allowed mutation result categories are limited to `unsafe_rejected`, `degraded`, `overfit`,
`research_only`, `paper_research_candidate`, and `offline_mutation_champion`. Forbidden live
states are not emitted.

The latest registry selects `genome-directional-convexity-spy-fixture-v1-mut-delta-bull` as the
offline mutation champion. Several volatility-expansion candidates remain rejected because the
family still carries high overfit and IV-crush failure pressure in fixture replay.

## Proof artifacts

- Mutation registry: `artifacts/dopey/mutations/mutation_registry.jsonl`
- Bundle ProofLedger: `artifacts/dopey/mutations/dopey_mutation_population_bundle.jsonl`
- Failure-mode registry: `artifacts/dopey/failure_modes/failure_mode_registry.jsonl`
- Tournament ProofLedger: `artifacts/dopey/tournaments/dopey_tournament.jsonl`
- Champion registry: `artifacts/dopey/champion_registry/champion_registry.jsonl`

## Validation

- `python -m pytest tests/test_mutation_population_structure_bundle.py` -> `35 passed`
- `python -m pytest` -> `170 passed`

## Safety state

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- PaperBroker still refuses `live_allowed=true`
- Robinhood, Alpaca, and Tradier stubs still raise `LiveTradingDisabledError`
- No live broker connection, no credentials, no live promotion, no schedule, no commit

## Known gaps

- Scores are deterministic fixture scores, not real market evidence.
- Mutation selection is deterministic and bounded; it is not a large-scale optimizer.
- Failure-mode feedback applies small scorecard penalties and registry hints, not autonomous
  retraining.
- Live-market sources and broker-fill histories remain intentionally deferred.

## Failure Feedback Optimizer Connection

The mutation-population failure registry now serves as the source input for
`dopey-failure-feedback-optimizer-v1`. Future mutation populations can consume feedback profiles
from `artifacts/dopey/failure_feedback/failure_feedback_registry.jsonl` to prioritize
replay-only candidates that target recurring family failures.

The first feedback optimizer run generated `16` valid feedback mutations across all four
families and selected
`genome-directional-convexity-spy-fixture-v1-fb-fakeout-pattern` as the best replay-only
candidate. It compared:

- base champion `genome-directional-convexity-spy-fixture-v1`: `0.577118`
- previous mutation champion `genome-directional-convexity-spy-fixture-v1-mut-delta-bull`:
  `0.591118`
- feedback candidate `genome-directional-convexity-spy-fixture-v1-fb-fakeout-pattern`:
  `0.616118`

The feedback path remains deterministic, fixture-only, paper-only, and live-blocked.
