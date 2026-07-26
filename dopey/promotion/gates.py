"""Pure protected evaluators for symbol, strategy, and pair activation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dopey.protocols.identity import canonical_hash

from .schema import (
    PromotionThresholds,
    ResearchActivationState,
    StrategyPromotionEvidence,
    SymbolPromotionEvidence,
    SymbolStrategyPromotionEvidence,
)


_COMMON_FLOAT_FIELDS: tuple[str, ...] = (
    "causal_confidence",
    "calibration_error",
    "independence_score",
    "missing_fraction",
)


def _validate_identifier(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"promotion evidence requires a non-empty identifier: field={field}")
    return normalized


def _validate_fraction(value: float, field: str) -> None:
    if value < 0.0 or value > 1.0:
        raise ValueError(f"promotion fraction is outside [0, 1]: field={field}, value={value}")


def _validate_common(evidence: Mapping[str, Any]) -> None:
    for field in _COMMON_FLOAT_FIELDS:
        _validate_fraction(float(evidence[field]), field)


def _unsafe_failures(evidence: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if not bool(evidence["deterministic_replay"]):
        failures.append("deterministic_replay")
    if bool(evidence["leakage_detected"]):
        failures.append("leakage_detected")
    if bool(evidence["revised_data_contamination"]):
        failures.append("revised_data_contamination")
    if bool(evidence["reward_hacking_detected"]):
        failures.append("reward_hacking_detected")
    return failures


def _quality_failures(evidence: Mapping[str, Any], thresholds: PromotionThresholds) -> list[str]:
    failures: list[str] = []
    comparisons = (
        ("causal_confidence", float(evidence["causal_confidence"]) >= thresholds["min_causal_confidence"]),
        ("calibration_error", float(evidence["calibration_error"]) <= thresholds["max_calibration_error"]),
        ("independence_score", float(evidence["independence_score"]) >= thresholds["min_independence_score"]),
        ("missing_fraction", float(evidence["missing_fraction"]) <= thresholds["max_missing_fraction"]),
        ("after_cost_gain", float(evidence["after_cost_gain"]) > 0.0),
        ("contested_gain", float(evidence["contested_gain"]) >= 0.0),
        ("confidence_interval_lower", float(evidence["confidence_interval_lower"]) > 0.0),
    )
    failures.extend(name for name, passed in comparisons if not passed)
    return failures


def _decision(
    gate_type: str,
    subject_id: str,
    state: ResearchActivationState,
    failed_thresholds: list[str],
    thresholds: PromotionThresholds,
    activation_allowed: bool,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "artifact_type": f"{gate_type}_autonomous_research_promotion_gate",
        "gate_version": "dopey-autonomous-research-promotion-gate-v1",
        "gate_type": gate_type,
        "subject_id": subject_id,
        "state": state.value,
        "failed_thresholds": sorted(set(failed_thresholds)),
        "threshold_version": thresholds["threshold_version"],
        "automatic_research_activation_allowed": activation_allowed,
        "human_review_required": False,
        "protected_evaluator_required": True,
        "candidate_may_grade_itself": False,
        "candidate_may_modify_gate": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "decision_hash": canonical_hash(body)}


def evaluate_symbol_promotion(
    evidence: SymbolPromotionEvidence,
    thresholds: PromotionThresholds,
) -> dict[str, Any]:
    symbol_id = _validate_identifier(evidence["symbol_id"], "symbol_id")
    _validate_common(evidence)
    unsafe = _unsafe_failures(evidence)
    if unsafe:
        return _decision("symbol", symbol_id, ResearchActivationState.QUARANTINED, unsafe, thresholds, False)
    replay_failures = [
        name
        for name, passed in (
            ("history_rows", evidence["history_rows"] >= thresholds["symbol_min_history_rows"]),
            ("replay_samples", evidence["replay_samples"] >= thresholds["symbol_min_replay_samples"]),
        )
        if not passed
    ]
    if replay_failures:
        return _decision("symbol", symbol_id, ResearchActivationState.EXPERIMENTAL, replay_failures, thresholds, False)
    if evidence["private_samples"] < thresholds["symbol_min_private_samples"]:
        return _decision("symbol", symbol_id, ResearchActivationState.REPLAY_VALIDATED, ["private_samples"], thresholds, False)
    if evidence["external_samples"] < thresholds["symbol_min_external_samples"]:
        return _decision("symbol", symbol_id, ResearchActivationState.PRIVATE_VALIDATED, ["external_samples"], thresholds, False)
    if evidence["forward_samples"] < thresholds["symbol_min_forward_samples"]:
        return _decision("symbol", symbol_id, ResearchActivationState.EXTERNAL_VALIDATED, ["forward_samples"], thresholds, False)
    final_failures = _quality_failures(evidence, thresholds)
    if evidence["independent_strategies"] < thresholds["symbol_min_independent_strategies"]:
        final_failures.append("independent_strategies")
    state = ResearchActivationState.RESEARCH_APPROVED if not final_failures else ResearchActivationState.FORWARD_PAPER
    return _decision("symbol", symbol_id, state, final_failures, thresholds, not final_failures)


def evaluate_strategy_promotion(
    evidence: StrategyPromotionEvidence,
    thresholds: PromotionThresholds,
) -> dict[str, Any]:
    strategy_id = _validate_identifier(evidence["strategy_id"], "strategy_id")
    _validate_identifier(evidence["lineage_id"], "lineage_id")
    _validate_common(evidence)
    _validate_fraction(evidence["transfer_score"], "transfer_score")
    _validate_fraction(evidence["complexity_score"], "complexity_score")
    _validate_fraction(evidence["abstention_rate"], "abstention_rate")
    unsafe = _unsafe_failures(evidence)
    if not evidence["evaluator_independent"]:
        unsafe.append("evaluator_independent")
    if unsafe:
        return _decision("strategy", strategy_id, ResearchActivationState.QUARANTINED, unsafe, thresholds, False)
    if evidence["backtest_samples"] < thresholds["strategy_min_backtest_samples"]:
        return _decision("strategy", strategy_id, ResearchActivationState.EXPERIMENTAL, ["backtest_samples"], thresholds, False)
    if evidence["private_samples"] < thresholds["strategy_min_private_samples"]:
        return _decision("strategy", strategy_id, ResearchActivationState.REPLAY_VALIDATED, ["private_samples"], thresholds, False)
    if evidence["external_samples"] < thresholds["strategy_min_external_samples"]:
        return _decision("strategy", strategy_id, ResearchActivationState.PRIVATE_VALIDATED, ["external_samples"], thresholds, False)
    if evidence["forward_samples"] < thresholds["strategy_min_forward_samples"]:
        return _decision("strategy", strategy_id, ResearchActivationState.EXTERNAL_VALIDATED, ["forward_samples"], thresholds, False)
    final_failures = _quality_failures(evidence, thresholds)
    comparisons = (
        ("symbol_count", evidence["symbol_count"] >= thresholds["strategy_min_symbols"]),
        ("era_count", evidence["era_count"] >= thresholds["strategy_min_eras"]),
        ("regime_count", evidence["regime_count"] >= thresholds["strategy_min_regimes"]),
        ("transfer_score", evidence["transfer_score"] >= thresholds["min_transfer_score"]),
        ("complexity_score", evidence["complexity_score"] <= thresholds["max_complexity_score"]),
        ("abstention_rate", evidence["abstention_rate"] <= thresholds["max_abstention_rate"]),
    )
    final_failures.extend(name for name, passed in comparisons if not passed)
    state = ResearchActivationState.RESEARCH_APPROVED if not final_failures else ResearchActivationState.FORWARD_PAPER
    return _decision("strategy", strategy_id, state, final_failures, thresholds, not final_failures)


def evaluate_symbol_strategy_promotion(
    evidence: SymbolStrategyPromotionEvidence,
    symbol_gate: Mapping[str, Any],
    strategy_gate: Mapping[str, Any],
    thresholds: PromotionThresholds,
) -> dict[str, Any]:
    symbol_id = _validate_identifier(evidence["symbol_id"], "symbol_id")
    strategy_id = _validate_identifier(evidence["strategy_id"], "strategy_id")
    subject_id = f"{symbol_id}::{strategy_id}"
    _validate_common(evidence)
    if symbol_gate.get("subject_id") != symbol_id:
        raise ValueError(
            "pair promotion received a mismatched symbol gate: "
            f"pair_symbol={symbol_id}, gate_subject={symbol_gate.get('subject_id')}"
        )
    if strategy_gate.get("subject_id") != strategy_id:
        raise ValueError(
            "pair promotion received a mismatched strategy gate: "
            f"pair_strategy={strategy_id}, gate_subject={strategy_gate.get('subject_id')}"
        )
    unsafe = _unsafe_failures(evidence)
    if unsafe:
        return _decision("symbol_strategy", subject_id, ResearchActivationState.QUARANTINED, unsafe, thresholds, False)
    gate_failures: list[str] = []
    if symbol_gate.get("automatic_research_activation_allowed") is not True:
        gate_failures.append("symbol_gate")
    if strategy_gate.get("automatic_research_activation_allowed") is not True:
        gate_failures.append("strategy_gate")
    if evidence["forward_samples"] < thresholds["pair_min_forward_samples"]:
        gate_failures.append("forward_samples")
    if evidence["regime_count"] < thresholds["pair_min_regimes"]:
        gate_failures.append("regime_count")
    gate_failures.extend(_quality_failures(evidence, thresholds))
    state = ResearchActivationState.RESEARCH_APPROVED if not gate_failures else ResearchActivationState.FORWARD_PAPER
    return _decision("symbol_strategy", subject_id, state, gate_failures, thresholds, not gate_failures)
