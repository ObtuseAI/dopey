"""Deterministic offline ensemble allocator data models (paper-only, fixture-only).

These dataclasses describe a paper-only simulated allocation layer. They never touch real
capital, broker order sizing, or live execution. All scores are deterministic fixture math.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


FORBIDDEN_ALLOCATION_DECISIONS = frozenset({
    "live_allocate",
    "micro_live",
    "adaptive_live",
    "real_capital",
    "broker_order",
})

ALLOWED_ALLOCATION_DECISIONS = frozenset({
    "increase_paper_attention",
    "hold_paper_attention",
    "reduce_paper_attention",
    "starve_weak_signal",
    "quarantine_overfit",
    "research_only",
    "reject",
})


@dataclass
class StrategyAllocationCandidate:
    strategy_id: str
    strategy_family: str
    source_type: str                       # tournament | mutation | feedback | champion
    base_score: float = 0.0
    walk_forward_score: float = 0.0
    analysis_fusion_score: float = 0.0
    macro_fit_score: float = 0.0
    iv_surface_fit_score: float = 0.0
    greek_fit_score: float = 0.0
    liquidity_robustness_score: float = 0.0
    slippage_robustness_score: float = 0.0
    pattern_score: float = 0.0
    failure_pressure_score: float = 0.0
    overfit_level: str = "unknown"
    overfit_rank: int = 0
    mutation_delta: float = 0.0
    promotion_state: str = "entrant"
    paper_only: bool = True
    holdout_score: float = 0.0
    consistency_score: float = 0.0
    consistency_verdict: str = ""
    corpus_v2_consistency_score: float = 0.0
    corpus_v2_consistency_verdict: str = ""
    best_regimes: list[str] = field(default_factory=list)
    worst_regimes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FamilyAllocationProfile:
    strategy_family: str
    candidate_count: int = 0
    best_score: float = 0.0
    median_score: float = 0.0
    family_weight: float = 0.0
    top_strategy_id: str = ""
    overfit_level: str = "unknown"
    regime_specialist: bool = False
    all_weather: bool = False
    failure_pressure_score: float = 0.0
    best_regimes: list[str] = field(default_factory=list)
    worst_regimes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RegimeAllocationProfile:
    regime_tag: str
    preferred_families: list[str] = field(default_factory=list)
    penalized_families: list[str] = field(default_factory=list)
    starve_families: list[str] = field(default_factory=list)
    family_preference_multiplier: dict[str, float] = field(default_factory=dict)
    regime_notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AllocationScoreBreakdown:
    strategy_id: str
    proof_component: float = 0.0
    regime_component: float = 0.0
    liquidity_component: float = 0.0
    greek_iv_component: float = 0.0
    macro_component: float = 0.0
    pattern_component: float = 0.0
    failure_penalty: float = 0.0
    overfit_penalty: float = 0.0
    mutation_bonus: float = 0.0
    diversification_component: float = 0.0
    overall_score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    def component_sum(self) -> float:
        return round(
            self.proof_component
            + self.regime_component
            + self.liquidity_component
            + self.greek_iv_component
            + self.macro_component
            + self.pattern_component
            - self.failure_penalty
            - self.overfit_penalty
            + self.mutation_bonus
            + self.diversification_component,
            6,
        )


@dataclass
class SimulatedAllocationDecision:
    strategy_id: str
    strategy_family: str
    recommended_weight: float = 0.0
    previous_weight: float = 0.0
    weight_delta: float = 0.0
    decision: str = "research_only"
    reason_codes: list[str] = field(default_factory=list)
    paper_only: bool = True
    live_allowed: bool = False
    score_breakdown: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EnsembleAllocationResult:
    allocator_status: str = "ok"
    mode: str = "RESEARCH"
    live_trading_enabled: bool = False
    candidates_loaded: int = 0
    families_allocated: list[str] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    family_profiles: list[dict] = field(default_factory=list)
    regime_profiles: list[dict] = field(default_factory=list)
    top_strategy: str = ""
    top_family: str = ""
    weights_sum: float = 0.0
    live_blocked: bool = True
    safety_state: dict = field(default_factory=dict)
    reproducibility_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EnsembleReplayResult:
    ensemble_variant: str = "allocator_weighted"
    single_champion_score: float = 0.0
    equal_weight_score: float = 0.0
    allocator_weighted_score: float = 0.0
    overfit_adjusted_score: float = 0.0
    best_ensemble_variant: str = "allocator_weighted"
    robustness: float = 0.0
    family_diversification: float = 0.0
    regime_coverage: float = 0.0
    failure_exposure: float = 0.0
    improves_over_champion: bool = False
    paper_only: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EnsembleRobustnessScore:
    mean_score: float = 0.0
    min_score: float = 0.0
    spread: float = 0.0
    drawdown_proxy: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FamilyDiversificationScore:
    families_represented: int = 0
    effective_family_count: float = 0.0
    herfindahl_concentration: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RegimeCoverageScore:
    regimes_covered: int = 0
    regimes_total: int = 0
    coverage_fraction: float = 0.0
    covered_regimes: list[str] = field(default_factory=list)
    uncovered_regimes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CapitalRedeploymentRecommendation:
    recommendation_id: str
    target_strategy_family: str
    target_strategy_id: str
    action: str                              # increase | hold | reduce | starve | quarantine | research_only
    reason_codes: list[str] = field(default_factory=list)
    source_evidence: list[str] = field(default_factory=list)
    failure_mode_evidence: list[str] = field(default_factory=list)
    regime_evidence: list[str] = field(default_factory=list)
    proof_level: str = "paper_only"
    paper_only: bool = True
    live_allowed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def assert_decision_safe(decision: str) -> None:
    if decision in FORBIDDEN_ALLOCATION_DECISIONS:
        raise ValueError(f"forbidden live allocation decision emitted: {decision}")
    if decision not in ALLOWED_ALLOCATION_DECISIONS:
        raise ValueError(f"unknown allocation decision: {decision}")
