"""Sequential L0-L5 promotion derived only from protected evidence ledgers."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Literal, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from sealed_evaluator_client.aggregate_contract import ALLOWED_FAILURE_CODES
from sealed_evaluator_client.budget import PROHIBITED_REQUEST_TERMS
from sealed_evaluator_client.signatures import verify_sealed_response_signature

from .identity import JsonValue, canonical_hash, parse_utc, require_sha256, require_utc_iso
from .contracts import candidate_genome_from_mapping
from .forward_signatures import verify_forward_evidence_signature
from .ledger import append_canonical_ascendancy_record, verify_hash_chained_ledger
from .negative_controls import NegativeControlResult, evaluate_negative_controls
from .policy_ids import V1_REQUIRED_NEGATIVE_CONTROL_IDS
from .stress import RequiredStressEvidence, evaluate_required_stress_evidence
from .tickets import (
    PaperExecutionTicket,
    abstention_record_from_mapping,
    paper_fill_observation_from_mapping,
    paper_execution_ticket_from_mapping,
)
from verifier.protected_manifest import ASCENDANCY_DYNAMIC_STATE_PATHS, file_sha256


EvidenceLevel = Literal["L0", "L1", "L2", "L3", "L4", "L5"]
CandidateMode = Literal["options_expression", "abstention_policy"]
CanonicalAuditResult = tuple[dict[str, object], dict[str, object]]
CanonicalAuditRunner = Callable[[Path], CanonicalAuditResult]
LEVELS: tuple[EvidenceLevel, ...] = ("L0", "L1", "L2", "L3", "L4", "L5")
FORWARD_EVIDENCE_KIND = "prospective_paper"
PROSPECTIVE_PROFITABILITY_EVIDENCE_CLASS = "prospective_market_evidence"
FORWARD_INPUT_VALIDATION_STATUS = "independently_validated_point_in_time_inputs"
FORWARD_MEMBERSHIP_VALIDATION_STATUS = (
    "independently_validated_point_in_time_membership"
)
FORWARD_SUCCESS_DEFINITION = (
    "net_utility_strictly_positive_after_complete_costs"
)
FORWARD_OUTCOME_UNIT = "net_utility_fraction_of_paper_bankroll_after_complete_costs"
FORWARD_MISSED_FILL_UTILITY_POLICY = "missed_fill_candidate_net_utility_equals_zero"
SESSION_CLUSTER_T_CRITICAL = 2.093
OPTIONS_BASELINE_IDS = frozenset(
    {"no_trade", "risk_matched_underlying", "simple_option_or_vertical"}
)
ABSTENTION_BASELINE_IDS = frozenset(
    {"no_trade", "always_express", "random_abstention"}
)
ENVIRONMENT_ID = "dopey-options-paper-v1"
STAGE_EVALUATOR_VERSION = "ascendancy-stage-proof-v1"
STAGE_AUTHENTICATION_METHOD = "ed25519_promotion_authority_receipt_v1"
PROMOTION_GOVERNOR_ID = "dopey-promotion-governor-v1"
PROMOTION_AUTHORITY_TRUST_FILE = "PROMOTION_AUTHORITY_TRUST.json"
STAGE_EVALUATOR_IDS = MappingProxyType(
    {
        "development": "ascendancy-development-evaluator-v1",
        "negative_control": "ascendancy-negative-control-evaluator-v1",
        "stress_matrix": "ascendancy-stress-matrix-evaluator-v1",
        "clean_room_replication": "ascendancy-clean-room-replicator-v1",
        "routing_eligibility": "ascendancy-routing-evaluator-v1",
        "retirement_state": "ascendancy-retirement-evaluator-v1",
    }
)
RED_TEAM_EVALUATOR_IDS = MappingProxyType(
    {
        domain: f"ascendancy-red-team-{domain}-v1"
        for domain in ("leakage", "economic", "statistical", "tail", "implementation", "behavioral")
    }
)
EXTERNAL_PINNED_ROLE_IDS = frozenset(
    {
        "dynamic_anchor_authority",
        "promotion_authority",
        "sealed_evaluator",
        "forward_recorder",
        "outcome_source",
    }
)
AUTHENTICATED_STAGE_PROOF_TYPES = frozenset(
    {
        "development",
        "negative_control",
        "stress_matrix",
        "red_team",
        "clean_room_replication",
    }
)
PROMOTION_DECISION_ARTIFACT_FIELDS = frozenset(
    {
        "artifact_type",
        "schema_version",
        "candidate_id",
        "candidate_author_id",
        "candidate_mode",
        "frozen_specification_hash",
        "from_level",
        "to_level",
        "allowed",
        "reason_codes",
        "evaluated_at",
        "trial_registry_hash",
        "experiment_registry_record_count",
        "proof_registry_hash_before",
        "proof_registry_record_count_before",
        "dynamic_state_hash",
        "audit_snapshot_hash",
        "paper_only",
        "live_blocked",
    }
)
SIGNED_STAGE_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "environment_id",
        "authority_id",
        "authority_version",
        "evidence_id",
        "proof_type",
        "review_domain",
        "candidate_id",
        "candidate_author_id",
        "frozen_specification_hash",
        "experiment_id",
        "evaluator_id",
        "evaluator_version",
        "passed",
        "source_artifact_hash",
        "issued_at",
        "paper_only",
        "live_blocked",
    }
)
PROMOTION_AUTHORITY_TRUST_FIELDS = frozenset(
    {
        "schema_version",
        "environment_id",
        "status",
        "algorithm",
        "authority_id",
        "authority_version",
        "key_id",
        "public_key_base64",
    }
)


@dataclass(frozen=True, slots=True)
class CanonicalCandidateIdentity:
    candidate_id: str
    candidate_author_id: str
    frozen_at: str
    frozen_specification_hash: str
    frozen_specification: dict[str, JsonValue]
    candidate_mode: CandidateMode


@dataclass(frozen=True, slots=True)
class CanonicalPromotionState:
    current_level: EvidenceLevel
    latest_transition_evidence_id: str | None
    latest_transition_event_time: str | None
    latest_transition_artifact_hash: str | None


@dataclass(frozen=True, slots=True)
class PromotionAuthorityTrust:
    authority_id: str
    authority_version: str
    key_id: str
    public_key_bytes: bytes


@dataclass(frozen=True, slots=True)
class TrialAccounting:
    registered: int
    completed: int
    failed: int
    abandoned: int
    unresolved: int
    registry_hash: str


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    required_red_teams: frozenset[str]
    required_negative_controls: frozenset[str]
    maximum_holdout_submissions: int
    minimum_forward_decisions: int
    minimum_forward_settlements: int
    minimum_forward_sessions: int
    minimum_forward_options_decisions: int
    minimum_forward_lower_bound_utility: float
    minimum_abstention_active_policy_lower_bound_utility: float
    maximum_forward_brier_score: float
    maximum_forward_loss_fraction: float


@dataclass(frozen=True, slots=True)
class PromotionEvidence:
    candidate_id: str
    candidate_author_id: str
    current_level: EvidenceLevel
    requested_level: EvidenceLevel
    frozen_at: str
    frozen_specification_hash: str
    evaluated_at: str


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    allowed: bool
    current_level: EvidenceLevel
    requested_level: EvidenceLevel
    reason_codes: tuple[str, ...]
    paper_only: bool
    live_blocked: bool
    trial_accounting: TrialAccounting
    proof_registry_hash: str
    dynamic_state_hash: str
    audit_snapshot_hash: str


def v1_promotion_policy() -> PromotionPolicy:
    return PromotionPolicy(
        frozenset({"leakage", "economic", "statistical", "tail", "implementation", "behavioral"}),
        V1_REQUIRED_NEGATIVE_CONTROL_IDS,
        1,
        100,
        100,
        20,
        20,
        0.0,
        0.0001,
        0.25,
        0.02,
    )


def canonical_candidate_registration(
    candidate_id: str,
    candidate_author_id: str,
    frozen_at: str,
    frozen_specification: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    if not candidate_id or not candidate_author_id:
        raise ValueError("canonical candidate identity fields cannot be empty")
    require_utc_iso(frozen_at)
    exact_fields = {
        "artifact_type",
        "schema_version",
        "candidate_id",
        "candidate_author_id",
        "candidate_mode",
        "frozen_at",
        "candidate_genome_hash",
        "candidate_genome",
        "paper_only",
        "live_blocked",
    }
    if set(frozen_specification) != exact_fields:
        raise ValueError("frozen candidate differs from the exact canonical v1 schema")
    candidate_mode = frozen_specification.get("candidate_mode")
    if candidate_mode not in {"options_expression", "abstention_policy"}:
        raise ValueError("frozen candidate requires an exact candidate_mode")
    required_bindings: dict[str, JsonValue] = {
        "artifact_type": "frozen_candidate_specification",
        "schema_version": "dopey-frozen-candidate-v1",
        "candidate_id": candidate_id,
        "candidate_author_id": candidate_author_id,
        "candidate_mode": cast(JsonValue, candidate_mode),
        "frozen_at": frozen_at,
        "paper_only": True,
        "live_blocked": True,
    }
    if any(frozen_specification.get(key) != value for key, value in required_bindings.items()):
        raise ValueError("frozen candidate specification identity is incomplete or inconsistent")
    raw_genome = frozen_specification.get("candidate_genome")
    genome_hash = frozen_specification.get("candidate_genome_hash")
    if not isinstance(raw_genome, dict) or not isinstance(genome_hash, str):
        raise ValueError("frozen candidate lacks its exact candidate genome")
    genome = candidate_genome_from_mapping(cast(dict[str, object], raw_genome))
    require_sha256(genome_hash, "candidate_genome_hash")
    if (
        genome.candidate_id != candidate_id
        or genome.candidate_mode != candidate_mode
        or genome.genome_hash != genome_hash
    ):
        raise ValueError("frozen candidate genome identity is inconsistent")
    frozen_hash = canonical_hash(cast(JsonValue, frozen_specification))
    return {
        "record_type": "candidate_registration",
        "environment_id": ENVIRONMENT_ID,
        "candidate_id": candidate_id,
        "candidate_author_id": candidate_author_id,
        "candidate_mode": cast(JsonValue, candidate_mode),
        "frozen_at": frozen_at,
        "frozen_specification": frozen_specification,
        "frozen_specification_hash": frozen_hash,
        "initial_level": "L0",
        "status": "frozen_registered",
        "paper_only": True,
        "live_blocked": True,
    }


def _lineage_records(lineage_path: Path) -> tuple[dict[str, JsonValue], ...]:
    records: list[dict[str, JsonValue]] = []
    for line_number, line in enumerate(
        lineage_path.resolve(strict=True).read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        decoded = json.loads(line)
        if not isinstance(decoded, dict):
            raise ValueError(
                "candidate lineage record must be a mapping: "
                f"path={lineage_path}, line={line_number}"
            )
        records.append(cast(dict[str, JsonValue], decoded))
    if not records or records[0].get("record_type") != "registry_initialization":
        raise ValueError("candidate lineage lacks its canonical initialization record")
    return tuple(records)


def canonical_candidate_identity(
    lineage_path: Path,
    candidate_id: str,
) -> CanonicalCandidateIdentity:
    if not candidate_id:
        raise ValueError("candidate selector cannot be empty")
    matching = [
        record
        for record in _lineage_records(lineage_path)[1:]
        if record.get("candidate_id") == candidate_id
    ]
    if len(matching) != 1:
        raise ValueError(
            "candidate must have exactly one canonical lineage registration: "
            f"candidate_id={candidate_id}, observed={len(matching)}"
        )
    record = matching[0]
    required_values: dict[str, JsonValue] = {
        "record_type": "candidate_registration",
        "environment_id": ENVIRONMENT_ID,
        "initial_level": "L0",
        "status": "frozen_registered",
        "paper_only": True,
        "live_blocked": True,
    }
    if any(record.get(key) != value for key, value in required_values.items()):
        raise ValueError("candidate lineage registration violates the canonical v1 schema")
    author_id = record.get("candidate_author_id")
    candidate_mode = record.get("candidate_mode")
    frozen_at = record.get("frozen_at")
    frozen_hash = record.get("frozen_specification_hash")
    raw_specification = record.get("frozen_specification")
    if (
        not isinstance(author_id, str)
        or not author_id
        or candidate_mode not in {"options_expression", "abstention_policy"}
        or not isinstance(frozen_at, str)
        or not isinstance(raw_specification, dict)
    ):
        raise ValueError("candidate lineage registration identity is incomplete")
    require_utc_iso(frozen_at)
    if not isinstance(frozen_hash, str):
        raise ValueError("candidate lineage frozen specification identity is invalid")
    require_sha256(frozen_hash, "frozen_specification_hash")
    specification = cast(dict[str, JsonValue], raw_specification)
    expected_record = canonical_candidate_registration(
        candidate_id,
        author_id,
        frozen_at,
        specification,
    )
    if record != expected_record or expected_record["frozen_specification_hash"] != frozen_hash:
        raise ValueError("candidate lineage registration is not canonically content-bound")
    return CanonicalCandidateIdentity(
        candidate_id,
        author_id,
        frozen_at,
        cast(str, frozen_hash),
        specification,
        cast(CandidateMode, candidate_mode),
    )


def derive_trial_accounting(
    experiment_registry_path: Path,
    candidate_id: str,
    frozen_specification_hash: str,
    evaluated_at: str,
) -> TrialAccounting:
    records = verify_hash_chained_ledger(experiment_registry_path)
    require_sha256(frozen_specification_hash, "frozen_specification_hash")
    require_utc_iso(evaluated_at)
    seen_experiment_ids: set[str] = set()
    for record in records:
        if record.get("substantive_trial") is not True:
            continue
        experiment_id = record.get("experiment_id")
        if not isinstance(experiment_id, str) or not experiment_id:
            raise ValueError("substantive experiment requires a non-empty experiment_id")
        if experiment_id in seen_experiment_ids:
            raise ValueError(
                f"duplicate substantive experiment_id: experiment_id={experiment_id}"
            )
        seen_experiment_ids.add(experiment_id)
        record_candidate_id = record.get("candidate_id")
        if not isinstance(record_candidate_id, str) or not record_candidate_id:
            raise ValueError(
                f"substantive experiment requires a candidate_id: experiment_id={experiment_id}"
            )
        record_frozen_hash = record.get("frozen_specification_hash")
        if not _is_sha256(record_frozen_hash):
            raise ValueError(
                "substantive experiment requires a frozen specification hash: "
                f"experiment_id={experiment_id}"
            )
        event_time = str(record["event_time"])
        if parse_utc(event_time) > parse_utc(evaluated_at):
            raise ValueError(
                f"substantive experiment is future-dated: experiment_id={experiment_id}"
            )
        if record.get("status") == "completed" and not _is_sha256(
            record.get("result_artifact_hash")
        ):
            raise ValueError(
                "completed substantive experiment requires result_artifact_hash: "
                f"experiment_id={experiment_id}"
            )
    trials = [
        record
        for record in records
        if record.get("candidate_id") == candidate_id
        and record.get("frozen_specification_hash") == frozen_specification_hash
        and record.get("substantive_trial") is True
    ]
    statuses = [str(record.get("status")) for record in trials]
    allowed_statuses = {"completed", "failed", "abandoned", "running"}
    unknown = sorted(set(statuses).difference(allowed_statuses))
    if unknown:
        raise ValueError(f"experiment registry contains unknown trial statuses: statuses={unknown}")
    return TrialAccounting(
        registered=len(trials),
        completed=statuses.count("completed"),
        failed=statuses.count("failed"),
        abandoned=statuses.count("abandoned"),
        unresolved=statuses.count("running"),
        registry_hash=canonical_hash(list(records)),
    )


def _candidate_proofs(
    proof_registry_path: Path,
    evidence: PromotionEvidence,
) -> tuple[tuple[dict[str, JsonValue], ...], str]:
    all_records = verify_hash_chained_ledger(proof_registry_path)
    records = tuple(
        record
        for record in all_records
        if record.get("candidate_id") == evidence.candidate_id
        and record.get("frozen_specification_hash") == evidence.frozen_specification_hash
    )
    seen_evidence_ids: set[str] = set()
    for record in records:
        required_fields = {
            "proof_type",
            "evidence_id",
            "evaluator_id",
            "environment_id",
            "event_time",
            "passed",
        }
        missing = sorted(field for field in required_fields if record.get(field) in {None, ""})
        if missing:
            raise ValueError(f"proof record is incomplete: missing={missing}")
        evidence_id = str(record["evidence_id"])
        if evidence_id in seen_evidence_ids:
            raise ValueError(f"proof evidence ID is duplicated: evidence_id={evidence_id}")
        seen_evidence_ids.add(evidence_id)
        if record["environment_id"] != "dopey-options-paper-v1":
            raise ValueError("proof record environment identity mismatch")
        if not isinstance(record["passed"], bool):
            raise ValueError("proof record passed field must be boolean")
        if record["evaluator_id"] == evidence.candidate_author_id:
            raise ValueError("candidate author cannot evaluate its own proof")
        require_utc_iso(str(record["event_time"]))
        if parse_utc(str(record["event_time"])) <= parse_utc(evidence.frozen_at):
            raise ValueError("proof evidence must be recorded after candidate freeze")
        if parse_utc(str(record["event_time"])) > parse_utc(evidence.evaluated_at):
            raise ValueError("proof evidence cannot be future-dated relative to evaluation")
    return records, canonical_hash(list(all_records))


def _decode_canonical_base64(value: object, field_name: str, expected_length: int) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError(f"promotion authority field is empty: field={field_name}")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"promotion authority field is invalid base64: field={field_name}") from error
    if len(decoded) != expected_length or base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError(f"promotion authority field has invalid canonical bytes: field={field_name}")
    return decoded


def _load_promotion_authority_trust(trust_path: Path) -> PromotionAuthorityTrust:
    decoded = json.loads(trust_path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(decoded, dict) or set(decoded) != PROMOTION_AUTHORITY_TRUST_FIELDS:
        raise ValueError("promotion authority trust differs from the exact v1 schema")
    trust = cast(dict[str, JsonValue], decoded)
    if (
        trust["schema_version"] != "dopey-promotion-authority-trust-v1"
        or trust["environment_id"] != ENVIRONMENT_ID
        or trust["algorithm"] != "ed25519"
    ):
        raise ValueError("promotion authority trust identity is invalid")
    if trust["status"] != "configured":
        raise PermissionError("promotion authority trust is not configured")
    authority_id = trust["authority_id"]
    authority_version = trust["authority_version"]
    key_id = trust["key_id"]
    if not all(isinstance(value, str) and value for value in (authority_id, authority_version, key_id)):
        raise ValueError("configured promotion authority trust identity is incomplete")
    public_key_bytes = _decode_canonical_base64(trust["public_key_base64"], "public_key_base64", 32)
    expected_key_id = f"ed25519-sha256-{hashlib.sha256(public_key_bytes).hexdigest()}"
    if key_id != expected_key_id:
        raise ValueError("promotion authority key identity differs from its pinned public key")
    return PromotionAuthorityTrust(
        cast(str, authority_id),
        cast(str, authority_version),
        cast(str, key_id),
        public_key_bytes,
    )


def _canonical_stage_receipt_bytes(receipt: dict[str, JsonValue]) -> bytes:
    if set(receipt) != SIGNED_STAGE_RECEIPT_FIELDS:
        raise ValueError("signed stage receipt differs from the exact v1 schema")
    if (
        receipt.get("schema_version") != "dopey-signed-stage-receipt-v1"
        or receipt.get("environment_id") != ENVIRONMENT_ID
        or receipt.get("paper_only") is not True
        or receipt.get("live_blocked") is not True
        or not isinstance(receipt.get("passed"), bool)
    ):
        raise ValueError("signed stage receipt authority is invalid")
    for field_name in (
        "authority_id",
        "authority_version",
        "evidence_id",
        "proof_type",
        "candidate_id",
        "candidate_author_id",
        "frozen_specification_hash",
        "experiment_id",
        "evaluator_id",
        "evaluator_version",
        "source_artifact_hash",
        "issued_at",
    ):
        if not isinstance(receipt.get(field_name), str) or not receipt.get(field_name):
            raise ValueError(f"signed stage receipt identity is incomplete: field={field_name}")
    require_sha256(cast(str, receipt["frozen_specification_hash"]), "frozen_specification_hash")
    require_sha256(cast(str, receipt["source_artifact_hash"]), "source_artifact_hash")
    require_utc_iso(cast(str, receipt["issued_at"]))
    proof_type = receipt["proof_type"]
    review_domain = receipt["review_domain"]
    if proof_type == "red_team":
        if not isinstance(review_domain, str) or review_domain not in RED_TEAM_EVALUATOR_IDS:
            raise ValueError("signed red-team receipt review domain is invalid")
    elif review_domain is not None:
        raise ValueError("non-red-team signed stage receipt cannot assert a review domain")
    return json.dumps(
        receipt,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _verify_stage_receipt(
    trust_path: Path,
    receipt: dict[str, JsonValue],
    signature_base64: object,
) -> PromotionAuthorityTrust:
    trust = _load_promotion_authority_trust(trust_path)
    if (
        receipt.get("authority_id") != trust.authority_id
        or receipt.get("authority_version") != trust.authority_version
    ):
        raise ValueError("signed stage receipt authority differs from the pinned trust root")
    message = _canonical_stage_receipt_bytes(receipt)
    signature = _decode_canonical_base64(signature_base64, "receipt_signature_base64", 64)
    public_key = Ed25519PublicKey.from_public_bytes(trust.public_key_bytes)
    try:
        public_key.verify(signature, message)
    except InvalidSignature as error:
        raise ValueError("signed stage receipt Ed25519 verification failed") from error
    return trust


def _expected_stage_evaluator(record: dict[str, JsonValue]) -> str | None:
    proof_type = record.get("proof_type")
    if proof_type == "red_team":
        review_domain = record.get("review_domain")
        if not isinstance(review_domain, str):
            return None
        return RED_TEAM_EVALUATOR_IDS.get(review_domain)
    if not isinstance(proof_type, str):
        return None
    return STAGE_EVALUATOR_IDS.get(proof_type)


def _authenticated_stage_proofs(
    proof_records: tuple[dict[str, JsonValue], ...],
    experiment_registry_path: Path,
    evidence: PromotionEvidence,
    external_anchor_verified: bool,
    repository_root: Path,
    proof_types: frozenset[str],
) -> tuple[tuple[dict[str, JsonValue], ...], tuple[str, ...]]:
    all_experiments = verify_hash_chained_ledger(experiment_registry_path)
    experiments = {
        str(record.get("experiment_id")): record
        for record in all_experiments
        if record.get("candidate_id") == evidence.candidate_id
        and record.get("frozen_specification_hash") == evidence.frozen_specification_hash
        and record.get("substantive_trial") is True
    }
    valid: list[dict[str, JsonValue]] = []
    reasons: list[str] = []
    for record in proof_records:
        proof_type = record.get("proof_type")
        if proof_type not in proof_types:
            continue
        evidence_id = str(record.get("evidence_id"))
        record_valid = external_anchor_verified
        expected_evaluator = _expected_stage_evaluator(record)
        if (
            expected_evaluator is None
            or record.get("evaluator_id") != expected_evaluator
            or record.get("evaluator_version") != STAGE_EVALUATOR_VERSION
            or record.get("authentication_method") != STAGE_AUTHENTICATION_METHOD
        ):
            record_valid = False
        raw_receipt = record.get("receipt_body")
        receipt_hash = record.get("receipt_body_hash")
        if not isinstance(raw_receipt, dict) or not _is_sha256(receipt_hash):
            record_valid = False
        else:
            receipt = cast(dict[str, JsonValue], raw_receipt)
            receipt_bindings: dict[str, JsonValue] = {
                "schema_version": "dopey-signed-stage-receipt-v1",
                "environment_id": ENVIRONMENT_ID,
                "evidence_id": evidence_id,
                "proof_type": cast(JsonValue, proof_type),
                "review_domain": cast(JsonValue, record.get("review_domain")),
                "candidate_id": evidence.candidate_id,
                "candidate_author_id": evidence.candidate_author_id,
                "frozen_specification_hash": evidence.frozen_specification_hash,
                "experiment_id": cast(JsonValue, record.get("experiment_id")),
                "evaluator_id": cast(JsonValue, record.get("evaluator_id")),
                "evaluator_version": STAGE_EVALUATOR_VERSION,
                "passed": cast(JsonValue, record.get("passed")),
                "source_artifact_hash": cast(JsonValue, record.get("source_artifact_hash")),
                "issued_at": cast(JsonValue, record.get("event_time")),
                "paper_only": True,
                "live_blocked": True,
            }
            try:
                receipt_matches = (
                    canonical_hash(cast(JsonValue, receipt)) == receipt_hash
                    and all(receipt.get(key) == value for key, value in receipt_bindings.items())
                )
                _verify_stage_receipt(
                    repository_root / PROMOTION_AUTHORITY_TRUST_FILE,
                    receipt,
                    record.get("receipt_signature_base64"),
                )
            except (OSError, PermissionError, TypeError, ValueError):
                receipt_matches = False
            if not receipt_matches:
                record_valid = False
        experiment_id = record.get("experiment_id")
        experiment = experiments.get(str(experiment_id))
        source_hash = record.get("source_artifact_hash")
        raw_source = record.get("source_artifact")
        if (
            experiment is None
            or experiment.get("status") != "completed"
            or not _is_sha256(experiment.get("result_artifact_hash"))
            or experiment.get("result_artifact_hash") != source_hash
            or not _is_sha256(source_hash)
            or not isinstance(raw_source, dict)
        ):
            record_valid = False
        else:
            source = cast(dict[str, JsonValue], raw_source)
            try:
                source_matches_hash = canonical_hash(cast(JsonValue, source)) == source_hash
                proof_after_experiment = parse_utc(str(record["event_time"])) >= parse_utc(
                    str(experiment["event_time"])
                )
            except (KeyError, TypeError, ValueError):
                source_matches_hash = False
                proof_after_experiment = False
            source_bindings: dict[str, JsonValue] = {
                "artifact_type": (
                    "candidate_retirement_state"
                    if proof_type == "retirement_state"
                    else "authenticated_stage_evaluation"
                ),
                "schema_version": (
                    "dopey-candidate-retirement-state-v1"
                    if proof_type == "retirement_state"
                    else "dopey-authenticated-stage-evaluation-v1"
                ),
                "proof_type": cast(JsonValue, proof_type),
                "evidence_id": evidence_id,
                "candidate_id": evidence.candidate_id,
                "candidate_author_id": evidence.candidate_author_id,
                "frozen_specification_hash": evidence.frozen_specification_hash,
                "experiment_id": cast(JsonValue, experiment_id),
                "evaluator_id": cast(JsonValue, record.get("evaluator_id")),
                "evaluator_version": STAGE_EVALUATOR_VERSION,
                "evaluated_at": cast(JsonValue, record.get("event_time")),
                "passed": cast(JsonValue, record.get("passed")),
                "paper_only": True,
                "live_blocked": True,
            }
            if proof_type == "retirement_state":
                source_bindings["environment_id"] = ENVIRONMENT_ID
            type_specific_fields = (
                ("review_domain",)
                if proof_type == "red_team"
                else (
                    "control_id",
                    "observed_absolute_effect",
                    "maximum_expected_absolute_effect",
                    "explanation_evidence_id",
                )
                if proof_type == "negative_control"
                else ()
            )
            for field_name in type_specific_fields:
                source_bindings[field_name] = cast(JsonValue, record.get(field_name))
            if (
                not source_matches_hash
                or not proof_after_experiment
                or any(source.get(key) != value for key, value in source_bindings.items())
            ):
                record_valid = False
        if record_valid:
            valid.append(record)
        else:
            reasons.append(f"stage_proof_authentication_invalid:{evidence_id}")
    return tuple(valid), tuple(reasons)


def _canonical_promotion_decision_artifact(
    decision: PromotionDecision,
    identity: CanonicalCandidateIdentity,
    evaluated_at: str,
    experiment_registry_record_count: int,
    proof_registry_record_count_before: int,
) -> dict[str, JsonValue]:
    if not decision.allowed or decision.reason_codes:
        raise ValueError("promotion transition requires an internally allowed gate result")
    if (
        experiment_registry_record_count < 0
        or proof_registry_record_count_before < 0
    ):
        raise ValueError("promotion transition registry counts cannot be negative")
    return {
        "artifact_type": "promotion_decision",
        "schema_version": "dopey-promotion-decision-v1",
        "candidate_id": identity.candidate_id,
        "candidate_author_id": identity.candidate_author_id,
        "candidate_mode": identity.candidate_mode,
        "frozen_specification_hash": identity.frozen_specification_hash,
        "from_level": decision.current_level,
        "to_level": decision.requested_level,
        "allowed": True,
        "reason_codes": [],
        "evaluated_at": evaluated_at,
        "trial_registry_hash": decision.trial_accounting.registry_hash,
        "experiment_registry_record_count": experiment_registry_record_count,
        "proof_registry_hash_before": decision.proof_registry_hash,
        "proof_registry_record_count_before": proof_registry_record_count_before,
        "dynamic_state_hash": decision.dynamic_state_hash,
        "audit_snapshot_hash": decision.audit_snapshot_hash,
        "paper_only": True,
        "live_blocked": True,
    }


def canonical_promotion_state(
    proof_records: tuple[dict[str, JsonValue], ...],
    identity: CanonicalCandidateIdentity,
    evaluated_at: str,
    repository_root: Path,
) -> CanonicalPromotionState:
    require_utc_iso(evaluated_at)
    current_index = 0
    latest_evidence_id: str | None = None
    latest_event_time: str | None = None
    latest_artifact_hash: str | None = None
    all_proof_records = verify_hash_chained_ledger(repository_root / "PROOF_LEDGER.jsonl")
    all_experiment_records = verify_hash_chained_ledger(
        repository_root / "EXPERIMENT_REGISTRY.jsonl"
    )
    proof_positions = {
        str(record["record_id"]): index
        for index, record in enumerate(all_proof_records)
    }
    transitions = [
        record
        for record in proof_records
        if record.get("proof_type") == "promotion_transition"
    ]
    for record in transitions:
        event_time = record.get("event_time")
        from_level = record.get("from_level")
        to_level = record.get("to_level")
        evidence_id = record.get("evidence_id")
        source_hash = record.get("source_artifact_hash")
        raw_source = record.get("source_artifact")
        raw_receipt = record.get("receipt_body")
        receipt_hash = record.get("receipt_body_hash")
        if (
            not isinstance(event_time, str)
            or parse_utc(event_time) > parse_utc(evaluated_at)
            or (
                latest_event_time is not None
                and parse_utc(event_time) <= parse_utc(latest_event_time)
            )
            or from_level != LEVELS[current_index]
            or current_index + 1 >= len(LEVELS)
            or to_level != LEVELS[current_index + 1]
            or not isinstance(evidence_id, str)
            or not evidence_id
            or record.get("record_type") != "promotion_transition"
            or record.get("evaluator_id") != PROMOTION_GOVERNOR_ID
            or record.get("evaluator_version") != STAGE_EVALUATOR_VERSION
            or record.get("authentication_method") != STAGE_AUTHENTICATION_METHOD
            or record.get("candidate_author_id") != identity.candidate_author_id
            or record.get("passed") is not True
            or record.get("paper_only") is not True
            or record.get("live_blocked") is not True
            or not _is_sha256(source_hash)
            or record.get("data_hash") != source_hash
            or not isinstance(raw_source, dict)
            or not isinstance(raw_receipt, dict)
            or not _is_sha256(receipt_hash)
        ):
            raise ValueError("canonical promotion transition is malformed or non-sequential")
        source = cast(dict[str, JsonValue], raw_source)
        bindings: dict[str, JsonValue] = {
            "artifact_type": "promotion_decision",
            "schema_version": "dopey-promotion-decision-v1",
            "candidate_id": identity.candidate_id,
            "candidate_author_id": identity.candidate_author_id,
            "candidate_mode": identity.candidate_mode,
            "frozen_specification_hash": identity.frozen_specification_hash,
            "from_level": cast(JsonValue, from_level),
            "to_level": cast(JsonValue, to_level),
            "allowed": True,
            "reason_codes": [],
            "evaluated_at": event_time,
            "paper_only": True,
            "live_blocked": True,
        }
        experiment_record_count = source.get("experiment_registry_record_count")
        proof_record_count = source.get("proof_registry_record_count_before")
        record_id = record.get("record_id")
        proof_position = proof_positions.get(str(record_id))
        if (
            set(source) != PROMOTION_DECISION_ARTIFACT_FIELDS
            or not isinstance(experiment_record_count, int)
            or isinstance(experiment_record_count, bool)
            or experiment_record_count < 0
            or experiment_record_count > len(all_experiment_records)
            or not isinstance(proof_record_count, int)
            or isinstance(proof_record_count, bool)
            or proof_record_count < 0
            or proof_position is None
            or proof_record_count != proof_position
            or canonical_hash(cast(JsonValue, source)) != source_hash
            or any(source.get(key) != value for key, value in bindings.items())
            or not _is_sha256(source.get("trial_registry_hash"))
            or not _is_sha256(source.get("proof_registry_hash_before"))
            or not _is_sha256(source.get("dynamic_state_hash"))
            or not _is_sha256(source.get("audit_snapshot_hash"))
            or source.get("trial_registry_hash")
            != canonical_hash(list(all_experiment_records[:experiment_record_count]))
            or source.get("proof_registry_hash_before")
            != canonical_hash(list(all_proof_records[:proof_record_count]))
        ):
            raise ValueError("canonical promotion transition artifact is invalid")
        receipt = cast(dict[str, JsonValue], raw_receipt)
        receipt_bindings: dict[str, JsonValue] = {
            "schema_version": "dopey-signed-stage-receipt-v1",
            "environment_id": ENVIRONMENT_ID,
            "evidence_id": evidence_id,
            "proof_type": "promotion_transition",
            "review_domain": None,
            "candidate_id": identity.candidate_id,
            "candidate_author_id": identity.candidate_author_id,
            "frozen_specification_hash": identity.frozen_specification_hash,
            "experiment_id": cast(JsonValue, record.get("experiment_id")),
            "evaluator_id": PROMOTION_GOVERNOR_ID,
            "evaluator_version": STAGE_EVALUATOR_VERSION,
            "passed": True,
            "source_artifact_hash": cast(JsonValue, source_hash),
            "issued_at": event_time,
            "paper_only": True,
            "live_blocked": True,
        }
        try:
            receipt_valid = (
                canonical_hash(cast(JsonValue, receipt)) == receipt_hash
                and all(receipt.get(key) == value for key, value in receipt_bindings.items())
            )
            _verify_stage_receipt(
                repository_root / PROMOTION_AUTHORITY_TRUST_FILE,
                receipt,
                record.get("receipt_signature_base64"),
            )
        except (OSError, PermissionError, TypeError, ValueError):
            receipt_valid = False
        if not receipt_valid:
            raise ValueError("canonical promotion transition receipt is invalid")
        current_index += 1
        latest_evidence_id = evidence_id
        latest_event_time = event_time
        latest_artifact_hash = cast(str, source_hash)
    return CanonicalPromotionState(
        LEVELS[current_index],
        latest_evidence_id,
        latest_event_time,
        latest_artifact_hash,
    )


def append_authenticated_promotion_transition(
    repository_root: Path,
    candidate_id: str,
    source_artifact: dict[str, JsonValue],
    receipt_body: dict[str, JsonValue],
    receipt_signature_base64: str,
    code_version: str,
) -> dict[str, JsonValue]:
    return _append_authenticated_promotion_transition_with_audit_runner(
        repository_root,
        candidate_id,
        source_artifact,
        receipt_body,
        receipt_signature_base64,
        code_version,
        _run_full_canonical_audit,
    )


def append_authenticated_promotion_transition_with_external_root(
    repository_root: Path,
    external_trust_root_path: Path,
    candidate_id: str,
    source_artifact: dict[str, JsonValue],
    receipt_body: dict[str, JsonValue],
    receipt_signature_base64: str,
    code_version: str,
) -> dict[str, JsonValue]:
    return _append_authenticated_promotion_transition_with_audit_runner(
        repository_root,
        candidate_id,
        source_artifact,
        receipt_body,
        receipt_signature_base64,
        code_version,
        _external_root_audit_runner(external_trust_root_path),
    )


def _append_authenticated_promotion_transition_with_audit_runner(
    repository_root: Path,
    candidate_id: str,
    source_artifact: dict[str, JsonValue],
    receipt_body: dict[str, JsonValue],
    receipt_signature_base64: str,
    code_version: str,
    audit_runner: CanonicalAuditRunner,
) -> dict[str, JsonValue]:
    root = repository_root.resolve(strict=True)
    if not code_version:
        raise ValueError("promotion transition code version cannot be empty")
    audit_result, dynamic_state = audit_runner(root)
    if (
        audit_result.get("external_anchor_verified") is not True
        or dynamic_state.get("external_anchor_verified") is not True
    ):
        raise PermissionError("promotion transition requires an externally anchored prior state")
    identity = canonical_candidate_identity(root / "CANDIDATE_LINEAGE.jsonl", candidate_id)
    issued_at = receipt_body.get("issued_at")
    if not isinstance(issued_at, str):
        raise ValueError("promotion transition receipt lacks its signed issue time")
    selector = PromotionEvidence(
        identity.candidate_id,
        identity.candidate_author_id,
        "L0",
        "L1",
        identity.frozen_at,
        identity.frozen_specification_hash,
        issued_at,
    )
    proof_records, _ = _candidate_proofs(root / "PROOF_LEDGER.jsonl", selector)
    state = canonical_promotion_state(proof_records, identity, issued_at, root)
    current_index = LEVELS.index(state.current_level)
    if current_index + 1 >= len(LEVELS):
        raise ValueError("L5 is the autonomous promotion ceiling")
    next_level = LEVELS[current_index + 1]
    canonical_decision = _evaluate_promotion_for_root_with_audit_runner(
        PromotionEvidence(
            identity.candidate_id,
            identity.candidate_author_id,
            state.current_level,
            next_level,
            identity.frozen_at,
            identity.frozen_specification_hash,
            issued_at,
        ),
        v1_promotion_policy(),
        root,
        audit_runner,
    )
    if not canonical_decision.allowed:
        raise PermissionError(
            "promotion transition canonical gates are not satisfied: "
            f"reasons={canonical_decision.reason_codes}"
        )
    experiment_record_count = len(
        verify_hash_chained_ledger(root / "EXPERIMENT_REGISTRY.jsonl")
    )
    proof_record_count = len(verify_hash_chained_ledger(root / "PROOF_LEDGER.jsonl"))
    expected_source_artifact = _canonical_promotion_decision_artifact(
        canonical_decision,
        identity,
        issued_at,
        experiment_record_count,
        proof_record_count,
    )
    if source_artifact != expected_source_artifact:
        raise ValueError(
            "promotion transition source differs from the internally recomputed gate result"
        )
    source_hash = canonical_hash(cast(JsonValue, source_artifact))
    evidence_id = receipt_body.get("evidence_id")
    experiment_id = receipt_body.get("experiment_id")
    receipt_bindings: dict[str, JsonValue] = {
        "schema_version": "dopey-signed-stage-receipt-v1",
        "environment_id": ENVIRONMENT_ID,
        "evidence_id": cast(JsonValue, evidence_id),
        "proof_type": "promotion_transition",
        "review_domain": None,
        "candidate_id": identity.candidate_id,
        "candidate_author_id": identity.candidate_author_id,
        "frozen_specification_hash": identity.frozen_specification_hash,
        "experiment_id": cast(JsonValue, experiment_id),
        "evaluator_id": PROMOTION_GOVERNOR_ID,
        "evaluator_version": STAGE_EVALUATOR_VERSION,
        "passed": True,
        "source_artifact_hash": source_hash,
        "issued_at": issued_at,
        "paper_only": True,
        "live_blocked": True,
    }
    if any(receipt_body.get(key) != value for key, value in receipt_bindings.items()):
        raise ValueError("promotion transition receipt is not bound to the canonical candidate state")
    _verify_stage_receipt(
        root / PROMOTION_AUTHORITY_TRUST_FILE,
        receipt_body,
        receipt_signature_base64,
    )
    if not isinstance(evidence_id, str) or not evidence_id or not isinstance(experiment_id, str):
        raise ValueError("promotion transition receipt identities are incomplete")
    _assert_canonical_audit_snapshot_unchanged_with_runner(
        root,
        canonical_decision.audit_snapshot_hash,
        audit_runner,
    )
    receipt_hash = canonical_hash(cast(JsonValue, receipt_body))
    payload: dict[str, JsonValue] = {
        "event_time": issued_at,
        "code_version": code_version,
        "data_hash": source_hash,
        "experiment_id": experiment_id,
        "record_type": "promotion_transition",
        "proof_type": "promotion_transition",
        "evidence_id": evidence_id,
        "candidate_id": identity.candidate_id,
        "candidate_author_id": identity.candidate_author_id,
        "frozen_specification_hash": identity.frozen_specification_hash,
        "environment_id": ENVIRONMENT_ID,
        "evaluator_id": PROMOTION_GOVERNOR_ID,
        "evaluator_version": STAGE_EVALUATOR_VERSION,
        "authentication_method": STAGE_AUTHENTICATION_METHOD,
        "from_level": state.current_level,
        "to_level": next_level,
        "passed": True,
        "source_artifact": source_artifact,
        "source_artifact_hash": source_hash,
        "receipt_body": receipt_body,
        "receipt_body_hash": receipt_hash,
        "receipt_signature_base64": receipt_signature_base64,
        "paper_only": True,
        "live_blocked": True,
    }
    return append_canonical_ascendancy_record(
        root,
        "proof",
        f"promotion-transition:{candidate_id}:{next_level}:{evidence_id}",
        payload,
    )


def _negative_control_results(
    proof_records: tuple[dict[str, JsonValue], ...],
) -> tuple[NegativeControlResult, ...]:
    results: list[NegativeControlResult] = []
    for record in proof_records:
        if record.get("proof_type") != "negative_control":
            continue
        control_id = record.get("control_id")
        observed = record.get("observed_absolute_effect")
        maximum = record.get("maximum_expected_absolute_effect")
        if not isinstance(control_id, str) or not control_id:
            raise ValueError("negative-control proof lacks control identity")
        if not isinstance(observed, (int, float)) or isinstance(observed, bool):
            raise ValueError("negative-control proof observed effect must be numeric")
        if not isinstance(maximum, (int, float)) or isinstance(maximum, bool):
            raise ValueError("negative-control proof tolerance must be numeric")
        if not math.isfinite(float(observed)) or not math.isfinite(float(maximum)):
            raise ValueError("negative-control proof values must be finite")
        explanation = record.get("explanation_evidence_id")
        if explanation is not None and not isinstance(explanation, str):
            raise ValueError("negative-control explanation identity must be a string or null")
        results.append(
            NegativeControlResult(
                control_id,
                str(record["evaluator_id"]),
                str(record["evidence_id"]),
                float(observed),
                float(maximum),
                bool(record["passed"]),
                cast(str | None, explanation),
            )
        )
    return tuple(results)


def _stress_matrix_reasons(
    proof_records: tuple[dict[str, JsonValue], ...],
) -> list[str]:
    stress_proofs = [
        record
        for record in proof_records
        if record.get("proof_type") == "stress_matrix"
        and record.get("passed") is True
    ]
    if len(stress_proofs) != 1:
        return ["stress_matrix_proof_missing_or_duplicated"]
    raw_source = stress_proofs[0].get("source_artifact")
    if not isinstance(raw_source, dict):
        return ["stress_matrix_artifact_invalid"]
    raw_results = raw_source.get("stress_results")
    if not isinstance(raw_results, list):
        return ["stress_matrix_artifact_invalid"]
    results: list[RequiredStressEvidence] = []
    expected_fields = {"scenario_id", "family", "completed", "passed", "evidence_id"}
    for raw_result in raw_results:
        if not isinstance(raw_result, dict) or set(raw_result) != expected_fields:
            return ["stress_matrix_artifact_invalid"]
        scenario_id = raw_result.get("scenario_id")
        family = raw_result.get("family")
        completed = raw_result.get("completed")
        passed = raw_result.get("passed")
        evidence_id = raw_result.get("evidence_id")
        if (
            not isinstance(scenario_id, str)
            or not scenario_id
            or not isinstance(family, str)
            or not family
            or not isinstance(completed, bool)
            or not isinstance(passed, bool)
            or not isinstance(evidence_id, str)
            or not evidence_id
        ):
            return ["stress_matrix_artifact_invalid"]
        results.append(
            RequiredStressEvidence(
                scenario_id,
                family,
                completed,
                passed,
                evidence_id,
            )
        )
    gate = evaluate_required_stress_evidence(tuple(results))
    if gate.passed:
        return []
    return ["stress_matrix_gate_blocked", *gate.reason_codes]


SEALED_SUBMISSION_FIELDS = frozenset(
    {
        "candidate_id",
        "frozen_specification_hash",
        "submission_count",
        "request_id",
        "requested_at",
        "evaluator_id",
        "evaluator_version",
        "aggregate_metric_ids",
    }
)


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        require_sha256(value, "evidence_hash")
    except ValueError:
        return False
    return True


def _is_unique_string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item for item in value)
        and len(value) == len(set(value))
    )


def _sealed_submission_map_reasons(
    submissions: dict[str, JsonValue],
    hash_submissions: dict[str, JsonValue],
    submissions_used: int,
    allowed_metric_ids: tuple[str, ...],
    evaluator_id: str,
    evaluator_version: str,
) -> list[str]:
    reasons: list[str] = []
    if submissions_used != len(submissions) or submissions_used != len(hash_submissions):
        reasons.append("sealed_budget_accounting_invalid")
    seen_request_ids: set[str] = set()
    for candidate_key, raw_record in submissions.items():
        if not isinstance(candidate_key, str) or not candidate_key or not isinstance(raw_record, dict):
            reasons.append("sealed_budget_accounting_invalid")
            continue
        record = cast(dict[str, JsonValue], raw_record)
        if set(record) != SEALED_SUBMISSION_FIELDS:
            reasons.append("sealed_budget_accounting_invalid")
            continue
        frozen_hash = record.get("frozen_specification_hash")
        request_id = record.get("request_id")
        requested_at = record.get("requested_at")
        if record.get("candidate_id") != candidate_key or not _is_sha256(frozen_hash):
            reasons.append("sealed_budget_accounting_invalid")
        if not isinstance(frozen_hash, str) or hash_submissions.get(frozen_hash) != record:
            reasons.append("sealed_budget_candidate_hash_alias_mismatch")
        if record.get("submission_count") != 1:
            reasons.append("sealed_evaluation_must_be_one_shot")
        if (
            not isinstance(request_id, str)
            or not request_id.startswith("sealed-request-")
            or request_id in seen_request_ids
        ):
            reasons.append("sealed_budget_accounting_invalid")
        else:
            seen_request_ids.add(request_id)
        if not isinstance(requested_at, str):
            reasons.append("sealed_budget_accounting_invalid")
        else:
            try:
                require_utc_iso(requested_at)
            except ValueError:
                reasons.append("sealed_budget_accounting_invalid")
        if record.get("evaluator_id") != evaluator_id or record.get(
            "evaluator_version"
        ) != evaluator_version:
            reasons.append("sealed_evaluator_identity_mismatch")
        if record.get("aggregate_metric_ids") != list(allowed_metric_ids):
            reasons.append("sealed_budget_accounting_invalid")
    for frozen_hash_key, raw_record in hash_submissions.items():
        if not _is_sha256(frozen_hash_key) or not isinstance(raw_record, dict):
            reasons.append("sealed_budget_accounting_invalid")
            continue
        record = cast(dict[str, JsonValue], raw_record)
        candidate_key = record.get("candidate_id")
        if record.get("frozen_specification_hash") != frozen_hash_key:
            reasons.append("sealed_budget_accounting_invalid")
        if not isinstance(candidate_key, str) or submissions.get(candidate_key) != record:
            reasons.append("sealed_budget_candidate_hash_alias_mismatch")
    return reasons


def _sealed_proof_reasons(
    proof: dict[str, JsonValue],
    submission: dict[str, JsonValue],
    allowed_metric_ids: tuple[str, ...],
    evaluator_id: str,
    evaluator_version: str,
    evidence: PromotionEvidence,
    repository_root: Path,
) -> list[str]:
    reasons: list[str] = []
    if proof.get("evaluator_id") != evaluator_id or proof.get(
        "evaluator_version"
    ) != evaluator_version:
        reasons.append("sealed_evaluator_identity_mismatch")
    if proof.get("submission_number") != 1:
        reasons.append("sealed_evaluation_must_be_one_shot")
    if proof.get("aggregate_feedback_only") is not True or proof.get(
        "raw_holdout_access"
    ) is not False:
        reasons.append("sealed_feedback_isolation_invalid")
    raw_metrics = proof.get("aggregate_metrics")
    if not isinstance(raw_metrics, dict):
        reasons.append("sealed_response_metrics_invalid")
        metrics: dict[str, JsonValue] = {}
    else:
        metrics = cast(dict[str, JsonValue], raw_metrics)
        if any(
            not isinstance(metric_id, str)
            or not metric_id
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            for metric_id, value in metrics.items()
        ):
            reasons.append("sealed_response_metrics_invalid")
    failure_codes = proof.get("failure_codes")
    if not isinstance(failure_codes, list) or any(
        not isinstance(code, str) or not code for code in failure_codes
    ):
        reasons.append("sealed_response_evidence_incomplete")
        failure_codes = []
    if len(failure_codes) != len(set(failure_codes)) or not set(failure_codes).issubset(
        ALLOWED_FAILURE_CODES
    ):
        reasons.append("sealed_response_evidence_incomplete")
    passed = proof.get("passed")
    if passed is True:
        if set(metrics) != set(allowed_metric_ids) or failure_codes:
            reasons.append("sealed_response_metric_set_mismatch")
    elif passed is False:
        if metrics or not failure_codes:
            reasons.append("sealed_response_evidence_incomplete")
        reasons.append("sealed_evaluation_reported_failure")
    else:
        reasons.append("sealed_response_evidence_incomplete")
    raw_response_body = proof.get("response_body")
    response_body_hash = proof.get("response_body_hash")
    signed_issued_at: str | None = None
    if not isinstance(raw_response_body, dict) or not _is_sha256(response_body_hash):
        reasons.append("sealed_response_body_binding_invalid")
    else:
        response_body = cast(dict[str, JsonValue], raw_response_body)
        raw_signed_issued_at = response_body.get("evaluator_issued_at")
        if isinstance(raw_signed_issued_at, str):
            signed_issued_at = raw_signed_issued_at
        expected_bindings: dict[str, JsonValue] = {
            "request_id": cast(JsonValue, submission.get("request_id")),
            "candidate_id": evidence.candidate_id,
            "frozen_specification_hash": evidence.frozen_specification_hash,
            "submission_number": 1,
            "evaluator_id": evaluator_id,
            "evaluator_version": evaluator_version,
            "evaluator_issued_at": cast(JsonValue, proof.get("event_time")),
            "passed": cast(JsonValue, passed),
            "aggregate_feedback_only": True,
            "raw_holdout_access": False,
        }
        if any(response_body.get(key) != value for key, value in expected_bindings.items()):
            reasons.append("sealed_response_body_binding_invalid")
        if response_body.get("aggregate_metrics") != metrics or response_body.get(
            "failure_codes"
        ) != failure_codes:
            reasons.append("sealed_response_body_binding_invalid")
        try:
            observed_response_body_hash = canonical_hash(cast(JsonValue, response_body))
        except (TypeError, ValueError):
            observed_response_body_hash = ""
        if observed_response_body_hash != response_body_hash:
            reasons.append("sealed_response_body_binding_invalid")
    if proof.get("source_artifact_hash") != response_body_hash:
        reasons.append("sealed_response_body_binding_invalid")
    signature_base64 = proof.get("signature_base64")
    if not isinstance(signature_base64, str) or not signature_base64:
        reasons.append("sealed_external_signature_verification_missing")
    else:
        try:
            if not isinstance(raw_response_body, dict):
                raise ValueError("sealed response body is unavailable for signature verification")
            verification = verify_sealed_response_signature(
                repository_root / "SEALED_EVALUATOR_TRUST.json",
                cast(dict[str, JsonValue], raw_response_body),
                signature_base64,
            )
        except (OSError, PermissionError, ValueError):
            reasons.append("sealed_external_signature_verification_invalid")
        else:
            if (
                verification.evaluator_id != evaluator_id
                or verification.evaluator_version != evaluator_version
                or verification.response_body_hash != response_body_hash
            ):
                reasons.append("sealed_external_signature_verification_invalid")
    requested_at = submission.get("requested_at")
    event_time = proof.get("event_time")
    if (
        isinstance(requested_at, str)
        and isinstance(event_time, str)
        and signed_issued_at == event_time
    ):
        try:
            if parse_utc(signed_issued_at) <= parse_utc(requested_at):
                reasons.append("sealed_response_precedes_request")
            if parse_utc(signed_issued_at) > parse_utc(evidence.evaluated_at):
                reasons.append("sealed_response_future_dated")
        except ValueError:
            reasons.append("sealed_response_evidence_incomplete")
    else:
        reasons.append("sealed_response_evidence_incomplete")
    return reasons


def _sealed_budget_reasons(
    holdout_budget_path: Path,
    evidence: PromotionEvidence,
    proof_records: tuple[dict[str, JsonValue], ...],
    policy: PromotionPolicy,
    repository_root: Path,
) -> list[str]:
    reasons: list[str] = []
    if not holdout_budget_path.exists():
        return ["sealed_budget_missing"]
    decoded = json.loads(holdout_budget_path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        return ["sealed_budget_accounting_invalid"]
    budget = cast(dict[str, JsonValue], decoded)
    if budget.get("schema_version") != "dopey-sealed-budget-v1" or budget.get(
        "environment_id"
    ) != "dopey-options-paper-v1":
        reasons.append("sealed_budget_accounting_invalid")
    if budget.get("status") != "configured_external_evaluator":
        reasons.append("sealed_evaluator_not_configured")
    if budget.get("aggregate_feedback_only") is not True or budget.get(
        "raw_holdout_access"
    ) is not False:
        reasons.append("sealed_feedback_isolation_invalid")
    if budget.get("maximum_submissions_per_frozen_candidate") != policy.maximum_holdout_submissions:
        reasons.append("sealed_evaluation_must_be_one_shot")
    maximum_total = budget.get("maximum_total_submissions")
    submissions_used = budget.get("submissions_used")
    if (
        not isinstance(maximum_total, int)
        or isinstance(maximum_total, bool)
        or maximum_total <= 0
        or not isinstance(submissions_used, int)
        or isinstance(submissions_used, bool)
        or submissions_used < 0
        or submissions_used > maximum_total
    ):
        reasons.append("sealed_budget_accounting_invalid")
        submissions_used = 0
    if submissions_used < 1:
        reasons.append("sealed_evaluation_submission_missing")
    raw_allowed_metric_ids = budget.get("allowed_aggregate_metric_ids")
    if not _is_unique_string_list(raw_allowed_metric_ids):
        reasons.append("sealed_budget_accounting_invalid")
        allowed_metric_ids: tuple[str, ...] = ()
    else:
        allowed_metric_ids = tuple(cast(list[str], raw_allowed_metric_ids))
        if any(
            any(term in metric_id.lower() for term in PROHIBITED_REQUEST_TERMS)
            for metric_id in allowed_metric_ids
        ):
            reasons.append("sealed_feedback_isolation_invalid")
    evaluator_id = budget.get("evaluator_id")
    evaluator_version = budget.get("evaluator_version")
    if not isinstance(evaluator_id, str) or not evaluator_id or not isinstance(
        evaluator_version, str
    ) or not evaluator_version:
        reasons.append("sealed_evaluator_identity_mismatch")
        evaluator_id = ""
        evaluator_version = ""
    raw_submissions = budget.get("candidate_submissions")
    raw_hash_submissions = budget.get("frozen_hash_submissions")
    if not isinstance(raw_submissions, dict) or not isinstance(raw_hash_submissions, dict):
        reasons.append("sealed_budget_accounting_invalid")
        return reasons
    submissions = cast(dict[str, JsonValue], raw_submissions)
    hash_submissions = cast(dict[str, JsonValue], raw_hash_submissions)
    reasons.extend(
        _sealed_submission_map_reasons(
            submissions,
            hash_submissions,
            submissions_used,
            allowed_metric_ids,
            evaluator_id,
            evaluator_version,
        )
    )
    raw_candidate_submission = submissions.get(evidence.candidate_id)
    raw_hash_submission = hash_submissions.get(evidence.frozen_specification_hash)
    if not isinstance(raw_candidate_submission, dict) or not isinstance(raw_hash_submission, dict):
        reasons.append("sealed_evaluation_submission_missing")
        return reasons
    candidate_submission = cast(dict[str, JsonValue], raw_candidate_submission)
    hash_submission = cast(dict[str, JsonValue], raw_hash_submission)
    if candidate_submission != hash_submission:
        reasons.append("sealed_budget_candidate_hash_alias_mismatch")
    if candidate_submission.get("candidate_id") != evidence.candidate_id or candidate_submission.get(
        "frozen_specification_hash"
    ) != evidence.frozen_specification_hash:
        reasons.append("sealed_budget_candidate_hash_mismatch")
    if candidate_submission.get("submission_count") != 1:
        reasons.append("sealed_evaluation_must_be_one_shot")
    request_id = candidate_submission.get("request_id")
    matching_proofs = [
        record
        for record in proof_records
        if record.get("proof_type") == "sealed_evaluation"
        and record.get("request_id") == request_id
    ]
    if len(matching_proofs) != 1:
        reasons.append("sealed_evaluation_proof_not_bound_to_budget_request")
        return reasons
    reasons.extend(
        _sealed_proof_reasons(
            matching_proofs[0],
            candidate_submission,
            allowed_metric_ids,
            evaluator_id,
            evaluator_version,
            evidence,
            repository_root,
        )
    )
    return reasons


def _canonical_embedded_artifact(
    value: object,
    expected_hash: object,
) -> dict[str, JsonValue] | None:
    if not isinstance(value, dict) or not _is_sha256(expected_hash):
        return None
    artifact = cast(dict[str, JsonValue], value)
    try:
        observed_hash = canonical_hash(cast(JsonValue, artifact))
    except (TypeError, ValueError):
        return None
    if observed_hash != expected_hash:
        return None
    return artifact


@dataclass(frozen=True, slots=True)
class SessionClusterBounds:
    cluster_count: int
    mean: float
    lower_bound: float
    upper_bound: float


def _session_cluster_bounds(
    values_by_session: dict[str, list[float]],
) -> SessionClusterBounds:
    if not values_by_session or any(not values for values in values_by_session.values()):
        raise ValueError("session-cluster inference requires non-empty session groups")
    cluster_means = tuple(
        sum(values) / len(values)
        for _, values in sorted(values_by_session.items())
    )
    if any(not math.isfinite(value) for value in cluster_means):
        raise ValueError("session-cluster inference received a non-finite value")
    mean = sum(cluster_means) / len(cluster_means)
    variance = (
        sum((value - mean) ** 2 for value in cluster_means)
        / (len(cluster_means) - 1)
        if len(cluster_means) > 1
        else 0.0
    )
    margin = SESSION_CLUSTER_T_CRITICAL * math.sqrt(variance / len(cluster_means))
    return SessionClusterBounds(
        cluster_count=len(cluster_means),
        mean=mean,
        lower_bound=mean - margin,
        upper_bound=mean + margin,
    )


def _embedded_snapshot_mapping(
    snapshot: object,
    expected_hash: object,
) -> dict[str, JsonValue] | None:
    if not isinstance(snapshot, str) or not _is_sha256(expected_hash):
        return None
    try:
        decoded = json.loads(snapshot)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(decoded, dict):
        return None
    mapping = cast(dict[str, JsonValue], decoded)
    try:
        if canonical_hash(cast(JsonValue, mapping)) != expected_hash:
            return None
    except (TypeError, ValueError):
        return None
    return mapping


def _forward_receipt_is_valid(
    repository_root: Path,
    raw_receipt: object,
    receipt_hash: object,
    signature_base64: object,
    purpose: str,
    candidate_id: str,
    frozen_specification_hash: str,
    record_id: str,
    subject_artifact_hash: str,
    claimed_issued_at: str,
    subject_event_time: str,
    latest_allowed_time: str,
) -> bool:
    if (
        not isinstance(raw_receipt, dict)
        or not _is_sha256(receipt_hash)
        or not isinstance(signature_base64, str)
        or not signature_base64
    ):
        return False
    receipt = cast(dict[str, JsonValue], raw_receipt)
    expected: dict[str, JsonValue] = {
        "schema_version": "dopey-forward-evidence-receipt-v1",
        "environment_id": ENVIRONMENT_ID,
        "purpose": purpose,
        "candidate_id": candidate_id,
        "frozen_specification_hash": frozen_specification_hash,
        "record_id": record_id,
        "subject_artifact_hash": subject_artifact_hash,
        "issued_at": claimed_issued_at,
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        return False
    try:
        require_utc_iso(claimed_issued_at)
        if not (
            parse_utc(subject_event_time)
            <= parse_utc(claimed_issued_at)
            <= parse_utc(latest_allowed_time)
        ):
            return False
        verification = verify_forward_evidence_signature(
            repository_root / "FORWARD_EVIDENCE_TRUST.json",
            receipt,
            signature_base64,
        )
    except (OSError, PermissionError, TypeError, ValueError):
        return False
    return (
        verification.purpose == purpose
        and verification.receipt_body_hash == receipt_hash
        and verification.subject_artifact_hash == subject_artifact_hash
        and canonical_hash(cast(JsonValue, receipt)) == receipt_hash
    )


def _forward_reasons(
    forward_registry_path: Path,
    evidence: PromotionEvidence,
    policy: PromotionPolicy,
    candidate_mode: CandidateMode,
    candidate_genome_hash: str,
) -> list[str]:
    require_sha256(candidate_genome_hash, "candidate_genome_hash")
    reasons: list[str] = []
    resolved_forward_path = forward_registry_path.resolve(strict=True)
    repository_root = resolved_forward_path.parent.parent
    all_records = verify_hash_chained_ledger(resolved_forward_path)
    records = [
        record
        for record in all_records
        if record.get("candidate_id") == evidence.candidate_id
        and record.get("frozen_specification_hash") == evidence.frozen_specification_hash
    ]
    decisions: dict[str, dict[str, JsonValue]] = {}
    decision_tickets: dict[str, PaperExecutionTicket] = {}
    decision_complete_cost_hashes: dict[str, str] = {}
    settlements: dict[str, dict[str, JsonValue]] = {}
    execution_observations: dict[str, dict[str, JsonValue]] = {}
    execution_observation_parent_ids: set[str] = set()
    fill_observation_ids: set[str] = set()
    fill_artifact_hashes: set[str] = set()
    sessions: set[str] = set()
    prediction_ids: set[str] = set()
    opportunity_ids: set[str] = set()
    prediction_artifact_hashes: set[str] = set()
    decision_artifact_hashes: set[str] = set()
    action_artifact_hashes: set[str] = set()
    predicted_success_probabilities: dict[str, float] = {}
    settlement_ids: set[str] = set()
    outcome_ids: set[str] = set()
    settlement_evidence_ids: set[str] = set()
    settlement_artifact_hashes: set[str] = set()
    for record in records:
        record_type = record.get("record_type")
        if record_type == "forward_decision":
            required_string_fields = (
                "forward_id",
                "prediction_id",
                "opportunity_id",
                "session_id",
                "event_time",
                "recorder_issued_at",
                "prediction_artifact_hash",
                "decision_artifact_hash",
            )
            if any(
                not isinstance(record.get(field), str) or not record.get(field)
                for field in required_string_fields
            ):
                reasons.append("forward_decision_incomplete")
                continue
            forward_id = cast(str, record["forward_id"])
            prediction_id = cast(str, record["prediction_id"])
            opportunity_id = cast(str, record["opportunity_id"])
            session_id = cast(str, record["session_id"])
            event_time = cast(str, record["event_time"])
            recorder_issued_at = cast(str, record["recorder_issued_at"])
            prediction_artifact_hash = cast(str, record["prediction_artifact_hash"])
            decision_artifact_hash = cast(str, record["decision_artifact_hash"])
            action_artifact_hash_value = record.get("action_artifact_hash")
            parsed_ticket: PaperExecutionTicket | None = None
            complete_cost_stack_artifact_hash: str | None = None
            record_reasons: list[str] = []
            if record.get("environment_id") != "dopey-options-paper-v1":
                record_reasons.append("forward_environment_identity_mismatch")
            if record.get("candidate_mode") != candidate_mode:
                record_reasons.append("forward_candidate_mode_mismatch")
            if record.get("candidate_genome_hash") != candidate_genome_hash:
                record_reasons.append("forward_candidate_genome_mismatch")
            if record.get("evidence_kind") != FORWARD_EVIDENCE_KIND:
                record_reasons.append("non_forward_evidence_labeled_as_forward")
            if (
                record.get("paper_only") is not True
                or record.get("live_blocked") is not True
                or record.get("replay") is not False
                or record.get("backtest") is not False
                or record.get("realized_evidence") is not False
            ):
                record_reasons.append("forward_evidence_authority_invalid")
            if (
                record.get("evidence_class") != PROSPECTIVE_PROFITABILITY_EVIDENCE_CLASS
                or record.get("opportunity_synthetic") is not False
                or record.get("profitability_evidence_eligible") is not True
            ):
                record_reasons.append("forward_evidence_not_profitability_eligible")
            try:
                require_utc_iso(event_time)
                if parse_utc(event_time) <= parse_utc(evidence.frozen_at):
                    record_reasons.append("forward_evidence_not_after_candidate_freeze")
                if parse_utc(event_time) > parse_utc(evidence.evaluated_at):
                    record_reasons.append("forward_evidence_future_dated")
            except ValueError:
                record_reasons.append("forward_decision_time_invalid")
            ticket_id = record.get("ticket_id")
            abstention_id = record.get("abstention_id")
            has_ticket = isinstance(ticket_id, str) and bool(ticket_id)
            has_abstention = isinstance(abstention_id, str) and bool(abstention_id)
            if (
                has_ticket == has_abstention
                or (ticket_id is not None and not has_ticket)
                or (abstention_id is not None and not has_abstention)
            ):
                record_reasons.append("forward_decision_action_identity_invalid")
            if not _is_sha256(prediction_artifact_hash) or not _is_sha256(
                decision_artifact_hash
            ):
                record_reasons.append("forward_decision_artifact_identity_invalid")
            if not _is_sha256(action_artifact_hash_value):
                record_reasons.append("forward_decision_action_artifact_invalid")
            prediction_artifact = _canonical_embedded_artifact(
                record.get("prediction_artifact"),
                prediction_artifact_hash,
            )
            decision_artifact = _canonical_embedded_artifact(
                record.get("decision_artifact"),
                decision_artifact_hash,
            )
            if prediction_artifact is None or decision_artifact is None:
                record_reasons.append("forward_decision_artifact_content_invalid")
            else:
                if not _forward_receipt_is_valid(
                    repository_root,
                    record.get("recorder_receipt_body"),
                    record.get("recorder_receipt_body_hash"),
                    record.get("recorder_signature_base64"),
                    "forward_record",
                    evidence.candidate_id,
                    evidence.frozen_specification_hash,
                    forward_id,
                    decision_artifact_hash,
                    recorder_issued_at,
                    event_time,
                    evidence.evaluated_at,
                ):
                    record_reasons.append("forward_recorder_receipt_invalid")
                prediction_bindings: dict[str, JsonValue] = {
                    "artifact_type": "forward_prediction",
                    "prediction_id": prediction_id,
                    "opportunity_id": opportunity_id,
                    "candidate_id": evidence.candidate_id,
                    "frozen_specification_hash": evidence.frozen_specification_hash,
                    "candidate_mode": candidate_mode,
                    "success_definition": FORWARD_SUCCESS_DEFINITION,
                    "evidence_class": PROSPECTIVE_PROFITABILITY_EVIDENCE_CLASS,
                    "opportunity_synthetic": False,
                    "profitability_evidence_eligible": True,
                    "paper_only": True,
                    "live_blocked": True,
                }
                decision_bindings: dict[str, JsonValue] = {
                    "artifact_type": "forward_decision",
                    "forward_id": forward_id,
                    "prediction_id": prediction_id,
                    "opportunity_id": opportunity_id,
                    "candidate_id": evidence.candidate_id,
                    "frozen_specification_hash": evidence.frozen_specification_hash,
                    "candidate_mode": candidate_mode,
                    "candidate_genome_hash": cast(
                        JsonValue,
                        candidate_genome_hash,
                    ),
                    "prediction_artifact_hash": prediction_artifact_hash,
                    "input_validation_status": FORWARD_INPUT_VALIDATION_STATUS,
                    "membership_validation_status": FORWARD_MEMBERSHIP_VALIDATION_STATUS,
                    "decision_time": event_time,
                    "recorder_issued_at": recorder_issued_at,
                    "ticket_id": cast(JsonValue, ticket_id),
                    "abstention_id": cast(JsonValue, abstention_id),
                    "market_context_hash": cast(
                        JsonValue,
                        record.get("market_context_hash"),
                    ),
                    "membership_attestation_hash": cast(
                        JsonValue,
                        record.get("membership_attestation_hash"),
                    ),
                    "evidence_class": PROSPECTIVE_PROFITABILITY_EVIDENCE_CLASS,
                    "opportunity_synthetic": False,
                    "profitability_evidence_eligible": True,
                    "paper_only": True,
                    "live_blocked": True,
                }
                expected_action_type: str | None = None
                if has_ticket and not has_abstention:
                    expected_action_type = "paper_execution_ticket"
                elif has_abstention and not has_ticket:
                    expected_action_type = "abstention_record"
                if expected_action_type is not None:
                    decision_bindings["action_type"] = expected_action_type
                if (
                    candidate_mode == "options_expression"
                    and expected_action_type != "paper_execution_ticket"
                ) or (
                    candidate_mode == "abstention_policy"
                    and expected_action_type != "abstention_record"
                ):
                    record_reasons.append("forward_action_candidate_mode_mismatch")
                if _is_sha256(action_artifact_hash_value):
                    decision_bindings["action_artifact_hash"] = cast(
                        str,
                        action_artifact_hash_value,
                    )
                if any(
                    prediction_artifact.get(key) != value
                    for key, value in prediction_bindings.items()
                ) or any(
                    decision_artifact.get(key) != value
                    for key, value in decision_bindings.items()
                ):
                    record_reasons.append("forward_decision_artifact_content_invalid")
                action_artifact = _canonical_embedded_artifact(
                    decision_artifact.get("action_artifact"),
                    action_artifact_hash_value,
                )
                if action_artifact is None or expected_action_type is None:
                    record_reasons.append("forward_decision_action_artifact_invalid")
                else:
                    try:
                        if expected_action_type == "paper_execution_ticket":
                            action = paper_execution_ticket_from_mapping(action_artifact)
                            action_id = action.ticket_id
                            parsed_ticket = action
                        else:
                            action = abstention_record_from_mapping(action_artifact)
                            action_id = action.abstention_id
                    except (KeyError, TypeError, ValueError):
                        record_reasons.append("forward_decision_action_artifact_invalid")
                    else:
                        expected_action_id = ticket_id if has_ticket else abstention_id
                        if (
                            action_id != expected_action_id
                            or action.opportunity_id != opportunity_id
                            or action.candidate_id != evidence.candidate_id
                            or action.candidate_genome_hash
                            != candidate_genome_hash
                            or action.decision_timestamp != event_time
                            or action.paper_only is not True
                            or action.live_blocked is not True
                        ):
                            record_reasons.append("forward_decision_action_binding_invalid")
                        if (
                            action.evidence_class == "synthetic_mechanics_only"
                            or action.opportunity_synthetic is not False
                        ):
                            record_reasons.append("forward_evidence_not_profitability_eligible")
                        action_prospective_hash = action.prospective_evidence_hash
                        attested_prospective_hash = decision_artifact.get(
                            "prospective_evidence_hash"
                        )
                        if (
                            not _is_sha256(action_prospective_hash)
                            or attested_prospective_hash != action_prospective_hash
                        ):
                            record_reasons.append("forward_input_attestation_invalid")
                        market_context = _embedded_snapshot_mapping(
                            action.market_context_snapshot,
                            action.market_context_hash,
                        )
                        prospective_evidence = _embedded_snapshot_mapping(
                            action.prospective_evidence_snapshot,
                            action.prospective_evidence_hash,
                        )
                        membership_attestation_hash = record.get(
                            "membership_attestation_hash"
                        )
                        if (
                            market_context is None
                            or prospective_evidence is None
                            or record.get("market_context_hash")
                            != action.market_context_hash
                            or not _is_sha256(market_context.get("content_hash"))
                            or market_context.get("membership_mode")
                            != "independent_point_in_time"
                            or market_context.get("synthetic") is not False
                            or not _is_sha256(membership_attestation_hash)
                            or market_context.get("membership_attestation_hash")
                            != membership_attestation_hash
                            or prospective_evidence.get("market_context_hash")
                            != market_context.get("content_hash")
                            or prospective_evidence.get("synthetic") is not False
                        ):
                            record_reasons.append("forward_membership_attestation_invalid")
                        raw_complete_cost_hash = (
                            prospective_evidence.get(
                                "complete_cost_model_artifact_hash"
                            )
                            if prospective_evidence is not None
                            else None
                        )
                        if not _is_sha256(raw_complete_cost_hash):
                            record_reasons.append("forward_complete_cost_stack_invalid")
                        else:
                            complete_cost_stack_artifact_hash = cast(
                                str,
                                raw_complete_cost_hash,
                            )
                prediction_time = prediction_artifact.get("prediction_time")
                predicted_success_probability = prediction_artifact.get(
                    "predicted_success_probability"
                )
                if not _is_sha256(prediction_artifact.get("source_data_hash")) or not isinstance(
                    prediction_time, str
                ):
                    record_reasons.append("forward_prediction_artifact_source_invalid")
                else:
                    try:
                        require_utc_iso(prediction_time)
                        if (
                            parse_utc(prediction_time) <= parse_utc(evidence.frozen_at)
                            or parse_utc(prediction_time) > parse_utc(event_time)
                            or parse_utc(prediction_time) > parse_utc(evidence.evaluated_at)
                        ):
                            record_reasons.append("forward_prediction_artifact_time_invalid")
                    except ValueError:
                        record_reasons.append("forward_prediction_artifact_time_invalid")
                if (
                    not isinstance(predicted_success_probability, (int, float))
                    or isinstance(predicted_success_probability, bool)
                    or not math.isfinite(float(predicted_success_probability))
                    or not 0.0 <= float(predicted_success_probability) <= 1.0
                ):
                    record_reasons.append("forward_prediction_calibration_input_invalid")
            if forward_id in decisions:
                record_reasons.append("forward_decision_id_duplicated")
            if prediction_id in prediction_ids:
                record_reasons.append("forward_prediction_id_duplicated")
            if opportunity_id in opportunity_ids:
                record_reasons.append("forward_opportunity_id_duplicated")
            if prediction_artifact_hash in prediction_artifact_hashes:
                record_reasons.append("forward_prediction_artifact_duplicated")
            if decision_artifact_hash in decision_artifact_hashes:
                record_reasons.append("forward_decision_artifact_duplicated")
            if (
                _is_sha256(action_artifact_hash_value)
                and action_artifact_hash_value in action_artifact_hashes
            ):
                record_reasons.append("forward_decision_action_artifact_duplicated")
            reasons.extend(record_reasons)
            if record_reasons:
                continue
            decisions[forward_id] = record
            if parsed_ticket is not None:
                decision_tickets[forward_id] = parsed_ticket
            if complete_cost_stack_artifact_hash is not None:
                decision_complete_cost_hashes[forward_id] = (
                    complete_cost_stack_artifact_hash
                )
            prediction_ids.add(prediction_id)
            opportunity_ids.add(opportunity_id)
            prediction_artifact_hashes.add(prediction_artifact_hash)
            decision_artifact_hashes.add(decision_artifact_hash)
            action_artifact_hashes.add(cast(str, action_artifact_hash_value))
            predicted_success_probabilities[forward_id] = float(
                cast(float, predicted_success_probability)
            )
            sessions.add(session_id)
        elif record_type == "forward_execution_observation":
            required_string_fields = (
                "execution_observation_id",
                "parent_decision_id",
                "ticket_id",
                "session_id",
                "event_time",
                "recorder_issued_at",
                "fill_observation_id",
                "fill_status",
                "fill_artifact_hash",
            )
            if any(
                not isinstance(record.get(field), str) or not record.get(field)
                for field in required_string_fields
            ):
                reasons.append("forward_execution_observation_incomplete")
                continue
            execution_observation_id = cast(
                str,
                record["execution_observation_id"],
            )
            parent_decision_id = cast(str, record["parent_decision_id"])
            ticket_id = cast(str, record["ticket_id"])
            event_time = cast(str, record["event_time"])
            recorder_issued_at = cast(str, record["recorder_issued_at"])
            fill_observation_id = cast(str, record["fill_observation_id"])
            fill_status = cast(str, record["fill_status"])
            fill_artifact_hash = cast(str, record["fill_artifact_hash"])
            record_reasons = []
            if candidate_mode != "options_expression":
                record_reasons.append("abstention_candidate_has_execution_observation")
            if record.get("environment_id") != ENVIRONMENT_ID:
                record_reasons.append("forward_environment_identity_mismatch")
            if record.get("candidate_mode") != candidate_mode:
                record_reasons.append("forward_candidate_mode_mismatch")
            if record.get("evidence_kind") != FORWARD_EVIDENCE_KIND:
                record_reasons.append("non_forward_evidence_labeled_as_forward")
            if (
                record.get("paper_only") is not True
                or record.get("live_blocked") is not True
                or record.get("replay") is not False
                or record.get("backtest") is not False
                or record.get("realized_evidence") is not False
            ):
                record_reasons.append("forward_evidence_authority_invalid")
            if (
                record.get("evidence_class")
                != PROSPECTIVE_PROFITABILITY_EVIDENCE_CLASS
                or record.get("opportunity_synthetic") is not False
                or record.get("profitability_evidence_eligible") is not True
            ):
                record_reasons.append("forward_evidence_not_profitability_eligible")
            decision = decisions.get(parent_decision_id)
            ticket = decision_tickets.get(parent_decision_id)
            if decision is None or ticket is None:
                record_reasons.append("forward_execution_observation_parent_missing")
            elif (
                decision.get("ticket_id") != ticket_id
                or decision.get("session_id") != record.get("session_id")
            ):
                record_reasons.append("forward_execution_observation_parent_identity_mismatch")
            try:
                require_utc_iso(event_time)
                if decision is not None and parse_utc(event_time) <= parse_utc(
                    str(decision["event_time"])
                ):
                    record_reasons.append("forward_execution_observation_not_after_decision")
                if parse_utc(event_time) > parse_utc(evidence.evaluated_at):
                    record_reasons.append("forward_evidence_future_dated")
            except ValueError:
                record_reasons.append("forward_execution_observation_time_invalid")
            fill_artifact = _canonical_embedded_artifact(
                record.get("fill_artifact"),
                fill_artifact_hash,
            )
            if fill_artifact is None or ticket is None:
                record_reasons.append("forward_execution_observation_artifact_invalid")
            else:
                try:
                    fill_observation = paper_fill_observation_from_mapping(
                        fill_artifact,
                        ticket,
                    )
                except (KeyError, TypeError, ValueError):
                    record_reasons.append("forward_execution_observation_artifact_invalid")
                else:
                    if (
                        fill_observation.observation_id != fill_observation_id
                        or fill_observation.ticket_id != ticket_id
                        or fill_observation.witnessed_at != event_time
                        or fill_observation.paper_fill_status != fill_status
                        or fill_status not in {"filled", "missed"}
                        or fill_observation.evidence_class
                        != PROSPECTIVE_PROFITABILITY_EVIDENCE_CLASS
                        or fill_observation.realized_evidence is not False
                        or fill_observation.paper_only is not True
                        or fill_observation.live_blocked is not True
                    ):
                        record_reasons.append(
                            "forward_execution_observation_artifact_binding_invalid"
                        )
                    if not _forward_receipt_is_valid(
                        repository_root,
                        record.get("recorder_receipt_body"),
                        record.get("recorder_receipt_body_hash"),
                        record.get("recorder_signature_base64"),
                        "forward_record",
                        evidence.candidate_id,
                        evidence.frozen_specification_hash,
                        execution_observation_id,
                        fill_artifact_hash,
                        recorder_issued_at,
                        event_time,
                        evidence.evaluated_at,
                    ):
                        record_reasons.append("forward_recorder_receipt_invalid")
            if execution_observation_id in execution_observations:
                record_reasons.append("forward_execution_observation_id_duplicated")
            if parent_decision_id in execution_observation_parent_ids:
                record_reasons.append("forward_decision_observed_more_than_once")
            if fill_observation_id in fill_observation_ids:
                record_reasons.append("forward_fill_observation_id_duplicated")
            if fill_artifact_hash in fill_artifact_hashes:
                record_reasons.append("forward_fill_artifact_duplicated")
            reasons.extend(record_reasons)
            if record_reasons:
                continue
            execution_observations[execution_observation_id] = record
            execution_observation_parent_ids.add(parent_decision_id)
            fill_observation_ids.add(fill_observation_id)
            fill_artifact_hashes.add(fill_artifact_hash)
        elif record_type == "forward_settlement":
            required_string_fields = (
                "settlement_id",
                "parent_decision_id",
                "prediction_id",
                "opportunity_id",
                "session_id",
                "maturity_time",
                "event_time",
                "recorder_issued_at",
                "outcome_source_issued_at",
                "outcome_id",
                "outcome_label",
                "grade",
                "evidence_id",
                "settlement_artifact_hash",
                "source_evidence_hash",
                "outcome_unit",
                "success_definition",
                "complete_cost_stack_artifact_hash",
            )
            if any(
                not isinstance(record.get(field), str) or not record.get(field)
                for field in required_string_fields
            ):
                reasons.append("forward_settlement_incomplete")
                continue
            settlement_id = cast(str, record["settlement_id"])
            event_time = cast(str, record["event_time"])
            recorder_issued_at = cast(str, record["recorder_issued_at"])
            outcome_source_issued_at = cast(str, record["outcome_source_issued_at"])
            maturity_time = cast(str, record["maturity_time"])
            outcome_id = cast(str, record["outcome_id"])
            evidence_id = cast(str, record["evidence_id"])
            settlement_artifact_hash = cast(str, record["settlement_artifact_hash"])
            source_evidence_hash = cast(str, record["source_evidence_hash"])
            record_reasons = []
            if record.get("environment_id") != "dopey-options-paper-v1":
                record_reasons.append("forward_environment_identity_mismatch")
            if record.get("candidate_mode") != candidate_mode:
                record_reasons.append("forward_candidate_mode_mismatch")
            if record.get("evidence_kind") != FORWARD_EVIDENCE_KIND:
                record_reasons.append("non_forward_evidence_labeled_as_forward")
            if (
                record.get("paper_only") is not True
                or record.get("live_blocked") is not True
                or record.get("replay") is not False
                or record.get("backtest") is not False
                or record.get("realized_evidence") is not False
            ):
                record_reasons.append("forward_evidence_authority_invalid")
            if (
                record.get("evidence_class") != PROSPECTIVE_PROFITABILITY_EVIDENCE_CLASS
                or record.get("opportunity_synthetic") is not False
                or record.get("profitability_evidence_eligible") is not True
            ):
                record_reasons.append("forward_evidence_not_profitability_eligible")
            try:
                require_utc_iso(event_time)
                require_utc_iso(maturity_time)
                if parse_utc(event_time) <= parse_utc(evidence.frozen_at):
                    record_reasons.append("forward_evidence_not_after_candidate_freeze")
                if parse_utc(event_time) > parse_utc(evidence.evaluated_at):
                    record_reasons.append("forward_evidence_future_dated")
                if parse_utc(event_time) <= parse_utc(maturity_time):
                    record_reasons.append("forward_settlement_not_after_maturity")
            except ValueError:
                record_reasons.append("forward_settlement_time_invalid")
            candidate_net_utility = record.get("candidate_net_utility")
            raw_baselines = record.get("baseline_net_utilities")
            raw_baseline_hashes = record.get("baseline_artifact_hashes")
            expected_baseline_ids = (
                OPTIONS_BASELINE_IDS
                if candidate_mode == "options_expression"
                else ABSTENTION_BASELINE_IDS
            )
            if (
                record.get("outcome_unit") != FORWARD_OUTCOME_UNIT
                or record.get("success_definition") != FORWARD_SUCCESS_DEFINITION
                or not isinstance(candidate_net_utility, (int, float))
                or isinstance(candidate_net_utility, bool)
                or not math.isfinite(float(candidate_net_utility))
                or not isinstance(raw_baselines, dict)
                or set(raw_baselines) != expected_baseline_ids
                or any(
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(float(value))
                    for value in raw_baselines.values()
                )
                or not isinstance(raw_baseline_hashes, dict)
                or set(raw_baseline_hashes) != expected_baseline_ids
                or any(not _is_sha256(value) for value in raw_baseline_hashes.values())
                or not _is_sha256(record.get("complete_cost_stack_artifact_hash"))
            ):
                record_reasons.append("forward_settlement_outcome_invalid")
            else:
                expected_outcome_label = (
                    "win"
                    if float(candidate_net_utility) > 0.0
                    else "loss"
                    if float(candidate_net_utility) < 0.0
                    else "flat"
                )
                if record.get("outcome_label") != expected_outcome_label:
                    record_reasons.append("forward_settlement_outcome_label_invalid")
            if candidate_mode == "options_expression":
                if (
                    not isinstance(record.get("execution_observation_id"), str)
                    or not record.get("execution_observation_id")
                    or record.get("fill_status") not in {"filled", "missed"}
                    or record.get("missed_fill_utility_policy")
                    != FORWARD_MISSED_FILL_UTILITY_POLICY
                ):
                    record_reasons.append("forward_settlement_execution_binding_invalid")
            elif (
                record.get("execution_observation_id") is not None
                or record.get("fill_status") is not None
                or record.get("missed_fill_utility_policy") is not None
            ):
                record_reasons.append("abstention_settlement_has_execution_binding")
            if record.get("grade") != "settled_forward_outcome":
                record_reasons.append("forward_settlement_grade_invalid")
            if not _is_sha256(settlement_artifact_hash) or not _is_sha256(
                source_evidence_hash
            ):
                record_reasons.append("forward_settlement_artifact_identity_invalid")
            settlement_artifact = _canonical_embedded_artifact(
                record.get("settlement_artifact"),
                settlement_artifact_hash,
            )
            source_evidence_artifact = _canonical_embedded_artifact(
                record.get("source_evidence_artifact"),
                source_evidence_hash,
            )
            if settlement_artifact is None or source_evidence_artifact is None:
                record_reasons.append("forward_settlement_artifact_content_invalid")
            else:
                if not _forward_receipt_is_valid(
                    repository_root,
                    record.get("recorder_receipt_body"),
                    record.get("recorder_receipt_body_hash"),
                    record.get("recorder_signature_base64"),
                    "forward_record",
                    evidence.candidate_id,
                    evidence.frozen_specification_hash,
                    settlement_id,
                    settlement_artifact_hash,
                    recorder_issued_at,
                    event_time,
                    evidence.evaluated_at,
                ):
                    record_reasons.append("forward_recorder_receipt_invalid")
                settlement_bindings: dict[str, JsonValue] = {
                    "artifact_type": "forward_settlement",
                    "settlement_id": settlement_id,
                    "parent_decision_id": cast(JsonValue, record.get("parent_decision_id")),
                    "prediction_id": cast(JsonValue, record.get("prediction_id")),
                    "opportunity_id": cast(JsonValue, record.get("opportunity_id")),
                    "candidate_id": evidence.candidate_id,
                    "frozen_specification_hash": evidence.frozen_specification_hash,
                    "candidate_mode": candidate_mode,
                    "maturity_time": maturity_time,
                    "settlement_time": event_time,
                    "recorder_issued_at": recorder_issued_at,
                    "outcome_source_issued_at": outcome_source_issued_at,
                    "outcome_id": outcome_id,
                    "outcome_label": cast(JsonValue, record.get("outcome_label")),
                    "outcome_unit": FORWARD_OUTCOME_UNIT,
                    "success_definition": FORWARD_SUCCESS_DEFINITION,
                    "candidate_net_utility": cast(JsonValue, candidate_net_utility),
                    "baseline_net_utilities": cast(JsonValue, raw_baselines),
                    "complete_cost_stack_artifact_hash": cast(
                        JsonValue,
                        record.get("complete_cost_stack_artifact_hash"),
                    ),
                    "baseline_artifact_hashes": cast(
                        JsonValue,
                        raw_baseline_hashes,
                    ),
                    "execution_observation_id": cast(
                        JsonValue,
                        record.get("execution_observation_id"),
                    ),
                    "fill_status": cast(JsonValue, record.get("fill_status")),
                    "missed_fill_utility_policy": cast(
                        JsonValue,
                        record.get("missed_fill_utility_policy"),
                    ),
                    "grade": "settled_forward_outcome",
                    "evidence_id": evidence_id,
                    "source_evidence_hash": source_evidence_hash,
                    "evidence_class": PROSPECTIVE_PROFITABILITY_EVIDENCE_CLASS,
                    "opportunity_synthetic": False,
                    "profitability_evidence_eligible": True,
                    "paper_only": True,
                    "live_blocked": True,
                }
                source_bindings: dict[str, JsonValue] = {
                    "artifact_type": "forward_outcome_evidence",
                    "evidence_id": evidence_id,
                    "outcome_id": outcome_id,
                    "opportunity_id": cast(JsonValue, record.get("opportunity_id")),
                    "prediction_id": cast(JsonValue, record.get("prediction_id")),
                    "candidate_id": evidence.candidate_id,
                    "frozen_specification_hash": evidence.frozen_specification_hash,
                    "candidate_mode": candidate_mode,
                    "outcome_label": cast(JsonValue, record.get("outcome_label")),
                    "outcome_unit": FORWARD_OUTCOME_UNIT,
                    "success_definition": FORWARD_SUCCESS_DEFINITION,
                    "candidate_net_utility": cast(JsonValue, candidate_net_utility),
                    "baseline_net_utilities": cast(JsonValue, raw_baselines),
                    "complete_cost_stack_artifact_hash": cast(
                        JsonValue,
                        record.get("complete_cost_stack_artifact_hash"),
                    ),
                    "baseline_artifact_hashes": cast(
                        JsonValue,
                        raw_baseline_hashes,
                    ),
                    "execution_observation_id": cast(
                        JsonValue,
                        record.get("execution_observation_id"),
                    ),
                    "fill_status": cast(JsonValue, record.get("fill_status")),
                    "missed_fill_utility_policy": cast(
                        JsonValue,
                        record.get("missed_fill_utility_policy"),
                    ),
                    "outcome_source_issued_at": outcome_source_issued_at,
                    "evidence_class": PROSPECTIVE_PROFITABILITY_EVIDENCE_CLASS,
                    "opportunity_synthetic": False,
                    "profitability_evidence_eligible": True,
                    "paper_only": True,
                    "live_blocked": True,
                }
                if any(
                    settlement_artifact.get(key) != value
                    for key, value in settlement_bindings.items()
                ) or any(
                    source_evidence_artifact.get(key) != value
                    for key, value in source_bindings.items()
                ):
                    record_reasons.append("forward_settlement_artifact_content_invalid")
                observed_at = source_evidence_artifact.get("observed_at")
                outcome_derivation_id = source_evidence_artifact.get(
                    "outcome_derivation_id"
                )
                if (
                    not _is_sha256(source_evidence_artifact.get("data_hash"))
                    or not isinstance(observed_at, str)
                    or not isinstance(outcome_derivation_id, str)
                    or not outcome_derivation_id
                ):
                    record_reasons.append("forward_settlement_source_evidence_invalid")
                else:
                    if not _forward_receipt_is_valid(
                        repository_root,
                        record.get("outcome_receipt_body"),
                        record.get("outcome_receipt_body_hash"),
                        record.get("outcome_signature_base64"),
                        "outcome_source",
                        evidence.candidate_id,
                        evidence.frozen_specification_hash,
                        evidence_id,
                        source_evidence_hash,
                        outcome_source_issued_at,
                        observed_at,
                        evidence.evaluated_at,
                    ):
                        record_reasons.append("forward_outcome_source_receipt_invalid")
                    try:
                        require_utc_iso(observed_at)
                        if (
                            parse_utc(observed_at) < parse_utc(maturity_time)
                            or parse_utc(observed_at) > parse_utc(event_time)
                            or parse_utc(observed_at) > parse_utc(evidence.evaluated_at)
                            or parse_utc(outcome_source_issued_at)
                            > parse_utc(recorder_issued_at)
                        ):
                            record_reasons.append("forward_settlement_source_evidence_time_invalid")
                    except ValueError:
                        record_reasons.append("forward_settlement_source_evidence_time_invalid")
            if settlement_id in settlement_ids:
                record_reasons.append("forward_settlement_id_duplicated")
            if outcome_id in outcome_ids:
                record_reasons.append("forward_outcome_id_duplicated")
            if evidence_id in settlement_evidence_ids:
                record_reasons.append("forward_settlement_evidence_id_duplicated")
            if settlement_artifact_hash in settlement_artifact_hashes:
                record_reasons.append("forward_settlement_artifact_duplicated")
            reasons.extend(record_reasons)
            if record_reasons:
                continue
            settlements[settlement_id] = record
            settlement_ids.add(settlement_id)
            outcome_ids.add(outcome_id)
            settlement_evidence_ids.add(evidence_id)
            settlement_artifact_hashes.add(settlement_artifact_hash)
    settled_parent_ids: set[str] = set()
    valid_pair_count = 0
    paired_utilities: list[float] = []
    brier_terms_by_session: dict[str, list[float]] = {}
    incremental_utilities_by_baseline: dict[str, dict[str, list[float]]] = {
        baseline_id: {}
        for baseline_id in (
            OPTIONS_BASELINE_IDS
            if candidate_mode == "options_expression"
            else ABSTENTION_BASELINE_IDS
        )
    }
    for settlement in settlements.values():
        parent_id = str(settlement["parent_decision_id"])
        decision = decisions.get(parent_id)
        if decision is None:
            reasons.append("forward_settlement_parent_missing")
            continue
        if parent_id in settled_parent_ids:
            reasons.append("forward_decision_settled_more_than_once")
            continue
        if any(
            settlement.get(field) != decision.get(field)
            for field in ("prediction_id", "opportunity_id", "session_id")
        ):
            reasons.append("forward_settlement_parent_identity_mismatch")
            continue
        decision_time = parse_utc(str(decision["event_time"]))
        maturity_time = parse_utc(str(settlement["maturity_time"]))
        settlement_time = parse_utc(str(settlement["event_time"]))
        if maturity_time <= decision_time:
            reasons.append("forward_maturity_precedes_decision")
            continue
        if settlement_time <= maturity_time:
            reasons.append("forward_settlement_not_after_maturity")
            continue
        probability = predicted_success_probabilities.get(parent_id)
        candidate_net_utility = settlement.get("candidate_net_utility")
        raw_baselines = settlement.get("baseline_net_utilities")
        if (
            probability is None
            or not isinstance(candidate_net_utility, (int, float))
            or isinstance(candidate_net_utility, bool)
            or not isinstance(raw_baselines, dict)
        ):
            reasons.append("forward_quality_inputs_incomplete")
            continue
        if (
            settlement.get("complete_cost_stack_artifact_hash")
            != decision_complete_cost_hashes.get(parent_id)
        ):
            reasons.append("forward_settlement_complete_cost_stack_mismatch")
            continue
        if candidate_mode == "options_expression":
            raw_execution_observation_id = settlement.get("execution_observation_id")
            observation = (
                execution_observations.get(raw_execution_observation_id)
                if isinstance(raw_execution_observation_id, str)
                else None
            )
            if (
                observation is None
                or observation.get("parent_decision_id") != parent_id
                or observation.get("ticket_id") != decision.get("ticket_id")
                or observation.get("fill_status") != settlement.get("fill_status")
                or parse_utc(str(observation["event_time"])) > maturity_time
            ):
                reasons.append("forward_settlement_execution_observation_mismatch")
                continue
            if (
                settlement.get("fill_status") == "missed"
                and float(candidate_net_utility) != 0.0
            ):
                reasons.append("missed_fill_candidate_utility_not_zero")
                continue
        utility = float(candidate_net_utility)
        calibration_target = 1.0 if utility > 0.0 else 0.0
        session_id = str(settlement["session_id"])
        settled_parent_ids.add(parent_id)
        valid_pair_count += 1
        paired_utilities.append(utility)
        brier_terms_by_session.setdefault(session_id, []).append(
            (probability - calibration_target) ** 2
        )
        for baseline_id, raw_baseline_utility in cast(
            dict[str, JsonValue],
            raw_baselines,
        ).items():
            if not isinstance(raw_baseline_utility, (int, float)) or isinstance(
                raw_baseline_utility,
                bool,
            ):
                reasons.append("forward_quality_inputs_incomplete")
                continue
            incremental_utilities_by_baseline[baseline_id].setdefault(
                session_id,
                [],
            ).append(utility - float(raw_baseline_utility))
    if len(decisions) < policy.minimum_forward_decisions:
        reasons.append("insufficient_forward_decisions")
    if valid_pair_count < policy.minimum_forward_settlements:
        reasons.append("insufficient_forward_settlements")
    if len(brier_terms_by_session) < policy.minimum_forward_sessions:
        reasons.append("insufficient_forward_sessions")
    if candidate_mode == "options_expression":
        options_decision_count = sum(
            1
            for decision in decisions.values()
            if isinstance(decision.get("ticket_id"), str) and decision.get("ticket_id")
        )
        if options_decision_count < policy.minimum_forward_options_decisions:
            reasons.append("insufficient_forward_options_decisions")
        if execution_observation_parent_ids != set(decisions):
            reasons.append("forward_execution_observation_coverage_incomplete")
    elif execution_observations:
        reasons.append("abstention_candidate_has_execution_observation")
    if paired_utilities:
        baseline_bounds = {
            baseline_id: _session_cluster_bounds(values_by_session)
            for baseline_id, values_by_session in incremental_utilities_by_baseline.items()
            if values_by_session
        }
        calibration_bounds = _session_cluster_bounds(brier_terms_by_session)
        maximum_loss_fraction = max(0.0, max(-value for value in paired_utilities))
        if set(baseline_bounds) != set(incremental_utilities_by_baseline):
            reasons.append("forward_matched_baseline_evidence_incomplete")
        elif candidate_mode == "options_expression":
            reasons.extend(
                f"forward_baseline_lower_bound_below_threshold:{baseline_id}"
                for baseline_id, bounds in sorted(baseline_bounds.items())
                if bounds.lower_bound < policy.minimum_forward_lower_bound_utility
            )
        else:
            no_trade_bounds = baseline_bounds["no_trade"]
            active_bounds = tuple(
                baseline_bounds[baseline_id]
                for baseline_id in ("always_express", "random_abstention")
            )
            if no_trade_bounds.lower_bound < 0.0:
                reasons.append("abstention_inferior_to_no_trade")
            if any(bounds.lower_bound < 0.0 for bounds in active_bounds):
                reasons.append("abstention_inferior_to_active_baseline")
            if max(bounds.lower_bound for bounds in active_bounds) < (
                policy.minimum_abstention_active_policy_lower_bound_utility
            ):
                reasons.append("abstention_positive_selection_not_demonstrated")
        if calibration_bounds.upper_bound > policy.maximum_forward_brier_score:
            reasons.append("forward_cluster_calibration_above_threshold")
        if maximum_loss_fraction > policy.maximum_forward_loss_fraction:
            reasons.append("forward_loss_fraction_above_threshold")
    else:
        reasons.append("forward_quality_inputs_incomplete")
    return reasons


def _validate_canonical_dynamic_state(
    repository_root: Path,
    dynamic_state: dict[str, object],
) -> dict[str, object]:
    if (
        dynamic_state.get("schema_version") != "dopey-dynamic-state-audit-v1"
        or dynamic_state.get("environment_id") != "dopey-options-paper-v1"
        or not _is_sha256(dynamic_state.get("dynamic_state_hash"))
    ):
        raise ValueError("canonical dynamic-state audit identity is invalid")
    raw_files = dynamic_state.get("files")
    if not isinstance(raw_files, dict):
        raise ValueError("canonical dynamic-state audit lacks its file identities")
    files = cast(dict[str, object], raw_files)
    promotion_state_paths = (
        "CANDIDATE_LINEAGE.jsonl",
        "EXPERIMENT_REGISTRY.jsonl",
        "PROOF_LEDGER.jsonl",
        "HOLDOUT_BUDGET.json",
        "shadow_trading/FORWARD_EVIDENCE.jsonl",
    )
    if not set(promotion_state_paths).issubset(ASCENDANCY_DYNAMIC_STATE_PATHS):
        raise ValueError("promotion dynamic-state path policy is incomplete")
    for relative_path in promotion_state_paths:
        artifact_path = (repository_root / relative_path).resolve(strict=True)
        if files.get(relative_path) != file_sha256(artifact_path):
            raise ValueError(
                "canonical dynamic-state audit changed before promotion evaluation: "
                f"path={relative_path}"
            )
    return dynamic_state


def _canonical_repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _canonical_source_manifest_path(repository_root: Path) -> Path:
    manifest_path = (repository_root / "DATA_MANIFEST.json").resolve(strict=True)
    decoded = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("canonical data manifest must be a mapping")
    source_manifest = decoded.get("source_manifest")
    if not isinstance(source_manifest, str) or not source_manifest:
        raise ValueError("canonical data manifest lacks its source-manifest path")
    source_path = Path(source_manifest)
    if not source_path.is_absolute():
        raise ValueError("canonical source-manifest path must be absolute")
    return source_path.resolve(strict=True)


def _run_full_canonical_audit(
    repository_root: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    from verifier.audit import run_ascendancy_audit

    source_manifest_path = _canonical_source_manifest_path(repository_root)
    audit_result = run_ascendancy_audit(repository_root, source_manifest_path)
    return _validate_full_canonical_audit(repository_root, audit_result)


def _run_full_canonical_audit_with_external_root(
    repository_root: Path,
    external_trust_root_path: Path,
) -> CanonicalAuditResult:
    from verifier.audit import run_ascendancy_audit_with_external_root

    source_manifest_path = _canonical_source_manifest_path(repository_root)
    audit_result = run_ascendancy_audit_with_external_root(
        repository_root,
        source_manifest_path,
        external_trust_root_path,
    )
    return _validate_full_canonical_audit(repository_root, audit_result)


def _external_root_audit_runner(
    external_trust_root_path: Path,
) -> CanonicalAuditRunner:
    resolved_external_path = external_trust_root_path.resolve(strict=True)

    def run_with_external_root(repository_root: Path) -> CanonicalAuditResult:
        return _run_full_canonical_audit_with_external_root(
            repository_root,
            resolved_external_path,
        )

    return run_with_external_root


def _validate_full_canonical_audit(
    repository_root: Path,
    audit_result: dict[str, object],
) -> CanonicalAuditResult:
    if (
        audit_result.get("schema_version") != "dopey-ascendancy-audit-v1"
        or audit_result.get("environment_id") != "dopey-options-paper-v1"
        or audit_result.get("status") != "pass_fail_closed_research_kernel"
        or audit_result.get("paper_only") is not True
        or audit_result.get("live_blocked") is not True
        or audit_result.get("action_ready") is not False
        or audit_result.get("profitability_edge_demonstrated") is not False
    ):
        raise ValueError("full canonical Ascendancy audit identity or authority is invalid")
    raw_dynamic_state = audit_result.get("dynamic_state")
    if not isinstance(raw_dynamic_state, dict):
        raise ValueError("full canonical Ascendancy audit lacks dynamic-state evidence")
    dynamic_state = _validate_canonical_dynamic_state(
        repository_root,
        cast(dict[str, object], raw_dynamic_state),
    )
    return audit_result, dynamic_state


def _canonical_audit_snapshot_hash(
    audit_result: dict[str, object],
    dynamic_state: dict[str, object],
) -> str:
    raw_files = dynamic_state.get("files")
    if not isinstance(raw_files, dict):
        raise ValueError("canonical audit snapshot lacks dynamic file identities")
    raw_pinned_identities = dynamic_state.get(
        "external_trust_root_pinned_role_identities"
    )
    if not isinstance(raw_pinned_identities, dict):
        raise ValueError("canonical audit snapshot lacks pinned role identities")
    pinned_identities = cast(dict[str, object], raw_pinned_identities)
    snapshot: dict[str, JsonValue] = {
        "schema_version": "dopey-canonical-audit-snapshot-v1",
        "environment_id": ENVIRONMENT_ID,
        "protected_manifest_sha256": cast(
            JsonValue,
            audit_result.get("protected_manifest_sha256"),
        ),
        "source_manifest_sha256": cast(
            JsonValue,
            audit_result.get("source_manifest_sha256"),
        ),
        "dynamic_state_hash": cast(JsonValue, dynamic_state.get("dynamic_state_hash")),
        "dynamic_anchor_id": cast(JsonValue, dynamic_state.get("dynamic_anchor_id")),
        "dynamic_anchor_sequence": cast(
            JsonValue,
            dynamic_state.get("dynamic_anchor_sequence"),
        ),
        "dynamic_anchor_parent_id": cast(
            JsonValue,
            dynamic_state.get("dynamic_anchor_parent_id"),
        ),
        "dynamic_anchor_receipt_sha256": cast(
            JsonValue,
            dynamic_state.get("dynamic_anchor_receipt_sha256"),
        ),
        "external_trust_root_id": cast(
            JsonValue,
            dynamic_state.get("external_trust_root_id"),
        ),
        "external_trust_root_version": cast(
            JsonValue,
            dynamic_state.get("external_trust_root_version"),
        ),
        "external_trust_root_sha256": cast(
            JsonValue,
            dynamic_state.get("external_trust_root_sha256"),
        ),
        "external_trust_root_pinned_role_identities": cast(
            dict[str, JsonValue],
            pinned_identities,
        ),
        "files": cast(dict[str, JsonValue], raw_files),
    }
    for field_name in (
        "protected_manifest_sha256",
        "source_manifest_sha256",
        "dynamic_state_hash",
    ):
        require_sha256(cast(str, snapshot[field_name]), field_name)
    repository_anchor_verified = dynamic_state.get("repository_anchor_verified") is True
    if repository_anchor_verified:
        require_sha256(
            cast(str, snapshot["dynamic_anchor_receipt_sha256"]),
            "dynamic_anchor_receipt_sha256",
        )
        if not isinstance(snapshot["dynamic_anchor_id"], str) or not snapshot["dynamic_anchor_id"]:
            raise ValueError("canonical audit snapshot lacks a repository anchor identity")
        if (
            not isinstance(snapshot["dynamic_anchor_sequence"], int)
            or isinstance(snapshot["dynamic_anchor_sequence"], bool)
            or snapshot["dynamic_anchor_sequence"] < 1
        ):
            raise ValueError("canonical audit snapshot lacks a repository anchor sequence")
    elif (
        snapshot["dynamic_anchor_id"] is not None
        or snapshot["dynamic_anchor_receipt_sha256"] is not None
        or snapshot["dynamic_anchor_sequence"] is not None
        or snapshot["dynamic_anchor_parent_id"] is not None
    ):
        raise ValueError("unverified repository audit snapshot asserts anchor identities")
    external_root_fields = (
        "external_trust_root_id",
        "external_trust_root_version",
        "external_trust_root_sha256",
    )
    if dynamic_state.get("external_anchor_verified") is True:
        for field_name in external_root_fields[:2]:
            if not isinstance(snapshot[field_name], str) or not snapshot[field_name]:
                raise ValueError(
                    "canonical audit snapshot lacks its external trust-root identity"
                )
        require_sha256(
            cast(str, snapshot["external_trust_root_sha256"]),
            "external_trust_root_sha256",
        )
        if set(pinned_identities) != EXTERNAL_PINNED_ROLE_IDS:
            raise ValueError("canonical audit snapshot pinned-role set is invalid")
        for role_id, raw_identity in pinned_identities.items():
            if not isinstance(raw_identity, dict) or set(raw_identity) != {
                "identity_id",
                "identity_version",
                "key_id",
                "public_key_sha256",
            }:
                raise ValueError(
                    "canonical audit snapshot pinned-role identity is invalid: "
                    f"role={role_id}"
                )
            identity = cast(dict[str, object], raw_identity)
            if any(
                not isinstance(identity.get(field_name), str)
                or not identity.get(field_name)
                for field_name in ("identity_id", "identity_version", "key_id")
            ):
                raise ValueError(
                    "canonical audit snapshot pinned-role identity is incomplete: "
                    f"role={role_id}"
                )
            require_sha256(
                cast(str, identity.get("public_key_sha256")),
                f"pinned_role.{role_id}.public_key_sha256",
            )
            if identity.get("key_id") != (
                f"ed25519-sha256-{identity['public_key_sha256']}"
            ):
                raise ValueError(
                    "canonical audit snapshot pinned-role key identity is invalid: "
                    f"role={role_id}"
                )
    elif any(snapshot[field_name] is not None for field_name in external_root_fields):
        raise ValueError("unverified canonical audit snapshot asserts an external trust root")
    elif pinned_identities:
        raise ValueError("unverified canonical audit snapshot asserts pinned role identities")
    return canonical_hash(snapshot)


def _assert_canonical_audit_snapshot_unchanged(
    repository_root: Path,
    expected_snapshot_hash: str,
) -> None:
    _assert_canonical_audit_snapshot_unchanged_with_runner(
        repository_root,
        expected_snapshot_hash,
        _run_full_canonical_audit,
    )


def _assert_canonical_audit_snapshot_unchanged_with_runner(
    repository_root: Path,
    expected_snapshot_hash: str,
    audit_runner: CanonicalAuditRunner,
) -> None:
    require_sha256(expected_snapshot_hash, "expected_audit_snapshot_hash")
    fresh_audit, fresh_dynamic_state = audit_runner(repository_root)
    observed_snapshot_hash = _canonical_audit_snapshot_hash(
        fresh_audit,
        fresh_dynamic_state,
    )
    if observed_snapshot_hash != expected_snapshot_hash:
        raise ValueError(
            "canonical Ascendancy state changed after evidence reads: "
            f"expected={expected_snapshot_hash}, observed={observed_snapshot_hash}"
        )


def _assert_canonical_audit_snapshot_unchanged_with_external_root(
    repository_root: Path,
    external_trust_root_path: Path,
    expected_snapshot_hash: str,
) -> None:
    audit_runner = _external_root_audit_runner(external_trust_root_path)
    _assert_canonical_audit_snapshot_unchanged_with_runner(
        repository_root,
        expected_snapshot_hash,
        audit_runner,
    )


def _candidate_author_conflict_reasons(
    candidate_author_id: str,
    dynamic_state: dict[str, object],
) -> tuple[str, ...]:
    raw_pinned_identities = dynamic_state.get(
        "external_trust_root_pinned_role_identities"
    )
    if not isinstance(raw_pinned_identities, dict):
        return ("external_pinned_role_identities_missing",)
    protected_identities: dict[str, str] = {
        "promotion_governor": PROMOTION_GOVERNOR_ID,
        **{
            f"stage_evaluator:{role}": evaluator_id
            for role, evaluator_id in STAGE_EVALUATOR_IDS.items()
        },
        **{
            f"red_team:{role}": evaluator_id
            for role, evaluator_id in RED_TEAM_EVALUATOR_IDS.items()
        },
    }
    for role, raw_identity in cast(
        dict[str, object],
        raw_pinned_identities,
    ).items():
        if isinstance(raw_identity, dict) and isinstance(
            raw_identity.get("identity_id"),
            str,
        ):
            protected_identities[f"external:{role}"] = cast(
                str,
                raw_identity["identity_id"],
            )
    return tuple(
        f"candidate_author_conflicts_with_protected_role:{role}"
        for role, protected_identity in sorted(protected_identities.items())
        if candidate_author_id == protected_identity
    )


def _cumulative_promotion_gate_state(
    repository_root: Path,
    identity: CanonicalCandidateIdentity,
    target_level: EvidenceLevel,
    evaluated_at: str,
    audit_result: dict[str, object],
    dynamic_state: dict[str, object],
    policy: PromotionPolicy,
) -> tuple[
    tuple[str, ...],
    TrialAccounting,
    tuple[dict[str, JsonValue], ...],
    str,
]:
    if policy != v1_promotion_policy():
        raise ValueError("promotion policy must be derived from frozen Ascendancy v1 policy")
    selector = PromotionEvidence(
        identity.candidate_id,
        identity.candidate_author_id,
        target_level,
        target_level,
        identity.frozen_at,
        identity.frozen_specification_hash,
        evaluated_at,
    )
    experiment_registry_path = repository_root / "EXPERIMENT_REGISTRY.jsonl"
    proof_registry_path = repository_root / "PROOF_LEDGER.jsonl"
    accounting = derive_trial_accounting(
        experiment_registry_path,
        identity.candidate_id,
        identity.frozen_specification_hash,
        evaluated_at,
    )
    proof_records, proof_registry_hash = _candidate_proofs(
        proof_registry_path,
        selector,
    )
    target_index = LEVELS.index(target_level)
    reasons: list[str] = []
    if target_index == 0:
        return (), accounting, proof_records, proof_registry_hash
    reasons.extend(
        _candidate_author_conflict_reasons(
            identity.candidate_author_id,
            dynamic_state,
        )
    )
    if accounting.unresolved > 0:
        reasons.append("trial_accounting_incomplete")
    external_anchor_verified = (
        audit_result.get("external_anchor_verified") is True
        and dynamic_state.get("external_anchor_verified") is True
    )
    authenticated_proofs, authentication_reasons = _authenticated_stage_proofs(
        proof_records,
        experiment_registry_path,
        selector,
        external_anchor_verified,
        repository_root,
        AUTHENTICATED_STAGE_PROOF_TYPES,
    )
    reasons.extend(authentication_reasons)
    if not external_anchor_verified:
        reasons.append("external_dynamic_state_anchor_not_verified")
    negative_control_gate = evaluate_negative_controls(
        _negative_control_results(authenticated_proofs),
        policy.required_negative_controls,
        identity.candidate_author_id,
    )
    if not negative_control_gate.passed:
        reasons.append("negative_control_gate_blocked")
        reasons.extend(negative_control_gate.reason_codes)
    reasons.extend(_stress_matrix_reasons(authenticated_proofs))
    if not any(
        record.get("proof_type") == "development" and record.get("passed") is True
        for record in authenticated_proofs
    ):
        reasons.append("development_evidence_missing")
    if accounting.registered == 0:
        reasons.append("no_registered_substantive_trials")
    if accounting.completed == 0:
        reasons.append("no_completed_substantive_trials")
    if target_index >= LEVELS.index("L2"):
        passed_domains = {
            str(record.get("review_domain"))
            for record in authenticated_proofs
            if record.get("proof_type") == "red_team"
            and record.get("passed") is True
            and record.get("review_domain")
        }
        reasons.extend(
            f"missing_red_team:{team}"
            for team in sorted(policy.required_red_teams.difference(passed_domains))
        )
    if target_index >= LEVELS.index("L3") and not any(
        record.get("proof_type") == "clean_room_replication"
        and record.get("passed") is True
        for record in authenticated_proofs
    ):
        reasons.append("clean_room_replication_missing")
    if target_index >= LEVELS.index("L4"):
        if (
            audit_result.get("certification_eligible") is not True
            or dynamic_state.get("certification_eligible") is not True
        ):
            reasons.append("dynamic_state_not_certification_eligible")
        reasons.extend(
            _sealed_budget_reasons(
                repository_root / "HOLDOUT_BUDGET.json",
                selector,
                proof_records,
                policy,
                repository_root,
            )
        )
    if target_index >= LEVELS.index("L5"):
        reasons.extend(
            _forward_reasons(
                repository_root / "shadow_trading" / "FORWARD_EVIDENCE.jsonl",
                selector,
                policy,
                identity.candidate_mode,
                cast(str, identity.frozen_specification["candidate_genome_hash"]),
            )
        )
    return tuple(sorted(set(reasons))), accounting, proof_records, proof_registry_hash


def _evaluate_promotion_for_root(
    evidence: PromotionEvidence,
    policy: PromotionPolicy,
    repository_root: Path,
) -> PromotionDecision:
    return _evaluate_promotion_for_root_with_audit_runner(
        evidence,
        policy,
        repository_root,
        _run_full_canonical_audit,
    )


def _evaluate_promotion_for_root_with_external_root(
    evidence: PromotionEvidence,
    policy: PromotionPolicy,
    repository_root: Path,
    external_trust_root_path: Path,
) -> PromotionDecision:
    return _evaluate_promotion_for_root_with_audit_runner(
        evidence,
        policy,
        repository_root,
        _external_root_audit_runner(external_trust_root_path),
    )


def _evaluate_promotion_for_root_with_audit_runner(
    evidence: PromotionEvidence,
    policy: PromotionPolicy,
    repository_root: Path,
    audit_runner: CanonicalAuditRunner,
) -> PromotionDecision:
    if policy != v1_promotion_policy():
        raise ValueError("promotion policy must be derived from frozen Ascendancy v1 policy")
    if not evidence.candidate_id or not evidence.candidate_author_id:
        raise ValueError("promotion request identity is incomplete")
    require_utc_iso(evidence.frozen_at)
    require_utc_iso(evidence.evaluated_at)
    require_sha256(evidence.frozen_specification_hash, "frozen_specification_hash")
    if parse_utc(evidence.evaluated_at) < parse_utc(evidence.frozen_at):
        raise ValueError("promotion evaluation cannot precede candidate freeze")
    current_utc = datetime.now(timezone.utc)
    if parse_utc(evidence.evaluated_at) > current_utc:
        raise ValueError("promotion evaluation timestamp cannot be future-dated")
    root = repository_root.resolve(strict=True)
    audit_result, dynamic_state = audit_runner(root)
    audit_snapshot_hash = _canonical_audit_snapshot_hash(audit_result, dynamic_state)
    identity = canonical_candidate_identity(
        root / "CANDIDATE_LINEAGE.jsonl",
        evidence.candidate_id,
    )
    if parse_utc(evidence.evaluated_at) < parse_utc(identity.frozen_at):
        raise ValueError("promotion evaluation cannot precede canonical candidate freeze")
    canonical_selector = PromotionEvidence(
        identity.candidate_id,
        identity.candidate_author_id,
        "L0",
        evidence.requested_level,
        identity.frozen_at,
        identity.frozen_specification_hash,
        evidence.evaluated_at,
    )
    proof_records, _ = _candidate_proofs(
        root / "PROOF_LEDGER.jsonl",
        canonical_selector,
    )
    promotion_state = canonical_promotion_state(
        proof_records,
        identity,
        evidence.evaluated_at,
        root,
    )
    bound_evidence = PromotionEvidence(
        identity.candidate_id,
        identity.candidate_author_id,
        promotion_state.current_level,
        evidence.requested_level,
        identity.frozen_at,
        identity.frozen_specification_hash,
        evidence.evaluated_at,
    )
    gate_reasons, accounting, _, proof_registry_hash = _cumulative_promotion_gate_state(
        root,
        identity,
        bound_evidence.requested_level,
        bound_evidence.evaluated_at,
        audit_result,
        dynamic_state,
        policy,
    )
    reasons: list[str] = list(gate_reasons)
    if evidence.candidate_author_id != identity.candidate_author_id:
        reasons.append("candidate_author_identity_mismatch")
    if evidence.frozen_at != identity.frozen_at:
        reasons.append("candidate_freeze_time_identity_mismatch")
    if evidence.frozen_specification_hash != identity.frozen_specification_hash:
        reasons.append("frozen_specification_identity_mismatch")
    if evidence.current_level != promotion_state.current_level:
        reasons.append("current_level_not_canonical")
    current_index = LEVELS.index(promotion_state.current_level)
    requested_index = LEVELS.index(bound_evidence.requested_level)
    if requested_index != current_index + 1:
        reasons.append("promotion_must_advance_exactly_one_level")
    _assert_canonical_audit_snapshot_unchanged_with_runner(
        root,
        audit_snapshot_hash,
        audit_runner,
    )
    return PromotionDecision(
        allowed=not reasons,
        current_level=promotion_state.current_level,
        requested_level=bound_evidence.requested_level,
        reason_codes=tuple(sorted(set(reasons))),
        paper_only=True,
        live_blocked=True,
        trial_accounting=accounting,
        proof_registry_hash=proof_registry_hash,
        dynamic_state_hash=str(dynamic_state["dynamic_state_hash"]),
        audit_snapshot_hash=audit_snapshot_hash,
    )


def evaluate_promotion(
    evidence: PromotionEvidence,
    policy: PromotionPolicy,
) -> PromotionDecision:
    return _evaluate_promotion_for_root(
        evidence,
        policy,
        _canonical_repository_root(),
    )


def evaluate_promotion_with_external_root(
    evidence: PromotionEvidence,
    policy: PromotionPolicy,
    external_trust_root_path: Path,
) -> PromotionDecision:
    return _evaluate_promotion_for_root_with_external_root(
        evidence,
        policy,
        _canonical_repository_root(),
        external_trust_root_path,
    )
