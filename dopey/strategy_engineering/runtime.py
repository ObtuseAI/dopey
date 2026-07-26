"""One bounded strategy-engineering cycle over local paper evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from dopey.gates.evaluator import evaluate_gate
from dopey.gates.policy import policy_by_id
from dopey.protocols.identity import canonical_hash

from .forward import (
    build_evaluation_manifest,
    build_quality_diversity_archive,
    generate_forward_candidates,
)
from .institutional_intelligence import institutional_evaluation_contract
from .institutional_registry import (
    INSTITUTIONAL_DOCTRINES,
    INSTITUTIONAL_SOURCES,
    validate_institutional_registry,
)
from .reverse import build_reverse_cases, infer_reverse_hypotheses
from .source_registry import PRIMARY_SOURCES


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _candidate_gate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return evaluate_gate(
        policy_by_id("experiment_admission"),
        str(candidate["candidate_id"]),
        {
            "leakage_detected": False,
            "revised_data_contamination": False,
            "candidate_may_grade_itself": candidate["candidate_may_grade_itself"],
            "interpretable": bool(str(candidate["research_expression"]).strip()),
            "complexity_score": float(candidate["complexity_score"]),
        },
        tuple(
            str(value)
            for value in (*candidate["source_ids"], *candidate["evidence_parent_ids"])
        ),
    )


def run_strategy_engineering_cycle(
    predictions: Sequence[Mapping[str, Any]],
    settlements: Sequence[Mapping[str, Any]],
    output_root: Path,
    candidate_budget: int,
    minimum_reverse_support: int,
    issued_at: datetime,
) -> dict[str, Any]:
    if issued_at.tzinfo is None:
        raise ValueError("strategy engineering issued_at must be timezone-aware")
    validate_institutional_registry()
    cases = build_reverse_cases(predictions, settlements)
    reverse_report = infer_reverse_hypotheses(cases, minimum_reverse_support, 0.05, 24)
    reverse_hypotheses = tuple(
        record
        for record in reverse_report["hypotheses"]
        if record["hypothesis_status"] == "association_only_replay_required"
    )
    candidates = generate_forward_candidates(candidate_budget, reverse_hypotheses)
    gate_decisions = tuple(_candidate_gate(candidate) for candidate in candidates)
    archive = build_quality_diversity_archive(candidates)
    manifests = tuple(build_evaluation_manifest(candidate) for candidate in candidates)
    body: dict[str, Any] = {
        "artifact_type": "autonomous_strategy_engineering_cycle",
        "cycle_version": "dopey-strategy-engineering-cycle-v2",
        "cycle_status": "complete_shadow_only",
        "issued_at": issued_at.isoformat(),
        "reverse_report": reverse_report,
        "forward_candidate_count": len(candidates),
        "reverse_steered_candidate_count": sum(
            bool(candidate["evidence_parent_ids"]) for candidate in candidates
        ),
        "forward_candidates": candidates,
        "quality_diversity_archive": archive,
        "evaluation_manifests": manifests,
        "gate_decisions": gate_decisions,
        "shadow_admitted_count": sum(
            decision["decision"] == "SHADOW_ONLY" for decision in gate_decisions
        ),
        "source_registry": PRIMARY_SOURCES,
        "institutional_source_registry": INSTITUTIONAL_SOURCES,
        "institutional_doctrine_registry": INSTITUTIONAL_DOCTRINES,
        "institutional_evaluation_contract": institutional_evaluation_contract(),
        "institutional_council_required_before_private_selection": True,
        "source_claims_are_not_dopey_evidence": True,
        "positive_promotion_allowed": False,
        "operator_promotion_required": True,
        "order_construction_allowed": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    output = {**body, "cycle_hash": canonical_hash(body)}
    _write_json_atomic(output_root / "latest_reverse_report.json", reverse_report)
    _write_json_atomic(output_root / "latest_quality_diversity_archive.json", archive)
    _write_json_atomic(output_root / "latest_cycle.json", output)
    return output
