from __future__ import annotations

import json
from pathlib import Path

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_autonomy import full_open_source_autonomous_orchestrator as full_autonomy_module
from dopey_autonomy.autonomous_admissibility_kernel import evaluate_autonomous_admissibility
from dopey_autonomy.autonomy_common import CandidateInput, write_autonomy_fixture_cases
from dopey_autonomy.full_open_source_autonomous_orchestrator import run_full_open_source_autonomous_orchestrator
from dopey_data_ingestion.autonomous_open_data_manifest_builder import run_autonomous_open_data_manifest_builder
from dopey_data_ingestion.autonomous_open_data_quarantine_fetcher import run_autonomous_open_data_quarantine_fetcher
from dopey_data_ingestion.autonomous_open_data_source_discovery import run_autonomous_open_data_source_discovery
from dopey_data_ingestion.autonomous_open_data_validator_bridge import run_autonomous_open_data_validator_bridge
from dopey_data_ingestion.autonomous_open_ohlcv_normalizer import run_autonomous_open_ohlcv_normalizer
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_models import FINDING_CATEGORIES
from dopey_open_source.autonomous_oss_quant_discovery import run_autonomous_oss_quant_discovery
from dopey_options_autonomy.open_options_data_autonomy_plan import run_open_options_data_autonomy_plan
from dopey_paper_autonomy.autonomous_paper_trading_loop import run_autonomous_paper_trading_loop
from dopey_reporting.data_loader import EVIDENCE_PATHS, ReportingEvidence
from dopey_reporting.reporting_bundle import _open_source_autonomous_options_trader_summary
from dopey_research_autonomy.autonomous_backtest_stat_fitness_pipeline import run_autonomous_backtest_stat_fitness_pipeline
from dopey_research_autonomy.autonomous_strategy_search import build_autonomous_strategy_candidates
from dopey_research_autonomy.run_autonomous_research_engine import run_autonomous_research_engine
from dopey_research_autonomy.s_tier_options_benchmark import run_s_tier_options_benchmark
from dopey_validation.full_suite_stabilizer import timeout_result, write_test_shard_plan

def test_autonomous_admissibility_rejects_unsafe_sources_and_accepts_permissive() -> None:
    cases = [
        CandidateInput("unknown", "unknown", "daily_ohlcv", "", "https://example.invalid", False, True, False, False, False, False, False, False, False, "", "", True),
        CandidateInput("credentials", "credentials", "daily_ohlcv", "MIT", "https://example.invalid", True, True, True, False, False, False, False, False, False, "", "", True),
        CandidateInput("paid", "paid", "daily_ohlcv", "MIT", "https://example.invalid", True, True, False, True, False, False, False, False, False, "", "", True),
        CandidateInput("ambiguous", "ambiguous", "daily_ohlcv", "MIT", "https://example.invalid", True, False, False, False, False, False, False, False, False, "", "", True),
        CandidateInput("permissive", "permissive", "repo", "MIT", "https://example.invalid", True, True, False, False, False, False, False, False, False, "license", "", True),
    ]
    result = evaluate_autonomous_admissibility(cases)
    records = _read_jsonl(Path(result["artifact_paths"]["autonomous_source_admissibility_records"]))
    decisions = {record["source_id"]: record["decision"] for record in records}
    assert decisions["unknown"] == "rejected_unknown_license"
    assert decisions["credentials"] == "rejected_credentials_required"
    assert decisions["paid"] == "rejected_proprietary_or_paid"
    assert decisions["ambiguous"] == "rejected_ambiguous_terms"
    assert decisions["permissive"] == "accepted_machine_verified_open"
    assert result["no_manual_review_status_emitted"] is True
    assert "manual_review_required" not in json.dumps(result)
    assert "operator_review_required" not in json.dumps(result)


def test_oss_and_open_data_discovery_are_safe_and_artifact_backed() -> None:
    oss = run_autonomous_oss_quant_discovery()
    data = run_autonomous_open_data_source_discovery()
    assert oss["open_source_candidate_count"] >= 10
    assert oss["open_source_accepted_count"] >= 1
    assert oss["repo_cloned_count"] == 0
    assert oss["external_code_executed_count"] == 0
    assert data["open_data_candidate_count"] >= 8
    assert data["alpha_vantage_excluded"] is True
    assert data["credentials_created"] is False
    assert data["broker_connection_used"] is False
    for path in [*oss["artifact_paths"].values(), *data["artifact_paths"].values()]:
        assert Path(path).exists()


def test_data_lanes_complete_blocked_without_admissible_ingest_files() -> None:
    fetch = run_autonomous_open_data_quarantine_fetcher()
    normalizer = run_autonomous_open_ohlcv_normalizer()
    manifest = run_autonomous_open_data_manifest_builder()
    bridge = run_autonomous_open_data_validator_bridge()
    assert fetch["fetch_status"] == "no_machine_admissible_sources"
    assert fetch["fetch_attempt_count"] == 0
    assert normalizer["normalization_status"] == "blocked_no_accepted_open_ohlcv_files"
    assert manifest["manifest_status"] == "no_accepted_open_data_files"
    assert bridge["autonomous_open_data_status"] == "no_accepted_open_data_sources"
    assert bridge["valid_real_dataset"] is False


