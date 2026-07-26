"""Fail-closed bridge from grounded coach reviews to quarantined research proposals."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Final, NotRequired, TypedDict

from dopey.protocols.identity import canonical_hash


COACH_BRIDGE_VERSION: Final[str] = "dopey-quarantined-coach-bridge-v1"
REFERENCE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\[\[((?:level|structure|lesson):[A-Za-z0-9:_\-]+)\]\]"
)
NUMERIC_LITERAL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9_])[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"(?:[eE][+-]?\d+)?(?:%|bps?)?(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
VALID_SESSION_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "complete_research_coaching",
        "complete_research_coaching_no_prior_lessons",
        "complete_research_coaching_abstained",
    }
)


class CoachBridgeContractError(RuntimeError):
    """Raised when a coach artifact cannot safely enter quarantine."""


class QuarantinedCoachProposal(TypedDict):
    proposal_id: str
    proposal_state: str
    source_session_id: str
    source_session_hash: str
    hypothesis_id: str
    hypothesis: dict[str, str]
    linked_experiment_ids: list[str]
    linked_experiments: list[dict[str, Any]]
    linked_risk_ids: list[str]
    evidence_refs: list[str]
    evidence_weight: float
    mutation_target_resolved: bool
    automatic_apply_allowed: bool
    strategy_mutation_allowed: bool
    code_mutation_allowed: bool
    prompt_mutation_allowed: bool
    broker_access: bool
    order_authority: bool
    live_blocked: bool
    strategy_promotion_allowed: bool
    paper_only: bool


class CoachSessionProjection(TypedDict):
    source_session_id: str
    source_session_hash: str
    generated_utc: str
    head_coach_id: str
    source_packet_hash: str
    source_model_input_hash: str
    source_replay_hash: str
    source_frozen_evidence_hash: str
    symbol: str
    timeframe: str
    decision_cutoff: str
    proposal_count: int
    linked_proposal_count: int
    blocked_proposal_count: int
    abstained: bool
    proposals: list[QuarantinedCoachProposal]
    orphan_experiments: list[dict[str, Any]]


class QuarantinedCoachProposalBatch(TypedDict):
    artifact_type: str
    schema_version: str
    batch_status: str
    outcome_status: str
    source_session_count: int
    proposal_count: int
    linked_proposal_count: int
    blocked_proposal_count: int
    orphan_experiment_count: int
    sessions: list[CoachSessionProjection]
    evidence_weight: float
    mutation_targets_resolved: int
    automatic_apply_allowed: bool
    strategy_mutation_allowed: bool
    code_mutation_allowed: bool
    prompt_mutation_allowed: bool
    broker_access: bool
    order_authority: bool
    strategy_promotion_allowed: bool
    paper_only: bool
    live_blocked: bool
    next_gate: str
    batch_hash: NotRequired[str]
    batch_id: NotRequired[str]


def _require_mapping(record: Mapping[str, Any], key: str, context: str) -> Mapping[str, Any]:
    value = record.get(key)
    if not isinstance(value, Mapping):
        raise CoachBridgeContractError(
            f"coach bridge requires an object: context={context}, field={key}, actual={type(value).__name__}"
        )
    return value


def _require_records(record: Mapping[str, Any], key: str, context: str) -> list[Mapping[str, Any]]:
    value = record.get(key)
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise CoachBridgeContractError(
            f"coach bridge requires an object array: context={context}, field={key}"
        )
    return list(value)


def _require_text(record: Mapping[str, Any], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CoachBridgeContractError(
            f"coach bridge requires non-empty text: context={context}, field={key}, value={value!r}"
        )
    return value.strip()


def _require_exact(record: Mapping[str, Any], key: str, expected: object, context: str) -> None:
    actual = record.get(key)
    if actual != expected:
        raise CoachBridgeContractError(
            f"coach bridge contract mismatch: context={context}, field={key}, "
            f"expected={expected!r}, actual={actual!r}"
        )


def _all_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for child in value.values() for text in _all_strings(child)]
    if isinstance(value, list):
        return [text for child in value for text in _all_strings(child)]
    return []


def _refs(value: object) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                reference
                for text in _all_strings(value)
                for reference in REFERENCE_PATTERN.findall(text)
            }
        )
    )


def _reference_occurrence_count(value: object) -> int:
    return sum(len(REFERENCE_PATTERN.findall(text)) for text in _all_strings(value))


def _validate_no_free_numeric_literals(value: object) -> None:
    for text in _all_strings(value):
        without_refs = REFERENCE_PATTERN.sub("", text)
        match = NUMERIC_LITERAL_PATTERN.search(without_refs)
        if match is not None:
            raise CoachBridgeContractError(
                "coach bridge rejected a free numeric literal: "
                f"literal={match.group(0)!r}, text={text!r}"
            )


def _validated_reference_registry(session: Mapping[str, Any]) -> frozenset[str]:
    evidence = _require_mapping(session, "evidence_coach", "session")
    structures = _require_records(evidence, "structure_registry", "evidence_coach")
    facts = _require_records(evidence, "numeric_fact_registry", "evidence_coach")
    lessons_record = _require_mapping(evidence, "prior_trade_lessons", "evidence_coach")
    lessons = _require_records(lessons_record, "lessons", "prior_trade_lessons")
    identifiers = [
        *(_require_text(record, "structure_id", "structure_registry") for record in structures),
        *(_require_text(record, "level_ref", "numeric_fact_registry") for record in facts),
        *(_require_text(record, "lesson_id", "prior_trade_lessons") for record in lessons),
    ]
    if len(set(identifiers)) != len(identifiers):
        raise CoachBridgeContractError("coach bridge reference registry contains duplicate identifiers")
    return frozenset(identifiers)


def _validate_boundaries(session: Mapping[str, Any]) -> None:
    authority = _require_mapping(session, "authority", "session")
    expected_authority: dict[str, object] = {
        "research_only": True,
        "paper_only": True,
        "live_blocked": True,
        "broker_access": False,
        "order_authority": False,
        "strategy_promotion_allowed": False,
        "parameter_mutation_allowed": False,
    }
    for key, expected in expected_authority.items():
        _require_exact(authority, key, expected, "authority")

    boundary = _require_mapping(session, "mutation_boundary", "session")
    expected_mutation: dict[str, object] = {
        "coach_suggestions_quarantined": True,
        "purged_walk_forward_required": True,
        "held_out_validation_required": True,
        "automatic_activation_allowed": False,
    }
    for key, expected in expected_mutation.items():
        _require_exact(boundary, key, expected, "mutation_boundary")

    option_boundary = _require_mapping(session, "option_claim_boundary", "session")
    _require_exact(
        option_boundary,
        "status",
        "blocked_missing_point_in_time_entry_and_exit_option_evidence",
        "option_claim_boundary",
    )
    _require_exact(
        option_boundary,
        "underlying_ohlcv_cannot_validate_option_pnl",
        True,
        "option_claim_boundary",
    )
    _require_exact(
        option_boundary,
        "zero_dte_weekly_option_outcome_claim_allowed",
        False,
        "option_claim_boundary",
    )


def _validate_replay(session: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    evidence = _require_mapping(session, "evidence_coach", "session")
    replay = _require_mapping(evidence, "blind_replay", "evidence_coach")
    frozen = _require_mapping(replay, "frozen_evidence", "blind_replay")
    for key, expected in {
        "future_data_visible_during_frozen_detection": False,
        "decision_inputs_exclude_reveal_window": True,
        "replay_outcome_separate_from_frozen_decision_packet": True,
        "not_trade_decision": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }.items():
        _require_exact(replay, key, expected, "blind_replay")
    for key, expected in {
        "not_trade_decision": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
        "viewport_is_detector_input": False,
        "image_pixels_are_detector_input": False,
        "raw_ohlcv_is_detector_input": True,
    }.items():
        _require_exact(frozen, key, expected, "frozen_evidence")
    for key in ("symbol", "timeframe"):
        if _require_text(replay, key, "blind_replay") != _require_text(frozen, key, "frozen_evidence"):
            raise CoachBridgeContractError(
                f"coach bridge replay identity mismatch: field={key}, "
                f"replay={replay.get(key)!r}, frozen={frozen.get(key)!r}"
            )
    return replay, frozen


def _validate_session(
    session: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], bool]:
    _require_exact(session, "artifact_type", "two_coach_chart_research_session", "session")
    _require_exact(session, "schema_version", "dopey-two-coach-chart-replay-v1", "session")
    status = _require_text(session, "status", "session")
    if status not in VALID_SESSION_STATUSES:
        raise CoachBridgeContractError(f"coach bridge rejected session status: status={status!r}")
    session_hash = _require_text(session, "session_hash", "session")
    unhashed = dict(session)
    unhashed.pop("session_hash", None)
    actual_hash = canonical_hash(unhashed)
    if actual_hash != session_hash:
        raise CoachBridgeContractError(
            f"coach bridge session hash mismatch: expected={session_hash}, actual={actual_hash}"
        )
    _validate_boundaries(session)
    replay, frozen = _validate_replay(session)

    topology = _require_mapping(session, "topology", "session")
    head_coach_id = _require_text(topology, "head_coach_id", "topology")
    if head_coach_id not in {"claude", "codex"}:
        raise CoachBridgeContractError(
            f"coach bridge requires Claude or Codex as head coach: head_coach_id={head_coach_id!r}"
        )
    _require_exact(topology, "runtime_fallback_allowed", False, "topology")

    head_coach = _require_mapping(session, "head_coach", "session")
    _require_exact(head_coach, "head_coach_id", head_coach_id, "head_coach")
    _require_exact(head_coach, "status", "completed_analysis_only", "head_coach")
    _require_exact(head_coach, "runtime_fallback_used", False, "head_coach")
    _require_exact(head_coach, "analysis_only", True, "head_coach")
    _require_exact(head_coach, "paper_only", True, "head_coach")
    _require_exact(head_coach, "live_blocked", True, "head_coach")
    _require_exact(head_coach, "model_input_reveal_values_visible", False, "head_coach")
    grounding = _require_mapping(head_coach, "grounding", "head_coach")
    _require_exact(grounding, "all_references_resolved", True, "grounding")
    _require_exact(grounding, "direct_model_authored_levels_allowed", False, "grounding")
    _require_exact(
        grounding,
        "numeric_grounding_status",
        "verified_no_free_numeric_literals",
        "grounding",
    )
    analysis = _require_mapping(head_coach, "structured_analysis", "head_coach")
    abstain = analysis.get("abstain")
    if not isinstance(abstain, bool):
        raise CoachBridgeContractError(
            "coach bridge requires a boolean abstention decision: "
            f"status={status!r}, actual={type(abstain).__name__}"
        )
    status_is_abstained = status == "complete_research_coaching_abstained"
    if abstain != status_is_abstained:
        raise CoachBridgeContractError(
            "coach bridge abstention decision conflicts with session status: "
            f"status={status!r}, abstain={abstain!r}"
        )
    registry = _validated_reference_registry(session)
    referenced_ids = _refs(analysis)
    unknown = sorted(set(referenced_ids) - registry)
    if unknown:
        raise CoachBridgeContractError(f"coach bridge found unknown evidence references: refs={unknown}")
    if list(grounding.get("referenced_ids", [])) != list(referenced_ids):
        raise CoachBridgeContractError("coach bridge grounding reference set does not match structured analysis")
    _require_exact(grounding, "unique_reference_count", len(referenced_ids), "grounding")
    _require_exact(
        grounding,
        "reference_count",
        _reference_occurrence_count(analysis),
        "grounding",
    )
    _validate_no_free_numeric_literals(analysis)
    return head_coach, replay, frozen, abstain


def _text_record(record: Mapping[str, Any], fields: Sequence[str], context: str) -> dict[str, str]:
    return {field: _require_text(record, field, context) for field in fields}


def _identified_record(prefix: str, record: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    body = dict(record)
    identity = f"{prefix}:{canonical_hash(body)[:24]}"
    return identity, body


def _session_projection(session: Mapping[str, Any]) -> CoachSessionProjection:
    head_coach, replay, frozen, abstained = _validate_session(session)
    analysis = _require_mapping(head_coach, "structured_analysis", "head_coach")
    hypotheses = _require_records(analysis, "hypotheses", "structured_analysis")
    experiments = _require_records(analysis, "recommended_experiments", "structured_analysis")
    risks = _require_records(analysis, "adversarial_findings", "structured_analysis")
    experiment_records: list[dict[str, Any]] = []
    for index, experiment in enumerate(experiments):
        body = _text_record(
            experiment,
            (
                "title",
                "objective",
                "falsification",
                "expected_information_gain",
                "safety_constraints",
            ),
            f"recommended_experiments[{index}]",
        )
        experiment_id, identified = _identified_record("coach-experiment", body)
        experiment_records.append(
            {
                "experiment_id": experiment_id,
                **identified,
                "evidence_refs": list(_refs(body)),
                "experiment_state": "QUARANTINED_UNVERIFIED",
            }
        )

    risk_records: list[dict[str, Any]] = []
    for index, risk in enumerate(risks):
        body = _text_record(
            risk,
            ("title", "risk", "evidence_needed"),
            f"adversarial_findings[{index}]",
        )
        risk_id, identified = _identified_record("coach-risk", body)
        risk_records.append({"risk_id": risk_id, **identified, "evidence_refs": list(_refs(body))})

    source_session_id = _require_text(session, "session_id", "session")
    source_session_hash = _require_text(session, "session_hash", "session")
    proposals: list[QuarantinedCoachProposal] = []
    linked_experiment_ids: set[str] = set()
    if not abstained:
        for index, hypothesis in enumerate(hypotheses):
            hypothesis_body = _text_record(
                hypothesis,
                ("title", "mechanism", "evidence_needed", "falsification"),
                f"hypotheses[{index}]",
            )
            hypothesis_id, identified_hypothesis = _identified_record(
                "coach-hypothesis",
                hypothesis_body,
            )
            hypothesis_refs = set(_refs(hypothesis_body))
            linked_experiments = [
                record
                for record in experiment_records
                if hypothesis_refs.intersection(record["evidence_refs"])
            ]
            linked_risks = [
                record
                for record in risk_records
                if hypothesis_refs.intersection(record["evidence_refs"])
            ]
            linked_ids = [str(record["experiment_id"]) for record in linked_experiments]
            linked_experiment_ids.update(linked_ids)
            state = "QUARANTINED" if linked_ids else "BLOCKED_MISSING_LINKED_EXPERIMENT"
            proposal_body = {
                "source_session_id": source_session_id,
                "source_session_hash": source_session_hash,
                "hypothesis_id": hypothesis_id,
                "linked_experiment_ids": linked_ids,
                "linked_risk_ids": [str(record["risk_id"]) for record in linked_risks],
                "evidence_refs": sorted(
                    hypothesis_refs.union(
                        reference
                        for record in linked_experiments
                        for reference in record["evidence_refs"]
                    )
                ),
                "proposal_state": state,
            }
            proposal_id = f"coach-proposal:{canonical_hash(proposal_body)[:24]}"
            proposals.append(
                {
                    "proposal_id": proposal_id,
                    "proposal_state": state,
                    "source_session_id": source_session_id,
                    "source_session_hash": source_session_hash,
                    "hypothesis_id": hypothesis_id,
                    "hypothesis": identified_hypothesis,
                    "linked_experiment_ids": linked_ids,
                    "linked_experiments": linked_experiments,
                    "linked_risk_ids": [str(record["risk_id"]) for record in linked_risks],
                    "evidence_refs": proposal_body["evidence_refs"],
                    "evidence_weight": 0.0,
                    "mutation_target_resolved": False,
                    "automatic_apply_allowed": False,
                    "strategy_mutation_allowed": False,
                    "code_mutation_allowed": False,
                    "prompt_mutation_allowed": False,
                    "broker_access": False,
                    "order_authority": False,
                    "live_blocked": True,
                    "strategy_promotion_allowed": False,
                    "paper_only": True,
                }
            )

    orphan_experiments = [
        {**record, "experiment_state": "BLOCKED_MISSING_LINKED_HYPOTHESIS"}
        for record in experiment_records
        if str(record["experiment_id"]) not in linked_experiment_ids
    ]
    linked_count = sum(record["proposal_state"] == "QUARANTINED" for record in proposals)
    return {
        "source_session_id": source_session_id,
        "source_session_hash": source_session_hash,
        "generated_utc": _require_text(session, "generated_utc", "session"),
        "head_coach_id": _require_text(head_coach, "head_coach_id", "head_coach"),
        "source_packet_hash": _require_text(
            _require_mapping(session, "evidence_coach", "session"),
            "packet_hash",
            "evidence_coach",
        ),
        "source_model_input_hash": _require_text(head_coach, "model_input_hash", "head_coach"),
        "source_replay_hash": _require_text(replay, "replay_hash", "blind_replay"),
        "source_frozen_evidence_hash": _require_text(frozen, "evidence_hash", "frozen_evidence"),
        "symbol": _require_text(replay, "symbol", "blind_replay"),
        "timeframe": _require_text(replay, "timeframe", "blind_replay"),
        "decision_cutoff": _require_text(replay, "decision_cutoff", "blind_replay"),
        "proposal_count": len(proposals),
        "linked_proposal_count": linked_count,
        "blocked_proposal_count": len(proposals) - linked_count,
        "abstained": abstained,
        "proposals": proposals,
        "orphan_experiments": orphan_experiments,
    }


def build_quarantined_coach_proposal_batch(
    sessions: Sequence[Mapping[str, Any]],
) -> QuarantinedCoachProposalBatch:
    """Validate and project coach sessions without resolving or applying a mutation."""

    projections = sorted(
        (_session_projection(session) for session in sessions),
        key=lambda record: (record["generated_utc"], record["source_session_hash"]),
    )
    session_hashes = [record["source_session_hash"] for record in projections]
    if len(set(session_hashes)) != len(session_hashes):
        raise CoachBridgeContractError("coach bridge input contains duplicate session hashes")
    proposal_count = sum(record["proposal_count"] for record in projections)
    linked_count = sum(record["linked_proposal_count"] for record in projections)
    blocked_count = sum(record["blocked_proposal_count"] for record in projections)
    orphan_count = sum(len(record["orphan_experiments"]) for record in projections)
    if linked_count:
        outcome_status = "complete_quarantined_proposals"
    elif proposal_count:
        outcome_status = "blocked_missing_linked_experiments"
    elif projections:
        outcome_status = "complete_no_actionable_coach_proposals"
    else:
        outcome_status = "complete_no_coach_sessions"
    body: QuarantinedCoachProposalBatch = {
        "artifact_type": "quarantined_coach_proposal_batch",
        "schema_version": COACH_BRIDGE_VERSION,
        "batch_status": "complete",
        "outcome_status": outcome_status,
        "source_session_count": len(projections),
        "proposal_count": proposal_count,
        "linked_proposal_count": linked_count,
        "blocked_proposal_count": blocked_count,
        "orphan_experiment_count": orphan_count,
        "sessions": projections,
        "evidence_weight": 0.0,
        "mutation_targets_resolved": 0,
        "automatic_apply_allowed": False,
        "strategy_mutation_allowed": False,
        "code_mutation_allowed": False,
        "prompt_mutation_allowed": False,
        "broker_access": False,
        "order_authority": False,
        "strategy_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "next_gate": "independent_experiment_then_purged_walk_forward_and_held_out_validation",
    }
    batch_hash = canonical_hash(body)
    return {
        **body,
        "batch_hash": batch_hash,
        "batch_id": f"coach-proposal-batch:{batch_hash[:24]}",
    }
