# DOPEY Failure-Mode Feedback Optimizer Report

## Purpose

`DOPEY_FAILURE_MODE_FEEDBACK_OPTIMIZER_BUNDLE_V1` converts mined failure evidence into
deterministic, offline, fixture-only mutation guidance and constraint-tuning recommendations.
It is replay-only and paper-only. It does not fetch market data, connect to brokers, request
credentials, schedule runs, or promote any strategy to a live state.

## Failure-Mode Aggregation

- Optimizer version: `dopey-failure-feedback-optimizer-v1`
- Feedback model version: `dopey-failure-feedback-model-v1`
- Source registry: `artifacts/dopey/failure_modes/failure_mode_registry.jsonl`
- Feedback registry: `artifacts/dopey/failure_feedback/failure_feedback_registry.jsonl`
- Feedback ProofLedger: `artifacts/dopey/failure_feedback/feedback_optimizer.jsonl`
- Final feedback run id: `failure-feedback-dopey-feedback-v1`
- Failure aggregate slices loaded: `31`

The aggregator profiles failure modes by strategy family, structure type, regime tag, pattern
type, Greek/IV context, liquidity verdict, slippage verdict, overfit level, mutation type,
severity, and recurrence count.

## Family Failure Profiles

| Family | Failure modes | Recurrence | Top targeted failures | Worst regimes | Overfit |
|---|---:|---:|---|---|---|
| `directional_convexity` | 5 | 8 | `mutation_drift`, `unsafe_structure_rejected`, `high_spread_bad_fill_failure`, `fakeout_against_directional`, `low_liquidity_decay_failure` | `family_limit_validator`, `mutation_population`, `gap_reversal`, `high_spread_bad_fill`, `low_liquidity_decay` | `unknown` |
| `short_duration_defined_risk` | 8 | 35 | `pattern_contradiction`, `high_spread_bad_fill_failure`, `slippage_over_sensitivity`, `mutation_drift`, `unsafe_structure_rejected` | `high_spread_bad_fill`, `pattern_fixture_corpus`, `family_limit_validator`, `mutation_population`, `low_liquidity_decay` | `high` |
| `volatility_compression` | 7 | 42 | `high_spread_bad_fill_failure`, `poor_greek_fit`, `low_liquidity_decay_failure`, `slippage_over_sensitivity`, `mutation_drift` | `high_spread_bad_fill`, `macro_shock_risk_off`, `low_liquidity_decay`, `family_limit_validator`, `mutation_population` | `unknown` |
| `volatility_expansion` | 8 | 24 | `overfit_train_only`, `IV_crush_against_vol_expansion`, `unsafe_structure_rejected`, `holdout_collapse`, `mutation_drift` | `post_event_iv_crush`, `train_validation_holdout`, `family_limit_validator`, `high_spread_bad_fill`, `holdout` | `high` |

## Constraint Recommendations

- Recommendations generated: `65`
- Accepted via replay-only candidate decisions: `3`
- Rejected candidate decisions: `13`
- Advisory-only recommendations: `41`

Recommendation categories include tighter max-spread and liquidity thresholds, stronger
slippage penalties, IV-crush guards, macro-shock compression guards, directional fakeout
confirmation, theta-decay guards, holdout/overfit penalties, and explicit unsafe-structure ban
patterns. All recommendations are advisory or replay-only. None alter live settings or broker
configuration.

## Feedback-Guided Mutation Batch

- Policy version: `dopey-feedback-mutation-policy-v1`
- Feedback mutations generated: `16`
- Valid feedback mutations: `16`
- Families covered: `directional_convexity`, `volatility_expansion`,
  `volatility_compression`, `short_duration_defined_risk`
- Validator: `FamilyMutationLimitValidator`

Every feedback mutation preserves `live_allowed=false`, `defined_risk_only=true`, and
`structure_risk=defined`.

## Best Feedback Candidate

- Base champion: `genome-directional-convexity-spy-fixture-v1`
- Previous mutation champion: `genome-directional-convexity-spy-fixture-v1-mut-delta-bull`
- Best feedback candidate: `genome-directional-convexity-spy-fixture-v1-fb-fakeout-pattern`
- Base score: `0.577118`
- Previous mutation score: `0.591118`
- Feedback score: `0.616118`
- Delta vs previous mutation: `0.025`
- Delta vs base: `0.039`
- Overfit delta: `0`
- Failure-mode reduction estimate: `-0.04`
- Accepted status: `accepted_replay_only`

The accepted candidate is replay-only and research-only. It is not a live candidate.

## Safety State

- `mode=RESEARCH`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- PaperBroker still rejects `live_allowed=true`
- Robinhood/Alpaca/Tradier stubs still raise `LiveTradingDisabledError`
- No broker connection, credentials, network market data, live trades, live promotion,
  autonomous schedule, heavy dependency, or commit

## Limitations

- Scores are deterministic fixture replay scores, not live performance evidence.
- Failure-mode reduction is an offline estimate based on targeted failure coverage, not a live
  claim.
- Recommendations do not autonomously retrain on real data.
- The optimizer does not modify safety boundaries, broker settings, or live mode configs.

