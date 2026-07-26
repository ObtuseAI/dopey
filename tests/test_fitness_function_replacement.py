from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_inventory import build_inventory
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_fitness.fitness_models import FitnessInput, stable_fitness_hash
from dopey_fitness.promotion_gate import evaluate_fitness_promotion_gate
from dopey_fitness.proxy_fitness_quarantine import classify_proxy_reference
from dopey_fitness.truth_gated_fitness_engine import (
    BACKTEST_METRIC_SET_PATH,
    FITNESS_DECISION_PATH,
    FITNESS_INPUT_PATH,
    FITNESS_LEDGER_PATH,
    FITNESS_METRIC_COMPONENT_CASES_PATH,
    FITNESS_METRIC_COMPONENTS_PATH,
    FITNESS_PENALTIES_PATH,
    FITNESS_PENALTY_CASES_PATH,
    FITNESS_PROMOTION_GATE_CASES_PATH,
    FITNESS_PROMOTION_GATE_PATH,
    FITNESS_QUALITY_FLAGS_PATH,
    FITNESS_RANK_RECORDS_PATH,
    FITNESS_REPLACEMENT_PROOF_PATH,
    FITNESS_REPLACEMENT_SUMMARY_PATH,
    FITNESS_REPORT_PATH,
    FITNESS_SCORECARDS_PATH,
    PROXY_FITNESS_QUARANTINE_CASES_PATH,
    PROXY_FITNESS_QUARANTINE_FINDINGS_PATH,
    STATISTICAL_TRUTH_DECISION_PATH,
    STATISTICAL_TRUTH_SUMMARY_PATH,
    build_fitness_input,
    compute_metric_components,
    compute_penalties,
    run_fitness_function_replacement,
)
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _fitness_replacement_summary
from dopey_validation.full_suite_stabilizer import CommandResult, timeout_result, write_test_shard_plan


@pytest.fixture(scope="module")
def fitness_result() -> dict:
    return run_fitness_function_replacement()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_model_serialization_and_hash_determinism() -> None:
    record = FitnessInput(
        artifact_type="fitness_input",
        fitness_version="",
        truth_summary_path="summary",
        truth_decision_path="decision",
        metric_set_path="metric",
        bootstrap_ci_path="bootstrap",
        baseline_comparisons_path="baseline",
        backtest_trade_records_path="trades",
        backtest_summary_path="backtest",
        truth_status="fixture_model_statistics_only",
        truth_decision="hold_fixture_validation_only",
        statistical_promotion_allowed=False,
        real_sample_size=0,
        fixture_model_sample_size=55,
        sample_count=55,
        quote_priced_trade_count=0,
        real_history_used=False,
        real_option_chain_used=False,
        not_real_statistical_evidence=True,
        not_real_backtest_evidence=True,
        not_real_fitness_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        paper_only=True,
        live_blocked=True,
        input_hash="",
    )
    first = record.to_dict()
    second = record.to_dict()
    assert first == second
    assert first["input_hash"] == stable_fitness_hash(first)
    assert first["paper_only"] is True
    assert first["live_blocked"] is True
    assert first["not_real_fitness_evidence"] is True


def test_fitness_input_loads_statistical_truth_summary(fitness_result: dict) -> None:
    truth_summary = _json(STATISTICAL_TRUTH_SUMMARY_PATH)
    truth_decision = _json(STATISTICAL_TRUTH_DECISION_PATH)
    fitness_input = _json(FITNESS_INPUT_PATH)
    assert fitness_input["truth_status"] == truth_summary["truth_status"]
    assert fitness_input["truth_decision"] == truth_decision["truth_decision"]
    assert fitness_input["statistical_promotion_allowed"] is False


def test_diagnostic_score_computes_deterministically(fitness_result: dict) -> None:
    first = _json(FITNESS_REPLACEMENT_SUMMARY_PATH)
    second_result = run_fitness_function_replacement()
    second = _json(FITNESS_REPLACEMENT_SUMMARY_PATH)
    assert first["diagnostic_score"] == second["diagnostic_score"] == second_result["diagnostic_score"]
    assert first["promotion_allowed"] is False


def test_win_rate_component(fitness_result: dict) -> None:
    components = {record["component_name"]: record for record in _jsonl(FITNESS_METRIC_COMPONENTS_PATH)}
    assert components["win_rate_component"]["raw_value"] == 0.581818
    assert components["win_rate_component"]["weighted_score"] > 0.0


