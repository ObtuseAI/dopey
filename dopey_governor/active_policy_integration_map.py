"""Deterministic active policy integration map for DOPEY."""
from __future__ import annotations

import json
from pathlib import Path

from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_core.repo_paths import REPORTS_DIR

from .active_trading_policy import ACTIVE_TRADING_POLICY_VERSION, active_trading_canon_record


ACTIVE_POLICY_INTEGRATION_MAP_VERSION = "dopey-active-policy-integration-map-v1"
REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "governor"
INTEGRATION_MAP_JSON = ARTIFACT_DIR / "active_policy_integration_map.json"
INTEGRATION_MAP_MD = REPORTS_DIR / "ACTIVE_POLICY_INTEGRATION_MAP.md"


def active_policy_safety_state() -> dict:
    return {
        "mode": "RESEARCH",
        "paper_only": True,
        "live_blocked": True,
        "live_trading_enabled": False,
        "funded_broker_connections_enabled": False,
        "allow_unofficial_robinhood_api": False,
        "broker_credentials_required": False,
        "network_market_data_required": False,
    }


def build_enforcement_points() -> list[dict]:
    return [
        _point("strategy_genome_generation", "dopey_research_pipeline.strategy_fixture", ["long_call_long_put_preference", "legacy_spread_marked_noncompliant"], ["buy_to_open_long_call", "buy_to_open_long_put"], ["sell_to_open", "unsupported_spread"], "normal positions require next-day close", "0DTE requires special lifecycle", ["test_active_strategy_generation_only_long_call_long_put"]),
        _point("strategy_mutation", "dopey_strategy_lab.genome_mutation", ["reject_short_leg_mutation", "reject_same_day_churn_mutation", "live_allowed_false"], ["offline_alpha_layer_mutation"], ["short_option_leg_mutation", "live_execution_mutation"], "same-day churn mutation rejected", "0DTE mutation must retain special lifecycle", ["test_mutation_rejects_short_option_leg", "test_mutation_rejects_same_day_churn_candidate"]),
        _point("structure_builder", "dopey_options.structure_builder", ["active_policy_structure_classification", "legacy_spread_noncompliant_marker"], ["long_call", "long_put"], ["vertical", "credit_spread", "short_straddle"], "no close authority here", "marks 0DTE structures for lifecycle review", ["test_structure_builder_marks_unsupported_spreads_noncompliant"]),
        _point("tournament_candidate_validation", "dopey_tournament.runner", ["active_policy_compliant_candidates_survive", "unsafe_candidates_rejected"], ["paper_candidate"], ["active_noncompliant_candidate"], "same-day churn penalty", "0DTE only with special lifecycle evidence", ["test_active_policy_compliant_candidates_survive_tournament_validation"]),
        _point("order_intent_creation", "dopey_research_pipeline.intent_builder", ["active_policy_required_fields", "buy_to_open_only"], ["buy_to_open"], ["sell_to_open", "multi_leg_spread"], "normal close cannot be created same day", "0DTE fields must be explicit", ["test_buy_to_open_call_allowed", "test_buy_to_open_put_allowed"]),
        _point("order_intent_validator", "dopey_execution.order_intent_validator", ["active_policy_errors", "long_call_long_put_only", "live_order_rejected"], ["buy_to_open", "sell_to_close"], ["sell_to_open", "naked_sale", "undefined_risk", "unsupported_multileg"], "same_day_round_trip_rejected", "zero_dte_requires_special_lifecycle", ["test_active_policy_enforcement_points_include_order_validator", "test_same_day_round_trip_rejected_for_normal_call"]),
        _point("paper_broker", "dopey_execution.paper_broker", ["independent_active_policy_enforcement", "proof_record_reason_code"], ["active_buy_to_open", "next_day_sell_to_close"], ["live_allowed_true", "sell_to_open", "same_day_close"], "same-day close rejected before fill", "0DTE special lifecycle accepted or rejected explicitly", ["test_active_policy_enforcement_points_include_paper_broker", "test_paper_broker_rejects_sell_to_open"]),
        _point("simulated_position_ledger", "dopey_execution.position_lifecycle", ["open_close_date_tracking", "matching_open_position_required"], ["paper_open", "paper_closed"], ["close_without_open", "close_before_open"], "records blocked_same_day_round_trip", "records zero_dte_special_lifecycle", ["test_close_without_open_position_rejected", "test_next_day_close_allowed_for_call"]),
        _point("paper_account_ledger", "dopey_execution.account_ledger", ["account_level_open_position_tracking", "close_eligible_date", "day_trade_event_log"], ["buy_to_open_long_call", "buy_to_open_long_put", "next_day_sell_to_close"], ["sell_to_open", "same_day_normal_close", "close_without_open"], "same-day close attempts logged and rejected", "0DTE account lifecycle proof tracked separately", ["test_paper_account_ledger_serializes_deterministically", "test_day_trade_event_logged_when_same_day_close_attempted"]),
        _point("configurable_day_trade_policy", "dopey_execution.day_trade_policy", ["conservative_offline_policy", "rolling_window_audit_visible", "not_legal_advice"], ["next_trading_day_close", "multi_day_rotation"], ["normal_same_day_round_trip"], "minimum_close_delay=next_trading_day", "special 0DTE exit controlled by config", ["test_same_day_close_rejected_for_call", "test_next_day_close_allowed_for_put"]),
        _point("pdt_safe_rotation_planner", "dopey_execution.rotation_planner", ["delayed_exit_plan", "allowed_entry_plan", "blocked_action_plan"], ["open_compliant_new_entry", "delayed_rotation"], ["blocked_same_day_round_trip", "blocked_live_path"], "creates delayed exit instead of churn", "requires explicit 0DTE lifecycle approval", ["test_rotation_planner_allows_new_compliant_entry", "test_rotation_planner_creates_delayed_exit_plan"]),
        _point("simulated_close_exit_evaluator", "dopey_execution.no_day_trade_guard", ["no_day_trade_guard", "next_day_close_gate"], ["next_day_sell_to_close"], ["same_day_round_trip"], "core enforcement point", "delegates special 0DTE expiry handling", ["test_same_day_round_trip_rejected_for_normal_put"]),
        _point("0dte_lifecycle_handler", "dopey_execution.zero_dte_lifecycle", ["strict_lifecycle_state", "liquidity_approval", "risk_cap_approval", "reason_code"], ["zero_dte_expiry_managed"], ["missing_lifecycle", "missing_liquidity", "missing_risk_cap"], "not a normal day-trade loophole", "primary 0DTE handler", ["test_zero_dte_call_requires_special_lifecycle", "test_zero_dte_expiry_managed_state_is_not_normal_day_trade"]),
        _point("0dte_special_lifecycle_risk_model", "dopey_options.zero_dte_decision_engine", ["strict_liquidity", "strict_spread", "strict_slippage", "greeks_stable_enough", "iv_not_overpaid", "proof_and_signal_present", "risk_cap"], ["approved_for_paper_open", "approved_with_throttle"], ["blocked_liquidity", "blocked_spread", "blocked_slippage", "blocked_iv_shock", "sell_to_open", "undefined_risk_structure"], "normal same-day churn still rejected", "0DTE requires dedicated risk decision before account entry", ["test_liquid_strong_trend_call_approved", "test_zero_dte_blocked_candidate_cannot_enter_account_ledger"]),
        _point("0dte_expiry_outcome_replay_simulator", "dopey_options.zero_dte_replay_engine", ["fixture_only_replay", "expiry_management", "special_close_guard", "advisory_threshold_feedback"], ["paper_learning_feedback"], ["live_order", "broker_execution", "real_market_data", "auto_approval_from_replay"], "special-close replay remains reason-code gated", "0DTE replay is advisory evidence only", ["test_clean_bullish_trend_call_replay_survives", "test_replay_feedback_does_not_auto_approve_blocked_candidate"]),
        _point("0dte_threshold_feedback_optimizer", "dopey_options.zero_dte_threshold_optimizer", ["feedback_aggregation", "candidate_threshold_generation", "shadow_replay", "promotion_gate"], ["paper_shadow_candidate", "research_default_candidate_artifact"], ["live_threshold_mutation", "unsafe_new_approval", "auto_live_promotion"], "normal same-day churn remains blocked by invariant", "threshold optimization is fixture-only advisory evidence", ["test_shadow_replay_detects_unsafe_new_approval", "test_optimizer_decision_does_not_mutate_live_thresholds"]),
        _point("meta_governor", "dopey_governor.meta_governor", ["paper_only_promotion", "active_policy_summary_visible"], ["paper_candidate"], ["live_candidate"], "same-day churn candidates demoted", "0DTE proof gap blocks promotion", ["test_live_trading_remains_disabled_after_active_policy_integration"]),
        _point("proof_ledger", "dopey_core.proof_ledger", ["append_only_policy_proof", "reason_codes_recorded"], ["paper_proof_record"], ["live_order_record"], "same-day rejection reason retained", "0DTE lifecycle proof retained", ["test_paper_broker_records_policy_rejection_reason"]),
        _point("evidence_audit", "dopey_audit.active_policy_audit", ["active_policy_artifacts_present", "forbidden_violation_scan"], ["audit_pass"], ["missing_policy_kernel", "same_day_violation", "undefined_risk_active_candidate"], "audit flags same-day round-trip violation", "audit requires zero_dte_lifecycle_proof", ["test_active_policy_enforcement_points_include_audit", "test_audit_recognizes_active_policy_artifacts"]),
        _point("reporting_export_review", "dopey_reporting/dopey_export/dopey_export_review", ["active_policy_summary", "artifact_ledger", "live_blocked_state"], ["offline_review_artifact"], ["live_handoff"], "reports no-day-trade guard summary", "reports 0DTE lifecycle summary", ["test_reporting_includes_active_policy_summary", "test_export_review_includes_active_policy_summary"]),
    ]


