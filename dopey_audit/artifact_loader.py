"""Artifact loader + inventory builder for the offline evidence audit harness."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dopey_research_pipeline.quality_ledger import reproducibility_hash

from .evidence_models import (
    EvidenceArtifact,
    EvidenceCompletenessReport,
    EvidenceFreshnessReport,
    EvidenceInventory,
    EvidenceRecordDigest,
)


ARTIFACT_ROOT = Path(__file__).resolve().parent.parent / "artifacts" / "dopey"

# Artifact type -> (relative path, kind, required version fields).
# kind: registry | ledger
ARTIFACT_SPECS: list[tuple[str, str, str, list[str]]] = [
    ("paper_pipeline_ledger", "proof_ledger/dopey_paper_pipeline.jsonl", "ledger", ["run_id", "final_status"]),
    ("walk_forward_ledger", "walk_forward/dopey_walk_forward.jsonl", "ledger", ["run_id", "final_status"]),
    ("tournament_ledger", "tournaments/dopey_tournament.jsonl", "ledger", ["run_id", "final_status"]),
    ("mutation_registry", "mutations/mutation_registry.jsonl", "registry", ["mutation_registry_version"]),
    ("mutation_population_ledger", "mutations/dopey_mutation_population_bundle.jsonl", "ledger", ["run_id", "final_status"]),
    ("mutation_tournament_ledger", "mutations/dopey_mutation_tournament.jsonl", "ledger", ["run_id", "final_status"]),
    ("failure_mode_registry", "failure_modes/failure_mode_registry.jsonl", "registry", ["version"]),
    ("failure_feedback_registry", "failure_feedback/failure_feedback_registry.jsonl", "registry", ["feedback_optimizer_version"]),
    ("feedback_optimizer_ledger", "failure_feedback/feedback_optimizer.jsonl", "ledger", ["run_id", "final_status"]),
    ("source_registry", "source_registry/data_inflow_registry.jsonl", "registry", ["registry_version"]),
    ("iv_surface_registry", "iv_surface/iv_surface_registry.jsonl", "registry", ["iv_surface_expansion_version"]),
    ("iv_surface_ledger", "iv_surface/iv_surface_skew_bundle.jsonl", "ledger", ["run_id", "final_status"]),
    ("macro_event_registry", "macro_events/macro_event_registry.jsonl", "registry", ["macro_event_expansion_version"]),
    ("macro_event_ledger", "macro_events/macro_event_bundle.jsonl", "ledger", ["run_id", "final_status"]),
    ("ensemble_registry", "ensemble_allocator/ensemble_allocation_registry.jsonl", "registry", ["ensemble_allocator_version"]),
    ("ensemble_ledger", "ensemble_allocator/ensemble_replay.jsonl", "ledger", ["run_id", "final_status"]),
    ("meta_governor_registry", "meta_governor/meta_governor_registry.jsonl", "registry", ["meta_governor_version"]),
    ("meta_governor_decisions", "meta_governor/meta_governor_decisions.jsonl", "registry", ["meta_governor_version"]),
    ("meta_governor_ledger", "meta_governor/meta_governor_proof.jsonl", "ledger", ["run_id", "final_status"]),
    ("champion_registry", "champion_registry/champion_registry.jsonl", "registry", ["champion_strategy_id"]),
    ("walk_forward_consistency_registry", "walk_forward_consistency/consistency_registry.jsonl", "registry", ["stronger_wf_consistency_version"]),
    ("walk_forward_consistency_proof", "walk_forward_consistency/consistency_proof.jsonl", "ledger", ["run_id", "final_status"]),
    ("family_consistency_profile", "walk_forward_consistency/family_consistency_profile.jsonl", "registry", ["plan_id"]),
    ("champion_consistency", "champion_registry/champion_consistency.jsonl", "registry", ["champion_strategy_id", "consistency_verdict"]),
    ("regime_holdout_corpus_v2_registry", "regime_holdout_corpus_v2/corpus_registry.jsonl", "registry", ["corpus_v2_version", "corpus_id"]),
    ("regime_holdout_corpus_v2_replay", "regime_holdout_corpus_v2/corpus_v2_replay.jsonl", "registry", ["plan_id"]),
    ("regime_holdout_corpus_v2_coverage", "regime_holdout_corpus_v2/corpus_coverage.jsonl", "registry", ["corpus_id"]),
    ("regime_holdout_corpus_v2_proof", "regime_holdout_corpus_v2/corpus_v2_proof.jsonl", "ledger", ["run_id", "final_status"]),
    ("fundamental_registry", "fundamental_fixtures/fundamental_registry.jsonl", "registry", ["sector_peer_fundamental_expansion_version"]),
    ("fundamental_coverage", "fundamental_fixtures/fundamental_coverage.jsonl", "registry", ["coverage_id"]),
    ("fundamental_ledger", "fundamental_fixtures/fundamental_bundle.jsonl", "ledger", ["run_id", "final_status"]),
    ("reporting_dashboard_index", "reporting/dashboard_index.json", "registry", ["reporting_dashboard_index_version"]),
    ("strategy_report_cards", "reporting/strategy_report_cards.jsonl", "registry", ["strategy_id"]),
    ("family_report_cards", "reporting/family_report_cards.jsonl", "registry", ["strategy_family"]),
    ("scenario_report_cards", "reporting/scenario_report_cards.jsonl", "registry", ["scenario_id"]),
    ("performance_attribution", "reporting/performance_attribution.jsonl", "registry", ["record_id"]),
    ("reporting_bundle_proof", "reporting/reporting_bundle_proof.jsonl", "ledger", ["run_id", "final_status"]),
    ("export_registry", "exports/export_registry.jsonl", "registry", ["export_registry_version", "bundle_id", "profile"]),
    ("export_manifest", "exports/export_manifest.jsonl", "registry", ["manifest_id", "bundle_id", "profile"]),
    ("export_verification", "exports/export_verification.jsonl", "registry", ["copy_proof_id", "bundle_id", "verification_status"]),
    ("export_safety_scan", "exports/export_safety_scan.jsonl", "registry", ["scan_id", "bundle_id", "scan_status"]),
    ("export_copy_proof", "exports/export_copy_proof.jsonl", "registry", ["copy_proof_id", "bundle_id", "verification_status"]),
    ("export_compaction_summary", "exports/export_compaction_summary.jsonl", "registry", ["bundle_id", "compacted_artifact_count"]),
    ("export_review_registry", "export_reviews/export_review_registry.jsonl", "registry", ["review_registry_version", "review_id", "source_bundle_id"]),
    ("export_review_findings", "export_reviews/export_review_findings.jsonl", "registry", ["finding_id", "severity", "category"]),
    ("export_review_proof", "export_reviews/export_review_proof.jsonl", "ledger", ["run_id", "final_status"]),
    ("export_review_checklist", "export_reviews/EXPORT_REVIEW_CHECKLIST.md", "registry", ["content_sha256"]),
    ("export_review_executive_summary", "export_reviews/EXPORT_REVIEW_EXECUTIVE_SUMMARY.md", "registry", ["content_sha256"]),
    ("export_review_evidence_map", "export_reviews/EXPORT_REVIEW_EVIDENCE_MAP.json", "registry", ["map_id", "source_bundle_id"]),
    ("export_review_priority_queue", "export_reviews/EXPORT_REVIEW_PRIORITY_QUEUE.md", "registry", ["content_sha256"]),
    ("export_review_safety_summary", "export_reviews/EXPORT_REVIEW_SAFETY_SUMMARY.md", "registry", ["content_sha256"]),
    ("active_policy_integration_map", "governor/active_policy_integration_map.json", "registry", ["integration_map_version", "policy_version"]),
    ("active_policy_order_validation_proof", "governor/active_policy_order_validation_proof.jsonl", "registry", ["artifact_type", "policy_version"]),
    ("active_policy_position_lifecycle_proof", "governor/active_policy_position_lifecycle_proof.jsonl", "registry", ["artifact_type"]),
    ("active_policy_paperbroker_proof", "governor/active_policy_paperbroker_proof.jsonl", "registry", ["artifact_type"]),
    ("zero_dte_lifecycle_proof", "governor/zero_dte_lifecycle_proof.jsonl", "registry", ["artifact_type"]),
    ("no_day_trade_guard_proof", "governor/no_day_trade_guard_proof.jsonl", "registry", ["artifact_type"]),
    ("active_policy_audit", "audit/active_policy_audit.jsonl", "registry", ["active_policy_audit_version", "policy_version"]),
    ("paper_account_ledger", "account_ledger/paper_account_ledger.json", "registry", ["account_ledger_model_version", "account_id"]),
    ("day_trade_policy", "account_ledger/day_trade_policy.json", "registry", ["policy_id", "policy_version"]),
    ("pdt_safe_policy", "account_ledger/pdt_safe_policy.json", "registry", ["policy_id", "policy_version"]),
    ("rotation_plan", "account_ledger/rotation_plan.json", "registry", ["rotation_planner_version", "plan_id"]),
    ("rotation_planner_proof", "account_ledger/rotation_planner_proof.jsonl", "registry", ["rotation_planner_version", "artifact_type"]),
    ("day_trade_event_log", "account_ledger/day_trade_event_log.jsonl", "registry", ["event_id", "position_id"]),
    ("zero_dte_account_lifecycle_proof", "account_ledger/zero_dte_account_lifecycle_proof.jsonl", "registry", ["artifact_type"]),
    ("paperbroker_account_ledger_proof", "account_ledger/paperbroker_account_ledger_proof.jsonl", "registry", ["artifact_type"]),
    ("zero_dte_risk_thresholds", "zero_dte_risk/zero_dte_risk_thresholds.json", "registry", ["artifact_type", "thresholds"]),
    ("zero_dte_risk_decisions", "zero_dte_risk/zero_dte_risk_decisions.jsonl", "registry", ["candidate_id", "decision"]),
    ("zero_dte_risk_summary", "zero_dte_risk/zero_dte_risk_summary.json", "registry", ["zero_dte_risk_model_version", "threshold_version"]),
    ("zero_dte_risk_proof", "zero_dte_risk/zero_dte_risk_proof.jsonl", "registry", ["artifact_type", "candidate_id"]),
    ("zero_dte_blocked_candidates", "zero_dte_risk/zero_dte_blocked_candidates.jsonl", "registry", ["candidate_id", "decision"]),
    ("zero_dte_approved_candidates", "zero_dte_risk/zero_dte_approved_candidates.jsonl", "registry", ["candidate_id", "decision"]),
    ("zero_dte_replay_inputs", "zero_dte_replay/zero_dte_replay_inputs.jsonl", "registry", ["replay_id", "candidate_id"]),
    ("zero_dte_intraday_states", "zero_dte_replay/zero_dte_intraday_states.jsonl", "registry", ["state_id", "minute_index"]),
    ("zero_dte_replay_decision_points", "zero_dte_replay/zero_dte_replay_decision_points.jsonl", "registry", ["decision_point_id", "action"]),
    ("zero_dte_replay_outcomes", "zero_dte_replay/zero_dte_replay_outcomes.jsonl", "registry", ["replay_id", "outcome_type"]),
    ("zero_dte_expiry_management", "zero_dte_replay/zero_dte_expiry_management.jsonl", "registry", ["replay_id", "expiry_state"]),
    ("zero_dte_threshold_feedback", "zero_dte_replay/zero_dte_threshold_feedback.jsonl", "registry", ["replay_id", "recommendations"]),
    ("zero_dte_replay_summary", "zero_dte_replay/zero_dte_replay_summary.json", "registry", ["artifact_type", "zero_dte_replay_model_version"]),
    ("zero_dte_replay_proof", "zero_dte_replay/zero_dte_replay_proof.jsonl", "registry", ["artifact_type", "replay_id"]),
    ("zero_dte_threshold_feedback_aggregate", "zero_dte_threshold_optimizer/threshold_feedback_aggregate.json", "registry", ["artifact_type", "aggregate_id"]),
    ("zero_dte_threshold_candidates", "zero_dte_threshold_optimizer/threshold_candidates.jsonl", "registry", ["artifact_type", "candidate_threshold_id"]),
    ("zero_dte_shadow_replay_results", "zero_dte_threshold_optimizer/shadow_replay_results.jsonl", "registry", ["artifact_type", "shadow_replay_id"]),
    ("zero_dte_threshold_optimization_decisions", "zero_dte_threshold_optimizer/optimization_decisions.jsonl", "registry", ["artifact_type", "optimizer_run_id"]),
    ("zero_dte_recommended_threshold_profile", "zero_dte_threshold_optimizer/recommended_threshold_profile.json", "registry", ["artifact_type", "selected_candidate_threshold_id"]),
    ("zero_dte_rejected_threshold_profiles", "zero_dte_threshold_optimizer/rejected_threshold_profiles.jsonl", "registry", ["artifact_type", "candidate_threshold_id"]),
    ("zero_dte_threshold_optimizer_summary", "zero_dte_threshold_optimizer/threshold_optimizer_summary.json", "registry", ["artifact_type", "zero_dte_threshold_optimizer_version"]),
    ("zero_dte_threshold_optimizer_proof", "zero_dte_threshold_optimizer/threshold_optimizer_proof.jsonl", "registry", ["artifact_type", "optimizer_run_id"]),
    ("zero_dte_adversarial_fixture_cases", "zero_dte_adversarial_corpus/adversarial_fixture_cases.json", "registry", ["artifact_type", "case_count"]),
    ("zero_dte_adversarial_intraday_paths", "zero_dte_adversarial_corpus/adversarial_intraday_paths.json", "registry", ["artifact_type", "path_count"]),
    ("zero_dte_adversarial_replay_outcomes", "zero_dte_adversarial_corpus/adversarial_replay_outcomes.jsonl", "registry", ["artifact_type", "case_id"]),
    ("zero_dte_adversarial_threshold_feedback", "zero_dte_adversarial_corpus/adversarial_threshold_feedback.jsonl", "registry", ["artifact_type", "case_id"]),
    ("zero_dte_adversarial_optimizer_effects", "zero_dte_adversarial_corpus/adversarial_optimizer_effects.jsonl", "registry", ["artifact_type", "case_id"]),
    ("zero_dte_adversarial_coverage_summary", "zero_dte_adversarial_corpus/adversarial_coverage_summary.json", "registry", ["artifact_type", "coverage_completeness_score"]),
    ("zero_dte_combined_replay_summary", "zero_dte_adversarial_corpus/combined_replay_summary.json", "registry", ["artifact_type", "combined_fixture_count"]),
    ("zero_dte_adversarial_corpus_proof", "zero_dte_adversarial_corpus/adversarial_corpus_proof.jsonl", "registry", ["artifact_type", "case_id"]),
    ("zero_dte_underlying_families", "zero_dte_cross_underlying_v2/underlying_families.json", "registry", ["artifact_type", "family_count"]),
    ("zero_dte_cross_underlying_regime_cases", "zero_dte_cross_underlying_v2/cross_underlying_regime_cases.json", "registry", ["artifact_type", "case_count"]),
    ("zero_dte_cross_underlying_intraday_paths", "zero_dte_cross_underlying_v2/cross_underlying_intraday_paths.json", "registry", ["artifact_type", "path_count"]),
    ("zero_dte_cross_underlying_replay_outcomes", "zero_dte_cross_underlying_v2/cross_underlying_replay_outcomes.jsonl", "registry", ["artifact_type", "case_id"]),
    ("zero_dte_cross_underlying_threshold_feedback", "zero_dte_cross_underlying_v2/cross_underlying_threshold_feedback.jsonl", "registry", ["artifact_type", "case_id"]),
    ("zero_dte_cross_underlying_optimizer_effects", "zero_dte_cross_underlying_v2/cross_underlying_optimizer_effects.jsonl", "registry", ["artifact_type", "case_id"]),
    ("zero_dte_cross_underlying_coverage_summary", "zero_dte_cross_underlying_v2/cross_underlying_coverage_summary.json", "registry", ["artifact_type", "cross_underlying_completeness_score"]),
    ("zero_dte_combined_v1_v2_replay_summary", "zero_dte_cross_underlying_v2/combined_v1_v2_replay_summary.json", "registry", ["artifact_type", "combined_v1_v2_fixture_count"]),
    ("zero_dte_cross_underlying_threshold_survival", "zero_dte_cross_underlying_v2/cross_underlying_threshold_survival.json", "registry", ["artifact_type", "stricter_gamma_theta_profile_status"]),
    ("zero_dte_cross_underlying_corpus_proof", "zero_dte_cross_underlying_v2/cross_underlying_corpus_proof.jsonl", "registry", ["artifact_type", "case_id"]),
    ("hybrid_underlying_families", "hybrid_swing_0dte_v3/hybrid_underlying_families.json", "registry", ["artifact_type", "family_count"]),
    ("hybrid_swing_candidates", "hybrid_swing_0dte_v3/hybrid_swing_candidates.json", "registry", ["artifact_type", "candidate_count"]),
    ("hybrid_opportunity_pairs", "hybrid_swing_0dte_v3/hybrid_opportunity_pairs.json", "registry", ["artifact_type", "pair_count"]),
    ("hybrid_multi_day_paths", "hybrid_swing_0dte_v3/hybrid_multi_day_paths.json", "registry", ["artifact_type", "path_count"]),
    ("hybrid_replay_outcomes", "hybrid_swing_0dte_v3/hybrid_replay_outcomes.jsonl", "registry", ["pair_id", "risk_adjusted_preference"]),
    ("hybrid_preference_scores", "hybrid_swing_0dte_v3/hybrid_preference_scores.jsonl", "registry", ["pair_id", "risk_adjusted_preference"]),
    ("hybrid_allocator_tags", "hybrid_swing_0dte_v3/hybrid_allocator_tags.jsonl", "registry", ["artifact_type", "pair_id"]),
    ("hybrid_coverage_summary", "hybrid_swing_0dte_v3/hybrid_coverage_summary.json", "registry", ["artifact_type", "hybrid_completeness_score"]),
    ("hybrid_threshold_survival", "hybrid_swing_0dte_v3/hybrid_threshold_survival.json", "registry", ["artifact_type", "hybrid_stricter_gamma_theta_profile_status"]),
    ("hybrid_replay_summary", "hybrid_swing_0dte_v3/hybrid_replay_summary.json", "registry", ["artifact_type", "hybrid_pair_count"]),
    ("hybrid_corpus_proof", "hybrid_swing_0dte_v3/hybrid_corpus_proof.jsonl", "registry", ["artifact_type", "pair_id"]),
    ("proof_weighted_opportunities", "allocation/proof_weighted_opportunities.jsonl", "registry", ["opportunity_id", "strategy_type"]),
    ("paper_allocation_policy", "allocation/paper_allocation_policy.json", "registry", ["artifact_type", "policy_id"]),
    ("paper_risk_budget", "allocation/paper_risk_budget.json", "registry", ["artifact_type", "budget_id"]),
    ("paper_allocation_decisions", "allocation/paper_allocation_decisions.jsonl", "registry", ["allocation_id", "decision"]),
    ("paper_allocation_plan", "allocation/paper_allocation_plan.json", "registry", ["plan_id", "plan_hash"]),
    ("allocation_rejections", "allocation/allocation_rejections.jsonl", "registry", ["allocation_id", "decision"]),
    ("allocation_watchlist", "allocation/allocation_watchlist.jsonl", "registry", ["allocation_id", "decision"]),
    ("allocation_exposure_summary", "allocation/allocation_exposure_summary.json", "registry", ["artifact_type", "zero_dte_exposure_share"]),
    ("allocation_constraint_summary", "allocation/allocation_constraint_summary.json", "registry", ["artifact_type", "same_day_churn_allocation_allowed"]),
    ("allocation_proof", "allocation/allocation_proof.jsonl", "registry", ["artifact_type", "allocation_id"]),
    ("portfolio_replay_policy", "portfolio_replay/portfolio_replay_policy.json", "registry", ["artifact_type", "policy_id"]),
    ("portfolio_replay_opportunities", "portfolio_replay/portfolio_replay_opportunities.jsonl", "registry", ["artifact_type", "case_id"]),
    ("portfolio_states", "portfolio_replay/portfolio_states.jsonl", "registry", ["state_id", "state_hash"]),
    ("portfolio_positions", "portfolio_replay/portfolio_positions.jsonl", "registry", ["portfolio_position_id", "source_allocation_id"]),
    ("portfolio_rotation_decisions", "portfolio_replay/portfolio_rotation_decisions.jsonl", "registry", ["rotation_decision_id", "decision_type"]),
    ("portfolio_exposure_snapshots", "portfolio_replay/portfolio_exposure_snapshots.jsonl", "registry", ["snapshot_id", "exposure_hash"]),
    ("exposure_stress_results", "portfolio_replay/exposure_stress_results.jsonl", "registry", ["artifact_type", "stress_scenario_id"]),
    ("portfolio_allocator_feedback", "portfolio_replay/portfolio_allocator_feedback.jsonl", "registry", ["artifact_type", "feedback_id"]),
    ("portfolio_threshold_feedback", "portfolio_replay/portfolio_threshold_feedback.jsonl", "registry", ["artifact_type", "feedback_id"]),
    ("portfolio_replay_summary", "portfolio_replay/portfolio_replay_summary.json", "registry", ["artifact_type", "portfolio_replay_version"]),
    ("portfolio_replay_proof", "portfolio_replay/portfolio_replay_proof.jsonl", "registry", ["artifact_type", "replay_id"]),
    ("portfolio_stress_ladder_policy", "portfolio_stress_ladder/stress_ladder_policy.json", "registry", ["artifact_type", "ladder_id"]),
    ("crisis_mode_throttle_profiles", "portfolio_stress_ladder/crisis_mode_throttle_profiles.json", "registry", ["artifact_type", "profile_count"]),
    ("stress_ladder_replay_cases", "portfolio_stress_ladder/stress_ladder_replay_cases.json", "registry", ["artifact_type", "stress_case_count"]),
    ("stress_level_evaluations", "portfolio_stress_ladder/stress_level_evaluations.jsonl", "registry", ["artifact_type", "evaluation_id"]),
    ("stress_transition_decisions", "portfolio_stress_ladder/stress_transition_decisions.jsonl", "registry", ["transition_id", "transition_hash"]),
    ("crisis_throttle_results", "portfolio_stress_ladder/crisis_throttle_results.jsonl", "registry", ["artifact_type", "throttle_result_id"]),
    ("crisis_recovery_results", "portfolio_stress_ladder/crisis_recovery_results.jsonl", "registry", ["artifact_type", "recovery_result_id"]),
    ("crisis_allocator_feedback", "portfolio_stress_ladder/crisis_allocator_feedback.jsonl", "registry", ["artifact_type", "feedback_id"]),
    ("crisis_threshold_feedback", "portfolio_stress_ladder/crisis_threshold_feedback.jsonl", "registry", ["artifact_type", "feedback_id"]),
    ("stress_ladder_summary", "portfolio_stress_ladder/stress_ladder_summary.json", "registry", ["artifact_type", "stress_ladder_version"]),
    ("stress_ladder_proof", "portfolio_stress_ladder/stress_ladder_proof.jsonl", "registry", ["artifact_type", "proof_id"]),
    ("incident_taxonomy", "incident_response/incident_taxonomy.json", "registry", ["artifact_type", "taxonomy_version"]),
    ("incident_rehearsal_cases", "incident_response/incident_rehearsal_cases.json", "registry", ["artifact_type", "incident_case_count"]),
    ("incident_signals", "incident_response/incident_signals.jsonl", "registry", ["signal_id", "signal_hash"]),
    ("kill_switch_states", "incident_response/kill_switch_states.jsonl", "registry", ["kill_switch_id", "state_hash"]),
    ("incident_response_decisions", "incident_response/incident_response_decisions.jsonl", "registry", ["response_id", "decision_hash"]),
    ("incident_recovery_plans", "incident_response/incident_recovery_plans.jsonl", "registry", ["recovery_plan_id", "plan_hash"]),
    ("incident_allocator_feedback", "incident_response/incident_allocator_feedback.jsonl", "registry", ["artifact_type", "feedback_id"]),
    ("incident_threshold_feedback", "incident_response/incident_threshold_feedback.jsonl", "registry", ["artifact_type", "feedback_id"]),
    ("incident_stress_ladder_feedback", "incident_response/incident_stress_ladder_feedback.jsonl", "registry", ["artifact_type", "feedback_id"]),
    ("incident_rehearsal_summary", "incident_response/incident_rehearsal_summary.json", "registry", ["artifact_type", "incident_response_version"]),
    ("incident_response_proof", "incident_response/incident_response_proof.jsonl", "registry", ["artifact_type", "proof_id"]),
    ("lifecycle_policy", "lifecycle/lifecycle_policy.json", "registry", ["artifact_type", "policy_id"]),
    ("lifecycle_cases", "lifecycle/lifecycle_cases.json", "registry", ["artifact_type", "lifecycle_case_count"]),
    ("lifecycle_states", "lifecycle/lifecycle_states.jsonl", "registry", ["state_id", "state_hash"]),
    ("lifecycle_transitions", "lifecycle/lifecycle_transitions.jsonl", "registry", ["transition_id", "transition_hash"]),
    ("lifecycle_proof", "lifecycle/lifecycle_proof.jsonl", "registry", ["artifact_type", "proof_id"]),
    ("lifecycle_paperbroker_results", "lifecycle/lifecycle_paperbroker_results.jsonl", "registry", ["artifact_type", "result_id"]),
    ("lifecycle_account_ledger_results", "lifecycle/lifecycle_account_ledger_results.jsonl", "registry", ["artifact_type", "result_id"]),
    ("lifecycle_feedback_allocator", "lifecycle/lifecycle_feedback_allocator.jsonl", "registry", ["artifact_type", "feedback_id"]),
    ("lifecycle_feedback_portfolio", "lifecycle/lifecycle_feedback_portfolio.jsonl", "registry", ["artifact_type", "feedback_id"]),
    ("lifecycle_feedback_stress_ladder", "lifecycle/lifecycle_feedback_stress_ladder.jsonl", "registry", ["artifact_type", "feedback_id"]),
    ("lifecycle_feedback_incident", "lifecycle/lifecycle_feedback_incident.jsonl", "registry", ["artifact_type", "feedback_id"]),
    ("lifecycle_summary", "lifecycle/lifecycle_summary.json", "registry", ["artifact_type", "lifecycle_simulator_version"]),
    ("broker_readiness_preflight_checks", "broker_readiness/broker_preflight_checks.jsonl", "registry", ["check_id", "check_hash"]),
    ("read_only_boundary_simulations", "broker_readiness/read_only_boundary_simulations.jsonl", "registry", ["simulation_id", "simulation_hash"]),
    ("broker_capability_fixtures", "broker_readiness/broker_capability_fixtures.json", "registry", ["artifact_type", "fixture_count"]),
    ("broker_readiness_run_result", "broker_readiness/broker_readiness_run_result.json", "registry", ["run_id", "readiness_status"]),
    ("broker_readiness_boundary_blocks", "broker_readiness/broker_readiness_boundary_blocks.jsonl", "registry", ["block_id", "block_hash"]),
    ("broker_readiness_proof", "broker_readiness/broker_readiness_proof.jsonl", "registry", ["proof_id", "proof_hash"]),
    ("read_only_detector_scope", "broker_readiness/manual_approval/read_only_detector_scope.json", "registry", ["scope_id", "scope_hash"]),
    ("manual_approval_gate", "broker_readiness/manual_approval/manual_approval_gate.json", "registry", ["gate_id", "gate_hash"]),
    ("read_only_detector_approval_packet", "broker_readiness/manual_approval/read_only_detector_approval_packet.json", "registry", ["packet_id", "packet_hash"]),
    ("operator_acknowledgement_required", "broker_readiness/manual_approval/operator_acknowledgement_required.md", "registry", ["content_sha256"]),
    ("future_detector_command_templates", "broker_readiness/manual_approval/future_detector_command_templates.jsonl", "registry", ["template_id", "template_hash"]),
    ("manual_gate_validation_results", "broker_readiness/manual_approval/manual_gate_validation_results.jsonl", "registry", ["validation_id", "validation_hash"]),
    ("manual_approval_boundary_blocks", "broker_readiness/manual_approval/manual_approval_boundary_blocks.jsonl", "registry", ["block_id", "block_hash"]),
    ("manual_approval_packet_summary", "broker_readiness/manual_approval/manual_approval_packet_summary.json", "registry", ["artifact_type", "summary_hash"]),
    ("manual_approval_packet_proof", "broker_readiness/manual_approval/manual_approval_packet_proof.jsonl", "ledger", ["proof_id", "proof_hash"]),
    ("read_only_detector_dry_run_inputs", "broker_readiness/dry_run/read_only_detector_dry_run_inputs.jsonl", "registry", ["dry_run_id", "input_hash"]),
    ("simulated_broker_capability_responses", "broker_readiness/dry_run/simulated_broker_capability_responses.jsonl", "registry", ["response_id", "response_hash"]),
    ("simulated_read_only_shapes", "broker_readiness/dry_run/simulated_read_only_shapes.json", "registry", ["artifact_type", "shape_hash"]),
    ("simulated_forbidden_shapes", "broker_readiness/dry_run/simulated_forbidden_shapes.json", "registry", ["artifact_type", "shape_hash"]),
    ("read_only_detector_dry_run_results", "broker_readiness/dry_run/read_only_detector_dry_run_results.jsonl", "registry", ["dry_run_id", "result_hash"]),
    ("future_detector_contract", "broker_readiness/dry_run/future_detector_contract.md", "registry", ["content_sha256"]),
    ("dry_run_boundary_blocks", "broker_readiness/dry_run/dry_run_boundary_blocks.jsonl", "registry", ["block_id", "block_hash"]),
    ("dry_run_detector_proof", "broker_readiness/dry_run/read_only_detector_dry_run_proof.jsonl", "ledger", ["proof_id", "proof_hash"]),
    ("read_only_detector_dry_run_summary", "broker_readiness/dry_run/read_only_detector_dry_run_summary.json", "registry", ["artifact_type", "summary_hash"]),
    ("approval_intake_requests", "broker_readiness/approval_intake/approval_intake_requests.jsonl", "registry", ["request_id", "request_hash"]),
    ("approval_scope_validations", "broker_readiness/approval_intake/approval_scope_validations.jsonl", "registry", ["validation_id", "validation_hash"]),
    ("approval_intake_results", "broker_readiness/approval_intake/approval_intake_results.jsonl", "registry", ["result_id", "result_hash"]),
    ("approval_forbidden_terms", "broker_readiness/approval_intake/approval_forbidden_terms.json", "registry", ["artifact_type", "term_library_hash"]),
    ("approval_boundary_blocks", "broker_readiness/approval_intake/approval_boundary_blocks.jsonl", "registry", ["block_id", "block_hash"]),
    ("approval_incident_escalations", "broker_readiness/approval_intake/approval_incident_escalations.jsonl", "registry", ["escalation_id", "escalation_hash"]),
    ("approval_intake_summary", "broker_readiness/approval_intake/approval_intake_summary.json", "registry", ["artifact_type", "summary_hash"]),
    ("approval_intake_proof", "broker_readiness/approval_intake/approval_intake_proof.jsonl", "ledger", ["proof_id", "proof_hash"]),
    ("handoff_inputs", "broker_readiness/approval_to_run_handoff/handoff_inputs.jsonl", "registry", ["handoff_input_id", "input_hash"]),
    ("future_detector_run_envelopes", "broker_readiness/approval_to_run_handoff/future_detector_run_envelopes.jsonl", "registry", ["envelope_id", "envelope_hash"]),
    ("approval_to_run_gate_decisions", "broker_readiness/approval_to_run_handoff/approval_to_run_gate_decisions.jsonl", "registry", ["gate_decision_id", "decision_hash"]),
    ("disabled_handoff_command_templates", "broker_readiness/approval_to_run_handoff/disabled_handoff_command_templates.jsonl", "registry", ["template_id", "template_hash"]),
    ("handoff_boundary_blocks", "broker_readiness/approval_to_run_handoff/handoff_boundary_blocks.jsonl", "registry", ["block_id", "block_hash"]),
    ("handoff_incident_escalations", "broker_readiness/approval_to_run_handoff/handoff_incident_escalations.jsonl", "registry", ["escalation_id", "escalation_hash"]),
    ("approval_to_run_handoff_summary", "broker_readiness/approval_to_run_handoff/approval_to_run_handoff_summary.json", "registry", ["artifact_type", "summary_hash"]),
    ("approval_to_run_handoff_proof", "broker_readiness/approval_to_run_handoff/approval_to_run_handoff_proof.jsonl", "ledger", ["proof_id", "proof_hash"]),
    ("pre_run_safety_scan_inputs", "broker_readiness/pre_run_safety/pre_run_safety_scan_inputs.jsonl", "registry", ["scan_input_id", "input_hash"]),
    ("pre_run_boundary_scan_results", "broker_readiness/pre_run_safety/pre_run_boundary_scan_results.jsonl", "registry", ["boundary_scan_id", "scan_hash"]),
    ("pre_run_safety_decisions", "broker_readiness/pre_run_safety/pre_run_safety_decisions.jsonl", "registry", ["decision_id", "decision_hash"]),
    ("pre_run_forbidden_boundary_patterns", "broker_readiness/pre_run_safety/pre_run_forbidden_boundary_patterns.json", "registry", ["artifact_type", "pattern_hash"]),
    ("pre_run_boundary_classifications", "broker_readiness/pre_run_safety/pre_run_boundary_classifications.jsonl", "registry", ["classification_id", "classification_hash"]),
    ("pre_run_incident_escalations", "broker_readiness/pre_run_safety/pre_run_incident_escalations.jsonl", "registry", ["escalation_id", "escalation_hash"]),
    ("pre_run_safety_summary", "broker_readiness/pre_run_safety/pre_run_safety_summary.json", "registry", ["artifact_type", "summary_hash"]),
    ("pre_run_safety_proof", "broker_readiness/pre_run_safety/pre_run_safety_proof.jsonl", "ledger", ["proof_id", "proof_hash"]),
    ("read_only_detector_run_requests", "broker_readiness/read_only_detector/read_only_detector_run_requests.jsonl", "registry", ["request_id", "request_hash"]),
    ("read_only_capability_records", "broker_readiness/read_only_detector/read_only_capability_records.jsonl", "registry", ["capability_id", "record_hash"]),
    ("read_only_blocked_write_execute_records", "broker_readiness/read_only_detector/read_only_blocked_write_execute_records.jsonl", "registry", ["capability_id", "record_hash"]),
    ("read_only_provider_boundary_results", "broker_readiness/read_only_detector/read_only_provider_boundary_results.jsonl", "registry", ["boundary_result_id", "boundary_hash"]),
    ("read_only_detector_run_results", "broker_readiness/read_only_detector/read_only_detector_run_results.jsonl", "registry", ["run_id", "result_hash"]),
    ("read_only_detector_post_run_evidence", "broker_readiness/read_only_detector/read_only_detector_post_run_evidence.json", "registry", ["artifact_type", "evidence_hash"]),
    ("read_only_detector_incident_escalations", "broker_readiness/read_only_detector/read_only_detector_incident_escalations.jsonl", "registry", ["escalation_id", "escalation_hash"]),
    ("read_only_detector_summary", "broker_readiness/read_only_detector/read_only_detector_summary.json", "registry", ["artifact_type", "summary_hash"]),
    ("read_only_detector_proof", "broker_readiness/read_only_detector/read_only_detector_proof.jsonl", "ledger", ["proof_id", "proof_hash"]),
    ("evidence_contract", "broker_readiness/evidence_contract/evidence_contract.json", "registry", ["contract_id", "contract_hash"]),
    ("evidence_items", "broker_readiness/evidence_contract/evidence_items.jsonl", "registry", ["item_id", "item_hash"]),
    ("boundary_assertions", "broker_readiness/evidence_contract/boundary_assertions.jsonl", "registry", ["assertion_id", "assertion_hash"]),
    ("evidence_validation_results", "broker_readiness/evidence_contract/evidence_validation_results.jsonl", "registry", ["validation_id", "validation_hash"]),
    ("evidence_promotion_decisions", "broker_readiness/evidence_contract/evidence_promotion_decisions.jsonl", "registry", ["decision_id", "decision_hash"]),
    ("evidence_contract_summary", "broker_readiness/evidence_contract/evidence_contract_summary.json", "registry", ["artifact_type", "summary_hash"]),
    ("evidence_contract_proof", "broker_readiness/evidence_contract/evidence_contract_proof.jsonl", "ledger", ["proof_id", "proof_hash"]),
    ("history_dataset_manifest", "history/history_dataset_manifest.json", "registry", ["artifact_type", "manifest_reproducibility_hash"]),
    ("history_dataset_validation", "history/history_dataset_validation.json", "registry", ["artifact_type", "dataset_status"]),
    ("history_symbol_coverage", "history/history_symbol_coverage.jsonl", "registry", ["artifact_type", "symbol"]),
    ("history_quality_flags", "history/history_quality_flags.jsonl", "registry", ["artifact_type", "reason_code"]),
    ("history_loader_proof", "history/history_loader_proof.jsonl", "ledger", ["artifact_type", "proof_id"]),
    ("history_spine_summary", "history/history_spine_summary.json", "registry", ["artifact_type", "dataset_status"]),
    ("iv_solver_validation", "model_repricing/iv_solver_validation.json", "registry", ["artifact_type", "validation_status"]),
    ("vol_surface_model", "model_repricing/vol_surface_model.json", "registry", ["artifact_type", "vol_surface_model_version"]),
    ("model_repricing_cases", "model_repricing/model_repricing_cases.jsonl", "registry", ["artifact_type", "case_id"]),
    ("model_repricing_results", "model_repricing/model_repricing_results.jsonl", "registry", ["artifact_type", "path_id"]),
    ("model_repricing_quality_flags", "model_repricing/model_repricing_quality_flags.jsonl", "registry", ["artifact_type", "reason_code"]),
    ("model_repricing_summary", "model_repricing/model_repricing_summary.json", "registry", ["artifact_type", "model_repricing_status"]),
    ("model_repricing_proof", "model_repricing/model_repricing_proof.jsonl", "ledger", ["artifact_type", "proof_id"]),
    ("signal_engine_input_summary", "signals/signal_engine_input_summary.json", "registry", ["artifact_type", "signal_engine_status"]),
    ("momentum_signals", "signals/momentum_signals.jsonl", "registry", ["artifact_type", "signal_family", "record_hash"]),
    ("breakout_signals", "signals/breakout_signals.jsonl", "registry", ["artifact_type", "signal_family", "record_hash"]),
    ("fakeout_signals", "signals/fakeout_signals.jsonl", "registry", ["artifact_type", "signal_family", "record_hash"]),
    ("trend_pullback_signals", "signals/trend_pullback_signals.jsonl", "registry", ["artifact_type", "signal_family", "record_hash"]),
    ("volatility_regime_signals", "signals/volatility_regime_signals.jsonl", "registry", ["artifact_type", "signal_family", "record_hash"]),
    ("relative_strength_signals", "signals/relative_strength_signals.jsonl", "registry", ["artifact_type", "signal_family", "record_hash"]),
    ("market_regime_signals", "signals/market_regime_signals.jsonl", "registry", ["artifact_type", "signal_family", "record_hash"]),
    ("directional_setup_signals", "signals/directional_setup_signals.jsonl", "registry", ["artifact_type", "signal_family", "record_hash"]),
    ("signal_quality_flags", "signals/signal_quality_flags.jsonl", "registry", ["artifact_type", "reason_code"]),
    ("signal_engine_summary", "signals/signal_engine_summary.json", "registry", ["artifact_type", "signal_engine_status"]),
    ("signal_engine_proof", "signals/signal_engine_proof.jsonl", "ledger", ["artifact_type", "proof_id"]),
    ("backtest_signal_inputs", "backtest/backtest_signal_inputs.jsonl", "registry", ["artifact_type", "signal_id", "input_hash"]),
    ("backtest_trade_intents", "backtest/backtest_trade_intents.jsonl", "registry", ["artifact_type", "intent_id", "record_hash"]),
    ("backtest_entry_decisions", "backtest/backtest_entry_decisions.jsonl", "registry", ["artifact_type", "decision_id", "record_hash"]),
    ("backtest_exit_decisions", "backtest/backtest_exit_decisions.jsonl", "registry", ["artifact_type", "decision_id", "record_hash"]),
    ("backtest_position_states", "backtest/backtest_position_states.jsonl", "registry", ["artifact_type", "state_id", "record_hash"]),
    ("backtest_mark_records", "backtest/backtest_mark_records.jsonl", "registry", ["artifact_type", "mark_id", "record_hash"]),
    ("backtest_trade_records", "backtest/backtest_trade_records.jsonl", "registry", ["artifact_type", "trade_id", "record_hash"]),
    ("backtest_quality_flags", "backtest/backtest_quality_flags.jsonl", "registry", ["artifact_type", "reason_code"]),
    ("backtest_run_summary", "backtest/backtest_run_summary.json", "registry", ["artifact_type", "backtest_status"]),
    ("backtest_proof", "backtest/backtest_proof.jsonl", "ledger", ["artifact_type", "proof_id"]),
    ("statistical_truth_input", "stats/statistical_truth_input.json", "registry", ["artifact_type", "input_hash"]),
    ("backtest_sample_profile", "stats/backtest_sample_profile.json", "registry", ["artifact_type", "profile_hash"]),
    ("backtest_metric_set", "stats/backtest_metric_set.json", "registry", ["artifact_type", "metric_hash"]),
    ("bootstrap_confidence_intervals", "stats/bootstrap_confidence_intervals.json", "registry", ["artifact_type", "ci_hash"]),
    ("baseline_comparisons", "stats/baseline_comparisons.jsonl", "registry", ["artifact_type", "baseline_name", "comparison_hash"]),
    ("multiple_testing_adjustment", "stats/multiple_testing_adjustment.json", "registry", ["artifact_type", "adjustment_hash"]),
    ("deflated_sharpe_result", "stats/deflated_sharpe_result.json", "registry", ["artifact_type", "result_hash"]),
    ("statistical_truth_decision", "stats/statistical_truth_decision.json", "registry", ["artifact_type", "truth_decision"]),
    ("statistical_truth_quality_flags", "stats/statistical_truth_quality_flags.jsonl", "registry", ["artifact_type", "reason_code"]),
    ("statistical_truth_summary", "stats/statistical_truth_summary.json", "registry", ["artifact_type", "truth_status"]),
    ("statistical_truth_proof", "stats/statistical_truth_proof.jsonl", "ledger", ["artifact_type", "proof_id"]),
    ("fitness_input", "fitness/fitness_input.json", "registry", ["artifact_type", "input_hash"]),
    ("fitness_metric_components", "fitness/fitness_metric_components.jsonl", "registry", ["artifact_type", "component_id", "component_hash"]),
    ("fitness_penalties", "fitness/fitness_penalties.jsonl", "registry", ["artifact_type", "penalty_id", "penalty_hash"]),
    ("fitness_scorecards", "fitness/fitness_scorecards.jsonl", "registry", ["artifact_type", "scorecard_id", "scorecard_hash"]),
    ("fitness_rank_records", "fitness/fitness_rank_records.jsonl", "registry", ["artifact_type", "rank_id", "rank_hash"]),
    ("fitness_promotion_gate", "fitness/fitness_promotion_gate.json", "registry", ["artifact_type", "promotion_gate_status", "gate_hash"]),
    ("fitness_decision", "fitness/fitness_decision.json", "registry", ["artifact_type", "fitness_decision", "decision_hash"]),
    ("proxy_fitness_quarantine_findings", "fitness/proxy_fitness_quarantine_findings.jsonl", "registry", ["artifact_type", "classification", "finding_hash"]),
    ("fitness_quality_flags", "fitness/fitness_quality_flags.jsonl", "registry", ["artifact_type", "reason_code"]),
    ("fitness_replacement_summary", "fitness/fitness_replacement_summary.json", "registry", ["artifact_type", "fitness_status"]),
    ("fitness_replacement_proof", "fitness/fitness_replacement_proof.jsonl", "ledger", ["artifact_type", "proof_id"]),
    ("data_ingestion_plan", "data_ingestion/data_ingestion_plan.json", "registry", ["artifact_type", "ingestion_status", "plan_hash"]),
    ("dataset_requirements", "data_ingestion/dataset_requirements.jsonl", "registry", ["artifact_type", "dataset_family", "requirement_hash"]),
    ("provider_candidates", "data_ingestion/provider_candidates.jsonl", "registry", ["artifact_type", "provider_name", "provider_hash"]),
    ("local_staging_contract", "data_ingestion/local_staging_contract.json", "registry", ["artifact_type", "contract_id", "staging_hash"]),
    ("schema_contracts", "data_ingestion/schema_contracts.jsonl", "registry", ["artifact_type", "dataset_family", "schema_hash"]),
    ("license_provenance_requirements", "data_ingestion/license_provenance_requirements.jsonl", "registry", ["artifact_type", "dataset_family", "license_hash"]),
    ("data_quality_gates", "data_ingestion/data_quality_gates.jsonl", "registry", ["artifact_type", "gate_id", "gate_hash"]),
    ("import_readiness_decision", "data_ingestion/import_readiness_decision.json", "registry", ["artifact_type", "import_readiness_decision", "decision_hash"]),
    ("ingestion_plan_quality_flags", "data_ingestion/ingestion_plan_quality_flags.jsonl", "registry", ["artifact_type", "reason_code", "flag_hash"]),
    ("data_ingestion_plan_summary", "data_ingestion/data_ingestion_plan_summary.json", "registry", ["artifact_type", "ingestion_status", "summary_hash"]),
    ("data_ingestion_plan_proof", "data_ingestion/data_ingestion_plan_proof.jsonl", "ledger", ["artifact_type", "proof_id", "proof_hash"]),
    ("local_ohlcv_import_input", "local_ohlcv_import/local_ohlcv_import_input.json", "registry", ["artifact_type", "input_hash"]),
    ("local_ohlcv_file_inventory", "local_ohlcv_import/local_ohlcv_file_inventory.jsonl", "registry", ["artifact_type", "file_id", "file_hash"]),
    ("local_ohlcv_schema_results", "local_ohlcv_import/local_ohlcv_schema_results.jsonl", "registry", ["artifact_type", "result_id", "schema_hash"]),
    ("local_ohlcv_quality_results", "local_ohlcv_import/local_ohlcv_quality_results.jsonl", "registry", ["artifact_type", "result_id", "quality_hash"]),
    ("local_ohlcv_license_provenance_results", "local_ohlcv_import/local_ohlcv_license_provenance_results.jsonl", "registry", ["artifact_type", "result_id", "license_hash"]),
    ("local_ohlcv_import_decision", "local_ohlcv_import/local_ohlcv_import_decision.json", "registry", ["artifact_type", "local_ohlcv_status", "decision_hash"]),
    ("local_ohlcv_import_summary", "local_ohlcv_import/local_ohlcv_import_summary.json", "registry", ["artifact_type", "local_ohlcv_status", "summary_hash"]),
    ("local_ohlcv_import_proof", "local_ohlcv_import/local_ohlcv_import_proof.jsonl", "ledger", ["artifact_type", "proof_id", "proof_hash"]),
    ("real_ohlcv_history_spine_upgrade", "history/real_ohlcv_history_spine_upgrade.json", "registry", ["artifact_type", "history_spine_upgrade_status", "upgrade_hash"]),
    ("real_ohlcv_history_spine_activation", "history/real_ohlcv_history_spine_activation.json", "registry", ["artifact_type", "history_spine_activation_status", "activation_hash"]),
    ("real_ohlcv_history_symbol_coverage", "history/real_ohlcv_history_symbol_coverage.jsonl", "registry", ["artifact_type", "coverage_id"]),
    ("real_ohlcv_history_date_coverage", "history/real_ohlcv_history_date_coverage.jsonl", "registry", ["artifact_type", "coverage_id"]),
    ("real_ohlcv_history_quality_flags", "history/real_ohlcv_history_quality_flags.jsonl", "registry", ["artifact_type", "reason_code", "flag_hash"]),
    ("real_ohlcv_history_activation_quality_flags", "history/real_ohlcv_history_activation_quality_flags.jsonl", "registry", ["artifact_type", "reason_code", "flag_hash"]),
    ("real_ohlcv_history_spine_proof", "history/real_ohlcv_history_spine_proof.jsonl", "ledger", ["artifact_type", "proof_id", "proof_hash"]),
    ("real_ohlcv_history_activation_proof", "history/real_ohlcv_history_activation_proof.jsonl", "ledger", ["artifact_type", "proof_id", "proof_hash"]),
    ("real_signal_validation_input", "real_signal_validation/real_signal_validation_input.json", "registry", ["artifact_type", "input_hash"]),
    ("real_signal_records", "real_signal_validation/real_signal_records.jsonl", "registry", ["artifact_type", "signal_id", "record_hash"]),
    ("real_directional_setup_records", "real_signal_validation/real_directional_setup_records.jsonl", "registry", ["artifact_type", "setup_id", "record_hash"]),
    ("real_signal_quality_flags", "real_signal_validation/real_signal_quality_flags.jsonl", "registry", ["artifact_type", "reason_code", "flag_hash"]),
    ("real_signal_validation_summary", "real_signal_validation/real_signal_validation_summary.json", "registry", ["artifact_type", "real_signal_validation_status", "summary_hash"]),
    ("real_signal_validation_proof", "real_signal_validation/real_signal_validation_proof.jsonl", "ledger", ["artifact_type", "proof_id", "proof_hash"]),
    ("options_chain_quote_contract", "options_data_contract/options_chain_quote_contract.json", "registry", ["artifact_type", "options_contract_status", "contract_hash"]),
    ("options_schema_contracts", "options_data_contract/options_schema_contracts.jsonl", "registry", ["artifact_type", "schema_id", "schema_hash"]),
    ("options_quality_gate_plan", "options_data_contract/options_quality_gate_plan.jsonl", "registry", ["artifact_type", "gate_id", "gate_hash"]),
    ("options_import_readiness_decision", "options_data_contract/options_import_readiness_decision.json", "registry", ["artifact_type", "options_import_readiness_decision", "decision_hash"]),
    ("options_data_contract_summary", "options_data_contract/options_data_contract_summary.json", "registry", ["artifact_type", "options_contract_status", "summary_hash"]),
    ("options_data_contract_proof", "options_data_contract/options_data_contract_proof.jsonl", "ledger", ["artifact_type", "proof_id", "proof_hash"]),
    ("real_data_validation_stack_summary", "real_data_validation_stack/real_data_validation_stack_summary.json", "registry", ["artifact_type", "local_ohlcv_status", "summary_hash"]),
    ("real_data_validation_stack_proof", "real_data_validation_stack/real_data_validation_stack_proof.jsonl", "ledger", ["artifact_type", "proof_id", "proof_hash"]),
    ("oss_candidate_registry", "open_source/oss_candidate_registry.jsonl", "registry", ["artifact_type", "candidate_id", "candidate_hash"]),
    ("oss_license_security_results", "open_source/oss_license_security_results.jsonl", "registry", ["artifact_type", "candidate_id", "gate_hash"]),
    ("oss_candidate_scorecard", "open_source/oss_candidate_scorecard.json", "registry", ["artifact_type", "oss_stack_version"]),
    ("oss_discovery_summary", "open_source/oss_discovery_summary.json", "registry", ["artifact_type", "oss_stack_version"]),
    ("oss_discovery_proof", "open_source/oss_discovery_proof.jsonl", "ledger", ["artifact_type", "proof_id"]),
    ("oss_sandbox_import_plan", "open_source/oss_sandbox_import_plan.json", "registry", ["artifact_type", "plan_id", "plan_hash"]),
    ("oss_capability_extraction_plan", "open_source/oss_capability_extraction_plan.jsonl", "registry", ["artifact_type", "capability_id", "capability_hash"]),
    ("oss_adapter_contracts", "open_source/oss_adapter_contracts.jsonl", "registry", ["artifact_type", "adapter_id", "adapter_hash"]),
    ("free_data_candidate_registry", "free_data/free_data_candidate_registry.jsonl", "registry", ["artifact_type", "source_name", "candidate_hash"]),
    ("free_data_provenance_gate_results", "free_data/free_data_provenance_gate_results.jsonl", "registry", ["artifact_type", "source_name", "result_hash"]),
    ("free_data_candidate_summary", "free_data/free_data_candidate_summary.json", "registry", ["artifact_type", "free_data_stack_version", "summary_hash"]),
    ("free_data_candidate_proof", "free_data/free_data_candidate_proof.jsonl", "ledger", ["artifact_type", "proof_id", "proof_hash"]),
    ("local_ohlcv_import_fix_advice", "local_ohlcv_import/local_ohlcv_import_fix_advice.json", "registry", ["artifact_type", "fix_advice_status", "advice_hash"]),
    ("real_ohlcv_history_activation_blockers", "history/real_ohlcv_history_activation_blockers.jsonl", "registry", ["artifact_type", "blocker_id", "blocker_hash"]),
    ("open_source_quant_stack_and_free_data_path_summary", "open_source_path/open_source_quant_stack_and_free_data_path_summary.json", "registry", ["artifact_type", "local_ohlcv_status", "summary_hash"]),
    ("open_source_quant_stack_and_free_data_path_quality_flags", "open_source_path/open_source_quant_stack_and_free_data_path_quality_flags.jsonl", "registry", ["artifact_type", "flag_id", "flag_hash"]),
    ("open_source_quant_stack_and_free_data_path_proof", "open_source_path/open_source_quant_stack_and_free_data_path_proof.jsonl", "ledger", ["artifact_type", "proof_id", "proof_hash"]),
    ("local_free_ohlcv_validation_and_activation_stack_summary", "local_free_ohlcv_stack/local_free_ohlcv_validation_and_activation_stack_summary.json", "registry", ["artifact_type", "local_ohlcv_status", "summary_hash"]),
    ("local_free_ohlcv_validation_and_activation_stack_quality_flags", "local_free_ohlcv_stack/local_free_ohlcv_validation_and_activation_stack_quality_flags.jsonl", "registry", ["artifact_type", "flag_id", "flag_hash"]),
    ("local_free_ohlcv_validation_and_activation_stack_proof", "local_free_ohlcv_stack/local_free_ohlcv_validation_and_activation_stack_proof.jsonl", "ledger", ["artifact_type", "proof_id", "proof_hash"]),
    ("manual_free_ohlcv_source_candidates", "manual_ohlcv_staging/manual_free_ohlcv_source_candidates.jsonl", "registry", ["artifact_type", "source_candidate_id", "candidate_hash"]),
    ("manual_ohlcv_staging_checklist", "manual_ohlcv_staging/manual_ohlcv_staging_checklist.json", "registry", ["artifact_type", "checklist_id", "checklist_hash"]),
    ("manual_ohlcv_hash_records", "manual_ohlcv_staging/manual_ohlcv_hash_records.jsonl", "registry", ["artifact_type", "file_id", "hash_record_hash"]),
    ("manual_ohlcv_manifest_draft", "manual_ohlcv_staging/manual_ohlcv_manifest_draft.json", "registry", ["artifact_type", "draft_id", "draft_hash"]),
    ("manual_ohlcv_preflight_results", "manual_ohlcv_staging/manual_ohlcv_preflight_results.jsonl", "registry", ["artifact_type", "result_id", "record_hash"]),
    ("manual_ohlcv_preflight_summary", "manual_ohlcv_staging/manual_ohlcv_preflight_summary.json", "registry", ["artifact_type", "preflight_status", "summary_hash"]),
    ("manual_ohlcv_import_fix_plan", "manual_ohlcv_staging/manual_ohlcv_import_fix_plan.json", "registry", ["artifact_type", "fix_plan_status", "plan_hash"]),
    ("manual_ohlcv_import_fix_items", "manual_ohlcv_staging/manual_ohlcv_import_fix_items.jsonl", "registry", ["artifact_type", "hint_id", "hint_hash"]),
    ("manual_ohlcv_staging_summary", "manual_ohlcv_staging/manual_ohlcv_staging_summary.json", "registry", ["artifact_type", "manual_staging_status", "summary_hash"]),
    ("manual_ohlcv_staging_proof", "manual_ohlcv_staging/manual_ohlcv_staging_proof.jsonl", "ledger", ["artifact_type", "proof_id", "proof_hash"]),
    ("operator_reviewed_ohlcv_stage_input", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_stage_input.json", "registry", ["artifact_type", "input_hash"]),
    ("operator_ohlcv_source_review_contract", "operator_reviewed_ohlcv_stage/operator_ohlcv_source_review_contract.json", "registry", ["artifact_type", "contract_id", "contract_hash"]),
    ("operator_ohlcv_source_review_status", "operator_reviewed_ohlcv_stage/operator_ohlcv_source_review_status.json", "registry", ["artifact_type", "status", "review_hash"]),
    ("operator_reviewed_ohlcv_staged_file_status", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_staged_file_status.json", "registry", ["artifact_type", "status", "status_hash"]),
    ("operator_reviewed_ohlcv_staged_file_inventory", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_staged_file_inventory.jsonl", "registry", ["artifact_type", "inventory_id", "inventory_hash"]),
    ("operator_reviewed_ohlcv_manifest_candidate", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_manifest_candidate.json", "registry", ["artifact_type", "manifest_candidate_status", "candidate_hash"]),
    ("operator_reviewed_ohlcv_final_manifest_status", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_final_manifest_status.json", "registry", ["artifact_type", "final_manifest_status", "status_hash"]),
    ("operator_reviewed_ohlcv_rerun_steps", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_rerun_steps.jsonl", "registry", ["artifact_type", "step_id", "step_hash"]),
    ("operator_reviewed_ohlcv_rerun_decision", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_rerun_decision.json", "registry", ["artifact_type", "operator_reviewed_stage_decision", "decision_hash"]),
    ("operator_reviewed_ohlcv_evidence_boundary", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_evidence_boundary.json", "registry", ["artifact_type", "boundary_id", "boundary_hash"]),
    ("operator_reviewed_ohlcv_action_packet", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_action_packet.json", "registry", ["artifact_type", "packet_id", "packet_hash"]),
    ("operator_reviewed_ohlcv_action_packet_markdown", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_action_packet.md", "registry", ["content_sha256"]),
    ("operator_reviewed_ohlcv_stage_rerun_summary", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_stage_rerun_summary.json", "registry", ["artifact_type", "operator_reviewed_stage_status", "summary_hash"]),
    ("operator_reviewed_ohlcv_stage_rerun_quality_flags", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_stage_rerun_quality_flags.jsonl", "registry", ["artifact_type", "flag_id", "flag_hash"]),
    ("operator_reviewed_ohlcv_stage_rerun_proof", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_stage_rerun_proof.jsonl", "ledger", ["artifact_type", "proof_id", "proof_hash"]),
    ("autonomous_admissibility_kernel_summary", "autonomy/autonomous_admissibility_kernel_summary.json", "registry", ["artifact_type", "accepted_count", "summary_hash"]),
    ("autonomous_oss_discovery_summary", "open_source_autonomy/autonomous_oss_discovery_summary.json", "registry", ["artifact_type", "open_source_candidate_count", "summary_hash"]),
    ("autonomous_open_data_source_summary", "open_data_autonomy/autonomous_open_data_source_summary.json", "registry", ["artifact_type", "open_data_candidate_count", "summary_hash"]),
    ("open_data_quarantine_fetch_summary", "open_data_autonomy/open_data_quarantine_fetch_summary.json", "registry", ["artifact_type", "fetch_status", "summary_hash"]),
    ("open_ohlcv_normalization_summary", "open_data_autonomy/open_ohlcv_normalization_summary.json", "registry", ["artifact_type", "normalization_status", "summary_hash"]),
    ("autonomous_open_data_manifest_summary", "open_data_autonomy/autonomous_open_data_manifest_summary.json", "registry", ["artifact_type", "manifest_status", "summary_hash"]),
    ("autonomous_open_data_validator_bridge_summary", "open_data_autonomy/autonomous_open_data_validator_bridge_summary.json", "registry", ["artifact_type", "autonomous_open_data_status", "summary_hash"]),
    ("open_options_data_autonomy_summary", "options_autonomy/open_options_data_autonomy_summary.json", "registry", ["artifact_type", "options_data_status", "summary_hash"]),
    ("autonomous_research_engine_summary", "research_autonomy/autonomous_research_engine_summary.json", "registry", ["artifact_type", "research_status", "summary_hash"]),
    ("autonomous_backtest_stat_fitness_summary", "research_autonomy/autonomous_backtest_stat_fitness_summary.json", "registry", ["artifact_type", "pipeline_status", "summary_hash"]),
    ("autonomous_research_promotion_decision", "research_autonomy/autonomous_research_promotion_decision.json", "registry", ["artifact_type", "promotion_status", "decision_hash"]),
    ("autonomous_paper_trading_loop_summary", "paper_autonomy/autonomous_paper_trading_loop_summary.json", "registry", ["artifact_type", "paper_loop_status", "summary_hash"]),
    ("s_tier_options_benchmark_summary", "research_autonomy/s_tier_options_benchmark_summary.json", "registry", ["artifact_type", "s_tier_benchmark_status", "summary_hash"]),
    ("full_open_source_autonomous_orchestrator_summary", "full_autonomy/full_open_source_autonomous_orchestrator_summary.json", "registry", ["artifact_type", "autonomy_status", "summary_hash"]),
    ("full_autonomy_validation_summary", "full_autonomy/full_autonomy_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("exhaustive_open_data_discovery_matrix_summary", "open_data_breakthrough/exhaustive_open_data_discovery_matrix_summary.json", "registry", ["artifact_type", "total_candidates_discovered", "summary_hash"]),
    ("machine_license_terms_summary", "open_data_breakthrough/machine_license_terms_summary.json", "registry", ["artifact_type", "candidate_count", "summary_hash"]),
    ("quarantine_download_summary", "open_data_breakthrough/quarantine_download_summary.json", "registry", ["artifact_type", "download_status", "summary_hash"]),
    ("breakthrough_open_ohlcv_normalization_summary", "open_data_breakthrough/open_ohlcv_normalization_summary.json", "registry", ["artifact_type", "summary_hash"]),
    ("open_options_normalization_summary", "options_autonomy/open_options_normalization_summary.json", "registry", ["artifact_type", "open_options_normalization_status", "summary_hash"]),
    ("open_data_evidence_manifest_summary", "open_data_breakthrough/open_data_evidence_manifest_summary.json", "registry", ["artifact_type", "manifest_status", "summary_hash"]),
    ("open_data_validator_bridge_summary", "open_data_breakthrough/open_data_validator_bridge_summary.json", "registry", ["artifact_type", "history_activation_status", "summary_hash"]),
    ("quote_priced_options_unlock_gate", "backtest/quote_priced_options_unlock_gate.json", "registry", ["artifact_type", "quote_priced_options_status", "summary_hash"]),
    ("model_priced_options_research_summary", "research_autonomy/model_priced_options_research_summary.json", "registry", ["artifact_type", "model_priced_research_status", "summary_hash"]),
    ("exhaustive_discovery_proof_report", "open_data_breakthrough/exhaustive_discovery_proof_report.json", "registry", ["artifact_type", "total_candidates_discovered", "report_hash"]),
    ("open_data_breakthrough_full_completion_summary", "open_data_breakthrough/open_data_breakthrough_full_completion_summary.json", "registry", ["artifact_type", "breakthrough_status", "summary_hash"]),
    ("open_data_breakthrough_validation_summary", "open_data_breakthrough/open_data_breakthrough_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("openbb_runtime_status", "openbb_autonomy/openbb_runtime_status.json", "registry", ["artifact_type", "openbb_runtime_status", "summary_hash"]),
    ("openbb_provider_registry_summary", "openbb_autonomy/openbb_provider_registry_summary.json", "registry", ["artifact_type", "provider_count", "summary_hash"]),
    ("openbb_no_key_source_probe_summary", "openbb_autonomy/openbb_no_key_source_probe_summary.json", "registry", ["artifact_type", "probe_status", "summary_hash"]),
    ("openbb_ohlcv_normalization_summary", "openbb_autonomy/openbb_ohlcv_normalization_summary.json", "registry", ["artifact_type", "openbb_ohlcv_status", "summary_hash"]),
    ("openbb_evidence_manifest_summary", "openbb_autonomy/openbb_evidence_manifest_summary.json", "registry", ["artifact_type", "openbb_manifest_status", "summary_hash"]),
    ("openbb_validator_bridge_summary", "openbb_autonomy/openbb_validator_bridge_summary.json", "registry", ["artifact_type", "openbb_history_activation_status", "summary_hash"]),
    ("model_priced_v2_research_summary", "research_autonomy/model_priced_v2_research_summary.json", "registry", ["artifact_type", "model_priced_v2_status", "summary_hash"]),
    ("s_tier_v2_summary", "research_autonomy/s_tier_v2_summary.json", "registry", ["artifact_type", "s_tier_v2_status", "summary_hash"]),
    ("paper_rotation_engine_summary", "paper_autonomy/paper_rotation_engine_summary.json", "registry", ["artifact_type", "paper_rotation_status", "summary_hash"]),
    ("remaining_gap_eliminator_summary", "full_autonomy/remaining_gap_eliminator_summary.json", "registry", ["artifact_type", "remaining_gap_count", "summary_hash"]),
    ("finish_everything_orchestrator_summary", "finish_everything/finish_everything_orchestrator_summary.json", "registry", ["artifact_type", "finish_everything_status", "summary_hash"]),
    ("finish_everything_validation_summary", "finish_everything/finish_everything_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("runtime_bootstrap_summary", "runtime_bootstrap/local_dependency_bootstrap_summary.json", "registry", ["artifact_type", "bootstrap_status", "summary_hash"]),
    ("market_data_lake_summary", "market_intake/market_data_lake_summary.json", "registry", ["artifact_type", "market_data_status", "summary_hash"]),
    ("chart_vision_summary", "chart_vision/chart_vision_summary.json", "registry", ["artifact_type", "chart_vision_status", "summary_hash"]),
    ("aggressive_signal_engine_summary", "signals/aggressive_signal_engine_summary.json", "registry", ["artifact_type", "signal_generation_status", "summary_hash"]),
    ("model_priced_trade_constructor_summary", "options_engine/model_priced_trade_constructor_summary.json", "registry", ["artifact_type", "model_priced_options_status", "summary_hash"]),
    ("paper_money_tournament_summary", "tournament/paper_money_tournament_summary.json", "registry", ["artifact_type", "paper_tournament_status", "summary_hash"]),
    ("pnl_scoreboard_summary", "scoreboard/pnl_scoreboard_summary.json", "registry", ["artifact_type", "pnl_scoreboard_status", "summary_hash"]),
    ("risk_throttle_summary", "risk/risk_throttle_summary.json", "registry", ["artifact_type", "risk_throttle_status", "summary_hash"]),
    ("evolution_loop_summary", "evolution/evolution_loop_summary.json", "registry", ["artifact_type", "evolution_status", "summary_hash"]),
    ("live_gate_status", "live_gate/live_gate_status.json", "registry", ["artifact_type", "live_gate_status", "summary_hash"]),
    ("wealth_engine_full_completion_summary", "wealth_engine/wealth_engine_full_completion_summary.json", "registry", ["artifact_type", "wealth_engine_status", "summary_hash"]),
    ("wealth_engine_validation_summary", "wealth_engine/wealth_engine_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("provider_install_repair_summary", "provider_install/provider_install_repair_summary.json", "registry", ["artifact_type", "active_python_status", "summary_hash"]),
    ("provider_health_diagnostics_summary", "market_intake/provider_health_diagnostics_summary.json", "registry", ["artifact_type", "yahoo_direct_diagnosis", "summary_hash"]),
    ("public_ohlcv_provider_ladder_v2_summary", "market_intake/public_ohlcv_provider_ladder_v2_summary.json", "registry", ["artifact_type", "provider_ladder_status", "summary_hash"]),
    ("public_ohlcv_fetch_attempts_v2", "market_intake/public_ohlcv_fetch_attempts_v2.jsonl", "registry", ["artifact_type", "provider", "record_hash"]),
    ("public_ohlcv_fetch_successes_v2", "market_intake/public_ohlcv_fetch_successes_v2.jsonl", "registry", ["artifact_type", "provider", "record_hash"]),
    ("public_ohlcv_fetch_failures_v2", "market_intake/public_ohlcv_fetch_failures_v2.jsonl", "registry", ["artifact_type", "provider", "record_hash"]),
    ("market_lake_public_promotion_summary", "market_intake/market_lake_public_promotion_summary.json", "registry", ["artifact_type", "active_lake_status", "summary_hash"]),
    ("market_data_cache_summary", "market_intake/market_data_cache_summary.json", "registry", ["artifact_type", "market_data_cache_status", "summary_hash"]),
    ("market_universe_expansion_summary", "market_intake/market_universe_expansion_summary.json", "registry", ["artifact_type", "market_universe_expansion_status", "summary_hash"]),
    ("real_public_market_wealth_rerun_summary", "real_public_wealth/real_public_market_wealth_rerun_summary.json", "registry", ["artifact_type", "real_public_rerun_status", "summary_hash"]),
    ("real_public_market_wealth_validation_summary", "real_public_wealth/real_public_market_wealth_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("public_vs_fixture_scoreboard_split", "scoreboard/public_vs_fixture_scoreboard_split.json", "registry", ["artifact_type", "scoreboard_split_status", "summary_hash"]),
    ("public_lake_freeze_guard_summary", "public_champion_evolution/public_lake_freeze_guard_summary.json", "registry", ["artifact_type", "public_lake_guard_status", "summary_hash"]),
    ("public_universe_expansion_v2_summary", "public_champion_evolution/public_universe_expansion_v2_summary.json", "registry", ["artifact_type", "public_universe_expansion_status", "summary_hash"]),
    ("model_priced_path_simulator_v3_summary", "options_engine/model_priced_path_simulator_v3_summary.json", "registry", ["artifact_type", "model_priced_path_simulator_status", "summary_hash"]),
    ("public_signal_mutation_factory_v3_summary", "signals/public_signal_mutation_factory_v3_summary.json", "registry", ["artifact_type", "public_signal_mutation_status", "summary_hash"]),
    ("public_walk_forward_tournament_v3_summary", "tournament/public_walk_forward_tournament_v3_summary.json", "registry", ["artifact_type", "public_walk_forward_status", "summary_hash"]),
    ("public_paper_champion_gate_summary", "champions/public_paper_champion_gate_summary.json", "registry", ["artifact_type", "public_paper_champion_gate_status", "summary_hash"]),
    ("public_champion_scoreboard_v3", "scoreboard/public_champion_scoreboard_v3.json", "registry", ["artifact_type", "scoreboard_status", "summary_hash"]),
    ("public_champion_evolution_summary", "evolution/public_champion_evolution_summary.json", "registry", ["artifact_type", "public_champion_evolution_status", "summary_hash"]),
    ("public_champion_risk_summary_v3", "risk/public_champion_risk_summary_v3.json", "registry", ["artifact_type", "public_champion_risk_status", "summary_hash"]),
    ("public_champion_live_gate_status", "live_gate/public_champion_live_gate_status.json", "registry", ["artifact_type", "live_gate_status", "summary_hash"]),
    ("public_market_paper_champion_evolution_summary", "public_champion_evolution/public_market_paper_champion_evolution_summary.json", "registry", ["artifact_type", "public_champion_evolution_status", "summary_hash"]),
    ("public_market_paper_champion_validation_summary", "public_champion_evolution/public_market_paper_champion_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("public_lake_final_state_lock_v2_summary", "public_signal_deepening/public_lake_final_state_lock_v2_summary.json", "registry", ["artifact_type", "public_lake_final_state_status", "summary_hash"]),
    ("strategy_cohort_summary", "public_signal_deepening/strategy_cohort_summary.json", "registry", ["artifact_type", "strategy_cohort_status", "summary_hash"]),
    ("public_signal_mutation_factory_v4_summary", "signals/public_signal_mutation_factory_v4_summary.json", "registry", ["artifact_type", "public_signal_mutation_status", "summary_hash"]),
    ("model_priced_path_simulator_v4_summary", "options_engine/model_priced_path_simulator_v4_summary.json", "registry", ["artifact_type", "model_priced_path_simulator_status", "summary_hash"]),
    ("public_cohort_walk_forward_tournament_v4_summary", "tournament/public_cohort_walk_forward_tournament_v4_summary.json", "registry", ["artifact_type", "public_cohort_walk_forward_status", "summary_hash"]),
    ("public_paper_champion_gate_v2_summary", "champions/public_paper_champion_gate_v2_summary.json", "registry", ["artifact_type", "public_paper_champion_gate_status", "summary_hash"]),
    ("public_signal_deepening_loop_v2_summary", "evolution/public_signal_deepening_loop_v2_summary.json", "registry", ["artifact_type", "public_signal_deepening_status", "summary_hash"]),
    ("public_signal_deepening_scoreboard_v4", "scoreboard/public_signal_deepening_scoreboard_v4.json", "registry", ["artifact_type", "scoreboard_status", "summary_hash"]),
    ("public_signal_deepening_live_gate_status_v2", "live_gate/public_signal_deepening_live_gate_status_v2.json", "registry", ["artifact_type", "live_gate_status", "summary_hash"]),
    ("public_market_signal_mutation_deepening_v2_summary", "public_signal_deepening/public_market_signal_mutation_deepening_v2_summary.json", "registry", ["artifact_type", "public_signal_deepening_status", "summary_hash"]),
    ("public_market_signal_mutation_deepening_v2_validation_summary", "public_signal_deepening/public_market_signal_mutation_deepening_v2_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("champion_hardening_preflight_summary", "champion_hardening/champion_hardening_preflight_summary.json", "registry", ["artifact_type", "champion_hardening_preflight_status", "summary_hash"]),
    ("public_signal_artifact_cleaner_summary", "champion_hardening/public_signal_artifact_cleaner_summary.json", "registry", ["artifact_type", "signal_artifact_cleaner_status", "summary_hash"]),
    ("public_champion_inventory_v1_summary", "champion_hardening/public_champion_inventory_v1_summary.json", "registry", ["artifact_type", "public_champion_inventory_status", "summary_hash"]),
    ("public_champion_deep_stress_matrix_v1_summary", "champion_hardening/public_champion_deep_stress_matrix_v1_summary.json", "registry", ["artifact_type", "deep_stress_status", "summary_hash"]),
    ("public_champion_holdout_expansion_v1_summary", "champion_hardening/public_champion_holdout_expansion_v1_summary.json", "registry", ["artifact_type", "holdout_expansion_status", "summary_hash"]),
    ("public_champion_decay_monitor_v1_summary", "champion_hardening/public_champion_decay_monitor_v1_summary.json", "registry", ["artifact_type", "decay_monitor_status", "summary_hash"]),
    ("public_champion_hardening_gate_v1_summary", "champion_hardening/public_champion_hardening_gate_v1_summary.json", "registry", ["artifact_type", "champion_hardening_gate_status", "summary_hash"]),
    ("public_champion_hardening_scoreboard_v1", "scoreboard/public_champion_hardening_scoreboard_v1.json", "registry", ["artifact_type", "scoreboard_status", "summary_hash"]),
    ("public_champion_hardening_live_gate_status_v3", "live_gate/public_champion_hardening_live_gate_status_v3.json", "registry", ["artifact_type", "live_gate_status", "summary_hash"]),
    ("public_paper_champion_hardening_and_deep_stress_v1_summary", "champion_hardening/public_paper_champion_hardening_and_deep_stress_v1_summary.json", "registry", ["artifact_type", "champion_hardening_status", "summary_hash"]),
    ("public_paper_champion_hardening_and_deep_stress_v1_validation_summary", "champion_hardening/public_paper_champion_hardening_and_deep_stress_v1_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("public_champion_repair_preflight_v1_summary", "champion_repair/public_champion_repair_preflight_v1_summary.json", "registry", ["artifact_type", "public_champion_repair_preflight_status", "summary_hash"]),
    ("public_champion_artifact_guard_v1_summary", "champion_repair/public_champion_artifact_guard_v1_summary.json", "registry", ["artifact_type", "artifact_guard_status", "summary_hash"]),
    ("conditional_champion_repair_planner_v1_summary", "champion_repair/conditional_champion_repair_planner_v1_summary.json", "registry", ["artifact_type", "conditional_champion_repair_planner_status", "summary_hash"]),
    ("conditional_champion_signal_retune_v1_summary", "signals/conditional_champion_signal_retune_v1_summary.json", "registry", ["artifact_type", "conditional_champion_signal_retune_status", "summary_hash"]),
    ("conditional_champion_retune_path_simulator_v1_summary", "options_engine/conditional_champion_retune_path_simulator_v1_summary.json", "registry", ["artifact_type", "conditional_champion_retune_path_status", "summary_hash"]),
    ("conditional_champion_retune_tournament_v1_summary", "champion_repair/conditional_champion_retune_tournament_v1_summary.json", "registry", ["artifact_type", "conditional_champion_retune_tournament_status", "summary_hash"]),
    ("conditional_champion_retune_hardening_gate_v1_summary", "champion_repair/conditional_champion_retune_hardening_gate_v1_summary.json", "registry", ["artifact_type", "conditional_champion_retune_hardening_status", "summary_hash"]),
    ("demoted_champion_salvage_analyzer_v1_summary", "champion_repair/demoted_champion_salvage_analyzer_v1_summary.json", "registry", ["artifact_type", "demoted_champion_salvage_status", "summary_hash"]),
    ("public_champion_repair_scoreboard_v1", "scoreboard/public_champion_repair_scoreboard_v1.json", "registry", ["artifact_type", "scoreboard_status", "summary_hash"]),
    ("public_champion_repair_live_gate_status_v1", "live_gate/public_champion_repair_live_gate_status_v1.json", "registry", ["artifact_type", "live_gate_status", "summary_hash"]),
    ("public_champion_repair_and_retune_v1_summary", "champion_repair/public_champion_repair_and_retune_v1_summary.json", "registry", ["artifact_type", "public_champion_repair_status", "summary_hash"]),
    ("public_champion_repair_and_retune_v1_validation_summary", "champion_repair/public_champion_repair_and_retune_v1_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("public_signal_research_preflight_v1_summary", "signal_research/public_signal_research_preflight_v1_summary.json", "registry", ["artifact_type", "public_signal_research_preflight_status", "summary_hash"]),
    ("failed_champion_family_quarantine_v1_summary", "signal_research/failed_champion_family_quarantine_v1_summary.json", "registry", ["artifact_type", "failed_family_quarantine_status", "summary_hash"]),
    ("public_feature_miner_v1_summary", "signal_research/public_feature_miner_v1_summary.json", "registry", ["artifact_type", "public_feature_miner_status", "summary_hash"]),
    ("discovery_signal_family_generator_v1_summary", "signal_research/discovery_signal_family_generator_v1_summary.json", "registry", ["artifact_type", "discovery_signal_family_status", "summary_hash"]),
    ("research_candidate_generator_v1_summary", "signal_research/research_candidate_generator_v1_summary.json", "registry", ["artifact_type", "research_candidate_generator_status", "summary_hash"]),
    ("research_path_simulator_v1_summary", "signal_research/research_path_simulator_v1_summary.json", "registry", ["artifact_type", "research_path_simulator_status", "summary_hash"]),
    ("research_tournament_v1_summary", "signal_research/research_tournament_v1_summary.json", "registry", ["artifact_type", "research_tournament_status", "summary_hash"]),
    ("research_breakthrough_gate_v1_summary", "signal_research/research_breakthrough_gate_v1_summary.json", "registry", ["artifact_type", "research_breakthrough_gate_status", "summary_hash"]),
    ("research_mutation_queue_v1_summary", "signal_research/research_mutation_queue_v1_summary.json", "registry", ["artifact_type", "research_mutation_queue_status", "summary_hash"]),
    ("public_signal_research_scoreboard_v1", "scoreboard/public_signal_research_scoreboard_v1.json", "registry", ["artifact_type", "scoreboard_status", "summary_hash"]),
    ("public_signal_research_live_gate_status_v1", "live_gate/public_signal_research_live_gate_status_v1.json", "registry", ["artifact_type", "live_gate_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v1_summary", "signal_research/public_signal_research_breakthrough_v1_summary.json", "registry", ["artifact_type", "public_signal_research_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v1_validation_summary", "signal_research/public_signal_research_breakthrough_v1_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("public_signal_research_v2_preflight_summary", "signal_research_v2/public_signal_research_v2_preflight_summary.json", "registry", ["artifact_type", "public_signal_research_v2_preflight_status", "summary_hash"]),
    ("watchlist_candidate_extractor_v2_summary", "signal_research_v2/watchlist_candidate_extractor_v2_summary.json", "registry", ["artifact_type", "watchlist_extractor_status", "summary_hash"]),
    ("symbol_sector_density_scheduler_v2_summary", "signal_research_v2/symbol_sector_density_scheduler_v2_summary.json", "registry", ["artifact_type", "symbol_sector_density_status", "summary_hash"]),
    ("watchlist_mutation_planner_v2_summary", "signal_research_v2/watchlist_mutation_planner_v2_summary.json", "registry", ["artifact_type", "watchlist_mutation_status", "summary_hash"]),
    ("public_feature_miner_v2_summary", "signal_research_v2/public_feature_miner_v2_summary.json", "registry", ["artifact_type", "public_feature_miner_v2_status", "summary_hash"]),
    ("research_candidate_generator_v2_summary", "signal_research_v2/research_candidate_generator_v2_summary.json", "registry", ["artifact_type", "research_candidate_generator_v2_status", "summary_hash"]),
    ("research_path_simulator_v2_summary", "signal_research_v2/research_path_simulator_v2_summary.json", "registry", ["artifact_type", "research_path_simulator_v2_status", "summary_hash"]),
    ("research_tournament_v2_summary", "signal_research_v2/research_tournament_v2_summary.json", "registry", ["artifact_type", "research_tournament_v2_status", "summary_hash"]),
    ("research_breakthrough_gate_v2_summary", "signal_research_v2/research_breakthrough_gate_v2_summary.json", "registry", ["artifact_type", "research_breakthrough_gate_v2_status", "summary_hash"]),
    ("research_mutation_queue_v2_summary", "signal_research_v2/research_mutation_queue_v2_summary.json", "registry", ["artifact_type", "research_mutation_queue_v2_status", "summary_hash"]),
    ("public_signal_research_scoreboard_v2", "scoreboard/public_signal_research_scoreboard_v2.json", "registry", ["artifact_type", "scoreboard_status", "summary_hash"]),
    ("public_signal_research_live_gate_status_v2", "live_gate/public_signal_research_live_gate_status_v2.json", "registry", ["artifact_type", "live_gate_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v2_summary", "signal_research_v2/public_signal_research_breakthrough_v2_summary.json", "registry", ["artifact_type", "public_signal_research_v2_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v2_validation_summary", "signal_research_v2/public_signal_research_breakthrough_v2_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("public_signal_research_v3_preflight_summary", "signal_research_v3/public_signal_research_v3_preflight_summary.json", "registry", ["artifact_type", "public_signal_research_v3_preflight_status", "summary_hash"]),
    ("research_mutation_queue_executor_v3_summary", "signal_research_v3/research_mutation_queue_executor_v3_summary.json", "registry", ["artifact_type", "research_mutation_queue_executor_status", "summary_hash"]),
    ("stable_family_template_repair_v3_summary", "signal_research_v3/stable_family_template_repair_v3_summary.json", "registry", ["artifact_type", "stable_family_template_repair_status", "summary_hash"]),
    ("research_candidate_generator_v3_summary", "signal_research_v3/research_candidate_generator_v3_summary.json", "registry", ["artifact_type", "research_candidate_generator_v3_status", "summary_hash"]),
    ("profit_holdout_repair_scorer_v3_summary", "signal_research_v3/profit_holdout_repair_scorer_v3_summary.json", "registry", ["artifact_type", "profit_holdout_repair_scorer_status", "summary_hash"]),
    ("research_path_simulator_v3_summary", "signal_research_v3/research_path_simulator_v3_summary.json", "registry", ["artifact_type", "research_path_simulator_v3_status", "summary_hash"]),
    ("research_tournament_v3_summary", "signal_research_v3/research_tournament_v3_summary.json", "registry", ["artifact_type", "research_tournament_v3_status", "summary_hash"]),
    ("research_breakthrough_gate_v3_summary", "signal_research_v3/research_breakthrough_gate_v3_summary.json", "registry", ["artifact_type", "research_breakthrough_gate_v3_status", "summary_hash"]),
    ("research_mutation_queue_v3_summary", "signal_research_v3/research_mutation_queue_v3_summary.json", "registry", ["artifact_type", "research_mutation_queue_v3_status", "summary_hash"]),
    ("zero_dte_replay_outcomes_artifact_repair_v1_summary", "active_policy/zero_dte_replay_outcomes_artifact_repair_v1_summary.json", "registry", ["artifact_type", "zero_dte_replay_outcomes_repair_status", "summary_hash"]),
    ("public_signal_research_scoreboard_v3", "scoreboard/public_signal_research_scoreboard_v3.json", "registry", ["artifact_type", "scoreboard_status", "summary_hash"]),
    ("public_signal_research_live_gate_status_v3", "live_gate/public_signal_research_live_gate_status_v3.json", "registry", ["artifact_type", "live_gate_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v3_summary", "signal_research_v3/public_signal_research_breakthrough_v3_summary.json", "registry", ["artifact_type", "public_signal_research_v3_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v3_validation_summary", "signal_research_v3/public_signal_research_breakthrough_v3_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("public_signal_research_v4_preflight_summary", "signal_research_v4/public_signal_research_v4_preflight_summary.json", "registry", ["artifact_type", "public_signal_research_v4_preflight_status", "summary_hash"]),
    ("research_candidate_generator_v4_summary", "signal_research_v4/research_candidate_generator_v4_summary.json", "registry", ["artifact_type", "research_candidate_generator_v4_status", "summary_hash"]),
    ("research_path_simulator_v4_summary", "signal_research_v4/research_path_simulator_v4_summary.json", "registry", ["artifact_type", "research_path_simulator_v4_status", "summary_hash"]),
    ("research_tournament_v4_summary", "signal_research_v4/research_tournament_v4_summary.json", "registry", ["artifact_type", "research_tournament_v4_status", "summary_hash"]),
    ("research_breakthrough_gate_v4_summary", "signal_research_v4/research_breakthrough_gate_v4_summary.json", "registry", ["artifact_type", "research_breakthrough_gate_v4_status", "summary_hash"]),
    ("research_mutation_queue_v4_summary", "signal_research_v4/research_mutation_queue_v4_summary.json", "registry", ["artifact_type", "research_mutation_queue_v4_status", "summary_hash"]),
    ("zero_dte_replay_outcomes_artifact_guard_v2_summary", "active_policy/zero_dte_replay_outcomes_artifact_guard_v2_summary.json", "registry", ["artifact_type", "zero_dte_replay_outcomes_guard_status", "summary_hash"]),
    ("public_signal_research_scoreboard_v4", "scoreboard/public_signal_research_scoreboard_v4.json", "registry", ["artifact_type", "scoreboard_status", "summary_hash"]),
    ("public_signal_research_live_gate_status_v4", "live_gate/public_signal_research_live_gate_status_v4.json", "registry", ["artifact_type", "live_gate_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v4_summary", "signal_research_v4/public_signal_research_breakthrough_v4_summary.json", "registry", ["artifact_type", "public_signal_research_v4_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v4_validation_summary", "signal_research_v4/public_signal_research_breakthrough_v4_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("public_signal_research_v5_preflight_summary", "signal_research_v5/public_signal_research_v5_preflight_summary.json", "registry", ["artifact_type", "public_signal_research_v5_preflight_status", "summary_hash"]),
    ("public_signal_research_v5_baseline_freeze_summary", "signal_research_v5/public_signal_research_v5_baseline_freeze_summary.json", "registry", ["artifact_type", "baseline_freeze_status", "summary_hash"]),
    ("research_mutation_queue_executor_v5_summary", "signal_research_v5/research_mutation_queue_executor_v5_summary.json", "registry", ["artifact_type", "research_mutation_queue_executor_v5_status", "summary_hash"]),
    ("no_trade_filter_optimizer_v5_summary", "signal_research_v5/no_trade_filter_optimizer_v5_summary.json", "registry", ["artifact_type", "no_trade_filter_optimizer_v5_status", "summary_hash"]),
    ("research_candidate_generator_v5_summary", "signal_research_v5/research_candidate_generator_v5_summary.json", "registry", ["artifact_type", "research_candidate_generator_v5_status", "summary_hash"]),
    ("profit_holdout_split_scorer_v5_summary", "signal_research_v5/profit_holdout_split_scorer_v5_summary.json", "registry", ["artifact_type", "profit_holdout_split_scorer_v5_status", "summary_hash"]),
    ("research_path_simulator_v5_summary", "signal_research_v5/research_path_simulator_v5_summary.json", "registry", ["artifact_type", "research_path_simulator_v5_status", "summary_hash"]),
    ("research_tournament_v5_summary", "signal_research_v5/research_tournament_v5_summary.json", "registry", ["artifact_type", "research_tournament_v5_status", "summary_hash"]),
    ("research_breakthrough_gate_v5_summary", "signal_research_v5/research_breakthrough_gate_v5_summary.json", "registry", ["artifact_type", "research_breakthrough_gate_v5_status", "summary_hash"]),
    ("research_mutation_queue_v5_summary", "signal_research_v5/research_mutation_queue_v5_summary.json", "registry", ["artifact_type", "research_mutation_queue_v5_status", "summary_hash"]),
    ("public_signal_research_scoreboard_v5", "scoreboard/public_signal_research_scoreboard_v5.json", "registry", ["artifact_type", "scoreboard_v5_status", "summary_hash"]),
    ("public_signal_research_live_gate_status_v5", "live_gate/public_signal_research_live_gate_status_v5.json", "registry", ["artifact_type", "live_gate_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v5_summary", "signal_research_v5/public_signal_research_breakthrough_v5_summary.json", "registry", ["artifact_type", "public_signal_research_v5_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v5_validation_summary", "signal_research_v5/public_signal_research_breakthrough_v5_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    ("public_signal_research_v6_preflight_summary", "signal_research_v6/public_signal_research_v6_preflight_summary.json", "registry", ["artifact_type", "public_signal_research_v6_preflight_status", "summary_hash"]),
    ("public_signal_research_v6_baseline_freeze_summary", "signal_research_v6/public_signal_research_v6_baseline_freeze_summary.json", "registry", ["artifact_type", "baseline_freeze_status", "summary_hash"]),
    ("v5_gate_rejection_analyzer_v6_summary", "signal_research_v6/v5_gate_rejection_analyzer_v6_summary.json", "registry", ["artifact_type", "v5_gate_rejection_analyzer_status", "summary_hash"]),
    ("research_mutation_queue_executor_v6_summary", "signal_research_v6/research_mutation_queue_executor_v6_summary.json", "registry", ["artifact_type", "research_mutation_queue_executor_v6_status", "summary_hash"]),
    ("breakthrough_blocker_repair_policy_v6_summary", "signal_research_v6/breakthrough_blocker_repair_policy_v6_summary.json", "registry", ["artifact_type", "breakthrough_blocker_repair_policy_status", "summary_hash"]),
    ("research_candidate_generator_v6_summary", "signal_research_v6/research_candidate_generator_v6_summary.json", "registry", ["artifact_type", "research_candidate_generator_v6_status", "summary_hash"]),
    ("profit_holdout_split_scorer_v6_summary", "signal_research_v6/profit_holdout_split_scorer_v6_summary.json", "registry", ["artifact_type", "profit_holdout_split_scorer_v6_status", "summary_hash"]),
    ("research_path_simulator_v6_summary", "signal_research_v6/research_path_simulator_v6_summary.json", "registry", ["artifact_type", "research_path_simulator_v6_status", "summary_hash"]),
    ("research_tournament_v6_summary", "signal_research_v6/research_tournament_v6_summary.json", "registry", ["artifact_type", "research_tournament_v6_status", "summary_hash"]),
    ("research_breakthrough_gate_v6_summary", "signal_research_v6/research_breakthrough_gate_v6_summary.json", "registry", ["artifact_type", "research_breakthrough_gate_v6_status", "summary_hash"]),
    ("research_mutation_queue_v6_summary", "signal_research_v6/research_mutation_queue_v6_summary.json", "registry", ["artifact_type", "research_mutation_queue_v6_status", "summary_hash"]),
    ("public_signal_research_scoreboard_v6", "scoreboard/public_signal_research_scoreboard_v6.json", "registry", ["artifact_type", "scoreboard_v6_status", "summary_hash"]),
    ("public_signal_research_live_gate_status_v6", "live_gate/public_signal_research_live_gate_status_v6.json", "registry", ["artifact_type", "live_gate_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v6_summary", "signal_research_v6/public_signal_research_breakthrough_v6_summary.json", "registry", ["artifact_type", "public_signal_research_v6_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v6_validation_summary", "signal_research_v6/public_signal_research_breakthrough_v6_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
    # DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7
    ("public_signal_research_v7_preflight_summary", "signal_research_v7/public_signal_research_v7_preflight_summary.json", "registry", ["artifact_type", "public_signal_research_v7_preflight_status", "summary_hash"]),
    ("public_signal_research_v7_baseline_freeze_summary", "signal_research_v7/public_signal_research_v7_baseline_freeze_summary.json", "registry", ["artifact_type", "baseline_freeze_status", "summary_hash"]),
    ("no_trade_contribution_audit_v7_summary", "signal_research_v7/no_trade_contribution_audit_v7_summary.json", "registry", ["artifact_type", "no_trade_contribution_audit_status", "summary_hash"]),
    ("v6_watchlist_diagnosis_v7_summary", "signal_research_v7/v6_watchlist_diagnosis_v7_summary.json", "registry", ["artifact_type", "v6_watchlist_diagnosis_v7_status", "summary_hash"]),
    ("research_mutation_queue_executor_v7_summary", "signal_research_v7/research_mutation_queue_executor_v7_summary.json", "registry", ["artifact_type", "research_mutation_queue_executor_v7_status", "summary_hash"]),
    ("trade_active_repair_policy_v7_summary", "signal_research_v7/trade_active_repair_policy_v7_summary.json", "registry", ["artifact_type", "trade_active_repair_policy_status", "summary_hash"]),
    ("research_candidate_generator_v7_summary", "signal_research_v7/research_candidate_generator_v7_summary.json", "registry", ["artifact_type", "research_candidate_generator_v7_status", "summary_hash"]),
    ("profit_holdout_split_scorer_v7_summary", "signal_research_v7/profit_holdout_split_scorer_v7_summary.json", "registry", ["artifact_type", "profit_holdout_split_scorer_v7_status", "summary_hash"]),
    ("research_path_simulator_v7_summary", "signal_research_v7/research_path_simulator_v7_summary.json", "registry", ["artifact_type", "research_path_simulator_v7_status", "summary_hash"]),
    ("research_tournament_v7_summary", "signal_research_v7/research_tournament_v7_summary.json", "registry", ["artifact_type", "research_tournament_v7_status", "summary_hash"]),
    ("research_breakthrough_gate_v7_summary", "signal_research_v7/research_breakthrough_gate_v7_summary.json", "registry", ["artifact_type", "research_breakthrough_gate_v7_status", "summary_hash"]),
    ("research_mutation_queue_v7_summary", "signal_research_v7/research_mutation_queue_v7_summary.json", "registry", ["artifact_type", "research_mutation_queue_v7_status", "summary_hash"]),
    ("public_signal_research_scoreboard_v7", "scoreboard/public_signal_research_scoreboard_v7.json", "registry", ["artifact_type", "scoreboard_v7_status", "summary_hash"]),
    ("public_signal_research_live_gate_status_v7", "live_gate/public_signal_research_live_gate_status_v7.json", "registry", ["artifact_type", "live_gate_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v7_summary", "signal_research_v7/public_signal_research_breakthrough_v7_summary.json", "registry", ["artifact_type", "public_signal_research_v7_status", "summary_hash"]),
    ("public_signal_research_breakthrough_v7_validation_summary", "signal_research_v7/public_signal_research_breakthrough_v7_validation_summary.json", "registry", ["artifact_type", "validation_status", "summary_hash"]),
]

# Required-field aliases per artifact type. Maps artifact_type -> {required_field: [aliases]}.
_FIELD_ALIASES: dict[str, dict[str, list[str]]] = {
    "failure_mode_registry": {"version": ["version", "failure_mode_registry_version"]},
    "source_registry": {"registry_version": ["registry_version", "source_registry_version", "registry_id"]},
    "champion_consistency": {
        "consistency_verdict": ["consistency_verdict", "champion_consistency_verdict", "runner_up_consistency_verdict"],
    },
}


def _aliases_for(artifact_type: str, field_name: str) -> list[str]:
    return _FIELD_ALIASES.get(artifact_type, {}).get(field_name, [field_name])


def load_records(path: Path | str) -> list[dict]:
    target = Path(path)
    if not target.exists():
        return []
    if target.suffix.lower() in {".md", ".txt", ".html"}:
        text = target.read_text(encoding="utf-8", errors="replace")
        seed = {
            "text_artifact_version": "dopey-text-artifact-v1",
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "line_count": len(text.splitlines()),
            "path": str(target),
        }
        return [{**seed, "reproducibility_hash": reproducibility_hash(seed)}]
    if target.suffix == ".json":
        text = target.read_text(encoding="utf-8").strip()
        if not text:
            return []
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        return [parsed]
    records: list[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def load_latest_record(path: Path | str) -> dict:
    records = load_records(path)
    return records[-1] if records else {}


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_version(artifact_type: str, record: dict) -> str:
    spec = next((s for s in ARTIFACT_SPECS if s[0] == artifact_type), None)
    if not spec or not spec[3]:
        return ""
    version_field = spec[3][0]
    aliases = _aliases_for(artifact_type, version_field)
    for key in aliases:
        if isinstance(record, dict) and key in record:
            return str(record[key])
    return ""


def _missing_required_fields(artifact_type: str, record: dict) -> list[str]:
    spec = next((s for s in ARTIFACT_SPECS if s[0] == artifact_type), None)
    if not spec:
        return []
    required = spec[3]
    missing: list[str] = []
    for field_name in required:
        aliases = _aliases_for(artifact_type, field_name)
        if not any(k in record for k in aliases):
            missing.append(field_name)
    return missing


def build_artifact_record(artifact_type: str, path: Path | str) -> EvidenceArtifact:
    target = Path(path)
    artifact = EvidenceArtifact(artifact_type=artifact_type, path=str(target))
    if not target.exists():
        artifact.status = "missing"
        artifact.parse_status = "not_loaded"
        return artifact
    artifact.exists = True
    artifact.hash = _file_hash(target)
    try:
        records = load_records(target)
    except json.JSONDecodeError as exc:
        artifact.status = "parse_error"
        artifact.parse_status = f"json_error: {exc}"
        return artifact
    artifact.parse_status = "ok"
    artifact.record_count = len(records)
    if not records:
        artifact.status = "empty"
        return artifact
    latest = records[-1]
    artifact.latest_run_id = str(latest.get("run_id") or latest.get("batch_id") or latest.get("feedback_run_id") or "")
    artifact.model_version = _resolve_version(artifact_type, latest)
    artifact.safety_state = latest.get("safety_state", {}) if isinstance(latest.get("safety_state"), dict) else {}
    artifact.missing_required_fields = _missing_required_fields(artifact_type, latest)
    artifact.status = "stale" if artifact.missing_required_fields else "present"
    return artifact


def build_inventory(root: Path | str | None = None) -> EvidenceInventory:
    base = Path(root) if root else ARTIFACT_ROOT
    artifacts: list[EvidenceArtifact] = []
    digests: list[EvidenceRecordDigest] = []
    for artifact_type, rel_path, kind, _ in ARTIFACT_SPECS:
        full = base / rel_path
        artifact = build_artifact_record(artifact_type, full)
        artifacts.append(artifact)
        if artifact.status in {"present", "stale"}:
            try:
                records = load_records(full)
            except json.JSONDecodeError:
                continue
            for idx, record in enumerate(records):
                digests.append(EvidenceRecordDigest(
                    artifact_type=artifact_type,
                    path=str(full),
                    record_index=idx,
                    record_hash=hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
                    reproducibility_hash=str(record.get("reproducibility_hash", "")),
                    run_id=str(record.get("run_id") or record.get("batch_id") or record.get("feedback_run_id") or ""),
                    final_status=str(record.get("final_status", "")),
                ))
    return EvidenceInventory(artifacts=artifacts, record_digests=digests)


def build_completeness_report(inventory: EvidenceInventory) -> EvidenceCompletenessReport:
    expected = len(inventory.artifacts)
    present = sum(1 for a in inventory.artifacts if a.status in {"present", "stale"})
    missing = [a.artifact_type for a in inventory.artifacts if a.status == "missing"]
    empty = [a.artifact_type for a in inventory.artifacts if a.status in {"empty", "parse_error"}]
    return EvidenceCompletenessReport(
        expected_artifacts=expected,
        present_artifacts=present,
        missing_artifacts=missing,
        empty_artifacts=empty,
        completeness_fraction=round(present / expected, 6) if expected else 0.0,
    )


def build_freshness_report(inventory: EvidenceInventory) -> EvidenceFreshnessReport:
    stale = [a.artifact_type for a in inventory.artifacts if a.status == "stale"]
    missing_run_ids = [a.artifact_type for a in inventory.artifacts if a.status in {"present", "stale"} and not a.latest_run_id]
    notes: list[str] = []
    if stale:
        notes.append("some artifacts are missing required schema fields (stale)")
    if missing_run_ids:
        notes.append("some artifacts lack a run id")
    return EvidenceFreshnessReport(stale_artifacts=stale, missing_run_ids=missing_run_ids, notes=notes)
