# DOPEY Portfolio Stress Ladder Artifact Ledger

## Summary

- artifact set: `dopey_portfolio_replay_v2_stress_ladder_and_crisis_mode_throttles_v1`
- stress case count: `120`
- transition decision count: `120`
- crisis throttle result count: `120`
- crisis recovery result count: `120`
- allocator feedback count: `120`
- threshold feedback count: `120`
- proof record count: `120`
- crisis trigger count: `29`
- lockdown trigger count: `18`
- zero_dte_throttle_count: `8`
- paper_only: `true`
- live_blocked: `true`
- real_sizing_allowed: `false`

## Artifacts

| Artifact path | Artifact type | Hash | Record count | Stress cases | Transitions | Throttles | Recoveries | Proof layer | Safety state |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `artifacts/dopey/portfolio_stress_ladder/stress_ladder_policy.json` | `portfolio_stress_ladder_policy` | `462d5bb7083785ef5b5a21540061dce1ba33fd94c635e78ec998f22ff42556a2` | 1 | 0 | 0 | 0 | 0 | policy | paper-only live-blocked |
| `artifacts/dopey/portfolio_stress_ladder/crisis_mode_throttle_profiles.json` | `crisis_mode_throttle_profiles` | `03220835b3e236a177740c54a7ed0da1ee7f6f01c28c834b5c436fb35837f7e4` | 17 | 0 | 0 | 0 | 0 | throttle profiles | paper-only live-blocked |
| `artifacts/dopey/portfolio_stress_ladder/stress_ladder_replay_cases.json` | `stress_ladder_replay_cases` | `357d59878716075f60551cad5ba3a7925e2f8af1ed29c6a5fd3f990e2fdeaeed` | 120 | 120 | 0 | 0 | 0 | replay input | paper-only live-blocked |
| `artifacts/dopey/portfolio_stress_ladder/stress_level_evaluations.jsonl` | `stress_level_evaluations` | `3d3b1c6ef1b34dd8914ea8f9cbf4ad359502a344491fa63dededaa181db60ad0` | 120 | 120 | 0 | 0 | 0 | stress evaluation | paper-only live-blocked |
| `artifacts/dopey/portfolio_stress_ladder/stress_transition_decisions.jsonl` | `stress_transition_decisions` | `06c44fdda96fba0f6a113b0a6777e02ead987821d78d46c32e11cc284788fde1` | 120 | 0 | 120 | 0 | 0 | transition ledger | paper-only live-blocked |
| `artifacts/dopey/portfolio_stress_ladder/crisis_throttle_results.jsonl` | `crisis_throttle_results` | `2dacedc9ed03fd57269bc95b3b3e11b2161e20ea6d15028af54aefa6d0fe8ad9` | 120 | 0 | 0 | 120 | 0 | throttle ledger | paper-only live-blocked |
| `artifacts/dopey/portfolio_stress_ladder/crisis_recovery_results.jsonl` | `crisis_recovery_results` | `73b4a5c8a8a5ba721e27afe411a893dd3fe8d9da04d65ed48886cfd7bdc09cad` | 120 | 0 | 0 | 0 | 120 | recovery ledger | paper-only live-blocked |
| `artifacts/dopey/portfolio_stress_ladder/crisis_allocator_feedback.jsonl` | `crisis_allocator_feedback` | `2617ee832c0214c34e351166a9b9abb0e9afcd6b9c4a027415ffffdf2c11711a` | 120 | 0 | 0 | 0 | 0 | allocator feedback | advisory paper-only live-blocked |
| `artifacts/dopey/portfolio_stress_ladder/crisis_threshold_feedback.jsonl` | `crisis_threshold_feedback` | `4b4f5824f3a6270cf21888734dd3f1c3f26f60fb26006966f81e5e06d0a372d7` | 120 | 0 | 0 | 0 | 0 | threshold feedback | advisory paper-only live-blocked |
| `artifacts/dopey/portfolio_stress_ladder/stress_ladder_summary.json` | `stress_ladder_summary` | `1d452e9cae92ed0d3be81666dc143628ee0b7336c0872c20245ee240502ddd6d` | 1 | 120 | 120 | 120 | 120 | summary | paper-only live-blocked |
| `artifacts/dopey/portfolio_stress_ladder/stress_ladder_proof.jsonl` | `stress_ladder_proof` | `6e370a922ff5e7d8ed6e2e00a3cacd7d95c3019af570e266b78a5c8fe7385f54` | 120 | 120 | 120 | 120 | 120 | proof ledger | paper-only live-blocked |

## Stress Level Distribution

- `normal`: `16`
- `elevated`: `16`
- `defensive`: `17`
- `severe`: `24`
- `crisis`: `29`
- `lockdown`: `18`

## Throttle Distribution

- `reduce_allocation`: `32`
- `swing_only`: `15`
- `block_zero_dte`: `8`
- `block_family`: `3`
- `block_regime`: `1`
- `block_high_gamma`: `1`
- `block_high_theta`: `1`
- `block_iv_crush`: `12`
- `block_event_macro`: `2`
- `no_trade_only`: `27`
- `lockdown_allocation`: `18`

## Recovery Distribution

- `crisis_to_severe`: `5`
- `severe_to_defensive`: `2`
- `defensive_to_elevated`: `1`

## Safety State

- lockdown_blocks_new_entries: `true`
- same_day_churn_allowed: `false`
- same_day_close_forced_count: `0`
- paper_shadow_contained: `true`
- delayed_rotation_advisory_only: `true`
- no_day_trade_dominant: `true`
- paperbroker_override_allowed: `false`
- portfolio_feedback_advisory_only: `true`
- threshold_feedback_advisory_only: `true`
- live_blocked: `true`
- no_broker: `true`
- no_real_market_data: `true`
- no_real_sizing: `true`
