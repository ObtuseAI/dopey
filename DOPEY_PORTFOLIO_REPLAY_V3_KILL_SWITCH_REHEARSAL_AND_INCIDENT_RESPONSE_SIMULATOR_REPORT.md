# DOPEY Portfolio Replay V3 Kill-Switch Rehearsal And Incident Response Simulator Report

## Objective

`DOPEY_PORTFOLIO_REPLAY_V3_KILL_SWITCH_REHEARSAL_AND_INCIDENT_RESPONSE_SIMULATOR_V1` adds an offline, deterministic, fixture-only incident response simulator before any broker-readiness work. It rehearses how DOPEY detects, classifies, contains, throttles, locks down, documents, and gradually recovers from unsafe or contradictory states.

This bundle does not enable live trading, broker execution, Robinhood integration, credentials, market data, scheduler behavior, real account sizing, buying-power logic, account balances, or live orders.

## Incident Taxonomy

The taxonomy covers policy violations, no-day-trade violations, 0DTE lifecycle violations, portfolio exposure violations, crisis-mode violations, PaperBroker override attempts, live path injection, broker path injection, credential exposure, scheduler emergence, real market data references, real sizing references, artifact integrity drift, audit staleness, proof contradiction, export safety violations, validation failure, and unknown state controls.

The taxonomy artifact contains 56 incident definitions. Critical live/broker/credential/scheduler/real-sizing incidents map to `terminal_block`; no-day-trade pressure maps to at least `paper_lockdown`; artifact drift maps to `manual_review_required` or `audit_only`; full-suite timeout misclassified as pass maps to `terminal_block`.

## Kill-Switch States

Allowed states are `inactive`, `monitor`, `paper_throttle`, `paper_lockdown`, `audit_only`, `manual_review_required`, and `terminal_block`.

The rehearsal produced 144 kill-switch states:

- `terminal_block`: 32
- `paper_lockdown`: 48
- `paper_throttle`: 27
- `manual_review_required`: 19
- `monitor`: 15
- `audit_only`: 2
- `inactive`: 1

No kill-switch state allows broker execution, live orders, PaperBroker override, threshold live mutation, or forced same-day close.

## Incident Response Policy

The response policy creates deterministic `IncidentSignal`, `KillSwitchState`, `IncidentResponseDecision`, and `IncidentRecoveryPlan` records. All records are paper-only and live-blocked. Response decisions include monitoring, paper allocation throttle, new-entry block, 0DTE block, paper lockdown, audit-only mode, manual review, terminal block, and rejected fixture.

Response decision distribution:

- `terminal_block`: 32
- `paper_lockdown`: 33
- `throttle_paper_allocation`: 27
- `manual_review_required`: 19
- `block_zero_dte`: 14
- `continue_monitoring`: 16
- `audit_only_mode`: 2
- `block_new_entries`: 1

## Recovery Rehearsal

Recovery is gradual and proof-gated. `terminal_block` cannot auto-recover. Boundary incidents involving credentials, live path injection, broker path injection, scheduler emergence, market-data references, real sizing references, or PaperBroker override require manual review. Evidence incidents require proof refresh and audit rerun. No recovery plan weakens live blocking or paper-only status.

Recovery target distribution:

- `paper_throttle`: 48
- `manual_review_required`: 32
- `monitor`: 29
- `audit_only`: 19
- `inactive`: 16

## Fixtures And Engine

The bundle writes 144 incident rehearsal cases across the required groups:

- `policy_violation_incident`: 16
- `no_day_trade_incident`: 16
- `zero_dte_lifecycle_incident`: 16
- `portfolio_exposure_incident`: 16
- `crisis_mode_incident`: 16
- `broker_live_boundary_incident`: 16
- `evidence_audit_export_incident`: 16
- `validation_incident`: 8
- `recovery_incident`: 8
- `negative_control_incident`: 8
- `multi_incident_cascade`: 8

The engine loads taxonomy and cases, evaluates incidents, selects kill-switch state, writes response decisions, writes recovery plans, produces allocator/threshold/stress-ladder feedback, writes proof records, and validates expectations without randomness, network access, broker access, or real market data.

## Feedback Integration

Allocator incident feedback is advisory and offline:

- `keep_live_default_behavior_unchanged`: 144
- `force_no_trade`: 65
- `throttle_paper_allocation`: 61
- `incident_terminal_block`: 32

Threshold incident feedback is advisory and offline:

