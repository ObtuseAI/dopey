"""Canonical contextual routing among promoted paper candidates and abstention."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

from .identity import JsonValue, parse_utc, require_sha256, require_utc_iso
from .promotion import (
    LEVELS,
    CanonicalAuditRunner,
    CanonicalCandidateIdentity,
    PromotionEvidence,
    _authenticated_stage_proofs,
    _assert_canonical_audit_snapshot_unchanged_with_runner,
    _canonical_audit_snapshot_hash,
    _candidate_proofs,
    _canonical_repository_root,
    _cumulative_promotion_gate_state,
    _external_root_audit_runner,
    _run_full_canonical_audit,
    canonical_candidate_identity,
    canonical_promotion_state,
    v1_promotion_policy,
)
from .retirement import (
    RETIREMENT_STATE_MAX_AGE_SECONDS,
    validate_canonical_retirement_artifact,
)


EvidenceLevel = Literal["L0", "L1", "L2", "L3", "L4", "L5"]
EVIDENCE_RANK = {level: index for index, level in enumerate(LEVELS)}
ROUTING_EVIDENCE_MAX_AGE_SECONDS = 3600.0
V1_PROSPECTIVE_ROUTING_MINIMUM_EVIDENCE_LEVEL: EvidenceLevel = "L4"


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    candidate_id: str
    frozen_specification_hash: str
    promotion_evidence_id: str
    routing_evidence_id: str
    retirement_evidence_id: str
    evidence_level: EvidenceLevel
    validated_contexts: frozenset[str]
    lower_bound_utility: float
    quote_gate_passed: bool
    risk_gate_passed: bool
    quarantined: bool


@dataclass(frozen=True, slots=True)
class RouteDecision:
    selected_candidate_id: str | None
    action: Literal["paper_candidate", "abstain"]
    reason_codes: tuple[str, ...]
    paper_only: bool
    live_blocked: bool


def _candidate_evidence(
    identity: CanonicalCandidateIdentity,
    evaluated_at: str,
) -> PromotionEvidence:
    return PromotionEvidence(
        identity.candidate_id,
        identity.candidate_author_id,
        "L0",
        "L1",
        identity.frozen_at,
        identity.frozen_specification_hash,
        evaluated_at,
    )


def _routing_artifact_matches(
    source: dict[str, JsonValue],
    candidate: RouteCandidate,
    context_id: str,
    candidate_mode: str,
) -> bool:
    contexts = source.get("validated_contexts")
    if (
        not isinstance(contexts, list)
        or any(not isinstance(item, str) or not item for item in contexts)
        or len(contexts) != len(set(contexts))
        or contexts != sorted(contexts)
    ):
        return False
    expected: dict[str, JsonValue] = {
        "promotion_evidence_id": candidate.promotion_evidence_id,
        "retirement_evidence_id": candidate.retirement_evidence_id,
        "candidate_mode": candidate_mode,
        "evidence_level": candidate.evidence_level,
        "validated_contexts": sorted(candidate.validated_contexts),
        "lower_bound_utility": candidate.lower_bound_utility,
        "quote_gate_passed": candidate.quote_gate_passed,
        "risk_gate_passed": candidate.risk_gate_passed,
        "quarantined": candidate.quarantined,
    }
    return (
        context_id in candidate.validated_contexts
        and all(source.get(key) == value for key, value in expected.items())
    )


def _canonical_route_candidate(
    repository_root: Path,
    candidate: RouteCandidate,
    context_id: str,
    evaluated_at: str,
    audit_result: dict[str, object],
    dynamic_state: dict[str, object],
) -> bool:
    require_sha256(candidate.frozen_specification_hash, "frozen_specification_hash")
    identity = canonical_candidate_identity(
        repository_root / "CANDIDATE_LINEAGE.jsonl",
        candidate.candidate_id,
    )
    if candidate.frozen_specification_hash != identity.frozen_specification_hash:
        return False
    selector = _candidate_evidence(identity, evaluated_at)
    proof_records, _ = _candidate_proofs(repository_root / "PROOF_LEDGER.jsonl", selector)
    promotion_state = canonical_promotion_state(
        proof_records,
        identity,
        evaluated_at,
        repository_root,
    )
    if (
        promotion_state.current_level != candidate.evidence_level
        or promotion_state.latest_transition_evidence_id != candidate.promotion_evidence_id
        or promotion_state.latest_transition_event_time is None
    ):
        return False
    cumulative_reasons, _, _, _ = _cumulative_promotion_gate_state(
        repository_root,
        identity,
        promotion_state.current_level,
        evaluated_at,
        audit_result,
        dynamic_state,
        v1_promotion_policy(),
    )
    if cumulative_reasons:
        return False
    routing_matching = tuple(
        record
        for record in proof_records
        if record.get("proof_type") == "routing_eligibility"
        and record.get("evidence_id") == candidate.routing_evidence_id
    )
    retirement_matching = tuple(
        record
        for record in proof_records
        if record.get("proof_type") == "retirement_state"
        and record.get("evidence_id") == candidate.retirement_evidence_id
    )
    if len(routing_matching) != 1 or len(retirement_matching) != 1:
        return False
    authenticated, reasons = _authenticated_stage_proofs(
        (*routing_matching, *retirement_matching),
        repository_root / "EXPERIMENT_REGISTRY.jsonl",
        selector,
        audit_result.get("external_anchor_verified") is True
        and dynamic_state.get("external_anchor_verified") is True,
        repository_root,
        frozenset({"routing_eligibility", "retirement_state"}),
    )
    if reasons or len(authenticated) != 2:
        return False
    authenticated_by_type = {
        str(record.get("proof_type")): record
        for record in authenticated
    }
    routing_record = authenticated_by_type.get("routing_eligibility")
    retirement_record = authenticated_by_type.get("retirement_state")
    if routing_record is None or retirement_record is None:
        return False
    routing_time = parse_utc(str(routing_record["event_time"]))
    retirement_time = parse_utc(str(retirement_record["event_time"]))
    evaluation_time = parse_utc(evaluated_at)
    promotion_time = parse_utc(promotion_state.latest_transition_event_time)
    if (
        routing_record.get("passed") is not True
        or retirement_record.get("passed") is not True
        or routing_time <= promotion_time
        or retirement_time <= promotion_time
        or retirement_time > routing_time
        or (evaluation_time - routing_time).total_seconds() > ROUTING_EVIDENCE_MAX_AGE_SECONDS
        or (evaluation_time - retirement_time).total_seconds()
        > RETIREMENT_STATE_MAX_AGE_SECONDS
    ):
        return False
    raw_routing_source = routing_record.get("source_artifact")
    raw_retirement_source = retirement_record.get("source_artifact")
    if not isinstance(raw_routing_source, dict) or not isinstance(
        raw_retirement_source,
        dict,
    ):
        return False
    retirement_decision = validate_canonical_retirement_artifact(
        cast(dict[str, JsonValue], raw_retirement_source),
        identity.candidate_id,
        identity.candidate_author_id,
        identity.frozen_specification_hash,
        candidate.retirement_evidence_id,
        str(retirement_record["event_time"]),
    )
    valid_until = raw_retirement_source.get("valid_until")
    if (
        retirement_decision.state != "CONTINUE_PAPER"
        or not isinstance(valid_until, str)
        or parse_utc(valid_until) < evaluation_time
        or candidate.quarantined
    ):
        return False
    return _routing_artifact_matches(
        cast(dict[str, JsonValue], raw_routing_source),
        candidate,
        context_id,
        identity.candidate_mode,
    )


def _route_validated_candidate_for_root(
    repository_root: Path,
    context_id: str,
    candidates: tuple[RouteCandidate, ...],
    minimum_evidence_level: EvidenceLevel,
    evaluated_at: str,
) -> RouteDecision:
    return _route_validated_candidate_for_root_with_audit_runner(
        repository_root,
        context_id,
        candidates,
        minimum_evidence_level,
        evaluated_at,
        _run_full_canonical_audit,
    )


def _route_validated_candidate_for_root_with_external_root(
    repository_root: Path,
    external_trust_root_path: Path,
    context_id: str,
    candidates: tuple[RouteCandidate, ...],
    minimum_evidence_level: EvidenceLevel,
    evaluated_at: str,
) -> RouteDecision:
    return _route_validated_candidate_for_root_with_audit_runner(
        repository_root,
        context_id,
        candidates,
        minimum_evidence_level,
        evaluated_at,
        _external_root_audit_runner(external_trust_root_path),
    )


def _route_validated_candidate_for_root_with_audit_runner(
    repository_root: Path,
    context_id: str,
    candidates: tuple[RouteCandidate, ...],
    minimum_evidence_level: EvidenceLevel,
    evaluated_at: str,
    audit_runner: CanonicalAuditRunner,
) -> RouteDecision:
    if not context_id:
        raise ValueError("router requires a context identity")
    if minimum_evidence_level not in EVIDENCE_RANK:
        raise ValueError("router minimum evidence level is invalid")
    effective_minimum_level = max(
        minimum_evidence_level,
        V1_PROSPECTIVE_ROUTING_MINIMUM_EVIDENCE_LEVEL,
        key=lambda level: EVIDENCE_RANK[level],
    )
    require_utc_iso(evaluated_at)
    if parse_utc(evaluated_at) > datetime.now(timezone.utc):
        raise ValueError("router evaluation timestamp cannot be future-dated")
    try:
        audit_result, audit_state = audit_runner(repository_root)
    except (OSError, ValueError):
        return RouteDecision(
            None,
            "abstain",
            ("canonical_audit_unavailable_or_invalid",),
            True,
            True,
        )
    audit_reasons: list[str] = []
    if (
        audit_result.get("certification_eligible") is not True
        or audit_state.get("certification_eligible") is not True
    ):
        audit_reasons.append("canonical_audit_certification_ineligible")
    if (
        audit_result.get("external_anchor_verified") is not True
        or audit_state.get("external_anchor_verified") is not True
    ):
        audit_reasons.append("external_dynamic_state_anchor_unverified")
    if audit_reasons:
        return RouteDecision(None, "abstain", tuple(audit_reasons), True, True)
    audit_snapshot_hash = _canonical_audit_snapshot_hash(audit_result, audit_state)
    seen_ids: set[str] = set()
    eligible: list[RouteCandidate] = []
    candidate_reasons: list[str] = []
    for candidate in candidates:
        if not candidate.candidate_id or candidate.candidate_id in seen_ids:
            candidate_reasons.append("router_candidate_identity_invalid")
            continue
        seen_ids.add(candidate.candidate_id)
        if not math.isfinite(candidate.lower_bound_utility):
            candidate_reasons.append(f"router_candidate_evidence_invalid:{candidate.candidate_id}")
            continue
        try:
            canonical = _canonical_route_candidate(
                repository_root,
                candidate,
                context_id,
                evaluated_at,
                audit_result,
                audit_state,
            )
        except (KeyError, OSError, TypeError, ValueError):
            canonical = False
        if not canonical:
            candidate_reasons.append(f"router_candidate_evidence_invalid:{candidate.candidate_id}")
            continue
        if (
            EVIDENCE_RANK[candidate.evidence_level] >= EVIDENCE_RANK[effective_minimum_level]
            and candidate.lower_bound_utility > 0.0
            and candidate.quote_gate_passed
            and candidate.risk_gate_passed
            and not candidate.quarantined
        ):
            eligible.append(candidate)
    try:
        _assert_canonical_audit_snapshot_unchanged_with_runner(
            repository_root,
            audit_snapshot_hash,
            audit_runner,
        )
    except (OSError, ValueError):
        return RouteDecision(
            None,
            "abstain",
            ("canonical_state_changed_during_routing",),
            True,
            True,
        )
    if candidate_reasons:
        return RouteDecision(
            None,
            "abstain",
            tuple(sorted(set(candidate_reasons))),
            True,
            True,
        )
    if not eligible:
        return RouteDecision(
            None,
            "abstain",
            ("no_validated_positive_lower_bound_candidate",),
            True,
            True,
        )
    selected = sorted(
        eligible,
        key=lambda item: (-item.lower_bound_utility, item.candidate_id),
    )[0]
    return RouteDecision(selected.candidate_id, "paper_candidate", (), True, True)


def route_validated_candidate(
    context_id: str,
    candidates: tuple[RouteCandidate, ...],
    minimum_evidence_level: EvidenceLevel,
    evaluated_at: str,
) -> RouteDecision:
    return _route_validated_candidate_for_root(
        _canonical_repository_root(),
        context_id,
        candidates,
        minimum_evidence_level,
        evaluated_at,
    )


def route_validated_candidate_with_external_root(
    external_trust_root_path: Path,
    context_id: str,
    candidates: tuple[RouteCandidate, ...],
    minimum_evidence_level: EvidenceLevel,
    evaluated_at: str,
) -> RouteDecision:
    return _route_validated_candidate_for_root_with_external_root(
        _canonical_repository_root(),
        external_trust_root_path,
        context_id,
        candidates,
        minimum_evidence_level,
        evaluated_at,
    )
