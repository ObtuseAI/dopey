"""Deterministic scorecards for pattern fixtures."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .pattern_fixture_library import PatternFixture, build_pattern_fixture_library


PATTERN_SCORECARD_VERSION = "dopey-pattern-scorecard-v1"


@dataclass(frozen=True)
class PatternScorecard:
    pattern_id: str
    strategy_family: str
    regime_tag: str
    family_match_score: float
    failure_penalty_score: float
    confidence_score: float
    directional_alignment_score: float
    volatility_alignment_score: float
    overall_score: float
    status: str
    notes: str = ""
    model_version: str = PATTERN_SCORECARD_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _family_direction(family: str) -> str:
    if family == "volatility_compression":
        return "neutral"
    if family == "volatility_expansion":
        return "neutral"
    if family == "directional_convexity":
        return "long"
    if family == "short_duration_defined_risk":
        return "long"
    return "neutral"


def _family_volatility_bias(family: str) -> str:
    if family == "volatility_compression":
        return "compression"
    if family in {"volatility_expansion", "directional_convexity"}:
        return "expansion"
    return "neutral"


def score_pattern_fixture(
    fixture: PatternFixture,
    strategy_family: str,
    regime_tag: str,
    active_failure_modes: list[str] | None = None,
) -> PatternScorecard:
    applies = regime_tag in fixture.regime_tags
    preferred = strategy_family in fixture.preferred_strategy_families
    penalized = strategy_family in fixture.penalized_strategy_families
    family_match = 1.0 if preferred else (0.35 if penalized else 0.55)
    if not applies:
        family_match *= 0.65
    failure_modes = active_failure_modes or []
    failure_penalty = 0.0
    if penalized:
        failure_penalty += 0.35
    if fixture.failure_mode in failure_modes:
        failure_penalty += 0.25
    direction = _family_direction(strategy_family)
    volatility = _family_volatility_bias(strategy_family)
    directional_alignment = 1.0 if fixture.directional_bias in {direction, "neutral"} else 0.45
    volatility_alignment = 1.0 if fixture.volatility_bias in {volatility, "neutral"} else 0.45
    score = _clamp(
        0.35 * family_match
        + 0.25 * fixture.confidence
        + 0.15 * directional_alignment
        + 0.15 * volatility_alignment
        + 0.10 * (1.0 if applies else 0.50)
        - failure_penalty,
        0.0,
        1.0,
    )
    if score >= 0.70:
        status = "supports_family"
    elif score >= 0.45:
        status = "neutral"
    else:
        status = "penalizes_family"
    return PatternScorecard(
        pattern_id=fixture.pattern_id,
        strategy_family=strategy_family,
        regime_tag=regime_tag,
        family_match_score=round(family_match, 6),
        failure_penalty_score=round(_clamp(failure_penalty, 0.0, 1.0), 6),
        confidence_score=round(fixture.confidence, 6),
        directional_alignment_score=round(directional_alignment, 6),
        volatility_alignment_score=round(volatility_alignment, 6),
        overall_score=round(score, 6),
        status=status,
        notes="deterministic pattern fixture score; not a predictive signal",
    )


def score_pattern_context(
    strategy_family: str,
    regime_tag: str,
    fixtures: list[PatternFixture] | None = None,
    active_failure_modes: list[str] | None = None,
) -> list[PatternScorecard]:
    rows = fixtures or build_pattern_fixture_library()
    matching = [p for p in rows if regime_tag in p.regime_tags]
    if not matching:
        matching = rows
    return [
        score_pattern_fixture(p, strategy_family, regime_tag, active_failure_modes)
        for p in matching
    ]


def summarize_pattern_scores(scorecards: list[PatternScorecard]) -> dict:
    if not scorecards:
        return {
            "pattern_scorecard_version": PATTERN_SCORECARD_VERSION,
            "average_pattern_score": 0.0,
            "supporting_patterns": [],
            "penalizing_patterns": [],
        }
    avg = round(sum(s.overall_score for s in scorecards) / len(scorecards), 6)
    return {
        "pattern_scorecard_version": PATTERN_SCORECARD_VERSION,
        "average_pattern_score": avg,
        "supporting_patterns": [s.pattern_id for s in scorecards if s.status == "supports_family"],
        "penalizing_patterns": [s.pattern_id for s in scorecards if s.status == "penalizes_family"],
        "fixture_only": True,
    }
