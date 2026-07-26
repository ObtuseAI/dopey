from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_inventory import build_inventory
from dopey_backtest.backtest_models import BacktestSignalInput, stable_backtest_hash
from dopey_backtest.honest_backtester import (
    BACKTEST_ENTRY_DECISIONS_PATH,
    BACKTEST_EXIT_CASES_PATH,
    BACKTEST_EXIT_DECISIONS_PATH,
    BACKTEST_EXPECTED_MATH_CASES_PATH,
    BACKTEST_LEDGER_PATH,
    BACKTEST_MARK_RECORDS_PATH,
    BACKTEST_POLICY_CASES_PATH,
    BACKTEST_POSITION_STATES_PATH,
    BACKTEST_PROOF_PATH,
    BACKTEST_QUALITY_FLAGS_PATH,
    BACKTEST_REPORT_PATH,
    BACKTEST_RUN_SUMMARY_PATH,
    BACKTEST_SIGNAL_INPUTS_PATH,
    BACKTEST_TRADE_INTENTS_PATH,
    BACKTEST_TRADE_RECORDS_PATH,
    run_honest_backtester,
)
from dopey_backtest.model_priced_trade_simulator import default_exit_config, simulate_intent_with_marks
from dopey_backtest.signal_trade_mapper import map_signal_records_to_trade_intents, policy_violation_reason_codes
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _honest_backtester_summary
from dopey_validation.full_suite_stabilizer import CommandResult, timeout_result, write_test_shard_plan


@pytest.fixture(scope="module")
def backtest_result() -> dict:
    return run_honest_backtester()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _directional_record(direction: str, candidate_strategy: str, option_structure: str) -> dict:
    return {
        "artifact_type": "directional_setup_signal",
        "signal_id": f"{candidate_strategy}-{direction}-signal",
        "symbol": "SPY_MODEL",
        "signal_date": "2026-07-01",
        "signal_family": "directional_setup",
        "source_signal_family": "momentum",
        "direction": direction,
        "candidate_strategy": candidate_strategy,
        "option_structure": option_structure,
        "normalized_score": 0.75 if direction == "bullish" else -0.75 if direction == "bearish" else 0.0,
        "confidence_proxy": 0.75,
        "data_source_tier": "fixture_only",
        "real_history_used": False,
        "fixture_only": True,
        "not_real_signal_evidence": True,
        "paper_only": True,
        "live_blocked": True,
        "reason_codes": ["test_directional_setup"],
        "spread_created": False,
        "short_vol_created": False,
        "naked_selling_created": False,
        "same_day_churn_allowed": False,
        "real_sizing_used": False,
        "broker_required": False,
    }


def _mapped_intent(direction: str, candidate_strategy: str, option_structure: str) -> dict:
    mapped = map_signal_records_to_trade_intents([_directional_record(direction, candidate_strategy, option_structure)])
    assert len(mapped["trade_intents"]) == 1
    return mapped["trade_intents"][0]


def test_model_serialization_and_hash_determinism() -> None:
    record = BacktestSignalInput(
        artifact_type="backtest_signal_input",
        signal_id="sig-1",
        symbol="spy",
        signal_family="momentum",
        signal_date="2026-07-01",
        direction="bullish",
        candidate_strategy="long_call",
        option_structure="long_call",
        normalized_score=0.25,
        confidence_proxy=0.5,
        data_source_tier="fixture_only",
        real_history_used=False,
        fixture_only=True,
        not_real_signal_evidence=True,
        not_real_backtest_evidence=True,
        paper_only=True,
        live_blocked=True,
        reason_codes=["b", "a"],
        input_hash="",
    )
    first = record.to_dict()
    second = record.to_dict()
    assert first == second
    assert first["input_hash"] == stable_backtest_hash(first)
    assert first["paper_only"] is True
    assert first["live_blocked"] is True
    assert first["not_real_backtest_evidence"] is True


def test_signal_to_trade_mapper_creates_long_call_intent_for_bullish_setup() -> None:
    intent = _mapped_intent("bullish", "long_call", "long_call")
    assert intent["candidate_strategy"] == "long_call"
    assert intent["option_structure"] == "long_call"
    assert intent["model_priced"] is True
    assert intent["quote_priced"] is False


