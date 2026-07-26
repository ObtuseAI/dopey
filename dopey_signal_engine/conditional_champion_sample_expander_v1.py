"""Sample expansion target selection for conditional champion retune."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.public_champion_common import sector_for_symbol


def sample_expansion_targets(parents: list[str], rows_by_symbol: dict[str, list[dict[str, str]]]) -> dict[str, list[str]]:
    all_symbols = sorted(rows_by_symbol.keys())
    sector_symbols: dict[str, list[str]] = {}
    for symbol in all_symbols:
        sector_symbols.setdefault(sector_for_symbol(symbol), []).append(symbol)
    targets: dict[str, list[str]] = {}
    for parent in parents:
        targets[parent] = all_symbols[:60]
        underrepresented = sorted(sector_symbols.keys())[:8]
        for sector in underrepresented:
            targets[parent].extend(sector_symbols.get(sector, [])[:5])
        targets[parent] = sorted(set(targets[parent]))[:80]
    return targets
