"""Dopey liquidity engine: deterministic liquidity scoring (research stub, no network).

DOPEY-native stub. Scores contract liquidity from open interest, volume, and bid/ask spread.
Higher is better; used by contract ranker and the aggression gate (weak liquidity penalized).
"""
from __future__ import annotations

from .ontology import OptionContract


FORWARD_ENTRY_MIN_OPEN_INTEREST = 25
FORWARD_ENTRY_MIN_VOLUME = 5
FORWARD_ENTRY_MAX_RELATIVE_SPREAD = 0.10
ENTRY_POLICY_VERSION = "dopey-forward-entry-quality-v2"
FORWARD_EXIT_MAX_RELATIVE_SPREAD = 0.25
EXIT_POLICY_VERSION = "dopey-forward-exit-quality-v3"


def quote_relative_spread(bid: float, ask: float) -> float:
    if bid < 0.0 or ask < bid:
        raise ValueError(f"invalid option quote for spread calculation: bid={bid}, ask={ask}")
    midpoint = (bid + ask) / 2.0
    return (ask - bid) / midpoint if midpoint > 0.0 else float("inf")


def forward_entry_liquidity_rejection_reasons(
    bid: float,
    ask: float,
    volume: int,
    open_interest: int,
) -> tuple[str, ...]:
    reasons: list[str] = []
    spread = quote_relative_spread(bid, ask)
    if bid < 0.05:
        reasons.append("entry_bid_below_0_05")
    if ask <= 0.0:
        reasons.append("entry_ask_not_positive")
    if spread > FORWARD_ENTRY_MAX_RELATIVE_SPREAD:
        reasons.append("entry_relative_spread_above_10pct")
    if volume < FORWARD_ENTRY_MIN_VOLUME:
        reasons.append("entry_volume_below_5")
    if open_interest < FORWARD_ENTRY_MIN_OPEN_INTEREST:
        reasons.append("entry_open_interest_below_25")
    return tuple(reasons)


def forward_exit_quote_rejection_reasons(bid: float, ask: float) -> tuple[str, ...]:
    spread = quote_relative_spread(bid, ask)
    if spread > FORWARD_EXIT_MAX_RELATIVE_SPREAD:
        return ("exit_relative_spread_above_25pct",)
    return ()


def liquidity_score(contract: OptionContract) -> float:
    spread = contract.spread_pct()
    spread_penalty = 1.0 - min(spread, 1.0)
    oi = min(contract.open_interest / 1000.0, 1.0)
    vol = min(contract.volume / 500.0, 1.0)
    return round(0.4 * oi + 0.3 * vol + 0.3 * spread_penalty, 6)
