"""Constitutionally bounded genome inheritance."""

from __future__ import annotations

from typing import Any

from dopey.constitution.mutation_protection import assert_mutation_proposal_safe

from .schema import PromotionState, ResearchGenome, build_research_genome


SURFACE_FIELD: dict[str, str] = {
    "agent_prompts": "prompt_bundle_version",
    "agent_composition": "agent_ids",
    "research_ordering": "analysis_order",
    "technical_composites": "indicator_ids",
    "regime_strategies": "regime_strategy",
    "evidence_budgets": "evidence_budget_units",
    "model_selection": "model_tier",
    "stopping_policies": "stopping_rule",
    "disagreement_resolution": "disagreement_rule",
    "calibration_models": "calibration_method",
    "data_lane_priorities": "data_lane_priorities",
    "morphology_rules": "morphology_rule",
    "world_model_update_policies": "world_model_update_policy",
}


def inherit_genome(
    parent: ResearchGenome,
    surface: str,
    value: Any,
    mutation_id: str,
) -> ResearchGenome:
    proposal = {
        "surface": surface,
        "auto_apply": False,
        "promotion_state": "EXPERIMENTAL",
        "mutation_id": mutation_id,
    }
    assert_mutation_proposal_safe(proposal)
    if surface not in SURFACE_FIELD:
        raise ValueError(f"genome inheritance has no field for evolvable surface: surface={surface}")
    values = parent.to_dict()
    field = SURFACE_FIELD[surface]
    values[field] = value
    tuple_fields = {"agent_ids", "analysis_order", "indicator_ids", "timeframes", "data_lane_priorities"}
    for tuple_field in tuple_fields:
        values[tuple_field] = tuple(values[tuple_field])
    if surface == "agent_composition" and set(values["analysis_order"]) != set(values["agent_ids"]):
        values["analysis_order"] = tuple(values["agent_ids"])
    return build_research_genome(
        (parent.genome_id,),
        parent.generation + 1,
        values["agent_ids"],
        values["analysis_order"],
        values["indicator_ids"],
        values["timeframes"],
        int(values["evidence_budget_units"]),
        str(values["stopping_rule"]),
        str(values["calibration_method"]),
        str(values["synthesis_rule"]),
        str(values["model_tier"]),
        values["data_lane_priorities"],
        str(values["morphology_rule"]),
        str(values["world_model_update_policy"]),
        str(values["regime_strategy"]),
        str(values["prompt_bundle_version"]),
        str(values["disagreement_rule"]),
        PromotionState.EXPERIMENTAL,
    )
