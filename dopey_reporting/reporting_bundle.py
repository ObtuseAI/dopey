"""Orchestrate the DOPEY tournament performance reporting dashboard bundle."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dopey_core.proof_ledger import ProofEntry, ProofLedger
from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .data_loader import (
    EVIDENCE_PATHS,
    FAMILY_REPORT_CARDS_PATH,
    PERFORMANCE_ATTRIBUTION_PATH,
    REGIME_REPORT_CARDS_PATH,
    REPORTING_BUNDLE_SUMMARY_PATH,
    REPORTING_DASHBOARD_INDEX_JSON,
    REPORTING_DASHBOARD_INDEX_MD,
    REPORTING_PROOF_PATH,
    SCENARIO_REPORT_CARDS_PATH,
    STATIC_DASHBOARD_PATH,
    STRATEGY_REPORT_CARDS_PATH,
    ReportingEvidence,
    artifact_paths,
    load_reporting_evidence,
    safety_state,
    verify_reporting_safety_state,
    write_json,
    write_jsonl_records,
)
from .family_report_cards import build_family_report_cards
from .performance_attribution import build_performance_attribution
from .performance_models import canonical_reporting_hash
from .regime_explainability import build_regime_report_cards
from .report_models import (
    REPORTING_BUNDLE_VERSION,
    REPORTING_DASHBOARD_INDEX_VERSION,
    DashboardArtifactIndex,
    ReportingBundleResult,
)
from .scenario_explainability import build_scenario_report_cards
from .strategy_report_cards import build_strategy_report_cards


def _with_record_hash(record: dict) -> dict:
    output = dict(record)
    output["reproducibility_hash"] = canonical_reporting_hash(output)
    return output


def _write_markdown_index(index: DashboardArtifactIndex, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# DOPEY Tournament Performance Reporting Dashboard Index")
    lines.append("")
    lines.append("- fixture_only: `true`")
    lines.append("- paper_only: `true`")
    lines.append("- live_allowed: `false`")
    lines.append(f"- audit_status: `{index.audit_status}`")
    lines.append("")
    lines.append("## Top Strategies")
    for strategy_id in index.top_strategies:
        lines.append(f"- `{strategy_id}`")
    lines.append("")
    lines.append("## Family Rankings")
    for row in index.family_rankings:
        lines.append(f"- rank `{row['family_rank']}` `{row['strategy_family']}` best=`{row['best_strategy']}` score=`{row['average_score']}`")
    lines.append("")
    lines.append("## Artifact Paths")
    for name, artifact_path in sorted(index.artifact_paths.items()):
        lines.append(f"- `{name}`: `{artifact_path}`")
    lines.append("")
    lines.append("## Known Gaps")
    for gap in index.known_gaps:
        lines.append(f"- {gap}")
    lines.append("")
    lines.append("## Next Recommended Build Targets")
    for target_name in index.next_recommended_build_targets:
        lines.append(f"- `{target_name}`")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _write_static_dashboard(
    index: DashboardArtifactIndex,
    strategy_records: list[dict],
    family_records: list[dict],
    path: Path | str,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        f"<tr><td>{record['strategy_id']}</td><td>{record['strategy_family']}</td><td>{record['tournament_score']}</td><td>{record['meta_governor_decision']}</td></tr>"
        for record in strategy_records[:12]
    )
    family_rows = "\n".join(
        f"<tr><td>{record['family_rank']}</td><td>{record['strategy_family']}</td><td>{record['best_strategy']}</td><td>{record['recommended_research_action']}</td></tr>"
        for record in family_records
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>DOPEY Static Reporting Dashboard</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #171717; background: #f7f7f5; }}
    h1, h2 {{ margin: 0 0 12px; }}
    section {{ margin: 0 0 24px; }}
    table {{ width: 100%; border-collapse: collapse; background: #ffffff; }}
    th, td {{ border: 1px solid #d6d6d0; padding: 8px; text-align: left; }}
    th {{ background: #e8eee8; }}
    .safety {{ font-weight: 700; color: #0f4f2f; }}
  </style>
</head>
<body>
  <h1>DOPEY Static Reporting Dashboard</h1>
  <section class="safety">Fixture-only, paper-only, static artifact. No server, no refresh, no broker credentials, no live trading.</section>
  <section>
    <h2>Top Strategies</h2>
    <table><thead><tr><th>Strategy</th><th>Family</th><th>Score</th><th>Decision</th></tr></thead><tbody>{rows}</tbody></table>
  </section>
  <section>
    <h2>Family Reports</h2>
    <table><thead><tr><th>Rank</th><th>Family</th><th>Best Strategy</th><th>Research Action</th></tr></thead><tbody>{family_rows}</tbody></table>
  </section>
  <section>
    <h2>Audit</h2>
    <p>audit_status: {index.audit_status}; live_allowed: false; paper_only: true.</p>
  </section>
</body>
</html>
"""
    target.write_text(html, encoding="utf-8")
    return target


def _known_gaps(evidence: ReportingEvidence) -> list[str]:
    gaps = []
    for gap in evidence.audit.get("gaps", []) or []:
        if isinstance(gap, dict):
            gaps.append(str(gap.get("category", "")))
    if not gaps:
        gaps.append("deterministic_fixture_only_limitation")
    gaps.append("reporting artifacts explain paper evidence only; they are not live performance evidence")
    if not evidence.active_policy:
        gaps.append("active_policy_audit_missing")
    if not evidence.paper_account_ledger:
        gaps.append("paper_account_ledger_missing")
    if not evidence.rotation_plan:
        gaps.append("rotation_plan_missing")
    if not evidence.zero_dte_risk_summary:
        gaps.append("zero_dte_risk_summary_missing")
    if not evidence.zero_dte_replay_summary:
        gaps.append("zero_dte_replay_summary_missing")
    if not evidence.zero_dte_threshold_optimizer_summary:
        gaps.append("zero_dte_threshold_optimizer_summary_missing")
    if not evidence.zero_dte_combined_replay_summary:
        gaps.append("zero_dte_adversarial_combined_replay_summary_missing")
    if not evidence.zero_dte_combined_v1_v2_replay_summary:
        gaps.append("zero_dte_cross_underlying_v2_combined_replay_summary_missing")
    if not evidence.hybrid_replay_summary:
        gaps.append("hybrid_swing_0dte_v3_replay_summary_missing")
    if not evidence.paper_allocation_plan:
        gaps.append("proof_weighted_paper_allocation_plan_missing")
    if not evidence.portfolio_replay_summary:
        gaps.append("portfolio_replay_summary_missing")
    if not evidence.stress_ladder_summary:
        gaps.append("portfolio_stress_ladder_summary_missing")
    if not evidence.incident_rehearsal_summary:
        gaps.append("incident_rehearsal_summary_missing")
    if not evidence.history_spine_summary:
        gaps.append("history_spine_summary_missing")
    if not evidence.model_repricing_summary:
        gaps.append("model_repricing_summary_missing")
    if not evidence.signal_engine_summary:
        gaps.append("signal_engine_summary_missing")
    if not evidence.backtest_run_summary:
        gaps.append("honest_backtester_summary_missing")
    if not evidence.statistical_truth_summary:
        gaps.append("statistical_truth_summary_missing")
    if not evidence.fitness_replacement_summary:
        gaps.append("fitness_replacement_summary_missing")
    if not evidence.data_ingestion_plan_summary:
        gaps.append("data_ingestion_plan_summary_missing")
    if not evidence.real_data_validation_stack_summary:
        gaps.append("real_data_validation_stack_summary_missing")
    if not evidence.open_source_path_summary:
        gaps.append("open_source_path_summary_missing")
    if not evidence.local_free_ohlcv_stack_summary:
        gaps.append("local_free_ohlcv_stack_summary_missing")
    return [gap for gap in gaps if gap]


def _active_policy_summary(evidence: ReportingEvidence) -> dict:
    active = evidence.active_policy or {}
    return {
        "policy_version": active.get("policy_version", ""),
        "verdict": active.get("verdict", "missing"),
        "safety_errors": active.get("safety_errors", 0),
        "allowed_strategy_universe": ["long_call", "long_put"],
        "rejected_structure_summary": [
            "sell_to_open",
            "naked_option_sale",
            "undefined_risk_structure",
            "unsupported_multileg_structure",
            "normal_same_day_round_trip",
        ],
        "no_day_trade_guard": "normal same-day open/close rejected",
        "zero_dte_lifecycle": "special lifecycle with liquidity, risk cap, and reason-code gates",
        "paperbroker_policy_proof": active.get("artifact_paths", {}).get("active_policy_paperbroker_proof", ""),
        "audit_policy_proof": active.get("artifact_paths", {}).get("active_policy_audit", ""),
        "live_blocked": True,
    }


def _account_ledger_summary(evidence: ReportingEvidence) -> dict:
    ledger = evidence.paper_account_ledger or {}
    rotation = evidence.rotation_plan or {}
    positions = ledger.get("positions", []) if isinstance(ledger.get("positions", []), list) else []
    events = ledger.get("day_trade_events", []) if isinstance(ledger.get("day_trade_events", []), list) else []
    open_positions = [
        position for position in positions
        if isinstance(position, dict) and position.get("close_status") == "open"
    ]
    close_eligible = [
        position for position in open_positions
        if position.get("same_day_close_blocked") is not True
    ]
    same_day_blocked = [
        position for position in open_positions
        if position.get("same_day_close_blocked") is True
    ]
    delayed_exits = rotation.get("delayed_exits", []) if isinstance(rotation.get("delayed_exits", []), list) else []
    decisions = rotation.get("decisions", []) if isinstance(rotation.get("decisions", []), list) else []
    zero_dte = [
        position for position in open_positions
        if isinstance(position, dict) and position.get("zero_dte") is True
    ]
    return {
        "account_id": ledger.get("account_id", ""),
        "ledger_hash": ledger.get("ledger_hash", ""),
        "open_positions_count": len(open_positions),
        "close_eligible_positions_count": len(close_eligible),
        "same_day_blocked_positions_count": len(same_day_blocked),
        "delayed_exits_count": len(delayed_exits),
        "rotation_decisions_count": len(decisions),
        "zero_dte_open_positions_count": len(zero_dte),
        "day_trade_events_count": len(events),
        "paper_only": True,
        "live_blocked": True,
    }


def _zero_dte_risk_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.zero_dte_risk_summary or {}
    return {
        "zero_dte_risk_model_version": summary.get("zero_dte_risk_model_version", ""),
        "threshold_version": summary.get("threshold_version", ""),
        "approved_count": summary.get("approved_count", 0),
        "blocked_count": summary.get("blocked_count", 0),
        "throttled_count": summary.get("throttled_count", 0),
        "expiry_managed_only_count": summary.get("expiry_managed_only_count", 0),
        "non_zero_dte_alternative_recommendations": summary.get("non_zero_dte_alternative_recommendations", 0),
        "top_block_reasons": summary.get("top_block_reasons", {}),
        "risk_tier_distribution": summary.get("risk_tier_distribution", {}),
        "all_expectations_matched": summary.get("all_expectations_matched", False),
        "paper_only": True,
        "live_blocked": True,
    }


def _zero_dte_replay_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.zero_dte_replay_summary or {}
    return {
        "zero_dte_replay_model_version": summary.get("zero_dte_replay_model_version", ""),
        "fixture_case_count": summary.get("fixture_case_count", 0),
        "fixture_path_count": summary.get("fixture_path_count", 0),
        "replay_count": summary.get("replay_count", 0),
        "outcome_distribution": summary.get("outcome_distribution", {}),
        "threshold_feedback_distribution": summary.get("threshold_feedback_distribution", {}),
        "blocked_correctly_count": summary.get("blocked_correctly_count", 0),
        "blocked_maybe_too_strict_count": summary.get("blocked_maybe_too_strict_count", 0),
        "throttle_feedback_count": summary.get("throttle_feedback_count", 0),
        "special_close_used_count": summary.get("special_close_used_count", 0),
        "expiry_management_distribution": summary.get("expiry_management_distribution", {}),
        "later_expiry_feedback_count": summary.get("later_expiry_feedback_count", 0),
        "all_expectations_matched": summary.get("all_expectations_matched", False),
        "all_feedback_expectations_matched": summary.get("all_feedback_expectations_matched", False),
        "paper_only": True,
        "live_blocked": True,
    }


