"""Integration checks for paper execution quality and readiness tiering."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from dopey.ascendancy.execution_quality import (
    PaperExecutionQualityInput,
    evaluate_paper_execution_quality,
    v1_execution_quality_policy,
)
from dopey.ascendancy.readiness_frontier import build_trade_readiness_frontier
from dopey_execution.execution_quality_logger import ExecutionQualityLogger
from dopey.runtime.run_trade_readiness_frontier import run_trade_readiness_frontier


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def test_observed_and_simulated_execution_evidence_remain_distinct() -> None:
    observed = PaperExecutionQualityInput(
        observation_id="paper-execution-quality-001",
        instrument_id="SPY-OPTION-PACKAGE",
        side="buy",
        fill_status="filled",
        quantity=10,
        package_leg_count=2,
        arrival_bid=1.0,
        arrival_ask=1.2,
        arrival_benchmark_price=1.1,
        executed_price=1.15,
        post_trade_mid_1m=1.18,
        post_trade_mid_5m=1.2,
        fees=0.01,
        quote_age_ms=125.0,
        evidence_class="observed_nbbo",
        observed_at="2026-07-18T15:00:00+00:00",
        paper_only=True,
        live_blocked=True,
    )
    validated = evaluate_paper_execution_quality(observed, v1_execution_quality_policy())
    simulated = evaluate_paper_execution_quality(
        replace(
            observed,
            observation_id="paper-execution-quality-002",
            evidence_class="simulated_quote",
        ),
        v1_execution_quality_policy(),
    )

    assert validated["status"] == "observed_execution_quality_validated"
    assert validated["effective_to_quoted_ratio"] == 0.5
    assert validated["execution_calibration_eligible"] is True
    assert validated["strategy_profitability_evidence_eligible"] is False
    assert simulated["status"] == "uncalibrated_simulated_execution"
    assert simulated["execution_calibration_eligible"] is False

    logger = ExecutionQualityLogger()
    logged = logger.evaluate_and_log(observed, v1_execution_quality_policy())
    events = logger.events()
    assert logged["status"] == "observed_execution_quality_validated"
    assert len(events) == 1
    assert events[0]["execution_quality_event_hash"]


def test_current_frontier_is_source_backed_and_keeps_live_authority_absent(tmp_path: Path) -> None:
    output_path = tmp_path / "trade_readiness_frontier.json"
    report_path = tmp_path / "DOPEY_TRADE_READINESS_FRONTIER_REPORT.md"
    frontier = run_trade_readiness_frontier(REPOSITORY_ROOT, output_path, report_path)
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    levels = persisted["levels"]

    assert frontier["reproducibility_hash"] == persisted["reproducibility_hash"]
    assert levels["research_mechanics"]["ready"] is True
    assert levels["live_execution"]["ready"] is False
    assert levels["live_execution"]["status"] == "constitutionally_unavailable"
    assert persisted["thresholds_weakened"] is False
    assert persisted["simulation_counted_as_realized_evidence"] is False
    assert report_path.is_file()


def test_resumable_nightly_green_status_unlocks_only_paper_promotion() -> None:
    sealed = {"paper_only": True, "live_blocked": True}
    frontier = build_trade_readiness_frontier(
        {
            **sealed,
            "action_ready": True,
            "forward_closed_trades": 100,
            "forward_closed_trades_required": 100,
            "checks": {
                "forward_track_sample_sufficient": True,
                "forward_track_net_positive": True,
                "any_cohort_regime_robust": True,
                "statistical_truth_promotion_allowed": True,
            },
        },
        {
            **sealed,
            "suite_green": True,
            "suite": {"suite_status": "complete_green", "failed": 0, "errors": 0},
        },
        {**sealed, "options_data_validated": True, "quote_priced_backtest_allowed": True},
        {**sealed, "dataset_status": "operator_staged_real_dataset", "data_files": [{}] * 200},
        {**sealed, "stress_case_count": 120, "paper_shadow_contained": True, "same_day_churn_allowed": False},
        {**sealed, "incident_case_count": 144, "terminal_block_auto_recovery_allowed": False},
        {**sealed, "proof_completeness": True, "lifecycle_case_count": 136, "paperbroker_override_allowed": False},
    )

    assert frontier["levels"]["strategy_promotion"]["ready"] is True
    assert frontier["levels"]["live_execution"]["ready"] is False
    assert frontier["live_trading_enabled"] is False
