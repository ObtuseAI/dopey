"""Durable autonomous promotion evaluation over accumulated evidence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from dopey.protocols.identity import canonical_hash

from .registry import append_activation_decision
from .runtime import build_autonomous_promotion_matrix
from .schema import (
    StrategyPromotionEvidence,
    SymbolPromotionEvidence,
    SymbolStrategyPromotionEvidence,
)
from .thresholds import AUTONOMOUS_PROMOTION_THRESHOLDS


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_array(record: dict[str, Any], key: str, path: Path) -> list[dict[str, Any]]:
    value = record.get(key)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"promotion evidence requires an object array: path={path}, key={key}")
    return [dict(item) for item in value]


def _activated_blueprints(
    raw: dict[str, Any],
    activated_strategy_ids: list[str],
    evidence_path: Path,
) -> list[dict[str, Any]]:
    value = raw.get("strategy_blueprints", [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(
            f"promotion strategy_blueprints must be an object array: path={evidence_path}"
        )
    by_id = {str(record.get("strategy_id", "")): dict(record) for record in value}
    if len(by_id) != len(value):
        raise ValueError(f"promotion strategy_blueprints contain duplicate identities: path={evidence_path}")
    output: list[dict[str, Any]] = []
    for strategy_id in activated_strategy_ids:
        blueprint = by_id.get(strategy_id)
        if blueprint is None:
            continue
        output.append(
            {
                **blueprint,
                "activation_state": "RESEARCH_APPROVED",
                "automatic_research_activation_allowed": True,
                "candidate_may_grade_itself": False,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return output


def run_autonomous_promotion_cycle(
    evidence_path: Path,
    output_root: Path,
    issued_at: datetime,
) -> dict[str, Any]:
    if issued_at.tzinfo is None:
        raise ValueError("promotion cycle issued_at must be timezone-aware")
    if not evidence_path.exists():
        body: dict[str, Any] = {
            "artifact_type": "autonomous_research_promotion_cycle",
            "cycle_version": "dopey-autonomous-promotion-cycle-v1",
            "cycle_status": "missing_promotion_evidence",
            "issued_at": issued_at.isoformat(),
            "evidence_path": str(evidence_path),
            "automatic_research_activation_count": 0,
            "human_review_required": False,
            "candidate_self_activation_allowed": False,
            "readiness_effect": "none",
            "execution_effect": "none",
            "paper_only": True,
            "live_blocked": True,
        }
        missing_output = {**body, "cycle_hash": canonical_hash(body)}
        _write_json_atomic(output_root / "latest_promotion_cycle.json", missing_output)
        return missing_output
    raw: Any = json.loads(evidence_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"promotion evidence root must be an object: path={evidence_path}")
    symbols = cast(list[SymbolPromotionEvidence], _load_array(raw, "symbols", evidence_path))
    strategies = cast(list[StrategyPromotionEvidence], _load_array(raw, "strategies", evidence_path))
    pairs = cast(list[SymbolStrategyPromotionEvidence], _load_array(raw, "pairs", evidence_path))
    matrix = build_autonomous_promotion_matrix(
        symbols,
        strategies,
        pairs,
        AUTONOMOUS_PROMOTION_THRESHOLDS,
    )
    registry_path = output_root / "activation_decisions.jsonl"
    appended = 0
    for group in ("symbol_gates", "strategy_gates", "symbol_strategy_gates"):
        for decision in matrix[group]:
            if append_activation_decision(registry_path, decision):
                appended += 1
    activation_count = int(matrix["automatic_research_activation_count"])
    activated_blueprints = _activated_blueprints(
        raw,
        list(matrix["activated_strategy_ids"]),
        evidence_path,
    )
    if activated_blueprints:
        _write_json_atomic(output_root / "champion_strategies.json", activated_blueprints)
    body = {
        "artifact_type": "autonomous_research_promotion_cycle",
        "cycle_version": "dopey-autonomous-promotion-cycle-v1",
        "cycle_status": (
            "evaluation_complete_activated"
            if activation_count > 0
            else "evaluation_complete_no_activations"
        ),
        "evaluation_status": "complete",
        "issued_at": issued_at.isoformat(),
        "evidence_path": str(evidence_path),
        "matrix": matrix,
        "registry_appended_count": appended,
        "automatic_research_activation_count": activation_count,
        "activated_blueprint_count": len(activated_blueprints),
        "human_review_required": False,
        "candidate_self_activation_allowed": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    output = {**body, "cycle_hash": canonical_hash(body)}
    _write_json_atomic(output_root / "latest_promotion_cycle.json", output)
    return output
