from __future__ import annotations

import json
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from dopey_analysis.run_real_signal_validation_gate import run_real_signal_validation_gate
from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_data.run_real_ohlcv_history_spine_activation import run_real_ohlcv_history_spine_activation
from dopey_data_ingestion.free_data_candidate_registry import free_data_candidate_records
from dopey_data_ingestion.free_data_provenance_gate import build_free_data_provenance_gate_results
from dopey_data_ingestion.local_ohlcv_file_inventory import (
    DAILY_OHLCV_DIR,
    REAL_DATA_MANIFEST_PATH,
    SCAN_DIRS,
    LocalOhlcvParsedFile,
    repo_relative_path,
    sha256_file,
)
from dopey_data_ingestion.local_ohlcv_import_models import LocalOhlcvImportDecision
from dopey_data_ingestion.local_ohlcv_import_validator import _quality_result, _schema_result
from dopey_data_ingestion.local_ohlcv_license_provenance_validator import validate_file_license_provenance
from dopey_data_ingestion.local_ohlcv_schema_validator import validate_parsed_schema
from dopey_data_ingestion.run_free_data_provenance_gate import run_free_data_provenance_gate
from dopey_data_ingestion.run_local_free_ohlcv_validation_and_activation_stack import (
    run_local_free_ohlcv_validation_and_activation_stack,
)
from dopey_data_ingestion.run_local_ohlcv_import_validator import run_local_ohlcv_import_validator
from dopey_export.artifact_selector import export_selection_rules
from dopey_reporting.data_loader import EVIDENCE_PATHS, ReportingEvidence, load_reporting_evidence
from dopey_reporting.reporting_bundle import _local_free_ohlcv_stack_summary
from dopey_validation.full_suite_stabilizer import CommandResult, timeout_result, write_test_shard_plan


@contextmanager
def _temporarily_clear_staging() -> Iterator[None]:
    """Simulate the no-staged-files state on a possibly populated repo.

    Moves operator-staged raw files and the final manifest aside, yields, then
    restores them and refreshes validator/activation/signal artifacts so live
    artifacts reflect the true repo state again after the test.
    """
    stash = REAL_DATA_MANIFEST_PATH.parent.parent / f".pytest_stash_{uuid.uuid4().hex[:8]}"
    moved: list[tuple[Path, Path]] = []
    try:
        for folder in SCAN_DIRS:
            if not folder.exists():
                continue
            for path in sorted(folder.rglob("*")):
                if path.is_file() and path.suffix.lower() in {".csv", ".jsonl"}:
                    target = stash / path.relative_to(REAL_DATA_MANIFEST_PATH.parent.parent)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(target))
                    moved.append((path, target))
        if REAL_DATA_MANIFEST_PATH.exists():
            target = stash / REAL_DATA_MANIFEST_PATH.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(REAL_DATA_MANIFEST_PATH), str(target))
            moved.append((REAL_DATA_MANIFEST_PATH, target))
        yield
    finally:
        for original, target in moved:
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(original))
        if stash.exists():
            shutil.rmtree(stash, ignore_errors=True)
        run_local_ohlcv_import_validator()
        run_real_ohlcv_history_spine_activation()
        run_real_signal_validation_gate()


def test_model_serialization_and_hash_determinism() -> None:
    decision = LocalOhlcvImportDecision(
        artifact_type="local_ohlcv_import_decision",
        validator_version="x",
        decision_id="d",
        local_ohlcv_status="missing_local_ohlcv_files",
        valid_real_dataset=False,
        real_data_imported=False,
        history_spine_upgrade_allowed=False,
        terminal_block=False,
        manual_review_required=False,
        real_data_files_present=False,
        reason_codes=["missing_local_ohlcv_files"],
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        decision_hash="",
    )
    first = decision.to_dict()
    second = LocalOhlcvImportDecision(**{key: first[key] for key in LocalOhlcvImportDecision.__dataclass_fields__}).to_dict()
    assert first["decision_hash"] == second["decision_hash"]
    assert first["paper_only"] is True
    assert first["live_blocked"] is True
    assert first["not_live_data"] is True
    assert first["not_broker_data"] is True
    assert first["not_strategy_promotion"] is True


