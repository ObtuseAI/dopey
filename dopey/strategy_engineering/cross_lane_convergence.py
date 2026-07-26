"""Cross-lane convergence: what do DOPEY's independent measurements AGREE on?

DOPEY runs several INDEPENDENT held-out / forward measurement lanes that each
touch directional edge by strategy family, but nothing in the system notices
when they agree. Independent corroboration is the single strongest honest
epistemic upgrade available: a finding two or three genuinely different methods
reach separately is far more trustworthy than any one of them alone - and where
they CONFLICT, that is exactly what deserves investigation.

The lanes, and why they are independent:
- scanner fitness    : held-out HISTORICAL directional-detector settlement
                       (excess over drift, >2021-12-31)
- screener weights   : held-out rank-IC of the screening FACTORS per archetype
- compression study  : held-out bandwidth-compression range/direction test
- playbook trust     : FORWARD (prospective, live) contested settlement
- signal calibration : FORWARD phantom-settlement system base rate (coarse)

This maps each lane's result to a canonical family, takes the SIGN of its
directional edge, and reports where independent lanes corroborate vs conflict.
It raises CONFIDENCE; it is never an edge claim and never promotes. Forward
settlement remains the only path to trust. Every finding is stamped
research_hypothesis / not_edge_evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .playbook_settlement import PLAYBOOK_TRUST_VERSION
from .scanner_holdout_fitness import SCANNER_FITNESS_VERSION

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ART = REPO_ROOT / "artifacts" / "dopey"
CONVERGENCE_PATH = ART / "strategy_engineering" / "cross_lane_convergence.json"

CONVERGENCE_VERSION = "dopey-cross-lane-convergence-v2"

MOMENTUM = "momentum_continuation"
REVERSION = "mean_reversion"
COMPRESSION = "volatility_compression"
FAMILIES = (MOMENTUM, REVERSION, COMPRESSION)

# scanner detector -> canonical family
DETECTOR_FAMILY = {
    "ts_momentum": MOMENTUM,
    "channel_breakout": MOMENTUM,
    "gap_continuation": MOMENTUM,
    "week52_high": MOMENTUM,
    "box_breakout": MOMENTUM,
    "short_term_reversal": REVERSION,
    "band_snapback": REVERSION,
    "capitulation": REVERSION,
    "quality_pullback": REVERSION,
    "bb_squeeze": COMPRESSION,
    "vcp": COMPRESSION,
}

# screener archetype -> canonical family
ARCHETYPE_FAMILY = {
    "long_call_momentum_breakout": MOMENTUM,
    "long_call_quality_pullback": REVERSION,
    "long_put_crowded_fade": REVERSION,
    "long_premium_vol_expansion": COMPRESSION,
}

# playbook family-trust key -> canonical family
PLAYBOOK_FAMILY = {
    "momentum_trend": MOMENTUM,
    "mean_reversion": REVERSION,
}

RATED_SETTLEMENT_FLOOR = 30
CORROBORATION_MIN_LANES = 2
STRONG_CORROBORATION_LANES = 3

# Below these magnitudes a lane's directional read is noise, not a stance, so it
# counts as neither corroboration nor conflict. Excess/IC lanes share a scale
# (~return units); the playbook lane is hit-rate-minus-0.5, a coarser scale.
EDGE_DEADBAND = 0.001       # scanner excess, screener IC, compression excess
HIT_RATE_DEADBAND = 0.02    # playbook contested-hit-rate deviation from 0.5


def _sign(value: float, deadband: float = 0.0) -> str:
    if value > deadband:
        return "positive"
    if value < -deadband:
        return "negative"
    return "neutral"


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def scanner_stances(scanner_eval: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per-family event-weighted mean excess from the scanner fitness lane."""
    if scanner_eval.get("scanner_fitness_version") != SCANNER_FITNESS_VERSION:
        return {}
    per = scanner_eval.get("per_detector", {})
    if not isinstance(per, dict) or not per:
        return {}
    agg: dict[str, list[tuple[float, int]]] = {}
    for detector, bucket in per.items():
        family = DETECTOR_FAMILY.get(detector)
        if family is None or not isinstance(bucket, dict):
            continue
        agg.setdefault(family, []).append(
            (float(bucket.get("mean_excess", 0.0)), int(bucket.get("events", 0)))
        )
    stances: dict[str, dict[str, Any]] = {}
    for family, rows in agg.items():
        total_events = sum(events for _excess, events in rows)
        if total_events == 0:
            continue
        weighted = sum(excess * events for excess, events in rows) / total_events
        stances[family] = {
            "lane": "scanner_fitness",
            "method": "held_out_historical_detector_settlement",
            "sign": _sign(weighted, EDGE_DEADBAND),
            "magnitude": round(weighted, 6),
            "sample": total_events,
        }
    return stances


