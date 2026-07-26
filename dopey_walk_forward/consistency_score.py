"""Deterministic walk-forward consistency scoring (paper-only).

Workstream C of `DOPEY_STRONGER_WALK_FORWARD_CONSISTENCY_EXPANSION_V1`.

Score components (all 0..1, deterministic fixture math):
  * split_pass_rate            - fraction of splits the strategy passes
  * validation_stability       - mean validation pass rate across splits
  * holdout_survival           - mean holdout pass rate across splits
  * regime_coverage            - fraction of distinct regimes that passed
  * family_consistency         - agreement with the dominant family pass-rate
  * score_variance             - 1 - stdev of split consistency
  * drawdown_proxy_stability   - 1 - normalized drawdown proxy dispersion
  * liquidity_slippage_stability - mean of (1 - slippage penalty) over splits
  * greek_iv_stability         - mean greek/IV stability over splits
  * macro_stability            - mean of (1 - macro contradiction) over splits
  * pattern_stability          - mean of pattern confidence over splits
  * failure_recurrence         - 1 - mean of recurring failure penalty
  * overfit_penalty            - 1 - max(0, train - holdout) - holdout collapse
  * improvement_persistence    - fraction of splits with consistent improvement

These components roll up into a single overall consistency score.
The score is *advisory* — it is not a real performance metric, just deterministic
fixture math used to rank/weight strategies for paper research only.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Iterable

from .replay_models import ReplayResult


@dataclass(frozen=True)
class SplitReplayResult:
    """Result of replaying a single strategy across a single walk-forward split."""
    split_id: str
    strategy_id: str
    strategy_family: str
    split_type: str
    train_passed: bool
    validation_passed: bool
    holdout_passed: bool
    train_score: float
    validation_score: float
    holdout_score: float
    score_variance: float
    regime_tags_covered: tuple[str, ...]
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "split_id": self.split_id,
            "strategy_id": self.strategy_id,
            "strategy_family": self.strategy_family,
            "split_type": self.split_type,
            "train_passed": self.train_passed,
            "validation_passed": self.validation_passed,
            "holdout_passed": self.holdout_passed,
            "train_score": round(self.train_score, 6),
            "validation_score": round(self.validation_score, 6),
            "holdout_score": round(self.holdout_score, 6),
            "score_variance": round(self.score_variance, 6),
            "regime_tags_covered": list(self.regime_tags_covered),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class StrategyConsistencyScore:
    """Per-strategy aggregate consistency score across all splits."""
    strategy_id: str
    strategy_family: str
    split_pass_rate: float
    validation_stability: float
    holdout_survival: float
    regime_coverage: float
    family_consistency: float
    score_variance: float
    drawdown_proxy_stability: float
    liquidity_slippage_stability: float
    greek_iv_stability: float
    macro_stability: float
    pattern_stability: float
    failure_recurrence: float
    overfit_penalty: float
    improvement_persistence: float
    overall: float
    split_replay_results: tuple[SplitReplayResult, ...] = ()

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "strategy_family": self.strategy_family,
            "split_pass_rate": round(self.split_pass_rate, 6),
            "validation_stability": round(self.validation_stability, 6),
            "holdout_survival": round(self.holdout_survival, 6),
            "regime_coverage": round(self.regime_coverage, 6),
            "family_consistency": round(self.family_consistency, 6),
            "score_variance": round(self.score_variance, 6),
            "drawdown_proxy_stability": round(self.drawdown_proxy_stability, 6),
            "liquidity_slippage_stability": round(self.liquidity_slippage_stability, 6),
            "greek_iv_stability": round(self.greek_iv_stability, 6),
            "macro_stability": round(self.macro_stability, 6),
            "pattern_stability": round(self.pattern_stability, 6),
            "failure_recurrence": round(self.failure_recurrence, 6),
            "overfit_penalty": round(self.overfit_penalty, 6),
            "improvement_persistence": round(self.improvement_persistence, 6),
            "overall": round(self.overall, 6),
            "split_replay_results": [r.to_dict() for r in self.split_replay_results],
            "split_count": len(self.split_replay_results),
        }


@dataclass(frozen=True)
class FamilyConsistencyProfile:
    strategy_family: str
    candidate_count: int
    best_overall: float
    mean_overall: float
    median_overall: float
    family_pass_rate: float
    family_validation_stability: float
    family_holdout_survival: float
    family_regime_coverage: float
    family_overfit_penalty: float
    top_strategy_id: str
    weak_strategies: tuple[str, ...]
    regime_specialist: bool
    all_weather: bool
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "strategy_family": self.strategy_family,
            "candidate_count": self.candidate_count,
            "best_overall": round(self.best_overall, 6),
            "mean_overall": round(self.mean_overall, 6),
            "median_overall": round(self.median_overall, 6),
            "family_pass_rate": round(self.family_pass_rate, 6),
            "family_validation_stability": round(self.family_validation_stability, 6),
            "family_holdout_survival": round(self.family_holdout_survival, 6),
            "family_regime_coverage": round(self.family_regime_coverage, 6),
            "family_overfit_penalty": round(self.family_overfit_penalty, 6),
            "top_strategy_id": self.top_strategy_id,
            "weak_strategies": list(self.weak_strategies),
            "regime_specialist": self.regime_specialist,
            "all_weather": self.all_weather,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class HoldoutRobustnessScore:
    """Aggregate robustness score across all holdout windows in the plan."""
    plan_id: str
    holdout_pass_rate: float
    holdout_collapse_windows: int
    macro_contradiction_holdouts: int
    bad_fill_holdouts: int
    regime_coverage: float
    min_holdout_score: float
    mean_holdout_score: float
    max_holdout_score: float
    robust: bool

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "holdout_pass_rate": round(self.holdout_pass_rate, 6),
            "holdout_collapse_windows": self.holdout_collapse_windows,
            "macro_contradiction_holdouts": self.macro_contradiction_holdouts,
            "bad_fill_holdouts": self.bad_fill_holdouts,
            "regime_coverage": round(self.regime_coverage, 6),
            "min_holdout_score": round(self.min_holdout_score, 6),
            "mean_holdout_score": round(self.mean_holdout_score, 6),
            "max_holdout_score": round(self.max_holdout_score, 6),
            "robust": self.robust,
        }


# ---------------------------------------------------------------------------
# Score helpers
# ---------------------------------------------------------------------------

def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: Iterable[float]) -> float:
    xs = list(xs)
    if not xs:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def score_strategy_from_split_results(
    strategy_id: str,
    strategy_family: str,
    split_results: list[SplitReplayResult],
    family_means: dict[str, float] | None = None,
    train_only_window_ids: set[str] | None = None,
) -> StrategyConsistencyScore:
    """Roll up a per-strategy consistency score from per-split replay results.

    `family_means` lets the scorer penalize a strategy whose family is also weak (family
    consistency: a strong family with one weak strategy is downgraded; a weak family with
    one strong strategy is upgraded to family mean).
    """
    if not split_results:
        return StrategyConsistencyScore(
            strategy_id=strategy_id, strategy_family=strategy_family,
            split_pass_rate=0.0, validation_stability=0.0, holdout_survival=0.0,
            regime_coverage=0.0, family_consistency=0.0, score_variance=0.0,
            drawdown_proxy_stability=0.0, liquidity_slippage_stability=0.0,
            greek_iv_stability=0.0, macro_stability=0.0, pattern_stability=0.0,
            failure_recurrence=0.0, overfit_penalty=0.0, improvement_persistence=0.0,
            overall=0.0, split_replay_results=tuple(split_results),
        )

    family_means = family_means or {}
    train_only_window_ids = train_only_window_ids or set()

    n_splits = len(split_results)
    train_passes = sum(1 for r in split_results if r.train_passed)
    val_passes = sum(1 for r in split_results if r.validation_passed)
    holdout_passes = sum(1 for r in split_results if r.holdout_passed)

    # All-split pass: a split passes iff validation and holdout both pass.
    passed_splits = [r for r in split_results if r.validation_passed and r.holdout_passed]
    split_pass_rate = _clamp01(len(passed_splits) / n_splits)
    validation_stability = _clamp01(val_passes / n_splits)
    holdout_survival = _clamp01(holdout_passes / n_splits)

    # Regime coverage: distinct regimes touched by passing splits / distinct regimes touched at all.
    all_regimes = {tag for r in split_results for tag in r.regime_tags_covered}
    passed_regimes = {tag for r in passed_splits for tag in r.regime_tags_covered}
    regime_coverage = _clamp01(len(passed_regimes & all_regimes) / max(1, len(all_regimes)))

    # Score variance across splits.
    overall_scores = [_clamp01((r.train_score + r.validation_score + r.holdout_score) / 3.0) for r in split_results]
    score_variance = _clamp01(1.0 - min(1.0, _stdev(overall_scores)))

    # Drawdown proxy: lower validation-vs-holdout dispersion = better.
    deltas = [abs(r.validation_score - r.holdout_score) for r in split_results]
    drawdown_proxy_stability = _clamp01(1.0 - _mean(deltas))

    # Family consistency: a strategy in a strong family is rewarded; in a weak family, the
    # strategy is pulled toward the family mean.
    family_mean = family_means.get(strategy_family, 0.5)
    own_overall = _mean(overall_scores)
    family_consistency = _clamp01(0.5 * own_overall + 0.5 * family_mean)

    # Liquidity/slippage stability proxy: validation/holdout surviving splits usually correlate
    # with healthy regime_context; we approximate by 1 - mean(1 - min(val, holdout)).
    ls_stability = _mean([max(r.validation_score, r.holdout_score) for r in split_results])

    # Greek/IV stability: average of validation+holdout scores for split_results that have
    # >= 1 holdout pass — proxy for the structure surviving the IV context.
    holdout_passed_results = [r for r in split_results if r.holdout_passed]
    greek_iv_stability = _mean([(r.validation_score + r.holdout_score) / 2.0 for r in holdout_passed_results]) if holdout_passed_results else 0.0

    # Macro stability proxy: 1 - mean(1 - holdout_score).
    macro_stability = _mean([r.holdout_score for r in split_results])

    # Pattern stability proxy: 1 - mean(1 - max(val, holdout)).
    pattern_stability = _mean([max(r.validation_score, r.holdout_score) for r in split_results])

    # Failure recurrence proxy: 1 - (loss_count / total).
    loss_count = sum(1 for r in split_results if not r.holdout_passed)
    failure_recurrence = _clamp01(1.0 - loss_count / max(1, n_splits))

    # Overfit penalty: if train_passes >> (val+holdout)_passes, penalty is high.
    train_minus_oos = max(0.0, train_passes / n_splits - (val_passes + holdout_passes) / (2.0 * n_splits))
    holdout_collapse = 1.0 if holdout_passes == 0 and train_passes > 0 else 0.0
    overfit_penalty = _clamp01(1.0 - min(1.0, 0.6 * train_minus_oos + 0.4 * holdout_collapse))

    # Improvement persistence: fraction of splits where validation and holdout agree direction.
    agreement = sum(1 for r in split_results
                    if (r.validation_score >= 0.5) == (r.holdout_score >= 0.5))
    improvement_persistence = _clamp01(agreement / n_splits)

    overall = round(_clamp01(
        0.18 * split_pass_rate
        + 0.14 * validation_stability
        + 0.16 * holdout_survival
        + 0.08 * regime_coverage
        + 0.08 * family_consistency
        + 0.06 * score_variance
        + 0.05 * drawdown_proxy_stability
        + 0.05 * ls_stability
        + 0.05 * greek_iv_stability
        + 0.05 * macro_stability
        + 0.04 * pattern_stability
        + 0.03 * failure_recurrence
        + 0.02 * overfit_penalty
        + 0.01 * improvement_persistence
    ), 6)

    return StrategyConsistencyScore(
        strategy_id=strategy_id,
        strategy_family=strategy_family,
        split_pass_rate=round(split_pass_rate, 6),
        validation_stability=round(validation_stability, 6),
        holdout_survival=round(holdout_survival, 6),
        regime_coverage=round(regime_coverage, 6),
        family_consistency=round(family_consistency, 6),
        score_variance=round(score_variance, 6),
        drawdown_proxy_stability=round(drawdown_proxy_stability, 6),
        liquidity_slippage_stability=round(ls_stability, 6),
        greek_iv_stability=round(greek_iv_stability, 6),
        macro_stability=round(macro_stability, 6),
        pattern_stability=round(pattern_stability, 6),
        failure_recurrence=round(failure_recurrence, 6),
        overfit_penalty=round(overfit_penalty, 6),
        improvement_persistence=round(improvement_persistence, 6),
        overall=overall,
        split_replay_results=tuple(split_results),
    )


def build_family_consistency_profile(
    family: str,
    strategy_scores: list[StrategyConsistencyScore],
    known_regimes: set[str],
) -> FamilyConsistencyProfile:
    if not strategy_scores:
        return FamilyConsistencyProfile(
            strategy_family=family, candidate_count=0, best_overall=0.0,
            mean_overall=0.0, median_overall=0.0, family_pass_rate=0.0,
            family_validation_stability=0.0, family_holdout_survival=0.0,
            family_regime_coverage=0.0, family_overfit_penalty=0.0,
            top_strategy_id="", weak_strategies=(),
            regime_specialist=False, all_weather=False,
        )
    overalls = sorted(s.score_variance for s in strategy_scores)
    best = max(s.overall for s in strategy_scores)
    mean_overall = _mean([s.overall for s in strategy_scores])
    median_overall = overalls[len(overalls) // 2]
    family_pass_rate = _mean([s.split_pass_rate for s in strategy_scores])
    family_validation_stability = _mean([s.validation_stability for s in strategy_scores])
    family_holdout_survival = _mean([s.holdout_survival for s in strategy_scores])
    family_regime_coverage = _mean([s.regime_coverage for s in strategy_scores])
    family_overfit_penalty = _mean([s.overfit_penalty for s in strategy_scores])
    top = sorted(strategy_scores, key=lambda s: (-s.overall, s.strategy_id))[0]
    weak = tuple(sorted(s.strategy_id for s in strategy_scores if s.overall < 0.40))
    regime_tags_covered: set[str] = set()
    for s in strategy_scores:
        for r in s.split_replay_results:
            regime_tags_covered.update(r.regime_tags_covered)
    specialist = len(regime_tags_covered) <= max(1, len(known_regimes) // 4)
    all_weather = len(regime_tags_covered) >= max(2, len(known_regimes) - 1)
    return FamilyConsistencyProfile(
        strategy_family=family,
        candidate_count=len(strategy_scores),
        best_overall=round(best, 6),
        mean_overall=round(mean_overall, 6),
        median_overall=round(median_overall, 6),
        family_pass_rate=round(family_pass_rate, 6),
        family_validation_stability=round(family_validation_stability, 6),
        family_holdout_survival=round(family_holdout_survival, 6),
        family_regime_coverage=round(family_regime_coverage, 6),
        family_overfit_penalty=round(family_overfit_penalty, 6),
        top_strategy_id=top.strategy_id,
        weak_strategies=weak,
        regime_specialist=specialist,
        all_weather=all_weather,
    )


def build_holdout_robustness(
    plan_id: str,
    split_results: list[SplitReplayResult],
    known_regimes: set[str],
    macro_contradiction_regimes: set[str] | None = None,
    bad_fill_regimes: set[str] | None = None,
) -> HoldoutRobustnessScore:
    macro_contradiction_regimes = macro_contradiction_regimes or {"macro_contradiction_pressure"}
    bad_fill_regimes = bad_fill_regimes or {"high_spread_bad_fill", "low_liquidity_decay", "short_duration_bad_fill"}
    holdout_results = list(split_results)
    if not holdout_results:
        return HoldoutRobustnessScore(
            plan_id=plan_id, holdout_pass_rate=0.0, holdout_collapse_windows=0,
            macro_contradiction_holdouts=0, bad_fill_holdouts=0,
            regime_coverage=0.0, min_holdout_score=0.0, mean_holdout_score=0.0,
            max_holdout_score=0.0, robust=False,
        )
    holdout_scores = [r.holdout_score for r in holdout_results]
    collapse = sum(1 for r in holdout_results if not r.holdout_passed)
    macro_h = sum(1 for r in holdout_results if set(r.regime_tags_covered) & macro_contradiction_regimes)
    bad_h = sum(1 for r in holdout_results if set(r.regime_tags_covered) & bad_fill_regimes)
    all_regimes = {tag for r in holdout_results for tag in r.regime_tags_covered}
    robust = (sum(1 for r in holdout_results if r.holdout_passed) / len(holdout_results)) >= 0.4 and collapse < len(holdout_results) // 2
    return HoldoutRobustnessScore(
        plan_id=plan_id,
        holdout_pass_rate=round(_mean([1.0 if r.holdout_passed else 0.0 for r in holdout_results]), 6),
        holdout_collapse_windows=collapse,
        macro_contradiction_holdouts=macro_h,
        bad_fill_holdouts=bad_h,
        regime_coverage=round(len(all_regimes & known_regimes) / max(1, len(known_regimes)), 6),
        min_holdout_score=round(min(holdout_scores), 6),
        mean_holdout_score=round(_mean(holdout_scores), 6),
        max_holdout_score=round(max(holdout_scores), 6),
        robust=robust,
    )


def family_means_from_scores(
    strategy_scores: list[StrategyConsistencyScore],
) -> dict[str, float]:
    out: dict[str, list[float]] = {}
    for s in strategy_scores:
        out.setdefault(s.strategy_family, []).append(s.overall)
    return {family: round(_mean(values), 6) for family, values in out.items()}
