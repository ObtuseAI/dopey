"""Cohort regime tournament V4 — scores each cohort under each regime."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.public_champion_common import (
    group_records,
    pnl_metrics,
    record_with_hash,
    safe_float,
)

from dopey_strategy_cohorts.strategy_cohort_models import COHORT_LEVELS


def build_public_cohort_regime_scores_v4(trades: list[dict[str, object]]) -> list[dict[str, object]]:
    scores: list[dict[str, object]] = []
    for level in COHORT_LEVELS:
        groups = group_records(trades, level)
        for cohort_id, records in groups.items():
            regime_groups = group_records(records, "regime")
            for regime, regime_records in regime_groups.items():
                metrics = pnl_metrics(regime_records)
                scores.append(record_with_hash({
                    "artifact_type": "public_cohort_regime_score_v4",
                    "cohort_level": level,
                    "cohort_id": cohort_id,
                    "regime": regime,
                    **metrics,
                    "public_data_only": all(str(r.get("market_data_source_type", "")).startswith("public") for r in regime_records),
                    "live_trading_enabled": False,
                }, "record_hash"))
    return scores


def regime_survival_for(records: list[dict[str, object]]) -> dict[str, object]:
    regime_groups = group_records(records, "regime")
    survival: dict[str, object] = {}
    for regime, regime_records in regime_groups.items():
        metrics = pnl_metrics(regime_records)
        survival[str(regime)] = {
            "sample_count": metrics["sample_count"],
            "net_pnl": metrics["net_pnl"],
            "survived": bool(metrics["sample_count"] >= 3 and safe_float(metrics["net_pnl"]) > 0.0),
        }
    return survival
