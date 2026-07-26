# DOPEY 0DTE Threshold Feedback Optimizer Report

## Objective

`DOPEY_0DTE_THRESHOLD_FEEDBACK_OPTIMIZER_V1` turns deterministic 0DTE replay feedback into offline threshold candidate profiles for the 0DTE risk model. It is fixture-only, paper-only, advisory, promotion-gated, and live-blocked.

The optimizer does not mutate the default threshold fixture and does not enable trading.

## Source Replay Artifacts

Inputs are local artifacts only:

- `artifacts/dopey/zero_dte_replay/zero_dte_threshold_feedback.jsonl`
- `artifacts/dopey/zero_dte_replay/zero_dte_replay_outcomes.jsonl`
- `artifacts/dopey/zero_dte_replay/zero_dte_replay_summary.json`
- `artifacts/dopey/zero_dte_replay/zero_dte_expiry_management.jsonl`
- `artifacts/dopey/zero_dte_risk/zero_dte_risk_decisions.jsonl`
- `artifacts/dopey/zero_dte_risk/zero_dte_blocked_candidates.jsonl`
- `artifacts/dopey/zero_dte_risk/zero_dte_approved_candidates.jsonl`
- `artifacts/dopey/zero_dte_risk/zero_dte_risk_thresholds.json`

Source replay summary SHA256:

- `A0AB56AFFC77FBB310A54BA3847B7B6DFBC694C88AD387100BFBA6E175FE5F20`

## Feedback Aggregation

The aggregate loads:

- `24` feedback records
- `24` replay outcomes
- `8` approved baseline risk candidates
- `13` blocked baseline risk candidates
- `1` throttled baseline risk candidate
- `24` expiry-management records

It identifies:

- validated blocks: `4`
- possible overstrict blocks: `1`
- approved failures: `11`
- approved successes: `5`
- throttle validations: `1`
- later-expiry recommendations: `1`

## Candidate Threshold Generation

Generated profiles:

- `stricter_liquidity_profile`
- `stricter_gamma_theta_profile`
- `stricter_iv_overpayment_profile`
- `proof_strengthened_profile`
- `later_expiry_preference_profile`
- `balanced_research_profile`
- `coverage_expansion_profile`
- `rejected_too_loose_profile`

Safety invariants on every candidate:

- `paper_only=true`
- `live_blocked=true`
- `allow_live_threshold_mutation=false`
- `allow_sell_to_open=false`
- `allow_normal_same_day_churn=false`
- explicit thesis remains required
- explicit exit plan remains required

## Hybrid V3 Evidence Input

The optimizer now consumes `DOPEY_CROSS_UNDERLYING_V3_MULTI_DAY_SWING_0DTE_HYBRID_REPLAY_CORPUS_V1` after the cross-underlying v2 corpus. The hybrid layer contributes 192 offline pairwise comparisons between 0DTE candidates and multi-day swing alternatives. It records the zero-DTE-vs-swing preference distribution, post-hybrid stricter gamma/theta survival state, later-expiry preference state, paper-shadow downgrade state, and research-default promotion block.

Hybrid evidence remains advisory-only and does not mutate live or default thresholds.

## Shadow Replay

Each candidate is replayed against the existing 0DTE risk fixture corpus and compared with baseline decisions.

Shadow replay summary:

- candidates replayed: `8`
- total decision changes: `11`
- total new approvals: `8`
- total new blocks: `2`
- total new throttles: `0`
- unsafe approvals: `6`
- overfit warnings: `8`
- safety errors: `6`

The unsafe approvals are confined to the negative-control `rejected_too_loose_profile`, which is rejected.

## Optimizer Decision Policy

Decision gates:

- reject if any safety error occurs
- reject if any unsafe approval occurs
- reject if a candidate approves a live path
- reject if unsupported structures, missing thesis, missing exit plan, poor liquidity, or wide spread are approved
- hold advisory-only when evidence is useful but overfit or coverage warnings remain
- promote to paper-shadow only when no unsafe approvals occur and validated blocks remain preserved
- promote to research-default only when strict replay, feedback, evidence, and overfit gates pass

## Recommended Profile

Recommended threshold profile:

- `stricter_gamma_theta_profile`

Decision:

- `promote_to_paper_shadow_candidate`

This is a paper-shadow candidate only. It is not written into the default live or research threshold fixture.

