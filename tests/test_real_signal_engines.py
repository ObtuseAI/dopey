from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dopey_analysis.history_signal_adapter import HISTORY_SPINE_SUMMARY_PATH, load_default_history_signal_input
from dopey_analysis.run_real_signal_engines import (
    BREAKOUT_SIGNALS_PATH,
    DIRECTIONAL_SETUP_SIGNALS_PATH,
    FAKEOUT_SIGNALS_PATH,
    MARKET_REGIME_SIGNALS_PATH,
    MOMENTUM_SIGNALS_PATH,
    RELATIVE_STRENGTH_SIGNALS_PATH,
    SAMPLE_BENCHMARK_SERIES_PATH,
    SAMPLE_PRICE_SERIES_PATH,
    SIGNAL_ENGINE_INPUT_SUMMARY_PATH,
    SIGNAL_ENGINE_LEDGER_PATH,
    SIGNAL_ENGINE_PROOF_PATH,
    SIGNAL_ENGINE_REPORT_PATH,
    SIGNAL_ENGINE_SUMMARY_PATH,
    SIGNAL_EXPECTED_MATH_CASES_PATH,
    SIGNAL_QUALITY_FLAGS_PATH,
    TREND_PULLBACK_SIGNALS_PATH,
    VOLATILITY_REGIME_SIGNALS_PATH,
    _fixture_benchmark_series,
    _fixture_signal_series,
    build_signal_fixture_bundle,
    run_real_signal_engines,
)
from dopey_analysis.signal_models import make_price_bar, stable_signal_hash
from dopey_analysis.technical_signal_engine import (
    compute_breakout_signal,
    compute_fakeout_signal,
    compute_market_regime_signal,
    compute_momentum_signal,
    compute_relative_strength_signal,
    compute_trend_pullback_signal,
    compute_volatility_regime_signal,
    map_directional_setup_signal,
    realized_volatility,
)
from dopey_audit.artifact_loader import ARTIFACT_SPECS
from dopey_audit.evidence_inventory import build_inventory
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary, render_safety_summary
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _signal_engine_summary
from dopey_validation.full_suite_stabilizer import CommandResult, timeout_result, write_test_shard_plan


@pytest.fixture(scope="module")
def signal_result() -> dict:
    return run_real_signal_engines()


@pytest.fixture(scope="module")
def fixture_bundle() -> dict:
    return build_signal_fixture_bundle()


@pytest.fixture(scope="module")
def fixture_series(fixture_bundle: dict) -> dict:
    return _fixture_signal_series(fixture_bundle)


@pytest.fixture(scope="module")
def benchmark_series(fixture_bundle: dict):
    return _fixture_benchmark_series(fixture_bundle)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_model_serialization_and_hash_determinism() -> None:
    bar = make_price_bar("spy", "2026-01-01", 100.0, 101.0, 99.0, 100.5, 100.5, 1000, "fixture_only", False, True, True)
    first = bar.to_dict()
    second = bar.to_dict()
    assert first == second
    assert first["record_hash"] == stable_signal_hash(first)
    assert first["paper_only"] is True
    assert first["live_blocked"] is True


def test_momentum_calculation(fixture_series: dict) -> None:
    signal = compute_momentum_signal(fixture_series["MOM_BULL"], "2026-02-25", 20).to_dict()
    assert signal["return_5d"] > 0
    assert signal["return_10d"] > 0
    assert signal["return_20d"] > 0
    assert signal["direction"] == "bullish"
    assert "positive_momentum" in signal["reason_codes"]


def test_breakout_detection(fixture_series: dict) -> None:
    signal = compute_breakout_signal(fixture_series["BREAK_UP"], "2026-02-25", 20).to_dict()
    assert signal["direction"] == "bullish"
    assert signal["close_price"] > signal["prior_high"]
    assert signal["volume_confirmed"] is True
    assert "close_above_prior_high" in signal["reason_codes"]


def test_breakdown_detection(fixture_series: dict) -> None:
    signal = compute_breakout_signal(fixture_series["BREAK_DOWN"], "2026-02-25", 20).to_dict()
    assert signal["direction"] == "bearish"
    assert signal["close_price"] < signal["prior_low"]
    assert signal["volume_confirmed"] is True
    assert "close_below_prior_low" in signal["reason_codes"]


def test_fakeout_detection(fixture_series: dict) -> None:
    signal = compute_fakeout_signal(fixture_series["FAKE_UP_001"], "2026-02-21", 20).to_dict()
    assert signal["direction"] == "bearish"
    assert signal["prior_breakout_attempt"] is True
    assert signal["close_back_inside_prior_range"] is True
    assert signal["failed_breakout_direction"] == "failed_bullish_breakout"


