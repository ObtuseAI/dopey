"""Deterministic pattern fixture library for DOPEY.

Pattern fixtures are offline engineering inputs. They are not trained signals, market-data
features, or predictive claims.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


PATTERN_FIXTURE_CORPUS_ID = "dopey-pattern-fixture-corpus-v1"

REQUIRED_PATTERN_TYPES: tuple[str, ...] = (
    "bullish_breakout_continuation",
    "bearish_breakdown_continuation",
    "failed_breakout_reversal",
    "failed_breakdown_reversal",
    "range_pin",
    "volatility_expansion_setup",
    "post_event_iv_crush_setup",
    "liquidity_trap",
    "high_spread_false_signal",
    "gamma_squeeze_proxy",
    "theta_decay_window",
    "macro_shock_reversal",
    "chop_fakeout",
    "trend_vol_continuation",
    "low_liquidity_decay_pattern",
    "skew_warning_pattern",
)


@dataclass(frozen=True)
class PatternOutcomeHint:
    pattern_id: str
    strategy_family: str
    expected_score_delta: float
    confidence: float
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PatternFailureMode:
    pattern_id: str
    failure_mode: str
    penalized_strategy_families: list[str] = field(default_factory=list)
    severity_score: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PatternFixture:
    pattern_id: str
    pattern_type: str
    regime_tags: list[str]
    directional_bias: str
    volatility_bias: str
    confidence: float
    preferred_strategy_families: list[str]
    penalized_strategy_families: list[str]
    failure_mode: str
    expected_effect: str
    notes: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PatternFixture":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class PatternRecognitionSummary:
    corpus_id: str
    pattern_count: int
    pattern_types: list[str]
    preferred_family_counts: dict[str, int]
    penalized_family_counts: dict[str, int]
    average_confidence: float
    fixture_only: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def build_pattern_fixture_library() -> list[PatternFixture]:
    return [
        PatternFixture("pattern-bullish-breakout-continuation", "bullish_breakout_continuation",
                       ["bullish_breakout"], "long", "expansion", 0.82,
                       ["directional_convexity", "short_duration_defined_risk"],
                       ["volatility_compression"], "breakout_failure",
                       "supports long delta and useful gamma", "fixture continuation pattern"),
        PatternFixture("pattern-bearish-breakdown-continuation", "bearish_breakdown_continuation",
                       ["bearish_breakdown"], "short", "expansion", 0.78,
                       ["directional_convexity", "volatility_expansion"],
                       ["volatility_compression"], "breakdown_failure",
                       "supports bearish convexity", "fixture breakdown continuation pattern"),
        PatternFixture("pattern-failed-breakout-reversal", "failed_breakout_reversal",
                       ["gap_reversal", "range_bound_pin"], "short", "compression", 0.70,
                       ["volatility_compression"], ["directional_convexity", "short_duration_defined_risk"],
                       "false_breakout", "penalizes late directional entries", "fixture reversal pattern"),
        PatternFixture("pattern-failed-breakdown-reversal", "failed_breakdown_reversal",
                       ["gap_reversal"], "long", "compression", 0.66,
                       ["volatility_compression"], ["directional_convexity"],
                       "false_breakdown", "penalizes breakdown chasing", "fixture reversal pattern"),
        PatternFixture("pattern-range-pin", "range_pin", ["range_bound_pin", "chop_vol_compression"],
                       "neutral", "compression", 0.84, ["volatility_compression"],
                       ["volatility_expansion", "directional_convexity"], "pin_risk",
                       "rewards defined-risk compression", "fixture range pin pattern"),
        PatternFixture("pattern-vol-expansion-setup", "volatility_expansion_setup",
                       ["event_vol_expansion", "trend_vol_expansion"], "neutral", "expansion", 0.86,
                       ["volatility_expansion", "directional_convexity"],
                       ["volatility_compression"], "iv_crush_after_event",
                       "rewards long vega/gamma before expansion", "fixture vol expansion pattern"),
        PatternFixture("pattern-post-event-iv-crush", "post_event_iv_crush_setup",
                       ["post_event_iv_crush"], "neutral", "compression", 0.88,
                       ["volatility_compression"], ["volatility_expansion"],
                       "long_vega_crush", "rewards short/controlled vega", "fixture IV crush pattern"),
        PatternFixture("pattern-liquidity-trap", "liquidity_trap",
                       ["liquidity_decay", "low_liquidity_decay"], "neutral", "neutral", 0.76,
                       ["directional_convexity"], ["short_duration_defined_risk", "volatility_expansion"],
                       "liquidity_decay", "penalizes fragile fills", "fixture liquidity trap pattern"),
        PatternFixture("pattern-high-spread-false-signal", "high_spread_false_signal",
                       ["high_spread_bad_fill"], "neutral", "neutral", 0.80,
                       ["volatility_compression"], ["short_duration_defined_risk", "directional_convexity"],
                       "bad_fill_false_signal", "penalizes bad spread setups", "fixture spread pattern"),
        PatternFixture("pattern-gamma-squeeze-proxy", "gamma_squeeze_proxy",
                       ["bullish_breakout", "trend_vol_expansion"], "long", "expansion", 0.72,
                       ["directional_convexity", "volatility_expansion"], ["volatility_compression"],
                       "gamma_chase", "rewards convexity with risk control", "fixture gamma proxy pattern"),
        PatternFixture("pattern-theta-decay-window", "theta_decay_window",
                       ["range_bound_pin", "low_liquidity_decay"], "neutral", "compression", 0.74,
                       ["volatility_compression"], ["volatility_expansion", "short_duration_defined_risk"],
                       "theta_bleed", "penalizes long premium without movement", "fixture theta pattern"),
        PatternFixture("pattern-macro-shock-reversal", "macro_shock_reversal",
                       ["macro_shock_risk_off"], "short", "expansion", 0.83,
                       ["volatility_expansion", "directional_convexity"], ["volatility_compression"],
                       "macro_shock_gap", "rewards shock convexity", "fixture macro shock pattern"),
        PatternFixture("pattern-chop-fakeout", "chop_fakeout",
                       ["chop_vol_compression", "range_bound_pin"], "neutral", "compression", 0.81,
                       ["volatility_compression"], ["directional_convexity", "short_duration_defined_risk"],
                       "chop_fakeout", "penalizes fakeout chasing", "fixture chop pattern"),
        PatternFixture("pattern-trend-vol-continuation", "trend_vol_continuation",
                       ["trend_vol_expansion"], "long", "expansion", 0.85,
                       ["directional_convexity", "volatility_expansion", "short_duration_defined_risk"],
                       ["volatility_compression"], "trend_exhaustion",
                       "rewards trend continuation with expanding vol", "fixture trend/vol pattern"),
        PatternFixture("pattern-low-liquidity-decay", "low_liquidity_decay_pattern",
                       ["low_liquidity_decay", "liquidity_decay"], "neutral", "compression", 0.78,
                       ["volatility_compression"], ["short_duration_defined_risk", "volatility_expansion"],
                       "liquidity_decay", "penalizes fragile fills and premium decay", "fixture liquidity pattern"),
        PatternFixture("pattern-skew-warning", "skew_warning_pattern",
                       ["macro_shock_risk_off", "bearish_breakdown"], "short", "expansion", 0.69,
                       ["volatility_expansion"], ["volatility_compression", "short_duration_defined_risk"],
                       "skew_shock", "warns compression and short-DTE against skew shock",
                       "fixture skew warning pattern"),
    ]


def summarize_pattern_fixture_library(fixtures: list[PatternFixture] | None = None) -> PatternRecognitionSummary:
    rows = fixtures or build_pattern_fixture_library()
    preferred: dict[str, int] = {}
    penalized: dict[str, int] = {}
    for fixture in rows:
        for family in fixture.preferred_strategy_families:
            preferred[family] = preferred.get(family, 0) + 1
        for family in fixture.penalized_strategy_families:
            penalized[family] = penalized.get(family, 0) + 1
    avg_confidence = round(sum(p.confidence for p in rows) / len(rows), 6) if rows else 0.0
    return PatternRecognitionSummary(
        corpus_id=PATTERN_FIXTURE_CORPUS_ID,
        pattern_count=len(rows),
        pattern_types=sorted({p.pattern_type for p in rows}),
        preferred_family_counts=preferred,
        penalized_family_counts=penalized,
        average_confidence=avg_confidence,
    )