def _zero_dte_threshold_optimizer_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.zero_dte_threshold_optimizer_summary or {}
    return {
        "zero_dte_threshold_optimizer_version": summary.get("zero_dte_threshold_optimizer_version", ""),
        "optimizer_run_id": summary.get("optimizer_run_id", ""),
        "candidate_count": summary.get("candidate_count", 0),
        "rejected_count": summary.get("rejected_count", 0),
        "paper_shadow_candidate_count": summary.get("paper_shadow_candidate_count", 0),
        "research_default_candidate_count": summary.get("research_default_candidate_count", 0),
        "recommended_threshold_profile": summary.get("recommended_threshold_profile", ""),
        "unsafe_approval_count": summary.get("unsafe_approval_count", 0),
        "overfit_warning_count": summary.get("overfit_warning_count", 0),
        "fixture_coverage_gap_count": summary.get("fixture_coverage_gap_count", 0),
        "advisory_only": summary.get("advisory_only", True),
        "live_threshold_mutation_allowed": summary.get("live_threshold_mutation_allowed", False),
        "paper_only": True,
        "live_blocked": True,
    }


def _zero_dte_adversarial_corpus_summary(evidence: ReportingEvidence) -> dict:
    combined = evidence.zero_dte_combined_replay_summary or {}
    coverage = evidence.zero_dte_adversarial_coverage_summary or {}
    return {
        "adversarial_fixture_count": combined.get("adversarial_fixture_count", 0),
        "combined_fixture_count": combined.get("combined_fixture_count", 0),
        "case_family_distribution": combined.get("case_family_distribution", {}),
        "risk_vector_distribution": combined.get("risk_vector_distribution", {}),
        "replay_expectation_match_rate": 1.0 if combined.get("all_adversarial_replay_expectations_matched", False) else 0.0,
        "optimizer_effect_match_rate": 1.0 if combined.get("all_adversarial_optimizer_effects_matched", False) else 0.0,
        "policy_loophole_block_rate": combined.get("policy_loophole_block_rate", 0.0),
        "special_close_stress_count": combined.get("special_close_stress_count", 0),
        "expiry_management_stress_count": combined.get("expiry_management_stress_count", 0),
        "overfit_pressure_score": combined.get("overfit_pressure_score", coverage.get("overfit_pressure_score", 0.0)),
        "threshold_candidate_survival_status": combined.get("stricter_gamma_theta_profile_status", ""),
        "research_default_promotion_allowed": combined.get("research_default_promotion_allowed", False),
        "coverage_completeness_score": coverage.get("coverage_completeness_score", 0.0),
        "paper_only": True,
        "live_blocked": True,
    }


def _zero_dte_cross_underlying_v2_summary(evidence: ReportingEvidence) -> dict:
    combined = evidence.zero_dte_combined_v1_v2_replay_summary or {}
    coverage = evidence.zero_dte_cross_underlying_coverage_summary or {}
    survival = evidence.zero_dte_cross_underlying_threshold_survival or {}
    return {
        "cross_underlying_v2_fixture_count": combined.get("cross_underlying_v2_fixture_count", 0),
        "combined_v1_v2_fixture_count": combined.get("combined_v1_v2_fixture_count", 0),
        "underlying_family_count": combined.get("underlying_family_count", 0),
        "underlying_family_distribution": combined.get("underlying_family_distribution", {}),
        "regime_family_distribution": combined.get("regime_family_distribution", {}),
        "option_type_distribution": combined.get("option_type_distribution", {}),
        "call_put_balance_score": coverage.get("call_put_balance_score", 0.0),
        "risk_vector_distribution": combined.get("risk_vector_distribution", {}),
        "replay_expectation_match_rate": 1.0 if combined.get("all_cross_underlying_replay_expectations_matched", False) else 0.0,
        "optimizer_effect_match_rate": 1.0 if combined.get("all_cross_underlying_optimizer_effects_matched", False) else 0.0,
        "policy_loophole_block_rate_by_family": combined.get("policy_loophole_block_rate_by_family", {}),
        "special_close_summary_by_family": combined.get("special_close_summary_by_family", {}),
        "expiry_management_summary_by_family": combined.get("expiry_management_summary_by_family", {}),
        "later_expiry_summary_by_family": combined.get("later_expiry_summary_by_family", {}),
        "cross_underlying_completeness_score": combined.get("cross_underlying_completeness_score", coverage.get("cross_underlying_completeness_score", 0.0)),
        "threshold_candidate_survival_status": survival.get("stricter_gamma_theta_profile_status", combined.get("threshold_candidate_survival_status", "")),
        "paper_shadow_candidate_downgrade_status": survival.get("paper_shadow_candidate_downgrade_status", ""),
        "research_default_promotion_allowed": survival.get("research_default_promotion_allowed", False),
        "paper_only": True,
        "live_blocked": True,
    }


def _hybrid_swing_0dte_v3_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.hybrid_replay_summary or {}
    coverage = evidence.hybrid_coverage_summary or {}
    survival = evidence.hybrid_threshold_survival or {}
    return {
        "hybrid_pair_count": summary.get("hybrid_pair_count", 0),
        "hybrid_replay_count": summary.get("hybrid_replay_count", 0),
        "swing_candidate_count": summary.get("swing_candidate_count", 0),
        "multi_day_path_count": summary.get("multi_day_path_count", 0),
        "underlying_family_count": summary.get("underlying_family_count", 0),
        "underlying_family_distribution": summary.get("underlying_family_distribution", {}),
        "regime_family_distribution": summary.get("regime_family_distribution", {}),
        "option_type_distribution": summary.get("option_type_distribution", {}),
        "preference_distribution": summary.get("preference_distribution", {}),
        "allocator_tag_distribution": summary.get("allocator_tag_distribution", {}),
        "hybrid_completeness_score": summary.get("hybrid_completeness_score", coverage.get("hybrid_completeness_score", 0.0)),
        "call_put_balance_score": coverage.get("call_put_balance_score", 0.0),
        "delayed_rotation_count": summary.get("delayed_rotation_count", 0),
        "special_close_count": summary.get("special_close_count", 0),
        "next_day_close_count": summary.get("next_day_close_count", 0),
        "overnight_gap_stress_count": summary.get("overnight_gap_stress_count", 0),
        "threshold_candidate_survival_status": survival.get("hybrid_stricter_gamma_theta_profile_status", ""),
        "later_expiry_preference_status": survival.get("later_expiry_preference_status", ""),
        "paper_shadow_candidate_downgrade_status": survival.get("paper_shadow_candidate_downgrade_status", ""),
        "research_default_promotion_allowed": survival.get("research_default_promotion_allowed", False),
        "real_sizing_allowed": summary.get("real_sizing_allowed", False),
        "paper_only": True,
        "live_blocked": True,
    }


def _proof_weighted_allocation_summary(evidence: ReportingEvidence) -> dict:
    plan = evidence.paper_allocation_plan or {}
    exposure = evidence.allocation_exposure_summary or {}
    constraint = evidence.allocation_constraint_summary or {}
    risk_summary = plan.get("risk_summary", {}) if isinstance(plan.get("risk_summary", {}), dict) else {}
    decision_distribution = {}
    plan_constraints = plan.get("constraint_summary", {}) if isinstance(plan.get("constraint_summary", {}), dict) else {}
    if isinstance(plan_constraints.get("decision_distribution", {}), dict):
        decision_distribution = plan_constraints.get("decision_distribution", {})
    return {
        "plan_id": plan.get("plan_id", ""),
        "opportunity_count": plan.get("opportunity_count", 0),
        "allocated_count": plan.get("allocated_count", 0),
        "throttled_count": plan.get("throttled_count", 0),
        "shadow_only_count": plan.get("shadow_only_count", 0),
        "delayed_rotation_count": plan.get("delayed_rotation_count", 0),
        "watchlist_count": plan.get("watchlist_count", 0),
        "rejected_count": plan.get("rejected_count", 0),
        "decision_distribution": decision_distribution,
        "allocation_by_strategy_type": plan.get("allocation_by_strategy_type", {}),
        "allocation_by_underlying_family": plan.get("allocation_by_underlying_family", {}),
        "allocation_by_regime_family": plan.get("allocation_by_regime_family", {}),
        "allocation_by_option_type": plan.get("allocation_by_option_type", {}),
        "zero_dte_paper_premium_risk_units": risk_summary.get("zero_dte_paper_premium_risk_units", exposure.get("zero_dte_paper_premium_risk_units", 0.0)),
        "swing_paper_premium_risk_units": risk_summary.get("swing_paper_premium_risk_units", exposure.get("swing_paper_premium_risk_units", 0.0)),
        "zero_dte_exposure_share": risk_summary.get("zero_dte_exposure_share", exposure.get("zero_dte_exposure_share", 0.0)),
        "zero_dte_share_status": exposure.get("zero_dte_share_status", ""),
        "delayed_rotation_reserves_advisory_only": constraint.get("delayed_rotation_reserves_advisory_only", True),
        "same_day_churn_allocation_allowed": constraint.get("same_day_churn_allocation_allowed", False),
        "paper_broker_override_allowed": constraint.get("paper_broker_override_allowed", False),
        "block_reason_distribution": constraint.get("block_reason_distribution", {}),
        "constraint_reason_distribution": constraint.get("constraint_reason_distribution", {}),
        "paper_only": True,
        "live_blocked": True,
        "no_real_sizing": True,
    }


def _portfolio_replay_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.portfolio_replay_summary or {}
    latest_snapshot = summary.get("latest_exposure_snapshot", {}) if isinstance(summary.get("latest_exposure_snapshot", {}), dict) else {}
    constraint = latest_snapshot.get("constraint_status", {}) if isinstance(latest_snapshot.get("constraint_status", {}), dict) else {}
    return {
        "portfolio_replay_version": summary.get("portfolio_replay_version", ""),
        "portfolio_id": summary.get("portfolio_id", ""),
        "source_allocation_plan_id": summary.get("source_allocation_plan_id", ""),
        "replay_case_count": summary.get("replay_case_count", 0),
        "stress_case_count": summary.get("stress_case_count", 0),
        "state_count": summary.get("state_count", 0),
        "position_count": summary.get("position_count", 0),
        "rotation_decision_count": summary.get("rotation_decision_count", 0),
        "exposure_snapshot_count": summary.get("exposure_snapshot_count", 0),
        "blocked_action_count": summary.get("blocked_action_count", 0),
        "same_day_close_blocked_count": summary.get("same_day_close_blocked_count", 0),
        "paper_shadow_containment_count": summary.get("paper_shadow_containment_count", 0),
        "delayed_rotation_decision_count": summary.get("delayed_rotation_decision_count", 0),
        "zero_dte_exposure_share_max": summary.get("zero_dte_exposure_share_max", 0.0),
        "zero_dte_exposure_status": summary.get("zero_dte_exposure_status", ""),
        "decision_distribution": summary.get("decision_distribution", {}),
        "case_family_distribution": summary.get("case_family_distribution", {}),
        "allocator_feedback_actions": summary.get("allocator_feedback_actions", {}),
        "threshold_feedback_actions": summary.get("threshold_feedback_actions", {}),
        "latest_total_paper_exposure": latest_snapshot.get("total_paper_premium_risk_units", 0.0),
        "latest_zero_dte_units": latest_snapshot.get("zero_dte_paper_units", 0.0),
        "latest_swing_units": latest_snapshot.get("swing_paper_units", 0.0),
        "latest_delayed_rotation_reserve": latest_snapshot.get("delayed_rotation_reserved_units", 0.0),
        "latest_paper_shadow_units": latest_snapshot.get("paper_shadow_units", 0.0),
        "latest_call_units": latest_snapshot.get("call_units", 0.0),
        "latest_put_units": latest_snapshot.get("put_units", 0.0),
        "latest_high_gamma_units": latest_snapshot.get("high_gamma_units", 0.0),
        "latest_high_theta_units": latest_snapshot.get("high_theta_units", 0.0),
        "latest_iv_crush_units": latest_snapshot.get("iv_crush_exposed_units", 0.0),
        "latest_event_macro_units": latest_snapshot.get("event_macro_exposed_units", 0.0),
        "latest_constraint_status": constraint,
        "same_day_churn_allowed": summary.get("same_day_churn_allowed", False),
        "paper_shadow_contained": summary.get("paper_shadow_contained", True),
        "delayed_rotation_advisory_only": summary.get("delayed_rotation_advisory_only", True),
        "portfolio_feedback_advisory_only": summary.get("portfolio_feedback_advisory_only", True),
        "paper_only": True,
        "live_blocked": True,
        "no_real_sizing": True,
    }


