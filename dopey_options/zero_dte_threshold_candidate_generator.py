"""Generate deterministic offline 0DTE threshold candidate profiles."""
from __future__ import annotations

from typing import Any

from .zero_dte_risk_thresholds import ZeroDTERiskThresholds
from .zero_dte_threshold_candidate import threshold_field_names
from .zero_dte_threshold_optimizer_models import (
    ZERO_DTE_THRESHOLD_OPTIMIZER_VERSION,
    ZeroDTEThresholdCandidate,
    zero_dte_threshold_candidate_hash,
)


def generate_zero_dte_threshold_candidates(
    aggregate,
    base_thresholds: ZeroDTERiskThresholds,
) -> list[ZeroDTEThresholdCandidate]:
    tightened_support = sorted(aggregate.feedback_counts_by_type)
    return [
        _candidate(
            "stricter_liquidity_profile",
            base_thresholds,
            {
                "max_spread_pct": 0.034,
                "minimum_volume": 1500,
                "minimum_open_interest": 2500,
                "minimum_liquidity_score": 0.78,
                "max_spread_adjusted_entry_penalty": 0.105,
            },
            {},
            [
                "replay_feedback_tightens_spread_and_liquidity",
                f"supporting_feedback:{aggregate.feedback_counts_by_type.get('tighten_liquidity_threshold', 0)}",
            ],
            ["reduce_wide_spread_and_liquidity_decay_approvals"],
            "stricter",
            "paper_shadow_candidate",
            [],
        ),
        _candidate(
            "stricter_gamma_theta_profile",
            base_thresholds,
            {
                "max_gamma_instability_score": 0.52,
                "max_theta_decay_pressure": 0.44,
            },
            {},
            [
                "replay_feedback_tightens_gamma_and_theta",
                f"supporting_feedback:{aggregate.feedback_counts_by_type.get('tighten_gamma_instability_threshold', 0) + aggregate.feedback_counts_by_type.get('tighten_theta_decay_threshold', 0)}",
            ],
            ["reduce_gamma_reversal_and_theta_decay_traps"],
            "stricter",
            "paper_shadow_candidate",
            [],
        ),
        _candidate(
            "stricter_iv_overpayment_profile",
            base_thresholds,
            {
                "max_iv_shock_score": 0.66,
                "max_premium_overpayment_score": 0.62,
                "max_iv_rank_fixture": 0.72,
                "max_implied_volatility": 0.70,
            },
            {},
            [
                "replay_feedback_tightens_iv_overpayment",
                f"supporting_feedback:{aggregate.feedback_counts_by_type.get('tighten_iv_overpayment_threshold', 0)}",
            ],
            ["reduce_iv_crush_and_premium_trap_approvals"],
            "stricter",
            "paper_shadow_candidate",
            [],
        ),
        _candidate(
            "proof_strengthened_profile",
            base_thresholds,
            {
                "minimum_proof_score": 0.78,
                "minimum_signal_confidence": 0.74,
                "explicit_thesis_required": True,
                "explicit_exit_plan_required": True,
            },
            {},
            [
                "replay_feedback_increases_proof_requirement",
                f"supporting_feedback:{aggregate.feedback_counts_by_type.get('increase_proof_score_requirement', 0)}",
            ],
            ["reduce_false_breakout_and_weak_signal_approvals"],
            "stricter",
            "paper_shadow_candidate",
            [],
        ),
        _candidate(
            "later_expiry_preference_profile",
            base_thresholds,
            {},
            {"later_expiry_preference": "prefer_when_replay_confirms_later_expiry_superiority"},
            [
                "replay_confirmed_later_expiry_alternative",
                f"supporting_feedback:{aggregate.later_expiry_recommendation_count}",
            ],
            ["prefer_non_zero_dte_alternative_when_fixture_replay_confirms_better_path"],
            "balanced_research",
            "paper_shadow_candidate",
            [],
        ),
        _candidate(
            "balanced_research_profile",
            base_thresholds,
            {
                "max_spread_pct": 0.038,
                "minimum_liquidity_score": 0.76,
                "max_gamma_instability_score": 0.55,
                "max_theta_decay_pressure": 0.47,
                "max_premium_overpayment_score": 0.66,
                "minimum_proof_score": 0.74,
                "minimum_signal_confidence": 0.70,
                "explicit_thesis_required": True,
                "explicit_exit_plan_required": True,
            },
            {"validated_feedback_types": tightened_support},
            ["modestly_tighten_controls_with_replay_support"],
            ["safest_next_offline_paper_replay_cycle"],
            "balanced_research",
            "research_default_candidate",
            [],
        ),
        _candidate(
            "coverage_expansion_profile",
            base_thresholds,
            {},
            {"fixture_expansion_required": True},
            ["blocked_maybe_too_strict_requires_more_fixture_coverage"],
            ["add_ambiguous_blocked_candidate_fixture_coverage_without_threshold_change"],
            "coverage_expansion_only",
            "needs_more_fixture_coverage",
            ["blocked_maybe_too_strict", "pin_risk", "special_close_missing_reason"],
        ),
        _candidate(
            "rejected_too_loose_profile",
            base_thresholds,
            {
                "max_spread_pct": 0.50,
                "minimum_volume": 0,
                "minimum_open_interest": 0,
                "minimum_liquidity_score": 0.0,
                "max_slippage_score": 1.0,
                "max_spread_adjusted_entry_penalty": 1.0,
                "max_gamma_instability_score": 1.0,
                "max_theta_decay_pressure": 1.0,
                "max_iv_shock_score": 1.0,
                "max_premium_overpayment_score": 1.0,
                "max_iv_rank_fixture": 1.0,
                "max_implied_volatility": 1.0,
                "minimum_proof_score": 0.0,
                "minimum_signal_confidence": 0.0,
                "throttle_risk_score": 1.0,
                "block_risk_score": 1.0,
                "explicit_thesis_required": True,
                "explicit_exit_plan_required": True,
            },
            {"negative_control": True},
            ["negative_control_should_be_rejected_by_optimizer"],
            ["prove_unsafe_new_approvals_are_rejected"],
            "rejected_too_loose",
            "reject",
            [],
        ),
    ]


