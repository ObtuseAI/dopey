from __future__ import annotations

import inspect
import json
import math
from datetime import date, timedelta
from typing import Any, cast

import pytest

import dopey_acceleration.frontier as frontier_module
from dopey.protocols.identity import canonical_hash
from dopey_acceleration.frontier import OPENROUTER_HYBRID_COMPONENTS, OPENROUTER_MODELS
from dopey_analysis.two_coach_engine import (
    MAX_HEAD_COACH_MODEL_INPUT_BYTES,
    TwoCoachContractError,
    build_head_coach_model_state,
    retrieve_prior_trade_lessons,
    validate_head_coach_analysis,
)
from dopey_chart_vision.grounded_structure_engine import (
    build_blind_replay_evidence,
    build_grounded_structure_evidence,
)
from dopey_equity_swing.market_structure import Bar


def _history(count: int) -> list[Bar]:
    start = date(2024, 1, 2)
    rows: list[Bar] = []
    prior_close = 100.0
    for index in range(count):
        center = 100.0 + index * 0.08 + math.sin(index / 4.0) * 3.2
        open_value = prior_close
        close = center + math.sin(index / 2.7) * 0.35
        rows.append(
            Bar(
                date=(start + timedelta(days=index)).isoformat(),
                open=open_value,
                high=max(open_value, close) + 0.75,
                low=min(open_value, close) - 0.75,
                close=close,
                adjusted_close=close,
                volume=1_000_000 + index * 2_000,
            )
        )
        prior_close = close
    return rows


def _analysis(summary: str) -> dict[str, Any]:
    return {
        "summary": summary,
        "hypotheses": [
            {
                "title": "Grounded setup",
                "mechanism": "Price is interacting with [[structure:known]].",
                "evidence_needed": "Retain [[level:known]].",
                "falsification": "Lose [[level:known]].",
            }
        ],
        "adversarial_findings": [],
        "uncertainties": ["The candidate definition may not generalize."],
        "recommended_experiments": [],
        "abstain": False,
    }


def _packet() -> dict[str, Any]:
    return {
        "packet_hash": "packet-hash",
        "session_id": "two-coach:fixture",
        "mode": "paper_research_only",
        "topology": {
            "coach_count": 2,
            "evidence_coach_id": "deterministic_structure_replay_coach_v1",
            "head_coach_id": "claude",
            "runtime_fallback_allowed": False,
        },
        "instrument": {
            "symbol": "SPY",
            "asset_class": "equity_underlying",
            "timeframe": "daily",
            "as_of": "2026-07-21",
        },
        "data_snapshot": {
            "chart_content_hash": "chart-hash",
            "future_data_visible_during_detection": False,
        },
        "evidence_coach": {
            "structure_registry": [
                {
                    "structure_id": "structure:known",
                    "structure_type": "swing_low",
                    "directional_bias": "bullish",
                    "available_at_date": "historical_cutoff",
                    "level_refs": ["level:known"],
                }
            ],
            "numeric_fact_registry": [
                {
                    "level_ref": "level:known",
                    "label": "confirmed_support",
                    "canonical_display": "101.25",
                    "unit": "price",
                }
            ],
            "prior_trade_lessons": {"lessons": []},
            "blind_replay": {
                "reveal_end": "2026-07-21",
                "outcome": {"underlying_close_return_decimal": "0.25"},
            },
        },
        "option_claim_boundary": {
            "status": "blocked_missing_point_in_time_entry_and_exit_option_evidence",
        },
        "mutation_boundary": {"automatic_activation_allowed": False},
        "authority": {
            "research_only": True,
            "paper_only": True,
            "live_blocked": True,
            "broker_access": False,
            "order_authority": False,
        },
    }


def _validated_trade(
    position_id: str,
    symbol: str,
    strategy: str,
    exit_date: str,
    path_pnl: float,
) -> dict[str, Any]:
    return {
        "position_id": position_id,
        "symbol": symbol,
        "candidate_strategy": strategy,
        "signal_family": "relative_strength",
        "exit_date": exit_date,
        "exit_reason": "premium_target" if path_pnl > 0.0 else "premium_stop",
        "path_pnl": path_pnl,
        "trade_return": 0.2 if path_pnl > 0.0 else -0.2,
        "ex_ante": True,
        "outcome_integrity_class": "validated_forward_outcome",
        "included_in_forward_performance_statistics": True,
        "historical_record_preserved": True,
    }


