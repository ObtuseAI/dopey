"""Pre-Snap Read + Audible - diagnose the live look, protect the football.

An AVOID-graded look must audible to no-trade; a contested family checks to
research-only; an edge below the cost line audibles to no-trade; a favorable
corroborated-and-survives look proceeds to monitor; and an UNCERTAIN look
defaults to the safe call (throw it away). Measure-only.
"""
from __future__ import annotations

from datetime import date, timedelta

from dopey.strategy_engineering.pre_snap_read import (
    build_pre_snap_reads,
    diagnose_pre_snap_read,
)


def _spine(stretched: bool) -> dict[str, tuple[list[float], list[str]]]:
    closes = [100.0] * 30
    dates = [(date(2020, 1, 1) + timedelta(days=i)).isoformat() for i in range(31)]
    closes.append(112.0 if stretched else 100.5)
    return {"NVDA": (closes, dates)}


def _scorecard(call: str, family: str = "momentum", context: str = "stretched_above"):
    return {"situations": [{"family": family, "entry_context": context, "call": call}]}


def _convergence(verdict: str, sign: str = "positive", survives=None):
    return {"families": [{
        "family": "momentum_continuation", "verdict": verdict, "consensus_sign": sign,
        "option_cost_annotation": {"survives_long_option_costs": survives},
    }]}


def _candidate():
    return {"symbol": "NVDA", "family": "momentum", "direction": "bullish"}


def test_avoid_look_audibles_to_no_trade() -> None:
    read = diagnose_pre_snap_read(
        _candidate(), _spine(stretched=True), _scorecard("avoid_strong"),
        _convergence("corroborated"), {}, "2020-01-31",
    )
    assert read["look"]["entry_context"] == "stretched_above"
    assert read["audible"] == "audible_to_no_trade"
    assert read["read"] == "unfavorable"


def test_contested_family_checks_research_only() -> None:
    read = diagnose_pre_snap_read(
        _candidate(), _spine(stretched=False), _scorecard("neutral_monitor", context="near"),
        _convergence("contested_lanes_disagree", sign="mixed"), {}, "2020-01-31",
    )
    assert read["audible"] == "check_research_only"


def test_edge_below_cost_line_audibles_to_no_trade() -> None:
    read = diagnose_pre_snap_read(
        _candidate(), _spine(stretched=False), _scorecard("no_tradeable_edge", context="near"),
        _convergence("corroborated", survives=False), {}, "2020-01-31",
    )
    assert read["audible"] == "audible_to_no_trade"
    assert read["read"] == "edge_below_cost_line"


def test_favorable_look_proceeds_to_monitor() -> None:
    read = diagnose_pre_snap_read(
        _candidate(), _spine(stretched=False), _scorecard("monitor_candidate", context="near"),
        _convergence("corroborated", survives=True), {}, "2020-01-31",
    )
    assert read["audible"] == "proceed_monitor"
    assert read["read"] == "favorable"


def test_uncertain_look_defaults_to_safe_call() -> None:
    # no convergence mapping, non-avoid scorecard -> protect the football
    read = diagnose_pre_snap_read(
        {"symbol": "NVDA", "family": "market_regime", "direction": "bullish"},
        _spine(stretched=False), _scorecard("neutral_monitor", family="market_regime", context="near"),
        {"families": []}, {}, "2020-01-31",
    )
    assert read["audible"] == "check_down_default_no_trade"


def test_unknown_symbol_cannot_read_the_look() -> None:
    read = diagnose_pre_snap_read(
        {"symbol": "ZZZ", "family": "momentum", "direction": "bullish"},
        _spine(stretched=False), _scorecard("avoid"), _convergence("corroborated"), {}, "2020-01-31",
    )
    assert read["audible"] == "check_insufficient_look"
    assert read["look"]["entry_context"] == "unknown"


def test_batch_counts_no_trade_audibles_and_is_measure_only() -> None:
    candidates = [
        {"symbol": "NVDA", "family": "momentum", "direction": "bullish"},
    ]
    result = build_pre_snap_reads(
        candidates, _spine(stretched=True), _scorecard("avoid_strong"),
        _convergence("corroborated"), {}, "2020-01-31",
    )
    assert result["no_trade_audibles"] >= 1
    assert result["promotion_allowed"] is False
    assert "protect the football" in result["coaching_principle"]
