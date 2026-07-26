"""Loser kill queue builder for public champion evolution."""
from __future__ import annotations

from dopey_autonomy.public_champion_common import record_with_hash, safe_float


def build_public_loser_kill_queue(leaderboard: list[dict[str, object]], generation: int) -> list[dict[str, object]]:
    killed: list[dict[str, object]] = []
    for row in leaderboard:
        reasons = kill_reasons(row)
        if not reasons:
            continue
        record = {
            "artifact_type": "public_loser_kill_queue",
            "generation": generation,
            "strategy_id": row.get("strategy_id", ""),
            "setup_family": row.get("setup_family", ""),
            "kill_reasons": reasons,
            "net_pnl": row.get("net_pnl", 0.0),
            "profit_factor": row.get("profit_factor", 0.0),
            "max_drawdown": row.get("max_drawdown", 0.0),
            "paper_only": True,
            "live_trading_enabled": False,
        }
        killed.append(record_with_hash(record, "record_hash"))
    return killed


def kill_reasons(row: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    if safe_float(row.get("net_pnl")) <= 0.0:
        reasons.append("non_positive_net_pnl")
    if safe_float(row.get("profit_factor")) < 1.0:
        reasons.append("profit_factor_below_one")
    if safe_float(row.get("split_pass_rate")) < 0.35:
        reasons.append("split_fragility")
    if safe_float(row.get("top_symbol_trade_share")) > 0.60:
        reasons.append("one_symbol_fluke_risk")
    if safe_float(row.get("top_regime_trade_share")) > 0.82:
        reasons.append("one_regime_fluke_risk")
    if abs(min(safe_float(row.get("max_drawdown")), 0.0)) > 3500.0:
        reasons.append("giant_drawdown")
    return reasons