def test_signal_to_trade_mapper_creates_long_put_intent_for_bearish_setup() -> None:
    intent = _mapped_intent("bearish", "long_put", "long_put")
    assert intent["candidate_strategy"] == "long_put"
    assert intent["option_structure"] == "long_put"
    assert intent["model_priced"] is True
    assert intent["quote_priced"] is False


def test_signal_to_trade_mapper_creates_no_trade_record_for_neutral_setup() -> None:
    intent = _mapped_intent("neutral", "no_trade", "none")
    assert intent["candidate_strategy"] == "no_trade"
    assert intent["option_structure"] == "none"
    assert intent["pricing_source_tier"] == "fixture_only"


def test_spread_short_vol_and_naked_selling_rejected() -> None:
    spread = _directional_record("bullish", "long_call", "vertical_spread")
    short_vol = _directional_record("bullish", "long_call", "long_call")
    short_vol["short_vol_created"] = True
    naked = _directional_record("bearish", "long_put", "long_put")
    naked["naked_selling_created"] = True
    mapped = map_signal_records_to_trade_intents([spread, short_vol, naked])
    assert mapped["trade_intents"] == []
    assert len(mapped["quality_flags"]) == 3
    assert all(flag["reason_code"] == "blocked_policy_violation" for flag in mapped["quality_flags"])


def test_same_day_churn_rejected() -> None:
    record = _directional_record("bullish", "long_call", "long_call")
    record["same_day_churn_allowed"] = True
    reasons = policy_violation_reason_codes(record)
    assert "disallowed_same_day_churn_allowed" in reasons
    mapped = map_signal_records_to_trade_intents([record])
    assert mapped["trade_intents"] == []
    assert mapped["quality_flags"][0]["reason_code"] == "blocked_policy_violation"


def test_model_priced_trade_simulation_produces_deterministic_marks() -> None:
    intent = _mapped_intent("bullish", "long_call", "long_call")
    dates = ["2026-07-01", "2026-07-02", "2026-07-03"]
    first = simulate_intent_with_marks(intent, [2.0, 2.5, 2.75], dates, "unit_path", "missing_real_dataset", default_exit_config())
    second = simulate_intent_with_marks(intent, [2.0, 2.5, 2.75], dates, "unit_path", "missing_real_dataset", default_exit_config())
    assert first["trade_records"] == second["trade_records"]
    assert len(first["mark_records"]) == 3
    assert first["trade_records"][0]["path_pnl"] == 0.75


def test_premium_stop_exits() -> None:
    intent = _mapped_intent("bullish", "long_call", "long_call")
    result = simulate_intent_with_marks(intent, [2.0, 0.9, 0.8], ["2026-07-01", "2026-07-02", "2026-07-03"], "stop_path", "missing_real_dataset", default_exit_config())
    trade = result["trade_records"][0]
    assert trade["exit_reason"] == "premium_stop"
    assert trade["path_pnl"] == -1.1


def test_premium_target_exits() -> None:
    intent = _mapped_intent("bearish", "long_put", "long_put")
    result = simulate_intent_with_marks(intent, [2.0, 4.1, 4.2], ["2026-07-01", "2026-07-02", "2026-07-03"], "target_path", "missing_real_dataset", default_exit_config())
    trade = result["trade_records"][0]
    assert trade["exit_reason"] == "premium_target"
    assert trade["path_pnl"] == 2.1


def test_time_stop_exits() -> None:
    intent = _mapped_intent("bullish", "long_call", "long_call")
    result = simulate_intent_with_marks(
        intent,
        [2.0, 2.1, 2.2, 2.25],
        ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"],
        "time_path",
        "missing_real_dataset",
        default_exit_config(),
    )
    trade = result["trade_records"][0]
    assert trade["exit_reason"] == "time_stop"
    assert trade["holding_steps"] == 3


def test_pnl_in_abstract_premium_units_only() -> None:
    intent = _mapped_intent("bullish", "long_call", "long_call")
    result = simulate_intent_with_marks(intent, [3.0, 3.6], ["2026-07-01", "2026-07-02"], "premium_path", "missing_real_dataset", default_exit_config())
    trade = result["trade_records"][0]
    assert trade["entry_premium"] == 3.0
    assert trade["exit_premium"] == 3.6
    assert trade["path_pnl"] == 0.6
    assert trade["trade_return_model_units"] == 0.2
    assert "premium_units_only" in trade["reason_codes"]


