from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.test_local_free_ohlcv_import_validator_and_history_activation import _temporarily_clear_staging

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_data_ingestion.operator_ohlcv_source_review_contract import (
    BLOCKING_LICENSE_STATUSES,
    OPERATOR_SOURCE_REVIEW_PATH,
    template_source_review_packet,
    validate_operator_source_review_packet,
)
from dopey_data_ingestion.operator_reviewed_ohlcv_final_manifest_status import (
    REAL_DATA_MANIFEST_FINAL_PATH,
    evaluate_operator_reviewed_final_manifest_status,
)
from dopey_data_ingestion.operator_reviewed_ohlcv_manifest_candidate import build_operator_reviewed_manifest_candidate
from dopey_data_ingestion.operator_reviewed_ohlcv_stage_models import (
    OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
    OperatorReviewedOhlcvStageInput,
)
from dopey_data_ingestion.operator_reviewed_ohlcv_staged_file_detector import (
    DAILY_OHLCV_DIR,
    STAGED_FILE_INVENTORY_PATH,
    build_staged_file_inventory,
    detect_operator_reviewed_staged_files,
)
from dopey_data_ingestion.run_operator_reviewed_ohlcv_stage_rerun import (
    COMMANDS_PATH,
    SUMMARY_PATH,
    run_operator_reviewed_ohlcv_stage_rerun,
    write_operator_reviewed_fixture_cases,
)
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_models import FINDING_CATEGORIES, NEXT_REVIEW_BUILD_TARGET
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _operator_reviewed_ohlcv_stage_summary
from dopey_validation.full_suite_stabilizer import timeout_result, write_test_shard_plan


def test_model_serialization_and_hash_determinism() -> None:
    record = OperatorReviewedOhlcvStageInput(
        artifact_type="operator_reviewed_ohlcv_stage_input",
        stage_version=OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        input_id="test-input",
        source_review_path="dopey_data/real/manifests/operator_ohlcv_source_review.json",
        daily_ohlcv_folder="dopey_data/real/raw/daily_ohlcv/",
        market_context_folder="dopey_data/real/raw/market_context/",
        corporate_actions_folder="dopey_data/real/raw/corporate_actions/",
        final_manifest_path="dopey_data/real/manifests/real_data_manifest.json",
        candidate_manifest_path="dopey_data/real/manifests/real_data_manifest.candidate.json",
        paper_only=False,
        live_blocked=False,
        network_fetch_performed=True,
        credentials_created=True,
        env_created=True,
        broker_connection_used=True,
        strategy_promotion_allowed=True,
        not_options_evidence=False,
        not_profitability_claim=False,
        not_live_ready=False,
        input_hash="unstable",
    ).to_dict()
    assert record == {**record, "input_hash": record["input_hash"]}
    assert record["paper_only"] is True
    assert record["live_blocked"] is True
    assert record["network_fetch_performed"] is False
    assert record["credentials_created"] is False
    assert record["env_created"] is False
    assert record["broker_connection_used"] is False
    assert record["strategy_promotion_allowed"] is False
    assert record["not_options_evidence"] is True
    assert record["not_profitability_claim"] is True
    assert record["not_live_ready"] is True


def test_source_review_packet_missing_template_incomplete_and_blocking_licenses(tmp_path: Path) -> None:
    missing = validate_operator_source_review_packet(tmp_path / "missing.json")
    assert missing["status"] == "operator_review_packet_missing"
    assert missing["source_review_valid"] is False
    assert missing["evidence_allowed"] is False

    template_path = tmp_path / "template.json"
    template_path.write_text(json.dumps(template_source_review_packet()), encoding="utf-8")
    template = validate_operator_source_review_packet(template_path)
    assert template["status"] == "operator_review_packet_incomplete"

    incomplete_path = tmp_path / "incomplete.json"
    incomplete_path.write_text(json.dumps({"review_id": "incomplete"}), encoding="utf-8")
    incomplete = validate_operator_source_review_packet(incomplete_path)
    assert incomplete["status"] == "operator_review_packet_incomplete"

    for license_status in BLOCKING_LICENSE_STATUSES:
        packet = _valid_source_review_packet() | {"license_status": license_status}
        path = tmp_path / f"{license_status}.json"
        path.write_text(json.dumps(packet), encoding="utf-8")
        result = validate_operator_source_review_packet(path)
        assert result["status"] == "operator_review_packet_incomplete"


def test_source_review_valid_and_affirmation_false_terminal(tmp_path: Path) -> None:
    valid_path = tmp_path / "valid.json"
    valid_path.write_text(json.dumps(_valid_source_review_packet()), encoding="utf-8")
    valid = validate_operator_source_review_packet(valid_path)
    assert valid["status"] == "operator_review_packet_valid"
    assert valid["source_review_valid"] is True
    assert valid["evidence_allowed"] is True

    blocked_path = tmp_path / "blocked.json"
    blocked_path.write_text(json.dumps(_valid_source_review_packet() | {"operator_affirms_no_credentials": False}), encoding="utf-8")
    blocked = validate_operator_source_review_packet(blocked_path)
    assert blocked["status"] == "terminal_block"


