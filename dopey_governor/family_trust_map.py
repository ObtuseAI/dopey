"""Deterministic family and regime trust maps for the offline meta-governor.

Builds FamilyTrustProfile per strategy family and RegimeTrustProfile per known fixture
regime from the aggregated evidence. All math is deterministic fixture aggregation.
"""
from __future__ import annotations

from collections import defaultdict

from dopey_strategy_lab.regime_allocator import (
    build_regime_profiles,
    regime_class_for_tag,
)

from .meta_governor_models import FamilyTrustProfile, RegimeTrustProfile, StrategyProofProfile
from .proof_evidence_loader import EvidenceBundle
from .proof_quality import OVERFIT_RANK


FAMILY_TRUST_MAP_VERSION = "dopey-family-regime-trust-map-v1"

# Known fixture regime vocabulary (macro + walk-forward corpus).
KNOWN_REGIME_TAGS = [
    "bullish_breakout",
    "bearish_breakdown",
    "trend_vol_expansion",
    "event_vol_expansion",
    "pre_fomc_vol_expansion",
    "post_event_iv_crush",
    "chop_vol_compression",
    "low_liquidity_decay",
    "high_spread_bad_fill",
    "macro_shock_risk_off",
    "gap_reversal",
]

REGIME_REQUIRED_EVIDENCE = {
    "trend": ["walk_forward_replay", "tournament", "liquidity_slippage", "greeks_iv_validation"],
    "event_vol": ["iv_surface_skew_term", "macro_event_fixtures", "greeks_iv_validation", "pattern_fixture_intelligence"],
    "post_event_crush": ["iv_surface_skew_term", "greeks_iv_validation", "liquidity_slippage"],
    "bad_fill": ["liquidity_slippage", "tournament"],
    "macro_contradiction": ["macro_event_fixtures", "iv_surface_skew_term", "pattern_fixture_intelligence"],
}


def _family_best_worst(evidence: EvidenceBundle, family: str) -> tuple[list[str], list[str]]:
    best = list(evidence.champion.get("best_regimes_by_family", {}).get(family, []))
    worst = list(evidence.champion.get("worst_regimes_by_family", {}).get(family, []))
    if not best or not worst:
        for fp in evidence.ensemble.get("family_profiles", []):
            if fp.get("strategy_family") == family:
                best = best or list(fp.get("best_regimes", []))
                worst = worst or list(fp.get("worst_regimes", []))
                break
    return sorted(set(best)), sorted(set(worst))


def build_family_trust_profiles(evidence: EvidenceBundle,
                                 profiles: list[StrategyProofProfile]) -> list[FamilyTrustProfile]:
    """Aggregate per-family trust from proof profiles + champion/ensemble summaries."""
    overfit_summary = evidence.champion.get("overfit_summary", {}) or evidence.ensemble.get("overfit_summary", {})
    failure_by_family = dict(evidence.ensemble.get("failure_pressure_by_family", {}))
    family_weights = dict(evidence.ensemble.get("family_weights", {}))
    ensemble_profiles = {fp.get("strategy_family"): fp for fp in evidence.ensemble.get("family_profiles", [])}

    by_family: dict[str, list[StrategyProofProfile]] = defaultdict(list)
    for profile in profiles:
        by_family[profile.strategy_family].append(profile)

    # Map strategy-id-keyed overfit levels back to families via proof profiles.
    family_overfit_level: dict[str, str] = {}
    for profile in profiles:
        family_overfit_level[profile.strategy_family] = profile.overfit_level

    result: list[FamilyTrustProfile] = []
    families = set(by_family) | set(family_weights) | set(family_overfit_level)
    for family in sorted(families):
        items = by_family.get(family, [])
        avg_overfit = 0.0
        if items:
            avg_overfit = sum(p.overfit_rank for p in items) / len(items) / 3.0
        elif family in family_overfit_level:
            avg_overfit = OVERFIT_RANK.get(family_overfit_level.get(family, "high"), 3) / 3.0
        elif family in overfit_summary and isinstance(overfit_summary[family], str):
            avg_overfit = OVERFIT_RANK.get(overfit_summary[family], 3) / 3.0
        failure_pressure = failure_by_family.get(family, 0.0)
        ens = ensemble_profiles.get(family, {})
        # pressures (higher = worse)
        liquidity_pressure = round(1.0 - float(ens.get("best_score", 0.6)), 6) if ens else 0.4
        # derive from ensemble family profile fields if available
        greek_iv_pressure = round(max(0.0, 1.0 - (sum(float(p.greek_fit) for p in items) / len(items) if items else 0.6)), 6)
        macro_pressure = round(max(0.0, 1.0 - (sum(float(p.macro_fit) for p in items) / len(items) if items else 0.5)), 6)
        best_regimes, worst_regimes = _family_best_worst(evidence, family)
        ensemble_weight = family_weights.get(family, 0.0)

        # trust score rewards low pressure + ensemble support + low overfit.
        trust = round(
            0.30 * (1.0 - avg_overfit)
            + 0.20 * (1.0 - failure_pressure)
            + 0.15 * min(1.0, ensemble_weight * 2.0)
            + 0.15 * (1.0 - liquidity_pressure)
            + 0.10 * (1.0 - greek_iv_pressure)
            + 0.10 * (1.0 - macro_pressure),
            6,
        )
        trust = max(0.0, min(1.0, trust))

        if avg_overfit >= 0.9 or failure_pressure >= 0.45:
            attention = "starve"
            intensity = "none"
        elif trust >= 0.65:
            attention = "increase"
            intensity = "moderate"
        elif trust >= 0.45:
            attention = "hold"
            intensity = "low"
        else:
            attention = "reduce"
            intensity = "low"

        constraints: list[str] = []
        if avg_overfit >= 0.9:
            constraints.append("overfit_guard_required")
        if failure_pressure >= 0.40:
            constraints.append("failure_mode_reduction_required")
        if not best_regimes:
            constraints.append("regime_specialization_unknown")

        result.append(FamilyTrustProfile(
            strategy_family=family,
            trust_score=trust,
            best_regimes=best_regimes,
            worst_regimes=worst_regimes,
            overfit_pressure=round(avg_overfit, 6),
            failure_pressure=round(failure_pressure, 6),
            liquidity_pressure=liquidity_pressure,
            greek_iv_pressure=greek_iv_pressure,
            macro_pressure=macro_pressure,
            recommended_attention=attention,
            allowed_mutation_intensity=intensity,
            constraints=constraints,
            ensemble_weight=round(ensemble_weight, 6),
        ))
    result.sort(key=lambda p: (-p.trust_score, p.strategy_family))
    return result


