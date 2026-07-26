"""Typed models for deterministic DOPEY export bundle review artifacts."""
from __future__ import annotations

from dataclasses import asdict, dataclass


EXPORT_REVIEW_VERSION = "dopey-export-bundle-review-assistant-v1"
NEXT_REVIEW_BUILD_TARGET = "DOPEY_MANUAL_STAGE_FREE_OHLCV_FILES_AND_RERUN_VALIDATOR"
FINDING_SEVERITIES = ["info", "note", "warning", "error", "safety_error"]
FINDING_CATEGORIES = [
    "manifest",
    "copy_proof",
    "hash",
    "safety",
    "credential_scan",
    "audit",
    "reporting",
    "strategy_evidence",
    "family_evidence",
    "scenario_evidence",
    "gap",
    "known_limitation",
    "data_ingestion",
    "open_source_free_data",
    "local_free_ohlcv_stack",
    "manual_ohlcv_staging",
    "operator_reviewed_ohlcv_stage",
    "open_source_autonomy",
    "open_data_breakthrough",
    "finish_everything_openbb",
    "wealth_engine",
    "market_provider_expansion",
    "public_champion_evolution",
    "public_signal_research_breakthrough_v7",
    "next_step",
]


@dataclass(frozen=True)
class ExportReviewFinding:
    finding_id: str
    severity: str
    category: str
    artifact_path: str
    summary: str
    evidence: dict
    recommended_action: str
    paper_only: bool
    live_related: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExportReviewPriority:
    priority_id: str
    rank: int
    artifact_path: str
    reason: str
    severity: str
    recommended_action: str
    reviewer_note: str
    category: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExportReviewChecklist:
    checklist_id: str
    source_bundle_id: str
    sections: list[dict]
    safety_state: dict
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExportReviewEvidenceMap:
    map_id: str
    source_bundle_id: str
    source_export_path: str
    report_to_source_artifacts: list[dict]
    dashboard_to_source_artifacts: list[dict]
    strategy_to_evidence_layers: list[dict]
    family_to_evidence_layers: list[dict]
    manifest_to_exported_files: list[dict]
    copy_proof_to_target_files: list[dict]
    audit_to_artifact_specs: list[dict]
    missing_references: list[dict]
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExportReviewDecision:
    decision_id: str
    source_bundle_id: str
    decision: str
    suitability: str
    reasons: list[str]
    limitations: list[str]
    next_build_target: str
    paper_only: bool
    live_blocked: bool
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExportReviewBundle:
    review_id: str
    source_bundle_id: str
    source_export_path: str
    manifest_path: str
    copy_proof_path: str
    artifact_count: int
    total_size_bytes: int
    hash_status: str
    copy_status: str
    safety_status: str
    credential_scan_status: str
    active_forbidden_live_decisions: int
    review_artifact_paths: list[str]
    recommended_review_order: list[str]
    known_gaps: list[str]
    next_build_target: str
    paper_only: bool
    live_blocked: bool
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExportReviewRunResult:
    review_status: str
    mode: str
    live_trading_enabled: bool
    source_bundle_id: str
    source_export_path: str
    shared_export_path: str
    artifact_count: int
    manifest_status: str
    copy_proof_status: str
    hash_status: str
    safety_status: str
    credential_status: str
    active_forbidden_live_decisions: int
    findings_count: int
    safety_errors: int
    warnings: int
    review_artifacts_written: list[str]
    review_registry_path: str
    executive_summary_path: str
    checklist_path: str
    evidence_map_path: str
    priority_queue_path: str
    safety_summary_path: str
    proof_record_path: str
    live_blocked: bool
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)
