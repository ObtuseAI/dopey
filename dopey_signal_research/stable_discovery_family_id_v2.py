"""Stable discovery family ID repair V2."""
from __future__ import annotations

import hashlib

from dopey_autonomy.signal_research_v2_common import (
    is_generic_label,
    is_quarantined_signature,
    stable_family_id_from_label,
)


def assign_stable_ids(original_label: str, direction: str = "bullish") -> dict[str, str]:
    discovery_family_id = stable_family_id_from_label(original_label)
    seed_hash = hashlib.sha256(discovery_family_id.encode()).hexdigest()[:12]
    return {
        "discovery_family_id": discovery_family_id,
        "research_family_id": discovery_family_id,
        "watchlist_seed_id": f"wl-seed-{seed_hash}",
        "cohort_id": discovery_family_id.split("|")[0] if "|" in discovery_family_id else discovery_family_id,
        "directional_cohort_id": f"{direction}|{discovery_family_id.split('|')[0]}",
        "regime_cohort_id": "broad_market",
        "symbol_cluster_cohort_id": "multi_sector_v2",
        "original_label": original_label,
        "generic_label_repaired": is_generic_label(original_label),
        "quarantine_overlap": is_quarantined_signature(discovery_family_id),
    }
