"""Promotion and elimination policy for the paper tournament."""
from __future__ import annotations

from dopey_wealth_engine.common import stable_hash


def build_winner_loser_records(scores: list[dict]) -> tuple[list[dict], list[dict]]:
    promotions: list[dict] = []
    eliminations: list[dict] = []
    for score in scores:
        pnl = float(score["net_paper_pnl"])
        drawdown = abs(float(score["max_drawdown"]))
        if pnl > 0 and drawdown < max(2_500.0, pnl * 2.0):
            record = {
                "artifact_type": "winner_promotion_record",
                "strategy_family": score["strategy_family"],
                "promotion_level": "paper_champion" if pnl > 1_500 else "paper_active",
                "net_paper_pnl": score["net_paper_pnl"],
                "max_drawdown": score["max_drawdown"],
                "market_data_source_type": score.get("market_data_source_type", "fixture_fallback"),
                "public_data_paper_champion": score.get("market_data_source_type", "") != "fixture_fallback" and pnl > 1_500,
                "fixture_only_champion": score.get("market_data_source_type", "fixture_fallback") == "fixture_fallback" and pnl > 1_500,
                "live_promotion_allowed": False,
                "paper_only": True,
                "live_blocked": True,
            }
            record["record_hash"] = stable_hash(record)
            promotions.append(record)
        if pnl < -500 or drawdown > 4_000 or int(score["loss_streak"]) >= 4:
            record = {
                "artifact_type": "loser_elimination_record",
                "strategy_family": score["strategy_family"],
                "elimination_action": "kill" if pnl < -1_500 else "throttle",
                "net_paper_pnl": score["net_paper_pnl"],
                "max_drawdown": score["max_drawdown"],
                "market_data_source_type": score.get("market_data_source_type", "fixture_fallback"),
                "reason": "drawdown_or_negative_expectancy",
                "paper_only": True,
                "live_blocked": True,
            }
            record["record_hash"] = stable_hash(record)
            eliminations.append(record)
    return promotions, eliminations
