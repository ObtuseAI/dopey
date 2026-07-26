# DOPEY Read-Only Detector Approval Intake Validator Report

This bundle validates fixture approval text only. It is not detector execution, broker integration, Robinhood MCP integration, credential setup, live trading, order review, order placement, order cancellation, scheduling, real sizing, or market-data access.

## Objective
- Validate whether fixture approval text exactly matches the required read-only detector acknowledgement.
- Reject missing, partial, stale, malformed, ambiguous, or scope-expanding approvals.
- Keep any exact valid fixture approval limited to future-detector eligibility for a later explicitly approved bundle.

## Summary
- approval_intake_status: `approval_intake_fixture_validated`
- request_count: `96`
- exact_valid_fixture_approval_count: `12`
- invalid_approval_count: `52`
- manual_review_count: `8`
- terminal_block_count: `24`
- future_detector_eligible_count: `12`
- detector_run_allowed_now_count: `0`
- broker_connection_allowed_now_count: `0`
- credential_allowed_now_count: `0`
- live_order_allowed_now_count: `0`
- scheduler_allowed_now_count: `0`
- real_sizing_allowed_now_count: `0`

## Approval Status Distribution
- `invalid`: `40`
- `manual_review_required`: `8`
- `missing`: `12`
- `terminal_block`: `24`
- `valid_exact_read_only_detector_only_fixture`: `12`

## Forbidden Scope Scanner
- `account_balance`: `1`
- `autonomous_live`: `1`
- `autonomous_live_trading`: `1`
- `broker_write`: `1`
- `broker_write_access`: `1`
- `buying_power`: `1`
- `cancel_order`: `1`
- `cancel_orders`: `1`
- `command_injection_like_text`: `1`
- `credential`: `1`
- `credentials`: `1`
- `hidden_newline_command`: `1`
- `live_trading`: `9`
- `network_market_data`: `1`
- `path_token_reference`: `1`
- `place_trades`: `1`
- `real_sizing`: `1`
- `robinhood_mcp_execution`: `1`
- `scheduler`: `1`
- `store_credentials`: `1`
- `token`: `1`

## Safety State
- approval_effective_now: `false`
- detector_run_allowed_now: `false`
- broker_connection_allowed_now: `false`
- credential_allowed_now: `false`
- live_order_allowed_now: `false`
- scheduler_allowed_now: `false`
- real_sizing_allowed_now: `false`
- read_only_detector_run: `false`
- paper_only: `true`
- live_blocked: `true`

## Limitations
- Approval intake can recognize an exact local fixture approval, but it cannot run the detector.
- Full suite timeout remains `inconclusive_timeout`, not pass.
- A future detector run still requires a separate explicitly approved bundle.

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
