# DOPEY 0DTE Replay Artifact Ledger

## Summary

- artifact_bundle: `DOPEY_0DTE_EXPIRY_OUTCOME_REPLAY_SIMULATOR_V1`
- fixture_path_count: `24`
- replay_count: `24`
- proof_layer: `zero_dte_replay_proof`
- paper_only: `true`
- live_blocked: `true`
- no_real_market_data: `true`
- no_broker: `true`

## Artifacts

| Artifact type | Path | SHA256 | Records |
|---|---|---:|---:|
| `zero_dte_replay_inputs` | `artifacts/dopey/zero_dte_replay/zero_dte_replay_inputs.jsonl` | `2A05C86A04206F5D6AAC23E042DACB518E0BF1873D88105F6A5062072103D02A` | `24` |
| `zero_dte_intraday_states` | `artifacts/dopey/zero_dte_replay/zero_dte_intraday_states.jsonl` | `D00A8A578F8838ECA5C8C4E4B8B99292511B0010BEBD1DAF8521147BA03765FE` | `72` |
| `zero_dte_replay_decision_points` | `artifacts/dopey/zero_dte_replay/zero_dte_replay_decision_points.jsonl` | `8C450330DC5B9F3C117D62648ED6D63FE3D2800E5D3EEF1267CEBB78E222D9B1` | `72` |
| `zero_dte_replay_outcomes` | `artifacts/dopey/zero_dte_replay/zero_dte_replay_outcomes.jsonl` | `A02E6124B380E18229939360DF675ACE93AD9F350F8962421AE398B64C8E44CC` | `24` |
| `zero_dte_expiry_management` | `artifacts/dopey/zero_dte_replay/zero_dte_expiry_management.jsonl` | `46CCCF7BB4CB2A6B9928F19AA1BE6572BCCA168814DEF86074E05F5402B34DB2` | `24` |
| `zero_dte_threshold_feedback` | `artifacts/dopey/zero_dte_replay/zero_dte_threshold_feedback.jsonl` | `BBB2939CCB0B01D7DD0CA00F3C0EDB20B214EDD8D7802BC87CE3CB0E2D819C49` | `24` |
| `zero_dte_replay_summary` | `artifacts/dopey/zero_dte_replay/zero_dte_replay_summary.json` | `A0AB56AFFC77FBB310A54BA3847B7B6DFBC694C88AD387100BFBA6E175FE5F20` | `1` |
| `zero_dte_replay_proof` | `artifacts/dopey/zero_dte_replay/zero_dte_replay_proof.jsonl` | `AA7F60C4965228651EFF35C64E998EDF7ADB18E994A6F21406F49676AF478F84` | `24` |

## Outcome Distribution

- `approved_survived_fixture`: `2`
- `approved_decayed`: `4`
- `approved_spiked_then_failed`: `2`
- `approved_special_close_helped`: `1`
- `approved_expiry_managed_success`: `2`
- `approved_expiry_managed_failure`: `2`
- `approved_should_have_been_throttled_more`: `3`
- `throttled_correctly`: `1`
- `blocked_correctly`: `4`
- `blocked_maybe_too_strict`: `1`
- `prefer_later_expiry_confirmed`: `1`
- `rejected_policy_violation`: `1`

## Safety State

- replay artifacts are deterministic local files;
- threshold feedback is advisory only;
- replay proof records include paper-only, live-blocked, no-real-market-data, and no-broker flags;
- no replay artifact grants live trading approval.
