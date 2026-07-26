from __future__ import annotations

from pathlib import Path

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_autonomy.autonomy_common import read_json, read_jsonl, write_jsonl
from dopey_autonomy.run_open_data_breakthrough_full_completion import run_open_data_breakthrough_full_completion, write_breakthrough_fixture_cases
from dopey_backtest.quote_priced_options_unlock_gate import run_quote_priced_options_unlock_gate
from dopey_data_ingestion.exhaustive_discovery_proof_report import run_exhaustive_discovery_proof_report
from dopey_data_ingestion.exhaustive_open_data_discovery_matrix import build_discovery_summary, default_discovery_candidates, run_exhaustive_open_data_discovery_matrix
from dopey_data_ingestion.exhaustive_open_data_discovery_models import ExhaustiveOpenDataCandidate
from dopey_data_ingestion.machine_license_terms_verifier import verify_candidate_license_terms
from dopey_data_ingestion.open_data_breakthrough_manifest_builder import run_open_data_breakthrough_manifest_builder
from dopey_data_ingestion.open_data_breakthrough_quarantine_downloader import RECORDS_PATH as DOWNLOAD_RECORDS_PATH
from dopey_data_ingestion.open_data_breakthrough_quarantine_downloader import run_open_data_breakthrough_quarantine_downloader
from dopey_data_ingestion.open_data_breakthrough_validator_bridge import run_open_data_breakthrough_validator_bridge
from dopey_data_ingestion.open_ohlcv_autonomous_normalizer import run_open_ohlcv_autonomous_normalizer
from dopey_export_review.review_models import FINDING_CATEGORIES
from dopey_options_autonomy.open_options_autonomous_normalizer import run_open_options_autonomous_normalizer
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_research_autonomy.model_priced_options_research_expansion import run_model_priced_options_research_expansion


def test_discovery_rejects_bad_sources_and_avoids_manual_review_statuses() -> None:
    summary = run_exhaustive_open_data_discovery_matrix()
    records = [candidate.to_dict() for candidate in default_discovery_candidates()]
    statuses = {record["machine_admissibility_status"] for record in records}

    assert summary["no_manual_review_status_count"] == 0
    assert not any("manual" in status or "operator" in status for status in statuses)
    assert "rejected_unknown_license" in statuses
    assert "rejected_ambiguous_terms" in statuses
    assert "rejected_credentials_required" in statuses
    assert "rejected_payment_required" in statuses
    assert "rejected_scrape_only" in statuses
    assert "rejected_alpha_vantage" in statuses
    assert "rejected_tradingview" in statuses


def test_machine_verified_permissive_ohlcv_and_options_candidates_are_accepted_in_summary() -> None:
    records = [
        _candidate("accepted-ohlcv", "open_ohlcv", "accepted_machine_verified_open_ohlcv_candidate").to_dict(),
        _candidate("accepted-options", "historical_options_quotes", "accepted_machine_verified_open_options_candidate").to_dict(),
    ]
    summary = build_discovery_summary(records)

    assert summary["accepted_ohlcv_candidate_count"] == 1
    assert summary["accepted_options_candidate_count"] == 1
    assert verify_candidate_license_terms(records[0])["license_terms_acceptance_allowed"] is True
    assert verify_candidate_license_terms(records[1])["license_terms_acceptance_allowed"] is True


def test_no_accepted_candidates_is_successful_blocked_completion() -> None:
    summary = run_open_data_breakthrough_quarantine_downloader()

    assert summary["download_status"] == "no_machine_admissible_sources"
    assert summary["download_attempt_count"] == 0
    assert summary["credentials_created"] is False
    assert summary["broker_connection_used"] is False


def test_normalizers_handle_no_files() -> None:
    write_jsonl(DOWNLOAD_RECORDS_PATH, [])

    ohlcv = run_open_ohlcv_autonomous_normalizer()
    options = run_open_options_autonomous_normalizer()

    assert ohlcv["open_ohlcv_normalization_status"] == "no_accepted_ohlcv_files"
    assert options["open_options_normalization_status"] == "no_machine_admissible_open_options_data"
    assert options["quote_priced_backtest_allowed"] is False
    assert options["model_priced_research_allowed"] is True


def test_accepted_fixture_files_normalize_manifest_bridge_and_unlock(tmp_path: Path) -> None:
    ohlcv_path = tmp_path / "accepted_ohlcv.csv"
    options_path = tmp_path / "accepted_options.csv"
    ohlcv_path.write_text(
        "date,symbol,open,high,low,close,adjusted_close,volume\n"
        "2024-01-02,SPY,470,475,468,474,474,1000000\n",
        encoding="utf-8",
    )
    options_path.write_text(
        "snapshot_date,underlying_symbol,contract_symbol,expiration_date,strike,option_type,bid,ask,last,volume,open_interest,implied_volatility\n"
        "2024-01-02,SPY,SPY240119C00475000,2024-01-19,475,call,2.1,2.3,2.2,100,1000,0.22\n",
        encoding="utf-8",
    )
    write_jsonl(
        DOWNLOAD_RECORDS_PATH,
        [
            _download_record("accepted-ohlcv", "open_ohlcv", ohlcv_path),
            _download_record("accepted-options", "historical_options_quotes", options_path),
        ],
    )

    ohlcv = run_open_ohlcv_autonomous_normalizer()
    options = run_open_options_autonomous_normalizer()
    manifest = run_open_data_breakthrough_manifest_builder()
    bridge = run_open_data_breakthrough_validator_bridge()
    quote = run_quote_priced_options_unlock_gate()

    assert ohlcv["normalized_ohlcv_file_count"] == 1
    assert options["normalized_options_file_count"] == 1
    assert manifest["manifest_status"] == "open_ohlcv_and_options_manifests_ready"
    assert bridge["valid_real_dataset"] is True
    assert bridge["quote_priced_backtest_allowed"] is True
    assert quote["quote_priced_backtest_allowed"] is True


