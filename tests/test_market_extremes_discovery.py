"""Integration coverage for signed stock movers and both option outcome tails."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from dopey.strategy_engineering.option_roi_discovery import discover_option_roi_strategies
from dopey.strategy_engineering.swing_target_discovery import discover_swing_targets


OHLCV_HEADER = "date,symbol,open,high,low,close,adjusted_close,volume,source"
CHAIN_HEADER = (
    "snapshot_date,symbol,expiry,dte_calendar,option_type,strike,bid,ask,mid,"
    "last,volume,open_interest,implied_vol,underlying_spot,source"
)


def _write_history(root: Path, symbol: str, final_return: float) -> None:
    root.mkdir(parents=True, exist_ok=True)
    closes = [100.0 + (0.05 if index % 2 else -0.05) for index in range(39)]
    closes.append(closes[-1] * (1.0 + final_return))
    start = date(2026, 1, 1)
    lines = [OHLCV_HEADER]
    for index, close in enumerate(closes):
        observed = (start + timedelta(days=index)).isoformat()
        lines.append(
            f"{observed},{symbol},{close},{close * 1.01},{close * 0.99},"
            f"{close},{close},1500000,test"
        )
    (root / f"{symbol}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _chain_row(
    observed: str,
    symbol: str,
    option_type: str,
    mid: float,
    spot: float,
) -> str:
    return (
        f"{observed},{symbol},2026-08-21,30,{option_type},100,"
        f"{mid - 0.02},{mid + 0.02},{mid},{mid},500,2000,0.55,{spot},test"
    )


def _write_chain_session(root: Path, observed: str, rows: tuple[str, ...]) -> None:
    session = root / observed
    session.mkdir(parents=True, exist_ok=True)
    for row in rows:
        symbol = row.split(",")[1]
        (session / f"{symbol}_chain.csv").write_text(
            "\n".join((CHAIN_HEADER, row)) + "\n",
            encoding="utf-8",
        )


def test_four_tail_discovery_preserves_signed_rankings_and_safety(tmp_path: Path) -> None:
    history = tmp_path / "history"
    _write_history(history, "BIGUP", 0.12)
    _write_history(history, "SMALLUP", 0.03)
    _write_history(history, "BIGDN", -0.14)
    _write_history(history, "SMALLDN", -0.02)

    chains = tmp_path / "chains"
    _write_chain_session(
        chains,
        "2026-07-16",
        (
            _chain_row("2026-07-16", "BIGUP", "call", 1.0, 100.0),
            _chain_row("2026-07-16", "BIGDN", "put", 2.0, 100.0),
        ),
    )
    _write_chain_session(
        chains,
        "2026-07-17",
        (
            _chain_row("2026-07-17", "BIGUP", "call", 3.0, 112.0),
            _chain_row("2026-07-17", "BIGDN", "put", 0.2, 86.0),
        ),
    )

    option_report = discover_option_roi_strategies(
        chains,
        winner_quantile=0.5,
        top_winner_report=10,
        top_loser_report=10,
    )
    assert [row["symbol"] for row in option_report["top_winners"]] == ["BIGUP"]
    assert [row["symbol"] for row in option_report["top_losers"]] == ["BIGDN"]
    assert option_report["top_winners"][0]["roi_pct"] > 0.0
    assert option_report["top_losers"][0]["roi_pct"] < 0.0
    assert option_report["top_losers"][0]["entry_conditions"]["entry_mid"] == 2.0
    assert option_report["loser_cohort_is_counterevidence"] is True

    market_report = discover_swing_targets(
        history,
        chains_root=chains,
        biggest_mover_count=4,
        max_targets=20,
    )
    assert [row["symbol"] for row in market_report["top_gainers"]] == [
        "BIGUP",
        "SMALLUP",
    ]
    assert [row["symbol"] for row in market_report["top_decliners"]] == [
        "BIGDN",
        "SMALLDN",
    ]
    assert all(row["latest_return_pct"] > 0.0 for row in market_report["top_gainers"])
    assert all(row["latest_return_pct"] < 0.0 for row in market_report["top_decliners"])
    big_up = next(row for row in market_report["swing_targets"] if row["symbol"] == "BIGUP")
    big_down = next(row for row in market_report["swing_targets"] if row["symbol"] == "BIGDN")
    assert big_up["coincides_with_option_winner"] is True
    assert big_down["coincides_with_option_loser"] is True
    assert market_report["profit_or_edge_claimed"] is False
    assert market_report["order_construction_allowed"] is False
    assert market_report["paper_only"] is True and market_report["live_blocked"] is True
