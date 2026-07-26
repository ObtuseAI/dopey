"""Deterministic offline ensemble replay + scorecard for DOPEY.

Compares a single champion, an equal-weight family basket, and the allocator-weighted
ensemble across fixture windows. All scores are deterministic paper units — no real account
balance, real PnL, or broker sizing is simulated.
"""
from __future__ import annotations

from .ensemble_models import (
    EnsembleReplayResult,
    EnsembleRobustnessScore,
    FamilyDiversificationScore,
    RegimeCoverageScore,
    StrategyAllocationCandidate,
    SimulatedAllocationDecision,
)


ENSEMBLE_REPLAY_VERSION = "dopey-ensemble-replay-v1"


def _accepted(candidates, decisions) -> list[tuple[StrategyAllocationCandidate, SimulatedAllocationDecision]]:
    pairs = []
    for candidate, decision in zip(candidates, decisions):
        if decision.recommended_weight > 0.0:
            pairs.append((candidate, decision))
    return pairs


def compute_family_diversification(candidates: list[StrategyAllocationCandidate], weights: list[float]) -> FamilyDiversificationScore:
    family_share: dict[str, float] = {}
    for candidate, weight in zip(candidates, weights):
        family_share[candidate.strategy_family] = family_share.get(candidate.strategy_family, 0.0) + weight
    total = sum(family_share.values()) or 1.0
    shares = [v / total for v in family_share.values()]
    herfindahl = round(sum(s * s for s in shares), 6)
    effective = round(1.0 / herfindahl, 6) if herfindahl > 0 else 0.0
    return FamilyDiversificationScore(
        families_represented=len(family_share),
        effective_family_count=effective,
        herfindahl_concentration=herfindahl,
    )


def compute_regime_coverage(candidates: list[StrategyAllocationCandidate], weights: list[float], known_regimes: list[str]) -> RegimeCoverageScore:
    covered: set[str] = set()
    for candidate, weight in zip(candidates, weights):
        if weight > 0.0:
            covered.update(candidate.best_regimes)
    known = set(known_regimes)
    uncovered = sorted(known - covered)
    cov = sorted(covered & known)
    fraction = round(len(cov) / max(1, len(known)), 6)
    return RegimeCoverageScore(
        regimes_covered=len(cov),
        regimes_total=len(known),
        coverage_fraction=fraction,
        covered_regimes=cov,
        uncovered_regimes=uncovered,
    )


def compute_robustness(scores: list[float]) -> EnsembleRobustnessScore:
    if not scores:
        return EnsembleRobustnessScore()
    mean = round(sum(scores) / len(scores), 6)
    mn = round(min(scores), 6)
    mx = round(max(scores), 6)
    spread = round(mx - mn, 6)
    drawdown = round(max(0.0, mean - mn), 6)
    return EnsembleRobustnessScore(mean_score=mean, min_score=mn, spread=spread, drawdown_proxy=drawdown)


def _overfit_penalty(candidate: StrategyAllocationCandidate) -> float:
    rank = {"none": 0.0, "low": 0.02, "moderate": 0.05, "high": 0.10, "unknown": 0.05}.get(
        candidate.overfit_level, 0.05
    )
    return rank


def run_ensemble_replay(
    candidates: list[StrategyAllocationCandidate],
    decisions: list[SimulatedAllocationDecision],
    *,
    known_regimes: list[str] | None = None,
) -> EnsembleReplayResult:
    """Compare single-champion vs equal-weight vs allocator-weighted ensemble (paper units)."""
    if not candidates:
        return EnsembleReplayResult()
    known_regimes = known_regimes or sorted({r for c in candidates for r in c.best_regimes})
    weights = [d.recommended_weight for d in decisions]
    accepted = _accepted(candidates, decisions)

    # Single champion: best base_score candidate (deterministic).
    champion = sorted(candidates, key=lambda c: (-c.base_score, c.strategy_id))[0]
    single_champion_score = round(champion.base_score, 6)

    # Equal-weight family basket: average of accepted candidate base scores.
    accepted_scores = [c.base_score for c, _ in accepted] or [c.base_score for c in candidates]
    equal_weight_score = round(sum(accepted_scores) / len(accepted_scores), 6)

    # Allocator-weighted ensemble.
    if accepted:
        weight_mass = sum(d.recommended_weight for _, d in accepted)
        if weight_mass > 0:
            allocator_score = round(
                sum(c.base_score * d.recommended_weight for c, d in accepted) / weight_mass, 6
            )
        else:
            allocator_score = equal_weight_score
    else:
        allocator_score = single_champion_score

    # Overfit-adjusted ensemble: penalize weighted contributions by overfit level.
    if accepted:
        weight_mass = sum(d.recommended_weight for _, d in accepted) or 1.0
        overfit_adjusted = round(
            sum((c.base_score - _overfit_penalty(c)) * d.recommended_weight for c, d in accepted) / weight_mass, 6
        )
    else:
        overfit_adjusted = round(champion.base_score - _overfit_penalty(champion), 6)

    # Concentration penalty: if one strategy dominates (>0.40) the overfit-adjusted score dips.
    max_weight = max(weights) if weights else 0.0
    if max_weight > 0.40:
        overfit_adjusted = round(overfit_adjusted - (max_weight - 0.40) * 0.10, 6)

    robustness = compute_robustness([c.base_score for c, _ in accepted] or [c.base_score for c in candidates])
    diversification = compute_family_diversification(candidates, weights)
    coverage = compute_regime_coverage(candidates, weights, known_regimes)

    scored = {
        "single_champion": single_champion_score,
        "equal_weight": equal_weight_score,
        "allocator_weighted": allocator_score,
        "overfit_adjusted": overfit_adjusted,
    }
    best_variant = max(scored, key=lambda k: (scored[k], k == "allocator_weighted"))

    return EnsembleReplayResult(
        ensemble_variant="allocator_weighted",
        single_champion_score=single_champion_score,
        equal_weight_score=equal_weight_score,
        allocator_weighted_score=allocator_score,
        overfit_adjusted_score=overfit_adjusted,
        best_ensemble_variant=best_variant,
        robustness=robustness.drawdown_proxy,
        family_diversification=diversification.effective_family_count,
        regime_coverage=coverage.coverage_fraction,
        failure_exposure=round(sum(c.failure_pressure_score * w for c, w in zip(candidates, weights)), 6),
        improves_over_champion=allocator_score > single_champion_score,
        paper_only=True,
    )
