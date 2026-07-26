"""Operator-reviewable deterministic organism templates."""

from __future__ import annotations

from dopey.constitution.authority import Authority
from dopey.protocols.agents import AgentContract, validate_agent_contract


def _contract(
    agent_id: str,
    role: str,
    authority: Authority,
    inputs: tuple[str, ...],
    outputs: tuple[str, ...],
    evidence_requirements: tuple[str, ...],
) -> AgentContract:
    contract = AgentContract(
        agent_id=agent_id,
        role=role,
        authority=authority,
        inputs=inputs,
        outputs=outputs,
        clock_domain="daily",
        resource_budget={"data_reads": 5000, "wall_seconds": 10.0, "tokens": 0},
        evidence_requirements=evidence_requirements,
        failure_policy="ABSTAIN",
        capabilities=("read_typed_local_evidence", "emit_typed_research_messages"),
        agent_version="dopey-deterministic-agent-v1",
    )
    validate_agent_contract(contract)
    return contract


def breakout_organism_template() -> tuple[AgentContract, ...]:
    contracts = (
        _contract(
            "technical_evidence_agent",
            "normalize multi-timeframe technical evidence",
            Authority.OBSERVE,
            ("multi_timeframe_technical_evidence",),
            ("MEASUREMENT", "DATA_GAP"),
            ("technical_measurement",),
        ),
        _contract(
            "regime_agent",
            "interpret shared world-model context",
            Authority.RESEARCH,
            ("shared_market_world_model",),
            ("OBSERVATION", "UNCERTAINTY"),
            ("shared_market_world_model",),
        ),
        _contract(
            "bull_hypothesis_agent",
            "form the strongest supported bull hypothesis",
            Authority.RESEARCH,
            ("multi_timeframe_technical_evidence", "shared_market_world_model"),
            ("HYPOTHESIS",),
            ("technical_measurement", "shared_market_world_model"),
        ),
        _contract(
            "bear_hypothesis_agent",
            "form the strongest supported bear hypothesis",
            Authority.RESEARCH,
            ("multi_timeframe_technical_evidence", "shared_market_world_model"),
            ("HYPOTHESIS",),
            ("technical_measurement", "shared_market_world_model"),
        ),
        _contract(
            "neutral_unknown_agent",
            "preserve neutral and unknown hypotheses",
            Authority.RESEARCH,
            ("multi_timeframe_technical_evidence", "shared_market_world_model"),
            ("HYPOTHESIS", "UNCERTAINTY", "DATA_GAP"),
            ("technical_measurement", "shared_market_world_model"),
        ),
        _contract(
            "adversarial_agent",
            "attack all directional hypotheses and expose omitted evidence",
            Authority.ADVERSARIAL_REVIEW,
            ("hypotheses", "shared_market_world_model"),
            ("COUNTEREVIDENCE", "VETO", "DATA_GAP"),
            ("technical_measurement", "shared_market_world_model"),
        ),
        _contract(
            "synthesizer_agent",
            "synthesize probabilities without action or execution authority",
            Authority.RESEARCH,
            ("hypotheses", "counterevidence"),
            ("OBSERVATION", "UNCERTAINTY"),
            ("technical_measurement", "shared_market_world_model"),
        ),
    )
    return contracts


SPECIALIST_ROLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "structure_agent": ("evaluate structure and probabilistic pattern evidence", ("technical_structure_pattern_evidence",)),
    "momentum_agent": ("evaluate normalized multi-timeframe momentum", ("technical_measurement",)),
    "volume_participation_agent": ("evaluate volume participation and profile evidence", ("technical_measurement", "technical_structure_pattern_evidence")),
    "relative_strength_agent": ("evaluate relative strength context", ("cross_sectional_market_context",)),
    "options_context_agent": ("evaluate options surface evidence when present", ("validated_options_surface",)),
    "fundamental_context_agent": ("evaluate point-in-time fundamental evidence when present", ("validated_fundamental_evidence",)),
    "macro_sensitivity_agent": ("evaluate macro and cross-asset sensitivity", ("shared_market_world_model",)),
    "earnings_event_agent": ("evaluate point-in-time earnings event evidence", ("validated_earnings_event",)),
    "positioning_agent": ("evaluate positioning and crowding evidence", ("shared_market_world_model",)),
    "liquidity_agent": ("evaluate liquidity and fragility evidence", ("shared_market_world_model",)),
    "calibration_agent": ("challenge confidence using settled calibration evidence", ("calibration_summary",)),
    "knowledge_boundary_agent": ("identify unavailable or out-of-distribution evidence", ("shared_market_world_model",)),
}


OBJECTIVE_SPECIALISTS: dict[str, tuple[str, ...]] = {
    "breakout": (
        "structure_agent", "momentum_agent", "volume_participation_agent", "relative_strength_agent",
        "options_context_agent", "fundamental_context_agent", "calibration_agent",
    ),
    "pullback": (
        "structure_agent", "momentum_agent", "volume_participation_agent", "relative_strength_agent", "calibration_agent",
    ),
    "fundamental_deterioration": (
        "fundamental_context_agent", "liquidity_agent", "options_context_agent", "positioning_agent", "calibration_agent",
    ),
    "volatility_expansion": (
        "structure_agent", "momentum_agent", "options_context_agent", "liquidity_agent", "calibration_agent",
    ),
    "crowded_reversal": (
        "positioning_agent", "structure_agent", "volume_participation_agent", "liquidity_agent", "calibration_agent",
    ),
    "macro_sensitive_equity": (
        "macro_sensitivity_agent", "liquidity_agent", "relative_strength_agent", "fundamental_context_agent", "calibration_agent",
    ),
    "earnings_event": (
        "earnings_event_agent", "fundamental_context_agent", "options_context_agent", "liquidity_agent", "calibration_agent",
    ),
    "options_dislocation": (
        "options_context_agent", "structure_agent", "liquidity_agent", "positioning_agent", "calibration_agent",
    ),
}


def dynamic_organism_template(
    objective_type: str,
    include_knowledge_boundary_agent: bool,
) -> tuple[AgentContract, ...]:
    if objective_type not in OBJECTIVE_SPECIALISTS:
        raise ValueError(
            "research objective has no governed deterministic morphology: "
            f"objective_type={objective_type}, supported={sorted(OBJECTIVE_SPECIALISTS)}"
        )
    core = breakout_organism_template()
    specialist_ids = list(OBJECTIVE_SPECIALISTS[objective_type])
    if include_knowledge_boundary_agent and "knowledge_boundary_agent" not in specialist_ids:
        specialist_ids.append("knowledge_boundary_agent")
    specialists = tuple(
        _contract(
            agent_id,
            SPECIALIST_ROLES[agent_id][0],
            Authority.RESEARCH,
            SPECIALIST_ROLES[agent_id][1],
            ("OBSERVATION", "UNCERTAINTY", "DATA_GAP"),
            SPECIALIST_ROLES[agent_id][1],
        )
        for agent_id in specialist_ids
    )
    return core + specialists