## Validation

- `python -m pytest tests/test_failure_feedback_optimizer.py -q` -> `31 passed`
- `python -m pytest` -> `201 passed`
- Import smoke -> `FAILURE_FEEDBACK_IMPORT_OK`
- Tournament smoke -> `tournament_status: ok`
- Mutation population smoke -> `bundle_status: ok`
- Feedback optimizer smoke -> `optimizer_status: ok`
- Blunder integrity -> `BLUNDER_INTEGRITY_OK checked=78`

## Next Recommended Build Target

Deterministic IV surface/skew fixture expansion.

## IV Surface Feedback Addendum

The feedback optimizer now receives IV surface failure modes through the standard failure-mode
registry after `python -m dopey_options.run_iv_surface_skew_bundle`.

New IV surface failure modes:

- `premium_overpayment_trap_failure`
- `iv_crush_after_vol_expansion_failure`
- `front_event_bump_against_compression`
- `backwardation_against_compression`
- `skew_trap_against_directional`
- `surface_instability_fakeout_failure`
- `short_duration_front_iv_instability`
- `term_structure_mismatch`
- `wing_elevation_breakout_risk`

New recommendation keys include premium-overpayment penalties, post-event crush avoidance,
front-event-bump guards, compression macro/term guards, directional skew alignment, surface
stability guards, short-duration front-IV guards, term-risk penalties, and wing-elevation
breakout guards.

Latest feedback optimizer smoke after the IV registry refresh:

- `optimizer_status: ok`
- Failure modes loaded: `57`
- Recommendations generated: `83`
- Feedback mutations generated: `16`
- Feedback mutations valid: `16`
- Best feedback mutation: `genome-directional-convexity-spy-fixture-v1-fb-fakeout-pattern`
- Score delta vs previous mutation: `0.025`
- Live blocked: `true`

## Macro-Event Fixture Expansion Addendum

The feedback optimizer now receives macro-event failure modes through the standard failure-mode
registry after `python -m dopey_analysis.run_macro_event_bundle`.

New macro-event failure modes:

- `macro_fakeout_against_directional`
- `event_gap_against_short_duration`
- `rate_shock_against_compression`
- `vix_spike_against_compression`
- `post_event_crush_against_vol_expansion`
- `breadth_contradiction_against_directional`
- `liquidity_contraction_bad_fill_failure`
- `overnight_gap_slippage_failure`
- `sector_rotation_mismatch`
- `macro_event_overfit`

New macro-aware recommendation keys include:

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

Latest feedback optimizer smoke after the macro-event registry refresh:

- `optimizer_status: ok`
- Failure modes loaded: `37`
- Recommendations generated: `77`
- Recommendations accepted: `4`
- Recommendations rejected: `12`
- Feedback mutations generated: `16`
- Feedback mutations valid: `16`
- Best feedback mutation: `genome-directional-convexity-spy-fixture-v1-fb-fakeout-pattern`
- Live blocked: `true`

All recommendations remain replay-only and advisory. No live promotion state is introduced.

All recommendations remain replay-only and advisory. No live promotion state is introduced.

---

## Influence on allocation and redeployment

The failure-feedback evidence feeds directly into the offline ensemble allocator and the
capital redeployment engine:

- **Allocation**: family failure pressure is computed from the latest failure-mode registry
  via `aggregate_failure_modes` + `build_family_failure_profiles`. The pressure sum is
  soft-saturated (`pressure / (pressure + 30)`) into a 0..1 family failure-pressure score.
  This score drives the `failure_penalty` component in the allocation breakdown and the
  direct `starve_weak_signal` decision when a family crosses the 0.40 pressure threshold.
  Feedback candidates that improved the previous mutation champion without overfit
  regression are added as allocation candidates with a positive `mutation_delta`.

- **Redeployment**: the capital redeployment engine consumes the allocation decisions plus
  the same family failure-pressure map. Families with recurring failure modes receive a
  `starve` redeployment action with the saturated pressure recorded as failure-mode
  evidence. Families that improved via feedback but remain below the proof threshold receive
  a `research_only` / `hold` action rather than a live allocation.

All feedback influence remains paper-only and offline; no feedback recommendation can
produce a live allocation or promotion.

## Update: new fundamental failure modes and feedback

The feedback optimizer now consumes ten additional deterministic
sector/peer/fundamental failure modes:

* peer_contradiction_against_directional — peer-confirmation guard
* aluation_trap_against_directional — valuation-trap penalty
* low_dispersion_against_vol_expansion — peer-dispersion requirement for vol expansion
* post_event_clarity_against_vol_expansion — low-dispersion requirement for compression
* high_dispersion_against_compression — low-dispersion requirement for compression
* evision_shock_against_compression — revision-shock guard for compression
* crowded_fakeout_against_short_duration — crowding/fakeout penalty for short duration
* small_cap_liquidity_decay_against_short_duration — sector-liquidity guard
* sector_rotation_late_day_bad_fill — sector-rotation late-day guard
* undamental_event_overfit — fundamental holdout weighting

These are advisory or replay-only and do not retrain on real data. The optimizer
still never promotes a strategy to a live state.
