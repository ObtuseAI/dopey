from __future__ import annotations

from pathlib import Path

from dopey_symbol_lab.lab import build_symbol_lab_state


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def test_real_spy_symbol_lab_composes_strategy_and_option_evidence() -> None:
    first = build_symbol_lab_state(
        REPOSITORY_ROOT,
        "SPY",
        "trend",
        760.0,
        14,
        0.0,
    )
    second = build_symbol_lab_state(
        REPOSITORY_ROOT,
        "SPY",
        "trend",
        760.0,
        14,
        0.0,
    )

    assert first["content_hash"] == second["content_hash"]
    assert first["synthetic_data_used"] is False
    assert first["paper_only"] is True
    assert first["live_blocked"] is True
    assert first["promotion_allowed"] is False

    strategy = first["strategy_research"]
    assert isinstance(strategy, dict)
    assert strategy["recipe_trial_count"] == 12
    assert strategy["multiple_testing_policy"]
    assert strategy["historical_testing_is_not_forward_proof"] is True
    assert all(record["promotion_allowed"] is False for record in strategy["strategy_results"])
    assert all("selection_adjusted_mean" in record for record in strategy["strategy_results"])

    options = first["options_value_lab"]
    assert isinstance(options, dict)
    assert options["projector_status"] == "complete_scenario_research"
    assert options["eligible_contract_count"] > 0
    assert options["best_expression"] is not None
    assert options["future_values_are_model_projections_not_quotes"] is True
    assert options["profitability_claim_allowed"] is False
    assert len(options["scenario_surface"]) >= 9

    market = first["market_profile"]
    assert isinstance(market, dict)
    assert market["nearest_support"] is not None
    assert market["nearest_resistance"] is not None
    assert market["options_chain"]["quote_derived"] is True
    assert market["earnings"]["status"]