def test_no_account_balance_buying_power_or_real_sizing_in_artifacts(backtest_result: dict) -> None:
    for path in [BACKTEST_TRADE_INTENTS_PATH, BACKTEST_TRADE_RECORDS_PATH, BACKTEST_RUN_SUMMARY_PATH]:
        text = path.read_text(encoding="utf-8").lower()
        assert "account_balance" not in text
        assert "buying_power" not in text
        assert "real_capital" not in text
    summary = _json(BACKTEST_RUN_SUMMARY_PATH)
    assert summary["paper_only"] is True
    assert summary["live_blocked"] is True


def test_missing_real_history_recorded_honestly(backtest_result: dict) -> None:
    summary = _json(BACKTEST_RUN_SUMMARY_PATH)
    if summary["history_dataset_status"] == "valid_real_dataset":
        assert summary["backtest_status"] in {
            "valid_real_history_backtest_ready",
            "valid_real_history_model_priced_backtest_complete",
        }
    else:
        assert summary["backtest_status"] == "missing_real_history_fixture_validation_only"
        assert summary["real_history_used"] is False
        assert "missing_real_history" in summary["quality_flags"]


def test_missing_real_option_chain_recorded_honestly(backtest_result: dict) -> None:
    summary = _json(BACKTEST_RUN_SUMMARY_PATH)
    assert summary["quote_priced_trade_count"] == 0
    assert "missing_real_option_chain" in summary["quality_flags"]
    records = _jsonl(BACKTEST_TRADE_RECORDS_PATH)
    assert all(record["real_option_chain_used"] is False for record in records)


def test_no_quote_priced_claim_without_quote_data(backtest_result: dict) -> None:
    summary = _json(BACKTEST_RUN_SUMMARY_PATH)
    assert summary["pricing_source_tier_distribution"]["quote_priced"] == 0
    records = _jsonl(BACKTEST_TRADE_RECORDS_PATH)
    assert all(record["quote_priced"] is False for record in records)
    assert all(record["pricing_source_tier"] == "model_priced" for record in records)


def test_no_real_backtest_evidence_profitability_or_live_readiness_claim(backtest_result: dict) -> None:
    summary = _json(BACKTEST_RUN_SUMMARY_PATH)
    assert summary["not_real_backtest_evidence"] is True
    assert summary["not_profitability_claim"] is True
    assert summary["not_live_ready"] is True
    assert "not_real_backtest_evidence" in summary["quality_flags"]
    assert "not_profitability_claim" in summary["quality_flags"]
    assert "not_live_ready" in summary["quality_flags"]


def test_artifacts_written(backtest_result: dict) -> None:
    for path in [
        BACKTEST_SIGNAL_INPUTS_PATH,
        BACKTEST_TRADE_INTENTS_PATH,
        BACKTEST_ENTRY_DECISIONS_PATH,
        BACKTEST_EXIT_DECISIONS_PATH,
        BACKTEST_POSITION_STATES_PATH,
        BACKTEST_MARK_RECORDS_PATH,
        BACKTEST_TRADE_RECORDS_PATH,
        BACKTEST_QUALITY_FLAGS_PATH,
        BACKTEST_RUN_SUMMARY_PATH,
        BACKTEST_PROOF_PATH,
        BACKTEST_EXPECTED_MATH_CASES_PATH,
        BACKTEST_POLICY_CASES_PATH,
        BACKTEST_EXIT_CASES_PATH,
        BACKTEST_REPORT_PATH,
        BACKTEST_LEDGER_PATH,
    ]:
        assert path.exists()
    assert _json(BACKTEST_EXPECTED_MATH_CASES_PATH)["case_count"] == 24
    assert _json(BACKTEST_POLICY_CASES_PATH)["case_count"] == 28
    assert _json(BACKTEST_EXIT_CASES_PATH)["case_count"] == 15


