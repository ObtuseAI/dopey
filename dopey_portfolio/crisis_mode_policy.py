"""Offline crisis-mode policy for portfolio stress ladder replay."""
from __future__ import annotations

from typing import Any

from .stress_ladder_models import (
    CrisisModeThrottle,
    PortfolioStressLadder,
    PortfolioStressLevel,
    crisis_throttle_hash,
    stress_ladder_hash,
    stress_level_hash,
)


STRESS_LEVEL_RANKS: dict[str, int] = {
    "normal": 0,
    "elevated": 1,
    "defensive": 2,
    "severe": 3,
    "crisis": 4,
    "lockdown": 5,
}


def default_stress_levels() -> list[PortfolioStressLevel]:
    configs = [
        ("normal", ["normal_pressure"], ["open_position", "hold_position", "rotate_allowed"], [], 1.0, 1.0, 1.0, 1.0, 1.0, ["reduce_allocation"]),
        ("elevated", ["mild_0dte_pressure", "delayed_rotation_backlog"], ["open_position", "hold_position", "rotate_delayed"], ["oversized_0dte_entry"], 0.85, 0.65, 0.95, 1.0, 0.75, ["reduce_allocation"]),
        ("defensive", ["moderate_gamma_pressure", "moderate_theta_pressure", "rejected_candidate_pressure"], ["swing_only", "delay_rotation", "watchlist_only"], ["fragile_family_entry"], 0.65, 0.35, 0.85, 0.8, 0.5, ["reduce_allocation", "swing_only"]),
        ("severe", ["iv_crush_exposure", "event_macro_shock", "paper_shadow_leakage_attempt"], ["swing_only", "delay_rotation", "no_trade_only"], ["zero_dte_entry", "high_gamma_entry"], 0.4, 0.0, 0.55, 0.6, 0.25, ["block_zero_dte", "block_high_gamma", "block_high_theta"]),
        ("crisis", ["liquidity_collapse", "spread_explosion", "multi_stressor", "same_day_close_pressure"], ["highest_proof_swing", "delay_rotation", "no_trade_only"], ["new_zero_dte_entry", "fragile_family_entry"], 0.18, 0.0, 0.25, 0.35, 0.1, ["block_zero_dte", "block_family", "block_regime", "no_trade_only"]),
        ("lockdown", ["live_path_injection", "broker_path_injection", "real_sizing_injection"], ["audit_only", "next_day_policy_exit"], ["new_entry", "same_day_close"], 0.0, 0.0, 0.0, 0.0, 0.0, ["lockdown_allocation", "block_new_entries"]),
    ]
    levels: list[PortfolioStressLevel] = []
    for name, triggers, allowed, blocked, allocation, zero_dte, swing, delayed, shadow, throttles in configs:
        level = PortfolioStressLevel(
            stress_level_id=f"portfolio-stress-level-{name}",
            level_name=name,
            level_rank=STRESS_LEVEL_RANKS[name],
            trigger_conditions=triggers,
            allowed_actions=allowed,
            blocked_actions=blocked,
            allocation_multiplier=allocation,
            zero_dte_multiplier=zero_dte,
            swing_multiplier=swing,
            delayed_rotation_multiplier=delayed,
            paper_shadow_multiplier=shadow,
            required_throttles=throttles,
            paper_only=True,
            live_blocked=True,
            level_hash="",
        )
        levels.append(PortfolioStressLevel(**{**level.to_dict(), "level_hash": stress_level_hash(level)}))
    return levels


