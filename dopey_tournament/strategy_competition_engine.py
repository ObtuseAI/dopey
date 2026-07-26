"""Build paper tournament leaderboards."""
from __future__ import annotations

from dopey_wealth_engine.common import stable_hash


def build_strategy_leaderboard(scores: list[dict]) -> list[dict]:
    leaderboard: list[dict] = []
    for rank, score in enumerate(scores, start=1):
        record = {
            "artifact_type": "paper_tournament_leaderboard",
            "rank": rank,
            "strategy_family": score["strategy_family"],
            "market_data_source_type": score.get("market_data_source_type", "fixture_fallback"),
            "net_paper_pnl": score["net_paper_pnl"],
            "max_drawdown": score["max_drawdown"],
            "profit_factor": score["profit_factor"],
            "win_rate": score["win_rate"],
            "paper_allocation_action": "increase" if rank <= 3 and float(score["net_paper_pnl"]) > 0 else "reduce",
            "paper_only": True,
            "live_blocked": True,
        }
        record["record_hash"] = stable_hash(record)
        leaderboard.append(record)
    return leaderboard
