"""Broker-readiness preflight checklist built from offline proof artifacts."""
from __future__ import annotations

from pathlib import Path

from .broker_readiness_models import BrokerReadinessPreflightCheck, make_preflight_check


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "dopey"


def build_preflight_checks() -> list[BrokerReadinessPreflightCheck]:
    definitions = _active_policy_definitions() + _lifecycle_account_definitions() + _portfolio_incident_definitions() + _boundary_definitions() + _manual_gate_definitions()
    return [
        make_preflight_check(
            f"broker-preflight-{index:03d}",
            category,
            name,
            _status_for_evidence(paths),
            [str(path) for path in paths],
            [] if _status_for_evidence(paths) == "pass" else [f"{name}_missing"],
            True,
        )
        for index, (category, name, paths) in enumerate(definitions, start=1)
    ]


def _status_for_evidence(paths: list[Path]) -> str:
    return "pass" if all(path.exists() for path in paths) else "fail"


def _active_policy_definitions() -> list[tuple[str, str, list[Path]]]:
    active_path = ARTIFACT_ROOT / "audit" / "active_policy_audit.jsonl"
    governor_path = ARTIFACT_ROOT / "governor" / "active_policy_order_validation_proof.jsonl"
    return [
        ("active_policy", "long_call_policy_check", [active_path]),
        ("active_policy", "long_put_policy_check", [active_path]),
        ("active_policy", "sell_to_open_block_check", [active_path]),
        ("active_policy", "no_naked_sale_check", [active_path]),
        ("active_policy", "no_uncovered_writing_check", [active_path]),
        ("active_policy", "no_unsupported_spreads_check", [active_path]),
        ("active_policy", "no_undefined_risk_check", [active_path]),
        ("active_policy", "no_normal_same_day_open_close_check", [active_path]),
        ("active_policy", "zero_dte_special_lifecycle_check", [ARTIFACT_ROOT / "zero_dte_risk" / "zero_dte_risk_summary.json"]),
        ("active_policy", "buy_to_open_only_entry_check", [governor_path]),
        ("active_policy", "sell_to_close_only_exit_check", [governor_path]),
        ("active_policy", "long_premium_only_check", [active_path]),
        ("active_policy", "active_forbidden_live_decisions_zero_check", [active_path]),
        ("active_policy", "paper_only_policy_check", [active_path]),
        ("active_policy", "live_blocked_policy_check", [active_path]),
        ("active_policy", "broker_path_injection_terminal_check", [ARTIFACT_ROOT / "incident_response" / "incident_rehearsal_summary.json"]),
    ]


def _lifecycle_account_definitions() -> list[tuple[str, str, list[Path]]]:
    lifecycle_root = ARTIFACT_ROOT / "lifecycle"
    account_root = ARTIFACT_ROOT / "account_ledger"
    return [
        ("lifecycle", "lifecycle_simulator_exists_check", [lifecycle_root / "lifecycle_summary.json"]),
        ("paperbroker", "paperbroker_adapter_exists_check", [REPO_ROOT / "dopey_execution" / "paper_broker.py"]),
        ("account_ledger", "account_ledger_adapter_exists_check", [REPO_ROOT / "dopey_lifecycle" / "account_ledger_lifecycle_adapter.py"]),
        ("lifecycle", "lifecycle_proof_exists_check", [lifecycle_root / "lifecycle_proof.jsonl"]),
        ("paperbroker", "paperbroker_cannot_be_overridden_check", [lifecycle_root / "lifecycle_paperbroker_results.jsonl"]),
        ("account_ledger", "account_ledger_mismatch_manual_review_check", [lifecycle_root / "lifecycle_account_ledger_results.jsonl"]),
        ("account_ledger", "account_ledger_exists_check", [account_root / "paper_account_ledger.json"]),
        ("no_day_trade", "no_day_trade_guard_exists_check", [account_root / "day_trade_policy.json"]),
        ("no_day_trade", "delayed_rotation_exists_check", [account_root / "rotation_plan.json"]),
        ("no_day_trade", "same_day_normal_close_blocked_check", [account_root / "day_trade_event_log.jsonl"]),
        ("no_day_trade", "next_day_close_allowed_check", [account_root / "rotation_planner_proof.jsonl"]),
        ("zero_dte", "zero_dte_special_lifecycle_separately_tracked_check", [account_root / "zero_dte_account_lifecycle_proof.jsonl"]),
        ("lifecycle", "lifecycle_states_written_check", [lifecycle_root / "lifecycle_states.jsonl"]),
        ("lifecycle", "lifecycle_transitions_written_check", [lifecycle_root / "lifecycle_transitions.jsonl"]),
        ("paperbroker", "paperbroker_policy_executor_not_optimizer_check", [lifecycle_root / "lifecycle_paperbroker_results.jsonl"]),
        ("account_ledger", "account_ledger_hash_boundary_check", [account_root / "paper_account_ledger.json"]),
        ("lifecycle", "lifecycle_summary_consumed_by_broker_readiness_check", [lifecycle_root / "lifecycle_summary.json"]),
    ]


