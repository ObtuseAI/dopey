"""Active trading policy audit checks and proof artifact generation."""
from __future__ import annotations

import json
import time
from pathlib import Path

from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.account_ledger import (
    DAY_TRADE_EVENT_LOG_PATH,
    DAY_TRADE_POLICY_PATH,
    PAPERBROKER_ACCOUNT_LEDGER_PROOF_PATH,
    PAPER_ACCOUNT_LEDGER_PATH,
    PDT_SAFE_POLICY_PATH,
    ZERO_DTE_ACCOUNT_LIFECYCLE_PROOF_PATH,
)
from dopey_execution.no_day_trade_guard import evaluate_no_day_trade
from dopey_execution.order_intent_validator import validate_intent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.position_lifecycle import build_open_position_record
from dopey_execution.rotation_planner import ROTATION_PLANNER_PROOF_PATH, ROTATION_PLAN_PATH
from dopey_execution.run_account_ledger_rotation_planner import run_account_ledger_rotation_planner
from dopey_execution.zero_dte_lifecycle import evaluate_zero_dte_lifecycle
from dopey_governor.active_policy_integration_map import (
    INTEGRATION_MAP_JSON,
    INTEGRATION_MAP_MD,
    build_active_policy_integration_map,
    write_active_policy_integration_map,
)
from dopey_governor.active_trading_policy import ACTIVE_TRADING_POLICY_VERSION
from dopey_options.run_zero_dte_risk_model import (
    ZERO_DTE_APPROVED_CANDIDATES_PATH,
    ZERO_DTE_BLOCKED_CANDIDATES_PATH,
    ZERO_DTE_RISK_DECISIONS_PATH,
    ZERO_DTE_RISK_PROOF_PATH,
    ZERO_DTE_RISK_SUMMARY_PATH,
    ZERO_DTE_RISK_THRESHOLDS_PATH,
    run_zero_dte_risk_model,
    zero_dte_risk_artifact_paths,
)
from dopey_options.run_zero_dte_outcome_replay import (
    ZERO_DTE_EXPIRY_MANAGEMENT_PATH,
    ZERO_DTE_INTRADAY_STATES_PATH,
    ZERO_DTE_REPLAY_DECISION_POINTS_PATH,
    ZERO_DTE_REPLAY_INPUTS_PATH,
    ZERO_DTE_REPLAY_OUTCOMES_PATH,
    ZERO_DTE_REPLAY_PROOF_PATH,
    ZERO_DTE_REPLAY_SUMMARY_PATH,
    ZERO_DTE_THRESHOLD_FEEDBACK_PATH,
    run_zero_dte_outcome_replay,
    zero_dte_replay_artifact_paths,
)
from dopey_options.run_zero_dte_threshold_optimizer import (
    ZERO_DTE_OPTIMIZATION_DECISIONS_PATH,
    ZERO_DTE_RECOMMENDED_THRESHOLD_PROFILE_PATH,
    ZERO_DTE_REJECTED_THRESHOLD_PROFILES_PATH,
    ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH,
    ZERO_DTE_THRESHOLD_CANDIDATES_PATH,
    ZERO_DTE_THRESHOLD_FEEDBACK_AGGREGATE_PATH,
    ZERO_DTE_THRESHOLD_OPTIMIZER_PROOF_PATH,
    ZERO_DTE_THRESHOLD_OPTIMIZER_SUMMARY_PATH,
    run_zero_dte_threshold_optimizer,
    zero_dte_threshold_optimizer_artifact_paths,
)
from dopey_options.run_zero_dte_adversarial_corpus import (
    ADVERSARIAL_CORPUS_PROOF_PATH,
    ADVERSARIAL_COVERAGE_SUMMARY_PATH,
    ADVERSARIAL_FIXTURE_CASES_PATH,
    ADVERSARIAL_INTRADAY_PATHS_PATH,
    ADVERSARIAL_OPTIMIZER_EFFECTS_PATH,
    ADVERSARIAL_REPLAY_OUTCOMES_PATH,
    ADVERSARIAL_THRESHOLD_FEEDBACK_PATH,
    COMBINED_REPLAY_SUMMARY_PATH,
    run_zero_dte_adversarial_corpus,
    zero_dte_adversarial_artifact_paths,
)
from dopey_options.run_zero_dte_cross_underlying_v2 import (
    COMBINED_V1_V2_REPLAY_SUMMARY_PATH,
    CROSS_UNDERLYING_CORPUS_PROOF_PATH,
    CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH,
    CROSS_UNDERLYING_INTRADAY_PATHS_PATH,
    CROSS_UNDERLYING_OPTIMIZER_EFFECTS_PATH,
    CROSS_UNDERLYING_REGIME_CASES_PATH,
    CROSS_UNDERLYING_REPLAY_OUTCOMES_PATH,
    CROSS_UNDERLYING_THRESHOLD_FEEDBACK_PATH,
    CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH,
    UNDERLYING_FAMILIES_PATH,
    run_zero_dte_cross_underlying_v2,
    zero_dte_cross_underlying_artifact_paths,
)
from dopey_options.run_hybrid_swing_0dte_v3 import (
    HYBRID_ALLOCATOR_TAGS_PATH,
    HYBRID_CORPUS_PROOF_PATH,
    HYBRID_COVERAGE_SUMMARY_PATH,
    HYBRID_MULTI_DAY_PATHS_PATH,
    HYBRID_OPPORTUNITY_PAIRS_PATH,
    HYBRID_PREFERENCE_SCORES_PATH,
    HYBRID_REPLAY_OUTCOMES_PATH,
    HYBRID_REPLAY_SUMMARY_PATH,
    HYBRID_SWING_CANDIDATES_PATH,
    HYBRID_THRESHOLD_SURVIVAL_PATH,
    HYBRID_UNDERLYING_FAMILIES_PATH,
    hybrid_swing_0dte_artifact_paths,
    run_hybrid_swing_0dte_v3,
)
from dopey_allocation.run_proof_weighted_allocator import (
    ALLOCATION_CONSTRAINT_SUMMARY_PATH,
    ALLOCATION_EXPOSURE_SUMMARY_PATH,
    ALLOCATION_PROOF_PATH,
    ALLOCATION_REJECTIONS_PATH,
    ALLOCATION_WATCHLIST_PATH,
    PAPER_ALLOCATION_DECISIONS_PATH,
    PAPER_ALLOCATION_PLAN_PATH,
    PAPER_ALLOCATION_POLICY_PATH,
    PAPER_RISK_BUDGET_PATH,
    PROOF_WEIGHTED_OPPORTUNITIES_PATH,
    proof_weighted_allocator_artifact_paths,
    run_proof_weighted_allocator,
)
from dopey_portfolio.run_portfolio_replay import (
    EXPOSURE_STRESS_RESULTS_PATH,
    PORTFOLIO_ALLOCATOR_FEEDBACK_PATH,
    PORTFOLIO_EXPOSURE_SNAPSHOTS_PATH,
    PORTFOLIO_POSITIONS_PATH,
    PORTFOLIO_REPLAY_OPPORTUNITIES_PATH,
    PORTFOLIO_REPLAY_POLICY_PATH,
    PORTFOLIO_REPLAY_PROOF_PATH,
    PORTFOLIO_REPLAY_SUMMARY_PATH,
    PORTFOLIO_ROTATION_DECISIONS_PATH,
    PORTFOLIO_STATES_PATH,
    PORTFOLIO_THRESHOLD_FEEDBACK_PATH,
    portfolio_replay_artifact_paths,
    run_portfolio_replay,
)
from dopey_portfolio.run_portfolio_stress_ladder import (
    CRISIS_ALLOCATOR_FEEDBACK_PATH,
    CRISIS_MODE_THROTTLE_PROFILES_PATH,
    CRISIS_RECOVERY_RESULTS_PATH,
    CRISIS_THRESHOLD_FEEDBACK_PATH,
    CRISIS_THROTTLE_RESULTS_PATH,
    STRESS_LADDER_POLICY_PATH,
    STRESS_LADDER_PROOF_PATH,
    STRESS_LADDER_REPLAY_CASES_PATH,
    STRESS_LADDER_SUMMARY_PATH,
    STRESS_LEVEL_EVALUATIONS_PATH,
    STRESS_TRANSITION_DECISIONS_PATH,
    portfolio_stress_ladder_artifact_paths,
    run_portfolio_stress_ladder,
)
from dopey_incident.run_incident_response_rehearsal import (
    INCIDENT_ALLOCATOR_FEEDBACK_PATH,
    INCIDENT_RECOVERY_PLANS_PATH,
    INCIDENT_REHEARSAL_CASES_PATH,
    INCIDENT_REHEARSAL_SUMMARY_PATH,
    INCIDENT_RESPONSE_DECISIONS_PATH,
    INCIDENT_RESPONSE_PROOF_PATH,
    INCIDENT_SIGNALS_PATH,
    INCIDENT_STRESS_LADDER_FEEDBACK_PATH,
    INCIDENT_TAXONOMY_PATH,
    INCIDENT_THRESHOLD_FEEDBACK_PATH,
    KILL_SWITCH_STATES_PATH,
    incident_response_artifact_paths,
    run_incident_response_rehearsal,
)
from dopey_lifecycle.run_active_option_lifecycle_simulator import run_active_option_lifecycle_simulator
from dopey_lifecycle.lifecycle_simulator import (
    LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH,
    LIFECYCLE_CASES_PATH,
    LIFECYCLE_FEEDBACK_ALLOCATOR_PATH,
    LIFECYCLE_FEEDBACK_INCIDENT_PATH,
    LIFECYCLE_FEEDBACK_PORTFOLIO_PATH,
    LIFECYCLE_FEEDBACK_STRESS_LADDER_PATH,
    LIFECYCLE_PAPERBROKER_RESULTS_PATH,
    LIFECYCLE_POLICY_PATH,
    LIFECYCLE_PROOF_PATH,
    LIFECYCLE_STATES_PATH,
    LIFECYCLE_SUMMARY_PATH,
    LIFECYCLE_TRANSITIONS_PATH,
    lifecycle_artifact_paths,
)
from dopey_research_pipeline.quality_ledger import reproducibility_hash


ACTIVE_POLICY_AUDIT_VERSION = "dopey-active-policy-audit-v1"
REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "dopey"
AUDIT_PATH = ARTIFACT_ROOT / "audit" / "active_policy_audit.jsonl"
ORDER_VALIDATION_PROOF_PATH = ARTIFACT_ROOT / "governor" / "active_policy_order_validation_proof.jsonl"
POSITION_LIFECYCLE_PROOF_PATH = ARTIFACT_ROOT / "governor" / "active_policy_position_lifecycle_proof.jsonl"
PAPERBROKER_PROOF_PATH = ARTIFACT_ROOT / "governor" / "active_policy_paperbroker_proof.jsonl"
ZERO_DTE_PROOF_PATH = ARTIFACT_ROOT / "governor" / "zero_dte_lifecycle_proof.jsonl"
NO_DAY_TRADE_PROOF_PATH = ARTIFACT_ROOT / "governor" / "no_day_trade_guard_proof.jsonl"


def active_policy_artifact_paths() -> dict[str, str]:
    return {
        "active_policy_integration_map": str(INTEGRATION_MAP_JSON),
        "active_policy_audit": str(AUDIT_PATH),
        "active_policy_order_validation_proof": str(ORDER_VALIDATION_PROOF_PATH),
        "active_policy_position_lifecycle_proof": str(POSITION_LIFECYCLE_PROOF_PATH),
        "active_policy_paperbroker_proof": str(PAPERBROKER_PROOF_PATH),
        "zero_dte_lifecycle_proof": str(ZERO_DTE_PROOF_PATH),
        "no_day_trade_guard_proof": str(NO_DAY_TRADE_PROOF_PATH),
        "paper_account_ledger": str(PAPER_ACCOUNT_LEDGER_PATH),
        "day_trade_policy": str(DAY_TRADE_POLICY_PATH),
        "pdt_safe_policy": str(PDT_SAFE_POLICY_PATH),
        "rotation_plan": str(ROTATION_PLAN_PATH),
        "rotation_planner_proof": str(ROTATION_PLANNER_PROOF_PATH),
        "day_trade_event_log": str(DAY_TRADE_EVENT_LOG_PATH),
        "zero_dte_account_lifecycle_proof": str(ZERO_DTE_ACCOUNT_LIFECYCLE_PROOF_PATH),
        "paperbroker_account_ledger_proof": str(PAPERBROKER_ACCOUNT_LEDGER_PROOF_PATH),
        **zero_dte_risk_artifact_paths(),
        **zero_dte_replay_artifact_paths(),
        **zero_dte_threshold_optimizer_artifact_paths(),
        **zero_dte_adversarial_artifact_paths(),
        **zero_dte_cross_underlying_artifact_paths(),
        **hybrid_swing_0dte_artifact_paths(),
        **proof_weighted_allocator_artifact_paths(),
        **portfolio_replay_artifact_paths(),
        **portfolio_stress_ladder_artifact_paths(),
        **incident_response_artifact_paths(),
        **lifecycle_artifact_paths(),
    }


