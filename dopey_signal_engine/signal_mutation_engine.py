"""Mutation engine for promising aggressive signal candidates."""
from __future__ import annotations

from dopey_wealth_engine.common import stable_hash


def mutate_signal_candidates(candidates: list[dict]) -> list[dict]:
    mutations: list[dict] = []
    for candidate in candidates:
        if candidate["trade_intent"] == "no_trade":
            continue
        if float(candidate["confidence_score"]) < 0.6:
            continue
        record = {
            "artifact_type": "signal_mutation_record",
            "parent_signal_id": candidate["signal_id"],
            "symbol": candidate["symbol"],
            "setup_family": candidate["setup_family"],
            "mutation_type": "wider_invalidation_higher_target",
            "mutated_target_move": round(float(candidate["target_move"]) * 1.15, 4),
            "mutated_risk_score": round(min(1.0, float(candidate["risk_score"]) + 0.04), 4),
            "paper_only": True,
            "live_blocked": True,
        }
        record["record_hash"] = stable_hash(record)
        mutations.append(record)
    return mutations

