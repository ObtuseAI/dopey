"""Integration proofs for the research-only equity distribution forecast."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from dopey.forecasting.equity_distribution import (
    EquityForecastPolicy,
    EquityPriceBar,
    build_equity_distribution_forecast,
    short_horizon_equity_forecast_policy,
)
from dopey.forecasting.operational import (
    _as_of_slice_sha256,
    run_equity_distribution_forecast_artifact,
    run_equity_distribution_forecast_batch,
)
from dopey.technical.history_adapter import load_default_validated_symbol_history


def _price_rows(rows: list[dict[str, object]]) -> list[EquityPriceBar]:
    return [
        EquityPriceBar(
            date=str(row["date"]),
            close=float(row["close"]),
            adjusted_close=float(row["adjusted_close"]),
            volume=int(row["volume"]),
        )
        for row in rows
    ]


def _policy(
    maximum_analogue_count: int,
    minimum_analogue_count: int,
    minimum_effective_sample_size: float,
    minimum_diagnostic_predictions: int,
    maximum_diagnostic_predictions: int,
) -> EquityForecastPolicy:
    return EquityForecastPolicy(
        horizon_trading_days=10,
        short_lookback=5,
        medium_lookback=20,
        long_lookback=60,
        maximum_analogue_count=maximum_analogue_count,
        minimum_analogue_count=minimum_analogue_count,
        minimum_effective_sample_size=minimum_effective_sample_size,
        minimum_active_feature_count=8,
        recency_half_life_observations=1260,
        lower_interval_quantile=0.1,
        upper_interval_quantile=0.9,
        neutral_log_return_band=0.005,
        minimum_diagnostic_predictions=minimum_diagnostic_predictions,
        maximum_diagnostic_predictions=maximum_diagnostic_predictions,
    )


def _real_histories() -> tuple[
    list[EquityPriceBar],
    str,
    list[EquityPriceBar],
    str,
]:
    subject, subject_proof = load_default_validated_symbol_history("AAPL")
    benchmark, benchmark_proof = load_default_validated_symbol_history("SPY")
    return (
        _price_rows(cast(list[dict[str, object]], subject)),
        str(subject_proof["actual_sha256"]),
        _price_rows(cast(list[dict[str, object]], benchmark)),
        str(benchmark_proof["actual_sha256"]),
    )


def test_short_horizon_policies_are_independent_and_stricter() -> None:
    policies = [
        short_horizon_equity_forecast_policy(horizon)
        for horizon in range(1, 6)
    ]

    assert [policy.horizon_trading_days for policy in policies] == [1, 2, 3, 4, 5]
    assert all(policy.minimum_analogue_count == 20 for policy in policies)
    assert all(policy.minimum_diagnostic_predictions == 60 for policy in policies)
    assert [policy.neutral_log_return_band for policy in policies] == sorted(
        policy.neutral_log_return_band for policy in policies
    )
    with pytest.raises(ValueError, match="one through five"):
        short_horizon_equity_forecast_policy(0)
    with pytest.raises(ValueError, match="one through five"):
        short_horizon_equity_forecast_policy(6)


def test_real_history_forecast_is_distributional_past_only_and_non_promotional() -> (
    None
):
    subject, subject_source, benchmark, benchmark_source = _real_histories()
    as_of = min(subject[-1]["date"], benchmark[-1]["date"])

    forecast = build_equity_distribution_forecast(
        "AAPL",
        subject,
        subject_source,
        "SPY",
        benchmark,
        benchmark_source,
        as_of,
        _policy(30, 12, 6.0, 30, 60),
    )

    assert forecast["forecast_status"] == (
        "research_distribution_available_no_edge_or_coverage_claim"
    )
    distribution = forecast["price_distribution"]
    assert distribution is not None
    prices = [record["price"] for record in distribution["return_and_price_quantiles"]]
    assert prices == sorted(prices)
    mass = distribution["directional_empirical_mass"]
    assert mass["bearish"] + mass["neutral"] + mass["bullish"] == pytest.approx(1.0)
    assert mass["calibrated_probability_claimed"] is False
    assert distribution["conformal_method_claimed"] is False
    assert distribution["finite_sample_coverage_guaranteed"] is False
    assert forecast["historical_option_evidence_consumed"] is False
    assert forecast["corporate_action_semantics_validated"] is False
    assert forecast["strategy_promotion_allowed"] is False
    assert forecast["order_construction_allowed"] is False
    assert forecast["paper_only"] is True
    assert forecast["live_blocked"] is True

    analogues = forecast["analogue_evidence"]["selected_analogues"]
    assert len(analogues) >= 12
    assert all(record["label_end_date"] < as_of for record in analogues)
    assert forecast["analogue_evidence"]["overlapping_label_windows_selected"] is False
    diagnostics = forecast["prequential_diagnostics"]
    assert diagnostics["same_or_future_outcomes_used_for_training"] is False
    assert diagnostics["coverage_diagnostic_only"] is True
    assert diagnostics["coverage_guarantee_claimed"] is False
    assert diagnostics["promotion_allowed"] is False
    assert diagnostics["proper_scores_are_prequential"] is True
    assert diagnostics["overlapping_diagnostic_label_windows_scored"] is False
    assert diagnostics["mean_multiclass_brier_score"] is not None
    assert diagnostics["beta_scaled_benchmark_mean_multiclass_brier_score"] is not None
    assert diagnostics["uniform_mean_multiclass_log_loss"] is not None
    guardrail = forecast["point_forecast_guardrail"]
    assert guardrail["accuracy_improvement_claimed"] is False
    assert guardrail["selection_uses_only_past_prequential_diagnostics"] is True
    if diagnostics["mae_skill_vs_beta_scaled_benchmark"] > 0.0:
        assert guardrail["selected_method"] == "historical_analogue_median"
    else:
        assert (
            guardrail["selected_method"]
            == "beta_scaled_benchmark_baseline_median"
        )


def test_hash_pinned_operator_adapter_writes_reviewable_research_artifact(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "aapl_distribution.json"

    forecast = run_equity_distribution_forecast_artifact(
        "AAPL",
        "SPY",
        output_path,
        _policy(15, 6, 3.0, 10, 20),
    )

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").endswith("\n")
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["reproducibility_hash"] == forecast["reproducibility_hash"]
    assert not output_path.with_name(f".{output_path.name}.tmp").exists()
    assert forecast["subject_source_id"]
    assert forecast["benchmark_source_id"]
    assert forecast["policy"]["horizon_trading_days"] == 10
    assert forecast["not_trade_decision"] is True
    assert forecast["strategy_promotion_allowed"] is False
    assert forecast["order_construction_allowed"] is False
    assert forecast["paper_only"] is True
    assert forecast["live_blocked"] is True


def test_batch_adapter_publishes_hash_pinned_manifest_after_symbol_artifacts(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "batch"

    summary = run_equity_distribution_forecast_batch(
        ("AAPL", "MSFT"),
        "SPY",
        output_root,
        _policy(15, 6, 3.0, 10, 20),
    )

    assert summary["batch_status"] == "research_batch_complete_no_edge_or_live_claim"
    assert summary["symbol_count"] == 2
    assert summary["historical_option_evidence_consumed"] is False
    assert summary["edge_claimed"] is False
    assert summary["strategy_promotion_allowed"] is False
    assert summary["order_construction_allowed"] is False
    assert summary["live_blocked"] is True
    assert summary["baseline_guardrail_count"] <= summary["symbol_count"]
    assert (output_root / "AAPL_distribution.json").is_file()
    assert (output_root / "MSFT_distribution.json").is_file()
    assert (output_root / "batch_summary.json").is_file()
    written = json.loads((output_root / "batch_summary.json").read_text(encoding="utf-8"))
    assert written["reproducibility_hash"] == summary["reproducibility_hash"]
    assert {record["artifact_path"] for record in summary["records"]} == {
        "AAPL_distribution.json",
        "MSFT_distribution.json",
    }
    assert all(len(record["artifact_sha256"]) == 64 for record in summary["records"])
    assert all(record["selected_point_forecast_method"] for record in summary["records"])


def test_rows_after_as_of_cannot_change_the_forecast() -> None:
    subject, subject_source, benchmark, benchmark_source = _real_histories()
    subject = subject[-1600:]
    benchmark = benchmark[-1700:]
    as_of = subject[-300]["date"]
    policy = _policy(15, 6, 3.0, 10, 20)

    original = build_equity_distribution_forecast(
        "AAPL",
        subject,
        subject_source,
        "SPY",
        benchmark,
        benchmark_source,
        as_of,
        policy,
    )
    altered_subject = [dict(row) for row in subject]
    altered_benchmark = [dict(row) for row in benchmark]
    for row in altered_subject:
        if str(row["date"]) > as_of:
            row["close"] = float(row["close"]) * 7.0
            row["adjusted_close"] = float(row["adjusted_close"]) * 7.0
            row["volume"] = int(row["volume"]) + 99_000_000
    for row in altered_benchmark:
        if str(row["date"]) > as_of:
            row["close"] = float(row["close"]) * 5.0
            row["adjusted_close"] = float(row["adjusted_close"]) * 5.0

    altered = build_equity_distribution_forecast(
        "AAPL",
        cast(list[EquityPriceBar], altered_subject),
        subject_source,
        "SPY",
        cast(list[EquityPriceBar], altered_benchmark),
        benchmark_source,
        as_of,
        policy,
    )

    assert altered == original
    assert _as_of_slice_sha256(
        cast(list[dict[str, object]], subject),
        as_of,
    ) == _as_of_slice_sha256(
        cast(list[dict[str, object]], altered_subject),
        as_of,
    )
    assert _as_of_slice_sha256(
        cast(list[dict[str, object]], benchmark),
        as_of,
    ) == _as_of_slice_sha256(
        cast(list[dict[str, object]], altered_benchmark),
        as_of,
    )


def test_insufficient_real_history_analogues_abstain_without_price_output() -> None:
    subject, subject_source, benchmark, benchmark_source = _real_histories()
    subject = subject[-100:]
    benchmark = benchmark[-110:]
    as_of = min(subject[-1]["date"], benchmark[-1]["date"])

    forecast = build_equity_distribution_forecast(
        "AAPL",
        subject,
        subject_source,
        "SPY",
        benchmark,
        benchmark_source,
        as_of,
        _policy(30, 20, 10.0, 20, 30),
    )

    assert forecast["forecast_status"].startswith("abstain_")
    assert forecast["price_distribution"] is None
    assert forecast["not_edge_evidence"] is True
    assert forecast["strategy_promotion_allowed"] is False
    assert forecast["order_construction_allowed"] is False