def test_options_research_fitness_paper_and_benchmark_remain_honest_without_evidence() -> None:
    options = run_open_options_data_autonomy_plan()
    research = run_autonomous_research_engine()
    pipeline = run_autonomous_backtest_stat_fitness_pipeline()
    paper = run_autonomous_paper_trading_loop()
    benchmark = run_s_tier_options_benchmark()
    assert options["options_data_status"] == "no_machine_admissible_open_options_data"
    assert options["quote_priced_backtest_allowed"] is False
    assert options["model_priced_research_allowed"] is True
    assert research["research_status"] == "blocked_no_accepted_real_data"
    assert {record["intent"] for record in build_autonomous_strategy_candidates([{"signal_id": "a", "direction": "bullish", "data_tier": "accepted_open_ohlcv_only"}, {"signal_id": "b", "direction": "bearish", "data_tier": "accepted_open_ohlcv_only"}, {"signal_id": "c", "direction": "neutral", "data_tier": "accepted_open_ohlcv_only"}])} == {"long_call", "long_put", "no_trade"}
    assert pipeline["research_promotion_status"] == "blocked_missing_evidence"
    assert paper["paper_loop_status"] == "blocked_no_accepted_real_data"
    assert benchmark["s_tier_engineering_progress"] is True
    assert benchmark["s_tier_live_superiority_claim"] is False
    assert benchmark["live_readiness_claim"] is False


def test_full_orchestrator_artifacts_integration_and_safety_boundaries() -> None:
    result = run_full_open_source_autonomous_orchestrator()
    assert result["autonomy_status"] == "max_completion_no_machine_admissible_open_data"
    assert result["valid_real_dataset"] is False
    assert result["quote_priced_backtest_allowed"] is False
    assert result["model_priced_research_allowed"] is True
    assert result["credentials_created"] is False
    assert result["env_created"] is False
    assert result["broker_connection_used"] is False
    assert result["alpha_vantage_excluded"] is True
    assert result["strategy_promotion_allowed"] is False
    assert result["not_profitability_claim"] is True
    assert result["not_live_ready"] is True
    assert Path(result["artifact_paths"]["full_open_source_autonomous_orchestrator_summary"]).exists()
    assert full_autonomy_module.REPORT_PATH.exists()
    assert full_autonomy_module.COMMANDS_PATH.exists()


def test_fixtures_and_audit_reporting_export_review_validation_hooks() -> None:
    fixtures = write_autonomy_fixture_cases()
    assert fixtures["fixture_case_count"] >= 350
    assert all(json.loads(Path(path).read_text(encoding="utf-8"))["cases"][0]["fixture_only"] for path in fixtures["fixture_paths"])

    artifact_names = {spec[0] for spec in ARTIFACT_SPECS}
    assert "full_open_source_autonomous_orchestrator_summary" in artifact_names
    assert "autonomous_admissibility_kernel_summary" in artifact_names
    assert "full_open_source_autonomous_orchestrator_summary" in EVIDENCE_PATHS

    reporting = _empty_reporting_evidence({"autonomy_status": "max_completion_no_machine_admissible_open_data"})
    report_summary = _open_source_autonomous_options_trader_summary(reporting)
    assert report_summary["autonomy_status"] == "max_completion_no_machine_admissible_open_data"

    export_ids = {rule.artifact_id for rule in export_selection_rules()}
    assert "full_open_source_autonomous_orchestrator_summary" in export_ids
    assert "autonomous_admissibility_kernel_summary" in export_ids
    assert "open_source_autonomy" in FINDING_CATEGORIES
    plan = write_test_shard_plan(["tests/test_open_source_autonomous_options_trader_max_completion.py"], [], {"collection": {"status": "pass", "stdout_tail": ""}, "full_suite": {"status": "inconclusive_timeout"}})
    assert plan["open_source_autonomous_options_trader_tests"] == ["tests/test_open_source_autonomous_options_trader_max_completion.py"]
    timeout = timeout_result(["python", "-m", "pytest"], 1)
    assert timeout["status"] == "inconclusive_timeout"
    assert timeout["timeout_recorded_as_pass"] is False


def test_no_forbidden_terms_in_new_artifacts_or_commands() -> None:
    run_full_open_source_autonomous_orchestrator()
    command_text = full_autonomy_module.COMMANDS_PATH.read_text(encoding="utf-8")
    forbidden = ["Alpha Vantage", ".env", "broker order", "Robinhood MCP"]
    for term in forbidden:
        assert term not in command_text
    summary = json.loads(full_autonomy_module.SUMMARY_PATH.read_text(encoding="utf-8"))
    assert summary["credentials_created"] is False
    assert summary["env_created"] is False
    assert summary["broker_connection_used"] is False
    assert summary["live_promotion_status"] is False


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _empty_reporting_evidence(full_summary: dict) -> ReportingEvidence:
    values = {field_name: {} for field_name in ReportingEvidence.__dataclass_fields__}
    values["full_open_source_autonomous_orchestrator_summary"] = full_summary
    return ReportingEvidence(**values)