def test_expectancy_component(fitness_result: dict) -> None:
    components = {record["component_name"]: record for record in _jsonl(FITNESS_METRIC_COMPONENTS_PATH)}
    assert components["expectancy_component"]["raw_value"] == 0.646175
    assert components["expectancy_component"]["normalized_value"] > 0.5


def test_drawdown_control_component(fitness_result: dict) -> None:
    components = {record["component_name"]: record for record in _jsonl(FITNESS_METRIC_COMPONENTS_PATH)}
    assert components["drawdown_control_component"]["raw_value"] == -4.472074
    assert 0.0 < components["drawdown_control_component"]["normalized_value"] <= 1.0


def test_payoff_ratio_component(fitness_result: dict) -> None:
    components = {record["component_name"]: record for record in _jsonl(FITNESS_METRIC_COMPONENTS_PATH)}
    assert components["payoff_ratio_component"]["raw_value"] == 1.173369
    assert components["payoff_ratio_component"]["weighted_score"] > 0.0


def test_bootstrap_ci_component(fitness_result: dict) -> None:
    components = {record["component_name"]: record for record in _jsonl(FITNESS_METRIC_COMPONENTS_PATH)}
    assert "bootstrap_ci_diagnostic_component" in components
    assert components["bootstrap_ci_diagnostic_component"]["source_metric"] == "mean_pnl_ci"


def test_baseline_diagnostic_component(fitness_result: dict) -> None:
    components = {record["component_name"]: record for record in _jsonl(FITNESS_METRIC_COMPONENTS_PATH)}
    assert "baseline_delta_diagnostic_component" in components
    assert components["baseline_delta_diagnostic_component"]["source_metric"] == "baseline_delta"


def test_fixture_only_penalty(fitness_result: dict) -> None:
    penalties = {record["penalty_name"]: record for record in _jsonl(FITNESS_PENALTIES_PATH)}
    assert penalties["fixture_only_penalty"]["applies"] is True
    assert penalties["fixture_only_penalty"]["penalty_value"] > 0


def test_missing_real_history_penalty(fitness_result: dict) -> None:
    penalties = {record["penalty_name"]: record for record in _jsonl(FITNESS_PENALTIES_PATH)}
    assert penalties["missing_real_history_penalty"]["applies"] is True


def test_missing_options_chain_penalty(fitness_result: dict) -> None:
    penalties = {record["penalty_name"]: record for record in _jsonl(FITNESS_PENALTIES_PATH)}
    assert penalties["missing_options_chain_penalty"]["applies"] is True


def test_insufficient_real_sample_penalty(fitness_result: dict) -> None:
    penalties = {record["penalty_name"]: record for record in _jsonl(FITNESS_PENALTIES_PATH)}
    assert penalties["insufficient_real_sample_penalty"]["applies"] is True


def test_truth_gate_block_penalty(fitness_result: dict) -> None:
    penalties = {record["penalty_name"]: record for record in _jsonl(FITNESS_PENALTIES_PATH)}
    assert penalties["truth_gate_block_penalty"]["applies"] is True


def test_promotion_gate_blocks_when_statistical_promotion_is_false() -> None:
    gate = evaluate_fitness_promotion_gate(
        {"promotion_allowed": False, "truth_status": "fixture_model_statistics_only", "not_real_statistical_evidence": True, "not_profitability_claim": True, "not_live_ready": True},
        {"promotion_allowed": False, "real_sample_size": 0, "quote_priced_trade_count": 0},
        {"real_history_used": False, "quote_priced_trade_count": 0, "not_real_backtest_evidence": True, "not_profitability_claim": True, "not_live_ready": True},
        {},
        {},
    )
    assert gate["promotion_allowed"] is False
    assert gate["promotion_gate_status"] == "truth_gate_blocked"
    assert "statistical_truth_promotion_false" in gate["blocked_reason_codes"]


def test_promotion_gate_blocks_when_real_history_is_missing() -> None:
    gate = _current_gate()
    assert "missing_real_history" in gate["blocked_reason_codes"]
    assert gate["real_history_used"] is False


