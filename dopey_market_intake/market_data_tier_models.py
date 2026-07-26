"""Tier doctrine for market-vision and paper-trading data."""
from __future__ import annotations


DATA_TIERS = ["market_vision", "research_sandbox", "paper_trading", "evidence_grade"]
LIVE_GATE_DISABLED = {
    "live_trading_enabled": False,
    "broker_connection_used": False,
    "credentials_created": False,
    "env_created": False,
}


def assign_data_tier(row_count: int, sanity_pass: bool, continuity_pass: bool, freshness_pass: bool, provenance_strength: str) -> str:
    if not sanity_pass:
        return "market_vision"
    if row_count < 120:
        return "market_vision"
    if row_count < 500 or not continuity_pass:
        return "research_sandbox"
    if freshness_pass and provenance_strength in {"public_no_key", "local_cache"}:
        return "paper_trading"
    return "research_sandbox"


def tier_permissions(data_tier: str) -> dict[str, bool]:
    return {
        "market_vision_allowed": data_tier in {"market_vision", "research_sandbox", "paper_trading", "evidence_grade"},
        "research_sandbox_allowed": data_tier in {"research_sandbox", "paper_trading", "evidence_grade"},
        "paper_trading_allowed": data_tier in {"paper_trading", "evidence_grade"},
        "formal_claim_allowed": data_tier == "evidence_grade",
        "live_gate_allowed": False,
    }
