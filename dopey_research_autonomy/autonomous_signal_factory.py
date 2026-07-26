"""Generate autonomous paper-only signal candidates from accepted data tiers."""
from __future__ import annotations

from typing import Any

from dopey_autonomy.autonomy_common import stable_hash


SIGNAL_FAMILIES = ["momentum", "breakout", "fakeout_reversal", "trend_pullback", "relative_strength", "volatility_regime", "market_regime", "event_risk_avoidance"]


def build_autonomous_signal_candidates(valid_real_dataset: bool) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, family in enumerate(SIGNAL_FAMILIES):
        direction = "bullish" if family in {"momentum", "breakout", "relative_strength"} else ("bearish" if family == "fakeout_reversal" else "neutral")
        record = {
            "artifact_type": "autonomous_signal_candidates",
            "signal_id": f"autonomous-signal-{family}",
            "family": family,
            "direction": direction,
            "data_tier": "accepted_open_ohlcv_only" if valid_real_dataset else "no_accepted_real_data",
            "evidence_label": "accepted_real_data" if valid_real_dataset else "blocked_no_real_evidence",
            "signal_allowed_for_research": valid_real_dataset,
            "rank": index + 1,
            "paper_only": True,
            "live_blocked": True,
        }
        record["signal_hash"] = stable_hash(record)
        records.append(record)
    return records

