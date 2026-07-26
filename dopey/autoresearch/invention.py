"""Deterministic, evidence-steered invention of strategy challengers."""

from __future__ import annotations

from collections.abc import Sequence

from dopey.protocols.identity import canonical_hash

from .schema import ResearchFinding, StrategyBlueprint
from .taxonomy import RESEARCH_LINEAGES


_FINDING_OPERATORS: dict[str, str] = {
    "FAILURE": "repair_failure",
    "SUCCESS": "retain_success",
    "BACKTEST": "challenge_backtest",
    "RESEARCH": "expand_evidence",
    "CALIBRATION": "repair_calibration",
    "SETTLEMENT": "learn_forward_outcome",
}


def _validate_findings(findings: Sequence[ResearchFinding]) -> None:
    known_lineages = {record["lineage_id"] for record in RESEARCH_LINEAGES}
    for finding in findings:
        if finding["lineage_id"] not in known_lineages:
            raise ValueError(f"research finding references unknown lineage: lineage_id={finding['lineage_id']}")
        if finding["finding_type"] not in _FINDING_OPERATORS:
            raise ValueError(f"research finding has unknown type: finding_type={finding['finding_type']}")
        for field in ("finding_id", "target_gene", "direction", "evidence_id"):
            if not finding[field].strip():
                raise ValueError(f"research finding requires non-empty field: field={field}")


def invent_strategy_candidates(
    seeds: Sequence[StrategyBlueprint],
    findings: Sequence[ResearchFinding],
    candidate_budget: int,
    generation: int,
) -> tuple[StrategyBlueprint, ...]:
    if candidate_budget <= 0 or generation <= 0:
        raise ValueError(
            "strategy invention requires positive budget and generation: "
            f"candidate_budget={candidate_budget}, generation={generation}"
        )
    _validate_findings(findings)
    if not seeds:
        raise ValueError("strategy invention requires at least one seed")
    seed_by_lineage = {record["lineage_id"]: record for record in seeds}
    if len(seed_by_lineage) != len(seeds):
        raise ValueError("strategy invention requires one seed per lineage")
    lineage_order = tuple(record["lineage_id"] for record in RESEARCH_LINEAGES)
    missing = sorted(set(lineage_order) - set(seed_by_lineage))
    if missing:
        raise ValueError(f"strategy invention is missing seed lineages: lineages={missing}")
    finding_by_lineage: dict[str, ResearchFinding] = {}
    for finding in sorted(findings, key=lambda record: record["finding_id"]):
        finding_by_lineage.setdefault(finding["lineage_id"], finding)
    candidates: list[StrategyBlueprint] = []
    for index in range(candidate_budget):
        lineage_id = lineage_order[index % len(lineage_order)]
        mutation_variant = index // len(lineage_order)
        parent = seed_by_lineage[lineage_id]
        finding = finding_by_lineage.get(lineage_id)
        if finding is None:
            operator = "novelty_probe"
            mutation_gene = (
                f"novelty_probe:g{generation}:variant{mutation_variant}"
            )
            evidence_parent_ids: tuple[str, ...] = ()
        else:
            operator = _FINDING_OPERATORS[finding["finding_type"]]
            mutation_gene = (
                f"{operator}:{finding['target_gene']}:{finding['direction']}:"
                f"variant{mutation_variant}"
            )
            evidence_parent_ids = (finding["evidence_id"],)
        genes = (*parent["genes"], mutation_gene)
        identity = canonical_hash(
            {
                "lineage_id": lineage_id,
                "parent_id": parent["strategy_id"],
                "generation": generation,
                "genes": genes,
                "evidence_parent_ids": evidence_parent_ids,
            }
        )
        candidates.append(
            {
                "strategy_id": f"strategy:{lineage_id}:{identity[:16]}",
                "lineage_id": lineage_id,
                "generation": generation,
                "parent_ids": (parent["strategy_id"],),
                "objective": parent["objective"],
                "genes": genes,
                "mutation_operator": operator,
                "evidence_parent_ids": evidence_parent_ids,
                "activation_state": "EXPERIMENTAL",
                "automatic_research_activation_allowed": False,
                "candidate_may_grade_itself": False,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return tuple(candidates)