def test_promotion_gate_blocks_when_quote_priced_count_is_zero() -> None:
    gate = _current_gate()
    assert gate["quote_priced_trade_count"] == 0
    assert "no_quote_priced_data" in gate["blocked_reason_codes"]


def test_promotion_gate_blocks_not_real_statistical_evidence() -> None:
    gate = _current_gate()
    assert "not_real_statistical_evidence" in gate["blocked_reason_codes"]


def test_promotion_gate_blocks_not_profitability_claim() -> None:
    gate = _current_gate()
    assert "not_profitability_claim" in gate["blocked_reason_codes"]


def test_promotion_gate_blocks_not_live_ready_claim() -> None:
    gate = _current_gate()
    assert "not_live_ready" in gate["blocked_reason_codes"]


def test_old_proxy_fitness_references_are_quarantined(fitness_result: dict) -> None:
    findings = _jsonl(PROXY_FITNESS_QUARANTINE_FINDINGS_PATH)
    assert findings
    assert any("fitness_score" in record["matched_tokens"] or "champion" in record["matched_tokens"] for record in findings)
    assert _json(FITNESS_REPLACEMENT_SUMMARY_PATH)["old_proxy_fitness_quarantined"] is True


def test_active_proxy_promotion_input_terminal_blocks() -> None:
    classification, reason_code, terminal_block, manual_review = classify_proxy_reference("dopey_strategy_lab/active.py", "strategy_promoted=true", ["strategy_promoted"])
    assert classification == "blocked_active_promotion_input"
    assert reason_code == "active_proxy_promotion_terminal_block"
    assert terminal_block is True
    assert manual_review is False


def test_allowed_historical_doc_references_do_not_terminal_block() -> None:
    classification, reason_code, terminal_block, manual_review = classify_proxy_reference("DOPEY_CANON.md", "fitness_score existed historically", ["fitness_score"])
    assert classification == "allowed_historical_doc"
    assert terminal_block is False
    assert manual_review is False
    assert reason_code == "historical_or_artifact_reference_not_promotion_input"


def test_fitness_decision_is_hold_no_promotion(fitness_result: dict) -> None:
    decision = _json(FITNESS_DECISION_PATH)
    assert decision["fitness_decision"] == "hold_no_promotion"
    assert decision["fitness_status"] == "fixture_model_diagnostic_only"


def test_promotion_allowed_and_strategy_promoted_are_false(fitness_result: dict) -> None:
    summary = _json(FITNESS_REPLACEMENT_SUMMARY_PATH)
    assert summary["promotion_allowed"] is False
    assert summary["strategy_promoted"] is False


def test_claim_statuses_are_false(fitness_result: dict) -> None:
    summary = _json(FITNESS_REPLACEMENT_SUMMARY_PATH)
    assert summary["significance_claim_allowed"] is False
    assert summary["real_alpha_claim_allowed"] is False
    assert summary["profitability_claim_allowed"] is False
    assert summary["live_readiness_claim_allowed"] is False


def test_artifacts_written(fitness_result: dict) -> None:
    for path in [
        FITNESS_INPUT_PATH,
        FITNESS_METRIC_COMPONENTS_PATH,
        FITNESS_PENALTIES_PATH,
        FITNESS_SCORECARDS_PATH,
        FITNESS_RANK_RECORDS_PATH,
        FITNESS_PROMOTION_GATE_PATH,
        FITNESS_DECISION_PATH,
        PROXY_FITNESS_QUARANTINE_FINDINGS_PATH,
        FITNESS_QUALITY_FLAGS_PATH,
        FITNESS_REPLACEMENT_SUMMARY_PATH,
        FITNESS_REPLACEMENT_PROOF_PATH,
        FITNESS_METRIC_COMPONENT_CASES_PATH,
        FITNESS_PENALTY_CASES_PATH,
        FITNESS_PROMOTION_GATE_CASES_PATH,
        PROXY_FITNESS_QUARANTINE_CASES_PATH,
        FITNESS_REPORT_PATH,
        FITNESS_LEDGER_PATH,
    ]:
        assert path.exists()
    case_total = sum(_json(path)["case_count"] for path in [FITNESS_METRIC_COMPONENT_CASES_PATH, FITNESS_PENALTY_CASES_PATH, FITNESS_PROMOTION_GATE_CASES_PATH, PROXY_FITNESS_QUARANTINE_CASES_PATH])
    assert case_total >= 80


