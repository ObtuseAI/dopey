"""Option-expression cost: does an underlying edge survive as a long option?

A long ATM option pays half-spread + slippage + commission on both sides AND
theta over the horizon, so a small correct move loses. The breakeven move must
be positive and rise with IV; a tiny excess must fail; a large move must pass.
"""
from __future__ import annotations

from dopey.strategy_engineering.option_expression_cost import (
    breakeven_move,
    net_return_for_move,
    survives_option_costs,
)


def test_breakeven_is_positive_and_rises_with_iv() -> None:
    low = breakeven_move(iv=0.20)
    mid = breakeven_move(iv=0.30)
    high = breakeven_move(iv=0.45)
    assert 0.0 < low < mid < high  # higher IV -> pricier option -> larger move needed


def test_small_correct_move_loses() -> None:
    # a +0.6% underlying move over 5 days on a 30DTE ATM option
    net = net_return_for_move(0.006, iv=0.30)
    assert net < 0.0


def test_large_move_wins() -> None:
    net = net_return_for_move(0.10, iv=0.30)
    assert net > 0.0


def test_zero_move_loses_the_full_tax() -> None:
    # no move: you pay round-trip spread + slippage + commission + 5 days theta
    assert net_return_for_move(0.0, iv=0.30) < -0.05


def test_survives_verdict_matches_breakeven() -> None:
    be = breakeven_move(iv=0.30)
    below = survives_option_costs(be * 0.5, iv=0.30)
    above = survives_option_costs(be * 1.5, iv=0.30)
    assert below["survives_long_option_costs"] is False
    assert above["survives_long_option_costs"] is True
    assert below["promotion_allowed"] is False


def test_mean_reversion_lead_does_not_survive() -> None:
    # this session's corroborated mean-reversion excess (+0.62% underlying)
    verdict = survives_option_costs(0.00616, iv=0.30)
    assert verdict["survives_long_option_costs"] is False
    assert verdict["breakeven_underlying_move"] > 0.00616
