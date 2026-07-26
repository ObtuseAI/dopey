"""Integration invariants for the DOPEY CRR validation oracle."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dopey_options.binomial_oracle import (
    cash_dividend,
    defined_risk_vertical_bounds,
    price_binomial_option,
    run_binomial_oracle_validation,
)


def test_binomial_oracle_validates_american_exercise_and_separation(tmp_path: Path) -> None:
    output = tmp_path / "binomial_oracle_validation.json"
    result = run_binomial_oracle_validation(output)
    stored = json.loads(output.read_text(encoding="utf-8"))

    assert result["validation_status"] == "complete"
    assert result["passed_test_count"] == result["test_count"]
    assert result["fixtures"]["american_put"]["model_price"] >= result["fixtures"]["european_put"]["model_price"]
    assert result["fixtures"]["american_put"]["early_exercise_node_count"] > 0
    assert result["fixtures"]["discrete_dividend_american_call"]["cash_dividend_method"] == "exact_nonrecombining_path_tree"
    assert stored["separation_law"]["execution_fill_simulator"] == "not_substituted"
    assert stored["promotion_allowed"] is False


def test_binomial_oracle_rejects_cash_dividend_state_explosion() -> None:
    with pytest.raises(ValueError, match="node budget"):
        price_binomial_option("call", "american", 100.0, 100.0, 1.0, 0.05, 0.0, 0.2, 19, (cash_dividend(0.5, 1.0),))


def test_defined_risk_vertical_bounds_are_capped() -> None:
    bounds = defined_risk_vertical_bounds("call", 100.0, 110.0, 6.0, 2.0)

    assert bounds["maximum_loss"] == 4.0
    assert bounds["maximum_profit"] == 6.0
    assert bounds["loss_is_capped"] is True
