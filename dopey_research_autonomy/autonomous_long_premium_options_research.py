"""Long-call/long-put research intent construction."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import stable_hash


def build_long_premium_option_intents(strategies: list[dict[str, Any]], options_quote_data_available: bool) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for strategy in strategies:
        record = {
            "artifact_type": "autonomous_long_premium_option_intents",
            "intent_id": f"intent-{strategy['strategy_id']}",
            "strategy_id": strategy["strategy_id"],
            "intent": strategy["intent"],
            "option_side": "call" if strategy["intent"] == "long_call" else ("put" if strategy["intent"] == "long_put" else "none"),
            "pricing_mode": "quote_priced" if options_quote_data_available else "model_priced_or_blocked",
            "quote_priced_evidence_allowed": options_quote_data_available,
            "model_priced_research_allowed": not options_quote_data_available,
            "expiration_selection_mode": "research_only_multi_day_default",
            "zero_dte_lane": "special_research_guarded_not_default",
            "paper_only": True,
            "live_blocked": True,
            "strategy_promotion_allowed": False,
        }
        record["intent_hash"] = stable_hash(record)
        records.append(record)
    return records

