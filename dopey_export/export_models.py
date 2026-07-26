"""Typed export verifier models for deterministic DOPEY handoff bundles."""
from __future__ import annotations

from dataclasses import asdict, dataclass


EXPORT_VERIFIER_VERSION = "dopey-artifact-compaction-export-verifier-v1"
DEFAULT_EXPORT_PROFILE = "handoff_shared_folder"
EXPORT_PROFILES = [
    "minimal_proof",
    "reporting_dashboard",
    "full_offline_evidence",
    "handoff_shared_folder",
    "audit_only",
]
FORBIDDEN_ACTIVE_EXPORT_TOKENS = frozenset({
    "live_candidate",
    "micro_live",
    "adaptive_live",
    "real_capital",
    "broker_order",
    "enable_live",
    "live_allocate",
    "funded_execution",
})


@dataclass(frozen=True)
class ExportArtifact:
    artifact_id: str
    artifact_type: str
    source_path: str
    relative_export_path: str
    size_bytes: int
    sha256: str
    record_count: int
    parse_status: str
    required: bool
    safety_scan_status: str
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExportManifest:
    manifest_id: str
    bundle_id: str
    created_at_utc: str
    profile: str
    artifact_count: int
    required_artifacts_present: int
    optional_artifacts_present: int
    total_size_bytes: int
    bundle_sha256: str
    artifacts: list[ExportArtifact]
    safety_state: dict
    reproducibility_hash: str

    def to_dict(self) -> dict:
        record = asdict(self)
        record["artifacts"] = [artifact.to_dict() for artifact in self.artifacts]
        return record


@dataclass(frozen=True)
class ExportProfile:
    profile_name: str
    include_reports: bool
    include_reporting_dashboard: bool
    include_audit: bool
    include_full_evidence: bool
    include_copy_target: bool
    compact_large_ledgers: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExportSelectionRule:
    artifact_id: str
    artifact_type: str
    source_path: str
    relative_export_path: str
    required: bool
    profiles: list[str]
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExportBundlePlan:
    bundle_id: str
    profile: str
    selected_artifacts: list[ExportArtifact]
    missing_required_artifacts: list[str]
    missing_optional_artifacts: list[str]
    skipped_artifacts: list[dict]
    required_artifacts: list[str]
    optional_artifacts: list[str]
    safety_state: dict
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id,
            "profile": self.profile,
            "selected_artifacts": [artifact.to_dict() for artifact in self.selected_artifacts],
            "missing_required_artifacts": self.missing_required_artifacts,
            "missing_optional_artifacts": self.missing_optional_artifacts,
            "skipped_artifacts": self.skipped_artifacts,
            "required_artifacts": self.required_artifacts,
            "optional_artifacts": self.optional_artifacts,
            "safety_state": self.safety_state,
            "reproducibility_hash": self.reproducibility_hash,
        }


@dataclass(frozen=True)
class CompactionPlan:
    bundle_id: str
    profile: str
    source_artifacts: list[ExportArtifact]
    output_dir: str
    jsonl_summary_threshold_bytes: int
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id,
            "profile": self.profile,
            "source_artifacts": [artifact.to_dict() for artifact in self.source_artifacts],
            "output_dir": self.output_dir,
            "jsonl_summary_threshold_bytes": self.jsonl_summary_threshold_bytes,
            "reproducibility_hash": self.reproducibility_hash,
        }


@dataclass(frozen=True)
class CompactedArtifact:
    source_artifact_id: str
    source_path: str
    compacted_path: str
    compaction_method: str
    source_sha256: str
    compacted_sha256: str
    source_size_bytes: int
    compacted_size_bytes: int
    record_count: int
    notes: list[str]
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LedgerCompactionSummary:
    source_path: str
    record_count: int
    first_record_hash: str
    last_record_hash: str
    schema_keys: list[str]
    model_versions_observed: list[str]
    strategy_ids_observed: list[str]
    safety_state_fields_observed: list[str]
    forbidden_live_decision_count: int
    top_level_summary_metrics: dict
    source_sha256: str
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CompactionSummary:
    bundle_id: str
    compacted_artifact_count: int
    compacted_artifacts: list[CompactedArtifact]
    skipped_artifacts: list[dict]
    output_dir: str
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return {
            "bundle_id": self.bundle_id,
            "compacted_artifact_count": self.compacted_artifact_count,
            "compacted_artifacts": [artifact.to_dict() for artifact in self.compacted_artifacts],
            "skipped_artifacts": self.skipped_artifacts,
            "output_dir": self.output_dir,
            "reproducibility_hash": self.reproducibility_hash,
        }


@dataclass(frozen=True)
class ExportSafetyFinding:
    finding_id: str
    severity: str
    artifact_path: str
    reason: str
    token: str
    field_path: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExportSafetyScanResult:
    scan_id: str
    bundle_id: str
    artifacts_scanned: int
    findings: list[ExportSafetyFinding]
    active_forbidden_live_decisions: int
    credential_findings: int
    env_file_findings: int
    verification_blocked: bool
    scan_status: str
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return {
            "scan_id": self.scan_id,
            "bundle_id": self.bundle_id,
            "artifacts_scanned": self.artifacts_scanned,
            "findings": [finding.to_dict() for finding in self.findings],
            "active_forbidden_live_decisions": self.active_forbidden_live_decisions,
            "credential_findings": self.credential_findings,
            "env_file_findings": self.env_file_findings,
            "verification_blocked": self.verification_blocked,
            "scan_status": self.scan_status,
            "reproducibility_hash": self.reproducibility_hash,
        }


@dataclass(frozen=True)
class CopyProof:
    copy_proof_id: str
    bundle_id: str
    source_dir: str
    target_dir: str
    files_expected: int
    files_copied: int
    files_verified: int
    bytes_expected: int
    bytes_verified: int
    hash_mismatches: list[str]
    missing_files: list[str]
    extra_files: list[str]
    verification_status: str
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExportBundleResult:
    export_status: str
    mode: str
    live_trading_enabled: bool
    profile: str
    bundle_id: str
    artifacts_selected: int
    artifacts_exported: int
    compacted_artifacts: int
    total_size_bytes: int
    safety_findings: int
    active_forbidden_live_decisions: int
    credential_findings: int
    local_export_path: str
    shared_export_path: str
    copy_status: str
    files_verified: int
    hash_mismatches: int
    live_blocked: bool
    manifest_path: str
    copy_proof_path: str
    proof_record_path: str
    export_registry_path: str
    export_safety_scan_path: str
    export_verification_path: str
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)
