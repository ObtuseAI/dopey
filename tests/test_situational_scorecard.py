"""Situational Scorecard - the championship call sheet, measure-only.

Discipline first: a negative-expectancy context is AVOID; a corroborated
underlying edge that dies at option costs is no_tradeable_edge (never a trade);
a contested family is research_only. There is no TRADE call at L0 - the best
available is monitor_candidate, and only when a finding survives option costs.
"""
from __future__ import annotations

from dopey.strategy_engineering.situational_scorecard import build_situational_scorecard
from dopey.strategy_engineering.trade_memory import MEMORY_VERSION


def _memory(family_buckets):
    return {
        "memory_version": MEMORY_VERSION,
        "per_family": {
            family: {"conditional_by_stretch": buckets}
            for family, buckets in family_buckets.items()
        },
    }


def _bucket(mean, count=1000, win=0.35):
    return {
        "mean_trade_return_model_units": mean,
        "count": count,
        "win_rate": win,
    }


def _convergence(families):
    return {"families": families}


def test_worst_negative_context_is_avoid_strong() -> None:
    memory = _memory({"momentum": {
        "stretched_above": _bucket(-1.2),
        "near": _bucket(-0.1),
    }})
    card = build_situational_scorecard(memory, _convergence([]), {})
    worst = next(s for s in card["situations"] if s["entry_context"] == "stretched_above")
    assert worst["call"] == "avoid_strong"
    assert worst["is_worst_context_for_family"] is True


def test_moderate_negative_is_avoid() -> None:
    memory = _memory({"momentum": {"below": _bucket(-0.7), "near": _bucket(-1.5)}})
    card = build_situational_scorecard(memory, _convergence([]), {})
    below = next(s for s in card["situations"] if s["entry_context"] == "below")
    assert below["call"] == "avoid"  # negative but not the worst bucket


def test_corroborated_but_cost_failing_is_no_tradeable_edge() -> None:
    memory = _memory({"trend_pullback": {"near": _bucket(0.05)}})  # non-negative context
    convergence = _convergence([{
        "family": "mean_reversion", "verdict": "corroborated", "consensus_sign": "positive",
        "option_cost_annotation": {"survives_long_option_costs": False},
    }])
    card = build_situational_scorecard(memory, convergence, {})
    call = card["situations"][0]
    assert call["call"] == "no_tradeable_edge"


def test_corroborated_and_survives_is_monitor_candidate() -> None:
    memory = _memory({"trend_pullback": {"near": _bucket(0.05)}})
    convergence = _convergence([{
        "family": "mean_reversion", "verdict": "corroborated", "consensus_sign": "positive",
        "option_cost_annotation": {"survives_long_option_costs": True},
    }])
    card = build_situational_scorecard(memory, convergence, {})
    assert card["situations"][0]["call"] == "monitor_candidate"
    assert card["monitor_candidates"]


def test_contested_family_is_research_only() -> None:
    memory = _memory({"momentum": {"near": _bucket(0.02)}})
    convergence = _convergence([{"family": "momentum_continuation", "verdict": "contested_lanes_disagree", "consensus_sign": "mixed"}])
    card = build_situational_scorecard(memory, convergence, {})
    assert card["situations"][0]["call"] == "contested_research_only"


def test_thin_context_excluded() -> None:
    memory = _memory({"momentum": {"near": _bucket(-2.0, count=10)}})  # below the 200 floor
    card = build_situational_scorecard(memory, _convergence([]), {})
    assert card["situations"] == []


def test_current_market_situation_reads_regime() -> None:
    macro = {
        "vol_term_structure": {"VIX": 16.6, "VIX3M": 19.5},
        "liquidity_impulse": {"impulse_4w_pct": 0.024},
    }
    card = build_situational_scorecard(_memory({}), _convergence([]), macro)
    situation = card["current_market_situation"]
    assert situation["vix_term_structure"] == "contango_calm"
    assert situation["liquidity_state"] == "flooding"


def test_scorecard_is_measure_only_with_avoid_headline() -> None:
    memory = _memory({"fakeout": {"stretched_above": _bucket(-3.1), "near": _bucket(-0.3)}})
    card = build_situational_scorecard(memory, _convergence([]), {})
    assert card["promotion_allowed"] is False
    assert card["not_edge_evidence"] is True
    assert "AVOID" in card["headline"]
    assert "eliminating the negative plays" in card["coaching_principle"]


def test_stale_trade_memory_version_fails_closed() -> None:
    memory = _memory({"momentum": {"near": _bucket(-1.0)}})
    memory["memory_version"] = "dopey-trade-memory-v1"

    card = build_situational_scorecard(memory, _convergence([]), {})

    assert card["situations"] == []
    assert (
        card["trade_memory_evidence_status"]
        == "blocked_incompatible_trade_memory_version"
    )
    assert "rebuild required" in card["headline"]
