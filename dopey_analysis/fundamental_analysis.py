"""Dopey fundamental analysis layer: deterministic fundamental-context scoring.

DEFERRED (real data): earnings calendar, SEC filing feed, analyst revision feed, sector/peer
comparison. No network. Implements: earnings/filing event risk, valuation context, growth
quality, analyst revisions, sector/peer, fundamental regime, company event risk.
"""
from __future__ import annotations

from .models import FundamentalContext


def score_fundamental(ctx: FundamentalContext) -> float:
    """Aggregate fundamental layer score in 0..1. Higher = fundamental tailwind."""
    s = (
        0.25 * ctx.fundamental_support_score
        + 0.20 * ctx.growth_quality_score
        + 0.15 * ctx.valuation_context_score
        + 0.15 * ctx.analyst_revision_score
        + 0.15 * ctx.sector_peer_score
        - 0.15 * ctx.earnings_risk_score
        - 0.10 * ctx.filing_event_score
    )
    return round(max(0.0, min(1.0, s)), 6)