## Rejected Profiles

Rejected profiles:

- `rejected_too_loose_profile`

Reason codes include:

- `unsafe_new_approval_greeks_instability`
- `unsafe_new_approval_high_slippage`
- `unsafe_new_approval_iv_or_premium_overpayment`
- `unsafe_new_approval_poor_liquidity`
- `unsafe_new_approval_weak_proof`
- `unsafe_new_approval_wide_spread`
- `unsafe_new_approval_detected`
- `validated_block_not_preserved`
- `candidate_loosened_controls`

## Promotion Gates

Current decision counts:

- rejected: `1`
- advisory-only: `2`
- needs more fixture coverage: `2`
- paper-shadow candidates: `3`
- research-default candidates: `0`

No candidate is auto-promoted into live/default execution.

## Overfit Controls

The optimizer separates fixture evidence from production confidence:

- a blocked candidate that works in replay becomes a fixture-coverage gap, not an approval
- broad tightening with replay mismatch becomes advisory-only
- negative controls are retained as rejected proof
- research-default requires zero unsafe approvals and clean replay/feedback gates

## Audit, Report, Export, Review

Integrated surfaces:

- active policy audit recognizes all eight optimizer artifacts
- offline evidence inventory recognizes all eight optimizer artifacts
- reporting bundle includes optimizer summary fields
- export selector includes optimizer reports and artifacts
- export review executive/safety summaries include optimizer state
- validation shard plan includes `tests/test_zero_dte_threshold_optimizer.py`

## Validation

Targeted validation completed:

- `python -m pytest tests/test_zero_dte_threshold_optimizer.py -q`: `67 passed`
- `python -m dopey_options.run_zero_dte_threshold_optimizer`: `ok`
- `python -m dopey_governor.run_active_policy_integration_check`: `ok`, enforcement points `20`
- active policy audit direct check: `pass`, safety errors `0`
- `python -m dopey_reporting.run_tournament_performance_reporting_bundle`: `ok`

Full-suite status remains not yet newly completed for this bundle at report creation time. A timeout must be recorded as `inconclusive_timeout`, not pass.

## Limitations

- Fixture replay is not live profitability evidence.
- Threshold candidates are not predictive-performance claims.
- Paper-shadow recommendation is not execution authority.
- The optimizer cannot loosen no-day-trade, broker, credential, or live-trading boundaries.
- Overstrict blocked cases require more fixture coverage, not automatic approval.

## Safety State

- `mode=RESEARCH`
- `paper_only=true`
- `live_blocked=true`
- `live_trading_enabled=false`
- `funded_broker_connections_enabled=false`
- `allow_unofficial_robinhood_api=false`
- no real market data
- no broker connection
- no credentials
- no scheduler
- no live orders
- no git commit

## Final Validation Update

Additional final validation completed for this bundle:

- `python -m pytest tests/test_zero_dte_threshold_optimizer.py -q`: `67 passed in 2.19s`
- `python -m pytest tests/test_zero_dte_outcome_replay.py tests/test_zero_dte_risk_model.py -q`: `133 passed in 4.27s`
- `python -m pytest tests/test_zero_dte_account_lifecycle.py tests/test_account_ledger_policy.py tests/test_rotation_planner.py tests/test_paperbroker_account_ledger.py -q`: `57 passed in 12.53s`
- `python -m pytest tests/test_active_policy_integration.py tests/test_active_trading_policy.py -q`: `32 passed in 6.87s`
- `python -m dopey_options.run_zero_dte_threshold_optimizer`: `ok`
- `python -m dopey_options.run_zero_dte_outcome_replay`: `ok`
- `python -m dopey_options.run_zero_dte_risk_model`: `ok`
- `python -m dopey_execution.run_account_ledger_rotation_planner`: `ok`
- `python -m dopey_governor.run_active_policy_integration_check`: `ok`, enforcement points `20`
- `python -m dopey_audit.run_offline_evidence_replay_audit`: `pass`, artifacts scanned `88`, safety errors `0`
- `python -m dopey_reporting.run_tournament_performance_reporting_bundle`: `ok`
- `python -m dopey_export.run_artifact_compaction_export_verifier`: `ok`, artifacts selected `120`, credential findings `0`
- `python -m dopey_export_review.run_export_bundle_review_assistant`: `ok`, artifact count `120`, safety errors `0`
- `python -m dopey_validation.full_suite_stabilizer`: `full_suite_status=inconclusive_timeout`, `timeout_recorded_as_pass=false`
- `python -m pytest --collect-only`: `911 tests collected in 0.48s`
- `python -m pytest`: `inconclusive_timeout` after `315.9s`; the run was stopped while still in `tests/test_export_bundle_review_assistant.py`

