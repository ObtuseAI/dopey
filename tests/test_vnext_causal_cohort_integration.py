"""Integration coverage for canonical cohort routing and causal evaluation."""

from __future__ import annotations

from dopey.truth.causal_evaluation import evaluate_causal_cohorts
from dopey.truth.cohorts import canonicalize_evaluation_records


def test_causal_evaluation_preserves_children_and_blocks_weak_promotion() -> None:
    source = [
        {
            "child_id": f"prediction-{index}",
            "strategy_id": f"breakout-v{index % 3}",
            "setup_family": "volatility_squeeze_breakout",
            "exit_policy": "swing_exit",
            "dte_bucket": 14,
            "moneyness_bucket": "ATM",
            "direction": "bullish",
            "regime": "low_volatility" if index % 2 == 0 else "normal_volatility",
            "symbol": ("SPY", "QQQ", "IWM", "DIA")[index % 4],
            "era": "validation" if index < 20 else "held_out",
            "signal_value": 1.0 if index % 3 else -1.0,
            "outcome_value": 0.02 if index % 3 else -0.015,
            "baseline_value": 0.001,
            "held_out": True,
            "contested_truth": index % 11 == 0,
        }
        for index in range(40)
    ]
    canonical = canonicalize_evaluation_records(source)
    result = evaluate_causal_cohorts(canonical, 300, 20260714, 20, 0.05, 100)

    assert result["record_count"] == 40
    assert result["cohort_count"] == 1
    assert result["any_cohort_regime_robust"] is False
    assert result["statistical_truth_promotion_allowed"] is False
    evaluation = result["evaluations"][0]
    assert evaluation["sample_count"] == 40
    assert len(evaluation["child_ids"]) == 40
    assert evaluation["promotion_recommendation"] == "SHADOW_ONLY"
    assert evaluation["automatic_promotion_allowed"] is False
    assert evaluation["held_out"] is True
