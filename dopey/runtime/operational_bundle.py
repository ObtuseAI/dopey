"""Run the complete governed vNext operating loop and write reviewable artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dopey.observatory.builder import build_observatory_artifact, write_observatory_artifact
from dopey.settlement.grading import SettlementPolicy
from dopey.settlement.runtime import SettlementRunPaths, run_settlement_cycle
from dopey.technical.history_adapter import load_validated_symbol_history
from dopey.world_model.cross_section import build_cross_sectional_context
from dopey_data.history_store import HISTORY_MANIFEST_PATH, load_history_manifest

from .vnext_research import VNextRunPaths, run_vnext_research


def _write_object(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(value), sort_keys=True, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _build_cross_section(market_time: str) -> dict[str, Any]:
    manifest = load_history_manifest(HISTORY_MANIFEST_PATH)
    histories: dict[str, list[Any]] = {}
    proofs: dict[str, dict[str, Any]] = {}
    for symbol in manifest.required_universe:
        histories[symbol], proofs[symbol] = load_validated_symbol_history(symbol, HISTORY_MANIFEST_PATH)
    return build_cross_sectional_context(histories, proofs, market_time, 20, 50, 60)


def _build_empty_evolution_status(observed_at: str) -> dict[str, Any]:
    return {
        "artifact_type": "bounded_recursive_evolution_status",
        "evolution_cycle_version": "dopey-recursive-evolution-v1",
        "observed_at": observed_at,
        "status": "no_operational_candidate_submitted",
        "evaluations": [],
        "promotion_packets": [],
        "automatic_research_activation_count": 0,
        "recursive_levels_available": [0, 1, 2, 3, 4, 5],
        "human_review_required": False,
        "full_promotion_matrix_required_for_activation": True,
        "historical_replay_is_forward_proof": False,
        "paper_only": True,
        "live_blocked": True,
    }


def run_operational_bundle(
    symbol: str,
    objective_type: str,
    event_time: str,
    market_time: str,
    as_of_date: str,
    observed_at: str,
    output_dir: Path,
    repository_root: Path,
    cross_asset_context: Path,
    news_context: Path,
    prior_calibration_summary: Path,
    readiness_path: Path,
) -> dict[str, Any]:
    cross_section_path = output_dir / "cross_sectional_context.json"
    cross_section = _build_cross_section(market_time)
    _write_object(cross_section_path, cross_section)

    input_dir = output_dir / "inputs"
    cross_asset_snapshot_path = input_dir / "cross_asset_context.json"
    news_snapshot_path = input_dir / "news_context.json"
    prior_calibration_snapshot_path = input_dir / "prior_calibration_summary.json"
    _write_object(cross_asset_snapshot_path, json.loads(cross_asset_context.read_text(encoding="utf-8")))
    _write_object(news_snapshot_path, json.loads(news_context.read_text(encoding="utf-8")))
    _write_object(prior_calibration_snapshot_path, json.loads(prior_calibration_summary.read_text(encoding="utf-8")))

    current_calibration_summary = output_dir / "calibration_summary.json"
    calibration_input = current_calibration_summary if current_calibration_summary.exists() else prior_calibration_snapshot_path
    research_summary = run_vnext_research(
        symbol,
        objective_type,
        event_time,
        market_time,
        VNextRunPaths(
            output_dir=output_dir,
            cross_asset_context=cross_asset_snapshot_path,
            news_context=news_snapshot_path,
            calibration_summary=calibration_input,
            cross_section_context=cross_section_path,
            macro_manifest=repository_root / "dopey_data" / "real" / "manifests" / "macro_context_manifest.json",
            fundamental_file_reference="dopey_data/real/raw/macro_context/fundamentals.csv",
            options_manifest=repository_root / "dopey_data" / "real" / "manifests" / "options_data_manifest.json",
            earnings_directory=repository_root / "dopey_data" / "real" / "raw" / "earnings_calendar",
        ),
    )
    settlement_summary = run_settlement_cycle(
        as_of_date,
        observed_at,
        SettlementRunPaths(
            prediction_ledger=output_dir / "forward_predictions.jsonl",
            settlement_memory=output_dir / "memory" / "settlements.jsonl",
            calibration_memory=output_dir / "memory" / "calibration.jsonl",
            calibration_summary=output_dir / "calibration_summary.json",
        ),
        SettlementPolicy(
            neutral_return_band=0.01,
            contested_margin=0.0025,
            maximum_price_gap_days=5,
            probability_floor=1e-12,
        ),
        10,
        30,
    )
    settlement_cycle_path = output_dir / "settlement_cycle_summary.json"
    _write_object(settlement_cycle_path, settlement_summary)

    evolution_status = _build_empty_evolution_status(observed_at)
    evolution_status_path = output_dir / "evolution_status.json"
    _write_object(evolution_status_path, evolution_status)

    observatory = build_observatory_artifact(
        output_dir,
        readiness_path,
        evolution_status_path,
        settlement_cycle_path,
        observed_at,
        repository_root,
    )
    observatory_path = output_dir / "observatory_artifact.json"
    write_observatory_artifact(observatory_path, observatory)

    result = {
        "artifact_type": "dopey_vnext_operational_bundle_summary",
        "operational_bundle_version": "dopey-vnext-operational-bundle-v1",
        "symbol": symbol,
        "objective_type": objective_type,
        "research_run_status": research_summary["run_status"],
        "research_control": research_summary["final_research_control"],
        "settled_count": settlement_summary["settled_count"],
        "pending_count": settlement_summary["pending_count"],
        "quarantined_count": settlement_summary["quarantined_count"],
        "minimum_settlement_date": research_summary["minimum_settlement_date"],
        "observatory_artifact": str(observatory_path),
        "observatory_snapshot_status": observatory["snapshot"]["status"],
        "automatic_promotion_count": 0,
        "action_ready": False,
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_order_authority": True,
    }
    _write_object(output_dir / "operational_bundle_summary.json", result)
    return result
