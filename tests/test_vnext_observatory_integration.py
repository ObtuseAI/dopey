"""Integration coverage for the source-backed local vNext observatory."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from dopey.observatory.builder import build_observatory_artifact
from dopey.observatory.portable_html import (
    NORMALIZED_HEADER_WIDTH,
    PORTABLE_HEADER_WIDTH,
    READER_HEADER_OVERRIDE,
    normalize_portable_header_width,
)


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def test_observatory_materializes_verified_sql_sources_and_sealed_status(tmp_path: Path) -> None:
    output_dir = tmp_path / "operational"
    sources: dict[str, dict[str, Any]] = {
        "vnext_research_summary.json": {
            "paper_only": True,
            "live_blocked": True,
            "hypotheses": {"bull": 0.4, "bear": 0.2, "neutral": 0.2, "unknown": 0.2},
            "final_research_control": "ABSTAIN",
            "minimum_settlement_date": "2026-07-28",
        },
        "world_model.json": {
            "known_dimension_count": 1,
            "unknown_dimension_count": 1,
            "regimes": {
                "equity_trend": {"state": "supported", "probability": 0.7, "uncertainty": 0.3, "limitations": []},
                "options_dealer_state": {"state": "unknown", "probability": 0.0, "uncertainty": 1.0, "limitations": ["missing"]},
            },
        },
        "technical_evidence.json": {
            "measurement_count": 1,
            "measurements": [{"timeframe": "daily", "strength": 0.4}],
        },
        "organism_episode.json": {
            "agent_results": [{
                "agent_id": "technical_evidence_agent",
                "status": "completed",
                "confidence": 0.6,
                "runtime": {"data_reads": 1},
                "uncertainties": [],
                "requested_followups": [],
            }],
        },
        "metacognition.json": {
            "confidence": {
                "model": 0.5,
                "evidence_completeness": 0.6,
                "evidence_freshness": 1.0,
                "historical_analogue_quality": 0.3,
                "calibration_quality": 0.2,
                "causal_confidence": 0.2,
                "regime_familiarity": 0.3,
                "agent_disagreement": 0.4,
                "final_research_confidence": 0.12,
            },
        },
        "shadow_controller.json": {
            "guards": [{"guard": "scope_guard", "status": "pass", "violations": [], "may_increase_readiness": False}],
        },
        "homeostasis.json": {"variables": {"data_freshness": 1.0, "strategy_concentration": 1.0}},
        "resource_ledger.json": {"utilization": {"wall_seconds": 0.1}},
        "constitution_state.json": {
            "paper_only": True,
            "live_blocked": True,
            "broker_authority": False,
            "order_authority": False,
            "credential_access": False,
            "self_unlock_available": False,
        },
        "calibration_summary.json": {
            "settled_total": 0,
            "pending_total": 1,
            "expected_calibration_error": None,
            "calibration_sample_sufficient": False,
        },
        "input_time_proofs.json": {
            "artifact_type": "vnext_input_time_proofs",
            "proof_id": "vnext-input-time-proof:test",
            "point_in_time_complete": True,
            "inputs": {
                "news": {
                    "status": "point_in_time_valid",
                    "timestamp": "2026-07-14T20:00:00+00:00",
                    "age_hours": 1.0,
                    "maximum_age_hours": 72.0,
                },
                "calibration": {
                    "status": "excluded_missing_point_in_time_timestamp",
                    "used_as_calibration_evidence": False,
                },
            },
            "paper_only": True,
            "live_blocked": True,
        },
    }
    for name, value in sources.items():
        _write(output_dir / name, value)
    readiness_path = tmp_path / "readiness.json"
    evolution_path = tmp_path / "evolution.json"
    settlement_path = tmp_path / "settlement.json"
    _write(readiness_path, {"readiness_status": "not_action_ready", "paper_only": True, "live_blocked": True})
    _write(evolution_path, {"evaluations": [], "automatic_promotion_count": 0, "paper_only": True, "live_blocked": True})
    _write(settlement_path, {"pending_count": 1, "settled_count": 0, "paper_only": True, "live_blocked": True})

    artifact = build_observatory_artifact(
        output_dir,
        readiness_path,
        evolution_path,
        settlement_path,
        "2026-07-14T21:00:00+00:00",
        tmp_path,
    )

    assert artifact["surface"] == "dashboard"
    assert artifact["snapshot"]["status"] == "ready"
    assert artifact["package_info"]["action_ready"] is False
    assert artifact["snapshot"]["datasets"]["hero_metrics"][0]["automatic_promotions"] == 0
    assert artifact["snapshot"]["datasets"]["hero_metrics"][0]["time_proof_failures"] == 0
    database_path = output_dir / "observatory_snapshot.sqlite"
    with sqlite3.connect(database_path) as connection:
        for source in artifact["manifest"]["sources"]:
            if "query" not in source:
                continue
            rows = connection.execute(source["query"]["sql"]).fetchall()
            assert len(rows) == len(artifact["snapshot"]["datasets"][source["id"]])


def test_portable_observatory_normalization_is_signature_guarded() -> None:
    raw = f"<html><head></head><style>{PORTABLE_HEADER_WIDTH}padding:0}}</style></html>"
    normalized = normalize_portable_header_width(raw)

    assert PORTABLE_HEADER_WIDTH not in normalized
    assert NORMALIZED_HEADER_WIDTH in normalized
    assert READER_HEADER_OVERRIDE in normalized
