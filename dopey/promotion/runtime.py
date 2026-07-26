"""Autonomous promotion matrix orchestration with three mandatory gates."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from dopey.protocols.identity import canonical_hash

from .gates import (
    evaluate_strategy_promotion,
    evaluate_symbol_promotion,
    evaluate_symbol_strategy_promotion,
)
from .schema import (
    PromotionThresholds,
    StrategyPromotionEvidence,
    SymbolPromotionEvidence,
    SymbolStrategyPromotionEvidence,
)


def _unique_index(records: Sequence[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for record in records:
        identifier = str(record[key])
        if identifier in output:
            raise ValueError(f"promotion matrix contains a duplicate identifier: key={key}, value={identifier}")
        output[identifier] = record
    return output


def build_autonomous_promotion_matrix(
    symbols: Sequence[SymbolPromotionEvidence],
    strategies: Sequence[StrategyPromotionEvidence],
    pairs: Sequence[SymbolStrategyPromotionEvidence],
    thresholds: PromotionThresholds,
) -> dict[str, Any]:
    symbol_gates = [evaluate_symbol_promotion(record, thresholds) for record in symbols]
    strategy_gates = [evaluate_strategy_promotion(record, thresholds) for record in strategies]
    symbol_index = _unique_index(symbol_gates, "subject_id")
    strategy_index = _unique_index(strategy_gates, "subject_id")
    pair_gates: list[dict[str, Any]] = []
    seen_pairs: set[str] = set()
    for evidence in pairs:
        symbol_id = evidence["symbol_id"]
        strategy_id = evidence["strategy_id"]
        pair_id = f"{symbol_id}::{strategy_id}"
        if pair_id in seen_pairs:
            raise ValueError(f"promotion matrix contains a duplicate pair: pair_id={pair_id}")
        if symbol_id not in symbol_index or strategy_id not in strategy_index:
            raise ValueError(
                "promotion pair references missing component evidence: "
                f"pair_id={pair_id}, symbol_present={symbol_id in symbol_index}, "
                f"strategy_present={strategy_id in strategy_index}"
            )
        seen_pairs.add(pair_id)
        pair_gates.append(
            evaluate_symbol_strategy_promotion(
                evidence,
                symbol_index[symbol_id],
                strategy_index[strategy_id],
                thresholds,
            )
        )
    activated_pairs = sorted(
        str(record["subject_id"])
        for record in pair_gates
        if record["automatic_research_activation_allowed"] is True
    )
    body: dict[str, Any] = {
        "artifact_type": "autonomous_research_promotion_matrix",
        "matrix_version": "dopey-autonomous-research-promotion-matrix-v1",
        "threshold_version": thresholds["threshold_version"],
        "symbol_gates": symbol_gates,
        "strategy_gates": strategy_gates,
        "symbol_strategy_gates": pair_gates,
        "activated_symbol_ids": sorted(
            key for key, record in symbol_index.items() if record["automatic_research_activation_allowed"] is True
        ),
        "activated_strategy_ids": sorted(
            key for key, record in strategy_index.items() if record["automatic_research_activation_allowed"] is True
        ),
        "activated_symbol_strategy_ids": activated_pairs,
        "automatic_research_activation_count": len(activated_pairs),
        "human_review_required": False,
        "candidate_self_activation_allowed": False,
        "backtest_only_activation_allowed": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    return {**body, "matrix_hash": canonical_hash(body)}