def test_audit_recognizes_backtest_artifacts(backtest_result: dict) -> None:
    names = {spec[0] for spec in ARTIFACT_SPECS}
    required = {
        "backtest_signal_inputs",
        "backtest_trade_intents",
        "backtest_entry_decisions",
        "backtest_exit_decisions",
        "backtest_position_states",
        "backtest_mark_records",
        "backtest_trade_records",
        "backtest_quality_flags",
        "backtest_run_summary",
        "backtest_proof",
    }
    assert required.issubset(names)
    inventory = build_inventory()
    status_by_type = {artifact.artifact_type: artifact.status for artifact in inventory.artifacts}
    assert status_by_type["backtest_run_summary"] == "present"


def test_reporting_includes_backtest_summary(backtest_result: dict) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    summary = _honest_backtester_summary(evidence)
    if summary.get("history_dataset_status") == "valid_real_dataset":
        assert summary["backtest_status"] in {
            "valid_real_history_backtest_ready",
            "valid_real_history_model_priced_backtest_complete",
        }
        assert summary["trade_intent_count"] > 0
    else:
        assert summary["backtest_status"] == "missing_real_history_fixture_validation_only"
        assert summary["trade_intent_count"] == 80
    assert summary["quote_priced_trade_count"] == 0
    assert summary["not_real_backtest_evidence"] is True


def test_export_includes_backtest_artifacts() -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {
        "backtest_signal_inputs",
        "backtest_trade_intents",
        "backtest_entry_decisions",
        "backtest_exit_decisions",
        "backtest_position_states",
        "backtest_mark_records",
        "backtest_trade_records",
        "backtest_quality_flags",
        "backtest_run_summary",
        "backtest_proof",
    }.issubset(ids)


def test_export_review_includes_backtest_summary(backtest_result: dict) -> None:
    ctx = SimpleNamespace(
        shared_export_path="",
        reporting_summary={"honest_backtester_summary": _json(BACKTEST_RUN_SUMMARY_PATH)},
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
    decision = SimpleNamespace(decision="review_ready", suitability="offline_review", next_build_target="DOPEY_STATISTICAL_TRUTH_LAYER_V1")
    rendered = render_executive_summary(ctx, bundle, [], decision)
    assert "Honest Backtester" in rendered
    assert "fixture/model validation only" in rendered
    assert "not_real_backtest_evidence: `true`" in rendered
    assert "not_profitability_claim: `true`" in rendered
    assert "not_live_ready: `true`" in rendered


def test_validation_stabilizer_includes_backtest_shard() -> None:
    summary = {
        "collection": {"status": "pass", "stdout_tail": ""},
        "full_suite": {"status": "inconclusive_timeout"},
    }
    plan = write_test_shard_plan(
        ["tests/test_honest_backtester.py"],
        [CommandResult(["python", "-m", "pytest", "tests/test_honest_backtester.py", "-q"], "pass", 0, 0.1, False, False, "", "")],
        summary,
    )
    assert "tests/test_honest_backtester.py" in plan["split_suite_lanes"]["honest_backtester_tests"]
    assert "tests/test_honest_backtester.py" in plan["artifact_writing_tests_sequential"]


def test_full_pytest_timeout_remains_inconclusive_not_pass() -> None:
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout"
    assert result["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled() -> None:
    intent = ExecutionIntent(
        intent_id="honest-backtester-live-disabled",
        symbol="SPY",
        structure="single",
        legs=[{"side": "buy", "symbol": "SPY_CALL", "option_type": "call", "expiry": "2026-08-21"}],
        live_allowed=True,
        paper=False,
    )
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(intent)


def test_no_broker_connection_credentials_scheduler_real_sizing_or_robinhood_mcp(backtest_result: dict) -> None:
    source_text = "\n".join(path.read_text(encoding="utf-8").lower() for path in [
        Path("dopey_backtest/backtest_models.py"),
        Path("dopey_backtest/signal_trade_mapper.py"),
        Path("dopey_backtest/model_priced_trade_simulator.py"),
        Path("dopey_backtest/honest_backtester.py"),
        Path("dopey_backtest/run_honest_backtester.py"),
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
    summary = _json(BACKTEST_RUN_SUMMARY_PATH)
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

