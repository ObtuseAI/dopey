"""Typed records for autonomous recursive strategy research."""

from __future__ import annotations

from typing import Literal, TypedDict


ResearchFindingType = Literal[
    "FAILURE",
    "SUCCESS",
    "BACKTEST",
    "RESEARCH",
    "CALIBRATION",
    "SETTLEMENT",
]


class ResearchLineage(TypedDict):
    lineage_id: str
    objective: str
    seed_genes: tuple[str, ...]
    mutation_operators: tuple[str, ...]


class StrategyBlueprint(TypedDict):
    strategy_id: str
    lineage_id: str
    generation: int
    parent_ids: tuple[str, ...]
    objective: str
    genes: tuple[str, ...]
    mutation_operator: str
    evidence_parent_ids: tuple[str, ...]
    activation_state: str
    automatic_research_activation_allowed: bool
    candidate_may_grade_itself: bool
    paper_only: bool
    live_blocked: bool


class ResearchFinding(TypedDict):
    finding_id: str
    finding_type: ResearchFindingType
    lineage_id: str
    target_gene: str
    direction: str
    evidence_id: str


class EvaluationTask(TypedDict):
    partition: str
    purpose: str
    item_level_feedback_visible: bool
    selection_authority: bool
    required_checks: tuple[str, ...]
