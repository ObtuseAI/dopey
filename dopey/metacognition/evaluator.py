"""Synthesize difficulty, confidence, knowledge boundary, and control."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dopey.constitution.authority import Authority
from dopey.protocols.agents import AgentResult

from .abstention import choose_control_output
from .calibration import calibration_state
from .confidence import ConfidenceDimensions, aggregate_confidence
from .difficulty import estimate_difficulty
from .disagreement import disagreement_score
from .knowledge_boundary import classify_knowledge_boundary
from .progress import expected_information_gain
from .resource_control import evaluate_research_utility
from .strategy_selector import select_strategy


def evaluate_metacognition(
    objective_type: str,
    authority: Authority,
    technical_evidence: Mapping[str, Any],
    world_model: Mapping[str, Any],
    agent_results: Sequence[AgentResult],
    hypothesis_probabilities: Sequence[float],
    calibration_summary: Mapping[str, Any],
    resource_ledger: Mapping[str, Any],
) -> dict[str, Any]:
    measurements = list(technical_evidence.get("measurements", []))
    complete_measurements = sum(record.get("measurement_status") == "complete" for record in measurements)
    technical_completeness = complete_measurements / len(measurements) if measurements else 0.0
    known_dimensions = int(world_model.get("known_dimension_count", 0) or 0)
    unknown_dimensions = int(world_model.get("unknown_dimension_count", 0) or 0)
    total_dimensions = known_dimensions + unknown_dimensions
    world_completeness = known_dimensions / total_dimensions if total_dimensions else 0.0
    evidence_completeness = 0.65 * technical_completeness + 0.35 * world_completeness
    freshness_values = [
        float(record.get("freshness", 0.0) or 0.0)
        for record in measurements
        if record.get("measurement_status") == "complete"
    ]
    freshness = min(freshness_values) if freshness_values else 0.0
    regime_familiarity = min(0.75, world_completeness * 0.75)
    disagreement = disagreement_score(hypothesis_probabilities)
    calibration = calibration_state(calibration_summary)
    model_confidence = (
        sum(result.confidence for result in agent_results) / len(agent_results)
        if agent_results else 0.0
    )
    confidence = aggregate_confidence(
        ConfidenceDimensions(
            model=model_confidence,
            evidence_completeness=evidence_completeness,
            evidence_freshness=freshness,
            historical_analogue_quality=min(0.5, regime_familiarity),
            calibration_quality=float(calibration["calibration_quality"]),
            causal_confidence=0.2,
            agent_disagreement=disagreement,
            regime_familiarity=regime_familiarity,
            settlement_sample_size=float(calibration["sample_size_score"]),
        )
    )
    boundary = classify_knowledge_boundary(authority, evidence_completeness, regime_familiarity)
    difficulty = estimate_difficulty(
        evidence_completeness,
        regime_familiarity,
        disagreement,
        len(world_model.get("contradictions", [])),
    )
    unknown_fraction = unknown_dimensions / total_dimensions if total_dimensions else 1.0
    information_gain = expected_information_gain(unknown_fraction, 0.45, 0.2)
    evidence_quality = min(evidence_completeness, freshness)
    resource_utility = evaluate_research_utility(
        information_gain,
        evidence_quality,
        resource_ledger,
        0.1,
        1.0 - float(confidence["final_research_confidence"]),
    )
    budget_exceeded = bool(resource_ledger.get("budget_exceeded", False))
    primary_control = choose_control_output(
        boundary,
        float(confidence["final_research_confidence"]),
        information_gain,
        resource_utility,
        budget_exceeded,
    )
    secondary_controls: list[str] = []
    if disagreement >= 0.5:
        secondary_controls.append("ADD_ADVERSARY")
    if unknown_dimensions > 0:
        secondary_controls.append("EXPAND_EVIDENCE")
    if float(confidence["causal_confidence"]) < 0.5:
        secondary_controls.append("REPLAY_HISTORY")
    return {
        "artifact_type": "metacognitive_evaluation",
        "metacognition_version": "dopey-metacognition-v1",
        "knowledge_boundary": boundary.value,
        "difficulty": difficulty,
        "confidence": confidence,
        "calibration": calibration,
        "selected_strategy": select_strategy(objective_type, boundary, str(difficulty["level"])),
        "expected_information_gain": information_gain,
        "research_utility": resource_utility,
        "primary_control": primary_control.value,
        "secondary_controls": sorted(set(secondary_controls)),
        "readiness_effect": "none_protected_gate_not_read_or_written",
        "paper_only": True,
        "live_blocked": True,
        "promotion_allowed": False,
    }
