"""Advisory, bounded interventions for unhealthy research state."""

from __future__ import annotations

from collections.abc import Mapping


def recommend_interventions(variables: Mapping[str, float]) -> list[str]:
    interventions: list[str] = []
    if float(variables.get("strategy_concentration", 0.0)) > 0.8:
        interventions.extend(
            [
                "reduce_elite_reuse_in_shadow_replay",
                "inject_alternate_research_archetypes",
                "run_cross_regime_replay",
            ]
        )
    if float(variables.get("calibration_quality", 1.0)) < 0.5:
        interventions.append("collect_probability_calibration_outcomes")
    if float(variables.get("world_model_coverage", 1.0)) < 0.75:
        interventions.append("expand_missing_world_model_evidence")
    if float(variables.get("resource_pressure", 0.0)) > 0.9:
        interventions.append("terminate_low_marginal_utility_research")
    if float(variables.get("settlement_completion", 1.0)) < 1.0:
        interventions.append("await_forward_settlement_without_early_grading")
    if float(variables.get("lane_completion", 1.0)) < 1.0:
        interventions.append("restore_incomplete_evidence_lanes")
    if float(variables.get("option_chain_continuity", 1.0)) < 0.5:
        interventions.append("preserve_options_unknown_state_until_validated_chain_available")
    if float(variables.get("universe_health", 1.0)) < 0.75:
        interventions.append("expand_governed_universe_probation")
    if float(variables.get("model_dependence", 0.0)) > 0.75:
        interventions.append("diversify_model_and_deterministic_evidence_paths")
    if float(variables.get("archive_diversity", 1.0)) < 0.5:
        interventions.append("increase_shadow_archive_diversity")
    if float(variables.get("research_backlog_pressure", 0.0)) > 0.8:
        interventions.append("prioritize_high_information_gain_backlog")
    if float(variables.get("phantom_signal_coverage", 1.0)) < 0.5:
        interventions.append("increase_phantom_signal_settlement_coverage")
    return sorted(set(interventions))
