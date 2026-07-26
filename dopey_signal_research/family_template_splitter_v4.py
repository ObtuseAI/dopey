"""V4 family template splitter.

Splits the V3 continuation and volume families into 4+4 subfamilies so
the tournament cannot collapse them into a single cohort. Each
subfamily has its own stable family ID, candidate quota, symbol quota,
sector quota, and separate tournament label.
"""
from __future__ import annotations

import hashlib
from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_common import is_quarantined_signature
from dopey_autonomy.signal_research_v3_common import STABLE_FAMILY_CONTINUATION, STABLE_FAMILY_VOLUME
from dopey_autonomy.signal_research_v4_common import (
    FAMILY_SPLIT_PATH,
    FAMILY_SPLIT_PROOF_PATH,
    FAMILY_SPLIT_QUALITY_FLAGS_PATH,
    FAMILY_SPLIT_SUMMARY_PATH,
    RESEARCH_V4_ROOT,
    V4_CONTINUATION_SUBFAMILIES,
    V4_VOLUME_SUBFAMILIES,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_signal_research.volume_family_rescue_v4 import run_volume_family_rescue


def run_family_template_splitter_v4() -> dict[str, object]:
    RESEARCH_V4_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    quality_flags: list[dict[str, object]] = []
    type_counter: Counter[str] = Counter()
    quarantine_overlap = 0

    for sub in V4_CONTINUATION_SUBFAMILIES:
        records.append(_split_record(STABLE_FAMILY_CONTINUATION, sub, "continuation", subfamily_quota=6500, symbol_quota=70, sector_quota=10, tournament_label=f"continuation::{sub.split('|', 1)[1] if '|' in sub else sub}"))
        type_counter["continuation"] += 1
    for sub in V4_VOLUME_SUBFAMILIES:
        records.append(_split_record(STABLE_FAMILY_VOLUME, sub, "volume", subfamily_quota=6500, symbol_quota=70, sector_quota=10, tournament_label=f"volume::{sub.split('|', 1)[1] if '|' in sub else sub}"))
        type_counter["volume"] += 1

    for record in records:
        if is_quarantined_signature(str(record.get("stable_subfamily_id", ""))):
            quarantine_overlap += 1
            quality_flags.append(record_with_hash({"artifact_type": "family_template_splitter_quality_flag_v4", "flag_id": "quarantine_overlap", "stable_subfamily_id": record.get("stable_subfamily_id"), **live_safety_fields()}, "record_hash"))

    volume_rescue = run_volume_family_rescue()
    volume_status = str(volume_rescue.get("volume_rescue_status", ""))

    summary = {
        "artifact_type": "family_template_splitter_v4_summary",
        "family_template_splitter_v4_version": "dopey-family-template-splitter-v4",
        "family_template_splitter_status": "family_template_splitter_complete_v4",
        "continuation_subfamily_count": len(V4_CONTINUATION_SUBFAMILIES),
        "volume_subfamily_count": len(V4_VOLUME_SUBFAMILIES),
        "total_subfamily_count": len(V4_CONTINUATION_SUBFAMILIES) + len(V4_VOLUME_SUBFAMILIES),
        "volume_rescue_enabled": True,
        "volume_rescue_status": volume_status,
        "separate_tournament_labels_enabled": True,
        "quarantine_overlap_count": quarantine_overlap,
        "type_counts": dict(type_counter),
        "public_data_only": True,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(FAMILY_SPLIT_SUMMARY_PATH, summary)
    write_jsonl_file(FAMILY_SPLIT_PATH, records)
    write_jsonl_file(FAMILY_SPLIT_QUALITY_FLAGS_PATH, quality_flags)
    write_stage_proof(FAMILY_SPLIT_PROOF_PATH, "family-template-splitter-v4", str(summary["family_template_splitter_status"]), summary)
    return {**summary, "artifact_paths": {"family_template_splitter_v4_summary": str(FAMILY_SPLIT_SUMMARY_PATH)}, "volume_rescue": volume_rescue}


def _split_record(stable_family_id: str, subfamily_id: str, family_type: str, *, subfamily_quota: int, symbol_quota: int, sector_quota: int, tournament_label: str) -> dict[str, object]:
    return record_with_hash(
        {
            "artifact_type": "family_template_split_v4",
            "split_id": f"famsplit-{hashlib.sha256(subfamily_id.encode()).hexdigest()[:12]}",
            "stable_family_id": stable_family_id,
            "stable_subfamily_id": subfamily_id,
            "family_type": family_type,
            "candidate_quota": subfamily_quota,
            "symbol_quota": symbol_quota,
            "sector_quota": sector_quota,
            "tournament_label": tournament_label,
            "separate_tournament_label": True,
            "dte_default": 14,
            "moneyness_default": "1pct_otm",
            "exit_policy_default": "trend_follow",
            "public_data_only": True,
            **live_safety_fields(),
        },
        "record_hash",
    )