- `no_live_threshold_mutation`: 144
- `incident_terminal_block`: 32
- `require_more_fixture_coverage`: 21
- `block_threshold_profile`: 17

Stress ladder incident feedback is advisory and offline:

- `incident_rehearsal_observed`: 144
- `force_no_trade`: 80
- `require_stress_ladder_rerun`: 32
- `block_zero_dte`: 14

No feedback mutates live/default behavior.

## Safety Proof

The incident response proof ledger records:

- `same_day_close_forced_count`: 0
- `same_day_churn_allowed`: false
- `paperbroker_override_allowed`: false
- `terminal_block_auto_recovery_allowed`: false
- `full_suite_timeout_recorded_as_pass`: false
- `paper_only`: true
- `live_blocked`: true
- `no_real_market_data`: true
- `no_broker`: true
- `no_real_sizing`: true
- `no_scheduler`: true
- `no_credentials`: true

## Audit, Reporting, Export, Review

Offline audit recognizes all 11 incident artifacts and adds safety checks for paper-only, live-blocked, no real dollars, no buying power, no account balance, no broker path, no credentials, no scheduler, no live order, no same-day churn, no forced same-day close, no PaperBroker override, no terminal-block auto-recovery, and full-suite timeout truth.

Reporting surfaces incident case count, family distribution, severity distribution, kill-switch distribution, response distribution, terminal block count, manual review count, audit-only count, recovery plans, and safety state.

Export and export review include the incident response report, ledger, artifacts, and executive-summary section.

## Validation

Targeted incident shard:

- `python -m pytest tests/test_incident_response.py -q`: 185 passed

Dependent targeted shards passed sequentially:

- `tests/test_portfolio_stress_ladder.py`: 113 passed
- `tests/test_portfolio_replay.py`: 110 passed
- `tests/test_proof_weighted_allocator.py`: 100 passed
- `tests/test_hybrid_swing_0dte_v3.py`: 107 passed
- `tests/test_zero_dte_cross_underlying_v2.py`: 91 passed
- `tests/test_zero_dte_adversarial_corpus.py`: 86 passed
- `tests/test_zero_dte_threshold_optimizer.py`: 67 passed
- `tests/test_zero_dte_outcome_replay.py tests/test_zero_dte_risk_model.py`: 133 passed
- `tests/test_zero_dte_account_lifecycle.py tests/test_account_ledger_policy.py tests/test_rotation_planner.py tests/test_paperbroker_account_ledger.py`: 57 passed
- `tests/test_active_policy_integration.py tests/test_active_trading_policy.py`: 32 passed

Smokes passed for incident response, portfolio replay, stress ladder, allocator, hybrid replay, cross-underlying V2, adversarial corpus, threshold optimizer, outcome replay, risk model, account ledger rotation, active policy integration, audit, reporting, export, review, and stabilizer.

`python -m pytest --collect-only` collected 1703 tests. Bounded `python -m pytest` timed out after 125.027 seconds in `tests/test_artifact_compaction_export_verifier.py`; status is `inconclusive_timeout`, not pass.

## Limitations

This is deterministic fixture evidence only. It does not prove profitability, predictive power, market accuracy, live readiness, broker capability, real account behavior, or real incident response. It is a rehearsal and governance proof layer only.


## Active Lifecycle Integration

`DOPEY_ACTIVE_LONG_CALL_LONG_PUT_LIFECYCLE_SIMULATOR_V1` now feeds incident response with advisory lifecycle feedback. Incident terminal block cases interrupt lifecycle progress without forcing same-day close, overriding PaperBroker, mutating live policy, or auto-recovering terminal blocks.

## Broker-Readiness Boundary Incidents

- broker_readiness_boundary_violations_terminal_block: `true`
- broker_capability_detector_before_approval_terminal_block: `true`
- credential_env_scheduler_network_live_order_real_sizing_violations_terminal_block: `true`
- auto_recovery_for_broker_boundary_violations: `false`

## Manual Approval Bypass Incident Update - 2026-07-04

- Read-only detector run attempted without approval terminal-blocks.
- Detector scope expansion attempted before approval terminal-blocks.
- Command template enabled without approval terminal-blocks.
- Approval text that expands into live trading, credentials, order placement, order cancellation, scheduler, autonomous live trading, or real sizing terminal-blocks.
- Detector network-call or broker-connection attempts inside the packet bundle terminal-block.
