from __future__ import annotations

import json
from pathlib import Path

from tests.test_local_free_ohlcv_import_validator_and_history_activation import _temporarily_clear_staging

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_data.real_ohlcv_history_spine_upgrade import build_real_ohlcv_history_spine_upgrade
from dopey_data_ingestion.free_data_candidate_registry import free_data_candidate_records
from dopey_data_ingestion.free_data_provenance_gate import build_free_data_provenance_gate_results
from dopey_data_ingestion.local_ohlcv_import_fix_advisor import build_local_ohlcv_fix_advice
from dopey_data_ingestion.local_ohlcv_import_validator import validate_local_ohlcv_import
from dopey_data_ingestion.run_local_ohlcv_import_validator import MANIFEST_TEMPLATE_PATH, run_local_ohlcv_import_validator
from dopey_export.artifact_selector import export_selection_rules
from dopey_open_source.oss_capability_extraction import CAPABILITY_CATEGORIES, build_adapter_contracts
from dopey_open_source.oss_license_security_gate import oss_license_security_records
from dopey_open_source.oss_quant_stack_registry import oss_candidate_records
from dopey_open_source.oss_sandbox_import_plan import write_oss_sandbox_import_plan
from dopey_open_source.run_open_source_quant_stack_and_free_data_path import (
    OPEN_SOURCE_PATH_SUMMARY_PATH,
    run_open_source_quant_stack_and_free_data_path,
)
from dopey_reporting.reporting_bundle import _open_source_path_summary
from dopey_reporting.data_loader import ReportingEvidence
from dopey_validation.full_suite_stabilizer import write_test_shard_plan


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_open_source_models_are_hash_deterministic_and_candidate_only() -> None:
    first = oss_candidate_records()
    second = oss_candidate_records()
    assert first == second
    assert first
    assert all(record["approval_required"] for record in first)
    assert all(record["not_imported"] for record in first)
    assert all(record["not_executed"] for record in first)
    assert all(record["paper_only"] and record["live_blocked"] for record in first)


def test_license_security_gate_blocks_risky_candidates_for_manual_review() -> None:
    records = oss_candidate_records()
    results = oss_license_security_records(records)
    by_id = {record["candidate_id"]: record for record in results}
    assert by_id["oss-ta-style"]["gate_status"] == "manual_review_required"
    assert by_id["oss-lean"]["broker_live_trading_manual_review"] is True
    assert by_id["oss-yfinance-style"]["network_fetching_manual_review"] is True
    assert all(record["no_direct_promotion_authority"] for record in results)
    assert all(record["no_direct_broker_authority"] for record in results)
    assert all(record["no_direct_scheduler_authority"] for record in results)


def test_sandbox_and_adapter_contracts_block_external_authority() -> None:
    plan = write_oss_sandbox_import_plan()
    adapters = [record.to_dict() for record in build_adapter_contracts()]
    assert plan["repo_cloned_count"] == 0
    assert plan["dependency_installed_count"] == 0
    assert plan["external_code_imported_count"] == 0
    assert plan["external_code_executed_count"] == 0
    assert set(CAPABILITY_CATEGORIES) >= {"event loop architecture", "options pricing/math", "ML model training workflow", "RL environment workflow"}
    assert adapters
    assert all(record["external_component_cannot_call_broker"] for record in adapters)
    assert all(record["external_component_cannot_fetch_network_data_unless_approved"] for record in adapters)
    assert all(record["external_component_cannot_place_orders"] for record in adapters)
    assert all(record["external_component_cannot_write_credentials"] for record in adapters)
    assert all(record["output_authority"] == "candidate_signal_or_diagnostic_only" for record in adapters)


def test_free_data_candidates_are_not_evidence_without_license_and_provenance() -> None:
    candidates = free_data_candidate_records()
    results = build_free_data_provenance_gate_results(candidates)
    assert candidates
    assert all(record["credentials_required"] is False for record in candidates)
    assert all(record["not_fetched_by_dopey"] is True for record in candidates)
    assert all(record["evidence_allowed"] is False for record in candidates)
    assert all(record["gate_status"] in {"blocked_missing_license", "blocked_missing_provenance", "manual_review_required"} for record in results)


