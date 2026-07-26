"""Typed immutable schema for reusable research architectures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from dopey.protocols.identity import canonical_hash


class PromotionState(StrEnum):
    EXPERIMENTAL = "EXPERIMENTAL"
    QUARANTINED = "QUARANTINED"
    SHADOW_ONLY = "SHADOW_ONLY"
    REPLAY_VALIDATED = "REPLAY_VALIDATED"
    PRIVATE_VALIDATED = "PRIVATE_VALIDATED"
    EXTERNAL_VALIDATED = "EXTERNAL_VALIDATED"
    HELD_OUT_VALIDATED = "HELD_OUT_VALIDATED"
    FORWARD_PAPER = "FORWARD_PAPER"
    CONTESTED_VALIDATED = "CONTESTED_VALIDATED"
    CALIBRATED = "CALIBRATED"
    RESEARCH_APPROVED = "RESEARCH_APPROVED"
    DEGRADED = "DEGRADED"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class ResearchGenome:
    genome_id: str
    genome_version: str
    parent_ids: tuple[str, ...]
    generation: int
    agent_ids: tuple[str, ...]
    analysis_order: tuple[str, ...]
    indicator_ids: tuple[str, ...]
    timeframes: tuple[str, ...]
    evidence_budget_units: int
    stopping_rule: str
    calibration_method: str
    synthesis_rule: str
    model_tier: str
    data_lane_priorities: tuple[str, ...]
    morphology_rule: str
    world_model_update_policy: str
    regime_strategy: str
    prompt_bundle_version: str
    disagreement_rule: str
    promotion_state: PromotionState
    content_hash: str
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["promotion_state"] = self.promotion_state.value
        return record


def _body(
    parent_ids: tuple[str, ...],
    generation: int,
    agent_ids: tuple[str, ...],
    analysis_order: tuple[str, ...],
    indicator_ids: tuple[str, ...],
    timeframes: tuple[str, ...],
    evidence_budget_units: int,
    stopping_rule: str,
    calibration_method: str,
    synthesis_rule: str,
    model_tier: str,
    data_lane_priorities: tuple[str, ...],
    morphology_rule: str,
    world_model_update_policy: str,
    regime_strategy: str,
    prompt_bundle_version: str,
    disagreement_rule: str,
    promotion_state: PromotionState,
) -> dict[str, Any]:
    return {
        "genome_version": "dopey-research-genome-v1",
        "parent_ids": list(parent_ids),
        "generation": generation,
        "agent_ids": list(agent_ids),
        "analysis_order": list(analysis_order),
        "indicator_ids": list(indicator_ids),
        "timeframes": list(timeframes),
        "evidence_budget_units": evidence_budget_units,
        "stopping_rule": stopping_rule,
        "calibration_method": calibration_method,
        "synthesis_rule": synthesis_rule,
        "model_tier": model_tier,
        "data_lane_priorities": list(data_lane_priorities),
        "morphology_rule": morphology_rule,
        "world_model_update_policy": world_model_update_policy,
        "regime_strategy": regime_strategy,
        "prompt_bundle_version": prompt_bundle_version,
        "disagreement_rule": disagreement_rule,
        "promotion_state": promotion_state.value,
        "paper_only": True,
        "live_blocked": True,
    }


def build_research_genome(
    parent_ids: tuple[str, ...],
    generation: int,
    agent_ids: tuple[str, ...],
    analysis_order: tuple[str, ...],
    indicator_ids: tuple[str, ...],
    timeframes: tuple[str, ...],
    evidence_budget_units: int,
    stopping_rule: str,
    calibration_method: str,
    synthesis_rule: str,
    model_tier: str,
    data_lane_priorities: tuple[str, ...],
    morphology_rule: str,
    world_model_update_policy: str,
    regime_strategy: str,
    prompt_bundle_version: str,
    disagreement_rule: str,
    promotion_state: PromotionState,
) -> ResearchGenome:
    if generation < 0 or evidence_budget_units <= 0:
        raise ValueError(
            "genome generation and budget are invalid: "
            f"generation={generation}, evidence_budget_units={evidence_budget_units}"
        )
    required_collections = {
        "agent_ids": agent_ids,
        "analysis_order": analysis_order,
        "indicator_ids": indicator_ids,
        "timeframes": timeframes,
        "data_lane_priorities": data_lane_priorities,
    }
    empty = sorted(name for name, values in required_collections.items() if not values)
    if empty:
        raise ValueError(f"genome requires non-empty architecture collections: empty={empty}")
    for name, values in required_collections.items():
        if len(values) != len(set(values)):
            raise ValueError(f"genome collection contains duplicates: field={name}, values={values}")
    if set(analysis_order) != set(agent_ids):
        raise ValueError("genome analysis order must contain every agent exactly once")
    body = _body(
        parent_ids,
        generation,
        agent_ids,
        analysis_order,
        indicator_ids,
        timeframes,
        evidence_budget_units,
        stopping_rule,
        calibration_method,
        synthesis_rule,
        model_tier,
        data_lane_priorities,
        morphology_rule,
        world_model_update_policy,
        regime_strategy,
        prompt_bundle_version,
        disagreement_rule,
        promotion_state,
    )
    content_hash = canonical_hash(body)
    return ResearchGenome(
        genome_id=f"research-genome:{content_hash[:24]}",
        content_hash=content_hash,
        **{key: value for key, value in body.items() if key not in {"parent_ids", "agent_ids", "analysis_order", "indicator_ids", "timeframes", "data_lane_priorities", "promotion_state"}},
        parent_ids=parent_ids,
        agent_ids=agent_ids,
        analysis_order=analysis_order,
        indicator_ids=indicator_ids,
        timeframes=timeframes,
        data_lane_priorities=data_lane_priorities,
        promotion_state=promotion_state,
    )
