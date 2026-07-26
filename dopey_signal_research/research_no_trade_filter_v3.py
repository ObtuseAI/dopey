"""No-trade filters for V3 selective candidate generation."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import record_with_hash


def evaluate_no_trade_filters_v3(features: dict[str, dict[str, float]], template_id: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    risk = features.get("risk_filter", {})
    regime = features.get("regime", {})
    volume = features.get("volume", {})
    reversal = features.get("reversal", {})

    if float(risk.get("avoid_thin_volume", 0.0)) >= 1.0:
        reasons.append("low_liquidity")
    if float(risk.get("avoid_overextended_move", 0.0)) >= 1.0:
        reasons.append("overextended_entry")
    if float(risk.get("avoid_poor_regime_alignment", 0.0)) >= 1.0:
        reasons.append("regime_conflict")
    if float(regime.get("volatility_regime", 0.0)) >= 1.0 and float(regime.get("risk_on_proxy", 0.0)) < 1.0:
        reasons.append("volatility_shock_regime")
    if float(volume.get("volume_climax", 0.0)) >= 1.0 and "volume" in template_id:
        reasons.append("exhaustion_spike")
    if float(reversal.get("overextension", 0.0)) > 0.06:
        reasons.append("overextended_gap")

    return len(reasons) == 0, reasons


def no_trade_record(candidate_id: str, reasons: list[str]) -> dict[str, object]:
    return record_with_hash(
        {
            "artifact_type": "research_no_trade_filter_record_v3",
            "candidate_id": candidate_id,
            "no_trade_filter_reasons": reasons,
            "trade_intent": "no_trade",
            "public_data_only": True,
            **live_safety_fields(),
        },
        "record_hash",
    )
