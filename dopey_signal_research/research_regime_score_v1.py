"""Research regime score V1."""
from __future__ import annotations

from collections import defaultdict

from dopey_autonomy.public_champion_common import safe_float


def regime_scores(trades: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get("regime", trade.get("trend_regime", "unknown")))].append(trade)
    rows: list[dict[str, object]] = []
    for regime, cohort in grouped.items():
        pnl = sum(safe_float(trade.get("paper_pnl")) for trade in cohort)
        rows.append({
            "artifact_type": "research_tournament_regime_score_v1",
            "regime": regime,
            "trade_count": len(cohort),
            "net_pnl": round(pnl, 6),
        })
    return rows
