# DOPEY Structure Builder Report

## Scope

The structure builder converts strategy-family intent into deterministic defined-risk option
structures for fixture replay. It records risk summaries for tournament and champion proofs.

## Implemented modules

- `dopey_options/structure_profiles.py`
- `dopey_options/defined_risk_structures.py`
- `dopey_options/structure_builder.py`
- `dopey_walk_forward/family_structures.py`
- `dopey_walk_forward/replay_engine.py`
- `dopey_walk_forward/replay_models.py`
- `dopey_tournament/runner.py`
- `dopey_tournament/models.py`
- `dopey_tournament/ledger_tournament.py`

## Model versions

- Structure profile version: `dopey-structure-profiles-v1`
- Defined-risk policy version: `dopey-defined-risk-structures-v1`
- Structure builder version: `dopey-structure-builder-v1`

## Supported structures

- `long_call_vertical`
- `long_put_vertical`
- `long_straddle_proxy`
- `long_strangle_proxy`
- `iron_condor_proxy`
- `credit_spread_pair_proxy`
- `butterfly_proxy`
- `short_dte_debit_spread_proxy`

## Risk fields recorded

- structure type and family
- leg count
- max loss
- max reward
- net debit or credit
- directional bias
- volatility bias
- Greek exposure summary
- liquidity score
- slippage pressure
- safety verdict

## Latest tournament structure summary

- `directional_convexity`: `vertical`, average leg count `2.0`, average max loss `3.8475`,
  safety verdict `defined_risk`
- `volatility_expansion`: `strangle`, average leg count `2.0`, average max loss `7.935833`,
  safety verdict `defined_risk`
- `volatility_compression`: `iron_condor`, average leg count `4.0`, average max loss `2.2725`,
  safety verdict `defined_risk`
- `short_duration_defined_risk`: `butterfly`, average leg count `3.0`, average max loss
  `1.4325`, safety verdict `defined_risk`

The public replay intent remains compatible with existing execution validation because family
structures are still exposed as `vertical`, `strangle`, `iron_condor`, and `butterfly`, while the
new builder attaches a richer `structure_build_result` for proof and scoring.

## Safety behavior

The builder rejects naked or undefined-risk structures before scoring. It does not create live
orders and does not widen broker capability. Live promotion remains blocked by config, order
intent validation, PaperBroker, and broker stubs.

## Tests

The structure tests validate long-call verticals, long-put verticals, vol-expansion proxies,
compression proxies, short-duration proxies, naked-risk rejection, risk-summary max loss and leg
count, and liquidity/slippage/Greek integration.
