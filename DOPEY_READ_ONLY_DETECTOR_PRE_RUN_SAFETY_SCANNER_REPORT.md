# DOPEY Read-Only Detector Pre-Run Safety Scanner

## Objective
Build an offline pre-run gate for a future separately approved read-only detector bundle.

## Why This Is Not Detector Execution
- detector_run_in_this_bundle: `false`
- broker_connection_in_this_bundle: `false`
- credentials_in_this_bundle: `false`
- scheduler_in_this_bundle: `false`
- real_sizing_in_this_bundle: `false`

## Models And Scanner
- pre_run_scan_input_model: `PreRunSafetyScanInput`
- boundary_scan_result_model: `PreRunBoundaryScanResult`
- safety_decision_model: `PreRunSafetyDecision`
- forbidden_boundary_scanner: `pre_run_forbidden_boundary_scanner`
- command_template_checks: disabled, not allowed now, explicit reapproval, separate future bundle, pre-run scan, post-run evidence
- audit_export_review_checks: source hashes consumed from handoff, approval intake, dry run, manual packet, preflight, audit, export, review

## Summary
- scan_input_count: `96`
- future_bundle_preparation_allowed_count: `16`
- detector_run_allowed_now_count: `0`
- broker_connection_allowed_now_count: `0`
- credential_allowed_now_count: `0`
- live_order_allowed_now_count: `0`
- scheduler_allowed_now_count: `0`
- real_sizing_allowed_now_count: `0`
- terminal_block_count: `72`
- manual_review_count: `8`
- command_templates_disabled: `true`
- boundary_classification_distribution: `{'allowed_blocked_command_template': 4, 'allowed_documentation_mention': 69, 'allowed_negative_control_fixture': 4, 'forbidden_active_runtime_usage': 35}`
- decision_distribution: `{'blocked_credential_finding': 6, 'blocked_missing_handoff': 1, 'blocked_permission_leak': 16, 'blocked_safety_finding': 6, 'blocked_timeout_misclassified': 8, 'future_bundle_preparation_allowed': 16, 'manual_review_required': 7, 'terminal_block': 36}`

## Validation
- targeted_pre_run_tests: recorded in `tests/test_read_only_detector_pre_run_safety_scanner.py`
- full_suite_status: `inconclusive_timeout` remains not pass until separately proven

## Limitations
- No broker capability proof exists.
- No broker connection, credential setup, Robinhood MCP integration, real market data, live order, scheduler, or real sizing exists.
- A future detector run still requires a separate approved bundle plus a clean pre-run scan.

## Safety State
- safety_state: `live_blocked_broker_absent_detector_not_run`
- next_required_gate: `human_approved_read_only_broker_capability_detector_bundle`

## DOPEY_HUMAN_APPROVED_READ_ONLY_BROKER_CAPABILITY_DETECTOR_V1

- status: `human_approved_read_only_detector_validated`
- detector_status_distribution: `{'not_run_approval_missing': 31, 'not_run_manual_review_required': 1, 'not_run_pre_run_blocked': 1, 'not_run_terminal_block': 19, 'read_only_detector_fixture_completed': 68}`
- post_run_evidence_written: `true`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
