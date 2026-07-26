"""Dopey microstructure analysis layer: deterministic microstructure scoring.

DEFERRED (real data): live quote pressure, order-book imbalance, intraday liquidity-window
feed. No network. Implements: spread quality, liquidity, slippage sensitivity, volume/OI
anomalies, quote stability, contract fillability, execution-quality attribution.
"""
from __future__ import annotations

from .models import MicrostructureContext


def score_microstructure(ctx: MicrostructureContext) -> float:
    """Aggregate microstructure layer score in 0..1. Higher = healthier execution environment."""
    s = (
        0.25 * ctx.spread_quality_score
        + 0.25 * ctx.liquidity_score
        + 0.15 * ctx.contract_fillability_score
        + 0.15 * ctx.quote_stability_score
        - 0.10 * ctx.slippage_sensitivity_score
        - 0.10 * ctx.volume_oi_anomaly_score
    )
    return round(max(0.0, min(1.0, s)), 6)
