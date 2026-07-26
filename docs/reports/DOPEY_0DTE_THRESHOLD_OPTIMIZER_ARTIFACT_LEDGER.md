# DOPEY 0DTE Threshold Optimizer Artifact Ledger

## Summary

- artifact_bundle: `DOPEY_0DTE_THRESHOLD_FEEDBACK_OPTIMIZER_V1`
- optimizer_run_id: `zero-dte-threshold-optimizer-run-1e1f06b72625`
- candidate_count: `8`
- rejected_count: `1`
- paper_shadow_candidate_count: `3`
- research_default_candidate_count: `0`
- recommended_threshold_profile: `stricter_gamma_theta_profile`
- proof_layer: `zero_dte_threshold_optimizer_proof`
- paper_only: `true`
- live_blocked: `true`
- no_real_market_data: `true`
- no_broker: `true`

## Artifacts

| Artifact type | Path | SHA256 | Records |
|---|---|---:|---:|
| `zero_dte_threshold_feedback_aggregate` | `artifacts/dopey/zero_dte_threshold_optimizer/threshold_feedback_aggregate.json` | `9E4A9FA7D0FC4D1A293B11AAB4E6274B85B648BEC8959598D7C837AB92E24F09` | `1` |
| `zero_dte_threshold_candidates` | `artifacts/dopey/zero_dte_threshold_optimizer/threshold_candidates.jsonl` | `E441A41357AE2FEAE3FAD96519D11F7167A9266075F9A057706711D062302E87` | `8` |
| `zero_dte_shadow_replay_results` | `artifacts/dopey/zero_dte_threshold_optimizer/shadow_replay_results.jsonl` | `AB2856AB6B8645D09F9BDBD120965166E9A09C951592715AE310B857C204D78D` | `8` |
| `zero_dte_threshold_optimization_decisions` | `artifacts/dopey/zero_dte_threshold_optimizer/optimization_decisions.jsonl` | `A48F8F066020F2E4A44579D56393F022C879C9874539F60A64803283DF1D15EF` | `8` |
| `zero_dte_recommended_threshold_profile` | `artifacts/dopey/zero_dte_threshold_optimizer/recommended_threshold_profile.json` | `E9A37D69E9655684C7B7B1AE8EFCAC823C3722B4ABF15A2B00B5141562F128E6` | `1` |
| `zero_dte_rejected_threshold_profiles` | `artifacts/dopey/zero_dte_threshold_optimizer/rejected_threshold_profiles.jsonl` | `EBBD594C2EFDF14386D9AB61ECFF56D38E73C397ACE182AEA0CCEC6FF2686B03` | `1` |
| `zero_dte_threshold_optimizer_summary` | `artifacts/dopey/zero_dte_threshold_optimizer/threshold_optimizer_summary.json` | `62357EC9DCA00D277214E467CFAA391A44095DF960C84E88DCFB35E3F1226E0C` | `1` |
| `zero_dte_threshold_optimizer_proof` | `artifacts/dopey/zero_dte_threshold_optimizer/threshold_optimizer_proof.jsonl` | `3D80EDAC23253BA1B0BA359702C438DC5AB353A35084749CB4006DC58B222095` | `8` |

## Decision Distribution

- `reject_candidate`: `1`
- `hold_advisory_only`: `2`
- `needs_more_fixture_coverage`: `2`
- `promote_to_paper_shadow_candidate`: `3`
- `promote_to_research_default_candidate`: `0`

## Proof State

Every proof record carries:

- optimizer run id
- source replay summary hash
- source threshold version
- candidate threshold id
- candidate hash
- shadow replay hash
- decision
- reason codes
- safety status
- overfit status
- promotion gate
- paper-only flag
- live-blocked flag
- no-real-market-data flag
- no-broker flag

## Safety State

- threshold optimizer artifacts are deterministic local files
- threshold feedback is advisory only
- default thresholds are not mutated
- unsafe new approvals reject threshold candidates
- no threshold optimizer artifact grants live trading approval
