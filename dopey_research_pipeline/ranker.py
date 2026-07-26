"""Dopey pipeline contract ranking: deterministic research ranker for the paper pipeline.

Extends dopey_options.contract_ranker with a richer deterministic blend used by the research
pipeline: liquidity score, spread width, volume, open interest, delta range, IV context, and a
slippage estimate. Output is deterministic ranked candidates. No network; no live exec.
"""
from __future__ import annotations

from dopey_options.ontology import OptionChain, OptionContract
from dopey_options.liquidity_engine import liquidity_score


def slippage_estimate(contract: OptionContract) -> float:
    """Deterministic naive slippage estimate = half the bid/ask spread (in price units)."""
    if contract.bid <= 0 or contract.ask <= 0:
        return round(contract.last * 0.05, 6)
    return round((contract.ask - contract.bid) / 2.0, 6)


def in_target_delta(contract: OptionContract, lo: float = 0.30, hi: float = 0.70) -> float:
    """Return 1.0 if |delta| is within the target convexity band, else 0.0."""
    d = abs(contract.delta)
    return 1.0 if lo <= d <= hi else 0.0


def iv_context_score(contract: OptionContract, iv_floor: float = 0.10, iv_ceiling: float = 0.25) -> float:
    """Return 1.0 if IV is within a reasonable research band, scaled down outside it."""
    if iv_floor <= contract.iv <= iv_ceiling:
        return 1.0
    if contract.iv < iv_floor:
        return max(0.0, contract.iv / iv_floor)
    return max(0.0, iv_ceiling / contract.iv)


def rank_pipeline_candidates(chain: OptionChain) -> list[dict]:
    """Deterministic ranked candidate list. Each entry: {symbol, score, liquidity, spread,
    slippage, delta, iv, open_interest, volume}. Highest score first."""
    rows = []
    for c in chain.contracts:
        liq = liquidity_score(c)
        spread = c.spread_pct()
        slip = slippage_estimate(c)
        delta_ok = in_target_delta(c)
        iv_ok = iv_context_score(c)
        # blend: liquidity dominant, then delta/iv fit, penalize wide spread + slippage
        score = (
            0.40 * liq
            + 0.20 * delta_ok
            + 0.15 * iv_ok
            + 0.10 * min(c.open_interest / 40000.0, 1.0)
            + 0.10 * min(c.volume / 9000.0, 1.0)
            + 0.05 * (1.0 - min(spread, 1.0))
            - 0.05 * min(slip, 1.0)
        )
        rows.append({
            "symbol": c.symbol,
            "option_type": c.option_type,
            "strike": c.strike,
            "expiry": c.expiry,
            "score": round(score, 6),
            "liquidity": liq,
            "spread_pct": spread,
            "slippage": slip,
            "delta": c.delta,
            "iv": c.iv,
            "open_interest": c.open_interest,
            "volume": c.volume,
            "bid": c.bid,
            "ask": c.ask,
            "mid": c.mid(),
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows
