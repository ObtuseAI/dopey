from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_inventory import build_inventory
from dopey_backtest.honest_backtester import (
    BACKTEST_ARTIFACT_DIR,
    HISTORY_SPINE_SUMMARY_PATH,
    run_honest_backtester,
)
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _statistical_truth_summary
from dopey_stats.bootstrap_truth_engine import bootstrap_confidence_intervals, default_bootstrap_truth_config
from dopey_stats.run_statistical_truth_layer import (
    BACKTEST_METRIC_SET_PATH,
    BASELINE_COMPARISONS_PATH,
    BOOTSTRAP_CONFIDENCE_INTERVALS_PATH,
    DEFLATED_SHARPE_RESULT_PATH,
    MULTIPLE_TESTING_ADJUSTMENT_PATH,
    STATS_BOOTSTRAP_CASES_PATH,
    STATS_GATE_CASES_PATH,
    STATS_LEDGER_PATH,
    STATS_METRIC_CASES_PATH,
    STATS_REPORT_PATH,
    STATISTICAL_TRUTH_DECISION_PATH,
    STATISTICAL_TRUTH_INPUT_PATH,
    STATISTICAL_TRUTH_PROOF_PATH,
    STATISTICAL_TRUTH_QUALITY_FLAGS_PATH,
    STATISTICAL_TRUTH_SUMMARY_PATH,
    BACKTEST_SAMPLE_PROFILE_PATH,
    run_statistical_truth_layer,
)
from dopey_stats.statistical_metric_calculator import calculate_metric_set
from dopey_stats.statistical_truth_gate import evaluate_statistical_truth_decision
from dopey_stats.statistical_truth_models import StatisticalTruthInput, stable_truth_hash
from dopey_validation.full_suite_stabilizer import CommandResult, timeout_result, write_test_shard_plan


@pytest.fixture(scope="module")
def stats_result() -> dict:
    if BACKTEST_ARTIFACT_DIR.exists():
        shutil.rmtree(BACKTEST_ARTIFACT_DIR)
    HISTORY_SPINE_SUMMARY_PATH.unlink(missing_ok=True)
    run_honest_backtester()
    return run_statistical_truth_layer()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_model_serialization_and_hash_determinism() -> None:
    record = StatisticalTruthInput(
        artifact_type="statistical_truth_input",
        statistical_truth_version="",
        backtest_summary_path="summary.json",
        backtest_trade_records_path="trades.jsonl",
        backtest_quality_flags_path="flags.jsonl",
        backtest_status="missing_real_history_fixture_validation_only",
        history_dataset_status="missing_real_dataset",
        real_history_used=False,
        real_option_chain_used=False,
        quote_priced_trade_count=0,
        not_real_backtest_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        paper_only=True,
        live_blocked=True,
        not_real_statistical_evidence=True,
        input_hash="",
    )
    first = record.to_dict()
    second = record.to_dict()
    assert first == second
    assert first["input_hash"] == stable_truth_hash(first)
    assert first["paper_only"] is True
    assert first["live_blocked"] is True
    assert first["not_real_statistical_evidence"] is True


def test_metric_calculator_mean_median_win_rate_drawdown(stats_result: dict) -> None:
    metrics = _json(BACKTEST_METRIC_SET_PATH)
    assert metrics["sample_count"] == 55
    assert metrics["win_count"] == 32
    assert metrics["loss_count"] == 23
    assert metrics["win_rate"] == 0.581818
    assert metrics["average_model_unit_pnl"] == 0.646175
    assert metrics["median_model_unit_pnl"] == 2.664876
    assert metrics["total_model_unit_pnl"] == 35.539623
    assert metrics["max_drawdown_model_units"] == -4.472074


def test_payoff_ratio_and_profit_factor_in_model_units_only(stats_result: dict) -> None:
    metrics = _json(BACKTEST_METRIC_SET_PATH)
    assert metrics["payoff_ratio_model_units"] == 1.173369
    assert metrics["profit_factor_model_units"] == 1.632513
    assert metrics["promotion_allowed"] is False
    assert metrics["not_real_statistical_evidence"] is True


def test_bootstrap_ci_determinism() -> None:
    pnl_values = [1.0, -0.5, 2.0, -1.0, 0.25] * 5
    config = default_bootstrap_truth_config()
    first = bootstrap_confidence_intervals(pnl_values, 0, config)
    second = bootstrap_confidence_intervals(pnl_values, 0, config)
    assert first == second
    assert first["seed"] == 8675309
    assert first["iterations"] == 1000
    assert first["insufficient_real_sample"] is True


def test_insufficient_sample_blocks_real_significance() -> None:
    result = bootstrap_confidence_intervals([1.0, -1.0], 0, default_bootstrap_truth_config())
    assert result["insufficient_sample"] is True
    assert result["significance_claim_allowed"] is False
    assert result["real_alpha_claim_allowed"] is False


def test_missing_real_history_and_options_chain_block_real_evidence(stats_result: dict) -> None:
    summary = _json(STATISTICAL_TRUTH_SUMMARY_PATH)
    decision = _json(STATISTICAL_TRUTH_DECISION_PATH)
    assert summary["real_sample_size"] == 0
    assert summary["not_real_statistical_evidence"] is True
    assert "missing_real_history_blocks_real_evidence" in decision["blocked_reason_codes"]
    assert "missing_real_options_chain_blocks_real_options_edge" in decision["blocked_reason_codes"]


def test_baseline_comparisons_are_diagnostic_only(stats_result: dict) -> None:
    comparisons = _jsonl(BASELINE_COMPARISONS_PATH)
    assert len(comparisons) == 6
    assert {record["baseline_name"] for record in comparisons} == {
        "zero_return_baseline",
        "random_direction_fixture_baseline",
        "always_long_call_model_baseline",
        "always_long_put_model_baseline",
        "no_trade_baseline",
        "shuffled_signal_baseline",
    }
    assert all(record["diagnostic_only"] is True for record in comparisons)
    assert all(record["real_evidence"] is False for record in comparisons)
    assert all(record["superiority_claim_allowed"] is False for record in comparisons)


def test_multiple_testing_guard_blocks_significance_claim_on_fixture_only_data(stats_result: dict) -> None:
    adjustment = _json(MULTIPLE_TESTING_ADJUSTMENT_PATH)
    assert adjustment["p_values_blocked"] is True
    assert adjustment["bonferroni_adjustment_applied"] is True
    assert adjustment["benjamini_hochberg_adjustment_applied"] is True
    assert adjustment["significance_claim_allowed"] is False
    assert adjustment["real_alpha_claim_allowed"] is False
    assert adjustment["promotion_allowed"] is False


def test_deflated_sharpe_is_diagnostic_only(stats_result: dict) -> None:
    result = _json(DEFLATED_SHARPE_RESULT_PATH)
    assert result["diagnostic_only"] is True
    assert result["p_value"] is None
    assert result["significance_claim_allowed"] is False
    assert result["real_alpha_claim_allowed"] is False


def test_truth_gate_returns_hold_fixture_validation_only(stats_result: dict) -> None:
    decision = _json(STATISTICAL_TRUTH_DECISION_PATH)
    assert decision["truth_status"] == "fixture_model_statistics_only"
    assert decision["truth_decision"] == "hold_fixture_validation_only"
    assert decision["promotion_allowed"] is False
    assert decision["terminal_block"] is False


def test_claim_permissions_all_false(stats_result: dict) -> None:
    summary = _json(STATISTICAL_TRUTH_SUMMARY_PATH)
    assert summary["promotion_allowed"] is False
    assert summary["significance_claim_allowed"] is False
    assert summary["real_alpha_claim_allowed"] is False
    assert summary["profitability_claim_allowed"] is False
    assert summary["live_readiness_claim_allowed"] is False


def test_terminal_block_on_safety_leak() -> None:
    backtest_summary = {
        "real_history_used": False,
        "quote_priced_trade_count": 0,
        "not_real_backtest_evidence": True,
        "not_profitability_claim": True,
    }
    sample_profile = {"real_sample_size": 0}
    metric_set = {"sample_count": 1}
    bootstrap = {"insufficient_real_sample": True}
    multiple = {"p_values_blocked": True}
    sharpe = {"diagnostic_only": True}
    decision = evaluate_statistical_truth_decision(
        backtest_summary,
        sample_profile,
        metric_set,
        bootstrap,
        multiple,
        sharpe,
        [],
        ["broker_connection"],
    )
    assert decision["truth_status"] == "terminal_block"
    assert decision["truth_decision"] == "terminal_block"
    assert decision["promotion_allowed"] is False


def test_artifacts_written(stats_result: dict) -> None:
    for path in [
        STATISTICAL_TRUTH_INPUT_PATH,
        BACKTEST_SAMPLE_PROFILE_PATH,
        BACKTEST_METRIC_SET_PATH,
        BOOTSTRAP_CONFIDENCE_INTERVALS_PATH,
        BASELINE_COMPARISONS_PATH,
        MULTIPLE_TESTING_ADJUSTMENT_PATH,
        DEFLATED_SHARPE_RESULT_PATH,
        STATISTICAL_TRUTH_DECISION_PATH,
        STATISTICAL_TRUTH_QUALITY_FLAGS_PATH,
        STATISTICAL_TRUTH_SUMMARY_PATH,
        STATISTICAL_TRUTH_PROOF_PATH,
        STATS_METRIC_CASES_PATH,
        STATS_BOOTSTRAP_CASES_PATH,
        STATS_GATE_CASES_PATH,
        STATS_REPORT_PATH,
        STATS_LEDGER_PATH,
    ]:
        assert path.exists()
    assert _json(STATS_METRIC_CASES_PATH)["case_count"] == 24
    assert _json(STATS_BOOTSTRAP_CASES_PATH)["case_count"] == 24
    assert _json(STATS_GATE_CASES_PATH)["case_count"] == 24


def test_audit_recognizes_stats_artifacts(stats_result: dict) -> None:
    names = {spec[0] for spec in ARTIFACT_SPECS}
    required = {
        "statistical_truth_input",
        "backtest_sample_profile",
        "backtest_metric_set",
        "bootstrap_confidence_intervals",
        "baseline_comparisons",
        "multiple_testing_adjustment",
        "deflated_sharpe_result",
        "statistical_truth_decision",
        "statistical_truth_quality_flags",
        "statistical_truth_summary",
        "statistical_truth_proof",
    }
    assert required.issubset(names)
    inventory = build_inventory()
    status_by_type = {artifact.artifact_type: artifact.status for artifact in inventory.artifacts}
    assert status_by_type["statistical_truth_summary"] == "present"


def test_reporting_includes_stats_summary(stats_result: dict) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    summary = _statistical_truth_summary(evidence)
    assert summary["truth_status"] == "fixture_model_statistics_only"
    assert summary["truth_decision"] == "hold_fixture_validation_only"
    assert summary["sample_count"] == 55
    assert summary["promotion_allowed"] is False


def test_export_includes_stats_artifacts() -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {
        "statistical_truth_input",
        "backtest_sample_profile",
        "backtest_metric_set",
        "bootstrap_confidence_intervals",
        "baseline_comparisons",
        "multiple_testing_adjustment",
        "deflated_sharpe_result",
        "statistical_truth_decision",
        "statistical_truth_quality_flags",
        "statistical_truth_summary",
        "statistical_truth_proof",
    }.issubset(ids)


def test_export_review_includes_stats_summary(stats_result: dict) -> None:
    ctx = SimpleNamespace(
        shared_export_path="",
        reporting_summary={"statistical_truth_summary": _json(STATISTICAL_TRUTH_SUMMARY_PATH)},
        audit_gap_plan={},
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
    decision = SimpleNamespace(decision="review_ready", suitability="offline_review", next_build_target="DOPEY_FITNESS_FUNCTION_REPLACEMENT_V1")
    rendered = render_executive_summary(ctx, bundle, [], decision)
    assert "Statistical Truth Layer" in rendered
    assert "fixture/model diagnostics only" in rendered
    assert "significance_claim_allowed: `false`" in rendered
    assert "real_alpha_claim_allowed: `false`" in rendered
    assert "promotion_allowed: `false`" in rendered


def test_validation_stabilizer_includes_stats_shard() -> None:
    summary = {
        "collection": {"status": "pass", "stdout_tail": ""},
        "full_suite": {"status": "inconclusive_timeout"},
    }
    plan = write_test_shard_plan(
        ["tests/test_statistical_truth_layer.py"],
        [CommandResult(["python", "-m", "pytest", "tests/test_statistical_truth_layer.py", "-q"], "pass", 0, 0.1, False, False, "", "")],
        summary,
    )
    assert "tests/test_statistical_truth_layer.py" in plan["split_suite_lanes"]["statistical_truth_layer_tests"]
    assert "tests/test_statistical_truth_layer.py" in plan["artifact_writing_tests_sequential"]


def test_full_pytest_timeout_remains_inconclusive_not_pass() -> None:
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout"
    assert result["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled() -> None:
    intent = ExecutionIntent(
        intent_id="stats-live-disabled",
        symbol="SPY",
        structure="single",
        legs=[{"side": "buy", "symbol": "SPY_CALL", "option_type": "call", "expiry": "2026-08-21"}],
        live_allowed=True,
        paper=False,
    )
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(intent)


def test_no_broker_connection_credentials_scheduler_real_sizing_or_robinhood_mcp(stats_result: dict) -> None:
    source_text = "\n".join(path.read_text(encoding="utf-8").lower() for path in [
        Path("dopey_stats/statistical_truth_models.py"),
        Path("dopey_stats/statistical_metric_calculator.py"),
        Path("dopey_stats/bootstrap_truth_engine.py"),
        Path("dopey_stats/baseline_comparison.py"),
        Path("dopey_stats/multiple_testing_guard.py"),
        Path("dopey_stats/deflated_sharpe.py"),
        Path("dopey_stats/statistical_truth_gate.py"),
        Path("dopey_stats/run_statistical_truth_layer.py"),
    ])
    assert "requests." not in source_text
    assert "websocket" not in source_text
    assert "place_order" not in source_text
    assert "cancel_order" not in source_text
    assert "review_order" not in source_text
    assert "sk-proj-" not in source_text
    assert "api_key" not in source_text
    assert ".env" not in source_text
    assert "cron" not in source_text
    assert "apscheduler" not in source_text
    assert "robinhood_mcp" not in source_text
    summary = _json(STATISTICAL_TRUTH_SUMMARY_PATH)
    assert summary["live_blocked"] is True
    assert summary["paper_only"] is True


def test_metric_calculator_on_small_manual_series() -> None:
    summary = {"real_history_used": False, "quote_priced_trade_count": 0}
    records = [{"path_pnl": 1.0}, {"path_pnl": -0.5}, {"path_pnl": 0.0}, {"path_pnl": 2.0}]
    metrics = calculate_metric_set(summary, records)
    assert metrics["sample_count"] == 4
    assert metrics["win_count"] == 2
    assert metrics["loss_count"] == 1
    assert metrics["flat_count"] == 1
    assert metrics["average_model_unit_pnl"] == 0.625
    assert metrics["median_model_unit_pnl"] == 0.5
    assert metrics["win_rate"] == 0.5


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        pytest.skip("Blunder SHA256 manifest not available")
    checked = 0
    bad = 0
    for line in manifest.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or "  " not in stripped:
            continue
        expected, raw_path = stripped.split("  ", 1)
        candidate = Path(raw_path.strip())
        if not candidate.exists():
            continue
        checked += 1
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual.lower() != expected.lower():
            bad += 1
    assert checked > 0, "no Blunder files were checked (manifest paths unresolved)"
    assert bad == 0, f"{bad} Blunder source file(s) changed since baseline"
