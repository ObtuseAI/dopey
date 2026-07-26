"""Post-Snap Read: re-diagnose open positions when the picture changes.

Mahomes' most distinctive skill is not the pre-snap read (everyone elite has
that); it is processing AFTER the snap - the disguise rotates, the pocket
breaks, and he re-diagnoses live: stay on schedule, extend, or throw it away.

DOPEY's exit policy is deliberately mechanical and PINNED (stop/target/time -
evidence semantics must not drift), but nothing re-reads the RESEARCH picture
of open positions after entry: has the entry context rotated into an
AVOID-graded bucket? has the family's convergence verdict flipped since entry?
This does that re-diagnosis daily and emits in-flight calls:

  on_schedule        - the look is unchanged or benign; play the call as designed
  scramble_alert     - the context rotated into an AVOID-graded bucket; the
                       protection broke - flag for review
  broken_play_alert  - context AVOID-rotated AND the family is contested or
                       negative; the play design is dead - strongest flag

STRICTLY ADVISORY: the mechanical exits still govern; this module annotates,
it never closes, sizes, or overrides. The honest reason: mid-flight
discretionary exits would change the forward walk's evidence semantics.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .pre_snap_read import CANDIDATE_TO_CONVERGENCE
from .trade_memory import spine_conditions

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ART = REPO_ROOT / "artifacts" / "dopey"
POST_SNAP_PATH = ART / "strategy_engineering" / "post_snap_reads.json"

POST_SNAP_VERSION = "dopey-post-snap-read-v1"


def _avoid_contexts(scorecard: Mapping[str, Any], family: str) -> set[str]:
    return {
        s["entry_context"]
        for s in scorecard.get("situations", [])
        if s.get("family") == family and str(s.get("call", "")).startswith("avoid")
    }


def _family_flipped(convergence: Mapping[str, Any], family: str) -> bool:
    key = CANDIDATE_TO_CONVERGENCE.get(family)
    if key is None:
        return False
    for entry in convergence.get("families", []):
        if entry.get("family") == key:
            return entry.get("verdict") == "contested_lanes_disagree" or (
                entry.get("consensus_sign") == "negative"
            )
    return False


def rediagnose_position(
    position: Mapping[str, Any],
    spine_by_symbol: Mapping[str, tuple[Sequence[float], Sequence[str]]],
    scorecard: Mapping[str, Any],
    convergence: Mapping[str, Any],
    as_of_date: str,
) -> dict[str, Any]:
    symbol = str(position.get("symbol", ""))
    family = str(position.get("signal_family", position.get("family", "")))
    entry_date = str(position.get("entry_date", ""))
    if symbol not in spine_by_symbol:
        return {
            "position_id": str(position.get("position_id", "")),
            "symbol": symbol, "family": family,
            "call": "cannot_read_no_spine", "entry_context": "unknown", "current_context": "unknown",
        }
    closes, dates = spine_by_symbol[symbol]
    entry_context = str(spine_conditions(closes, dates, entry_date).get("stretch_bucket", "unknown"))
    current_context = str(spine_conditions(closes, dates, as_of_date).get("stretch_bucket", "unknown"))
    avoid = _avoid_contexts(scorecard, family)
    rotated_into_avoid = current_context in avoid and entry_context not in avoid
    flipped = _family_flipped(convergence, family)
    if rotated_into_avoid and flipped:
        call = "broken_play_alert"
    elif rotated_into_avoid:
        call = "scramble_alert"
    elif current_context in avoid:  # entered in an avoid context and still there
        call = "scramble_alert"
    else:
        call = "on_schedule"
    return {
        "position_id": str(position.get("position_id", "")),
        "symbol": symbol,
        "family": family,
        "entry_date": entry_date,
        "entry_context": entry_context,
        "current_context": current_context,
        "context_rotated": entry_context != current_context,
        "family_contested_or_negative": flipped,
        "call": call,
    }


def build_post_snap_reads(
    open_positions: Sequence[Mapping[str, Any]],
    spine_by_symbol: Mapping[str, tuple[Sequence[float], Sequence[str]]],
    scorecard: Mapping[str, Any],
    convergence: Mapping[str, Any],
    as_of_date: str,
) -> dict[str, Any]:
    reads = [
        rediagnose_position(p, spine_by_symbol, scorecard, convergence, as_of_date)
        for p in open_positions
    ]
    call_counts: dict[str, int] = {}
    for read in reads:
        call_counts[read["call"]] = call_counts.get(read["call"], 0) + 1
    return {
        "artifact_type": "post_snap_reads",
        "post_snap_version": POST_SNAP_VERSION,
        "as_of_date": as_of_date,
        "reads": reads,
        "call_counts": call_counts,
        "alerts": [r for r in reads if r["call"].endswith("_alert")],
        "exit_policy_note": (
            "STRICTLY ADVISORY: the pinned mechanical exit policy still governs every "
            "position; a mid-flight discretionary exit would change the forward walk's "
            "evidence semantics. This annotates the changed picture for review only"
        ),
        "not_edge_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