def default_crisis_throttle_profiles() -> list[CrisisModeThrottle]:
    configs = [
        ("normal", "reduce_allocation", True, True, True, True, True, 1.0, 8.0, 14.0, ["normal_pressure_no_extra_throttle"]),
        ("elevated", "reduce_allocation", True, True, True, True, True, 0.85, 5.0, 10.0, ["elevated_risk_reduction"]),
        ("defensive", "swing_only", True, True, True, True, True, 0.65, 3.5, 7.0, ["defensive_prefer_swing"]),
        ("severe", "block_zero_dte", True, True, False, True, True, 0.4, 2.5, 4.5, ["severe_zero_dte_block"]),
        ("crisis", "no_trade_only", False, True, False, False, True, 0.18, 1.0, 1.5, ["crisis_no_trade_for_fragile_setup"]),
        ("lockdown", "lockdown_allocation", False, True, False, False, False, 0.0, 0.0, 0.0, ["lockdown_blocks_new_entries"]),
        ("crisis", "block_family", False, True, False, False, True, 0.0, 0.0, 0.0, ["crisis_family_block"]),
        ("crisis", "block_regime", False, True, False, False, True, 0.0, 0.0, 0.0, ["crisis_regime_block"]),
        ("defensive", "block_family", False, True, True, True, True, 0.25, 1.0, 2.0, ["defensive_family_throttle"]),
        ("defensive", "block_regime", False, True, True, True, True, 0.25, 1.0, 2.0, ["defensive_regime_throttle"]),
        ("severe", "block_high_gamma", False, True, False, True, True, 0.0, 0.0, 0.0, ["severe_high_gamma_block"]),
        ("severe", "block_high_theta", False, True, False, True, True, 0.0, 0.0, 0.0, ["severe_high_theta_block"]),
        ("severe", "block_iv_crush", False, True, False, True, True, 0.0, 0.0, 0.0, ["severe_iv_crush_block"]),
        ("severe", "block_event_macro", False, True, False, True, True, 0.0, 0.0, 0.0, ["severe_event_macro_block"]),
        ("defensive", "delay_rotation", False, True, True, True, True, 0.5, 2.0, 4.0, ["delayed_rotation_preserved_advisory"]),
        ("defensive", "paper_shadow_only", False, False, False, False, True, 0.0, 0.0, 0.0, ["paper_shadow_contained"]),
        ("elevated", "watchlist_only", False, False, False, False, True, 0.0, 0.0, 0.0, ["watchlist_only_under_pressure"]),
    ]
    profiles: list[CrisisModeThrottle] = []
    for level, throttle_type, new_entry, exit_allowed, zero_dte, swing, shadow, allocation, attention_cap, premium_cap, reasons in configs:
        throttle = CrisisModeThrottle(
            throttle_id=f"crisis-throttle-{level}-{throttle_type}",
            stress_level=level,
            throttle_type=throttle_type,
            trigger_reason_codes=reasons,
            affected_strategy_types=_affected_strategy_types(throttle_type),
            affected_underlying_families=["fragile-family", "low-liquidity-family"] if throttle_type == "block_family" else [],
            affected_regime_families=["crowded-regime", "macro-sensitive-regime"] if throttle_type == "block_regime" else [],
            new_entry_allowed=new_entry,
            exit_allowed=exit_allowed,
            same_day_close_allowed=False,
            zero_dte_allowed=zero_dte,
            swing_allowed=swing,
            delayed_rotation_allowed=level not in {"lockdown"},
            paper_shadow_allowed=shadow,
            allocation_multiplier=allocation,
            paper_attention_cap=attention_cap,
            paper_premium_risk_cap=premium_cap,
            reason_codes=reasons,
            paper_only=True,
            live_blocked=True,
            throttle_hash="",
        )
        profiles.append(CrisisModeThrottle(**{**throttle.to_dict(), "throttle_hash": crisis_throttle_hash(throttle)}))
    return profiles


def default_portfolio_stress_ladder() -> PortfolioStressLadder:
    levels = [level.to_dict() for level in default_stress_levels()]
    profiles = [profile.to_dict() for profile in default_crisis_throttle_profiles()]
    ladder = PortfolioStressLadder(
        ladder_id="dopey-portfolio-stress-ladder-v1",
        ladder_version="dopey-portfolio-replay-v2-stress-ladder-v1",
        stress_levels=levels,
        transition_rules=_transition_rules(),
        crisis_modes=[
            {"mode": "normal", "new_entry_policy": "standard_paper_rules"},
            {"mode": "elevated", "new_entry_policy": "modest_risk_throttle"},
            {"mode": "defensive", "new_entry_policy": "cap_zero_dte_and_fragile_families"},
            {"mode": "severe", "new_entry_policy": "block_most_zero_dte_prefer_swing_delayed_no_trade"},
            {"mode": "crisis", "new_entry_policy": "block_zero_dte_fragile_family_only_highest_proof_swing"},
            {"mode": "lockdown", "new_entry_policy": "audit_only_no_new_entries"},
        ],
        throttle_profiles=profiles,
        paper_only=True,
        live_blocked=True,
        ladder_hash="",
    )
    return PortfolioStressLadder(**{**ladder.to_dict(), "ladder_hash": stress_ladder_hash(ladder)})