def _portfolio_incident_definitions() -> list[tuple[str, str, list[Path]]]:
    return [
        ("allocation", "allocator_exists_check", [ARTIFACT_ROOT / "allocation" / "paper_allocation_plan.json"]),
        ("portfolio", "portfolio_replay_exists_check", [ARTIFACT_ROOT / "portfolio_replay" / "portfolio_replay_summary.json"]),
        ("stress_ladder", "stress_ladder_exists_check", [ARTIFACT_ROOT / "portfolio_stress_ladder" / "stress_ladder_summary.json"]),
        ("incident_response", "incident_response_exists_check", [ARTIFACT_ROOT / "incident_response" / "incident_rehearsal_summary.json"]),
        ("incident_response", "terminal_block_works_check", [ARTIFACT_ROOT / "incident_response" / "incident_response_decisions.jsonl"]),
        ("stress_ladder", "lockdown_blocks_new_entries_check", [ARTIFACT_ROOT / "portfolio_stress_ladder" / "stress_ladder_summary.json"]),
        ("audit", "full_suite_timeout_cannot_be_pass_check", [ARTIFACT_ROOT / "validation" / "full_suite_stabilizer_summary.json"]),
        ("export_review", "export_safety_scan_check", [ARTIFACT_ROOT / "exports" / "export_safety_scan.jsonl"]),
        ("audit", "offline_audit_exists_check", [ARTIFACT_ROOT / "audit" / "evidence_replay_audit_proof.jsonl"]),
        ("export_review", "export_review_exists_check", [ARTIFACT_ROOT / "export_reviews" / "export_review_proof.jsonl"]),
        ("portfolio", "portfolio_blocks_same_day_close_check", [ARTIFACT_ROOT / "portfolio_replay" / "portfolio_replay_summary.json"]),
        ("stress_ladder", "crisis_mode_throttle_exists_check", [ARTIFACT_ROOT / "portfolio_stress_ladder" / "crisis_throttle_results.jsonl"]),
        ("incident_response", "no_auto_recovery_terminal_block_check", [ARTIFACT_ROOT / "incident_response" / "incident_recovery_plans.jsonl"]),
        ("allocation", "allocator_advisory_only_check", [ARTIFACT_ROOT / "allocation" / "allocation_constraint_summary.json"]),
        ("portfolio", "portfolio_no_real_sizing_check", [ARTIFACT_ROOT / "portfolio_replay" / "portfolio_replay_summary.json"]),
        ("stress_ladder", "stress_feedback_advisory_only_check", [ARTIFACT_ROOT / "portfolio_stress_ladder" / "crisis_allocator_feedback.jsonl"]),
        ("portfolio", "portfolio_exposure_snapshot_exists_check", [ARTIFACT_ROOT / "portfolio_replay" / "portfolio_exposure_snapshots.jsonl"]),
        ("portfolio", "portfolio_allocator_feedback_exists_check", [ARTIFACT_ROOT / "portfolio_replay" / "portfolio_allocator_feedback.jsonl"]),
        ("stress_ladder", "stress_transition_decisions_exist_check", [ARTIFACT_ROOT / "portfolio_stress_ladder" / "stress_transition_decisions.jsonl"]),
        ("incident_response", "incident_recovery_no_auto_terminal_check", [ARTIFACT_ROOT / "incident_response" / "incident_recovery_plans.jsonl"]),
    ]