def test_grounded_detector_is_viewport_invariant_and_accepts_no_render_inputs() -> None:
    rows = _history(150)
    viewports = [
        {"width": 480 + index * 37, "height": 320 + index * 11, "dpr": 1 + index % 3}
        for index in range(20)
    ]

    results = [
        build_grounded_structure_evidence("SPY", "daily", rows, "fixture-data-v1")
        for _viewport in viewports
    ]

    assert len({result["evidence_hash"] for result in results}) == 1
    assert len({canonical_hash(result["structures"]) for result in results}) == 1
    assert all(result["viewport_is_detector_input"] is False for result in results)
    assert all(result["image_pixels_are_detector_input"] is False for result in results)
    assert set(inspect.signature(build_grounded_structure_evidence).parameters) == {
        "symbol",
        "timeframe",
        "rows",
        "data_version",
    }


def test_grounded_structures_record_confirmation_and_declared_fibonacci_policy() -> None:
    result = build_grounded_structure_evidence("SPY", "daily", _history(170), "fixture-data-v1")
    swings = [
        record
        for record in result["structures"]
        if str(record["structure_type"]).startswith("swing_")
    ]
    fibonacci = [
        record
        for record in result["structures"]
        if record["structure_type"] == "fibonacci_retracement_set"
    ]

    assert swings
    assert all(record["available_at_date"] for record in swings)
    assert all(record["available_at_bar_id"] not in record["anchor_bar_ids"] for record in swings)
    assert result["fibonacci_anchor_policy"] == "latest_opposite_confirmed_pivot_leg"
    assert fibonacci and len(fibonacci[0]["level_refs"]) == 7


def test_future_bar_mutation_cannot_change_frozen_structure_packet() -> None:
    rows = _history(150)
    frozen = rows[:130]
    original = build_grounded_structure_evidence("SPY", "daily", frozen, "fixture-data-v1")
    mutated = [dict(row) for row in rows]
    mutated[-1]["high"] = float(mutated[-1]["high"]) * 4.0
    mutated[-1]["close"] = float(mutated[-1]["close"]) * 3.0
    cast_rows = cast(list[Bar], mutated)

    after_future_mutation = build_grounded_structure_evidence(
        "SPY",
        "daily",
        cast_rows[:130],
        "fixture-data-v1",
    )

    assert after_future_mutation == original


def test_blind_replay_separates_frozen_decision_and_underlying_only_outcome() -> None:
    replay = build_blind_replay_evidence(
        "SPY",
        "daily",
        _history(150),
        "fixture-data-v1",
        5,
    )

    assert replay["future_data_visible_during_frozen_detection"] is False
    assert replay["decision_inputs_exclude_reveal_window"] is True
    assert replay["outcome"]["option_outcome_status"] == "blocked_missing_point_in_time_option_evidence"
    assert replay["outcome"]["not_option_pnl_evidence"] is True


