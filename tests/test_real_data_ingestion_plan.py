from __future__ import annotations

import csv

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_data_ingestion.dataset_requirement_catalog import dataset_requirement_records
from dopey_data_ingestion.ingestion_plan_models import DataIngestionPlan
from dopey_data_ingestion.local_staging_contract import REAL_DATA_MANIFEST_PATH
from dopey_data_ingestion.provider_candidate_registry import provider_candidate_records
from dopey_data_ingestion.run_real_data_ingestion_plan import run_real_data_ingestion_plan
from dopey_data_ingestion.schema_contracts import sample_row_is_real_candidate, sample_template_paths


def test_ingestion_plan_models_are_hash_deterministic() -> None:
    plan = DataIngestionPlan(
        artifact_type="data_ingestion_plan",
        ingestion_plan_version="x",
        plan_id="plan",
        ingestion_status="real_data_ingestion_plan_ready",
        import_readiness_decision="plan_ready_import_not_started",
        dataset_requirement_count=8,
        provider_candidate_count=11,
        schema_contract_count=8,
        quality_gate_count=137,
        objective="offline contract",
        allowed_later_bundles=["DOPEY_LOCAL_OHLCV_IMPORT_VALIDATOR_V1"],
        network_fetch_performed=False,
        broker_connection_used=False,
        credentials_created=False,
        env_created=False,
        real_data_files_present=False,
        real_data_ingested=False,
        real_data_validated=False,
        not_real_evidence=True,
        not_strategy_promotion=True,
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        plan_hash="",
    )
    first = plan.to_dict()
    second = DataIngestionPlan(**first).to_dict()
    assert first["plan_hash"] == second["plan_hash"]


def test_ingestion_plan_catalog_provider_and_runner_outputs() -> None:
    summary = run_real_data_ingestion_plan()
    if summary["real_data_files_present"]:
        assert summary["ingestion_status"] in {
            "manual_review_required",
            "missing_provider_selection",
            "terminal_block",
        }
        assert summary["import_readiness_decision"] != "plan_ready_import_not_started"
    else:
        assert summary["ingestion_status"] == "real_data_ingestion_plan_ready"
        assert summary["import_readiness_decision"] == "plan_ready_import_not_started"
    assert summary["dataset_requirement_count"] == 8
    assert summary["provider_candidate_count"] == 11
    assert summary["schema_contract_count"] == 8
    assert summary["quality_gate_count"] == 137
    assert isinstance(summary["real_data_files_present"], bool)
    assert summary["real_data_ingested"] is False
    assert summary["real_data_validated"] is False
    assert summary["network_fetch_performed"] is False
    assert summary["broker_connection_used"] is False
    assert summary["credentials_created"] is False
    assert summary["env_created"] is False
    assert {record["dataset_family"] for record in dataset_requirement_records()} == {
        "daily_ohlcv",
        "corporate_actions",
        "historical_options_chain",
        "historical_options_quotes",
        "fundamentals",
        "earnings_calendar",
        "market_context",
        "benchmark_and_universe_metadata",
    }
    assert all(record["status"] == "manual_review_required" for record in provider_candidate_records() if record["credential_required"])


def test_ingestion_plan_sample_templates_are_not_real() -> None:
    run_real_data_ingestion_plan()
    for path_text in sample_template_paths():
        with open(path_text, "r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert rows
        assert rows[0]["sample_only"] == "true"
        assert rows[0]["not_real_data"] == "true"
        assert not sample_row_is_real_candidate(rows[0])


def test_ingestion_plan_preserves_existing_operator_manifest() -> None:
    if not REAL_DATA_MANIFEST_PATH.exists():
        return
    before = REAL_DATA_MANIFEST_PATH.read_bytes()
    run_real_data_ingestion_plan()
    assert REAL_DATA_MANIFEST_PATH.read_bytes() == before


def test_audit_recognizes_ingestion_artifacts() -> None:
    artifact_types = {spec[0] for spec in ARTIFACT_SPECS}
    assert "data_ingestion_plan" in artifact_types
    assert "import_readiness_decision" in artifact_types
    assert "data_ingestion_plan_summary" in artifact_types
