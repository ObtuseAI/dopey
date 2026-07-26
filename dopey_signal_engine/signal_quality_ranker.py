"""Rank aggressive signal candidates by asymmetry, confidence, and risk."""
from __future__ import annotations

from dopey_wealth_engine.common import stable_hash


def rank_signal_candidates(candidates: list[dict]) -> list[dict]:
    ranked: list[dict] = []
    sorted_candidates = sorted(candidates, key=_score, reverse=True)
    for rank, candidate in enumerate(sorted_candidates, start=1):
        record = {
            "artifact_type": "signal_quality_ranking",
            "rank": rank,
            "signal_id": candidate["signal_id"],
            "symbol": candidate["symbol"],
            "trade_intent": candidate["trade_intent"],
            "setup_family": candidate["setup_family"],
            "quality_score": round(_score(candidate), 6),
            "paper_trade_candidate": candidate["trade_intent"] in {"long_call", "long_put"} and _score(candidate) >= 0.45,
            "paper_only": True,
            "live_blocked": True,
        }
        record["record_hash"] = stable_hash(record)
        ranked.append(record)
    return ranked


def _score(candidate: dict) -> float:
    if candidate["trade_intent"] == "no_trade":
        return 0.1
    return (
        float(candidate["confidence_score"]) * 0.4
        + float(candidate["asymmetry_score"]) * 0.35
        + float(candidate["liquidity_proxy_score"]) * 0.15
        - float(candidate["risk_score"]) * 0.25
        + (0.05 if candidate["data_tier"] in {"paper_trading", "evidence_grade"} else 0.0)
    )