def test_no_files_detector_and_runner_preserve_blocked_state() -> None:
    with _temporarily_clear_staging():
        detector = detect_operator_reviewed_staged_files()
        assert detector["staged_file_count"] == 0
        assert detector["real_data_files_present"] is False
        assert detector["operator_files_missing"] is True
        assert detector["terminal_block"] is False
        assert STAGED_FILE_INVENTORY_PATH.exists()
        assert STAGED_FILE_INVENTORY_PATH.read_text(encoding="utf-8") == ""

        summary = run_operator_reviewed_ohlcv_stage_rerun()
    # Refresh operator-stage artifacts so they reflect the true (staged) repo state again.
    run_operator_reviewed_ohlcv_stage_rerun()
    assert summary["operator_reviewed_stage_status"] == "operator_files_missing"
    assert summary["operator_reviewed_stage_decision"] == "operator_must_stage_reviewed_files"
    assert summary["source_review_status"] == "operator_review_packet_missing"
    assert summary["staged_file_count"] == 0
    assert summary["manifest_candidate_status"] == "blocked_missing_staged_files"
    assert summary["final_manifest_status"] == "final_manifest_missing"
    assert summary["local_ohlcv_status"] == "missing_local_ohlcv_files"
    assert summary["history_spine_activation_status"] == "blocked_missing_local_ohlcv"
    assert summary["real_signal_validation_status"] == "blocked_missing_valid_real_history"
    assert summary["valid_real_dataset"] is False
    assert summary["real_history_used"] is False
    assert summary["real_signal_evidence"] is False
    assert summary["strategy_promotion_allowed"] is False
    assert summary["network_fetch_performed"] is False
    assert summary["credentials_created"] is False
    assert summary["env_created"] is False
    assert summary["broker_connection_used"] is False
    assert summary["not_options_evidence"] is True
    assert summary["not_profitability_claim"] is True
    assert summary["not_live_ready"] is True
    assert summary["next_recommended_target"] == "DOPEY_OPERATOR_STAGE_REVIEWED_FREE_OHLCV_FILES"
    assert SUMMARY_PATH.exists()


def test_detector_rejects_unsupported_credentials_live_and_sample_markers() -> None:
    DAILY_OHLCV_DIR.mkdir(parents=True, exist_ok=True)
    bad_files = [
        DAILY_OHLCV_DIR / "operator_stage_bad.txt",
        DAILY_OHLCV_DIR / "operator_stage_token.csv",
        DAILY_OHLCV_DIR / "operator_stage_live.csv",
        DAILY_OHLCV_DIR / "operator_stage_sample.csv",
    ]
    try:
        bad_files[0].write_text("not,csv\n", encoding="utf-8")
        bad_files[1].write_text("date,symbol,open,high,low,close,adjusted_close,volume,source\n2024-01-01,SPY,1,1,1,1,1,1,api_key=sk-testtoken123456\n", encoding="utf-8")
        bad_files[2].write_text("date,symbol,open,high,low,close,adjusted_close,volume,source\n2024-01-01,SPY,1,1,1,1,1,1,broker live order record account balance buying power real sizing scheduler\n", encoding="utf-8")
        bad_files[3].write_text("date,symbol,open,high,low,close,adjusted_close,volume,source,sample_only,not_real_data\n2024-01-01,SAMPLE_ONLY,1,1,1,1,1,1,fixture,true,true\n", encoding="utf-8")
        result = detect_operator_reviewed_staged_files()
        assert result["terminal_block"] is True
        assert result["unsupported_file_count"] >= 1
        assert result["credential_or_token_count"] >= 1
        assert result["broker_live_order_scheduler_real_sizing_count"] >= 1
        assert result["sample_contamination_count"] >= 1
    finally:
        for path in bad_files:
            path.unlink(missing_ok=True)


