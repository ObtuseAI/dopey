"""Deterministic paper-only promotion / demotion / quarantine policy.

All outputs are paper/research governance only. No function here can emit a live promotion,
real capital decision, or broker order. Unsafe live flags cause immediate rejection.
"""
from __future__ import annotations

from .meta_governor_models import (
    ALLOWED_TIERS,
    FORBIDDEN_DECISIONS,
    MetaGovernorDecision,
    PromotionEligibilityProfile,
    StrategyProofProfile,
    assert_decision_safe,
    assert_tier_safe,
)
from .proof_quality import ProofQualityResult


PROMOTION_POLICY_VERSION = "dopey-proof-weighted-promotion-policy-v1"

# Proof-strength bands.
PROOF_BAND_STRONG = 0.65
PROOF_BAND_CANDIDATE = 0.55
PROOF_BAND_WATCHLIST = 0.45
PROOF_BAND_RESEARCH = 0.30

# Risk / disqualifying thresholds.
HIGH_OVERFIT_RANK = 3
FAILURE_STARVE_PRESSURE = 0.40
LOW_LIQUIDITY_FLOOR = 0.40


def _is_unsafe(profile: StrategyProofProfile) -> bool:
    """Any live-enabling flag on a research candidate is unsafe -> reject."""
    if profile.paper_only is not True:
        return True
    return False


def quarantine_policy(profile: StrategyProofProfile) -> str | None:
    """Return a quarantine decision if the candidate must be quarantined, else None."""
    if _is_unsafe(profile):
        return "reject_unsafe"
    if profile.overfit_rank >= HIGH_OVERFIT_RANK:
        return "quarantine_overfit"
    return None


def demotion_policy(profile: StrategyProofProfile, quality: ProofQualityResult) -> str | None:
    """Return a demotion/starvation decision if applicable, else None."""
    if profile.failure_pressure >= FAILURE_STARVE_PRESSURE:
        return "starve_weak_signal"
    if quality.proof_strength < PROOF_BAND_RESEARCH and profile.ensemble_weight <= 0.0:
        return "reduce_paper_attention"
    return None


def promotion_policy(profile: StrategyProofProfile, quality: ProofQualityResult, *,
                      is_top_strategy: bool = False,
                      is_ensemble_member: bool = False,
                      is_mutation_champion: bool = False) -> str:
    """Return the deterministic paper-only promotion decision."""
    # 1. Safety / quarantine / demotion gate first (highest precedence).
    quarantine = quarantine_policy(profile)
    if quarantine:
        return quarantine
    demotion = demotion_policy(profile, quality)
    if demotion:
        return demotion

    # 2. Missing-evidence gate.
    if quality.evidence_coverage < 0.5 or quality.proof_strength < PROOF_BAND_RESEARCH:
        return "request_more_fixture_evidence"

    # 3. Promotion tiers by proof strength + role flags.
    strength = quality.proof_strength
    wf = profile.walk_forward_consistency
    if is_mutation_champion and strength >= PROOF_BAND_CANDIDATE and profile.mutation_improvement > 0 and wf >= 0.45:
        return "mark_offline_mutation_champion"
    if is_top_strategy and strength >= PROOF_BAND_STRONG and wf >= 0.60:
        return "promote_to_paper_champion"
    if is_ensemble_member and strength >= PROOF_BAND_CANDIDATE and wf >= 0.50:
        return "mark_offline_ensemble_member"
    if strength >= PROOF_BAND_CANDIDATE and wf >= 0.50:
        return "promote_to_paper_candidate"
    if strength >= PROOF_BAND_WATCHLIST and wf >= 0.40:
        return "promote_to_paper_watchlist"
    return "hold_research_only"


