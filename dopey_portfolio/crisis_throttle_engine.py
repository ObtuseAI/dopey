"""Apply offline crisis-mode throttles to portfolio stress cases."""
from __future__ import annotations

from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .stress_ladder_models import CrisisModeThrottle


def select_throttle_profile(
    stress_level: str,
    stressors: list[str],
    action: str,
    profiles: list[CrisisModeThrottle],
) -> CrisisModeThrottle:
    throttle_type = _throttle_type_for(stress_level, stressors, action)
    for profile in profiles:
        if profile.stress_level == stress_level and profile.throttle_type == throttle_type:
            return profile
    for profile in profiles:
        if profile.stress_level == stress_level:
            return profile
    raise ValueError(f"missing throttle profile for stress level: {stress_level}")


def apply_crisis_throttle(
    case: dict[str, Any],
    stress_level: str,
    profile: CrisisModeThrottle,
) -> dict[str, Any]:
    action = str(case["attempted_action"])
    stressors = [str(value) for value in case["stressors"]]
    new_entry = action in {"open_zero_dte", "open_swing", "open_fragile_family", "open_high_gamma", "open_high_theta"}
    zero_dte_action = "zero_dte" in action or "0dte" in action
    fragile_action = "fragile" in action or "low_liquidity" in stressors
    audit_only = action == "audit_only"
    next_day_exit = action == "next_day_policy_exit"
    blocked = False
    reason_codes = list(profile.reason_codes)
    if profile.stress_level == "lockdown":
        blocked = new_entry or zero_dte_action or action == "same_day_close"
        reason_codes.append("lockdown_new_entries_blocked")
    elif action.startswith("paper_shadow"):
        blocked = True
        reason_codes.append("paper_shadow_leakage_blocked")
    elif profile.zero_dte_allowed is False and zero_dte_action:
        blocked = True
        reason_codes.append("zero_dte_blocked_by_crisis_mode")
    elif profile.new_entry_allowed is False and new_entry and not (profile.stress_level == "crisis" and action == "open_highest_proof_swing"):
        blocked = True
        reason_codes.append("new_entry_throttled_by_crisis_mode")
    elif fragile_action and profile.stress_level in {"crisis", "lockdown"}:
        blocked = True
        reason_codes.append("fragile_family_blocked_by_crisis_mode")
    if action == "same_day_close":
        blocked = True
        reason_codes.append("same_day_close_remains_blocked")
    if audit_only or next_day_exit:
        blocked = False
        reason_codes.append("audit_or_next_day_policy_action_allowed")
    result = {
        "artifact_type": "crisis_throttle_result",
        "throttle_result_id": f"crisis-throttle-result-{case['stress_case_id']}",
        "stress_case_id": case["stress_case_id"],
        "attempted_action": action,
        "stress_level": stress_level,
        "throttle_id": profile.throttle_id,
        "throttle_type": profile.throttle_type,
        "allowed": not blocked,
        "blocked": blocked,
        "new_entry_allowed": profile.new_entry_allowed and not blocked,
        "exit_allowed": profile.exit_allowed and action != "same_day_close",
        "same_day_close_allowed": False,
        "zero_dte_allowed": profile.zero_dte_allowed and not zero_dte_action,
        "swing_allowed": profile.swing_allowed,
        "delayed_rotation_allowed": profile.delayed_rotation_allowed,
        "paper_shadow_allowed": profile.paper_shadow_allowed,
        "new_paper_attention_cap": profile.paper_attention_cap,
        "new_paper_premium_risk_cap": profile.paper_premium_risk_cap,
        "allocation_multiplier": profile.allocation_multiplier,
        "reason_codes": sorted(set(reason_codes)),
        "safety_status": "paper_only_live_blocked",
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    result["throttle_result_hash"] = reproducibility_hash(result)
    return result


def _throttle_type_for(stress_level: str, stressors: list[str], action: str) -> str:
    stressor_set = set(stressors)
    if stress_level == "lockdown":
        return "lockdown_allocation"
    if "family_concentration" in stressor_set or "low_liquidity_family" in stressor_set:
        return "block_family"
    if "regime_concentration" in stressor_set:
        return "block_regime"
    if "moderate_gamma_pressure" in stressor_set or "high_gamma" in action:
        return "block_high_gamma"
    if "moderate_theta_pressure" in stressor_set or "high_theta" in action:
        return "block_high_theta"
    if "iv_crush_exposure" in stressor_set:
        return "block_iv_crush"
    if "event_macro_shock" in stressor_set or "macro_sensitive_family" in stressor_set:
        return "block_event_macro"
    if stress_level in {"severe", "crisis"} and ("zero_dte" in action or "0dte" in action):
        return "block_zero_dte"
    if stress_level == "crisis":
        return "no_trade_only"
    if stress_level == "defensive":
        return "swing_only"
    if stress_level == "elevated":
        return "reduce_allocation"
    return "reduce_allocation"
