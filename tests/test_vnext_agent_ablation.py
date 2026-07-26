"""Stable forward-counterfactual fixtures for protected agent ablation."""

from __future__ import annotations

from dopey.truth.agent_ablation import evaluate_agent_ablation


def test_agent_ablation_validates_helpful_agent_and_recommends_harmful_retirement() -> None:
    predictions = []
    settlements = []
    symbols = ("SPY", "QQQ", "IWM", "DIA")
    for index in range(40):
        prediction_id = f"prediction-{index}"
        realized = "bull" if index % 2 == 0 else "bear"
        full = (
            {"bull": 0.7, "bear": 0.1, "neutral": 0.1, "unknown": 0.1}
            if realized == "bull"
            else {"bull": 0.1, "bear": 0.7, "neutral": 0.1, "unknown": 0.1}
        )
        harmful_ablation = (
            {"bull": 0.8, "bear": 0.05, "neutral": 0.1, "unknown": 0.05}
            if realized == "bull"
            else {"bull": 0.05, "bear": 0.8, "neutral": 0.1, "unknown": 0.05}
        )
        predictions.append(
            {
                "prediction_id": prediction_id,
                "symbol": symbols[index % len(symbols)],
                "hypotheses": full,
                "agent_ablation_precommitted_before_outcome": True,
                "agent_ablation_hypotheses": {
                    "helpful_agent": {"bull": 0.25, "bear": 0.25, "neutral": 0.25, "unknown": 0.25},
                    "harmful_agent": harmful_ablation,
                },
            }
        )
        settlements.append(
            {
                "prediction_id": prediction_id,
                "symbol": symbols[index % len(symbols)],
                "settlement_status": "settled_forward_outcome",
                "actual_settlement_date": f"2026-09-{index % 28 + 1:02d}",
                "realized_class": realized,
                "contested_truth": index % 9 == 0,
            }
        )

    result = evaluate_agent_ablation(predictions, settlements, 500, 17, 0.05, 30, 3)
    by_agent = {record["agent_id"]: record for record in result["evaluations"]}

    assert result["evaluation_status"] == "forward_ablation_evaluated"
    assert by_agent["helpful_agent"]["agent_contribution_validated"] is True
    assert by_agent["harmful_agent"]["retirement_recommended"] is True
    assert result["automatic_retirement_count"] == 1
    assert result["automatic_validation_transition_count"] == 1
    assert result["automatic_promotion_count"] == 0
    assert by_agent["helpful_agent"]["human_review_required"] is False
    assert by_agent["harmful_agent"]["auto_applied"] is True
