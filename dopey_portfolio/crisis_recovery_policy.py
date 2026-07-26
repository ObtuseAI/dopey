"""Gradual offline recovery rules for crisis-mode replay."""
from __future__ import annotations

from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .crisis_mode_policy import STRESS_LEVEL_RANKS


RECOVERY_STEPS: dict[str, str] = {
    "lockdown": "crisis",
    "crisis": "severe",
    "severe": "defensive",
    "defensive": "elevated",
    "elevated": "normal",
    "normal": "normal",
}


def evaluate_recovery(case: dict[str, Any], evaluated_level: str) -> dict[str, Any]:
    stressors = [str(value) for value in case["stressors"]]
    recovery_requested = bool(case.get("recovery_case", False))
    repeated_stress = "repeated_stress" in stressors
    to_level = evaluated_level
    allowed = False
    reason_codes = ["recovery_not_requested"]
    if recovery_requested:
        candidate = RECOVERY_STEPS[evaluated_level]
        allowed = True
        to_level = candidate
        reason_codes = [f"{evaluated_level}_to_{candidate}", "gradual_recovery_only"]
        if evaluated_level == "crisis" and str(case.get("requested_recovery_level", "")) == "normal":
            allowed = False
            to_level = "severe"
            reason_codes.append("crisis_cannot_jump_to_normal")
        if repeated_stress:
            to_level = evaluated_level
            reason_codes.append("repeated_stress_slows_recovery")
    result = {
        "artifact_type": "crisis_recovery_result",
        "recovery_result_id": f"crisis-recovery-{case['stress_case_id']}",
        "stress_case_id": case["stress_case_id"],
        "from_stress_level": evaluated_level,
        "to_stress_level": to_level,
        "recovery_allowed": allowed,
        "recovery_case": recovery_requested,
        "zero_dte_recovery_multiplier": _zero_dte_multiplier(to_level),
        "swing_recovery_multiplier": _swing_multiplier(to_level),
        "fragile_family_recovery_multiplier": _fragile_family_multiplier(to_level),
        "direct_crisis_to_normal_allowed": False,
        "no_day_trade_dominant": True,
        "paper_shadow_contained": True,
        "delayed_rotation_advisory_only": True,
        "live_threshold_mutation_allowed": False,
        "reason_codes": sorted(set(reason_codes)),
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
    }
    result["recovery_hash"] = reproducibility_hash(result)
    return result


def recovery_transition_level(from_level: str) -> str:
    return RECOVERY_STEPS[from_level]


def _zero_dte_multiplier(level_name: str) -> float:
    rank = STRESS_LEVEL_RANKS[level_name]
    return max(0.0, round((5 - rank) / 5 * 0.5, 4))


def _swing_multiplier(level_name: str) -> float:
    rank = STRESS_LEVEL_RANKS[level_name]
    return max(0.0, round((5 - rank) / 5, 4))


def _fragile_family_multiplier(level_name: str) -> float:
    rank = STRESS_LEVEL_RANKS[level_name]
    return max(0.0, round((5 - rank) / 5 * 0.35, 4))
