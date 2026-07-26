"""Typed autonomous admissibility models for machine-only source decisions."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .autonomy_common import RUN_ID, SafetyDecision, stable_hash


@dataclass(frozen=True)
class AutonomousAdmissibilityInput:
    source_id: str
    source_name: str
    source_family: str
    license_id: str
    source_url: str
    machine_readable_license: bool
    machine_readable_terms: bool
    credentials_required: bool
    paid_or_proprietary: bool
    broker_or_live_source: bool
    scrape_only: bool
    explicit_scrape_permission: bool
    sample_or_fixture: bool
    suspicious: bool
    provenance_url: str
    direct_download_url: str
    adjusted_close_semantics_known: bool

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["admissibility_version"] = RUN_ID
        record["input_hash"] = stable_hash(record)
        return record


@dataclass(frozen=True)
class AutonomousSourceAdmissibilityRecord:
    source_id: str
    source_name: str
    source_family: str
    source_url: str
    decision: SafetyDecision
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["artifact_type"] = "autonomous_source_admissibility_record"
        record["admissibility_version"] = RUN_ID
        record["source_hash"] = stable_hash(record)
        return record


@dataclass(frozen=True)
class AutonomousLicenseAdmissibilityRecord:
    source_id: str
    license_id: str
    license_known: bool
    license_machine_verified: bool
    license_decision: SafetyDecision
    copyleft_reference_only: bool
    reason_codes: list[str]

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["artifact_type"] = "autonomous_license_admissibility_record"
        record["admissibility_version"] = RUN_ID
        record["license_hash"] = stable_hash(record)
        return record


@dataclass(frozen=True)
class AutonomousProvenanceAdmissibilityRecord:
    source_id: str
    source_url: str
    provenance_url: str
    provenance_machine_verified: bool
    no_credentials: bool
    not_broker_or_live: bool
    not_sample_or_fixture: bool
    reason_codes: list[str]

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["artifact_type"] = "autonomous_provenance_admissibility_record"
        record["admissibility_version"] = RUN_ID
        record["provenance_hash"] = stable_hash(record)
        return record


@dataclass(frozen=True)
class AutonomousDataAdmissibilityDecision:
    source_id: str
    decision: SafetyDecision
    evidence_allowed: bool
    ingest_allowed: bool
    fetch_allowed: bool
    reason_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["artifact_type"] = "autonomous_data_admissibility_decision"
        record["admissibility_version"] = RUN_ID
        record["decision_hash"] = stable_hash(record)
        return record


@dataclass(frozen=True)
class AutonomousRepoAdmissibilityDecision:
    source_id: str
    decision: SafetyDecision
    import_mode: str
    repo_allowed_as_reference: bool
    repo_allowed_as_adapter_candidate: bool
    repo_allowed_as_sandbox_candidate: bool
    reason_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["artifact_type"] = "autonomous_repo_admissibility_decision"
        record["admissibility_version"] = RUN_ID
        record["decision_hash"] = stable_hash(record)
        return record


@dataclass(frozen=True)
class AutonomousAdmissibilityQualityFlag:
    flag_id: str
    source_id: str
    severity: str
    reason_code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["artifact_type"] = "autonomous_admissibility_quality_flag"
        record["admissibility_version"] = RUN_ID
        record["flag_hash"] = stable_hash(record)
        return record


@dataclass(frozen=True)
class AutonomousAdmissibilityProofRecord:
    proof_id: str
    accepted_count: int
    rejected_count: int
    quarantined_count: int
    terminal_block_count: int
    no_manual_review_status_emitted: bool
    no_human_review_required: bool
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["artifact_type"] = "autonomous_admissibility_proof"
        record["admissibility_version"] = RUN_ID
        record["proof_hash"] = stable_hash(record)
        return record
