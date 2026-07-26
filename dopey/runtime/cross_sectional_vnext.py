"""Resumable cross-sectional vNext prediction and settlement operation."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from dopey.constitution.execution_seal import assert_output_research_only
from dopey.protocols.identity import canonical_hash
from dopey.settlement.grading import SettlementPolicy
from dopey.settlement.accrual import run_forward_accrual_monitor
from dopey.settlement.predictions import append_prediction
from dopey.settlement.runtime import SettlementRunPaths, run_settlement_cycle
from dopey.technical.history_adapter import load_validated_symbol_history
from dopey.truth.agent_ablation import evaluate_agent_ablation_ledgers
from dopey.world_model.cross_section import build_cross_sectional_context
from dopey_data.history_store import HISTORY_MANIFEST_PATH

from .vnext_research import VNextRunPaths, run_vnext_research


def _load_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"cross-sectional vNext input is missing: path={path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"cross-sectional vNext input must be an object: path={path}")
    return value


def _write_object_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(dict(value), sort_keys=True, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _snapshot_object(source_path: Path, target_path: Path) -> dict[str, Any]:
    value = _load_object(source_path)
    _write_object_atomic(target_path, value)
    return value


def _session_descriptor(
    symbols: Sequence[str],
    objective_type: str,
    event_time: str,
    market_time: str,
) -> dict[str, Any]:
    return {
        "symbols": list(symbols),
        "objective_type": objective_type,
        "event_time": event_time,
        "market_time": market_time,
    }


def _find_session_checkpoint(
    output_root: Path,
    descriptor: Mapping[str, Any],
) -> tuple[Path | None, dict[str, Any]]:
    matches: list[tuple[Path, dict[str, Any]]] = []
    checkpoint_root = output_root / "checkpoints"
    for path in sorted(checkpoint_root.glob("*.json")):
        checkpoint = _load_object(path)
        checkpoint_descriptor = {
            "symbols": checkpoint.get("requested_symbols"),
            "objective_type": checkpoint.get("objective_type"),
            "event_time": checkpoint.get("event_time"),
            "market_time": checkpoint.get("market_time"),
        }
        if checkpoint_descriptor == dict(descriptor):
            fingerprint = str(checkpoint.get("batch_fingerprint", ""))
            if not fingerprint or path.stem != fingerprint:
                raise ValueError(
                    "cross-sectional checkpoint filename and fingerprint disagree: "
                    f"path={path}, fingerprint={fingerprint}"
                )
            matches.append((path, checkpoint))
    if len(matches) > 1:
        raise ValueError(
            "cross-sectional session has multiple checkpoints: "
            f"descriptor={dict(descriptor)}, paths={[str(path) for path, _ in matches]}"
        )
    return matches[0] if matches else (None, {})


def _select_session_inputs(
    output_root: Path,
    descriptor: Mapping[str, Any],
    checkpoint_exists: bool,
) -> Path:
    market_date = str(descriptor["market_time"])[:10]
    legacy = output_root / "inputs" / market_date
    versioned = legacy / canonical_hash(descriptor)[:24]
    required_names = {
        "cross_asset_context.json",
        "news_context.json",
        "cross_sectional_context.json",
    }

    def _complete(path: Path) -> bool:
        return all((path / name).is_file() for name in required_names)

    if checkpoint_exists:
        if _complete(versioned):
            return versioned
        if _complete(legacy):
            return legacy
        raise FileNotFoundError(
            "resumable cross-sectional checkpoint lacks immutable session inputs: "
            f"versioned={versioned}, legacy={legacy}"
        )
    existing_names = {
        path.name
        for path in versioned.glob("*.json")
        if path.is_file()
    }
    if existing_names and existing_names != required_names:
        raise ValueError(
            "cross-sectional session input initialization is partial: "
            f"path={versioned}, expected={sorted(required_names)}, actual={sorted(existing_names)}"
        )
    return versioned


def _history_source_hashes(proofs: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for symbol, proof in sorted(proofs.items()):
        actual_hash = str(proof.get("actual_sha256", ""))
        if not actual_hash:
            raise ValueError(f"cross-sectional history proof lacks actual_sha256: symbol={symbol}")
        hashes[symbol] = actual_hash
    return hashes


def _validate_resumed_history_sources(
    cross_section: Mapping[str, Any],
    proofs: Mapping[str, Mapping[str, Any]],
) -> None:
    expected_value = cross_section.get("source_hashes")
    if not isinstance(expected_value, Mapping):
        raise TypeError("resumed cross-sectional context lacks source_hashes")
    expected = {str(symbol): str(value) for symbol, value in expected_value.items()}
    actual = _history_source_hashes(proofs)
    if expected != actual:
        changed = sorted(
            symbol
            for symbol in set(expected) | set(actual)
            if expected.get(symbol) != actual.get(symbol)
        )
        raise ValueError(
            "resumable cross-sectional history sources drifted from the immutable context: "
            f"changed_symbols={changed}"
        )


def _require_repository_input(path: Path, repository_root: Path, input_name: str) -> Path:
    resolved_root = repository_root.resolve(strict=True)
    resolved_path = path.resolve(strict=True)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(
            "cross-sectional vNext input is outside the repository boundary: "
            f"input_name={input_name}, path={resolved_path}, repository_root={resolved_root}"
        ) from error
    return resolved_path


def _point_in_time_histories(
    symbols: Sequence[str],
    market_time: str,
) -> tuple[dict[str, list[Any]], dict[str, dict[str, Any]]]:
    market_date = datetime.fromisoformat(market_time.replace("Z", "+00:00")).date().isoformat()
    histories: dict[str, list[Any]] = {}
    proofs: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        history, proof = load_validated_symbol_history(symbol, HISTORY_MANIFEST_PATH)
        filtered = [row for row in history if str(row["date"]) <= market_date]
        if not filtered:
            raise ValueError(
                "cross-sectional vNext has no point-in-time history: "
                f"symbol={symbol}, market_date={market_date}"
            )
        histories[symbol] = filtered
        proofs[symbol] = {
            **proof,
            "point_in_time_last_date": str(filtered[-1]["date"]),
            "point_in_time_row_count": len(filtered),
        }
    return histories, proofs


def _settlement_paths(output_root: Path) -> SettlementRunPaths:
    return SettlementRunPaths(
        prediction_ledger=output_root / "forward_predictions.jsonl",
        settlement_memory=output_root / "memory" / "settlements.jsonl",
        calibration_memory=output_root / "memory" / "calibration.jsonl",
        calibration_summary=output_root / "calibration_summary.json",
    )


def _run_settlement(
    output_root: Path,
    as_of_date: str,
    observed_at: str,
) -> dict[str, Any]:
    paths = _settlement_paths(output_root)
    if not paths.prediction_ledger.exists():
        paths.prediction_ledger.parent.mkdir(parents=True, exist_ok=True)
        paths.prediction_ledger.write_text("", encoding="utf-8")
    summary = run_settlement_cycle(
        as_of_date,
        observed_at,
        paths,
        SettlementPolicy(
            neutral_return_band=0.01,
            contested_margin=0.0025,
            maximum_price_gap_days=5,
            probability_floor=1e-12,
        ),
        10,
        30,
    )
    _write_object_atomic(output_root / "latest_settlement_summary.json", summary)
    return summary


def _checkpoint_record(
    batch_fingerprint: str,
    event_time: str,
    market_time: str,
    objective_type: str,
    symbols: Sequence[str],
    completed: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "artifact_type": "cross_sectional_vnext_checkpoint",
        "checkpoint_version": "dopey-cross-sectional-vnext-checkpoint-v1",
        "batch_fingerprint": batch_fingerprint,
        "event_time": event_time,
        "market_time": market_time,
        "objective_type": objective_type,
        "requested_symbols": list(symbols),
        "completed": dict(completed),
        "completed_count": len(completed),
        "batch_status": "complete" if len(completed) == len(symbols) else "in_progress_resumable",
        "paper_only": True,
        "live_blocked": True,
    }


def run_cross_sectional_vnext(
    symbols: Sequence[str],
    objective_type: str,
    event_time: str,
    market_time: str,
    output_root: Path,
    repository_root: Path,
    cross_asset_context: Path,
    news_context: Path,
    macro_manifest: Path,
    options_manifest: Path,
    earnings_directory: Path,
) -> dict[str, Any]:
    normalized_symbols = tuple(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
    if not normalized_symbols:
        raise ValueError("cross-sectional vNext requires at least one symbol")
    validated_cross_asset_context = _require_repository_input(
        cross_asset_context,
        repository_root,
        "cross_asset_context",
    )
    validated_news_context = _require_repository_input(news_context, repository_root, "news_context")
    validated_macro_manifest = _require_repository_input(macro_manifest, repository_root, "macro_manifest")
    validated_options_manifest = _require_repository_input(options_manifest, repository_root, "options_manifest")
    validated_earnings_directory = _require_repository_input(
        earnings_directory,
        repository_root,
        "earnings_directory",
    )
    histories, proofs = _point_in_time_histories(normalized_symbols, market_time)
    session_descriptor = _session_descriptor(
        normalized_symbols,
        objective_type,
        event_time,
        market_time,
    )
    prior_checkpoint_path, prior_checkpoint = _find_session_checkpoint(
        output_root,
        session_descriptor,
    )
    session_inputs = _select_session_inputs(
        output_root,
        session_descriptor,
        prior_checkpoint_path is not None,
    )
    cross_asset_snapshot = session_inputs / "cross_asset_context.json"
    news_snapshot = session_inputs / "news_context.json"
    cross_section_path = session_inputs / "cross_sectional_context.json"
    if cross_asset_snapshot.exists() or news_snapshot.exists() or cross_section_path.exists():
        cross_asset = _load_object(cross_asset_snapshot)
        news = _load_object(news_snapshot)
        cross_section = _load_object(cross_section_path)
        _validate_resumed_history_sources(cross_section, proofs)
    else:
        cross_asset = _snapshot_object(validated_cross_asset_context, cross_asset_snapshot)
        news = _snapshot_object(validated_news_context, news_snapshot)
        cross_section = build_cross_sectional_context(histories, proofs, market_time, 20, 50, 60)
        _write_object_atomic(cross_section_path, cross_section)
    as_of_date = market_time[:10]
    settlement_before = _run_settlement(output_root, as_of_date, event_time)
    batch_inputs = {
        "symbols": list(normalized_symbols),
        "objective_type": objective_type,
        "event_time": event_time,
        "market_time": market_time,
        "cross_asset_hash": canonical_hash(cross_asset),
        "news_hash": canonical_hash(news),
        "cross_section_hash": cross_section["content_hash"],
        "macro_manifest_hash": canonical_hash(_load_object(validated_macro_manifest)),
        "options_manifest_hash": canonical_hash(_load_object(validated_options_manifest)),
    }
    batch_fingerprint = canonical_hash(batch_inputs)
    session_dir = output_root / "sessions" / batch_fingerprint[:24]
    if prior_checkpoint_path is not None and prior_checkpoint_path.stem != batch_fingerprint:
        raise ValueError(
            "resumable cross-sectional immutable inputs no longer match the checkpoint: "
            f"checkpoint={prior_checkpoint_path.stem}, computed={batch_fingerprint}, "
            f"session_inputs={session_inputs}"
        )
    checkpoint_path = (
        prior_checkpoint_path
        if prior_checkpoint_path is not None
        else output_root / "checkpoints" / f"{batch_fingerprint}.json"
    )
    existing_checkpoint = prior_checkpoint
    if not existing_checkpoint and checkpoint_path.exists():
        existing_checkpoint = _load_object(checkpoint_path)
    if existing_checkpoint and existing_checkpoint.get("batch_fingerprint") != batch_fingerprint:
        raise ValueError(
            "cross-sectional checkpoint fingerprint mismatch: "
            f"path={checkpoint_path}, expected={batch_fingerprint}, actual={existing_checkpoint.get('batch_fingerprint')}"
        )
    completed_value = existing_checkpoint.get("completed", {})
    if not isinstance(completed_value, dict):
        raise TypeError(f"cross-sectional checkpoint completed field must be an object: path={checkpoint_path}")
    completed: dict[str, Any] = dict(completed_value)
    central_ledger = output_root / "forward_predictions.jsonl"
    for symbol in normalized_symbols:
        symbol_dir = session_dir / "symbols" / symbol
        summary_path = symbol_dir / "vnext_research_summary.json"
        prediction_path = symbol_dir / "latest_prediction.json"
        if symbol not in completed:
            summary = run_vnext_research(
                symbol,
                objective_type,
                event_time,
                market_time,
                VNextRunPaths(
                    output_dir=symbol_dir,
                    cross_asset_context=cross_asset_snapshot,
                    news_context=news_snapshot,
                    calibration_summary=output_root / "calibration_summary.json",
                    cross_section_context=cross_section_path,
                    macro_manifest=validated_macro_manifest,
                    fundamental_file_reference="dopey_data/real/raw/macro_context/fundamentals.csv",
                    options_manifest=validated_options_manifest,
                    earnings_directory=validated_earnings_directory,
                ),
            )
            completed[symbol] = {
                "summary_hash": summary["reproducibility_hash"],
                "prediction_id": summary["prediction_id"],
                "final_research_control": summary["final_research_control"],
                "specialist_data_gap_count": summary["specialist_data_gap_count"],
            }
            _write_object_atomic(
                checkpoint_path,
                _checkpoint_record(
                    batch_fingerprint,
                    event_time,
                    market_time,
                    objective_type,
                    normalized_symbols,
                    completed,
                ),
            )
        if not summary_path.exists() or not prediction_path.exists():
            raise FileNotFoundError(
                "cross-sectional completed checkpoint lacks symbol artifacts: "
                f"symbol={symbol}, summary_path={summary_path}, prediction_path={prediction_path}"
            )
        summary = _load_object(summary_path)
        prediction = _load_object(prediction_path)
        if str(summary.get("reproducibility_hash", "")) != str(completed[symbol].get("summary_hash", "")):
            raise ValueError(
                "cross-sectional completed summary does not match checkpoint: "
                f"symbol={symbol}, checkpoint_path={checkpoint_path}"
            )
        append_prediction(central_ledger, prediction)
    checkpoint = _checkpoint_record(
        batch_fingerprint,
        event_time,
        market_time,
        objective_type,
        normalized_symbols,
        completed,
    )
    _write_object_atomic(checkpoint_path, checkpoint)
    settlement_after = _run_settlement(output_root, as_of_date, event_time)
    accrual_monitor = run_forward_accrual_monitor(
        central_ledger,
        _settlement_paths(output_root).settlement_memory,
        as_of_date,
        output_root / "forward_accrual_monitor.json",
        SettlementPolicy(
            neutral_return_band=0.01,
            contested_margin=0.0025,
            maximum_price_gap_days=5,
            probability_floor=1e-12,
        ),
    )
    ablation = evaluate_agent_ablation_ledgers(
        central_ledger,
        _settlement_paths(output_root).settlement_memory,
        1000,
        20260714,
        0.05,
        30,
        3,
    )
    _write_object_atomic(output_root / "latest_agent_ablation.json", ablation)
    summary_body: dict[str, Any] = {
        "artifact_type": "cross_sectional_vnext_batch_summary",
        "batch_version": "dopey-cross-sectional-vnext-v1",
        "batch_status": "complete_awaiting_forward_settlement",
        "batch_fingerprint": batch_fingerprint,
        "event_time": event_time,
        "market_time": market_time,
        "objective_type": objective_type,
        "requested_symbol_count": len(normalized_symbols),
        "completed_symbol_count": len(completed),
        "abstention_count": sum(
            str(record.get("final_research_control", "")) in {"ABSTAIN", "TERMINATE"}
            for record in completed.values()
            if isinstance(record, Mapping)
        ),
        "specialist_data_gap_count": sum(
            int(record.get("specialist_data_gap_count", 0) or 0)
            for record in completed.values()
            if isinstance(record, Mapping)
        ),
        "prediction_ledger": str(central_ledger),
        "settled_count_before": settlement_before["settled_count"],
        "settled_count_after": settlement_after["settled_count"],
        "pending_count": settlement_after["pending_count"],
        "quarantined_count": settlement_after["quarantined_count"],
        "forward_accrual_monitor_status": accrual_monitor["monitor_status"],
        "next_minimum_settlement_date": accrual_monitor["next_minimum_settlement_date"],
        "gradeable_unrecorded_count": accrual_monitor["gradeable_unrecorded_count"],
        "due_missing_verified_price_count": accrual_monitor["due_missing_verified_price_count"],
        "calibration_sample_sufficient": bool(
            _load_object(output_root / "calibration_summary.json").get("calibration_sample_sufficient", False)
        ),
        "agent_ablation_status": ablation["evaluation_status"],
        "agent_ablation_eligible_settlement_count": ablation["eligible_settlement_count"],
        "validated_positive_agent_count": ablation["validated_positive_agent_count"],
        "retirement_recommendation_count": ablation["retirement_recommendation_count"],
        "automatic_promotion_count": 0,
        "action_ready": False,
        "readiness_effect": "none_protected_external_gate",
        "paper_only": True,
        "live_blocked": True,
        "no_broker": True,
        "no_order_authority": True,
    }
    summary = {**summary_body, "reproducibility_hash": canonical_hash(summary_body)}
    assert_output_research_only(summary)
    _write_object_atomic(session_dir / "batch_summary.json", summary)
    _write_object_atomic(output_root / "latest_batch_summary.json", summary)
    return summary