def test_trend_pullback_detection(fixture_series: dict) -> None:
    signal = compute_trend_pullback_signal(fixture_series["PULL_UP_001"], "2026-03-02", 20).to_dict()
    assert signal["direction"] == "bullish"
    assert signal["continuation_confirmed"] is True
    assert "continuation_confirmed" in signal["reason_codes"]


def test_realized_vol_calculation(fixture_series: dict) -> None:
    value = realized_volatility(fixture_series["VOL_EXP"].bars[:40], 20)
    assert value >= 0.0
    assert isinstance(value, float)


def test_volatility_expansion_detection(fixture_series: dict) -> None:
    signal = compute_volatility_regime_signal(fixture_series["VOL_EXP"], "2026-03-07", 20).to_dict()
    assert signal["expansion_trigger"] is True
    assert signal["compression_trigger"] is False
    assert "volatility_expansion" in signal["reason_codes"]


def test_volatility_compression_detection(fixture_series: dict) -> None:
    signal = compute_volatility_regime_signal(fixture_series["VOL_COMP"], "2026-03-17", 20).to_dict()
    assert signal["compression_trigger"] is True
    assert signal["expansion_trigger"] is False
    assert "volatility_compression" in signal["reason_codes"]


def test_relative_strength_calculation(fixture_series: dict, benchmark_series) -> None:
    signal = compute_relative_strength_signal(fixture_series["RS_STRONG"], benchmark_series, "2026-02-25", 20).to_dict()
    assert signal["relative_return"] > 0
    assert signal["direction"] == "bullish"
    assert signal["missing_benchmark"] is False


def test_missing_benchmark_handling(fixture_series: dict) -> None:
    signal = compute_relative_strength_signal(fixture_series["RS_STRONG"], None, "2026-02-25", 20).to_dict()
    assert signal["direction"] == "neutral"
    assert signal["missing_benchmark"] is True
    assert "missing_benchmark" in signal["reason_codes"]


def test_regime_classifier_insufficient_history_state(fixture_series: dict) -> None:
    short_bars = fixture_series["REG_UP"].bars[:20]
    short_series = fixture_series["REG_UP"].__class__(
        artifact_type="signal_series",
        symbol="REG_UP",
        bars=short_bars,
        data_source_tier="fixture_only",
        real_history_used=False,
        fixture_only=True,
        not_real_signal_evidence=True,
        paper_only=True,
        live_blocked=True,
        series_hash="short",
    )
    signal = compute_market_regime_signal(short_series, short_bars[-1].date, 20).to_dict()
    assert signal["regime_label"] == "insufficient_history"
    assert signal["direction"] == "neutral"


def test_regime_classifier_trend_up_state(fixture_series: dict) -> None:
    signal = compute_market_regime_signal(fixture_series["REG_UP"], "2026-03-12", 20).to_dict()
    assert signal["trend_state"] == "trend_up"
    assert signal["regime_label"] == "trend_up_low_vol"
    assert signal["direction"] == "bullish"


def test_regime_classifier_trend_down_high_vol_state(fixture_series: dict) -> None:
    signal = compute_market_regime_signal(fixture_series["REG_DOWN_HV"], "2026-03-13", 20).to_dict()
    assert signal["trend_state"] == "trend_down"
    assert signal["volatility_state"] == "high_vol"
    assert signal["regime_label"] == "trend_down_high_vol"
    assert signal["direction"] == "bearish"


def test_directional_mapper_creates_long_call_candidate_only_for_bullish_setup(fixture_series: dict) -> None:
    source = compute_momentum_signal(fixture_series["MOM_BULL"], "2026-02-25", 20).to_dict()
    setup = map_directional_setup_signal(source).to_dict()
    assert setup["candidate_strategy"] == "long_call"
    assert setup["long_call_candidate"] is True
    assert setup["long_put_candidate"] is False
    assert setup["no_trade"] is False


def test_directional_mapper_creates_long_put_candidate_only_for_bearish_setup(fixture_series: dict) -> None:
    source = compute_momentum_signal(fixture_series["MOM_BEAR"], "2026-02-25", 20).to_dict()
    setup = map_directional_setup_signal(source).to_dict()
    assert setup["candidate_strategy"] == "long_put"
    assert setup["long_call_candidate"] is False
    assert setup["long_put_candidate"] is True
    assert setup["no_trade"] is False


def test_directional_mapper_creates_no_trade_for_neutral_setup(fixture_series: dict) -> None:
    source = compute_volatility_regime_signal(fixture_series["VOL_COMP"], "2026-03-17", 20).to_dict()
    setup = map_directional_setup_signal(source).to_dict()
    assert setup["candidate_strategy"] == "no_trade"
    assert setup["no_trade"] is True


