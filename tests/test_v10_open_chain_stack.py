from __future__ import annotations

import json

from dopey_backtest.forward_paper_walk import (
    COMMISSION_PREMIUM_UNITS,
    MAX_MARKING_SESSIONS,
    _close,
    _load_ledger,
)
from dopey_options.chain_analytics import enrich_rows_with_greeks, real_chain_positioning_metrics
from dopey_options.chain_snapshot_loader import _parse_file, load_latest_chain_snapshot

CHAIN_HEADER = (
    "snapshot_date,symbol,expiry,dte_calendar,option_type,strike,bid,ask,mid,last,"
    "volume,open_interest,implied_vol,underlying_spot,source"
)


def _chain_csv(rows: list[str]) -> str:
    return CHAIN_HEADER + "\n" + "\n".join(rows) + "\n"


def test_chain_parser_accepts_clean_rows_and_rejects_dirty_ones() -> None:
    text = _chain_csv(
        [
            "2026-07-09,SPY,2026-08-07,29,call,750.0,10.0,10.2,10.1,10.05,100,5000,0.15,751.24,yahoo_finance_chain_snapshot",
            "2026-07-09,SPY,2026-08-07,29,put,750.0,9.0,9.2,9.1,9.05,80,4000,0.16,751.24,yahoo_finance_chain_snapshot",
            "2099-01-01,SPY,2026-08-07,29,call,750.0,10.0,10.2,10.1,10.05,100,5000,0.15,751.24,x",
            "2026-07-09,SPY,2026-08-07,29,call,-5.0,10.0,10.2,10.1,10.05,100,5000,0.15,751.24,x",
            "2026-07-09,SPY,2026-08-07,29,call,750.0,11.0,10.2,10.1,10.05,100,5000,0.15,751.24,x",
            "2026-07-09,SPY,2026-08-07,29,vertical_spread,750.0,10.0,10.2,10.1,10.05,100,5000,0.15,751.24,x",
        ]
    )
    rows, reasons = _parse_file(text, "test.csv")
    assert len(rows) == 2
    assert any("future_snapshot_date" in reason for reason in reasons)
    assert any("quality_reject" in reason for reason in reasons)
    assert any("bad_option_type" in reason for reason in reasons)


def test_chain_parser_rejects_wrong_schema() -> None:
    rows, reasons = _parse_file("date,strike\n2026-07-09,100\n", "bad.csv")
    assert rows == []
    assert reasons == ["schema_mismatch:bad.csv"]


def test_greeks_enrichment_and_real_metrics() -> None:
    base = {
        "snapshot_date": "2026-07-09",
        "symbol": "TST",
        "expiry": "2026-08-07",
        "dte_calendar": 29,
        "mid": 5.0,
        "last": 5.0,
        "volume": 10,
        "bid": 4.9,
        "ask": 5.1,
        "source": "fixture",
        "quote_derived": True,
    }
    rows = [
        {**base, "option_type": "call", "strike": 100.0, "open_interest": 1000, "implied_vol": 0.2, "underlying_spot": 100.0},
        {**base, "option_type": "put", "strike": 100.0, "open_interest": 2000, "implied_vol": 0.2, "underlying_spot": 100.0},
    ]
    enriched = enrich_rows_with_greeks(rows)
    call_row = next(row for row in enriched if row["option_type"] == "call")
    put_row = next(row for row in enriched if row["option_type"] == "put")
    assert call_row["gamma"] > 0 and put_row["gamma"] > 0
    assert 0 < call_row["delta"] < 1 and -1 < put_row["delta"] < 0
    metrics = real_chain_positioning_metrics(enriched)
    assert len(metrics) == 1
    metric = metrics[0]
    assert metric["symbol"] == "TST"
    assert metric["put_call_oi_ratio"] == 2.0
    assert metric["quote_derived"] is True
    # equal gamma, put OI double call OI -> net dealer GEX negative
    assert metric["total_gex_dollar_per_pct"] < 0


def test_live_chain_snapshot_state_consistent() -> None:
    snapshot = load_latest_chain_snapshot()
    if snapshot["chain_snapshot_status"] == "real_chain_snapshot_validated":
        assert snapshot["row_count"] > 0
        assert snapshot["quote_derived"] is True
        assert all(row["ask"] >= row["bid"] >= 0 for row in snapshot["rows"][:200])
    else:
        assert snapshot["rows"] == []


def test_forward_walk_close_math_conservative_fills() -> None:
    position = {
        "position_id": "fw-TST-long_call-2026-07-09-00",
        "symbol": "TST",
        "candidate_strategy": "long_call",
        "option_type": "call",
        "signal_id": "s",
        "signal_family": "momentum",
        "signal_date": "2026-07-08",
        "entry_date": "2026-07-09",
        "expiry": "2026-08-07",
        "strike": 100.0,
        "entry_bid": 4.9,
        "entry_ask": 5.1,
        "entry_fill": 5.1065,
        "entry_spot": 100.0,
        "entry_iv": 0.2,
        "marking_sessions": 2,
        "missed_marks": 0,
        "last_mark_bid": 6.0,
        "last_mark_date": "2026-07-10",
        "quote_priced": True,
        "pricing_source_tier": "quote_derived_snapshot",
        "ex_ante": True,
        "paper_only": True,
        "live_blocked": True,
    }
    closed = _close(position, 6.0, "2026-07-11", "time_stop")
    assert closed["exit_fill"] == round(6.0 - COMMISSION_PREMIUM_UNITS, 6)
    assert closed["path_pnl"] == round(closed["exit_fill"] - 5.1065, 6)
    assert closed["exit_reason"] == "time_stop"
    assert closed["quote_priced"] is True and closed["ex_ante"] is True
    assert closed["win_loss_marker"] == "win_forward_walk"
    # entry paid the ask plus commission; exit received the bid minus commission
    assert position["entry_fill"] > position["entry_bid"]
    assert closed["exit_fill"] < 6.0 + 1e-9


def test_forward_walk_ledger_defaults() -> None:
    ledger = _load_ledger()
    assert set(ledger) >= {"open_positions", "closed_trades", "last_marking_date"}
    assert isinstance(ledger["open_positions"], list)
    assert isinstance(ledger["closed_trades"], list)
    assert MAX_MARKING_SESSIONS >= 1


def test_forward_walk_summary_is_honest() -> None:
    from dopey_backtest.forward_paper_walk import SUMMARY_PATH, run_forward_paper_walk

    summary = run_forward_paper_walk()
    assert summary["strategy_promotion_allowed"] is False
    assert summary["not_profitability_claim"] is True
    assert summary["paper_only"] is True and summary["live_blocked"] is True
    assert SUMMARY_PATH.exists()
    on_disk = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    assert on_disk["forward_walk_status"] == summary["forward_walk_status"]