def test_quote_unlock_blocked_and_model_priced_allowed_without_options() -> None:
    write_jsonl(DOWNLOAD_RECORDS_PATH, [])
    run_open_ohlcv_autonomous_normalizer()
    run_open_options_autonomous_normalizer()

    quote = run_quote_priced_options_unlock_gate()
    model = run_model_priced_options_research_expansion()

    assert quote["quote_priced_backtest_allowed"] is False
    assert quote["model_priced_research_allowed"] is True
    assert model["pricing_tier"] == "model_priced"
    assert model["quote_priced"] is False
    assert model["not_real_options_evidence"] is True
    assert model["not_profitability_claim"] is True
    assert model["not_live_ready"] is True


def test_discovery_proof_and_full_orchestrator_default_case_write_artifacts() -> None:
    write_jsonl(DOWNLOAD_RECORDS_PATH, [])
    proof = run_exhaustive_discovery_proof_report()
    summary = run_open_data_breakthrough_full_completion()
    fixtures = write_breakthrough_fixture_cases()

    assert proof["total_candidates_discovered"] >= 20
    assert proof["rejection_counts_by_reason"]
    assert summary["breakthrough_status"] == "max_discovery_complete_no_machine_admissible_ohlcv"
    assert summary["accepted_ohlcv_source_count"] == 0
    assert summary["accepted_options_source_count"] == 0
    assert summary["quote_priced_backtest_allowed"] is False
    assert summary["model_priced_research_allowed"] is True
    assert summary["strategy_promotion_allowed"] is False
    assert summary["live_promotion_allowed"] is False
    assert summary["profitability_claim"] is False
    assert summary["live_readiness_claim"] is False
    assert fixtures["fixture_case_count"] >= 300


def test_audit_reporting_export_review_and_validation_integration() -> None:
    artifact_types = {spec[0] for spec in ARTIFACT_SPECS}

    assert "open_data_breakthrough_full_completion_summary" in artifact_types
    assert "quote_priced_options_unlock_gate" in artifact_types
    assert "open_data_breakthrough_full_completion_summary" in EVIDENCE_PATHS
    assert "open_data_breakthrough" in FINDING_CATEGORIES
    assert Path("dopey_validation/full_suite_stabilizer.py").read_text(encoding="utf-8").find("test_open_data_breakthrough_and_options_evidence_completion.py") >= 0
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    assert hasattr(evidence, "open_data_breakthrough_full_completion_summary")


def test_no_forbidden_runtime_markers_in_breakthrough_outputs() -> None:
    summary = read_json(Path("artifacts/dopey/open_data_breakthrough/open_data_breakthrough_full_completion_summary.json"))
    records = read_jsonl(Path("artifacts/dopey/open_data_breakthrough/exhaustive_open_data_candidate_registry.jsonl"))

    assert summary.get("alpha_vantage_excluded", True) is True
    assert summary.get("tradingview_excluded", True) is True
    assert summary.get("credentials_created", False) is False
    assert summary.get("env_created", False) is False
    assert summary.get("broker_connection_used", False) is False
    assert summary.get("strategy_promotion_allowed", False) is False
    assert not any(record.get("source_name") == "Alpha Vantage" and record.get("machine_admissibility_status") != "rejected_alpha_vantage" for record in records)
    assert not any(record.get("source_name") == "TradingView" and record.get("machine_admissibility_status") != "rejected_tradingview" for record in records)


def _candidate(candidate_id: str, family: str, status: str) -> ExhaustiveOpenDataCandidate:
    return ExhaustiveOpenDataCandidate(
        candidate_id=candidate_id,
        source_name=candidate_id,
        source_url=f"https://example.invalid/{candidate_id}",
        discovery_channel="permissive_example_dataset",
        dataset_family=family,
        license_name="MIT",
        license_url=f"https://example.invalid/{candidate_id}/LICENSE",
        license_machine_verified=True,
        terms_url=f"https://example.invalid/{candidate_id}/terms",
        terms_machine_verified=True,
        requires_credentials=False,
        requires_login=False,
        requires_payment=False,
        requires_scraping=False,
        bulk_download_available=True,
        api_key_required=False,
        historical_depth_claim="fixture_claim",
        asset_coverage_claim="fixture_claim",
        options_data_claim="options" if "options" in family else "",
        ohlcv_data_claim="ohlcv" if family == "open_ohlcv" else "",
        schema_claim="fixture_schema",
        provenance_claim="fixture_provenance",
        direct_download_url="",
        machine_admissibility_status=status,
        reject_reason="",
    )


def _download_record(candidate_id: str, family: str, path: Path) -> dict:
    return {
        "artifact_type": "quarantine_download_records",
        "candidate_id": candidate_id,
        "dataset_family": family,
        "source_url": f"https://example.invalid/{candidate_id}",
        "license_name": "MIT",
        "terms_url": f"https://example.invalid/{candidate_id}/terms",
        "quarantine_path": str(path),
        "sha256": "fixture_hash",
        "size_bytes": path.stat().st_size,
        "paper_only": True,
        "live_blocked": True,
    }
