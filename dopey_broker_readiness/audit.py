"""Audit helpers for broker-readiness artifacts."""
from __future__ import annotations


FORBIDDEN_BROKER_READINESS_FIELDS: tuple[tuple[str, str], ...] = (
    ("real_dollars", "real_dollar_sizing_forbidden"),
    ("buying_power", "buying_power_forbidden"),
    ("account_balance", "account_balance_forbidden"),
    ("broker_connection", "broker_connection_forbidden"),
    ("credentials", "credentials_forbidden"),
    ("scheduler", "scheduler_forbidden"),
    ("network_market_data", "network_market_data_forbidden"),
    ("live_order_review", "live_order_review_forbidden"),
    ("order_placement", "order_placement_forbidden"),
)

FORBIDDEN_MANUAL_APPROVAL_FIELDS: tuple[tuple[str, str], ...] = (
    ("approval_present", "manual_approval_must_not_be_present"),
    ("approval_valid", "manual_approval_must_not_be_valid"),
    ("detector_approved_now", "manual_approval_detector_must_not_be_approved"),
    ("detector_run_now", "manual_approval_detector_must_not_run"),
    ("live_trading_enabled", "manual_approval_live_trading_forbidden"),
    ("broker_connection_created", "manual_approval_broker_connection_forbidden"),
    ("credentials_created", "manual_approval_credentials_forbidden"),
    ("scheduler_created", "manual_approval_scheduler_forbidden"),
    ("real_sizing_created", "manual_approval_real_sizing_forbidden"),
    ("robinhood_mcp_integration_created", "manual_approval_robinhood_mcp_forbidden"),
    ("read_only_detector_run", "manual_approval_detector_run_forbidden"),
)

FORBIDDEN_TEMPLATE_TOKENS: tuple[tuple[str, str], ...] = (
    ("credential", "manual_template_credentials_forbidden"),
    ("api_key", "manual_template_credentials_forbidden"),
    ("token_path", "manual_template_token_path_forbidden"),
    (".env", "manual_template_env_forbidden"),
    ("place-order", "manual_template_order_placement_forbidden"),
    ("place_order", "manual_template_order_placement_forbidden"),
    ("cancel-order", "manual_template_order_cancellation_forbidden"),
    ("cancel_order", "manual_template_order_cancellation_forbidden"),
    ("scheduler", "manual_template_scheduler_forbidden"),
    ("broker-connect", "manual_template_broker_connection_forbidden"),
    ("enable-live", "manual_template_live_trading_forbidden"),
    ("live-execution", "manual_template_live_trading_forbidden"),
)


def audit_broker_readiness_summary(summary: dict) -> list[dict]:
    findings: list[dict] = []
    if summary.get("paper_only") is not True or summary.get("live_blocked") is not True:
        findings.append({"check_id": "broker_readiness_paper_live_boundary", "severity": "safety_error"})
    if summary.get("readiness_status") in {"live_ready", "broker_ready"}:
        findings.append({"check_id": "broker_readiness_not_live_ready", "severity": "safety_error"})
    if summary.get("next_required_gate") != "explicit_human_approval_for_future_read_only_capability_detector_bundle":
        findings.append({"check_id": "broker_readiness_manual_approval_gate", "severity": "safety_error"})
    for field_name, check_id in FORBIDDEN_BROKER_READINESS_FIELDS:
        if bool(summary.get(field_name, False)):
            findings.append({"check_id": check_id, "severity": "safety_error"})
    return findings


def audit_manual_approval_packet_summary(summary: dict) -> list[dict]:
    findings: list[dict] = []
    if summary.get("paper_only") is not True or summary.get("live_blocked") is not True:
        findings.append({"check_id": "manual_approval_paper_live_boundary", "severity": "safety_error"})
    if summary.get("readiness_status") != "approval_packet_ready":
        findings.append({"check_id": "manual_approval_packet_readiness_status", "severity": "safety_error"})
    if summary.get("next_required_gate") != "explicit_human_approval_for_read_only_broker_capability_detector_only":
        findings.append({"check_id": "manual_approval_packet_next_gate", "severity": "safety_error"})
    if summary.get("command_templates_disabled") is not True:
        findings.append({"check_id": "manual_approval_templates_disabled", "severity": "safety_error"})
    if summary.get("command_templates_require_manual_approval") is not True:
        findings.append({"check_id": "manual_approval_templates_require_approval", "severity": "safety_error"})
    for field_name, check_id in FORBIDDEN_MANUAL_APPROVAL_FIELDS:
        if bool(summary.get(field_name, False)):
            findings.append({"check_id": check_id, "severity": "safety_error"})
    return findings


