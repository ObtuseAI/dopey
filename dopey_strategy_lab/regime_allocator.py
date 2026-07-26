"""Deterministic regime-aware allocation profiles for the offline ensemble allocator.

Each major fixture regime maps to family preference multipliers. This layer is fixture math
only; it does not consume live market data. The regime tags mirror the deterministic macro /
walk-forward fixture regime vocabulary.
"""
from __future__ import annotations

from .ensemble_models import RegimeAllocationProfile


REGIME_ALLOCATOR_VERSION = "dopey-regime-allocator-v1"

DIRECTIONAL = "directional_convexity"
VOL_EXPANSION = "volatility_expansion"
VOL_COMPRESSION = "volatility_compression"
SHORT_DURATION = "short_duration_defined_risk"

_TREND = "trend"
_EVENT_VOL = "event_vol"
_POST_EVENT_CRUSH = "post_event_crush"
_BAD_FILL = "bad_fill"
_MACRO_CONTRADICTION = "macro_contradiction"


def _profile(preferred, penalized, starve, multipliers, notes="") -> RegimeAllocationProfile:
    return RegimeAllocationProfile(
        regime_tag="",
        preferred_families=sorted(preferred),
        penalized_families=sorted(penalized),
        starve_families=sorted(starve),
        family_preference_multiplier={k: round(v, 3) for k, v in multipliers.items()},
        regime_notes=notes,
    )


def build_regime_profiles() -> dict[str, RegimeAllocationProfile]:
    """Return the deterministic regime-class -> family preference profile map."""
    profiles: dict[str, RegimeAllocationProfile] = {}

    # Trend / breakout regimes — prefer directional convexity.
    trend = _profile(
        preferred={DIRECTIONAL},
        penalized={VOL_COMPRESSION},
        starve=set(),
        multipliers={DIRECTIONAL: 1.15, VOL_EXPANSION: 1.00, VOL_COMPRESSION: 0.80, SHORT_DURATION: 0.90},
        notes="confirmed trend rewards directional convexity; short-duration only if liquidity is strong",
    )
    profiles[_TREND] = trend

    # Event-vol / macro-shock regimes — prefer vol expansion only if IV surface confirms.
    event_vol = _profile(
        preferred={VOL_EXPANSION},
        penalized={VOL_COMPRESSION, SHORT_DURATION},
        starve=set(),
        multipliers={VOL_EXPANSION: 1.15, DIRECTIONAL: 0.85, VOL_COMPRESSION: 0.75, SHORT_DURATION: 0.75},
        notes="event vol rewards long-vol only when IV expansion is confirmed and premium is not a trap",
    )
    profiles[_EVENT_VOL] = event_vol

    # Post-event IV crush / range regimes — prefer compression.
    crush = _profile(
        preferred={VOL_COMPRESSION},
        penalized={VOL_EXPANSION, DIRECTIONAL},
        starve=set(),
        multipliers={VOL_COMPRESSION: 1.15, SHORT_DURATION: 0.95, VOL_EXPANSION: 0.70, DIRECTIONAL: 0.80},
        notes="post-event crush rewards compression; directional fakeout setups penalized",
    )
    profiles[_POST_EVENT_CRUSH] = crush

    # Bad-fill / low-liquidity regimes — starve weak signals, prefer liquidity.
    bad_fill = _profile(
        preferred=set(),
        penalized={SHORT_DURATION},
        starve={SHORT_DURATION, VOL_EXPANSION},
        multipliers={DIRECTIONAL: 0.85, VOL_EXPANSION: 0.70, VOL_COMPRESSION: 0.80, SHORT_DURATION: 0.55},
        notes="low liquidity starves short-duration and fragile multi-leg structures",
    )
    profiles[_BAD_FILL] = bad_fill

    # Macro contradiction regimes — reduce allocation, research-only.
    contradiction = _profile(
        preferred=set(),
        penalized={DIRECTIONAL, VOL_COMPRESSION, VOL_EXPANSION},
        starve=set(),
        multipliers={DIRECTIONAL: 0.70, VOL_EXPANSION: 0.75, VOL_COMPRESSION: 0.75, SHORT_DURATION: 0.85},
        notes="macro contradiction reduces directional and shock-exposed allocation; research-only",
    )
    profiles[_MACRO_CONTRADICTION] = contradiction

    return profiles


# Deterministic mapping from concrete fixture regime tags to regime classes.
REGIME_TAG_CLASS: dict[str, str] = {
    "bullish_breakout": _TREND,
    "bearish_breakdown": _TREND,
    "trend_vol_expansion": _TREND,
    "event_vol_expansion": _EVENT_VOL,
    "pre_fomc_vol_expansion": _EVENT_VOL,
    "post_event_iv_crush": _POST_EVENT_CRUSH,
    "chop_vol_compression": _POST_EVENT_CRUSH,
    "low_liquidity_decay": _BAD_FILL,
    "high_spread_bad_fill": _BAD_FILL,
    "macro_shock_risk_off": _MACRO_CONTRADICTION,
    "gap_reversal": _MACRO_CONTRADICTION,
}


def regime_class_for_tag(regime_tag: str) -> str:
    return REGIME_TAG_CLASS.get(regime_tag, _MACRO_CONTRADICTION)


def regime_multiplier_for_family(regime_class: str, strategy_family: str, *, iv_confirms_expansion: bool = False,
                                 liquidity_robust: bool = False, macro_confirmed: bool = False) -> float:
    """Deterministic per-family multiplier for a regime class with evidence gates."""
    profiles = build_regime_profiles()
    profile = profiles.get(regime_class, profiles[_MACRO_CONTRADICTION])
    base = profile.family_preference_multiplier.get(strategy_family, 0.80)

    if regime_class == _EVENT_VOL and strategy_family == VOL_EXPANSION:
        # Vol expansion only preferred when IV surface confirms expansion.
        if not iv_confirms_expansion:
            base = round(base - 0.30, 3)
    if regime_class == _EVENT_VOL and strategy_family == DIRECTIONAL:
        if not macro_confirmed:
            base = round(base - 0.10, 3)
    if regime_class == _TREND and strategy_family == SHORT_DURATION:
        if not liquidity_robust:
            base = round(base - 0.15, 3)
    if regime_class == _BAD_FILL:
        if not liquidity_robust:
            base = round(min(base, 0.55), 3)
    return max(0.50, min(1.20, base))


def regime_profiles_to_dict() -> dict[str, dict]:
    return {key: profile.to_dict() for key, profile in build_regime_profiles().items()}
