"""Typed models for DOPEY static reporting dashboard artifacts.

All models are offline, fixture-only, paper-only records. They do not represent live
performance evidence and never authorize broker execution.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


REPORTING_BUNDLE_VERSION = "dopey-tournament-performance-reporting-dashboard-v1"
REPORTING_DASHBOARD_INDEX_VERSION = "dopey-reporting-dashboard-index-v1"


@dataclass(frozen=True)
class EvidenceLayerExplanation:
    layer_name: str
    supports: list[str]
    contradicts: list[str]
    score_contribution: float
    confidence: float
    known_limitations: list[str]
    artifact_paths: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StrategyReportCard:
    strategy_id: str
    strategy_family: str
    promotion_state: str
    tournament_score: float
    walk_forward_consistency_score: float
    corpus_v2_score: float
    macro_fit_score: float
    iv_surface_fit_score: float
    greek_fit_score: float
    fundamental_fit_score: float
    liquidity_robustness_score: float
    slippage_robustness_score: float
    pattern_score: float
    failure_pressure_score: float
    overfit_level: str
    ensemble_weight: float
    meta_governor_decision: str
    top_supporting_evidence: list[str]
    top_contradicting_evidence: list[str]
    top_failure_modes: list[str]
    best_regimes: list[str]
    worst_regimes: list[str]
    paper_only: bool
    live_allowed: bool
    summary_decision: str
    score_table: dict[str, float]
    evidence_support: list[EvidenceLayerExplanation]
    evidence_contradiction: list[EvidenceLayerExplanation]
    scenario_explanations: list[str]
    known_limitations: list[str]
    reproducibility_hash: str

    def to_dict(self) -> dict:
        record = asdict(self)
        record["evidence_support"] = [e.to_dict() for e in self.evidence_support]
        record["evidence_contradiction"] = [e.to_dict() for e in self.evidence_contradiction]
        return record


@dataclass(frozen=True)
class FamilyReportCard:
    strategy_family: str
    family_rank: int
    best_strategy: str
    average_score: float
    best_regimes: list[str]
    worst_regimes: list[str]
    family_strengths: list[str]
    family_weaknesses: list[str]
    overfit_pressure: float
    failure_pressure: float
    liquidity_pressure: float
    macro_pressure: float
    iv_pressure: float
    fundamental_pressure: float
    recommended_research_action: str
    summary_decision: str
    score_table: dict[str, float]
    paper_only: bool
    live_allowed: bool
    known_limitations: list[str]
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ScenarioReportCard:
    scenario_id: str
    scenario_type: str
    source_layer: str
    preferred_families: list[str]
    penalized_families: list[str]
    winning_strategy: str
    losing_strategy: str
    dominant_failure_modes: list[str]
    explanation: str
    safety_note: str
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RegimeReportCard:
    regime_id: str
    regime_type: str
    source_layer: str
    preferred_families: list[str]
    penalized_families: list[str]
    winning_strategy: str
    failing_strategy: str
    primary_failure_mode: str
    score_movement_explanation: str
    safety_note: str
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PerformanceAttributionSummary:
    record_id: str
    strategy_id: str
    strategy_family: str
    tournament_baseline: float
    walk_forward_consistency: float
    corpus_v2_holdout: float
    mutation_delta: float
    failure_feedback: float
    ensemble_allocation: float
    meta_governor_trust: float
    macro_fit: float
    iv_surface_skew_term_fit: float
    greeks_fit: float
    liquidity_slippage: float
    sector_peer_fundamental_fit: float
    pattern_confirmation: float
    overfit_penalty: float
    failure_pressure: float
    top_positive_drivers: list[str]
    top_negative_drivers: list[str]
    unexplained_residual: float
    deterministic_hash: str
    paper_only: bool
    live_allowed: bool
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DashboardArtifactIndex:
    reporting_dashboard_index_version: str
    reporting_bundle_version: str
    top_strategies: list[str]
    family_rankings: list[dict]
    scenario_summaries: list[dict]
    evidence_layer_summaries: list[dict]
    audit_status: str
    safety_status: dict
    artifact_paths: dict[str, str]
    reproducibility_hashes: dict[str, str]
    known_gaps: list[str]
    next_recommended_build_targets: list[str]
    fixture_only: bool
    paper_only: bool
    live_allowed: bool
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReportingBundleResult:
    reporting_bundle_status: str
    mode: str
    live_trading_enabled: bool
    strategies_reported: int
    families_reported: int
    scenarios_reported: int
    attribution_records: int
    dashboard_artifacts_written: list[str]
    top_strategy: str
    top_family: str
    audit_status: str
    live_blocked: bool
    dashboard_index_path: str
    proof_record_path: str
    safety_state: dict
    reproducibility_hash: str

    def to_dict(self) -> dict:
        return asdict(self)
