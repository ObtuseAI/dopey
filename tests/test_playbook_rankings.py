"""Contract tests for the ranked bullish and bearish research Playbook."""

from __future__ import annotations

from copy import deepcopy

import pytest

from dopey.protocols.identity import canonical_hash
from dopey.strategy_engineering.playbook_rankings import build_playbook_rankings
from dopey.strategy_engineering.playbook_settlement import PLAYBOOK_TRUST_VERSION
from dopey_dashboard.control_center_state import _playbook_rankings_state


MARKET_AS_OF = "2026-07-21"
GENERATED_UTC = "2026-07-22T14:00:00+00:00"
SOURCE_HASH = "a" * 64


def _detection(
    symbol: str,
    category: str,
    strength: float,
) -> dict[str, object]:
    horizon, bias = category.rsplit("_", maxsplit=1)
    horizon_days = [5] if horizon == "short_term" else [20]
    direction = "long" if bias == "bullish" else "short"
    setup_id = f"{category}_setup"
    return {
        "detection_id": f"{symbol}:{category}",
        "symbol": symbol,
        "setup_id": setup_id,
        "family": f"{horizon}_price_setup",
        "direction": direction,
        "horizon_days": horizon_days,
        "strength": strength,
        "as_of_date": MARKET_AS_OF,
        "details": {"source": "independent_price_setup"},
        "lineage": ["test-governed-price-evidence"],
    }