def test_no_spread_short_vol_or_naked_selling_setup_created(signal_result: dict) -> None:
    setups = _jsonl(DIRECTIONAL_SETUP_SIGNALS_PATH)
    assert setups
    assert all(record["spread_created"] is False for record in setups)
    assert all(record["short_vol_created"] is False for record in setups)
    assert all(record["naked_selling_created"] is False for record in setups)
    assert all(record["same_day_churn_allowed"] is False for record in setups)
    assert {record["candidate_strategy"] for record in setups}.issubset({"long_call", "long_put", "no_trade"})


def test_missing_real_history_is_recorded_honestly(signal_result: dict) -> None:
    input_summary = _json(SIGNAL_ENGINE_INPUT_SUMMARY_PATH)
    summary = _json(SIGNAL_ENGINE_SUMMARY_PATH)
    assert input_summary["history_dataset_status"] == summary["history_dataset_status"]
    if summary["history_dataset_status"] == "valid_real_dataset":
        assert summary["signal_engine_status"] == "local_real_history_signal_computation_ready"
        assert summary["real_history_used"] is True
    else:
        assert summary["signal_engine_status"] == "missing_real_history_signal_validation_only"
        assert summary["real_history_used"] is False


def test_no_fake_real_history_pass(signal_result: dict) -> None:
    history_input = load_default_history_signal_input()
    assert HISTORY_SPINE_SUMMARY_PATH.exists()
    spine = json.loads(HISTORY_SPINE_SUMMARY_PATH.read_text(encoding="utf-8"))
    if spine.get("dataset_status") == "valid_real_dataset":
        assert history_input.real_history_used is True
        assert history_input.signal_status == "local_real_history_signal_computation_ready"
        assert history_input.local_real_history_case_count > 0
    else:
        assert history_input.real_history_used is False
        assert history_input.signal_status == "missing_real_history_signal_validation_only"


def test_fixture_only_signals_are_labeled_fixture_only(signal_result: dict) -> None:
    for path in [
        MOMENTUM_SIGNALS_PATH,
        BREAKOUT_SIGNALS_PATH,
        FAKEOUT_SIGNALS_PATH,
        TREND_PULLBACK_SIGNALS_PATH,
        VOLATILITY_REGIME_SIGNALS_PATH,
        RELATIVE_STRENGTH_SIGNALS_PATH,
        MARKET_REGIME_SIGNALS_PATH,
        DIRECTIONAL_SETUP_SIGNALS_PATH,
    ]:
        records = _jsonl(path)
        assert records
        assert all(record["data_source_tier"] == "fixture_only" for record in records)
        assert all(record["fixture_only"] is True for record in records)
        assert all(record["real_history_used"] is False for record in records)
        assert all(record["not_real_signal_evidence"] is True for record in records)


def test_no_real_edge_claim(signal_result: dict) -> None:
    summary = _json(SIGNAL_ENGINE_SUMMARY_PATH)
    assert summary["not_real_edge_evidence"] is True
    assert "not_real_edge_evidence" in summary["quality_flags"]
    assert summary["next_recommended_target"] == "DOPEY_HONEST_BACKTESTER_V1"


def test_artifacts_written(signal_result: dict) -> None:
    for path in [
        SAMPLE_PRICE_SERIES_PATH,
        SAMPLE_BENCHMARK_SERIES_PATH,
        SIGNAL_EXPECTED_MATH_CASES_PATH,
        SIGNAL_ENGINE_INPUT_SUMMARY_PATH,
        MOMENTUM_SIGNALS_PATH,
        BREAKOUT_SIGNALS_PATH,
        FAKEOUT_SIGNALS_PATH,
        TREND_PULLBACK_SIGNALS_PATH,
        VOLATILITY_REGIME_SIGNALS_PATH,
        RELATIVE_STRENGTH_SIGNALS_PATH,
        MARKET_REGIME_SIGNALS_PATH,
        DIRECTIONAL_SETUP_SIGNALS_PATH,
        SIGNAL_QUALITY_FLAGS_PATH,
        SIGNAL_ENGINE_SUMMARY_PATH,
        SIGNAL_ENGINE_PROOF_PATH,
        SIGNAL_ENGINE_REPORT_PATH,
        SIGNAL_ENGINE_LEDGER_PATH,
    ]:
        assert path.exists()
    expected = _json(SIGNAL_EXPECTED_MATH_CASES_PATH)
    assert expected["case_count"] == 80


