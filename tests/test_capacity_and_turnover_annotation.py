"""Capacity and turnover annotations - scale descriptors, never promotion inputs.

Capacity answers "is this position liquid enough to hold real capital"; the
binding participation cap governs, thin liquidity is flagged, and every
annotation is explicitly stamped not-a-promotion-input. Turnover answers "how
fast does the paper book cycle" from the entry-date span and validated close
count, with no historical book-size series required.
"""
from __future__ import annotations

from dopey_risk_engine.capacity_annotation import (
    OPTION_CONTRACT_MULTIPLIER,
    book_capacity,
    position_capacity,
)
from dopey_backtest.forward_paper_walk import _turnover_annotation


def test_open_interest_is_binding_when_tighter() -> None:
    # OI 80 -> 0 contracts at 1%; volume 1000 -> 50 at 5%. OI binds at 0.
    cap = position_capacity(entry_fill=5.0, entry_volume=1000, entry_open_interest=80)
    assert cap["oi_cap_contracts"] == 0
    assert cap["volume_cap_contracts"] == 50
    assert cap["executable_contracts"] == 0
    assert cap["binding_constraint"] == "open_interest"
    assert cap["thin_liquidity"] is True
    assert cap["premium_notional_usd"] == 0.0


def test_volume_is_binding_when_tighter() -> None:
    # OI 5000 -> 50 at 1%; volume 200 -> 10 at 5%. Volume binds at 10.
    cap = position_capacity(entry_fill=2.0, entry_volume=200, entry_open_interest=5000)
    assert cap["executable_contracts"] == 10
    assert cap["binding_constraint"] == "day_volume"
    assert cap["premium_notional_usd"] == 10 * 2.0 * OPTION_CONTRACT_MULTIPLIER
    assert cap["thin_liquidity"] is False


def test_liquid_position_scales() -> None:
    cap = position_capacity(entry_fill=3.5, entry_volume=20000, entry_open_interest=40000)
    # OI 1% -> 400, volume 5% -> 1000; OI binds at 400.
    assert cap["executable_contracts"] == 400
    assert cap["premium_notional_usd"] == 400 * 3.5 * 100


def test_book_capacity_aggregates_and_flags_thin() -> None:
    caps = [
        position_capacity(5.0, 1000, 80),      # thin, 0 contracts
        position_capacity(2.0, 200, 5000),     # 10 contracts
        position_capacity(3.5, 20000, 40000),  # 400 contracts
    ]
    book = book_capacity(caps)
    assert book["positions_annotated"] == 3
    assert book["thin_liquidity_position_count"] == 1
    assert book["min_executable_contracts"] == 0
    assert book["capacity_annotation_not_a_promotion_input"] is True
    assert book["total_premium_notional_usd"] == round(
        0.0 + 10 * 2.0 * 100 + 400 * 3.5 * 100, 2
    )


def test_book_capacity_empty() -> None:
    book = book_capacity([])
    assert book["positions_annotated"] == 0
    assert book["total_premium_notional_usd"] == 0.0
    assert book["capacity_annotation_not_a_promotion_input"] is True


def test_turnover_computes_closes_per_session_and_cycle_time() -> None:
    ledger = {
        "closed_trades": [
            {"entry_date": "2026-07-06"},
            {"entry_date": "2026-07-07"},
        ],
        "open_positions": [{"entry_date": "2026-07-20"}, {"entry_date": "2026-07-20"}],
        "last_marking_date": "2026-07-20",
    }
    integrity = {"validated_closed_trade_count": 5}
    result = _turnover_annotation(ledger, integrity)
    assert result["turnover_status"] == "computed"
    # 2026-07-06 -> 2026-07-20 is 10 trading sessions (2 full weeks).
    assert result["observed_span_trading_sessions"] == 10
    assert result["closes_per_trading_session"] == 0.5
    assert result["implied_sessions_to_cycle_current_book"] == 4.0
    assert result["capacity_annotation_not_a_promotion_input"] is True


def test_turnover_insufficient_history() -> None:
    result = _turnover_annotation({"closed_trades": [], "open_positions": [], "last_marking_date": ""}, {"validated_closed_trade_count": 0})
    assert result["turnover_status"] == "insufficient_history"


def test_turnover_zero_closes_leaves_cycle_time_null() -> None:
    ledger = {
        "closed_trades": [],
        "open_positions": [{"entry_date": "2026-07-13"}],
        "last_marking_date": "2026-07-20",
    }
    result = _turnover_annotation(ledger, {"validated_closed_trade_count": 0})
    assert result["closes_per_trading_session"] == 0.0
    assert result["implied_sessions_to_cycle_current_book"] is None