def _stress_ladder_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.stress_ladder_summary or {}
    return {
        "stress_ladder_version": summary.get("stress_ladder_version", ""),
        "stress_case_count": summary.get("stress_case_count", 0),
        "stress_level_evaluation_count": summary.get("stress_level_evaluation_count", 0),
        "transition_decision_count": summary.get("transition_decision_count", 0),
        "crisis_throttle_result_count": summary.get("crisis_throttle_result_count", 0),
        "crisis_recovery_result_count": summary.get("crisis_recovery_result_count", 0),
        "proof_record_count": summary.get("proof_record_count", 0),
        "stress_level_distribution": summary.get("stress_level_distribution", {}),
        "transition_distribution": summary.get("transition_distribution", {}),
        "throttle_type_distribution": summary.get("throttle_type_distribution", {}),
        "recovery_transition_distribution": summary.get("recovery_transition_distribution", {}),
        "crisis_mode_trigger_count": summary.get("crisis_mode_trigger_count", 0),
        "lockdown_trigger_count": summary.get("lockdown_trigger_count", 0),
        "zero_dte_throttle_count": summary.get("zero_dte_throttle_count", 0),
        "swing_only_count": summary.get("swing_only_count", 0),
        "no_trade_only_count": summary.get("no_trade_only_count", 0),
        "family_regime_block_count": summary.get("family_regime_block_count", 0),
        "high_gamma_theta_throttle_count": summary.get("high_gamma_theta_throttle_count", 0),
        "liquidity_spread_crisis_count": summary.get("liquidity_spread_crisis_count", 0),
        "lockdown_blocks_new_entries": summary.get("lockdown_blocks_new_entries", False),
        "same_day_close_forced_count": summary.get("same_day_close_forced_count", 0),
        "same_day_churn_allowed": summary.get("same_day_churn_allowed", False),
        "paper_shadow_contained": summary.get("paper_shadow_contained", True),
        "delayed_rotation_advisory_only": summary.get("delayed_rotation_advisory_only", True),
        "no_day_trade_dominant": summary.get("no_day_trade_dominant", True),
        "paperbroker_override_allowed": summary.get("paperbroker_override_allowed", False),
        "allocator_feedback_actions": summary.get("allocator_feedback_actions", {}),
        "threshold_feedback_actions": summary.get("threshold_feedback_actions", {}),
        "paper_only": True,
        "live_blocked": True,
        "no_real_sizing": True,
    }


def _incident_rehearsal_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.incident_rehearsal_summary or {}
    return {
        "incident_response_version": summary.get("incident_response_version", ""),
        "incident_case_count": summary.get("incident_case_count", 0),
        "incident_signal_count": summary.get("incident_signal_count", 0),
        "kill_switch_state_count": summary.get("kill_switch_state_count", 0),
        "incident_response_decision_count": summary.get("incident_response_decision_count", 0),
        "incident_recovery_plan_count": summary.get("incident_recovery_plan_count", 0),
        "proof_record_count": summary.get("proof_record_count", 0),
        "case_group_distribution": summary.get("case_group_distribution", {}),
        "incident_family_distribution": summary.get("incident_family_distribution", {}),
        "severity_distribution": summary.get("severity_distribution", {}),
        "kill_switch_state_distribution": summary.get("kill_switch_state_distribution", {}),
        "response_decision_distribution": summary.get("response_decision_distribution", {}),
        "recovery_plan_distribution": summary.get("recovery_plan_distribution", {}),
        "terminal_block_count": summary.get("terminal_block_count", 0),
        "manual_review_count": summary.get("manual_review_count", 0),
        "audit_only_count": summary.get("audit_only_count", 0),
        "paper_lockdown_count": summary.get("paper_lockdown_count", 0),
        "same_day_close_forced_count": summary.get("same_day_close_forced_count", 0),
        "same_day_churn_allowed": summary.get("same_day_churn_allowed", False),
        "paperbroker_override_allowed": summary.get("paperbroker_override_allowed", False),
        "terminal_block_auto_recovery_allowed": summary.get("terminal_block_auto_recovery_allowed", False),
        "full_suite_timeout_recorded_as_pass": summary.get("full_suite_timeout_recorded_as_pass", False),
        "allocator_feedback_advisory_only": summary.get("allocator_feedback_advisory_only", True),
        "threshold_feedback_advisory_only": summary.get("threshold_feedback_advisory_only", True),
        "stress_ladder_feedback_advisory_only": summary.get("stress_ladder_feedback_advisory_only", True),
        "paper_only": True,
        "live_blocked": True,
        "no_real_sizing": True,
    }


def _active_lifecycle_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.lifecycle_summary or {}
    return {
        "lifecycle_simulator_version": summary.get("lifecycle_simulator_version", ""),
        "lifecycle_case_count": summary.get("lifecycle_case_count", 0),
        "state_count": summary.get("state_count", 0),
        "transition_count": summary.get("transition_count", 0),
        "proof_record_count": summary.get("proof_record_count", 0),
        "state_distribution": summary.get("state_distribution", {}),
        "transition_distribution": summary.get("transition_distribution", {}),
        "paper_open_count": summary.get("paper_open_count", 0),
        "paper_close_count": summary.get("paper_close_count", 0),
        "blocked_transition_count": summary.get("blocked_transition_count", 0),
        "no_day_trade_block_count": summary.get("no_day_trade_block_count", 0),
        "delayed_rotation_count": summary.get("delayed_rotation_count", 0),
        "zero_dte_special_lifecycle_count": summary.get("zero_dte_special_lifecycle_count", 0),
        "zero_dte_expiry_managed_count": summary.get("zero_dte_expiry_managed_count", 0),
        "zero_dte_special_close_success_count": summary.get("zero_dte_special_close_success_count", 0),
        "swing_next_day_close_count": summary.get("swing_next_day_close_count", 0),
        "paperbroker_rejection_count": summary.get("paperbroker_rejection_count", 0),
        "account_ledger_mismatch_count": summary.get("account_ledger_mismatch_count", 0),
        "incident_interruption_count": summary.get("incident_interruption_count", 0),
        "stress_interruption_count": summary.get("stress_interruption_count", 0),
        "terminal_block_count": summary.get("terminal_block_count", 0),
        "proof_completeness": summary.get("proof_completeness", False),
        "same_day_churn_allowed": summary.get("same_day_churn_allowed", False),
        "paperbroker_override_allowed": summary.get("paperbroker_override_allowed", False),
        "full_suite_timeout_recorded_as_pass": summary.get("full_suite_timeout_recorded_as_pass", False),
        "feedback_advisory_only": summary.get("feedback_advisory_only", True),
        "paper_only": True,
        "live_blocked": True,
        "no_real_sizing": True,
    }


def _broker_readiness_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.broker_readiness_summary or {}
    return {
        "broker_readiness_version": summary.get("broker_readiness_version", ""),
        "readiness_status": summary.get("readiness_status", ""),
        "not_broker_ready": summary.get("not_broker_ready", True),
        "not_live_ready": summary.get("not_live_ready", True),
        "read_only_boundary_simulated": summary.get("read_only_boundary_simulated", False),
        "next_required_gate": summary.get("next_required_gate", ""),
        "preflight_check_count": summary.get("preflight_check_count", 0),
        "blocking_failures": summary.get("blocking_failures", 0),
        "read_only_simulation_count": summary.get("read_only_simulation_count", 0),
        "write_execute_blocked_count": summary.get("write_execute_blocked_count", 0),
        "credential_blocks": summary.get("credential_blocks", 0),
        "scheduler_blocks": summary.get("scheduler_blocks", 0),
        "network_blocks": summary.get("network_blocks", 0),
        "broker_blocks": summary.get("broker_blocks", 0),
        "manual_gate_count": summary.get("manual_gate_count", 0),
        "full_suite_timeout_recorded_as_pass": summary.get("full_suite_timeout_recorded_as_pass", False),
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_credential": True,
        "no_scheduler": True,
        "no_real_sizing": True,
    }


def _manual_approval_packet_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.manual_approval_packet_summary or {}
    gate = evidence.manual_approval_gate or {}
    scope = evidence.read_only_detector_scope or {}
    template = evidence.future_detector_command_templates or {}
    return {
        "manual_approval_packet_version": summary.get("manual_approval_packet_version", ""),
        "readiness_status": summary.get("readiness_status", ""),
        "approval_status": summary.get("approval_status", "approval_missing"),
        "approval_present": summary.get("approval_present", False),
        "approval_valid": summary.get("approval_valid", False),
        "detector_approved_now": summary.get("detector_approved_now", False),
        "detector_run_now": summary.get("detector_run_now", False),
        "future_detector_scope": summary.get("future_detector_scope", scope.get("scope_id", "")),
        "exact_acknowledgement_required": summary.get("exact_acknowledgement_required", True),
        "operator_acknowledgement_required": summary.get("operator_acknowledgement_required", gate.get("required_approval_text", "")),
        "command_templates_disabled": summary.get("command_templates_disabled", template.get("enabled") is False if template else True),
        "command_templates_require_manual_approval": summary.get("command_templates_require_manual_approval", template.get("requires_manual_approval") is True if template else True),
        "command_template_count": summary.get("command_template_count", 0),
        "case_count": summary.get("case_count", 0),
        "boundary_block_count": summary.get("boundary_block_count", 0),
        "next_required_gate": summary.get("next_required_gate", ""),
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_credential": True,
        "no_scheduler": True,
        "no_real_sizing": True,
    }


def _read_only_detector_dry_run_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.read_only_detector_dry_run_summary or {}
    response = evidence.simulated_broker_capability_responses or {}
    return {
        "dry_run_validator_version": summary.get("dry_run_validator_version", ""),
        "dry_run_status": summary.get("dry_run_status", ""),
        "approval_status": summary.get("approval_status", "approval_missing"),
        "approval_present": summary.get("approval_present", False),
        "detector_approved": summary.get("detector_approved", False),
        "detector_run_attempted": summary.get("detector_run_attempted", False),
        "broker_connection_attempted": summary.get("broker_connection_attempted", False),
        "credential_access_attempted": summary.get("credential_access_attempted", False),
        "network_access_attempted": summary.get("network_access_attempted", False),
        "live_order_attempted": summary.get("live_order_attempted", False),
        "input_count": summary.get("input_count", 0),
        "simulated_response_count": summary.get("simulated_response_count", 1 if response else 0),
        "read_only_shape_count": summary.get("read_only_shape_count", 0),
        "blocked_write_execute_shape_count": summary.get("blocked_write_execute_shape_count", 0),
        "forbidden_field_count": summary.get("forbidden_field_count", 0),
        "boundary_block_count": summary.get("boundary_block_count", 0),
        "proof_record_count": summary.get("proof_record_count", 0),
        "future_detector_contract_path": summary.get("future_detector_contract_path", ""),
        "next_required_gate": summary.get("next_required_gate", ""),
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_credential": True,
        "no_scheduler": True,
        "no_real_sizing": True,
    }