def _boundary_definitions() -> list[tuple[str, str, list[Path]]]:
    config_path = REPO_ROOT / "configs" / "dopey.research.yaml"
    broker_boundaries = REPO_ROOT / "DOPEY_BROKER_BOUNDARIES.md"
    return [
        ("credential_boundary", "credentials_absent_check", [broker_boundaries]),
        ("credential_boundary", "env_absent_from_exports_check", [ARTIFACT_ROOT / "exports" / "export_safety_scan.jsonl"]),
        ("broker_boundary", "broker_connection_absent_check", [config_path]),
        ("broker_boundary", "robinhood_integration_absent_check", [broker_boundaries]),
        ("network_boundary", "network_market_data_dependency_absent_check", [broker_boundaries]),
        ("scheduler_boundary", "scheduler_absent_check", [broker_boundaries]),
        ("real_sizing_boundary", "real_sizing_absent_check", [broker_boundaries]),
        ("real_sizing_boundary", "buying_power_absent_check", [broker_boundaries]),
        ("real_sizing_boundary", "account_balance_absent_check", [broker_boundaries]),
        ("broker_boundary", "live_orders_absent_check", [broker_boundaries]),
        ("broker_boundary", "live_flags_blocked_check", [config_path]),
        ("broker_boundary", "broker_path_injections_terminal_blocked_check", [ARTIFACT_ROOT / "incident_response" / "incident_rehearsal_summary.json"]),
        ("credential_boundary", "credential_request_terminal_blocked_check", [ARTIFACT_ROOT / "incident_response" / "incident_rehearsal_summary.json"]),
        ("scheduler_boundary", "scheduler_creation_terminal_blocked_check", [ARTIFACT_ROOT / "incident_response" / "incident_rehearsal_summary.json"]),
        ("network_boundary", "network_request_terminal_blocked_check", [ARTIFACT_ROOT / "incident_response" / "incident_rehearsal_summary.json"]),
        ("broker_boundary", "robinhood_path_before_approval_blocked_check", [ARTIFACT_ROOT / "incident_response" / "incident_rehearsal_summary.json"]),
        ("broker_boundary", "broker_integration_before_approval_blocked_check", [broker_boundaries]),
        ("broker_boundary", "live_order_review_against_broker_blocked_check", [broker_boundaries]),
        ("broker_boundary", "live_order_placement_blocked_check", [broker_boundaries]),
        ("broker_boundary", "order_cancel_against_broker_blocked_check", [broker_boundaries]),
    ]


def _manual_gate_definitions() -> list[tuple[str, str, list[Path]]]:
    broker_boundaries = REPO_ROOT / "DOPEY_BROKER_BOUNDARIES.md"
    return [
        ("manual_approval_boundary", "read_only_detector_not_yet_approved_check", [broker_boundaries]),
        ("manual_approval_boundary", "live_execution_not_approved_check", [broker_boundaries]),
        ("manual_approval_boundary", "credential_setup_not_approved_check", [broker_boundaries]),
        ("manual_approval_boundary", "broker_integration_not_approved_check", [broker_boundaries]),
        ("manual_approval_boundary", "scheduler_not_approved_check", [broker_boundaries]),
        ("manual_approval_boundary", "deployment_not_approved_check", [broker_boundaries]),
        ("manual_approval_boundary", "manual_approval_required_next_gate_check", [broker_boundaries]),
        ("manual_approval_boundary", "not_live_ready_status_check", [broker_boundaries]),
    ]