def _dominant_failure_modes_for_regime(evidence: EvidenceBundle, regime_tag: str) -> list[str]:
    modes: dict[str, int] = defaultdict(int)
    for mode in evidence.failure_modes.get("failure_modes", []):
        regimes = [str(r) for r in mode.get("windows_or_regimes", [])]
        if regime_tag in regimes or regime_class_for_tag(regime_tag) in regimes:
            modes[str(mode.get("failure_mode_id", ""))] += int(mode.get("recurrence_count", 1))
    return [m for m, _ in sorted(modes.items(), key=lambda kv: (-kv[1], kv[0]))][:5]


def build_regime_trust_profiles(evidence: EvidenceBundle) -> list[RegimeTrustProfile]:
    """Build per-regime trust profiles from the regime allocator + evidence."""
    regime_profiles = build_regime_profiles()
    result: list[RegimeTrustProfile] = []
    for regime_tag in KNOWN_REGIME_TAGS:
        regime_class = regime_class_for_tag(regime_tag)
        profile = regime_profiles.get(regime_class, regime_profiles["macro_contradiction"])
        required = REGIME_REQUIRED_EVIDENCE.get(regime_class, ["tournament", "walk_forward_replay"])
        dominant = _dominant_failure_modes_for_regime(evidence, regime_tag)
        # regime trust rewards preferred-family breadth + evidence availability.
        present = evidence.layers_present()
        evidence_factor = sum(1 for layer in required if present.get(_layer_to_key(layer), False)) / max(1, len(required))
        breadth = len(profile.preferred_families) / 4.0
        trust = round(0.5 * evidence_factor + 0.3 * breadth + 0.2 * (1.0 - min(1.0, len(dominant) / 5.0)), 6)
        result.append(RegimeTrustProfile(
            regime_tag=regime_tag,
            regime_class=regime_class,
            preferred_families=profile.preferred_families,
            penalized_families=profile.penalized_families,
            starve_families=profile.starve_families,
            dominant_failure_modes=dominant,
            required_evidence_layers=sorted(required),
            trust_score=trust,
        ))
    result.sort(key=lambda p: (-p.trust_score, p.regime_tag))
    return result


def _layer_to_key(layer: str) -> str:
    mapping = {
        "walk_forward_replay": "tournament",
        "tournament": "tournament",
        "liquidity_slippage": "ensemble",
        "greeks_iv_validation": "ensemble",
        "iv_surface_skew_term": "iv_surface",
        "macro_event_fixtures": "macro_events",
        "pattern_fixture_intelligence": "champion",
    }
    return mapping.get(layer, "champion")
