"""Dopey tournament score models (offline, deterministic, paper-only).

TournamentResult: aggregate per-tournament result.
StrategyTournamentScore: per-strategy tournament score (walk-forward + analysis fusion).
ChampionRegistryEntry: champion registry record.

The rich per-lane dimensions (liquidity/slippage, greeks, IV surface, pattern,
macro-event, fundamental, mutation-evolution summaries) were restored after the
branch-switch file loss: the tournament runner and its test suites construct and
consume them; the public-release sync had reduced these models to the slim core.
All restored fields default to honest zeros / empties.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class StrategyTournamentScore:
    tournament_id: str
    strategy_id: str
    strategy_family: str
    windows_replayed: int = 0
    walk_forward_overall: float = 0.0
    analysis_fusion_overall: float = 0.0
    overfit_level: str = "none"
    aggression_gate_decision: str = "research_only"
    paper_only_rank: int = 0
    champion_status: str = "entrant"   # champion | runner_up | entrant
    known_failure_modes: list[str] = field(default_factory=list)
    proof_record_path: str = ""
    combined_score: float = 0.0        # blend of walk-forward + analysis fusion (used for ranking)
    # ---- walk-forward decomposition ----
    holdout_score: float = 0.0
    liquidity_robustness: float = 0.0
    invalidation_quality: float = 0.0
    paper_fill_quality: float = 0.0
    regime_survival_score: float = 0.0
    family_regime_survival: float = 0.0
    overfit_rank: int = 3
    best_regimes: list[str] = field(default_factory=list)
    worst_regimes: list[str] = field(default_factory=list)
    # ---- liquidity / slippage lane ----
    average_liquidity_score: float = 0.0
    average_fill_quality_score: float = 0.0
    average_expected_slippage_pct: float = 0.0
    worst_slippage_regime: str = ""
    best_liquidity_regime: str = ""
    best_fill_quality_regime: str = ""
    liquidity_robustness_score: float = 0.0
    slippage_robustness_score: float = 0.0
    survived_bad_fill_low_liquidity: bool = False
    # ---- greeks lane ----
    average_greek_fit_score: float = 0.0
    average_delta_fit_score: float = 0.0
    average_gamma_fit_score: float = 0.0
    average_theta_fit_score: float = 0.0
    average_vega_fit_score: float = 0.0
    average_greek_attribution_quality: float = 0.0
    best_greek_fit_regime: str = ""
    worst_greek_risk_regime: str = ""
    greek_risk_verdict: str = ""
    greek_strengths: list[str] = field(default_factory=list)
    greek_weaknesses: list[str] = field(default_factory=list)
    survived_high_theta_high_vega_risk: bool = False
    # ---- IV context / surface lane ----
    average_iv_context_score: float = 0.0
    average_skew_score: float = 0.0
    average_term_structure_score: float = 0.0
    average_iv_surface_fit_score: float = 0.0
    average_family_iv_fit_score: float = 0.0
    average_skew_term_score: float = 0.0
    average_premium_overpayment_score: float = 0.0
    average_iv_crush_score: float = 0.0
    average_iv_expansion_score: float = 0.0
    average_front_event_bump_score: float = 0.0
    average_skew_trap_score: float = 0.0
    average_wing_elevation_score: float = 0.0
    average_surface_instability_penalty: float = 0.0
    average_term_structure_risk_penalty: float = 0.0
    average_iv_mismatch_penalty: float = 0.0
    best_iv_surface_regime: str = ""
    worst_iv_surface_regime: str = ""
    worst_iv_surface_scenario: str = ""
    iv_surface_verdicts: list[str] = field(default_factory=list)
    iv_surface_risk_flags: list[str] = field(default_factory=list)
    # ---- pattern lane ----
    average_pattern_fixture_score: float = 0.0
    supporting_pattern_ids: list[str] = field(default_factory=list)
    penalizing_pattern_ids: list[str] = field(default_factory=list)
    # ---- macro-event lane ----
    average_macro_fit_score: float = 0.0
    average_macro_risk_score: float = 0.0
    average_macro_opportunity_score: float = 0.5
    average_event_risk_score: float = 0.5
    average_rate_shock_score: float = 0.5
    average_vix_vvix_stress_score: float = 0.5
    average_breadth_sector_confirmation_score: float = 0.5
    average_liquidity_regime_macro_score: float = 0.5
    average_macro_contradiction_penalty: float = 0.0
    average_event_gap_risk_penalty: float = 0.0
    best_macro_regime: str = ""
    worst_macro_regime: str = ""
    best_macro_scenario: str = ""
    worst_macro_scenario: str = ""
    macro_event_risk_flags: list[str] = field(default_factory=list)
    # ---- fundamental lane ----
    average_fundamental_fit_score: float = 0.0
    average_sector_fit_score: float = 0.0
    average_peer_confirmation_score: float = 0.0
    average_valuation_risk_score: float = 0.0
    average_earnings_quality_score: float = 0.0
    average_crowding_risk_score: float = 0.0
    average_fundamental_contradiction_penalty: float = 0.0
    average_fragility_penalty: float = 0.0
    fundamental_risk_flags: list[str] = field(default_factory=list)
    best_fundamental_scenario: str = ""
    worst_fundamental_scenario: str = ""
    best_fundamental_regime: str = ""
    worst_fundamental_regime: str = ""
    family_fundamental_fit_score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TournamentResult:
    tournament_id: str
    mode: str
    live_trading_enabled: bool
    tournament_status: str
    champion_strategy_id: str
    runner_up_strategy_id: str
    strategy_ranking: list[dict] = field(default_factory=list)
    family_scorecard: dict = field(default_factory=dict)
    overfit_summary: dict = field(default_factory=dict)
    promotion_decisions: dict = field(default_factory=dict)
    champion_registry_path: str = ""
    proof_record_path: str = ""
    live_blocked: bool = True
    reproducibility_hash: str = ""
    # ---- restored corpus / lane summaries ----
    corpus_id: str = ""
    window_count: int = 0
    regime_tags_covered: list[str] = field(default_factory=list)
    family_replay_summaries: dict = field(default_factory=dict)
    analysis_fusion_summaries: dict = field(default_factory=dict)
    safety_state: dict = field(default_factory=dict)
    liquidity_model_version: str = ""
    slippage_model_version: str = ""
    slippage_liquidity_summary: dict = field(default_factory=dict)
    worst_slippage_regimes: dict = field(default_factory=dict)
    best_fill_quality_regimes: dict = field(default_factory=dict)
    greeks_validation_model_version: str = ""
    iv_fixture_model_version: str = ""
    iv_surface_expansion_version: str = ""
    greek_iv_summary: dict = field(default_factory=dict)
    iv_surface_expansion_summary: dict = field(default_factory=dict)
    worst_greek_risk_regimes: dict = field(default_factory=dict)
    best_greek_fit_regimes: dict = field(default_factory=dict)
    source_scorecard_summary: dict = field(default_factory=dict)
    pattern_recognition_summary: dict = field(default_factory=dict)
    mutation_evolution_summary: dict = field(default_factory=dict)
    structure_builder_summary: dict = field(default_factory=dict)
    failure_mode_summary: dict = field(default_factory=dict)
    macro_event_expansion_version: str = ""
    macro_event_summary: dict = field(default_factory=dict)
    family_macro_scores: dict = field(default_factory=dict)
    fundamental_expansion_version: str = ""
    fundamental_summary: dict = field(default_factory=dict)
    family_fundamental_scores: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChampionRegistryEntry:
    tournament_id: str
    champion_strategy_id: str
    runner_up_strategy_id: str
    family_ranking: list[dict] = field(default_factory=list)
    walk_forward_summary: dict = field(default_factory=dict)
    analysis_fusion_summary: dict = field(default_factory=dict)
    overfit_summary: dict = field(default_factory=dict)
    paper_only_promotion_status: str = "research_only"
    run_id: str = ""
    reproducibility_hash: str = ""
    # ---- restored per-champion lane summaries ----
    best_regimes_by_family: dict = field(default_factory=dict)
    worst_regimes_by_family: dict = field(default_factory=dict)
    family_strengths: dict = field(default_factory=dict)
    family_weaknesses: dict = field(default_factory=dict)
    champion_best_regimes: list[str] = field(default_factory=list)
    champion_worst_regimes: list[str] = field(default_factory=list)
    champion_overfit_level: str = "none"
    champion_replay_score: float = 0.0
    champion_analysis_fusion_score: float = 0.0
    safety_state: dict = field(default_factory=dict)
    corpus_id: str = ""
    window_count: int = 0
    average_liquidity_score: float = 0.0
    average_fill_quality_score: float = 0.0
    worst_slippage_regime: str = ""
    best_liquidity_regime: str = ""
    liquidity_robustness_score: float = 0.0
    slippage_robustness_score: float = 0.0
    survived_bad_fill_low_liquidity: bool = False
    slippage_liquidity_summary: dict = field(default_factory=dict)
    greeks_validation_model_version: str = ""
    iv_fixture_model_version: str = ""
    iv_surface_expansion_version: str = ""
    average_greek_fit_score: float = 0.0
    average_iv_context_score: float = 0.0
    average_iv_surface_fit_score: float = 0.0
    average_family_iv_fit_score: float = 0.0
    average_skew_term_score: float = 0.0
    average_premium_overpayment_score: float = 0.0
    average_greek_attribution_quality: float = 0.0
    best_greek_fit_regime: str = ""
    worst_greek_risk_regime: str = ""
    greek_strengths: list[str] = field(default_factory=list)
    greek_weaknesses: list[str] = field(default_factory=list)
    greek_iv_summary: dict = field(default_factory=dict)
    iv_surface_expansion_summary: dict = field(default_factory=dict)
    survived_high_theta_high_vega_risk: bool = False
    source_scorecard_summary: dict = field(default_factory=dict)
    pattern_recognition_summary: dict = field(default_factory=dict)
    mutation_evolution_summary: dict = field(default_factory=dict)
    structure_builder_summary: dict = field(default_factory=dict)
    failure_mode_summary: dict = field(default_factory=dict)
    best_mutated_strategy_id: str = ""
    parent_vs_mutation_comparison: dict = field(default_factory=dict)
    average_macro_fit_score: float = 0.0
    average_macro_risk_score: float = 0.0
    best_macro_regime: str = ""
    worst_macro_regime: str = ""
    macro_failure_modes: list[str] = field(default_factory=list)
    event_risk_robustness: float = 0.5
    vix_vvix_stress_robustness: float = 0.5
    breadth_sector_confirmation_score: float = 0.0
    macro_contradiction_score: float = 0.0
    macro_event_summary: dict = field(default_factory=dict)
    average_fundamental_fit_score: float = 0.0
    average_sector_fit_score: float = 0.0
    average_peer_confirmation_score: float = 0.0
    average_valuation_risk_score: float = 0.0
    average_earnings_quality_score: float = 0.0
    average_crowding_risk_score: float = 0.0
    average_fundamental_contradiction_penalty: float = 0.0
    average_fragility_penalty: float = 0.0
    fundamental_risk_flags: list[str] = field(default_factory=list)
    best_fundamental_scenario: str = ""
    worst_fundamental_scenario: str = ""
    fundamental_summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