def test_head_coach_model_state_is_bounded_and_excludes_replay_reveal_values() -> None:
    packet = _packet()

    state = build_head_coach_model_state(packet)
    encoded = json.dumps(state, sort_keys=True)

    assert state["model_input_bytes"] <= MAX_HEAD_COACH_MODEL_INPUT_BYTES
    assert state["model_input_bytes"] == len(
        json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    assert state["replay_input_boundary"]["reveal_values_visible_to_head_coach"] is False
    assert state["replay_input_boundary"]["future_bars_visible_to_head_coach"] is False
    assert "underlying_close_return_decimal" not in encoded
    assert "reveal_end" not in encoded
    assert "0.25" not in encoded
    assert packet["evidence_coach"]["blind_replay"]["outcome"] == {
        "underlying_close_return_decimal": "0.25"
    }


def test_head_coach_model_state_references_are_a_subset_of_full_local_registry() -> None:
    packet = _packet()

    state = build_head_coach_model_state(packet)
    compact_evidence = state["evidence_coach"]
    compact_structure_refs = {
        record["structure_id"] for record in compact_evidence["structures"]
    }
    compact_level_refs = {
        record["level_ref"] for record in compact_evidence["numeric_facts"]
    }
    full_structure_refs = {
        record["structure_id"]
        for record in packet["evidence_coach"]["structure_registry"]
    }
    full_level_refs = {
        record["level_ref"]
        for record in packet["evidence_coach"]["numeric_fact_registry"]
    }

    assert compact_structure_refs <= full_structure_refs
    assert compact_level_refs <= full_level_refs


def test_head_coach_cannot_cite_a_full_packet_reference_omitted_from_model_input() -> None:
    packet = _packet()
    model_state = build_head_coach_model_state(packet)
    model_state["evidence_coach"]["numeric_facts"] = []
    analysis = _analysis("Use [[structure:known]] with [[level:known]].")

    with pytest.raises(TwoCoachContractError, match="blocked_unknown_evidence_reference"):
        validate_head_coach_analysis(analysis, packet, model_state)


def test_prior_trade_retrieval_is_point_in_time_balanced_and_input_order_invariant() -> None:
    records = [
        _validated_trade("winner", "SPY", "long_call", "2026-07-10", 1.0),
        _validated_trade("loser", "SPY", "long_call", "2026-07-09", -1.0),
        _validated_trade("other", "META", "long_put", "2026-07-08", -0.5),
        _validated_trade("future", "SPY", "long_call", "2026-07-22", 2.0),
    ]

    first = retrieve_prior_trade_lessons(records, "SPY", "long_call", "2026-07-21", "source-hash")
    second = retrieve_prior_trade_lessons(list(reversed(records)), "SPY", "long_call", "2026-07-21", "source-hash")

    assert first == second
    assert {lesson["outcome_bucket"] for lesson in first["lessons"]} >= {"winner", "loser"}
    assert "future" not in {lesson["source_position_id"] for lesson in first["lessons"]}
    assert first["pnl_magnitude_used_for_ranking"] is False
    assert first["censored_included"] is False
    assert first["quarantined_included"] is False


@pytest.mark.parametrize(
    "literal",
    ("$100.25", "100", ".50", "1e2", "100,000", "-3.5%"),
)
def test_head_coach_contract_rejects_free_numeric_literals(literal: str) -> None:
    analysis = _analysis(f"Grounded support is {literal} near [[level:known]].")
    packet = _packet()

    with pytest.raises(TwoCoachContractError, match="blocked_hallucinated_numeric_literal"):
        validate_head_coach_analysis(
            analysis,
            packet,
            build_head_coach_model_state(packet),
        )


def test_head_coach_contract_resolves_registered_references() -> None:
    analysis = _analysis("Use [[structure:known]] with [[level:known]].")
    packet = _packet()

    result = validate_head_coach_analysis(
        analysis,
        packet,
        build_head_coach_model_state(packet),
    )

    assert result["all_references_resolved"] is True
    assert result["numeric_grounding_status"] == "verified_no_free_numeric_literals"
    assert result["unique_reference_count"] == 2


def test_head_coach_contract_rejects_unknown_reference() -> None:
    analysis = _analysis("Use [[structure:unknown]] with [[level:known]].")
    packet = _packet()

    with pytest.raises(TwoCoachContractError, match="blocked_unknown_evidence_reference"):
        validate_head_coach_analysis(
            analysis,
            packet,
            build_head_coach_model_state(packet),
        )


def test_selected_head_coach_never_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        frontier_module,
        "head_coach_availability",
        lambda: {
            "claude": {"available": True, "availability_reason": "fixture"},
            "codex": {"available": False, "availability_reason": "fixture_missing"},
        },
    )
    calls: list[str] = []
    monkeypatch.setattr(
        frontier_module,
        "run_frontier_council",
        lambda *args: calls.append("claude") or {},
    )

    with pytest.raises(RuntimeError, match="no fallback is allowed"):
        frontier_module.run_research_head_coach("bounded review", "codex", {}, 30)

    assert calls == []


def test_claude_head_coach_requires_the_existing_four_model_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    structured = _analysis("Use [[structure:known]] with [[level:known]].")
    expected_models = [OPENROUTER_MODELS[provider] for provider in OPENROUTER_HYBRID_COMPONENTS]
    monkeypatch.setattr(
        frontier_module,
        "head_coach_availability",
        lambda: {
            "claude": {"available": True, "availability_reason": "fixture"},
            "codex": {"available": True, "availability_reason": "fixture"},
        },
    )

    def council(
        objective: str,
        providers: tuple[str, ...],
        state: dict[str, Any],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        assert objective and state == {"packet": "fixture"} and timeout_seconds == 30
        assert providers == (frontier_module.OPENROUTER_HYBRID_PROVIDER,)
        return {
            "results": [
                {
                    "component_models": expected_models,
                    "structured_analysis": structured,
                    "usage": {"cost": 0.01},
                    "paid_response_count": 4,
                    "paid_response_ids": ["one", "two", "three", "four"],
                    "routing_plan": {},
                }
            ]
        }

    monkeypatch.setattr(frontier_module, "run_frontier_council", council)

    result = frontier_module.run_research_head_coach(
        "bounded review",
        "claude",
        {"packet": "fixture"},
        30,
    )

    assert result["head_coach_id"] == "claude"
    assert result["head_coach_model"] == "anthropic/claude-sonnet-5"
    assert result["route_id"] == "openrouter_four_model_hybrid"
    assert result["runtime_fallback_used"] is False
