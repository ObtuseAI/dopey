"""Map autonomous signals to long-premium options research intents."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import stable_hash


ALLOWED_INTENTS = frozenset({"long_call", "long_put", "no_trade"})


def build_autonomous_strategy_candidates(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for signal in signals:
        intent = _intent_for(signal)
        record = {
            "artifact_type": "autonomous_strategy_candidates",
            "strategy_id": f"strategy-{signal['signal_id']}",
            "source_signal_id": signal["signal_id"],
            "intent": intent,
            "allowed_intent": intent in ALLOWED_INTENTS,
            "strategy_family": "long_premium_options",
            "same_day_churn_default_allowed": False,
            "paper_research_only": True,
            "strategy_promotion_allowed": False,
            "paper_only": True,
            "live_blocked": True,
        }
        record["strategy_hash"] = stable_hash(record)
        records.append(record)
    return records


def _intent_for(signal: dict[str, Any]) -> str:
    if signal["data_tier"] == "no_accepted_real_data" or signal["direction"] == "neutral":
        return "no_trade"
    if signal["direction"] == "bullish":
        return "long_call"
    if signal["direction"] == "bearish":
        return "long_put"
    return "no_trade"

