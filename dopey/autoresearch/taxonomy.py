"""Diverse strategy-lineage taxonomy for recursive research."""

from __future__ import annotations

from typing import Final

from dopey.protocols.identity import canonical_hash

from .schema import ResearchLineage, StrategyBlueprint


RESEARCH_LINEAGES: Final[tuple[ResearchLineage, ...]] = (
    {"lineage_id": "technical_momentum", "objective": "test persistent normalized momentum across horizons", "seed_genes": ("weekly_trend", "daily_momentum", "volume_confirmation", "regime_abstention"), "mutation_operators": ("change_lookback", "change_timeframe", "add_divergence", "simplify")},
    {"lineage_id": "structural_trend", "objective": "test break, retest, acceptance, and failure structures", "seed_genes": ("swing_structure", "break_acceptance", "relative_strength", "failure_exit"), "mutation_operators": ("alter_structure", "add_failed_breakout", "change_horizon", "simplify")},
    {"lineage_id": "fundamental_quality", "objective": "test durable quality with valuation and revision constraints", "seed_genes": ("quality_floor", "cash_flow_health", "revision_guard", "valuation_abstention"), "mutation_operators": ("change_quality_floor", "add_revision", "add_sector_relative", "simplify")},
    {"lineage_id": "fundamental_deterioration", "objective": "test forward deterioration and accounting-risk mechanisms", "seed_genes": ("cash_flow_decay", "estimate_revisions", "dilution_guard", "liquidity_guard"), "mutation_operators": ("add_balance_sheet", "change_revision_window", "add_crowding", "simplify")},
    {"lineage_id": "volatility_options", "objective": "test equity-first volatility and derivatives dislocations", "seed_genes": ("equity_thesis_first", "surface_quality", "skew_state", "cost_guard"), "mutation_operators": ("change_tenor", "add_term_structure", "add_dealer_state", "simplify")},
    {"lineage_id": "macro_regime", "objective": "test regime-conditioned equity research policies", "seed_genes": ("rates_regime", "dollar_regime", "growth_inflation_state", "regime_abstention"), "mutation_operators": ("add_credit", "change_regime_model", "add_release_clock", "simplify")},
    {"lineage_id": "breadth_participation", "objective": "test participation breadth and leadership durability", "seed_genes": ("breadth_state", "leadership_concentration", "relative_participation", "narrowing_guard"), "mutation_operators": ("change_breadth_window", "add_equal_weight", "add_thrust", "simplify")},
    {"lineage_id": "cross_asset", "objective": "test cross-asset stress and confirmation mechanisms", "seed_genes": ("rates_context", "credit_context", "commodity_context", "correlation_guard"), "mutation_operators": ("add_currency", "add_crypto_risk", "change_lag", "simplify")},
    {"lineage_id": "adversarial", "objective": "discover failure mechanisms that invalidate attractive theses", "seed_genes": ("market_prior", "opposite_case", "leakage_attack", "contested_truth"), "mutation_operators": ("add_null", "add_liquidity_attack", "add_narrative_attack", "simplify")},
    {"lineage_id": "calibration_first", "objective": "improve probability calibration before apparent precision", "seed_genes": ("confidence_decomposition", "regime_calibration", "sample_sufficiency", "weakest_dimension_cap"), "mutation_operators": ("change_calibrator", "add_reliability_bin", "add_regime_cap", "simplify")},
    {"lineage_id": "abstention_first", "objective": "improve research quality through explicit no-edge decisions", "seed_genes": ("knowledge_boundary", "information_gain", "no_edge_thesis", "terminate_low_yield"), "mutation_operators": ("change_abstention_threshold", "add_unknown_state", "add_utility_stop", "simplify")},
    {"lineage_id": "execution_cost_aware_research", "objective": "stress paper research against defensible friction assumptions", "seed_genes": ("spread_cost", "slippage_sensitivity", "liquidity_quality", "no_execution_authority"), "mutation_operators": ("change_cost_stress", "add_marking_challenge", "add_capacity_guard", "simplify")},
    {"lineage_id": "symbolic_factor_discovery", "objective": "discover compact interpretable factor expressions under complexity and redundancy controls", "seed_genes": ("typed_primitives", "symbolic_expression", "complexity_cap", "redundancy_pruning"), "mutation_operators": ("add_primitive", "alter_relation", "change_normalization", "simplify")},
    {"lineage_id": "relative_value_reversion", "objective": "test point-in-time relative-value dislocations with structural-break and cost guards", "seed_genes": ("spread_stability", "relative_dislocation", "change_point_guard", "cost_abstention"), "mutation_operators": ("change_pair_family", "change_window", "add_break_guard", "simplify")},
    {"lineage_id": "regime_change_detection", "objective": "detect structural change early enough to reroute or abstain without rewriting truth", "seed_genes": ("sequential_change_point", "clock_alignment", "regime_uncertainty", "abstention"), "mutation_operators": ("change_detector", "change_hazard", "add_cross_asset_state", "simplify")},
    {"lineage_id": "sequential_risk_control", "objective": "control continuous research peeking, false discoveries, and calibration risk", "seed_genes": ("online_alpha_budget", "confidence_sequence", "conformal_abstention", "protected_floor"), "mutation_operators": ("tighten_alpha", "change_abstention_calibrator", "add_family_control", "simplify")},
)


def build_seed_strategies() -> tuple[StrategyBlueprint, ...]:
    records: list[StrategyBlueprint] = []
    for lineage in RESEARCH_LINEAGES:
        identity = canonical_hash({"lineage_id": lineage["lineage_id"], "genes": lineage["seed_genes"], "generation": 0})
        records.append(
            {
                "strategy_id": f"strategy:{lineage['lineage_id']}:{identity[:16]}",
                "lineage_id": lineage["lineage_id"],
                "generation": 0,
                "parent_ids": (),
                "objective": lineage["objective"],
                "genes": lineage["seed_genes"],
                "mutation_operator": "seed",
                "evidence_parent_ids": (),
                "activation_state": "EXPERIMENTAL",
                "automatic_research_activation_allowed": False,
                "candidate_may_grade_itself": False,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return tuple(records)
