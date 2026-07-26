"""Tests for the overbought/oversold swing-target scanner."""
from __future__ import annotations

from pathlib import Path

import pytest

from dopey.strategy_engineering.swing_target_discovery import (
    MIN_BARS,
    compute_mover_metrics,
    discover_swing_targets,
    load_ohlcv_history,
)

_HEADER = "date,symbol,open,high,low,close,adjusted_close,volume,source"


def _write_history(root: Path, symbol: str, closes: list[float]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = [_HEADER]
    for i, close in enumerate(closes):
        day = 1 + i
        date = f"2026-01-{day:02d}" if day <= 28 else f"2026-02-{day - 28:02d}"
        lines.append(f"{date},{symbol},{close},{close * 1.01},{close * 0.99},{close},{close},1000000,test")
    (root / f"{symbol}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_no_history_reports_and_claims_nothing(tmp_path: Path):
    rep = discover_swing_targets(tmp_path / "empty")
    assert rep["status"] == "no_ohlcv_history"
    assert rep["profit_or_edge_claimed"] is False
    assert rep["order_construction_allowed"] is False


def test_metrics_require_minimum_bars(tmp_path: Path):
    root = tmp_path / "hist"
    _write_history(root, "SHORT", [100.0] * (MIN_BARS - 1))
    assert load_ohlcv_history(root) == {}  # dropped: too few bars


def test_overbought_symbol_flagged_short(tmp_path: Path):
    root = tmp_path / "hist"
    # Steady strong uptrend -> high RSI, positive last move -> overbought.
    closes = [100.0 * (1.03 ** i) for i in range(40)]
    _write_history(root, "UPUP", closes)
    metrics = compute_mover_metrics(load_ohlcv_history(root)["UPUP"])
    assert metrics is not None and metrics["rsi_14"] >= 70.0
    rep = discover_swing_targets(root)
    target = next(t for t in rep["swing_targets"] if t["symbol"] == "UPUP")
    assert target["stretch_state"] == "overbought"
    assert target["swing_bias"] == "mean_reversion_short"
    assert target["is_trade_signal"] is False


def test_oversold_symbol_flagged_long(tmp_path: Path):
    root = tmp_path / "hist"
    closes = [100.0 * (0.97 ** i) for i in range(40)]  # steady downtrend
    _write_history(root, "DNDN", closes)
    rep = discover_swing_targets(root)
    target = next(t for t in rep["swing_targets"] if t["symbol"] == "DNDN")
    assert target["stretch_state"] == "oversold"
    assert target["swing_bias"] == "mean_reversion_long"


def test_neutral_symbol_not_targeted(tmp_path: Path):
    root = tmp_path / "hist"
    # Flat, tiny oscillation -> RSI ~50, no extreme.
    closes = [100.0 + (0.1 if i % 2 else -0.1) for i in range(40)]
    _write_history(root, "FLAT", closes)
    rep = discover_swing_targets(root)
    assert all(t["symbol"] != "FLAT" for t in rep["swing_targets"])


def test_option_winner_cross_reference_raises_priority(tmp_path: Path):
    hist = tmp_path / "hist"
    closes = [100.0 * (1.03 ** i) for i in range(40)]
    _write_history(hist, "META", closes)

    # Minimal two-session chain where a META call is a big winner.
    chains = tmp_path / "chains"
    chdr = ("snapshot_date,symbol,expiry,dte_calendar,option_type,strike,bid,ask,"
            "mid,last,volume,open_interest,implied_vol,underlying_spot,source")
    for date, mid, spot in (("2026-07-09", 1.0, 100.0), ("2026-07-10", 3.0, 108.0)):
        d = chains / date
        d.mkdir(parents=True)
        (d / "META_chain.csv").write_text(
            "\n".join([chdr, f"{date},META,2026-08-07,29,call,100,{mid - 0.02},{mid + 0.02},{mid},{mid},100,500,0.9,{spot},test"]) + "\n",
            encoding="utf-8",
        )

    without = discover_swing_targets(hist)
    with_opt = discover_swing_targets(hist, chains_root=chains)
    t_without = next(t for t in without["swing_targets"] if t["symbol"] == "META")
    t_with = next(t for t in with_opt["swing_targets"] if t["symbol"] == "META")
    assert t_with["coincides_with_option_winner"] is True
    assert t_without["coincides_with_option_winner"] is False
    assert t_with["research_priority"] > t_without["research_priority"]


def test_honesty_invariants_on_every_target(tmp_path: Path):
    root = tmp_path / "hist"
    _write_history(root, "UPUP", [100.0 * (1.03 ** i) for i in range(40)])
    _write_history(root, "DNDN", [100.0 * (0.97 ** i) for i in range(40)])
    rep = discover_swing_targets(root)
    assert rep["mean_reversion_is_an_unvalidated_hypothesis"] is True
    assert rep["profit_or_edge_claimed"] is False
    assert rep["positive_promotion_allowed"] is False
    for t in rep["swing_targets"]:
        assert t["paper_only"] is True and t["live_blocked"] is True
        assert t["is_trade_signal"] is False
        assert "forward_paper_settlement" in t["required_forward_checks"]


def test_real_staged_history_if_present():
    root = Path(__file__).resolve().parents[1] / "dopey_data" / "history" / "raw"
    if not root.is_dir() or len(list(root.glob("*.csv"))) < 3:
        pytest.skip("insufficient staged OHLCV history")
    rep = discover_swing_targets(root)
    assert rep["status"] == "complete"
    assert rep["symbols_scored"] > 0
    assert rep["profit_or_edge_claimed"] is False
    assert rep["live_blocked"] is True