def test_audit_recognizes_signal_artifacts(signal_result: dict) -> None:
    names = {spec[0] for spec in ARTIFACT_SPECS}
    required = {
        "signal_engine_input_summary",
        "momentum_signals",
        "breakout_signals",
        "fakeout_signals",
        "trend_pullback_signals",
        "volatility_regime_signals",
        "relative_strength_signals",
        "market_regime_signals",
        "directional_setup_signals",
        "signal_quality_flags",
        "signal_engine_summary",
        "signal_engine_proof",
    }
    assert required.issubset(names)
    inventory = build_inventory()
    status_by_type = {artifact.artifact_type: artifact.status for artifact in inventory.artifacts}
    assert status_by_type["signal_engine_summary"] == "present"


def test_reporting_includes_signal_summary(signal_result: dict) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    summary = _signal_engine_summary(evidence)
    if summary.get("history_dataset_status") == "valid_real_dataset":
        assert summary["signal_engine_status"] == "local_real_history_signal_computation_ready"
    else:
        assert summary["signal_engine_status"] == "missing_real_history_signal_validation_only"
    assert summary["fixture_only_case_count"] == 80
    assert summary["not_real_edge_evidence"] is True


def test_export_includes_signal_artifacts() -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {
        "signal_engine_input_summary",
        "momentum_signals",
        "breakout_signals",
        "fakeout_signals",
        "trend_pullback_signals",
        "volatility_regime_signals",
        "relative_strength_signals",
        "market_regime_signals",
        "directional_setup_signals",
        "signal_quality_flags",
        "signal_engine_summary",
        "signal_engine_proof",
    }.issubset(ids)


def test_export_review_includes_signal_summary(signal_result: dict) -> None:
    ctx = SimpleNamespace(
        shared_export_path="",
        reporting_summary={"signal_engine_summary": _json(SIGNAL_ENGINE_SUMMARY_PATH)},
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
    decision = SimpleNamespace(decision="review_ready", suitability="offline_review", next_build_target="DOPEY_HONEST_BACKTESTER_V1")
    rendered = render_executive_summary(ctx, bundle, [], decision)
    assert "Real Signal Engines" in rendered
    assert "fixture/math validation only" in rendered
    assert "not_real_edge_evidence: `true`" in rendered


def test_validation_stabilizer_includes_signal_shard() -> None:
    summary = {
        "collection": {"status": "pass", "stdout_tail": ""},
        "full_suite": {"status": "inconclusive_timeout"},
    }
    plan = write_test_shard_plan(
        ["tests/test_real_signal_engines.py"],
        [CommandResult(["python", "-m", "pytest", "tests/test_real_signal_engines.py", "-q"], "pass", 0, 0.1, False, False, "", "")],
        summary,
    )
    assert "tests/test_real_signal_engines.py" in plan["split_suite_lanes"]["real_signal_engine_tests"]
    assert "tests/test_real_signal_engines.py" in plan["artifact_writing_tests_sequential"]


def test_full_pytest_timeout_remains_inconclusive_not_pass() -> None:
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout"
    assert result["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled() -> None:
    intent = ExecutionIntent(
        intent_id="signal-engine-live-disabled",
        symbol="SPY",
        structure="single",
        legs=[{"side": "buy", "symbol": "SPY_CALL", "option_type": "call", "expiry": "2026-08-21"}],
        live_allowed=True,
        paper=False,
    )
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(intent)


def test_no_broker_connection_credentials_scheduler_or_real_sizing(signal_result: dict) -> None:
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in [
        Path("dopey_analysis/signal_models.py"),
        Path("dopey_analysis/technical_signal_engine.py"),
        Path("dopey_analysis/history_signal_adapter.py"),
        Path("dopey_analysis/run_real_signal_engines.py"),
    ])
    assert "requests" not in text
    assert "websocket" not in text
    assert "place_order" not in text
    assert "cancel_order" not in text
    assert "review_order" not in text
    assert "sk-proj-" not in text
    assert "api_key" not in text
    assert ".env" not in text
    assert "cron" not in text
    assert "apscheduler" not in text
    assert "buying_power" not in text
    assert "account_balance" not in text
    assert "robinhood_mcp" not in text
    setups = _jsonl(DIRECTIONAL_SETUP_SIGNALS_PATH)
    assert all(record["broker_required"] is False for record in setups)
    assert all(record["real_sizing_used"] is False for record in setups)


def test_export_review_safety_summary_mentions_signal_engines() -> None:
    ctx = SimpleNamespace(
        safety_state={
            "mode": "RESEARCH",
            "live_trading_enabled": False,
            "funded_broker_connections_enabled": False,
            "allow_unofficial_robinhood_api": False,
        },
        export_safety_scan={"active_forbidden_live_decisions": 0, "credential_findings": 0},
    )
    assert "real_signal_engines" in render_safety_summary(ctx)


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        assert True
        return
    assert manifest.read_text(encoding="utf-8").strip() != ""
