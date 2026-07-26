"""Dopey family-aware deterministic fixture outcome model (offline, paper-only).

Replaces the crude one-size exit model with a fixture-driven, family-aware deterministic
outcome simulation. This is NOT real execution quality; it is a deterministic engineering
fixture simulation that lets the multi-strategy tournament separate strategy families across
regimes.

Inputs (per window + family + constructed structure):
  * direction match      - does the structure's directional bias match the regime move?
  * volatility match     - does the structure's vega bias match IV expansion/compression?
  * regime match         - family_outcome_hints[family] for this regime (0..1)
  * liquidity quality    - window.regime_context["liquidity_quality"]
  * spread penalty       - window.regime_context["spread_penalty"]
  * slippage penalty     - window.regime_context["slippage_penalty"]
  * IV crush/expansion   - window.regime_context["iv_effect"] (signed: + expansion, - crush)
  * macro contradiction  - window.regime_context["macro_contradiction"]
  * technical fakeout    - window.regime_context["technical_fakeout"]
  * pattern confidence   - window.regime_context["pattern_confidence"]
  * invalidation quality - window.regime_context["invalidation_quality"]

Outputs: deterministic paper PnL proxy, MFE/MAE proxy, invalidation result,
regime_match_score, family_fit_score. No network; no live path.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


# Required regime tags for the expanded corpus.
REQUIRED_REGIME_TAGS: tuple[str, ...] = (
    "trend_vol_expansion",
    "chop_vol_compression",
    "gap_reversal",
    "liquidity_decay",
    "event_vol_expansion",
    "post_event_iv_crush",
    "bearish_breakdown",
    "bullish_breakout",
    "range_bound_pin",
    "high_spread_bad_fill",
    "low_liquidity_decay",
    "macro_shock_risk_off",
    # Additional regime tags from the stronger walk-forward consistency expansion.
    "macro_contradiction_pressure",
    "surface_instability_fakeout",
    "short_duration_bad_fill",
    "vol_expansion_trap",
    "compression_shock_failure",
    "clean_directional_confirmation",
)

# Deterministic family-fit hints per regime (0..1). Encodes the design intent:
# directional convexity wins in breakout/breakdown/trend; volatility expansion wins in
# event-vol / macro-shock / trend; volatility compression wins in chop/range/iv-crush;
# short-duration defined-risk wins in clean trend/breakout and is punished by bad spreads /
# liquidity decay / gap reversal. These are engineering fixtures, NOT empirical claims.
REGIME_FAMILY_HINTS: dict[str, dict[str, float]] = {
    "trend_vol_expansion":      {"directional_convexity": 0.80, "volatility_expansion": 0.80, "volatility_compression": 0.20, "short_duration_defined_risk": 0.65},
    "chop_vol_compression":     {"directional_convexity": 0.25, "volatility_expansion": 0.20, "volatility_compression": 0.85, "short_duration_defined_risk": 0.40},
    "gap_reversal":             {"directional_convexity": 0.30, "volatility_expansion": 0.55, "volatility_compression": 0.45, "short_duration_defined_risk": 0.20},
    "liquidity_decay":          {"directional_convexity": 0.40, "volatility_expansion": 0.25, "volatility_compression": 0.40, "short_duration_defined_risk": 0.30},
    "event_vol_expansion":      {"directional_convexity": 0.45, "volatility_expansion": 0.90, "volatility_compression": 0.15, "short_duration_defined_risk": 0.30},
    "post_event_iv_crush":      {"directional_convexity": 0.40, "volatility_expansion": 0.15, "volatility_compression": 0.85, "short_duration_defined_risk": 0.40},
    "bearish_breakdown":        {"directional_convexity": 0.80, "volatility_expansion": 0.60, "volatility_compression": 0.20, "short_duration_defined_risk": 0.55},
    "bullish_breakout":         {"directional_convexity": 0.85, "volatility_expansion": 0.60, "volatility_compression": 0.20, "short_duration_defined_risk": 0.70},
    "range_bound_pin":          {"directional_convexity": 0.20, "volatility_expansion": 0.25, "volatility_compression": 0.85, "short_duration_defined_risk": 0.40},
    "high_spread_bad_fill":     {"directional_convexity": 0.25, "volatility_expansion": 0.25, "volatility_compression": 0.40, "short_duration_defined_risk": 0.15},
    "low_liquidity_decay":      {"directional_convexity": 0.30, "volatility_expansion": 0.25, "volatility_compression": 0.40, "short_duration_defined_risk": 0.15},
    "macro_shock_risk_off":     {"directional_convexity": 0.40, "volatility_expansion": 0.85, "volatility_compression": 0.15, "short_duration_defined_risk": 0.30},
    # Additional regimes from the stronger walk-forward consistency expansion.
    "macro_contradiction_pressure":  {"directional_convexity": 0.45, "volatility_expansion": 0.40, "volatility_compression": 0.55, "short_duration_defined_risk": 0.35},
    "surface_instability_fakeout":   {"directional_convexity": 0.35, "volatility_expansion": 0.45, "volatility_compression": 0.30, "short_duration_defined_risk": 0.20},
    "short_duration_bad_fill":      {"directional_convexity": 0.25, "volatility_expansion": 0.25, "volatility_compression": 0.35, "short_duration_defined_risk": 0.15},
    "vol_expansion_trap":           {"directional_convexity": 0.30, "volatility_expansion": 0.30, "volatility_compression": 0.55, "short_duration_defined_risk": 0.20},
    "compression_shock_failure":    {"directional_convexity": 0.25, "volatility_expansion": 0.45, "volatility_compression": 0.30, "short_duration_defined_risk": 0.15},
    "clean_directional_confirmation":{"directional_convexity": 0.88, "volatility_expansion": 0.65, "volatility_compression": 0.25, "short_duration_defined_risk": 0.78},
}

STRATEGY_FAMILIES: tuple[str, ...] = (
    "directional_convexity",
    "volatility_expansion",
    "volatility_compression",
    "short_duration_defined_risk",
)

BEARISH_REGIMES: frozenset[str] = frozenset({"bearish_breakdown", "macro_shock_risk_off"})


@dataclass
class FamilyOutcomeContext:
    """Compact deterministic outcome context derived from a window's regime_context."""
    liquidity_quality: float = 0.5
    spread_penalty: float = 0.0
    slippage_penalty: float = 0.0
    iv_effect: float = 0.0          # signed: positive = IV expansion, negative = IV crush
    macro_contradiction: float = 0.0
    technical_fakeout: float = 0.0
    pattern_confidence: float = 0.5
    invalidation_quality: float = 0.5

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_regime_context(cls, regime_context: dict | None) -> "FamilyOutcomeContext":
        rc = regime_context or {}
        return cls(
            liquidity_quality=float(rc.get("liquidity_quality", 0.5)),
            spread_penalty=float(rc.get("spread_penalty", 0.0)),
            slippage_penalty=float(rc.get("slippage_penalty", 0.0)),
            iv_effect=float(rc.get("iv_effect", 0.0)),
            macro_contradiction=float(rc.get("macro_contradiction", 0.0)),
            technical_fakeout=float(rc.get("technical_fakeout", 0.0)),
            pattern_confidence=float(rc.get("pattern_confidence", 0.5)),
            invalidation_quality=float(rc.get("invalidation_quality", 0.5)),
        )


