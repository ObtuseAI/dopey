# DOPEY Proof-Weighted Allocator Artifact Ledger

## Summary

- artifact set: `proof_weighted_capital_allocator_for_long_premium_options_v1`
- opportunity count: `83`
- allocation decision count: `83`
- allocated count: `23`
- throttled count: `8`
- shadow-only count: `8`
- delayed rotation count: `8`
- watchlist count: `6`
- rejection count: `30`
- total paper attention weight: `21.31`
- total paper premium risk units: `52.3`
- paper_only: `true`
- live_blocked: `true`
- real_sizing_allowed: `false`

## Artifacts

| Artifact path | Artifact type | Hash | Record count | Allocation count | Rejection count | Watchlist count | Proof layer | Safety state |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| `artifacts/dopey/allocation/proof_weighted_opportunities.jsonl` | `proof_weighted_opportunities` | `d4229a40a16c5213e4ce96a91d3d700d573311ec42064d81559366137d69739d` | 83 | 0 | 0 | 0 | opportunity input | paper-only live-blocked |
| `artifacts/dopey/allocation/paper_allocation_policy.json` | `paper_allocation_policy` | `1e758b713caa2f0991cad50dd4bdce9442820ddc9781a213ebc28869176f18cf` | 1 | 0 | 0 | 0 | policy | paper-only live-blocked |
| `artifacts/dopey/allocation/paper_risk_budget.json` | `paper_risk_budget` | `707fe2c777ca05c32530a83b4bb5dc761b291133679b19afef93c76e69549e65` | 1 | 0 | 0 | 0 | risk budget | paper-only live-blocked |
| `artifacts/dopey/allocation/paper_allocation_decisions.jsonl` | `paper_allocation_decisions` | `a9f9566457fd4bd95891f0e6bc276acec058f9c41761ba6037d49612d22107f1` | 83 | 39 | 30 | 14 | decision ledger | paper-only live-blocked |
| `artifacts/dopey/allocation/paper_allocation_plan.json` | `paper_allocation_plan` | `fe2810589d99ee7c3e5c2e92ae94cd66e5b94a30bc8230779bd338b594e1f46c` | 1 | 23 | 30 | 6 | plan summary | paper-only live-blocked |
| `artifacts/dopey/allocation/allocation_rejections.jsonl` | `allocation_rejections` | `9fbd3741b0727cf221f3c7a8a99d4313964f6715871fc424edb548a5714cc871` | 30 | 0 | 30 | 0 | rejection ledger | paper-only live-blocked |
| `artifacts/dopey/allocation/allocation_watchlist.jsonl` | `allocation_watchlist` | `d78e7796124cc648923dbe1e09cf78eefe473ddef8d8e9a0e4ad9b019a0986ae` | 22 | 0 | 0 | 22 | watchlist ledger | paper-only live-blocked |
| `artifacts/dopey/allocation/allocation_exposure_summary.json` | `allocation_exposure_summary` | `ce7ad39f94fe1df4dae2cddf49a0629ba4a2d6535b3a66cf647aff9d663aec97` | 1 | 0 | 0 | 0 | exposure controls | paper-only live-blocked |
| `artifacts/dopey/allocation/allocation_constraint_summary.json` | `allocation_constraint_summary` | `7c4cee9d0867b10e796aef3d46bde58a858e90d1ca2c957adb4ea0f1164744ab` | 1 | 0 | 0 | 0 | constraint controls | paper-only live-blocked |
| `artifacts/dopey/allocation/allocation_proof.jsonl` | `allocation_proof` | `6ca9981e4df9f25693bf215ff48703d9b8adb0da8adb50b640c411c5061fc49f` | 83 | 39 | 30 | 14 | proof ledger | paper-only live-blocked |

## Decision Distribution

- `allocate_paper`: `23`
- `allocate_paper_throttled`: `8`
- `allocate_paper_shadow_only`: `8`
- `reserve_for_delayed_rotation`: `8`
- `needs_more_fixture_coverage`: `6`
- `reject_liquidity`: `8`
- `reject_live_path`: `1`
- `reject_no_day_trade_constraint`: `6`
- `reject_no_trade`: `8`
- `reject_policy_violation`: `7`

## Allocation By Strategy Type

- `swing_long_call`: `18.55`
- `swing_long_put`: `13.85`
- `zero_dte_long_call`: `10.65`
- `zero_dte_long_put`: `7.25`
- `delayed_rotation_long_call`: `0.75`
- `delayed_rotation_long_put`: `1.25`
- `no_trade`: `0.0`

## Exposure State

- zero_dte_paper_premium_risk_units: `17.9`
- swing_paper_premium_risk_units: `32.4`
- zero_dte_exposure_share: `0.342256`
- zero_dte_share_status: `within_cap`
- delayed_rotation_reserves_advisory_only: `true`
- same_day_churn_allocation_allowed: `false`
- paper_broker_override_allowed: `false`
