"""Pure portfolio-concentration policy for forward paper positions."""
from __future__ import annotations

from collections import Counter
from typing import Any

from dopey_autonomy.public_champion_common import sector_for_symbol
from dopey_risk_engine.forward_entry_guard import (
    MAX_SYMBOL_PREMIUM_SHARE,
    premium_at_risk_by_symbol,
    top_symbol_premium_share,
)


# v3 (2026-07-22): book capacity raised 12 -> 20 for forward-evidence velocity.
# The readiness gate needs 100 validated closes across >=10 entry-date cohorts;
# at cap 12 the book saturated (266 open-cap entry rejections in one marking run)
# and the ETA was ~25 trading days. A 20-position book with the ~3-session
# turnover yields ~6-7 closes/day (~15 trading days), with sector/direction caps
# scaled to keep proportional diversity. Entry quality floors, exit policy, and
# ALL validation thresholds (sample size, cohort minimum, integrity classes)
# are unchanged - this widens the paper book, never the evidence bar.
MAX_OPEN_POSITIONS = 20
MAX_NEW_POSITIONS_PER_RUN = 8
MAX_POSITIONS_PER_SECTOR = 4
MAX_POSITIONS_PER_DIRECTION = 13
PORTFOLIO_POLICY_VERSION = "dopey-forward-portfolio-concentration-v3"


def strategy_direction(strategy: str) -> str:
    if strategy == "long_call":
        return "bullish"
    if strategy == "long_put":
        return "bearish"
    raise ValueError(f"unsupported forward-walk strategy: strategy={strategy}")


def portfolio_counts(
    positions: list[dict[str, Any]],
) -> tuple[set[str], Counter[str], Counter[str]]:
    symbols: set[str] = set()
    sectors: Counter[str] = Counter()
    directions: Counter[str] = Counter()
    for position in positions:
        symbol = str(position["symbol"])
        strategy = str(position["candidate_strategy"])
        symbols.add(symbol)
        sectors[str(position.get("entry_sector", sector_for_symbol(symbol)))] += 1
        directions[strategy_direction(strategy)] += 1
    return symbols, sectors, directions


def evaluate_forward_portfolio(positions: list[dict[str, Any]]) -> dict[str, Any]:
    symbols, sectors, directions = portfolio_counts(positions)
    premium_by_symbol = premium_at_risk_by_symbol(positions)
    top_premium_share = top_symbol_premium_share(positions)
    violations: list[str] = []
    if len(positions) > MAX_OPEN_POSITIONS:
        violations.append("portfolio_open_position_cap_breached")
    if len(positions) > len(symbols):
        violations.append("portfolio_duplicate_symbol_exposure")
    if any(count > MAX_POSITIONS_PER_SECTOR for count in sectors.values()):
        violations.append("portfolio_sector_cap_breached")
    if any(count > MAX_POSITIONS_PER_DIRECTION for count in directions.values()):
        violations.append("portfolio_direction_cap_breached")
    if top_premium_share > MAX_SYMBOL_PREMIUM_SHARE:
        violations.append("portfolio_symbol_premium_share_cap_breached")
    return {
        "portfolio_policy_version": PORTFOLIO_POLICY_VERSION,
        "open_position_count": len(positions),
        "unique_symbol_count": len(symbols),
        "duplicate_symbol_position_count": len(positions) - len(symbols),
        "sector_counts": dict(sorted(sectors.items())),
        "direction_counts": dict(sorted(directions.items())),
        "premium_at_risk_by_symbol": dict(sorted(premium_by_symbol.items())),
        "top_symbol_premium_share": round(top_premium_share, 6),
        "max_open_positions": MAX_OPEN_POSITIONS,
        "max_positions_per_sector": MAX_POSITIONS_PER_SECTOR,
        "max_positions_per_direction": MAX_POSITIONS_PER_DIRECTION,
        "max_symbol_premium_share": MAX_SYMBOL_PREMIUM_SHARE,
        "violation_reason_codes": violations,
        "portfolio_concentration_green": not violations,
        "paper_only": True,
        "live_blocked": True,
    }
