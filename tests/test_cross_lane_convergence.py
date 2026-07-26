"""Cross-lane convergence - corroborate directional findings across lanes.

Corroboration must require >=2 INDEPENDENT lanes agreeing on sign; genuine
sign disagreement is flagged contested; near-zero magnitudes are neutral (no
false conflict); and every finding stays research_hypothesis / not_edge -
convergence raises confidence, forward settlement still arbitrates.
"""
from __future__ import annotations

from dopey.strategy_engineering.cross_lane_convergence import (
    COMPRESSION,
    MOMENTUM,
    REVERSION,
    build_convergence,
    converge_family,
    scanner_stances,
    screener_stances,
)
from dopey.strategy_engineering.playbook_settlement import PLAYBOOK_TRUST_VERSION
from dopey.strategy_engineering.scanner_holdout_fitness import (
    SCANNER_FITNESS_VERSION,
)


def _scanner(per_detector):
    return {
        "scanner_fitness_version": SCANNER_FITNESS_VERSION,
        "per_detector": per_detector,
    }


def test_two_lanes_agree_is_corroborated() -> None:
    stances = [
        {"lane": "scanner_fitness", "sign": "positive", "magnitude": 0.006, "sample": 1900},
        {"lane": "screener_weights", "sign": "positive", "magnitude": 0.013, "sample": 2},
    ]
    result = converge_family(REVERSION, stances)
    assert result["verdict"] == "corroborated"
    assert result["consensus_sign"] == "positive"
    assert set(result["independent_lanes"]) == {"scanner_fitness", "screener_weights"}


def test_three_lanes_agree_is_strong() -> None:
    stances = [
        {"lane": "a", "sign": "negative", "magnitude": -0.01, "sample": 100},
        {"lane": "b", "sign": "negative", "magnitude": -0.02, "sample": 100},
        {"lane": "c", "sign": "negative", "magnitude": -0.03, "sample": 100},
    ]
    assert converge_family(COMPRESSION, stances)["verdict"] == "corroborated_strong"


def test_sign_disagreement_is_contested() -> None:
    stances = [
        {"lane": "scanner_fitness", "sign": "negative", "magnitude": -0.003, "sample": 9000},
        {"lane": "screener_weights", "sign": "positive", "magnitude": 0.012, "sample": 1},
    ]
    result = converge_family(MOMENTUM, stances)
    assert result["verdict"] == "contested_lanes_disagree"
    assert result["consensus_sign"] == "mixed"


def test_single_rated_lane_is_not_corroboration() -> None:
    stances = [{"lane": "scanner_fitness", "sign": "positive", "magnitude": 0.01, "sample": 100}]
    assert converge_family(REVERSION, stances)["verdict"] == "single_lane_only"


def test_neutral_magnitude_does_not_manufacture_conflict() -> None:
    # a near-zero scanner read must NOT count as a positive dissent against two
    # negative lanes - it is neutral and the negatives corroborate
    stances = [
        {"lane": "scanner_fitness", "sign": "neutral", "magnitude": 0.0005, "sample": 300},
        {"lane": "screener_weights", "sign": "negative", "magnitude": -0.007, "sample": 1},
        {"lane": "compression_study", "sign": "negative", "magnitude": -0.002, "sample": 3000},
    ]
    result = converge_family(COMPRESSION, stances)
    assert result["verdict"] == "corroborated"
    assert result["consensus_sign"] == "negative"


def test_scanner_stances_deadbands_near_zero() -> None:
    # bb_squeeze/vcp average near zero -> compression stance should be neutral
    stances = scanner_stances(_scanner({
        "bb_squeeze": {"mean_excess": 0.0006, "events": 100},
        "vcp": {"mean_excess": -0.0002, "events": 100},
    }))
    assert stances[COMPRESSION]["sign"] == "neutral"


def test_scanner_event_weights_dominate() -> None:
    # a huge-sample negative detector outweighs a tiny-sample positive one
    stances = scanner_stances(_scanner({
        "ts_momentum": {"mean_excess": -0.003, "events": 9000},
        "channel_breakout": {"mean_excess": 0.05, "events": 10},
    }))
    assert stances[MOMENTUM]["sign"] == "negative"


def test_screener_maps_archetypes_to_families() -> None:
    stances = screener_stances({
        "long_call_quality_pullback": 0.019,
        "long_put_crowded_fade": 0.008,
        "long_premium_vol_expansion": -0.007,
    })
    assert stances[REVERSION]["sign"] == "positive"  # avg of the two reversion archetypes
    assert stances[COMPRESSION]["sign"] == "negative"


def test_full_build_is_research_only_and_names_corroboration() -> None:
    report = build_convergence(
        scanner_eval=_scanner({
            "short_term_reversal": {"mean_excess": 0.009, "events": 900},
            "band_snapback": {"mean_excess": 0.004, "events": 600},
            "ts_momentum": {"mean_excess": -0.003, "events": 9000},
            "bb_squeeze": {"mean_excess": 0.0006, "events": 300},
        }),
        screener_archetypes={
            "long_call_quality_pullback": 0.019,
            "long_premium_vol_expansion": -0.007,
            "long_call_momentum_breakout": 0.012,
        },
        compression_study={"direction_question": {"validation": {"era_status": "evaluated", "mean_excess_over_drift": -0.0023, "events": 3000}}},
        playbook_trust={
            "playbook_trust_version": PLAYBOOK_TRUST_VERSION,
            "per_family": {
                "mean_reversion": {
                    "trust_state": (
                        "unrated_insufficient_effective_"
                        "contested_settlements"
                    ),
                    "contested_hit_rate": 0.71,
                    "contested_settled": 70,
                    "effective_contested_hit_rate": 0.71,
                    "effective_contested_settled": 7,
                }
            },
        },
        signal_calibration={"contested_hit_rate": 0.4645},
    )
    assert report["promotion_allowed"] is False
    assert report["not_edge_evidence"] is True
    corroborated = {f["family"]: f["consensus_sign"] for f in report["corroborated_findings"]}
    # mean_reversion corroborated positive (scanner + screener); compression
    # corroborated negative (screener + compression study; scanner neutral)
    assert corroborated.get("mean_reversion") == "positive"
    assert corroborated.get("volatility_compression") == "negative"
    # Seventy raw settlements collapse to seven effective clusters, so the
    # playbook lane does not count.
    reversion = next(f for f in report["families"] if f["family"] == "mean_reversion")
    assert "playbook_forward_settlement" not in reversion["independent_lanes"]


def test_stale_scanner_fitness_version_is_excluded() -> None:
    scanner_eval = _scanner(
        {"ts_momentum": {"mean_excess": 0.50, "events": 10_000}}
    )
    scanner_eval["scanner_fitness_version"] = "dopey-scanner-holdout-fitness-v1"

    report = build_convergence(
        scanner_eval=scanner_eval,
        screener_archetypes={},
        compression_study={},
        playbook_trust={
            "playbook_trust_version": PLAYBOOK_TRUST_VERSION,
            "per_family": {},
        },
    )

    momentum = next(
        family
        for family in report["families"]
        if family["family"] == MOMENTUM
    )
    assert "scanner_fitness" not in momentum["independent_lanes"]
    assert (
        report["input_evidence_status"]["scanner_fitness"]
        == "blocked_incompatible_version"
    )
