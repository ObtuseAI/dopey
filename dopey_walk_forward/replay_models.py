"""Dopey walk-forward replay result models (offline, deterministic, paper-only).

ReplayResult: per-window outcome of replaying a StrategyGenome.
WalkForwardScore: aggregate score across all windows.
OverfitSignal: overfit classification (none/low/moderate/high) + reasons.
ReplayVerdict: the overall replay verdict (promoted/research_only/rejected) — paper-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class ReplayResult:
    strategy_id: str
    window_id: str
    window_type: str
    regime_tag: str
    selected_contracts: list[str] = field(default_factory=list)
    paper_intent_id: str = ""
    simulated_fill: float = 0.0
    simulated_exit: float = 0.0
    paper_pnl: float = 0.0
    max_adverse_excursion: float = 0.0
    max_favorable_excursion: float = 0.0
    slippage_score: float = 0.0
    liquidity_score: float = 0.0
    invalidation_triggered: bool = False
    verdict: str = "hold"          # pass | hold | fail (per-window)
    # ---- restored rich replay dimensions (lost in the branch-switch file loss;
    # the tournament runner / evolution tournament aggregate them). All are
    # deterministic fixture measurements, defaulting to honest zeros.
    structure: str = ""
    structure_risk_summary: dict = field(default_factory=dict)
    # fill / slippage model dimensions
    fill_quality_score: float = 0.0
    expected_slippage_pct: float = 0.0
    # greek fit dimensions
    greek_fit_score: float = 0.0
    delta_fit_score: float = 0.0
    gamma_fit_score: float = 0.0
    theta_fit_score: float = 0.0
    vega_fit_score: float = 0.0
    greek_risk_flags: list[str] = field(default_factory=list)
    greek_risk_verdict: str = ""
    greek_attribution_quality_score: float = 0.0
    # iv context / chain surface dimensions
    iv_context_score: float = 0.0
    skew_score: float = 0.0
    term_structure_score: float = 0.0
    # iv surface scenario lane dimensions
    iv_surface_scenario_id: str = ""
    iv_surface_fit_score: float = 0.0
    family_iv_fit_score: float = 0.0
    skew_term_score: float = 0.0
    premium_overpayment_score: float = 0.0
    iv_crush_score: float = 0.0
    iv_expansion_score: float = 0.0
    front_event_bump_score: float = 0.0
    skew_trap_score: float = 0.0
    wing_elevation_score: float = 0.0
    surface_instability_penalty: float = 0.0
    term_structure_risk_penalty: float = 0.0
    iv_crush_expansion_mismatch_penalty: float = 0.0
    iv_surface_risk_flags: list[str] = field(default_factory=list)
    iv_surface_verdict: str = ""
    # family outcome dimensions
    regime_match_score: float = 0.0
    family_fit_score: float = 0.0
    exit_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WalkForwardScore:
    consistency_score: float = 0.0
    window_pass_rate: float = 0.0
    regime_survival_score: float = 0.0
    slippage_tolerance_score: float = 0.0
    liquidity_robustness_score: float = 0.0
    invalidation_quality_score: float = 0.0
    overfit_suspicion_score: float = 0.0
    train_mean_pnl: float = 0.0
    validation_mean_pnl: float = 0.0
    holdout_mean_pnl: float = 0.0
    overall: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OverfitSignal:
    level: str = "none"            # none | low | moderate | high
    reasons: list[str] = field(default_factory=list)
    train_passed: bool = False
    validation_passed: bool = False
    holdout_passed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReplayVerdict:
    decision: str = "research_only"   # research_only | paper_candidate | replay_promoted_paper_candidate | rejected
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
