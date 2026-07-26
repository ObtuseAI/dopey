"""Integration smoke coverage for the cross-client acceleration control plane."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TextIO

import pytest

from dopey_acceleration import autonomous_improvement as autonomous_improvement_module
from dopey_acceleration import schedule as schedule_module
from dopey_acceleration import readiness as readiness_module
from dopey_acceleration.autonomous_improvement import (
    _operational_override,
    run_autonomous_improvement_cycle,
)
from dopey_acceleration.cycle import (
    _commands,
    _reconcile_evidence_state,
    _record_completed_lane,
    _record_started_lane,
)
from dopey_acceleration.common import stamped, write_json_atomic
from dopey_acceleration.llm_research import _successful_analyses
from dopey_acceleration.reliability_guard import evaluate_reliability_guard
from dopey_acceleration.research_mutations import (
    ResearchMutationEvidence,
    ResearchMutationState,
    activated_research_overrides,
    evaluate_research_mutation,
    propose_research_mutations,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = Path(sys.executable)


def test_acceleration_json_write_replaces_without_temp_residue(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state.json"

    write_json_atomic(target, {"generation": 1})
    write_json_atomic(target, {"generation": 2})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "generation": 2
    }
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


def test_research_control_plane_has_no_live_or_broker_lane() -> None:
    lane_ids = {record["lane_id"] for record in schedule_module.LANES}
    commands = _commands(REPO_ROOT)

    assert "live_branch" not in lane_ids
    assert "live_branch" not in commands
    assert "daily_close_stack" not in commands
    assert "nightly_validation" not in commands
    assert not any(
        term in " ".join(command).lower()
        for command in commands.values()
        for term in ("broker", "place_order", "operator_live_branch")
    )


def test_research_mutation_requires_independent_shadow_evidence_before_command_use(
    tmp_path: Path,
) -> None:
    proposals = propose_research_mutations(
        {
            "autonomous_strategy_research": {
                "status": "degraded_evidence"
            }
        }
    )
    assert len(proposals) == 1
    proposal = proposals[0]
    pending = evaluate_research_mutation(proposal, None)
    assert pending["state"] is ResearchMutationState.PENDING_SHADOW_EVIDENCE
    assert activated_research_overrides((pending,)) == {}

    evidence: ResearchMutationEvidence = {
        "proposal_id": proposal["proposal_id"],
        "sample_count": 40,
        "effect_interval_lower": 0.03,
        "cost_ratio": 0.90,
        "evaluator_independent": True,
        "deterministic": True,
        "invariant_violations": (),
    }
    approved = evaluate_research_mutation(proposal, evidence)
    overrides = activated_research_overrides((approved,))
    assert approved["state"] is ResearchMutationState.SHADOW_APPROVED
    assert overrides == {
        "autonomous_strategy_research.candidate_budget": 16
    }

    policy_path = (
        tmp_path
        / "artifacts"
        / "dopey"
        / "acceleration"
        / "autonomous_improvement"
        / "active_policy.json"
    )
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps(
            stamped(
                {
                    "policy_status": "active_threshold_gated",
                    "research_overrides": overrides,
                    "evidence_thresholds_lowered": False,
                    "paper_only": True,
                    "live_blocked": True,
                }
            )
        ),
        encoding="utf-8",
    )
    command = _commands(tmp_path)["autonomous_strategy_research"]
    assert command[command.index("--candidate-budget") + 1] == "16"


def test_standalone_operator_lanes_are_visible_but_never_acceleration_due(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "schedule_state.json"
    plan_path = tmp_path / "schedule_plan.json"
    state_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(schedule_module, "SCHEDULE_STATE_PATH", state_path)
    monkeypatch.setattr(schedule_module, "SCHEDULE_PLAN_PATH", plan_path)
    now_by_lane = {
        "daily_close_stack": datetime(2026, 7, 20, 22, 0, tzinfo=timezone.utc),
        "nightly_validation": datetime(2026, 7, 21, 9, 0, tzinfo=timezone.utc),
    }
    for lane_id, owner in schedule_module.EXTERNAL_LANE_OWNERS.items():
        plan = schedule_module.build_schedule_plan(
            schedule_module.REPO_ROOT,
            now_by_lane[lane_id],
            (lane_id,),
        )
        by_id = {record["lane_id"]: record for record in plan["lanes"]}
        assert by_id[lane_id]["calendar_due"] is True
        assert by_id[lane_id]["due"] is False
        assert by_id[lane_id]["execution_owner"] == owner
        assert by_id[lane_id]["subsumed_by"] == owner
        assert lane_id not in plan["due_lane_ids"]


def test_vnext_forward_lane_is_gated_and_evidence_verified() -> None:
    policy = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "vnext_forward_research"
    )
    contract = schedule_module.LANE_EVIDENCE_CONTRACTS["vnext_forward_research"]
    command = _commands(REPO_ROOT)["vnext_forward_research"]

    assert policy["network"] is False
    assert policy["window"] == "after_close"
    assert policy["timeout_seconds"] == 10_800
    assert contract["status_key"] == "batch_status"
    assert contract["required_status"] == "complete_awaiting_forward_settlement"
    assert command[-2:] == ["-m", "dopey.runtime.run_cross_sectional_vnext"]
    assert not any(
        term in " ".join(command).lower() for term in ("broker", "order", "credential")
    )


def test_symbol_intelligence_lane_is_daily_local_and_evidence_verified() -> None:
    policy = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "symbol_intelligence_lab"
    )
    contract = schedule_module.LANE_EVIDENCE_CONTRACTS["symbol_intelligence_lab"]
    command = _commands(REPO_ROOT)["symbol_intelligence_lab"]

    assert policy["network"] is False
    assert policy["window"] == "after_close"
    assert policy["interval_minutes"] == 1_440
    assert policy["timeout_seconds"] == 7_200
    assert contract["status_key"] == "batch_status"
    assert contract["required_status"] == "complete"
    assert command[1:] == ["-m", "dopey_symbol_lab.run_symbol_lab", "--all"]
    assert not any(
        term in " ".join(command).lower() for term in ("broker", "order", "credential")
    )


def test_playbook_refresh_lane_is_multidaily_local_and_evidence_verified() -> None:
    policy = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "playbook_refresh"
    )
    contract = schedule_module.LANE_EVIDENCE_CONTRACTS["playbook_refresh"]
    command = _commands(REPO_ROOT)["playbook_refresh"]

    assert policy["network"] is False
    assert policy["window"] == "always"
    assert policy["interval_minutes"] == 240
    assert policy["timeout_seconds"] == 900
    assert contract["status_key"] == "refresh_status"
    assert contract["required_status"] == "complete"
    assert Path(contract["artifact_path"]).parts[-3:] == (
        "dopey",
        "playbook",
        "playbook_refresh_result.json",
    )
    assert command[1:] == ["-m", "dopey.strategy_engineering.run_playbook_refresh"]
    assert not any(
        term in " ".join(command).lower() for term in ("broker", "order", "credential")
    )


def test_autonomous_strategy_lane_is_local_bounded_and_evidence_verified() -> None:
    policy = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "autonomous_strategy_research"
    )
    contract = schedule_module.LANE_EVIDENCE_CONTRACTS["autonomous_strategy_research"]
    command = _commands(REPO_ROOT)["autonomous_strategy_research"]

    assert policy["network"] is False
    assert policy["interval_minutes"] == 240
    assert policy["timeout_seconds"] == 1_800
    assert contract["status_key"] == "cycle_status"
    assert contract["required_status"] == "experiments_queued"
    assert command[1:3] == ["-m", "dopey.autoresearch.run_autoresearch_cycle"]
    assert command[command.index("--candidate-budget") + 1] == "24"
    assert not any(
        term in " ".join(command).lower() for term in ("broker", "order", "credential")
    )
    evaluation_policy = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "autonomous_experiment_evaluation"
    )
    evaluation_contract = schedule_module.LANE_EVIDENCE_CONTRACTS[
        "autonomous_experiment_evaluation"
    ]
    evaluation_command = _commands(REPO_ROOT)["autonomous_experiment_evaluation"]
    assert evaluation_policy["network"] is False
    assert evaluation_policy["interval_minutes"] == 240
    assert evaluation_contract["status_key"] == "evaluation_status"
    assert evaluation_contract["timestamp_key"] == "last_verified_at"
    assert evaluation_contract["max_age_hours"] == 8.0
    assert evaluation_command[1:3] == [
        "-m",
        "dopey.autoresearch.run_experiment_evaluation",
    ]

    coached_policy = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "coached_evolution_cycle"
    )
    coached_contract = schedule_module.LANE_EVIDENCE_CONTRACTS[
        "coached_evolution_cycle"
    ]
    coached_command = _commands(REPO_ROOT)["coached_evolution_cycle"]
    assert coached_policy["network"] is True
    assert coached_policy["interval_minutes"] == 240
    assert coached_policy["timeout_seconds"] == 2_100
    assert coached_policy["retries"] == 1
    assert coached_contract["status_key"] == "run_status"
    assert coached_contract["required_status"] == "complete"
    assert coached_command[1:3] == [
        "-m",
        "dopey_evolution.run_coached_evolution_cycle",
    ]
    assert coached_command[coached_command.index("--symbol") + 1] == "SPY"
    assert coached_command[coached_command.index("--timeframe") + 1] == "daily"
    assert coached_command[coached_command.index("--head-coach") + 1] == "claude"
    assert (
        coached_command[coached_command.index("--daily-new-session-limit") + 1] == "1"
    )
    assert "--force" not in coached_command
    assert not any(
        term in " ".join(coached_command).lower()
        for term in ("broker", "place_order", "credential")
    )

    coach_policy = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "coach_proposal_quarantine"
    )
    coach_contract = schedule_module.LANE_EVIDENCE_CONTRACTS[
        "coach_proposal_quarantine"
    ]
    coach_command = _commands(REPO_ROOT)["coach_proposal_quarantine"]
    assert coach_policy["network"] is False
    assert coach_policy["interval_minutes"] == 240
    assert coach_policy["timeout_seconds"] == 120
    assert coach_contract["status_key"] == "batch_status"
    assert coach_contract["required_status"] == "complete"
    assert coach_command[1:3] == ["-m", "dopey_evolution.run_coach_bridge"]
    assert not any(
        term in " ".join(coach_command).lower()
        for term in ("broker", "order", "credential")
    )

    promotion_policy = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "autonomous_promotion_evaluation"
    )
    promotion_command = _commands(REPO_ROOT)["autonomous_promotion_evaluation"]
    promotion_contract = schedule_module.LANE_EVIDENCE_CONTRACTS[
        "autonomous_promotion_evaluation"
    ]
    assert promotion_policy["network"] is False
    assert promotion_policy["timeout_seconds"] == 600
    assert promotion_command[1:3] == ["-m", "dopey.promotion.run_promotion_cycle"]
    assert promotion_contract["status_key"] == "evaluation_status"
    assert promotion_contract["required_status"] == "complete"

    synthesis_policy = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "autonomous_promotion_evidence_synthesis"
    )
    synthesis_contract = schedule_module.LANE_EVIDENCE_CONTRACTS[
        "autonomous_promotion_evidence_synthesis"
    ]
    synthesis_command = _commands(REPO_ROOT)["autonomous_promotion_evidence_synthesis"]
    assert synthesis_policy["network"] is False
    assert synthesis_policy["timeout_seconds"] == 600
    assert synthesis_contract["status_key"] == "synthesis_status"
    assert synthesis_contract["required_status"] == "complete"
    assert synthesis_command[1:3] == ["-m", "dopey.autoresearch.run_evidence_synthesis"]

    intelligence_policy = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "intelligence_discovery_research"
    )
    intelligence_contract = schedule_module.LANE_EVIDENCE_CONTRACTS[
        "intelligence_discovery_research"
    ]
    intelligence_command = _commands(REPO_ROOT)["intelligence_discovery_research"]
    assert intelligence_policy["network"] is False
    assert intelligence_policy["interval_minutes"] == 360
    assert intelligence_policy["timeout_seconds"] == 900
    assert intelligence_contract["required_status"] == "cognitive_experiments_queued"
    assert intelligence_command[1:3] == [
        "-m",
        "dopey.intelligence_research.run_intelligence_cycle",
    ]
    assert (
        intelligence_command[intelligence_command.index("--cognitive-level") + 1] == "2"
    )
    llm_research_path = Path(
        intelligence_command[intelligence_command.index("--llm-research") + 1]
    )
    assert llm_research_path.parts[-4:] == (
        "artifacts",
        "dopey",
        "llm_research",
        "latest_cycle.json",
    )

    llm_policy = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "llm_frontier_research"
    )
    llm_contract = schedule_module.LANE_EVIDENCE_CONTRACTS["llm_frontier_research"]
    llm_command = _commands(REPO_ROOT)["llm_frontier_research"]
    assert llm_policy["network"] is True
    assert llm_policy["interval_minutes"] == 360
    assert llm_policy["timeout_seconds"] == 2_100
    assert llm_contract["status_key"] == "cycle_status"
    assert llm_contract["required_status"] == "complete_analysis_current"
    assert llm_command[1:3] == ["-m", "dopey_acceleration.run_llm_research"]
    assert llm_command[llm_command.index("--timeout-seconds") + 1] == "300"
    assert not any(
        term in " ".join(llm_command).lower()
        for term in ("broker", "order", "credential")
    )

    improvement_policy = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "autonomous_self_improvement"
    )
    improvement_contract = schedule_module.LANE_EVIDENCE_CONTRACTS[
        "autonomous_self_improvement"
    ]
    improvement_command = _commands(REPO_ROOT)["autonomous_self_improvement"]
    assert improvement_policy["network"] is False
    assert improvement_contract["required_status"] == "complete"
    assert improvement_command[1:3] == [
        "-m",
        "dopey_acceleration.run_autonomous_improvement",
    ]


def test_operational_self_improvement_only_changes_sealed_fields() -> None:
    lane = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "llm_frontier_research"
    )
    override, reasons = _operational_override(
        lane,
        "inconclusive_timeout",
        True,
    )

    assert override == {"timeout_seconds": 3150}
    assert reasons == ["bounded_timeout_recovery"]
    assert set(override) <= {"interval_minutes", "timeout_seconds", "retries"}


@pytest.mark.parametrize(
    "lane_id",
    ("coached_evolution_cycle", "llm_frontier_research"),
)
def test_paid_model_lanes_never_gain_outer_retries(lane_id: str) -> None:
    lane = next(
        record for record in schedule_module.LANES if record["lane_id"] == lane_id
    )

    override, reasons = _operational_override(
        lane,
        "failed",
        True,
    )

    assert "retries" not in override
    assert "bounded_transient_network_retry" not in reasons


def _write_control_plane_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record), encoding="utf-8")


def _verified_lane_evidence() -> dict[str, Any]:
    return {
        "verification_required": True,
        "verification_status": "verified_complete",
        "artifact_path": "test-artifact.json",
        "artifact_availability": "available",
        "status_key": "status",
        "actual_status": "complete",
        "required_status": "complete",
        "verified_complete": True,
    }


@pytest.mark.parametrize(
    ("slo_record", "expected_guard_status"),
    (
        (None, "blocked_unverified_reliability_artifact"),
        (
            stamped(
                {
                    "artifact_type": "reliability_slo",
                    "slo_version": "dopey-reliability-slo-v3",
                    "slo_status": "error_budget_breached",
                    "as_of_date": "2026-07-24",
                    "generated_at_utc": "2026-07-24T11:30:00+00:00",
                    "breaches": ["test reliability breach"],
                    "operational_cadence_guard_allowed": True,
                    "operational_cadence_guard_scope": "fail_closed_cadence_acceleration_only",
                    "edge_evidence_allowed": False,
                    "readiness_gate_input_allowed": False,
                    "trading_gate_input_allowed": False,
                    "paper_only": True,
                    "live_blocked": True,
                }
            ),
            "blocked_error_budget_breached",
        ),
    ),
)
def test_autonomous_improvement_suppresses_cadence_and_excludes_external_lanes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    slo_record: dict[str, Any] | None,
    expected_guard_status: str,
) -> None:
    repo_root = tmp_path / "repo"
    output_root = (
        repo_root / "artifacts" / "dopey" / "acceleration" / "autonomous_improvement"
    )
    schedule_state_path = tmp_path / "schedule_state.json"
    _write_control_plane_json(
        schedule_state_path,
        {
            "lane_statuses": {
                "autonomous_strategy_research": {"status": "completed"},
            }
        },
    )
    if slo_record is not None:
        _write_control_plane_json(
            repo_root / "artifacts" / "dopey" / "ops" / "reliability_slo.json",
            slo_record,
        )
    monkeypatch.setattr(
        autonomous_improvement_module,
        "SCHEDULE_STATE_PATH",
        schedule_state_path,
    )
    monkeypatch.setattr(
        autonomous_improvement_module,
        "evaluate_lane_evidence",
        lambda _lane_id: _verified_lane_evidence(),
    )

    result = run_autonomous_improvement_cycle(
        repo_root,
        output_root,
        datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
    )
    active_policy = json.loads(
        (output_root / "active_policy.json").read_text(encoding="utf-8")
    )
    coverage_by_id = {
        str(record["lane_id"]): record for record in result["lane_coverage"]
    }

    assert result["reliability_guard"]["guard_status"] == expected_guard_status
    assert result["reliability_guard"]["cadence_acceleration_allowed"] is False
    assert all(
        "interval_minutes" not in override
        for override in active_policy["lane_overrides"].values()
    )
    assert result["all_schedule_lanes_self_improvable"] is False
    assert result["all_owned_schedule_lanes_self_improvable"] is True
    for lane_id, owner in schedule_module.EXTERNAL_LANE_OWNERS.items():
        assert lane_id not in active_policy["lane_overrides"]
        assert coverage_by_id[lane_id]["self_improvement_enabled"] is False
        assert coverage_by_id[lane_id]["execution_owner"] == owner
        assert (
            coverage_by_id[lane_id]["self_improvement_exclusion_reason"]
            == "externally_owned_lane"
        )
    history_path = Path(result["policy_history_path"])
    assert history_path.exists()
    assert (
        json.loads(history_path.read_text(encoding="utf-8"))["immutable_history"]
        is True
    )


def test_autonomous_improvement_records_reliability_rollback_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    output_root = (
        repo_root / "artifacts" / "dopey" / "acceleration" / "autonomous_improvement"
    )
    slo_path = repo_root / "artifacts" / "dopey" / "ops" / "reliability_slo.json"
    schedule_state_path = tmp_path / "schedule_state.json"
    _write_control_plane_json(schedule_state_path, {"lane_statuses": {}})
    monkeypatch.setattr(
        autonomous_improvement_module,
        "SCHEDULE_STATE_PATH",
        schedule_state_path,
    )
    monkeypatch.setattr(
        autonomous_improvement_module,
        "evaluate_lane_evidence",
        lambda _lane_id: _verified_lane_evidence(),
    )
    _write_control_plane_json(
        slo_path,
        stamped(
            {
                "artifact_type": "reliability_slo",
                "slo_version": "dopey-reliability-slo-v3",
                "slo_status": "within_error_budget",
                "as_of_date": "2026-07-24",
                "generated_at_utc": "2026-07-24T11:30:00+00:00",
                "breaches": [],
                "operational_cadence_guard_allowed": True,
                "operational_cadence_guard_scope": "fail_closed_cadence_acceleration_only",
                "edge_evidence_allowed": False,
                "readiness_gate_input_allowed": False,
                "trading_gate_input_allowed": False,
                "paper_only": True,
                "live_blocked": True,
            }
        ),
    )
    first = run_autonomous_improvement_cycle(
        repo_root,
        output_root,
        datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
    )
    first_history_path = Path(first["policy_history_path"])
    first_history = first_history_path.read_text(encoding="utf-8")
    first_policy = json.loads(
        (output_root / "active_policy.json").read_text(encoding="utf-8")
    )
    assert any(
        "interval_minutes" in override
        for override in first_policy["lane_overrides"].values()
    )
    assert not (
        set(first_policy["lane_overrides"]) & set(schedule_module.EXTERNAL_LANE_OWNERS)
    )
    monkeypatch.setattr(schedule_module, "REPO_ROOT", repo_root)
    monkeypatch.setattr(
        schedule_module,
        "ACTIVE_IMPROVEMENT_POLICY_PATH",
        output_root / "active_policy.json",
    )
    first_effective_lanes, first_effective_policy_status = (
        schedule_module._effective_lanes(
            datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
        )
    )
    first_context_lane = next(
        record
        for record in first_effective_lanes
        if record["lane_id"] == "context_outcome_settlement"
    )
    assert first_context_lane["interval_minutes"] == 120
    assert first_effective_policy_status == "active_threshold_gated"

    _write_control_plane_json(
        slo_path,
        stamped(
            {
                "artifact_type": "reliability_slo",
                "slo_version": "dopey-reliability-slo-v3",
                "slo_status": "error_budget_breached",
                "as_of_date": "2026-07-24",
                "generated_at_utc": "2026-07-24T12:30:00+00:00",
                "breaches": ["test reliability breach"],
                "operational_cadence_guard_allowed": True,
                "operational_cadence_guard_scope": "fail_closed_cadence_acceleration_only",
                "edge_evidence_allowed": False,
                "readiness_gate_input_allowed": False,
                "trading_gate_input_allowed": False,
                "paper_only": True,
                "live_blocked": True,
            }
        ),
    )
    second = run_autonomous_improvement_cycle(
        repo_root,
        output_root,
        datetime(2026, 7, 24, 13, 0, tzinfo=timezone.utc),
    )
    second_policy = json.loads(
        (output_root / "active_policy.json").read_text(encoding="utf-8")
    )
    latest_cycle = json.loads(
        (output_root / "latest_cycle.json").read_text(encoding="utf-8")
    )
    history_paths = sorted((output_root / "history").glob("*.json"))
    transitions = [
        json.loads(line)
        for line in (output_root / "policy_transitions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    monkeypatch.setattr(
        schedule_module,
        "ACTIVE_IMPROVEMENT_POLICY_PATH",
        output_root / "active_policy.json",
    )
    effective_lanes, effective_policy_status = schedule_module._effective_lanes(
        datetime(2026, 7, 24, 13, 0, tzinfo=timezone.utc)
    )

    assert (
        second["policy_transition"]["transition_type"] == "reliability_guard_rollback"
    )
    assert second["previous_policy_hash"] == first_policy["reproducibility_hash"]
    assert second["automatic_rollback_count"] > 0
    assert second["reliability_interval_rollback_lane_ids"]
    assert all(
        "interval_minutes" not in override
        for override in second_policy["lane_overrides"].values()
    )
    assert len(history_paths) == 2
    assert first_history_path.read_text(encoding="utf-8") == first_history
    assert len(transitions) == 2
    assert (
        transitions[-1]["reproducibility_hash"]
        == second["policy_transition"]["reproducibility_hash"]
    )
    assert effective_policy_status == "active_recovery_only_cadence_baseline"
    assert len(effective_lanes) == len(schedule_module.LANES)
    assert second["paper_only"] is True
    assert second["live_blocked"] is True
    assert (
        latest_cycle["cycle_status"]
        == schedule_module.LANE_EVIDENCE_CONTRACTS["autonomous_self_improvement"][
            "required_status"
        ]
    )
    assert latest_cycle["activation_status"] == "activation_committed"


def test_schedule_rejects_tampered_autonomous_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = tmp_path / "active_policy.json"
    policy = stamped(
        {
            "artifact_type": "autonomous_improvement_active_policy",
            "policy_status": "active_threshold_gated",
            "lane_overrides": {},
            "evidence_thresholds_lowered": False,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    policy["lane_overrides"] = {
        "news_intake": {
            "interval_minutes": 15,
        }
    }
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setattr(
        schedule_module,
        "ACTIVE_IMPROVEMENT_POLICY_PATH",
        policy_path,
    )

    with pytest.raises(ValueError, match="reproducibility hash validation"):
        schedule_module._effective_lanes(
            datetime(2026, 7, 24, 13, 0, tzinfo=timezone.utc)
        )


def test_schedule_neutralizes_legacy_interval_acceleration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = tmp_path / "active_policy.json"
    policy = stamped(
        {
            "artifact_type": "autonomous_improvement_active_policy",
            "policy_version": "dopey-autonomous-improvement-v1",
            "policy_status": "active_threshold_gated",
            "lane_overrides": {
                "context_outcome_settlement": {
                    "interval_minutes": 120,
                    "timeout_seconds": 360,
                }
            },
            "evidence_thresholds_lowered": False,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setattr(
        schedule_module,
        "ACTIVE_IMPROVEMENT_POLICY_PATH",
        policy_path,
    )

    effective, status = schedule_module._effective_lanes(
        datetime(2026, 7, 24, 13, 0, tzinfo=timezone.utc)
    )
    lane = next(
        record
        for record in effective
        if record["lane_id"] == "context_outcome_settlement"
    )

    assert lane["interval_minutes"] == 240
    assert lane["timeout_seconds"] == 360
    assert status == "active_recovery_only_cadence_baseline"


def test_schedule_ignores_uncommitted_v2_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = tmp_path / "active_policy.json"
    policy = stamped(
        {
            "artifact_type": "autonomous_improvement_active_policy",
            "policy_version": "dopey-autonomous-improvement-v2",
            "policy_status": "active_threshold_gated",
            "lane_overrides": {
                "context_outcome_settlement": {
                    "timeout_seconds": 360,
                }
            },
            "evidence_thresholds_lowered": False,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setattr(
        schedule_module,
        "ACTIVE_IMPROVEMENT_POLICY_PATH",
        policy_path,
    )

    effective, status = schedule_module._effective_lanes(
        datetime(2026, 7, 24, 13, 0, tzinfo=timezone.utc)
    )
    lane = next(
        record
        for record in effective
        if record["lane_id"] == "context_outcome_settlement"
    )

    assert lane["timeout_seconds"] == 180
    assert status == "baseline_uncommitted_active_policy"


def test_reliability_guard_rejects_tampered_and_stale_slo(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    slo_path = repo_root / "artifacts" / "dopey" / "ops" / "reliability_slo.json"
    valid = stamped(
        {
            "artifact_type": "reliability_slo",
            "slo_version": "dopey-reliability-slo-v3",
            "slo_status": "within_error_budget",
            "as_of_date": "2026-07-24",
            "generated_at_utc": "2026-07-24T11:30:00+00:00",
            "breaches": [],
            "operational_cadence_guard_allowed": True,
            "operational_cadence_guard_scope": "fail_closed_cadence_acceleration_only",
            "edge_evidence_allowed": False,
            "readiness_gate_input_allowed": False,
            "trading_gate_input_allowed": False,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    tampered = {**valid, "slo_status": "error_budget_breached"}
    _write_control_plane_json(slo_path, tampered)

    tampered_guard = evaluate_reliability_guard(
        repo_root,
        datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
    )

    assert tampered_guard["guard_status"] == "blocked_unverified_reliability_artifact"
    assert "hash" in tampered_guard["detail"]

    stale_payload = dict(valid)
    stale_payload.pop("reproducibility_hash")
    stale_payload["generated_at_utc"] = "2026-07-22T00:00:00+00:00"
    stale = stamped(stale_payload)
    _write_control_plane_json(slo_path, stale)

    stale_guard = evaluate_reliability_guard(
        repo_root,
        datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
    )

    assert stale_guard["guard_status"] == "blocked_unverified_reliability_artifact"
    assert "stale" in stale_guard["detail"]


def test_hybrid_component_analyses_reach_the_adjudicator() -> None:
    component = {
        "summary": "component",
        "hypotheses": [],
        "adversarial_findings": [],
        "uncertainties": [],
        "recommended_experiments": [],
        "abstain": True,
    }
    fused = {**component, "summary": "fused"}
    council = {
        "results": [
            {
                "provider": "openrouter_four_model_hybrid",
                "model": (
                    "google/gemini-3.6-flash + openai/gpt-5.6-luna + "
                    "z-ai/glm-5.2 + anthropic/claude-sonnet-5"
                ),
                "status": "completed_analysis_only",
                "structured_analysis": fused,
                "component_analyses": [
                    {
                        "provider": "openrouter_gemini_3_6_flash",
                        "model": "google/gemini-3.6-flash",
                        "analysis": component,
                    },
                    {
                        "provider": "openrouter_luna_5_6",
                        "model": "openai/gpt-5.6-luna",
                        "analysis": component,
                    },
                    {
                        "provider": "openrouter_glm_5_2",
                        "model": "z-ai/glm-5.2",
                        "analysis": component,
                    },
                    {
                        "provider": "openrouter_claude_sonnet_5",
                        "model": "anthropic/claude-sonnet-5",
                        "analysis": component,
                    },
                ],
            }
        ]
    }

    analyses = _successful_analyses(council)

    assert [record["provider"] for record in analyses] == [
        "openrouter_gemini_3_6_flash",
        "openrouter_luna_5_6",
        "openrouter_glm_5_2",
        "openrouter_claude_sonnet_5",
        "openrouter_four_model_hybrid",
    ]

    evidence_policy = next(
        record
        for record in schedule_module.LANES
        if record["lane_id"] == "intelligence_evidence_evaluation"
    )
    evidence_contract = schedule_module.LANE_EVIDENCE_CONTRACTS[
        "intelligence_evidence_evaluation"
    ]
    evidence_command = _commands(REPO_ROOT)["intelligence_evidence_evaluation"]
    assert evidence_policy["network"] is False
    assert evidence_policy["timeout_seconds"] == 1_800
    assert evidence_contract["status_key"] == "evidence_status"
    assert evidence_contract["required_status"] == "evaluation_complete"
    assert evidence_command[1:3] == [
        "-m",
        "dopey.intelligence_research.run_cognitive_evidence_cycle",
    ]
    assert evidence_command[evidence_command.index("--visible-variants") + 1] == "16"


def _send(handle: TextIO, message: dict[str, Any]) -> None:
    handle.write(json.dumps(message, separators=(",", ":")) + "\n")
    handle.flush()


def _receive(handle: TextIO) -> dict[str, Any]:
    line = handle.readline()
    if not line:
        raise RuntimeError("MCP server closed stdout before returning a response")
    response = json.loads(line)
    if not isinstance(response, dict):
        raise TypeError(
            f"MCP response must be an object: actual={type(response).__name__}"
        )
    return response


def test_mcp_server_inspection_and_execution_gate() -> None:
    environment = os.environ.copy()
    environment["DOPEY_MCP_ALLOW_EXECUTE"] = "0"
    environment["DOPEY_MCP_ALLOW_FRONTIER"] = "0"
    process = subprocess.Popen(
        [str(PYTHON), "-m", "dopey_acceleration.mcp_server"],
        cwd=str(REPO_ROOT),
        env=environment,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("MCP smoke process did not expose STDIO pipes")
    try:
        _send(
            process.stdin,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1"},
                },
            },
        )
        initialized = _receive(process.stdout)
        assert initialized["result"]["protocolVersion"] == "2025-11-25"
        assert initialized["result"]["serverInfo"]["version"] == "0.6.0"

        _send(
            process.stdin,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )
        _send(
            process.stdin,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        listed = _receive(process.stdout)
        names = {tool["name"] for tool in listed["result"]["tools"]}
        assert "inspect_system_state" in names
        assert "run_frontier_analysis_council" in names
        frontier_tool = next(
            tool
            for tool in listed["result"]["tools"]
            if tool["name"] == "run_frontier_analysis_council"
        )
        providers_schema = frontier_tool["inputSchema"]["properties"]["providers"]
        provider_values = providers_schema["items"]["enum"]
        assert provider_values == ["openrouter_four_model_hybrid"]
        assert providers_schema["minItems"] == 1
        assert providers_schema["maxItems"] == 1
        assert {
            "openrouter_gemini_3_6_flash",
            "openrouter_luna_5_6",
            "openrouter_glm_5_2",
            "openrouter_claude_sonnet_5",
            "openrouter_gemini_3_5_flash",
            "openrouter_terra_5_6_pro",
        }.isdisjoint(provider_values)

        _send(
            process.stdin,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "inspect_compounding_research", "arguments": {}},
            },
        )
        inspected = _receive(process.stdout)
        assert inspected["result"]["isError"] is False
        assert inspected["result"]["structuredContent"]["live_blocked"] is True

        _send(
            process.stdin,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "run_research_cycle",
                    "arguments": {
                        "lane_ids": [],
                        "confirmation": "paper_research_only",
                    },
                },
            },
        )
        blocked = _receive(process.stdout)
        assert blocked["result"]["isError"] is True
        assert (
            "research execution is disabled" in blocked["result"]["content"][0]["text"]
        )
    finally:
        process.stdin.close()
        process.wait(timeout=20)
    assert process.returncode == 0


def test_schedule_uses_attempt_cadence_without_claiming_partial_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 13, 18, 0, tzinfo=timezone.utc)
    prior_attempt = now - timedelta(minutes=10)
    state_path = tmp_path / "schedule_state.json"
    plan_path = tmp_path / "schedule_plan.json"
    news_manifest_path = tmp_path / "news_context_manifest.json"
    state_path.write_text(
        json.dumps(
            {
                "last_attempt_utc": {"news_intake": prior_attempt.isoformat()},
                "last_success_utc": {"news_intake": prior_attempt.isoformat()},
                "lane_statuses": {"news_intake": {"status": "degraded_evidence"}},
            }
        ),
        encoding="utf-8",
    )
    news_manifest_path.write_text(
        json.dumps({"pipeline_status": "partial_explicit_source_failures"}),
        encoding="utf-8",
    )
    contracts = dict(schedule_module.LANE_EVIDENCE_CONTRACTS)
    contracts["news_intake"] = {
        "artifact_path": news_manifest_path,
        "status_key": "pipeline_status",
        "required_status": "complete",
    }
    monkeypatch.setattr(schedule_module, "SCHEDULE_STATE_PATH", state_path)
    monkeypatch.setattr(schedule_module, "SCHEDULE_PLAN_PATH", plan_path)
    monkeypatch.setattr(schedule_module, "LANE_EVIDENCE_CONTRACTS", contracts)

    plan = schedule_module.build_schedule_plan(
        schedule_module.REPO_ROOT, now, ("news_intake",)
    )
    lane = next(
        record for record in plan["lanes"] if record["lane_id"] == "news_intake"
    )

    assert lane["due"] is False
    assert lane["minutes_since_attempt"] == 10.0
    assert lane["minutes_since_success"] is None
    assert lane["last_verified_success_utc"] is None
    assert lane["last_run_status"] == "degraded_evidence"
    assert lane["evidence_verification"]["verification_status"] == "degraded_evidence"


def test_lane_evidence_requires_status_and_bounded_freshness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 13, 18, 0, tzinfo=timezone.utc)
    manifest_path = tmp_path / "news_context_manifest.json"
    contract = {
        "artifact_path": manifest_path,
        "status_key": "pipeline_status",
        "required_status": "complete",
        "timestamp_key": "created_at",
        "max_age_hours": 3.0,
    }
    contracts = dict(schedule_module.LANE_EVIDENCE_CONTRACTS)
    contracts["news_intake"] = contract
    monkeypatch.setattr(schedule_module, "LANE_EVIDENCE_CONTRACTS", contracts)
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_status": "complete",
                "created_at": (now - timedelta(hours=4)).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    stale = schedule_module.evaluate_lane_evidence_at("news_intake", now)

    assert stale["actual_status"] == "complete"
    assert stale["freshness_status"] == "stale"
    assert stale["verified_complete"] is False
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_status": "complete",
                "created_at": (now - timedelta(hours=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    fresh = schedule_module.evaluate_lane_evidence_at("news_intake", now)
    assert fresh["freshness_status"] == "fresh"
    assert fresh["verified_complete"] is True


def test_lane_attempt_start_is_persistable_before_work_begins() -> None:
    attempts, successes, statuses = _record_started_lane(
        {},
        {"news_intake": "2026-07-13T16:00:00+00:00"},
        {},
        "news_intake",
        "2026-07-13T18:00:00+00:00",
    )

    assert attempts["news_intake"] == "2026-07-13T18:00:00+00:00"
    assert successes["news_intake"] == "2026-07-13T16:00:00+00:00"
    assert statuses["news_intake"]["status"] == "attempt_started"
    assert statuses["news_intake"]["completed_utc"] == ""


def test_degraded_lane_outcome_preserves_prior_verified_success_and_inputs() -> None:
    last_attempt = {"news_intake": "2026-07-13T16:00:00+00:00"}
    last_success = {"news_intake": "2026-07-12T16:00:00+00:00"}
    lane_statuses: dict[str, dict[str, Any]] = {}
    evidence: schedule_module.LaneEvidenceStatus = {
        "verification_required": True,
        "verification_status": "degraded_evidence",
        "artifact_path": "news_context_manifest.json",
        "artifact_availability": "available",
        "status_key": "pipeline_status",
        "actual_status": "partial_explicit_source_failures",
        "required_status": "complete",
        "verified_complete": False,
    }

    updated_attempt, updated_success, updated_statuses, outcome = (
        _record_completed_lane(
            last_attempt,
            last_success,
            lane_statuses,
            "news_intake",
            "2026-07-13T18:00:00+00:00",
            evidence,
        )
    )

    assert outcome == "degraded_evidence"
    assert updated_attempt["news_intake"] == "2026-07-13T18:00:00+00:00"
    assert updated_success["news_intake"] == "2026-07-12T16:00:00+00:00"
    assert updated_statuses["news_intake"]["status"] == "degraded_evidence"
    assert last_attempt == {"news_intake": "2026-07-13T16:00:00+00:00"}
    assert last_success == {"news_intake": "2026-07-12T16:00:00+00:00"}
    assert lane_statuses == {}


def test_legacy_false_success_is_removed_once_then_verified_history_is_preserved() -> (
    None
):
    evidence: schedule_module.LaneEvidenceStatus = {
        "verification_required": True,
        "verification_status": "degraded_evidence",
        "artifact_path": "news_context_manifest.json",
        "artifact_availability": "available",
        "status_key": "pipeline_status",
        "actual_status": "partial_explicit_source_failures",
        "required_status": "complete",
        "verified_complete": False,
    }
    timestamp = "2026-07-13T18:00:00+00:00"
    legacy_state = {"last_success_utc": {"news_intake": timestamp}}

    legacy_attempt, legacy_success, legacy_statuses = _reconcile_evidence_state(
        legacy_state,
        {"news_intake": evidence},
    )

    assert legacy_attempt["news_intake"] == timestamp
    assert "news_intake" not in legacy_success
    assert legacy_statuses["news_intake"]["reconciled_from_legacy_state"] is True

    versioned_state = {
        "schedule_state_version": schedule_module.SCHEDULE_STATE_VERSION,
        "last_attempt_utc": {"news_intake": timestamp},
        "last_success_utc": {"news_intake": "2026-07-12T18:00:00+00:00"},
    }
    _, versioned_success, versioned_statuses = _reconcile_evidence_state(
        versioned_state,
        {"news_intake": evidence},
    )

    assert versioned_success["news_intake"] == "2026-07-12T18:00:00+00:00"
    assert versioned_statuses["news_intake"]["reconciled_from_legacy_state"] is False


@pytest.mark.parametrize("prior_status", ("failed", "degraded_evidence"))
def test_newer_verified_llm_artifact_reconciles_failed_schedule_state(
    tmp_path: Path,
    prior_status: str,
) -> None:
    failed_attempt = "2026-07-22T15:58:36.563362+00:00"
    prior_success = "2026-07-22T09:52:38.759870+00:00"
    recovered_completion = "2026-07-22T16:57:15.799862+00:00"
    artifact_path = tmp_path / "latest_cycle.json"
    artifact_path.write_text(
        json.dumps(
            {
                "cycle_status": "complete_analysis_current",
                "issued_at": recovered_completion,
            }
        ),
        encoding="utf-8",
    )
    evidence: schedule_module.LaneEvidenceStatus = {
        "verification_required": True,
        "verification_status": "verified_complete",
        "artifact_path": str(artifact_path),
        "artifact_availability": "available",
        "status_key": "cycle_status",
        "actual_status": "complete_analysis_current",
        "required_status": "complete_analysis_current",
        "verified_complete": True,
    }
    state = {
        "schedule_state_version": schedule_module.SCHEDULE_STATE_VERSION,
        "last_attempt_utc": {"llm_frontier_research": failed_attempt},
        "last_success_utc": {"llm_frontier_research": prior_success},
        "lane_statuses": {
            "llm_frontier_research": {
                "status": prior_status,
                "completed_utc": failed_attempt,
                "error": "prior failure",
            }
        },
    }

    attempts, successes, statuses = _reconcile_evidence_state(
        state,
        {"llm_frontier_research": evidence},
    )

    assert attempts["llm_frontier_research"] == recovered_completion
    assert successes["llm_frontier_research"] == recovered_completion
    recovered = statuses["llm_frontier_research"]
    assert recovered["status"] == "completed"
    assert recovered["completed_utc"] == recovered_completion
    assert recovered["error"] == ""
    assert recovered["reconciled_from_newer_verified_artifact"] is True
    assert recovered["reconciliation_source"] == {
        "artifact_path": str(artifact_path),
        "timestamp_key": "issued_at",
        "prior_status": prior_status,
        "prior_attempt_utc": failed_attempt,
    }
    assert state["lane_statuses"]["llm_frontier_research"]["status"] == prior_status


@pytest.mark.parametrize("prior_status", ("failed", "degraded_evidence", "completed"))
def test_newer_verified_playbook_artifact_reconciles_schedule_state(
    tmp_path: Path,
    prior_status: str,
) -> None:
    failed_attempt = "2026-07-22T19:05:02.611078+00:00"
    prior_success = "2026-07-22T15:57:47.588040+00:00"
    recovered_completion = "2026-07-22T19:20:09.712433+00:00"
    artifact_path = tmp_path / "playbook_refresh_result.json"
    artifact_path.write_text(
        json.dumps(
            {
                "refresh_status": "complete",
                "completed_utc": recovered_completion,
            }
        ),
        encoding="utf-8",
    )
    evidence: schedule_module.LaneEvidenceStatus = {
        "verification_required": True,
        "verification_status": "verified_complete",
        "artifact_path": str(artifact_path),
        "artifact_availability": "available",
        "status_key": "refresh_status",
        "actual_status": "complete",
        "required_status": "complete",
        "verified_complete": True,
    }
    state = {
        "schedule_state_version": schedule_module.SCHEDULE_STATE_VERSION,
        "last_attempt_utc": {"playbook_refresh": failed_attempt},
        "last_success_utc": {"playbook_refresh": prior_success},
        "lane_statuses": {
            "playbook_refresh": {
                "status": prior_status,
                "completed_utc": failed_attempt,
                "error": "prior failure",
            }
        },
    }

    attempts, successes, statuses = _reconcile_evidence_state(
        state,
        {"playbook_refresh": evidence},
    )

    assert attempts["playbook_refresh"] == recovered_completion
    assert successes["playbook_refresh"] == recovered_completion
    recovered = statuses["playbook_refresh"]
    assert recovered["status"] == "completed"
    assert recovered["completed_utc"] == recovered_completion
    assert recovered["error"] == ""
    assert recovered["reconciled_from_newer_verified_artifact"] is True
    assert recovered["reconciliation_source"] == {
        "artifact_path": str(artifact_path),
        "timestamp_key": "completed_utc",
        "prior_status": prior_status,
        "prior_attempt_utc": failed_attempt,
    }


def test_verified_artifact_recovery_does_not_touch_other_failed_lanes(
    tmp_path: Path,
) -> None:
    failed_attempt = "2026-07-22T15:58:36.563362+00:00"
    artifact_path = tmp_path / "news_context_manifest.json"
    artifact_path.write_text(
        json.dumps(
            {
                "pipeline_status": "complete",
                "issued_at": "2026-07-22T16:57:15.799862+00:00",
            }
        ),
        encoding="utf-8",
    )
    evidence: schedule_module.LaneEvidenceStatus = {
        "verification_required": True,
        "verification_status": "verified_complete",
        "artifact_path": str(artifact_path),
        "artifact_availability": "available",
        "status_key": "pipeline_status",
        "actual_status": "complete",
        "required_status": "complete",
        "verified_complete": True,
    }
    state = {
        "schedule_state_version": schedule_module.SCHEDULE_STATE_VERSION,
        "last_attempt_utc": {"news_intake": failed_attempt},
        "last_success_utc": {"news_intake": "2026-07-22T09:52:38.759870+00:00"},
        "lane_statuses": {
            "news_intake": {
                "status": "failed",
                "completed_utc": failed_attempt,
                "error": "preserve this failure",
            }
        },
    }

    attempts, successes, statuses = _reconcile_evidence_state(
        state,
        {"news_intake": evidence},
    )

    assert attempts["news_intake"] == failed_attempt
    assert successes["news_intake"] == "2026-07-22T09:52:38.759870+00:00"
    assert statuses["news_intake"] == state["lane_statuses"]["news_intake"]


def test_readiness_plan_removes_calendar_duration_bottleneck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs: dict[str, tuple[Path, dict[str, Any]]] = {
        "ACTION_GATE_PATH": (
            tmp_path / "action.json",
            {
                "forward_closed_trades": 4,
                "forward_closed_trades_required": 100,
                "checks": {},
            },
        ),
        "CONTEXT_GATE_PATH": (
            tmp_path / "context.json",
            {
                "joint_snapshot_day_count": 1,
                "minimum_snapshot_days": 60,
                "context_decision_ledger_count": 2,
                "context_outcome_ledger_count": 0,
                "minimum_resolved_decisions": 200,
            },
        ),
        "SWING_SUMMARY_PATH": (
            tmp_path / "swing.json",
            {"actionable_shadow_thesis_count": 2},
        ),
        "UNIVERSE_SUMMARY_PATH": (
            tmp_path / "universe.json",
            {"active_universe_size": 43},
        ),
        "NEWS_MANIFEST_PATH": (
            tmp_path / "news_manifest.json",
            {
                "pipeline_status": "complete",
                "source_coverage": {"required_coverage_complete": True},
                "source_statuses": [],
            },
        ),
    }
    for constant_name, (path, record) in inputs.items():
        path.write_text(json.dumps(record), encoding="utf-8")
        monkeypatch.setattr(readiness_module, constant_name, path)
    monkeypatch.setattr(readiness_module, "PLAN_PATH", tmp_path / "plan.json")

    plan = readiness_module.build_readiness_acceleration_plan(
        readiness_module.REPO_ROOT
    )
    bottleneck_ids = [str(record["bottleneck_id"]) for record in plan["bottlenecks"]]

    assert "point_in_time_context_days" not in bottleneck_ids
    assert bottleneck_ids[0] == "resolved_context_decisions"
    assert plan["context_snapshot_telemetry"]["calendar_duration_gate_enabled"] is False
    assert plan["removed_gate_ids"] == ["point_in_time_context_days"]
    assert plan["remaining_evidence_thresholds_lowered"] is False
    assert plan["intake_health"]["news_required_coverage_complete"] is True
