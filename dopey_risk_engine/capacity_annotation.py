"""Capacity annotation: what capital scale could the paper evidence support?

Pure, annotation-only. The forward walk sizes ONE contract per position; that
tells you a strategy's direction and win/loss, but not whether it could hold
any real capital. A signal that only ever fires on contracts trading 3 lots a
day is untradeable at size no matter how good its hit rate looks.

For each position we estimate the largest contract count executable without
materially moving the market, under two conservative participation caps:

    contracts <= OI_PARTICIPATION_CAP  * entry_open_interest
    contracts <= VOL_PARTICIPATION_CAP * entry_day_volume

The binding (smaller) cap governs; premium notional = contracts * fill * 100.
These are deliberately conservative desk rules of thumb, not a market-impact
model - they answer "is this liquid enough to matter", not "what is the exact
slippage". Explicitly NOT a promotion input: capacity can only ever argue a
strategy is too small to bother with, never that it has an edge.
"""
from __future__ import annotations

from typing import Any

CAPACITY_VERSION = "dopey-capacity-annotation-v1"
OPTION_CONTRACT_MULTIPLIER = 100
OI_PARTICIPATION_CAP = 0.01   # <=1% of resting open interest
VOL_PARTICIPATION_CAP = 0.05  # <=5% of the day's contract volume
# Below this executable contract count the position is "thin" - real capital
# could not participate meaningfully even once.
THIN_CONTRACT_FLOOR = 5


def position_capacity(
    entry_fill: float,
    entry_volume: int,
    entry_open_interest: int,
) -> dict[str, Any]:
    """Executable-contract and premium-notional capacity for one position."""
    volume = max(int(entry_volume), 0)
    open_interest = max(int(entry_open_interest), 0)
    fill = max(float(entry_fill), 0.0)
    oi_cap_contracts = int(OI_PARTICIPATION_CAP * open_interest)
    vol_cap_contracts = int(VOL_PARTICIPATION_CAP * volume)
    executable_contracts = min(oi_cap_contracts, vol_cap_contracts)
    binding = (
        "open_interest"
        if oi_cap_contracts <= vol_cap_contracts
        else "day_volume"
    )
    premium_notional = executable_contracts * fill * OPTION_CONTRACT_MULTIPLIER
    return {
        "executable_contracts": executable_contracts,
        "binding_constraint": binding,
        "oi_cap_contracts": oi_cap_contracts,
        "volume_cap_contracts": vol_cap_contracts,
        "premium_notional_usd": round(premium_notional, 2),
        "thin_liquidity": executable_contracts < THIN_CONTRACT_FLOOR,
    }


def book_capacity(position_capacities: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate: total premium-notional capacity and the binding thin count."""
    if not position_capacities:
        return {
            "capacity_version": CAPACITY_VERSION,
            "positions_annotated": 0,
            "total_premium_notional_usd": 0.0,
            "min_executable_contracts": 0,
            "thin_liquidity_position_count": 0,
            "participation_caps": {
                "open_interest": OI_PARTICIPATION_CAP,
                "day_volume": VOL_PARTICIPATION_CAP,
            },
            "capacity_annotation_not_a_promotion_input": True,
        }
    executable = [record["executable_contracts"] for record in position_capacities]
    return {
        "capacity_version": CAPACITY_VERSION,
        "positions_annotated": len(position_capacities),
        "total_premium_notional_usd": round(
            sum(record["premium_notional_usd"] for record in position_capacities), 2
        ),
        "min_executable_contracts": min(executable),
        "thin_liquidity_position_count": sum(
            1 for record in position_capacities if record["thin_liquidity"]
        ),
        "participation_caps": {
            "open_interest": OI_PARTICIPATION_CAP,
            "day_volume": VOL_PARTICIPATION_CAP,
        },
        "capacity_annotation_not_a_promotion_input": True,
    }
