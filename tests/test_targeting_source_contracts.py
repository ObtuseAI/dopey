"""Focused proofs for fail-closed targeting evidence and lake quality."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from dopey.strategy_engineering.playbook_scanner import PLAYBOOK_SCAN_VERSION
from dopey.strategy_engineering.playbook_settlement import PLAYBOOK_TRUST_VERSION
from dopey.strategy_engineering.scanner_holdout_fitness import (
    DRIFT_BASELINE_POLICY_VERSION,
    EVENT_DEDUPLICATION_POLICY_VERSION,
    SCANNER_FITNESS_VERSION,
    SOURCE_HASH_POLICY_VERSION,
)
from dopey_core.market_calendar import is_trading_day
from dopey_data import history_validator
from dopey_data.history_models import history_manifest_hash
from dopey_data.history_validator import placeholder_history_manifest_record
from dopey_market_intake import market_data_lake_builder as lake_builder
from dopey_options.model_iv_calibration_contract import (
    MODEL_IV_CALIBRATION_COMPLETE_STATUS,
    MODEL_IV_CALIBRATION_VERSION,
)
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_targeting.models import default_targeting_policy
from dopey_targeting.runtime import TargetingPaths, run_symbol_targeting
from operator_tools import operator_scanner_fitness

OBSERVED_AT = datetime(2026, 7, 26, 15, 0, tzinfo=timezone.utc)


def _write_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _trading_dates(end: date, count: int) -> list[date]:
    dates: list[date] = []
    cursor = end
    while len(dates) < count:
        if is_trading_day(cursor):
            dates.append(cursor)
        cursor -= timedelta(days=1)
    return sorted(dates)


def _write_history(root: Path) -> tuple[Path, Path, Path]:
    history_root = root / "history" / "raw"
    history_root.mkdir(parents=True, exist_ok=True)
    data_path = history_root / "SPY.csv"
    rows = [
        (
            f"{session.isoformat()},SPY,{100 + index},"
            f"{102 + index},{99 + index},{101 + index},"
            f"{101 + index},1000000,yahoo_finance\n"
        )
        for index, session in enumerate(_trading_dates(date(2026, 7, 24), 35))
    ]
    data_path.write_text(
        "date,symbol,open,high,low,close,adjusted_close,volume,source\n"
        + "".join(rows),
        encoding="utf-8",
    )
    manifest_path = root / "history" / "history_dataset_manifest.json"
    manifest = placeholder_history_manifest_record(history_root)
    manifest["dataset_status"] = "operator_staged_real_dataset"
    manifest["required_universe"] = ["SPY"]
    manifest["data_files"] = [
        {
            "path": "SPY.csv",
            "format": "csv",
            "symbols": ["SPY"],
            "sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
            "source": "yahoo_finance",
            "row_count": 35,
        }
    ]
    manifest["manifest_reproducibility_hash"] = history_manifest_hash(manifest)
    _write_json(manifest_path, manifest)
    return history_root, manifest_path, data_path


def _current_settlement() -> dict[str, object]:
    return {
        "artifact_type": "playbook_settlement",
        "detection_id": "current-detection",
        "setup_id": "mean_reversion_setup",
        "family": "mean_reversion",
        "symbol": "SPY",
        "as_of_date": "2026-07-20",
        "settle_date": "2026-07-22",
        "horizon_days": 2,
        "direction": "long",
        "forward_return": 0.01,
        "graded": True,
        "hit": True,
        "contested_truth": True,
        "prior_drift": 0.0,
        "source_playbook_scan_version": PLAYBOOK_SCAN_VERSION,
        "independently_selected_setup": False,
        "framing_selection_policy_version": None,
        "legacy_direction_assumption": False,
        "legacy_dual_framing": False,
        "rating_eligible": True,
        "rating_policy_version": PLAYBOOK_TRUST_VERSION,
        "not_trade_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _current_detection() -> dict[str, object]:
    return {
        "detection_id": "current-detection",
        "setup_id": "mean_reversion_setup",
        "family": "mean_reversion",
        "symbol": "SPY",
        "as_of_date": "2026-07-20",
        "direction": "long",
        "strength": 0.7,
        "horizon_days": [2],
        "source_playbook_scan_version": PLAYBOOK_SCAN_VERSION,
        "is_trade_signal": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _current_scanner() -> dict[str, object]:
    return {
        "artifact_type": "scanner_fitness_evaluation",
        "evaluated_at_utc": OBSERVED_AT.isoformat(),
        "scanner_fitness_version": SCANNER_FITNESS_VERSION,
        "drift_baseline_policy_version": DRIFT_BASELINE_POLICY_VERSION,
        "event_deduplication_policy_version": (
            EVENT_DEDUPLICATION_POLICY_VERSION
        ),
        "source_hash_policy_version": SOURCE_HASH_POLICY_VERSION,
        "source_universe_hash": "a" * 64,
        "detector_exception_count": 0,
        "detector_exception_counts": {},
        "detector_exception_budget_status": "within_budget",
        "sample_sufficient": True,
        "score": 0.5,
        "not_edge_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _current_iv_artifacts() -> tuple[dict[str, object], dict[str, object]]:
    row: dict[str, object] = {
        "artifact_type": "model_iv_calibration_row",
        "model_iv_calibration_version": MODEL_IV_CALIBRATION_VERSION,
        "symbol": "SPY",
        "snapshot_date": "2026-07-24",
        "mid_bisection_iv": 0.25,
        "quote_derived": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary: dict[str, object] = {
        "artifact_type": "model_iv_calibration_summary",
        "model_iv_calibration_version": MODEL_IV_CALIBRATION_VERSION,
        "calibration_status": MODEL_IV_CALIBRATION_COMPLETE_STATUS,
        "snapshot_date": "2026-07-24",
        "atm_contracts_compared": 1,
        "symbols_covered": ["SPY"],
        "per_symbol_multipliers": {
            "SPY": {"multiplier": 1.2, "contracts": 10}
        },
        "quote_derived": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary, row


def _write_current_sources(root: Path) -> tuple[TargetingPaths, Path]:
    history_root, manifest_path, history_path = _write_history(root)
    playbook_root = root / "playbook"
    detection_path = playbook_root / "detections.jsonl"
    settlement_path = playbook_root / "settlements.jsonl"
    _write_jsonl(detection_path, [_current_detection()])
    _write_jsonl(settlement_path, [_current_settlement()])
    scanner_path = root / "scanner.json"
    _write_json(scanner_path, _current_scanner())
    iv_summary, iv_row = _current_iv_artifacts()
    iv_summary_path = root / "iv_summary.json"
    iv_rows_path = root / "iv_rows.jsonl"
    _write_json(iv_summary_path, iv_summary)
    _write_jsonl(iv_rows_path, [iv_row])
    return (
        TargetingPaths(
            history_root=history_root,
            history_manifest_path=manifest_path,
            playbook_detection_path=detection_path,
            playbook_settlement_path=settlement_path,
            scanner_fitness_path=scanner_path,
            iv_calibration_rows_path=iv_rows_path,
            iv_calibration_summary_path=iv_summary_path,
            artifact_root=root / "targeting",
        ),
        history_path,
    )


def test_targeting_blocks_tampered_history_and_persists_zero_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(history_validator, "REQUIRED_HISTORY_UNIVERSE", ("SPY",))
    paths, history_path = _write_current_sources(tmp_path)
    history_path.write_text(
        history_path.read_text(encoding="utf-8")
        + "2026-07-27,SPY,140,142,139,141,141,1000000,yahoo_finance\n",
        encoding="utf-8",
    )

    summary = run_symbol_targeting(
        paths,
        default_targeting_policy(),
        OBSERVED_AT,
    )

    assert (
        summary["targeting_status"]
        == "blocked_invalid_or_stale_upstream_evidence"
    )
    assert summary["candidate_count"] == 0
    assert summary["verified_shadow_candidate_count"] == 0
    assert summary["stale_or_mismatched_evidence_consumed"] is False
    assert "history_dataset_not_valid_real_dataset" in {
        blocker["reason_code"] for blocker in summary["upstream_blockers"]
    }
    alias = paths.artifact_root / "symbol_candidate_registry.json"
    generation = Path(str(summary["candidate_registry_generation_path"]))
    assert generation.is_file()
    assert json.loads(generation.read_text(encoding="utf-8")) == json.loads(
        alias.read_text(encoding="utf-8")
    )
    assert json.loads(alias.read_text(encoding="utf-8"))["candidates"] == []
    assert not (paths.artifact_root / "shadow_targeting_ledger.jsonl").exists()


def test_targeting_blocks_mismatched_scanner_and_stale_iv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(history_validator, "REQUIRED_HISTORY_UNIVERSE", ("SPY",))
    paths, _ = _write_current_sources(tmp_path)
    scanner = _current_scanner()
    scanner["scanner_fitness_version"] = "dopey-scanner-holdout-fitness-v4"
    _write_json(paths.scanner_fitness_path, scanner)
    iv_summary, iv_row = _current_iv_artifacts()
    iv_summary["snapshot_date"] = "2026-06-01"
    iv_summary.pop("reproducibility_hash")
    iv_summary["reproducibility_hash"] = reproducibility_hash(iv_summary)
    iv_row["snapshot_date"] = "2026-06-01"
    _write_json(paths.iv_calibration_summary_path, iv_summary)
    _write_jsonl(paths.iv_calibration_rows_path, [iv_row])

    summary = run_symbol_targeting(
        paths,
        default_targeting_policy(),
        OBSERVED_AT,
    )

    reason_codes = {
        blocker["reason_code"] for blocker in summary["upstream_blockers"]
    }
    assert "scanner_contract_mismatch" in reason_codes
    assert "iv_calibration_summary_contract_mismatch" in reason_codes
    assert summary["history_symbol_count"] == 1
    assert summary["candidate_count"] == 1
    assert summary["verified_shadow_candidate_count"] == 0
    registry = json.loads(
        (paths.artifact_root / "symbol_candidate_registry.json").read_text(
            encoding="utf-8"
        )
    )
    assert registry["every_history_symbol_is_a_candidate"] is True
    assert registry["candidates"][0]["symbol"] == "SPY"
    assert registry["candidates"][0]["targeting_score"] == 0.0
    assert (
        registry["candidates"][0]["candidate_status"]
        == "blocked_invalid_or_stale_upstream_evidence"
    )
    blocked_forecast = json.loads(
        (
            paths.artifact_root / "per_symbol_forecast_skill.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        blocked_forecast["forecast_skill_status"]
        == "blocked_invalid_or_stale_upstream_evidence"
    )
    assert blocked_forecast["per_symbol"] == {}
    blocked_shadow = json.loads(
        (
            paths.artifact_root / "shadow_targeting_evidence.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        blocked_shadow["shadow_evidence_status"]
        == "blocked_invalid_or_stale_upstream_evidence"
    )


def test_targeting_persists_content_addressed_registry_before_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(history_validator, "REQUIRED_HISTORY_UNIVERSE", ("SPY",))
    paths, _ = _write_current_sources(tmp_path)

    first = run_symbol_targeting(
        paths,
        default_targeting_policy(),
        OBSERVED_AT,
    )
    second = run_symbol_targeting(
        paths,
        default_targeting_policy(),
        OBSERVED_AT,
    )

    first_generation = Path(str(first["candidate_registry_generation_path"]))
    second_generation = Path(str(second["candidate_registry_generation_path"]))
    alias = paths.artifact_root / "symbol_candidate_registry.json"
    assert first["upstream_blocker_count"] == 0
    assert first["candidate_count"] == 1
    assert first_generation == second_generation
    assert len(list((paths.artifact_root / "registry_generations").glob("*.json"))) == 1
    assert first_generation.is_file()
    assert first_generation.read_bytes() == alias.read_bytes()


def test_active_lake_rejects_nonfinite_and_inconsistent_ohlcv_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "dopey_data"
    monkeypatch.setattr(lake_builder, "DATA_ROOT", data_root)
    active_path = (
        data_root
        / "market_lake"
        / "active"
        / "daily_ohlcv"
        / "SPY.csv"
    )
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(
        "date,open,high,low,close,volume\n"
        "2026-07-23,100,102,99,101,1000\n"
        "2026-07-24,nan,104,100,103,1000\n"
        "2026-07-25,103,102,100,101,1000\n"
        "2026-07-26,103,104,105,103,1000\n"
        "2026-07-27,103,104,100,103,-1\n"
        "2026-07-28,103,inf,100,103,1000\n",
        encoding="utf-8",
    )
    file_record: dict[str, object] = {
        "symbol": "SPY",
        "source": "public_ohlcv",
        "market_data_source_type": "public_live_fetch",
        "active_path": str(active_path),
        "row_count": 6,
        "start_date": "2026-07-23",
        "end_date": "2026-07-28",
    }

    quality, rows, resolved_path = lake_builder._validate_active_lake_file(
        file_record
    )

    assert resolved_path == active_path.resolve()
    assert len(rows) == 1
    assert quality["invalid_row_count"] == 5
    assert quality["manifest_row_count_matches"] is False
    assert quality["sanity_pass"] is False
    assert quality["quality_status"] == "fail"


def test_scanner_operator_summary_emits_freshness_timestamp() -> None:
    evaluation: dict[str, object] = {
        "scanner_fitness_version": SCANNER_FITNESS_VERSION,
        "holdout_events": 100,
        "holdout_event_unit": "unique_symbol_date",
        "raw_detector_events": 100,
        "cofired_detector_event_duplicates": 0,
        "event_deduplication_policy_version": (
            EVENT_DEDUPLICATION_POLICY_VERSION
        ),
        "distinct_detectors_fired": 2,
        "symbols_evaluated": 10,
        "selected_symbols": ["SPY"],
        "symbol_selection_policy": "deterministic_sha256_spread_v1",
        "mean_excess_over_drift": 0.0,
        "event_deduped_mean_excess_over_drift": 0.0,
        "raw_detector_weighted_mean_excess_over_drift": 0.0,
        "deflated_mean_excess": 0.0,
        "hit_rate": 0.5,
        "raw_detector_weighted_hit_rate": 0.5,
        "drift_baseline_policy": (
            "point_in_time_only_fully_matured_forward_windows"
        ),
        "drift_baseline_policy_version": DRIFT_BASELINE_POLICY_VERSION,
        "source_universe_hash": "a" * 64,
        "source_hash_policy_version": SOURCE_HASH_POLICY_VERSION,
        "source_hash_fields": ["date", "close"],
        "detector_exception_count": 0,
        "detector_exception_counts": {},
        "detector_exception_budget_status": "within_budget",
        "sample_sufficient": True,
        "per_detector": {},
    }

    summary = operator_scanner_fitness._build_summary(
        evaluation,
        OBSERVED_AT.isoformat(),
    )

    assert summary["evaluated_at_utc"] == OBSERVED_AT.isoformat()
    assert datetime.fromisoformat(
        str(summary["evaluated_at_utc"])
    ).tzinfo is not None
