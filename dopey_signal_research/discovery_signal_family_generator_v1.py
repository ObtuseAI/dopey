"""Discovery signal family generator V1."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_common import (
    FAMILY_REGISTRY_PATH,
    RESEARCH_ROOT,
    is_quarantined_signature,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file
from dopey_signal_research.discovery_signal_family_models_v1 import FAMILY_TEMPLATES, DiscoveryFamilyTemplate


CANDIDATES_PATH = RESEARCH_ROOT / "discovery_signal_family_candidates_v1.jsonl"
FILTER_HITS_PATH = RESEARCH_ROOT / "discovery_signal_family_negative_filter_hits_v1.jsonl"
SUMMARY_PATH = RESEARCH_ROOT / "discovery_signal_family_generator_v1_summary.json"
PROOF_PATH = RESEARCH_ROOT / "discovery_signal_family_generator_v1_proof.jsonl"


def run_discovery_signal_family_generator_v1() -> dict[str, object]:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    registry: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    filter_hits: list[dict[str, object]] = []
    overlap_count = 0
    direction_counts: Counter[str] = Counter()

    for template in FAMILY_TEMPLATES:
        overlap = is_quarantined_signature(template.family_id)
        if overlap:
            overlap_count += 1
            filter_hits.append(record_with_hash({
                "artifact_type": "discovery_signal_family_negative_filter_hit_v1",
                "family_id": template.family_id,
                "failed_family_overlap_risk": True,
                **live_safety_fields(),
            }, "record_hash"))
            continue
        direction_counts[template.direction] += 1
        record = family_record(template)
        registry.append(record)
        candidates.append(record)

    summary = {
        "artifact_type": "discovery_signal_family_generator_v1_summary",
        "discovery_signal_family_generator_version": "dopey-public-discovery-family-generator-v1",
        "discovery_signal_family_status": "discovery_families_generated",
        "candidate_family_count": len(candidates),
        "quarantine_overlap_count": overlap_count,
        "new_family_count": len(candidates),
        "bullish_family_count": direction_counts.get("bullish", 0),
        "bearish_family_count": direction_counts.get("bearish", 0),
        "no_trade_filter_count": direction_counts.get("no_trade", 0),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(FAMILY_REGISTRY_PATH, registry)
    write_jsonl_file(CANDIDATES_PATH, candidates)
    write_jsonl_file(FILTER_HITS_PATH, filter_hits)
    write_stage_proof(PROOF_PATH, "discovery-signal-family-generator-v1", str(summary["discovery_signal_family_status"]), summary)
    return {**summary, "artifact_paths": {"discovery_signal_family_generator_v1_summary": str(SUMMARY_PATH)}}


def family_record(template: DiscoveryFamilyTemplate) -> dict[str, object]:
    return record_with_hash({
        "artifact_type": "discovery_signal_family_registry_v1",
        "family_id": template.family_id,
        "direction": template.direction,
        "family_type": template.family_type,
        "feature_rules": [{"group": group, "feature": feature, "threshold": threshold} for group, feature, threshold in template.feature_rules],
        "exit_policy": template.exit_policy,
        "dte_bucket": template.dte,
        "moneyness_bucket": template.moneyness,
        "failed_family_overlap_risk": False,
        **live_safety_fields(),
    }, "record_hash")


def matches_family(features: dict[str, dict[str, float]], template: DiscoveryFamilyTemplate) -> bool:
    for group, feature, threshold in template.feature_rules:
        value = float(features.get(group, {}).get(feature, 0.0))
        if threshold >= 1.0:
            if value < threshold:
                return False
        elif threshold <= -1.0:
            if value > threshold:
                return False
        elif threshold >= 0:
            if value < threshold:
                return False
        else:
            if value > threshold:
                return False
    return True
