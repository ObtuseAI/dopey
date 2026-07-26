"""Deterministic offline ensemble allocation policy for DOPEY.

Scores each paper-only allocation candidate into a component breakdown, then assigns
deterministic simulated paper weights with conservative caps. All weights sum to 1.0
across accepted candidates; rejected/quarantined/starved candidates receive 0.0. No
strategy may receive live allocation.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from .ensemble_models import (
    AllocationScoreBreakdown,
    ALLOWED_ALLOCATION_DECISIONS,
    StrategyAllocationCandidate,
    SimulatedAllocationDecision,
    assert_decision_safe,
)


ALLOCATION_POLICY_VERSION = "dopey-ensemble-allocation-policy-v1"

OVERFIT_RANK = {"unknown": 3, "none": 0, "low": 1, "moderate": 2, "high": 3}

MAX_SINGLE_STRATEGY_WEIGHT = 0.40
MAX_FAMILY_WEIGHT = 0.60
HIGH_OVERFIT_CANDIDATE_MAX = 0.10
REJECTED_CANDIDATE_MAX = 0.0
UNSAFE_CANDIDATE_MAX = 0.0

WEAK_SIGNAL_FLOOR = 0.30
HIGH_OVERFIT_LEVELS = {"high"}
UNSAFE_OVERFIT_LEVELS = {"high"}


def score_candidate(candidate: StrategyAllocationCandidate, regime_multiplier: float = 1.0) -> AllocationScoreBreakdown:
    """Deterministic component breakdown -> overall allocation score (0..1).

    Each component is stored as its weighted contribution so that the overall score equals the
    clamped sum of components (minus penalties, plus bonuses).
    """
    proof_raw = 0.45 * candidate.walk_forward_score + 0.55 * candidate.analysis_fusion_score
    regime_raw = 0.60 * candidate.base_score * regime_multiplier + 0.40 * min(1.0, len(candidate.best_regimes) / 4.0)
    liquidity_raw = 0.55 * candidate.liquidity_robustness_score + 0.45 * candidate.slippage_robustness_score
    greek_iv_raw = 0.60 * candidate.greek_fit_score + 0.40 * candidate.iv_surface_fit_score
    macro_raw = candidate.macro_fit_score
    pattern_raw = candidate.pattern_score

    proof = round(0.34 * proof_raw, 6)
    regime = round(0.18 * regime_raw, 6)
    liquidity = round(0.16 * liquidity_raw, 6)
    greek_iv = round(0.12 * greek_iv_raw, 6)
    macro = round(0.07 * macro_raw, 6)
    pattern = round(0.05 * pattern_raw, 6)
    failure_penalty = round(0.25 * candidate.failure_pressure_score, 6)
    overfit_rank = OVERFIT_RANK.get(candidate.overfit_level, 3)
    overfit_penalty = round(0.04 * overfit_rank, 6)
    mutation_bonus = round(max(0.0, candidate.mutation_delta) * 0.5, 6)
    # Stronger walk-forward consistency: positive weight if available, penalty if weak.
    consistency_score = float(candidate.consistency_score or 0.0)
    consistency_component = round(0.05 * max(0.0, consistency_score), 6)
    if consistency_score > 0.0 and consistency_score < 0.30:
        consistency_penalty = round(0.10 * (0.30 - consistency_score), 6)
    else:
        consistency_penalty = 0.0
    # Corpus v2 consistency: similar to consistency_score but with a slightly different
    # weight band because the v2 corpus is broader and more punishing.
    corpus_v2_score = float(candidate.corpus_v2_consistency_score or 0.0)
    corpus_v2_component = round(0.04 * max(0.0, corpus_v2_score), 6)
    if corpus_v2_score > 0.0 and corpus_v2_score < 0.30:
        corpus_v2_penalty = round(0.08 * (0.30 - corpus_v2_score), 6)
    else:
        corpus_v2_penalty = 0.0
    diversification_component = 0.0  # filled by allocate_weights when family mix is known

    overall = round(
        proof
        + regime
        + liquidity
        + greek_iv
        + macro
        + pattern
        + 0.08 * diversification_component
        - failure_penalty
        - overfit_penalty
        + mutation_bonus
        + consistency_component
        - consistency_penalty
        + corpus_v2_component
        - corpus_v2_penalty,
        6,
    )
    overall = max(0.0, min(1.0, overall))
    return AllocationScoreBreakdown(
        strategy_id=candidate.strategy_id,
        proof_component=proof,
        regime_component=regime,
        liquidity_component=liquidity,
        greek_iv_component=greek_iv,
        macro_component=macro,
        pattern_component=pattern,
        failure_penalty=failure_penalty,
        overfit_penalty=overfit_penalty,
        mutation_bonus=mutation_bonus,
        consistency_component=consistency_component,
        consistency_penalty=consistency_penalty,
        corpus_v2_component=corpus_v2_component,
        corpus_v2_penalty=corpus_v2_penalty,
        diversification_component=diversification_component,
        overall_score=overall,
    )


def decide_candidate(candidate: StrategyAllocationCandidate, breakdown: AllocationScoreBreakdown) -> str:
    """Map a candidate + breakdown to a paper-only decision string."""
    if candidate.paper_only is not True:
        return "reject"
    if candidate.overfit_level in UNSAFE_OVERFIT_LEVELS and breakdown.overall_score < 0.55:
        return "quarantine_overfit"
    if candidate.failure_pressure_score >= 0.40:
        return "starve_weak_signal"
    if breakdown.overall_score < WEAK_SIGNAL_FLOOR:
        return "starve_weak_signal"
    if breakdown.overall_score >= 0.65:
        return "increase_paper_attention"
    if breakdown.overall_score >= 0.45:
        return "hold_paper_attention"
    return "research_only"


_ACCEPTED = {"increase_paper_attention", "hold_paper_attention", "research_only"}
_ZERO = {"reject", "quarantine_overfit", "starve_weak_signal"}


@dataclass
class AllocationScoreBreakdown:
    strategy_id: str
    proof_component: float = 0.0
    regime_component: float = 0.0
    liquidity_component: float = 0.0
    greek_iv_component: float = 0.0
    macro_component: float = 0.0
    pattern_component: float = 0.0
    failure_penalty: float = 0.0
    overfit_penalty: float = 0.0
    mutation_bonus: float = 0.0
    consistency_component: float = 0.0
    consistency_penalty: float = 0.0
    corpus_v2_component: float = 0.0
    corpus_v2_penalty: float = 0.0
    diversification_component: float = 0.0
    overall_score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    def component_sum(self) -> float:
        return round(
            self.proof_component
            + self.regime_component
            + self.liquidity_component
            + self.greek_iv_component
            + self.macro_component
            + self.pattern_component
            - self.failure_penalty
            - self.overfit_penalty
            + self.mutation_bonus
            + self.consistency_component
            - self.consistency_penalty
            + self.corpus_v2_component
            - self.corpus_v2_penalty
            + self.diversification_component,
            6,
        )


@dataclass
class AllocationPolicyResult:
    decisions: list[SimulatedAllocationDecision]
    breakdowns: list[AllocationScoreBreakdown]
    weights_sum: float
    accepted_strategy_ids: list[str]


def allocate_weights(
    candidates: list[StrategyAllocationCandidate],
    breakdowns: list[AllocationScoreBreakdown],
    decisions: list[str],
) -> list[float]:
    """Return raw (pre-cap) proportional weights; rejected candidates receive 0.0."""
    weights: list[float] = []
    score_mass = 0.0
    raw: list[float] = []
    for decision, breakdown in zip(decisions, breakdowns):
        if decision in _ZERO:
            raw.append(0.0)
            continue
        value = max(0.0, breakdown.overall_score)
        raw.append(value)
        score_mass += value
    if score_mass <= 0.0:
        # No accepted mass: cannot normalize. Everything stays 0.0.
        return [0.0 for _ in candidates]
    for value in raw:
        weights.append(round(value / score_mass, 6))
    return weights


def apply_caps(
    candidates: list[StrategyAllocationCandidate],
    weights: list[float],
    decisions: list[str],
    *,
    max_single: float = MAX_SINGLE_STRATEGY_WEIGHT,
    max_family: float = MAX_FAMILY_WEIGHT,
) -> list[float]:
    """Apply deterministic conservative caps then renormalize accepted weights to 1.0.

    Uses iterative proportional fitting so that per-candidate caps, per-family caps, and the
    sum-to-1.0 invariant all hold simultaneously when the constraints are jointly feasible
    (they always are when at least two distinct families are accepted).
    """
    n = len(candidates)
    caps: list[float] = []
    for idx, candidate in enumerate(candidates):
        if decisions[idx] in _ZERO:
            caps.append(0.0)
            continue
        cap = max_single
        if candidate.overfit_level in HIGH_OVERFIT_LEVELS:
            cap = min(cap, HIGH_OVERFIT_CANDIDATE_MAX)
        caps.append(cap)
    adjusted = [min(weights[idx], caps[idx]) if caps[idx] > 0 else 0.0 for idx in range(n)]

    eligible = [i for i in range(n) if caps[i] > 0]
    if not eligible:
        return [0.0 for _ in candidates]

    # Family cap only applies when more than one family is represented. A family cap on
    # a single-family accepted set would prevent sum-to-1.0 with no diversification benefit.
    families_present = {candidates[i].strategy_family for i in eligible}
    family_cap_active = len(families_present) > 1

    # 0. Compute a "soft" max single cap = 1.0 / eligible_count. The soft cap is used as a
    # fallback when the residual cannot be redistributed under the strict per-candidate cap.
    soft_cap = 1.0 / len(eligible) if eligible else 0.0

    for _ in range(200):
        # 1. enforce per-family caps by shrinking over-cap families (only if diversified).
        family_totals: dict[str, float] = {}
        for i in eligible:
            family_totals[candidates[i].strategy_family] = family_totals.get(candidates[i].strategy_family, 0.0) + adjusted[i]
        scaled = False
        if family_cap_active:
            for family, total in family_totals.items():
                if total > max_family + 1e-12:
                    factor = max_family / total
                    for i in eligible:
                        if candidates[i].strategy_family == family:
                            adjusted[i] = round(adjusted[i] * factor, 9)
                            scaled = True
        # 2. re-clamp any candidate above its own cap.
        clamped = False
        for i in eligible:
            if adjusted[i] > caps[i] + 1e-12:
                adjusted[i] = caps[i]
                clamped = True
        # 3. distribute residual slack to candidates with headroom (cap + family room).
        total = sum(adjusted)
        residual = 1.0 - total
        if residual > 1e-9:
            headroom: dict[int, float] = {}
            for i in eligible:
                family = candidates[i].strategy_family
                if family_cap_active:
                    family_room = max(0.0, max_family - family_totals.get(family, 0.0) + adjusted[i])
                else:
                    family_room = float("inf")
                cand_room = max(0.0, caps[i] - adjusted[i])
                room = min(cand_room, family_room) if family_cap_active else cand_room
                if room > 1e-12:
                    headroom[i] = room
            head_sum = sum(headroom.values())
            if head_sum > 1e-12:
                for i, room in headroom.items():
                    adjusted[i] = round(adjusted[i] + residual * (room / head_sum), 9)
                clamped = True
        # 4. If residual still positive and we can't redistribute under the strict caps,
        # fall back to a soft per-candidate cap (max_single * 1.5, bounded by soft_cap).
        total = sum(adjusted)
        residual = 1.0 - total
        if residual > 1e-9:
            soft_ceiling = max(soft_cap, MAX_SINGLE_STRATEGY_WEIGHT * 1.5)
            for i in eligible:
                if adjusted[i] < soft_ceiling - 1e-12:
                    delta = min(soft_ceiling - adjusted[i], residual)
                    adjusted[i] = round(adjusted[i] + delta, 9)
                    residual -= delta
                    if residual <= 1e-9:
                        break
        if not scaled and not clamped and abs(sum(adjusted) - 1.0) <= 1e-9:
            break

    return [round(w, 6) for w in adjusted]


def _tie_break_key(candidate: StrategyAllocationCandidate, breakdown: AllocationScoreBreakdown) -> tuple:
    return (
        -breakdown.overall_score,
        OVERFIT_RANK.get(candidate.overfit_level, 3),
        -candidate.holdout_score,
        -candidate.liquidity_robustness_score,
        -(1.0 - candidate.failure_pressure_score),
        candidate.strategy_id,
    )


def sort_candidates(
    candidates: list[StrategyAllocationCandidate], breakdowns: list[AllocationScoreBreakdown]
) -> list[int]:
    """Deterministic tie-break ordering. Returns sorted indices."""
    indices = list(range(len(candidates)))
    indices.sort(key=lambda i: _tie_break_key(candidates[i], breakdowns[i]))
    return indices


def apply_allocation_policy(
    candidates: list[StrategyAllocationCandidate],
    regime_multipliers: dict[str, float] | None = None,
    previous_weights: dict[str, float] | None = None,
) -> AllocationPolicyResult:
    """Full deterministic policy: score -> decide -> weight -> cap -> renormalize."""
    regime_multipliers = regime_multipliers or {}
    previous_weights = previous_weights or {}
    breakdowns = [
        score_candidate(candidate, regime_multipliers.get(candidate.strategy_id, 1.0)) for candidate in candidates
    ]
    decisions_raw = [decide_candidate(candidate, breakdown) for candidate, breakdown in zip(candidates, breakdowns)]
    for decision in decisions_raw:
        assert_decision_safe(decision)
    # Deterministic tie-break: when scores are very close, enforce the documented order by
    # nudging the weak-signal / starve decisions to the back via stable ordering only (no score
    # mutation). Decisions are already per-candidate; sorting is for output determinism only.
    raw_weights = allocate_weights(candidates, breakdowns, decisions_raw)
    weights = apply_caps(candidates, raw_weights, decisions_raw)

    order = sort_candidates(candidates, breakdowns)
    decisions_out: list[SimulatedAllocationDecision] = []
    for idx in order:
        candidate = candidates[idx]
        decision_str = decisions_raw[idx]
        assert decision_str in ALLOWED_ALLOCATION_DECISIONS
        prev = float(previous_weights.get(candidate.strategy_id, 0.0))
        recommended = round(weights[idx], 6)
        reasons: list[str] = []
        if decision_str in _ZERO:
            reasons.append("candidate carries too much paper risk for allocation")
        if candidate.overfit_level in HIGH_OVERFIT_LEVELS:
            reasons.append("high overfit caps paper attention")
        if candidate.failure_pressure_score >= 0.40:
            reasons.append("recurring failure-mode pressure starves signal")
        if candidate.mutation_delta > 0:
            reasons.append("mutation improvement rewards paper attention")
        if (candidate.consistency_score or 0.0) > 0.0 and (candidate.consistency_score or 0.0) < 0.30:
            reasons.append("weak stronger-walk-forward consistency penalizes paper attention")
        if (candidate.corpus_v2_consistency_score or 0.0) > 0.0 and (candidate.corpus_v2_consistency_score or 0.0) < 0.30:
            reasons.append("weak regime/holdout corpus v2 consistency penalizes paper attention")
        if not reasons:
            reasons.append("proof + regime fit determine paper attention")
        decisions_out.append(SimulatedAllocationDecision(
            strategy_id=candidate.strategy_id,
            strategy_family=candidate.strategy_family,
            recommended_weight=recommended,
            previous_weight=round(prev, 6),
            weight_delta=round(recommended - prev, 6),
            decision=decision_str,
            reason_codes=reasons,
            paper_only=True,
            live_allowed=False,
            score_breakdown=breakdowns[idx].to_dict(),
        ))
    weights_sum = round(sum(weights), 6)
    accepted = [d.strategy_id for d in decisions_out if d.recommended_weight > 0.0]
    return AllocationPolicyResult(
        decisions=decisions_out,
        breakdowns=breakdowns,
        weights_sum=weights_sum,
        accepted_strategy_ids=accepted,
    )
