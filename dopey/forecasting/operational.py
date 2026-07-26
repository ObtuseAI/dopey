"""Hash-pinned file adapter for research-only equity forecast artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, TypedDict, cast

from dopey.technical.history_adapter import load_default_validated_symbol_history

from .equity_distribution import (
    EquityDistributionForecast,
    EquityForecastPolicy,
    EquityPriceBar,
    build_equity_distribution_forecast,
    short_horizon_equity_forecast_policy,
)


class EquityForecastArtifactRecord(TypedDict):
    symbol: str
    forecast_status: str
    as_of_date: str
    artifact_path: str
    artifact_sha256: str
    forecast_reproducibility_hash: str
    distribution_available: bool
    diagnostics_status: str
    observed_interval_coverage: float | None
    mae_skill_versus_beta_scaled_benchmark: float | None
    selected_point_forecast_method: str
    selected_point_forecast_price: float | None
    strategy_promotion_allowed: bool
    order_construction_allowed: bool
    live_blocked: bool


class EquityForecastBatchSummary(TypedDict):
    artifact_type: str
    batch_version: str
    batch_status: str
    benchmark_symbol: str
    symbol_count: int
    distribution_available_count: int
    abstention_count: int
    negative_or_missing_mae_skill_count: int
    baseline_guardrail_count: int
    historical_option_evidence_consumed: bool
    edge_claimed: bool
    strategy_promotion_allowed: bool
    order_construction_allowed: bool
    live_blocked: bool
    records: list[EquityForecastArtifactRecord]
    reproducibility_hash: str


class ShortHorizonForecastRecord(TypedDict):
    horizon_trading_days: int
    forecast_status: str
    artifact_path: str
    artifact_sha256: str
    forecast_reproducibility_hash: str
    distribution_available: bool
    diagnostic_prediction_count: int
    observed_interval_coverage: float | None
    mae_skill_versus_beta_scaled_benchmark: float | None
    brier_skill_versus_beta_scaled_benchmark: float | None
    log_loss_skill_versus_beta_scaled_benchmark: float | None
    selected_point_forecast_method: str
    selected_point_forecast_price: float | None
    promotion_allowed: bool


class ShortHorizonForecastSuiteSummary(TypedDict):
    artifact_type: str
    suite_version: str
    suite_status: str
    symbol: str
    benchmark_symbol: str
    as_of_date: str
    horizon_count: int
    horizons_trading_days: list[int]
    distribution_available_count: int
    positive_mae_skill_count: int
    all_horizons_independently_scored: bool
    historical_option_evidence_consumed: bool
    option_payoff_edge_claimed: bool
    strategy_promotion_allowed: bool
    order_construction_allowed: bool
    paper_only: bool
    live_blocked: bool
    records: list[ShortHorizonForecastRecord]
    reproducibility_hash: str


def run_equity_distribution_forecast_artifact(
    symbol: str,
    benchmark_symbol: str,
    output_path: Path,
    policy: EquityForecastPolicy,
) -> EquityDistributionForecast:
    """Read governed histories and atomically write one non-promotional forecast."""
    forecast = build_default_equity_distribution_forecast(
        symbol,
        benchmark_symbol,
        policy,
    )
    _write_json_atomic(output_path, forecast)
    return forecast


def build_default_equity_distribution_forecast(
    symbol: str,
    benchmark_symbol: str,
    policy: EquityForecastPolicy,
) -> EquityDistributionForecast:
    """Build one forecast from hash-pinned governed histories without writing."""
    subject_rows, subject_proof = load_default_validated_symbol_history(symbol)
    benchmark_rows, benchmark_proof = load_default_validated_symbol_history(
        benchmark_symbol
    )
    as_of_date = min(subject_rows[-1]["date"], benchmark_rows[-1]["date"])
    subject_slice_sha256 = _as_of_slice_sha256(subject_rows, as_of_date)
    benchmark_slice_sha256 = _as_of_slice_sha256(benchmark_rows, as_of_date)
    forecast = build_equity_distribution_forecast(
        symbol,
        cast(list[EquityPriceBar], subject_rows),
        subject_slice_sha256,
        benchmark_symbol,
        cast(list[EquityPriceBar], benchmark_rows),
        benchmark_slice_sha256,
        as_of_date,
        policy,
    )
    if not subject_proof["actual_sha256"] or not benchmark_proof["actual_sha256"]:
        raise ValueError("governed history proofs require non-empty full-file hashes")
    return forecast


def _as_of_slice_sha256(rows: list[dict[str, object]], as_of_date: str) -> str:
    selected = [
        {
            "date": str(row["date"]),
            "close": float(row["close"]),
            "adjusted_close": float(row["adjusted_close"]),
            "volume": int(row["volume"]),
        }
        for row in rows
        if str(row["date"]) <= as_of_date
    ]
    if not selected or selected[-1]["date"] != as_of_date:
        raise ValueError(
            "governed history does not contain the declared as-of date: "
            f"as_of_date={as_of_date}, selected_count={len(selected)}"
        )
    return hashlib.sha256(
        json.dumps(
            selected,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def run_equity_distribution_forecast_batch(
    symbols: tuple[str, ...],
    benchmark_symbol: str,
    output_root: Path,
    policy: EquityForecastPolicy,
) -> EquityForecastBatchSummary:
    """Publish one complete research batch; the manifest is the completion marker."""
    normalized_symbols = tuple(symbol.strip().upper() for symbol in symbols)
    if not normalized_symbols or any(not symbol for symbol in normalized_symbols):
        raise ValueError("equity forecast batch requires non-empty symbols")
    if len(set(normalized_symbols)) != len(normalized_symbols):
        raise ValueError(
            f"equity forecast batch symbols must be unique: symbols={normalized_symbols}"
        )
    forecasts = [
        build_default_equity_distribution_forecast(
            symbol,
            benchmark_symbol,
            policy,
        )
        for symbol in normalized_symbols
    ]
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[EquityForecastArtifactRecord] = []
    for forecast in forecasts:
        symbol = str(forecast["symbol"])
        artifact_path = output_root / f"{symbol}_distribution.json"
        _write_json_atomic(artifact_path, forecast)
        diagnostics = forecast["prequential_diagnostics"]
        guardrail = forecast["point_forecast_guardrail"]
        records.append(
            {
                "symbol": symbol,
                "forecast_status": str(forecast["forecast_status"]),
                "as_of_date": str(forecast["as_of_date"]),
                "artifact_path": artifact_path.relative_to(output_root).as_posix(),
                "artifact_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
                "forecast_reproducibility_hash": str(
                    forecast["reproducibility_hash"]
                ),
                "distribution_available": forecast["price_distribution"] is not None,
                "diagnostics_status": str(diagnostics["diagnostic_status"]),
                "observed_interval_coverage": diagnostics[
                    "observed_interval_coverage"
                ],
                "mae_skill_versus_beta_scaled_benchmark": diagnostics[
                    "mae_skill_vs_beta_scaled_benchmark"
                ],
                "selected_point_forecast_method": str(
                    guardrail["selected_method"]
                ),
                "selected_point_forecast_price": guardrail["selected_price"],
                "strategy_promotion_allowed": forecast[
                    "strategy_promotion_allowed"
                ],
                "order_construction_allowed": forecast[
                    "order_construction_allowed"
                ],
                "live_blocked": forecast["live_blocked"],
            }
        )
    summary_body: dict[str, Any] = {
        "artifact_type": "equity_distribution_forecast_batch_summary",
        "batch_version": "dopey-equity-distribution-forecast-batch-v3",
        "batch_status": "research_batch_complete_no_edge_or_live_claim",
        "benchmark_symbol": benchmark_symbol.strip().upper(),
        "symbol_count": len(records),
        "distribution_available_count": sum(
            record["distribution_available"] for record in records
        ),
        "abstention_count": sum(
            record["forecast_status"].startswith("abstain_") for record in records
        ),
        "negative_or_missing_mae_skill_count": sum(
            record["mae_skill_versus_beta_scaled_benchmark"] is None
            or float(record["mae_skill_versus_beta_scaled_benchmark"]) <= 0.0
            for record in records
        ),
        "baseline_guardrail_count": sum(
            record["selected_point_forecast_method"]
            == "beta_scaled_benchmark_baseline_median"
            for record in records
        ),
        "historical_option_evidence_consumed": False,
        "edge_claimed": False,
        "strategy_promotion_allowed": False,
        "order_construction_allowed": False,
        "live_blocked": True,
        "records": records,
    }
    summary: EquityForecastBatchSummary = {
        **summary_body,
        "reproducibility_hash": hashlib.sha256(
            json.dumps(
                summary_body,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest(),
    }
    _write_json_payload_atomic(output_root / "batch_summary.json", summary)
    return summary


def run_short_horizon_equity_distribution_suite(
    symbol: str,
    benchmark_symbol: str,
    output_root: Path,
) -> ShortHorizonForecastSuiteSummary:
    """Publish independently scored one-to-five-session equity forecasts."""
    normalized_symbol = symbol.strip().upper()
    normalized_benchmark = benchmark_symbol.strip().upper()
    if not normalized_symbol or not normalized_benchmark:
        raise ValueError(
            "short-horizon forecast suite requires symbol and benchmark"
        )
    forecasts = [
        build_default_equity_distribution_forecast(
            normalized_symbol,
            normalized_benchmark,
            short_horizon_equity_forecast_policy(horizon),
        )
        for horizon in range(1, 6)
    ]
    as_of_dates = {str(forecast["as_of_date"]) for forecast in forecasts}
    if len(as_of_dates) != 1:
        raise ValueError(
            "short-horizon forecasts do not share one market frontier: "
            f"as_of_dates={sorted(as_of_dates)}"
        )
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[ShortHorizonForecastRecord] = []
    for forecast in forecasts:
        horizon = int(forecast["horizon_trading_days"])
        artifact_path = output_root / f"{normalized_symbol}_{horizon}td.json"
        _write_json_atomic(artifact_path, forecast)
        diagnostics = forecast["prequential_diagnostics"]
        guardrail = forecast["point_forecast_guardrail"]
        records.append(
            {
                "horizon_trading_days": horizon,
                "forecast_status": str(forecast["forecast_status"]),
                "artifact_path": artifact_path.relative_to(output_root).as_posix(),
                "artifact_sha256": hashlib.sha256(
                    artifact_path.read_bytes()
                ).hexdigest(),
                "forecast_reproducibility_hash": str(
                    forecast["reproducibility_hash"]
                ),
                "distribution_available": forecast["price_distribution"] is not None,
                "diagnostic_prediction_count": int(
                    diagnostics["prediction_count"]
                ),
                "observed_interval_coverage": diagnostics[
                    "observed_interval_coverage"
                ],
                "mae_skill_versus_beta_scaled_benchmark": diagnostics[
                    "mae_skill_vs_beta_scaled_benchmark"
                ],
                "brier_skill_versus_beta_scaled_benchmark": diagnostics[
                    "brier_skill_vs_beta_scaled_benchmark"
                ],
                "log_loss_skill_versus_beta_scaled_benchmark": diagnostics[
                    "log_loss_skill_vs_beta_scaled_benchmark"
                ],
                "selected_point_forecast_method": str(
                    guardrail["selected_method"]
                ),
                "selected_point_forecast_price": guardrail["selected_price"],
                "promotion_allowed": forecast["strategy_promotion_allowed"],
            }
        )
    summary_body: dict[str, Any] = {
        "artifact_type": "short_horizon_equity_distribution_forecast_suite",
        "suite_version": "dopey-short-horizon-equity-forecast-suite-v1",
        "suite_status": "research_complete_no_option_edge_or_live_claim",
        "symbol": normalized_symbol,
        "benchmark_symbol": normalized_benchmark,
        "as_of_date": next(iter(as_of_dates)),
        "horizon_count": len(records),
        "horizons_trading_days": [
            record["horizon_trading_days"] for record in records
        ],
        "distribution_available_count": sum(
            record["distribution_available"] for record in records
        ),
        "positive_mae_skill_count": sum(
            record["mae_skill_versus_beta_scaled_benchmark"] is not None
            and float(record["mae_skill_versus_beta_scaled_benchmark"]) > 0.0
            for record in records
        ),
        "all_horizons_independently_scored": True,
        "historical_option_evidence_consumed": False,
        "option_payoff_edge_claimed": False,
        "strategy_promotion_allowed": False,
        "order_construction_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "records": records,
    }
    summary: ShortHorizonForecastSuiteSummary = {
        **summary_body,
        "reproducibility_hash": hashlib.sha256(
            json.dumps(
                summary_body,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest(),
    }
    _write_json_payload_atomic(output_root / "short_horizon_summary.json", summary)
    return summary


def _write_json_atomic(
    output_path: Path,
    forecast: EquityDistributionForecast,
) -> None:
    _write_json_payload_atomic(output_path, forecast)


def _write_json_payload_atomic(
    output_path: Path,
    payload: dict[str, Any],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, output_path)