def build_active_policy_integration_map() -> dict:
    record = {
        "integration_map_version": ACTIVE_POLICY_INTEGRATION_MAP_VERSION,
        "policy_version": ACTIVE_TRADING_POLICY_VERSION,
        "canon": active_trading_canon_record(),
        "safety_state": active_policy_safety_state(),
        "enforcement_points": build_enforcement_points(),
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def write_active_policy_integration_map(
    json_path: Path | str = INTEGRATION_MAP_JSON,
    markdown_path: Path | str = INTEGRATION_MAP_MD,
) -> dict:
    record = build_active_policy_integration_map()
    json_target = Path(json_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_target = Path(markdown_path)
    md_target.write_text(render_integration_map_markdown(record), encoding="utf-8")
    return {**record, "json_path": str(json_target), "markdown_path": str(md_target)}


def render_integration_map_markdown(record: dict) -> str:
    lines = ["# DOPEY Active Policy Integration Map", ""]
    lines.append(f"- integration_map_version: `{record['integration_map_version']}`")
    lines.append(f"- policy_version: `{record['policy_version']}`")
    lines.append("- paper_only: `true`")
    lines.append("- live_blocked: `true`")
    lines.append("")
    lines.append("| Enforcement point | Component | Allowed | Rejected | No-day-trade | 0DTE | Tests |")
    lines.append("|---|---|---|---|---|---|---|")
    for point in record["enforcement_points"]:
        lines.append(
            "| `{name}` | `{component}` | {allowed} | {rejected} | {day} | {zero} | {tests} |".format(
                name=point["enforcement_point"],
                component=point["component"],
                allowed=", ".join(point["allowed_action_types"]),
                rejected=", ".join(point["rejected_action_types"]),
                day=point["no_day_trade_handling"],
                zero=point["zero_dte_handling"],
                tests=", ".join(point["tests_covering"]),
            )
        )
    return "\n".join(lines) + "\n"


def _point(
    enforcement_point: str,
    component: str,
    checks: list[str],
    allowed: list[str],
    rejected: list[str],
    no_day_trade: str,
    zero_dte: str,
    tests: list[str],
) -> dict:
    return {
        "enforcement_point": enforcement_point,
        "component": component,
        "policy_checks_applied": checks,
        "allowed_action_types": allowed,
        "rejected_action_types": rejected,
        "no_day_trade_handling": no_day_trade,
        "zero_dte_handling": zero_dte,
        "paper_only": True,
        "live_blocked": True,
        "tests_covering": tests,
    }