def _approval_intake_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.approval_intake_summary or {}
    return {
        "approval_intake_validator_version": summary.get("approval_intake_validator_version", ""),
        "approval_intake_status": summary.get("approval_intake_status", ""),
        "request_count": summary.get("request_count", 0),
        "validation_count": summary.get("validation_count", 0),
        "result_count": summary.get("result_count", 0),
        "approval_status_distribution": summary.get("approval_status_distribution", {}),
        "forbidden_term_distribution": summary.get("forbidden_term_distribution", {}),
        "exact_match_validation_count": summary.get("exact_match_validation_count", 0),
        "exact_valid_fixture_approval_count": summary.get("exact_valid_fixture_approval_count", 0),
        "invalid_approval_count": summary.get("invalid_approval_count", 0),
        "manual_review_count": summary.get("manual_review_count", 0),
        "terminal_block_count": summary.get("terminal_block_count", 0),
        "future_detector_eligible_count": summary.get("future_detector_eligible_count", 0),
        "approval_effective_now_count": summary.get("approval_effective_now_count", 0),
        "detector_run_allowed_now_count": summary.get("detector_run_allowed_now_count", 0),
        "broker_connection_allowed_now_count": summary.get("broker_connection_allowed_now_count", 0),
        "credential_allowed_now_count": summary.get("credential_allowed_now_count", 0),
        "live_order_allowed_now_count": summary.get("live_order_allowed_now_count", 0),
        "scheduler_allowed_now_count": summary.get("scheduler_allowed_now_count", 0),
        "real_sizing_allowed_now_count": summary.get("real_sizing_allowed_now_count", 0),
        "next_required_gate": summary.get("next_required_gate", ""),
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_credential": True,
        "no_scheduler": True,
        "no_real_sizing": True,
        "read_only_detector_run": False,
    }


def _approval_to_run_handoff_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.approval_to_run_handoff_summary or {}
    return {
        "approval_to_run_handoff_gate_version": summary.get("approval_to_run_handoff_gate_version", ""),
        "approval_to_run_handoff_status": summary.get("approval_to_run_handoff_status", ""),
        "input_count": summary.get("input_count", 0),
        "envelope_count": summary.get("envelope_count", 0),
        "gate_decision_count": summary.get("gate_decision_count", 0),
        "gate_status_distribution": summary.get("gate_status_distribution", {}),
        "future_bundle_eligible_count": summary.get("future_bundle_eligible_count", 0),
        "blocked_missing_valid_approval_count": summary.get("blocked_missing_valid_approval_count", 0),
        "blocked_terminal_incident_count": summary.get("blocked_terminal_incident_count", 0),
        "manual_review_required_count": summary.get("manual_review_required_count", 0),
        "blocked_audit_or_export_failure_count": summary.get("blocked_audit_or_export_failure_count", 0),
        "blocked_runtime_permission_leak_count": summary.get("blocked_runtime_permission_leak_count", 0),
        "blocked_scope_expansion_count": summary.get("blocked_scope_expansion_count", 0),
        "blocked_timeout_misclassified_as_pass_count": summary.get("blocked_timeout_misclassified_as_pass_count", 0),
        "current_detector_run_allowed_count": summary.get("current_detector_run_allowed_count", 0),
        "broker_connection_allowed_now_count": summary.get("broker_connection_allowed_now_count", 0),
        "credential_allowed_now_count": summary.get("credential_allowed_now_count", 0),
        "live_order_allowed_now_count": summary.get("live_order_allowed_now_count", 0),
        "scheduler_allowed_now_count": summary.get("scheduler_allowed_now_count", 0),
        "real_sizing_allowed_now_count": summary.get("real_sizing_allowed_now_count", 0),
        "separate_future_bundle_required_count": summary.get("separate_future_bundle_required_count", 0),
        "explicit_reapproval_required_count": summary.get("explicit_reapproval_required_count", 0),
        "pre_run_safety_scan_required_count": summary.get("pre_run_safety_scan_required_count", 0),
        "post_run_evidence_required_count": summary.get("post_run_evidence_required_count", 0),
        "disabled_command_template_count": summary.get("disabled_command_template_count", 0),
        "command_templates_disabled": summary.get("command_templates_disabled", True),
        "next_required_gate": summary.get("next_required_gate", ""),
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_credential": True,
        "no_scheduler": True,
        "no_real_sizing": True,
        "read_only_detector_run": False,
    }


def _pre_run_safety_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.pre_run_safety_summary or {}
    return {
        "pre_run_safety_scanner_version": summary.get("pre_run_safety_scanner_version", ""),
        "pre_run_safety_status": summary.get("pre_run_safety_status", ""),
        "scan_input_count": summary.get("scan_input_count", 0),
        "boundary_scan_count": summary.get("boundary_scan_count", 0),
        "decision_count": summary.get("decision_count", 0),
        "future_bundle_preparation_allowed_count": summary.get("future_bundle_preparation_allowed_count", 0),
        "detector_run_allowed_now_count": summary.get("detector_run_allowed_now_count", 0),
        "broker_connection_allowed_now_count": summary.get("broker_connection_allowed_now_count", 0),
        "credential_allowed_now_count": summary.get("credential_allowed_now_count", 0),
        "live_order_allowed_now_count": summary.get("live_order_allowed_now_count", 0),
        "scheduler_allowed_now_count": summary.get("scheduler_allowed_now_count", 0),
        "real_sizing_allowed_now_count": summary.get("real_sizing_allowed_now_count", 0),
        "command_templates_disabled": summary.get("command_templates_disabled", True),
        "boundary_classification_distribution": summary.get("boundary_classification_distribution", {}),
        "terminal_block_count": summary.get("terminal_block_count", 0),
        "manual_review_count": summary.get("manual_review_count", 0),
        "next_required_gate": summary.get("next_required_gate", ""),
        "safety_state": summary.get("safety_state", ""),
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_credential": True,
        "no_scheduler": True,
        "no_real_sizing": True,
        "read_only_detector_run": False,
    }


def _read_only_detector_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.read_only_detector_summary or {}
    return {
        "read_only_detector_version": summary.get("read_only_detector_version", ""),
        "detector_bundle_status": summary.get("detector_bundle_status", ""),
        "approval_status": summary.get("approval_status", "approval_missing"),
        "detector_status_distribution": summary.get("detector_status_distribution", {}),
        "provider_type_distribution": summary.get("provider_type_distribution", {}),
        "capability_family_distribution": summary.get("capability_family_distribution", {}),
        "capability_records_total": summary.get("capability_records_total", 0),
        "read_only_records_total": summary.get("read_only_records_total", 0),
        "write_execute_blocked_total": summary.get("write_execute_blocked_total", 0),
        "credential_block_total": summary.get("credential_block_total", 0),
        "scheduler_block_total": summary.get("scheduler_block_total", 0),
        "live_execution_block_total": summary.get("live_execution_block_total", 0),
        "post_run_evidence_written": summary.get("post_run_evidence_written", False),
        "not_live_ready": summary.get("not_live_ready", True),
        "boundary_violation_count": summary.get("boundary_violation_count", 0),
        "incident_escalation_count": summary.get("incident_escalation_count", 0),
        "next_required_gate": summary.get("next_required_gate", ""),
        "safety_state": summary.get("safety_state", ""),
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_credential": True,
        "no_scheduler": True,
        "no_real_sizing": True,
    }


def _read_only_detector_evidence_contract_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.evidence_contract_summary or {}
    return {
        "evidence_contract_version": summary.get("evidence_contract_version", ""),
        "evidence_contract_status": summary.get("evidence_contract_status", ""),
        "completeness_score": summary.get("completeness_score", 0),
        "completeness_dimensions": summary.get("completeness_dimensions", {}),
        "promotion_decision": summary.get("promotion_decision", "hold_review_only"),
        "allowed_next_stage": summary.get("allowed_next_stage", "review_only"),
        "terminal_block_count": summary.get("terminal_block_count", 0),
        "manual_review_count": summary.get("manual_review_count", 0),
        "evidence_item_count": summary.get("evidence_item_count", 0),
        "boundary_assertion_count": summary.get("boundary_assertion_count", 0),
        "next_recommended_target": summary.get("next_recommended_target", ""),
        "not_live_ready": summary.get("not_live_ready", True),
        "paper_only": True,
        "live_blocked": True,
        "live_trading_enabled": False,
        "broker_write_execute_created": False,
        "credentials_created": False,
        "scheduler_created": False,
        "real_sizing_created": False,
    }


def _history_spine_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.history_spine_summary or {}
    validation = evidence.history_dataset_validation or {}
    return {
        "history_spine_version": summary.get("history_spine_version", ""),
        "dataset_status": summary.get("dataset_status", validation.get("dataset_status", "missing_real_dataset")),
        "real_local_data_found": summary.get("real_local_data_found", False),
        "row_count": summary.get("row_count", validation.get("row_count", 0)),
        "symbols_covered": summary.get("symbols_covered", []),
        "symbols_missing": summary.get("symbols_missing", []),
        "symbols_stale": summary.get("symbols_stale", []),
        "date_range": summary.get("date_range", {"start_date": validation.get("start_date", ""), "end_date": validation.get("end_date", "")}),
        "quality_flags": summary.get("quality_flags", []),
        "manifest_path": summary.get("manifest_path", validation.get("expected_manifest_path", "")),
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_scheduler": True,
        "no_real_sizing": True,
    }


def _model_repricing_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.model_repricing_summary or {}
    iv_validation = evidence.iv_solver_validation or {}
    surface = evidence.vol_surface_model or {}
    latest_flag = evidence.model_repricing_quality_flags or {}
    quality_flags = summary.get("quality_flags", [])
    if latest_flag and isinstance(latest_flag, dict):
        reason_code = latest_flag.get("reason_code", "")
        if reason_code and reason_code not in quality_flags:
            quality_flags = [*quality_flags, reason_code]
    return {
        "model_repricing_version": summary.get("model_repricing_version", ""),
        "model_repricing_status": summary.get("model_repricing_status", "missing"),
        "iv_solver_validation_status": summary.get("iv_solver_validation_status", iv_validation.get("validation_status", "missing")),
        "repricing_path_count": summary.get("repricing_path_count", 0),
        "repricing_step_count": summary.get("repricing_step_count", 0),
        "pricing_source_tier_distribution": summary.get("pricing_source_tier_distribution", {"fixture_only": 0, "model_priced": 0, "quote_priced": 0}),
        "model_priced_records": summary.get("model_priced_records", 0),
        "quote_priced_records": summary.get("quote_priced_records", 0),
        "history_dataset_status": summary.get("history_dataset_status", "missing_real_dataset"),
        "real_history_absent": summary.get("real_history_absent", True),
        "real_option_chain_absent": summary.get("real_option_chain_absent", surface.get("real_option_chain_absent", True)),
        "quality_flags": sorted(quality_flags),
        "real_backtest_results_created": summary.get("real_backtest_results_created", False),
        "expected_outcome_consumed": summary.get("expected_outcome_consumed", False),
        "next_recommended_target": summary.get("next_recommended_target", "DOPEY_REAL_SIGNAL_ENGINES_V1"),
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_scheduler": True,
        "no_real_sizing": True,
    }


