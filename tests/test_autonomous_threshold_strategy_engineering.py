"""Integration coverage for threshold control and strategy engineering."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dopey.gates.adaptation import propose_stricter_policy
from dopey.gates.audit import audit_threshold_fabric
from dopey.gates.evaluator import evaluate_gate
from dopey.gates.policy import AUTONOMOUS_GATE_POLICIES, policy_by_id
from dopey.gates.sequential import confidence_sequence, conformal_abstention_threshold, online_alpha_budget
from dopey.memory.ledger import MemoryKind, build_memory_record
from dopey.strategy_engineering.runtime import run_strategy_engineering_cycle
from dopey.strategy_engineering.factor_language import build_factor_program, evaluate_factor_program
from dopey_acceleration.cycle import _commands
from dopey_acceleration.schedule import LANES, LANE_EVIDENCE_CONTRACTS, REPO_ROOT


def _prediction(index: int) -> dict[str, Any]:
    year = 2024 + (index // 2) % 2
    high = index % 2 == 0
    return {
        "prediction_id": f"prediction:{index}",
        "symbol": "SPY" if index % 3 else "QQQ",
        "prediction_market_time": f"{year}-01-02T20:00:00+00:00",
        "hypotheses": {"bull": 0.70 if high else 0.25, "bear": 0.10 if high else 0.45, "neutral": 0.10 if high else 0.20, "unknown": 0.10},
        "agent_contributions": {"momentum_agent": 0.75 if high else -0.25},
        "final_research_confidence": 0.75 if high else 0.25,
        "evidence_ids": [f"evidence:{index}"],
        "point_in_time_proof_id": f"proof:{index}",
        "point_in_time_complete": True,
        "paper_only": True,
        "live_blocked": True,
    }


def _settlement(index: int) -> dict[str, Any]:
    year = 2024 + (index // 2) % 2
    return {
        "prediction_id": f"prediction:{index}",
        "settlement_status": "settled_forward_outcome",
        "actual_settlement_date": f"{year}-02-02",
        "dominant_correct": index % 2 == 0,
        "contested_truth": index % 5 == 0,
        "paper_only": True,
        "live_blocked": True,
    }


def test_threshold_fabric_is_fail_closed_and_tighten_only() -> None:
    audit = audit_threshold_fabric(AUTONOMOUS_GATE_POLICIES, datetime(2026, 7, 16, tzinfo=timezone.utc))
    decision = evaluate_gate(
        policy_by_id("data_admission"),
        "dataset:SPY",
        {"point_in_time_complete": True, "provenance_complete": True, "schema_valid": True, "freshness": 1.0},
        ("manifest:1",),
    )
    looser = propose_stricter_policy(policy_by_id("data_admission"), "missing_fraction", 0.10, ("evidence:1",))
    stricter = propose_stricter_policy(policy_by_id("data_admission"), "missing_fraction", 0.02, ("evidence:1",))

    assert audit["audit_status"] == "complete"
    assert decision["passed"] is False
    assert decision["decision"] == "QUARANTINE"
    assert decision["positive_promotion_allowed"] is False
    assert looser["adaptation_status"] == "rejected_not_stricter_or_missing_evidence"
    assert stricter["adaptation_status"] == "accepted_stricter"


def test_sequential_controls_are_conservative_and_explicit() -> None:
    sequence = confidence_sequence((0.8,) * 40, 0.05)
    alpha = online_alpha_budget(0.05, 10)
    conformal = conformal_abstention_threshold(tuple(index / 20 for index in range(20)), 0.10)

    assert sequence["status"] == "anytime_valid_union_bound"
    assert float(sequence["lower"]) <= 0.8 <= float(sequence["upper"])
    assert float(alpha["spent_upper_bound"]) < 0.05
    assert conformal["status"] == "finite_sample_split_conformal"


def test_factor_language_is_executable_and_has_no_future_or_order_operators() -> None:
    program = build_factor_program(("trend_strength", "volatility_state", "participation"))
    values = evaluate_factor_program(
        program,
        {
            "trend_strength": (0.4, 0.6),
            "volatility_state": (0.2, 0.3),
            "participation": (0.5, 0.7),
        },
    )

    assert values == (0.35, 0.5)
    assert program["future_data_operators_allowed"] is False
    assert program["order_construction_allowed"] is False


def test_strategy_engineering_builds_shadow_candidates_and_reverse_hypotheses(tmp_path: Path) -> None:
    output = run_strategy_engineering_cycle(
        tuple(_prediction(index) for index in range(24)),
        tuple(_settlement(index) for index in range(24)),
        tmp_path,
        24,
        8,
        datetime(2026, 7, 16, tzinfo=timezone.utc),
    )

    assert output["cycle_status"] == "complete_shadow_only"
    assert output["forward_candidate_count"] == 24
    assert output["reverse_steered_candidate_count"] == 24
    assert output["shadow_admitted_count"] == 24
    assert output["reverse_report"]["reverse_status"] == "complete_association_hypotheses_only"
    assert output["reverse_report"]["causal_claim_allowed"] is False
    assert output["quality_diversity_archive"]["single_scalar_champion_selected"] is False
    assert output["positive_promotion_allowed"] is False
    assert output["order_construction_allowed"] is False
    assert (tmp_path / "latest_cycle.json").is_file()


def test_strategy_engineering_reports_insufficient_forward_truth_honestly(tmp_path: Path) -> None:
    output = run_strategy_engineering_cycle(
        (),
        (),
        tmp_path,
        8,
        20,
        datetime(2026, 7, 16, tzinfo=timezone.utc),
    )

    assert output["reverse_report"]["reverse_status"] == "insufficient_settled_observations"
    assert output["forward_candidate_count"] == 8
    assert output["readiness_effect"] == "none"


def test_strategy_engineering_unwraps_canonical_settlement_memory(tmp_path: Path) -> None:
    settlements = tuple(
        build_memory_record(
            MemoryKind.SETTLEMENT,
            _settlement(index),
            "2026-07-16T20:00:00+00:00",
            f"prediction:{index}",
            (f"settlement:{index}",),
            "dopey-settlement-memory-v1",
        )
        for index in range(8)
    )
    output = run_strategy_engineering_cycle(
        tuple(_prediction(index) for index in range(8)),
        settlements,
        tmp_path,
        8,
        4,
        datetime(2026, 7, 16, tzinfo=timezone.utc),
    )

    assert output["reverse_report"]["settled_case_count"] == 8
    assert output["reverse_report"]["reverse_status"] == "complete_association_hypotheses_only"


def test_threshold_and_strategy_lanes_are_local_allowlisted_and_evidence_verified() -> None:
    policies = {record["lane_id"]: record for record in LANES}
    commands = _commands(REPO_ROOT)

    for lane_id in ("autonomous_threshold_audit", "strategy_engineering_research"):
        assert policies[lane_id]["network"] is False
        assert policies[lane_id]["retries"] == 1
        assert lane_id in commands
        assert lane_id in LANE_EVIDENCE_CONTRACTS
