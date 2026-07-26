"""Baseline long-straddle VRP probe - envelope-safe control, gate-isolated.

The probe must: build ATM straddles with BOTH legs long (buy-to-open), price
them from real snapshot rows, exit on COMBINED premium, settle one structure
to exactly ONE outcome, and stay in a ledger entirely separate from the
directional forward walk so it can never inflate the promotion gate.
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_backtest import straddle_vrp_probe as probe


def _chain_row(symbol, option_type, strike, spot, bid, ask, dte=30, expiry="2026-08-21"):
    return {
        "symbol": symbol,
        "option_type": option_type,
        "strike": float(strike),
        "underlying_spot": float(spot),
        "bid": float(bid),
        "ask": float(ask),
        "volume": 500,
        "open_interest": 2000,
        "implied_vol": 0.30,
        "dte_calendar": dte,
        "expiry": expiry,
    }


def _liquid_straddle_rows(symbol, spot, call_bid, call_ask, put_bid, put_ask):
    # three strikes; the ATM one at spot, both legs present and liquid
    rows = []
    for strike in (spot - 5, spot, spot + 5):
        cb, ca, pb, pa = (
            (call_bid, call_ask, put_bid, put_ask)
            if strike == spot
            else (0.5, 0.6, 0.5, 0.6)
        )
        rows.append(_chain_row(symbol, "call", strike, spot, cb, ca))
        rows.append(_chain_row(symbol, "put", strike, spot, pb, pa))
    return rows


def _patch_snapshot(monkeypatch, tmp_path, rows, snapshot_date="2026-07-23"):
    monkeypatch.setattr(probe, "LEDGER_PATH", tmp_path / "ledger.json")
    monkeypatch.setattr(probe, "SUMMARY_PATH", tmp_path / "summary.json")
    monkeypatch.setattr(
        probe,
        "load_latest_chain_snapshot",
        lambda: {
            "chain_snapshot_status": "real_chain_snapshot_validated",
            "snapshot_date": snapshot_date,
            "rows": rows,
        },
    )


def test_atm_straddle_picks_nearest_strike_both_legs() -> None:
    rows = _liquid_straddle_rows("AAA", 100.0, 3.0, 3.1, 2.8, 2.9)
    legs = probe.atm_straddle_legs(rows)
    assert legs is not None
    call_row, put_row = legs
    assert call_row["option_type"] == "call" and put_row["option_type"] == "put"
    assert call_row["strike"] == 100.0 and put_row["strike"] == 100.0


def test_missing_one_leg_yields_no_straddle() -> None:
    rows = [r for r in _liquid_straddle_rows("AAA", 100.0, 3.0, 3.1, 2.8, 2.9)
            if not (r["option_type"] == "put" and r["strike"] == 100.0)]
    assert probe.atm_straddle_legs(rows) is None


def test_illiquid_leg_rejects_straddle() -> None:
    rows = _liquid_straddle_rows("AAA", 100.0, 3.0, 3.1, 2.8, 2.9)
    for r in rows:
        if r["strike"] == 100.0:
            r["open_interest"] = 1  # below floor
    assert probe.atm_straddle_legs(rows) is None


def test_open_builds_both_legs_long(tmp_path, monkeypatch) -> None:
    rows = _liquid_straddle_rows("AAA", 100.0, 3.0, 3.1, 2.8, 2.9)
    _patch_snapshot(monkeypatch, tmp_path, rows)
    summary = probe.run_straddle_vrp_probe()
    assert summary["open_structure_count"] == 1
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    structure = ledger["open_structures"][0]
    assert structure["direction_bucket"] == "neutral"
    assert structure["both_legs_buy_to_open"] is True
    assert structure["no_short_option_leg"] is True
    # combined entry = call_ask + put_ask + 2*commission
    assert structure["combined_entry_fill"] == round(3.1 + 2.9 + 2 * probe.COMMISSION_PREMIUM_UNITS, 6)


def test_combined_premium_target_exit_and_single_outcome(tmp_path, monkeypatch) -> None:
    # open at combined ask ~6.0, then next snapshot marks combined bid ~14 -> +100%+
    rows_day1 = _liquid_straddle_rows("AAA", 100.0, 3.0, 3.1, 2.8, 2.9)
    _patch_snapshot(monkeypatch, tmp_path, rows_day1, "2026-07-23")
    probe.run_straddle_vrp_probe()

    rows_day2 = _liquid_straddle_rows("AAA", 100.0, 8.0, 8.1, 7.0, 7.1)
    _patch_snapshot(monkeypatch, tmp_path, rows_day2, "2026-07-24")
    summary = probe.run_straddle_vrp_probe()

    assert summary["newly_closed_count"] == 1
    assert summary["validated_closed_structure_count"] == 1
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    closed = ledger["closed_structures"][0]
    assert closed["exit_reason"] == "combined_premium_target"
    assert closed["counts_as_outcomes"] == 1  # ONE structure = ONE outcome
    assert closed["included_in_promotion_gate"] is False
    assert closed["win_loss_marker"] == "win"


def test_combined_premium_stop_exit(tmp_path, monkeypatch) -> None:
    rows_day1 = _liquid_straddle_rows("AAA", 100.0, 3.0, 3.1, 2.8, 2.9)
    _patch_snapshot(monkeypatch, tmp_path, rows_day1, "2026-07-23")
    probe.run_straddle_vrp_probe()
    # combined bid collapses to ~2.0 vs ~6.0 entry -> below -50%
    rows_day2 = _liquid_straddle_rows("AAA", 100.0, 1.0, 1.1, 1.0, 1.1)
    _patch_snapshot(monkeypatch, tmp_path, rows_day2, "2026-07-24")
    summary = probe.run_straddle_vrp_probe()
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    assert ledger["closed_structures"][0]["exit_reason"] == "combined_premium_stop"
    assert ledger["closed_structures"][0]["win_loss_marker"] == "loss"


def test_caps_open_structures(tmp_path, monkeypatch) -> None:
    rows = []
    for symbol in ("AAA", "BBB", "CCC", "DDD", "EEE"):
        rows.extend(_liquid_straddle_rows(symbol, 100.0, 3.0, 3.1, 2.8, 2.9))
    _patch_snapshot(monkeypatch, tmp_path, rows, "2026-07-23")
    # first run opens up to MAX_NEW_STRUCTURES_PER_RUN
    probe.run_straddle_vrp_probe()
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    assert len(ledger["open_structures"]) <= probe.MAX_OPEN_STRUCTURES
    assert len(ledger["open_structures"]) == probe.MAX_NEW_STRUCTURES_PER_RUN


def test_missing_quote_defers_then_censors(tmp_path, monkeypatch) -> None:
    rows_day1 = _liquid_straddle_rows("AAA", 100.0, 3.0, 3.1, 2.8, 2.9)
    _patch_snapshot(monkeypatch, tmp_path, rows_day1, "2026-07-23")
    probe.run_straddle_vrp_probe()
    # subsequent snapshots omit AAA entirely -> misses accrue, then censor
    for day in ("2026-07-24", "2026-07-27", "2026-07-28"):
        _patch_snapshot(monkeypatch, tmp_path, _liquid_straddle_rows("ZZZ", 50.0, 1.0, 1.1, 1.0, 1.1), day)
        summary = probe.run_straddle_vrp_probe()
    ledger = json.loads((tmp_path / "ledger.json").read_text())
    censored = [s for s in ledger["closed_structures"] if s.get("outcome_class") == "censored_missing_quote_continuity"]
    assert len(censored) == 1
    assert censored[0]["counts_as_outcomes"] == 0  # censored never counts as an outcome


def test_summary_is_gate_isolated_baseline(tmp_path, monkeypatch) -> None:
    rows = _liquid_straddle_rows("AAA", 100.0, 3.0, 3.1, 2.8, 2.9)
    _patch_snapshot(monkeypatch, tmp_path, rows)
    summary = probe.run_straddle_vrp_probe()
    assert summary["baseline_not_candidate"] is True
    assert summary["included_in_promotion_gate"] is False
    assert summary["strategy_promotion_allowed"] is False
    assert summary["separate_ledger_from_directional_forward_walk"] is True
    assert summary["one_structure_equals_one_outcome"] is True