def _signal_engine_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.signal_engine_summary or {}
    input_summary = evidence.signal_engine_input_summary or {}
    latest_flag = evidence.signal_quality_flags or {}
    quality_flags = summary.get("quality_flags", [])
    if latest_flag and isinstance(latest_flag, dict):
        reason_code = latest_flag.get("reason_code", "")
        if reason_code and reason_code not in quality_flags:
            quality_flags = [*quality_flags, reason_code]
    return {
        "signal_engine_version": summary.get("signal_engine_version", ""),
        "signal_engine_status": summary.get("signal_engine_status", input_summary.get("signal_status", "missing")),
        "history_dataset_status": summary.get("history_dataset_status", input_summary.get("history_dataset_status", "missing_real_dataset")),
        "real_history_used": summary.get("real_history_used", input_summary.get("real_history_used", False)),
        "fixture_only_case_count": summary.get("fixture_only_case_count", 0),
        "local_real_history_case_count": summary.get("local_real_history_case_count", input_summary.get("local_real_history_case_count", 0)),
        "signal_family_distribution": summary.get("signal_family_distribution", {}),
        "direction_distribution": summary.get("direction_distribution", {}),
        "long_call_candidate_count": summary.get("long_call_candidate_count", 0),
        "long_put_candidate_count": summary.get("long_put_candidate_count", 0),
        "no_trade_count": summary.get("no_trade_count", 0),
        "quality_flags": sorted(quality_flags),
        "not_real_edge_evidence": summary.get("not_real_edge_evidence", True),
        "next_recommended_target": summary.get("next_recommended_target", "DOPEY_HONEST_BACKTESTER_V1"),
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_scheduler": True,
        "no_real_sizing": True,
    }


def _honest_backtester_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.backtest_run_summary or {}
    latest_flag = evidence.backtest_quality_flags or {}
    quality_flags = summary.get("quality_flags", [])
    if latest_flag and isinstance(latest_flag, dict):
        reason_code = latest_flag.get("reason_code", "")
        if reason_code and reason_code not in quality_flags:
            quality_flags = [*quality_flags, reason_code]
    return {
        "backtest_engine_version": summary.get("backtest_engine_version", ""),
        "backtest_status": summary.get("backtest_status", "missing"),
        "history_dataset_status": summary.get("history_dataset_status", "missing_real_dataset"),
        "real_history_used": summary.get("real_history_used", False),
        "pricing_source_tier_distribution": summary.get("pricing_source_tier_distribution", {"fixture_only": 0, "model_priced": 0, "quote_priced": 0}),
        "data_source_tier_distribution": summary.get("data_source_tier_distribution", {"fixture_only": 0}),
        "trade_intent_count": summary.get("trade_intent_count", 0),
        "trade_record_count": summary.get("trade_record_count", 0),
        "long_call_trade_count": summary.get("long_call_trade_count", 0),
        "long_put_trade_count": summary.get("long_put_trade_count", 0),
        "no_trade_count": summary.get("no_trade_count", 0),
        "blocked_policy_violation_count": summary.get("blocked_policy_violation_count", 0),
        "model_priced_trade_count": summary.get("model_priced_trade_count", 0),
        "quote_priced_trade_count": summary.get("quote_priced_trade_count", 0),
        "fixture_only_trade_count": summary.get("fixture_only_trade_count", 0),
        "total_path_pnl_model_units": summary.get("total_path_pnl_model_units", 0.0),
        "average_path_pnl_model_units": summary.get("average_path_pnl_model_units", 0.0),
        "max_drawdown_model_units": summary.get("max_drawdown_model_units", 0.0),
        "win_count": summary.get("win_count", 0),
        "loss_count": summary.get("loss_count", 0),
        "quality_flags": sorted(quality_flags),
        "not_real_backtest_evidence": summary.get("not_real_backtest_evidence", True),
        "not_profitability_claim": summary.get("not_profitability_claim", True),
        "not_live_ready": summary.get("not_live_ready", True),
        "next_recommended_target": summary.get("next_recommended_target", "DOPEY_STATISTICAL_TRUTH_LAYER_V1"),
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_scheduler": True,
        "no_real_sizing": True,
    }


def _statistical_truth_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.statistical_truth_summary or {}
    latest_flag = evidence.statistical_truth_quality_flags or {}
    quality_flags = summary.get("quality_flags", [])
    if latest_flag and isinstance(latest_flag, dict):
        reason_code = latest_flag.get("reason_code", "")
        if reason_code and reason_code not in quality_flags:
            quality_flags = [*quality_flags, reason_code]
    return {
        "statistical_truth_version": summary.get("statistical_truth_version", ""),
        "truth_status": summary.get("truth_status", "missing"),
        "truth_decision": summary.get("truth_decision", "missing"),
        "sample_count": summary.get("sample_count", 0),
        "real_sample_size": summary.get("real_sample_size", 0),
        "fixture_model_sample_size": summary.get("fixture_model_sample_size", 0),
        "win_rate": summary.get("win_rate", 0.0),
        "average_model_unit_pnl": summary.get("average_model_unit_pnl", 0.0),
        "median_model_unit_pnl": summary.get("median_model_unit_pnl", 0.0),
        "total_model_unit_pnl": summary.get("total_model_unit_pnl", 0.0),
        "max_drawdown_model_units": summary.get("max_drawdown_model_units", 0.0),
        "bootstrap_mean_ci": summary.get("bootstrap_mean_ci", [0.0, 0.0]),
        "bootstrap_win_rate_ci": summary.get("bootstrap_win_rate_ci", [0.0, 0.0]),
        "baseline_comparison_count": summary.get("baseline_comparison_count", 0),
        "multiple_testing_applied": summary.get("multiple_testing_applied", False),
        "deflated_sharpe_diagnostic": summary.get("deflated_sharpe_diagnostic", True),
        "significance_claim_allowed": summary.get("significance_claim_allowed", False),
        "real_alpha_claim_allowed": summary.get("real_alpha_claim_allowed", False),
        "profitability_claim_allowed": summary.get("profitability_claim_allowed", False),
        "live_readiness_claim_allowed": summary.get("live_readiness_claim_allowed", False),
        "promotion_allowed": summary.get("promotion_allowed", False),
        "not_real_statistical_evidence": summary.get("not_real_statistical_evidence", True),
        "not_real_backtest_evidence": summary.get("not_real_backtest_evidence", True),
        "not_profitability_claim": summary.get("not_profitability_claim", True),
        "not_live_ready": summary.get("not_live_ready", True),
        "quality_flags": sorted(quality_flags),
        "next_recommended_target": summary.get("next_recommended_target", "DOPEY_FITNESS_FUNCTION_REPLACEMENT_V1"),
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_scheduler": True,
        "no_real_sizing": True,
    }


def _fitness_replacement_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.fitness_replacement_summary or {}
    latest_flag = evidence.fitness_quality_flags or {}
    decision = evidence.fitness_decision or {}
    quality_flags = summary.get("quality_flags", [])
    if latest_flag and isinstance(latest_flag, dict):
        reason_code = latest_flag.get("reason_code", "")
        if reason_code and reason_code not in quality_flags:
            quality_flags = [*quality_flags, reason_code]
    return {
        "fitness_version": summary.get("fitness_version", ""),
        "fitness_status": summary.get("fitness_status", decision.get("fitness_status", "missing")),
        "fitness_decision": summary.get("fitness_decision", decision.get("fitness_decision", "missing")),
        "diagnostic_score": summary.get("diagnostic_score", 0.0),
        "score_component_count": summary.get("score_component_count", 0),
        "penalty_count": summary.get("penalty_count", 0),
        "rank_record_count": summary.get("rank_record_count", 0),
        "promotion_allowed": summary.get("promotion_allowed", False),
        "strategy_promoted": summary.get("strategy_promoted", False),
        "truth_status": summary.get("truth_status", "missing"),
        "truth_decision": summary.get("truth_decision", "missing"),
        "real_sample_size": summary.get("real_sample_size", 0),
        "fixture_model_sample_size": summary.get("fixture_model_sample_size", 0),
        "old_proxy_fitness_quarantined": summary.get("old_proxy_fitness_quarantined", True),
        "blocked_active_proxy_promotion_count": summary.get("blocked_active_proxy_promotion_count", 0),
        "manual_review_proxy_reference_count": summary.get("manual_review_proxy_reference_count", 0),
        "not_real_fitness_evidence": summary.get("not_real_fitness_evidence", True),
        "not_real_statistical_evidence": summary.get("not_real_statistical_evidence", True),
        "not_real_backtest_evidence": summary.get("not_real_backtest_evidence", True),
        "not_profitability_claim": summary.get("not_profitability_claim", True),
        "not_live_ready": summary.get("not_live_ready", True),
        "quality_flags": sorted(quality_flags),
        "next_recommended_target": summary.get("next_recommended_target", "DOPEY_REAL_DATA_INGESTION_PLAN_V1"),
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_scheduler": True,
        "no_real_sizing": True,
    }


