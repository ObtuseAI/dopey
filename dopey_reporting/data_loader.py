"""Load and write DOPEY reporting artifacts.

This module reads local JSON/JSONL evidence only. It performs no network calls and never
touches broker credentials or live trading state.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dopey_backtest.trade_records_recovery import (
    iter_verified_trade_records,
    resolve_default_backtest_trade_ledger,
)
from dopey_core.config import default_config_path, load_config


ARTIFACT_ROOT = Path(__file__).resolve().parent.parent / "artifacts" / "dopey"
REPORTING_ARTIFACT_DIR = ARTIFACT_ROOT / "reporting"
REPORTING_DASHBOARD_INDEX_JSON = REPORTING_ARTIFACT_DIR / "dashboard_index.json"
REPORTING_DASHBOARD_INDEX_MD = REPORTING_ARTIFACT_DIR / "dashboard_index.md"
STRATEGY_REPORT_CARDS_PATH = REPORTING_ARTIFACT_DIR / "strategy_report_cards.jsonl"
FAMILY_REPORT_CARDS_PATH = REPORTING_ARTIFACT_DIR / "family_report_cards.jsonl"
SCENARIO_REPORT_CARDS_PATH = REPORTING_ARTIFACT_DIR / "scenario_report_cards.jsonl"
REGIME_REPORT_CARDS_PATH = REPORTING_ARTIFACT_DIR / "regime_report_cards.jsonl"
PERFORMANCE_ATTRIBUTION_PATH = REPORTING_ARTIFACT_DIR / "performance_attribution.jsonl"
REPORTING_BUNDLE_SUMMARY_PATH = REPORTING_ARTIFACT_DIR / "reporting_bundle_summary.json"
REPORTING_PROOF_PATH = REPORTING_ARTIFACT_DIR / "reporting_bundle_proof.jsonl"
STATIC_DASHBOARD_PATH = REPORTING_ARTIFACT_DIR / "static_dashboard.html"


EVIDENCE_PATHS: dict[str, Path] = {
    "tournament": ARTIFACT_ROOT / "tournaments" / "dopey_tournament.jsonl",
    "champion": ARTIFACT_ROOT / "champion_registry" / "champion_registry.jsonl",
    "mutation": ARTIFACT_ROOT / "mutations" / "mutation_registry.jsonl",
    "feedback": ARTIFACT_ROOT / "failure_feedback" / "failure_feedback_registry.jsonl",
    "failure_modes": ARTIFACT_ROOT / "failure_modes" / "failure_mode_registry.jsonl",
    "ensemble": ARTIFACT_ROOT / "ensemble_allocator" / "ensemble_allocation_registry.jsonl",
    "meta_governor": ARTIFACT_ROOT / "meta_governor" / "meta_governor_registry.jsonl",
    "meta_governor_decisions": ARTIFACT_ROOT / "meta_governor" / "meta_governor_decisions.jsonl",
    "macro_events": ARTIFACT_ROOT / "macro_events" / "macro_event_registry.jsonl",
    "iv_surface": ARTIFACT_ROOT / "iv_surface" / "iv_surface_registry.jsonl",
    "fundamental": ARTIFACT_ROOT / "fundamental_fixtures" / "fundamental_registry.jsonl",
    "stronger_consistency": ARTIFACT_ROOT / "walk_forward_consistency" / "consistency_registry.jsonl",
    "corpus_v2": ARTIFACT_ROOT / "regime_holdout_corpus_v2" / "corpus_registry.jsonl",
    "audit": ARTIFACT_ROOT / "audit" / "evidence_gap_plan.jsonl",
    "active_policy": ARTIFACT_ROOT / "audit" / "active_policy_audit.jsonl",
    "paper_account_ledger": ARTIFACT_ROOT / "account_ledger" / "paper_account_ledger.json",
    "rotation_plan": ARTIFACT_ROOT / "account_ledger" / "rotation_plan.json",
    "day_trade_event_log": ARTIFACT_ROOT / "account_ledger" / "day_trade_event_log.jsonl",
    "zero_dte_risk_summary": ARTIFACT_ROOT / "zero_dte_risk" / "zero_dte_risk_summary.json",
    "zero_dte_replay_summary": ARTIFACT_ROOT / "zero_dte_replay" / "zero_dte_replay_summary.json",
    "zero_dte_threshold_optimizer_summary": ARTIFACT_ROOT / "zero_dte_threshold_optimizer" / "threshold_optimizer_summary.json",
    "zero_dte_adversarial_coverage_summary": ARTIFACT_ROOT / "zero_dte_adversarial_corpus" / "adversarial_coverage_summary.json",
    "zero_dte_combined_replay_summary": ARTIFACT_ROOT / "zero_dte_adversarial_corpus" / "combined_replay_summary.json",
    "zero_dte_cross_underlying_coverage_summary": ARTIFACT_ROOT / "zero_dte_cross_underlying_v2" / "cross_underlying_coverage_summary.json",
    "zero_dte_combined_v1_v2_replay_summary": ARTIFACT_ROOT / "zero_dte_cross_underlying_v2" / "combined_v1_v2_replay_summary.json",
    "zero_dte_cross_underlying_threshold_survival": ARTIFACT_ROOT / "zero_dte_cross_underlying_v2" / "cross_underlying_threshold_survival.json",
    "hybrid_coverage_summary": ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_coverage_summary.json",
    "hybrid_replay_summary": ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_replay_summary.json",
    "hybrid_threshold_survival": ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_threshold_survival.json",
    "paper_allocation_plan": ARTIFACT_ROOT / "allocation" / "paper_allocation_plan.json",
    "allocation_exposure_summary": ARTIFACT_ROOT / "allocation" / "allocation_exposure_summary.json",
    "allocation_constraint_summary": ARTIFACT_ROOT / "allocation" / "allocation_constraint_summary.json",
    "portfolio_replay_summary": ARTIFACT_ROOT / "portfolio_replay" / "portfolio_replay_summary.json",
    "portfolio_exposure_snapshots": ARTIFACT_ROOT / "portfolio_replay" / "portfolio_exposure_snapshots.jsonl",
    "exposure_stress_results": ARTIFACT_ROOT / "portfolio_replay" / "exposure_stress_results.jsonl",
    "portfolio_allocator_feedback": ARTIFACT_ROOT / "portfolio_replay" / "portfolio_allocator_feedback.jsonl",
    "portfolio_threshold_feedback": ARTIFACT_ROOT / "portfolio_replay" / "portfolio_threshold_feedback.jsonl",
    "stress_ladder_summary": ARTIFACT_ROOT / "portfolio_stress_ladder" / "stress_ladder_summary.json",
    "stress_level_evaluations": ARTIFACT_ROOT / "portfolio_stress_ladder" / "stress_level_evaluations.jsonl",
    "crisis_throttle_results": ARTIFACT_ROOT / "portfolio_stress_ladder" / "crisis_throttle_results.jsonl",
    "crisis_recovery_results": ARTIFACT_ROOT / "portfolio_stress_ladder" / "crisis_recovery_results.jsonl",
    "crisis_allocator_feedback": ARTIFACT_ROOT / "portfolio_stress_ladder" / "crisis_allocator_feedback.jsonl",
    "crisis_threshold_feedback": ARTIFACT_ROOT / "portfolio_stress_ladder" / "crisis_threshold_feedback.jsonl",
    "incident_rehearsal_summary": ARTIFACT_ROOT / "incident_response" / "incident_rehearsal_summary.json",
    "incident_signals": ARTIFACT_ROOT / "incident_response" / "incident_signals.jsonl",
    "kill_switch_states": ARTIFACT_ROOT / "incident_response" / "kill_switch_states.jsonl",
    "incident_response_decisions": ARTIFACT_ROOT / "incident_response" / "incident_response_decisions.jsonl",
    "incident_recovery_plans": ARTIFACT_ROOT / "incident_response" / "incident_recovery_plans.jsonl",
    "incident_allocator_feedback": ARTIFACT_ROOT / "incident_response" / "incident_allocator_feedback.jsonl",
    "incident_threshold_feedback": ARTIFACT_ROOT / "incident_response" / "incident_threshold_feedback.jsonl",
    "incident_stress_ladder_feedback": ARTIFACT_ROOT / "incident_response" / "incident_stress_ladder_feedback.jsonl",
    "lifecycle_summary": ARTIFACT_ROOT / "lifecycle" / "lifecycle_summary.json",
    "lifecycle_states": ARTIFACT_ROOT / "lifecycle" / "lifecycle_states.jsonl",
    "lifecycle_transitions": ARTIFACT_ROOT / "lifecycle" / "lifecycle_transitions.jsonl",
    "lifecycle_paperbroker_results": ARTIFACT_ROOT / "lifecycle" / "lifecycle_paperbroker_results.jsonl",
    "lifecycle_account_ledger_results": ARTIFACT_ROOT / "lifecycle" / "lifecycle_account_ledger_results.jsonl",
    "lifecycle_feedback_allocator": ARTIFACT_ROOT / "lifecycle" / "lifecycle_feedback_allocator.jsonl",
    "lifecycle_feedback_portfolio": ARTIFACT_ROOT / "lifecycle" / "lifecycle_feedback_portfolio.jsonl",
    "lifecycle_feedback_stress_ladder": ARTIFACT_ROOT / "lifecycle" / "lifecycle_feedback_stress_ladder.jsonl",
    "lifecycle_feedback_incident": ARTIFACT_ROOT / "lifecycle" / "lifecycle_feedback_incident.jsonl",
    "broker_readiness_summary": ARTIFACT_ROOT / "broker_readiness" / "broker_readiness_summary.json",
    "broker_readiness_run_result": ARTIFACT_ROOT / "broker_readiness" / "broker_readiness_run_result.json",
    "broker_readiness_manual_gates": ARTIFACT_ROOT / "broker_readiness" / "broker_readiness_manual_gates.json",
    "broker_readiness_boundary_blocks": ARTIFACT_ROOT / "broker_readiness" / "broker_readiness_boundary_blocks.jsonl",
    "manual_approval_packet_summary": ARTIFACT_ROOT / "broker_readiness" / "manual_approval" / "manual_approval_packet_summary.json",
    "manual_approval_gate": ARTIFACT_ROOT / "broker_readiness" / "manual_approval" / "manual_approval_gate.json",
    "read_only_detector_scope": ARTIFACT_ROOT / "broker_readiness" / "manual_approval" / "read_only_detector_scope.json",
    "future_detector_command_templates": ARTIFACT_ROOT / "broker_readiness" / "manual_approval" / "future_detector_command_templates.jsonl",
    "manual_approval_boundary_blocks": ARTIFACT_ROOT / "broker_readiness" / "manual_approval" / "manual_approval_boundary_blocks.jsonl",
    "read_only_detector_dry_run_summary": ARTIFACT_ROOT / "broker_readiness" / "dry_run" / "read_only_detector_dry_run_summary.json",
    "read_only_detector_dry_run_results": ARTIFACT_ROOT / "broker_readiness" / "dry_run" / "read_only_detector_dry_run_results.jsonl",
    "simulated_broker_capability_responses": ARTIFACT_ROOT / "broker_readiness" / "dry_run" / "simulated_broker_capability_responses.jsonl",
    "dry_run_boundary_blocks": ARTIFACT_ROOT / "broker_readiness" / "dry_run" / "dry_run_boundary_blocks.jsonl",
    "approval_intake_requests": ARTIFACT_ROOT / "broker_readiness" / "approval_intake" / "approval_intake_requests.jsonl",
    "approval_scope_validations": ARTIFACT_ROOT / "broker_readiness" / "approval_intake" / "approval_scope_validations.jsonl",
    "approval_intake_results": ARTIFACT_ROOT / "broker_readiness" / "approval_intake" / "approval_intake_results.jsonl",
    "approval_forbidden_terms": ARTIFACT_ROOT / "broker_readiness" / "approval_intake" / "approval_forbidden_terms.json",
    "approval_boundary_blocks": ARTIFACT_ROOT / "broker_readiness" / "approval_intake" / "approval_boundary_blocks.jsonl",
    "approval_incident_escalations": ARTIFACT_ROOT / "broker_readiness" / "approval_intake" / "approval_incident_escalations.jsonl",
    "approval_intake_summary": ARTIFACT_ROOT / "broker_readiness" / "approval_intake" / "approval_intake_summary.json",
    "approval_intake_proof": ARTIFACT_ROOT / "broker_readiness" / "approval_intake" / "approval_intake_proof.jsonl",
    "handoff_inputs": ARTIFACT_ROOT / "broker_readiness" / "approval_to_run_handoff" / "handoff_inputs.jsonl",
    "future_detector_run_envelopes": ARTIFACT_ROOT / "broker_readiness" / "approval_to_run_handoff" / "future_detector_run_envelopes.jsonl",
    "approval_to_run_gate_decisions": ARTIFACT_ROOT / "broker_readiness" / "approval_to_run_handoff" / "approval_to_run_gate_decisions.jsonl",
    "disabled_handoff_command_templates": ARTIFACT_ROOT / "broker_readiness" / "approval_to_run_handoff" / "disabled_handoff_command_templates.jsonl",
    "handoff_boundary_blocks": ARTIFACT_ROOT / "broker_readiness" / "approval_to_run_handoff" / "handoff_boundary_blocks.jsonl",
    "handoff_incident_escalations": ARTIFACT_ROOT / "broker_readiness" / "approval_to_run_handoff" / "handoff_incident_escalations.jsonl",
    "approval_to_run_handoff_summary": ARTIFACT_ROOT / "broker_readiness" / "approval_to_run_handoff" / "approval_to_run_handoff_summary.json",
    "approval_to_run_handoff_proof": ARTIFACT_ROOT / "broker_readiness" / "approval_to_run_handoff" / "approval_to_run_handoff_proof.jsonl",
    "pre_run_safety_summary": ARTIFACT_ROOT / "broker_readiness" / "pre_run_safety" / "pre_run_safety_summary.json",
    "pre_run_safety_proof": ARTIFACT_ROOT / "broker_readiness" / "pre_run_safety" / "pre_run_safety_proof.jsonl",
    "read_only_detector_run_requests": ARTIFACT_ROOT / "broker_readiness" / "read_only_detector" / "read_only_detector_run_requests.jsonl",
    "read_only_capability_records": ARTIFACT_ROOT / "broker_readiness" / "read_only_detector" / "read_only_capability_records.jsonl",
    "read_only_blocked_write_execute_records": ARTIFACT_ROOT / "broker_readiness" / "read_only_detector" / "read_only_blocked_write_execute_records.jsonl",
    "read_only_provider_boundary_results": ARTIFACT_ROOT / "broker_readiness" / "read_only_detector" / "read_only_provider_boundary_results.jsonl",
    "read_only_detector_run_results": ARTIFACT_ROOT / "broker_readiness" / "read_only_detector" / "read_only_detector_run_results.jsonl",
    "read_only_detector_post_run_evidence": ARTIFACT_ROOT / "broker_readiness" / "read_only_detector" / "read_only_detector_post_run_evidence.json",
    "read_only_detector_incident_escalations": ARTIFACT_ROOT / "broker_readiness" / "read_only_detector" / "read_only_detector_incident_escalations.jsonl",
    "read_only_detector_summary": ARTIFACT_ROOT / "broker_readiness" / "read_only_detector" / "read_only_detector_summary.json",
    "read_only_detector_proof": ARTIFACT_ROOT / "broker_readiness" / "read_only_detector" / "read_only_detector_proof.jsonl",
    "evidence_contract": ARTIFACT_ROOT / "broker_readiness" / "evidence_contract" / "evidence_contract.json",
    "evidence_items": ARTIFACT_ROOT / "broker_readiness" / "evidence_contract" / "evidence_items.jsonl",
    "boundary_assertions": ARTIFACT_ROOT / "broker_readiness" / "evidence_contract" / "boundary_assertions.jsonl",
    "evidence_validation_results": ARTIFACT_ROOT / "broker_readiness" / "evidence_contract" / "evidence_validation_results.jsonl",
    "evidence_promotion_decisions": ARTIFACT_ROOT / "broker_readiness" / "evidence_contract" / "evidence_promotion_decisions.jsonl",
    "evidence_contract_summary": ARTIFACT_ROOT / "broker_readiness" / "evidence_contract" / "evidence_contract_summary.json",
    "evidence_contract_proof": ARTIFACT_ROOT / "broker_readiness" / "evidence_contract" / "evidence_contract_proof.jsonl",
    "history_spine_summary": ARTIFACT_ROOT / "history" / "history_spine_summary.json",
    "history_dataset_validation": ARTIFACT_ROOT / "history" / "history_dataset_validation.json",
    "history_symbol_coverage": ARTIFACT_ROOT / "history" / "history_symbol_coverage.jsonl",
    "history_quality_flags": ARTIFACT_ROOT / "history" / "history_quality_flags.jsonl",
    "model_repricing_summary": ARTIFACT_ROOT / "model_repricing" / "model_repricing_summary.json",
    "iv_solver_validation": ARTIFACT_ROOT / "model_repricing" / "iv_solver_validation.json",
    "vol_surface_model": ARTIFACT_ROOT / "model_repricing" / "vol_surface_model.json",
    "model_repricing_quality_flags": ARTIFACT_ROOT / "model_repricing" / "model_repricing_quality_flags.jsonl",
    "signal_engine_summary": ARTIFACT_ROOT / "signals" / "signal_engine_summary.json",
    "signal_engine_input_summary": ARTIFACT_ROOT / "signals" / "signal_engine_input_summary.json",
    "signal_quality_flags": ARTIFACT_ROOT / "signals" / "signal_quality_flags.jsonl",
    "backtest_run_summary": ARTIFACT_ROOT / "backtest" / "backtest_run_summary.json",
    "backtest_quality_flags": ARTIFACT_ROOT / "backtest" / "backtest_quality_flags.jsonl",
    "backtest_trade_records": ARTIFACT_ROOT / "backtest" / "backtest_trade_records.jsonl",
    "statistical_truth_summary": ARTIFACT_ROOT / "stats" / "statistical_truth_summary.json",
    "statistical_truth_quality_flags": ARTIFACT_ROOT / "stats" / "statistical_truth_quality_flags.jsonl",
    "backtest_metric_set": ARTIFACT_ROOT / "stats" / "backtest_metric_set.json",
    "bootstrap_confidence_intervals": ARTIFACT_ROOT / "stats" / "bootstrap_confidence_intervals.json",
    "baseline_comparisons": ARTIFACT_ROOT / "stats" / "baseline_comparisons.jsonl",
    "statistical_truth_decision": ARTIFACT_ROOT / "stats" / "statistical_truth_decision.json",
    "fitness_replacement_summary": ARTIFACT_ROOT / "fitness" / "fitness_replacement_summary.json",
    "fitness_quality_flags": ARTIFACT_ROOT / "fitness" / "fitness_quality_flags.jsonl",
    "fitness_decision": ARTIFACT_ROOT / "fitness" / "fitness_decision.json",
    "data_ingestion_plan_summary": ARTIFACT_ROOT / "data_ingestion" / "data_ingestion_plan_summary.json",
    "import_readiness_decision": ARTIFACT_ROOT / "data_ingestion" / "import_readiness_decision.json",
    "data_ingestion_plan": ARTIFACT_ROOT / "data_ingestion" / "data_ingestion_plan.json",
    "dataset_requirements": ARTIFACT_ROOT / "data_ingestion" / "dataset_requirements.jsonl",
    "provider_candidates": ARTIFACT_ROOT / "data_ingestion" / "provider_candidates.jsonl",
    "schema_contracts": ARTIFACT_ROOT / "data_ingestion" / "schema_contracts.jsonl",
    "data_quality_gates": ARTIFACT_ROOT / "data_ingestion" / "data_quality_gates.jsonl",
    "local_ohlcv_import_summary": ARTIFACT_ROOT / "local_ohlcv_import" / "local_ohlcv_import_summary.json",
    "real_ohlcv_history_spine_upgrade": ARTIFACT_ROOT / "history" / "real_ohlcv_history_spine_upgrade.json",
    "real_ohlcv_history_spine_activation": ARTIFACT_ROOT / "history" / "real_ohlcv_history_spine_activation.json",
    "real_signal_validation_summary": ARTIFACT_ROOT / "real_signal_validation" / "real_signal_validation_summary.json",
    "options_data_contract_summary": ARTIFACT_ROOT / "options_data_contract" / "options_data_contract_summary.json",
    "real_data_validation_stack_summary": ARTIFACT_ROOT / "real_data_validation_stack" / "real_data_validation_stack_summary.json",
    "open_source_path_summary": ARTIFACT_ROOT / "open_source_path" / "open_source_quant_stack_and_free_data_path_summary.json",
    "local_free_ohlcv_stack_summary": ARTIFACT_ROOT / "local_free_ohlcv_stack" / "local_free_ohlcv_validation_and_activation_stack_summary.json",
    "manual_ohlcv_staging_summary": ARTIFACT_ROOT / "manual_ohlcv_staging" / "manual_ohlcv_staging_summary.json",
    "operator_reviewed_ohlcv_stage_summary": ARTIFACT_ROOT / "operator_reviewed_ohlcv_stage" / "operator_reviewed_ohlcv_stage_rerun_summary.json",
    "autonomous_admissibility_kernel_summary": ARTIFACT_ROOT / "autonomy" / "autonomous_admissibility_kernel_summary.json",
    "autonomous_oss_discovery_summary": ARTIFACT_ROOT / "open_source_autonomy" / "autonomous_oss_discovery_summary.json",
    "autonomous_open_data_validator_bridge_summary": ARTIFACT_ROOT / "open_data_autonomy" / "autonomous_open_data_validator_bridge_summary.json",
    "open_options_data_autonomy_summary": ARTIFACT_ROOT / "options_autonomy" / "open_options_data_autonomy_summary.json",
    "autonomous_research_engine_summary": ARTIFACT_ROOT / "research_autonomy" / "autonomous_research_engine_summary.json",
    "autonomous_backtest_stat_fitness_summary": ARTIFACT_ROOT / "research_autonomy" / "autonomous_backtest_stat_fitness_summary.json",
    "autonomous_paper_trading_loop_summary": ARTIFACT_ROOT / "paper_autonomy" / "autonomous_paper_trading_loop_summary.json",
    "s_tier_options_benchmark_summary": ARTIFACT_ROOT / "research_autonomy" / "s_tier_options_benchmark_summary.json",
    "full_open_source_autonomous_orchestrator_summary": ARTIFACT_ROOT / "full_autonomy" / "full_open_source_autonomous_orchestrator_summary.json",
    "open_data_breakthrough_full_completion_summary": ARTIFACT_ROOT / "open_data_breakthrough" / "open_data_breakthrough_full_completion_summary.json",
    "exhaustive_open_data_discovery_matrix_summary": ARTIFACT_ROOT / "open_data_breakthrough" / "exhaustive_open_data_discovery_matrix_summary.json",
    "quote_priced_options_unlock_gate": ARTIFACT_ROOT / "backtest" / "quote_priced_options_unlock_gate.json",
    "model_priced_options_research_summary": ARTIFACT_ROOT / "research_autonomy" / "model_priced_options_research_summary.json",
    "finish_everything_orchestrator_summary": ARTIFACT_ROOT / "finish_everything" / "finish_everything_orchestrator_summary.json",
    "openbb_provider_registry_summary": ARTIFACT_ROOT / "openbb_autonomy" / "openbb_provider_registry_summary.json",
    "openbb_validator_bridge_summary": ARTIFACT_ROOT / "openbb_autonomy" / "openbb_validator_bridge_summary.json",
    "model_priced_v2_research_summary": ARTIFACT_ROOT / "research_autonomy" / "model_priced_v2_research_summary.json",
    "s_tier_v2_summary": ARTIFACT_ROOT / "research_autonomy" / "s_tier_v2_summary.json",
    "paper_rotation_engine_summary": ARTIFACT_ROOT / "paper_autonomy" / "paper_rotation_engine_summary.json",
    "remaining_gap_eliminator_summary": ARTIFACT_ROOT / "full_autonomy" / "remaining_gap_eliminator_summary.json",
    "wealth_engine_summary": ARTIFACT_ROOT / "wealth_engine" / "wealth_engine_full_completion_summary.json",
    "wealth_engine_validation_summary": ARTIFACT_ROOT / "wealth_engine" / "wealth_engine_validation_summary.json",
    "market_data_lake_summary": ARTIFACT_ROOT / "market_intake" / "market_data_lake_summary.json",
    "chart_vision_summary": ARTIFACT_ROOT / "chart_vision" / "chart_vision_summary.json",
    "pnl_scoreboard_summary": ARTIFACT_ROOT / "scoreboard" / "pnl_scoreboard_summary.json",
    "provider_install_repair_summary": ARTIFACT_ROOT / "provider_install" / "provider_install_repair_summary.json",
    "provider_health_diagnostics_summary": ARTIFACT_ROOT / "market_intake" / "provider_health_diagnostics_summary.json",
    "public_ohlcv_provider_ladder_v2_summary": ARTIFACT_ROOT / "market_intake" / "public_ohlcv_provider_ladder_v2_summary.json",
    "market_lake_public_promotion_summary": ARTIFACT_ROOT / "market_intake" / "market_lake_public_promotion_summary.json",
    "market_data_cache_summary": ARTIFACT_ROOT / "market_intake" / "market_data_cache_summary.json",
    "market_universe_expansion_summary": ARTIFACT_ROOT / "market_intake" / "market_universe_expansion_summary.json",
    "real_public_market_wealth_rerun_summary": ARTIFACT_ROOT / "real_public_wealth" / "real_public_market_wealth_rerun_summary.json",
    "real_public_market_wealth_validation_summary": ARTIFACT_ROOT / "real_public_wealth" / "real_public_market_wealth_validation_summary.json",
    "public_vs_fixture_scoreboard_split": ARTIFACT_ROOT / "scoreboard" / "public_vs_fixture_scoreboard_split.json",
    "public_lake_freeze_guard_summary": ARTIFACT_ROOT / "public_champion_evolution" / "public_lake_freeze_guard_summary.json",
    "public_universe_expansion_v2_summary": ARTIFACT_ROOT / "public_champion_evolution" / "public_universe_expansion_v2_summary.json",
    "model_priced_path_simulator_v3_summary": ARTIFACT_ROOT / "options_engine" / "model_priced_path_simulator_v3_summary.json",
    "public_signal_mutation_factory_v3_summary": ARTIFACT_ROOT / "signals" / "public_signal_mutation_factory_v3_summary.json",
    "public_walk_forward_tournament_v3_summary": ARTIFACT_ROOT / "tournament" / "public_walk_forward_tournament_v3_summary.json",
    "public_paper_champion_gate_summary": ARTIFACT_ROOT / "champions" / "public_paper_champion_gate_summary.json",
    "public_champion_scoreboard_v3": ARTIFACT_ROOT / "scoreboard" / "public_champion_scoreboard_v3.json",
    "public_champion_evolution_summary": ARTIFACT_ROOT / "evolution" / "public_champion_evolution_summary.json",
    "public_champion_risk_summary_v3": ARTIFACT_ROOT / "risk" / "public_champion_risk_summary_v3.json",
    "public_champion_live_gate_status": ARTIFACT_ROOT / "live_gate" / "public_champion_live_gate_status.json",
    "public_lake_final_state_lock_v2_summary": ARTIFACT_ROOT / "public_signal_deepening" / "public_lake_final_state_lock_v2_summary.json",
    "strategy_cohort_summary": ARTIFACT_ROOT / "public_signal_deepening" / "strategy_cohort_summary.json",
    "public_signal_mutation_factory_v4_summary": ARTIFACT_ROOT / "signals" / "public_signal_mutation_factory_v4_summary.json",
    "model_priced_path_simulator_v4_summary": ARTIFACT_ROOT / "options_engine" / "model_priced_path_simulator_v4_summary.json",
    "public_cohort_walk_forward_tournament_v4_summary": ARTIFACT_ROOT / "tournament" / "public_cohort_walk_forward_tournament_v4_summary.json",
    "public_paper_champion_gate_v2_summary": ARTIFACT_ROOT / "champions" / "public_paper_champion_gate_v2_summary.json",
    "public_signal_deepening_loop_v2_summary": ARTIFACT_ROOT / "evolution" / "public_signal_deepening_loop_v2_summary.json",
    "public_signal_deepening_scoreboard_v4": ARTIFACT_ROOT / "scoreboard" / "public_signal_deepening_scoreboard_v4.json",
    "public_signal_deepening_live_gate_status_v2": ARTIFACT_ROOT / "live_gate" / "public_signal_deepening_live_gate_status_v2.json",
    "public_market_signal_mutation_deepening_v2_summary": ARTIFACT_ROOT / "public_signal_deepening" / "public_market_signal_mutation_deepening_v2_summary.json",
    "public_market_signal_mutation_deepening_v2_validation_summary": ARTIFACT_ROOT / "public_signal_deepening" / "public_market_signal_mutation_deepening_v2_validation_summary.json",
    "champion_hardening_preflight_summary": ARTIFACT_ROOT / "champion_hardening" / "champion_hardening_preflight_summary.json",
    "public_signal_artifact_cleaner_summary": ARTIFACT_ROOT / "champion_hardening" / "public_signal_artifact_cleaner_summary.json",
    "public_champion_inventory_v1_summary": ARTIFACT_ROOT / "champion_hardening" / "public_champion_inventory_v1_summary.json",
    "public_champion_deep_stress_matrix_v1_summary": ARTIFACT_ROOT / "champion_hardening" / "public_champion_deep_stress_matrix_v1_summary.json",
    "public_champion_holdout_expansion_v1_summary": ARTIFACT_ROOT / "champion_hardening" / "public_champion_holdout_expansion_v1_summary.json",
    "public_champion_decay_monitor_v1_summary": ARTIFACT_ROOT / "champion_hardening" / "public_champion_decay_monitor_v1_summary.json",
    "public_champion_hardening_gate_v1_summary": ARTIFACT_ROOT / "champion_hardening" / "public_champion_hardening_gate_v1_summary.json",
    "public_champion_hardening_scoreboard_v1": ARTIFACT_ROOT / "scoreboard" / "public_champion_hardening_scoreboard_v1.json",
    "public_champion_hardening_live_gate_status_v3": ARTIFACT_ROOT / "live_gate" / "public_champion_hardening_live_gate_status_v3.json",
    "public_paper_champion_hardening_and_deep_stress_v1_summary": ARTIFACT_ROOT / "champion_hardening" / "public_paper_champion_hardening_and_deep_stress_v1_summary.json",
    "public_paper_champion_hardening_and_deep_stress_v1_validation_summary": ARTIFACT_ROOT / "champion_hardening" / "public_paper_champion_hardening_and_deep_stress_v1_validation_summary.json",
    "public_champion_repair_preflight_v1_summary": ARTIFACT_ROOT / "champion_repair" / "public_champion_repair_preflight_v1_summary.json",
    "public_champion_artifact_guard_v1_summary": ARTIFACT_ROOT / "champion_repair" / "public_champion_artifact_guard_v1_summary.json",
    "conditional_champion_retune_hardening_gate_v1_summary": ARTIFACT_ROOT / "champion_repair" / "conditional_champion_retune_hardening_gate_v1_summary.json",
    "public_champion_repair_and_retune_v1_summary": ARTIFACT_ROOT / "champion_repair" / "public_champion_repair_and_retune_v1_summary.json",
    "public_champion_repair_and_retune_v1_validation_summary": ARTIFACT_ROOT / "champion_repair" / "public_champion_repair_and_retune_v1_validation_summary.json",
    "public_signal_research_preflight_v1_summary": ARTIFACT_ROOT / "signal_research" / "public_signal_research_preflight_v1_summary.json",
    "research_breakthrough_gate_v1_summary": ARTIFACT_ROOT / "signal_research" / "research_breakthrough_gate_v1_summary.json",
    "public_signal_research_breakthrough_v1_summary": ARTIFACT_ROOT / "signal_research" / "public_signal_research_breakthrough_v1_summary.json",
    "public_signal_research_breakthrough_v1_validation_summary": ARTIFACT_ROOT / "signal_research" / "public_signal_research_breakthrough_v1_validation_summary.json",
    "public_signal_research_v2_preflight_summary": ARTIFACT_ROOT / "signal_research_v2" / "public_signal_research_v2_preflight_summary.json",
    "research_breakthrough_gate_v2_summary": ARTIFACT_ROOT / "signal_research_v2" / "research_breakthrough_gate_v2_summary.json",
    "public_signal_research_breakthrough_v2_summary": ARTIFACT_ROOT / "signal_research_v2" / "public_signal_research_breakthrough_v2_summary.json",
    "public_signal_research_breakthrough_v2_validation_summary": ARTIFACT_ROOT / "signal_research_v2" / "public_signal_research_breakthrough_v2_validation_summary.json",
    "public_signal_research_v3_preflight_summary": ARTIFACT_ROOT / "signal_research_v3" / "public_signal_research_v3_preflight_summary.json",
    "research_breakthrough_gate_v3_summary": ARTIFACT_ROOT / "signal_research_v3" / "research_breakthrough_gate_v3_summary.json",
    "public_signal_research_breakthrough_v3_summary": ARTIFACT_ROOT / "signal_research_v3" / "public_signal_research_breakthrough_v3_summary.json",
    "public_signal_research_breakthrough_v3_validation_summary": ARTIFACT_ROOT / "signal_research_v3" / "public_signal_research_breakthrough_v3_validation_summary.json",
    "public_signal_research_v4_preflight_summary": ARTIFACT_ROOT / "signal_research_v4" / "public_signal_research_v4_preflight_summary.json",
    "research_breakthrough_gate_v4_summary": ARTIFACT_ROOT / "signal_research_v4" / "research_breakthrough_gate_v4_summary.json",
    "public_signal_research_breakthrough_v4_summary": ARTIFACT_ROOT / "signal_research_v4" / "public_signal_research_breakthrough_v4_summary.json",
    "public_signal_research_breakthrough_v4_validation_summary": ARTIFACT_ROOT / "signal_research_v4" / "public_signal_research_breakthrough_v4_validation_summary.json",
    "public_signal_research_v5_preflight_summary": ARTIFACT_ROOT / "signal_research_v5" / "public_signal_research_v5_preflight_summary.json",
    "public_signal_research_v5_baseline_freeze_summary": ARTIFACT_ROOT / "signal_research_v5" / "public_signal_research_v5_baseline_freeze_summary.json",
    "research_mutation_queue_executor_v5_summary": ARTIFACT_ROOT / "signal_research_v5" / "research_mutation_queue_executor_v5_summary.json",
    "no_trade_filter_optimizer_v5_summary": ARTIFACT_ROOT / "signal_research_v5" / "no_trade_filter_optimizer_v5_summary.json",
    "research_candidate_generator_v5_summary": ARTIFACT_ROOT / "signal_research_v5" / "research_candidate_generator_v5_summary.json",
    "profit_holdout_split_scorer_v5_summary": ARTIFACT_ROOT / "signal_research_v5" / "profit_holdout_split_scorer_v5_summary.json",
    "research_path_simulator_v5_summary": ARTIFACT_ROOT / "signal_research_v5" / "research_path_simulator_v5_summary.json",
    "research_tournament_v5_summary": ARTIFACT_ROOT / "signal_research_v5" / "research_tournament_v5_summary.json",
    "research_breakthrough_gate_v5_summary": ARTIFACT_ROOT / "signal_research_v5" / "research_breakthrough_gate_v5_summary.json",
    "research_mutation_queue_v5_summary": ARTIFACT_ROOT / "signal_research_v5" / "research_mutation_queue_v5_summary.json",
    "public_signal_research_breakthrough_v5_summary": ARTIFACT_ROOT / "signal_research_v5" / "public_signal_research_breakthrough_v5_summary.json",
    "public_signal_research_breakthrough_v5_validation_summary": ARTIFACT_ROOT / "signal_research_v5" / "public_signal_research_breakthrough_v5_validation_summary.json",
    "public_signal_research_scoreboard_v5": ARTIFACT_ROOT / "scoreboard" / "public_signal_research_scoreboard_v5.json",
    "public_signal_research_live_gate_status_v5": ARTIFACT_ROOT / "live_gate" / "public_signal_research_live_gate_status_v5.json",
    "public_signal_research_v6_preflight_summary": ARTIFACT_ROOT / "signal_research_v6" / "public_signal_research_v6_preflight_summary.json",
    "public_signal_research_v6_baseline_freeze_summary": ARTIFACT_ROOT / "signal_research_v6" / "public_signal_research_v6_baseline_freeze_summary.json",
    "v5_gate_rejection_analyzer_v6_summary": ARTIFACT_ROOT / "signal_research_v6" / "v5_gate_rejection_analyzer_v6_summary.json",
    "research_mutation_queue_executor_v6_summary": ARTIFACT_ROOT / "signal_research_v6" / "research_mutation_queue_executor_v6_summary.json",
    "breakthrough_blocker_repair_policy_v6_summary": ARTIFACT_ROOT / "signal_research_v6" / "breakthrough_blocker_repair_policy_v6_summary.json",
    "research_candidate_generator_v6_summary": ARTIFACT_ROOT / "signal_research_v6" / "research_candidate_generator_v6_summary.json",
    "profit_holdout_split_scorer_v6_summary": ARTIFACT_ROOT / "signal_research_v6" / "profit_holdout_split_scorer_v6_summary.json",
    "research_path_simulator_v6_summary": ARTIFACT_ROOT / "signal_research_v6" / "research_path_simulator_v6_summary.json",
    "research_tournament_v6_summary": ARTIFACT_ROOT / "signal_research_v6" / "research_tournament_v6_summary.json",
    "research_breakthrough_gate_v6_summary": ARTIFACT_ROOT / "signal_research_v6" / "research_breakthrough_gate_v6_summary.json",
    "research_mutation_queue_v6_summary": ARTIFACT_ROOT / "signal_research_v6" / "research_mutation_queue_v6_summary.json",
    "public_signal_research_breakthrough_v6_summary": ARTIFACT_ROOT / "signal_research_v6" / "public_signal_research_breakthrough_v6_summary.json",
    "public_signal_research_breakthrough_v6_validation_summary": ARTIFACT_ROOT / "signal_research_v6" / "public_signal_research_breakthrough_v6_validation_summary.json",
    "public_signal_research_scoreboard_v6": ARTIFACT_ROOT / "scoreboard" / "public_signal_research_scoreboard_v6.json",
    "public_signal_research_live_gate_status_v6": ARTIFACT_ROOT / "live_gate" / "public_signal_research_live_gate_status_v6.json",
    "public_signal_research_v7_preflight_summary": ARTIFACT_ROOT / "signal_research_v7" / "public_signal_research_v7_preflight_summary.json",
    "public_signal_research_v7_baseline_freeze_summary": ARTIFACT_ROOT / "signal_research_v7" / "public_signal_research_v7_baseline_freeze_summary.json",
    "no_trade_contribution_audit_v7_summary": ARTIFACT_ROOT / "signal_research_v7" / "no_trade_contribution_audit_v7_summary.json",
    "v6_watchlist_diagnosis_v7_summary": ARTIFACT_ROOT / "signal_research_v7" / "v6_watchlist_diagnosis_v7_summary.json",
    "research_mutation_queue_executor_v7_summary": ARTIFACT_ROOT / "signal_research_v7" / "research_mutation_queue_executor_v7_summary.json",
    "trade_active_repair_policy_v7_summary": ARTIFACT_ROOT / "signal_research_v7" / "trade_active_repair_policy_v7_summary.json",
    "research_candidate_generator_v7_summary": ARTIFACT_ROOT / "signal_research_v7" / "research_candidate_generator_v7_summary.json",
    "profit_holdout_split_scorer_v7_summary": ARTIFACT_ROOT / "signal_research_v7" / "profit_holdout_split_scorer_v7_summary.json",
    "research_path_simulator_v7_summary": ARTIFACT_ROOT / "signal_research_v7" / "research_path_simulator_v7_summary.json",
    "research_tournament_v7_summary": ARTIFACT_ROOT / "signal_research_v7" / "research_tournament_v7_summary.json",
    "research_breakthrough_gate_v7_summary": ARTIFACT_ROOT / "signal_research_v7" / "research_breakthrough_gate_v7_summary.json",
    "research_mutation_queue_v7_summary": ARTIFACT_ROOT / "signal_research_v7" / "research_mutation_queue_v7_summary.json",
    "public_signal_research_breakthrough_v7_summary": ARTIFACT_ROOT / "signal_research_v7" / "public_signal_research_breakthrough_v7_summary.json",
    "public_signal_research_breakthrough_v7_validation_summary": ARTIFACT_ROOT / "signal_research_v7" / "public_signal_research_breakthrough_v7_validation_summary.json",
    "public_signal_research_scoreboard_v7": ARTIFACT_ROOT / "scoreboard" / "public_signal_research_scoreboard_v7.json",
    "public_signal_research_live_gate_status_v7": ARTIFACT_ROOT / "live_gate" / "public_signal_research_live_gate_status_v7.json",
    "public_market_paper_champion_evolution_summary": ARTIFACT_ROOT / "public_champion_evolution" / "public_market_paper_champion_evolution_summary.json",
    "public_market_paper_champion_validation_summary": ARTIFACT_ROOT / "public_champion_evolution" / "public_market_paper_champion_validation_summary.json",
}


@dataclass(frozen=True)
class ReportingEvidence:
    tournament: dict
    champion: dict
    mutation: dict
    feedback: dict
    failure_modes: dict
    ensemble: dict
    meta_governor: dict
    meta_governor_decisions: dict
    macro_events: dict
    iv_surface: dict
    fundamental: dict
    stronger_consistency: dict
    corpus_v2: dict
    audit: dict
    active_policy: dict
    paper_account_ledger: dict
    rotation_plan: dict
    day_trade_event_log: dict
    zero_dte_risk_summary: dict
    zero_dte_replay_summary: dict
    zero_dte_threshold_optimizer_summary: dict
    zero_dte_adversarial_coverage_summary: dict
    zero_dte_combined_replay_summary: dict
    zero_dte_cross_underlying_coverage_summary: dict
    zero_dte_combined_v1_v2_replay_summary: dict
    zero_dte_cross_underlying_threshold_survival: dict
    hybrid_coverage_summary: dict
    hybrid_replay_summary: dict
    hybrid_threshold_survival: dict
    paper_allocation_plan: dict
    allocation_exposure_summary: dict
    allocation_constraint_summary: dict
    portfolio_replay_summary: dict
    portfolio_exposure_snapshots: dict
    exposure_stress_results: dict
    portfolio_allocator_feedback: dict
    portfolio_threshold_feedback: dict
    stress_ladder_summary: dict
    stress_level_evaluations: dict
    crisis_throttle_results: dict
    crisis_recovery_results: dict
    crisis_allocator_feedback: dict
    crisis_threshold_feedback: dict
    incident_rehearsal_summary: dict
    incident_signals: dict
    kill_switch_states: dict
    incident_response_decisions: dict
    incident_recovery_plans: dict
    incident_allocator_feedback: dict
    incident_threshold_feedback: dict
    incident_stress_ladder_feedback: dict
    lifecycle_summary: dict
    lifecycle_states: dict
    lifecycle_transitions: dict
    lifecycle_paperbroker_results: dict
    lifecycle_account_ledger_results: dict
    lifecycle_feedback_allocator: dict
    lifecycle_feedback_portfolio: dict
    lifecycle_feedback_stress_ladder: dict
    lifecycle_feedback_incident: dict
    broker_readiness_summary: dict
    broker_readiness_run_result: dict
    broker_readiness_manual_gates: dict
    broker_readiness_boundary_blocks: dict
    manual_approval_packet_summary: dict
    manual_approval_gate: dict
    read_only_detector_scope: dict
    future_detector_command_templates: dict
    manual_approval_boundary_blocks: dict
    read_only_detector_dry_run_summary: dict
    read_only_detector_dry_run_results: dict
    simulated_broker_capability_responses: dict
    dry_run_boundary_blocks: dict
    approval_intake_requests: dict
    approval_scope_validations: dict
    approval_intake_results: dict
    approval_forbidden_terms: dict
    approval_boundary_blocks: dict
    approval_incident_escalations: dict
    approval_intake_summary: dict
    approval_intake_proof: dict
    handoff_inputs: dict
    future_detector_run_envelopes: dict
    approval_to_run_gate_decisions: dict
    disabled_handoff_command_templates: dict
    handoff_boundary_blocks: dict
    handoff_incident_escalations: dict
    approval_to_run_handoff_summary: dict
    approval_to_run_handoff_proof: dict
    pre_run_safety_summary: dict
    pre_run_safety_proof: dict
    read_only_detector_run_requests: dict
    read_only_capability_records: dict
    read_only_blocked_write_execute_records: dict
    read_only_provider_boundary_results: dict
    read_only_detector_run_results: dict
    read_only_detector_post_run_evidence: dict
    read_only_detector_incident_escalations: dict
    read_only_detector_summary: dict
    read_only_detector_proof: dict
    evidence_contract: dict
    evidence_items: dict
    boundary_assertions: dict
    evidence_validation_results: dict
    evidence_promotion_decisions: dict
    evidence_contract_summary: dict
    evidence_contract_proof: dict
    history_spine_summary: dict
    history_dataset_validation: dict
    history_symbol_coverage: dict
    history_quality_flags: dict
    model_repricing_summary: dict
    iv_solver_validation: dict
    vol_surface_model: dict
    model_repricing_quality_flags: dict
    signal_engine_summary: dict
    signal_engine_input_summary: dict
    signal_quality_flags: dict
    backtest_run_summary: dict
    backtest_quality_flags: dict
    backtest_trade_records: dict
    statistical_truth_summary: dict
    statistical_truth_quality_flags: dict
    backtest_metric_set: dict
    bootstrap_confidence_intervals: dict
    baseline_comparisons: dict
    statistical_truth_decision: dict
    fitness_replacement_summary: dict
    fitness_quality_flags: dict
    fitness_decision: dict
    data_ingestion_plan_summary: dict
    import_readiness_decision: dict
    data_ingestion_plan: dict
    dataset_requirements: dict
    provider_candidates: dict
    schema_contracts: dict
    data_quality_gates: dict
    local_ohlcv_import_summary: dict
    real_ohlcv_history_spine_upgrade: dict
    real_ohlcv_history_spine_activation: dict
    real_signal_validation_summary: dict
    options_data_contract_summary: dict
    real_data_validation_stack_summary: dict
    open_source_path_summary: dict
    local_free_ohlcv_stack_summary: dict
    manual_ohlcv_staging_summary: dict
    operator_reviewed_ohlcv_stage_summary: dict
    autonomous_admissibility_kernel_summary: dict
    autonomous_oss_discovery_summary: dict
    autonomous_open_data_validator_bridge_summary: dict
    open_options_data_autonomy_summary: dict
    autonomous_research_engine_summary: dict
    autonomous_backtest_stat_fitness_summary: dict
    autonomous_paper_trading_loop_summary: dict
    s_tier_options_benchmark_summary: dict
    full_open_source_autonomous_orchestrator_summary: dict
    open_data_breakthrough_full_completion_summary: dict
    exhaustive_open_data_discovery_matrix_summary: dict
    quote_priced_options_unlock_gate: dict
    model_priced_options_research_summary: dict
    finish_everything_orchestrator_summary: dict
    openbb_provider_registry_summary: dict
    openbb_validator_bridge_summary: dict
    model_priced_v2_research_summary: dict
    s_tier_v2_summary: dict
    paper_rotation_engine_summary: dict
    remaining_gap_eliminator_summary: dict
    wealth_engine_summary: dict
    wealth_engine_validation_summary: dict
    market_data_lake_summary: dict
    chart_vision_summary: dict
    pnl_scoreboard_summary: dict
    provider_install_repair_summary: dict
    provider_health_diagnostics_summary: dict
    public_ohlcv_provider_ladder_v2_summary: dict
    market_lake_public_promotion_summary: dict
    market_data_cache_summary: dict
    market_universe_expansion_summary: dict
    real_public_market_wealth_rerun_summary: dict
    real_public_market_wealth_validation_summary: dict
    public_vs_fixture_scoreboard_split: dict
    public_lake_freeze_guard_summary: dict
    public_universe_expansion_v2_summary: dict
    model_priced_path_simulator_v3_summary: dict
    public_signal_mutation_factory_v3_summary: dict
    public_walk_forward_tournament_v3_summary: dict
    public_paper_champion_gate_summary: dict
    public_champion_scoreboard_v3: dict
    public_champion_evolution_summary: dict
    public_champion_risk_summary_v3: dict
    public_champion_live_gate_status: dict
    public_market_paper_champion_evolution_summary: dict
    public_market_paper_champion_validation_summary: dict
    public_signal_research_v7_preflight_summary: dict
    public_signal_research_v7_baseline_freeze_summary: dict
    no_trade_contribution_audit_v7_summary: dict
    v6_watchlist_diagnosis_v7_summary: dict
    research_mutation_queue_executor_v7_summary: dict
    trade_active_repair_policy_v7_summary: dict
    research_candidate_generator_v7_summary: dict
    profit_holdout_split_scorer_v7_summary: dict
    research_path_simulator_v7_summary: dict
    research_tournament_v7_summary: dict
    research_breakthrough_gate_v7_summary: dict
    research_mutation_queue_v7_summary: dict
    public_signal_research_breakthrough_v7_summary: dict
    public_signal_research_breakthrough_v7_validation_summary: dict
    public_signal_research_scoreboard_v7: dict
    public_signal_research_live_gate_status_v7: dict


def safety_state() -> dict:
    cfg = load_config(default_config_path())
    return {
        "mode": str(cfg.get("mode", "RESEARCH")),
        "live_trading_enabled": bool(cfg.get("live_trading_enabled", False)),
        "funded_broker_connections_enabled": bool(cfg.get("funded_broker_connections_enabled", False)),
        "allow_unofficial_robinhood_api": bool(cfg.get("allow_unofficial_robinhood_api", False)),
        "paper_only_reporting": True,
        "fixture_only": True,
        "live_blocked": True,
    }


def verify_reporting_safety_state(state: dict) -> None:
    if state.get("mode") != "RESEARCH":
        raise ValueError(f"reporting bundle requires RESEARCH mode, got {state.get('mode')}")
    if state.get("live_trading_enabled") is not False:
        raise ValueError("reporting bundle requires live_trading_enabled=false")
    if state.get("funded_broker_connections_enabled") is not False:
        raise ValueError("reporting bundle requires funded_broker_connections_enabled=false")
    if state.get("allow_unofficial_robinhood_api") is not False:
        raise ValueError("reporting bundle requires allow_unofficial_robinhood_api=false")


def load_latest_jsonl(path: Path | str) -> dict:
    target = Path(path)
    if not target.exists():
        return {}
    lines = [line for line in target.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not lines:
        return {}
    return json.loads(lines[-1])


def load_reporting_evidence(paths: dict[str, Path]) -> ReportingEvidence:
    resolved = paths
    latest_backtest_trade_record = _load_reporting_backtest_trade_record(
        resolved["backtest_trade_records"]
    )
    return ReportingEvidence(
        tournament=load_latest_jsonl(resolved["tournament"]),
        champion=load_latest_jsonl(resolved["champion"]),
        mutation=load_latest_jsonl(resolved["mutation"]),
        feedback=load_latest_jsonl(resolved["feedback"]),
        failure_modes=load_latest_jsonl(resolved["failure_modes"]),
        ensemble=load_latest_jsonl(resolved["ensemble"]),
        meta_governor=load_latest_jsonl(resolved["meta_governor"]),
        meta_governor_decisions=load_latest_jsonl(resolved["meta_governor_decisions"]),
        macro_events=load_latest_jsonl(resolved["macro_events"]),
        iv_surface=load_latest_jsonl(resolved["iv_surface"]),
        fundamental=load_latest_jsonl(resolved["fundamental"]),
        stronger_consistency=load_latest_jsonl(resolved["stronger_consistency"]),
        corpus_v2=load_latest_jsonl(resolved["corpus_v2"]),
        audit=load_latest_jsonl(resolved["audit"]),
        active_policy=load_latest_jsonl(resolved["active_policy"]),
        paper_account_ledger=load_latest_json_or_jsonl(resolved["paper_account_ledger"]),
        rotation_plan=load_latest_json_or_jsonl(resolved["rotation_plan"]),
        day_trade_event_log=load_latest_json_or_jsonl(resolved["day_trade_event_log"]),
        zero_dte_risk_summary=load_latest_json_or_jsonl(resolved["zero_dte_risk_summary"]),
        zero_dte_replay_summary=load_latest_json_or_jsonl(resolved["zero_dte_replay_summary"]),
        zero_dte_threshold_optimizer_summary=load_latest_json_or_jsonl(resolved["zero_dte_threshold_optimizer_summary"]),
        zero_dte_adversarial_coverage_summary=load_latest_json_or_jsonl(resolved["zero_dte_adversarial_coverage_summary"]),
        zero_dte_combined_replay_summary=load_latest_json_or_jsonl(resolved["zero_dte_combined_replay_summary"]),
        zero_dte_cross_underlying_coverage_summary=load_latest_json_or_jsonl(resolved["zero_dte_cross_underlying_coverage_summary"]),
        zero_dte_combined_v1_v2_replay_summary=load_latest_json_or_jsonl(resolved["zero_dte_combined_v1_v2_replay_summary"]),
        zero_dte_cross_underlying_threshold_survival=load_latest_json_or_jsonl(resolved["zero_dte_cross_underlying_threshold_survival"]),
        hybrid_coverage_summary=load_latest_json_or_jsonl(resolved["hybrid_coverage_summary"]),
        hybrid_replay_summary=load_latest_json_or_jsonl(resolved["hybrid_replay_summary"]),
        hybrid_threshold_survival=load_latest_json_or_jsonl(resolved["hybrid_threshold_survival"]),
        paper_allocation_plan=load_latest_json_or_jsonl(resolved["paper_allocation_plan"]),
        allocation_exposure_summary=load_latest_json_or_jsonl(resolved["allocation_exposure_summary"]),
        allocation_constraint_summary=load_latest_json_or_jsonl(resolved["allocation_constraint_summary"]),
        portfolio_replay_summary=load_latest_json_or_jsonl(resolved["portfolio_replay_summary"]),
        portfolio_exposure_snapshots=load_latest_json_or_jsonl(resolved["portfolio_exposure_snapshots"]),
        exposure_stress_results=load_latest_json_or_jsonl(resolved["exposure_stress_results"]),
        portfolio_allocator_feedback=load_latest_json_or_jsonl(resolved["portfolio_allocator_feedback"]),
        portfolio_threshold_feedback=load_latest_json_or_jsonl(resolved["portfolio_threshold_feedback"]),
        stress_ladder_summary=load_latest_json_or_jsonl(resolved["stress_ladder_summary"]),
        stress_level_evaluations=load_latest_json_or_jsonl(resolved["stress_level_evaluations"]),
        crisis_throttle_results=load_latest_json_or_jsonl(resolved["crisis_throttle_results"]),
        crisis_recovery_results=load_latest_json_or_jsonl(resolved["crisis_recovery_results"]),
        crisis_allocator_feedback=load_latest_json_or_jsonl(resolved["crisis_allocator_feedback"]),
        crisis_threshold_feedback=load_latest_json_or_jsonl(resolved["crisis_threshold_feedback"]),
        incident_rehearsal_summary=load_latest_json_or_jsonl(resolved["incident_rehearsal_summary"]),
        incident_signals=load_latest_json_or_jsonl(resolved["incident_signals"]),
        kill_switch_states=load_latest_json_or_jsonl(resolved["kill_switch_states"]),
        incident_response_decisions=load_latest_json_or_jsonl(resolved["incident_response_decisions"]),
        incident_recovery_plans=load_latest_json_or_jsonl(resolved["incident_recovery_plans"]),
        incident_allocator_feedback=load_latest_json_or_jsonl(resolved["incident_allocator_feedback"]),
        incident_threshold_feedback=load_latest_json_or_jsonl(resolved["incident_threshold_feedback"]),
        incident_stress_ladder_feedback=load_latest_json_or_jsonl(resolved["incident_stress_ladder_feedback"]),
        lifecycle_summary=load_latest_json_or_jsonl(resolved["lifecycle_summary"]),
        lifecycle_states=load_latest_json_or_jsonl(resolved["lifecycle_states"]),
        lifecycle_transitions=load_latest_json_or_jsonl(resolved["lifecycle_transitions"]),
        lifecycle_paperbroker_results=load_latest_json_or_jsonl(resolved["lifecycle_paperbroker_results"]),
        lifecycle_account_ledger_results=load_latest_json_or_jsonl(resolved["lifecycle_account_ledger_results"]),
        lifecycle_feedback_allocator=load_latest_json_or_jsonl(resolved["lifecycle_feedback_allocator"]),
        lifecycle_feedback_portfolio=load_latest_json_or_jsonl(resolved["lifecycle_feedback_portfolio"]),
        lifecycle_feedback_stress_ladder=load_latest_json_or_jsonl(resolved["lifecycle_feedback_stress_ladder"]),
        lifecycle_feedback_incident=load_latest_json_or_jsonl(resolved["lifecycle_feedback_incident"]),
        broker_readiness_summary=load_latest_json_or_jsonl(resolved["broker_readiness_summary"]),
        broker_readiness_run_result=load_latest_json_or_jsonl(resolved["broker_readiness_run_result"]),
        broker_readiness_manual_gates=load_latest_json_or_jsonl(resolved["broker_readiness_manual_gates"]),
        broker_readiness_boundary_blocks=load_latest_json_or_jsonl(resolved["broker_readiness_boundary_blocks"]),
        manual_approval_packet_summary=load_latest_json_or_jsonl(resolved["manual_approval_packet_summary"]),
        manual_approval_gate=load_latest_json_or_jsonl(resolved["manual_approval_gate"]),
        read_only_detector_scope=load_latest_json_or_jsonl(resolved["read_only_detector_scope"]),
        future_detector_command_templates=load_latest_json_or_jsonl(resolved["future_detector_command_templates"]),
        manual_approval_boundary_blocks=load_latest_json_or_jsonl(resolved["manual_approval_boundary_blocks"]),
        read_only_detector_dry_run_summary=load_latest_json_or_jsonl(resolved["read_only_detector_dry_run_summary"]),
        read_only_detector_dry_run_results=load_latest_json_or_jsonl(resolved["read_only_detector_dry_run_results"]),
        simulated_broker_capability_responses=load_latest_json_or_jsonl(resolved["simulated_broker_capability_responses"]),
        dry_run_boundary_blocks=load_latest_json_or_jsonl(resolved["dry_run_boundary_blocks"]),
        approval_intake_requests=load_latest_json_or_jsonl(resolved["approval_intake_requests"]),
        approval_scope_validations=load_latest_json_or_jsonl(resolved["approval_scope_validations"]),
        approval_intake_results=load_latest_json_or_jsonl(resolved["approval_intake_results"]),
        approval_forbidden_terms=load_latest_json_or_jsonl(resolved["approval_forbidden_terms"]),
        approval_boundary_blocks=load_latest_json_or_jsonl(resolved["approval_boundary_blocks"]),
        approval_incident_escalations=load_latest_json_or_jsonl(resolved["approval_incident_escalations"]),
        approval_intake_summary=load_latest_json_or_jsonl(resolved["approval_intake_summary"]),
        approval_intake_proof=load_latest_json_or_jsonl(resolved["approval_intake_proof"]),
        handoff_inputs=load_latest_json_or_jsonl(resolved["handoff_inputs"]),
        future_detector_run_envelopes=load_latest_json_or_jsonl(resolved["future_detector_run_envelopes"]),
        approval_to_run_gate_decisions=load_latest_json_or_jsonl(resolved["approval_to_run_gate_decisions"]),
        disabled_handoff_command_templates=load_latest_json_or_jsonl(resolved["disabled_handoff_command_templates"]),
        handoff_boundary_blocks=load_latest_json_or_jsonl(resolved["handoff_boundary_blocks"]),
        handoff_incident_escalations=load_latest_json_or_jsonl(resolved["handoff_incident_escalations"]),
        approval_to_run_handoff_summary=load_latest_json_or_jsonl(resolved["approval_to_run_handoff_summary"]),
        approval_to_run_handoff_proof=load_latest_json_or_jsonl(resolved["approval_to_run_handoff_proof"]),
        pre_run_safety_summary=load_latest_json_or_jsonl(resolved["pre_run_safety_summary"]),
        pre_run_safety_proof=load_latest_json_or_jsonl(resolved["pre_run_safety_proof"]),
        read_only_detector_run_requests=load_latest_json_or_jsonl(resolved["read_only_detector_run_requests"]),
        read_only_capability_records=load_latest_json_or_jsonl(resolved["read_only_capability_records"]),
        read_only_blocked_write_execute_records=load_latest_json_or_jsonl(resolved["read_only_blocked_write_execute_records"]),
        read_only_provider_boundary_results=load_latest_json_or_jsonl(resolved["read_only_provider_boundary_results"]),
        read_only_detector_run_results=load_latest_json_or_jsonl(resolved["read_only_detector_run_results"]),
        read_only_detector_post_run_evidence=load_latest_json_or_jsonl(resolved["read_only_detector_post_run_evidence"]),
        read_only_detector_incident_escalations=load_latest_json_or_jsonl(resolved["read_only_detector_incident_escalations"]),
        read_only_detector_summary=load_latest_json_or_jsonl(resolved["read_only_detector_summary"]),
        read_only_detector_proof=load_latest_json_or_jsonl(resolved["read_only_detector_proof"]),
        evidence_contract=load_latest_json_or_jsonl(resolved["evidence_contract"]),
        evidence_items=load_latest_json_or_jsonl(resolved["evidence_items"]),
        boundary_assertions=load_latest_json_or_jsonl(resolved["boundary_assertions"]),
        evidence_validation_results=load_latest_json_or_jsonl(resolved["evidence_validation_results"]),
        evidence_promotion_decisions=load_latest_json_or_jsonl(resolved["evidence_promotion_decisions"]),
        evidence_contract_summary=load_latest_json_or_jsonl(resolved["evidence_contract_summary"]),
        evidence_contract_proof=load_latest_json_or_jsonl(resolved["evidence_contract_proof"]),
        history_spine_summary=load_latest_json_or_jsonl(resolved["history_spine_summary"]),
        history_dataset_validation=load_latest_json_or_jsonl(resolved["history_dataset_validation"]),
        history_symbol_coverage=load_latest_json_or_jsonl(resolved["history_symbol_coverage"]),
        history_quality_flags=load_latest_json_or_jsonl(resolved["history_quality_flags"]),
        model_repricing_summary=load_latest_json_or_jsonl(resolved["model_repricing_summary"]),
        iv_solver_validation=load_latest_json_or_jsonl(resolved["iv_solver_validation"]),
        vol_surface_model=load_latest_json_or_jsonl(resolved["vol_surface_model"]),
        model_repricing_quality_flags=load_latest_json_or_jsonl(resolved["model_repricing_quality_flags"]),
        signal_engine_summary=load_latest_json_or_jsonl(resolved["signal_engine_summary"]),
        signal_engine_input_summary=load_latest_json_or_jsonl(resolved["signal_engine_input_summary"]),
        signal_quality_flags=load_latest_json_or_jsonl(resolved["signal_quality_flags"]),
        backtest_run_summary=load_latest_json_or_jsonl(resolved["backtest_run_summary"]),
        backtest_quality_flags=load_latest_json_or_jsonl(resolved["backtest_quality_flags"]),
        backtest_trade_records=latest_backtest_trade_record,
        statistical_truth_summary=load_latest_json_or_jsonl(resolved["statistical_truth_summary"]),
        statistical_truth_quality_flags=load_latest_json_or_jsonl(resolved["statistical_truth_quality_flags"]),
        backtest_metric_set=load_latest_json_or_jsonl(resolved["backtest_metric_set"]),
        bootstrap_confidence_intervals=load_latest_json_or_jsonl(resolved["bootstrap_confidence_intervals"]),
        baseline_comparisons=load_latest_json_or_jsonl(resolved["baseline_comparisons"]),
        statistical_truth_decision=load_latest_json_or_jsonl(resolved["statistical_truth_decision"]),
        fitness_replacement_summary=load_latest_json_or_jsonl(resolved["fitness_replacement_summary"]),
        fitness_quality_flags=load_latest_json_or_jsonl(resolved["fitness_quality_flags"]),
        fitness_decision=load_latest_json_or_jsonl(resolved["fitness_decision"]),
        data_ingestion_plan_summary=load_latest_json_or_jsonl(resolved["data_ingestion_plan_summary"]),
        import_readiness_decision=load_latest_json_or_jsonl(resolved["import_readiness_decision"]),
        data_ingestion_plan=load_latest_json_or_jsonl(resolved["data_ingestion_plan"]),
        dataset_requirements=load_latest_json_or_jsonl(resolved["dataset_requirements"]),
        provider_candidates=load_latest_json_or_jsonl(resolved["provider_candidates"]),
        schema_contracts=load_latest_json_or_jsonl(resolved["schema_contracts"]),
        data_quality_gates=load_latest_json_or_jsonl(resolved["data_quality_gates"]),
        local_ohlcv_import_summary=load_latest_json_or_jsonl(resolved["local_ohlcv_import_summary"]),
        real_ohlcv_history_spine_upgrade=load_latest_json_or_jsonl(resolved["real_ohlcv_history_spine_upgrade"]),
        real_ohlcv_history_spine_activation=load_latest_json_or_jsonl(resolved["real_ohlcv_history_spine_activation"]),
        real_signal_validation_summary=load_latest_json_or_jsonl(resolved["real_signal_validation_summary"]),
        options_data_contract_summary=load_latest_json_or_jsonl(resolved["options_data_contract_summary"]),
        real_data_validation_stack_summary=load_latest_json_or_jsonl(resolved["real_data_validation_stack_summary"]),
        open_source_path_summary=load_latest_json_or_jsonl(resolved["open_source_path_summary"]),
        local_free_ohlcv_stack_summary=load_latest_json_or_jsonl(resolved["local_free_ohlcv_stack_summary"]),
        manual_ohlcv_staging_summary=load_latest_json_or_jsonl(resolved["manual_ohlcv_staging_summary"]),
        operator_reviewed_ohlcv_stage_summary=load_latest_json_or_jsonl(resolved["operator_reviewed_ohlcv_stage_summary"]),
        autonomous_admissibility_kernel_summary=load_latest_json_or_jsonl(resolved["autonomous_admissibility_kernel_summary"]),
        autonomous_oss_discovery_summary=load_latest_json_or_jsonl(resolved["autonomous_oss_discovery_summary"]),
        autonomous_open_data_validator_bridge_summary=load_latest_json_or_jsonl(resolved["autonomous_open_data_validator_bridge_summary"]),
        open_options_data_autonomy_summary=load_latest_json_or_jsonl(resolved["open_options_data_autonomy_summary"]),
        autonomous_research_engine_summary=load_latest_json_or_jsonl(resolved["autonomous_research_engine_summary"]),
        autonomous_backtest_stat_fitness_summary=load_latest_json_or_jsonl(resolved["autonomous_backtest_stat_fitness_summary"]),
        autonomous_paper_trading_loop_summary=load_latest_json_or_jsonl(resolved["autonomous_paper_trading_loop_summary"]),
        s_tier_options_benchmark_summary=load_latest_json_or_jsonl(resolved["s_tier_options_benchmark_summary"]),
        full_open_source_autonomous_orchestrator_summary=load_latest_json_or_jsonl(resolved["full_open_source_autonomous_orchestrator_summary"]),
        open_data_breakthrough_full_completion_summary=load_latest_json_or_jsonl(resolved["open_data_breakthrough_full_completion_summary"]),
        exhaustive_open_data_discovery_matrix_summary=load_latest_json_or_jsonl(resolved["exhaustive_open_data_discovery_matrix_summary"]),
        quote_priced_options_unlock_gate=load_latest_json_or_jsonl(resolved["quote_priced_options_unlock_gate"]),
        model_priced_options_research_summary=load_latest_json_or_jsonl(resolved["model_priced_options_research_summary"]),
        finish_everything_orchestrator_summary=load_latest_json_or_jsonl(resolved["finish_everything_orchestrator_summary"]),
        openbb_provider_registry_summary=load_latest_json_or_jsonl(resolved["openbb_provider_registry_summary"]),
        openbb_validator_bridge_summary=load_latest_json_or_jsonl(resolved["openbb_validator_bridge_summary"]),
        model_priced_v2_research_summary=load_latest_json_or_jsonl(resolved["model_priced_v2_research_summary"]),
        s_tier_v2_summary=load_latest_json_or_jsonl(resolved["s_tier_v2_summary"]),
        paper_rotation_engine_summary=load_latest_json_or_jsonl(resolved["paper_rotation_engine_summary"]),
        remaining_gap_eliminator_summary=load_latest_json_or_jsonl(resolved["remaining_gap_eliminator_summary"]),
        wealth_engine_summary=load_latest_json_or_jsonl(resolved["wealth_engine_summary"]),
        wealth_engine_validation_summary=load_latest_json_or_jsonl(resolved["wealth_engine_validation_summary"]),
        market_data_lake_summary=load_latest_json_or_jsonl(resolved["market_data_lake_summary"]),
        chart_vision_summary=load_latest_json_or_jsonl(resolved["chart_vision_summary"]),
        pnl_scoreboard_summary=load_latest_json_or_jsonl(resolved["pnl_scoreboard_summary"]),
        provider_install_repair_summary=load_latest_json_or_jsonl(resolved["provider_install_repair_summary"]),
        provider_health_diagnostics_summary=load_latest_json_or_jsonl(resolved["provider_health_diagnostics_summary"]),
        public_ohlcv_provider_ladder_v2_summary=load_latest_json_or_jsonl(resolved["public_ohlcv_provider_ladder_v2_summary"]),
        market_lake_public_promotion_summary=load_latest_json_or_jsonl(resolved["market_lake_public_promotion_summary"]),
        market_data_cache_summary=load_latest_json_or_jsonl(resolved["market_data_cache_summary"]),
        market_universe_expansion_summary=load_latest_json_or_jsonl(resolved["market_universe_expansion_summary"]),
        real_public_market_wealth_rerun_summary=load_latest_json_or_jsonl(resolved["real_public_market_wealth_rerun_summary"]),
        real_public_market_wealth_validation_summary=load_latest_json_or_jsonl(resolved["real_public_market_wealth_validation_summary"]),
        public_vs_fixture_scoreboard_split=load_latest_json_or_jsonl(resolved["public_vs_fixture_scoreboard_split"]),
        public_lake_freeze_guard_summary=load_latest_json_or_jsonl(resolved["public_lake_freeze_guard_summary"]),
        public_universe_expansion_v2_summary=load_latest_json_or_jsonl(resolved["public_universe_expansion_v2_summary"]),
        model_priced_path_simulator_v3_summary=load_latest_json_or_jsonl(resolved["model_priced_path_simulator_v3_summary"]),
        public_signal_mutation_factory_v3_summary=load_latest_json_or_jsonl(resolved["public_signal_mutation_factory_v3_summary"]),
        public_walk_forward_tournament_v3_summary=load_latest_json_or_jsonl(resolved["public_walk_forward_tournament_v3_summary"]),
        public_paper_champion_gate_summary=load_latest_json_or_jsonl(resolved["public_paper_champion_gate_summary"]),
        public_champion_scoreboard_v3=load_latest_json_or_jsonl(resolved["public_champion_scoreboard_v3"]),
        public_champion_evolution_summary=load_latest_json_or_jsonl(resolved["public_champion_evolution_summary"]),
        public_champion_risk_summary_v3=load_latest_json_or_jsonl(resolved["public_champion_risk_summary_v3"]),
        public_champion_live_gate_status=load_latest_json_or_jsonl(resolved["public_champion_live_gate_status"]),
        public_market_paper_champion_evolution_summary=load_latest_json_or_jsonl(resolved["public_market_paper_champion_evolution_summary"]),
        public_market_paper_champion_validation_summary=load_latest_json_or_jsonl(resolved["public_market_paper_champion_validation_summary"]),
        public_signal_research_v7_preflight_summary=load_latest_json_or_jsonl(resolved["public_signal_research_v7_preflight_summary"]),
        public_signal_research_v7_baseline_freeze_summary=load_latest_json_or_jsonl(resolved["public_signal_research_v7_baseline_freeze_summary"]),
        no_trade_contribution_audit_v7_summary=load_latest_json_or_jsonl(resolved["no_trade_contribution_audit_v7_summary"]),
        v6_watchlist_diagnosis_v7_summary=load_latest_json_or_jsonl(resolved["v6_watchlist_diagnosis_v7_summary"]),
        research_mutation_queue_executor_v7_summary=load_latest_json_or_jsonl(resolved["research_mutation_queue_executor_v7_summary"]),
        trade_active_repair_policy_v7_summary=load_latest_json_or_jsonl(resolved["trade_active_repair_policy_v7_summary"]),
        research_candidate_generator_v7_summary=load_latest_json_or_jsonl(resolved["research_candidate_generator_v7_summary"]),
        profit_holdout_split_scorer_v7_summary=load_latest_json_or_jsonl(resolved["profit_holdout_split_scorer_v7_summary"]),
        research_path_simulator_v7_summary=load_latest_json_or_jsonl(resolved["research_path_simulator_v7_summary"]),
        research_tournament_v7_summary=load_latest_json_or_jsonl(resolved["research_tournament_v7_summary"]),
        research_breakthrough_gate_v7_summary=load_latest_json_or_jsonl(resolved["research_breakthrough_gate_v7_summary"]),
        research_mutation_queue_v7_summary=load_latest_json_or_jsonl(resolved["research_mutation_queue_v7_summary"]),
        public_signal_research_breakthrough_v7_summary=load_latest_json_or_jsonl(resolved["public_signal_research_breakthrough_v7_summary"]),
        public_signal_research_breakthrough_v7_validation_summary=load_latest_json_or_jsonl(resolved["public_signal_research_breakthrough_v7_validation_summary"]),
        public_signal_research_scoreboard_v7=load_latest_json_or_jsonl(resolved["public_signal_research_scoreboard_v7"]),
        public_signal_research_live_gate_status_v7=load_latest_json_or_jsonl(resolved["public_signal_research_live_gate_status_v7"]),
    )


def _load_reporting_backtest_trade_record(path: Path) -> dict:
    if not path.exists():
        return {}
    canonical_path = EVIDENCE_PATHS["backtest_trade_records"].resolve()
    if path.resolve() != canonical_path:
        return load_latest_json_or_jsonl(path)
    resolution = resolve_default_backtest_trade_ledger()
    latest: dict[str, object] = {}
    for record in iter_verified_trade_records(resolution):
        latest = record
    return dict(latest)


def write_json(path: Path | str, record: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def load_latest_json_or_jsonl(path: Path | str) -> dict:
    target = Path(path)
    if not target.exists():
        return {}
    if target.suffix.lower() == ".json":
        text = target.read_text(encoding="utf-8-sig").strip()
        return json.loads(text) if text else {}
    return load_latest_jsonl(target)


def write_jsonl_records(path: Path | str, records: list[dict]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return target


def artifact_paths() -> dict[str, str]:
    return {
        "dashboard_index_json": str(REPORTING_DASHBOARD_INDEX_JSON),
        "dashboard_index_md": str(REPORTING_DASHBOARD_INDEX_MD),
        "strategy_report_cards": str(STRATEGY_REPORT_CARDS_PATH),
        "family_report_cards": str(FAMILY_REPORT_CARDS_PATH),
        "scenario_report_cards": str(SCENARIO_REPORT_CARDS_PATH),
        "regime_report_cards": str(REGIME_REPORT_CARDS_PATH),
        "performance_attribution": str(PERFORMANCE_ATTRIBUTION_PATH),
        "reporting_bundle_summary": str(REPORTING_BUNDLE_SUMMARY_PATH),
        "static_dashboard": str(STATIC_DASHBOARD_PATH),
        "reporting_bundle_proof": str(REPORTING_PROOF_PATH),
        "active_policy_audit": str(EVIDENCE_PATHS["active_policy"]),
        "active_policy_integration_map": str(ARTIFACT_ROOT / "governor" / "active_policy_integration_map.json"),
        "paper_account_ledger": str(EVIDENCE_PATHS["paper_account_ledger"]),
        "rotation_plan": str(EVIDENCE_PATHS["rotation_plan"]),
        "day_trade_event_log": str(EVIDENCE_PATHS["day_trade_event_log"]),
        "rotation_planner_proof": str(ARTIFACT_ROOT / "account_ledger" / "rotation_planner_proof.jsonl"),
        "zero_dte_account_lifecycle_proof": str(ARTIFACT_ROOT / "account_ledger" / "zero_dte_account_lifecycle_proof.jsonl"),
        "paperbroker_account_ledger_proof": str(ARTIFACT_ROOT / "account_ledger" / "paperbroker_account_ledger_proof.jsonl"),
        "zero_dte_risk_thresholds": str(ARTIFACT_ROOT / "zero_dte_risk" / "zero_dte_risk_thresholds.json"),
        "zero_dte_risk_decisions": str(ARTIFACT_ROOT / "zero_dte_risk" / "zero_dte_risk_decisions.jsonl"),
        "zero_dte_risk_summary": str(ARTIFACT_ROOT / "zero_dte_risk" / "zero_dte_risk_summary.json"),
        "zero_dte_risk_proof": str(ARTIFACT_ROOT / "zero_dte_risk" / "zero_dte_risk_proof.jsonl"),
        "zero_dte_blocked_candidates": str(ARTIFACT_ROOT / "zero_dte_risk" / "zero_dte_blocked_candidates.jsonl"),
        "zero_dte_approved_candidates": str(ARTIFACT_ROOT / "zero_dte_risk" / "zero_dte_approved_candidates.jsonl"),
        "zero_dte_replay_inputs": str(ARTIFACT_ROOT / "zero_dte_replay" / "zero_dte_replay_inputs.jsonl"),
        "zero_dte_intraday_states": str(ARTIFACT_ROOT / "zero_dte_replay" / "zero_dte_intraday_states.jsonl"),
        "zero_dte_replay_decision_points": str(ARTIFACT_ROOT / "zero_dte_replay" / "zero_dte_replay_decision_points.jsonl"),
        "zero_dte_replay_outcomes": str(ARTIFACT_ROOT / "zero_dte_replay" / "zero_dte_replay_outcomes.jsonl"),
        "zero_dte_expiry_management": str(ARTIFACT_ROOT / "zero_dte_replay" / "zero_dte_expiry_management.jsonl"),
        "zero_dte_threshold_feedback": str(ARTIFACT_ROOT / "zero_dte_replay" / "zero_dte_threshold_feedback.jsonl"),
        "zero_dte_replay_summary": str(ARTIFACT_ROOT / "zero_dte_replay" / "zero_dte_replay_summary.json"),
        "zero_dte_replay_proof": str(ARTIFACT_ROOT / "zero_dte_replay" / "zero_dte_replay_proof.jsonl"),
        "zero_dte_threshold_feedback_aggregate": str(ARTIFACT_ROOT / "zero_dte_threshold_optimizer" / "threshold_feedback_aggregate.json"),
        "zero_dte_threshold_candidates": str(ARTIFACT_ROOT / "zero_dte_threshold_optimizer" / "threshold_candidates.jsonl"),
        "zero_dte_shadow_replay_results": str(ARTIFACT_ROOT / "zero_dte_threshold_optimizer" / "shadow_replay_results.jsonl"),
        "zero_dte_threshold_optimization_decisions": str(ARTIFACT_ROOT / "zero_dte_threshold_optimizer" / "optimization_decisions.jsonl"),
        "zero_dte_recommended_threshold_profile": str(ARTIFACT_ROOT / "zero_dte_threshold_optimizer" / "recommended_threshold_profile.json"),
        "zero_dte_rejected_threshold_profiles": str(ARTIFACT_ROOT / "zero_dte_threshold_optimizer" / "rejected_threshold_profiles.jsonl"),
        "zero_dte_threshold_optimizer_summary": str(ARTIFACT_ROOT / "zero_dte_threshold_optimizer" / "threshold_optimizer_summary.json"),
        "zero_dte_threshold_optimizer_proof": str(ARTIFACT_ROOT / "zero_dte_threshold_optimizer" / "threshold_optimizer_proof.jsonl"),
        "zero_dte_adversarial_fixture_cases": str(ARTIFACT_ROOT / "zero_dte_adversarial_corpus" / "adversarial_fixture_cases.json"),
        "zero_dte_adversarial_intraday_paths": str(ARTIFACT_ROOT / "zero_dte_adversarial_corpus" / "adversarial_intraday_paths.json"),
        "zero_dte_adversarial_replay_outcomes": str(ARTIFACT_ROOT / "zero_dte_adversarial_corpus" / "adversarial_replay_outcomes.jsonl"),
        "zero_dte_adversarial_threshold_feedback": str(ARTIFACT_ROOT / "zero_dte_adversarial_corpus" / "adversarial_threshold_feedback.jsonl"),
        "zero_dte_adversarial_optimizer_effects": str(ARTIFACT_ROOT / "zero_dte_adversarial_corpus" / "adversarial_optimizer_effects.jsonl"),
        "zero_dte_adversarial_coverage_summary": str(ARTIFACT_ROOT / "zero_dte_adversarial_corpus" / "adversarial_coverage_summary.json"),
        "zero_dte_combined_replay_summary": str(ARTIFACT_ROOT / "zero_dte_adversarial_corpus" / "combined_replay_summary.json"),
        "zero_dte_adversarial_corpus_proof": str(ARTIFACT_ROOT / "zero_dte_adversarial_corpus" / "adversarial_corpus_proof.jsonl"),
        "zero_dte_underlying_families": str(ARTIFACT_ROOT / "zero_dte_cross_underlying_v2" / "underlying_families.json"),
        "zero_dte_cross_underlying_regime_cases": str(ARTIFACT_ROOT / "zero_dte_cross_underlying_v2" / "cross_underlying_regime_cases.json"),
        "zero_dte_cross_underlying_intraday_paths": str(ARTIFACT_ROOT / "zero_dte_cross_underlying_v2" / "cross_underlying_intraday_paths.json"),
        "zero_dte_cross_underlying_replay_outcomes": str(ARTIFACT_ROOT / "zero_dte_cross_underlying_v2" / "cross_underlying_replay_outcomes.jsonl"),
        "zero_dte_cross_underlying_threshold_feedback": str(ARTIFACT_ROOT / "zero_dte_cross_underlying_v2" / "cross_underlying_threshold_feedback.jsonl"),
        "zero_dte_cross_underlying_optimizer_effects": str(ARTIFACT_ROOT / "zero_dte_cross_underlying_v2" / "cross_underlying_optimizer_effects.jsonl"),
        "zero_dte_cross_underlying_coverage_summary": str(ARTIFACT_ROOT / "zero_dte_cross_underlying_v2" / "cross_underlying_coverage_summary.json"),
        "zero_dte_combined_v1_v2_replay_summary": str(ARTIFACT_ROOT / "zero_dte_cross_underlying_v2" / "combined_v1_v2_replay_summary.json"),
        "zero_dte_cross_underlying_threshold_survival": str(ARTIFACT_ROOT / "zero_dte_cross_underlying_v2" / "cross_underlying_threshold_survival.json"),
        "zero_dte_cross_underlying_corpus_proof": str(ARTIFACT_ROOT / "zero_dte_cross_underlying_v2" / "cross_underlying_corpus_proof.jsonl"),
        "hybrid_underlying_families": str(ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_underlying_families.json"),
        "hybrid_swing_candidates": str(ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_swing_candidates.json"),
        "hybrid_opportunity_pairs": str(ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_opportunity_pairs.json"),
        "hybrid_multi_day_paths": str(ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_multi_day_paths.json"),
        "hybrid_replay_outcomes": str(ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_replay_outcomes.jsonl"),
        "hybrid_preference_scores": str(ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_preference_scores.jsonl"),
        "hybrid_allocator_tags": str(ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_allocator_tags.jsonl"),
        "hybrid_coverage_summary": str(ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_coverage_summary.json"),
        "hybrid_threshold_survival": str(ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_threshold_survival.json"),
        "hybrid_replay_summary": str(ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_replay_summary.json"),
        "hybrid_corpus_proof": str(ARTIFACT_ROOT / "hybrid_swing_0dte_v3" / "hybrid_corpus_proof.jsonl"),
        "proof_weighted_opportunities": str(ARTIFACT_ROOT / "allocation" / "proof_weighted_opportunities.jsonl"),
        "paper_allocation_policy": str(ARTIFACT_ROOT / "allocation" / "paper_allocation_policy.json"),
        "paper_risk_budget": str(ARTIFACT_ROOT / "allocation" / "paper_risk_budget.json"),
        "paper_allocation_decisions": str(ARTIFACT_ROOT / "allocation" / "paper_allocation_decisions.jsonl"),
        "paper_allocation_plan": str(EVIDENCE_PATHS["paper_allocation_plan"]),
        "allocation_rejections": str(ARTIFACT_ROOT / "allocation" / "allocation_rejections.jsonl"),
        "allocation_watchlist": str(ARTIFACT_ROOT / "allocation" / "allocation_watchlist.jsonl"),
        "allocation_exposure_summary": str(EVIDENCE_PATHS["allocation_exposure_summary"]),
        "allocation_constraint_summary": str(EVIDENCE_PATHS["allocation_constraint_summary"]),
        "allocation_proof": str(ARTIFACT_ROOT / "allocation" / "allocation_proof.jsonl"),
        "portfolio_replay_policy": str(ARTIFACT_ROOT / "portfolio_replay" / "portfolio_replay_policy.json"),
        "portfolio_replay_opportunities": str(ARTIFACT_ROOT / "portfolio_replay" / "portfolio_replay_opportunities.jsonl"),
        "portfolio_states": str(ARTIFACT_ROOT / "portfolio_replay" / "portfolio_states.jsonl"),
        "portfolio_positions": str(ARTIFACT_ROOT / "portfolio_replay" / "portfolio_positions.jsonl"),
        "portfolio_rotation_decisions": str(ARTIFACT_ROOT / "portfolio_replay" / "portfolio_rotation_decisions.jsonl"),
        "portfolio_exposure_snapshots": str(EVIDENCE_PATHS["portfolio_exposure_snapshots"]),
        "exposure_stress_results": str(EVIDENCE_PATHS["exposure_stress_results"]),
        "portfolio_allocator_feedback": str(EVIDENCE_PATHS["portfolio_allocator_feedback"]),
        "portfolio_threshold_feedback": str(EVIDENCE_PATHS["portfolio_threshold_feedback"]),
        "portfolio_replay_summary": str(EVIDENCE_PATHS["portfolio_replay_summary"]),
        "portfolio_replay_proof": str(ARTIFACT_ROOT / "portfolio_replay" / "portfolio_replay_proof.jsonl"),
        "portfolio_stress_ladder_policy": str(ARTIFACT_ROOT / "portfolio_stress_ladder" / "stress_ladder_policy.json"),
        "crisis_mode_throttle_profiles": str(ARTIFACT_ROOT / "portfolio_stress_ladder" / "crisis_mode_throttle_profiles.json"),
        "stress_ladder_replay_cases": str(ARTIFACT_ROOT / "portfolio_stress_ladder" / "stress_ladder_replay_cases.json"),
        "stress_level_evaluations": str(EVIDENCE_PATHS["stress_level_evaluations"]),
        "stress_transition_decisions": str(ARTIFACT_ROOT / "portfolio_stress_ladder" / "stress_transition_decisions.jsonl"),
        "crisis_throttle_results": str(EVIDENCE_PATHS["crisis_throttle_results"]),
        "crisis_recovery_results": str(EVIDENCE_PATHS["crisis_recovery_results"]),
        "crisis_allocator_feedback": str(EVIDENCE_PATHS["crisis_allocator_feedback"]),
        "crisis_threshold_feedback": str(EVIDENCE_PATHS["crisis_threshold_feedback"]),
        "stress_ladder_summary": str(EVIDENCE_PATHS["stress_ladder_summary"]),
        "stress_ladder_proof": str(ARTIFACT_ROOT / "portfolio_stress_ladder" / "stress_ladder_proof.jsonl"),
        "incident_taxonomy": str(ARTIFACT_ROOT / "incident_response" / "incident_taxonomy.json"),
        "incident_rehearsal_cases": str(ARTIFACT_ROOT / "incident_response" / "incident_rehearsal_cases.json"),
        "incident_signals": str(EVIDENCE_PATHS["incident_signals"]),
        "kill_switch_states": str(EVIDENCE_PATHS["kill_switch_states"]),
        "incident_response_decisions": str(EVIDENCE_PATHS["incident_response_decisions"]),
        "incident_recovery_plans": str(EVIDENCE_PATHS["incident_recovery_plans"]),
        "incident_allocator_feedback": str(EVIDENCE_PATHS["incident_allocator_feedback"]),
        "incident_threshold_feedback": str(EVIDENCE_PATHS["incident_threshold_feedback"]),
        "incident_stress_ladder_feedback": str(EVIDENCE_PATHS["incident_stress_ladder_feedback"]),
        "incident_rehearsal_summary": str(EVIDENCE_PATHS["incident_rehearsal_summary"]),
        "incident_response_proof": str(ARTIFACT_ROOT / "incident_response" / "incident_response_proof.jsonl"),
        "broker_readiness_summary": str(EVIDENCE_PATHS["broker_readiness_summary"]),
        "broker_readiness_run_result": str(EVIDENCE_PATHS["broker_readiness_run_result"]),
        "broker_readiness_manual_gates": str(EVIDENCE_PATHS["broker_readiness_manual_gates"]),
        "broker_readiness_boundary_blocks": str(EVIDENCE_PATHS["broker_readiness_boundary_blocks"]),
        "broker_readiness_preflight_checks": str(ARTIFACT_ROOT / "broker_readiness" / "broker_preflight_checks.jsonl"),
        "read_only_boundary_simulations": str(ARTIFACT_ROOT / "broker_readiness" / "read_only_boundary_simulations.jsonl"),
        "broker_capability_fixtures": str(ARTIFACT_ROOT / "broker_readiness" / "broker_capability_fixtures.json"),
        "broker_readiness_proof": str(ARTIFACT_ROOT / "broker_readiness" / "broker_readiness_proof.jsonl"),
        "read_only_detector_scope": str(EVIDENCE_PATHS["read_only_detector_scope"]),
        "manual_approval_gate": str(EVIDENCE_PATHS["manual_approval_gate"]),
        "read_only_detector_approval_packet": str(ARTIFACT_ROOT / "broker_readiness" / "manual_approval" / "read_only_detector_approval_packet.json"),
        "operator_acknowledgement_required": str(ARTIFACT_ROOT / "broker_readiness" / "manual_approval" / "operator_acknowledgement_required.md"),
        "future_detector_command_templates": str(EVIDENCE_PATHS["future_detector_command_templates"]),
        "manual_gate_validation_results": str(ARTIFACT_ROOT / "broker_readiness" / "manual_approval" / "manual_gate_validation_results.jsonl"),
        "manual_approval_boundary_blocks": str(EVIDENCE_PATHS["manual_approval_boundary_blocks"]),
        "manual_approval_packet_summary": str(EVIDENCE_PATHS["manual_approval_packet_summary"]),
        "manual_approval_packet_proof": str(ARTIFACT_ROOT / "broker_readiness" / "manual_approval" / "manual_approval_packet_proof.jsonl"),
        "read_only_detector_dry_run_inputs": str(ARTIFACT_ROOT / "broker_readiness" / "dry_run" / "read_only_detector_dry_run_inputs.jsonl"),
        "simulated_broker_capability_responses": str(EVIDENCE_PATHS["simulated_broker_capability_responses"]),
        "simulated_read_only_shapes": str(ARTIFACT_ROOT / "broker_readiness" / "dry_run" / "simulated_read_only_shapes.json"),
        "simulated_forbidden_shapes": str(ARTIFACT_ROOT / "broker_readiness" / "dry_run" / "simulated_forbidden_shapes.json"),
        "read_only_detector_dry_run_results": str(EVIDENCE_PATHS["read_only_detector_dry_run_results"]),
        "dry_run_boundary_blocks": str(EVIDENCE_PATHS["dry_run_boundary_blocks"]),
        "future_detector_contract": str(ARTIFACT_ROOT / "broker_readiness" / "dry_run" / "future_detector_contract.md"),
        "read_only_detector_dry_run_summary": str(EVIDENCE_PATHS["read_only_detector_dry_run_summary"]),
        "read_only_detector_dry_run_proof": str(ARTIFACT_ROOT / "broker_readiness" / "dry_run" / "read_only_detector_dry_run_proof.jsonl"),
        "approval_intake_requests": str(EVIDENCE_PATHS["approval_intake_requests"]),
        "approval_scope_validations": str(EVIDENCE_PATHS["approval_scope_validations"]),
        "approval_intake_results": str(EVIDENCE_PATHS["approval_intake_results"]),
        "approval_forbidden_terms": str(EVIDENCE_PATHS["approval_forbidden_terms"]),
        "approval_boundary_blocks": str(EVIDENCE_PATHS["approval_boundary_blocks"]),
        "approval_incident_escalations": str(EVIDENCE_PATHS["approval_incident_escalations"]),
        "approval_intake_summary": str(EVIDENCE_PATHS["approval_intake_summary"]),
        "approval_intake_proof": str(EVIDENCE_PATHS["approval_intake_proof"]),
        "history_dataset_manifest": str(ARTIFACT_ROOT / "history" / "history_dataset_manifest.json"),
        "history_dataset_validation": str(EVIDENCE_PATHS["history_dataset_validation"]),
        "history_symbol_coverage": str(EVIDENCE_PATHS["history_symbol_coverage"]),
        "history_quality_flags": str(EVIDENCE_PATHS["history_quality_flags"]),
        "history_loader_proof": str(ARTIFACT_ROOT / "history" / "history_loader_proof.jsonl"),
        "history_spine_summary": str(EVIDENCE_PATHS["history_spine_summary"]),
        "iv_solver_validation": str(EVIDENCE_PATHS["iv_solver_validation"]),
        "vol_surface_model": str(EVIDENCE_PATHS["vol_surface_model"]),
        "model_repricing_cases": str(ARTIFACT_ROOT / "model_repricing" / "model_repricing_cases.jsonl"),
        "model_repricing_results": str(ARTIFACT_ROOT / "model_repricing" / "model_repricing_results.jsonl"),
        "model_repricing_quality_flags": str(EVIDENCE_PATHS["model_repricing_quality_flags"]),
        "model_repricing_summary": str(EVIDENCE_PATHS["model_repricing_summary"]),
        "model_repricing_proof": str(ARTIFACT_ROOT / "model_repricing" / "model_repricing_proof.jsonl"),
        "signal_engine_input_summary": str(EVIDENCE_PATHS["signal_engine_input_summary"]),
        "momentum_signals": str(ARTIFACT_ROOT / "signals" / "momentum_signals.jsonl"),
        "breakout_signals": str(ARTIFACT_ROOT / "signals" / "breakout_signals.jsonl"),
        "fakeout_signals": str(ARTIFACT_ROOT / "signals" / "fakeout_signals.jsonl"),
        "trend_pullback_signals": str(ARTIFACT_ROOT / "signals" / "trend_pullback_signals.jsonl"),
        "volatility_regime_signals": str(ARTIFACT_ROOT / "signals" / "volatility_regime_signals.jsonl"),
        "relative_strength_signals": str(ARTIFACT_ROOT / "signals" / "relative_strength_signals.jsonl"),
        "market_regime_signals": str(ARTIFACT_ROOT / "signals" / "market_regime_signals.jsonl"),
        "directional_setup_signals": str(ARTIFACT_ROOT / "signals" / "directional_setup_signals.jsonl"),
        "signal_quality_flags": str(EVIDENCE_PATHS["signal_quality_flags"]),
        "signal_engine_summary": str(EVIDENCE_PATHS["signal_engine_summary"]),
        "signal_engine_proof": str(ARTIFACT_ROOT / "signals" / "signal_engine_proof.jsonl"),
        "backtest_signal_inputs": str(ARTIFACT_ROOT / "backtest" / "backtest_signal_inputs.jsonl"),
        "backtest_trade_intents": str(ARTIFACT_ROOT / "backtest" / "backtest_trade_intents.jsonl"),
        "backtest_entry_decisions": str(ARTIFACT_ROOT / "backtest" / "backtest_entry_decisions.jsonl"),
        "backtest_exit_decisions": str(ARTIFACT_ROOT / "backtest" / "backtest_exit_decisions.jsonl"),
        "backtest_position_states": str(ARTIFACT_ROOT / "backtest" / "backtest_position_states.jsonl"),
        "backtest_mark_records": str(ARTIFACT_ROOT / "backtest" / "backtest_mark_records.jsonl"),
        "backtest_trade_records": str(EVIDENCE_PATHS["backtest_trade_records"]),
        "backtest_quality_flags": str(EVIDENCE_PATHS["backtest_quality_flags"]),
        "backtest_run_summary": str(EVIDENCE_PATHS["backtest_run_summary"]),
        "backtest_proof": str(ARTIFACT_ROOT / "backtest" / "backtest_proof.jsonl"),
        "statistical_truth_input": str(ARTIFACT_ROOT / "stats" / "statistical_truth_input.json"),
        "backtest_sample_profile": str(ARTIFACT_ROOT / "stats" / "backtest_sample_profile.json"),
        "backtest_metric_set": str(EVIDENCE_PATHS["backtest_metric_set"]),
        "bootstrap_confidence_intervals": str(EVIDENCE_PATHS["bootstrap_confidence_intervals"]),
        "baseline_comparisons": str(EVIDENCE_PATHS["baseline_comparisons"]),
        "multiple_testing_adjustment": str(ARTIFACT_ROOT / "stats" / "multiple_testing_adjustment.json"),
        "deflated_sharpe_result": str(ARTIFACT_ROOT / "stats" / "deflated_sharpe_result.json"),
        "statistical_truth_decision": str(EVIDENCE_PATHS["statistical_truth_decision"]),
        "statistical_truth_quality_flags": str(EVIDENCE_PATHS["statistical_truth_quality_flags"]),
        "statistical_truth_summary": str(EVIDENCE_PATHS["statistical_truth_summary"]),
        "statistical_truth_proof": str(ARTIFACT_ROOT / "stats" / "statistical_truth_proof.jsonl"),
        "fitness_input": str(ARTIFACT_ROOT / "fitness" / "fitness_input.json"),
        "fitness_metric_components": str(ARTIFACT_ROOT / "fitness" / "fitness_metric_components.jsonl"),
        "fitness_penalties": str(ARTIFACT_ROOT / "fitness" / "fitness_penalties.jsonl"),
        "fitness_scorecards": str(ARTIFACT_ROOT / "fitness" / "fitness_scorecards.jsonl"),
        "fitness_rank_records": str(ARTIFACT_ROOT / "fitness" / "fitness_rank_records.jsonl"),
        "fitness_promotion_gate": str(ARTIFACT_ROOT / "fitness" / "fitness_promotion_gate.json"),
        "fitness_decision": str(EVIDENCE_PATHS["fitness_decision"]),
        "proxy_fitness_quarantine_findings": str(ARTIFACT_ROOT / "fitness" / "proxy_fitness_quarantine_findings.jsonl"),
        "fitness_quality_flags": str(EVIDENCE_PATHS["fitness_quality_flags"]),
        "fitness_replacement_summary": str(EVIDENCE_PATHS["fitness_replacement_summary"]),
        "fitness_replacement_proof": str(ARTIFACT_ROOT / "fitness" / "fitness_replacement_proof.jsonl"),
        "data_ingestion_plan": str(EVIDENCE_PATHS["data_ingestion_plan"]),
        "dataset_requirements": str(EVIDENCE_PATHS["dataset_requirements"]),
        "provider_candidates": str(EVIDENCE_PATHS["provider_candidates"]),
        "local_staging_contract": str(ARTIFACT_ROOT / "data_ingestion" / "local_staging_contract.json"),
        "schema_contracts": str(EVIDENCE_PATHS["schema_contracts"]),
        "license_provenance_requirements": str(ARTIFACT_ROOT / "data_ingestion" / "license_provenance_requirements.jsonl"),
        "data_quality_gates": str(EVIDENCE_PATHS["data_quality_gates"]),
        "import_readiness_decision": str(EVIDENCE_PATHS["import_readiness_decision"]),
        "ingestion_plan_quality_flags": str(ARTIFACT_ROOT / "data_ingestion" / "ingestion_plan_quality_flags.jsonl"),
        "data_ingestion_plan_summary": str(EVIDENCE_PATHS["data_ingestion_plan_summary"]),
        "data_ingestion_plan_proof": str(ARTIFACT_ROOT / "data_ingestion" / "data_ingestion_plan_proof.jsonl"),
        "local_ohlcv_import_summary": str(EVIDENCE_PATHS["local_ohlcv_import_summary"]),
        "real_ohlcv_history_spine_upgrade": str(EVIDENCE_PATHS["real_ohlcv_history_spine_upgrade"]),
        "real_ohlcv_history_spine_activation": str(EVIDENCE_PATHS["real_ohlcv_history_spine_activation"]),
        "real_signal_validation_summary": str(EVIDENCE_PATHS["real_signal_validation_summary"]),
        "options_data_contract_summary": str(EVIDENCE_PATHS["options_data_contract_summary"]),
        "real_data_validation_stack_summary": str(EVIDENCE_PATHS["real_data_validation_stack_summary"]),
        "local_free_ohlcv_stack_summary": str(EVIDENCE_PATHS["local_free_ohlcv_stack_summary"]),
        "operator_reviewed_ohlcv_stage_summary": str(EVIDENCE_PATHS["operator_reviewed_ohlcv_stage_summary"]),
        "wealth_engine_summary": str(EVIDENCE_PATHS["wealth_engine_summary"]),
        "wealth_engine_validation_summary": str(EVIDENCE_PATHS["wealth_engine_validation_summary"]),
        "market_data_lake_summary": str(EVIDENCE_PATHS["market_data_lake_summary"]),
        "chart_vision_summary": str(EVIDENCE_PATHS["chart_vision_summary"]),
        "pnl_scoreboard_summary": str(EVIDENCE_PATHS["pnl_scoreboard_summary"]),
        "provider_install_repair_summary": str(EVIDENCE_PATHS["provider_install_repair_summary"]),
        "provider_health_diagnostics_summary": str(EVIDENCE_PATHS["provider_health_diagnostics_summary"]),
        "public_ohlcv_provider_ladder_v2_summary": str(EVIDENCE_PATHS["public_ohlcv_provider_ladder_v2_summary"]),
        "market_lake_public_promotion_summary": str(EVIDENCE_PATHS["market_lake_public_promotion_summary"]),
        "market_data_cache_summary": str(EVIDENCE_PATHS["market_data_cache_summary"]),
        "market_universe_expansion_summary": str(EVIDENCE_PATHS["market_universe_expansion_summary"]),
        "real_public_market_wealth_rerun_summary": str(EVIDENCE_PATHS["real_public_market_wealth_rerun_summary"]),
        "real_public_market_wealth_validation_summary": str(EVIDENCE_PATHS["real_public_market_wealth_validation_summary"]),
        "public_vs_fixture_scoreboard_split": str(EVIDENCE_PATHS["public_vs_fixture_scoreboard_split"]),
        "public_lake_freeze_guard_summary": str(EVIDENCE_PATHS["public_lake_freeze_guard_summary"]),
        "public_universe_expansion_v2_summary": str(EVIDENCE_PATHS["public_universe_expansion_v2_summary"]),
        "model_priced_path_simulator_v3_summary": str(EVIDENCE_PATHS["model_priced_path_simulator_v3_summary"]),
        "public_signal_mutation_factory_v3_summary": str(EVIDENCE_PATHS["public_signal_mutation_factory_v3_summary"]),
        "public_walk_forward_tournament_v3_summary": str(EVIDENCE_PATHS["public_walk_forward_tournament_v3_summary"]),
        "public_paper_champion_gate_summary": str(EVIDENCE_PATHS["public_paper_champion_gate_summary"]),
        "public_champion_scoreboard_v3": str(EVIDENCE_PATHS["public_champion_scoreboard_v3"]),
        "public_champion_evolution_summary": str(EVIDENCE_PATHS["public_champion_evolution_summary"]),
        "public_champion_risk_summary_v3": str(EVIDENCE_PATHS["public_champion_risk_summary_v3"]),
        "public_champion_live_gate_status": str(EVIDENCE_PATHS["public_champion_live_gate_status"]),
        "public_market_paper_champion_evolution_summary": str(EVIDENCE_PATHS["public_market_paper_champion_evolution_summary"]),
        "public_market_paper_champion_validation_summary": str(EVIDENCE_PATHS["public_market_paper_champion_validation_summary"]),
        "public_signal_research_v7_preflight_summary": str(EVIDENCE_PATHS["public_signal_research_v7_preflight_summary"]),
        "public_signal_research_v7_baseline_freeze_summary": str(EVIDENCE_PATHS["public_signal_research_v7_baseline_freeze_summary"]),
        "no_trade_contribution_audit_v7_summary": str(EVIDENCE_PATHS["no_trade_contribution_audit_v7_summary"]),
        "v6_watchlist_diagnosis_v7_summary": str(EVIDENCE_PATHS["v6_watchlist_diagnosis_v7_summary"]),
        "research_mutation_queue_executor_v7_summary": str(EVIDENCE_PATHS["research_mutation_queue_executor_v7_summary"]),
        "trade_active_repair_policy_v7_summary": str(EVIDENCE_PATHS["trade_active_repair_policy_v7_summary"]),
        "research_candidate_generator_v7_summary": str(EVIDENCE_PATHS["research_candidate_generator_v7_summary"]),
        "profit_holdout_split_scorer_v7_summary": str(EVIDENCE_PATHS["profit_holdout_split_scorer_v7_summary"]),
        "research_path_simulator_v7_summary": str(EVIDENCE_PATHS["research_path_simulator_v7_summary"]),
        "research_tournament_v7_summary": str(EVIDENCE_PATHS["research_tournament_v7_summary"]),
        "research_breakthrough_gate_v7_summary": str(EVIDENCE_PATHS["research_breakthrough_gate_v7_summary"]),
        "research_mutation_queue_v7_summary": str(EVIDENCE_PATHS["research_mutation_queue_v7_summary"]),
        "public_signal_research_breakthrough_v7_summary": str(EVIDENCE_PATHS["public_signal_research_breakthrough_v7_summary"]),
        "public_signal_research_breakthrough_v7_validation_summary": str(EVIDENCE_PATHS["public_signal_research_breakthrough_v7_validation_summary"]),
        "public_signal_research_scoreboard_v7": str(EVIDENCE_PATHS["public_signal_research_scoreboard_v7"]),
        "public_signal_research_live_gate_status_v7": str(EVIDENCE_PATHS["public_signal_research_live_gate_status_v7"]),
    }
