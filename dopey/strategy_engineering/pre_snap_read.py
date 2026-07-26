"""Pre-Snap Read + Audible: diagnose the live look, then check into the right call.

The situational scorecard is the CALL SHEET - static, historical, per
(family x context). Elite coordinators and quarterbacks add the live half: the
OC motions to make the defense reveal its coverage, and the QB reads that look
pre-snap and AUDIBLES - into the right protection, or out of a bad play
entirely. And the trait that most separates winning quarterbacks is not the
hero throw; it is PROTECTING THE FOOTBALL. Turnover avoidance beats big plays.

This applies the call sheet to a specific live candidate:
  1. read the LOOK - the candidate's current entry context (stretch vs its
     20-day average) from the live spine;
  2. read the COVERAGE SHELL - today's regime (vol term structure, liquidity);
  3. cross-reference the scorecard's call for (family, this context), the
     cross-lane convergence stance, and the option-cost verdict;
  4. emit an AUDIBLE - proceed-and-monitor, check the expression, or audible to
     no-trade - biased, like a disciplined QB, toward protecting the football:
     when the read is unfavorable or uncertain, the default is throw-it-away.

Measure-only advisory. It recommends a check; it never places or sizes an
order. At L0 the strongest audible is "proceed to monitor for forward
evidence" - there is no "fire" call.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .situational_scorecard import MEMORY_TO_CONVERGENCE
from .trade_memory import spine_conditions

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ART = REPO_ROOT / "artifacts" / "dopey"

PRE_SNAP_VERSION = "dopey-pre-snap-read-v1"

# Convergence family <- memory/candidate family (reuse the scorecard's mapping)
CANDIDATE_TO_CONVERGENCE = MEMORY_TO_CONVERGENCE


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _coverage_shell(macro: Mapping[str, Any]) -> dict[str, Any]:
    vts = macro.get("vol_term_structure", {}) if isinstance(macro, dict) else {}
    liq = macro.get("liquidity_impulse", {}) if isinstance(macro, dict) else {}
    vix = vts.get("VIX")
    vix3m = vts.get("VIX3M")
    impulse = liq.get("impulse_4w_pct")
    return {
        "vix": vix,
        "vol_shell": (
            "calm_contango" if (vix is not None and vix3m is not None and float(vix3m) > float(vix))
            else "stressed_or_flat"
        ),
        "liquidity_shell": (
            "flooding" if isinstance(impulse, (int, float)) and impulse > 0.01
            else "draining" if isinstance(impulse, (int, float)) and impulse < -0.01
            else "neutral"
        ),
    }


def _scorecard_call(scorecard: Mapping[str, Any], family: str, context: str) -> dict[str, Any] | None:
    for situation in scorecard.get("situations", []):
        if situation.get("family") == family and situation.get("entry_context") == context:
            return situation
    return None


def _convergence_family(convergence: Mapping[str, Any], family: str) -> dict[str, Any] | None:
    key = CANDIDATE_TO_CONVERGENCE.get(family)
    if key is None:
        return None
    for entry in convergence.get("families", []):
        if entry.get("family") == key:
            return entry
    return None


def diagnose_pre_snap_read(
    candidate: Mapping[str, Any],
    spine_by_symbol: Mapping[str, tuple[Sequence[float], Sequence[str]]],
    scorecard: Mapping[str, Any],
    convergence: Mapping[str, Any],
    macro: Mapping[str, Any],
    as_of_date: str,
) -> dict[str, Any]:
    """Diagnose one candidate's live look and emit an audible recommendation."""
    symbol = str(candidate.get("symbol", ""))
    family = str(candidate.get("family", ""))
    direction = str(candidate.get("direction", ""))

    # 1. the LOOK: current entry context from the live spine
    if symbol in spine_by_symbol:
        closes, dates = spine_by_symbol[symbol]
        conditions = spine_conditions(closes, dates, as_of_date)
        context = str(conditions.get("stretch_bucket", "unknown"))
    else:
        conditions = {}
        context = "unknown"

    shell = _coverage_shell(macro)
    scorecard_call = _scorecard_call(scorecard, family, context)
    convergence_family = _convergence_family(convergence, family)

    # 2. the AUDIBLE - protect the football: bias to the safe call.
    reasons: list[str] = []
    if context == "unknown":
        audible, read = "check_insufficient_look", "cannot read the look (symbol not on the spine or warmup)"
    elif scorecard_call and str(scorecard_call.get("call", "")).startswith("avoid"):
        audible = "audible_to_no_trade"
        read = "unfavorable"
        reasons.append(f"scorecard grades ({family}, {context}) as {scorecard_call['call']}")
    elif convergence_family and convergence_family.get("verdict") == "contested_lanes_disagree":
        audible = "check_research_only"
        read = "mixed_coverage"
        reasons.append("independent lanes disagree on this family's direction")
    elif (
        convergence_family
        and convergence_family.get("verdict") in ("corroborated", "corroborated_strong")
        and convergence_family.get("consensus_sign") == "positive"
        and convergence_family.get("option_cost_annotation", {}).get("survives_long_option_costs") is True
    ):
        audible, read = "proceed_monitor", "favorable"
        reasons.append("corroborated positive AND survives option costs - monitor for forward evidence")
    elif (
        convergence_family
        and convergence_family.get("option_cost_annotation", {}).get("survives_long_option_costs") is False
    ):
        audible = "audible_to_no_trade"
        read = "edge_below_cost_line"
        reasons.append("any underlying edge here does not survive long-option costs")
    else:
        # uncertain -> throw it away (checkdown). Turnover avoidance is the edge.
        audible, read = "check_down_default_no_trade", "uncertain"
        reasons.append("no favorable read established; default to the safe call")

    return {
        "symbol": symbol,
        "family": family,
        "direction": direction,
        "look": {
            "entry_context": context,
            "stretch": conditions.get("stretch"),
            "rvol_bucket": conditions.get("rvol_bucket"),
        },
        "coverage_shell": shell,
        "read": read,
        "audible": audible,
        "reasons": reasons,
        "scorecard_call": scorecard_call.get("call") if scorecard_call else "no_call",
        "protect_the_football": True,
        "not_edge_evidence": True,
        "promotion_allowed": False,
    }


def build_pre_snap_reads(
    candidates: Sequence[Mapping[str, Any]],
    spine_by_symbol: Mapping[str, tuple[Sequence[float], Sequence[str]]],
    scorecard: Mapping[str, Any],
    convergence: Mapping[str, Any],
    macro: Mapping[str, Any],
    as_of_date: str,
) -> dict[str, Any]:
    reads = [
        diagnose_pre_snap_read(c, spine_by_symbol, scorecard, convergence, macro, as_of_date)
        for c in candidates
    ]
    audible_counts: dict[str, int] = {}
    for read in reads:
        audible_counts[read["audible"]] = audible_counts.get(read["audible"], 0) + 1
    return {
        "artifact_type": "pre_snap_reads",
        "pre_snap_version": PRE_SNAP_VERSION,
        "as_of_date": as_of_date,
        "reads": reads,
        "audible_counts": audible_counts,
        "no_trade_audibles": sum(
            v for k, v in audible_counts.items() if "no_trade" in k or k.startswith("check")
        ),
        "coaching_principle": (
            "read the look before you commit, and protect the football: when the read is "
            "unfavorable or uncertain, the disciplined audible is no-trade. There is no fire call at L0"
        ),
        "not_edge_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