def test_empty_raw_folders_produce_missing_status_and_artifacts() -> None:
    with _temporarily_clear_staging():
        result = run_local_ohlcv_import_validator()
        assert result["local_ohlcv_status"] == "missing_local_ohlcv_files"
        assert result["local_ohlcv_import_decision"] == "blocked_missing_local_ohlcv"
        assert result["real_data_files_present"] is False
        assert result["valid_real_dataset"] is False
        assert result["real_data_imported"] is False
        assert result["real_data_validated"] is False
        assert result["history_spine_upgrade_allowed"] is False
        assert result["fix_advice_status"] == "manual_staging_required"
        for path in result["artifact_paths"].values():
            assert Path(path).exists()


def test_schema_validator_passes_valid_header_and_fails_bad_rows(tmp_path: Path) -> None:
    valid_path = tmp_path / "valid.csv"
    valid_rows = [{"date": "2024-01-02", "symbol": "AAPL", "open": "1", "high": "2", "low": "1", "close": "2", "adjusted_close": "2", "volume": "100"}]
    valid = _schema_result(valid_path, "daily_ohlcv", valid_rows).to_dict()
    assert valid["schema_pass"] is True
    missing = _schema_result(tmp_path / "missing.csv", "daily_ohlcv", [{"date": "2024-01-02", "symbol": "AAPL"}]).to_dict()
    assert missing["schema_pass"] is False
    assert "open" in missing["missing_columns"]
    parsed = LocalOhlcvParsedFile(
        path=valid_path,
        dataset_family="daily_ohlcv",
        rows=valid_rows,
        header_columns=list(valid_rows[0]),
        malformed_rows=1,
        text="",
    )
    malformed = validate_parsed_schema(parsed).to_dict()
    assert malformed["malformed_rows"] == 1
    assert malformed["schema_pass"] is False