def screener_stances(screener_archetypes: dict[str, float]) -> dict[str, dict[str, Any]]:
    """Per-family sign from screener per-archetype held-out rank-IC."""
    agg: dict[str, list[float]] = {}
    for archetype, ic in screener_archetypes.items():
        family = ARCHETYPE_FAMILY.get(archetype)
        if family is None or ic is None:
            continue
        agg.setdefault(family, []).append(float(ic))
    return {
        family: {
            "lane": "screener_weights",
            "method": "held_out_factor_rank_ic",
            "sign": _sign(sum(ics) / len(ics), EDGE_DEADBAND),
            "magnitude": round(sum(ics) / len(ics), 6),
            "sample": len(ics),
        }
        for family, ics in agg.items()
    }


def compression_stance(compression_study: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The compression study speaks to the volatility_compression family only."""
    direction = compression_study.get("direction_question", {})
    valid = direction.get("validation", {})
    if valid.get("era_status") != "evaluated":
        return {}
    excess = float(valid.get("mean_excess_over_drift", 0.0))
    return {
        COMPRESSION: {
            "lane": "compression_study",
            "method": "held_out_squeeze_break_direction",
            "sign": _sign(excess, EDGE_DEADBAND),
            "magnitude": round(excess, 6),
            "sample": int(valid.get("events", 0)),
        }
    }


def playbook_stances(playbook_trust: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per-family FORWARD contested settlement (rated only above the floor)."""
    if playbook_trust.get("playbook_trust_version") != PLAYBOOK_TRUST_VERSION:
        return {}
    per = playbook_trust.get("per_family", {})
    stances: dict[str, dict[str, Any]] = {}
    for key, bucket in per.items() if isinstance(per, dict) else []:
        family = PLAYBOOK_FAMILY.get(key)
        if family is None or not isinstance(bucket, dict):
            continue
        settled = bucket.get("effective_contested_settled")
        rate = bucket.get("effective_contested_hit_rate")
        if (
            bucket.get("trust_state") != "rated"
            or not isinstance(settled, int)
            or settled < RATED_SETTLEMENT_FLOOR
            or rate is None
        ):
            continue  # unrated: too few contested settlements to count as a lane
        stances[family] = {
            "lane": "playbook_forward_settlement",
            "method": "forward_effective_contested_clusters",
            "sign": _sign(float(rate) - 0.5, HIT_RATE_DEADBAND),
            "magnitude": round(float(rate) - 0.5, 6),
            "sample": settled,
        }
    return stances


def converge_family(family: str, stances: list[dict[str, Any]]) -> dict[str, Any]:
    rated = [s for s in stances if s["sign"] in ("positive", "negative")]
    positives = [s for s in rated if s["sign"] == "positive"]
    negatives = [s for s in rated if s["sign"] == "negative"]
    lanes = sorted({s["lane"] for s in rated})
    if not rated:
        verdict = "insufficient_no_rated_lane"
    elif positives and negatives:
        verdict = "contested_lanes_disagree"
    else:
        agreeing = len(positives) or len(negatives)
        if agreeing >= STRONG_CORROBORATION_LANES:
            verdict = "corroborated_strong"
        elif agreeing >= CORROBORATION_MIN_LANES:
            verdict = "corroborated"
        else:
            verdict = "single_lane_only"
    consensus_sign = (
        "positive" if positives and not negatives
        else "negative" if negatives and not positives
        else "mixed" if positives and negatives
        else "none"
    )
    return {
        "family": family,
        "verdict": verdict,
        "consensus_sign": consensus_sign,
        "agreeing_lane_count": max(len(positives), len(negatives)) if not (positives and negatives) else 0,
        "independent_lanes": lanes,
        "stances": stances,
        "research_hypothesis": True,
        "not_edge_evidence": True,
        "forward_settlement_remains_arbiter": True,
    }


def build_convergence(
    scanner_eval: dict[str, Any],
    screener_archetypes: dict[str, float],
    compression_study: dict[str, Any],
    playbook_trust: dict[str, Any],
    signal_calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    by_family: dict[str, list[dict[str, Any]]] = {family: [] for family in FAMILIES}
    for extractor in (
        scanner_stances(scanner_eval),
        screener_stances(screener_archetypes),
        compression_stance(compression_study),
        playbook_stances(playbook_trust),
    ):
        for family, stance in extractor.items():
            by_family.setdefault(family, []).append(stance)
    families = [converge_family(family, by_family.get(family, [])) for family in FAMILIES]
    for family in families:
        family["option_cost_annotation"] = _option_cost_annotation(family)
    corroborated = [
        f for f in families if f["verdict"] in ("corroborated", "corroborated_strong")
    ]
    contested = [f for f in families if f["verdict"] == "contested_lanes_disagree"]
    system_base_rate = None
    if isinstance(signal_calibration, dict):
        system_base_rate = signal_calibration.get("contested_hit_rate")
    return {
        "artifact_type": "cross_lane_convergence",
        "convergence_version": CONVERGENCE_VERSION,
        "input_evidence_status": {
            "scanner_fitness": (
                "current"
                if scanner_eval.get("scanner_fitness_version")
                == SCANNER_FITNESS_VERSION
                else "blocked_incompatible_version"
            ),
            "playbook_trust": (
                "current"
                if playbook_trust.get("playbook_trust_version")
                == PLAYBOOK_TRUST_VERSION
                else "blocked_incompatible_version"
            ),
        },
        "families": families,
        "corroborated_findings": [
            {"family": f["family"], "consensus_sign": f["consensus_sign"],
             "lanes": f["independent_lanes"], "verdict": f["verdict"],
             "survives_long_option_costs": f.get("option_cost_annotation", {}).get("survives_long_option_costs"),
             "breakeven_underlying_move": f.get("option_cost_annotation", {}).get("breakeven_underlying_move")}
            for f in corroborated
        ],
        "corroborated_and_survives_option_costs": [
            f["family"] for f in corroborated
            if f.get("option_cost_annotation", {}).get("survives_long_option_costs") is True
        ],
        "contested_findings": [f["family"] for f in contested],
        "system_contested_base_rate": system_base_rate,
        "headline": _headline(corroborated, contested),
        "epistemic_note": (
            "convergence of independent held-out and forward methods raises "
            "CONFIDENCE in a directional sign; it is not an edge claim and never "
            "promotes - forward settlement remains the sole arbiter of trust"
        ),
        "not_edge_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _option_cost_annotation(family: dict[str, Any]) -> dict[str, Any]:
    """Does this family's underlying edge survive expression as a long option?

    Uses the scanner_fitness stance magnitude (an underlying excess-over-drift)
    as the representative favorable move. Lazy import keeps the pricing/cost
    kernel out of this module's import surface.
    """
    stances = family.get("stances", [])
    scanner = next((s for s in stances if s.get("lane") == "scanner_fitness"), None)
    representative = scanner or (stances[0] if stances else None)
    if representative is None or representative.get("sign") not in ("positive", "negative"):
        return {"option_cost_status": "no_rated_underlying_excess"}
    from .option_expression_cost import survives_option_costs

    verdict = survives_option_costs(float(representative["magnitude"]))
    return {
        "option_cost_status": "computed",
        "representative_lane": representative["lane"],
        "underlying_excess_magnitude": verdict["underlying_excess_magnitude"],
        "breakeven_underlying_move": verdict["breakeven_underlying_move"],
        "net_long_option_return_at_excess": verdict["net_long_option_return_at_excess"],
        "survives_long_option_costs": verdict["survives_long_option_costs"],
    }


def _headline(corroborated: list[dict[str, Any]], contested: list[dict[str, Any]]) -> str:
    if not corroborated and not contested:
        return "no family has enough independent rated lanes to corroborate"
    parts = []
    for f in corroborated:
        parts.append(f"{f['family']} {f['consensus_sign']} ({len(f['independent_lanes'])} independent lanes)")
    if contested:
        parts.append("contested: " + ", ".join(f["family"] for f in contested))
    return "; ".join(parts)


def run_cross_lane_convergence() -> dict[str, Any]:
    from dopey_research_pipeline.artifact_io import write_json_atomic

    scanner_eval = _load(ART / "evolution" / "scanner_fitness_last_eval.json")
    screener_archetypes = _screener_archetype_ics()
    compression_study = _load(ART / "strategy_engineering" / "compression_expansion_study.json")
    playbook_trust = _load(ART / "playbook" / "playbook_family_trust.json")
    signal_calibration = _load(ART / "signal_calibration" / "signal_calibration_summary.json")
    report = build_convergence(
        scanner_eval, screener_archetypes, compression_study, playbook_trust, signal_calibration
    )
    write_json_atomic(CONVERGENCE_PATH, report)
    return report


def _screener_archetype_ics() -> dict[str, float]:
    """Read per-archetype held-out IC from the screener fitness artifact."""
    data = _load(ART / "evolution" / "screener_fitness_last_eval.json")
    per = data.get("per_archetype", {})
    if not isinstance(per, dict):
        return {}
    out: dict[str, float] = {}
    for archetype, bucket in per.items():
        if isinstance(bucket, dict) and bucket.get("mean_holdout_rank_ic") is not None:
            out[archetype] = float(bucket["mean_holdout_rank_ic"])
    return out
