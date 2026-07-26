"""Research coverage penalty V2."""
from __future__ import annotations

from dopey_autonomy.signal_research_v2_common import MIN_BREAKTHROUGH_SECTORS, MIN_BREAKTHROUGH_SYMBOLS, is_quarantined_signature


def coverage_penalty(row: dict[str, object]) -> tuple[float, list[str]]:
    penalties: list[str] = []
    score = 1.0
    symbol_count = int(row.get("symbol_count", 0))
    sector_count = int(row.get("sector_count", 0))
    family_id = str(row.get("family_id", row.get("discovery_family_id", "")))
    if symbol_count < MIN_BREAKTHROUGH_SYMBOLS:
        penalties.append("symbol_count_below_minimum")
        score -= 0.35
    if sector_count < MIN_BREAKTHROUGH_SECTORS:
        penalties.append("sector_count_below_minimum")
        score -= 0.25
    if symbol_count == 1:
        penalties.append("one_symbol_dependence")
        score -= 0.20
    if sector_count == 1:
        penalties.append("one_sector_dependence")
        score -= 0.15
    if is_quarantined_signature(family_id):
        penalties.append("failed_family_quarantine_overlap")
        score = 0.0
    return max(score, 0.0), penalties
