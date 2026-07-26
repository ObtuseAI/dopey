from __future__ import annotations

from pathlib import Path

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_autonomy.remaining_gap_eliminator import run_remaining_gap_eliminator
from dopey_autonomy.run_finish_literally_everything_orchestrator import run_finish_literally_everything_orchestrator, write_finish_everything_fixture_cases
from dopey_autonomy.autonomy_common import read_json, write_jsonl
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_models import FINDING_CATEGORIES
from dopey_openbb_autonomy.openbb_no_key_source_probe import RESULTS_PATH as PROBE_RESULTS_PATH
from dopey_openbb_autonomy.openbb_no_key_source_probe import build_probe_result, run_openbb_no_key_source_probe
from dopey_openbb_autonomy.openbb_ohlcv_normalization_bridge import run_openbb_ohlcv_normalization_bridge
from dopey_openbb_autonomy.openbb_provider_registry import PROVIDER_REGISTRY_PATH, run_openbb_provider_registry
from dopey_openbb_autonomy.openbb_runtime_detector import detect_openbb_runtime
from dopey_openbb_autonomy.openbb_validator_bridge import run_openbb_validator_bridge
from dopey_paper_autonomy.autonomous_paper_rotation_engine import run_autonomous_paper_rotation_engine
from dopey_research_autonomy.model_priced_options_research_expansion_v2 import run_model_priced_options_research_expansion_v2
from dopey_research_autonomy.s_tier_long_premium_engine_v2 import run_s_tier_long_premium_engine_v2
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence


def test_openbb_absent_or_present_runtime_detector_is_adapter_ready() -> None:
    runtime = detect_openbb_runtime()

    assert runtime["openbb_runtime_status"] in {"not_installed_adapter_ready", "installed_read_only_adapter_ready", "installed_version_unknown_adapter_ready"}
    assert runtime["global_install_attempted"] is False
    assert runtime["credentials_created"] is False
    assert runtime["env_created"] is False
    assert runtime["broker_connection_used"] is False
    assert runtime["network_fetch_performed"] is False


def test_openbb_provider_registry_rejects_forbidden_and_credentialed_providers() -> None:
    registry = run_openbb_provider_registry()
    providers = {record["provider_name"]: record for record in _read_jsonl(PROVIDER_REGISTRY_PATH)}

    assert registry["provider_count"] >= 10
    assert providers["fmp"]["provider_decision"] == "rejected_requires_api_key"
    assert providers["polygon"]["provider_decision"] == "rejected_requires_api_key"
    assert providers["broker_adapter"]["provider_decision"] == "rejected_broker_adjacent"
    assert providers["alpha_vantage"]["provider_decision"] == "rejected_alpha_vantage"
    assert providers["alpaca"]["provider_decision"] == "rejected_alpaca"
    assert providers["databento"]["provider_decision"] == "rejected_databento"
    assert providers["tradingview"]["provider_decision"] == "rejected_tradingview"


def test_openbb_no_key_probe_never_creates_credentials_or_broker_paths() -> None:
    probe = run_openbb_no_key_source_probe()

    assert probe["probe_status"] in {"openbb_not_available", "no_machine_admissible_openbb_provider"}
    assert probe["credentials_created"] is False
    assert probe["env_created"] is False
    assert probe["broker_connection_used"] is False
    assert probe["network_fetch_performed"] is False


def test_openbb_fixture_ohlcv_normalizes_and_validator_bridge_passes(tmp_path: Path) -> None:
    fixture = tmp_path / "openbb_fixture_ohlcv.csv"
    fixture.write_text(
        "date,symbol,open,high,low,close,adjusted_close,volume\n"
        "2024-01-02,SPY,470,475,468,474,474,1000000\n",
        encoding="utf-8",
    )
    provider = {
        "provider_id": "openbb-provider-fixture",
        "provider_name": "fixture_openbb",
        "dataset_family": "equities OHLCV",
        "openbb_endpoint": "openbb.equity.price.historical",
    }
    write_jsonl(PROBE_RESULTS_PATH, [build_probe_result(provider, fixture)])

    normalized = run_openbb_ohlcv_normalization_bridge()
    bridge = run_openbb_validator_bridge()

    assert normalized["openbb_accepted_ohlcv_file_count"] == 1
    assert normalized["openbb_ohlcv_status"] == "openbb_ohlcv_normalized"
    assert bridge["openbb_valid_real_dataset"] is True
    assert bridge["openbb_history_activation_status"] == "openbb_history_activation_pass"


def test_model_priced_v2_outputs_are_model_priced_not_quote_evidence() -> None:
    summary = run_model_priced_options_research_expansion_v2()
    scenarios = _read_jsonl(Path(summary["artifact_paths"]["model_priced_v2_scenario_grid"]))

    assert summary["model_priced_v2_status"] == "model_priced_v2_research_complete"
    assert summary["pricing_tier"] == "model_priced"
    assert summary["quote_priced"] is False
    assert summary["not_quote_evidence"] is True
    assert summary["not_real_options_evidence"] is True
    assert scenarios


