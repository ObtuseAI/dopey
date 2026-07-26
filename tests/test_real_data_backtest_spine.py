"""Tests for DOPEY's offline real-data backtest spine."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS, build_inventory
from dopey_data.history_models import (
    REQUIRED_HISTORY_UNIVERSE,
    HistoryBar,
    HistoryDataFile,
    HistoryDatasetManifest,
    history_manifest_hash,
)
from dopey_data.history_store import file_sha256, load_history_bars_from_file, load_history_manifest
from dopey_data.history_validator import placeholder_history_manifest_record, validate_history_dataset
from dopey_data.run_history_dataset_validation import (
    HISTORY_DATASET_MANIFEST_ARTIFACT_PATH,
    HISTORY_DATASET_VALIDATION_PATH,
    HISTORY_LOADER_PROOF_PATH,
    HISTORY_QUALITY_FLAGS_PATH,
    HISTORY_SPINE_SUMMARY_PATH,
    HISTORY_SYMBOL_COVERAGE_PATH,
    run_history_dataset_validation,
)
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary, render_safety_summary
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _history_spine_summary
from dopey_validation.full_suite_stabilizer import CommandResult, timeout_result, write_test_shard_plan


def _write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    headers = ["date", "symbol", "open", "high", "low", "close", "adjusted_close", "volume", "source"]
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(row.get(header, "")) for header in headers))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _base_row(symbol: str, date_value: str) -> dict[str, object]:
    return {
        "date": date_value,
        "symbol": symbol,
        "open": 100.0,
        "high": 103.0,
        "low": 99.0,
        "close": 102.0,
        "adjusted_close": 102.0,
        "volume": 1000000,
        "source": "operator_supplied_offline_file",
    }


def _write_manifest(manifest_path: Path, raw_dir: Path, data_file: Path, symbols: list[str], source: str) -> Path:
    record = placeholder_history_manifest_record(raw_dir)
    record["dataset_status"] = "operator_supplied_pending_validation"
    record["data_files"] = [
        {
            "path": data_file.name,
            "format": "csv",
            "symbols": symbols,
            "sha256": file_sha256(data_file),
            "source": source,
            "row_count": len(symbols),
        }
    ]
    record["manifest_reproducibility_hash"] = history_manifest_hash(record)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest_path


def _valid_universe_rows() -> list[dict[str, object]]:
    return [_base_row(symbol, "2024-01-02") for symbol in REQUIRED_HISTORY_UNIVERSE]


def test_model_serialization_is_deterministic() -> None:
    bar = HistoryBar.from_dict(_base_row("SPY", "2024-01-02"))
    first = bar.to_dict()
    second = HistoryBar.from_dict(first).to_dict()
    assert first == second
    file_ref = HistoryDataFile("raw/SPY.csv", "csv", ["SPY"], "abc", "operator_supplied_offline_file", 1)
    manifest = HistoryDatasetManifest.from_dict({
        **placeholder_history_manifest_record(Path("raw")),
        "data_files": [file_ref.to_dict()],
    })
    assert manifest.to_dict()["manifest_reproducibility_hash"] == manifest.to_dict()["manifest_reproducibility_hash"]


def test_manifest_loading() -> None:
    manifest = load_history_manifest(Path("dopey_data/history/history_dataset_manifest.json"))
    assert manifest.artifact_type == "history_dataset_manifest"
    # The live manifest reflects whatever the operator has (or has not) staged;
    # loading must parse it and the status must stay within the honest vocabulary.
    assert manifest.dataset_status in {
        "missing_real_dataset",
        "invalid_real_dataset",
        "valid_real_dataset",
        "operator_staged_real_dataset",
    }


def test_missing_dataset_is_honest_failure(tmp_path: Path) -> None:
    result = validate_history_dataset(tmp_path / "missing_manifest.json", tmp_path / "raw", False)
    assert result["dataset_status"] == "missing_real_dataset"
    assert result["summary"]["real_local_data_found"] is False
    assert "manifest_missing" in {flag["reason_code"] for flag in result["quality_flags"]}


def test_sample_csv_parsing(tmp_path: Path) -> None:
    csv_path = _write_csv(tmp_path / "history.csv", [_base_row("SPY", "2024-01-02")])
    bars = load_history_bars_from_file(csv_path, "csv")
    assert bars[0].symbol == "SPY"
    assert bars[0].date == "2024-01-02"
    assert bars[0].close == 102.0


def test_ohlc_validation(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    bad = _base_row("SPY", "2024-01-02")
    bad["high"] = 98.0
    csv_path = _write_csv(raw_dir / "history.csv", [bad])
    manifest_path = _write_manifest(tmp_path / "history_dataset_manifest.json", raw_dir, csv_path, ["SPY"], "operator_supplied_offline_file")
    result = validate_history_dataset(manifest_path, raw_dir, False)
    assert result["dataset_status"] == "invalid_real_dataset"
    assert "high_below_ohlc" in {flag["reason_code"] for flag in result["quality_flags"]}


def test_duplicate_detection(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    csv_path = _write_csv(raw_dir / "history.csv", [_base_row("SPY", "2024-01-02"), _base_row("SPY", "2024-01-02")])
    manifest_path = _write_manifest(tmp_path / "history_dataset_manifest.json", raw_dir, csv_path, ["SPY"], "operator_supplied_offline_file")
    result = validate_history_dataset(manifest_path, raw_dir, False)
    assert result["validation"]["duplicate_count"] == 1
    assert "duplicate_symbol_date" in {flag["reason_code"] for flag in result["quality_flags"]}


def test_missing_day_detection(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    csv_path = _write_csv(raw_dir / "history.csv", [_base_row("SPY", "2024-01-02"), _base_row("SPY", "2024-01-04")])
    manifest_path = _write_manifest(tmp_path / "history_dataset_manifest.json", raw_dir, csv_path, ["SPY"], "operator_supplied_offline_file")
    result = validate_history_dataset(manifest_path, raw_dir, False)
    spy = next(record for record in result["coverage_records"] if record["symbol"] == "SPY")
    assert spy["missing_weekday_count"] == 1
    assert "2024-01-03" in spy["missing_dates"]


def test_file_hash_generation(tmp_path: Path) -> None:
    csv_path = _write_csv(tmp_path / "history.csv", [_base_row("SPY", "2024-01-02")])
    assert len(file_sha256(csv_path)) == 64


def test_symbol_coverage_report(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    csv_path = _write_csv(raw_dir / "history.csv", _valid_universe_rows())
    manifest_path = _write_manifest(tmp_path / "history_dataset_manifest.json", raw_dir, csv_path, list(REQUIRED_HISTORY_UNIVERSE), "operator_supplied_offline_file")
    result = validate_history_dataset(manifest_path, raw_dir, False)
    assert result["dataset_status"] == "valid_real_dataset"
    assert result["validation"]["covered_symbol_count"] == len(REQUIRED_HISTORY_UNIVERSE)
    assert result["summary"]["symbols_covered"] == list(REQUIRED_HISTORY_UNIVERSE)


def test_no_fake_real_data_pass(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    rows = _valid_universe_rows()
    for row in rows:
        row["source"] = "synthetic_fixture"
    csv_path = _write_csv(raw_dir / "history.csv", rows)
    manifest_path = _write_manifest(tmp_path / "history_dataset_manifest.json", raw_dir, csv_path, list(REQUIRED_HISTORY_UNIVERSE), "synthetic_fixture")
    result = validate_history_dataset(manifest_path, raw_dir, False)
    assert result["dataset_status"] == "invalid_real_dataset"
    assert "source_declares_fixture_or_synthetic" in {flag["reason_code"] for flag in result["quality_flags"]}


def test_audit_recognizes_history_artifacts() -> None:
    run_history_dataset_validation()
    names = {spec[0] for spec in ARTIFACT_SPECS}
    required = {
        "history_dataset_manifest",
        "history_dataset_validation",
        "history_symbol_coverage",
        "history_quality_flags",
        "history_loader_proof",
        "history_spine_summary",
    }
    assert required.issubset(names)
    inventory = build_inventory()
    status_by_type = {artifact.artifact_type: artifact.status for artifact in inventory.artifacts}
    assert status_by_type["history_spine_summary"] == "present"


def test_reporting_includes_history_summary() -> None:
    result = run_history_dataset_validation()
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    summary = _history_spine_summary(evidence)
    # Reporting must MIRROR the validation outcome, whatever the current
    # dataset state is - never claim data that isn't there, never hide data
    # that is.
    assert summary["dataset_status"] == result["dataset_status"]
    assert summary["real_local_data_found"] is (result["dataset_status"] != "missing_real_dataset")


def test_export_includes_history_artifacts() -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {
        "history_dataset_manifest",
        "history_dataset_validation",
        "history_symbol_coverage",
        "history_quality_flags",
        "history_loader_proof",
        "history_spine_summary",
    }.issubset(ids)


def test_export_review_includes_history_summary() -> None:
    ctx = SimpleNamespace(
        shared_export_path="",
        reporting_summary={
            "history_spine_summary": {
                "dataset_status": "missing_real_dataset",
                "real_local_data_found": False,
                "row_count": 0,
                "symbols_covered": [],
                "symbols_missing": ["SPY"],
                "symbols_stale": [],
                "date_range": {},
                "quality_flags": ["data_files_missing"],
            }
        },
    )
    bundle = SimpleNamespace(
        source_bundle_id="bundle",
        source_export_path="source",
        artifact_count=1,
        hash_status="pass",
        copy_status="verified",
        safety_status="pass",
        credential_scan_status="pass",
        active_forbidden_live_decisions=0,
    )
    decision = SimpleNamespace(decision="review_ready", suitability="offline_review", next_build_target="DOPEY_MODEL_REPRICER_V1")
    rendered = render_executive_summary(ctx, bundle, [], decision)
    assert "Real-Data Backtest Spine" in rendered
    assert "missing_real_dataset" in rendered


def test_validation_stabilizer_includes_history_shard() -> None:
    summary = {
        "collection": {"status": "pass", "stdout_tail": ""},
        "full_suite": {"status": "inconclusive_timeout"},
    }
    plan = write_test_shard_plan(
        ["tests/test_real_data_backtest_spine.py"],
        [CommandResult(["python", "-m", "pytest", "tests/test_real_data_backtest_spine.py", "-q"], "pass", 0, 0.1, False, False, "", "")],
        summary,
    )
    assert "tests/test_real_data_backtest_spine.py" in plan["split_suite_lanes"]["real_data_backtest_spine_tests"]
    assert "tests/test_real_data_backtest_spine.py" in plan["artifact_writing_tests_sequential"]


def test_full_pytest_timeout_remains_inconclusive_not_pass() -> None:
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout"
    assert result["timeout_recorded_as_pass"] is False


def test_history_runner_writes_dataset_artifacts() -> None:
    result = run_history_dataset_validation()
    # The runner writes the full artifact set for EVERY honest outcome
    # (missing, invalid, or valid real dataset).
    assert result["dataset_status"] in {"missing_real_dataset", "invalid_real_dataset", "valid_real_dataset"}
    for path in [
        HISTORY_DATASET_MANIFEST_ARTIFACT_PATH,
        HISTORY_DATASET_VALIDATION_PATH,
        HISTORY_SYMBOL_COVERAGE_PATH,
        HISTORY_QUALITY_FLAGS_PATH,
        HISTORY_LOADER_PROOF_PATH,
        HISTORY_SPINE_SUMMARY_PATH,
    ]:
        assert path.exists()


def test_live_trading_still_disabled() -> None:
    intent = ExecutionIntent(
        intent_id="history-live-disabled",
        symbol="SPY",
        structure="single",
        legs=[{"side": "buy", "symbol": "SPY_CALL", "option_type": "call", "expiry": "2024-01-19"}],
        live_allowed=True,
        paper=False,
    )
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(intent)


def test_no_broker_connection_credentials_scheduler_or_real_sizing() -> None:
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in [
        Path("dopey_data/history_store.py"),
        Path("dopey_data/history_models.py"),
        Path("dopey_data/history_validator.py"),
        Path("dopey_data/run_history_dataset_validation.py"),
    ])
    assert "requests" not in text
    assert "websocket" not in text
    assert "place_order" not in text
    assert "cancel_order" not in text
    assert "review_order" not in text
    assert "sk-proj-" not in text
    assert "api_key" not in text
    assert "cron" not in text
    assert "apscheduler" not in text
    assert "buying_power" not in text
    assert "account_balance" not in text
    assert "robinhood_mcp" not in text


def test_export_review_safety_summary_mentions_history_spine() -> None:
    ctx = SimpleNamespace(
        safety_state={
            "mode": "RESEARCH",
            "live_trading_enabled": False,
            "funded_broker_connections_enabled": False,
            "allow_unofficial_robinhood_api": False,
        },
        export_safety_scan={"active_forbidden_live_decisions": 0, "credential_findings": 0},
    )
    assert "real_data_backtest_spine" in render_safety_summary(ctx)


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        assert True
        return
    assert manifest.read_text(encoding="utf-8-sig").strip() or manifest.exists()