def audit_future_detector_command_template(template: dict) -> list[dict]:
    findings: list[dict] = []
    if template.get("enabled") is not False:
        findings.append({"check_id": "manual_template_enabled", "severity": "safety_error"})
    if template.get("requires_manual_approval") is not True:
        findings.append({"check_id": "manual_template_missing_manual_approval", "severity": "safety_error"})
    if template.get("allowed_now") is not False:
        findings.append({"check_id": "manual_template_allowed_now", "severity": "safety_error"})
    command = str(template.get("command_template", "")).lower()
    for token, check_id in FORBIDDEN_TEMPLATE_TOKENS:
        if token in command:
            findings.append({"check_id": check_id, "severity": "safety_error"})
    return findings


def audit_read_only_detector_dry_run_summary(summary: dict) -> list[dict]:
    findings: list[dict] = []
    if summary.get("paper_only") is not True or summary.get("live_blocked") is not True:
        findings.append({"check_id": "dry_run_paper_live_boundary", "severity": "safety_error"})
    if summary.get("approval_status") != "approval_missing":
        findings.append({"check_id": "dry_run_approval_missing_required", "severity": "safety_error"})
    forbidden_true_fields = (
        "approval_present",
        "detector_approved",
        "detector_run_attempted",
        "broker_connection_attempted",
        "credential_access_attempted",
        "network_access_attempted",
        "live_order_attempted",
        "read_only_detector_run",
        "robinhood_mcp_integration_created",
    )
    for field_name in forbidden_true_fields:
        if bool(summary.get(field_name, False)):
            findings.append({"check_id": f"dry_run_{field_name}_forbidden", "severity": "safety_error"})
    required_true_fields = (
        "order_placement_blocked",
        "order_cancellation_blocked",
        "scheduler_blocked",
        "real_sizing_blocked",
        "no_broker",
        "no_credential",
        "no_scheduler",
        "no_real_sizing",
    )
    for field_name in required_true_fields:
        if summary.get(field_name) is not True:
            findings.append({"check_id": f"dry_run_{field_name}_required", "severity": "safety_error"})
    return findings


def audit_approval_intake_summary(summary: dict) -> list[dict]:
    findings: list[dict] = []
    if summary.get("paper_only") is not True or summary.get("live_blocked") is not True:
        findings.append({"check_id": "approval_intake_paper_live_boundary", "severity": "safety_error"})
    if summary.get("approval_intake_status") != "approval_intake_fixture_validated":
        findings.append({"check_id": "approval_intake_status_not_validated", "severity": "safety_error"})
    forbidden_true_fields = (
        "approval_effective_now",
        "detector_run_allowed_now",
        "broker_connection_allowed_now",
        "credential_allowed_now",
        "live_order_allowed_now",
        "scheduler_allowed_now",
        "real_sizing_allowed_now",
        "live_trading_enabled",
        "broker_connection_created",
        "credentials_created",
        "scheduler_created",
        "real_sizing_created",
        "robinhood_mcp_integration_created",
        "read_only_detector_run",
    )
    for field_name in forbidden_true_fields:
        if bool(summary.get(field_name, False)):
            findings.append({"check_id": f"approval_intake_{field_name}_forbidden", "severity": "safety_error"})
    required_zero_fields = (
        "approval_effective_now_count",
        "detector_run_allowed_now_count",
        "broker_connection_allowed_now_count",
        "credential_allowed_now_count",
        "live_order_allowed_now_count",
        "scheduler_allowed_now_count",
        "real_sizing_allowed_now_count",
    )
    for field_name in required_zero_fields:
        if int(summary.get(field_name, 0)) != 0:
            findings.append({"check_id": f"approval_intake_{field_name}_must_be_zero", "severity": "safety_error"})
    if summary.get("operator_text_raw_exported_for_unsafe_approvals") is not False:
        findings.append({"check_id": "approval_intake_raw_unsafe_text_exported", "severity": "safety_error"})
    if summary.get("terminal_block_count", 0) < 1:
        findings.append({"check_id": "approval_intake_scope_expansion_terminal_block_missing", "severity": "safety_error"})
    return findings


