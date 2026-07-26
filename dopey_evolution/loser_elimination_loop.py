"""Paper loser elimination loop."""
from __future__ import annotations

from dopey_wealth_engine.common import stable_hash


def build_loser_elimination_loop(scores: list[dict]) -> list[dict]:
    records: list[dict] = []
    for score in scores:
        if float(score["net_paper_pnl"]) >= 0 and int(score["loss_streak"]) < 4:
            continue
        record = {
            "artifact_type": "loser_elimination_loop",
            "strategy_family": score["strategy_family"],
            "elimination_level": "dead" if float(score["net_paper_pnl"]) < -1_500 else "paper_shadow",
            "net_paper_pnl": score["net_paper_pnl"],
            "loss_streak": score["loss_streak"],
            "paper_only": True,
            "live_blocked": True,
        }
        record["record_hash"] = stable_hash(record)
        records.append(record)
    return records