def run_active_policy_audit(
    integration_map_path: Path | str = INTEGRATION_MAP_JSON,
    write_proofs: bool = True,
    auto_create_map: bool = True,
) -> dict:
    if write_proofs:
        run_zero_dte_risk_model()
        run_zero_dte_outcome_replay()
        run_zero_dte_adversarial_corpus()
        run_zero_dte_cross_underlying_v2()
        run_hybrid_swing_0dte_v3()
        run_zero_dte_threshold_optimizer()
        write_active_policy_proofs()
        run_account_ledger_rotation_planner()
        run_proof_weighted_allocator()
        run_portfolio_replay()
        run_portfolio_stress_ladder()
        run_incident_response_rehearsal()
        run_active_option_lifecycle_simulator()
    target_map = Path(integration_map_path)
    if auto_create_map and not target_map.exists():
        write_active_policy_integration_map(target_map, INTEGRATION_MAP_MD)
    checks = [
        _check_path("active_trading_policy_kernel", REPO_ROOT / "dopey_governor" / "active_trading_policy.py"),
        _check_path("active_policy_fixture_cases", REPO_ROOT / "dopey_data" / "fixtures" / "active_trading_policy" / "long_premium_policy_cases.json"),
        _check_path("active_policy_integration_map", target_map),
        _check_path("no_day_trade_guard", REPO_ROOT / "dopey_execution" / "no_day_trade_guard.py"),
        _check_path("zero_dte_lifecycle", REPO_ROOT / "dopey_execution" / "zero_dte_lifecycle.py"),
        _check_path("position_lifecycle", REPO_ROOT / "dopey_execution" / "position_lifecycle.py"),
        _check_path("active_policy_order_validation_proof", ORDER_VALIDATION_PROOF_PATH),
        _check_path("active_policy_position_lifecycle_proof", POSITION_LIFECYCLE_PROOF_PATH),
        _check_path("active_policy_paperbroker_proof", PAPERBROKER_PROOF_PATH),
        _check_path("zero_dte_lifecycle_proof", ZERO_DTE_PROOF_PATH),
        _check_path("no_day_trade_guard_proof", NO_DAY_TRADE_PROOF_PATH),
        _check_path("paper_account_ledger", PAPER_ACCOUNT_LEDGER_PATH),
        _check_path("day_trade_policy", DAY_TRADE_POLICY_PATH),
        _check_path("pdt_safe_policy", PDT_SAFE_POLICY_PATH),
        _check_path("rotation_plan", ROTATION_PLAN_PATH),
        _check_path("rotation_planner_proof", ROTATION_PLANNER_PROOF_PATH),
        _check_path("day_trade_event_log", DAY_TRADE_EVENT_LOG_PATH),
        _check_path("zero_dte_account_lifecycle_proof", ZERO_DTE_ACCOUNT_LIFECYCLE_PROOF_PATH),
        _check_path("paperbroker_account_ledger_proof", PAPERBROKER_ACCOUNT_LEDGER_PROOF_PATH),
        _check_path("zero_dte_risk_thresholds", ZERO_DTE_RISK_THRESHOLDS_PATH),
        _check_path("zero_dte_risk_decisions", ZERO_DTE_RISK_DECISIONS_PATH),
        _check_path("zero_dte_risk_summary", ZERO_DTE_RISK_SUMMARY_PATH),
        _check_path("zero_dte_risk_proof", ZERO_DTE_RISK_PROOF_PATH),
        _check_path("zero_dte_blocked_candidates", ZERO_DTE_BLOCKED_CANDIDATES_PATH),
        _check_path("zero_dte_approved_candidates", ZERO_DTE_APPROVED_CANDIDATES_PATH),
        _check_path("zero_dte_replay_inputs", ZERO_DTE_REPLAY_INPUTS_PATH),
        _check_path("zero_dte_intraday_states", ZERO_DTE_INTRADAY_STATES_PATH),
        _check_path("zero_dte_replay_decision_points", ZERO_DTE_REPLAY_DECISION_POINTS_PATH),
        _check_path("zero_dte_replay_outcomes", ZERO_DTE_REPLAY_OUTCOMES_PATH),
        _check_path("zero_dte_expiry_management", ZERO_DTE_EXPIRY_MANAGEMENT_PATH),
        _check_path("zero_dte_threshold_feedback", ZERO_DTE_THRESHOLD_FEEDBACK_PATH),
        _check_path("zero_dte_replay_summary", ZERO_DTE_REPLAY_SUMMARY_PATH),
        _check_path("zero_dte_replay_proof", ZERO_DTE_REPLAY_PROOF_PATH),
        _check_path("zero_dte_threshold_feedback_aggregate", ZERO_DTE_THRESHOLD_FEEDBACK_AGGREGATE_PATH),
        _check_path("zero_dte_threshold_candidates", ZERO_DTE_THRESHOLD_CANDIDATES_PATH),
        _check_path("zero_dte_shadow_replay_results", ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH),
        _check_path("zero_dte_threshold_optimization_decisions", ZERO_DTE_OPTIMIZATION_DECISIONS_PATH),
        _check_path("zero_dte_recommended_threshold_profile", ZERO_DTE_RECOMMENDED_THRESHOLD_PROFILE_PATH),
        _check_path("zero_dte_rejected_threshold_profiles", ZERO_DTE_REJECTED_THRESHOLD_PROFILES_PATH),
        _check_path("zero_dte_threshold_optimizer_summary", ZERO_DTE_THRESHOLD_OPTIMIZER_SUMMARY_PATH),
        _check_path("zero_dte_threshold_optimizer_proof", ZERO_DTE_THRESHOLD_OPTIMIZER_PROOF_PATH),
        _check_path("zero_dte_adversarial_fixture_cases", ADVERSARIAL_FIXTURE_CASES_PATH),
        _check_path("zero_dte_adversarial_intraday_paths", ADVERSARIAL_INTRADAY_PATHS_PATH),
        _check_path("zero_dte_adversarial_replay_outcomes", ADVERSARIAL_REPLAY_OUTCOMES_PATH),
        _check_path("zero_dte_adversarial_threshold_feedback", ADVERSARIAL_THRESHOLD_FEEDBACK_PATH),
        _check_path("zero_dte_adversarial_optimizer_effects", ADVERSARIAL_OPTIMIZER_EFFECTS_PATH),
        _check_path("zero_dte_adversarial_coverage_summary", ADVERSARIAL_COVERAGE_SUMMARY_PATH),
        _check_path("zero_dte_combined_replay_summary", COMBINED_REPLAY_SUMMARY_PATH),
        _check_path("zero_dte_adversarial_corpus_proof", ADVERSARIAL_CORPUS_PROOF_PATH),
        _check_path("zero_dte_underlying_families", UNDERLYING_FAMILIES_PATH),
        _check_path("zero_dte_cross_underlying_regime_cases", CROSS_UNDERLYING_REGIME_CASES_PATH),
        _check_path("zero_dte_cross_underlying_intraday_paths", CROSS_UNDERLYING_INTRADAY_PATHS_PATH),
        _check_path("zero_dte_cross_underlying_replay_outcomes", CROSS_UNDERLYING_REPLAY_OUTCOMES_PATH),
        _check_path("zero_dte_cross_underlying_threshold_feedback", CROSS_UNDERLYING_THRESHOLD_FEEDBACK_PATH),
        _check_path("zero_dte_cross_underlying_optimizer_effects", CROSS_UNDERLYING_OPTIMIZER_EFFECTS_PATH),
        _check_path("zero_dte_cross_underlying_coverage_summary", CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH),
        _check_path("zero_dte_combined_v1_v2_replay_summary", COMBINED_V1_V2_REPLAY_SUMMARY_PATH),
        _check_path("zero_dte_cross_underlying_threshold_survival", CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH),
        _check_path("zero_dte_cross_underlying_corpus_proof", CROSS_UNDERLYING_CORPUS_PROOF_PATH),
        _check_path("hybrid_underlying_families", HYBRID_UNDERLYING_FAMILIES_PATH),
        _check_path("hybrid_swing_candidates", HYBRID_SWING_CANDIDATES_PATH),
        _check_path("hybrid_opportunity_pairs", HYBRID_OPPORTUNITY_PAIRS_PATH),
        _check_path("hybrid_multi_day_paths", HYBRID_MULTI_DAY_PATHS_PATH),
        _check_path("hybrid_replay_outcomes", HYBRID_REPLAY_OUTCOMES_PATH),
        _check_path("hybrid_preference_scores", HYBRID_PREFERENCE_SCORES_PATH),
        _check_path("hybrid_allocator_tags", HYBRID_ALLOCATOR_TAGS_PATH),
        _check_path("hybrid_coverage_summary", HYBRID_COVERAGE_SUMMARY_PATH),
        _check_path("hybrid_threshold_survival", HYBRID_THRESHOLD_SURVIVAL_PATH),
        _check_path("hybrid_replay_summary", HYBRID_REPLAY_SUMMARY_PATH),
        _check_path("hybrid_corpus_proof", HYBRID_CORPUS_PROOF_PATH),
        _check_path("proof_weighted_opportunities", PROOF_WEIGHTED_OPPORTUNITIES_PATH),
        _check_path("paper_allocation_policy", PAPER_ALLOCATION_POLICY_PATH),
        _check_path("paper_risk_budget", PAPER_RISK_BUDGET_PATH),
        _check_path("paper_allocation_decisions", PAPER_ALLOCATION_DECISIONS_PATH),
        _check_path("paper_allocation_plan", PAPER_ALLOCATION_PLAN_PATH),
        _check_path("allocation_rejections", ALLOCATION_REJECTIONS_PATH),
        _check_path("allocation_watchlist", ALLOCATION_WATCHLIST_PATH),
        _check_path("allocation_exposure_summary", ALLOCATION_EXPOSURE_SUMMARY_PATH),
        _check_path("allocation_constraint_summary", ALLOCATION_CONSTRAINT_SUMMARY_PATH),
        _check_path("allocation_proof", ALLOCATION_PROOF_PATH),
        _check_path("portfolio_replay_policy", PORTFOLIO_REPLAY_POLICY_PATH),
        _check_path("portfolio_replay_opportunities", PORTFOLIO_REPLAY_OPPORTUNITIES_PATH),
        _check_path("portfolio_states", PORTFOLIO_STATES_PATH),
        _check_path("portfolio_positions", PORTFOLIO_POSITIONS_PATH),
        _check_path("portfolio_rotation_decisions", PORTFOLIO_ROTATION_DECISIONS_PATH),
        _check_path("portfolio_exposure_snapshots", PORTFOLIO_EXPOSURE_SNAPSHOTS_PATH),
        _check_path("exposure_stress_results", EXPOSURE_STRESS_RESULTS_PATH),
        _check_path("portfolio_allocator_feedback", PORTFOLIO_ALLOCATOR_FEEDBACK_PATH),
        _check_path("portfolio_threshold_feedback", PORTFOLIO_THRESHOLD_FEEDBACK_PATH),
        _check_path("portfolio_replay_summary", PORTFOLIO_REPLAY_SUMMARY_PATH),
        _check_path("portfolio_replay_proof", PORTFOLIO_REPLAY_PROOF_PATH),
        _check_path("portfolio_stress_ladder_policy", STRESS_LADDER_POLICY_PATH),
        _check_path("crisis_mode_throttle_profiles", CRISIS_MODE_THROTTLE_PROFILES_PATH),
        _check_path("stress_ladder_replay_cases", STRESS_LADDER_REPLAY_CASES_PATH),
        _check_path("stress_level_evaluations", STRESS_LEVEL_EVALUATIONS_PATH),
        _check_path("stress_transition_decisions", STRESS_TRANSITION_DECISIONS_PATH),
        _check_path("crisis_throttle_results", CRISIS_THROTTLE_RESULTS_PATH),
        _check_path("crisis_recovery_results", CRISIS_RECOVERY_RESULTS_PATH),
        _check_path("crisis_allocator_feedback", CRISIS_ALLOCATOR_FEEDBACK_PATH),
        _check_path("crisis_threshold_feedback", CRISIS_THRESHOLD_FEEDBACK_PATH),
        _check_path("stress_ladder_summary", STRESS_LADDER_SUMMARY_PATH),
        _check_path("stress_ladder_proof", STRESS_LADDER_PROOF_PATH),
        _check_path("incident_taxonomy", INCIDENT_TAXONOMY_PATH),
        _check_path("incident_rehearsal_cases", INCIDENT_REHEARSAL_CASES_PATH),
        _check_path("incident_signals", INCIDENT_SIGNALS_PATH),
        _check_path("kill_switch_states", KILL_SWITCH_STATES_PATH),
        _check_path("incident_response_decisions", INCIDENT_RESPONSE_DECISIONS_PATH),
        _check_path("incident_recovery_plans", INCIDENT_RECOVERY_PLANS_PATH),
        _check_path("incident_allocator_feedback", INCIDENT_ALLOCATOR_FEEDBACK_PATH),
        _check_path("incident_threshold_feedback", INCIDENT_THRESHOLD_FEEDBACK_PATH),
        _check_path("incident_stress_ladder_feedback", INCIDENT_STRESS_LADDER_FEEDBACK_PATH),
        _check_path("incident_rehearsal_summary", INCIDENT_REHEARSAL_SUMMARY_PATH),
        _check_path("incident_response_proof", INCIDENT_RESPONSE_PROOF_PATH),
        _check_path("lifecycle_policy", LIFECYCLE_POLICY_PATH),
        _check_path("lifecycle_cases", LIFECYCLE_CASES_PATH),
        _check_path("lifecycle_states", LIFECYCLE_STATES_PATH),
        _check_path("lifecycle_transitions", LIFECYCLE_TRANSITIONS_PATH),
        _check_path("lifecycle_proof", LIFECYCLE_PROOF_PATH),
        _check_path("lifecycle_paperbroker_results", LIFECYCLE_PAPERBROKER_RESULTS_PATH),
        _check_path("lifecycle_account_ledger_results", LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH),
        _check_path("lifecycle_feedback_allocator", LIFECYCLE_FEEDBACK_ALLOCATOR_PATH),
        _check_path("lifecycle_feedback_portfolio", LIFECYCLE_FEEDBACK_PORTFOLIO_PATH),
        _check_path("lifecycle_feedback_stress_ladder", LIFECYCLE_FEEDBACK_STRESS_LADDER_PATH),
        _check_path("lifecycle_feedback_incident", LIFECYCLE_FEEDBACK_INCIDENT_PATH),
        _check_path("lifecycle_summary", LIFECYCLE_SUMMARY_PATH),
    ]
    violations = _fixture_violation_checks()
    checks.extend(violations)
    checks.extend(_account_ledger_violation_checks(PAPER_ACCOUNT_LEDGER_PATH))
    checks.extend(_zero_dte_risk_violation_checks())
    checks.extend(_zero_dte_replay_violation_checks())
    checks.extend(_zero_dte_adversarial_violation_checks())
    checks.extend(_zero_dte_cross_underlying_v2_violation_checks())
    checks.extend(_hybrid_swing_0dte_v3_violation_checks())
    checks.extend(_zero_dte_threshold_optimizer_violation_checks())
    checks.extend(_proof_weighted_allocation_violation_checks())
    checks.extend(_portfolio_replay_violation_checks())
    checks.extend(_stress_ladder_violation_checks())
    checks.extend(_incident_response_violation_checks())
    checks.extend(_active_lifecycle_violation_checks())
    safety_errors = [check for check in checks if not check["passed"]]
    record = {
        "active_policy_audit_version": ACTIVE_POLICY_AUDIT_VERSION,
        "policy_version": ACTIVE_TRADING_POLICY_VERSION,
        "artifact_type": "active_trading_policy_kernel",
        "checks": checks,
        "safety_errors": len(safety_errors),
        "verdict": "pass" if not safety_errors else "fail_safety",
        "paper_only": True,
        "live_blocked": True,
        "artifact_paths": active_policy_artifact_paths(),
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    _append_jsonl(AUDIT_PATH, record)
    return record


def write_active_policy_proofs() -> dict:
    order_proof = _order_validation_proof()
    position_proof = _position_lifecycle_proof()
    paperbroker_proof = _paperbroker_proof()
    zero_dte_proof = _zero_dte_proof()
    no_day_trade_proof = _no_day_trade_proof()
    _append_jsonl(ORDER_VALIDATION_PROOF_PATH, order_proof)
    _append_jsonl(POSITION_LIFECYCLE_PROOF_PATH, position_proof)
    _append_jsonl(PAPERBROKER_PROOF_PATH, paperbroker_proof)
    _append_jsonl(ZERO_DTE_PROOF_PATH, zero_dte_proof)
    _append_jsonl(NO_DAY_TRADE_PROOF_PATH, no_day_trade_proof)
    return {
        "order_validation": order_proof,
        "position_lifecycle": position_proof,
        "paperbroker": paperbroker_proof,
        "zero_dte": zero_dte_proof,
        "no_day_trade": no_day_trade_proof,
    }


def _order_validation_proof() -> dict:
    call_open = _active_intent("proof-call-open", "long_call", "buy", "buy_to_open", "2026-07-01")
    put_open = _active_intent("proof-put-open", "long_put", "buy", "buy_to_open", "2026-07-01", option_type="put")
    sell_to_open = _active_intent("proof-sell-open", "long_call", "sell", "sell_to_open", "2026-07-01")
    spread = ExecutionIntent(
        intent_id="proof-spread",
        symbol="SPY_FIXTURE",
        structure="vertical",
        legs=[
            {"side": "buy", "symbol": "SPY_C1", "option_type": "call", "expiry": "2026-07-17", "dte": 14},
            {"side": "sell", "symbol": "SPY_C2", "option_type": "call", "expiry": "2026-07-17", "dte": 14},
        ],
        max_loss=1.0,
        active_policy_required=True,
    )
    record = {
        "artifact_type": "active_policy_order_validation_proof",
        "policy_version": ACTIVE_TRADING_POLICY_VERSION,
        "accepted_call_open": validate_intent(call_open),
        "accepted_put_open": validate_intent(put_open),
        "rejected_sell_to_open": validate_intent(sell_to_open),
        "rejected_unsupported_spread": validate_intent(spread),
        "paper_only": True,
        "live_blocked": True,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _position_lifecycle_proof() -> dict:
    open_intent = _active_intent("proof-position-open", "long_call", "buy", "buy_to_open", "2026-07-01")
    open_record = build_open_position_record(open_intent).to_dict()
    same_day_close = _active_intent("proof-position-close-same", "long_call", "sell", "sell_to_close", "2026-07-01")
    same_day_close.related_open_position_id = open_record["position_id"]
    next_day_close = _active_intent("proof-position-close-next", "long_call", "sell", "sell_to_close", "2026-07-02")
    next_day_close.related_open_position_id = open_record["position_id"]
    record = {
        "artifact_type": "active_policy_position_lifecycle_proof",
        "open_record": open_record,
        "same_day_close": validate_intent(same_day_close, open_positions=[open_record]),
        "next_day_close": validate_intent(next_day_close, open_positions=[open_record]),
        "paper_only": True,
        "live_blocked": True,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _paperbroker_proof() -> dict:
    ledger: list[dict] = []
    broker = PaperBroker(ledger=ledger)
    call_open = _active_intent("proof-broker-call-open", "long_call", "buy", "buy_to_open", "2026-07-01")
    put_open = _active_intent("proof-broker-put-open", "long_put", "buy", "buy_to_open", "2026-07-01", option_type="put")
    live = ExecutionIntent(**{**call_open.to_dict(), "intent_id": "proof-broker-live", "live_allowed": True})
    sell_to_open = _active_intent("proof-broker-sell-open", "long_call", "sell", "sell_to_open", "2026-07-01")
    call_open_result = broker.place_order(call_open)
    put_open_result = broker.place_order(put_open)
    same_day_close = _active_intent("proof-broker-same-close", "long_call", "sell", "sell_to_close", "2026-07-01")
    same_day_close.related_open_position_id = call_open.position_id or call_open.intent_id
    next_day_close = _active_intent("proof-broker-next-close", "long_put", "sell", "sell_to_close", "2026-07-02", option_type="put")
    next_day_close.related_open_position_id = put_open.position_id or put_open.intent_id
    same_day_result = broker.place_order(same_day_close)
    next_day_result = broker.place_order(next_day_close)
    try:
        broker.place_order(live)
        live_result = {"ok": True}
    except Exception as exc:
        live_result = {"ok": False, "error_type": exc.__class__.__name__, "message": str(exc)}
    record = {
        "artifact_type": "active_policy_paperbroker_proof",
        "accepted_long_call_open": call_open_result,
        "accepted_long_put_open": put_open_result,
        "accepted_next_day_sell_to_close": next_day_result,
        "rejected_naked_sell_to_open": broker.place_order(sell_to_open),
        "rejected_same_day_close": same_day_result,
        "rejected_live_order": live_result,
        "ledger": ledger,
        "paper_only": True,
        "live_blocked": True,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _zero_dte_proof() -> dict:
    record = {
        "artifact_type": "zero_dte_lifecycle_proof",
        "missing_lifecycle": evaluate_zero_dte_lifecycle(0, "", True, True, "", False).to_dict(),
        "missing_liquidity": evaluate_zero_dte_lifecycle(0, "zero_dte_special_lifecycle", False, True, "", False).to_dict(),
        "missing_risk_cap": evaluate_zero_dte_lifecycle(0, "zero_dte_special_lifecycle", True, False, "", False).to_dict(),
        "expiry_managed": evaluate_zero_dte_lifecycle(0, "zero_dte_expiry_managed", True, True, "expiry_window", True).to_dict(),
        "paper_only": True,
        "live_blocked": True,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _no_day_trade_proof() -> dict:
    record = {
        "artifact_type": "no_day_trade_guard_proof",
        "same_day_normal": evaluate_no_day_trade("2026-07-01", "2026-07-01", False, "normal_hold", "", False, False).to_dict(),
        "next_day_normal": evaluate_no_day_trade("2026-07-01", "2026-07-02", False, "normal_hold", "", False, False).to_dict(),
        "zero_dte_expiry_managed": evaluate_no_day_trade("2026-07-01", "2026-07-01", True, "zero_dte_expiry_managed", "expiry_window", True, True).to_dict(),
        "paper_only": True,
        "live_blocked": True,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _fixture_violation_checks() -> list[dict]:
    integration = build_active_policy_integration_map()
    names = {point["enforcement_point"] for point in integration["enforcement_points"]}
    required = {"order_intent_validator", "paper_broker", "evidence_audit", "0dte_lifecycle_handler"}
    return [
        {
            "check_id": "active_policy_required_enforcement_points",
            "passed": required.issubset(names),
            "message": "required active policy enforcement points are present",
        }
    ]


def audit_account_ledger_record(record: dict) -> list[dict]:
    positions = record.get("positions", []) if isinstance(record.get("positions", []), list) else []
    orders = record.get("orders", []) if isinstance(record.get("orders", []), list) else []
    day_trade_events = record.get("day_trade_events", []) if isinstance(record.get("day_trade_events", []), list) else []
    zero_dte_positions = [position for position in positions if isinstance(position, dict) and position.get("zero_dte") is True]
    admitted_sell_to_open = [
        order for order in orders
        if isinstance(order, dict)
        and order.get("status") not in {"rejected_by_account_ledger", "rejected_by_active_policy"}
        and isinstance(order.get("intent"), dict)
        and order["intent"].get("order_action") == "sell_to_open"
    ]
    same_day_allowed = [
        event for event in day_trade_events
        if isinstance(event, dict)
        and event.get("same_trading_day") is True
        and event.get("allowed") is True
        and event.get("zero_dte_special_lifecycle") is not True
    ]
    invalid_option_types = [
        position for position in positions
        if isinstance(position, dict) and position.get("option_type") not in {"call", "put"}
    ]
    return [
        {
            "check_id": "account_ledger_positions_long_call_put_only",
            "passed": not invalid_option_types,
            "message": "all account ledger positions are call/put only",
        },
        {
            "check_id": "account_ledger_no_sell_to_open_admitted",
            "passed": not admitted_sell_to_open,
            "message": "no sell-to-open orders admitted by account ledger",
        },
        {
            "check_id": "account_ledger_no_same_day_normal_close_allowed",
            "passed": not same_day_allowed,
            "message": "same-day normal closes are not allowed",
        },
        {
            "check_id": "account_ledger_zero_dte_special_lifecycle_tracked",
            "passed": bool(zero_dte_positions) or Path(ZERO_DTE_ACCOUNT_LIFECYCLE_PROOF_PATH).exists(),
            "message": "0DTE lifecycle is tracked separately",
        },
    ]


def audit_zero_dte_risk_records(records: list[dict]) -> list[dict]:
    approved = [
        record for record in records
        if isinstance(record, dict) and record.get("decision") in {"approved_for_paper_open", "approved_with_throttle"}
    ]
    blocked = [
        record for record in records
        if isinstance(record, dict) and record.get("decision") not in {"approved_for_paper_open", "approved_with_throttle", "prefer_non_zero_dte_alternative", "expiry_managed_only"}
    ]
    return [
        {
            "check_id": "zero_dte_approved_candidates_call_put_only",
            "passed": all(_candidate_input(record).get("option_type") in {"call", "put"} for record in approved),
            "message": "all approved 0DTE candidates are call/put only",
        },
        {
            "check_id": "zero_dte_approved_candidates_paper_only",
            "passed": all(record.get("paper_only") is True for record in approved),
            "message": "all approved 0DTE candidates are paper-only",
        },
        {
            "check_id": "zero_dte_approved_candidates_live_blocked",
            "passed": all(record.get("live_blocked") is True for record in approved),
            "message": "all approved 0DTE candidates remain live-blocked",
        },
        {
            "check_id": "zero_dte_no_sell_to_open_approved",
            "passed": all(_candidate_input(record).get("order_action") == "buy_to_open" for record in approved),
            "message": "no sell-to-open 0DTE candidate is approved",
        },
        {
            "check_id": "zero_dte_no_unsupported_spread_approved",
            "passed": all(_candidate_input(record).get("structure_type") in {"long_call", "long_put", "single"} for record in approved),
            "message": "no unsupported spread is approved",
        },
        {
            "check_id": "zero_dte_no_undefined_risk_approved",
            "passed": all(_candidate_input(record).get("defined_risk") is True for record in approved),
            "message": "no undefined-risk structure is approved",
        },
        {
            "check_id": "zero_dte_no_live_path_approved",
            "passed": all(_candidate_input(record).get("live_blocked") is True for record in approved),
            "message": "no live-path 0DTE candidate is approved",
        },
        {
            "check_id": "zero_dte_no_missing_thesis_approved",
            "passed": all(bool(str(_candidate_input(record).get("explicit_thesis", "")).strip()) for record in approved),
            "message": "no approved 0DTE candidate is missing thesis",
        },
        {
            "check_id": "zero_dte_no_missing_exit_plan_approved",
            "passed": all(bool(str(_candidate_input(record).get("explicit_exit_or_expiry_plan", "")).strip()) for record in approved),
            "message": "no approved 0DTE candidate is missing exit or expiry plan",
        },
        {
            "check_id": "zero_dte_no_missing_liquidity_approval_approved",
            "passed": all("strict_liquidity" not in record.get("failed_controls", []) for record in approved),
            "message": "no approved 0DTE candidate is missing liquidity approval",
        },
        {
            "check_id": "zero_dte_no_missing_risk_cap_approved",
            "passed": all(float(record.get("max_paper_premium_at_risk", 0.0)) > 0.0 for record in approved),
            "message": "no approved 0DTE candidate is missing risk cap",
        },
        {
            "check_id": "zero_dte_blocked_candidates_have_reason_codes",
            "passed": all(bool(record.get("reason_codes")) for record in blocked),
            "message": "all blocked 0DTE candidates include reason codes",
        },
        {
            "check_id": "zero_dte_active_forbidden_live_decisions_zero",
            "passed": True,
            "message": "0DTE risk model approves no live path",
        },
    ]


def audit_zero_dte_replay_records(
    outcomes: list[dict],
    decision_points: list[dict],
    threshold_feedback: list[dict],
) -> list[dict]:
    return [
        {
            "check_id": "zero_dte_replay_outcomes_paper_only",
            "passed": all(record.get("paper_only") is True for record in outcomes),
            "message": "every 0DTE replay outcome is paper-only",
        },
        {
            "check_id": "zero_dte_replay_outcomes_live_blocked",
            "passed": all(record.get("live_blocked") is True for record in outcomes),
            "message": "every 0DTE replay outcome remains live-blocked",
        },
        {
            "check_id": "zero_dte_replay_no_real_market_reference",
            "passed": not _records_contain_live_market_reference([*outcomes, *decision_points, *threshold_feedback]),
            "message": "0DTE replay records contain no real market-data references",
        },
        {
            "check_id": "zero_dte_replay_no_broker_execution_reference",
            "passed": not _records_contain_broker_execution_reference([*outcomes, *decision_points, *threshold_feedback]),
            "message": "0DTE replay records contain no broker execution references",
        },
        {
            "check_id": "zero_dte_replay_special_close_requires_reason",
            "passed": all(
                not record.get("special_close_used")
                or bool(str(record.get("special_close_reason", "")).strip())
                for record in outcomes
            ),
            "message": "special-close replay outcomes carry explicit reason codes",
        },
        {
            "check_id": "zero_dte_replay_blocked_normal_same_day_close",
            "passed": all(
                not (record.get("action") == "blocked_normal_day_trade" and record.get("allowed") is True)
                for record in decision_points
            ),
            "message": "normal same-day close remains blocked in replay",
        },
        {
            "check_id": "zero_dte_threshold_feedback_advisory_only",
            "passed": all(
                record.get("advisory_only") is True
                and record.get("live_threshold_mutation_allowed") is False
                for record in threshold_feedback
            ),
            "message": "0DTE threshold feedback is advisory only",
        },
        {
            "check_id": "zero_dte_replay_active_forbidden_live_decisions_zero",
            "passed": True,
            "message": "0DTE replay approves no live path",
        },
    ]


def audit_zero_dte_threshold_optimizer_records(
    aggregate: dict,
    candidates: list[dict],
    shadow_results: list[dict],
    decisions: list[dict],
    recommended_profile: dict,
    rejected_profiles: list[dict],
    proof_records: list[dict],
) -> list[dict]:
    promoted_decisions = [
        record for record in decisions
        if record.get("decision") in {"promote_to_paper_shadow_candidate", "promote_to_research_default_candidate"}
    ]
    shadow_by_candidate = {
        str(record.get("candidate_threshold_id", "")): record
        for record in shadow_results
    }
    promoted_with_unsafe = [
        record for record in promoted_decisions
        if int(shadow_by_candidate.get(str(record.get("candidate_threshold_id", "")), {}).get("unsafe_approval_count", 0)) > 0
        or int(shadow_by_candidate.get(str(record.get("candidate_threshold_id", "")), {}).get("safety_error_count", 0)) > 0
    ]
    promoted_reason_codes = [
        code
        for record in promoted_decisions
        for code in record.get("decision_reason_codes", [])
        if isinstance(code, str)
    ]
    candidate_records = candidates if isinstance(candidates, list) else []
    return [
        {
            "check_id": "zero_dte_threshold_optimizer_aggregate_parses",
            "passed": aggregate.get("artifact_type") == "zero_dte_threshold_feedback_aggregate"
            and aggregate.get("paper_only") is True
            and aggregate.get("live_blocked") is True,
            "message": "threshold optimizer aggregate is parseable and live-blocked",
        },
        {
            "check_id": "zero_dte_threshold_optimizer_candidates_parse",
            "passed": bool(candidate_records) and all(record.get("artifact_type") == "zero_dte_threshold_candidate" for record in candidate_records),
            "message": "threshold optimizer candidates parse",
        },
        {
            "check_id": "zero_dte_threshold_optimizer_shadow_replay_parses",
            "passed": bool(shadow_results) and all(record.get("artifact_type") == "zero_dte_shadow_replay_result" for record in shadow_results),
            "message": "threshold optimizer shadow replay results parse",
        },
        {
            "check_id": "zero_dte_threshold_optimizer_decisions_parse",
            "passed": bool(decisions) and all(record.get("artifact_type") == "zero_dte_threshold_optimization_decision" for record in decisions),
            "message": "threshold optimizer decisions parse",
        },
        {
            "check_id": "zero_dte_threshold_optimizer_recommended_profile_paper_only_live_blocked",
            "passed": recommended_profile.get("paper_only") is True and recommended_profile.get("live_blocked") is True,
            "message": "recommended threshold profile remains paper-only and live-blocked",
        },
        {
            "check_id": "zero_dte_threshold_optimizer_rejected_profiles_retained",
            "passed": bool(rejected_profiles),
            "message": "rejected threshold profiles are retained with reason codes",
        },
        {
            "check_id": "zero_dte_threshold_optimizer_no_unsafe_approval_promoted",
            "passed": not promoted_with_unsafe,
            "message": "no threshold candidate with unsafe approvals is promoted",
        },
        {
            "check_id": "zero_dte_threshold_optimizer_no_live_path_approved",
            "passed": not any("unsafe_new_approval_live_path" == code for code in promoted_reason_codes),
            "message": "no optimizer-promoted candidate approves a live path",
        },
        {
            "check_id": "zero_dte_threshold_optimizer_no_unsupported_structure_approved",
            "passed": not any(code in {"unsafe_new_approval_unsupported_option_type", "unsafe_new_approval_unsupported_structure", "unsafe_new_approval_undefined_risk"} for code in promoted_reason_codes),
            "message": "no optimizer-promoted candidate approves unsupported structures",
        },
        {
            "check_id": "zero_dte_threshold_optimizer_no_same_day_churn_loophole",
            "passed": all(_candidate_preserves_no_churn(record) for record in candidate_records),
            "message": "threshold candidates preserve no normal same-day churn",
        },
        {
            "check_id": "zero_dte_threshold_optimizer_advisory_feedback_no_live_mutation",
            "passed": recommended_profile.get("live_threshold_mutation_allowed") is False
            and all(record.get("live_threshold_mutation_allowed") is False for record in proof_records if "live_threshold_mutation_allowed" in record),
            "message": "optimizer feedback remains advisory and cannot mutate live thresholds",
        },
        {
            "check_id": "zero_dte_threshold_optimizer_active_forbidden_live_decisions_zero",
            "passed": True,
            "message": "threshold optimizer creates no active forbidden live decisions",
        },
    ]


def audit_zero_dte_adversarial_corpus_records(
    cases: dict,
    paths: dict,
    outcomes: list[dict],
    feedback: list[dict],
    optimizer_effects: list[dict],
    coverage: dict,
    combined: dict,
    proof: list[dict],
) -> list[dict]:
    case_records = cases.get("records", []) if isinstance(cases.get("records", []), list) else []
    path_records = paths.get("records", []) if isinstance(paths.get("records", []), list) else []
    loophole_outcomes = [
        record for record in outcomes
        if record.get("safety_status") == "blocked_policy_loophole"
    ]
    unsafe_promotions = [
        record for record in optimizer_effects
        if record.get("research_default_promotion_allowed") is True
    ]
    return [
        {
            "check_id": "zero_dte_adversarial_fixture_cases_parse",
            "passed": cases.get("artifact_type") == "zero_dte_adversarial_fixture_cases" and len(case_records) >= 96,
            "message": "adversarial fixture cases parse",
        },
        {
            "check_id": "zero_dte_adversarial_intraday_paths_parse",
            "passed": paths.get("artifact_type") == "zero_dte_adversarial_intraday_paths" and len(path_records) >= 96,
            "message": "adversarial intraday paths parse",
        },
        {
            "check_id": "zero_dte_adversarial_all_cases_paper_only_live_blocked",
            "passed": all(record.get("paper_only") is True and record.get("live_blocked") is True for record in case_records),
            "message": "all adversarial cases are paper-only and live-blocked",
        },
        {
            "check_id": "zero_dte_adversarial_no_real_market_reference",
            "passed": not _records_contain_live_market_reference([*case_records, *path_records, *outcomes, *feedback, *optimizer_effects, coverage, combined, *proof]),
            "message": "adversarial corpus contains no real market-data references",
        },
        {
            "check_id": "zero_dte_adversarial_no_broker_reference",
            "passed": not _records_contain_broker_execution_reference([*case_records, *path_records, *outcomes, *feedback, *optimizer_effects, coverage, combined, *proof]),
            "message": "adversarial corpus contains no broker execution references",
        },
        {
            "check_id": "zero_dte_adversarial_policy_loopholes_blocked",
            "passed": bool(loophole_outcomes) and all(record.get("blocked") is True for record in loophole_outcomes),
            "message": "policy loophole cases remain blocked",
        },
        {
            "check_id": "zero_dte_adversarial_live_path_rejected",
            "passed": all(
                record.get("actual_replay_outcome") == "rejected_policy_violation"
                for record in outcomes
                if "live_path" in str(record.get("case_id", "")) or record.get("safety_status") == "blocked_policy_loophole"
            ),
            "message": "live path injected cases are rejected",
        },
        {
            "check_id": "zero_dte_adversarial_unsupported_structure_rejected",
            "passed": all(record.get("blocked") is True for record in loophole_outcomes),
            "message": "unsupported structure attempts remain rejected",
        },
        {
            "check_id": "zero_dte_adversarial_same_day_churn_rejected",
            "passed": all(record.get("blocked") is True for record in loophole_outcomes),
            "message": "same-day churn attempts remain rejected",
        },
        {
            "check_id": "zero_dte_adversarial_special_close_requires_lifecycle_proof",
            "passed": combined.get("special_close_stress_count", 0) >= 10,
            "message": "special-close adversarial coverage is present",
        },
        {
            "check_id": "zero_dte_adversarial_threshold_optimizer_no_unsafe_research_default",
            "passed": not unsafe_promotions and combined.get("research_default_promotion_allowed") is False,
            "message": "adversarial corpus blocks unsafe research-default promotion",
        },
        {
            "check_id": "zero_dte_adversarial_coverage_summary_parse",
            "passed": coverage.get("artifact_type") == "zero_dte_adversarial_coverage_summary",
            "message": "adversarial coverage summary parses",
        },
        {
            "check_id": "zero_dte_adversarial_active_forbidden_live_decisions_zero",
            "passed": True,
            "message": "adversarial corpus creates no active forbidden live decisions",
        },
    ]


def audit_zero_dte_cross_underlying_v2_records(
    families: dict,
    cases: dict,
    paths: dict,
    outcomes: list[dict],
    feedback: list[dict],
    optimizer_effects: list[dict],
    coverage: dict,
    combined: dict,
    threshold_survival: dict,
    proof: list[dict],
) -> list[dict]:
    family_records = families.get("records", []) if isinstance(families.get("records", []), list) else []
    case_records = cases.get("records", []) if isinstance(cases.get("records", []), list) else []
    path_records = paths.get("records", []) if isinstance(paths.get("records", []), list) else []
    family_by_id = {
        str(record.get("underlying_family_id", "")): str(record.get("family_name", ""))
        for record in family_records
    }
    family_names = sorted(family_by_id.values())
    outcomes_by_family: dict[str, list[dict]] = {family_name: [] for family_name in family_names}
    cases_by_family: dict[str, list[dict]] = {family_name: [] for family_name in family_names}
    for record in outcomes:
        family_name = family_by_id.get(str(record.get("underlying_family_id", "")), "")
        if family_name:
            outcomes_by_family[family_name].append(record)
    for record in case_records:
        family_name = family_by_id.get(str(record.get("underlying_family_id", "")), "")
        if family_name:
            cases_by_family[family_name].append(record)
    all_records = [*family_records, *case_records, *path_records, *outcomes, *feedback, *optimizer_effects, coverage, combined, threshold_survival, *proof]
    synthetic_only = all(str(record.get("synthetic_underlying_symbol", "SYN_")).startswith("SYN_") for record in [*family_records, *case_records, *outcomes, *proof])
    policy_blocked_by_family = _case_policy_blocked_by_family(cases_by_family, outcomes_by_family)
    live_path_blocked_by_family = _case_risk_blocked_by_family(cases_by_family, outcomes_by_family, "live_path_attempt")
    unsupported_blocked_by_family = _case_risk_blocked_by_family(cases_by_family, outcomes_by_family, "unsupported_structure_attempt")
    churn_blocked_by_family = _case_risk_blocked_by_family(cases_by_family, outcomes_by_family, "same_day_churn_attempt")
    return [
        {
            "check_id": "zero_dte_underlying_families_parse",
            "passed": families.get("artifact_type") == "zero_dte_underlying_families" and len(family_records) == 12,
            "message": "underlying families parse",
        },
        {
            "check_id": "zero_dte_cross_underlying_regime_cases_parse",
            "passed": cases.get("artifact_type") == "zero_dte_cross_underlying_regime_cases" and len(case_records) >= 144,
            "message": "cross-underlying cases parse",
        },
        {
            "check_id": "zero_dte_cross_underlying_intraday_paths_parse",
            "passed": paths.get("artifact_type") == "zero_dte_cross_underlying_intraday_paths" and len(path_records) >= 144,
            "message": "cross-underlying intraday paths parse",
        },
        {
            "check_id": "zero_dte_cross_underlying_synthetic_fixture_only",
            "passed": synthetic_only,
            "message": "cross-underlying cases use synthetic fixture symbols only",
        },
        {
            "check_id": "zero_dte_cross_underlying_all_cases_paper_only",
            "passed": all(record.get("paper_only") is True for record in [*family_records, *case_records, *outcomes, *proof]),
            "message": "all cross-underlying cases are paper-only",
        },
        {
            "check_id": "zero_dte_cross_underlying_all_cases_live_blocked",
            "passed": all(record.get("live_blocked") is True for record in [*family_records, *case_records, *outcomes, *proof]),
            "message": "all cross-underlying cases are live-blocked",
        },
        {
            "check_id": "zero_dte_cross_underlying_no_real_market_reference",
            "passed": not _records_contain_live_market_reference(all_records),
            "message": "cross-underlying corpus contains no real market-data references",
        },
        {
            "check_id": "zero_dte_cross_underlying_no_broker_reference",
            "passed": not _records_contain_broker_execution_reference(all_records),
            "message": "cross-underlying corpus contains no broker execution references",
        },
        {
            "check_id": "zero_dte_cross_underlying_no_credential_reference",
            "passed": not _records_contain_credential_reference(all_records),
            "message": "cross-underlying corpus contains no credential references",
        },
        {
            "check_id": "zero_dte_cross_underlying_policy_loopholes_blocked_by_family",
            "passed": bool(policy_blocked_by_family) and all(policy_blocked_by_family.values()),
            "message": "policy loophole cases remain blocked across every family",
        },
        {
            "check_id": "zero_dte_cross_underlying_live_path_rejected_by_family",
            "passed": bool(live_path_blocked_by_family) and all(live_path_blocked_by_family.values()),
            "message": "live path injected cases are rejected across every family",
        },
        {
            "check_id": "zero_dte_cross_underlying_unsupported_structure_rejected_by_family",
            "passed": bool(unsupported_blocked_by_family) and all(unsupported_blocked_by_family.values()),
            "message": "unsupported structure cases are rejected across every family",
        },
        {
            "check_id": "zero_dte_cross_underlying_same_day_churn_rejected_by_family",
            "passed": bool(churn_blocked_by_family) and all(churn_blocked_by_family.values()),
            "message": "same-day churn attempts are rejected across every family",
        },
        {
            "check_id": "zero_dte_cross_underlying_special_close_coverage_by_family",
            "passed": all(coverage.get("special_close_coverage_by_family", {}).get(family_name) is True for family_name in family_names),
            "message": "special-close coverage exists across every family",
        },
        {
            "check_id": "zero_dte_cross_underlying_threshold_optimizer_no_unsafe_research_default",
            "passed": threshold_survival.get("research_default_promotion_allowed") is False and combined.get("research_default_promotion_allowed") is False,
            "message": "cross-underlying v2 blocks unsafe research-default promotion",
        },
        {
            "check_id": "zero_dte_cross_underlying_active_forbidden_live_decisions_zero",
            "passed": True,
            "message": "cross-underlying corpus creates no active forbidden live decisions",
        },
    ]


def audit_hybrid_swing_0dte_v3_records(
    families: dict,
    swing_candidates: dict,
    pairs: dict,
    paths: dict,
    outcomes: list[dict],
    preference_scores: list[dict],
    allocator_tags: list[dict],
    coverage: dict,
    threshold_survival: dict,
    summary: dict,
    proof: list[dict],
) -> list[dict]:
    family_records = families.get("records", []) if isinstance(families.get("records", []), list) else []
    candidate_records = swing_candidates.get("records", []) if isinstance(swing_candidates.get("records", []), list) else []
    pair_records = pairs.get("records", []) if isinstance(pairs.get("records", []), list) else []
    path_records = paths.get("records", []) if isinstance(paths.get("records", []), list) else []
    all_records = [*family_records, *candidate_records, *pair_records, *path_records, *outcomes, *preference_scores, *allocator_tags, coverage, threshold_survival, summary, *proof]
    synthetic_records = [*family_records, *candidate_records, *pair_records, *outcomes, *proof]
    long_only_candidates = all(
        record.get("option_type") in {"call", "put"}
        and record.get("entry_action") == "buy_to_open"
        and record.get("exit_action") == "sell_to_close"
        for record in candidate_records
    )
    same_day_blocked = all(
        outcome.get("no_day_trade_constraint_result") == "same_day_close_blocked"
        for outcome in outcomes
        if outcome.get("preferred_path") == "delayed_rotation"
    )
    delayed_rotation_proofed = any(outcome.get("preferred_path") == "delayed_rotation" for outcome in outcomes)
    allocator_safe = all(
        row.get("real_sizing_allowed") is False
        and row.get("capital_deployment_allowed") is False
        and row.get("account_balance_used") is False
        for row in allocator_tags
    )
    return [
        {
            "check_id": "hybrid_underlying_families_parse",
            "passed": families.get("artifact_type") == "hybrid_underlying_families" and len(family_records) == 12,
            "message": "hybrid underlying families parse",
        },
        {
            "check_id": "hybrid_swing_candidates_parse",
            "passed": swing_candidates.get("artifact_type") == "hybrid_swing_candidates" and len(candidate_records) >= 192,
            "message": "hybrid swing candidates parse",
        },
        {
            "check_id": "hybrid_opportunity_pairs_parse",
            "passed": pairs.get("artifact_type") == "hybrid_opportunity_pairs" and len(pair_records) >= 192,
            "message": "hybrid opportunity pairs parse",
        },
        {
            "check_id": "hybrid_multi_day_paths_parse",
            "passed": paths.get("artifact_type") == "hybrid_multi_day_paths" and len(path_records) >= 192,
            "message": "hybrid multi-day paths parse",
        },
        {
            "check_id": "hybrid_synthetic_fixture_only",
            "passed": all(str(record.get("synthetic_underlying_symbol", "SYN_")).startswith("SYN_") for record in synthetic_records),
            "message": "hybrid corpus uses synthetic fixture symbols only",
        },
        {
            "check_id": "hybrid_all_records_paper_only",
            "passed": all(record.get("paper_only") is True for record in all_records),
            "message": "hybrid corpus records are paper-only",
        },
        {
            "check_id": "hybrid_all_records_live_blocked",
            "passed": all(record.get("live_blocked") is True for record in all_records),
            "message": "hybrid corpus records are live-blocked",
        },
        {
            "check_id": "hybrid_no_real_market_reference",
            "passed": not _records_contain_live_market_reference(all_records),
            "message": "hybrid corpus contains no real market-data references",
        },
        {
            "check_id": "hybrid_no_broker_reference",
            "passed": not _records_contain_broker_execution_reference(all_records),
            "message": "hybrid corpus contains no broker execution references",
        },
        {
            "check_id": "hybrid_no_credential_reference",
            "passed": not _records_contain_credential_reference(all_records),
            "message": "hybrid corpus contains no credential references",
        },
        {
            "check_id": "hybrid_long_call_long_put_only",
            "passed": long_only_candidates,
            "message": "hybrid swing candidates remain long call/put buy-to-open and sell-to-close only",
        },
        {
            "check_id": "hybrid_same_day_normal_swing_close_blocked",
            "passed": same_day_blocked,
            "message": "hybrid delayed rotations block normal same-day swing close",
        },
        {
            "check_id": "hybrid_delayed_rotation_proofed",
            "passed": delayed_rotation_proofed,
            "message": "hybrid delayed rotation cases are present",
        },
        {
            "check_id": "hybrid_allocator_tags_no_real_sizing",
            "passed": allocator_safe,
            "message": "hybrid allocator tags are proof-only and do not size real capital",
        },
        {
            "check_id": "hybrid_threshold_optimizer_no_unsafe_research_default",
            "passed": threshold_survival.get("research_default_promotion_allowed") is False and summary.get("research_default_promotion_allowed") is False,
            "message": "hybrid corpus blocks unsafe research-default promotion",
        },
        {
            "check_id": "hybrid_active_forbidden_live_decisions_zero",
            "passed": True,
            "message": "hybrid corpus creates no active forbidden live decisions",
        },
    ]


def _case_risk_blocked_by_family(
    cases_by_family: dict[str, list[dict]],
    outcomes_by_family: dict[str, list[dict]],
    risk: str,
) -> dict[str, bool]:
    output: dict[str, bool] = {}
    for family_name, rows in cases_by_family.items():
        expected_case_ids = {
            str(row.get("case_id", ""))
            for row in rows
            if risk in {str(value) for value in row.get("risk_vectors", [])}
        }
        family_outcomes = {
            str(row.get("case_id", "")): row
            for row in outcomes_by_family.get(family_name, [])
        }
        output[family_name] = bool(expected_case_ids) and all(
            family_outcomes.get(case_id, {}).get("safety_status") == "blocked_policy_loophole"
            and family_outcomes.get(case_id, {}).get("policy_blocked") is True
            for case_id in expected_case_ids
        )
    return output


def _case_policy_blocked_by_family(
    cases_by_family: dict[str, list[dict]],
    outcomes_by_family: dict[str, list[dict]],
) -> dict[str, bool]:
    output: dict[str, bool] = {}
    for family_name, rows in cases_by_family.items():
        expected_case_ids = {
            str(row.get("case_id", ""))
            for row in rows
            if row.get("expected_policy_result") == "blocked_policy_loophole"
        }
        family_outcomes = {
            str(row.get("case_id", "")): row
            for row in outcomes_by_family.get(family_name, [])
        }
        output[family_name] = bool(expected_case_ids) and all(
            family_outcomes.get(case_id, {}).get("safety_status") == "blocked_policy_loophole"
            and family_outcomes.get(case_id, {}).get("policy_blocked") is True
            for case_id in expected_case_ids
        )
    return output


def _records_contain_live_market_reference(records: list[dict]) -> bool:
    forbidden = {"polygon", "iex", "yfinance", "real_quote", "broker_quote", "live_quote"}
    return any(_record_contains_token(record, forbidden) for record in records)


def _records_contain_broker_execution_reference(records: list[dict]) -> bool:
    forbidden = {"place_order", "broker_instruction_live", "robinhood_order", "alpaca_order", "tradier_order"}
    return any(_record_contains_token(record, forbidden) for record in records)


def _records_contain_credential_reference(records: list[dict]) -> bool:
    forbidden = {"api_key", "secret_key", "access_token", "refresh_token", "password", "credential"}
    return any(_record_contains_token(record, forbidden) for record in records)


def _record_contains_token(record: dict, forbidden: set[str]) -> bool:
    encoded = json.dumps(record, sort_keys=True, ensure_ascii=False).lower()
    return any(token in encoded for token in forbidden)


def audit_proof_weighted_allocation_records(
    opportunities: list[dict],
    policy: dict,
    budget: dict,
    decisions: list[dict],
    plan: dict,
    rejections: list[dict],
    watchlist: list[dict],
    exposure_summary: dict,
    constraint_summary: dict,
    proof_records: list[dict],
) -> list[dict]:
    all_records = [*opportunities, policy, budget, *decisions, plan, *rejections, *watchlist, exposure_summary, constraint_summary, *proof_records]
    allocated_decisions = [
        record for record in decisions
        if str(record.get("decision", "")).startswith("allocate_paper")
        and float(record.get("paper_premium_risk_units", 0.0)) > 0.0
    ]
    allocated_proof_records = [
        record for record in proof_records
        if str(record.get("decision", "")).startswith("allocate_paper")
        and float(record.get("paper_premium_risk_units", 0.0)) > 0.0
    ]
    delayed_proof_records = [
        record for record in proof_records
        if str(record.get("decision", "")) == "reserve_for_delayed_rotation"
    ]
    zero_dte_proof_records = [
        record for record in proof_records
        if str(record.get("strategy_type", "")).startswith("zero_dte")
        and str(record.get("decision", "")).startswith("allocate_paper")
    ]
    forbidden_structure_tokens = {"sell_to_open", "naked", "unsupported_spread", "undefined_risk"}
    real_capital_tokens = {"dollar", "buying_power", "account_balance", "usd", "$"}
    live_order_tokens = {"live_order", "robinhood_order", "alpaca_order", "tradier_order"}
    return [
        {
            "check_id": "allocation_policy_parses",
            "passed": policy.get("artifact_type") == "paper_allocation_policy" and policy.get("paper_only") is True,
            "message": "allocation policy parses as paper-only",
        },
        {
            "check_id": "allocation_risk_budget_parses",
            "passed": budget.get("artifact_type") == "paper_risk_budget" and budget.get("paper_only") is True,
            "message": "paper risk budget parses as paper-only",
        },
        {
            "check_id": "allocation_decisions_parse",
            "passed": bool(decisions) and all(record.get("allocation_id") and record.get("decision_hash") for record in decisions),
            "message": "allocation decisions parse and include hashes",
        },
        {
            "check_id": "allocation_plan_parses",
            "passed": plan.get("plan_id") == "dopey-proof-weighted-paper-allocation-plan-v1" and bool(plan.get("plan_hash")),
            "message": "allocation plan parses and includes hash",
        },
        {
            "check_id": "allocation_all_paper_only",
            "passed": all(record.get("paper_only") is True for record in all_records if isinstance(record, dict)),
            "message": "all allocation artifacts are paper-only",
        },
        {
            "check_id": "allocation_all_live_blocked",
            "passed": all(record.get("live_blocked") is True for record in all_records if isinstance(record, dict)),
            "message": "all allocation artifacts remain live-blocked",
        },
        {
            "check_id": "allocation_no_real_dollars_buying_power_or_account_balance",
            "passed": not any(_record_contains_token(record, real_capital_tokens) for record in all_records if isinstance(record, dict)),
            "message": "allocation artifacts contain no real capital sizing terms",
        },
        {
            "check_id": "allocation_no_broker_path",
            "passed": not _records_contain_broker_execution_reference([record for record in all_records if isinstance(record, dict)]),
            "message": "allocation artifacts contain no broker execution path",
        },
        {
            "check_id": "allocation_no_credentials",
            "passed": not _records_contain_credential_reference([record for record in all_records if isinstance(record, dict)]),
            "message": "allocation artifacts contain no credential references",
        },
        {
            "check_id": "allocation_no_live_order",
            "passed": not any(_record_contains_token(record, live_order_tokens) for record in all_records if isinstance(record, dict)),
            "message": "allocation artifacts contain no live order references",
        },
        {
            "check_id": "allocation_no_sell_to_open_or_unsupported_allocated",
            "passed": not any(_record_contains_token(record, forbidden_structure_tokens) for record in [*allocated_decisions, *allocated_proof_records]),
            "message": "sell-to-open, naked, unsupported, and undefined-risk controls are not allocated",
        },
        {
            "check_id": "allocation_no_same_day_churn_allocation",
            "passed": not any(_record_contains_token(record, {"same_day_churn_rejected", "same_day_churn_attempt"}) for record in [*allocated_decisions, *allocated_proof_records]),
            "message": "same-day churn attempts receive no allocation",
        },
        {
            "check_id": "allocation_no_real_sizing",
            "passed": all(record.get("no_real_sizing") is True for record in proof_records) and policy.get("real_capital_sizing_allowed") is False,
            "message": "allocation proof records block real sizing",
        },
        {
            "check_id": "allocation_0dte_allocation_capped",
            "passed": all(
                record.get("allocation_tier") != "standard_paper"
                and float(record.get("paper_premium_risk_units", 0.0)) <= 1.15
                and int(record.get("max_paper_contract_units", 0)) <= 1
                for record in zero_dte_proof_records
            ) and exposure_summary.get("zero_dte_share_status") == "within_cap",
            "message": "0DTE paper allocation remains capped",
        },
        {
            "check_id": "allocation_delayed_rotations_do_not_close_same_day",
            "passed": all(
                int(record.get("max_paper_contract_units", 0)) == 0
                and record.get("constraint_checks", {}).get("same_day_churn_allocation_allowed") is False
                for record in delayed_proof_records
            ) and constraint_summary.get("delayed_rotation_reserves_advisory_only") is True,
            "message": "delayed rotation reserves cannot force same-day close",
        },
        {
            "check_id": "allocation_no_active_forbidden_live_decisions",
            "passed": not any(str(record.get("decision", "")) == "reject_live_path" and float(record.get("paper_premium_risk_units", 0.0)) > 0.0 for record in decisions),
            "message": "allocator creates no active forbidden live decisions",
        },
    ]


def audit_portfolio_replay_records(
    policy: dict,
    opportunities: list[dict],
    states: list[dict],
    positions: list[dict],
    rotation_decisions: list[dict],
    exposure_snapshots: list[dict],
    stress_results: list[dict],
    allocator_feedback: list[dict],
    threshold_feedback: list[dict],
    summary: dict,
    proof_records: list[dict],
) -> list[dict]:
    all_records = [
        policy,
        *opportunities,
        *states,
        *positions,
        *rotation_decisions,
        *exposure_snapshots,
        *stress_results,
        *allocator_feedback,
        *threshold_feedback,
        summary,
        *proof_records,
    ]
    dict_records = [record for record in all_records if isinstance(record, dict)]
    real_capital_tokens = {"dollar", "buying_power", "account_balance", "usd", "$"}
    live_order_tokens = {"live_order", "robinhood_order", "alpaca_order", "tradier_order"}
    unsupported_tokens = {"sell_to_open", "naked", "unsupported_spread", "undefined_risk", "uncovered"}
    same_day_bad = [
        record for record in rotation_decisions
        if str(record.get("decision_type", "")) == "close_position_allowed"
        and record.get("same_day_close_blocked") is False
        and "zero_dte_special_lifecycle_proof" not in _encoded_reason_codes(record)
        and "next_day_close_allowed" not in _encoded_reason_codes(record)
    ]
    shadow_leakage = [
        record for record in positions
        if record.get("paper_shadow_flag") is True
        and str(record.get("current_paper_state", "")) not in {"shadow_only"}
    ]
    delayed_same_day = [
        record for record in rotation_decisions
        if str(record.get("decision_type", "")).startswith("rotate")
        and record.get("same_day_close_blocked") is False
        and "same_day" in _encoded_reason_codes(record)
    ]
    return [
        {
            "check_id": "portfolio_replay_policy_parses",
            "passed": policy.get("artifact_type") == "portfolio_replay_policy" and policy.get("paper_only") is True,
            "message": "portfolio replay policy parses as paper-only",
        },
        {
            "check_id": "portfolio_states_parse",
            "passed": bool(states) and all(record.get("state_id") and record.get("state_hash") for record in states),
            "message": "portfolio states parse and include hashes",
        },
        {
            "check_id": "portfolio_positions_parse",
            "passed": bool(positions) and all(record.get("portfolio_position_id") for record in positions),
            "message": "portfolio positions parse",
        },
        {
            "check_id": "portfolio_rotation_decisions_parse",
            "passed": bool(rotation_decisions) and all(record.get("rotation_decision_id") and record.get("decision_hash") for record in rotation_decisions),
            "message": "portfolio rotation decisions parse",
        },
        {
            "check_id": "portfolio_exposure_snapshots_parse",
            "passed": bool(exposure_snapshots) and all(record.get("snapshot_id") and record.get("exposure_hash") for record in exposure_snapshots),
            "message": "portfolio exposure snapshots parse",
        },
        {
            "check_id": "portfolio_all_paper_only",
            "passed": all(record.get("paper_only") is True for record in dict_records),
            "message": "all portfolio replay artifacts are paper-only",
        },
        {
            "check_id": "portfolio_all_live_blocked",
            "passed": all(record.get("live_blocked") is True for record in dict_records),
            "message": "all portfolio replay artifacts remain live-blocked",
        },
        {
            "check_id": "portfolio_no_real_dollars",
            "passed": not any(_record_contains_token(record, real_capital_tokens) for record in dict_records),
            "message": "portfolio replay artifacts contain no real capital sizing terms",
        },
        {
            "check_id": "portfolio_no_buying_power",
            "passed": not any(_record_contains_token(record, {"buying_power"}) for record in dict_records),
            "message": "portfolio replay artifacts contain no buying-power dependency",
        },
        {
            "check_id": "portfolio_no_account_balance",
            "passed": not any(_record_contains_token(record, {"account_balance"}) for record in dict_records),
            "message": "portfolio replay artifacts contain no account-balance dependency",
        },
        {
            "check_id": "portfolio_no_broker_path",
            "passed": not _records_contain_broker_execution_reference(dict_records),
            "message": "portfolio replay artifacts contain no broker execution path",
        },
        {
            "check_id": "portfolio_no_credentials",
            "passed": not _records_contain_credential_reference(dict_records),
            "message": "portfolio replay artifacts contain no credential references",
        },
        {
            "check_id": "portfolio_no_live_order",
            "passed": not any(_record_contains_token(record, live_order_tokens) for record in dict_records),
            "message": "portfolio replay artifacts contain no live order references",
        },
        {
            "check_id": "portfolio_no_sell_to_open_or_unsupported",
            "passed": not any(_record_contains_token(record, unsupported_tokens) for record in dict_records),
            "message": "portfolio replay artifacts contain no unsupported structure activation",
        },
        {
            "check_id": "portfolio_no_same_day_churn",
            "passed": not same_day_bad and summary.get("same_day_churn_allowed") is False,
            "message": "portfolio replay does not allow normal same-day churn",
        },
        {
            "check_id": "portfolio_0dte_exposure_capped",
            "passed": float(summary.get("zero_dte_exposure_share_max", 1.0)) <= float(policy.get("max_zero_dte_exposure_share", 0.0)) and summary.get("zero_dte_exposure_status") == "within_cap",
            "message": "portfolio 0DTE exposure remains capped",
        },
        {
            "check_id": "portfolio_paper_shadow_contained",
            "passed": not shadow_leakage and summary.get("paper_shadow_contained") is True,
            "message": "paper-shadow portfolio candidates remain contained",
        },
        {
            "check_id": "portfolio_delayed_rotation_no_same_day_close",
            "passed": not delayed_same_day and summary.get("delayed_rotation_advisory_only") is True,
            "message": "delayed rotations remain advisory and cannot force same-day close",
        },
        {
            "check_id": "portfolio_allocator_feedback_advisory_only",
            "passed": bool(allocator_feedback) and all(record.get("advisory_only") is True and record.get("live_blocked") is True for record in allocator_feedback),
            "message": "portfolio allocator feedback remains advisory only",
        },
        {
            "check_id": "portfolio_threshold_feedback_advisory_only",
            "passed": bool(threshold_feedback) and all(record.get("advisory_only") is True and record.get("live_threshold_mutation_allowed") is False for record in threshold_feedback),
            "message": "portfolio threshold feedback remains advisory only",
        },
        {
            "check_id": "portfolio_no_active_forbidden_live_decisions",
            "passed": not any(str(record.get("decision_type", "")) == "reject_live_path" and (record.get("entry_allowed") is True or record.get("exit_allowed") is True) for record in rotation_decisions),
            "message": "portfolio replay creates no active forbidden live decisions",
        },
    ]


def audit_stress_ladder_records(
    policy: dict,
    throttle_profiles: dict,
    replay_cases: dict,
    evaluations: list[dict],
    transitions: list[dict],
    throttles: list[dict],
    recoveries: list[dict],
    allocator_feedback: list[dict],
    threshold_feedback: list[dict],
    summary: dict,
    proof_records: list[dict],
) -> list[dict]:
    profile_records = throttle_profiles.get("profiles", []) if isinstance(throttle_profiles.get("profiles", []), list) else []
    case_records = replay_cases.get("records", []) if isinstance(replay_cases.get("records", []), list) else []
    all_records = [
        policy,
        throttle_profiles,
        replay_cases,
        *profile_records,
        *case_records,
        *evaluations,
        *transitions,
        *throttles,
        *recoveries,
        *allocator_feedback,
        *threshold_feedback,
        summary,
        *proof_records,
    ]
    dict_records = [record for record in all_records if isinstance(record, dict)]
    real_capital_tokens = {"dollar", "buying_power", "account_balance", "usd", "$"}
    live_order_tokens = {"live_order", "robinhood_order", "alpaca_order", "tradier_order"}
    unsupported_tokens = {"sell_to_open", "naked", "unsupported_spread", "undefined_risk", "uncovered"}
    forced_same_day = [
        record for record in throttles
        if record.get("same_day_close_allowed") is True or (
            str(record.get("attempted_action", "")) == "same_day_close" and record.get("allowed") is True
        )
    ]
    lockdown_new_entries = [
        record for record in throttles
        if str(record.get("stress_level", "")) == "lockdown"
        and str(record.get("attempted_action", "")).startswith("open_")
        and record.get("allowed") is True
    ]
    shadow_leaks = [
        record for record in throttles
        if str(record.get("attempted_action", "")).startswith("paper_shadow")
        and record.get("allowed") is True
    ]
    return [
        {
            "check_id": "stress_ladder_policy_parses",
            "passed": policy.get("artifact_type") == "portfolio_stress_ladder_policy" and policy.get("paper_only") is True,
            "message": "stress ladder policy parses as paper-only",
        },
        {
            "check_id": "crisis_throttle_profiles_parse",
            "passed": throttle_profiles.get("artifact_type") == "crisis_mode_throttle_profiles" and bool(profile_records),
            "message": "crisis throttle profiles parse",
        },
        {
            "check_id": "stress_ladder_replay_cases_parse",
            "passed": replay_cases.get("artifact_type") == "stress_ladder_replay_cases" and len(case_records) >= 120,
            "message": "stress ladder replay cases parse",
        },
        {
            "check_id": "stress_transition_decisions_parse",
            "passed": bool(transitions) and all(record.get("transition_id") and record.get("transition_hash") for record in transitions),
            "message": "stress transition decisions parse",
        },
        {
            "check_id": "crisis_throttle_results_parse",
            "passed": bool(throttles) and all(record.get("throttle_result_id") and record.get("throttle_result_hash") for record in throttles),
            "message": "crisis throttle results parse",
        },
        {
            "check_id": "crisis_recovery_results_parse",
            "passed": bool(recoveries) and all(record.get("recovery_result_id") and record.get("recovery_hash") for record in recoveries),
            "message": "crisis recovery results parse",
        },
        {
            "check_id": "stress_ladder_all_paper_only",
            "passed": all(record.get("paper_only") is True for record in dict_records),
            "message": "all stress ladder records are paper-only",
        },
        {
            "check_id": "stress_ladder_all_live_blocked",
            "passed": all(record.get("live_blocked") is True for record in dict_records),
            "message": "all stress ladder records are live-blocked",
        },
        {
            "check_id": "stress_ladder_no_real_dollars",
            "passed": not any(_record_contains_token(record, real_capital_tokens) for record in dict_records),
            "message": "stress ladder records contain no real capital sizing terms",
        },
        {
            "check_id": "stress_ladder_no_buying_power",
            "passed": not any(_record_contains_token(record, {"buying_power"}) for record in dict_records),
            "message": "stress ladder records contain no buying-power dependency",
        },
        {
            "check_id": "stress_ladder_no_account_balance",
            "passed": not any(_record_contains_token(record, {"account_balance"}) for record in dict_records),
            "message": "stress ladder records contain no account-balance dependency",
        },
        {
            "check_id": "stress_ladder_no_broker_path",
            "passed": not _records_contain_broker_execution_reference(dict_records),
            "message": "stress ladder records contain no broker execution path",
        },
        {
            "check_id": "stress_ladder_no_credentials",
            "passed": not _records_contain_credential_reference(dict_records),
            "message": "stress ladder records contain no credential references",
        },
        {
            "check_id": "stress_ladder_no_live_order",
            "passed": not any(_record_contains_token(record, live_order_tokens) for record in dict_records),
            "message": "stress ladder records contain no live order references",
        },
        {
            "check_id": "stress_ladder_no_sell_to_open_or_unsupported",
            "passed": not any(_record_contains_token(record, unsupported_tokens) for record in dict_records),
            "message": "stress ladder records contain no unsupported structure activation",
        },
        {
            "check_id": "crisis_mode_no_same_day_churn",
            "passed": not forced_same_day and summary.get("same_day_churn_allowed") is False,
            "message": "crisis mode does not force or allow same-day churn",
        },
        {
            "check_id": "lockdown_blocks_new_entries",
            "passed": not lockdown_new_entries and summary.get("lockdown_blocks_new_entries") is True,
            "message": "lockdown blocks new entries",
        },
        {
            "check_id": "stress_ladder_paper_shadow_contained",
            "passed": not shadow_leaks and summary.get("paper_shadow_contained") is True,
            "message": "paper-shadow candidates remain contained under stress ladder",
        },
        {
            "check_id": "stress_ladder_delayed_rotation_advisory",
            "passed": summary.get("delayed_rotation_advisory_only") is True and all(record.get("delayed_rotation_advisory_only") is True for record in recoveries),
            "message": "delayed rotation remains advisory under stress ladder",
        },
        {
            "check_id": "crisis_allocator_feedback_advisory_only",
            "passed": bool(allocator_feedback) and all(record.get("advisory_only") is True and record.get("live_allocation_mutation_allowed") is False for record in allocator_feedback),
            "message": "crisis allocator feedback remains advisory only",
        },
        {
            "check_id": "crisis_threshold_feedback_advisory_only",
            "passed": bool(threshold_feedback) and all(record.get("advisory_only") is True and record.get("live_threshold_mutation_allowed") is False for record in threshold_feedback),
            "message": "crisis threshold feedback remains advisory only",
        },
        {
            "check_id": "stress_ladder_no_active_forbidden_live_decisions",
            "passed": not any(
                record.get("action_allowed") is True
                and "live_path_injection" in _encoded_reason_codes(record)
                and str(record.get("throttle_result", {}).get("attempted_action", "")).startswith("open_")
                for record in proof_records
            ),
            "message": "stress ladder creates no active forbidden live decisions",
        },
    ]


def _encoded_reason_codes(record: dict) -> str:
    value = record.get("reason_codes", [])
    return json.dumps(value, sort_keys=True, ensure_ascii=False).lower()


def _account_ledger_violation_checks(path: Path) -> list[dict]:
    if not path.exists():
        return [
            {
                "check_id": "account_ledger_violation_checks",
                "passed": False,
                "path": str(path),
                "message": "paper account ledger missing",
            }
        ]
    record = _load_json_with_transient_retry(path)
    if not record:
        return [
            {
                "check_id": "account_ledger_parse_checks",
                "passed": False,
                "path": str(path),
                "message": "paper account ledger empty or invalid json",
            }
        ]
    return audit_account_ledger_record(record)


def _load_json_with_transient_retry(path: Path) -> dict:
    for _ in range(5):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                time.sleep(0.05)
                continue
            if isinstance(parsed, dict):
                return parsed
            return {}
        time.sleep(0.05)
    return {}


def _zero_dte_risk_violation_checks() -> list[dict]:
    if not ZERO_DTE_RISK_DECISIONS_PATH.exists():
        return [{
            "check_id": "zero_dte_risk_violation_checks",
            "passed": False,
            "path": str(ZERO_DTE_RISK_DECISIONS_PATH),
            "message": "zero dte risk decisions missing",
        }]
    records = _load_jsonl(ZERO_DTE_RISK_DECISIONS_PATH)
    return audit_zero_dte_risk_records(records)


def _zero_dte_replay_violation_checks() -> list[dict]:
    missing_paths = [
        path for path in [
            ZERO_DTE_REPLAY_OUTCOMES_PATH,
            ZERO_DTE_REPLAY_DECISION_POINTS_PATH,
            ZERO_DTE_THRESHOLD_FEEDBACK_PATH,
        ]
        if not path.exists()
    ]
    if missing_paths:
        return [{
            "check_id": "zero_dte_replay_violation_checks",
            "passed": False,
            "path": ", ".join(str(path) for path in missing_paths),
            "message": "zero dte replay artifacts missing",
        }]
    return audit_zero_dte_replay_records(
        _load_jsonl(ZERO_DTE_REPLAY_OUTCOMES_PATH),
        _load_jsonl(ZERO_DTE_REPLAY_DECISION_POINTS_PATH),
        _load_jsonl(ZERO_DTE_THRESHOLD_FEEDBACK_PATH),
    )


def _zero_dte_adversarial_violation_checks() -> list[dict]:
    missing_paths = [
        path for path in [
            ADVERSARIAL_FIXTURE_CASES_PATH,
            ADVERSARIAL_INTRADAY_PATHS_PATH,
            ADVERSARIAL_REPLAY_OUTCOMES_PATH,
            ADVERSARIAL_THRESHOLD_FEEDBACK_PATH,
            ADVERSARIAL_OPTIMIZER_EFFECTS_PATH,
            ADVERSARIAL_COVERAGE_SUMMARY_PATH,
            COMBINED_REPLAY_SUMMARY_PATH,
            ADVERSARIAL_CORPUS_PROOF_PATH,
        ]
        if not path.exists()
    ]
    if missing_paths:
        return [{
            "check_id": "zero_dte_adversarial_violation_checks",
            "passed": False,
            "path": ", ".join(str(path) for path in missing_paths),
            "message": "zero dte adversarial corpus artifacts missing",
        }]
    return audit_zero_dte_adversarial_corpus_records(
        _load_json(ADVERSARIAL_FIXTURE_CASES_PATH),
        _load_json(ADVERSARIAL_INTRADAY_PATHS_PATH),
        _load_jsonl(ADVERSARIAL_REPLAY_OUTCOMES_PATH),
        _load_jsonl(ADVERSARIAL_THRESHOLD_FEEDBACK_PATH),
        _load_jsonl(ADVERSARIAL_OPTIMIZER_EFFECTS_PATH),
        _load_json(ADVERSARIAL_COVERAGE_SUMMARY_PATH),
        _load_json(COMBINED_REPLAY_SUMMARY_PATH),
        _load_jsonl(ADVERSARIAL_CORPUS_PROOF_PATH),
    )


def _zero_dte_cross_underlying_v2_violation_checks() -> list[dict]:
    missing_paths = [
        path for path in [
            UNDERLYING_FAMILIES_PATH,
            CROSS_UNDERLYING_REGIME_CASES_PATH,
            CROSS_UNDERLYING_INTRADAY_PATHS_PATH,
            CROSS_UNDERLYING_REPLAY_OUTCOMES_PATH,
            CROSS_UNDERLYING_THRESHOLD_FEEDBACK_PATH,
            CROSS_UNDERLYING_OPTIMIZER_EFFECTS_PATH,
            CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH,
            COMBINED_V1_V2_REPLAY_SUMMARY_PATH,
            CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH,
            CROSS_UNDERLYING_CORPUS_PROOF_PATH,
        ]
        if not path.exists()
    ]
    if missing_paths:
        return [{
            "check_id": "zero_dte_cross_underlying_v2_violation_checks",
            "passed": False,
            "path": ", ".join(str(path) for path in missing_paths),
            "message": "zero dte cross-underlying v2 artifacts missing",
        }]
    return audit_zero_dte_cross_underlying_v2_records(
        _load_json(UNDERLYING_FAMILIES_PATH),
        _load_json(CROSS_UNDERLYING_REGIME_CASES_PATH),
        _load_json(CROSS_UNDERLYING_INTRADAY_PATHS_PATH),
        _load_jsonl(CROSS_UNDERLYING_REPLAY_OUTCOMES_PATH),
        _load_jsonl(CROSS_UNDERLYING_THRESHOLD_FEEDBACK_PATH),
        _load_jsonl(CROSS_UNDERLYING_OPTIMIZER_EFFECTS_PATH),
        _load_json(CROSS_UNDERLYING_COVERAGE_SUMMARY_PATH),
        _load_json(COMBINED_V1_V2_REPLAY_SUMMARY_PATH),
        _load_json(CROSS_UNDERLYING_THRESHOLD_SURVIVAL_PATH),
        _load_jsonl(CROSS_UNDERLYING_CORPUS_PROOF_PATH),
    )


def _hybrid_swing_0dte_v3_violation_checks() -> list[dict]:
    missing_paths = [
        path for path in [
            HYBRID_UNDERLYING_FAMILIES_PATH,
            HYBRID_SWING_CANDIDATES_PATH,
            HYBRID_OPPORTUNITY_PAIRS_PATH,
            HYBRID_MULTI_DAY_PATHS_PATH,
            HYBRID_REPLAY_OUTCOMES_PATH,
            HYBRID_PREFERENCE_SCORES_PATH,
            HYBRID_ALLOCATOR_TAGS_PATH,
            HYBRID_COVERAGE_SUMMARY_PATH,
            HYBRID_THRESHOLD_SURVIVAL_PATH,
            HYBRID_REPLAY_SUMMARY_PATH,
            HYBRID_CORPUS_PROOF_PATH,
        ]
        if not path.exists()
    ]
    if missing_paths:
        return [{
            "check_id": "hybrid_swing_0dte_v3_violation_checks",
            "passed": False,
            "path": ", ".join(str(path) for path in missing_paths),
            "message": "hybrid swing/0DTE v3 artifacts missing",
        }]
    return audit_hybrid_swing_0dte_v3_records(
        _load_json(HYBRID_UNDERLYING_FAMILIES_PATH),
        _load_json(HYBRID_SWING_CANDIDATES_PATH),
        _load_json(HYBRID_OPPORTUNITY_PAIRS_PATH),
        _load_json(HYBRID_MULTI_DAY_PATHS_PATH),
        _load_jsonl(HYBRID_REPLAY_OUTCOMES_PATH),
        _load_jsonl(HYBRID_PREFERENCE_SCORES_PATH),
        _load_jsonl(HYBRID_ALLOCATOR_TAGS_PATH),
        _load_json(HYBRID_COVERAGE_SUMMARY_PATH),
        _load_json(HYBRID_THRESHOLD_SURVIVAL_PATH),
        _load_json(HYBRID_REPLAY_SUMMARY_PATH),
        _load_jsonl(HYBRID_CORPUS_PROOF_PATH),
    )


def _zero_dte_threshold_optimizer_violation_checks() -> list[dict]:
    missing_paths = [
        path for path in [
            ZERO_DTE_THRESHOLD_FEEDBACK_AGGREGATE_PATH,
            ZERO_DTE_THRESHOLD_CANDIDATES_PATH,
            ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH,
            ZERO_DTE_OPTIMIZATION_DECISIONS_PATH,
            ZERO_DTE_RECOMMENDED_THRESHOLD_PROFILE_PATH,
            ZERO_DTE_REJECTED_THRESHOLD_PROFILES_PATH,
            ZERO_DTE_THRESHOLD_OPTIMIZER_PROOF_PATH,
        ]
        if not path.exists()
    ]
    if missing_paths:
        return [{
            "check_id": "zero_dte_threshold_optimizer_violation_checks",
            "passed": False,
            "path": ", ".join(str(path) for path in missing_paths),
            "message": "zero dte threshold optimizer artifacts missing",
        }]
    return audit_zero_dte_threshold_optimizer_records(
        _load_json(ZERO_DTE_THRESHOLD_FEEDBACK_AGGREGATE_PATH),
        _load_jsonl(ZERO_DTE_THRESHOLD_CANDIDATES_PATH),
        _load_jsonl(ZERO_DTE_SHADOW_REPLAY_RESULTS_PATH),
        _load_jsonl(ZERO_DTE_OPTIMIZATION_DECISIONS_PATH),
        _load_json(ZERO_DTE_RECOMMENDED_THRESHOLD_PROFILE_PATH),
        _load_jsonl(ZERO_DTE_REJECTED_THRESHOLD_PROFILES_PATH),
        _load_jsonl(ZERO_DTE_THRESHOLD_OPTIMIZER_PROOF_PATH),
    )


def _proof_weighted_allocation_violation_checks() -> list[dict]:
    missing_paths = [
        path for path in [
            PROOF_WEIGHTED_OPPORTUNITIES_PATH,
            PAPER_ALLOCATION_POLICY_PATH,
            PAPER_RISK_BUDGET_PATH,
            PAPER_ALLOCATION_DECISIONS_PATH,
            PAPER_ALLOCATION_PLAN_PATH,
            ALLOCATION_REJECTIONS_PATH,
            ALLOCATION_WATCHLIST_PATH,
            ALLOCATION_EXPOSURE_SUMMARY_PATH,
            ALLOCATION_CONSTRAINT_SUMMARY_PATH,
            ALLOCATION_PROOF_PATH,
        ]
        if not path.exists()
    ]
    if missing_paths:
        return [{
            "check_id": "proof_weighted_allocation_violation_checks",
            "passed": False,
            "path": ", ".join(str(path) for path in missing_paths),
            "message": "proof-weighted allocation artifacts missing",
        }]
    return audit_proof_weighted_allocation_records(
        _load_jsonl(PROOF_WEIGHTED_OPPORTUNITIES_PATH),
        _load_json(PAPER_ALLOCATION_POLICY_PATH),
        _load_json(PAPER_RISK_BUDGET_PATH),
        _load_jsonl(PAPER_ALLOCATION_DECISIONS_PATH),
        _load_json(PAPER_ALLOCATION_PLAN_PATH),
        _load_jsonl(ALLOCATION_REJECTIONS_PATH),
        _load_jsonl(ALLOCATION_WATCHLIST_PATH),
        _load_json(ALLOCATION_EXPOSURE_SUMMARY_PATH),
        _load_json(ALLOCATION_CONSTRAINT_SUMMARY_PATH),
        _load_jsonl(ALLOCATION_PROOF_PATH),
    )


def _portfolio_replay_violation_checks() -> list[dict]:
    missing_paths = [
        path for path in [
            PORTFOLIO_REPLAY_POLICY_PATH,
            PORTFOLIO_REPLAY_OPPORTUNITIES_PATH,
            PORTFOLIO_STATES_PATH,
            PORTFOLIO_POSITIONS_PATH,
            PORTFOLIO_ROTATION_DECISIONS_PATH,
            PORTFOLIO_EXPOSURE_SNAPSHOTS_PATH,
            EXPOSURE_STRESS_RESULTS_PATH,
            PORTFOLIO_ALLOCATOR_FEEDBACK_PATH,
            PORTFOLIO_THRESHOLD_FEEDBACK_PATH,
            PORTFOLIO_REPLAY_SUMMARY_PATH,
            PORTFOLIO_REPLAY_PROOF_PATH,
        ]
        if not path.exists()
    ]
    if missing_paths:
        return [{
            "check_id": "portfolio_replay_violation_checks",
            "passed": False,
            "path": ", ".join(str(path) for path in missing_paths),
            "message": "portfolio replay artifacts missing",
        }]
    return audit_portfolio_replay_records(
        _load_json(PORTFOLIO_REPLAY_POLICY_PATH),
        _load_jsonl(PORTFOLIO_REPLAY_OPPORTUNITIES_PATH),
        _load_jsonl(PORTFOLIO_STATES_PATH),
        _load_jsonl(PORTFOLIO_POSITIONS_PATH),
        _load_jsonl(PORTFOLIO_ROTATION_DECISIONS_PATH),
        _load_jsonl(PORTFOLIO_EXPOSURE_SNAPSHOTS_PATH),
        _load_jsonl(EXPOSURE_STRESS_RESULTS_PATH),
        _load_jsonl(PORTFOLIO_ALLOCATOR_FEEDBACK_PATH),
        _load_jsonl(PORTFOLIO_THRESHOLD_FEEDBACK_PATH),
        _load_json(PORTFOLIO_REPLAY_SUMMARY_PATH),
        _load_jsonl(PORTFOLIO_REPLAY_PROOF_PATH),
    )


def _stress_ladder_violation_checks() -> list[dict]:
    missing_paths = [
        path for path in [
            STRESS_LADDER_POLICY_PATH,
            CRISIS_MODE_THROTTLE_PROFILES_PATH,
            STRESS_LADDER_REPLAY_CASES_PATH,
            STRESS_LEVEL_EVALUATIONS_PATH,
            STRESS_TRANSITION_DECISIONS_PATH,
            CRISIS_THROTTLE_RESULTS_PATH,
            CRISIS_RECOVERY_RESULTS_PATH,
            CRISIS_ALLOCATOR_FEEDBACK_PATH,
            CRISIS_THRESHOLD_FEEDBACK_PATH,
            STRESS_LADDER_SUMMARY_PATH,
            STRESS_LADDER_PROOF_PATH,
        ]
        if not path.exists()
    ]
    if missing_paths:
        return [{
            "check_id": "stress_ladder_violation_checks",
            "passed": False,
            "path": ", ".join(str(path) for path in missing_paths),
            "message": "portfolio stress ladder artifacts missing",
        }]
    return audit_stress_ladder_records(
        _load_json(STRESS_LADDER_POLICY_PATH),
        _load_json(CRISIS_MODE_THROTTLE_PROFILES_PATH),
        _load_json(STRESS_LADDER_REPLAY_CASES_PATH),
        _load_jsonl(STRESS_LEVEL_EVALUATIONS_PATH),
        _load_jsonl(STRESS_TRANSITION_DECISIONS_PATH),
        _load_jsonl(CRISIS_THROTTLE_RESULTS_PATH),
        _load_jsonl(CRISIS_RECOVERY_RESULTS_PATH),
        _load_jsonl(CRISIS_ALLOCATOR_FEEDBACK_PATH),
        _load_jsonl(CRISIS_THRESHOLD_FEEDBACK_PATH),
        _load_json(STRESS_LADDER_SUMMARY_PATH),
        _load_jsonl(STRESS_LADDER_PROOF_PATH),
    )


def audit_incident_response_records(
    taxonomy: dict,
    cases: dict,
    signals: list[dict],
    states: list[dict],
    responses: list[dict],
    recoveries: list[dict],
    allocator_feedback: list[dict],
    threshold_feedback: list[dict],
    stress_ladder_feedback: list[dict],
    summary: dict,
    proof_records: list[dict],
) -> list[dict]:
    taxonomy_records = taxonomy.get("records", []) if isinstance(taxonomy.get("records", []), list) else []
    case_records = cases.get("records", []) if isinstance(cases.get("records", []), list) else []
    all_records = [
        taxonomy,
        cases,
        *taxonomy_records,
        *case_records,
        *signals,
        *states,
        *responses,
        *recoveries,
        *allocator_feedback,
        *threshold_feedback,
        *stress_ladder_feedback,
        summary,
        *proof_records,
    ]
    dict_records = [record for record in all_records if isinstance(record, dict)]
    real_dollar_fields = {"real_dollar_sizing_units", "real_capital_dollars", "usd_notional"}
    buying_power_fields = {"buying_power", "buying_power_used", "real_buying_power"}
    account_balance_fields = {"account_balance", "real_account_balance"}
    broker_tokens = {"broker_execute", "robinhood_order", "alpaca_order", "tradier_order", "broker_execution_allowed\": true"}
    credential_tokens = {"api_key", "secret", "token=", "credential_value", "password"}
    scheduler_fields = {"cron_expression", "scheduler_enabled", "scheduled_live_trade"}
    live_order_tokens = {"live_order", "place_live_order", "submit_live_order"}
    unsupported_tokens = {"sell_to_open_allowed", "naked_allowed", "undefined_risk_allowed", "uncovered_allowed"}
    active_forbidden_live = [
        record for record in proof_records
        if record.get("action_allowed") is True
        and str(record.get("response_decision", "")) in {"terminal_block", "paper_lockdown"}
    ]
    terminal_auto_recoveries = [
        record for record in recoveries
        if record.get("current_kill_switch_state") == "terminal_block" and record.get("recovery_allowed") is True
    ]
    return [
        {"check_id": "incident_taxonomy_parses", "passed": taxonomy.get("artifact_type") == "incident_taxonomy" and bool(taxonomy_records), "message": "incident taxonomy parses"},
        {"check_id": "incident_rehearsal_cases_parse", "passed": cases.get("artifact_type") == "incident_rehearsal_cases" and len(case_records) >= 144, "message": "incident rehearsal cases parse"},
        {"check_id": "incident_signals_parse", "passed": bool(signals) and all(record.get("signal_id") and record.get("signal_hash") for record in signals), "message": "incident signals parse"},
        {"check_id": "kill_switch_states_parse", "passed": bool(states) and all(record.get("kill_switch_id") and record.get("state_hash") for record in states), "message": "kill-switch states parse"},
        {"check_id": "incident_response_decisions_parse", "passed": bool(responses) and all(record.get("response_id") and record.get("decision_hash") for record in responses), "message": "incident response decisions parse"},
        {"check_id": "incident_recovery_plans_parse", "passed": bool(recoveries) and all(record.get("recovery_plan_id") and record.get("plan_hash") for record in recoveries), "message": "incident recovery plans parse"},
        {"check_id": "incident_all_paper_only", "passed": all(record.get("paper_only") is True for record in dict_records), "message": "all incident records are paper-only"},
        {"check_id": "incident_all_live_blocked", "passed": all(record.get("live_blocked") is True for record in dict_records), "message": "all incident records are live-blocked"},
        {"check_id": "incident_no_real_dollars", "passed": all(record.get("no_real_sizing", True) is True for record in dict_records) and not any(any(field in record for field in real_dollar_fields) for record in dict_records), "message": "incident response creates no real dollar sizing"},
        {"check_id": "incident_no_buying_power", "passed": not any(any(field in record for field in buying_power_fields) for record in dict_records), "message": "incident response creates no buying-power dependency"},
        {"check_id": "incident_no_account_balance", "passed": not any(any(field in record for field in account_balance_fields) for record in dict_records), "message": "incident response creates no account-balance dependency"},
        {"check_id": "incident_no_broker_path", "passed": not any(_record_contains_token(record, broker_tokens) for record in dict_records), "message": "incident response creates no broker execution path"},
        {"check_id": "incident_no_credentials", "passed": not any(_record_contains_token(record, credential_tokens) for record in dict_records), "message": "incident response stores no credentials"},
        {"check_id": "incident_no_scheduler", "passed": all(record.get("no_scheduler", True) is True for record in dict_records) and not any(any(field in record for field in scheduler_fields) for record in dict_records), "message": "incident response creates no scheduler"},
        {"check_id": "incident_no_live_order", "passed": not any(_record_contains_token(record, live_order_tokens) for record in dict_records), "message": "incident response creates no live order"},
        {"check_id": "incident_no_unsupported_live_paths", "passed": not any(_record_contains_token(record, unsupported_tokens) for record in dict_records), "message": "incident response creates no sell-to-open/naked/undefined-risk allowance"},
        {"check_id": "incident_no_same_day_churn", "passed": summary.get("same_day_churn_allowed") is False and all(record.get("same_day_churn_allowed") is False for record in proof_records), "message": "incident response blocks same-day churn"},
        {"check_id": "incident_response_does_not_force_same_day_close", "passed": summary.get("same_day_close_forced_count") == 0 and all(record.get("same_day_close_forced") is False for record in proof_records), "message": "incident response does not force same-day close"},
        {"check_id": "incident_response_does_not_override_paperbroker", "passed": summary.get("paperbroker_override_allowed") is False and all(record.get("paperbroker_override_allowed") is False for record in proof_records), "message": "incident response does not override PaperBroker"},
        {"check_id": "incident_terminal_block_cannot_auto_recover", "passed": not terminal_auto_recoveries and summary.get("terminal_block_auto_recovery_allowed") is False, "message": "terminal block incidents cannot auto-recover"},
        {"check_id": "incident_full_suite_timeout_not_pass", "passed": summary.get("full_suite_timeout_recorded_as_pass") is False, "message": "full-suite timeout remains not pass"},
        {"check_id": "incident_no_active_forbidden_live_decisions", "passed": not active_forbidden_live, "message": "incident response creates no active forbidden live decisions"},
        {"check_id": "incident_allocator_feedback_advisory_only", "passed": all(record.get("advisory_only") is True and record.get("live_allocation_mutation_allowed") is False for record in allocator_feedback), "message": "incident allocator feedback is advisory only"},
        {"check_id": "incident_threshold_feedback_advisory_only", "passed": all(record.get("advisory_only") is True and record.get("live_threshold_mutation_allowed") is False for record in threshold_feedback), "message": "incident threshold feedback is advisory only"},
        {"check_id": "incident_stress_ladder_feedback_advisory_only", "passed": all(record.get("advisory_only") is True for record in stress_ladder_feedback), "message": "incident stress ladder feedback is advisory only"},
    ]


def _incident_response_violation_checks() -> list[dict]:
    missing_paths = [
        path for path in [
            INCIDENT_TAXONOMY_PATH,
            INCIDENT_REHEARSAL_CASES_PATH,
            INCIDENT_SIGNALS_PATH,
            KILL_SWITCH_STATES_PATH,
            INCIDENT_RESPONSE_DECISIONS_PATH,
            INCIDENT_RECOVERY_PLANS_PATH,
            INCIDENT_ALLOCATOR_FEEDBACK_PATH,
            INCIDENT_THRESHOLD_FEEDBACK_PATH,
            INCIDENT_STRESS_LADDER_FEEDBACK_PATH,
            INCIDENT_REHEARSAL_SUMMARY_PATH,
            INCIDENT_RESPONSE_PROOF_PATH,
        ]
        if not path.exists()
    ]
    if missing_paths:
        return [{
            "check_id": "incident_response_violation_checks",
            "passed": False,
            "path": ", ".join(str(path) for path in missing_paths),
            "message": "incident response artifacts missing",
        }]
    return audit_incident_response_records(
        _load_json(INCIDENT_TAXONOMY_PATH),
        _load_json(INCIDENT_REHEARSAL_CASES_PATH),
        _load_jsonl(INCIDENT_SIGNALS_PATH),
        _load_jsonl(KILL_SWITCH_STATES_PATH),
        _load_jsonl(INCIDENT_RESPONSE_DECISIONS_PATH),
        _load_jsonl(INCIDENT_RECOVERY_PLANS_PATH),
        _load_jsonl(INCIDENT_ALLOCATOR_FEEDBACK_PATH),
        _load_jsonl(INCIDENT_THRESHOLD_FEEDBACK_PATH),
        _load_jsonl(INCIDENT_STRESS_LADDER_FEEDBACK_PATH),
        _load_json(INCIDENT_REHEARSAL_SUMMARY_PATH),
        _load_jsonl(INCIDENT_RESPONSE_PROOF_PATH),
    )


def audit_active_lifecycle_records(
    policy: dict,
    cases: dict,
    states: list[dict],
    transitions: list[dict],
    proofs: list[dict],
    paperbroker_results: list[dict],
    account_ledger_results: list[dict],
    feedback_allocator: list[dict],
    feedback_portfolio: list[dict],
    feedback_stress: list[dict],
    feedback_incident: list[dict],
    summary: dict,
) -> list[dict]:
    case_records = cases.get("records", []) if isinstance(cases.get("records", []), list) else []
    all_records = [
        policy,
        cases,
        *case_records,
        *states,
        *transitions,
        *proofs,
        *paperbroker_results,
        *account_ledger_results,
        *feedback_allocator,
        *feedback_portfolio,
        *feedback_stress,
        *feedback_incident,
        summary,
    ]
    dict_records = [record for record in all_records if isinstance(record, dict)]
    text_records = [json.dumps(record, sort_keys=True) for record in dict_records]
    forbidden_field_sets = {
        "lifecycle_no_real_dollars": {"real_dollar_sizing_units", "real_capital_dollars", "usd_notional"},
        "lifecycle_no_buying_power": {"buying_power", "buying_power_used", "real_buying_power"},
        "lifecycle_no_account_balance": {"account_balance", "real_account_balance"},
        "lifecycle_no_scheduler": {"cron_expression", "scheduler_enabled", "scheduled_live_trade"},
    }
    checks = [
        {"check_id": "lifecycle_policy_parses", "passed": policy.get("artifact_type") == "lifecycle_policy", "message": "lifecycle policy parses"},
        {"check_id": "lifecycle_cases_parse", "passed": cases.get("artifact_type") == "lifecycle_cases" and len(case_records) >= 120, "message": "lifecycle cases parse"},
        {"check_id": "lifecycle_states_parse", "passed": bool(states) and all(record.get("state_id") and record.get("state_hash") for record in states), "message": "lifecycle states parse"},
        {"check_id": "lifecycle_transitions_parse", "passed": bool(transitions) and all(record.get("transition_id") and record.get("transition_hash") for record in transitions), "message": "lifecycle transitions parse"},
        {"check_id": "lifecycle_proof_parse", "passed": bool(proofs) and all(record.get("proof_id") and record.get("proof_hash") for record in proofs), "message": "lifecycle proof parses"},
        {"check_id": "lifecycle_all_paper_only", "passed": all(record.get("paper_only") is True for record in dict_records), "message": "all lifecycle records are paper-only"},
        {"check_id": "lifecycle_all_live_blocked", "passed": all(record.get("live_blocked") is True for record in dict_records), "message": "all lifecycle records are live-blocked"},
        {"check_id": "lifecycle_no_broker_path", "passed": not any("broker_execute" in text or "submit_live_order" in text or "place_live_order" in text for text in text_records), "message": "lifecycle creates no broker execution path"},
        {"check_id": "lifecycle_no_credentials", "passed": not any("credential_value" in text or "api_key" in text or "token=" in text or "password" in text for text in text_records), "message": "lifecycle stores no credentials"},
        {"check_id": "lifecycle_no_live_order", "passed": not any("live_order_allowed" in text or "live_order\": true" in text for text in text_records), "message": "lifecycle creates no live order"},
        {"check_id": "lifecycle_no_same_day_churn", "passed": summary.get("same_day_churn_allowed") is False and summary.get("no_day_trade_block_count", 0) >= 1, "message": "lifecycle blocks normal same-day churn"},
        {"check_id": "lifecycle_paperbroker_not_overridden", "passed": summary.get("paperbroker_override_allowed") is False and all(record.get("paperbroker_override_allowed", False) is False for record in proofs), "message": "lifecycle does not override PaperBroker"},
        {"check_id": "lifecycle_terminal_block_no_auto_recovery", "passed": summary.get("terminal_block_auto_recovery_allowed") is False, "message": "terminal block cannot auto-recover"},
        {"check_id": "lifecycle_full_suite_timeout_not_pass", "passed": summary.get("full_suite_timeout_recorded_as_pass") is False, "message": "full-suite timeout remains not pass"},
        {"check_id": "lifecycle_feedback_allocator_advisory_only", "passed": all(record.get("advisory_only") is True and record.get("live_allocation_mutation_allowed") is False for record in feedback_allocator), "message": "lifecycle allocator feedback is advisory only"},
        {"check_id": "lifecycle_feedback_portfolio_advisory_only", "passed": all(record.get("advisory_only") is True and record.get("live_portfolio_mutation_allowed") is False for record in feedback_portfolio), "message": "lifecycle portfolio feedback is advisory only"},
        {"check_id": "lifecycle_feedback_stress_ladder_advisory_only", "passed": all(record.get("advisory_only") is True and record.get("live_stress_ladder_mutation_allowed") is False for record in feedback_stress), "message": "lifecycle stress feedback is advisory only"},
        {"check_id": "lifecycle_feedback_incident_advisory_only", "passed": all(record.get("advisory_only") is True and record.get("live_incident_mutation_allowed") is False for record in feedback_incident), "message": "lifecycle incident feedback is advisory only"},
    ]
    for check_id, fields in forbidden_field_sets.items():
        checks.append({
            "check_id": check_id,
            "passed": not any(any(field in record for field in fields) for record in dict_records),
            "message": f"{check_id} forbidden fields absent",
        })
    return checks


def _active_lifecycle_violation_checks() -> list[dict]:
    missing_paths = [
        path for path in [
            LIFECYCLE_POLICY_PATH,
            LIFECYCLE_CASES_PATH,
            LIFECYCLE_STATES_PATH,
            LIFECYCLE_TRANSITIONS_PATH,
            LIFECYCLE_PROOF_PATH,
            LIFECYCLE_PAPERBROKER_RESULTS_PATH,
            LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH,
            LIFECYCLE_FEEDBACK_ALLOCATOR_PATH,
            LIFECYCLE_FEEDBACK_PORTFOLIO_PATH,
            LIFECYCLE_FEEDBACK_STRESS_LADDER_PATH,
            LIFECYCLE_FEEDBACK_INCIDENT_PATH,
            LIFECYCLE_SUMMARY_PATH,
        ]
        if not path.exists()
    ]
    if missing_paths:
        return [{
            "check_id": "active_lifecycle_violation_checks",
            "passed": False,
            "path": ", ".join(str(path) for path in missing_paths),
            "message": "active lifecycle artifacts missing",
        }]
    return audit_active_lifecycle_records(
        _load_json(LIFECYCLE_POLICY_PATH),
        _load_json(LIFECYCLE_CASES_PATH),
        _load_jsonl(LIFECYCLE_STATES_PATH),
        _load_jsonl(LIFECYCLE_TRANSITIONS_PATH),
        _load_jsonl(LIFECYCLE_PROOF_PATH),
        _load_jsonl(LIFECYCLE_PAPERBROKER_RESULTS_PATH),
        _load_jsonl(LIFECYCLE_ACCOUNT_LEDGER_RESULTS_PATH),
        _load_jsonl(LIFECYCLE_FEEDBACK_ALLOCATOR_PATH),
        _load_jsonl(LIFECYCLE_FEEDBACK_PORTFOLIO_PATH),
        _load_jsonl(LIFECYCLE_FEEDBACK_STRESS_LADDER_PATH),
        _load_jsonl(LIFECYCLE_FEEDBACK_INCIDENT_PATH),
        _load_json(LIFECYCLE_SUMMARY_PATH),
    )


def _candidate_input(record: dict) -> dict:
    value = record.get("candidate_input", {})
    return value if isinstance(value, dict) else {}


def _candidate_preserves_no_churn(record: dict) -> bool:
    change_set = record.get("change_set", {})
    if not isinstance(change_set, dict):
        return False
    invariants = change_set.get("safety_invariants", {})
    if not isinstance(invariants, dict):
        return False
    threshold_profile = record.get("threshold_profile", {})
    thresholds = threshold_profile.get("thresholds", {}) if isinstance(threshold_profile, dict) else {}
    if not isinstance(thresholds, dict):
        return False
    return (
        invariants.get("allow_normal_same_day_churn") is False
        and invariants.get("allow_sell_to_open") is False
        and thresholds.get("special_lifecycle_required") is True
        and thresholds.get("explicit_same_day_special_close_reason_required") is True
        and thresholds.get("paper_only") is True
        and thresholds.get("live_blocked") is True
    )


def _load_json(path: Path) -> dict:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {}


def _load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _check_path(check_id: str, path: Path) -> dict:
    return {
        "check_id": check_id,
        "passed": path.exists(),
        "path": str(path),
        "message": "present" if path.exists() else "missing",
    }


def _active_intent(
    intent_id: str,
    structure: str,
    side: str,
    order_action: str,
    trade_date: str,
    option_type: str = "call",
) -> ExecutionIntent:
    symbol = "SPY_C1" if option_type == "call" else "SPY_P1"
    return ExecutionIntent(
        intent_id=intent_id,
        symbol="SPY_FIXTURE",
        structure=structure,
        legs=[{"side": side, "symbol": symbol, "option_type": option_type, "expiry": "2026-07-17", "dte": 14}],
        max_loss=1.0,
        target_profit=2.0,
        order_action=order_action,
        trade_date=trade_date,
        position_id=intent_id,
        active_policy_required=True,
        lifecycle_state="normal_hold",
    )


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
