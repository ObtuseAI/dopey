from __future__ import annotations

import json
from pathlib import Path

from tests.test_local_free_ohlcv_import_validator_and_history_activation import _temporarily_clear_staging

from dopey_audit.artifact_loader import ARTIFACT_SPECS, build_inventory
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_data import ExportReviewContext
from dopey_export_review.review_models import NEXT_REVIEW_BUILD_TARGET
from dopey_export_review.review_packet import render_safety_summary
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _local_free_ohlcv_stack_summary
from dopey_validation.full_suite_stabilizer import collect_test_files, write_test_shard_plan
from dopey_data_ingestion.manual_free_ohlcv_source_candidates import manual_free_ohlcv_source_candidate_records
from dopey_data_ingestion.manual_ohlcv_import_fix_engine import build_manual_ohlcv_import_fix_plan_from_records
from dopey_data_ingestion.manual_ohlcv_manifest_draft import (
    LOCAL_REAL_DATA_MANIFEST_PATH,
    build_manual_ohlcv_manifest_draft,
    write_manual_ohlcv_manifest_draft,
)
from dopey_data_ingestion.manual_ohlcv_preflight_linter import _accepted_file_result, build_manual_ohlcv_preflight_summary
from dopey_data_ingestion.manual_ohlcv_staging_checklist import build_manual_ohlcv_staging_checklist
from dopey_data_ingestion.manual_ohlcv_staging_models import (
    MANUAL_OHLCV_STAGING_VERSION,
    ManualOhlcvStagingDecision,
    stable_manual_ohlcv_hash,
)
from dopey_data_ingestion.run_local_free_ohlcv_validation_and_activation_stack import (
    EXPORT_VERIFIER_TIMEOUT_NOTE_PATH,
    run_local_free_ohlcv_validation_and_activation_stack,
)


def test_model_serialization_and_hash_determinism() -> None:
    decision = ManualOhlcvStagingDecision(
        artifact_type="manual_ohlcv_staging_decision",
        staging_version=MANUAL_OHLCV_STAGING_VERSION,
        decision_id="case",
        manual_staging_status="manual_staging_required",
        manual_staging_decision="operator_must_stage_files",
        reason_codes=["missing_local_ohlcv_files"],
        real_data_files_present=False,
        valid_real_dataset=False,
        ready_for_local_ohlcv_validator=False,
        ready_for_history_spine_activation_after_validator_pass=False,
        strategy_promotion_allowed=False,
        paper_only=True,
        live_blocked=True,
        network_fetch_performed=False,
        credentials_created=False,
        env_created=False,
        broker_connection_used=False,
        not_strategy_promotion=True,
        decision_hash="",
    ).to_dict()
    assert decision == json.loads(json.dumps(decision, sort_keys=True))
    assert decision["decision_hash"] == stable_manual_ohlcv_hash(decision)
    assert decision["paper_only"] is True
    assert decision["live_blocked"] is True
    assert decision["network_fetch_performed"] is False


def test_source_candidates_exclude_alpha_vantage_and_require_manual_review() -> None:
    candidates = manual_free_ohlcv_source_candidate_records()
    assert len(candidates) == 8
    assert not any("alpha vantage" in candidate["source_name"].lower() for candidate in candidates)
    assert not any("robinhood" in json.dumps(candidate).lower() for candidate in candidates)
    assert all(candidate["manual_review_required"] is True for candidate in candidates)
    assert all(candidate["evidence_allowed"] is False for candidate in candidates)
    assert all(candidate["credentials_required"] is False for candidate in candidates)
    assert all(candidate["not_fetched_by_dopey"] is True for candidate in candidates)


def test_staging_checklist_required_folders_columns_and_manifest_fields() -> None:
    checklist = build_manual_ohlcv_staging_checklist()
    assert "dopey_data/real/raw/daily_ohlcv/" in checklist["required_folders"]
    assert "dopey_data/real/raw/market_context/" in checklist["required_folders"]
    assert "dopey_data/real/raw/corporate_actions/" in checklist["required_folders"]
    for column in ["date", "symbol", "open", "high", "low", "close", "adjusted_close", "volume", "source"]:
        assert column in checklist["required_daily_ohlcv_columns"]
    for field in ["manifest_id", "provider_terms_reviewed", "license_status", "file_hashes", "download_or_export_dates"]:
        assert field in checklist["required_manifest_fields"]


