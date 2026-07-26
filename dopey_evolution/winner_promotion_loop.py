"""Paper winner promotion loop."""
from __future__ import annotations

from dopey_wealth_engine.common import stable_hash


def build_winner_promotion_loop(scores: list[dict], throttles: list[dict]) -> list[dict]:
    throttled_targets = {str(record["target"]) for record in throttles}
    records: list[dict] = []
    for score in scores:
        pnl = float(score["net_paper_pnl"])
        if pnl <= 0:
            continue
        level = "paper_champion" if pnl > 1_500 and str(score["strategy_family"]) not in throttled_targets else "paper_active"
        record = {
            "artifact_type": "winner_promotion_loop",
            "strategy_family": score["strategy_family"],
            "promotion_level": level,
            "net_paper_pnl": score["net_paper_pnl"],
            "market_data_source_type": score.get("market_data_source_type", "fixture_fallback"),
            "public_data_paper_champion": score.get("market_data_source_type", "") != "fixture_fallback" and level == "paper_champion",
            "fixture_only_champion": score.get("market_data_source_type", "fixture_fallback") == "fixture_fallback" and level == "paper_champion",
            "fragility_demotion": str(score["strategy_family"]) in throttled_targets,
            "live_gate_candidate": level == "paper_champion",
            "direct_live_promotion_allowed": False,
            "paper_only": True,
            "live_blocked": True,
        }
        record["record_hash"] = stable_hash(record)
        records.append(record)
    return records
