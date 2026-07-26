from __future__ import annotations

import math

from dopey_analysis.real_history_signal_engine import (
    CONTEXT_ONLY_SYMBOLS,
    EVALUATION_CADENCE_TRADING_DAYS,
    EVALUATION_START_DATE,
    LOOKBACK_WINDOW,
    _evaluation_dates,
    run_real_history_signal_engine,
)
from dopey_analysis.signal_models import make_price_bar, make_signal_series
from dopey_analysis.technical_signal_engine import compute_momentum_signal
from dopey_backtest.backtest_models import stable_backtest_hash
from dopey_backtest.real_history_honest_backtester import (
    ENTRY_TENOR_CALENDAR_DAYS,
    IV_FALLBACK,
    RISK_FREE_RATE,
    _build_real_marks,
    _cohort_scoreboard,
    _iv_proxy,
    _relabel,
    run_real_history_honest_backtester,
)
from dopey_options.option_pricing_models import option_pricing_input, price_european_option


def _bar(symbol: str, date: str, close: float, open_price: float | None = None) -> object:
    open_value = close if open_price is None else open_price
    high = max(open_value, close) * 1.01
    low = min(open_value, close) * 0.99
    return make_price_bar(symbol, date, open_value, high, low, close, close, 1000, "local_real_history", True, False, False)


def _rows(dates_closes: list[tuple[str, float, float]]) -> list[dict[str, object]]:
    return [
        {"date": date, "adjusted_open": open_value, "adjusted_close": close}
        for date, open_value, close in dates_closes
    ]


def _reference_bs(option_type: str, strike: float, spot: float, tte_years: float, vol: float) -> float:
    result = price_european_option(
        option_pricing_input(
            symbol="TEST",
            option_type=option_type,
            strike=strike,
            expiry="",
            valuation_date="2024-01-02",
            underlying_price=spot,
            time_to_expiry_years=tte_years,
            implied_vol=vol,
            risk_free_rate=RISK_FREE_RATE,
            dividend_yield=0.0,
            pricing_source_tier="model_priced",
        )
    )
    return max(round(float(result.model_price), 6), 0.000001)


def test_evaluation_dates_respect_start_cadence_and_lookback() -> None:
    dates = [f"2026-01-{day:02d}" for day in range(1, 29)]
    bars = [_bar("SPY", date, 100.0 + index) for index, date in enumerate(dates)]
    series = make_signal_series("SPY", bars, "local_real_history", True, False, False)
    chosen = _evaluation_dates(series)
    assert all(value >= EVALUATION_START_DATE for value in chosen)
    indexes = [dates.index(value) for value in chosen]
    assert all(index >= LOOKBACK_WINDOW for index in indexes)
    assert all(
        later - earlier == EVALUATION_CADENCE_TRADING_DAYS
        for earlier, later in zip(indexes, indexes[1:])
    )


def test_vix_is_context_only() -> None:
    assert "VIX" in CONTEXT_ONLY_SYMBOLS


def test_signals_do_not_use_future_bars() -> None:
    flat = [_bar("AAPL", f"2025-01-{day:02d}", 100.0) for day in range(1, 25)]
    crash = flat[:23] + [_bar("AAPL", "2025-01-24", 20.0)]
    flat_series = make_signal_series("AAPL", flat, "local_real_history", True, False, False)
    crash_series = make_signal_series("AAPL", crash, "local_real_history", True, False, False)
    at_date = "2025-01-23"
    flat_signal = compute_momentum_signal(flat_series, at_date, 10).to_dict()
    crash_signal = compute_momentum_signal(crash_series, at_date, 10).to_dict()
    assert flat_signal["raw_value"] == crash_signal["raw_value"]
    assert flat_signal["normalized_score"] == crash_signal["normalized_score"]


def test_build_real_marks_enters_next_day_open_and_prices_black_scholes() -> None:
    rows = _rows(
        [
            ("2025-03-03", 100.0, 100.0),
            ("2025-03-04", 100.0, 100.0),
            ("2025-03-05", 102.0, 103.0),
            ("2025-03-06", 103.5, 104.0),
            ("2025-03-07", 104.0, 105.0),
            ("2025-03-10", 105.0, 106.0),
        ]
    )
    intent = {
        "intent_id": "intent-1",
        "symbol": "AAPL",
        "signal_id": "sig-1",
        "signal_family": "momentum",
        "signal_date": "2025-03-04",
        "direction": "bullish",
        "candidate_strategy": "long_call",
        "option_structure": "long_call",
        "data_source_tier": "local_real_history",
        "reason_codes": [],
    }
    built = _build_real_marks(intent, rows, max_holding_steps=3)
    assert built is not None
    marks, mark_dates, path_id, iv_used, fell_back = built
    assert mark_dates[0] == "2025-03-05"
    assert mark_dates[1] == "2025-03-06"
    assert len(marks) == len(mark_dates)
    assert marks[0] == _reference_bs("call", 102.0, 102.0, ENTRY_TENOR_CALENDAR_DAYS / 365.0, iv_used)
    expected_mark_1 = _reference_bs("call", 102.0, 104.0, (ENTRY_TENOR_CALENDAR_DAYS - 1) / 365.0, iv_used)
    assert marks[1] == expected_mark_1
    assert "AAPL" in path_id and "call" in path_id