def test_manifest_draft_with_no_files_is_manual_staging_required_and_preserves_final_manifest() -> None:
    with _temporarily_clear_staging():
        before = LOCAL_REAL_DATA_MANIFEST_PATH.read_bytes() if LOCAL_REAL_DATA_MANIFEST_PATH.exists() else b""
        result = write_manual_ohlcv_manifest_draft()
        after = LOCAL_REAL_DATA_MANIFEST_PATH.read_bytes() if LOCAL_REAL_DATA_MANIFEST_PATH.exists() else b""
        assert before == after
        assert result["draft_status"] == "manual_staging_required"
        assert result["hash_record_count"] == 0
        assert result["real_data_files_present"] is False
        assert result["license_status"] == "unknown"
        assert result["provider_terms_reviewed"] is False
        assert build_manual_ohlcv_manifest_draft()["hash_records"] == []


def test_preflight_with_no_files_returns_manual_staging_required() -> None:
    summary = build_manual_ohlcv_preflight_summary([])
    assert summary["preflight_status"] == "manual_staging_required"
    assert summary["network_fetch_performed"] is False
    assert summary["credentials_created"] is False


def test_preflight_blocks_sample_only_rows(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("date,symbol,open,high,low,close,adjusted_close,volume,source,sample_only\n2026-01-01,SPY,1,1,1,1,1,1,fixture,true\n", encoding="utf-8")
    result = _accepted_file_result(path)
    assert result["sample_only_rows_detected"] is True
    assert "sample_only_rows" in result["reason_codes"]


def test_preflight_blocks_sample_only_symbol(tmp_path: Path) -> None:
    path = tmp_path / "sample_symbol.csv"
    path.write_text("date,symbol,open,high,low,close,adjusted_close,volume,source\n2026-01-01,SAMPLE_ONLY,1,1,1,1,1,1,fixture\n", encoding="utf-8")
    result = _accepted_file_result(path)
    assert result["sample_only_symbol_detected"] is True
    assert "SAMPLE_ONLY" in result["reason_codes"]


def test_preflight_blocks_credentials_tokens_and_live_markers(tmp_path: Path) -> None:
    path = tmp_path / "token.csv"
    path.write_text(
        "date,symbol,open,high,low,close,adjusted_close,volume,source\n"
        "2026-01-01,SPY,1,1,1,1,1,1,api_key=secret live_trading order_submit scheduler real_sizing\n",
        encoding="utf-8",
    )
    result = _accepted_file_result(path)
    assert result["credential_token_patterns_detected"] is True
    assert result["broker_live_order_scheduler_real_sizing_patterns_detected"] is True
    assert result["terminal_block"] is True


def test_preflight_blocks_quality_candidates(tmp_path: Path) -> None:
    path = tmp_path / "quality.csv"
    path.write_text(
        "date,symbol,open,high,low,close,adjusted_close,volume,source\n"
        "2999-01-01,SPY,10,8,9,10,10,1,manual\n"
        "2999-01-01,SPY,10,8,9,10,10,1,manual\n",
        encoding="utf-8",
    )
    result = _accepted_file_result(path)
    assert result["future_dates_candidate_detected"] is True
    assert result["high_low_inconsistency_candidate_detected"] is True
    assert result["duplicate_date_symbol_rows_detected"] is True


def test_fix_plan_with_no_files_says_stage_files() -> None:
    result = build_manual_ohlcv_import_fix_plan_from_records(
        {"local_ohlcv_status": "missing_local_ohlcv_files"},
        {"preflight_status": "manual_staging_required"},
        {"real_data_files_present": False},
        [],
        [],
        [],
        [],
        [],
    )
    assert result["plan"]["fix_plan_status"] == "manual_staging_required"
    assert result["items"][0]["fix_group"] == "stage_files"
    assert result["plan"]["real_evidence_claim_allowed"] is False


def test_fix_plan_groups_schema_quality_license_sample_live_and_hash_errors() -> None:
    result = build_manual_ohlcv_import_fix_plan_from_records(
        {"local_ohlcv_status": "local_ohlcv_validation_fail"},
        {"preflight_status": "preflight_fail", "final_manifest_template_only": True},
        {"real_data_files_present": True},
        [{"result_id": "p", "local_file_path": "x.csv", "reason_codes": ["missing_required_header", "sample_only_rows", "credentials_tokens", "future_dates"]}],
        [{"result_id": "s", "local_file_path": "x.csv", "schema_pass": False}],
        [{"result_id": "q", "local_file_path": "x.csv", "reason_codes": ["duplicate_date_symbol", "sample_template_contamination", "credential_or_token_contamination"]}],
        [{"result_id": "l", "local_file_path": "x.csv", "reason_codes": ["missing_license", "missing_file_hash", "file_hash_mismatch"]}],
        [{"manual_review_required": True}],
    )
    groups = result["plan"]["fix_group_counts"]
    assert groups["repair_schema"] > 0
    assert groups["repair_quality"] > 0
    assert groups["repair_license_provenance"] > 0
    assert groups["remove_sample_template_rows"] > 0
    assert groups["remove_credentials_or_live_markers"] > 0
    assert groups["repair_hash_mismatch"] > 0


def test_combined_stack_preserves_blocked_no_files_state() -> None:
    with _temporarily_clear_staging():
        summary = run_local_free_ohlcv_validation_and_activation_stack()
    # Refresh stack artifacts so they reflect the true (staged) repo state again.
    run_local_free_ohlcv_validation_and_activation_stack()
    assert summary["manual_staging_status"] == "manual_staging_required"
    assert summary["manual_staging_decision"] == "operator_must_stage_files"
    assert summary["manifest_draft_status"] == "manual_staging_required"
    assert summary["preflight_status"] == "manual_staging_required"
    assert summary["fix_plan_status"] == "manual_staging_required"
    assert summary["local_ohlcv_status"] == "missing_local_ohlcv_files"
    assert summary["valid_real_dataset"] is False
    assert summary["history_spine_activation_status"] == "blocked_missing_local_ohlcv"
    assert summary["real_signal_validation_status"] == "blocked_missing_valid_real_history"
    assert summary["real_signal_evidence"] is False
    assert summary["network_fetch_performed"] is False
    assert summary["credentials_created"] is False
    assert summary["env_created"] is False
    assert summary["broker_connection_used"] is False
    assert summary["strategy_promotion_allowed"] is False


def test_manual_staging_artifacts_written_and_fixture_cases_exist() -> None:
    summary = run_local_free_ohlcv_validation_and_activation_stack()
    for path_text in summary["artifact_paths"].values():
        assert Path(path_text).exists()
    fixture_total = 0
    for path_text in summary["fixture_paths"]:
        parsed = json.loads(Path(path_text).read_text(encoding="utf-8"))
        fixture_total += parsed["case_count"]
        assert all(case["fixture_only"] and case["sample_only"] and case["not_real_data"] for case in parsed["cases"])
    assert fixture_total >= 120


def test_audit_recognizes_manual_artifacts() -> None:
    run_local_free_ohlcv_validation_and_activation_stack()
    artifact_types = {spec[0] for spec in ARTIFACT_SPECS}
    for artifact_type in [
        "manual_free_ohlcv_source_candidates",
        "manual_ohlcv_staging_checklist",
        "manual_ohlcv_hash_records",
        "manual_ohlcv_manifest_draft",
        "manual_ohlcv_preflight_results",
        "manual_ohlcv_preflight_summary",
        "manual_ohlcv_import_fix_plan",
        "manual_ohlcv_import_fix_items",
        "manual_ohlcv_staging_summary",
        "manual_ohlcv_staging_proof",
    ]:
        assert artifact_type in artifact_types
    inventory_types = {artifact.artifact_type for artifact in build_inventory().artifacts}
    assert "manual_ohlcv_staging_summary" in inventory_types


def test_reporting_includes_manual_staging_summary() -> None:
    with _temporarily_clear_staging():
        run_local_free_ohlcv_validation_and_activation_stack()
        evidence = load_reporting_evidence(EVIDENCE_PATHS)
    # Refresh stack artifacts so they reflect the true (staged) repo state again.
    run_local_free_ohlcv_validation_and_activation_stack()
    summary = _local_free_ohlcv_stack_summary(evidence)
    assert summary["manual_staging_status"] == "manual_staging_required"
    assert summary["manual_staging_decision"] == "operator_must_stage_files"
    assert summary["source_candidate_count"] == 8
    assert summary["hash_record_count"] == 0


def test_export_includes_manual_artifacts_and_docs() -> None:
    rules = export_selection_rules()
    paths = {rule.source_path for rule in rules}
    assert "docs/reports/DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_REPORT.md" in paths
    assert "artifacts/dopey/manual_ohlcv_staging/manual_ohlcv_staging_summary.json" in paths
    assert "artifacts/dopey/manual_ohlcv_staging/manual_ohlcv_import_fix_plan.json" in paths
    assert "artifacts/dopey/manual_ohlcv_staging/export_verifier_timeout_note.json" in paths


def test_export_review_mentions_manual_staging_safety() -> None:
    ctx = ExportReviewContext(
        safety_state={"mode": "RESEARCH", "live_trading_enabled": False, "funded_broker_connections_enabled": False, "allow_unofficial_robinhood_api": False},
        export_registry={},
        export_manifest={},
        export_safety_scan={"active_forbidden_live_decisions": 0, "credential_findings": 0},
        export_copy_proof={},
        export_verification={},
        reporting_summary={"local_free_ohlcv_stack_summary": {"manual_staging_status": "manual_staging_required"}},
        dashboard_index={},
        strategy_cards=[],
        family_cards=[],
        audit_gap_plan={},
        audit_summary={},
        source_export_path=Path("."),
        shared_export_path="",
        manifest_registry_path=Path("."),
        copy_proof_registry_path=Path("."),
    )
    rendered = render_safety_summary(ctx)
    assert "market_data_fetched_by_dopey: `false`" in rendered
    assert "credentials_or_env_created: `false`" in rendered
    assert "alpha_vantage_candidate_exists: `false`" in rendered
    assert NEXT_REVIEW_BUILD_TARGET == "DOPEY_MANUAL_STAGE_FREE_OHLCV_FILES_AND_RERUN_VALIDATOR"


def test_validation_stabilizer_includes_manual_test_shard() -> None:
    files = collect_test_files()
    assert "tests/test_manual_free_ohlcv_staging_or_local_import_fix.py" in files
    plan = write_test_shard_plan(
        files,
        [],
        {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}},
    )
    assert "tests/test_manual_free_ohlcv_staging_or_local_import_fix.py" in plan["local_free_ohlcv_stack_test_files"]
    assert plan["timeout_recorded_as_pass"] is False


def test_export_verifier_timeout_note_remains_inconclusive_not_pass() -> None:
    run_local_free_ohlcv_validation_and_activation_stack()
    note = json.loads(EXPORT_VERIFIER_TIMEOUT_NOTE_PATH.read_text(encoding="utf-8"))
    assert note["prior_export_verifier_status"] == "inconclusive_timeout"
    assert note["timeout_counts_as_pass"] is False
    assert note["preserve_last_successful_export_record_separately"] is True


def test_full_pytest_timeout_remains_inconclusive_not_pass() -> None:
    plan = write_test_shard_plan(
        collect_test_files(),
        [],
        {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}},
    )
    assert plan["full_suite_status"] == "inconclusive_timeout"
    assert plan["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled_and_no_credentials_or_env() -> None:
    summary = run_local_free_ohlcv_validation_and_activation_stack()
    assert summary["paper_only"] is True
    assert summary["live_blocked"] is True
    assert summary["broker_connection_used"] is False
    assert summary["credentials_created"] is False
    assert summary["env_created"] is False
    assert summary["strategy_promotion_allowed"] is False
