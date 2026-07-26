"""Deterministic offline regime/holdout corpus v2 models (paper-only).

Workstream A of `DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2`.

Models:
  RegimeHoldoutWindow             — single v2 holdout window with rich context.
  RegimeHoldoutCorpus             — collection of v2 holdout windows.
  SectorHoldoutContext            — sector-specific context (tech / financials / energy / etc.).
  MacroShockHoldoutContext        — macro-shock scenario context (CPI / FOMC / etc.).
  VolatilityTransitionHoldoutContext — IV / vol-transition context (pre-event, post-event, contango).
  LiquidityStressHoldoutContext   — liquidity / fill-stress context.
  CrossFamilyChallengeWindow      — challenge window designed to stress multiple families simultaneously.

All models are stdlib dataclasses, no pydantic, no network. They are the contracts consumed
by the corpus v2 builder, the coverage scorer, the v2 runner, and the meta-governor / ensemble
/ audit layers.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any


CORPUS_V2_VERSION = "dopey-regime-holdout-corpus-v2-v1"

# Window categories used by the v2 corpus. Each window belongs to exactly one primary
# category but may carry context from multiple categories.
V2_CATEGORIES: tuple[str, ...] = (
    "sector_specific",
    "macro_shock",
    "iv_transition",
    "liquidity_stress",
    "cross_family_challenge",
)

# Strategy families for which a v2 holdout may prefer or penalize outcomes.
V2_STRATEGY_FAMILIES: tuple[str, ...] = (
    "directional_convexity",
    "volatility_expansion",
    "volatility_compression",
    "short_duration_defined_risk",
)


@dataclass(frozen=True)
class SectorHoldoutContext:
    """Sector-specific holdout context."""
    sector: str                   # tech_growth | financials | energy | healthcare | small_caps | semiconductors | consumer_discretionary
    sector_signal: str            # risk_on | risk_off | rotation | defensive | momentum | breakdown
    sector_volatility_bias: str   # expansion | contraction | neutral
    sector_trend_score: float     # 0..1
    sector_relative_strength: float  # 0..1
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MacroShockHoldoutContext:
    """Macro-shock holdout context (CPI, FOMC, jobs, dollar, etc.)."""
    event_label: str              # hot_cpi | cool_cpi | hawkish_fomc | dovish_fomc | jobs_surprise | dollar_squeeze
    risk_on_off: str              # risk_on | risk_off | neutral
    yield_direction: str          # spike | crush | neutral
    vix_direction: str            # spike | crush | neutral
    macro_contradiction: float    # 0..1
    liquidity_contraction: float # 0..1
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class VolatilityTransitionHoldoutContext:
    """IV / volatility-transition holdout context."""
    transition_label: str         # pre_event_iv_expansion | post_event_iv_crush | front_iv_backwardation | normal_contango | wing_elevation_breakout | skew_collapse
    iv_effect_signed: float       # signed: +expansion / -crush
    skew_bias: str                # calls | puts | neutral
    term_shape: str               # contango | backwardation | flat
    surface_instability: float    # 0..1
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LiquidityStressHoldoutContext:
    """Liquidity / fill-stress holdout context."""
    stress_label: str             # wide_spread_opening | low_oi_chain | multi_leg_fill | late_day_fade | short_duration_cluster | macro_gap_slippage
    liquidity_quality: float      # 0..1
    spread_penalty: float         # 0..1
    slippage_penalty: float       # 0..1
    bad_fill_pressure: float      # 0..1
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CrossFamilyChallengeWindow:
    """Challenge window designed to stress multiple families simultaneously.

    Each `expected_family_pressure` entry maps a family to the expected
    paper-only stress level: positive means pressure (starve / quarantine),
    negative means support (rewards / increase attention). These are fixture
    assertions, not live performance claims.
    """
    challenge_label: str          # directional_fakeout_macro_contradiction | vol_expansion_post_event_trap | compression_breakout_shock_failure | short_duration_theta_liquidity_failure | all_family_high_uncertainty | clean_multi_signal_confirmation
    expected_family_pressure: dict[str, float]
    high_uncertainty: float       # 0..1
    cross_family_overlap: float   # 0..1
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "challenge_label": self.challenge_label,
            "expected_family_pressure": dict(self.expected_family_pressure),
            "high_uncertainty": round(self.high_uncertainty, 6),
            "cross_family_overlap": round(self.cross_family_overlap, 6),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class RegimeHoldoutWindow:
    """Single v2 holdout window with rich sector / macro / IV / liquidity / pattern context."""
    window_id: str
    regime_tag: str
    category: str                          # V2_CATEGORIES entry
    sector_context: SectorHoldoutContext
    macro_context: MacroShockHoldoutContext
    iv_surface_context: VolatilityTransitionHoldoutContext
    skew_term_context: VolatilityTransitionHoldoutContext
    liquidity_context: LiquidityStressHoldoutContext
    pattern_context: dict
    challenge_context: CrossFamilyChallengeContext | None  # only set for cross_family_challenge windows
    expected_family_pressure: dict[str, float]
    preferred_families: tuple[str, ...]
    penalized_families: tuple[str, ...]
    holdout_purpose: str
    sequence_id: int = 0
    notes: str = ""

    def __post_init__(self) -> None:
        if self.category not in V2_CATEGORIES:
            raise ValueError(f"unknown v2 category: {self.category}")
        if self.category == "cross_family_challenge" and self.challenge_context is None:
            raise ValueError(f"cross_family_challenge window {self.window_id} requires challenge_context")
        if self.category != "cross_family_challenge" and self.challenge_context is not None:
            # Acceptable but warn: not enforced.
            pass
        if not self.expected_family_pressure:
            raise ValueError(f"window {self.window_id} has no expected_family_pressure")
        for fam in self.expected_family_pressure:
            if fam not in V2_STRATEGY_FAMILIES:
                raise ValueError(f"unknown family in expected_family_pressure: {fam}")
        for fam in self.preferred_families:
            if fam not in V2_STRATEGY_FAMILIES:
                raise ValueError(f"unknown preferred family: {fam}")
        for fam in self.penalized_families:
            if fam not in V2_STRATEGY_FAMILIES:
                raise ValueError(f"unknown penalized family: {fam}")

    def to_dict(self) -> dict:
        d = {
            "window_id": self.window_id,
            "regime_tag": self.regime_tag,
            "category": self.category,
            "sector_context": self.sector_context.to_dict(),
            "macro_context": self.macro_context.to_dict(),
            "iv_surface_context": self.iv_surface_context.to_dict(),
            "skew_term_context": self.skew_term_context.to_dict(),
            "liquidity_context": self.liquidity_context.to_dict(),
            "pattern_context": dict(self.pattern_context),
            "challenge_context": self.challenge_context.to_dict() if self.challenge_context is not None else None,
            "expected_family_pressure": {k: round(float(v), 6) for k, v in self.expected_family_pressure.items()},
            "preferred_families": list(self.preferred_families),
            "penalized_families": list(self.penalized_families),
            "holdout_purpose": self.holdout_purpose,
            "sequence_id": self.sequence_id,
            "notes": self.notes,
            "deterministic_fixture_hash": self.deterministic_fixture_hash(),
        }
        return d

    def deterministic_fixture_hash(self) -> str:
        """Stable hash of the fixture (excluding the sequence_id which is assigned at build time)."""
        stripped = {
            "window_id": self.window_id,
            "regime_tag": self.regime_tag,
            "category": self.category,
            "sector_context": self.sector_context.to_dict(),
            "macro_context": self.macro_context.to_dict(),
            "iv_surface_context": self.iv_surface_context.to_dict(),
            "skew_term_context": self.skew_term_context.to_dict(),
            "liquidity_context": self.liquidity_context.to_dict(),
            "pattern_context": dict(self.pattern_context),
            "challenge_context": self.challenge_context.to_dict() if self.challenge_context is not None else None,
            "expected_family_pressure": {k: round(float(v), 6) for k, v in self.expected_family_pressure.items()},
            "preferred_families": list(self.preferred_families),
            "penalized_families": list(self.penalized_families),
            "holdout_purpose": self.holdout_purpose,
            "notes": self.notes,
        }
        return hashlib.sha256(json.dumps(stripped, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CrossFamilyChallengeContext:
    """Compat shim so a CrossFamilyChallengeWindow can be embedded in a RegimeHoldoutWindow.

    This is a thin wrapper that carries the same fields; the v2 builder uses it when
    constructing a cross-family-challenge window.
    """
    challenge_label: str
    expected_family_pressure: dict[str, float]
    high_uncertainty: float
    cross_family_overlap: float
    notes: str = ""

    @classmethod
    def from_challenge(cls, c: CrossFamilyChallengeWindow) -> "CrossFamilyChallengeContext":
        return cls(
            challenge_label=c.challenge_label,
            expected_family_pressure=dict(c.expected_family_pressure),
            high_uncertainty=c.high_uncertainty,
            cross_family_overlap=c.cross_family_overlap,
            notes=c.notes,
        )

    def to_dict(self) -> dict:
        return {
            "challenge_label": self.challenge_label,
            "expected_family_pressure": {k: round(float(v), 6) for k, v in self.expected_family_pressure.items()},
            "high_uncertainty": round(self.high_uncertainty, 6),
            "cross_family_overlap": round(self.cross_family_overlap, 6),
            "notes": self.notes,
        }


# Re-export CrossFamilyChallengeContext to be the same name as the requirement
# (`CrossFamilyChallengeWindow` is the builder-friendly name; the embedded form
# below is used inside RegimeHoldoutWindow).
@dataclass(frozen=True)
class RegimeHoldoutCorpus:
    """Collection of v2 holdout windows with deterministic hash."""
    corpus_id: str
    version: str
    windows: tuple[RegimeHoldoutWindow, ...]
    regime_coverage: tuple[str, ...]
    sector_coverage: tuple[str, ...]
    macro_coverage: tuple[str, ...]
    liquidity_stress_coverage: tuple[str, ...]
    volatility_transition_coverage: tuple[str, ...]

    @property
    def window_count(self) -> int:
        return len(self.windows)

    def deterministic_hash(self) -> str:
        payload = {
            "corpus_id": self.corpus_id,
            "version": self.version,
            "windows": [w.deterministic_fixture_hash() for w in self.windows],
            "regime_coverage": list(self.regime_coverage),
            "sector_coverage": list(self.sector_coverage),
            "macro_coverage": list(self.macro_coverage),
            "liquidity_stress_coverage": list(self.liquidity_stress_coverage),
            "volatility_transition_coverage": list(self.volatility_transition_coverage),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "corpus_id": self.corpus_id,
            "version": self.version,
            "window_count": self.window_count,
            "windows": [w.to_dict() for w in self.windows],
            "regime_coverage": list(self.regime_coverage),
            "sector_coverage": list(self.sector_coverage),
            "macro_coverage": list(self.macro_coverage),
            "liquidity_stress_coverage": list(self.liquidity_stress_coverage),
            "volatility_transition_coverage": list(self.volatility_transition_coverage),
            "deterministic_hash": self.deterministic_hash(),
        }


# Stub the embedded type so dataclass reference resolves.
CrossFamilyChallengeContext.__module__ = __name__


# ---------------------------------------------------------------------------
# Convenience constructors used by the corpus v2 builder.
# ---------------------------------------------------------------------------

def make_sector(sector: str, signal: str, vol_bias: str, trend: float, rel_strength: float, notes: str = "") -> SectorHoldoutContext:
    return SectorHoldoutContext(
        sector=sector, sector_signal=signal, sector_volatility_bias=vol_bias,
        sector_trend_score=_clamp01(trend), sector_relative_strength=_clamp01(rel_strength),
        notes=notes,
    )


def make_macro(event: str, risk: str, yld: str, vix: str, contradiction: float, liq: float, notes: str = "") -> MacroShockHoldoutContext:
    return MacroShockHoldoutContext(
        event_label=event, risk_on_off=risk, yield_direction=yld, vix_direction=vix,
        macro_contradiction=_clamp01(contradiction), liquidity_contraction=_clamp01(liq),
        notes=notes,
    )


def make_iv_transition(label: str, iv_effect: float, skew: str, term: str, instability: float, notes: str = "") -> VolatilityTransitionHoldoutContext:
    return VolatilityTransitionHoldoutContext(
        transition_label=label, iv_effect_signed=_clamp_signed(iv_effect),
        skew_bias=skew, term_shape=term, surface_instability=_clamp01(instability),
        notes=notes,
    )


def make_liquidity_stress(label: str, liq: float, spread: float, slippage: float, bad_fill: float, notes: str = "") -> LiquidityStressHoldoutContext:
    return LiquidityStressHoldoutContext(
        stress_label=label, liquidity_quality=_clamp01(liq),
        spread_penalty=_clamp01(spread), slippage_penalty=_clamp01(slippage),
        bad_fill_pressure=_clamp01(bad_fill), notes=notes,
    )


def make_challenge(label: str, family_pressure: dict[str, float], uncertainty: float, overlap: float, notes: str = "") -> CrossFamilyChallengeWindow:
    return CrossFamilyChallengeWindow(
        challenge_label=label,
        expected_family_pressure={k: float(v) for k, v in family_pressure.items()},
        high_uncertainty=_clamp01(uncertainty),
        cross_family_overlap=_clamp01(overlap),
        notes=notes,
    )


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _clamp_signed(x: float) -> float:
    return max(-1.0, min(1.0, float(x)))