def test_build_real_marks_put_and_insufficient_forward_bars() -> None:
    rows = _rows(
        [
            ("2025-03-03", 100.0, 100.0),
            ("2025-03-04", 100.0, 100.0),
            ("2025-03-05", 100.0, 99.0),
            ("2025-03-06", 98.0, 97.0),
        ]
    )
    put_intent = {
        "intent_id": "intent-2",
        "symbol": "SPY",
        "signal_id": "sig-2",
        "signal_family": "market_regime",
        "signal_date": "2025-03-04",
        "direction": "bearish",
        "candidate_strategy": "long_put",
        "option_structure": "long_put",
        "data_source_tier": "local_real_history",
        "reason_codes": [],
    }
    built = _build_real_marks(put_intent, rows, max_holding_steps=3)
    assert built is not None
    marks, mark_dates, path_id, iv_used, _ = built
    assert "put" in path_id
    assert marks[0] == _reference_bs("put", 100.0, 100.0, ENTRY_TENOR_CALENDAR_DAYS / 365.0, iv_used)
    tail_intent = dict(put_intent, signal_date="2025-03-06")
    assert _build_real_marks(tail_intent, rows, max_holding_steps=3) is None
    early_intent = dict(put_intent, signal_date="2025-03-01")
    marks_from_start = _build_real_marks(early_intent, rows, max_holding_steps=3)
    assert marks_from_start is None


def test_iv_proxy_fallback_on_flat_series() -> None:
    rows = _rows([(f"2025-04-{day:02d}", 100.0, 100.0) for day in range(1, 25)])
    iv, fell_back = _iv_proxy(rows, len(rows) - 1)
    assert fell_back is True
    assert iv == IV_FALLBACK


def test_relabel_sets_real_tiers_and_rehashes() -> None:
    record = {
        "artifact_type": "backtest_trade_record",
        "real_history_used": False,
        "fixture_only": True,
        "data_source_tier": "fixture_only",
        "path_pnl": 1.5,
        "record_hash": "stale",
    }
    relabeled = _relabel(record)
    assert relabeled["real_history_used"] is True
    assert relabeled["fixture_only"] is False
    assert relabeled["data_source_tier"] == "local_real_history"
    assert relabeled["record_hash"] == stable_backtest_hash(relabeled)
    assert record["record_hash"] == "stale"


def test_cohort_scoreboard_profit_factor_math() -> None:
    records = [
        {"signal_family": "momentum", "candidate_strategy": "long_call", "path_pnl": 2.0, "trade_return_model_units": 0.5},
        {"signal_family": "momentum", "candidate_strategy": "long_call", "path_pnl": -1.0, "trade_return_model_units": -0.25},
        {"signal_family": "momentum", "candidate_strategy": "long_call", "path_pnl": 3.0, "trade_return_model_units": 0.75},
    ]
    scoreboard = _cohort_scoreboard(records)
    assert len(scoreboard) == 1
    row = scoreboard[0]
    assert row["cohort_id"] == "momentum|long_call"
    assert row["sample_count"] == 3
    assert math.isclose(row["profit_factor"], 5.0)
    assert math.isclose(row["net_pnl_model_units"], 4.0)
    assert math.isclose(row["win_rate"], 2.0 / 3.0, rel_tol=1e-6)
    assert row["not_edge_evidence"] is True


def test_live_run_summary_reflects_real_history_and_blocked_claims() -> None:
    run_real_history_signal_engine()
    summary = run_real_history_honest_backtester()
    if summary["backtest_status"] == "blocked_missing_valid_real_history":
        assert summary["real_history_used"] is False
        return
    assert summary["backtest_status"] == "valid_real_history_model_priced_backtest_complete"
    assert summary["real_history_used"] is True
    assert summary["quote_priced_trade_count"] == 0
    assert summary["fixture_only_trade_count"] == 0
    assert summary["not_real_backtest_evidence"] is True
    assert summary["not_profitability_claim"] is True
    assert summary["not_live_ready"] is True
    assert summary["paper_only"] is True
    assert summary["live_blocked"] is True
    assert summary["trade_record_count"] > 0
    assert "missing_real_option_chain" in summary["quality_flags"]
    assert "spread_slippage_commission_costs_modeled" in summary["quality_flags"]
    assert summary["total_trade_costs_model_units"] > 0.0
