"""Run the fixed vNext organism as pure deterministic research functions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dopey.chronos.clocks import ClockStamp
from dopey.protocols.agents import AgentContract, AgentResult, AgentRuntime, validate_agent_result
from dopey.protocols.identity import build_causal_identity, canonical_hash
from dopey.protocols.messages import MessageType, ResearchMessage


def _complete_evidence_ids(technical: Mapping[str, Any], world_model: Mapping[str, Any]) -> tuple[str, ...]:
    evidence_ids = {
        str(record["evidence_id"])
        for record in technical.get("measurements", [])
        if record.get("measurement_status") == "complete"
    }
    if world_model.get("evidence_id"):
        evidence_ids.add(str(world_model["evidence_id"]))
    evidence_ids.update(
        str(record["evidence_id"])
        for record in technical.get("structure_pattern_evidence", [])
        if record.get("evidence_id")
    )
    return tuple(sorted(evidence_ids))


def _hypothesis_probabilities(
    technical: Mapping[str, Any],
    world_model: Mapping[str, Any],
) -> dict[str, float]:
    fusion = technical.get("fusion_states", {})
    directional = [
        str(fusion.get(indicator, "mixed_or_neutral"))
        for indicator in ("MACD_HISTOGRAM", "DMI_SPREAD", "ROC", "OBV_SLOPE", "CHAIKIN_MONEY_FLOW")
    ]
    positive = sum("positive" in state for state in directional) / len(directional)
    negative = sum("negative" in state for state in directional) / len(directional)
    unknown_dimensions = int(world_model.get("unknown_dimension_count", 0) or 0)
    known_dimensions = int(world_model.get("known_dimension_count", 0) or 0)
    total_dimensions = max(unknown_dimensions + known_dimensions, 1)
    unknown_fraction = unknown_dimensions / total_dimensions
    contradiction_pressure = min(0.4, 0.1 * len(world_model.get("contradictions", [])))
    raw = {
        "bull": 0.15 + 0.55 * positive * (1.0 - contradiction_pressure),
        "bear": 0.15 + 0.55 * negative * (1.0 - contradiction_pressure),
        "neutral": 0.2 + 0.25 * (1.0 - max(positive, negative)),
        "unknown": 0.1 + 0.6 * unknown_fraction,
    }
    total = sum(raw.values())
    return {name: round(value / total, 6) for name, value in raw.items()}


def _fusion_signal(technical: Mapping[str, Any], indicators: Sequence[str]) -> float:
    fusion = technical.get("fusion_states", {})
    states = [str(fusion.get(indicator, "mixed_or_neutral")) for indicator in indicators]
    positive = sum("positive" in state or "bull" in state for state in states)
    negative = sum("negative" in state or "bear" in state for state in states)
    return (positive - negative) / max(len(states), 1)


def _world_signal(world_model: Mapping[str, Any], dimensions: Sequence[str]) -> float:
    positive_terms = ("uptrend", "positive", "firm", "broad", "contained", "strengthening")
    negative_terms = ("downtrend", "negative", "aversion", "narrow", "elevated", "weakening", "stressed")
    scores: list[float] = []
    regimes = world_model.get("regimes", {})
    for dimension in dimensions:
        record = regimes.get(dimension, {}) if isinstance(regimes, Mapping) else {}
        state = str(record.get("state", "unknown")) if isinstance(record, Mapping) else "unknown"
        probability = float(record.get("probability", 0.0) or 0.0) if isinstance(record, Mapping) else 0.0
        direction = 1.0 if any(term in state for term in positive_terms) else -1.0 if any(term in state for term in negative_terms) else 0.0
        scores.append(direction * probability)
    return sum(scores) / len(scores) if scores else 0.0


def _fundamental_signal(evidence: Mapping[str, Any]) -> float:
    values = evidence.get("values", {})
    metrics = values.get("metrics", {}) if isinstance(values, Mapping) else {}
    if not isinstance(metrics, Mapping):
        return 0.0
    components: list[float] = []
    revenue_growth = metrics.get("revenue_growth")
    profit_margin = metrics.get("profit_margin")
    free_cashflow = metrics.get("free_cashflow")
    if revenue_growth is not None:
        components.append(max(-1.0, min(1.0, float(revenue_growth) * 4.0)))
    if profit_margin is not None:
        components.append(max(-1.0, min(1.0, float(profit_margin) * 3.0)))
    if free_cashflow is not None:
        components.append(0.35 if float(free_cashflow) > 0.0 else -0.35)
    return sum(components) / len(components) if components else 0.0


def _specialist_contribution(
    agent_id: str,
    specialist_evidence: Mapping[str, Mapping[str, Any]],
) -> float:
    technical = specialist_evidence.get("technical_measurement", {})
    world_model = specialist_evidence.get("shared_market_world_model", {})
    fundamental = specialist_evidence.get("validated_fundamental_evidence", {})
    raw = (
        _fusion_signal(technical, ("MACD_HISTOGRAM", "DMI_SPREAD", "ROC"))
        if agent_id == "momentum_agent"
        else _fusion_signal(technical, ("OBV_SLOPE", "CHAIKIN_MONEY_FLOW"))
        if agent_id == "volume_participation_agent"
        else _world_signal(world_model, ("equity_trend", "market_fragility"))
        if agent_id == "structure_agent"
        else _fundamental_signal(fundamental)
        if agent_id == "fundamental_context_agent"
        else _world_signal(world_model, ("growth", "rates", "dollar", "credit"))
        if agent_id == "macro_sensitivity_agent"
        else _world_signal(world_model, ("crowding",))
        if agent_id == "positioning_agent"
        else _world_signal(world_model, ("liquidity", "market_fragility"))
        if agent_id == "liquidity_agent"
        else 0.0
    )
    return round(max(-1.0, min(1.0, raw)), 6)


def _specialist_evidence_ids(
    contract: AgentContract,
    specialist_evidence: Mapping[str, Mapping[str, Any]],
    shared_evidence_ids: tuple[str, ...],
) -> tuple[str, ...]:
    references = set(shared_evidence_ids)
    for evidence_type in contract.evidence_requirements:
        record = specialist_evidence.get(evidence_type)
        if record is None:
            continue
        evidence_id = str(record.get("evidence_id", "")).strip()
        if evidence_id:
            references.add(evidence_id)
            continue
        reproducibility_hash = str(record.get("reproducibility_hash", "")).strip()
        identity = reproducibility_hash or canonical_hash(record)
        references.add(f"{evidence_type}:{identity[:24]}")
    return tuple(sorted(references))


def _apply_specialist_contributions(
    base: Mapping[str, float],
    contributions: Mapping[str, float],
) -> dict[str, float]:
    aggregate = sum(float(value) for value in contributions.values()) / max(len(contributions), 1)
    adjustment = max(-0.12, min(0.12, aggregate * 0.12))
    raw = {
        "bull": max(0.01, float(base["bull"]) + max(adjustment, 0.0)),
        "bear": max(0.01, float(base["bear"]) + max(-adjustment, 0.0)),
        "neutral": float(base["neutral"]),
        "unknown": float(base["unknown"]),
    }
    total = sum(raw.values())
    return {name: round(value / total, 6) for name, value in raw.items()}


def _message(
    sender: str,
    target: str,
    semantic_type: MessageType,
    content: dict[str, Any],
    evidence_ids: tuple[str, ...],
    confidence: float,
    clock: ClockStamp,
) -> ResearchMessage:
    causal = build_causal_identity(
        clock.parent_event_id,
        clock.session_id,
        clock.event_time,
        clock.market_time,
        clock.data_version,
        sender,
        clock.policy_version,
        clock.model_version,
    )
    message_body = {
        "sender": sender,
        "target": target,
        "semantic_type": semantic_type.value,
        "content": content,
        "evidence_ids": evidence_ids,
        "confidence": confidence,
        "causal_event_id": causal.event_id,
    }
    return ResearchMessage(
        message_id=canonical_hash(message_body),
        sender=sender,
        target=target,
        semantic_type=semantic_type,
        content=content,
        evidence_ids=evidence_ids,
        confidence=confidence,
        provenance="deterministic_vnext_organism",
        causal_identity=causal,
    )


def _result(
    agent_id: str,
    status: str,
    observations: tuple[ResearchMessage, ...],
    claims: tuple[ResearchMessage, ...],
    counterevidence: tuple[ResearchMessage, ...],
    uncertainties: tuple[ResearchMessage, ...],
    requested_followups: tuple[ResearchMessage, ...],
    confidence: float,
    evidence_ids: tuple[str, ...],
    data_reads: int,
) -> AgentResult:
    result = AgentResult(
        agent_id=agent_id,
        status=status,
        observations=observations,
        claims=claims,
        counterevidence=counterevidence,
        uncertainties=uncertainties,
        requested_followups=requested_followups,
        confidence=confidence,
        evidence_ids=evidence_ids,
        runtime=AgentRuntime(
            seconds=0.0,
            tokens=0,
            data_reads=data_reads,
            cpu_seconds=0.0,
            peak_memory_mb=0.0,
        ),
        paper_only=True,
        live_blocked=True,
    )
    validate_agent_result(result)
    return result


def _specialist_result(
    contract: AgentContract,
    available_evidence_types: set[str],
    evidence_ids: tuple[str, ...],
    clock: ClockStamp,
    contribution: float,
) -> AgentResult:
    missing = sorted(set(contract.evidence_requirements) - available_evidence_types)
    if missing:
        message = _message(
            contract.agent_id,
            "metacognitive_evaluator",
            MessageType.DATA_GAP,
            {
                "role": contract.role,
                "missing_evidence_types": missing,
                "unsupported_conclusion_emitted": False,
            },
            evidence_ids,
            0.0,
            clock,
        )
        return _result(
            contract.agent_id,
            "completed_with_data_gap",
            (),
            (),
            (),
            (message,),
            (message,),
            0.0,
            evidence_ids,
            len(evidence_ids),
        )
    message = _message(
        contract.agent_id,
        "synthesizer_agent",
        MessageType.OBSERVATION,
        {
            "role": contract.role,
            "evidence_requirements_satisfied": list(contract.evidence_requirements),
            "action_recommendation": "none_research_only",
            "precommitted_directional_contribution": contribution,
            "contribution_requires_forward_ablation_settlement": True,
        },
        evidence_ids,
        min(0.75, 0.4 + 0.03 * len(evidence_ids)),
        clock,
    )
    return _result(
        contract.agent_id,
        "completed",
        (message,),
        (),
        (),
        (),
        (),
        message.confidence,
        evidence_ids,
        len(evidence_ids),
    )


def run_research_organism(
    objective_type: str,
    symbol: str,
    contracts: Sequence[AgentContract],
    technical_evidence: Mapping[str, Any],
    world_model: Mapping[str, Any],
    clock: ClockStamp,
    available_evidence_types: tuple[str, ...],
    specialist_evidence: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], tuple[AgentResult, ...]]:
    contract_ids = {contract.agent_id for contract in contracts}
    required_ids = {
        "technical_evidence_agent",
        "regime_agent",
        "bull_hypothesis_agent",
        "bear_hypothesis_agent",
        "neutral_unknown_agent",
        "adversarial_agent",
        "synthesizer_agent",
    }
    missing_contracts = sorted(required_ids - contract_ids)
    if missing_contracts:
        raise ValueError(f"organism template is incomplete: missing_agent_ids={missing_contracts}")
    evidence_ids = _complete_evidence_ids(technical_evidence, world_model)
    base_probabilities = _hypothesis_probabilities(technical_evidence, world_model)
    specialist_contracts = tuple(contract for contract in contracts if contract.agent_id not in required_ids)
    available = set(available_evidence_types)
    contributions = {
        contract.agent_id: (
            _specialist_contribution(contract.agent_id, specialist_evidence)
            if set(contract.evidence_requirements) <= available
            else 0.0
        )
        for contract in specialist_contracts
    }
    probabilities = _apply_specialist_contributions(base_probabilities, contributions)
    ablation_hypotheses = {
        agent_id: _apply_specialist_contributions(
            base_probabilities,
            {name: value for name, value in contributions.items() if name != agent_id},
        )
        for agent_id in sorted(contributions)
    }
    measurement_count = int(technical_evidence.get("measurement_count", 0) or 0)
    known_count = int(world_model.get("known_dimension_count", 0) or 0)
    unknown_count = int(world_model.get("unknown_dimension_count", 0) or 0)
    technical_observation = _message(
        "technical_evidence_agent",
        "organism",
        MessageType.MEASUREMENT,
        {
            "symbol": symbol,
            "measurement_count": measurement_count,
            "fusion_states": dict(technical_evidence.get("fusion_states", {})),
        },
        evidence_ids,
        min(0.9, len(evidence_ids) / max(measurement_count, 1)),
        clock,
    )
    regime_observation = _message(
        "regime_agent",
        "organism",
        MessageType.OBSERVATION,
        {
            "known_dimension_count": known_count,
            "unknown_dimension_count": unknown_count,
            "contradictions": list(world_model.get("contradictions", [])),
        },
        (str(world_model["evidence_id"]),),
        known_count / max(known_count + unknown_count, 1),
        clock,
    )
    bull = _message(
        "bull_hypothesis_agent",
        "adversarial_agent",
        MessageType.HYPOTHESIS,
        {
            "hypothesis": "bull",
            "probability": probabilities["bull"],
            "failure_condition": "positive technical evidence fails or world-model contradiction strengthens",
        },
        evidence_ids,
        probabilities["bull"],
        clock,
    )
    bear = _message(
        "bear_hypothesis_agent",
        "adversarial_agent",
        MessageType.HYPOTHESIS,
        {
            "hypothesis": "bear",
            "probability": probabilities["bear"],
            "failure_condition": "negative technical evidence reverses or higher-timeframe support persists",
        },
        evidence_ids,
        probabilities["bear"],
        clock,
    )
    neutral = _message(
        "neutral_unknown_agent",
        "adversarial_agent",
        MessageType.HYPOTHESIS,
        {
            "hypothesis": "neutral",
            "probability": probabilities["neutral"],
            "failure_condition": "directional evidence converges across timeframes",
        },
        evidence_ids,
        probabilities["neutral"],
        clock,
    )
    unknown = _message(
        "neutral_unknown_agent",
        "adversarial_agent",
        MessageType.HYPOTHESIS,
        {
            "hypothesis": "unknown",
            "probability": probabilities["unknown"],
            "missing_world_dimensions": [
                name
                for name, record in world_model.get("regimes", {}).items()
                if record.get("state") == "unknown"
            ],
        },
        evidence_ids,
        probabilities["unknown"],
        clock,
    )
    counterevidence = _message(
        "adversarial_agent",
        "synthesizer_agent",
        MessageType.COUNTEREVIDENCE,
        {
            "world_model_contradictions": list(world_model.get("contradictions", [])),
            "unknown_dimension_count": unknown_count,
            "consensus_is_not_proof": True,
        },
        evidence_ids,
        min(1.0, 0.35 + 0.08 * unknown_count),
        clock,
    )
    dominant = max(probabilities, key=lambda name: probabilities[name])
    synthesis = _message(
        "synthesizer_agent",
        "metacognitive_evaluator",
        MessageType.OBSERVATION,
        {
            "hypothesis_probabilities": probabilities,
            "dominant_hypothesis": dominant,
            "action_recommendation": "none_research_only",
            "settlement_required": True,
        },
        evidence_ids,
        probabilities[dominant],
        clock,
    )
    core_results = (
        _result("technical_evidence_agent", "completed", (technical_observation,), (), (), (), (), technical_observation.confidence, evidence_ids, measurement_count),
        _result("regime_agent", "completed", (regime_observation,), (), (), (), (), regime_observation.confidence, evidence_ids, known_count + unknown_count),
        _result("bull_hypothesis_agent", "completed", (), (bull,), (), (), (), bull.confidence, evidence_ids, len(evidence_ids)),
        _result("bear_hypothesis_agent", "completed", (), (bear,), (), (), (), bear.confidence, evidence_ids, len(evidence_ids)),
        _result("neutral_unknown_agent", "completed", (), (neutral, unknown), (), (unknown,), (), max(neutral.confidence, unknown.confidence), evidence_ids, len(evidence_ids)),
        _result("adversarial_agent", "completed", (), (), (counterevidence,), (), (), counterevidence.confidence, evidence_ids, len(evidence_ids)),
        _result("synthesizer_agent", "completed", (synthesis,), (), (), (), (), synthesis.confidence, evidence_ids, len(evidence_ids)),
    )
    specialist_results = tuple(
        _specialist_result(
            contract,
            available,
            _specialist_evidence_ids(contract, specialist_evidence, evidence_ids),
            clock,
            contributions[contract.agent_id],
        )
        for contract in specialist_contracts
    )
    results = core_results + specialist_results
    body: dict[str, Any] = {
        "artifact_type": "dynamic_research_organism_episode",
        "organism_version": "dopey-dynamic-organism-v2",
        "objective_type": objective_type,
        "symbol": symbol,
        "organism_status": "completed_awaiting_settlement",
        "agent_contracts": [contract.to_dict() for contract in contracts],
        "agent_results": [result.to_dict() for result in results],
        "hypotheses": probabilities,
        "base_hypotheses": base_probabilities,
        "agent_contributions": contributions,
        "agent_ablation_hypotheses": ablation_hypotheses,
        "ablation_policy": "precommitted_remove_one_specialist_before_forward_outcome",
        "dominant_hypothesis": dominant,
        "unresolved_uncertainty": [
            name
            for name, record in world_model.get("regimes", {}).items()
            if record.get("state") == "unknown"
        ],
        "counterevidence": list(world_model.get("contradictions", [])),
        "specialist_agent_count": len(specialist_results),
        "specialist_data_gap_count": sum(result.status == "completed_with_data_gap" for result in specialist_results),
        "lifecycle": [
            "created",
            "evidence_acquired",
            "competing_hypotheses_formed",
            "hypotheses_attacked",
            "uncertainty_identified",
            "synthesized",
            "awaiting_prediction_record",
        ],
        "paper_only": True,
        "live_blocked": True,
        "action_recommendation": "none_research_only",
    }
    return {**body, "reproducibility_hash": canonical_hash(body)}, results
