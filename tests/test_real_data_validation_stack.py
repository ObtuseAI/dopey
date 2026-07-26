from __future__ import annotations

import json

from tests.test_local_free_ohlcv_import_validator_and_history_activation import _temporarily_clear_staging

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_data.real_ohlcv_history_spine_upgrade import build_real_ohlcv_history_spine_upgrade
from dopey_data_ingestion.local_ohlcv_import_models import LocalOhlcvImportDecision
from dopey_data_ingestion.local_ohlcv_import_validator import (
    _quality_result,
    _schema_result,
    required_manifest_template_fields,
    sample_row_is_blocked,
    validate_local_ohlcv_import,
)
from dopey_data_ingestion.options_chain_quote_contract import (
    OPTIONS_CHAIN_REQUIRED_FIELDS,
    OPTIONS_QUOTES_REQUIRED_FIELDS,
    build_options_chain_quote_contract,
)
from dopey_data_ingestion.run_local_ohlcv_import_validator import MANIFEST_TEMPLATE_PATH, run_local_ohlcv_import_validator
from dopey_data_ingestion.run_real_data_validation_stack import run_real_data_validation_stack
from dopey_analysis.real_signal_validation import build_real_signal_validation
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_safety_summary
from dopey_export_review.review_data import load_review_context
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_validation.full_suite_stabilizer import timeout_result, write_test_shard_plan, CommandResult


def test_local_ohlcv_import_models_hash_determinism() -> None:
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


def test_missing_local_ohlcv_files_blocks_import_and_upgrade() -> None:
    with _temporarily_clear_staging():
        result = run_local_ohlcv_import_validator()
        assert result["local_ohlcv_status"] == "missing_local_ohlcv_files"
        assert result["valid_real_dataset"] is False
        assert result["real_data_imported"] is False
        assert result["history_spine_upgrade_allowed"] is False


def test_manifest_template_contains_required_fields() -> None:
    run_local_ohlcv_import_validator()
    template = json.loads(MANIFEST_TEMPLATE_PATH.read_text(encoding="utf-8"))
    for field in required_manifest_template_fields():
        assert field in template


def test_sample_and_fake_symbol_rows_are_blocked() -> None:
    assert sample_row_is_blocked({"symbol": "SAMPLE_ONLY"})
    assert sample_row_is_blocked({"symbol": "AAPL", "sample_only": "true"})
    assert sample_row_is_blocked({"symbol": "AAPL", "not_real_data": "true"})


def test_ohlcv_schema_validation_detects_missing_columns(tmp_path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("date,symbol,open\n2024-01-02,AAPL,1\n", encoding="utf-8")
    rows = [{"date": "2024-01-02", "symbol": "AAPL", "open": "1"}]
    result = _schema_result(path, "daily_ohlcv", rows).to_dict()
    assert result["required_columns_present"] is False
    assert "high" in result["missing_columns"]


def test_ohlcv_quality_detects_inconsistency_duplicates_future_and_token(tmp_path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("api_key,not_allowed\n", encoding="utf-8")
    rows = [
        {"date": "2099-01-02", "symbol": "AAPL", "open": "10", "high": "9", "low": "11", "close": "10", "adjusted_close": "10", "volume": "1"},
        {"date": "2099-01-02", "symbol": "AAPL", "open": "10", "high": "9", "low": "11", "close": "10", "adjusted_close": "10", "volume": "1"},
    ]
    result = _quality_result(path, "daily_ohlcv", rows).to_dict()
    assert result["high_low_consistent"] is False
    assert result["duplicate_symbol_date_count"] == 1
    assert result["future_date_count"] == 2
    assert result["credential_token_found"] is True
    assert result["status"] == "terminal_block"


def test_license_provenance_missing_blocks_readiness() -> None:
    with _temporarily_clear_staging():
        result = validate_local_ohlcv_import()
        assert result["summary"]["valid_real_dataset"] is False


def test_history_spine_and_real_signal_validation_block_when_missing() -> None:
    from dopey_data.run_real_ohlcv_history_spine_activation import run_real_ohlcv_history_spine_activation

    with _temporarily_clear_staging():
        run_local_ohlcv_import_validator()
        history = build_real_ohlcv_history_spine_upgrade()["upgrade"]
        assert history["history_spine_upgrade_status"] == "blocked_missing_local_ohlcv"
        assert history["valid_real_dataset"] is False
        run_real_ohlcv_history_spine_activation()
        signals = build_real_signal_validation()["summary"]
        assert signals["real_signal_validation_status"] == "blocked_missing_valid_real_history"
        assert signals["real_signal_evidence"] is False


def test_options_contract_fields_and_default_readiness() -> None:
    result = build_options_chain_quote_contract()
    chain_schema = next(record for record in result["schemas"] if record["dataset_family"] == "historical_options_chain")
    quote_schema = next(record for record in result["schemas"] if record["dataset_family"] == "historical_options_quotes")
    assert set(OPTIONS_CHAIN_REQUIRED_FIELDS).issubset(set(chain_schema["required_fields"]))
    assert set(OPTIONS_QUOTES_REQUIRED_FIELDS).issubset(set(quote_schema["required_fields"]))
    gate_names = {record["gate_name"] for record in result["gates"]}
    assert "ask_ge_bid" in gate_names
    assert "expiry_ge_snapshot_or_quote_date" in gate_names
    assert result["summary"]["options_contract_status"] == "options_import_contract_ready"
    assert result["summary"]["options_data_validated"] is False
    assert result["summary"]["quote_priced_backtest_allowed"] is False


def test_combined_stack_summary_and_reporting_integration() -> None:
    with _temporarily_clear_staging():
        summary = run_real_data_validation_stack()
        assert summary["local_ohlcv_status"] == "missing_local_ohlcv_files"
        assert summary["history_spine_upgrade_status"] == "blocked_missing_local_ohlcv"
        assert summary["real_signal_validation_status"] == "blocked_missing_valid_real_history"
        assert summary["options_contract_status"] == "options_import_contract_ready"
        assert summary["network_fetch_performed"] is False
        assert summary["broker_connection_used"] is False
        assert summary["credentials_created"] is False
        assert summary["env_created"] is False
        evidence = load_reporting_evidence(EVIDENCE_PATHS)
        assert evidence.real_data_validation_stack_summary["local_ohlcv_status"] == "missing_local_ohlcv_files"
    # Refresh the combined stack artifact so it reflects the true (staged) repo state again.
    run_real_data_validation_stack()


def test_audit_export_review_and_stabilizer_recognize_stack() -> None:
    artifact_types = {spec[0] for spec in ARTIFACT_SPECS}
    assert "local_ohlcv_import_summary" in artifact_types
    assert "real_data_validation_stack_summary" in artifact_types
    export_ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "real_data_validation_stack_summary" in export_ids
    shard_plan = write_test_shard_plan(
        ["tests/test_real_data_validation_stack.py"],
        [CommandResult(["python", "-m", "pytest", "tests/test_real_data_validation_stack.py", "-q"], "pass", 0, 1.0, False, False, "", "")],
        {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}, "timeout_recorded_as_pass": False},
    )
    assert "tests/test_real_data_validation_stack.py" in shard_plan["real_data_validation_stack_test_files"]
    assert timeout_result(["python", "-m", "pytest"], 1)["status"] == "inconclusive_timeout"
