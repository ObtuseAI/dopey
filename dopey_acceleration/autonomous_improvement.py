"""Threshold-gated operational self-improvement for every research lane."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, cast

from dopey_research_pipeline.artifact_io import append_jsonl
from dopey.protocols.status_semantics import (
    OperationalStatusClass,
    classify_operational_status,
)

from .common import read_optional_json, stable_hash, stamped, write_json_atomic
from .reliability_guard import evaluate_reliability_guard
from .research_mutations import (
    ResearchMutationEvidence,
    activated_research_overrides,
    evaluate_research_mutation,
    propose_research_mutations,
)
from .schedule import (
    AUTONOMOUS_IMPROVEMENT_POLICY_VERSION,
    EXTERNAL_LANE_OWNERS,
    LANES,
    SCHEDULE_STATE_PATH,
    evaluate_lane_evidence,
)


IMPROVEMENT_VERSION: Final[str] = AUTONOMOUS_IMPROVEMENT_POLICY_VERSION
POLICY_HISTORY_DIRECTORY_NAME: Final[str] = "history"
POLICY_TRANSITION_LEDGER_NAME: Final[str] = "policy_transitions.jsonl"
POLICY_COMMIT_MARKER_NAME: Final[str] = "active_commit.json"
SEALED_OVERRIDE_FIELDS: Final[frozenset[str]] = frozenset(
    {"interval_minutes", "timeout_seconds", "retries"}
)
PAID_SINGLE_ATTEMPT_LANES: Final[frozenset[str]] = frozenset(
    {"coached_evolution_cycle", "llm_frontier_research"}
)
SAFE_INTERVAL_FLOORS: Final[dict[str, int]] = {
    "context_outcome_settlement": 120,
    "equity_swing_engine": 120,
    "symbol_intelligence_lab": 720,
    "vnext_forward_settlement": 120,
    "autonomous_strategy_research": 180,
    "coached_evolution_cycle": 240,
    "coach_proposal_quarantine": 180,
    "autonomous_threshold_audit": 180,
    "strategy_engineering_research": 180,
    "playbook_refresh": 180,
    "evidence_intelligence": 180,
    "autonomous_promotion_evidence_synthesis": 180,
    "autonomous_promotion_evaluation": 180,
    "autonomous_self_improvement": 240,
    "llm_frontier_research": 360,
    "intelligence_discovery_research": 240,
    "intelligence_evidence_evaluation": 240,
}


def _mapping(record: dict[str, Any], key: str) -> dict[str, Any]:
    value = record.get(key)
    return (
        {str(item_key): item_value for item_key, item_value in value.items()}
        if isinstance(value, dict)
        else {}
    )


def _status_for_lane(lane_statuses: dict[str, Any], lane_id: str) -> str:
    value = lane_statuses.get(lane_id)
    if isinstance(value, dict):
        return str(value.get("status", "unknown"))
    return "unknown"


def _reliability_guard(
    repo_root: Path,
    issued_at: datetime,
) -> dict[str, Any]:
    return evaluate_reliability_guard(repo_root, issued_at)


def _operational_override(
    lane: dict[str, Any],
    last_status: str,
    cadence_acceleration_allowed: bool,
) -> tuple[dict[str, int], list[str]]:
    lane_id = str(lane["lane_id"])
    status_assessment = classify_operational_status(last_status)
    override: dict[str, int] = {}
    reasons: list[str] = []
    floor = SAFE_INTERVAL_FLOORS.get(lane_id)
    if (
        cadence_acceleration_allowed
        and floor is not None
        and int(lane["interval_minutes"]) > floor
    ):
        override["interval_minutes"] = floor
        reasons.append("evidence_velocity_safe_floor")
    if status_assessment["status_class"] is OperationalStatusClass.FAILED:
        base_timeout = int(lane["timeout_seconds"])
        override["timeout_seconds"] = min(
            base_timeout * 2, max(base_timeout + 60, round(base_timeout * 1.5))
        )
        reasons.append("bounded_timeout_recovery")
    if (
        bool(lane["network"])
        and lane_id not in PAID_SINGLE_ATTEMPT_LANES
        and status_assessment["retry_candidate"]
    ):
        base_retries = int(lane["retries"])
        if base_retries < 3:
            override["retries"] = base_retries + 1
            reasons.append("bounded_transient_network_retry")
    return override, reasons


def _policy_integrity(
    policy: dict[str, Any],
    availability: str,
) -> tuple[str, str]:
    if availability != "available":
        return "not_available", ""
    claimed_hash = policy.get("reproducibility_hash")
    if not isinstance(claimed_hash, str) or not claimed_hash:
        return "unverified_missing_hash", ""
    unhashed = dict(policy)
    unhashed.pop("reproducibility_hash", None)
    if stable_hash(unhashed) != claimed_hash:
        return "unverified_hash_mismatch", ""
    return "verified", claimed_hash


def _lane_overrides(policy: dict[str, Any]) -> dict[str, dict[str, int]]:
    raw = policy.get("lane_overrides")
    if not isinstance(raw, dict):
        return {}
    return {
        str(lane_id): {
            str(field): int(value)
            for field, value in override.items()
            if str(field) in SEALED_OVERRIDE_FIELDS
            and isinstance(value, int)
            and not isinstance(value, bool)
        }
        for lane_id, override in raw.items()
        if isinstance(override, dict)
    }


def _override_delta(
    previous: dict[str, dict[str, int]],
    current: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    delta: list[dict[str, Any]] = []
    for lane_id in sorted(set(previous) | set(current)):
        before = previous.get(lane_id, {})
        after = current.get(lane_id, {})
        for field in sorted(set(before) | set(after)):
            previous_value = before.get(field)
            current_value = after.get(field)
            if previous_value == current_value:
                continue
            if current_value is None:
                change_type = "rolled_back_to_baseline"
            elif previous_value is None:
                change_type = "activated"
            else:
                change_type = "updated"
            delta.append(
                {
                    "lane_id": lane_id,
                    "field": field,
                    "previous_value": previous_value,
                    "current_value": current_value,
                    "change_type": change_type,
                }
            )
    return delta


def _write_immutable_json(path: Path, record: dict[str, Any]) -> None:
    if path.exists():
        existing, availability = read_optional_json(path)
        if availability != "available" or existing != record:
            raise FileExistsError(
                "autonomous improvement history path already contains different evidence: "
                f"path={path}"
            )
        return
    write_json_atomic(path, record)


def _research_mutation_evidence(
    output_root: Path,
) -> tuple[dict[str, ResearchMutationEvidence], str]:
    path = output_root / "research_mutation_evidence.json"
    artifact, availability = read_optional_json(path)
    raw_records = artifact.get("records", [])
    if not isinstance(raw_records, list):
        raise TypeError(
            f"research mutation evidence records must be an array: path={path}"
        )
    records: dict[str, ResearchMutationEvidence] = {}
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, dict):
            raise TypeError(
                "research mutation evidence record must be an object: "
                f"path={path}, index={index}"
            )
        proposal_id = raw_record.get("proposal_id")
        invariant_violations = raw_record.get("invariant_violations")
        if (
            not isinstance(proposal_id, str)
            or not proposal_id
            or not isinstance(invariant_violations, list)
            or not all(
                isinstance(value, str) for value in invariant_violations
            )
        ):
            raise ValueError(
                "research mutation evidence identity or invariants are invalid: "
                f"path={path}, index={index}"
            )
        evidence = cast(
            ResearchMutationEvidence,
            {
                "proposal_id": proposal_id,
                "sample_count": int(raw_record["sample_count"]),
                "effect_interval_lower": float(
                    raw_record["effect_interval_lower"]
                ),
                "cost_ratio": float(raw_record["cost_ratio"]),
                "evaluator_independent": raw_record.get(
                    "evaluator_independent"
                )
                is True,
                "deterministic": raw_record.get("deterministic") is True,
                "invariant_violations": tuple(invariant_violations),
            },
        )
        records[proposal_id] = evidence
    return records, availability


def run_autonomous_improvement_cycle(
    repo_root: Path,
    output_root: Path,
    issued_at: datetime,
) -> dict[str, Any]:
    if issued_at.tzinfo is None:
        raise ValueError("autonomous improvement issued_at must be timezone-aware")
    schedule_state, schedule_state_availability = read_optional_json(
        SCHEDULE_STATE_PATH
    )
    reliability_guard = _reliability_guard(repo_root, issued_at)
    cadence_acceleration_allowed = bool(
        reliability_guard["cadence_acceleration_allowed"]
    )
    active_policy_path = output_root / "active_policy.json"
    previous_policy, previous_policy_availability = read_optional_json(
        active_policy_path
    )
    previous_policy_integrity, previous_policy_hash = _policy_integrity(
        previous_policy,
        previous_policy_availability,
    )
    if previous_policy_integrity.startswith("unverified_"):
        cadence_acceleration_allowed = False
        reliability_guard = {
            **reliability_guard,
            "guard_status": "blocked_unverified_previous_policy",
            "cadence_acceleration_allowed": False,
            "detail": (
                "previous autonomous policy cannot be trusted for a new cadence "
                f"transition: integrity={previous_policy_integrity}"
            ),
        }
    lane_statuses = _mapping(schedule_state, "lane_statuses")
    mutation_evidence, mutation_evidence_availability = (
        _research_mutation_evidence(output_root)
    )
    research_mutation_proposals = propose_research_mutations(lane_statuses)
    research_mutation_decisions = tuple(
        evaluate_research_mutation(
            proposal,
            mutation_evidence.get(proposal["proposal_id"]),
        )
        for proposal in research_mutation_proposals
    )
    research_overrides = activated_research_overrides(
        research_mutation_decisions
    )
    coverage: list[dict[str, Any]] = []
    overrides: dict[str, dict[str, int]] = {}
    for lane in LANES:
        lane_id = str(lane["lane_id"])
        last_status = _status_for_lane(lane_statuses, lane_id)
        evidence = evaluate_lane_evidence(lane_id)
        external_owner = EXTERNAL_LANE_OWNERS.get(lane_id)
        self_improvement_enabled = external_owner is None
        override, reasons = (
            _operational_override(
                lane,
                last_status,
                cadence_acceleration_allowed,
            )
            if self_improvement_enabled
            else ({}, [])
        )
        if override:
            overrides[lane_id] = override
        coverage.append(
            {
                "lane_id": lane_id,
                "last_status": last_status,
                "evidence_verification": evidence["verification_status"],
                "self_improvement_enabled": self_improvement_enabled,
                "execution_owner": external_owner or "dopey_acceleration_cycle",
                "self_improvement_exclusion_reason": (
                    "" if self_improvement_enabled else "externally_owned_lane"
                ),
                "operational_mutation_surface": [
                    "interval_minutes_within_sealed_floor",
                    "timeout_seconds_tight_bounded_expansion",
                    "network_retries_maximum_three",
                ],
                "research_mutation_surface": [
                    "hypothesis_generation",
                    "adversarial_review",
                    "experiment_ranking",
                    "shadow_candidate_generation",
                    "automatic_abstention",
                ],
                "automatic_override": override,
                "override_reasons": reasons,
                "human_approval_required_for_safe_paper_research": False,
            }
        )
    self_improvable_lane_count = sum(
        1 for record in coverage if record["self_improvement_enabled"] is True
    )
    previous_overrides = (
        _lane_overrides(previous_policy)
        if previous_policy_integrity == "verified"
        else {}
    )
    delta = _override_delta(previous_overrides, overrides)
    activated = [
        record for record in delta if record["change_type"] in {"activated", "updated"}
    ]
    rolled_back = [
        record for record in delta if record["change_type"] == "rolled_back_to_baseline"
    ]
    reliability_interval_rollbacks = sorted(
        {
            str(record["lane_id"])
            for record in rolled_back
            if record["field"] == "interval_minutes"
            and not cadence_acceleration_allowed
        }
    )
    external_lane_rollbacks = sorted(
        {
            str(record["lane_id"])
            for record in rolled_back
            if str(record["lane_id"]) in EXTERNAL_LANE_OWNERS
        }
    )
    if previous_policy_integrity == "not_available":
        transition_type = "initial_activation"
    elif reliability_interval_rollbacks:
        transition_type = "reliability_guard_rollback"
    elif delta:
        transition_type = "policy_updated"
    else:
        transition_type = "policy_unchanged"
    issued_at_text = issued_at.astimezone(timezone.utc).isoformat()
    activation_cycle_id = stable_hash(
        {
            "issued_at": issued_at_text,
            "previous_policy_hash": previous_policy_hash,
            "lane_overrides": overrides,
            "research_overrides": research_overrides,
            "research_mutation_proposals": list(research_mutation_proposals),
            "research_mutation_decisions": list(research_mutation_decisions),
            "research_mutation_evidence_availability": (
                mutation_evidence_availability
            ),
            "research_mutation_activation_count": len(research_overrides),
            "transition_type": transition_type,
        }
    )[:24]
    history_identifier = (
        issued_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        + "-"
        + activation_cycle_id
    )
    history_path = (
        output_root / POLICY_HISTORY_DIRECTORY_NAME / f"{history_identifier}.json"
    )
    commit_marker_path = output_root / POLICY_COMMIT_MARKER_NAME
    active_policy = stamped(
        {
            "artifact_type": "autonomous_improvement_active_policy",
            "policy_version": IMPROVEMENT_VERSION,
            "policy_status": "active_threshold_gated",
            "issued_at": issued_at_text,
            "activation_cycle_id": activation_cycle_id,
            "policy_history_path": str(history_path),
            "activation_commit_marker_path": str(commit_marker_path),
            "activation_commit_protocol": (
                "history_transition_latest_then_active_pointer"
            ),
            "lane_overrides": overrides,
            "schedule_lane_count": len(LANES),
            "covered_lane_count": self_improvable_lane_count,
            "excluded_external_lane_count": len(LANES) - self_improvable_lane_count,
            "all_schedule_lanes_covered": False,
            "all_owned_schedule_lanes_covered": self_improvable_lane_count
            + len(EXTERNAL_LANE_OWNERS)
            == len(LANES),
            "reliability_guard": reliability_guard,
            "previous_policy_hash": previous_policy_hash,
            "previous_policy_integrity": previous_policy_integrity,
            "transition_type": transition_type,
            "policy_delta_count": len(delta),
            "automatic_activation_count": len(activated),
            "automatic_rollback_count": len(rolled_back),
            "reliability_interval_rollback_lane_ids": reliability_interval_rollbacks,
            "external_lane_rollback_lane_ids": external_lane_rollbacks,
            "sealed_override_fields": sorted(SEALED_OVERRIDE_FIELDS),
            "evidence_thresholds_lowered": False,
            "readiness_rules_mutable": False,
            "truth_rules_mutable": False,
            "provenance_rules_mutable": False,
            "execution_rules_mutable": False,
            "promotion_beyond_paper_shadow_allowed": False,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    transition = stamped(
        {
            "artifact_type": "autonomous_improvement_policy_transition",
            "transition_version": IMPROVEMENT_VERSION,
            "issued_at": issued_at_text,
            "activation_cycle_id": activation_cycle_id,
            "transition_type": transition_type,
            "previous_policy_hash": previous_policy_hash,
            "previous_policy_integrity": previous_policy_integrity,
            "active_policy_hash": active_policy["reproducibility_hash"],
            "policy_delta": delta,
            "research_overrides": research_overrides,
            "research_mutation_activation_count": len(research_overrides),
            "automatic_activation_count": len(activated),
            "automatic_rollback_count": len(rolled_back),
            "reliability_interval_rollback_lane_ids": reliability_interval_rollbacks,
            "external_lane_rollback_lane_ids": external_lane_rollbacks,
            "reliability_guard": reliability_guard,
            "history_path": str(history_path),
            "paper_only": True,
            "live_blocked": True,
        }
    )
    result = stamped(
        {
            "artifact_type": "autonomous_self_improvement_cycle",
            "cycle_version": IMPROVEMENT_VERSION,
            "cycle_status": "prepared_pending_activation_commit",
            "issued_at": issued_at_text,
            "activation_cycle_id": activation_cycle_id,
            "schedule_state_availability": schedule_state_availability,
            "schedule_lane_count": len(LANES),
            "covered_lane_count": self_improvable_lane_count,
            "excluded_external_lane_count": len(LANES) - self_improvable_lane_count,
            "lane_override_count": len(overrides),
            "research_mutation_proposal_count": len(
                research_mutation_proposals
            ),
            "research_mutation_activation_count": len(research_overrides),
            "research_mutation_proposals": list(research_mutation_proposals),
            "research_mutation_decisions": list(research_mutation_decisions),
            "research_overrides": research_overrides,
            "all_schedule_lanes_self_improvable": False,
            "all_owned_schedule_lanes_self_improvable": self_improvable_lane_count
            + len(EXTERNAL_LANE_OWNERS)
            == len(LANES),
            "lane_coverage": coverage,
            "active_policy_path": str(active_policy_path),
            "active_policy_hash": active_policy["reproducibility_hash"],
            "previous_policy_hash": previous_policy_hash,
            "previous_policy_integrity": previous_policy_integrity,
            "policy_transition": transition,
            "policy_history_path": str(history_path),
            "policy_transition_ledger_path": str(
                output_root / POLICY_TRANSITION_LEDGER_NAME
            ),
            "activation_commit_marker_path": str(commit_marker_path),
            "reliability_guard": reliability_guard,
            "zero_human_bottleneck_scope": "safe_paper_research_and_shadow_evaluation_only",
            "human_approval_retained_for": [
                "live_capital",
                "broker_or_credential_authority_expansion",
                "constitutional_rule_changes",
                "promotion_beyond_paper_shadow",
            ],
            "automatic_activation_count": len(activated),
            "automatic_rollback_count": len(rolled_back),
            "reliability_interval_rollback_lane_ids": reliability_interval_rollbacks,
            "external_lane_rollback_lane_ids": external_lane_rollbacks,
            "sealed_override_fields": sorted(SEALED_OVERRIDE_FIELDS),
            "evidence_thresholds_lowered": False,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    history = stamped(
        {
            "artifact_type": "autonomous_improvement_cycle_history",
            "history_version": IMPROVEMENT_VERSION,
            "issued_at": issued_at_text,
            "activation_cycle_id": activation_cycle_id,
            "active_policy": active_policy,
            "policy_transition": transition,
            "cycle_result": result,
            "immutable_history": True,
            "paper_only": True,
            "live_blocked": True,
        }
    )
    commit_marker = stamped(
        {
            "artifact_type": "autonomous_improvement_activation_commit",
            "commit_version": IMPROVEMENT_VERSION,
            "activation_cycle_id": activation_cycle_id,
            "committed_at_utc": issued_at_text,
            "active_policy_hash": active_policy["reproducibility_hash"],
            "history_hash": history["reproducibility_hash"],
            "transition_hash": transition["reproducibility_hash"],
            "prepared_cycle_result_hash": result["reproducibility_hash"],
            "active_policy_path": str(active_policy_path),
            "history_path": str(history_path),
            "paper_only": True,
            "live_blocked": True,
        }
    )
    _write_immutable_json(history_path, history)
    append_jsonl(output_root / POLICY_TRANSITION_LEDGER_NAME, transition)
    write_json_atomic(output_root / "latest_cycle.json", result)
    write_json_atomic(active_policy_path, active_policy)
    write_json_atomic(commit_marker_path, commit_marker)
    committed_result_payload = dict(result)
    committed_result_payload.pop("reproducibility_hash", None)
    committed_result_payload["cycle_status"] = "complete"
    committed_result_payload["activation_status"] = "activation_committed"
    committed_result_payload["activation_commit"] = commit_marker
    committed_result = stamped(committed_result_payload)
    write_json_atomic(output_root / "latest_cycle.json", committed_result)
    return committed_result
