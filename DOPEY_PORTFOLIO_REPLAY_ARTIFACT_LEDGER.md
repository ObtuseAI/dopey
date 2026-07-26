# DOPEY Portfolio Replay Artifact Ledger

## Summary

- artifact set: `dopey_portfolio_level_rotation_and_exposure_replay_v1`
- replay case count: `96`
- stress result count: `60`
- portfolio state count: `96`
- position count: `52`
- rotation decision count: `96`
- exposure snapshot count: `96`
- allocator feedback count: `96`
- threshold feedback count: `96`
- proof record count: `96`
- max 0DTE exposure share: `0.35`
- 0DTE exposure status: `within_cap`
- paper_only: `true`
- live_blocked: `true`
- real_sizing_allowed: `false`

## Artifacts

| Artifact path | Artifact type | Hash | Record count | Replay cases | Stress cases | Positions | Rotation decisions | Proof layer | Safety state |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `artifacts/dopey/portfolio_replay/portfolio_replay_policy.json` | `portfolio_replay_policy` | `e6d35c63be4a7b9e858d2ba26b2d5787b61bb29b14cadc9180cc79ae6fca22fb` | 1 | 0 | 0 | 0 | 0 | policy | paper-only live-blocked |
| `artifacts/dopey/portfolio_replay/portfolio_replay_opportunities.jsonl` | `portfolio_replay_opportunities` | `497966df1dc2b36dbee2dc9e1e52417fcab879019a27b206a23fa0284948eb30` | 96 | 96 | 0 | 0 | 0 | replay input | paper-only live-blocked |
| `artifacts/dopey/portfolio_replay/portfolio_states.jsonl` | `portfolio_states` | `c06bec48a044c03561ad4a44ada6a90b21bde6bb623f6f9382a912f2d1b2d538` | 96 | 96 | 0 | 0 | 0 | state ledger | paper-only live-blocked |
| `artifacts/dopey/portfolio_replay/portfolio_positions.jsonl` | `portfolio_positions` | `2b9052be205b938d0c6f5eb2d81e85b8aaa62c659db1b0799fcb285f09b11a30` | 52 | 0 | 0 | 52 | 0 | position ledger | paper-only live-blocked |
| `artifacts/dopey/portfolio_replay/portfolio_rotation_decisions.jsonl` | `portfolio_rotation_decisions` | `9df17d9a6c9321430d65d9c1d4ad10f1045af498e30d81b31aa9219db10218b9` | 96 | 0 | 0 | 0 | 96 | rotation ledger | paper-only live-blocked |
| `artifacts/dopey/portfolio_replay/portfolio_exposure_snapshots.jsonl` | `portfolio_exposure_snapshots` | `43730f550da8aa180f33aeef0d9fda94afa0a8f21f2b9e88b836e3b16791978d` | 96 | 0 | 0 | 0 | 0 | exposure ledger | paper-only live-blocked |
| `artifacts/dopey/portfolio_replay/exposure_stress_results.jsonl` | `exposure_stress_results` | `44e1f67c656b7c447df39c47bb372d26d6e210c7bbdb56944d8defd69497895a` | 60 | 0 | 60 | 0 | 0 | stress ledger | paper-only live-blocked |
| `artifacts/dopey/portfolio_replay/portfolio_allocator_feedback.jsonl` | `portfolio_allocator_feedback` | `1089830696db742781edc2b1c68dcd7ac6b19eaf53c21c0a3523a8768177547a` | 96 | 0 | 0 | 0 | 0 | allocator feedback | advisory paper-only live-blocked |
| `artifacts/dopey/portfolio_replay/portfolio_threshold_feedback.jsonl` | `portfolio_threshold_feedback` | `462d3d388f42fd737dd3758abe36155653397fd468ef1725487e11a0757c9438` | 96 | 0 | 0 | 0 | 0 | threshold feedback | advisory paper-only live-blocked |
| `artifacts/dopey/portfolio_replay/portfolio_replay_summary.json` | `portfolio_replay_summary` | `ce8413faa81bcb786727d8aadeb7c136d15371d68a89379c65062173524e1eb7` | 1 | 96 | 60 | 52 | 96 | summary | paper-only live-blocked |
| `artifacts/dopey/portfolio_replay/portfolio_replay_proof.jsonl` | `portfolio_replay_proof` | `7f0bfb403e6fd4af7247110239f870aefaf43419d851cf9143df1bf94e0d883c` | 96 | 96 | 0 | 0 | 0 | proof ledger | paper-only live-blocked |

## Decision Distribution

- `open_position`: `21`
- `close_position_allowed`: `3`
- `close_delayed_same_day_block`: `10`
- `rotate_allowed`: `1`
- `rotate_delayed`: `9`
- `paper_shadow_only`: `8`
- `watchlist_only`: `8`
- `reject_policy`: `7`
- `reject_exposure`: `28`
- `reject_live_path`: `1`

## Case Distribution

- `clean_swing_allocation`: `12`
- `clean_zero_dte_capped_allocation`: `12`
- `delayed_rotation_case`: `10`
- `same_day_close_blocked_case`: `10`
- `paper_shadow_containment_case`: `8`
- `watchlist_only_case`: `8`
- `no_trade_rejection_case`: `8`
- `underlying_family_concentration_case`: `8`
- `regime_family_concentration_case`: `8`
- `high_gamma_theta_throttle_case`: `6`
- `iv_event_macro_throttle_case`: `6`

## Safety State

- same_day_churn_allowed: `false`
- paper_shadow_contained: `true`
- delayed_rotation_advisory_only: `true`
- portfolio_feedback_advisory_only: `true`
- live_blocked: `true`
- no_broker: `true`
- no_real_market_data: `true`
- no_real_sizing: `true`

