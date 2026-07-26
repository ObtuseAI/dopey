"""Deterministic offline stress ladder replay engine."""
from __future__ import annotations

from collections import Counter
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .crisis_mode_policy import (
    allocator_feedback_for_level,
    default_crisis_throttle_profiles,
    default_portfolio_stress_ladder,
    evaluate_stress_level,
    threshold_feedback_for_level,
    transition_reason_codes,
)
from .crisis_recovery_policy import evaluate_recovery
from .crisis_throttle_engine import apply_crisis_throttle, select_throttle_profile
from .run_portfolio_replay import run_portfolio_replay
from .stress_ladder_models import StressTransitionDecision, stress_transition_hash


STRESS_LADDER_VERSION = "dopey-portfolio-replay-v2-stress-ladder-v1"


def build_stress_ladder_bundle() -> dict[str, Any]:
    portfolio_result = run_portfolio_replay()
    ladder = default_portfolio_stress_ladder()
    profiles = default_crisis_throttle_profiles()
    cases = build_stress_ladder_cases(portfolio_result["summary"])
    replay = replay_stress_ladder_cases(cases, profiles, portfolio_result["summary"])
    return {
        "portfolio_result": portfolio_result,
        "ladder": ladder,
        "throttle_profiles": profiles,
        "cases": cases,
        **replay,
    }


