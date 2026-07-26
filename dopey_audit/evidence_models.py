"""Audit data models for the offline evidence replay audit harness (paper-only)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


AUDIT_HARNESS_VERSION = "dopey-offline-evidence-replay-audit-v2"

# Audit verdicts.
AUDIT_VERDICTS = [
    "pass",
    "pass_with_notes",
    "warning",
    "fail_reproducibility",
    "fail_safety",
    "fail_schema",
    "fail_missing_evidence",
]

FINDING_SEVERITIES = ["info", "warning", "error", "safety_error"]

# Forbidden live tokens/decisions that must never appear as an *active* decision.
FORBIDDEN_LIVE_TOKENS = frozenset({
    "live_candidate",
    "micro_live",
    "adaptive_live",
    "real_capital",
    "broker_order",
    "enable_live",
    "live_allocate",
    "funded_execution",
})

ALLOWED_NEXT_BUILD_TARGETS = [
    "stronger_walk_forward_consistency_expansion",
    "larger_regime_holdout_corpus",
    "tournament_performance_reporting_dashboard_artifacts",
    "broker_capability_detector_hardening",
    "deterministic_sector_peer_fundamental_fixture_expansion",
    "artifact_compaction_export_verifier",
    "larger_offline_mutation_population_v2",
    "offline_cross_family_specialist_mutator",
    "deterministic_cross_asset_fixture_expansion",
    "export_bundle_review_assistant_artifacts",
    "DOPEY_STATISTICAL_TRUTH_LAYER_V1",
    "DOPEY_FITNESS_FUNCTION_REPLACEMENT_V1",
    "DOPEY_REAL_DATA_INGESTION_PLAN_V1",
    "DOPEY_LOCAL_OHLCV_IMPORT_VALIDATOR_V1",
    "DOPEY_LOCAL_FREE_OHLCV_IMPORT_VALIDATOR_AND_HISTORY_ACTIVATION_STACK_V1",
    "DOPEY_MANUAL_REAL_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1",
    "DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_V1",
    "DOPEY_MANUAL_STAGE_FREE_OHLCV_FILES_AND_RERUN_VALIDATOR",
    "DOPEY_OPERATOR_STAGE_REVIEWED_FREE_OHLCV_FILES",
    "DOPEY_OPERATOR_FINALIZE_REAL_DATA_MANIFEST_AND_RERUN_VALIDATOR",
    "DOPEY_REPAIR_REAL_OHLCV_HISTORY_ACTIVATION",
    "DOPEY_REAL_OHLCV_SIGNAL_BACKTESTER_V1",
    "DOPEY_AUTONOMOUS_OPEN_DATA_SOURCE_EXPANSION_V1",
    "DOPEY_MODEL_PRICED_OPTIONS_RESEARCH_EXPANSION_V1",
    "DOPEY_MODEL_PRICED_OPTIONS_RESEARCH_EXPANSION_V2",
    "DOPEY_ACCEPTED_OHLCV_REAL_SIGNAL_AND_MODEL_PRICED_OPTIONS_BACKTEST_V1",
    "DOPEY_AUTONOMOUS_OPENBB_PROVIDER_EXPANSION_V2",
    "DOPEY_ACCEPTED_OHLCV_MODEL_PRICED_OPTIONS_RESEARCH_V1",
    "DOPEY_PAPER_ONLY_MODEL_PRICED_AUTONOMOUS_ROTATION_HARDENING_V1",
    "DOPEY_REAL_OPTIONS_HONEST_BACKTESTER_V1",
    "DOPEY_PAPER_AUTONOMOUS_ROTATION_ENGINE_V1",
    "DOPEY_PAPER_MONEY_TOURNAMENT_ITERATION_AND_MARKET_EXPANSION_V2",
    "DOPEY_MARKET_DATA_PROVIDER_INSTALL_AND_FALLBACK_EXPANSION_V2",
    "DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1",
    "DOPEY_PUBLIC_PAPER_CHAMPION_HARDENING_AND_DEEP_STRESS_V1",
    "DOPEY_PUBLIC_CHAMPION_REPAIR_AND_RETUNE_V1",
    "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V1",
    "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V2",
    "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V3",
    "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4",
    "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5",
    "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6",
    "DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7",
    "DOPEY_RESEARCH_BREAKTHROUGH_TO_PUBLIC_PAPER_CHAMPION_V1",
    "DOPEY_PUBLIC_FEATURE_MINING_EXPANSION_V2",
    "DOPEY_AUDIT_EXPORT_REPAIR_V1",
    "DOPEY_ACTIVE_POLICY_ARTIFACT_CHAIN_REPAIR_V1",
    "DOPEY_PUBLIC_DATA_PROVIDER_DEEP_REPAIR_V3",
    "DOPEY_PUBLIC_MARKET_SIGNAL_MUTATION_DEEPENING_V2",
    "DOPEY_LIVE_GATE_CANDIDATE_REVIEW_AND_PAPER_CHAMPION_HARDENING_V1",
]


# ---------------------------------------------------------------------------
# Workstream A — evidence inventory models
# ---------------------------------------------------------------------------

@dataclass
class EvidenceRecordPointer:
    artifact_type: str
    path: str
    record_index: int = -1   # -1 means latest
    run_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceArtifact:
    artifact_type: str
    path: str
    exists: bool = False
    record_count: int = 0
    latest_run_id: str = ""
    hash: str = ""
    model_version: str = ""
    safety_state: dict = field(default_factory=dict)
    status: str = "missing"          # present | empty | stale | missing | parse_error
    parse_status: str = "not_loaded"  # ok | json_error | not_loaded
    missing_required_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceRecordDigest:
    artifact_type: str
    path: str
    record_index: int
    record_hash: str
    reproducibility_hash: str = ""
    run_id: str = ""
    final_status: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceInventory:
    artifacts: list[EvidenceArtifact] = field(default_factory=list)
    record_digests: list[EvidenceRecordDigest] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "artifacts": [a.to_dict() for a in self.artifacts],
            "record_digests": [d.to_dict() for d in self.record_digests],
            "artifact_count": len(self.artifacts),
            "present_count": sum(1 for a in self.artifacts if a.status == "present"),
            "missing_count": sum(1 for a in self.artifacts if a.status == "missing"),
            "empty_count": sum(1 for a in self.artifacts if a.status == "empty"),
            "total_records": sum(a.record_count for a in self.artifacts),
        }


@dataclass
class EvidenceCompletenessReport:
    expected_artifacts: int = 0
    present_artifacts: int = 0
    missing_artifacts: list[str] = field(default_factory=list)
    empty_artifacts: list[str] = field(default_factory=list)
    completeness_fraction: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceFreshnessReport:
    stale_artifacts: list[str] = field(default_factory=list)
    missing_run_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Workstream B — replay/hash audit models
# ---------------------------------------------------------------------------

@dataclass
class ReplayAuditCase:
    case_id: str
    artifact_type: str
    audit_kind: str               # hash | score | schema
    expected: str = ""
    recomputed: str = ""
    passed: bool = True
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScoreDriftFinding:
    case_id: str
    field: str
    stored: float
    recomputed: float
    delta: float
    severity: str = "warning"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HashDriftFinding:
    case_id: str
    artifact_type: str
    stored_hash: str
    recomputed_hash: str
    severity: str = "error"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SchemaDriftFinding:
    case_id: str
    artifact_type: str
    missing_fields: list[str]
    severity: str = "warning"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReplayAuditResult:
    cases: list[ReplayAuditCase] = field(default_factory=list)
    hash_findings: list[HashDriftFinding] = field(default_factory=list)
    score_findings: list[ScoreDriftFinding] = field(default_factory=list)
    schema_findings: list[SchemaDriftFinding] = field(default_factory=list)
    verdict: str = "pass"

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "cases": [c.to_dict() for c in self.cases],
            "hash_findings": [f.to_dict() for f in self.hash_findings],
            "score_findings": [f.to_dict() for f in self.score_findings],
            "schema_findings": [f.to_dict() for f in self.schema_findings],
            "case_count": len(self.cases),
            "hash_mismatches": len(self.hash_findings),
            "score_drift_findings": len(self.score_findings),
            "schema_warnings": len(self.schema_findings),
        }


# ---------------------------------------------------------------------------
# Workstream C — consistency audit models
# ---------------------------------------------------------------------------

@dataclass
class ConsistencyCheck:
    check_id: str
    description: str
    passed: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConsistencyFinding:
    check_id: str
    severity: str = "info"
    message: str = ""
    referenced_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CrossLayerConsistencyReport:
    checks: list[ConsistencyCheck] = field(default_factory=list)
    findings: list[ConsistencyFinding] = field(default_factory=list)
    consistency_errors: int = 0
    safety_errors: int = 0

    def to_dict(self) -> dict:
        return {
            "checks": [c.to_dict() for c in self.checks],
            "findings": [f.to_dict() for f in self.findings],
            "consistency_errors": self.consistency_errors,
            "safety_errors": self.safety_errors,
            "info_findings": sum(1 for f in self.findings if f.severity == "info"),
            "warning_findings": sum(1 for f in self.findings if f.severity == "warning"),
        }


# ---------------------------------------------------------------------------
# Workstream E — evidence gap planner models
# ---------------------------------------------------------------------------

@dataclass
class EvidenceGap:
    gap_id: str
    category: str
    severity: str = "warning"
    message: str = ""
    affected_families: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NextProofPriority:
    priority_id: str
    gap_category: str
    rank: int
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AuditRecommendedBuildTarget:
    target: str
    rationale: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AuditRunResult:
    audit_status: str = "ok"
    mode: str = "RESEARCH"
    live_trading_enabled: bool = False
    artifacts_scanned: int = 0
    records_scanned: int = 0
    replay_cases_run: int = 0
    hash_mismatches: int = 0
    score_drift_findings: int = 0
    schema_warnings: int = 0
    consistency_errors: int = 0
    safety_errors: int = 0
    forbidden_live_decisions_active: int = 0
    evidence_gaps: int = 0
    top_next_proof_priority: str = ""
    live_blocked: bool = True
    verdict: str = "pass"
    safety_state: dict = field(default_factory=dict)
    reproducibility_hash: str = ""
    audit_registry_path: str = ""
    audit_summary_path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
