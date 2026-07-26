"""Profit factor repair scorer V3."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import record_with_hash


def profit_factor_repair_score(candidate: dict[str, object]) -> float:
    features = candidate.get("feature_vector", {})
    if not isinstance(features, dict):
        return 0.0
    score = 0.5
    if candidate.get("source_mutation_id"):
        score += 0.1
    risk = features.get("risk_filter", {}) if isinstance(features.get("risk_filter"), dict) else {}
    if float(risk.get("avoid_overextended_move", 0.0)) < 1.0:
        score += 0.1
    volume = features.get("volume", {}) if isinstance(features.get("volume"), dict) else {}
    if float(volume.get("volume_percentile", 0.0)) >= 0.7:
        score += 0.05
    if not candidate.get("no_trade_filter_reasons"):
        score += 0.15
    family = str(candidate.get("stable_family_template_id", ""))
    if "volume" in family:
        score += 0.1
    return round(min(score, 1.0), 6)


def score_profit_factor_row(candidate: dict[str, object]) -> dict[str, object]:
    return record_with_hash(
        {
            "artifact_type": "profit_factor_repair_score_v3",
            "candidate_id": candidate.get("candidate_id", ""),
            "stable_family_template_id": candidate.get("stable_family_template_id", ""),
            "profit_factor_repair_score": profit_factor_repair_score(candidate),
            "source_mutation_id": candidate.get("source_mutation_id", ""),
            **live_safety_fields(),
        },
        "record_hash",
    )