def audit_approval_to_run_handoff_summary(summary: dict) -> list[dict]:
    findings: list[dict] = []
    if summary.get("paper_only") is not True or summary.get("live_blocked") is not True:
        findings.append({"check_id": "approval_to_run_handoff_paper_live_boundary", "severity": "safety_error"})
    if summary.get("approval_to_run_handoff_status") != "handoff_gate_validated":
        findings.append({"check_id": "approval_to_run_handoff_status_not_validated", "severity": "safety_error"})
    forbidden_true_fields = (
        "detector_run_allowed_now",
        "broker_connection_allowed_now",
        "credential_allowed_now",
        "live_order_allowed_now",
        "scheduler_allowed_now",
        "real_sizing_allowed_now",
        "broker_connection_created",
        "credentials_created",
        "scheduler_created",
        "real_sizing_created",
        "robinhood_mcp_integration_created",
        "read_only_detector_run",
    )
    for field_name in forbidden_true_fields:
        if bool(summary.get(field_name, False)):
            findings.append({"check_id": f"approval_to_run_handoff_{field_name}_forbidden", "severity": "safety_error"})
    required_zero_fields = (
        "current_detector_run_allowed_count",
        "broker_connection_allowed_now_count",
        "credential_allowed_now_count",
        "live_order_allowed_now_count",
        "scheduler_allowed_now_count",
        "real_sizing_allowed_now_count",
    )
    for field_name in required_zero_fields:
        if int(summary.get(field_name, 0)) != 0:
            findings.append({"check_id": f"approval_to_run_handoff_{field_name}_must_be_zero", "severity": "safety_error"})
    required_positive_fields = (
        "future_bundle_eligible_count",
        "separate_future_bundle_required_count",
        "explicit_reapproval_required_count",
        "pre_run_safety_scan_required_count",
        "post_run_evidence_required_count",
        "disabled_command_template_count",
        "blocked_missing_valid_approval_count",
        "blocked_terminal_incident_count",
        "manual_review_required_count",
        "blocked_audit_or_export_failure_count",
        "blocked_runtime_permission_leak_count",
        "blocked_scope_expansion_count",
        "blocked_timeout_misclassified_as_pass_count",
    )
    for field_name in required_positive_fields:
        if int(summary.get(field_name, 0)) < 1:
            findings.append({"check_id": f"approval_to_run_handoff_{field_name}_missing", "severity": "safety_error"})
    if summary.get("command_templates_disabled") is not True:
        findings.append({"check_id": "approval_to_run_handoff_templates_not_disabled", "severity": "safety_error"})
    if summary.get("source_full_suite_timeout_recorded_as_pass") is not False:
        findings.append({"check_id": "approval_to_run_handoff_source_timeout_recorded_as_pass", "severity": "safety_error"})
    if summary.get("next_required_gate") != "separate_explicitly_approved_read_only_detector_run_bundle":
        findings.append({"check_id": "approval_to_run_handoff_next_gate", "severity": "safety_error"})
    return findings


def audit_pre_run_safety_summary(summary: dict) -> list[dict]:
    findings: list[dict] = []
    if summary.get("paper_only") is not True or summary.get("live_blocked") is not True:
        findings.append({"check_id": "pre_run_safety_paper_live_boundary", "severity": "safety_error"})
    if summary.get("pre_run_safety_status") != "pre_run_safety_scanner_validated":
        findings.append({"check_id": "pre_run_safety_status_not_validated", "severity": "safety_error"})
    forbidden_true_fields = (
        "read_only_detector_run",
        "broker_connection_created",
        "credentials_created",
        "scheduler_created",
        "real_sizing_created",
        "robinhood_mcp_integration_created",
        "real_market_data_used",
        "live_order_created",
    )
    for field_name in forbidden_true_fields:
        if bool(summary.get(field_name, False)):
            findings.append({"check_id": f"pre_run_safety_{field_name}_forbidden", "severity": "safety_error"})
    required_zero_fields = (
        "detector_run_allowed_now_count",
        "broker_connection_allowed_now_count",
        "credential_allowed_now_count",
        "live_order_allowed_now_count",
        "scheduler_allowed_now_count",
        "real_sizing_allowed_now_count",
        "active_forbidden_live_decisions",
    )
    for field_name in required_zero_fields:
        if int(summary.get(field_name, 0)) != 0:
            findings.append({"check_id": f"pre_run_safety_{field_name}_must_be_zero", "severity": "safety_error"})
    required_true_fields = (
        "command_templates_disabled",
        "separate_future_bundle_required",
        "explicit_reapproval_required",
        "pre_run_safety_scan_required",
        "post_run_evidence_required",
    )
    for field_name in required_true_fields:
        if summary.get(field_name) is not True:
            findings.append({"check_id": f"pre_run_safety_{field_name}_required", "severity": "safety_error"})
    if int(summary.get("future_bundle_preparation_allowed_count", 0)) < 1:
        findings.append({"check_id": "pre_run_safety_future_bundle_preparation_missing", "severity": "safety_error"})
    if summary.get("next_required_gate") != "human_approved_read_only_broker_capability_detector_bundle":
        findings.append({"check_id": "pre_run_safety_next_gate", "severity": "safety_error"})
    return findings


