"""Tests for the V21-adaptable builds + V22 evolution fitness pieces.

Pure-function level: no live artifact IO (module runners are exercised by the
supervisor and the soak harness; these tests pin the decision logic)."""
from __future__ import annotations

import math

from dopey_analysis.trade_loss_coach import classify_closed_trade
from dopey_risk_engine.adversarial_signal_panel import build_panel_record
from dopey_risk_engine.exit_playbook import build_position_playbook
from dopey_risk_engine.market_simulation_engine import SCENARIO_CLASSES, run_named_scenarios

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "operator_evolve_fitness",
    Path(__file__).resolve().parent.parent / "operator_tools" / "operator_evolve_fitness.py",
)
_fitness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fitness)


POSITION = {
    "position_id": "fw-TEST-long_call-2026-07-09-00",
    "symbol": "TEST",
    "candidate_strategy": "long_call",
    "option_type": "call",
    "strike": 100.0,
    "expiry": "2026-08-07",
    "entry_date": "2026-07-09",
    "signal_date": "2026-07-02",
    "signal_family": "momentum",
    "entry_spot": 100.0,
    "entry_iv": 0.30,
    "entry_fill": 3.0,
    "marking_sessions": 0,
}


# ---------- exit playbook ----------

def test_playbook_trigger_geometry_call() -> None:
    book = build_position_playbook(dict(POSITION), risk_free=0.04)
    flat = next(s for s in book["scenarios"] if s["iv_scenario"] == "iv_flat_x1.0")
    stop, target = flat["stop_trigger_spot"], flat["target_trigger_spot"]
    assert stop is not None and target is not None
    # long call: stop must sit BELOW spot, target ABOVE
    assert stop < POSITION["entry_spot"] < target


def test_playbook_grid_actions_monotone_for_call() -> None:
    book = build_position_playbook(dict(POSITION), risk_free=0.04)
    flat = next(s for s in book["scenarios"] if s["iv_scenario"] == "iv_flat_x1.0")
    actions = [cell["action"] for cell in flat["grid"]]
    returns = [cell["mark_return"] for cell in flat["grid"]]
    assert returns == sorted(returns)  # call value rises with spot
    assert "discipline_closes_premium_stop" not in actions[-1]


def test_playbook_reports_pinned_discipline() -> None:
    book = build_position_playbook(dict(POSITION), risk_free=0.04)
    assert book["sessions_until_time_stop"] == 3


# ---------- named scenarios ----------

def test_named_scenarios_deterministic_and_complete() -> None:
    returns = {"TEST": [0.01, -0.02, 0.005, -0.01, 0.015] * 10}
    a = run_named_scenarios([dict(POSITION)], returns, risk_free=0.04)
    b = run_named_scenarios([dict(POSITION)], returns, risk_free=0.04)
    assert a == b
    assert [row["scenario"] for row in a] == [s["name"] for s in SCENARIO_CLASSES]
    assert all(len(row["worst_positions"]) <= 3 for row in a)


def test_vol_crush_hurts_long_premium_at_flat_spot() -> None:
    returns = {"TEST": [0.01, -0.02, 0.005, -0.01, 0.015] * 10}
    rows = {row["scenario"]: row for row in run_named_scenarios([dict(POSITION)], returns, 0.04)}
    assert rows["vol_crush_no_move"]["book_pnl_premium_units"] < 0
    assert rows["vol_spike_no_move"]["book_pnl_premium_units"] > rows["vol_crush_no_move"]["book_pnl_premium_units"]


# ---------- adversarial panel ----------

def _clean_context() -> dict:
    return {
        "long_call_entry_bias": "favorable",
        "sector_regime": "leading",
        "gamma_regime": "long_gamma_dampening",
        "crowd_state": "balanced",
        "earnings_blackout": False,
        "surface_tear_present": False,
    }


def test_panel_clean_context_proceeds() -> None:
    record = build_panel_record(dict(POSITION), _clean_context(), {}, {})
    assert record["panel_verdict_recorded_not_enforced"] == "would_proceed"
    assert record["risk_lens"]["kelly_ceiling"]["kelly_fraction_ceiling"] == 0.0


def test_panel_earnings_blackout_refuses() -> None:
    context = _clean_context()
    context["earnings_blackout"] = True
    record = build_panel_record(dict(POSITION), context, {}, {})
    assert record["panel_verdict_recorded_not_enforced"] == "would_refuse"
    assert "earnings_blackout_window" in record["bear_lens"]["flags"]


def test_panel_crowded_attention_flags() -> None:
    macro = {"attention": {"crowded_symbols": ["TEST"]}}
    record = build_panel_record(dict(POSITION), _clean_context(), macro, {})
    assert "crowded_attention" in record["bear_lens"]["flags"]


def test_panel_concentration_refuses() -> None:
    book = {"premium_at_risk_by_symbol": {"TEST": 40.0, "OTHER": 60.0}}
    record = build_panel_record(dict(POSITION), _clean_context(), {}, book)
    assert record["panel_verdict_recorded_not_enforced"] == "would_refuse"
    assert record["risk_lens"]["symbol_premium_share"] == 0.4


# ---------- trade loss coach ----------

