"""Holdout and split repair scorer V3."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import record_with_hash


def holdout_split_repair_score(candidate: dict[str, object]) -> tuple[float, float]:
    features = candidate.get("feature_vector", {})
    if not isinstance(features, dict):
        return 0.0, 0.0
    regime = features.get("regime", {}) if isinstance(features.get("regime"), dict) else {}
    rs = features.get("relative_strength", {}) if isinstance(features.get("relative_strength"), dict) else {}
    holdout = 0.4
    split_pass = 0.4
    if float(regime.get("risk_on_proxy", 0.0)) >= 1.0:
        holdout += 0.2
        split_pass += 0.15
    if float(rs.get("vs_spy", 0.0)) >= 0.0:
        holdout += 0.1
        split_pass += 0.1
    if not candidate.get("no_trade_filter_reasons"):
        holdout += 0.15
        split_pass += 0.15
    if candidate.get("source_mutation_id"):
        holdout += 0.1
        split_pass += 0.1
    return round(min(holdout, 1.0), 6), round(min(split_pass, 1.0), 6)


def score_holdout_split_row(candidate: dict[str, object]) -> dict[str, object]:
    holdout_score, split_score = holdout_split_repair_score(candidate)
    return record_with_hash(
        {
            "artifact_type": "holdout_split_repair_score_v3",
            "candidate_id": candidate.get("candidate_id", ""),
            "holdout_repair_score": holdout_score,
            "split_repair_score": split_score,
            "stable_family_template_id": candidate.get("stable_family_template_id", ""),
            **live_safety_fields(),
        },
        "record_hash",
    )
