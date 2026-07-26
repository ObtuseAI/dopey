"""Research universe coverage V2."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.public_champion_common import active_rows_by_symbol, is_test_symbol, sector_for_symbol


TARGET_SECTORS = (
    "broad_etf", "technology", "semiconductors", "financials", "energy",
    "healthcare", "consumer_discretionary", "consumer_staples", "industrials",
    "defense_aerospace", "software", "cloud", "cyber", "rates_proxy",
)


def build_universe(min_rows: int = 200, target_symbols: int = 100) -> dict[str, object]:
    rows_by_symbol = active_rows_by_symbol()
    eligible = [
        symbol for symbol, rows in rows_by_symbol.items()
        if len(rows) >= min_rows and not is_test_symbol(symbol)
    ]
    eligible.sort(key=lambda symbol: len(rows_by_symbol[symbol]), reverse=True)
    selected = eligible[:target_symbols]
    sectors = Counter(sector_for_symbol(symbol) for symbol in selected)
    return {
        "symbols": selected,
        "symbol_count": len(selected),
        "sector_counts": dict(sectors),
        "sector_count": len(sectors),
    }
