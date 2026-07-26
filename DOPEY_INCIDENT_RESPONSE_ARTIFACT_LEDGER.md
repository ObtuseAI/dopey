# DOPEY Incident Response Artifact Ledger

All artifacts are offline, deterministic, fixture-only, paper-only, and live-blocked.

| Artifact | Type | Records | SHA-256 |
| --- | --- | ---: | --- |
| `artifacts/dopey/incident_response/incident_taxonomy.json` | incident_taxonomy | 56 | `8bde3bf7671f257eaf4e8ac7b4f13e4b5771b2beb988c2f48724101579e809b1` |
| `artifacts/dopey/incident_response/incident_rehearsal_cases.json` | incident_rehearsal_cases | 144 | `77d1d5563353c901a4eeff97f7e1651c52245fc69c06ae7d00b2fbfac98b1af4` |
| `artifacts/dopey/incident_response/incident_signals.jsonl` | incident_signals | 144 | `62604eb5dd1e3817588828fc7f875d477b2acc8e3756e0669ce101535f07c994` |
| `artifacts/dopey/incident_response/kill_switch_states.jsonl` | kill_switch_states | 144 | `b7248b5b241ae2d6d751bb603f4cc83de473aff402b239d10a3d612b17267406` |
| `artifacts/dopey/incident_response/incident_response_decisions.jsonl` | incident_response_decisions | 144 | `670f1a2afe2b92e3bd3da111bb2fb037557a059eb2e55b869dc1c48b130dfd2d` |
| `artifacts/dopey/incident_response/incident_recovery_plans.jsonl` | incident_recovery_plans | 144 | `7953caf32799a0f89f376146a1ccaccd15e58d2e24ee9bb5ddda528176c073c0` |
| `artifacts/dopey/incident_response/incident_allocator_feedback.jsonl` | incident_allocator_feedback | 144 | `7da4a4ce9fe7ff392e9f78090a247a3082bf8bfe9d2797d51782f498716ef69c` |
| `artifacts/dopey/incident_response/incident_threshold_feedback.jsonl` | incident_threshold_feedback | 144 | `a0dfa6fb6e084d028e75d8484a58f1c78c6e90b787bf7dbff214b7263a015ce2` |
| `artifacts/dopey/incident_response/incident_stress_ladder_feedback.jsonl` | incident_stress_ladder_feedback | 144 | `4e776e0d8f908794cdb0dcc48fbbef3f2bc5c4baa8d7c23121be695df68d2534` |
| `artifacts/dopey/incident_response/incident_rehearsal_summary.json` | incident_rehearsal_summary | 1 | `4f11583b4677e226238fcd19c5e163f0e18b225a53fa11639cde9fd1b17a03c6` |
| `artifacts/dopey/incident_response/incident_response_proof.jsonl` | incident_response_proof | 144 | `8b9bbe5263c6dbca7cc753828cc5821f0e8a205c70557177b38975c402eafc42` |

## Counts

- Incident cases: 144
- Kill-switch states: 144
- Response decisions: 144
- Recovery plans: 144
- Proof records: 144
- Terminal blocks: 32
- Manual review states: 19
- Audit-only states: 2
- Paper lockdown states: 48

## Safety State

- `paper_only`: true
- `live_blocked`: true
- `no_real_market_data`: true
- `no_broker`: true
- `no_real_sizing`: true
- `no_scheduler`: true
- `no_credentials`: true
- `same_day_churn_allowed`: false
- `same_day_close_forced_count`: 0
- `paperbroker_override_allowed`: false
- `terminal_block_auto_recovery_allowed`: false
- `full_suite_timeout_recorded_as_pass`: false