def audit_read_only_detector_summary(summary: dict) -> list[dict]:
    findings: list[dict] = []
    if summary.get("paper_only") is not True or summary.get("live_blocked") is not True:
        findings.append({"check_id": "read_only_detector_paper_live_boundary", "severity": "safety_error"})
    if summary.get("detector_bundle_status") != "human_approved_read_only_detector_validated":
        findings.append({"check_id": "read_only_detector_status_not_validated", "severity": "safety_error"})
    forbidden_true_fields = (
        "credential_access_attempted",
        "network_access_attempted",
        "live_order_attempted",
        "order_placement_attempted",
        "order_cancellation_attempted",
        "scheduler_attempted",
        "real_sizing_attempted",
        "account_balance_attempted",
        "buying_power_attempted",
        "broker_mutation_attempted",
        "real_market_data_used",
        "broker_connection_created",
        "credentials_created",
        "scheduler_created",
        "real_sizing_created",
        "robinhood_mcp_integration_created",
    )
    for field_name in forbidden_true_fields:
        if bool(summary.get(field_name, False)):
            findings.append({"check_id": f"read_only_detector_{field_name}_forbidden", "severity": "safety_error"})
    if int(summary.get("active_forbidden_live_decisions", 0)) != 0:
        findings.append({"check_id": "read_only_detector_active_forbidden_live_decisions_must_be_zero", "severity": "safety_error"})
    if summary.get("not_live_ready") is not True:
        findings.append({"check_id": "read_only_detector_not_live_ready_required", "severity": "safety_error"})
    if summary.get("post_run_evidence_written") is not True:
        findings.append({"check_id": "read_only_detector_post_run_evidence_missing", "severity": "safety_error"})
    if int(summary.get("write_execute_blocked_total", 0)) < 1:
        findings.append({"check_id": "read_only_detector_write_execute_blocks_missing", "severity": "safety_error"})
    return findings


def audit_read_only_detector_evidence_contract_summary(summary: dict) -> list[dict]:
    findings: list[dict] = []
    if summary.get("paper_only") is not True or summary.get("live_blocked") is not True:
        findings.append({"check_id": "evidence_contract_paper_live_boundary", "severity": "safety_error"})
    if summary.get("not_live_ready") is not True:
        findings.append({"check_id": "evidence_contract_not_live_ready_required", "severity": "safety_error"})
    if summary.get("evidence_contract_status") not in {"evidence_contract_complete", "evidence_contract_manual_review"}:
        findings.append({"check_id": "evidence_contract_status_not_reviewable", "severity": "safety_error"})
    if summary.get("promotion_decision") not in {"eligible_for_simulated_quote_order_review_mirror", "manual_review_required", "hold_review_only"}:
        findings.append({"check_id": "evidence_contract_promotion_decision_forbidden", "severity": "safety_error"})
    forbidden_true_fields = (
        "live_trading_enabled",
        "broker_write_execute_created",
        "credentials_created",
        "scheduler_created",
        "real_sizing_created",
        "order_handling_created",
    )
    for field_name in forbidden_true_fields:
        if bool(summary.get(field_name, False)):
            findings.append({"check_id": f"evidence_contract_{field_name}_forbidden", "severity": "safety_error"})
    if int(summary.get("completeness_score", 0)) < 1:
        findings.append({"check_id": "evidence_contract_completeness_score_missing", "severity": "safety_error"})
    return findings
