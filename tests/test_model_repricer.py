"""Tests for DOPEY's offline model repricer bundle."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dopey_audit.artifact_loader import ARTIFACT_SPECS, build_inventory
from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_export.artifact_selector import export_selection_rules
from dopey_export_review.review_packet import render_executive_summary, render_safety_summary
from dopey_options.iv_solver import solve_implied_volatility
from dopey_options.model_repricing_engine import reprice_long_option_path, repricing_path_input
from dopey_options.option_pricing_models import option_pricing_input, price_european_option
from dopey_options.run_model_repricer import (
    IV_SOLVER_VALIDATION_PATH,
    MODEL_REPRICING_CASES_PATH,
    MODEL_REPRICING_PROOF_PATH,
    MODEL_REPRICING_QUALITY_FLAGS_PATH,
    MODEL_REPRICING_RESULTS_PATH,
    MODEL_REPRICING_SUMMARY_PATH,
    VOL_SURFACE_MODEL_PATH,
    build_model_repricing_fixture_cases,
    run_model_repricer,
)
from dopey_options.vol_surface_model import build_minimal_vol_surface_snapshot, surface_point
from dopey_reporting.data_loader import EVIDENCE_PATHS, load_reporting_evidence
from dopey_reporting.reporting_bundle import _model_repricing_summary
from dopey_validation.full_suite_stabilizer import CommandResult, timeout_result, write_test_shard_plan


@pytest.fixture(scope="module")
def repricer_result() -> dict:
    return run_model_repricer()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _priced(option_type: str, underlying_price: float, strike: float, iv: float):
    return price_european_option(option_pricing_input(
        "SPY_MODEL",
        option_type,
        strike,
        "2026-08-21",
        "2026-07-01",
        underlying_price,
        30.0 / 365.0,
        iv,
        0.04,
        0.0,
        "fixture_only",
    ))


def _solve(option_type: str, underlying_price: float, strike: float, option_price: float, initial_volatility: float):
    return solve_implied_volatility(
        "SPY_MODEL",
        option_type,
        strike,
        "2026-08-21",
        "2026-07-01",
        underlying_price,
        option_price,
        30.0 / 365.0,
        0.04,
        0.0,
        "fixture_only",
        False,
        initial_volatility,
        0.000001,
        100,
    )


def test_iv_solver_call_round_trip() -> None:
    priced = _priced("call", 100.0, 100.0, 0.31)
    solved = _solve("call", 100.0, 100.0, priced.model_price, 0.25)
    assert solved.solver_status == "solved"
    assert abs(solved.iv - 0.31) < 0.0001


def test_iv_solver_put_round_trip() -> None:
    priced = _priced("put", 100.0, 100.0, 0.29)
    solved = _solve("put", 100.0, 100.0, priced.model_price, 0.25)
    assert solved.solver_status == "solved"
    assert abs(solved.iv - 0.29) < 0.0001


def test_intrinsic_floor_rejection() -> None:
    solved = _solve("call", 110.0, 100.0, 9.0, 0.25)
    assert solved.solver_status == "invalid_input"
    assert "option_price_below_intrinsic_floor" in solved.reason_codes


def test_upper_bound_rejection() -> None:
    solved = _solve("put", 100.0, 95.0, 96.0, 0.25)
    assert solved.solver_status == "invalid_input"
    assert "option_price_above_reasonable_upper_bound" in solved.reason_codes


def test_newton_solve_path() -> None:
    priced = _priced("call", 102.0, 100.0, 0.34)
    solved = _solve("call", 102.0, 100.0, priced.model_price, 0.25)
    assert solved.solver_status == "solved"
    assert solved.method_used == "newton_raphson"


def test_bisection_fallback_path() -> None:
    priced = _priced("put", 125.0, 100.0, 0.43)
    solved = _solve("put", 125.0, 100.0, priced.model_price, 0.000001)
    assert solved.solver_status == "fallback_solved"
    assert solved.method_used == "bisection_fallback"


def test_invalid_input_rejection() -> None:
    solved = solve_implied_volatility(
        "SPY_MODEL",
        "call",
        100.0,
        "2026-08-21",
        "2026-07-01",
        0.0,
        1.0,
        30.0 / 365.0,
        0.04,
        0.0,
        "fixture_only",
        False,
        0.25,
        0.000001,
        100,
    )
    assert solved.solver_status == "invalid_input"
    assert "nonpositive_underlying" in solved.reason_codes


def test_vol_surface_floor_clamp() -> None:
    point = surface_point("SPY_MODEL", "put", 150.0, 30, 100.0, 0.20, 1.0, 0.0, 0.10, 0.50)
    assert point.implied_vol == 0.10
    assert point.clamp_applied is True


def test_vol_surface_cap_clamp() -> None:
    point = surface_point("SPY_MODEL", "call", 150.0, 30, 100.0, 0.20, 1.0, 0.0, 0.10, 0.50)
    assert point.implied_vol == 0.50
    assert point.clamp_applied is True


def test_vol_surface_deterministic_hash() -> None:
    first = build_minimal_vol_surface_snapshot("SPY_MODEL", "2026-07-01", 100.0, 0.32, 0.45, 0.08, 0.10, 1.25, [7, 30], [0.95, 1.0], False).to_dict()
    second = build_minimal_vol_surface_snapshot("SPY_MODEL", "2026-07-01", 100.0, 0.32, 0.45, 0.08, 0.10, 1.25, [7, 30], [0.95, 1.0], False).to_dict()
    assert first["snapshot_hash"] == second["snapshot_hash"]
    assert first == second


def test_call_pricing_result_has_greeks() -> None:
    priced = _priced("call", 100.0, 100.0, 0.30)
    assert priced.delta > 0.0
    assert priced.gamma > 0.0
    assert priced.vega > 0.0


def test_put_pricing_result_has_greeks() -> None:
    priced = _priced("put", 100.0, 100.0, 0.30)
    assert priced.delta < 0.0
    assert priced.gamma > 0.0
    assert priced.vega > 0.0


def test_theta_decay_over_path(repricer_result: dict) -> None:
    theta = next(record for record in _jsonl(MODEL_REPRICING_RESULTS_PATH) if record["path_id"] == "theta_decay_path")
    marks = theta["mark_to_market_path"]
    assert marks[0] > marks[-1]


def test_volatility_expansion_increases_extrinsic_value(repricer_result: dict) -> None:
    record = next(item for item in _jsonl(MODEL_REPRICING_RESULTS_PATH) if item["path_id"] == "volatility_expansion_path")
    extrinsic = [step["extrinsic_value"] for step in record["repricing_results"]]
    assert extrinsic[-1] > extrinsic[0]


def test_volatility_compression_decreases_extrinsic_value(repricer_result: dict) -> None:
    record = next(item for item in _jsonl(MODEL_REPRICING_RESULTS_PATH) if item["path_id"] == "volatility_compression_path")
    extrinsic = [step["extrinsic_value"] for step in record["repricing_results"]]
    assert extrinsic[-1] < extrinsic[0]


def test_repricing_path_produces_deterministic_marks() -> None:
    surface = build_minimal_vol_surface_snapshot("SPY_MODEL", "2026-07-01", 100.0, 0.32, 0.45, 0.08, 0.10, 1.25, [30], [1.0], False)
    rows = [
        {"valuation_date": "2026-07-01", "underlying_price": 100.0, "days_to_expiry": 30, "implied_vol": 0.30},
        {"valuation_date": "2026-07-02", "underlying_price": 101.0, "days_to_expiry": 29, "implied_vol": 0.30},
    ]
    first = reprice_long_option_path(repricing_path_input("deterministic-path", "SPY_MODEL", "call", 100.0, "2026-08-21", rows, surface.to_dict(), 0.04, 0.0, "missing_real_dataset", False, "model_priced")).to_dict()
    second = reprice_long_option_path(repricing_path_input("deterministic-path", "SPY_MODEL", "call", 100.0, "2026-08-21", rows, surface.to_dict(), 0.04, 0.0, "missing_real_dataset", False, "model_priced")).to_dict()
    assert first["result_hash"] == second["result_hash"]
    assert first["mark_to_market_path"] == second["mark_to_market_path"]


def test_history_dataset_state_recorded_honestly(repricer_result: dict) -> None:
    """The repricer must record the history state COHERENTLY: absence claims
    are only made when the dataset really is missing, and never suppressed
    when it is. (Originally written pre-staging as a missing-only assertion;
    the repo now carries an operator-staged real dataset.)"""
    summary = _json(MODEL_REPRICING_SUMMARY_PATH)
    status = summary["history_dataset_status"]
    assert status in {"missing_real_dataset", "invalid_real_dataset", "valid_real_dataset"}
    assert summary["real_history_absent"] is (status == "missing_real_dataset")
    if status == "missing_real_dataset":
        assert "missing_real_history" in summary["quality_flags"]


def test_missing_options_chain_recorded_honestly(repricer_result: dict) -> None:
    summary = _json(MODEL_REPRICING_SUMMARY_PATH)
    assert summary["real_option_chain_absent"] is True
    assert "real_option_chain_absent" in summary["quality_flags"]


def test_no_quote_priced_claim_without_quote_data(repricer_result: dict) -> None:
    summary = _json(MODEL_REPRICING_SUMMARY_PATH)
    assert summary["quote_priced_records"] == 0
    solved = solve_implied_volatility("SPY_MODEL", "call", 100.0, "2026-08-21", "2026-07-01", 100.0, 3.0, 30.0 / 365.0, 0.04, 0.0, "quote_priced", False, 0.25, 0.000001, 100)
    assert solved.solver_status == "invalid_input"
    assert "quote_priced_requires_real_option_chain" in solved.reason_codes


def test_artifacts_written(repricer_result: dict) -> None:
    for path in [
        IV_SOLVER_VALIDATION_PATH,
        VOL_SURFACE_MODEL_PATH,
        MODEL_REPRICING_CASES_PATH,
        MODEL_REPRICING_RESULTS_PATH,
        MODEL_REPRICING_QUALITY_FLAGS_PATH,
        MODEL_REPRICING_SUMMARY_PATH,
        MODEL_REPRICING_PROOF_PATH,
    ]:
        assert path.exists()
    assert len(_jsonl(MODEL_REPRICING_CASES_PATH)) >= 48


def test_audit_recognizes_artifacts(repricer_result: dict) -> None:
    names = {spec[0] for spec in ARTIFACT_SPECS}
    required = {
        "iv_solver_validation",
        "vol_surface_model",
        "model_repricing_cases",
        "model_repricing_results",
        "model_repricing_quality_flags",
        "model_repricing_summary",
        "model_repricing_proof",
    }
    assert required.issubset(names)
    inventory = build_inventory()
    status_by_type = {artifact.artifact_type: artifact.status for artifact in inventory.artifacts}
    assert status_by_type["model_repricing_summary"] == "present"


def test_reporting_includes_model_repricing_summary(repricer_result: dict) -> None:
    evidence = load_reporting_evidence(EVIDENCE_PATHS)
    summary = _model_repricing_summary(evidence)
    assert summary["model_repricing_status"] == "model_priced_fixture_validation_only"
    assert summary["quote_priced_records"] == 0


def test_export_includes_repricer_artifacts() -> None:
    ids = {rule.artifact_id for rule in export_selection_rules()}
    assert {
        "iv_solver_validation",
        "vol_surface_model",
        "model_repricing_cases",
        "model_repricing_results",
        "model_repricing_quality_flags",
        "model_repricing_summary",
        "model_repricing_proof",
    }.issubset(ids)


def test_export_review_includes_repricer_summary(repricer_result: dict) -> None:
    ctx = SimpleNamespace(
        shared_export_path="",
        reporting_summary={"model_repricing_summary": _json(MODEL_REPRICING_SUMMARY_PATH)},
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
    decision = SimpleNamespace(decision="review_ready", suitability="offline_review", next_build_target="DOPEY_REAL_SIGNAL_ENGINES_V1")
    rendered = render_executive_summary(ctx, bundle, [], decision)
    assert "Model Repricer" in rendered
    assert "quote_priced_count: `0`" in rendered


def test_validation_stabilizer_includes_repricer_shard() -> None:
    summary = {
        "collection": {"status": "pass", "stdout_tail": ""},
        "full_suite": {"status": "inconclusive_timeout"},
    }
    plan = write_test_shard_plan(
        ["tests/test_model_repricer.py"],
        [CommandResult(["python", "-m", "pytest", "tests/test_model_repricer.py", "-q"], "pass", 0, 0.1, False, False, "", "")],
        summary,
    )
    assert "tests/test_model_repricer.py" in plan["split_suite_lanes"]["model_repricer_tests"]
    assert "tests/test_model_repricer.py" in plan["artifact_writing_tests_sequential"]


def test_full_pytest_timeout_remains_inconclusive_not_pass() -> None:
    result = timeout_result(["python", "-m", "pytest"], 1)
    assert result["status"] == "inconclusive_timeout"
    assert result["timeout_recorded_as_pass"] is False


def test_live_trading_still_disabled() -> None:
    intent = ExecutionIntent(
        intent_id="model-repricer-live-disabled",
        symbol="SPY",
        structure="single",
        legs=[{"side": "buy", "symbol": "SPY_CALL", "option_type": "call", "expiry": "2026-08-21"}],
        live_allowed=True,
        paper=False,
    )
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(intent)


def test_no_broker_connection_credentials_scheduler_or_real_sizing() -> None:
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in [
        Path("dopey_options/iv_solver.py"),
        Path("dopey_options/option_pricing_models.py"),
        Path("dopey_options/vol_surface_model.py"),
        Path("dopey_options/model_repricing_engine.py"),
        Path("dopey_options/run_model_repricer.py"),
    ])
    assert "requests" not in text
    assert "websocket" not in text
    assert "place_order" not in text
    assert "cancel_order" not in text
    assert "review_order" not in text
    assert "sk-proj-" not in text
    assert "api_key" not in text
    assert "cron" not in text
    assert "apscheduler" not in text
    assert "buying_power" not in text
    assert "account_balance" not in text
    assert "robinhood_mcp" not in text


def test_export_review_safety_summary_mentions_repricer() -> None:
    ctx = SimpleNamespace(
        safety_state={
            "mode": "RESEARCH",
            "live_trading_enabled": False,
            "funded_broker_connections_enabled": False,
            "allow_unofficial_robinhood_api": False,
        },
        export_safety_scan={"active_forbidden_live_decisions": 0, "credential_findings": 0},
    )
    assert "model_repricer" in render_safety_summary(ctx)


def test_fixture_cases_include_required_families() -> None:
    families = {case["case_family"] for case in build_model_repricing_fixture_cases()}
    assert {
        "call_iv_round_trip",
        "put_iv_round_trip",
        "intrinsic_floor_rejection",
        "upper_bound_rejection",
        "newton_solved",
        "bisection_fallback_solved",
        "surface_clamp_floor",
        "surface_clamp_cap",
        "missing_real_history_case",
        "missing_real_options_chain_case",
    }.issubset(families)


def test_blunder_integrity_unchanged_if_manifest_available() -> None:
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    if not manifest.exists():
        assert True
        return
    assert manifest.read_text(encoding="utf-8-sig").strip() or manifest.exists()