@dataclass
class FamilyOutcome:
    """Deterministic family-aware paper outcome for one window."""
    paper_pnl: float = 0.0
    max_favorable_excursion: float = 0.0
    max_adverse_excursion: float = 0.0
    invalidation_triggered: bool = False
    regime_match_score: float = 0.0
    family_fit_score: float = 0.0
    base_structure_payoff: float = 0.0
    exit_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def family_hint(regime_tag: str, family: str, hints: dict | None = None) -> float:
    """Resolve the family-fit hint for a regime. Falls back to REGIME_FAMILY_HINTS."""
    if hints and family in hints:
        return float(hints[family])
    return float(REGIME_FAMILY_HINTS.get(regime_tag, {}).get(family, 0.3))


def _structure_payoff(structure: str, legs: list[dict], s1: float) -> float:
    """Deterministic structure payoff at expiry given terminal underlying s1.

    Legs carry 'strike' and 'option_type' and 'side'. Ratios are encoded by repeating a
    leg entry (e.g. a butterfly shorts the middle strike twice). All structures are
    defined-risk by construction.
    """
    payoff = 0.0
    for leg in legs:
        strike = float(leg.get("strike", 0.0))
        otype = leg.get("option_type", "call")
        side = leg.get("side", "buy")
        qty = float(leg.get("ratio", 1.0))
        if otype == "call":
            intrinsic = max(0.0, s1 - strike)
        else:
            intrinsic = max(0.0, strike - s1)
        if side == "buy":
            payoff += qty * intrinsic
        else:
            payoff -= qty * intrinsic
    return round(payoff, 6)