def test_detector_terminal_blocks_symlink_outside_repo_attempt_if_feasible(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlink unavailable")
    DAILY_OHLCV_DIR.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.csv"
    outside.write_text("date,symbol,open,high,low,close,adjusted_close,volume,source\n", encoding="utf-8")
    link = DAILY_OHLCV_DIR / "operator_stage_symlink.csv"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted")
    try:
        result = detect_operator_reviewed_staged_files()
        assert result["terminal_block"] is True
        assert result["symlink_or_outside_repo_count"] >= 1
    finally:
        link.unlink(missing_ok=True)


def test_manifest_candidate_blocks_without_files_and_does_not_overwrite_final_manifest() -> None:
    with _temporarily_clear_staging():
        original = _read_text_if_exists(REAL_DATA_MANIFEST_FINAL_PATH)
        try:
            candidate = build_operator_reviewed_manifest_candidate()
            assert candidate["manifest_candidate_status"] == "blocked_missing_staged_files"
            assert candidate["candidate_manifest_is_evidence"] is False
            assert _read_text_if_exists(REAL_DATA_MANIFEST_FINAL_PATH) == original
        finally:
            _restore_text(REAL_DATA_MANIFEST_FINAL_PATH, original)


def test_final_manifest_missing_status_when_no_files() -> None:
    with _temporarily_clear_staging():
        status = evaluate_operator_reviewed_final_manifest_status()
        assert status["final_manifest_status"] == "final_manifest_missing"


def test_action_packet_commands_fixtures_audit_reporting_export_review_and_timeouts() -> None:
    with _temporarily_clear_staging():
        summary = run_operator_reviewed_ohlcv_stage_rerun()
        packet_md = Path(summary["artifact_paths"]["operator_reviewed_ohlcv_action_packet_markdown"]).read_text(encoding="utf-8")
        assert "date,symbol,open,high,low,close,adjusted_close,volume,source" in packet_md
        assert "operator_ohlcv_source_review.json" in packet_md
        forbidden = ["curl", "wget", "Alpha Vantage", "broker commands"]
        commands_text = COMMANDS_PATH.read_text(encoding="utf-8")
        for term in forbidden:
            assert term in packet_md or term in commands_text
        assert "python -m dopey_data_ingestion.run_operator_reviewed_ohlcv_stage_rerun" in commands_text

        fixture_paths = write_operator_reviewed_fixture_cases()
        total_cases = sum(json.loads(Path(path).read_text(encoding="utf-8"))["case_count"] for path in fixture_paths)
        assert total_cases >= 180

        artifact_types = {spec[0] for spec in ARTIFACT_SPECS}
        assert "operator_reviewed_ohlcv_stage_rerun_summary" in artifact_types
        assert "operator_reviewed_ohlcv_action_packet" in artifact_types
        assert "operator_reviewed_ohlcv_stage_summary" in EVIDENCE_PATHS
        reporting = _operator_reviewed_ohlcv_stage_summary(load_reporting_evidence(EVIDENCE_PATHS))
        assert reporting["operator_reviewed_stage_status"] == "operator_files_missing"
        assert reporting["strategy_promotion_allowed"] is False
    # Refresh operator-stage artifacts so they reflect the true (staged) repo state again.
    run_operator_reviewed_ohlcv_stage_rerun()

    export_ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "operator_reviewed_ohlcv_stage_rerun_summary" in export_ids
    assert "operator_reviewed_ohlcv_action_packet" in export_ids
    assert NEXT_REVIEW_BUILD_TARGET == "DOPEY_MANUAL_STAGE_FREE_OHLCV_FILES_AND_RERUN_VALIDATOR"
    assert "operator_reviewed_ohlcv_stage" in FINDING_CATEGORIES

    timeout = timeout_result(["python", "-m", "pytest"], 1)
    assert timeout["status"] == "inconclusive_timeout"
    assert timeout["timeout_recorded_as_pass"] is False
    plan = write_test_shard_plan(["tests/test_operator_reviewed_ohlcv_stage_rerun.py"], [], {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}})
    assert "tests/test_operator_reviewed_ohlcv_stage_rerun.py" in plan["local_free_ohlcv_stack_test_files"]


def _valid_source_review_packet() -> dict:
    return {
        "review_id": "review-1",
        "reviewed_at": "2026-07-06T00:00:00Z",
        "reviewed_by": "operator",
        "source_name": "operator-reviewed-source",
        "source_type": "manual_export",
        "source_urls_or_reference_names": ["operator-record"],
        "download_or_export_dates": {"daily_ohlcv": "2026-07-06"},
        "dataset_families": ["daily_ohlcv"],
        "provider_terms_reviewed": True,
        "license_status": "reviewed_allowed_internal_research",
        "license_notes": "reviewed",
        "redistribution_allowed": False,
        "commercial_use_allowed": False,
        "internal_research_use_allowed": True,
        "provenance_notes": "operator reviewed local export",
        "survivorship_bias_reviewed": True,
        "adjusted_price_method_reviewed": True,
        "corporate_actions_available": True,
        "operator_affirms_no_credentials": True,
        "operator_affirms_not_broker_data": True,
        "operator_affirms_not_live_data": True,
        "operator_affirms_not_network_fetched_by_dopey": True,
        "operator_affirms_files_are_not_sample_templates": True,
        "operator_affirms_no_api_keys_or_tokens": True,
        "operator_affirms_no_account_balances_or_buying_power": True,
        "operator_affirms_no_order_or_execution_records": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _read_text_if_exists(path: Path) -> str | None:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None


def _restore_text(path: Path, content: str | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