def test_quality_validator_blocks_bad_ohlcv_sample_credentials_and_live_markers(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("api_key,broker live_trading order_submit scheduler real_sizing\n", encoding="utf-8")
    rows = [
        {"date": "2099-01-02", "symbol": "SAMPLE_ONLY", "open": "-1", "high": "1", "low": "5", "close": "2", "adjusted_close": "0", "volume": "-1", "sample_only": "true", "not_real_data": "true"},
        {"date": "2099-01-02", "symbol": "SAMPLE_ONLY", "open": "-1", "high": "1", "low": "5", "close": "2", "adjusted_close": "0", "volume": "-1", "sample_only": "true", "not_real_data": "true"},
    ]
    result = _quality_result(path, "daily_ohlcv", rows).to_dict()
    assert result["status"] == "terminal_block"
    assert result["duplicate_symbol_date_count"] == 1
    assert result["positive_ohlc"] is False
    assert result["high_low_consistent"] is False
    assert result["adjusted_close_positive"] is False
    assert result["volume_nonnegative"] is False
    assert result["future_date_count"] == 2
    assert result["fake_symbol_count"] == 2
    assert result["sample_only_row_count"] == 2
    assert result["not_real_data_row_count"] == 2
    assert result["credential_token_found"] is True
    assert result["broker_live_order_scheduler_real_sizing_found"] is True


def test_license_provenance_blocks_missing_template_unknown_and_hash_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "valid.csv"
    rows = [{"date": "2024-01-02", "symbol": "AAPL", "open": "1", "high": "2", "low": "1", "close": "2", "adjusted_close": "2", "volume": "100", "source": "operator"}]
    path.write_text("date,symbol,open,high,low,close,adjusted_close,volume,source\n2024-01-02,AAPL,1,2,1,2,2,100,operator\n", encoding="utf-8")
    parsed = LocalOhlcvParsedFile(path=path, dataset_family="daily_ohlcv", rows=rows, header_columns=list(rows[0]), malformed_rows=0, text=path.read_text(encoding="utf-8"))
    missing = validate_file_license_provenance(parsed, {}).to_dict()
    assert missing["status"] in {"blocked_missing_license", "blocked_missing_provenance", "manual_review_required"}
    template = validate_file_license_provenance(parsed, {"manifest_id": "TEMPLATE_ONLY_NOT_REAL_DATA", "template_only": True, "license_status": "unknown"}).to_dict()
    assert template["manifest_template_only"] is True
    mismatch_manifest = _valid_manifest(path, "bad-hash")
    mismatch = validate_file_license_provenance(parsed, mismatch_manifest).to_dict()
    assert mismatch["status"] == "terminal_block"
    valid = validate_file_license_provenance(parsed, _valid_manifest(path, sha256_file(path))).to_dict()
    assert valid["status"] == "provenance_pass"


def test_history_activation_and_signal_gate_block_when_missing() -> None:
    with _temporarily_clear_staging():
        run_local_ohlcv_import_validator()
        history = run_real_ohlcv_history_spine_activation()
        signals = run_real_signal_validation_gate()
        assert history["history_spine_activation_status"] == "blocked_missing_local_ohlcv"
        assert history["valid_real_dataset"] is False
        assert history["real_history_used"] is False
        assert history["real_ohlcv_rows_activated"] == 0
        assert history["real_ohlcv_symbols_activated"] == 0
        assert signals["real_signal_validation_status"] == "blocked_missing_valid_real_history"
        assert signals["real_signal_evidence"] is False
        assert signals["real_history_used"] is False


def test_valid_local_csv_allows_history_activation_and_signal_validation() -> None:
    with _temporarily_clear_staging():
        staged_path = DAILY_OHLCV_DIR / "pytest_valid_local_ohlcv.csv"
        DAILY_OHLCV_DIR.mkdir(parents=True, exist_ok=True)
        try:
            staged_path.write_text(
                "date,symbol,open,high,low,close,adjusted_close,volume,source\n"
                "2024-01-02,AAPL,100,110,99,108,108,1000,pytest-reviewed-source\n"
                "2024-01-03,AAPL,108,112,107,111,111,1200,pytest-reviewed-source\n",
                encoding="utf-8",
            )
            REAL_DATA_MANIFEST_PATH.write_text(json.dumps(_valid_manifest(staged_path, sha256_file(staged_path)), sort_keys=True, indent=2) + "\n", encoding="utf-8")
            local = run_local_ohlcv_import_validator()
            history = run_real_ohlcv_history_spine_activation()
            signals = run_real_signal_validation_gate()
            assert local["local_ohlcv_status"] == "local_ohlcv_validation_pass", local
            assert local["local_ohlcv_import_decision"] == "valid_local_ohlcv_ready_for_history_spine"
            assert history["history_spine_activation_status"] == "real_ohlcv_history_spine_activation_pass"
            assert history["real_ohlcv_rows_activated"] == 2
            assert history["real_ohlcv_symbols_activated"] == 1
            assert signals["real_signal_validation_status"] == "real_signal_validation_pass"
            assert signals["real_signal_evidence"] is True
        finally:
            if staged_path.exists():
                staged_path.unlink()
            if REAL_DATA_MANIFEST_PATH.exists():
                REAL_DATA_MANIFEST_PATH.unlink()


def test_free_data_gate_excludes_alpha_vantage_and_fetches_nothing() -> None:
    candidates = free_data_candidate_records()
    results = build_free_data_provenance_gate_results(candidates)
    summary = run_free_data_provenance_gate()
    assert all("Alpha Vantage" not in record["source_name"] for record in candidates)
    assert all(record["evidence_allowed"] is False for record in candidates)
    assert all(record["not_fetched_by_dopey"] is True for record in candidates)
    assert summary["network_fetch_performed"] is False
    assert summary["credentials_created"] is False
    assert summary["env_created"] is False
    assert all(record["gate_status"] != "evidence_allowed" for record in results)


def test_combined_stack_summary_reporting_audit_export_and_stabilizer() -> None:
    with _temporarily_clear_staging():
        summary = run_local_free_ohlcv_validation_and_activation_stack()
        cleared_evidence = load_reporting_evidence(EVIDENCE_PATHS)
    run_local_free_ohlcv_validation_and_activation_stack()
    assert summary["local_ohlcv_status"] == "missing_local_ohlcv_files"
    assert summary["history_spine_activation_status"] == "blocked_missing_local_ohlcv"
    assert summary["real_signal_validation_status"] == "blocked_missing_valid_real_history"
    assert summary["real_signal_evidence"] is False
    assert summary["network_fetch_performed"] is False
    assert summary["credentials_created"] is False
    assert summary["env_created"] is False
    assert summary["broker_connection_used"] is False
    assert summary["strategy_promotion_allowed"] is False
    assert summary["alpha_vantage_excluded"] is True
    assert len(_fixture_case_records(summary)) >= 160
    artifact_types = {spec[0] for spec in ARTIFACT_SPECS}
    assert "local_free_ohlcv_validation_and_activation_stack_summary" in artifact_types
    export_ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "local_free_ohlcv_validation_and_activation_stack_summary" in export_ids
    assert cleared_evidence.local_free_ohlcv_stack_summary["local_ohlcv_status"] == "missing_local_ohlcv_files"
    reporting_summary = _local_free_ohlcv_stack_summary(_empty_reporting_evidence(summary))
    assert reporting_summary["next_recommended_target"] == "DOPEY_MANUAL_STAGE_FREE_OHLCV_FILES_AND_RERUN_VALIDATOR"
    plan = write_test_shard_plan(
        ["tests/test_local_free_ohlcv_import_validator_and_history_activation.py"],
        [CommandResult(["python", "-m", "pytest", "tests/test_local_free_ohlcv_import_validator_and_history_activation.py", "-q"], "pass", 0, 1.0, False, False, "", "")],
        {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}},
    )
    assert plan["local_free_ohlcv_stack_test_files"] == ["tests/test_local_free_ohlcv_import_validator_and_history_activation.py"]
    assert timeout_result(["python", "-m", "pytest"], 1)["status"] == "inconclusive_timeout"
    assert timeout_result(["python", "-m", "dopey_export.run_artifact_compaction_export_verifier"], 1)["timeout_recorded_as_pass"] is False


