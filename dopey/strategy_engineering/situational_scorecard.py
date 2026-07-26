"""Situational Scorecard: the trading equivalent of a championship call sheet.

The greatest football programs (Saban's process, Belichick's situational
mastery, Walsh's Standard of Performance) do not run "a strategy." They run a
SITUATION-INDEXED CALL SHEET: for each distinct situation - down and distance,
field position, score, opponent tendency - there is a specific call and a
graded history of how it has done. The edge is preparation and discipline, not
a single trick play; and the deepest principle is that you win by "eliminating
the negative plays," not by forcing hero plays.

This synthesizes DOPEY's independent evidence into that call sheet. The
situations are (strategy family x entry context); for each, it fuses:
  - the Trade Memory Graph's conditional outcome (film study: how did this
    exact situation grade historically?),
  - the cross-lane convergence stance (are the units - independent lanes -
    corroborating a direction?),
  - the option-cost verdict (does any underlying edge survive expression as a
    long option, net of the theta + spread "tax"?),
and it emits a disciplined CALL. Crucially, at L0 there is no "TRADE" call -
the strongest available call is "monitor for forward evidence." The dominant,
highest-conviction call is AVOID: the contexts the film says are systematically
worst. That is a risk-management research finding, not proof of edge.

Measure-only, not_edge_evidence. A call sheet of what to AVOID and what to
watch, never a promise or an order.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .trade_memory import MEMORY_VERSION, OUTCOME_UNIT
from .trade_memory_active import load_active_trade_memory_summary

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ART = REPO_ROOT / "artifacts" / "dopey"
SCORECARD_PATH = ART / "strategy_engineering" / "situational_scorecard.json"

SCORECARD_VERSION = "dopey-situational-scorecard-v2"

# Map a memory-graph family to a convergence family where they align.
MEMORY_TO_CONVERGENCE = {
    "momentum": "momentum_continuation",
    "breakout": "momentum_continuation",
    "relative_strength": "momentum_continuation",
    "trend_pullback": "mean_reversion",
    "fakeout": "mean_reversion",
    "market_regime": None,  # macro/regime family - no single directional convergence
}

# A context is "avoid-grade" when its historical mean is both clearly negative
# and the worst (or near-worst) bucket for that family.
AVOID_MEAN_RETURN = -0.6
STRONG_AVOID_MEAN_RETURN = -1.0
# Course management (golf): aim where the miss is safe. A context whose miss
# pattern is catastrophic - a large share of near-total premium losses - is
# AVOID even when its mean looks mild; the double bogey kills the round.
CATASTROPHIC_MISS_SHARE = 0.25


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _convergence_by_family(convergence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for family in convergence.get("families", []):
        out[str(family.get("family"))] = family
    return out


def _call_for_context(
    family_stats: dict[str, Any],
    context_stats: dict[str, Any],
    convergence_family: dict[str, Any] | None,
) -> dict[str, Any]:
    mean_return = float(
        context_stats.get("mean_trade_return_model_units", 0.0)
    )
    family_buckets = family_stats.get("conditional_by_stretch", {})
    family_means = [
        float(value["mean_trade_return_model_units"])
        for value in family_buckets.values()
        if value.get("count", 0) >= 200
    ]
    is_worst = bool(family_means) and mean_return <= min(family_means) + 1e-9

    corroborated = bool(
        convergence_family
        and convergence_family.get("verdict") in ("corroborated", "corroborated_strong")
    )
    survives_cost = (
        convergence_family
        and convergence_family.get("option_cost_annotation", {}).get("survives_long_option_costs")
    )
    consensus = convergence_family.get("consensus_sign") if convergence_family else None

    catastrophic_share = float(context_stats.get("catastrophic_loss_share", 0.0) or 0.0)
    # Call logic - discipline first: eliminate the negative plays.
    if mean_return <= STRONG_AVOID_MEAN_RETURN and is_worst:
        call, rationale = "avoid_strong", "worst historical context for this family; deep negative expectancy"
    elif mean_return <= AVOID_MEAN_RETURN:
        call, rationale = "avoid", "negative historical expectancy in this context"
    elif (
        catastrophic_share >= CATASTROPHIC_MISS_SHARE
        and mean_return <= 0.0
    ):
        call, rationale = (
            "avoid_catastrophic_miss",
            f"miss pattern is unsafe: {catastrophic_share:.0%} of trades here lost >=90% of premium",
        )
    elif corroborated and consensus == "positive" and survives_cost is True:
        call, rationale = "monitor_candidate", "corroborated positive AND survives option costs - accrue forward evidence"
    elif corroborated and consensus == "positive" and survives_cost is False:
        call, rationale = "no_tradeable_edge", "corroborated on the underlying but does NOT survive long-option costs"
    elif convergence_family and convergence_family.get("verdict") == "contested_lanes_disagree":
        call, rationale = "contested_research_only", "independent lanes disagree on sign - investigate, do not act"
    else:
        call, rationale = "neutral_monitor", "no strong signal either way; least-bad contexts only"
    return {
        "call": call,
        "rationale": rationale,
        "historical_mean_trade_return_model_units": round(mean_return, 5),
        "historical_outcome_unit": OUTCOME_UNIT,
        "historical_win_rate": context_stats.get("win_rate"),
        "historical_sample": context_stats.get("count"),
        "miss_pattern": {
            "p10_trade_return_model_units": context_stats.get(
                "p10_trade_return_model_units"
            ),
            "catastrophic_loss_share": context_stats.get("catastrophic_loss_share"),
            "mean_max_adverse_excursion_premium_units": context_stats.get(
                "mean_max_adverse_excursion_premium_units"
            ),
        },
        "is_worst_context_for_family": is_worst,
        "convergence_verdict": convergence_family.get("verdict") if convergence_family else "no_convergence_mapping",
        "survives_long_option_costs": survives_cost,
    }


def _current_market_situation(macro: dict[str, Any]) -> dict[str, Any]:
    """The 'opponent this week': today's regime, as a situation modifier."""
    vts = macro.get("vol_term_structure", {}) if isinstance(macro, dict) else {}
    liq = macro.get("liquidity_impulse", {}) if isinstance(macro, dict) else {}
    vix = vts.get("VIX")
    vix3m = vts.get("VIX3M")
    contango = (vix is not None and vix3m is not None and float(vix3m) > float(vix))
    impulse = liq.get("impulse_4w_pct")
    return {
        "vix": vix,
        "vix_term_structure": "contango_calm" if contango else "backwardation_or_flat",
        "liquidity_impulse_4w_pct": impulse,
        "liquidity_state": (
            "flooding" if isinstance(impulse, (int, float)) and impulse > 0.01
            else "draining" if isinstance(impulse, (int, float)) and impulse < -0.01
            else "neutral"
        ),
        "note": "regime is a situation modifier; the calls below are conditioned on historical context, not this snapshot",
    }