def assess_promotion_eligibility(profile: StrategyProofProfile, quality: ProofQualityResult) -> PromotionEligibilityProfile:
    """Map a profile + quality into the highest paper tier it qualifies for."""
    blocked_tiers: list[str] = []
    disqualifying: list[str] = []
    missing: list[str] = []

    if _is_unsafe(profile):
        return PromotionEligibilityProfile(
            strategy_id=profile.strategy_id,
            strategy_family=profile.strategy_family,
            eligible_tier="rejected",
            blocked_tiers=sorted(ALLOWED_TIERS),
            disqualifying_failures=["live_enabling_flag_detected"],
            proof_strength=quality.proof_strength,
            risk_pressure=1.0,
            paper_only=False,
            live_blocked=True,
        )

    if profile.overfit_rank >= HIGH_OVERFIT_RANK:
        blocked_tiers.extend(["paper_champion", "offline_mutation_champion", "paper_candidate"])
        disqualifying.append("high_overfit")
    if profile.failure_pressure >= FAILURE_STARVE_PRESSURE:
        blocked_tiers.extend(["paper_champion", "offline_mutation_champion", "offline_ensemble_member", "paper_candidate"])
        disqualifying.append("recurring_failure_modes")
    if profile.liquidity_robustness < LOW_LIQUIDITY_FLOOR:
        blocked_tiers.extend(["paper_champion", "offline_mutation_champion"])
        disqualifying.append("low_liquidity_robustness")
    if quality.evidence_coverage < 0.5:
        missing.append("complete_evidence_layer_coverage")
    if quality.cross_layer_agreement < 0.9:
        missing.append("cross_layer_champion_agreement")
    if quality.walk_forward_consistency < PROOF_BAND_CANDIDATE:
        missing.append("stronger_walk_forward_consistency")

    if profile.overfit_rank >= HIGH_OVERFIT_RANK:
        eligible = "quarantine"
    elif profile.failure_pressure >= FAILURE_STARVE_PRESSURE:
        eligible = "research_only"
    elif quality.proof_strength >= PROOF_BAND_STRONG:
        eligible = "paper_champion"
    elif quality.proof_strength >= PROOF_BAND_CANDIDATE:
        eligible = "paper_candidate"
    elif quality.proof_strength >= PROOF_BAND_WATCHLIST:
        eligible = "paper_watchlist"
    elif quality.proof_strength >= PROOF_BAND_RESEARCH:
        eligible = "research_only"
    else:
        eligible = "research_only"
        missing.append("higher_proof_strength")

    return PromotionEligibilityProfile(
        strategy_id=profile.strategy_id,
        strategy_family=profile.strategy_family,
        eligible_tier=eligible,
        blocked_tiers=sorted(set(blocked_tiers)),
        required_missing_evidence=sorted(set(missing)),
        disqualifying_failures=sorted(set(disqualifying)),
        proof_strength=quality.proof_strength,
        risk_pressure=quality.risk_pressure,
        paper_only=True,
        live_blocked=True,
    )


LIVE_MIGRATION_CONDITIONS = [
    "prohibited_in_this_repository",
    "requires_a_separate_independently_reviewed_deployment_system",
]


def decide_meta_governor(profile: StrategyProofProfile, quality: ProofQualityResult, *,
                          is_top_strategy: bool = False,
                          is_ensemble_member: bool = False,
                          is_mutation_champion: bool = False) -> MetaGovernorDecision:
    """Produce the final deterministic paper-only governance decision."""
    eligibility = assess_promotion_eligibility(profile, quality)
    decision_str = promotion_policy(
        profile, quality,
        is_top_strategy=is_top_strategy,
        is_ensemble_member=is_ensemble_member,
        is_mutation_champion=is_mutation_champion,
    )
    assert_decision_safe(decision_str)
    assert_tier_safe(eligibility.eligible_tier)

    reasons: list[str] = []
    if decision_str == "reject_unsafe":
        reasons.append("live-enabling flag detected on a research candidate")
    elif decision_str == "quarantine_overfit":
        reasons.append("high overfit pressure quarantines the candidate")
    elif decision_str == "starve_weak_signal":
        reasons.append("recurring failure-mode pressure starves the candidate")
    elif decision_str.startswith("promote_to") or decision_str.startswith("mark_"):
        reasons.append(f"proof strength {round(quality.proof_strength,3)} supports paper promotion")
    elif decision_str == "request_more_fixture_evidence":
        reasons.append("insufficient evidence coverage or proof strength")
    elif decision_str == "reduce_paper_attention":
        reasons.append("weak proof and no ensemble support reduce paper attention")
    else:
        reasons.append("proof below promotion threshold; held as research-only")
    if profile.mutation_improvement > 0:
        reasons.append("mutation improvement recorded")

    return MetaGovernorDecision(
        strategy_id=profile.strategy_id,
        strategy_family=profile.strategy_family,
        decision=decision_str,
        eligible_tier=eligibility.eligible_tier,
        proof_strength=quality.proof_strength,
        risk_pressure=quality.risk_pressure,
        reason_codes=reasons,
        required_missing_evidence=eligibility.required_missing_evidence,
        disqualifying_failures=eligibility.disqualifying_failures,
        paper_only=True,
        live_allowed=False,
        live_migration_conditions=list(LIVE_MIGRATION_CONDITIONS) if decision_str.startswith(("promote_to_paper_champion", "mark_offline")) else [],
    )


def forbidden_decisions_emitted(decisions: list[MetaGovernorDecision]) -> list[str]:
    """Return any forbidden live decisions found (must always be empty)."""
    return sorted({d.decision for d in decisions if d.decision in FORBIDDEN_DECISIONS})
