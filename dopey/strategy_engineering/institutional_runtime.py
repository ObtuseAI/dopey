"""Artifact runtime for the paper-only institutional intelligence layer."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from dopey.protocols.identity import canonical_hash

from .institutional_intelligence import (
    allocate_research_gap_portfolio,
    institutional_evaluation_contract,
    synthesize_institutional_council,
)
from .institutional_registry import (
    INSTITUTIONAL_DOCTRINES,
    INSTITUTIONAL_SOURCES,
    validate_institutional_registry,
)
from .schema import CouncilObservation, ResearchGap, ThesisEscrow


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run_institutional_intelligence_cycle(
    theses: Sequence[ThesisEscrow],
    observations_by_candidate: Mapping[str, Sequence[CouncilObservation]],
    gaps: Sequence[ResearchGap],
    output_root: Path,
    research_budget_units: int,
    issued_at: datetime,
) -> dict[str, Any]:
    if issued_at.tzinfo is None:
        raise ValueError("institutional intelligence issued_at must be timezone-aware")
    validate_institutional_registry()
    thesis_ids = tuple(thesis["candidate_id"] for thesis in theses)
    if len(set(thesis_ids)) != len(thesis_ids):
        raise ValueError(
            "institutional intelligence requires unique thesis candidate identities"
        )
    orphan_observation_ids = sorted(set(observations_by_candidate) - set(thesis_ids))
    if orphan_observation_ids:
        raise ValueError(
            "institutional intelligence received observations for unknown candidates: "
            f"candidate_ids={orphan_observation_ids}"
        )
    council_syntheses = tuple(
        synthesize_institutional_council(
            thesis,
            observations_by_candidate.get(thesis["candidate_id"], ()),
        )
        for thesis in theses
    )
    gap_portfolio = allocate_research_gap_portfolio(gaps, research_budget_units)
    research_candidate_count = sum(
        synthesis["council_status"]
        == "research_candidate_requires_protected_evaluation"
        for synthesis in council_syntheses
    )
    body: dict[str, Any] = {
        "artifact_type": "institutional_intelligence_cycle",
        "cycle_version": "dopey-institutional-intelligence-cycle-v1",
        "cycle_status": "complete_research_only_gap_ranked",
        "issued_at": issued_at.isoformat(),
        "thesis_count": len(theses),
        "council_synthesis_count": len(council_syntheses),
        "research_candidate_count": research_candidate_count,
        "council_syntheses": council_syntheses,
        "gap_portfolio": gap_portfolio,
        "evaluation_contract": institutional_evaluation_contract(),
        "institutional_source_registry": INSTITUTIONAL_SOURCES,
        "institutional_doctrine_registry": INSTITUTIONAL_DOCTRINES,
        "source_count": len(INSTITUTIONAL_SOURCES),
        "doctrine_count": len(INSTITUTIONAL_DOCTRINES),
        "source_claims_are_not_dopey_evidence": True,
        "current_gap_snapshot_is_not_market_edge_evidence": True,
        "candidate_self_activation_allowed": False,
        "positive_promotion_allowed": False,
        "order_construction_allowed": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    output = {**body, "cycle_hash": canonical_hash(body)}
    _write_json_atomic(output_root / "latest_cycle.json", output)
    _write_json_atomic(output_root / "latest_gap_portfolio.json", gap_portfolio)
    return output