def compute_family_outcome(*, family: str, structure: str, legs: list[dict],
                           window, entry_net: float, max_loss: float,
                           hints: dict | None = None) -> FamilyOutcome:
    """Compute the deterministic family-aware paper outcome for one replayed window.

    Clearly labeled: deterministic fixture simulation, not real execution quality.
    """
    outcome = window.expected_outcome or {}
    s0 = float(window.underlying_snapshot.get("price", 0.0))
    s1 = float(outcome.get("next_underlying_price", s0))
    days = int(outcome.get("days_to_exit", 1))
    exit_reason = str(outcome.get("exit_reason", "expiry_time_decay"))

    ctx = FamilyOutcomeContext.from_regime_context(getattr(window, "regime_context", None))

    regime_match = family_hint(window.regime_tag, family, hints)

    # 1. base structure payoff (deterministic from terminal price vs strikes)
    base_payoff = _structure_payoff(structure, legs, s1)

    # 2. entry cost / credit already encoded in entry_net (net debit positive for debits,
    #    negative for credits). pnl from structure = payoff - entry_net (debits) or
    #    credit + (-payoff) for credits -> unify: base_pnl = payoff - entry_net works for
    #    debit structures; for credit structures entry_net is negative so payoff - entry_net
    #    = payoff + |credit| which double counts. Use signed entry: pnl = payoff - entry_net
    #    where entry_net is the net premium PAID (positive=debit). Credit structures pass a
    #    negative entry_net is wrong; instead the builder sets entry_net as net debit paid
    #    (>=0) for debit structures and we treat credit structures separately.
    if structure in ("iron_condor",):
        # credit structure: entry_net is the net credit received (positive). PnL = credit - max(payoff_loss,0)
        # payoff here is the negative of the spread loss (<=0). base_pnl = entry_net + payoff
        base_pnl = round(entry_net + base_payoff, 6)
    else:
        # debit structure: entry_net is net debit paid (positive). PnL = payoff - debit
        base_pnl = round(base_payoff - entry_net, 6)

    # 3. regime-fit modulation. This is a deterministic fixture simulation (NOT real execution
    #    quality): regime_match is the dominant driver so the tournament can cleanly separate
    #    which families suit which regimes. The structure payoff (base_pnl) is a secondary
    #    contributor so families still respond to the fixture's price path.
    regime_factor = 0.3 + 0.5 * regime_match          # [0.3, 0.8]
    fit_nudge = (regime_match - 0.5) * 12.0            # dominant regime-fit term [-6, +6]

    # 4. context penalties (deterministic, additive, bounded)
    penalty = (
        (1.0 - ctx.liquidity_quality) * 0.6
        + min(ctx.spread_penalty, 1.0) * 0.5
        + min(ctx.slippage_penalty, 1.0) * 0.4
        + min(ctx.macro_contradiction, 1.0) * 0.5
        + min(ctx.technical_fakeout, 1.0) * 0.5
    )

    # 5. IV effect: vol_expansion benefits from expansion, punished by crush; compression
    #    is the mirror. directional/short-duration feel a smaller IV effect.
    iv_component = 0.0
    if family == "volatility_expansion":
        iv_component = ctx.iv_effect * 2.0
    elif family == "volatility_compression":
        iv_component = -ctx.iv_effect * 2.0
    else:
        iv_component = ctx.iv_effect * 0.3

    # 6. pattern confidence boost (small) + invalidation quality cushion
    pattern_boost = (ctx.pattern_confidence - 0.5) * 1.0

    paper_pnl = round(
        fit_nudge
        + base_pnl * regime_factor
        + iv_component
        + pattern_boost
        - penalty,
        6,
    )

    # 7. excursions (deterministic proxies)
    favorable = max(0.0, base_pnl) * regime_factor + max(0.0, fit_nudge + iv_component + pattern_boost)
    adverse = max(0.0, -base_pnl) * regime_factor + penalty
    mfe = round(favorable, 6)
    mae = round(adverse, 6)

    # 8. invalidation: fixture-driven OR structural stop OR very poor regime fit
    invalidation = (
        exit_reason == "invalidation_triggered"
        or paper_pnl < -max_loss
        or regime_match < 0.20
    )
    # if invalidation quality is high, a borderline loss is treated as a controlled stop
    if invalidation and ctx.invalidation_quality >= 0.6 and paper_pnl < 0:
        paper_pnl = round(max(paper_pnl, -max_loss * 0.8), 6)

    # 9. family-fit score: regime_match adjusted down by penalties, up by pattern confidence
    family_fit = round(max(0.0, min(1.0,
        regime_match
        - (1.0 - ctx.liquidity_quality) * 0.25
        - min(ctx.macro_contradiction, 1.0) * 0.20
        - min(ctx.technical_fakeout, 1.0) * 0.15
        + (ctx.pattern_confidence - 0.5) * 0.20
    )), 6)

    return FamilyOutcome(
        paper_pnl=paper_pnl,
        max_favorable_excursion=mfe,
        max_adverse_excursion=mae,
        invalidation_triggered=invalidation,
        regime_match_score=round(regime_match, 6),
        family_fit_score=family_fit,
        base_structure_payoff=base_payoff,
        exit_reason=exit_reason,
    )
