"""Aggregate advisory 0DTE replay feedback into optimizer evidence."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .run_zero_dte_outcome_replay import (
    ZERO_DTE_EXPIRY_MANAGEMENT_PATH,
    ZERO_DTE_REPLAY_OUTCOMES_PATH,
    ZERO_DTE_REPLAY_SUMMARY_PATH,
    ZERO_DTE_THRESHOLD_FEEDBACK_PATH,
)
from .run_zero_dte_risk_model import (
    ZERO_DTE_APPROVED_CANDIDATES_PATH,
    ZERO_DTE_BLOCKED_CANDIDATES_PATH,
    ZERO_DTE_RISK_DECISIONS_PATH,
    ZERO_DTE_RISK_THRESHOLDS_PATH,
)
from .zero_dte_risk_model import ZERO_DTE_OPEN_APPROVAL_DECISIONS
from .zero_dte_threshold_optimizer_models import (
    ZeroDTEThresholdFeedbackAggregate,
    stable_zero_dte_optimizer_hash,
    zero_dte_feedback_aggregate_hash,
)


APPROVED_FAILURE_OUTCOMES: frozenset[str] = frozenset({
    "approved_decayed",
    "approved_spiked_then_failed",
    "approved_should_have_been_throttled_more",
    "approved_expiry_managed_failure",
})

APPROVED_SUCCESS_OUTCOMES: frozenset[str] = frozenset({
    "approved_survived_fixture",
    "approved_special_close_helped",
    "approved_expiry_managed_success",
})


def build_zero_dte_threshold_feedback_aggregate() -> ZeroDTEThresholdFeedbackAggregate:
    feedback_records = _load_jsonl(ZERO_DTE_THRESHOLD_FEEDBACK_PATH)
    outcome_records = _load_jsonl(ZERO_DTE_REPLAY_OUTCOMES_PATH)
    risk_decisions = _load_jsonl(ZERO_DTE_RISK_DECISIONS_PATH)
    blocked_candidates = _load_jsonl(ZERO_DTE_BLOCKED_CANDIDATES_PATH)
    approved_candidates = _load_jsonl(ZERO_DTE_APPROVED_CANDIDATES_PATH)
    expiry_records = _load_jsonl(ZERO_DTE_EXPIRY_MANAGEMENT_PATH)
    replay_summary = _load_json(ZERO_DTE_REPLAY_SUMMARY_PATH)
    _load_json(ZERO_DTE_RISK_THRESHOLDS_PATH)
    if not feedback_records:
        raise ValueError(f"0DTE threshold optimizer requires non-empty feedback artifact: {ZERO_DTE_THRESHOLD_FEEDBACK_PATH}")
    if not outcome_records:
        raise ValueError(f"0DTE threshold optimizer requires non-empty replay outcomes artifact: {ZERO_DTE_REPLAY_OUTCOMES_PATH}")
    if not risk_decisions:
        raise ValueError(f"0DTE threshold optimizer requires non-empty risk decisions artifact: {ZERO_DTE_RISK_DECISIONS_PATH}")
    feedback_counts = Counter(
        recommendation
        for record in feedback_records
        for recommendation in _string_list(record.get("recommendations", []))
    )
    outcome_counts = Counter(str(record.get("outcome_type", "")) for record in outcome_records)
    reason_counts = Counter(
        reason
        for record in [*risk_decisions, *outcome_records]
        for reason in _string_list(record.get("reason_codes", record.get("blocked_reason_codes", [])))
    )
    source_hash = _file_hash(ZERO_DTE_REPLAY_SUMMARY_PATH)
    seed = {
        "source_replay_summary_hash": source_hash,
        "feedback_records_loaded": len(feedback_records),
        "outcomes_loaded": len(outcome_records),
        "approved_count": len(approved_candidates),
        "blocked_count": len(blocked_candidates),
        "throttled_count": sum(1 for record in risk_decisions if record.get("decision") == "approved_with_throttle"),
        "expiry_managed_count": len(expiry_records),
        "later_expiry_recommendation_count": int(feedback_counts.get("prefer_later_expiry_more_often", 0)),
        "feedback_counts_by_type": dict(sorted(feedback_counts.items())),
        "outcome_counts_by_type": dict(sorted(outcome_counts.items())),
        "reason_code_counts": dict(sorted(reason_counts.items())),
        "validated_blocks": _validated_blocks(outcome_records),
        "possible_overstrict_blocks": _possible_overstrict_blocks(outcome_records),
        "approved_failures": _outcomes_by_type(outcome_records, APPROVED_FAILURE_OUTCOMES),
        "approved_successes": _outcomes_by_type(outcome_records, APPROVED_SUCCESS_OUTCOMES),
        "throttle_validations": _outcomes_by_type(outcome_records, frozenset({"throttled_correctly"})),
        "replay_expectations_match": bool(replay_summary.get("all_expectations_matched", False)),
        "feedback_expectations_match": bool(replay_summary.get("all_feedback_expectations_matched", False)),
    }
    aggregate_id = f"zero-dte-threshold-feedback-aggregate-{stable_zero_dte_optimizer_hash(seed)[:12]}"
    draft = ZeroDTEThresholdFeedbackAggregate(
        aggregate_id=aggregate_id,
        source_replay_summary_hash=source_hash,
        feedback_records_loaded=len(feedback_records),
        outcomes_loaded=len(outcome_records),
        approved_count=len(approved_candidates),
        blocked_count=len(blocked_candidates),
        throttled_count=seed["throttled_count"],
        expiry_managed_count=len(expiry_records),
        later_expiry_recommendation_count=seed["later_expiry_recommendation_count"],
        feedback_counts_by_type=seed["feedback_counts_by_type"],
        outcome_counts_by_type=seed["outcome_counts_by_type"],
        reason_code_counts=seed["reason_code_counts"],
        validated_blocks=seed["validated_blocks"],
        possible_overstrict_blocks=seed["possible_overstrict_blocks"],
        approved_failures=seed["approved_failures"],
        approved_successes=seed["approved_successes"],
        throttle_validations=seed["throttle_validations"],
        paper_only=True,
        live_blocked=True,
        aggregate_hash="",
    )
    return ZeroDTEThresholdFeedbackAggregate(
        aggregate_id=draft.aggregate_id,
        source_replay_summary_hash=draft.source_replay_summary_hash,
        feedback_records_loaded=draft.feedback_records_loaded,
        outcomes_loaded=draft.outcomes_loaded,
        approved_count=draft.approved_count,
        blocked_count=draft.blocked_count,
        throttled_count=draft.throttled_count,
        expiry_managed_count=draft.expiry_managed_count,
        later_expiry_recommendation_count=draft.later_expiry_recommendation_count,
        feedback_counts_by_type=draft.feedback_counts_by_type,
        outcome_counts_by_type=draft.outcome_counts_by_type,
        reason_code_counts=draft.reason_code_counts,
        validated_blocks=draft.validated_blocks,
        possible_overstrict_blocks=draft.possible_overstrict_blocks,
        approved_failures=draft.approved_failures,
        approved_successes=draft.approved_successes,
        throttle_validations=draft.throttle_validations,
        paper_only=True,
        live_blocked=True,
        aggregate_hash=zero_dte_feedback_aggregate_hash(draft),
    )


def source_replay_summary_expectations_match() -> bool:
    replay_summary = _load_json(ZERO_DTE_REPLAY_SUMMARY_PATH)
    return bool(replay_summary.get("all_expectations_matched", False)) and bool(replay_summary.get("all_feedback_expectations_matched", False))


def _validated_blocks(outcome_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _compact_outcome(record)
        for record in outcome_records
        if record.get("outcome_type") == "blocked_correctly"
    ]


def _possible_overstrict_blocks(outcome_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _compact_outcome(record)
        for record in outcome_records
        if record.get("outcome_type") == "blocked_maybe_too_strict"
    ]


def _outcomes_by_type(outcome_records: list[dict[str, Any]], outcome_types: frozenset[str]) -> list[dict[str, Any]]:
    return [
        _compact_outcome(record)
        for record in outcome_records
        if str(record.get("outcome_type", "")) in outcome_types
    ]


def _compact_outcome(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "replay_id": str(record.get("replay_id", "")),
        "candidate_id": str(record.get("candidate_id", "")),
        "decision": str(record.get("decision", "")),
        "outcome_type": str(record.get("outcome_type", "")),
        "reason_codes": _string_list(record.get("blocked_reason_codes", [])),
        "threshold_feedback": _string_list(record.get("threshold_feedback", [])),
        "paper_only": True,
        "live_blocked": True,
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required 0DTE threshold optimizer source artifact missing: {path}")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError(f"required 0DTE source artifact must be JSON object: {path}")
    return parsed


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"required 0DTE threshold optimizer source artifact missing: {path}")
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise TypeError(f"required 0DTE source JSONL record must be object: {path}")
        records.append(parsed)
    return records


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def risk_decision_is_approved(record: dict[str, Any]) -> bool:
    return str(record.get("decision", "")) in ZERO_DTE_OPEN_APPROVAL_DECISIONS