def _candidate(
    candidate_threshold_id: str,
    base_thresholds: ZeroDTERiskThresholds,
    threshold_overrides: dict[str, Any],
    policy_overrides: dict[str, Any],
    change_rationale: list[str],
    expected_effect: list[str],
    risk_posture: str,
    promotion_gate: str,
    requires_more_fixture_coverage: list[str],
) -> ZeroDTEThresholdCandidate:
    controls_tightened = _tightened_controls(base_thresholds, threshold_overrides)
    controls_loosened = _loosened_controls(base_thresholds, threshold_overrides)
    controls_unchanged = [
        name for name in threshold_field_names()
        if name not in set(controls_tightened).union(set(controls_loosened)) and name != "threshold_version"
    ]
    candidate_version = f"{ZERO_DTE_THRESHOLD_OPTIMIZER_VERSION}:{candidate_threshold_id}"
    draft = ZeroDTEThresholdCandidate(
        candidate_threshold_id=candidate_threshold_id,
        base_threshold_version=base_thresholds.threshold_version,
        candidate_version=candidate_version,
        change_set={
            "threshold_overrides": dict(sorted(threshold_overrides.items())),
            "policy_overrides": dict(sorted(policy_overrides.items())),
            "safety_invariants": {
                "paper_only": True,
                "live_blocked": True,
                "allow_live_threshold_mutation": False,
                "allow_sell_to_open": False,
                "allow_normal_same_day_churn": False,
            },
        },
        change_rationale=change_rationale,
        expected_effect=expected_effect,
        risk_posture=risk_posture,
        controls_tightened=controls_tightened,
        controls_loosened=controls_loosened,
        controls_unchanged=controls_unchanged,
        requires_more_fixture_coverage=requires_more_fixture_coverage,
        promotion_gate=promotion_gate,
        paper_only=True,
        live_blocked=True,
        candidate_hash="",
    )
    return ZeroDTEThresholdCandidate(
        candidate_threshold_id=draft.candidate_threshold_id,
        base_threshold_version=draft.base_threshold_version,
        candidate_version=draft.candidate_version,
        change_set=draft.change_set,
        change_rationale=draft.change_rationale,
        expected_effect=draft.expected_effect,
        risk_posture=draft.risk_posture,
        controls_tightened=draft.controls_tightened,
        controls_loosened=draft.controls_loosened,
        controls_unchanged=draft.controls_unchanged,
        requires_more_fixture_coverage=draft.requires_more_fixture_coverage,
        promotion_gate=draft.promotion_gate,
        paper_only=True,
        live_blocked=True,
        candidate_hash=zero_dte_threshold_candidate_hash(draft),
    )


def _tightened_controls(base_thresholds: ZeroDTERiskThresholds, overrides: dict[str, Any]) -> list[str]:
    base = base_thresholds.to_dict()
    tightened: list[str] = []
    for key, value in overrides.items():
        if key not in base:
            continue
        if _is_tightening(key, base[key], value):
            tightened.append(key)
    return sorted(tightened)


def _loosened_controls(base_thresholds: ZeroDTERiskThresholds, overrides: dict[str, Any]) -> list[str]:
    base = base_thresholds.to_dict()
    loosened: list[str] = []
    for key, value in overrides.items():
        if key not in base:
            continue
        if _is_loosening(key, base[key], value):
            loosened.append(key)
    return sorted(loosened)


def _is_tightening(key: str, base_value: Any, candidate_value: Any) -> bool:
    if isinstance(base_value, bool) and isinstance(candidate_value, bool):
        return candidate_value is True and base_value is False
    if not isinstance(base_value, int | float) or not isinstance(candidate_value, int | float):
        return False
    if key.startswith("minimum") or key in {"min_iv_rank_fixture"}:
        return float(candidate_value) > float(base_value)
    if key.startswith("max") or key in {"block_risk_score", "throttle_risk_score"}:
        return float(candidate_value) < float(base_value)
    return False


def _is_loosening(key: str, base_value: Any, candidate_value: Any) -> bool:
    if isinstance(base_value, bool) and isinstance(candidate_value, bool):
        return candidate_value is False and base_value is True
    if not isinstance(base_value, int | float) or not isinstance(candidate_value, int | float):
        return False
    if key.startswith("minimum") or key in {"min_iv_rank_fixture"}:
        return float(candidate_value) < float(base_value)
    if key.startswith("max") or key in {"block_risk_score", "throttle_risk_score"}:
        return float(candidate_value) > float(base_value)
    return False