The full-suite timeout is not a pass.
## Adversarial Corpus Integration

DOPEY_0DTE_EMPIRICAL_FIXTURE_EXPANSION_AND_ADVERSARIAL_REPLAY_CORPUS_V1 adds adversarial corpus context to the threshold optimizer summary. The optimizer now records 99 adversarial fixture cases and 123 combined baseline plus adversarial replay cases.

Post-adversarial result:

- stricter_gamma_theta_profile remains an offline paper-shadow candidate.
- Research-default promotion remains blocked.
- Post-adversarial recommendation: paper_shadow_only_no_research_default_promotion.
- Policy loophole block rate: 1.0.
- Overfit-pressure score: 1.0.
- Live/default threshold mutation remains false.

## Cross-Underlying V2 Optimizer Stress

The threshold optimizer now consumes cross-underlying v2 corpus evidence from `artifacts/dopey/zero_dte_cross_underlying_v2`. The optimizer summary records:

- cross_underlying_v2_fixture_count: `192`
- combined_v1_v2_fixture_count: `315`
- post_v2_threshold_candidate_survival_status: `paper_shadow_survives_no_research_default`
- post_v2_all_paper_shadow_candidate_survival_status: `recorded_advisory_or_paper_shadow_only`
- post_v2_paper_shadow_candidate_downgrade_status: `non_gamma_theta_shadow_candidates_advisory_only_under_cross_underlying_pressure`
- post_v2_negative_control_profile_status: `rejected_negative_control`
- post_v2_research_default_promotion_allowed: `false`

The v2 evidence is advisory and paper-only. It cannot mutate live/default thresholds, enable broker execution, create credentials, create a scheduler, or promote research-default settings without strict combined-corpus gates.
## Proof-Weighted Allocation Feedback

The threshold optimizer now reads the proof-weighted paper allocation plan and exposure summary when those artifacts are present. This feedback is advisory and fixture-only.

Recorded allocation feedback:

- allocation feedback loaded: `true`
- 0DTE paper premium risk units: `17.9`
- swing paper premium risk units: `32.4`
- 0DTE exposure share: `0.342256`
- 0DTE cap status: `within_cap`
- threshold action: `keep_0dte_caps_strict_paper_shadow_only`
- live threshold mutation allowed: `false`

Allocation feedback does not mutate live/default thresholds. It only confirms that strict 0DTE caps should remain in force until more fixture evidence supports expansion.

## Portfolio Exposure Feedback

The threshold optimizer now reads portfolio exposure feedback from `artifacts/dopey/portfolio_replay/portfolio_threshold_feedback.jsonl` when the portfolio replay bundle is present.

Recorded portfolio feedback:

- feedback records loaded: `96`
- live threshold mutation allowed: `false`
- same-day churn pressure is advisory and remains blocked
- high-gamma/high-theta pressure keeps affected profiles paper-shadow or advisory only
- 0DTE concentration pressure preserves strict 0DTE threshold profiles
- IV/event/macro pressure recommends advisory later-expiry strengthening

Portfolio feedback does not mutate live/default thresholds and does not promote research-default profiles into execution. It is static, fixture-only, paper-only feedback.

## Stress Ladder Threshold Feedback

The 0DTE threshold optimizer now reads advisory crisis feedback from `artifacts/dopey/portfolio_stress_ladder/crisis_threshold_feedback.jsonl`. The feedback can downgrade profiles that increase crisis transitions, preserve gamma/theta paper-shadow behavior when it reduces crisis pressure, strengthen later-expiry advisory preference, reject same-day churn pressure, and reject safety-boundary pressure. It cannot mutate live/default thresholds.

## Threshold Optimizer Incident Feedback Handling

The 0DTE threshold optimizer now reads advisory incident feedback from `artifacts/dopey/incident_response/incident_threshold_feedback.jsonl`. Incident feedback can block unsafe threshold profiles, request more fixture coverage, or mark terminal-block pressure. It cannot promote live/default thresholds or weaken 0DTE lifecycle gates.