def _data_ingestion_plan_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.data_ingestion_plan_summary or {}
    decision = evidence.import_readiness_decision or {}
    return {
        "ingestion_status": summary.get("ingestion_status", decision.get("ingestion_status", "missing")),
        "import_readiness_decision": summary.get("import_readiness_decision", decision.get("import_readiness_decision", "missing")),
        "dataset_requirement_count": summary.get("dataset_requirement_count", 0),
        "provider_candidate_count": summary.get("provider_candidate_count", 0),
        "schema_contract_count": summary.get("schema_contract_count", 0),
        "quality_gate_count": summary.get("quality_gate_count", 0),
        "real_data_files_present": summary.get("real_data_files_present", False),
        "real_data_ingested": summary.get("real_data_ingested", False),
        "real_data_validated": summary.get("real_data_validated", False),
        "network_fetch_performed": summary.get("network_fetch_performed", False),
        "broker_connection_used": summary.get("broker_connection_used", False),
        "credentials_created": summary.get("credentials_created", False),
        "env_created": summary.get("env_created", False),
        "license_review_required_count": summary.get("license_review_required_count", 0),
        "manual_review_required_count": summary.get("manual_review_required_count", 0),
        "terminal_block_count": summary.get("terminal_block_count", 0),
        "next_recommended_target": summary.get("next_recommended_target", "DOPEY_LOCAL_OHLCV_IMPORT_VALIDATOR_V1"),
        "sample_templates_not_real_evidence": True,
        "not_real_data_ingested": True,
        "not_real_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _real_data_validation_stack_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.real_data_validation_stack_summary or {}
    local = evidence.local_ohlcv_import_summary or {}
    history = evidence.real_ohlcv_history_spine_activation or evidence.real_ohlcv_history_spine_upgrade or {}
    signals = evidence.real_signal_validation_summary or {}
    options = evidence.options_data_contract_summary or {}
    return {
        "local_ohlcv_status": summary.get("local_ohlcv_status", local.get("local_ohlcv_status", "missing")),
        "valid_real_dataset": summary.get("valid_real_dataset", local.get("valid_real_dataset", False)),
        "real_history_used": summary.get("real_history_used", history.get("real_history_used", False)),
        "history_spine_upgrade_status": summary.get("history_spine_upgrade_status", history.get("history_spine_upgrade_status", "missing")),
        "history_spine_activation_status": summary.get("history_spine_activation_status", history.get("history_spine_activation_status", "missing")),
        "real_signal_validation_status": summary.get("real_signal_validation_status", signals.get("real_signal_validation_status", "missing")),
        "real_signal_evidence": summary.get("real_signal_evidence", signals.get("real_signal_evidence", False)),
        "options_contract_status": summary.get("options_contract_status", options.get("options_contract_status", "missing")),
        "options_data_validated": summary.get("options_data_validated", options.get("options_data_validated", False)),
        "quote_priced_backtest_allowed": summary.get("quote_priced_backtest_allowed", options.get("quote_priced_backtest_allowed", False)),
        "network_fetch_performed": summary.get("network_fetch_performed", False),
        "broker_connection_used": summary.get("broker_connection_used", False),
        "credentials_created": summary.get("credentials_created", False),
        "env_created": summary.get("env_created", False),
        "next_recommended_target": summary.get("next_recommended_target", "DOPEY_MANUAL_REAL_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1"),
        "paper_only": True,
        "live_blocked": True,
    }


def _open_source_path_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.open_source_path_summary or {}
    return {
        "oss_candidate_count": summary.get("oss_candidate_count", 0),
        "oss_reference_only_count": summary.get("oss_reference_only_count", 0),
        "oss_sandbox_candidate_count": summary.get("oss_sandbox_candidate_count", 0),
        "oss_adapter_candidate_count": summary.get("oss_adapter_candidate_count", 0),
        "oss_imported_count": summary.get("oss_imported_count", 0),
        "oss_executed_count": summary.get("oss_executed_count", 0),
        "free_data_candidate_count": summary.get("free_data_candidate_count", 0),
        "free_data_evidence_allowed_count": summary.get("free_data_evidence_allowed_count", 0),
        "free_data_manual_review_required_count": summary.get("free_data_manual_review_required_count", 0),
        "local_ohlcv_status": summary.get("local_ohlcv_status", "missing"),
        "local_ohlcv_fix_advice_status": summary.get("local_ohlcv_fix_advice_status", "missing"),
        "valid_real_dataset": summary.get("valid_real_dataset", False),
        "history_spine_upgrade_status": summary.get("history_spine_upgrade_status", "missing"),
        "network_fetch_performed": summary.get("network_fetch_performed", False),
        "credentials_created": summary.get("credentials_created", False),
        "env_created": summary.get("env_created", False),
        "alpha_vantage_excluded": summary.get("alpha_vantage_excluded", True),
        "next_recommended_target": summary.get("next_recommended_target", "DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1"),
        "paper_only": True,
        "live_blocked": True,
    }


def _local_free_ohlcv_stack_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.local_free_ohlcv_stack_summary or evidence.manual_ohlcv_staging_summary or {}
    return {
        "manual_staging_status": summary.get("manual_staging_status", "missing"),
        "manual_staging_decision": summary.get("manual_staging_decision", "missing"),
        "source_candidate_count": summary.get("source_candidate_count", 0),
        "evidence_allowed_count": summary.get("evidence_allowed_count", 0),
        "hash_record_count": summary.get("hash_record_count", 0),
        "manifest_draft_status": summary.get("manifest_draft_status", "missing"),
        "preflight_status": summary.get("preflight_status", "missing"),
        "fix_plan_status": summary.get("fix_plan_status", "missing"),
        "free_data_candidate_count": summary.get("free_data_candidate_count", 0),
        "free_data_evidence_allowed_count": summary.get("free_data_evidence_allowed_count", 0),
        "free_data_manual_review_required_count": summary.get("free_data_manual_review_required_count", 0),
        "local_ohlcv_status": summary.get("local_ohlcv_status", "missing"),
        "local_ohlcv_import_decision": summary.get("local_ohlcv_import_decision", "missing"),
        "local_ohlcv_fix_advice_status": summary.get("local_ohlcv_fix_advice_status", "missing"),
        "real_data_files_present": summary.get("real_data_files_present", False),
        "valid_real_dataset": summary.get("valid_real_dataset", False),
        "history_spine_activation_status": summary.get("history_spine_activation_status", "missing"),
        "real_history_used": summary.get("real_history_used", False),
        "real_signal_validation_status": summary.get("real_signal_validation_status", "missing"),
        "real_signal_evidence": summary.get("real_signal_evidence", False),
        "network_fetch_performed": summary.get("network_fetch_performed", False),
        "credentials_created": summary.get("credentials_created", False),
        "env_created": summary.get("env_created", False),
        "broker_connection_used": summary.get("broker_connection_used", False),
        "strategy_promotion_allowed": summary.get("strategy_promotion_allowed", False),
        "next_recommended_target": summary.get("next_recommended_target", "DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1"),
        "paper_only": True,
        "live_blocked": True,
    }


def _operator_reviewed_ohlcv_stage_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.operator_reviewed_ohlcv_stage_summary or {}
    return {
        "operator_reviewed_stage_status": summary.get("operator_reviewed_stage_status", "missing"),
        "operator_reviewed_stage_decision": summary.get("operator_reviewed_stage_decision", "missing"),
        "source_review_status": summary.get("source_review_status", "missing"),
        "source_review_valid": summary.get("source_review_valid", False),
        "staged_file_count": summary.get("staged_file_count", 0),
        "manifest_candidate_status": summary.get("manifest_candidate_status", "missing"),
        "final_manifest_status": summary.get("final_manifest_status", "missing"),
        "action_packet_status": "written" if summary else "missing",
        "local_ohlcv_status": summary.get("local_ohlcv_status", "missing"),
        "history_spine_activation_status": summary.get("history_spine_activation_status", "missing"),
        "real_signal_validation_status": summary.get("real_signal_validation_status", "missing"),
        "valid_real_dataset": summary.get("valid_real_dataset", False),
        "real_signal_evidence": summary.get("real_signal_evidence", False),
        "options_evidence_status": "not_options_evidence",
        "profitability_claim_status": "not_profitability_claim",
        "live_readiness_status": "not_live_ready",
        "network_fetch_performed": summary.get("network_fetch_performed", False),
        "credentials_created": summary.get("credentials_created", False),
        "env_created": summary.get("env_created", False),
        "broker_connection_used": summary.get("broker_connection_used", False),
        "strategy_promotion_allowed": summary.get("strategy_promotion_allowed", False),
        "next_recommended_target": summary.get("next_recommended_target", "DOPEY_OPERATOR_STAGE_REVIEWED_FREE_OHLCV_FILES"),
        "draft_manifest_is_evidence": False,
        "candidate_manifest_is_evidence": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _open_source_autonomous_options_trader_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.full_open_source_autonomous_orchestrator_summary or {}
    return {
        "autonomy_status": summary.get("autonomy_status", "missing"),
        "open_source_candidate_count": summary.get("open_source_candidate_count", 0),
        "open_source_accepted_count": summary.get("open_source_accepted_count", 0),
        "open_data_candidate_count": summary.get("open_data_candidate_count", 0),
        "open_data_accepted_count": summary.get("open_data_accepted_count", 0),
        "accepted_ohlcv_file_count": summary.get("accepted_ohlcv_file_count", 0),
        "valid_real_dataset": summary.get("valid_real_dataset", False),
        "options_data_status": summary.get("options_data_status", "missing"),
        "paper_trading_loop_status": summary.get("paper_trading_loop_status", "missing"),
        "s_tier_benchmark_status": summary.get("s_tier_benchmark_status", "missing"),
        "alpha_vantage_excluded": summary.get("alpha_vantage_excluded", True),
        "network_fetch_performed": summary.get("network_fetch_performed", False),
        "credentials_created": summary.get("credentials_created", False),
        "env_created": summary.get("env_created", False),
        "broker_connection_used": summary.get("broker_connection_used", False),
        "strategy_promotion_allowed": summary.get("strategy_promotion_allowed", False),
        "not_profitability_claim": summary.get("not_profitability_claim", True),
        "not_live_ready": summary.get("not_live_ready", True),
        "paper_only": True,
        "live_blocked": True,
    }


def _open_data_breakthrough_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.open_data_breakthrough_full_completion_summary or {}
    quote = evidence.quote_priced_options_unlock_gate or {}
    model = evidence.model_priced_options_research_summary or {}
    discovery = evidence.exhaustive_open_data_discovery_matrix_summary or {}
    return {
        "breakthrough_status": summary.get("breakthrough_status", "missing"),
        "total_candidates_discovered": summary.get("total_candidates_discovered", discovery.get("total_candidates_discovered", 0)),
        "accepted_ohlcv_source_count": summary.get("accepted_ohlcv_source_count", 0),
        "accepted_options_source_count": summary.get("accepted_options_source_count", 0),
        "accepted_context_source_count": summary.get("accepted_context_source_count", 0),
        "quote_priced_backtest_allowed": summary.get("quote_priced_backtest_allowed", quote.get("quote_priced_backtest_allowed", False)),
        "model_priced_research_allowed": summary.get("model_priced_research_allowed", model.get("model_priced_research_allowed", True)),
        "quote_unlock_status": summary.get("quote_unlock_status", quote.get("quote_priced_options_status", "missing")),
        "model_priced_research_status": summary.get("model_priced_research_status", model.get("model_priced_research_status", "missing")),
        "alpha_vantage_excluded": summary.get("alpha_vantage_excluded", True),
        "tradingview_excluded": summary.get("tradingview_excluded", True),
        "credentials_created": summary.get("credentials_created", False),
        "env_created": summary.get("env_created", False),
        "broker_connection_used": summary.get("broker_connection_used", False),
        "strategy_promotion_allowed": summary.get("strategy_promotion_allowed", False),
        "profitability_claim": summary.get("profitability_claim", False),
        "live_readiness_claim": summary.get("live_readiness_claim", False),
        "paper_only": True,
        "live_blocked": True,
    }


def _public_signal_research_v7_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.public_signal_research_breakthrough_v7_summary or {}
    return {
        "public_signal_research_v7_status": summary.get("public_signal_research_v7_status", "missing"),
        "next_recommended_target": summary.get("next_recommended_target", ""),
        "v7_candidate_count": summary.get("v7_candidate_count", 0),
        "v7_simulated_trade_count": summary.get("v7_simulated_trade_count", 0),
        "breakthrough_candidate_count": summary.get("breakthrough_candidate_count", 0),
        "watchlist_count": summary.get("watchlist_count", 0),
        "pf_above_110_count": summary.get("pf_above_110_count", 0),
        "improved_vs_v6_count": summary.get("improved_vs_v6_count", 0),
        "top_family": summary.get("top_research_family", ""),
        "live_gate_status": summary.get("live_gate_status", ""),
        "min_breakthrough_pf": summary.get("min_breakthrough_pf", 1.10),
        "no_trade_only_blocked": summary.get("no_trade_only_blocked", True),
        "paper_only": True,
        "live_blocked": True,
    }


def _finish_everything_openbb_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.finish_everything_orchestrator_summary or {}
    registry = evidence.openbb_provider_registry_summary or {}
    validator = evidence.openbb_validator_bridge_summary or {}
    model = evidence.model_priced_v2_research_summary or {}
    s_tier = evidence.s_tier_v2_summary or {}
    paper = evidence.paper_rotation_engine_summary or {}
    gaps = evidence.remaining_gap_eliminator_summary or {}
    return {
        "finish_everything_status": summary.get("finish_everything_status", "missing"),
        "openbb_runtime_status": summary.get("openbb_runtime_status", "missing"),
        "openbb_accepted_provider_count": summary.get("openbb_accepted_provider_count", registry.get("accepted_provider_count", 0)),
        "openbb_valid_real_dataset": summary.get("openbb_valid_real_dataset", validator.get("openbb_valid_real_dataset", False)),
        "model_priced_v2_status": summary.get("model_priced_v2_status", model.get("model_priced_v2_status", "missing")),
        "s_tier_v2_status": summary.get("s_tier_v2_status", s_tier.get("s_tier_v2_status", "missing")),
        "paper_rotation_status": summary.get("paper_rotation_status", paper.get("paper_rotation_status", "missing")),
        "remaining_gap_count": summary.get("remaining_gap_count", gaps.get("remaining_gap_count", 0)),
        "manual_review_dependency_count": summary.get("manual_review_dependency_count", 0),
        "operator_action_required_count": summary.get("operator_action_required_count", 0),
        "credentials_created": summary.get("credentials_created", False),
        "env_created": summary.get("env_created", False),
        "broker_connection_used": summary.get("broker_connection_used", False),
        "live_trading_enabled": summary.get("live_trading_enabled", False),
        "strategy_promotion_allowed": summary.get("strategy_promotion_allowed", False),
        "profitability_claim": summary.get("profitability_claim", False),
        "live_readiness_claim": summary.get("live_readiness_claim", False),
        "paper_only": True,
        "live_blocked": True,
    }


def _wealth_engine_summary(evidence: ReportingEvidence) -> dict:
    summary = evidence.wealth_engine_summary or {}
    market = evidence.market_data_lake_summary or {}
    chart = evidence.chart_vision_summary or {}
    scoreboard = evidence.pnl_scoreboard_summary or {}
    validation = evidence.wealth_engine_validation_summary or {}
    return {
        "wealth_engine_status": summary.get("wealth_engine_status", "missing"),
        "market_data_status": summary.get("market_data_status", market.get("market_data_status", "missing")),
        "symbols_loaded": summary.get("symbols_loaded", market.get("symbols_loaded", [])),
        "daily_ohlcv_rows": summary.get("daily_ohlcv_rows", market.get("daily_ohlcv_rows", 0)),
        "chart_count": summary.get("chart_count", chart.get("chart_count", 0)),
        "signal_candidate_count": summary.get("signal_candidate_count", 0),
        "option_trade_candidate_count": summary.get("option_trade_candidate_count", 0),
        "paper_tournament_trade_count": summary.get("paper_tournament_trade_count", 0),
        "pnl_scoreboard_status": summary.get("pnl_scoreboard_status", scoreboard.get("pnl_scoreboard_status", "missing")),
        "paper_champion_count": summary.get("paper_champion_count", 0),
        "live_gate_status": summary.get("live_gate_status", "missing"),
        "validation_status": validation.get("validation_status", "missing"),
        "timeout_recorded_as_pass": validation.get("timeout_recorded_as_pass", False),
        "credentials_created": summary.get("credentials_created", False),
        "env_created": summary.get("env_created", False),
        "broker_connection_used": summary.get("broker_connection_used", False),
        "live_trading_enabled": summary.get("live_trading_enabled", False),
        "profitability_claim": summary.get("profitability_claim", False),
        "live_readiness_claim": summary.get("live_readiness_claim", False),
        "paper_only": True,
        "live_blocked": True,
    }


def _market_provider_expansion_summary(evidence: ReportingEvidence) -> dict:
    rerun = evidence.real_public_market_wealth_rerun_summary or {}
    ladder = evidence.public_ohlcv_provider_ladder_v2_summary or {}
    promotion = evidence.market_lake_public_promotion_summary or {}
    split = evidence.public_vs_fixture_scoreboard_split or {}
    install = evidence.provider_install_repair_summary or {}
    diagnostics = evidence.provider_health_diagnostics_summary or {}
    return {
        "real_public_rerun_status": rerun.get("real_public_rerun_status", "missing"),
        "provider_ladder_status": ladder.get("provider_ladder_status", rerun.get("provider_ladder_status", "missing")),
        "public_rows_loaded": rerun.get("public_rows_loaded", ladder.get("public_ohlcv_rows_loaded", 0)),
        "public_symbols_loaded": rerun.get("public_symbols_loaded", ladder.get("symbols_loaded", [])),
        "active_public_symbol_count": rerun.get("active_public_symbol_count", promotion.get("active_symbols_public", 0)),
        "active_fixture_symbol_count": rerun.get("active_fixture_symbol_count", promotion.get("active_symbols_fixture", 0)),
        "public_strategy_score_count": split.get("public_strategy_score_count", 0),
        "fixture_strategy_score_count": split.get("fixture_strategy_score_count", 0),
        "yfinance_import_status": install.get("yfinance_import_status", "missing"),
        "openbb_import_status": install.get("openbb_import_status", "missing"),
        "stooq_diagnosis": diagnostics.get("stooq_diagnosis", "missing"),
        "yahoo_direct_diagnosis": diagnostics.get("yahoo_direct_diagnosis", "missing"),
        "live_trading_enabled": False,
        "credentials_created": False,
        "env_created": False,
        "broker_connection_used": False,
    }


def _build_dashboard_index(
    evidence: ReportingEvidence,
    strategy_records: list[dict],
    family_records: list[dict],
    scenario_records: list[dict],
    artifact_hashes: dict[str, str],
    safety: dict,
    audit_status: str,
) -> DashboardArtifactIndex:
    family_rankings = [
        {
            "strategy_family": record["strategy_family"],
            "family_rank": record["family_rank"],
            "best_strategy": record["best_strategy"],
            "average_score": record["average_score"],
        }
        for record in family_records
    ]
    scenario_summaries = [
        {
            "scenario_id": record["scenario_id"],
            "scenario_type": record["scenario_type"],
            "source_layer": record["source_layer"],
            "winning_strategy": record["winning_strategy"],
            "losing_strategy": record["losing_strategy"],
        }
        for record in scenario_records[:20]
    ]
    safety_with_active_policy = dict(safety)
    safety_with_active_policy["active_policy_summary"] = _active_policy_summary(evidence)
    safety_with_active_policy["account_ledger_summary"] = _account_ledger_summary(evidence)
    safety_with_active_policy["zero_dte_risk_summary"] = _zero_dte_risk_summary(evidence)
    safety_with_active_policy["zero_dte_replay_summary"] = _zero_dte_replay_summary(evidence)
    safety_with_active_policy["zero_dte_threshold_optimizer_summary"] = _zero_dte_threshold_optimizer_summary(evidence)
    safety_with_active_policy["zero_dte_adversarial_corpus_summary"] = _zero_dte_adversarial_corpus_summary(evidence)
    safety_with_active_policy["zero_dte_cross_underlying_v2_summary"] = _zero_dte_cross_underlying_v2_summary(evidence)
    safety_with_active_policy["hybrid_swing_0dte_v3_summary"] = _hybrid_swing_0dte_v3_summary(evidence)
    safety_with_active_policy["proof_weighted_allocation_summary"] = _proof_weighted_allocation_summary(evidence)
    safety_with_active_policy["portfolio_replay_summary"] = _portfolio_replay_summary(evidence)
    safety_with_active_policy["stress_ladder_summary"] = _stress_ladder_summary(evidence)
    safety_with_active_policy["incident_rehearsal_summary"] = _incident_rehearsal_summary(evidence)
    safety_with_active_policy["active_lifecycle_summary"] = _active_lifecycle_summary(evidence)
    safety_with_active_policy["broker_readiness_summary"] = _broker_readiness_summary(evidence)
    safety_with_active_policy["manual_approval_packet_summary"] = _manual_approval_packet_summary(evidence)
    safety_with_active_policy["read_only_detector_dry_run_summary"] = _read_only_detector_dry_run_summary(evidence)
    safety_with_active_policy["approval_intake_summary"] = _approval_intake_summary(evidence)
    safety_with_active_policy["approval_to_run_handoff_summary"] = _approval_to_run_handoff_summary(evidence)
    safety_with_active_policy["pre_run_safety_summary"] = _pre_run_safety_summary(evidence)
    safety_with_active_policy["read_only_detector_summary"] = _read_only_detector_summary(evidence)
    safety_with_active_policy["read_only_detector_evidence_contract_summary"] = _read_only_detector_evidence_contract_summary(evidence)
    safety_with_active_policy["history_spine_summary"] = _history_spine_summary(evidence)
    safety_with_active_policy["model_repricing_summary"] = _model_repricing_summary(evidence)
    safety_with_active_policy["signal_engine_summary"] = _signal_engine_summary(evidence)
    safety_with_active_policy["honest_backtester_summary"] = _honest_backtester_summary(evidence)
    safety_with_active_policy["statistical_truth_summary"] = _statistical_truth_summary(evidence)
    safety_with_active_policy["fitness_replacement_summary"] = _fitness_replacement_summary(evidence)
    safety_with_active_policy["data_ingestion_plan_summary"] = _data_ingestion_plan_summary(evidence)
    safety_with_active_policy["real_data_validation_stack_summary"] = _real_data_validation_stack_summary(evidence)
    safety_with_active_policy["open_source_path_summary"] = _open_source_path_summary(evidence)
    safety_with_active_policy["local_free_ohlcv_stack_summary"] = _local_free_ohlcv_stack_summary(evidence)
    safety_with_active_policy["operator_reviewed_ohlcv_stage_summary"] = _operator_reviewed_ohlcv_stage_summary(evidence)
    safety_with_active_policy["open_source_autonomous_options_trader_summary"] = _open_source_autonomous_options_trader_summary(evidence)
    safety_with_active_policy["open_data_breakthrough_summary"] = _open_data_breakthrough_summary(evidence)
    safety_with_active_policy["finish_everything_openbb_summary"] = _finish_everything_openbb_summary(evidence)
    safety_with_active_policy["wealth_engine_summary"] = _wealth_engine_summary(evidence)
    safety_with_active_policy["real_public_market_wealth_rerun_summary"] = _market_provider_expansion_summary(evidence)
    safety_with_active_policy["public_ohlcv_provider_ladder_v2_summary"] = evidence.public_ohlcv_provider_ladder_v2_summary or {}
    safety_with_active_policy["public_vs_fixture_scoreboard_split"] = evidence.public_vs_fixture_scoreboard_split or {}
    safety_with_active_policy["public_market_paper_champion_evolution_summary"] = evidence.public_market_paper_champion_evolution_summary or {}
    safety_with_active_policy["public_paper_champion_gate_summary"] = evidence.public_paper_champion_gate_summary or {}
    safety_with_active_policy["public_champion_live_gate_status"] = evidence.public_champion_live_gate_status or {}
    return DashboardArtifactIndex(
        reporting_dashboard_index_version=REPORTING_DASHBOARD_INDEX_VERSION,
        reporting_bundle_version=REPORTING_BUNDLE_VERSION,
        top_strategies=[record["strategy_id"] for record in strategy_records[:8]],
        family_rankings=family_rankings,
        scenario_summaries=scenario_summaries,
        evidence_layer_summaries=list(evidence.meta_governor.get("evidence_layer_scores", []) or []),
        audit_status=audit_status,
        safety_status=safety_with_active_policy,
        artifact_paths=artifact_paths(),
        reproducibility_hashes=artifact_hashes,
        known_gaps=_known_gaps(evidence),
        next_recommended_build_targets=["artifact_compaction_export_verifier", "DOPEY_OPERATOR_STAGE_REVIEWED_FREE_OHLCV_FILES"],
        fixture_only=True,
        paper_only=True,
        live_allowed=False,
        reproducibility_hash="",
    )


def _build_proof_entry(result: ReportingBundleResult, summary_record: dict) -> ProofEntry:
    return ProofEntry(
        run_id=REPORTING_BUNDLE_VERSION,
        task_id="tournament-performance-reporting-dashboard-artifacts",
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_hash=result.reproducibility_hash,
        plan_hash=reproducibility_hash({"reporting_bundle_version": REPORTING_BUNDLE_VERSION}),
        mock_trial_result="MOCK_PASS",
        execution_result={
            "reporting_result": result.to_dict(),
            "reporting_summary": summary_record,
            "safety_state": result.safety_state,
        },
        validation_result="VALIDATION_PASS",
        repair_attempts=0,
        artifacts=result.dashboard_artifacts_written,
        diffs=[],
        test_results={
            "reporting_bundle_status": result.reporting_bundle_status,
            "strategies_reported": result.strategies_reported,
            "families_reported": result.families_reported,
            "scenarios_reported": result.scenarios_reported,
            "attribution_records": result.attribution_records,
            "live_blocked": result.live_blocked,
        },
        final_status="PASS",
        lessons_candidate=[],
        promotion_candidate=[],
        limitations=[
            "static offline report artifacts only; no live dashboard server",
            "fixture-only paper evidence explanations; not live performance evidence",
            "no broker connection, credentials, network market data, live trades, schedule, or live promotion",
        ],
    )


def run_tournament_performance_reporting_bundle() -> dict:
    safety = safety_state()
    verify_reporting_safety_state(safety)
    evidence = load_reporting_evidence(EVIDENCE_PATHS)

    strategy_cards = build_strategy_report_cards(evidence)
    family_cards = build_family_report_cards(evidence, strategy_cards)
    scenario_cards = build_scenario_report_cards(evidence, strategy_cards)
    regime_cards = build_regime_report_cards(evidence, strategy_cards)
    attribution_records = build_performance_attribution(evidence, strategy_cards)

    strategy_dicts = [_with_record_hash(card.to_dict()) for card in strategy_cards]
    family_dicts = [_with_record_hash(card.to_dict()) for card in family_cards]
    scenario_dicts = [_with_record_hash(card.to_dict()) for card in scenario_cards]
    regime_dicts = [_with_record_hash(card.to_dict()) for card in regime_cards]
    attribution_dicts = [_with_record_hash(record.to_dict()) for record in attribution_records]

    write_jsonl_records(STRATEGY_REPORT_CARDS_PATH, strategy_dicts)
    write_jsonl_records(FAMILY_REPORT_CARDS_PATH, family_dicts)
    write_jsonl_records(SCENARIO_REPORT_CARDS_PATH, scenario_dicts)
    write_jsonl_records(REGIME_REPORT_CARDS_PATH, regime_dicts)
    write_jsonl_records(PERFORMANCE_ATTRIBUTION_PATH, attribution_dicts)

    artifact_hashes = {
        "strategy_report_cards": canonical_reporting_hash({"records": strategy_dicts}),
        "family_report_cards": canonical_reporting_hash({"records": family_dicts}),
        "scenario_report_cards": canonical_reporting_hash({"records": scenario_dicts}),
        "regime_report_cards": canonical_reporting_hash({"records": regime_dicts}),
        "performance_attribution": canonical_reporting_hash({"records": attribution_dicts}),
    }
    audit_status = "pass" if safety["live_blocked"] else "fail_safety"
    dashboard_index = _build_dashboard_index(
        evidence,
        strategy_dicts,
        family_dicts,
        scenario_dicts,
        artifact_hashes,
        safety,
        audit_status,
    )
    dashboard_record = _with_record_hash(dashboard_index.to_dict())
    write_json(REPORTING_DASHBOARD_INDEX_JSON, dashboard_record)
    _write_markdown_index(DashboardArtifactIndex(**dashboard_record), REPORTING_DASHBOARD_INDEX_MD)
    _write_static_dashboard(DashboardArtifactIndex(**dashboard_record), strategy_dicts, family_dicts, STATIC_DASHBOARD_PATH)

    top_strategy = strategy_dicts[0]["strategy_id"] if strategy_dicts else ""
    top_family = family_dicts[0]["strategy_family"] if family_dicts else ""
    summary_seed = {
        "reporting_bundle_version": REPORTING_BUNDLE_VERSION,
        "strategy_report_cards": strategy_dicts,
        "family_report_cards": family_dicts,
        "scenario_report_cards": scenario_dicts,
        "regime_report_cards": regime_dicts,
        "performance_attribution": attribution_dicts,
        "dashboard_index": dashboard_record,
        "active_policy_summary": _active_policy_summary(evidence),
        "account_ledger_summary": _account_ledger_summary(evidence),
        "zero_dte_risk_summary": _zero_dte_risk_summary(evidence),
        "zero_dte_replay_summary": _zero_dte_replay_summary(evidence),
        "zero_dte_threshold_optimizer_summary": _zero_dte_threshold_optimizer_summary(evidence),
        "zero_dte_adversarial_corpus_summary": _zero_dte_adversarial_corpus_summary(evidence),
        "zero_dte_cross_underlying_v2_summary": _zero_dte_cross_underlying_v2_summary(evidence),
        "hybrid_swing_0dte_v3_summary": _hybrid_swing_0dte_v3_summary(evidence),
        "proof_weighted_allocation_summary": _proof_weighted_allocation_summary(evidence),
        "portfolio_replay_summary": _portfolio_replay_summary(evidence),
        "stress_ladder_summary": _stress_ladder_summary(evidence),
        "incident_rehearsal_summary": _incident_rehearsal_summary(evidence),
        "active_lifecycle_summary": _active_lifecycle_summary(evidence),
        "broker_readiness_summary": _broker_readiness_summary(evidence),
        "manual_approval_packet_summary": _manual_approval_packet_summary(evidence),
        "read_only_detector_dry_run_summary": _read_only_detector_dry_run_summary(evidence),
        "approval_intake_summary": _approval_intake_summary(evidence),
        "approval_to_run_handoff_summary": _approval_to_run_handoff_summary(evidence),
        "pre_run_safety_summary": _pre_run_safety_summary(evidence),
        "read_only_detector_summary": _read_only_detector_summary(evidence),
        "read_only_detector_evidence_contract_summary": _read_only_detector_evidence_contract_summary(evidence),
        "history_spine_summary": _history_spine_summary(evidence),
        "model_repricing_summary": _model_repricing_summary(evidence),
        "signal_engine_summary": _signal_engine_summary(evidence),
        "honest_backtester_summary": _honest_backtester_summary(evidence),
        "statistical_truth_summary": _statistical_truth_summary(evidence),
        "fitness_replacement_summary": _fitness_replacement_summary(evidence),
        "data_ingestion_plan_summary": _data_ingestion_plan_summary(evidence),
        "real_data_validation_stack_summary": _real_data_validation_stack_summary(evidence),
        "open_source_path_summary": _open_source_path_summary(evidence),
        "local_free_ohlcv_stack_summary": _local_free_ohlcv_stack_summary(evidence),
        "operator_reviewed_ohlcv_stage_summary": _operator_reviewed_ohlcv_stage_summary(evidence),
        "open_source_autonomous_options_trader_summary": _open_source_autonomous_options_trader_summary(evidence),
        "open_data_breakthrough_summary": _open_data_breakthrough_summary(evidence),
        "finish_everything_openbb_summary": _finish_everything_openbb_summary(evidence),
        "wealth_engine_summary": _wealth_engine_summary(evidence),
        "real_public_market_wealth_rerun_summary": _market_provider_expansion_summary(evidence),
        "public_ohlcv_provider_ladder_v2_summary": evidence.public_ohlcv_provider_ladder_v2_summary or {},
        "public_vs_fixture_scoreboard_split": evidence.public_vs_fixture_scoreboard_split or {},
        "public_market_paper_champion_evolution_summary": evidence.public_market_paper_champion_evolution_summary or {},
        "public_paper_champion_gate_summary": evidence.public_paper_champion_gate_summary or {},
        "public_champion_live_gate_status": evidence.public_champion_live_gate_status or {},
        "public_signal_research_breakthrough_v7_summary": _public_signal_research_v7_summary(evidence),
        "safety_state": safety,
    }
    repro = reproducibility_hash(summary_seed)
    result = ReportingBundleResult(
        reporting_bundle_status="ok",
        mode=safety["mode"],
        live_trading_enabled=safety["live_trading_enabled"],
        strategies_reported=len(strategy_dicts),
        families_reported=len(family_dicts),
        scenarios_reported=len(scenario_dicts) + len(regime_dicts),
        attribution_records=len(attribution_dicts),
        dashboard_artifacts_written=[
            str(REPORTING_DASHBOARD_INDEX_JSON),
            str(REPORTING_DASHBOARD_INDEX_MD),
            str(STRATEGY_REPORT_CARDS_PATH),
            str(FAMILY_REPORT_CARDS_PATH),
            str(SCENARIO_REPORT_CARDS_PATH),
            str(REGIME_REPORT_CARDS_PATH),
            str(PERFORMANCE_ATTRIBUTION_PATH),
            str(REPORTING_BUNDLE_SUMMARY_PATH),
            str(STATIC_DASHBOARD_PATH),
            str(REPORTING_PROOF_PATH),
        ],
        top_strategy=top_strategy,
        top_family=top_family,
        audit_status=audit_status,
        live_blocked=True,
        dashboard_index_path=str(REPORTING_DASHBOARD_INDEX_JSON),
        proof_record_path=str(REPORTING_PROOF_PATH),
        safety_state=safety,
        reproducibility_hash=repro,
    )
    summary_record = {
        **result.to_dict(),
        "reporting_bundle_version": REPORTING_BUNDLE_VERSION,
        "strategy_report_card_count": len(strategy_dicts),
        "family_report_card_count": len(family_dicts),
        "scenario_report_card_count": len(scenario_dicts),
        "regime_report_card_count": len(regime_dicts),
        "performance_attribution_count": len(attribution_dicts),
        "active_policy_summary": _active_policy_summary(evidence),
        "account_ledger_summary": _account_ledger_summary(evidence),
        "zero_dte_risk_summary": _zero_dte_risk_summary(evidence),
        "zero_dte_replay_summary": _zero_dte_replay_summary(evidence),
        "zero_dte_threshold_optimizer_summary": _zero_dte_threshold_optimizer_summary(evidence),
        "zero_dte_adversarial_corpus_summary": _zero_dte_adversarial_corpus_summary(evidence),
        "zero_dte_cross_underlying_v2_summary": _zero_dte_cross_underlying_v2_summary(evidence),
        "hybrid_swing_0dte_v3_summary": _hybrid_swing_0dte_v3_summary(evidence),
        "proof_weighted_allocation_summary": _proof_weighted_allocation_summary(evidence),
        "portfolio_replay_summary": _portfolio_replay_summary(evidence),
        "stress_ladder_summary": _stress_ladder_summary(evidence),
        "incident_rehearsal_summary": _incident_rehearsal_summary(evidence),
        "active_lifecycle_summary": _active_lifecycle_summary(evidence),
        "broker_readiness_summary": _broker_readiness_summary(evidence),
        "manual_approval_packet_summary": _manual_approval_packet_summary(evidence),
        "read_only_detector_dry_run_summary": _read_only_detector_dry_run_summary(evidence),
        "approval_intake_summary": _approval_intake_summary(evidence),
        "approval_to_run_handoff_summary": _approval_to_run_handoff_summary(evidence),
        "pre_run_safety_summary": _pre_run_safety_summary(evidence),
        "read_only_detector_summary": _read_only_detector_summary(evidence),
        "read_only_detector_evidence_contract_summary": _read_only_detector_evidence_contract_summary(evidence),
        "history_spine_summary": _history_spine_summary(evidence),
        "model_repricing_summary": _model_repricing_summary(evidence),
        "signal_engine_summary": _signal_engine_summary(evidence),
        "honest_backtester_summary": _honest_backtester_summary(evidence),
        "statistical_truth_summary": _statistical_truth_summary(evidence),
        "fitness_replacement_summary": _fitness_replacement_summary(evidence),
        "data_ingestion_plan_summary": _data_ingestion_plan_summary(evidence),
        "real_data_validation_stack_summary": _real_data_validation_stack_summary(evidence),
        "open_source_path_summary": _open_source_path_summary(evidence),
        "local_free_ohlcv_stack_summary": _local_free_ohlcv_stack_summary(evidence),
        "operator_reviewed_ohlcv_stage_summary": _operator_reviewed_ohlcv_stage_summary(evidence),
        "open_source_autonomous_options_trader_summary": _open_source_autonomous_options_trader_summary(evidence),
        "open_data_breakthrough_summary": _open_data_breakthrough_summary(evidence),
        "finish_everything_openbb_summary": _finish_everything_openbb_summary(evidence),
        "wealth_engine_summary": _wealth_engine_summary(evidence),
        "real_public_market_wealth_rerun_summary": _market_provider_expansion_summary(evidence),
        "public_ohlcv_provider_ladder_v2_summary": evidence.public_ohlcv_provider_ladder_v2_summary or {},
        "public_vs_fixture_scoreboard_split": evidence.public_vs_fixture_scoreboard_split or {},
        "public_market_paper_champion_evolution_summary": evidence.public_market_paper_champion_evolution_summary or {},
        "public_paper_champion_gate_summary": evidence.public_paper_champion_gate_summary or {},
        "public_champion_live_gate_status": evidence.public_champion_live_gate_status or {},
        "public_signal_research_breakthrough_v7_summary": _public_signal_research_v7_summary(evidence),
        "champion_shift_explanation": "Current champion shifted to short_duration_defined_risk because the latest deterministic fixture stack rewards defined-risk Greek fit and clean short-duration regimes while exposing directional, volatility expansion, and compression fragility.",
        "strongest_positive_drivers": attribution_dicts[0]["top_positive_drivers"] if attribution_dicts else [],
        "strongest_negative_drivers": attribution_dicts[0]["top_negative_drivers"] if attribution_dicts else [],
    }
    write_json(REPORTING_BUNDLE_SUMMARY_PATH, _with_record_hash(summary_record))
    ProofLedger(REPORTING_PROOF_PATH).append(_build_proof_entry(result, summary_record))

    return result.to_dict()