def test_coach_classification_taxonomy() -> None:
    assert classify_closed_trade({"close_reason": "premium_target", "trade_return": 1.0}) == "winner"
    assert classify_closed_trade({"close_reason": "premium_stop", "trade_return": -0.55}) == "adverse_move_stop"
    assert classify_closed_trade({"close_reason": "time_stop", "trade_return": -0.04}) == "friction_scratch"
    assert classify_closed_trade({"close_reason": "time_stop", "trade_return": -0.25}) == "theta_bleed"
    assert classify_closed_trade({"close_reason": "expiry_intrinsic", "trade_return": -1.0}) == "expired_worthless"
    assert classify_closed_trade({
        "exit_reason": "premium_stop",
        "trade_return": -0.70,
        "exit_relative_spread": 1.20,
    }) == "liquidity_hole_stop"


# ---------- evolution fitness pieces ----------

def test_fitness_dedupes_family_fanout() -> None:
    records = [
        {"symbol": "A", "signal_date": "2024-01-02", "candidate_strategy": "long_call", "trade_return_model_units": 0.1},
        {"symbol": "A", "signal_date": "2024-01-02", "candidate_strategy": "long_call", "trade_return_model_units": 0.1},
        {"symbol": "A", "signal_date": "2024-01-02", "candidate_strategy": "long_put", "trade_return_model_units": -0.1},
    ]
    unique = _fitness.unique_directional_paths(records)
    assert len(unique) == 2


def test_fitness_era_split_convention() -> None:
    records = [
        {"signal_date": "2021-12-31"},
        {"signal_date": "2022-01-03"},
    ]
    train, holdout = _fitness.split_by_era(records)
    assert len(train) == 1 and len(holdout) == 1


def test_fitness_sample_floors_zero_the_score() -> None:
    thin = [
        {"symbol": "A", "signal_date": f"2024-01-{d:02d}", "candidate_strategy": "long_call", "trade_return_model_units": 0.5}
        for d in range(1, 10)
    ]
    scored = _fitness.score_holdout(thin)
    assert scored["score_psr"] == 0.0
    assert scored["floor_reason"]


def test_fitness_sharpe_like_basic() -> None:
    assert _fitness.sharpe_like([0.1, 0.1, 0.1]) == 0.0  # zero variance -> 0
    positive = _fitness.sharpe_like([0.02, 0.01, 0.03, 0.015])
    assert positive > 0
    assert math.isclose(_fitness.sharpe_like([-0.02, -0.01, -0.03, -0.015]), -positive, rel_tol=1e-9)


def test_fitness_daily_series_equal_weights_dates() -> None:
    records = [
        {"signal_date": "2024-01-02", "trade_return_model_units": 0.2},
        {"signal_date": "2024-01-02", "trade_return_model_units": 0.0},
        {"signal_date": "2024-01-03", "trade_return_model_units": -0.1},
    ]
    series = _fitness.daily_return_series(records)
    assert series == [("2024-01-02", 0.1), ("2024-01-03", -0.1)]


# ---------- fundamentals screen (V24 put-side lane) ----------

from dopey_market_intake.macro_context_gate import fundamentals_flags, fundamentals_state


def _fund_row(**overrides) -> dict:
    row = {
        "date": "2026-07-10", "symbol": "TEST", "theme": "ai", "in_universe": "0",
        "market_cap": "5e9", "trailing_pe": "", "forward_pe": "", "price_to_sales": "",
        "price_to_book": "", "profit_margin": "", "revenue_growth": "",
        "free_cashflow": "", "total_debt": "", "total_cash": "",
    }
    row.update({k: str(v) for k, v in overrides.items()})
    return row


def test_fundamentals_flags_speculative_garbage_scores_high() -> None:
    row = _fund_row(profit_margin=-0.55, price_to_sales=32, price_to_book=22, free_cashflow=-2e8)
    flags = fundamentals_flags(row)
    # no earnings + extreme P/S + extreme P/B + deeply unprofitable + burning cash
    assert len(flags) == 5


def test_fundamentals_flags_blue_chip_scores_zero() -> None:
    row = _fund_row(trailing_pe=28, price_to_sales=7, price_to_book=9, profit_margin=0.25, free_cashflow=9e10)
    assert fundamentals_flags(row) == []


def test_fundamentals_flags_triple_digit_pe_flags() -> None:
    row = _fund_row(trailing_pe=240, profit_margin=0.02, free_cashflow=1e8)
    assert "pe_extreme_or_no_earnings" in fundamentals_flags(row)


def test_fundamentals_state_candidate_rule_and_cap_floor() -> None:
    rows = [
        _fund_row(symbol="GARBAGE", market_cap=5e9, profit_margin=-0.55, price_to_sales=32, free_cashflow=-2e8),
        _fund_row(symbol="TINY", market_cap=3e8, profit_margin=-0.60, price_to_sales=40, free_cashflow=-1e7),
        _fund_row(symbol="BLUE", market_cap=3e12, trailing_pe=28, price_to_sales=7, profit_margin=0.25, free_cashflow=9e10),
    ]
    state = fundamentals_state(rows)
    assert state["short_candidate_flags"] == ["GARBAGE"]  # TINY fails the cap floor
    assert state["screen"]["BLUE"]["speculative_excess_score"] == 0
    assert "no_bias_change_unearned" in state["honest_limits"]


def test_fundamentals_state_stale_rows_excluded() -> None:
    rows = [
        _fund_row(symbol="OLD", date="2026-01-01", profit_margin=-0.9, price_to_sales=50, free_cashflow=-1e8),
        _fund_row(symbol="FRESH", date="2026-07-10", trailing_pe=20, profit_margin=0.2),
    ]
    state = fundamentals_state(rows)
    assert "OLD" not in state["screen"] and "FRESH" in state["screen"]