def test_audit_recognizes_fitness_artifacts(fitness_result: dict) -> None:
    names = {spec[0] for spec in ARTIFACT_SPECS}
    assert {
        "fitness_input",
        "fitness_metric_components",
        "fitness_penalties",
        "fitness_scorecards",
        "fitness_rank_records",
        "fitness_promotion_gate",
        "fitness_decision",
        "proxy_fitness_quarantine_findings",
        "fitness_quality_flags",
        "fitness_replacement_summary",
        "fitness_replacement_proof",
    }.issubset(names)
    inventory = build_inventory()
    status_by_type = {artifact.artifact_type: artifact.status for artifact in inventory.artifacts}
    assert status_by_type["fitness_replacement_summary"] == "present"


def test_reporting_includes_fitness_summary(fitness_result: dict) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    summary = _fitness_replacement_summary(evidence)
    assert summary["fitness_status"] == "fixture_model_diagnostic_only"
    assert summary["fitness_decision"] == "hold_no_promotion"
    assert summary["promotion_allowed"] is False
    assert summary["old_proxy_fitness_quarantined"] is True


def test_export_includes_fitness_artifacts() -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {
        "fitness_input",
        "fitness_metric_components",
        "fitness_penalties",
        "fitness_scorecards",
        "fitness_rank_records",
        "fitness_promotion_gate",
        "fitness_decision",
        "proxy_fitness_quarantine_findings",
        "fitness_quality_flags",
        "fitness_replacement_summary",
        "fitness_replacement_proof",
    }.issubset(ids)


def test_export_review_includes_fitness_summary(fitness_result: dict) -> None:
    ctx = SimpleNamespace(
        shared_export_path="",
        reporting_summary={"fitness_replacement_summary": _json(FITNESS_REPLACEMENT_SUMMARY_PATH)},
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
    decision = SimpleNamespace(decision="review_ready", suitability="offline_review", next_build_target="DOPEY_REAL_DATA_INGESTION_PLAN_V1")
    rendered = render_executive_summary(ctx, bundle, [], decision)
    assert "Fitness Function Replacement" in rendered
    assert "old_proxy_fitness_quarantined: `true`" in rendered
    assert "promotion_allowed: `false`" in rendered


def test_validation_stabilizer_includes_fitness_shard() -> None:
    summary = {
        "collection": {"status": "pass", "stdout_tail": ""},
        "full_suite": {"status": "inconclusive_timeout"},
    }
    plan = write_test_shard_plan(
        ["tests/test_fitness_function_replacement.py"],
        [CommandResult(["python", "-m", "pytest", "tests/test_fitness_function_replacement.py", "-q"], "pass", 0, 0.1, False, False, "", "")],
        summary,
    )
    assert "tests/test_fitness_function_replacement.py" in plan["split_suite_lanes"]["fitness_function_replacement_tests"]
    assert "tests/test_fitness_function_replacement.py" in plan["artifact_writing_tests_sequential"]


def test_full_pytest_timeout_remains_inconclusive_not_pass() -> None:
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout"
    assert result["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled() -> None:
    intent = ExecutionIntent(
        intent_id="fitness-replacement-live-disabled",
        symbol="SPY",
        structure="single",
        legs=[{"side": "buy", "symbol": "SPY_CALL", "option_type": "call", "expiry": "2026-08-21"}],
        live_allowed=True,
        paper=False,
    )
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(intent)


def test_no_broker_connection_credentials_scheduler_real_sizing_or_robinhood_mcp(fitness_result: dict) -> None:
    source_text = "\n".join(path.read_text(encoding="utf-8").lower() for path in [
        Path("dopey_fitness/fitness_models.py"),
        Path("dopey_fitness/truth_gated_fitness_engine.py"),
        Path("dopey_fitness/promotion_gate.py"),
        Path("dopey_fitness/proxy_fitness_quarantine.py"),
        Path("dopey_fitness/run_fitness_function_replacement.py"),
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
    summary = _json(FITNESS_REPLACEMENT_SUMMARY_PATH)
    assert summary["live_blocked"] is True
    assert summary["paper_only"] is True


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


def _current_gate() -> dict:
    return _json(FITNESS_PROMOTION_GATE_PATH)

