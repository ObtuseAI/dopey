"""Research holdout scoring V1."""
from __future__ import annotations

from dopey_autonomy.public_champion_common import safe_float


def holdout_split_pass_rate(trades: list[dict[str, object]]) -> float:
    if not trades:
        return 0.0
    midpoint = len(trades) // 2
    first = trades[:midpoint]
    second = trades[midpoint:]
    first_pnl = sum(safe_float(trade.get("paper_pnl")) for trade in first)
    second_pnl = sum(safe_float(trade.get("paper_pnl")) for trade in second)
    passes = int(first_pnl > 0.0) + int(second_pnl > 0.0)
    return round(passes / 2.0, 4)


def holdout_survival(trades: list[dict[str, object]]) -> bool:
    return holdout_split_pass_rate(trades) >= 0.5