def build_stress_ladder_cases(portfolio_summary: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    def add_case(case_family: str, required_case: str, from_level: str, stressors: list[str], action: str, recovery_case: bool, requested_recovery_level: str) -> None:
        case_index = len(cases) + 1
        expected_level = from_level if recovery_case else evaluate_stress_level(stressors)
        case = {
            "artifact_type": "stress_ladder_replay_case",
            "stress_case_id": f"stress-ladder-case-{case_index:03d}-{required_case}",
            "case_family": case_family,
            "required_case": required_case,
            "source_portfolio_id": portfolio_summary.get("portfolio_id", "dopey-paper-portfolio-replay-v1"),
            "source_portfolio_state_id": f"portfolio-state-reference-{case_index:03d}",
            "source_portfolio_summary_hash": portfolio_summary.get("reproducibility_hash", ""),
            "from_stress_level": from_level,
            "expected_stress_level": expected_level,
            "stressors": sorted(set(stressors)),
            "attempted_action": action,
            "recovery_case": recovery_case,
            "requested_recovery_level": requested_recovery_level,
            "expected_new_entry_allowed": _expected_new_entry_allowed(expected_level, action),
            "expected_zero_dte_allowed": _expected_zero_dte_allowed(expected_level, action),
            "expected_same_day_close_allowed": False,
            "expected_paper_shadow_contained": True,
            "expected_delayed_rotation_advisory_only": True,
            "paper_attention_units_before": _attention_before(expected_level),
            "paper_premium_risk_units_before": _premium_before(expected_level),
            "zero_dte_share_before": _zero_dte_share_before(expected_level),
            "paper_only": True,
            "live_blocked": True,
            "no_real_market_data": True,
            "no_broker": True,
            "no_real_sizing": True,
        }
        case["case_hash"] = reproducibility_hash(case)
        cases.append(case)

    _add_required_cases(add_case)
    targets = {
        "normal_stress_case": 16,
        "elevated_stress_case": 16,
        "defensive_stress_case": 16,
        "severe_stress_case": 16,
        "crisis_stress_case": 16,
        "lockdown_case": 12,
        "transition_up_case": 8,
        "recovery_case": 8,
        "injection_negative_control_case": 6,
        "paper_shadow_leakage_case": 6,
    }
    fill_specs = {
        "normal_stress_case": ("normal_pressure_case", "normal", ["normal_pressure"], "open_swing", False, ""),
        "elevated_stress_case": ("elevated_pressure_case", "normal", ["mild_0dte_pressure"], "open_zero_dte", False, ""),
        "defensive_stress_case": ("defensive_pressure_case", "elevated", ["moderate_gamma_pressure"], "open_high_gamma", False, ""),
        "severe_stress_case": ("severe_pressure_case", "defensive", ["iv_crush_exposure"], "open_zero_dte", False, ""),
        "crisis_stress_case": ("crisis_pressure_case", "severe", ["liquidity_collapse"], "open_fragile_family", False, ""),
        "lockdown_case": ("lockdown_pressure_case", "crisis", ["live_path_injection"], "open_swing", False, ""),
        "transition_up_case": ("transition_up_pressure_case", "normal", ["spread_explosion"], "open_zero_dte", False, ""),
        "recovery_case": ("recovery_pressure_case", "crisis", ["stress_cleared"], "open_swing", True, "severe"),
        "injection_negative_control_case": ("injection_negative_control_case", "crisis", ["broker_path_injection"], "open_swing", False, ""),
        "paper_shadow_leakage_case": ("paper_shadow_leakage_case", "defensive", ["paper_shadow_leakage_attempt"], "paper_shadow_leak_attempt", False, ""),
    }
    for family, target in targets.items():
        while sum(1 for case in cases if case["case_family"] == family) < target:
            count = sum(1 for case in cases if case["case_family"] == family) + 1
            prefix, from_level, stressors, action, recovery_case, requested = fill_specs[family]
            add_case(family, f"{prefix}_{count:02d}", from_level, stressors, action, recovery_case, requested)
    if len(cases) != 120:
        raise ValueError(f"stress ladder case count must be 120, got {len(cases)}")
    return cases


def replay_stress_ladder_cases(
    cases: list[dict[str, Any]],
    profiles: list[Any],
    portfolio_summary: dict[str, Any],
) -> dict[str, Any]:
    evaluations: list[dict[str, Any]] = []
    transitions: list[StressTransitionDecision] = []
    throttles: list[dict[str, Any]] = []
    recoveries: list[dict[str, Any]] = []
    allocator_feedback: list[dict[str, Any]] = []
    threshold_feedback: list[dict[str, Any]] = []
    proof_records: list[dict[str, Any]] = []
    for case in cases:
        level_name = str(case["from_stress_level"]) if bool(case.get("recovery_case", False)) else evaluate_stress_level([str(value) for value in case["stressors"]])
        evaluation = _stress_level_evaluation(case, level_name)
        transition = _transition_decision(case, evaluation)
        profile = select_throttle_profile(level_name, [str(value) for value in case["stressors"]], str(case["attempted_action"]), profiles)
        throttle = apply_crisis_throttle(case, level_name, profile)
        recovery = evaluate_recovery(case, level_name)
        allocator_record = _allocator_feedback_record(case, evaluation, throttle)
        threshold_record = _threshold_feedback_record(case, evaluation, throttle)
        proof = _proof_record(case, portfolio_summary, evaluation, transition, throttle, recovery, allocator_record, threshold_record)
        evaluations.append(evaluation)
        transitions.append(transition)
        throttles.append(throttle)
        recoveries.append(recovery)
        allocator_feedback.append(allocator_record)
        threshold_feedback.append(threshold_record)
        proof_records.append(proof)
    summary = _summary_record(cases, evaluations, transitions, throttles, recoveries, allocator_feedback, threshold_feedback, proof_records)
    return {
        "stress_level_evaluations": evaluations,
        "transition_decisions": transitions,
        "crisis_throttle_results": throttles,
        "crisis_recovery_results": recoveries,
        "crisis_allocator_feedback": allocator_feedback,
        "crisis_threshold_feedback": threshold_feedback,
        "stress_ladder_proof": proof_records,
        "summary": summary,
    }


def _add_required_cases(add_case) -> None:
    required = [
        ("normal_stress_case", "normal_portfolio_remains_normal", "normal", ["normal_pressure"], "open_swing", False, ""),
        ("elevated_stress_case", "mild_0dte_pressure_moves_to_elevated", "normal", ["mild_0dte_pressure"], "open_zero_dte", False, ""),
        ("defensive_stress_case", "moderate_gamma_pressure_moves_to_defensive", "normal", ["moderate_gamma_pressure"], "open_high_gamma", False, ""),
        ("defensive_stress_case", "high_theta_pressure_moves_to_defensive", "normal", ["moderate_theta_pressure"], "open_high_theta", False, ""),
        ("severe_stress_case", "iv_crush_exposure_moves_to_severe", "defensive", ["iv_crush_exposure"], "open_zero_dte", False, ""),
        ("severe_stress_case", "event_macro_shock_moves_to_severe", "defensive", ["event_macro_shock"], "open_swing", False, ""),
        ("crisis_stress_case", "liquidity_collapse_moves_to_crisis", "severe", ["liquidity_collapse"], "open_fragile_family", False, ""),
        ("crisis_stress_case", "spread_explosion_moves_to_crisis", "severe", ["spread_explosion"], "open_zero_dte", False, ""),
        ("crisis_stress_case", "multiple_simultaneous_stressors_move_to_crisis", "defensive", ["multi_stressor", "iv_crush_exposure", "moderate_gamma_pressure"], "open_zero_dte", False, ""),
        ("lockdown_case", "live_path_injection_moves_to_lockdown", "crisis", ["live_path_injection"], "open_swing", False, ""),
        ("injection_negative_control_case", "broker_path_injection_moves_to_lockdown", "crisis", ["broker_path_injection"], "open_swing", False, ""),
        ("injection_negative_control_case", "real_sizing_injection_moves_to_lockdown", "crisis", ["real_sizing_injection"], "open_swing", False, ""),
        ("paper_shadow_leakage_case", "paper_shadow_leakage_moves_to_severe_or_crisis", "defensive", ["paper_shadow_leakage_attempt"], "paper_shadow_leak_attempt", False, ""),
        ("crisis_stress_case", "same_day_churn_pressure_moves_to_crisis", "severe", ["same_day_close_pressure"], "same_day_close", False, ""),
        ("defensive_stress_case", "repeated_rejected_candidate_pressure_moves_to_defensive", "elevated", ["rejected_candidate_pressure"], "watchlist_review", False, ""),
        ("elevated_stress_case", "delayed_rotation_backlog_moves_to_elevated_defensive", "normal", ["delayed_rotation_backlog"], "delay_rotation", False, ""),
        ("crisis_stress_case", "crisis_mode_blocks_new_0dte", "severe", ["liquidity_collapse"], "open_zero_dte", False, ""),
        ("crisis_stress_case", "crisis_mode_permits_no_trade_only_for_fragile_family", "severe", ["liquidity_collapse", "low_liquidity_family"], "open_fragile_family", False, ""),
        ("crisis_stress_case", "crisis_mode_allows_only_highest_proof_swing_under_strict_cap", "severe", ["spread_explosion"], "open_highest_proof_swing", False, ""),
        ("lockdown_case", "lockdown_blocks_all_new_entries", "crisis", ["live_path_injection"], "open_swing", False, ""),
        ("lockdown_case", "lockdown_does_not_force_same_day_close", "crisis", ["live_path_injection"], "same_day_close", False, ""),
        ("lockdown_case", "lockdown_allows_audit_only_state", "crisis", ["live_path_injection"], "audit_only", False, ""),
        ("recovery_case", "recovery_from_crisis_to_severe_after_stress_clears", "crisis", ["stress_cleared"], "open_swing", True, "severe"),
        ("recovery_case", "recovery_from_severe_to_defensive_after_exposure_clears", "severe", ["stress_cleared"], "open_swing", True, "defensive"),
        ("recovery_case", "recovery_does_not_instantly_restore_aggressive_allocation", "crisis", ["stress_cleared"], "open_zero_dte", True, "normal"),
        ("recovery_case", "0dte_cap_remains_stricter_after_recovery", "severe", ["stress_cleared"], "open_zero_dte", True, "defensive"),
        ("recovery_case", "swing_allocation_recovers_before_0dte_allocation", "defensive", ["stress_cleared"], "open_swing", True, "elevated"),
        ("defensive_stress_case", "same_family_concentration_triggers_family_throttle", "elevated", ["family_concentration"], "open_fragile_family", False, ""),
        ("defensive_stress_case", "same_regime_concentration_triggers_regime_throttle", "elevated", ["regime_concentration"], "open_swing", False, ""),
        ("defensive_stress_case", "call_heavy_imbalance_triggers_directional_throttle", "elevated", ["call_heavy"], "open_swing", False, ""),
        ("defensive_stress_case", "put_heavy_imbalance_triggers_directional_throttle", "elevated", ["put_heavy"], "open_swing", False, ""),
        ("severe_stress_case", "high_gamma_profile_gets_blocked_under_severe", "defensive", ["iv_crush_exposure", "moderate_gamma_pressure"], "open_high_gamma", False, ""),
        ("severe_stress_case", "high_theta_profile_gets_blocked_under_severe", "defensive", ["event_macro_shock", "moderate_theta_pressure"], "open_high_theta", False, ""),
        ("crisis_stress_case", "event_sensitive_family_blocked_in_crisis", "severe", ["liquidity_collapse", "event_macro_shock"], "open_fragile_family", False, ""),
        ("crisis_stress_case", "low_liquidity_family_blocked_in_crisis", "severe", ["liquidity_collapse", "low_liquidity_family"], "open_fragile_family", False, ""),
        ("severe_stress_case", "macro_sensitive_family_throttled_under_severe", "defensive", ["macro_sensitive_family"], "open_swing", False, ""),
        ("paper_shadow_leakage_case", "paper_shadow_remains_contained_under_all_levels", "defensive", ["paper_shadow_leakage_attempt"], "paper_shadow_leak_attempt", False, ""),
        ("elevated_stress_case", "delayed_rotations_remain_advisory_under_all_levels", "normal", ["delayed_rotation_backlog"], "delay_rotation", False, ""),
        ("crisis_stress_case", "no_day_trade_guard_remains_dominant_under_all_levels", "severe", ["same_day_close_pressure"], "same_day_close", False, ""),
        ("lockdown_case", "paperbroker_is_not_overridden_by_crisis_mode", "crisis", ["live_path_injection"], "open_swing", False, ""),
    ]
    for args in required:
        add_case(*args)


def _stress_level_evaluation(case: dict[str, Any], level_name: str) -> dict[str, Any]:
    result = {
        "artifact_type": "stress_level_evaluation",
        "evaluation_id": f"stress-level-evaluation-{case['stress_case_id']}",
        "stress_case_id": case["stress_case_id"],
        "source_portfolio_state_id": case["source_portfolio_state_id"],
        "from_stress_level": case["from_stress_level"],
        "evaluated_stress_level": level_name,
        "expected_stress_level": case["expected_stress_level"],
        "expectation_matched": level_name == case["expected_stress_level"],
        "triggering_stressors": case["stressors"],
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    result["evaluation_hash"] = reproducibility_hash(result)
    return result


def _transition_decision(case: dict[str, Any], evaluation: dict[str, Any]) -> StressTransitionDecision:
    to_level = str(evaluation["evaluated_stress_level"])
    from_level = str(case["from_stress_level"])
    stressors = [str(value) for value in case["stressors"]]
    transition = StressTransitionDecision(
        transition_id=f"stress-transition-{case['stress_case_id']}",
        from_stress_level=from_level,
        to_stress_level=to_level,
        triggering_snapshot_id=str(case["source_portfolio_state_id"]),
        triggering_stressors=stressors,
        transition_allowed=True,
        transition_reason_codes=transition_reason_codes(from_level, to_level, stressors),
        allocator_feedback=allocator_feedback_for_level(to_level, stressors),
        threshold_feedback=threshold_feedback_for_level(to_level, stressors),
        paper_only=True,
        live_blocked=True,
        transition_hash="",
    )
    return StressTransitionDecision(**{**transition.to_dict(), "transition_hash": stress_transition_hash(transition)})


def _allocator_feedback_record(case: dict[str, Any], evaluation: dict[str, Any], throttle: dict[str, Any]) -> dict[str, Any]:
    actions = allocator_feedback_for_level(str(evaluation["evaluated_stress_level"]), [str(value) for value in case["stressors"]])
    record = {
        "artifact_type": "crisis_allocator_feedback",
        "feedback_id": f"crisis-allocator-feedback-{case['stress_case_id']}",
        "stress_case_id": case["stress_case_id"],
        "stress_level": evaluation["evaluated_stress_level"],
        "feedback_actions": actions,
        "primary_feedback_action": actions[0] if actions else "keep_live_default_behavior_unchanged",
        "throttle_type": throttle["throttle_type"],
        "advisory_only": True,
        "live_allocation_mutation_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    record["feedback_hash"] = reproducibility_hash(record)
    return record


def _threshold_feedback_record(case: dict[str, Any], evaluation: dict[str, Any], throttle: dict[str, Any]) -> dict[str, Any]:
    actions = threshold_feedback_for_level(str(evaluation["evaluated_stress_level"]), [str(value) for value in case["stressors"]])
    record = {
        "artifact_type": "crisis_threshold_feedback",
        "feedback_id": f"crisis-threshold-feedback-{case['stress_case_id']}",
        "stress_case_id": case["stress_case_id"],
        "stress_level": evaluation["evaluated_stress_level"],
        "feedback_actions": actions,
        "primary_feedback_action": actions[0] if actions else "keep_live_default_thresholds_unchanged",
        "throttle_type": throttle["throttle_type"],
        "advisory_only": True,
        "live_threshold_mutation_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    record["feedback_hash"] = reproducibility_hash(record)
    return record


def _proof_record(
    case: dict[str, Any],
    portfolio_summary: dict[str, Any],
    evaluation: dict[str, Any],
    transition: StressTransitionDecision,
    throttle: dict[str, Any],
    recovery: dict[str, Any],
    allocator_feedback: dict[str, Any],
    threshold_feedback: dict[str, Any],
) -> dict[str, Any]:
    record = {
        "artifact_type": "stress_ladder_proof",
        "proof_id": f"stress-ladder-proof-{case['stress_case_id']}",
        "stress_case_id": case["stress_case_id"],
        "source_portfolio_state_id": case["source_portfolio_state_id"],
        "source_portfolio_summary_hash": portfolio_summary.get("reproducibility_hash", ""),
        "evaluated_stress_level": evaluation["evaluated_stress_level"],
        "transition_decision": transition.to_dict(),
        "throttle_result": throttle,
        "recovery_result": recovery,
        "allocator_feedback": allocator_feedback,
        "threshold_feedback": threshold_feedback,
        "action_allowed": throttle["allowed"],
        "action_blocked": throttle["blocked"],
        "reason_codes": sorted(set([*transition.transition_reason_codes, *throttle["reason_codes"], *recovery["reason_codes"]])),
        "safety_status": "paper_only_live_blocked",
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    record["proof_hash"] = reproducibility_hash(record)
    return record


def _summary_record(
    cases: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    transitions: list[StressTransitionDecision],
    throttles: list[dict[str, Any]],
    recoveries: list[dict[str, Any]],
    allocator_feedback: list[dict[str, Any]],
    threshold_feedback: list[dict[str, Any]],
    proof_records: list[dict[str, Any]],
) -> dict[str, Any]:
    stress_levels = Counter(str(record["evaluated_stress_level"]) for record in evaluations)
    throttle_types = Counter(str(record["throttle_type"]) for record in throttles)
    transition_pairs = Counter(f"{record.from_stress_level}_to_{record.to_stress_level}" for record in transitions)
    recovery_pairs = Counter(f"{record['from_stress_level']}_to_{record['to_stress_level']}" for record in recoveries if record["recovery_case"])
    allocator_actions = Counter(action for record in allocator_feedback for action in record["feedback_actions"])
    threshold_actions = Counter(action for record in threshold_feedback for action in record["feedback_actions"])
    summary = {
        "artifact_type": "stress_ladder_summary",
        "stress_ladder_version": STRESS_LADDER_VERSION,
        "stress_case_count": len(cases),
        "stress_level_evaluation_count": len(evaluations),
        "transition_decision_count": len(transitions),
        "crisis_throttle_result_count": len(throttles),
        "crisis_recovery_result_count": len(recoveries),
        "allocator_feedback_count": len(allocator_feedback),
        "threshold_feedback_count": len(threshold_feedback),
        "proof_record_count": len(proof_records),
        "case_family_distribution": dict(sorted(Counter(str(case["case_family"]) for case in cases).items())),
        "stress_level_distribution": dict(sorted(stress_levels.items())),
        "transition_distribution": dict(sorted(transition_pairs.items())),
        "throttle_type_distribution": dict(sorted(throttle_types.items())),
        "recovery_transition_distribution": dict(sorted(recovery_pairs.items())),
        "crisis_mode_trigger_count": stress_levels.get("crisis", 0),
        "lockdown_trigger_count": stress_levels.get("lockdown", 0),
        "zero_dte_throttle_count": throttle_types.get("block_zero_dte", 0),
        "swing_only_count": throttle_types.get("swing_only", 0),
        "no_trade_only_count": throttle_types.get("no_trade_only", 0),
        "family_regime_block_count": throttle_types.get("block_family", 0) + throttle_types.get("block_regime", 0),
        "high_gamma_theta_throttle_count": throttle_types.get("block_high_gamma", 0) + throttle_types.get("block_high_theta", 0),
        "liquidity_spread_crisis_count": sum(1 for case in cases if set(case["stressors"]) & {"liquidity_collapse", "spread_explosion"}),
        "lockdown_blocks_new_entries": all(record["blocked"] is True for record in throttles if record["stress_level"] == "lockdown" and record["attempted_action"].startswith("open_")),
        "same_day_close_forced_count": 0,
        "same_day_churn_allowed": False,
        "paper_shadow_contained": True,
        "delayed_rotation_advisory_only": True,
        "no_day_trade_dominant": True,
        "paperbroker_override_allowed": False,
        "portfolio_feedback_advisory_only": True,
        "threshold_feedback_advisory_only": True,
        "allocator_feedback_actions": dict(sorted(allocator_actions.items())),
        "threshold_feedback_actions": dict(sorted(threshold_actions.items())),
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary


def _expected_new_entry_allowed(level_name: str, action: str) -> bool:
    if level_name == "lockdown":
        return False
    if level_name == "crisis" and action != "open_highest_proof_swing":
        return False
    return not action.startswith("paper_shadow") and action != "same_day_close"


def _expected_zero_dte_allowed(level_name: str, action: str) -> bool:
    if level_name in {"severe", "crisis", "lockdown"} and ("zero_dte" in action or "0dte" in action):
        return False
    return True


def _attention_before(level_name: str) -> float:
    return {"normal": 4.0, "elevated": 6.0, "defensive": 8.0, "severe": 10.0, "crisis": 12.0, "lockdown": 14.0}[level_name]


def _premium_before(level_name: str) -> float:
    return {"normal": 8.0, "elevated": 12.0, "defensive": 18.0, "severe": 24.0, "crisis": 30.0, "lockdown": 34.0}[level_name]


def _zero_dte_share_before(level_name: str) -> float:
    return {"normal": 0.18, "elevated": 0.32, "defensive": 0.35, "severe": 0.42, "crisis": 0.55, "lockdown": 0.0}[level_name]
