"""Dopey analysis fusion: combine all five analysis layers into one AnalysisFusionScore.

Rule: no single layer dominates. A strategy with strong technical setup but bad liquidity,
bad macro regime, weak fundamental context, or poor replay consistency must be downgraded.
Contradictions between layers incur a penalty. Offline; deterministic.
"""
from __future__ import annotations

from .models import (
    AnalysisFusionScore, MacroContext, MicrostructureContext, TechnicalContext,
    FundamentalContext, PatternSignal,
)
from .macro_analysis import score_macro
from .microstructure_analysis import score_microstructure
from .technical_analysis import score_technical
from .fundamental_analysis import score_fundamental
from .pattern_recognition import score_patterns


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _contradiction_penalty(macro: float, micro: float, technical: float,
                           fundamental: float, pattern: float) -> float:
    """Penalize when one layer is strongly positive while another is strongly negative."""
    scores = [macro, micro, technical, fundamental, pattern]
    hi = max(scores)
    lo = min(scores)
    spread = hi - lo
    # large spread between layers = contradiction; penalty grows with spread above 0.4
    return round(max(0.0, (spread - 0.4) * 1.2), 6)


def fuse_analysis(*, macro_ctx: MacroContext, micro_ctx: MicrostructureContext,
                  tech_ctx: TechnicalContext, fund_ctx: FundamentalContext,
                  patterns: list[PatternSignal],
                  replay_confirmation_score: float = 0.0,
                  freshness_reliability: float = 1.0,
                  family_regime_alignment: float | None = None,
                  pattern_fixture_score: float | None = None,
                  macro_event_scenario=None,
                  strategy_family: str | None = None) -> AnalysisFusionScore:
    """Fuse all five analysis layers into one AnalysisFusionScore.

    Weighting is balanced so no single layer dominates; contradictions penalize the overall.
    `replay_confirmation_score` (0..1) lets walk-forward replay confirmation lift the overall.

    Restored context inputs (reconstructed after the branch-switch file loss; the
    tournament/evolution callers and their tests kept using them). All are optional
    and leave the base fusion untouched when absent:
    - ``pattern_fixture_score`` (0..1): pattern-fixture corpus evidence, blended
      50/50 into the pattern layer so contradicting fixtures drag it down.
    - ``macro_event_scenario`` + ``strategy_family``: deterministic macro-event
      scenario fit (score_family_macro_event), blended 70/30 into the macro
      layer - an event scenario can hurt or help but never dominate.
    - ``family_regime_alignment`` (0..1): family-vs-regime hint alignment,
      shifting the overall by at most +/-0.04 around the neutral 0.5.
    """
    macro = score_macro(macro_ctx)
    micro = score_microstructure(micro_ctx)
    technical = score_technical(tech_ctx)
    fundamental = score_fundamental(fund_ctx)
    pattern = score_patterns(patterns)

    if macro_event_scenario is not None and strategy_family:
        from .macro_family_scoring import score_family_macro_event

        event_score = score_family_macro_event(strategy_family, macro_event_scenario)
        macro = round(0.7 * macro + 0.3 * _clamp01(event_score.macro_fit_score), 6)
    if pattern_fixture_score is not None:
        pattern = round(0.5 * pattern + 0.5 * _clamp01(pattern_fixture_score), 6)

    contradiction = _contradiction_penalty(macro, micro, technical, fundamental, pattern)

    # balanced weights — no single layer > 0.25
    raw = (
        0.20 * macro
        + 0.20 * micro
        + 0.20 * technical
        + 0.15 * fundamental
        + 0.15 * pattern
        + 0.10 * replay_confirmation_score
    )
    if family_regime_alignment is not None:
        raw += 0.08 * (_clamp01(family_regime_alignment) - 0.5)
    # gate: any layer below 0.25 caps the overall (no layer can carry a weak stack)
    min_layer = min(macro, micro, technical, fundamental, pattern)
    overall = raw - contradiction
    if min_layer < 0.25:
        # weak layer drags overall toward it
        overall = round(min(overall, min_layer + 0.25), 6)
    overall = max(0.0, min(1.0, round(overall, 6)))

    summary = (f"macro={macro} micro={micro} tech={technical} "
               f"fund={fundamental} pattern={pattern} "
               f"contradiction={contradiction} replay_confirm={replay_confirmation_score}")

    return AnalysisFusionScore(
        macro_score=macro,
        microstructure_score=micro,
        technical_score=technical,
        fundamental_score=fundamental,
        pattern_score=pattern,
        contradiction_penalty=contradiction,
        freshness_reliability_score=round(freshness_reliability, 6),
        replay_confirmation_score=round(replay_confirmation_score, 6),
        overall_score=overall,
        summary=summary,
    )
