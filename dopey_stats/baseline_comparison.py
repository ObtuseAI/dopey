"""Diagnostic-only baseline comparisons for model-unit backtest outputs."""
from __future__ import annotations

from typing import Any

from .statistical_truth_models import BaselineComparison


def build_baseline_comparisons(metric_set: dict[str, Any], trade_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observed = round(float(metric_set.get("average_model_unit_pnl", 0.0)), 6)
    pnl_values = [round(float(record.get("path_pnl", 0.0)), 6) for record in trade_records]
    call_values = [round(float(record.get("path_pnl", 0.0)), 6) for record in trade_records if record.get("candidate_strategy") == "long_call"]
    put_values = [round(float(record.get("path_pnl", 0.0)), 6) for record in trade_records if record.get("candidate_strategy") == "long_put"]
    shuffled_values = list(reversed(pnl_values))
    baselines = [
        ("zero_return_baseline", 0.0),
        ("random_direction_fixture_baseline", round(-observed, 6)),
        ("always_long_call_model_baseline", _average(call_values)),
        ("always_long_put_model_baseline", _average(put_values)),
        ("no_trade_baseline", 0.0),
        ("shuffled_signal_baseline", _average(shuffled_values)),
    ]
    records: list[dict[str, Any]] = []
    for name, baseline_value in baselines:
        comparison = BaselineComparison(
            artifact_type="baseline_comparison",
            statistical_truth_version="",
            baseline_name=name,
            sample_count=len(pnl_values),
            tested_metric="average_model_unit_pnl",
            observed_value=observed,
            baseline_value=baseline_value,
            delta=round(observed - baseline_value, 6),
            diagnostic_only=True,
            real_evidence=False,
            superiority_claim_allowed=False,
            paper_only=True,
            live_blocked=True,
            not_real_statistical_evidence=True,
            comparison_hash="",
        )
        records.append(comparison.to_dict())
    return records


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0
