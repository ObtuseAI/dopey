# DOPEY Broker-Readiness Artifact Ledger

## Safety State

- paper_only: `true`
- live_blocked: `true`
- broker_connection_created: `false`
- credentials_created: `false`
- scheduler_created: `false`
- real_sizing_created: `false`
- robinhood_mcp_integration_created: `false`
- readiness_status: `read_only_boundary_simulated`
- not_broker_ready: `true`
- next_required_gate: `explicit_human_approval_for_future_read_only_capability_detector_bundle`

## Artifacts

| Artifact path | Artifact type | SHA256 | Records | Checks | Simulations | Blocks | Manual gates | Proof layer |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `artifacts/dopey/broker_readiness/broker_preflight_checks.jsonl` | `broker_readiness_preflight_checks` | `3639cef8f87ed05f0afcb6d0451b7eaa484230c0bb5e69ee2fcdab40b8050adb` | 81 | 81 | 0 | 0 | 0 | preflight |
| `artifacts/dopey/broker_readiness/read_only_boundary_simulations.jsonl` | `read_only_boundary_simulations` | `c2160c923b8d397bde9f16dc538b4d5b6105ff435417353f53e41b7dcf78cafb` | 24 | 0 | 24 | 17 | 5 | boundary |
| `artifacts/dopey/broker_readiness/broker_capability_fixtures.json` | `broker_capability_fixtures` | `46cd6bfb42bfa163f43cdd030ecdfe54a7094cd7edca95424a28e0e5a25776b2` | 12 | 0 | 0 | 8 | 12 | fixture |
| `artifacts/dopey/broker_readiness/broker_readiness_run_result.json` | `broker_readiness_run_result` | `34dcb52e9ece2c7a9c4d1a25a9081c2ac4a45b5bffbbe3da20564dc206f515f1` | 1 | 81 | 24 | 17 | 13 | result |
| `artifacts/dopey/broker_readiness/broker_readiness_boundary_blocks.jsonl` | `broker_readiness_boundary_blocks` | `bc5431ba2cdd8ec8c2964863105c50295ef4468ac97902e57afdacdc309e52de` | 22 | 0 | 0 | 22 | 5 | block |
| `artifacts/dopey/broker_readiness/broker_readiness_manual_gates.json` | `broker_readiness_manual_gates` | `91265eb93c4985e2281a5657f86e2313cc9905f4c3d36e2fc923e5476ccd3458` | 13 | 8 | 5 | 0 | 13 | manual_gate |
| `artifacts/dopey/broker_readiness/broker_readiness_summary.json` | `broker_readiness_summary` | `fe17b237238f500970fd6ad66fae4d70dc752128b2fe8e039d84ed55c383724e` | 1 | 81 | 24 | 22 | 13 | summary |
| `artifacts/dopey/broker_readiness/broker_readiness_proof.jsonl` | `broker_readiness_proof` | `e2f43b55600d33e7f72f95dcab59e904282718608bd91d43b211cc667eab736d` | 105 | 81 | 24 | 17 | 13 | proof |

## Fixture Files

- `dopey_data/fixtures/broker_readiness/broker_preflight_checks.json`
- `dopey_data/fixtures/broker_readiness/read_only_boundary_simulations.json`
- `dopey_data/fixtures/broker_readiness/broker_capability_fixtures.json`
- `dopey_data/fixtures/broker_readiness/expected_broker_readiness_results.json`
- `dopey_data/fixtures/broker_readiness/expected_boundary_blocks.json`

## Read-Only Detector Dry-Run Fixture Validator Artifacts

- report: `DOPEY_READ_ONLY_DETECTOR_DRY_RUN_FIXTURE_VALIDATOR_REPORT.md`
- ledger: `DOPEY_READ_ONLY_DETECTOR_DRY_RUN_ARTIFACT_LEDGER.md`
- summary: `artifacts/dopey/broker_readiness/dry_run/read_only_detector_dry_run_summary.json`
- proof: `artifacts/dopey/broker_readiness/dry_run/read_only_detector_dry_run_proof.jsonl`
- contract: `artifacts/dopey/broker_readiness/dry_run/future_detector_contract.md`
- safety_state: `paper_only_live_blocked_fixture_only_detector_not_run`

## Read-Only Detector Dry-Run Fixture Validator Artifacts

- report: `DOPEY_READ_ONLY_DETECTOR_DRY_RUN_FIXTURE_VALIDATOR_REPORT.md`
- ledger: `DOPEY_READ_ONLY_DETECTOR_DRY_RUN_ARTIFACT_LEDGER.md`
- summary: `artifacts/dopey/broker_readiness/dry_run/read_only_detector_dry_run_summary.json`
- proof: `artifacts/dopey/broker_readiness/dry_run/read_only_detector_dry_run_proof.jsonl`
- contract: `artifacts/dopey/broker_readiness/dry_run/future_detector_contract.md`
- safety_state: `paper_only_live_blocked_fixture_only_detector_not_run`