def test_local_ohlcv_missing_status_and_fix_advice_are_preserved() -> None:
    with _temporarily_clear_staging():
        result = run_local_ohlcv_import_validator()
        validation = validate_local_ohlcv_import()
        advice = build_local_ohlcv_fix_advice(validation)
        assert result["local_ohlcv_status"] == "missing_local_ohlcv_files"
        assert result["real_data_files_present"] is False
        assert result["valid_real_dataset"] is False
        assert result["history_spine_upgrade_allowed"] is False
        assert result["fix_advice_status"] == "manual_staging_required"
        assert advice["fix_advice_status"] == "manual_staging_required"
        assert MANIFEST_TEMPLATE_PATH.exists()
        template = json.loads(MANIFEST_TEMPLATE_PATH.read_text(encoding="utf-8"))
        assert template["not_credentials"] is True
        assert template["not_network_fetched_by_dopey"] is True
        assert template["provenance_review_status"] == "manual_review_required"


def test_history_activation_blocked_when_local_ohlcv_missing() -> None:
    with _temporarily_clear_staging():
        run_local_ohlcv_import_validator()
        result = build_real_ohlcv_history_spine_upgrade()
        assert result["upgrade"]["history_spine_upgrade_status"] == "blocked_missing_local_ohlcv"
        assert result["upgrade"]["valid_real_dataset"] is False
        assert result["upgrade"]["real_history_used"] is False
        assert result["activation_blockers"]


def test_combined_runner_writes_artifacts_and_keeps_expected_safe_state() -> None:
    with _temporarily_clear_staging():
        summary = run_open_source_quant_stack_and_free_data_path()
    # Refresh the combined runner artifacts so they reflect the true (staged) repo state again.
    run_open_source_quant_stack_and_free_data_path()
    assert summary["oss_candidate_count"] >= 10
    assert summary["oss_imported_count"] == 0
    assert summary["oss_executed_count"] == 0
    assert summary["repo_cloned_count"] == 0
    assert summary["dependency_installed_count"] == 0
    assert summary["free_data_candidate_count"] >= 8
    assert summary["free_data_evidence_allowed_count"] == 0
    assert summary["network_fetch_performed"] is False
    assert summary["credentials_created"] is False
    assert summary["env_created"] is False
    assert summary["local_ohlcv_status"] == "missing_local_ohlcv_files"
    assert summary["local_ohlcv_fix_advice_status"] == "manual_staging_required"
    assert summary["valid_real_dataset"] is False
    assert summary["history_spine_upgrade_status"] == "blocked_missing_local_ohlcv"
    assert summary["real_history_used"] is False
    assert summary["strategy_promotion_allowed"] is False
    assert summary["alpha_vantage_excluded"] is True
    for path in summary["artifact_paths"].values():
        assert Path(path).exists()


def test_no_alpha_vantage_in_new_stack_files_or_artifacts() -> None:
    run_open_source_quant_stack_and_free_data_path()
    paths = [
        *list((REPO_ROOT / "dopey_open_source").glob("*.py")),
        REPO_ROOT / "dopey_data_ingestion" / "free_data_candidate_registry.py",
        REPO_ROOT / "dopey_data_ingestion" / "free_data_provenance_gate.py",
        OPEN_SOURCE_PATH_SUMMARY_PATH,
    ]
    for path in paths:
        assert "Alpha Vantage" not in path.read_text(encoding="utf-8")


def test_audit_reporting_export_and_validation_stabilizer_include_stack() -> None:
    artifact_names = {spec[0] for spec in ARTIFACT_SPECS}
    assert "open_source_quant_stack_and_free_data_path_summary" in artifact_names
    assert "local_ohlcv_import_fix_advice" in artifact_names
    assert "real_ohlcv_history_activation_blockers" in artifact_names
    export_ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "open_source_quant_stack_and_free_data_path_summary" in export_ids
    evidence = _empty_reporting_evidence({
        "oss_candidate_count": 12,
        "oss_imported_count": 0,
        "oss_executed_count": 0,
        "free_data_candidate_count": 8,
        "free_data_evidence_allowed_count": 0,
        "local_ohlcv_status": "missing_local_ohlcv_files",
        "local_ohlcv_fix_advice_status": "manual_staging_required",
        "history_spine_upgrade_status": "blocked_missing_local_ohlcv",
    })
    report_summary = _open_source_path_summary(evidence)
    assert report_summary["oss_candidate_count"] == 12
    assert report_summary["free_data_evidence_allowed_count"] == 0
    plan = write_test_shard_plan(
        ["tests/test_open_source_quant_stack_and_free_data_path.py"],
        [],
        {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}},
    )
    assert plan["open_source_free_data_path_test_files"] == ["tests/test_open_source_quant_stack_and_free_data_path.py"]
    assert plan["timeout_recorded_as_pass"] is False


def _empty_reporting_evidence(open_source_path_summary: dict) -> ReportingEvidence:
    fields = ReportingEvidence.__dataclass_fields__
    values = {field_name: {} for field_name in fields}
    values["open_source_path_summary"] = open_source_path_summary
    return ReportingEvidence(**values)
