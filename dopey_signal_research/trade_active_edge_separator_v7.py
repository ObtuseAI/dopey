"""Trade-active edge separator for V7.

Separates V6 path trades into no-trade and trade-active (long_call/long_put)
buckets, computes per-subfamily trade-active edge metrics, and identifies
whether a candidate's profitability depends on no-trade zeros rather than
realized option trades.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from dopey_autonomy.public_champion_common import safe_float


__all__ = [
    "is_no_trade",
    "is_trade_active",
    "separate_trades",
    "pnl_for_trades",
    "profit_factor",
    "compute_subfamily_trade_active_metrics",
    "compute_trade_active_edge",
]


def is_no_trade(trade: dict[str, object]) -> bool:
    """A trade is no-trade if direction is no_trade or pnl is exactly zero."""
    direction = str(trade.get("direction", "")).lower()
    return direction == "no_trade" or safe_float(trade.get("pnl", 0.0)) == 0.0


def is_trade_active(trade: dict[str, object]) -> bool:
    """A trade is trade-active if it is a long_call or long_put with non-zero pnl."""
    direction = str(trade.get("direction", "")).lower()
    return direction in {"long_call", "long_put"} and safe_float(trade.get("pnl", 0.0)) != 0.0


def separate_trades(trades: Sequence[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return (no_trade_trades, trade_active_trades)."""
    no_trade: list[dict[str, object]] = []
    active: list[dict[str, object]] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        if is_trade_active(trade):
            active.append(dict(trade))
        else:
            no_trade.append(dict(trade))
    return no_trade, active


def pnl_for_trades(trades: Sequence[dict[str, object]]) -> list[float]:
    return [safe_float(t.get("pnl", 0.0)) for t in trades]


def profit_factor(pnl_values: Sequence[float]) -> float:
    gains = sum(p for p in pnl_values if p > 0.0)
    losses = abs(sum(p for p in pnl_values if p < 0.0))
    if losses == 0.0:
        return round(gains, 6) if gains > 0.0 else 0.0
    return round(gains / losses, 6)


def compute_subfamily_trade_active_metrics(
    subfamily_id: str,
    trades: Sequence[dict[str, object]],
) -> dict[str, object]:
    """Compute trade-active edge for a single subfamily."""
    no_trade_trades, active_trades = separate_trades(trades)
    total_count = len(trades)
    no_trade_count = len(no_trade_trades)
    active_count = len(active_trades)

    no_trade_pnls = pnl_for_trades(no_trade_trades)
    active_pnls = pnl_for_trades(active_trades)

    no_trade_pnl = round(sum(no_trade_pnls), 6)
    active_pnl = round(sum(active_pnls), 6)
    total_pnl = round(no_trade_pnl + active_pnl, 6)

    no_trade_pf = profit_factor(no_trade_pnls)
    active_pf = profit_factor(active_pnls)
    total_pf = profit_factor(no_trade_pnls + active_pnls)

    no_trade_ratio = round(no_trade_count / total_count, 6) if total_count else 0.0
    active_ratio = round(active_count / total_count, 6) if total_count else 0.0

    return {
        "stable_subfamily_id": subfamily_id,
        "total_sample_count": total_count,
        "no_trade_count": no_trade_count,
        "trade_active_count": active_count,
        "no_trade_ratio": no_trade_ratio,
        "trade_active_ratio": active_ratio,
        "no_trade_pnl": no_trade_pnl,
        "trade_active_pnl": active_pnl,
        "total_pnl": total_pnl,
        "no_trade_profit_factor": no_trade_pf,
        "trade_active_profit_factor": active_pf,
        "total_profit_factor": total_pf,
    }


def compute_trade_active_edge(
    metrics: dict[str, object],
    min_pf: float = 1.10,
) -> dict[str, object]:
    """Return edge classification for a subfamily's trade-active bucket."""
    active_pf = safe_float(metrics.get("trade_active_profit_factor", 0.0))
    active_count = int(metrics.get("trade_active_count", 0))
    active_ratio = safe_float(metrics.get("trade_active_ratio", 0.0))

    has_edge = active_count > 0 and active_pf >= min_pf
    return {
        "stable_subfamily_id": metrics.get("stable_subfamily_id", ""),
        "trade_active_profit_factor": active_pf,
        "trade_active_sample_count": active_count,
        "trade_active_ratio": active_ratio,
        "trade_active_edge": has_edge,
        "trade_active_edge_above_min_pf": has_edge,
        "v7_min_breakthrough_pf": min_pf,
    }


def group_trades_by_subfamily(
    trades: Sequence[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """Index trades by stable_subfamily_id."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        sub = str(trade.get("stable_subfamily_id", ""))
        if sub:
            grouped[sub].append(dict(trade))
    return dict(grouped)
