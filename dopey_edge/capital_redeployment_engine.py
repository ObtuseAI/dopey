"""Dopey capital redeployment engine: simulated paper allocation recommendations only.

Recommend-only; no live exec, no account mutation. This module extends the original
recommend-only doctrine with a richer paper-only redeployment recommendation layer used by
the offline ensemble allocator. It never emits real capital allocation or broker order sizing.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


REDEPLOYMENT_ENGINE_VERSION = "dopey-capital-redeployment-engine-v1"

PAPER_ONLY_ACTIONS = frozenset({"increase", "hold", "reduce", "starve", "quarantine", "research_only"})
FORBIDDEN_REDEPLOYMENT_ACTIONS = frozenset({"live_allocate", "micro_live", "adaptive_live", "real_capital", "broker_order"})


@dataclass
class ReallocationRecommendation:
    from_family: str
    to_family: str
    fraction: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CapitalRedeploymentRecommendation:
    recommendation_id: str
    target_strategy_family: str
    target_strategy_id: str
    action: str
    reason_codes: list[str]
    source_evidence: list[str]
    failure_mode_evidence: list[str]
    regime_evidence: list[str]
    proof_level: str = "paper_only"
    paper_only: bool = True
    live_allowed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def redeploy_capital(family_scores: dict[str, float], current_alloc: dict[str, float],
                     min_realloc_edge: float = 0.10) -> list[ReallocationRecommendation]:
    """Recommend moving capital from weaker families to stronger ones. No live exec."""
    recs = []
    if not family_scores or not current_alloc:
        return recs
    ranked = sorted(family_scores.items(), key=lambda kv: kv[1], reverse=True)
    if len(ranked) < 2:
        return recs
    best_fam, best_score = ranked[0]
    worst_fam, worst_score = ranked[-1]
    if best_score - worst_score < min_realloc_edge:
        return recs
    move = round(min(current_alloc.get(worst_fam, 0.0) * 0.25, 0.25), 6)
    recs.append(ReallocationRecommendation(worst_fam, best_fam, move,
                                           f"redeploy toward stronger proof-backed family (edge {round(best_score-worst_score,4)})"))
    return recs


def _assert_paper_only(action: str) -> None:
    if action in FORBIDDEN_REDEPLOYMENT_ACTIONS:
        raise ValueError(f"forbidden live redeployment action: {action}")
    if action not in PAPER_ONLY_ACTIONS:
        raise ValueError(f"unknown redeployment action: {action}")


def build_capital_redeployment_recommendations(
    candidates: list[dict],
    *,
    regime_profiles: dict[str, dict] | None = None,
    failure_pressure_by_family: dict[str, float] | None = None,
) -> list[CapitalRedeploymentRecommendation]:
    """Produce simulated paper-only redeployment recommendations.

    ``candidates`` are allocator decision dicts (as produced by the ensemble allocator) and
    family candidate summaries. Every recommendation is paper-only; no live path is emitted.
    """
    failure_pressure_by_family = failure_pressure_by_family or {}
    regime_profiles = regime_profiles or {}
    recommendations: list[CapitalRedeploymentRecommendation] = []
    counter = 0
    for candidate in candidates:
        family = str(candidate.get("strategy_family", ""))
        strategy_id = str(candidate.get("strategy_id", ""))
        decision = str(candidate.get("decision", "research_only"))
        failure_pressure = float(failure_pressure_by_family.get(family, 0.0))
        weight = float(candidate.get("recommended_weight", 0.0))
        regime_class = str(candidate.get("regime_class", ""))
        regime_notes = regime_profiles.get(regime_class, {}).get("regime_notes", "")

        action: str
        reasons: list[str] = []
        failure_evidence: list[str] = []
        regime_evidence: list[str] = []
        source_evidence = [f"decision={decision}", f"recommended_weight={round(weight, 4)}"]

        if failure_pressure >= 0.40:
            action = "starve"
            reasons.append("recurring failure-mode pressure starves the family")
            failure_evidence.append(f"family_failure_pressure={round(failure_pressure, 3)}")
        elif decision == "quarantine_overfit":
            action = "quarantine"
            reasons.append("high-overfit candidate quarantined from paper attention")
        elif decision == "starve_weak_signal":
            action = "starve"
            reasons.append("weak signal starved")
        elif "iv_crush" in regime_class or "post_event" in regime_class:
            # Reduce vol-expansion attention after an IV crush failure mode.
            if family == "volatility_expansion":
                action = "reduce"
                reasons.append("reduce vol-expansion attention after post-event IV crush")
                regime_evidence.append("regime=post_event_iv_crush")
            else:
                action = "hold"
                reasons.append("hold paper attention through post-event normalization")
                regime_evidence.append(regime_notes)
        elif family == "short_duration_defined_risk" and regime_class in {"bad_fill", "low_liquidity_decay"}:
            action = "reduce"
            reasons.append("increase liquidity threshold for short-duration candidates")
            regime_evidence.append("regime=bad_fill_low_liquidity")
        elif decision == "increase_paper_attention":
            action = "increase"
            reasons.append("proof + regime fit reward paper attention")
            regime_evidence.append(regime_notes)
        elif decision == "hold_paper_attention":
            action = "hold"
            reasons.append("stable but mixed proof holds paper attention")
        else:
            action = "research_only"
            reasons.append("stable but insufficient proof; observation only")

        _assert_paper_only(action)
        counter += 1
        recommendations.append(CapitalRedeploymentRecommendation(
            recommendation_id=f"redeploy-{counter:03d}-{strategy_id or family}",
            target_strategy_family=family,
            target_strategy_id=strategy_id,
            action=action,
            reason_codes=reasons,
            source_evidence=source_evidence,
            failure_mode_evidence=failure_evidence,
            regime_evidence=regime_evidence,
        ))
    return recommendations