def _valid_manifest(path: Path, file_hash: str) -> dict:
    relative = repo_relative_path(path)
    return {
        "manifest_id": "pytest-reviewed-local-ohlcv",
        "created_at": "2026-07-06T00:00:00Z",
        "dataset_family": "daily_ohlcv",
        "provider_name": "pytest reviewed local file",
        "provider_terms_reviewed": True,
        "license_status": "reviewed_allowed_internal_research",
        "redistribution_allowed": False,
        "local_file_paths": [relative],
        "file_hashes": {relative: file_hash},
        "row_counts": {relative: 2},
        "symbol_counts": {relative: 1},
        "date_ranges": {relative: {"start": "2024-01-02", "end": "2024-01-03"}},
        "schema_version": "dopey-real-data-schema-contract-v1",
        "ingested_by": "manual_operator",
        "manual_operator_note": "pytest local fixture for validator behavior only",
        "source": "pytest-reviewed-source",
        "source_url_or_name": "pytest local source without credentials",
        "not_broker_data": True,
        "not_credentials": True,
        "not_live_data": True,
        "not_network_fetched_by_dopey": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _fixture_case_records(summary: dict) -> list[dict]:
    records: list[dict] = []
    for path_text in summary["fixture_paths"]:
        parsed = json.loads(Path(path_text).read_text(encoding="utf-8"))
        records.extend(parsed["cases"])
    return records


def _empty_reporting_evidence(local_free_ohlcv_stack_summary: dict) -> ReportingEvidence:
    values = {field_name: {} for field_name in ReportingEvidence.__dataclass_fields__}
    values["local_free_ohlcv_stack_summary"] = local_free_ohlcv_stack_summary
    return ReportingEvidence(**values)
