"""Deterministic offline meta-governor data models (paper-only, fixture-only).

These dataclasses describe a paper-only proof-weighted governance layer. They never emit a
live promotion, real capital decision, or broker action. All scores are deterministic
fixture math aggregated from existing DOPEY evidence registries.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


META_GOVERNOR_VERSION = "dopey-offline-meta-governor-v1"

# Allowed paper/research tiers (best -> worst within a run).
ALLOWED_TIERS = [
    "offline_mutation_champion",
    "paper_champion",
    "offline_ensemble_member",
    "paper_candidate",
    "paper_watchlist",
    "research_only",
    "quarantine",
    "rejected",
]

TIER_RANK = {tier: i for i, tier in enumerate(ALLOWED_TIERS)}

# Forbidden live tiers — must never be emitted.
FORBIDDEN_LIVE_TIERS = frozenset({
    "live_candidate",
    "micro_live",
    "adaptive_live",
    "real_capital",
    "broker_enabled",
})

# Allowed meta-governor decisions (all paper/research governance only).
ALLOWED_DECISIONS = frozenset({
    "promote_to_paper_watchlist",
    "promote_to_paper_candidate",
    "promote_to_paper_champion",
    "mark_offline_ensemble_member",
    "mark_offline_mutation_champion",
    "hold_research_only",
    "reduce_paper_attention",
    "starve_weak_signal",
    "quarantine_overfit",
    "reject_unsafe",
    "request_more_fixture_evidence",
})

FORBIDDEN_DECISIONS = frozenset({
    "live_candidate",
    "micro_live",
    "adaptive_live",
    "real_capital",
    "broker_order",
    "enable_live",
})


@dataclass
class EvidenceLayerScore:
    layer_name: str
    score: float = 0.0
    confidence: float = 0.0
    freshness: str = "missing"
    coverage: float = 0.0
    contradiction_pressure: float = 0.0
    known_limitations: list[str] = field(default_factory=list)
    status: str = "missing"  # strong | adequate | weak | missing

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StrategyProofProfile:
    strategy_id: str
    strategy_family: str
    current_score: float = 0.0
    score_trend: float = 0.0
    best_score: float = 0.0
    walk_forward_consistency: float = 0.0
    ensemble_weight: float = 0.0
    failure_pressure: float = 0.0
    overfit_level: str = "unknown"
    overfit_rank: int = 3
    liquidity_robustness: float = 0.0
    slippage_robustness: float = 0.0
    greek_fit: float = 0.0
    iv_surface_fit: float = 0.0
    macro_fit: float = 0.0
    pattern_fit: float = 0.0
    mutation_improvement: float = 0.0
    promotion_state: str = "entrant"
    source_type: str = "tournament"
    paper_only: bool = True
    best_regimes: list[str] = field(default_factory=list)
    worst_regimes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FamilyTrustProfile:
    strategy_family: str
    trust_score: float = 0.0
    best_regimes: list[str] = field(default_factory=list)
    worst_regimes: list[str] = field(default_factory=list)
    overfit_pressure: float = 0.0
    failure_pressure: float = 0.0
    liquidity_pressure: float = 0.0
    greek_iv_pressure: float = 0.0
    macro_pressure: float = 0.0
    recommended_attention: str = "research_only"
    allowed_mutation_intensity: str = "low"
    constraints: list[str] = field(default_factory=list)
    ensemble_weight: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RegimeTrustProfile:
    regime_tag: str
    regime_class: str = "macro_contradiction"
    preferred_families: list[str] = field(default_factory=list)
    penalized_families: list[str] = field(default_factory=list)
    starve_families: list[str] = field(default_factory=list)
    dominant_failure_modes: list[str] = field(default_factory=list)
    required_evidence_layers: list[str] = field(default_factory=list)
    trust_score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PromotionEligibilityProfile:
    strategy_id: str
    strategy_family: str
    eligible_tier: str = "research_only"
    blocked_tiers: list[str] = field(default_factory=list)
    required_missing_evidence: list[str] = field(default_factory=list)
    disqualifying_failures: list[str] = field(default_factory=list)
    proof_strength: float = 0.0
    risk_pressure: float = 0.0
    paper_only: bool = True
    live_blocked: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MetaGovernorDecision:
    strategy_id: str
    strategy_family: str
    decision: str = "hold_research_only"
    eligible_tier: str = "research_only"
    proof_strength: float = 0.0
    risk_pressure: float = 0.0
    reason_codes: list[str] = field(default_factory=list)
    required_missing_evidence: list[str] = field(default_factory=list)
    disqualifying_failures: list[str] = field(default_factory=list)
    paper_only: bool = True
    live_allowed: bool = False
    live_migration_conditions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MetaGovernorRunResult:
    meta_governor_status: str = "ok"
    mode: str = "RESEARCH"
    live_trading_enabled: bool = False
    strategies_evaluated: int = 0
    families_evaluated: int = 0
    paper_champions: list[str] = field(default_factory=list)
    offline_ensemble_members: list[str] = field(default_factory=list)
    offline_mutation_champions: list[str] = field(default_factory=list)
    quarantined: list[str] = field(default_factory=list)
    starved: list[str] = field(default_factory=list)
    research_only: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    forbidden_live_decisions_emitted: list[str] = field(default_factory=list)
    live_blocked: bool = True
    safety_state: dict = field(default_factory=dict)
    reproducibility_hash: str = ""
    registry_path: str = ""
    decisions_path: str = ""
    proof_record_path: str = ""
    summary_path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def assert_decision_safe(decision: str) -> None:
    if decision in FORBIDDEN_DECISIONS:
        raise ValueError(f"forbidden live meta-governor decision emitted: {decision}")
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(f"unknown meta-governor decision: {decision}")


def assert_tier_safe(tier: str) -> None:
    if tier in FORBIDDEN_LIVE_TIERS:
        raise ValueError(f"forbidden live promotion tier emitted: {tier}")
    if tier not in ALLOWED_TIERS:
        raise ValueError(f"unknown promotion tier: {tier}")
