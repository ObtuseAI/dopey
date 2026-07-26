"""The foundry's derived lanes consume the compact per-symbol spine view.

The raw per-row dict spine (>1GB at 200 symbols) is freed before the lanes
run; the lanes receive {"dates": [...], "adjusted_closes": [...]} per symbol.
These tests plant tiny fixtures through each lane to prove the joins still
produce observations (and honest accrual gates still hold) after the memory
refactor - a silent join regression here would starve the lanes to zero
observations while looking like "insufficient sample accruing".
"""
from __future__ import annotations

from dopey_analysis import indicator_foundry as foundry


def _compact_series(symbol_days: int, start_price: float = 100.0) -> dict[str, list]:
    dates = [f"2026-01-{day:02d}" for day in range(1, symbol_days + 1)]
    closes = [start_price + day for day in range(symbol_days)]
    return {"dates": dates, "adjusted_closes": closes}


def test_quote_lane_joins_compact_spine(monkeypatch) -> None:
    compact = {"AAPL": _compact_series(30)}
    snapshot_rows = [
        {
            "symbol": "AAPL",
            "dte_calendar": 30,
            "option_type": side,
            "strike": strike,
            "open_interest": 50,
            "implied_vol": 0.3 if side == "call" else 0.36,
            "underlying_spot": 101.0,
        }
        for side in ("call", "put")
        for strike in (100.0, 101.0, 102.0)
    ]
    monkeypatch.setattr(
        "dopey_options.chain_snapshot_loader.list_chain_snapshot_dates",
        lambda: ["2026-01-05"],
    )
    monkeypatch.setattr(
        "dopey_options.chain_snapshot_loader.load_chain_snapshot",
        lambda snapshot_date: {
            "chain_snapshot_status": "real_chain_snapshot_validated",
            "rows": snapshot_rows,
        },
    )
    lane = foundry.evaluate_quote_derived_lane(compact)
    assert lane["joinable_observations"] == 1
    assert lane["quote_lane_status"] == "insufficient_sample_accruing"
    assert lane["snapshot_days_in_archive"] == 1


def test_quote_lane_skips_unjoinable_snapshot_beyond_spine(monkeypatch) -> None:
    # Snapshot date at the spine frontier: forward window not grown yet -> no join.
    compact = {"AAPL": _compact_series(10)}
    monkeypatch.setattr(
        "dopey_options.chain_snapshot_loader.list_chain_snapshot_dates",
        lambda: ["2026-01-09"],
    )
    monkeypatch.setattr(
        "dopey_options.chain_snapshot_loader.load_chain_snapshot",
        lambda snapshot_date: {
            "chain_snapshot_status": "real_chain_snapshot_validated",
            "rows": [
                {
                    "symbol": "AAPL",
                    "dte_calendar": 30,
                    "option_type": "call",
                    "strike": 100.0,
                    "open_interest": 50,
                    "implied_vol": 0.3,
                    "underlying_spot": 101.0,
                }
            ],
        },
    )
    lane = foundry.evaluate_quote_derived_lane(compact)
    assert lane["joinable_observations"] == 0


def test_macro_lane_joins_spy_compact_spine(monkeypatch) -> None:
    days = 40
    compact = {"SPY": _compact_series(days)}
    vol_rows = []
    for day in range(1, days + 1):
        date = f"2026-01-{day:02d}"
        for symbol, close in (("VIX9D", 14.0), ("VIX3M", 17.0), ("SKEW", 130.0), ("VIX", 15.0)):
            vol_rows.append({"date": date, "symbol": symbol, "close": str(close)})
    monkeypatch.setattr(
        "dopey_market_intake.macro_context_gate.load_macro_lanes",
        lambda: {
            "macro_status": "macro_lanes_validated",
            "lanes": {"vol_term_structure.csv": vol_rows},
        },
    )
    lane = foundry.evaluate_macro_derived_lane(compact)
    assert lane["joinable_observations"] > 0
    assert lane["macro_lane_status"] == "insufficient_sample_accruing"


def test_attention_lane_joins_compact_spine(monkeypatch) -> None:
    days = 40
    compact = {"NVDA": _compact_series(days)}
    pageview_rows = [
        {"date": f"2026-01-{day:02d}", "symbol": "NVDA", "views": str(1000 + day)}
        for day in range(1, days + 1)
    ]
    monkeypatch.setattr(
        "dopey_market_intake.macro_context_gate.load_macro_lanes",
        lambda: {
            "macro_status": "macro_lanes_validated",
            "lanes": {"wikipedia_pageviews.csv": pageview_rows},
        },
    )
    lane = foundry.evaluate_attention_lane(compact)
    assert lane["joinable_observations"] > 0
    assert lane["attention_lane_status"] == "insufficient_sample_accruing"


def test_accumulator_arrays_survive_rank_ic_and_null_bar() -> None:
    # The train/valid accumulators are unboxed array('d') now; the IC and the
    # circular-shift null must accept them unchanged.
    from array import array

    values = array("d", [float(index % 7) for index in range(200)])
    forwards = array("d", [float((index * 3) % 5) - 2.0 for index in range(200)])
    ic = foundry.rank_ic(values, forwards)
    assert -1.0 <= ic <= 1.0
    bar = foundry.empirical_null_bar({"candidate": values}, forwards, shifts=5)
    assert bar >= 0.0
