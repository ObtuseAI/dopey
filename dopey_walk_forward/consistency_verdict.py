"""Deterministic consistency verdicts (paper-only).

Workstream C of `DOPEY_STRONGER_WALK_FORWARD_CONSISTENCY_EXPANSION_V1`.

Maps a `StrategyConsistencyScore` (and the wider family/holdout context) to a discrete
verdict. Verdicts are advisory research labels — they NEVER touch live execution.

Verdicts:
  * strong_consistency   - high overall + high holdout + high family consensus
  * acceptable_consistency - mid overall, no major overfit
  * fragile_consistency  - mid overall, fragile holdout OR high variance
  * overfit_warning      - significant train-vs-OOS gap
  * holdout_failure      - holdout did not survive
  * reject               - too weak for paper research attention
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Iterable

from .consistency_score import (
    FamilyConsistencyProfile,
    HoldoutRobustnessScore,
    StrategyConsistencyScore,
)


ALLOWED_CONSISTENCY_VERDICTS: tuple[str, ...] = (
    "strong_consistency",
    "acceptable_consistency",
    "fragile_consistency",
    "overfit_warning",
    "holdout_failure",
    "reject",
)


@dataclass(frozen=True)
class ConsistencyVerdict:
    strategy_id: str
    strategy_family: str
    verdict: str
    overall: float
    holdout_survival: float
    overfit_penalty: float
    family_consensus: float
    reason_codes: tuple[str, ...] = ()
    holdout_robust: bool = True
    promotion_eligible: bool = True

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "strategy_family": self.strategy_family,
            "verdict": self.verdict,
            "overall": round(self.overall, 6),
            "holdout_survival": round(self.holdout_survival, 6),
            "overfit_penalty": round(self.overfit_penalty, 6),
            "family_consensus": round(self.family_consensus, 6),
            "reason_codes": list(self.reason_codes),
            "holdout_robust": self.holdout_robust,
            "promotion_eligible": self.promotion_eligible,
        }


def decide_consistency_verdict(
    score: StrategyConsistencyScore,
    family_profile: FamilyConsistencyProfile | None = None,
    holdout_score: HoldoutRobustnessScore | None = None,
) -> ConsistencyVerdict:
    """Map a per-strategy consistency score to a discrete verdict.

    The verdict is deterministic and only uses the inputs above. It is advisory only.
    """
    reasons: list[str] = []
    family_consensus = family_profile.mean_overall if family_profile else score.family_consistency
    holdout_robust = holdout_score.robust if holdout_score else (score.holdout_survival >= 0.40)

    # Reject first: too weak even for paper research attention.
    if score.overall < 0.30:
        reasons.append("overall consistency below 0.30 — too weak for paper research")
        return ConsistencyVerdict(
            strategy_id=score.strategy_id, strategy_family=score.strategy_family,
            verdict="reject", overall=score.overall, holdout_survival=score.holdout_survival,
            overfit_penalty=score.overfit_penalty, family_consensus=family_consensus,
            reason_codes=tuple(reasons), holdout_robust=holdout_robust, promotion_eligible=False,
        )

    # Holdout failure: holdout never passed.
    if score.holdout_survival <= 0.10:
        reasons.append("holdout survival ≤ 0.10 — holdout collapse")
        return ConsistencyVerdict(
            strategy_id=score.strategy_id, strategy_family=score.strategy_family,
            verdict="holdout_failure", overall=score.overall, holdout_survival=score.holdout_survival,
            overfit_penalty=score.overfit_penalty, family_consensus=family_consensus,
            reason_codes=tuple(reasons), holdout_robust=holdout_robust, promotion_eligible=False,
        )

    # Overfit warning: overfit_penalty < 0.55 (i.e. high overfit) AND train-vs-OOS imbalance.
    if score.overfit_penalty < 0.55 and score.split_pass_rate >= 0.50:
        reasons.append("train vs OOS gap detected — overfit warning")
        return ConsistencyVerdict(
            strategy_id=score.strategy_id, strategy_family=score.strategy_family,
            verdict="overfit_warning", overall=score.overall, holdout_survival=score.holdout_survival,
            overfit_penalty=score.overfit_penalty, family_consensus=family_consensus,
            reason_codes=tuple(reasons), holdout_robust=holdout_robust, promotion_eligible=False,
        )

    # Strong consistency.
    if (
        score.overall >= 0.65
        and score.holdout_survival >= 0.55
        and score.overfit_penalty >= 0.60
        and score.regime_coverage >= 0.50
    ):
        reasons.append("overall ≥ 0.65 and holdout survival ≥ 0.55 and overfit_penalty ≥ 0.60")
        return ConsistencyVerdict(
            strategy_id=score.strategy_id, strategy_family=score.strategy_family,
            verdict="strong_consistency", overall=score.overall,
            holdout_survival=score.holdout_survival,
            overfit_penalty=score.overfit_penalty, family_consensus=family_consensus,
            reason_codes=tuple(reasons), holdout_robust=holdout_robust, promotion_eligible=True,
        )

    # Acceptable consistency.
    if score.overall >= 0.45:
        reasons.append("overall ≥ 0.45 — acceptable, but not strong")
        return ConsistencyVerdict(
            strategy_id=score.strategy_id, strategy_family=score.strategy_family,
            verdict="acceptable_consistency", overall=score.overall,
            holdout_survival=score.holdout_survival,
            overfit_penalty=score.overfit_penalty, family_consensus=family_consensus,
            reason_codes=tuple(reasons), holdout_robust=holdout_robust, promotion_eligible=True,
        )

    # Fragile consistency.
    reasons.append("mid overall, fragile consistency")
    return ConsistencyVerdict(
        strategy_id=score.strategy_id, strategy_family=score.strategy_family,
        verdict="fragile_consistency", overall=score.overall,
        holdout_survival=score.holdout_survival,
        overfit_penalty=score.overfit_penalty, family_consensus=family_consensus,
        reason_codes=tuple(reasons), holdout_robust=holdout_robust, promotion_eligible=True,
    )


def decide_family_verdict(profile: FamilyConsistencyProfile) -> str:
    if profile.mean_overall >= 0.60 and profile.family_holdout_survival >= 0.55 and profile.family_overfit_penalty >= 0.60:
        return "strong_family"
    if profile.mean_overall >= 0.45 and profile.family_pass_rate >= 0.40:
        return "acceptable_family"
    if profile.family_overfit_penalty < 0.55:
        return "overfit_warning_family"
    if profile.family_holdout_survival <= 0.20:
        return "holdout_failure_family"
    return "fragile_family"


def decide_holdout_verdict(score: HoldoutRobustnessScore) -> str:
    if score.robust and score.holdout_pass_rate >= 0.55:
        return "strong_holdout"
    if score.holdout_pass_rate >= 0.40:
        return "acceptable_holdout"
    if score.holdout_collapse_windows >= 1:
        return "holdout_collapse"
    return "fragile_holdout"