def _governed_inputs(
    symbol_count: int,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    list[dict[str, object]],
    dict[str, dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    categories = (
        "short_term_bullish",
        "short_term_bearish",
        "long_term_bullish",
        "long_term_bearish",
    )
    symbols = [f"S{index:02d}" for index in range(symbol_count)]
    detections = [
        _detection(symbol, category, float(index + 1))
        for index, symbol in enumerate(symbols)
        for category in categories
    ]
    scan_report: dict[str, object] = {
        "status": "complete",
        "detections": detections,
        "reproducibility_hash": "b" * 64,
    }
    trust_report: dict[str, object] = {
        "paper_only": True,
        "live_blocked": True,
        "playbook_trust_version": PLAYBOOK_TRUST_VERSION,
        "per_setup": {
            f"{category}_setup": {
                "trust_state": "rated",
                "settled": 30,
                "hit_rate": 0.6,
                "effective_contested_settled": 30,
                "effective_contested_hit_rate": 0.6,
            }
            for category in categories
        },
    }
    attention_snapshot: dict[str, object] = {
        "market_as_of_date": MARKET_AS_OF,
        "generated_at_utc": GENERATED_UTC,
        "future_observation_consumed": False,
        "universe_research_input_allowed": True,
        "snapshot_sha256": "c" * 64,
        "symbols": [
            {
                "symbol": symbol,
                "status": "scored",
                "freshness_status": "current",
                "attention_score": (index + 1) / max(symbol_count, 1),
                "completeness_ratio": 1.0,
                "missing_components": [],
                "component_scores": {
                    "market_activity": {
                        "score": (index + 1) / max(symbol_count, 1),
                    }
                },
                "provenance_sha256": "d" * 64,
            }
            for index, symbol in enumerate(symbols)
        ],
    }
    universe_summary: dict[str, object] = {
        "status": "evolved",
        "maximum_active_universe_size": 500,
        "active_after": symbol_count,
        "registry_mutated": False,
        "reproducibility_hash": "e" * 64,
        "ranked_members": [
            {
                "symbol": symbol,
                "resulting_tier": "probation",
                "research_tradable": True,
                "ranking_eligible_for_playbook": True,
                "selection_score": (index + 1) / max(symbol_count, 1),
                "avg_dollar_volume_20d": 100_000_000.0 + index,
                "market_cap": 10_000_000_000.0 + index,
                "reason_codes": ["liquid_single_stock"],
                "evidence_hash": "f" * 64,
            }
            for index, symbol in enumerate(symbols)
        ],
    }
    swing_theses: list[dict[str, object]] = []
    fundamental_confirmations = {
        symbol: {
            "artifact_type": "equity_fundamental_confirmation",
            "symbol": symbol,
            "as_of_date": MARKET_AS_OF,
            "fundamental_status": "real_snapshot_scored",
            "point_in_time_status": "exact_market_frontier_snapshot",
            "future_observation_consumed": False,
            "paper_only": True,
            "live_blocked": True,
            "valuation_evidence_status": "peer_relative_scored_sufficient",
            "valuation_support_score": 0.60,
            "growth_score": 0.60,
            "quality_score": 0.70,
            "valuation_peer_counts": {"forward_pe": 10, "price_to_sales": 10},
            "raw_metrics": {
                "forward_pe": 20.0,
                "price_to_sales": 3.0,
                "profit_margin": 0.20,
                "free_cashflow": 1_000_000_000.0,
            },
            "reason_codes": [],
            "source_snapshot_sha256": SOURCE_HASH,
        }
        for symbol in symbols
    }
    symbol_dossiers = [{"symbol": symbol, "role": "single_stock"} for symbol in symbols]
    source_artifacts = [
        {
            "path": "artifacts/dopey/test/governed_source.json",
            "sha256": SOURCE_HASH,
        }
    ]
    return (
        scan_report,
        trust_report,
        attention_snapshot,
        universe_summary,
        swing_theses,
        fundamental_confirmations,
        symbol_dossiers,
        source_artifacts,
    )


def _build(symbol_count: int) -> dict[str, object]:
    inputs = _governed_inputs(symbol_count)
    return build_playbook_rankings(
        *inputs,
        generated_utc=GENERATED_UTC,
        refresh_interval_minutes=240,
    )


def _rehash(artifact: dict[str, object]) -> None:
    body = {
        key: value
        for key, value in artifact.items()
        if key not in {"content_hash", "reproducibility_hash"}
    }
    content_hash = canonical_hash(body)
    artifact["content_hash"] = content_hash
    artifact["reproducibility_hash"] = content_hash


def test_rankings_publish_four_top_tens_and_one_unique_top_five() -> None:
    artifact = _build(10)
    lists = artifact["lists"]
    assert isinstance(lists, dict)

    assert set(lists) == {
        "short_term_bullish",
        "short_term_bearish",
        "long_term_bullish",
        "long_term_bearish",
        "overall",
    }
    assert all(
        len(lists[category]) == 10
        for category in (
            "short_term_bullish",
            "short_term_bearish",
            "long_term_bullish",
            "long_term_bearish",
        )
    )
    assert len(lists["overall"]) == 5
    recommendations = artifact["recommendations"]
    assert isinstance(recommendations, dict)
    overall_symbols = [recommendations[value]["symbol"] for value in lists["overall"]]
    assert len(overall_symbols) == len(set(overall_symbols)) == 5
    assert artifact["playbook_status"] == "complete_research_rankings"


def test_rankings_leave_insufficient_lists_unpadded() -> None:
    artifact = _build(3)
    lists = artifact["lists"]
    assert isinstance(lists, dict)

    assert all(
        len(lists[category]) == 3
        for category in (
            "short_term_bullish",
            "short_term_bearish",
            "long_term_bullish",
            "long_term_bearish",
        )
    )
    assert len(lists["overall"]) == 3
    assert artifact["playbook_status"] == "partial_insufficient_eligible_candidates"
    assert artifact["missing_slots_by_list"] == {
        "short_term_bullish": 7,
        "short_term_bearish": 7,
        "long_term_bullish": 7,
        "long_term_bearish": 7,
    }
    assert artifact["ranking_method"]["no_padding_when_insufficient"] is True


def test_forward_trust_rewards_only_positive_horizon_matched_skill() -> None:
    inputs = list(_governed_inputs(1))
    trust_report = inputs[1]
    assert isinstance(trust_report, dict)
    per_setup = trust_report["per_setup"]
    assert isinstance(per_setup, dict)
    short_trust = per_setup["short_term_bullish_setup"]
    long_trust = per_setup["long_term_bullish_setup"]
    assert isinstance(short_trust, dict) and isinstance(long_trust, dict)
    short_trust.update(
        {
            "trust_state": "rated",
            "settled": 290,
            "contested_settled": 181,
            "contested_hit_rate": 0.4609,
            "effective_contested_settled": 31,
            "effective_contested_hit_rate": 0.4609,
        }
    )
    long_trust.update(
        {
            "trust_state": "rated",
            "settled": 100,
            "hit_rate": 0.90,
            "effective_contested_settled": 100,
            "effective_contested_hit_rate": 0.90,
        }
    )

    artifact = build_playbook_rankings(
        *inputs,
        generated_utc=GENERATED_UTC,
        refresh_interval_minutes=240,
    )
    lists = artifact["lists"]
    recommendations = artifact["recommendations"]
    assert isinstance(lists, dict) and isinstance(recommendations, dict)
    short = recommendations[lists["short_term_bullish"][0]]
    long = recommendations[lists["long_term_bullish"][0]]

    assert short["score_breakdown"]["forward_trust"] == 0.0
    assert short["trust_evidence"][0]["scored_observations"] == 31
    assert (
        short["trust_evidence"][0]["trust_state"] == "no_positive_horizon_matched_skill"
    )
    assert long["score_breakdown"]["forward_trust"] == 0.0
    assert (
        long["trust_evidence"][0]["horizon_match"]
        == "unavailable_no_independent_long_horizon_settlement"
    )


def test_unrated_setup_receives_no_maturity_credit() -> None:
    inputs = list(_governed_inputs(1))
    trust_report = inputs[1]
    assert isinstance(trust_report, dict)
    per_setup = trust_report["per_setup"]
    assert isinstance(per_setup, dict)
    trust = per_setup["short_term_bullish_setup"]
    assert isinstance(trust, dict)
    trust.update(
        {
            "trust_state": "unrated_insufficient_settlements",
            "settled": 29,
            "hit_rate": 1.0,
        }
    )

    artifact = build_playbook_rankings(
        *inputs,
        generated_utc=GENERATED_UTC,
        refresh_interval_minutes=240,
    )
    lists = artifact["lists"]
    recommendations = artifact["recommendations"]
    assert isinstance(lists, dict) and isinstance(recommendations, dict)
    recommendation = recommendations[lists["short_term_bullish"][0]]

    assert recommendation["score_breakdown"]["forward_trust"] == 0.0
    assert (
        "no_positive_horizon_matched_setup_skill" in recommendation["missing_evidence"]
    )


def test_attention_changes_priority_but_never_creates_direction() -> None:
    inputs = list(_governed_inputs(1))
    scan_report = inputs[0]
    assert isinstance(scan_report, dict)
    detections = scan_report["detections"]
    assert isinstance(detections, list)
    scan_report["detections"] = [
        detection
        for detection in detections
        if detection["setup_id"] == "short_term_bullish_setup"
    ]
    high_attention = build_playbook_rankings(
        *inputs,
        generated_utc=GENERATED_UTC,
        refresh_interval_minutes=240,
    )
    attention_snapshot = inputs[2]
    assert isinstance(attention_snapshot, dict)
    attention_rows = attention_snapshot["symbols"]
    assert isinstance(attention_rows, list)
    attention_rows[0]["attention_score"] = 0.0
    low_attention = build_playbook_rankings(
        *inputs,
        generated_utc=GENERATED_UTC,
        refresh_interval_minutes=240,
    )

    for artifact in (high_attention, low_attention):
        lists = artifact["lists"]
        assert isinstance(lists, dict)
        assert len(lists["short_term_bullish"]) == 1
        assert lists["short_term_bearish"] == []
        assert lists["long_term_bullish"] == []
        assert lists["long_term_bearish"] == []
        assert artifact["ranking_method"]["attention_use"] == (
            "direction_neutral_research_priority_only"
        )
    high_lists = high_attention["lists"]
    low_lists = low_attention["lists"]
    high_recommendations = high_attention["recommendations"]
    low_recommendations = low_attention["recommendations"]
    assert isinstance(high_lists, dict) and isinstance(low_lists, dict)
    assert isinstance(high_recommendations, dict) and isinstance(
        low_recommendations, dict
    )
    high_id = high_lists["short_term_bullish"][0]
    low_id = low_lists["short_term_bullish"][0]
    assert high_id == low_id
    assert (
        high_recommendations[high_id]["research_priority_score"]
        > low_recommendations[low_id]["research_priority_score"]
    )


def test_missing_valuation_blocks_long_horizon_and_caps_short_horizon() -> None:
    inputs = list(_governed_inputs(1))
    fundamentals = inputs[5]
    assert isinstance(fundamentals, dict)
    del fundamentals["S00"]

    artifact = build_playbook_rankings(
        *inputs,
        generated_utc=GENERATED_UTC,
        refresh_interval_minutes=240,
    )
    lists = artifact["lists"]
    recommendations = artifact["recommendations"]
    assert isinstance(lists, dict) and isinstance(recommendations, dict)
    assert lists["long_term_bullish"] == []
    assert lists["long_term_bearish"] == []
    short_id = lists["short_term_bullish"][0]
    short = recommendations[short_id]
    assert short["research_priority_score"] <= 49.99
    assert short["recommendation_state"] == "screen_flag_missing_current_valuation"
    assert short["confidence_label"] == "low_research_confidence_valuation_gate_blocked"
    assert short["valuation_context"]["valuation_fit_score"] == 0.0
    assert (
        artifact["ranking_method"]["missing_valuation_neutral_imputation_allowed"]
        is False
    )


def test_bullish_valuation_contradiction_is_not_promoted_or_long_ranked() -> None:
    inputs = list(_governed_inputs(1))
    fundamentals = inputs[5]
    assert isinstance(fundamentals, dict)
    record = fundamentals["S00"]
    record["valuation_support_score"] = 0.10
    record["growth_score"] = 0.20
    record["quality_score"] = 0.20

    artifact = build_playbook_rankings(
        *inputs,
        generated_utc=GENERATED_UTC,
        refresh_interval_minutes=240,
    )
    lists = artifact["lists"]
    recommendations = artifact["recommendations"]
    assert isinstance(lists, dict) and isinstance(recommendations, dict)
    assert lists["long_term_bullish"] == []
    short = recommendations[lists["short_term_bullish"][0]]
    assert short["research_priority_score"] <= 44.99
    assert short["recommendation_state"] == "screen_flag_valuation_contradiction"
    assert "bullish_valuation_contradiction" in short["valuation_context"]["risk_flags"]
    assert short["trade_promotion_allowed"] is False


def test_valuation_source_hash_must_be_bound_to_source_manifest() -> None:
    inputs = list(_governed_inputs(1))
    fundamentals = inputs[5]
    assert isinstance(fundamentals, dict)
    fundamentals["S00"]["source_snapshot_sha256"] = "9" * 64

    with pytest.raises(ValueError, match="source hash bound"):
        build_playbook_rankings(
            *inputs,
            generated_utc=GENERATED_UTC,
            refresh_interval_minutes=240,
        )


def test_bearish_predictions_cannot_construct_short_stock_orders() -> None:
    artifact = _build(3)
    lists = artifact["lists"]
    recommendations = artifact["recommendations"]
    assert isinstance(lists, dict)
    assert isinstance(recommendations, dict)

    bearish_ids = lists["short_term_bearish"] + lists["long_term_bearish"]
    assert bearish_ids
    for recommendation_id in bearish_ids:
        recommendation = recommendations[recommendation_id]
        assert recommendation["directional_bias"] == "bearish"
        assert recommendation["order_construction_allowed"] is False
        assert recommendation["trade_promotion_allowed"] is False
        assert (
            recommendation["execution_state"]
            == "research_ranked_not_execution_instruction"
        )
        assert str(recommendation["bearish_expression_policy"]).startswith(
            "directional_research_only; no short-stock order;"
        )
    assert artifact["order_construction_allowed"] is False
    assert artifact["live_execution_allowed"] is False


def test_rankings_fail_closed_when_attention_and_price_frontiers_differ() -> None:
    inputs = list(_governed_inputs(3))
    attention_snapshot = inputs[2]
    assert isinstance(attention_snapshot, dict)
    attention_snapshot["market_as_of_date"] = "2026-07-20"

    with pytest.raises(ValueError, match="must share one market frontier"):
        build_playbook_rankings(
            *inputs,
            generated_utc=GENERATED_UTC,
            refresh_interval_minutes=240,
        )


def test_rankings_fail_closed_when_directional_scan_has_mixed_frontiers() -> None:
    inputs = list(_governed_inputs(3))
    scan_report = inputs[0]
    assert isinstance(scan_report, dict)
    detections = scan_report["detections"]
    assert isinstance(detections, list)
    first_detection = detections[0]
    assert isinstance(first_detection, dict)
    first_detection["as_of_date"] = "2026-07-20"

    with pytest.raises(ValueError, match="must share one market frontier"):
        build_playbook_rankings(
            *inputs,
            generated_utc=GENERATED_UTC,
            refresh_interval_minutes=240,
        )


def test_rankings_are_content_addressed_and_reproducible() -> None:
    artifact = _build(3)
    body = {
        key: value
        for key, value in artifact.items()
        if key not in {"content_hash", "reproducibility_hash"}
    }

    assert artifact["content_hash"] == canonical_hash(body)
    assert artifact["reproducibility_hash"] == artifact["content_hash"]
    assert _build(3)["content_hash"] == artifact["content_hash"]


def test_rankings_reject_stale_trust_rating_semantics() -> None:
    inputs = list(_governed_inputs(1))
    trust_report = inputs[1]
    assert isinstance(trust_report, dict)
    trust_report["playbook_trust_version"] = "dopey-playbook-trust-v1"

    with pytest.raises(ValueError, match="incompatible rating semantics"):
        build_playbook_rankings(
            *inputs,
            generated_utc=GENERATED_UTC,
            refresh_interval_minutes=240,
        )


@pytest.mark.parametrize("failure_mode", ["rank", "hash"])
def test_dashboard_rejects_malformed_playbook_ranks_and_hashes(
    failure_mode: str,
) -> None:
    artifact = deepcopy(_build(3))
    lists = artifact["lists"]
    recommendations = artifact["recommendations"]
    assert isinstance(lists, dict)
    assert isinstance(recommendations, dict)
    first_id = lists["short_term_bullish"][0]
    if failure_mode == "rank":
        recommendations[first_id]["rank"] = 2
        _rehash(artifact)
    else:
        recommendations[first_id]["thesis_summary"] = "tampered after hashing"

    issues: list[dict[str, object]] = []
    assert _playbook_rankings_state(artifact, issues) is None
    assert issues and issues[0]["issue_id"] == "playbook_rankings_invalid"
    if failure_mode == "rank":
        assert "rank is not ordered" in str(issues[0]["message"])
    else:
        assert "content hash verification failed" in str(issues[0]["message"])
