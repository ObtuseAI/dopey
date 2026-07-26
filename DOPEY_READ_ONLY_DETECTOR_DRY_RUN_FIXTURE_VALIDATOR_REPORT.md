# DOPEY Read-Only Detector Dry-Run Fixture Validator Report

This bundle validates future detector fixture schemas only. It is not detector execution, broker integration, Robinhood MCP integration, credential setup, live trading, scheduling, real sizing, or market-data access.

## Summary
- dry_run_status: `dry_run_fixture_validated`
- approval_status: `approval_missing`
- detector_approved: `False`
- detector_run_attempted: `False`
- input_count: `96`
- simulated_response_count: `32`
- read_only_shape_count: `21`
- blocked_write_execute_shape_count: `32`
- boundary_block_count: `12`
- proof_record_count: `96`
- next_required_gate: `explicit_human_approval_for_read_only_broker_capability_detector_only`

## Safety State
- paper_only: `true`
- live_blocked: `true`
- no_real_market_data: `true`
- no_broker: `true`
- no_real_sizing: `true`
- no_scheduler: `true`
- no_credential: `true`
- no_live_order: `true`

## Limitations
- No broker capability, live readiness, profitability, predictive power, or market accuracy is claimed.
- Full suite timeout remains `inconclusive_timeout`, not pass.
- Future detector approval remains missing.

## Approval Intake Validator
- Approval-intake validator exists as an offline fixture-only text validator.
- Dry-run remains not detector execution.

## DOPEY_READ_ONLY_DETECTOR_APPROVAL_TO_RUN_HANDOFF_GATE_V1

- status: `handoff_gate_validated`
- future_bundle_eligible_count: `12`
- current_detector_run_allowed_count: `0`
- broker_connection_allowed_now_count: `0`
- credential_allowed_now_count: `0`
- live_order_allowed_now_count: `0`
- scheduler_allowed_now_count: `0`
- real_sizing_allowed_now_count: `0`
- separate_future_bundle_required: `true`
- explicit_reapproval_required: `true`
- pre_run_safety_scan_required: `true`
- post_run_evidence_required: `true`

## DOPEY_READ_ONLY_DETECTOR_PRE_RUN_SAFETY_SCANNER_V1

- status: `pre_run_safety_scanner_validated`
- future_bundle_preparation_allowed_count: `16`
- detector_run_allowed_now_count: `0`
- broker_connection_allowed_now_count: `0`
- credential_allowed_now_count: `0`
- live_order_allowed_now_count: `0`
- scheduler_allowed_now_count: `0`
- real_sizing_allowed_now_count: `0`
- command_templates_disabled: `true`
- separate_future_bundle_required: `true`
- explicit_reapproval_required: `true`
- pre_run_safety_scan_required: `true`
- post_run_evidence_required: `true`
- pre_run_scanner_does_not_run_detector: `true`
- future_bundle_preparation_is_not_broker_connection: `true`
- boundary_leak_terminal_blocks: `true`