def evaluate_stress_level(stressors: list[str]) -> str:
    values = set(stressors)
    if values & {"live_path_injection", "broker_path_injection", "real_sizing_injection"}:
        return "lockdown"
    if values & {"liquidity_collapse", "spread_explosion", "multi_stressor", "same_day_close_pressure"}:
        return "crisis"
    if values & {"iv_crush_exposure", "event_macro_shock", "paper_shadow_leakage_attempt", "macro_sensitive_family"}:
        return "severe"
    if values & {"moderate_gamma_pressure", "moderate_theta_pressure", "rejected_candidate_pressure", "family_concentration", "regime_concentration", "call_heavy", "put_heavy"}:
        return "defensive"
    if values & {"mild_0dte_pressure", "delayed_rotation_backlog"}:
        return "elevated"
    return "normal"


def transition_reason_codes(from_level: str, to_level: str, stressors: list[str]) -> list[str]:
    from_rank = STRESS_LEVEL_RANKS[from_level]
    to_rank = STRESS_LEVEL_RANKS[to_level]
    direction = "transition_up" if to_rank > from_rank else "transition_down" if to_rank < from_rank else "transition_hold"
    return sorted({direction, *stressors})


def allocator_feedback_for_level(level_name: str, stressors: list[str]) -> list[str]:
    feedback: list[str] = []
    if level_name in {"elevated", "defensive", "severe", "crisis", "lockdown"}:
        feedback.append("reduce_total_allocation_under_stress")
    if level_name in {"severe", "crisis", "lockdown"}:
        feedback.append("block_0dte_under_crisis")
    if level_name in {"defensive", "severe", "crisis"}:
        feedback.append("reduce_family_concentration")
        feedback.append("reduce_regime_concentration")
    if "moderate_gamma_pressure" in stressors:
        feedback.append("reduce_high_gamma_exposure")
    if "moderate_theta_pressure" in stressors:
        feedback.append("reduce_high_theta_exposure")
    if level_name == "crisis":
        feedback.append("preserve_no_trade_recommendation")
    if "paper_shadow_leakage_attempt" in stressors:
        feedback.append("keep_paper_shadow_contained")
    if level_name == "normal":
        feedback.append("keep_live_default_behavior_unchanged")
    return sorted(set(feedback))


def threshold_feedback_for_level(level_name: str, stressors: list[str]) -> list[str]:
    feedback: list[str] = ["keep_live_default_thresholds_unchanged"]
    if level_name in {"severe", "crisis", "lockdown"}:
        feedback.append("downgrade_profile_that_increases_crisis_transitions")
    if "moderate_gamma_pressure" in stressors or "moderate_theta_pressure" in stressors:
        feedback.append("preserve_gamma_theta_paper_shadow_if_reduces_crisis")
    if "iv_crush_exposure" in stressors or "event_macro_shock" in stressors:
        feedback.append("strengthen_later_expiry_advisory_preference")
    if "same_day_close_pressure" in stressors:
        feedback.append("reject_profile_that_increases_same_day_churn_pressure")
    if set(stressors) & {"live_path_injection", "broker_path_injection", "real_sizing_injection"}:
        feedback.append("reject_profile_with_safety_boundary_pressure")
    return sorted(set(feedback))


def _affected_strategy_types(throttle_type: str) -> list[str]:
    if throttle_type == "block_zero_dte":
        return ["zero_dte_long_call", "zero_dte_long_put"]
    if throttle_type == "swing_only":
        return ["swing_long_call", "swing_long_put"]
    if throttle_type == "delay_rotation":
        return ["delayed_rotation_long_call", "delayed_rotation_long_put"]
    return []


def _transition_rules() -> list[dict[str, Any]]:
    return [
        {"from": "normal", "to": "elevated", "reason": "mild_0dte_or_delayed_backlog"},
        {"from": "elevated", "to": "defensive", "reason": "gamma_theta_or_rejection_pressure"},
        {"from": "defensive", "to": "severe", "reason": "iv_event_or_shadow_leakage"},
        {"from": "severe", "to": "crisis", "reason": "liquidity_spread_multi_or_churn_pressure"},
        {"from": "crisis", "to": "lockdown", "reason": "live_broker_or_real_sizing_injection"},
        {"from": "lockdown", "to": "crisis", "reason": "gradual_recovery_only"},
        {"from": "crisis", "to": "severe", "reason": "stress_clears"},
        {"from": "severe", "to": "defensive", "reason": "exposure_clears"},
        {"from": "defensive", "to": "elevated", "reason": "fragile_pressure_reduces"},
        {"from": "elevated", "to": "normal", "reason": "normal_pressure_returns"},
    ]