def build_situational_scorecard(
    memory_summary: dict[str, Any],
    convergence: dict[str, Any],
    macro: dict[str, Any],
) -> dict[str, Any]:
    convergence_by_family = _convergence_by_family(convergence)
    situations: list[dict[str, Any]] = []
    memory_version = str(memory_summary.get("memory_version", ""))
    memory_is_current = memory_version == MEMORY_VERSION
    per_family = memory_summary.get("per_family", {}) if memory_is_current else {}
    for family, family_stats in per_family.items():
        convergence_key = MEMORY_TO_CONVERGENCE.get(family)
        convergence_family = convergence_by_family.get(convergence_key) if convergence_key else None
        for context, context_stats in family_stats.get("conditional_by_stretch", {}).items():
            if int(context_stats.get("count", 0)) < 200:
                continue
            call = _call_for_context(family_stats, context_stats, convergence_family)
            situations.append({"family": family, "entry_context": context, **call})
    avoid = [s for s in situations if s["call"].startswith("avoid")]
    monitor = [s for s in situations if s["call"] == "monitor_candidate"]
    scorecard = {
        "artifact_type": "situational_scorecard",
        "scorecard_version": SCORECARD_VERSION,
        "trade_memory_evidence_status": (
            "current_fractional_return_units"
            if memory_is_current
            else "blocked_incompatible_trade_memory_version"
        ),
        "expected_trade_memory_version": MEMORY_VERSION,
        "observed_trade_memory_version": memory_version or "missing",
        "historical_outcome_unit": OUTCOME_UNIT,
        "current_market_situation": _current_market_situation(macro),
        "situations": sorted(
            situations,
            key=lambda situation: situation[
                "historical_mean_trade_return_model_units"
            ],
        ),
        "avoid_list": [
            {
                "family": situation["family"],
                "entry_context": situation["entry_context"],
                "mean_trade_return_model_units": situation[
                    "historical_mean_trade_return_model_units"
                ],
            }
            for situation in sorted(
                avoid,
                key=lambda value: value[
                    "historical_mean_trade_return_model_units"
                ],
            )
        ],
        "monitor_candidates": [{"family": s["family"], "entry_context": s["entry_context"]} for s in monitor],
        "headline": (
            _headline(avoid, monitor, situations)
            if memory_is_current
            else "trade-memory evidence blocked: rebuild required for fractional-return units"
        ),
        "coaching_principle": (
            "win by eliminating the negative plays: the highest-conviction calls are AVOID, "
            "as a research risk-control finding, not an edge claim. No TRADE call exists at L0; "
            "the best available call is monitor-for-forward-evidence"
        ),
        "not_edge_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return scorecard


def _headline(avoid: list[dict[str, Any]], monitor: list[dict[str, Any]], situations: list[dict[str, Any]]) -> str:
    if not situations:
        return "no situations with sufficient history yet"
    contexts = sorted({s["entry_context"] for s in avoid})
    parts = [f"{len(avoid)}/{len(situations)} situations are AVOID-grade"]
    if contexts:
        parts.append("worst entry contexts: " + ", ".join(contexts))
    parts.append(f"{len(monitor)} monitor-candidate(s)")
    return "; ".join(parts)


def run_situational_scorecard() -> dict[str, Any]:
    from dopey_research_pipeline.artifact_io import write_json_atomic

    try:
        memory_summary = load_active_trade_memory_summary(
            ART / "trade_memory",
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        memory_summary = {
            "memory_version": "unavailable_active_generation",
            "active_generation_error": str(error),
        }
    convergence = _load(ART / "strategy_engineering" / "cross_lane_convergence.json")
    macro = _load(ART / "macro_context" / "macro_context_summary.json")
    scorecard = build_situational_scorecard(memory_summary, convergence, macro)
    write_json_atomic(SCORECARD_PATH, scorecard)
    return scorecard