def test_s_tier_v2_does_not_claim_superiority_profitability_or_live_readiness() -> None:
    summary = run_s_tier_long_premium_engine_v2()

    assert summary["s_tier_v2_status"] == "s_tier_v2_engineering_target_complete"
    assert summary["s_tier_engineering_target"] is True
    assert summary["s_tier_live_superiority_claim"] is False
    assert summary["better_than_anyone_claim"] is False
    assert summary["profitability_claim"] is False
    assert summary["live_readiness_claim"] is False


def test_paper_rotation_blocks_without_data_and_runs_with_fixture_data(tmp_path: Path) -> None:
    write_jsonl(PROBE_RESULTS_PATH, [])
    run_openbb_ohlcv_normalization_bridge()
    blocked = run_autonomous_paper_rotation_engine()
    assert blocked["paper_rotation_status"] == "blocked_no_accepted_real_data"

    fixture = tmp_path / "openbb_fixture_ohlcv.csv"
    fixture.write_text(
        "date,symbol,open,high,low,close,adjusted_close,volume\n"
        "2024-01-03,QQQ,400,405,399,404,404,900000\n",
        encoding="utf-8",
    )
    provider = {
        "provider_id": "openbb-provider-fixture",
        "provider_name": "fixture_openbb",
        "dataset_family": "equities OHLCV",
        "openbb_endpoint": "openbb.equity.price.historical",
    }
    write_jsonl(PROBE_RESULTS_PATH, [build_probe_result(provider, fixture)])
    run_openbb_ohlcv_normalization_bridge()
    running = run_autonomous_paper_rotation_engine()
    assert running["paper_rotation_status"] == "paper_rotation_simulated_model_priced"
    assert running["broker_connection_used"] is False
    assert running["live_trading_enabled"] is False


def test_remaining_gap_eliminator_has_zero_manual_and_operator_dependencies() -> None:
    summary = run_remaining_gap_eliminator()
    gaps = _read_jsonl(Path(summary["artifact_paths"]["remaining_gap_registry"]))

    assert summary["manual_review_dependency_count"] == 0
    assert summary["operator_action_required_count"] == 0
    assert all(gap["manual_review_required"] is False for gap in gaps)
    assert all(gap["operator_action_required"] is False for gap in gaps)


def test_finish_orchestrator_completes_no_data_state_and_writes_fixtures() -> None:
    write_jsonl(PROBE_RESULTS_PATH, [])
    summary = run_finish_literally_everything_orchestrator()
    fixtures = write_finish_everything_fixture_cases()

    assert summary["finish_everything_status"] == "max_completion_model_priced_research_and_paper_engine_ready_blocked_no_accepted_data"
    assert summary["manual_review_dependency_count"] == 0
    assert summary["operator_action_required_count"] == 0
    assert summary["credentials_created"] is False
    assert summary["env_created"] is False
    assert summary["broker_connection_used"] is False
    assert summary["live_trading_enabled"] is False
    assert summary["strategy_promotion_allowed"] is False
    assert fixtures["fixture_case_count"] >= 500


def test_finish_everything_integration_surfaces_exist() -> None:
    artifact_types = {spec[0] for spec in ARTIFACT_SPECS}
    export_ids = {rule.artifact_id for rule in export_selection_rules()}
    evidence = load_reporting_evidence(EVIDENCE_PATHS)

    assert "finish_everything_orchestrator_summary" in artifact_types
    assert "openbb_provider_registry_summary" in artifact_types
    assert "finish_everything_orchestrator_summary" in export_ids
    assert "finish_everything_openbb" in FINDING_CATEGORIES
    assert "finish_everything_orchestrator_summary" in EVIDENCE_PATHS
    assert hasattr(evidence, "finish_everything_orchestrator_summary")
    assert Path("dopey_validation/full_suite_stabilizer.py").read_text(encoding="utf-8").find("test_finish_everything_openbb_model_priced_s_tier_completion.py") >= 0


def test_no_forbidden_runtime_markers_in_finish_summary() -> None:
    summary = read_json(Path("artifacts/dopey/finish_everything/finish_everything_orchestrator_summary.json"))

    assert summary.get("alpha_vantage_excluded", True) is True
    assert summary.get("alpaca_excluded", True) is True
    assert summary.get("databento_excluded", True) is True
    assert summary.get("tradingview_excluded", True) is True
    assert summary.get("credentials_created", False) is False
    assert summary.get("env_created", False) is False
    assert summary.get("broker_connection_used", False) is False
    assert summary.get("strategy_promotion_allowed", False) is False
    assert summary.get("profitability_claim", False) is False
    assert summary.get("live_readiness_claim", False) is False


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [__import__("json").loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
