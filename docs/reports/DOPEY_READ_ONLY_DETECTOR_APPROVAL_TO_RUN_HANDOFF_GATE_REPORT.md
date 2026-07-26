# DOPEY Read-Only Detector Approval-To-Run Handoff Gate

- offline_only: `true`
- fixture_only: `true`
- paper_only: `true`
- live_blocked: `true`
- approval_to_run_handoff_status: `handoff_gate_validated`
- input_count: `72`
- gate_decision_count: `72`
- gate_status_distribution: `{'blocked_audit_or_export_failure': 8, 'blocked_missing_valid_approval': 12, 'blocked_runtime_permission_leak': 8, 'blocked_scope_expansion': 6, 'blocked_terminal_incident': 12, 'blocked_timeout_misclassified_as_pass': 6, 'eligible_future_bundle_only': 12, 'manual_review_required': 8}`
- future_bundle_eligible_count: `12`
- current_detector_run_allowed_count: `0`
- broker_connection_allowed_now_count: `0`
- credential_allowed_now_count: `0`
- live_order_allowed_now_count: `0`
- scheduler_allowed_now_count: `0`
- real_sizing_allowed_now_count: `0`
- separate_future_bundle_required_count: `72`
- explicit_reapproval_required_count: `72`
- pre_run_safety_scan_required_count: `72`
- post_run_evidence_required_count: `72`
- disabled_command_template_count: `3`
- detector_run_in_this_bundle: `false`
- broker_connection_in_this_bundle: `false`
- credentials_in_this_bundle: `false`
- scheduler_in_this_bundle: `false`
- real_sizing_in_this_bundle: `false`
- next_required_gate: `separate_explicitly_approved_read_only_detector_run_bundle`

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

## DOPEY_HUMAN_APPROVED_READ_ONLY_BROKER_CAPABILITY_DETECTOR_V1

- status: `human_approved_read_only_detector_validated`
- detector_status_distribution: `{'not_run_approval_missing': 31, 'not_run_manual_review_required': 1, 'not_run_pre_run_blocked': 1, 'not_run_terminal_block': 19, 'read_only_detector_fixture_completed': 68}`
- post_run_evidence_written: `true`
- detector_output_is_not_live_readiness: `true`
- broker_write_execute_order_credential_scheduler_real_sizing_paths_blocked: `true`
