"""Deterministic artifact selection rules for DOPEY export bundles."""
from __future__ import annotations

import json
from pathlib import Path

from dopey_core.config import default_config_path, load_config

from .export_manifest import canonical_export_hash, sha256_file
from .export_models import (
    DEFAULT_EXPORT_PROFILE,
    EXPORT_PROFILES,
    ExportArtifact,
    ExportBundlePlan,
    ExportProfile,
    ExportSelectionRule,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "dopey"
EXPORT_ROOT = ARTIFACT_ROOT / "exports"
COMPACTED_ROOT = EXPORT_ROOT / "compacted"
EXPORT_REGISTRY_PATH = EXPORT_ROOT / "export_registry.jsonl"
EXPORT_MANIFEST_REGISTRY_PATH = EXPORT_ROOT / "export_manifest.jsonl"
EXPORT_VERIFICATION_PATH = EXPORT_ROOT / "export_verification.jsonl"
EXPORT_SAFETY_SCAN_PATH = EXPORT_ROOT / "export_safety_scan.jsonl"
EXPORT_COPY_PROOF_PATH = EXPORT_ROOT / "export_copy_proof.jsonl"
EXPORT_COMPACTION_SUMMARY_PATH = EXPORT_ROOT / "export_compaction_summary.jsonl"
EXPORT_PROOF_LEDGER_PATH = EXPORT_ROOT / "export_verifier_proof.jsonl"
BLUNDER_INTEGRITY_STATUS_PATH = EXPORT_ROOT / "blunder_integrity_status.json"


EXCLUDED_PATH_PARTS = {
    ".git",
    ".env",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    "_forked_blunder",
    "_forked_blunder_tests",
    "_forked_scripts",
}
JSONL_PARSE_THRESHOLD_BYTES = 8 * 1024 * 1024


def default_export_profile() -> ExportProfile:
    return export_profile_for(DEFAULT_EXPORT_PROFILE)


def export_profile_for(profile_name: str) -> ExportProfile:
    if profile_name not in EXPORT_PROFILES:
        raise ValueError(f"unsupported export profile: {profile_name}")
    return ExportProfile(
        profile_name=profile_name,
        include_reports=profile_name in {"minimal_proof", "reporting_dashboard", "full_offline_evidence", "handoff_shared_folder", "audit_only"},
        include_reporting_dashboard=profile_name in {"reporting_dashboard", "full_offline_evidence", "handoff_shared_folder"},
        include_audit=profile_name in {"minimal_proof", "full_offline_evidence", "handoff_shared_folder", "audit_only"},
        include_full_evidence=profile_name in {"full_offline_evidence", "handoff_shared_folder"},
        include_copy_target=profile_name == "handoff_shared_folder",
        compact_large_ledgers=True,
    )


def safety_state() -> dict:
    cfg = load_config(default_config_path())
    return {
        "mode": str(cfg.get("mode", "RESEARCH")),
        "live_trading_enabled": bool(cfg.get("live_trading_enabled", False)),
        "funded_broker_connections_enabled": bool(cfg.get("funded_broker_connections_enabled", False)),
        "allow_unofficial_robinhood_api": bool(cfg.get("allow_unofficial_robinhood_api", False)),
        "paper_only_export": True,
        "fixture_only": True,
        "live_blocked": True,
    }


def verify_export_safety_state(state: dict) -> None:
    if state.get("mode") != "RESEARCH":
        raise ValueError(f"export verifier requires RESEARCH mode, got {state.get('mode')}")
    if state.get("live_trading_enabled") is not False:
        raise ValueError("export verifier requires live_trading_enabled=false")
    if state.get("funded_broker_connections_enabled") is not False:
        raise ValueError("export verifier requires funded_broker_connections_enabled=false")
    if state.get("allow_unofficial_robinhood_api") is not False:
        raise ValueError("export verifier requires allow_unofficial_robinhood_api=false")


def repo_relative_path(path: Path | str) -> str:
    target = Path(path)
    if target.is_absolute():
        if target.is_relative_to(ARTIFACT_ROOT):
            return (Path("artifacts") / "dopey" / target.relative_to(ARTIFACT_ROOT)).as_posix()
        try:
            return target.relative_to(REPO_ROOT).as_posix()
        except ValueError as exc:
            raise ValueError(f"export source path is outside repo root: {target}") from exc
    return target.as_posix()


def resolve_repo_path(source_path: str) -> Path:
    target = Path(source_path)
    if target.is_absolute():
        return target
    parts = target.parts
    if len(parts) >= 2 and parts[0].lower() == "artifacts" and parts[1].lower() == "dopey":
        return ARTIFACT_ROOT.joinpath(*parts[2:])
    return REPO_ROOT / target


def is_excluded_path(path: Path | str) -> bool:
    parts = {part.lower() for part in Path(path).parts}
    normalized = str(path).replace("\\", "/").lower()
    if any(part.lower() in parts for part in EXCLUDED_PATH_PARTS):
        return True
    if "/artifacts/dopey/exports/" in normalized:
        return True
    if normalized.endswith(".env") or ".env." in normalized:
        return True
    return False


def _rule(
    artifact_id: str,
    artifact_type: str,
    source_path: str,
    relative_export_path: str,
    required: bool,
    profiles: list[str],
    notes: list[str],
) -> ExportSelectionRule:
    return ExportSelectionRule(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        source_path=source_path,
        relative_export_path=relative_export_path,
        required=required,
        profiles=profiles,
        notes=notes,
    )


def export_selection_rules() -> list[ExportSelectionRule]:
    all_profiles = list(EXPORT_PROFILES)
    full_profiles = ["full_offline_evidence", "handoff_shared_folder"]
    reporting_profiles = ["reporting_dashboard", "full_offline_evidence", "handoff_shared_folder"]
    audit_profiles = ["audit_only", "minimal_proof", "full_offline_evidence", "handoff_shared_folder"]
    report_files = [
        "DOPEY_VALIDATION_REPORT.md",
        "DOPEY_CANON.md",
        "DOPEY_RISK_DISCIPLINE.md",
        "DOPEY_BROKER_BOUNDARIES.md",
        "DOPEY_TOURNAMENT_PERFORMANCE_REPORTING_DASHBOARD_REPORT.md",
        "DOPEY_REPORTING_ARTIFACT_LEDGER.md",
        "DOPEY_TOURNAMENT_PERFORMANCE_REPORTING_DASHBOARD_SESSION_REPORT.md",
        "DOPEY_OFFLINE_EVIDENCE_REPLAY_AUDIT_REPORT.md",
        "DOPEY_OFFLINE_META_GOVERNOR_REPORT.md",
        "DOPEY_OFFLINE_ENSEMBLE_ALLOCATOR_REPORT.md",
        "DOPEY_SECTOR_PEER_FUNDAMENTAL_FIXTURE_EXPANSION_REPORT.md",
        "DOPEY_LARGER_REGIME_HOLDOUT_CORPUS_V2_REPORT.md",
        "DOPEY_STRONGER_WALK_FORWARD_CONSISTENCY_REPORT.md",
        "DOPEY_MACRO_EVENT_FIXTURE_EXPANSION_REPORT.md",
        "DOPEY_IV_SURFACE_SKEW_EXPANSION_REPORT.md",
        "DOPEY_FAILURE_FEEDBACK_OPTIMIZER_REPORT.md",
        "DOPEY_FAILURE_MODE_MINER_REPORT.md",
        "DOPEY_MUTATION_POPULATION_BUNDLE_REPORT.md",
        "DOPEY_GREEKS_IV_VALIDATION_REPORT.md",
        "DOPEY_SLIPPAGE_LIQUIDITY_REPORT.md",
        "DOPEY_TOURNAMENT_REPORT.md",
        "DOPEY_WALK_FORWARD_REPORT.md",
        "DOPEY_ACTIVE_TRADING_CANON_POLICY_REPORT.md",
        "DOPEY_ACTIVE_TRADING_POLICY_INTEGRATION_REPORT.md",
        "DOPEY_ACTIVE_POLICY_ARTIFACT_LEDGER.md",
        "DOPEY_FULL_VALIDATION_STABILIZER_REPORT.md",
        "DOPEY_TEXT_ENCODING_GUARD_REPORT.md",
        "DOPEY_NO_DAY_TRADE_ACCOUNT_LEDGER_AND_ROTATION_PLANNER_REPORT.md",
        "DOPEY_ACCOUNT_LEDGER_ARTIFACT_LEDGER.md",
        "DOPEY_0DTE_SPECIAL_LIFECYCLE_RISK_MODEL_REPORT.md",
        "DOPEY_0DTE_RISK_ARTIFACT_LEDGER.md",
        "DOPEY_0DTE_EXPIRY_OUTCOME_REPLAY_SIMULATOR_REPORT.md",
        "DOPEY_0DTE_REPLAY_ARTIFACT_LEDGER.md",
        "DOPEY_0DTE_THRESHOLD_FEEDBACK_OPTIMIZER_REPORT.md",
        "DOPEY_0DTE_THRESHOLD_OPTIMIZER_ARTIFACT_LEDGER.md",
        "DOPEY_0DTE_EMPIRICAL_FIXTURE_EXPANSION_AND_ADVERSARIAL_REPLAY_CORPUS_REPORT.md",
        "DOPEY_0DTE_ADVERSARIAL_CORPUS_ARTIFACT_LEDGER.md",
        "DOPEY_0DTE_ADVERSARIAL_CORPUS_V2_CROSS_UNDERLYING_REGIME_FAMILIES_REPORT.md",
        "DOPEY_0DTE_CROSS_UNDERLYING_V2_ARTIFACT_LEDGER.md",
        "DOPEY_CROSS_UNDERLYING_V3_MULTI_DAY_SWING_0DTE_HYBRID_REPLAY_CORPUS_REPORT.md",
        "DOPEY_HYBRID_SWING_0DTE_V3_ARTIFACT_LEDGER.md",
        "DOPEY_PROOF_WEIGHTED_CAPITAL_ALLOCATOR_FOR_LONG_PREMIUM_OPTIONS_REPORT.md",
        "DOPEY_PROOF_WEIGHTED_ALLOCATOR_ARTIFACT_LEDGER.md",
        "DOPEY_PORTFOLIO_LEVEL_ROTATION_AND_EXPOSURE_REPLAY_REPORT.md",
        "DOPEY_PORTFOLIO_REPLAY_ARTIFACT_LEDGER.md",
        "DOPEY_PORTFOLIO_REPLAY_V2_STRESS_LADDER_AND_CRISIS_MODE_THROTTLES_REPORT.md",
        "DOPEY_PORTFOLIO_STRESS_LADDER_ARTIFACT_LEDGER.md",
        "DOPEY_PORTFOLIO_REPLAY_V3_KILL_SWITCH_REHEARSAL_AND_INCIDENT_RESPONSE_SIMULATOR_REPORT.md",
        "DOPEY_INCIDENT_RESPONSE_ARTIFACT_LEDGER.md",
        "DOPEY_ACTIVE_LONG_CALL_LONG_PUT_LIFECYCLE_SIMULATOR_REPORT.md",
        "DOPEY_ACTIVE_LIFECYCLE_ARTIFACT_LEDGER.md",
        "DOPEY_BROKER_READINESS_PREFLIGHT_CHECKLIST_AND_READ_ONLY_BOUNDARY_SIMULATOR_REPORT.md",
        "DOPEY_BROKER_READINESS_ARTIFACT_LEDGER.md",
        "DOPEY_READ_ONLY_BROKER_CAPABILITY_DETECTOR_MANUAL_APPROVAL_PACKET_REPORT.md",
        "DOPEY_MANUAL_APPROVAL_PACKET_ARTIFACT_LEDGER.md",
        "DOPEY_READ_ONLY_DETECTOR_APPROVAL_INTAKE_VALIDATOR_REPORT.md",
        "DOPEY_APPROVAL_INTAKE_VALIDATOR_ARTIFACT_LEDGER.md",
        "DOPEY_READ_ONLY_DETECTOR_APPROVAL_TO_RUN_HANDOFF_GATE_REPORT.md",
        "DOPEY_APPROVAL_TO_RUN_HANDOFF_GATE_ARTIFACT_LEDGER.md",
        "DOPEY_READ_ONLY_DETECTOR_PRE_RUN_SAFETY_SCANNER_REPORT.md",
        "DOPEY_PRE_RUN_SAFETY_SCANNER_ARTIFACT_LEDGER.md",
        "DOPEY_HUMAN_APPROVED_READ_ONLY_BROKER_CAPABILITY_DETECTOR_REPORT.md",
        "DOPEY_READ_ONLY_DETECTOR_ARTIFACT_LEDGER.md",
        "DOPEY_READ_ONLY_DETECTOR_POST_RUN_EVIDENCE_CONTRACT_HARDENING_REPORT.md",
        "DOPEY_READ_ONLY_DETECTOR_EVIDENCE_CONTRACT_ARTIFACT_LEDGER.md",
        "DOPEY_REAL_DATA_BACKTEST_SPINE_REPORT.md",
        "DOPEY_REAL_DATA_BACKTEST_SPINE_ARTIFACT_LEDGER.md",
        "DOPEY_MODEL_REPRICER_REPORT.md",
        "DOPEY_MODEL_REPRICER_ARTIFACT_LEDGER.md",
        "DOPEY_REAL_SIGNAL_ENGINES_REPORT.md",
        "DOPEY_REAL_SIGNAL_ENGINES_ARTIFACT_LEDGER.md",
        "DOPEY_HONEST_BACKTESTER_REPORT.md",
        "DOPEY_HONEST_BACKTESTER_ARTIFACT_LEDGER.md",
        "DOPEY_STATISTICAL_TRUTH_LAYER_REPORT.md",
        "DOPEY_STATISTICAL_TRUTH_LAYER_ARTIFACT_LEDGER.md",
        "DOPEY_FITNESS_FUNCTION_REPLACEMENT_REPORT.md",
        "DOPEY_FITNESS_FUNCTION_REPLACEMENT_ARTIFACT_LEDGER.md",
        "DOPEY_REAL_DATA_INGESTION_PLAN_REPORT.md",
        "DOPEY_REAL_DATA_INGESTION_PLAN_ARTIFACT_LEDGER.md",
        "DOPEY_MANUAL_REAL_OHLCV_STAGING_INSTRUCTIONS.md",
        "DOPEY_REAL_DATA_VALIDATION_STACK_REPORT.md",
        "DOPEY_REAL_DATA_VALIDATION_STACK_ARTIFACT_LEDGER.md",
        "DOPEY_LOCAL_FREE_OHLCV_IMPORT_VALIDATOR_AND_HISTORY_ACTIVATION_REPORT.md",
        "DOPEY_LOCAL_FREE_OHLCV_IMPORT_VALIDATOR_AND_HISTORY_ACTIVATION_ARTIFACT_LEDGER.md",
        "DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_REPORT.md",
        "DOPEY_MANUAL_FREE_OHLCV_STAGING_OR_LOCAL_IMPORT_FIX_ARTIFACT_LEDGER.md",
        "DOPEY_MANUAL_FREE_OHLCV_STAGING_INSTRUCTIONS.md",
        "DOPEY_MANUAL_REAL_OHLCV_STAGING_INSTRUCTIONS.md",
        "DOPEY_OPERATOR_REVIEWED_OHLCV_STAGE_RERUN_REPORT.md",
        "DOPEY_OPERATOR_REVIEWED_OHLCV_STAGE_RERUN_ARTIFACT_LEDGER.md",
        "DOPEY_OPERATOR_REVIEWED_OHLCV_STAGE_RERUN_COMMANDS.md",
        "DOPEY_OPEN_SOURCE_QUANT_STACK_AND_FREE_DATA_PATH_REPORT.md",
        "DOPEY_OPEN_SOURCE_QUANT_STACK_AND_FREE_DATA_PATH_ARTIFACT_LEDGER.md",
        "DOPEY_OPEN_SOURCE_AUTONOMOUS_OPTIONS_TRADER_MAX_COMPLETION_REPORT.md",
        "DOPEY_OPEN_SOURCE_AUTONOMOUS_OPTIONS_TRADER_MAX_COMPLETION_ARTIFACT_LEDGER.md",
        "DOPEY_OPEN_SOURCE_AUTONOMOUS_OPTIONS_TRADER_COMMANDS.md",
        "DOPEY_TEST_SHARD_PLAN.md",
        "DOPEY_WEALTH_ENGINE_FULL_COMPLETION_REPORT.md",
        "DOPEY_WEALTH_ENGINE_FULL_COMPLETION_ARTIFACT_LEDGER.md",
        "DOPEY_WEALTH_ENGINE_COMMANDS.md",
        "DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1_REPORT.md",
        "DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1_ARTIFACT_LEDGER.md",
        "DOPEY_PUBLIC_MARKET_PAPER_CHAMPION_EVOLUTION_V1_COMMANDS.md",
    ]
    # Charter documents live at the repo root; every generated report/ledger/
    # commands doc lives under docs/reports (see dopey_core.repo_paths).
    root_charter_docs = {"DOPEY_VALIDATION_REPORT.md", "DOPEY_CANON.md", "DOPEY_RISK_DISCIPLINE.md", "DOPEY_BROKER_BOUNDARIES.md"}
    rules: list[ExportSelectionRule] = []
    for file_name in report_files:
        rules.append(_rule(
            artifact_id=f"report-{Path(file_name).stem.lower()}",
            artifact_type="validation_report" if file_name == "DOPEY_VALIDATION_REPORT.md" else "report_doc",
            source_path=file_name if file_name in root_charter_docs else f"docs/reports/{file_name}",
            relative_export_path=f"reports/{file_name}",
            required=file_name in root_charter_docs,
            profiles=all_profiles,
            notes=["documentation artifact"],
        ))
    artifact_specs = [
        ("reporting_dashboard_index", "reporting/dashboard_index.json", "artifacts/reporting/dashboard_index.json", True, reporting_profiles),
        ("reporting_dashboard_markdown", "reporting/dashboard_index.md", "artifacts/reporting/dashboard_index.md", True, reporting_profiles),
        ("strategy_report_cards", "reporting/strategy_report_cards.jsonl", "artifacts/reporting/strategy_report_cards.jsonl", True, reporting_profiles),
        ("family_report_cards", "reporting/family_report_cards.jsonl", "artifacts/reporting/family_report_cards.jsonl", True, reporting_profiles),
        ("scenario_report_cards", "reporting/scenario_report_cards.jsonl", "artifacts/reporting/scenario_report_cards.jsonl", True, reporting_profiles),
        ("regime_report_cards", "reporting/regime_report_cards.jsonl", "artifacts/reporting/regime_report_cards.jsonl", True, reporting_profiles),
        ("performance_attribution", "reporting/performance_attribution.jsonl", "artifacts/reporting/performance_attribution.jsonl", True, reporting_profiles),
        ("reporting_bundle_summary", "reporting/reporting_bundle_summary.json", "artifacts/reporting/reporting_bundle_summary.json", True, reporting_profiles),
        ("static_dashboard", "reporting/static_dashboard.html", "artifacts/reporting/static_dashboard.html", True, reporting_profiles),
        ("reporting_bundle_proof", "reporting/reporting_bundle_proof.jsonl", "artifacts/reporting/reporting_bundle_proof.jsonl", True, reporting_profiles),
        ("audit_summary", "audit/evidence_replay_audit_summary.md", "artifacts/audit/evidence_replay_audit_summary.md", True, audit_profiles),
        ("audit_inventory", "audit/evidence_inventory.jsonl", "artifacts/audit/evidence_inventory.jsonl", True, audit_profiles),
        ("audit_replay", "audit/replay_audit.jsonl", "artifacts/audit/replay_audit.jsonl", True, audit_profiles),
        ("audit_consistency", "audit/consistency_audit.jsonl", "artifacts/audit/consistency_audit.jsonl", True, audit_profiles),
        ("audit_safety", "audit/safety_audit.jsonl", "artifacts/audit/safety_audit.jsonl", True, audit_profiles),
        ("audit_gap_plan", "audit/evidence_gap_plan.jsonl", "artifacts/audit/evidence_gap_plan.jsonl", True, audit_profiles),
        ("audit_proof", "audit/evidence_replay_audit_proof.jsonl", "artifacts/audit/evidence_replay_audit_proof.jsonl", True, audit_profiles),
        ("active_policy_audit", "audit/active_policy_audit.jsonl", "artifacts/audit/active_policy_audit.jsonl", True, audit_profiles),
        ("active_policy_integration_map", "governor/active_policy_integration_map.json", "artifacts/governor/active_policy_integration_map.json", True, audit_profiles + full_profiles),
        ("active_policy_order_validation_proof", "governor/active_policy_order_validation_proof.jsonl", "artifacts/governor/active_policy_order_validation_proof.jsonl", True, audit_profiles + full_profiles),
        ("active_policy_position_lifecycle_proof", "governor/active_policy_position_lifecycle_proof.jsonl", "artifacts/governor/active_policy_position_lifecycle_proof.jsonl", True, audit_profiles + full_profiles),
        ("active_policy_paperbroker_proof", "governor/active_policy_paperbroker_proof.jsonl", "artifacts/governor/active_policy_paperbroker_proof.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_lifecycle_proof", "governor/zero_dte_lifecycle_proof.jsonl", "artifacts/governor/zero_dte_lifecycle_proof.jsonl", True, audit_profiles + full_profiles),
        ("no_day_trade_guard_proof", "governor/no_day_trade_guard_proof.jsonl", "artifacts/governor/no_day_trade_guard_proof.jsonl", True, audit_profiles + full_profiles),
        ("paper_account_ledger", "account_ledger/paper_account_ledger.json", "artifacts/account_ledger/paper_account_ledger.json", True, audit_profiles + full_profiles),
        ("day_trade_policy", "account_ledger/day_trade_policy.json", "artifacts/account_ledger/day_trade_policy.json", True, audit_profiles + full_profiles),
        ("pdt_safe_policy", "account_ledger/pdt_safe_policy.json", "artifacts/account_ledger/pdt_safe_policy.json", True, audit_profiles + full_profiles),
        ("rotation_plan", "account_ledger/rotation_plan.json", "artifacts/account_ledger/rotation_plan.json", True, audit_profiles + full_profiles),
        ("rotation_planner_proof", "account_ledger/rotation_planner_proof.jsonl", "artifacts/account_ledger/rotation_planner_proof.jsonl", True, audit_profiles + full_profiles),
        ("day_trade_event_log", "account_ledger/day_trade_event_log.jsonl", "artifacts/account_ledger/day_trade_event_log.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_account_lifecycle_proof", "account_ledger/zero_dte_account_lifecycle_proof.jsonl", "artifacts/account_ledger/zero_dte_account_lifecycle_proof.jsonl", True, audit_profiles + full_profiles),
        ("paperbroker_account_ledger_proof", "account_ledger/paperbroker_account_ledger_proof.jsonl", "artifacts/account_ledger/paperbroker_account_ledger_proof.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_risk_thresholds", "zero_dte_risk/zero_dte_risk_thresholds.json", "artifacts/zero_dte_risk/zero_dte_risk_thresholds.json", True, audit_profiles + full_profiles),
        ("zero_dte_risk_decisions", "zero_dte_risk/zero_dte_risk_decisions.jsonl", "artifacts/zero_dte_risk/zero_dte_risk_decisions.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_risk_summary", "zero_dte_risk/zero_dte_risk_summary.json", "artifacts/zero_dte_risk/zero_dte_risk_summary.json", True, audit_profiles + full_profiles),
        ("zero_dte_risk_proof", "zero_dte_risk/zero_dte_risk_proof.jsonl", "artifacts/zero_dte_risk/zero_dte_risk_proof.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_blocked_candidates", "zero_dte_risk/zero_dte_blocked_candidates.jsonl", "artifacts/zero_dte_risk/zero_dte_blocked_candidates.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_approved_candidates", "zero_dte_risk/zero_dte_approved_candidates.jsonl", "artifacts/zero_dte_risk/zero_dte_approved_candidates.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_replay_inputs", "zero_dte_replay/zero_dte_replay_inputs.jsonl", "artifacts/zero_dte_replay/zero_dte_replay_inputs.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_intraday_states", "zero_dte_replay/zero_dte_intraday_states.jsonl", "artifacts/zero_dte_replay/zero_dte_intraday_states.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_replay_decision_points", "zero_dte_replay/zero_dte_replay_decision_points.jsonl", "artifacts/zero_dte_replay/zero_dte_replay_decision_points.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_replay_outcomes", "zero_dte_replay/zero_dte_replay_outcomes.jsonl", "artifacts/zero_dte_replay/zero_dte_replay_outcomes.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_expiry_management", "zero_dte_replay/zero_dte_expiry_management.jsonl", "artifacts/zero_dte_replay/zero_dte_expiry_management.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_threshold_feedback", "zero_dte_replay/zero_dte_threshold_feedback.jsonl", "artifacts/zero_dte_replay/zero_dte_threshold_feedback.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_replay_summary", "zero_dte_replay/zero_dte_replay_summary.json", "artifacts/zero_dte_replay/zero_dte_replay_summary.json", True, audit_profiles + full_profiles),
        ("zero_dte_replay_proof", "zero_dte_replay/zero_dte_replay_proof.jsonl", "artifacts/zero_dte_replay/zero_dte_replay_proof.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_threshold_feedback_aggregate", "zero_dte_threshold_optimizer/threshold_feedback_aggregate.json", "artifacts/zero_dte_threshold_optimizer/threshold_feedback_aggregate.json", True, audit_profiles + full_profiles),
        ("zero_dte_threshold_candidates", "zero_dte_threshold_optimizer/threshold_candidates.jsonl", "artifacts/zero_dte_threshold_optimizer/threshold_candidates.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_shadow_replay_results", "zero_dte_threshold_optimizer/shadow_replay_results.jsonl", "artifacts/zero_dte_threshold_optimizer/shadow_replay_results.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_threshold_optimization_decisions", "zero_dte_threshold_optimizer/optimization_decisions.jsonl", "artifacts/zero_dte_threshold_optimizer/optimization_decisions.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_recommended_threshold_profile", "zero_dte_threshold_optimizer/recommended_threshold_profile.json", "artifacts/zero_dte_threshold_optimizer/recommended_threshold_profile.json", True, audit_profiles + full_profiles),
        ("zero_dte_rejected_threshold_profiles", "zero_dte_threshold_optimizer/rejected_threshold_profiles.jsonl", "artifacts/zero_dte_threshold_optimizer/rejected_threshold_profiles.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_threshold_optimizer_summary", "zero_dte_threshold_optimizer/threshold_optimizer_summary.json", "artifacts/zero_dte_threshold_optimizer/threshold_optimizer_summary.json", True, audit_profiles + full_profiles),
        ("zero_dte_threshold_optimizer_proof", "zero_dte_threshold_optimizer/threshold_optimizer_proof.jsonl", "artifacts/zero_dte_threshold_optimizer/threshold_optimizer_proof.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_adversarial_fixture_cases", "zero_dte_adversarial_corpus/adversarial_fixture_cases.json", "artifacts/zero_dte_adversarial_corpus/adversarial_fixture_cases.json", True, audit_profiles + full_profiles),
        ("zero_dte_adversarial_intraday_paths", "zero_dte_adversarial_corpus/adversarial_intraday_paths.json", "artifacts/zero_dte_adversarial_corpus/adversarial_intraday_paths.json", True, audit_profiles + full_profiles),
        ("zero_dte_adversarial_replay_outcomes", "zero_dte_adversarial_corpus/adversarial_replay_outcomes.jsonl", "artifacts/zero_dte_adversarial_corpus/adversarial_replay_outcomes.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_adversarial_threshold_feedback", "zero_dte_adversarial_corpus/adversarial_threshold_feedback.jsonl", "artifacts/zero_dte_adversarial_corpus/adversarial_threshold_feedback.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_adversarial_optimizer_effects", "zero_dte_adversarial_corpus/adversarial_optimizer_effects.jsonl", "artifacts/zero_dte_adversarial_corpus/adversarial_optimizer_effects.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_adversarial_coverage_summary", "zero_dte_adversarial_corpus/adversarial_coverage_summary.json", "artifacts/zero_dte_adversarial_corpus/adversarial_coverage_summary.json", True, audit_profiles + full_profiles),
        ("zero_dte_combined_replay_summary", "zero_dte_adversarial_corpus/combined_replay_summary.json", "artifacts/zero_dte_adversarial_corpus/combined_replay_summary.json", True, audit_profiles + full_profiles),
        ("zero_dte_adversarial_corpus_proof", "zero_dte_adversarial_corpus/adversarial_corpus_proof.jsonl", "artifacts/zero_dte_adversarial_corpus/adversarial_corpus_proof.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_underlying_families", "zero_dte_cross_underlying_v2/underlying_families.json", "artifacts/zero_dte_cross_underlying_v2/underlying_families.json", True, audit_profiles + full_profiles),
        ("zero_dte_cross_underlying_regime_cases", "zero_dte_cross_underlying_v2/cross_underlying_regime_cases.json", "artifacts/zero_dte_cross_underlying_v2/cross_underlying_regime_cases.json", True, audit_profiles + full_profiles),
        ("zero_dte_cross_underlying_intraday_paths", "zero_dte_cross_underlying_v2/cross_underlying_intraday_paths.json", "artifacts/zero_dte_cross_underlying_v2/cross_underlying_intraday_paths.json", True, audit_profiles + full_profiles),
        ("zero_dte_cross_underlying_replay_outcomes", "zero_dte_cross_underlying_v2/cross_underlying_replay_outcomes.jsonl", "artifacts/zero_dte_cross_underlying_v2/cross_underlying_replay_outcomes.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_cross_underlying_threshold_feedback", "zero_dte_cross_underlying_v2/cross_underlying_threshold_feedback.jsonl", "artifacts/zero_dte_cross_underlying_v2/cross_underlying_threshold_feedback.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_cross_underlying_optimizer_effects", "zero_dte_cross_underlying_v2/cross_underlying_optimizer_effects.jsonl", "artifacts/zero_dte_cross_underlying_v2/cross_underlying_optimizer_effects.jsonl", True, audit_profiles + full_profiles),
        ("zero_dte_cross_underlying_coverage_summary", "zero_dte_cross_underlying_v2/cross_underlying_coverage_summary.json", "artifacts/zero_dte_cross_underlying_v2/cross_underlying_coverage_summary.json", True, audit_profiles + full_profiles),
        ("zero_dte_combined_v1_v2_replay_summary", "zero_dte_cross_underlying_v2/combined_v1_v2_replay_summary.json", "artifacts/zero_dte_cross_underlying_v2/combined_v1_v2_replay_summary.json", True, audit_profiles + full_profiles),
        ("zero_dte_cross_underlying_threshold_survival", "zero_dte_cross_underlying_v2/cross_underlying_threshold_survival.json", "artifacts/zero_dte_cross_underlying_v2/cross_underlying_threshold_survival.json", True, audit_profiles + full_profiles),
        ("zero_dte_cross_underlying_corpus_proof", "zero_dte_cross_underlying_v2/cross_underlying_corpus_proof.jsonl", "artifacts/zero_dte_cross_underlying_v2/cross_underlying_corpus_proof.jsonl", True, audit_profiles + full_profiles),
        ("hybrid_underlying_families", "hybrid_swing_0dte_v3/hybrid_underlying_families.json", "artifacts/hybrid_swing_0dte_v3/hybrid_underlying_families.json", True, audit_profiles + full_profiles),
        ("hybrid_swing_candidates", "hybrid_swing_0dte_v3/hybrid_swing_candidates.json", "artifacts/hybrid_swing_0dte_v3/hybrid_swing_candidates.json", True, audit_profiles + full_profiles),
        ("hybrid_opportunity_pairs", "hybrid_swing_0dte_v3/hybrid_opportunity_pairs.json", "artifacts/hybrid_swing_0dte_v3/hybrid_opportunity_pairs.json", True, audit_profiles + full_profiles),
        ("hybrid_multi_day_paths", "hybrid_swing_0dte_v3/hybrid_multi_day_paths.json", "artifacts/hybrid_swing_0dte_v3/hybrid_multi_day_paths.json", True, audit_profiles + full_profiles),
        ("hybrid_replay_outcomes", "hybrid_swing_0dte_v3/hybrid_replay_outcomes.jsonl", "artifacts/hybrid_swing_0dte_v3/hybrid_replay_outcomes.jsonl", True, audit_profiles + full_profiles),
        ("hybrid_preference_scores", "hybrid_swing_0dte_v3/hybrid_preference_scores.jsonl", "artifacts/hybrid_swing_0dte_v3/hybrid_preference_scores.jsonl", True, audit_profiles + full_profiles),
        ("hybrid_allocator_tags", "hybrid_swing_0dte_v3/hybrid_allocator_tags.jsonl", "artifacts/hybrid_swing_0dte_v3/hybrid_allocator_tags.jsonl", True, audit_profiles + full_profiles),
        ("hybrid_coverage_summary", "hybrid_swing_0dte_v3/hybrid_coverage_summary.json", "artifacts/hybrid_swing_0dte_v3/hybrid_coverage_summary.json", True, audit_profiles + full_profiles),
        ("hybrid_threshold_survival", "hybrid_swing_0dte_v3/hybrid_threshold_survival.json", "artifacts/hybrid_swing_0dte_v3/hybrid_threshold_survival.json", True, audit_profiles + full_profiles),
        ("hybrid_replay_summary", "hybrid_swing_0dte_v3/hybrid_replay_summary.json", "artifacts/hybrid_swing_0dte_v3/hybrid_replay_summary.json", True, audit_profiles + full_profiles),
        ("hybrid_corpus_proof", "hybrid_swing_0dte_v3/hybrid_corpus_proof.jsonl", "artifacts/hybrid_swing_0dte_v3/hybrid_corpus_proof.jsonl", True, audit_profiles + full_profiles),
        ("proof_weighted_opportunities", "allocation/proof_weighted_opportunities.jsonl", "artifacts/allocation/proof_weighted_opportunities.jsonl", True, audit_profiles + full_profiles),
        ("paper_allocation_policy", "allocation/paper_allocation_policy.json", "artifacts/allocation/paper_allocation_policy.json", True, audit_profiles + full_profiles),
        ("paper_risk_budget", "allocation/paper_risk_budget.json", "artifacts/allocation/paper_risk_budget.json", True, audit_profiles + full_profiles),
        ("paper_allocation_decisions", "allocation/paper_allocation_decisions.jsonl", "artifacts/allocation/paper_allocation_decisions.jsonl", True, audit_profiles + full_profiles),
        ("paper_allocation_plan", "allocation/paper_allocation_plan.json", "artifacts/allocation/paper_allocation_plan.json", True, audit_profiles + full_profiles),
        ("allocation_rejections", "allocation/allocation_rejections.jsonl", "artifacts/allocation/allocation_rejections.jsonl", True, audit_profiles + full_profiles),
        ("allocation_watchlist", "allocation/allocation_watchlist.jsonl", "artifacts/allocation/allocation_watchlist.jsonl", True, audit_profiles + full_profiles),
        ("allocation_exposure_summary", "allocation/allocation_exposure_summary.json", "artifacts/allocation/allocation_exposure_summary.json", True, audit_profiles + full_profiles),
        ("allocation_constraint_summary", "allocation/allocation_constraint_summary.json", "artifacts/allocation/allocation_constraint_summary.json", True, audit_profiles + full_profiles),
        ("allocation_proof", "allocation/allocation_proof.jsonl", "artifacts/allocation/allocation_proof.jsonl", True, audit_profiles + full_profiles),
        ("portfolio_replay_policy", "portfolio_replay/portfolio_replay_policy.json", "artifacts/portfolio_replay/portfolio_replay_policy.json", True, audit_profiles + full_profiles),
        ("portfolio_replay_opportunities", "portfolio_replay/portfolio_replay_opportunities.jsonl", "artifacts/portfolio_replay/portfolio_replay_opportunities.jsonl", True, audit_profiles + full_profiles),
        ("portfolio_states", "portfolio_replay/portfolio_states.jsonl", "artifacts/portfolio_replay/portfolio_states.jsonl", True, audit_profiles + full_profiles),
        ("portfolio_positions", "portfolio_replay/portfolio_positions.jsonl", "artifacts/portfolio_replay/portfolio_positions.jsonl", True, audit_profiles + full_profiles),
        ("portfolio_rotation_decisions", "portfolio_replay/portfolio_rotation_decisions.jsonl", "artifacts/portfolio_replay/portfolio_rotation_decisions.jsonl", True, audit_profiles + full_profiles),
        ("portfolio_exposure_snapshots", "portfolio_replay/portfolio_exposure_snapshots.jsonl", "artifacts/portfolio_replay/portfolio_exposure_snapshots.jsonl", True, audit_profiles + full_profiles),
        ("exposure_stress_results", "portfolio_replay/exposure_stress_results.jsonl", "artifacts/portfolio_replay/exposure_stress_results.jsonl", True, audit_profiles + full_profiles),
        ("portfolio_allocator_feedback", "portfolio_replay/portfolio_allocator_feedback.jsonl", "artifacts/portfolio_replay/portfolio_allocator_feedback.jsonl", True, audit_profiles + full_profiles),
        ("portfolio_threshold_feedback", "portfolio_replay/portfolio_threshold_feedback.jsonl", "artifacts/portfolio_replay/portfolio_threshold_feedback.jsonl", True, audit_profiles + full_profiles),
        ("portfolio_replay_summary", "portfolio_replay/portfolio_replay_summary.json", "artifacts/portfolio_replay/portfolio_replay_summary.json", True, audit_profiles + full_profiles),
        ("portfolio_replay_proof", "portfolio_replay/portfolio_replay_proof.jsonl", "artifacts/portfolio_replay/portfolio_replay_proof.jsonl", True, audit_profiles + full_profiles),
        ("portfolio_stress_ladder_policy", "portfolio_stress_ladder/stress_ladder_policy.json", "artifacts/portfolio_stress_ladder/stress_ladder_policy.json", True, audit_profiles + full_profiles),
        ("crisis_mode_throttle_profiles", "portfolio_stress_ladder/crisis_mode_throttle_profiles.json", "artifacts/portfolio_stress_ladder/crisis_mode_throttle_profiles.json", True, audit_profiles + full_profiles),
        ("stress_ladder_replay_cases", "portfolio_stress_ladder/stress_ladder_replay_cases.json", "artifacts/portfolio_stress_ladder/stress_ladder_replay_cases.json", True, audit_profiles + full_profiles),
        ("stress_level_evaluations", "portfolio_stress_ladder/stress_level_evaluations.jsonl", "artifacts/portfolio_stress_ladder/stress_level_evaluations.jsonl", True, audit_profiles + full_profiles),
        ("stress_transition_decisions", "portfolio_stress_ladder/stress_transition_decisions.jsonl", "artifacts/portfolio_stress_ladder/stress_transition_decisions.jsonl", True, audit_profiles + full_profiles),
        ("crisis_throttle_results", "portfolio_stress_ladder/crisis_throttle_results.jsonl", "artifacts/portfolio_stress_ladder/crisis_throttle_results.jsonl", True, audit_profiles + full_profiles),
        ("crisis_recovery_results", "portfolio_stress_ladder/crisis_recovery_results.jsonl", "artifacts/portfolio_stress_ladder/crisis_recovery_results.jsonl", True, audit_profiles + full_profiles),
        ("crisis_allocator_feedback", "portfolio_stress_ladder/crisis_allocator_feedback.jsonl", "artifacts/portfolio_stress_ladder/crisis_allocator_feedback.jsonl", True, audit_profiles + full_profiles),
        ("crisis_threshold_feedback", "portfolio_stress_ladder/crisis_threshold_feedback.jsonl", "artifacts/portfolio_stress_ladder/crisis_threshold_feedback.jsonl", True, audit_profiles + full_profiles),
        ("stress_ladder_summary", "portfolio_stress_ladder/stress_ladder_summary.json", "artifacts/portfolio_stress_ladder/stress_ladder_summary.json", True, audit_profiles + full_profiles),
        ("stress_ladder_proof", "portfolio_stress_ladder/stress_ladder_proof.jsonl", "artifacts/portfolio_stress_ladder/stress_ladder_proof.jsonl", True, audit_profiles + full_profiles),
        ("incident_taxonomy", "incident_response/incident_taxonomy.json", "artifacts/incident_response/incident_taxonomy.json", True, audit_profiles + full_profiles),
        ("incident_rehearsal_cases", "incident_response/incident_rehearsal_cases.json", "artifacts/incident_response/incident_rehearsal_cases.json", True, audit_profiles + full_profiles),
        ("incident_signals", "incident_response/incident_signals.jsonl", "artifacts/incident_response/incident_signals.jsonl", True, audit_profiles + full_profiles),
        ("kill_switch_states", "incident_response/kill_switch_states.jsonl", "artifacts/incident_response/kill_switch_states.jsonl", True, audit_profiles + full_profiles),
        ("incident_response_decisions", "incident_response/incident_response_decisions.jsonl", "artifacts/incident_response/incident_response_decisions.jsonl", True, audit_profiles + full_profiles),
        ("incident_recovery_plans", "incident_response/incident_recovery_plans.jsonl", "artifacts/incident_response/incident_recovery_plans.jsonl", True, audit_profiles + full_profiles),
        ("incident_allocator_feedback", "incident_response/incident_allocator_feedback.jsonl", "artifacts/incident_response/incident_allocator_feedback.jsonl", True, audit_profiles + full_profiles),
        ("incident_threshold_feedback", "incident_response/incident_threshold_feedback.jsonl", "artifacts/incident_response/incident_threshold_feedback.jsonl", True, audit_profiles + full_profiles),
        ("incident_stress_ladder_feedback", "incident_response/incident_stress_ladder_feedback.jsonl", "artifacts/incident_response/incident_stress_ladder_feedback.jsonl", True, audit_profiles + full_profiles),
        ("incident_rehearsal_summary", "incident_response/incident_rehearsal_summary.json", "artifacts/incident_response/incident_rehearsal_summary.json", True, audit_profiles + full_profiles),
        ("incident_response_proof", "incident_response/incident_response_proof.jsonl", "artifacts/incident_response/incident_response_proof.jsonl", True, audit_profiles + full_profiles),
        ("lifecycle_policy", "lifecycle/lifecycle_policy.json", "artifacts/lifecycle/lifecycle_policy.json", True, audit_profiles + full_profiles),
        ("lifecycle_cases", "lifecycle/lifecycle_cases.json", "artifacts/lifecycle/lifecycle_cases.json", True, audit_profiles + full_profiles),
        ("lifecycle_states", "lifecycle/lifecycle_states.jsonl", "artifacts/lifecycle/lifecycle_states.jsonl", True, audit_profiles + full_profiles),
        ("lifecycle_transitions", "lifecycle/lifecycle_transitions.jsonl", "artifacts/lifecycle/lifecycle_transitions.jsonl", True, audit_profiles + full_profiles),
        ("lifecycle_proof", "lifecycle/lifecycle_proof.jsonl", "artifacts/lifecycle/lifecycle_proof.jsonl", True, audit_profiles + full_profiles),
        ("lifecycle_paperbroker_results", "lifecycle/lifecycle_paperbroker_results.jsonl", "artifacts/lifecycle/lifecycle_paperbroker_results.jsonl", True, audit_profiles + full_profiles),
        ("lifecycle_account_ledger_results", "lifecycle/lifecycle_account_ledger_results.jsonl", "artifacts/lifecycle/lifecycle_account_ledger_results.jsonl", True, audit_profiles + full_profiles),
        ("lifecycle_feedback_allocator", "lifecycle/lifecycle_feedback_allocator.jsonl", "artifacts/lifecycle/lifecycle_feedback_allocator.jsonl", True, audit_profiles + full_profiles),
        ("lifecycle_feedback_portfolio", "lifecycle/lifecycle_feedback_portfolio.jsonl", "artifacts/lifecycle/lifecycle_feedback_portfolio.jsonl", True, audit_profiles + full_profiles),
        ("lifecycle_feedback_stress_ladder", "lifecycle/lifecycle_feedback_stress_ladder.jsonl", "artifacts/lifecycle/lifecycle_feedback_stress_ladder.jsonl", True, audit_profiles + full_profiles),
        ("lifecycle_feedback_incident", "lifecycle/lifecycle_feedback_incident.jsonl", "artifacts/lifecycle/lifecycle_feedback_incident.jsonl", True, audit_profiles + full_profiles),
        ("lifecycle_summary", "lifecycle/lifecycle_summary.json", "artifacts/lifecycle/lifecycle_summary.json", True, audit_profiles + full_profiles),
        ("broker_readiness_preflight_checks", "broker_readiness/broker_preflight_checks.jsonl", "artifacts/broker_readiness/broker_preflight_checks.jsonl", True, audit_profiles + full_profiles),
        ("read_only_boundary_simulations", "broker_readiness/read_only_boundary_simulations.jsonl", "artifacts/broker_readiness/read_only_boundary_simulations.jsonl", True, audit_profiles + full_profiles),
        ("broker_capability_fixtures", "broker_readiness/broker_capability_fixtures.json", "artifacts/broker_readiness/broker_capability_fixtures.json", True, audit_profiles + full_profiles),
        ("broker_readiness_run_result", "broker_readiness/broker_readiness_run_result.json", "artifacts/broker_readiness/broker_readiness_run_result.json", True, audit_profiles + full_profiles),
        ("broker_readiness_boundary_blocks", "broker_readiness/broker_readiness_boundary_blocks.jsonl", "artifacts/broker_readiness/broker_readiness_boundary_blocks.jsonl", True, audit_profiles + full_profiles),
        ("broker_readiness_manual_gates", "broker_readiness/broker_readiness_manual_gates.json", "artifacts/broker_readiness/broker_readiness_manual_gates.json", True, audit_profiles + full_profiles),
        ("broker_readiness_summary", "broker_readiness/broker_readiness_summary.json", "artifacts/broker_readiness/broker_readiness_summary.json", True, audit_profiles + full_profiles),
        ("broker_readiness_proof", "broker_readiness/broker_readiness_proof.jsonl", "artifacts/broker_readiness/broker_readiness_proof.jsonl", True, audit_profiles + full_profiles),
        ("read_only_detector_scope", "broker_readiness/manual_approval/read_only_detector_scope.json", "artifacts/broker_readiness/manual_approval/read_only_detector_scope.json", True, audit_profiles + full_profiles),
        ("manual_approval_gate", "broker_readiness/manual_approval/manual_approval_gate.json", "artifacts/broker_readiness/manual_approval/manual_approval_gate.json", True, audit_profiles + full_profiles),
        ("read_only_detector_approval_packet", "broker_readiness/manual_approval/read_only_detector_approval_packet.json", "artifacts/broker_readiness/manual_approval/read_only_detector_approval_packet.json", True, audit_profiles + full_profiles),
        ("operator_acknowledgement_required", "broker_readiness/manual_approval/operator_acknowledgement_required.md", "artifacts/broker_readiness/manual_approval/operator_acknowledgement_required.md", True, audit_profiles + full_profiles),
        ("future_detector_command_templates", "broker_readiness/manual_approval/future_detector_command_templates.jsonl", "artifacts/broker_readiness/manual_approval/future_detector_command_templates.jsonl", True, audit_profiles + full_profiles),
        ("manual_gate_validation_results", "broker_readiness/manual_approval/manual_gate_validation_results.jsonl", "artifacts/broker_readiness/manual_approval/manual_gate_validation_results.jsonl", True, audit_profiles + full_profiles),
        ("manual_approval_boundary_blocks", "broker_readiness/manual_approval/manual_approval_boundary_blocks.jsonl", "artifacts/broker_readiness/manual_approval/manual_approval_boundary_blocks.jsonl", True, audit_profiles + full_profiles),
        ("manual_approval_packet_summary", "broker_readiness/manual_approval/manual_approval_packet_summary.json", "artifacts/broker_readiness/manual_approval/manual_approval_packet_summary.json", True, audit_profiles + full_profiles),
        ("manual_approval_packet_proof", "broker_readiness/manual_approval/manual_approval_packet_proof.jsonl", "artifacts/broker_readiness/manual_approval/manual_approval_packet_proof.jsonl", True, audit_profiles + full_profiles),
        ("read_only_detector_dry_run_inputs", "broker_readiness/dry_run/read_only_detector_dry_run_inputs.jsonl", "artifacts/broker_readiness/dry_run/read_only_detector_dry_run_inputs.jsonl", True, audit_profiles + full_profiles),
        ("simulated_broker_capability_responses", "broker_readiness/dry_run/simulated_broker_capability_responses.jsonl", "artifacts/broker_readiness/dry_run/simulated_broker_capability_responses.jsonl", True, audit_profiles + full_profiles),
        ("simulated_read_only_shapes", "broker_readiness/dry_run/simulated_read_only_shapes.json", "artifacts/broker_readiness/dry_run/simulated_read_only_shapes.json", True, audit_profiles + full_profiles),
        ("simulated_forbidden_shapes", "broker_readiness/dry_run/simulated_forbidden_shapes.json", "artifacts/broker_readiness/dry_run/simulated_forbidden_shapes.json", True, audit_profiles + full_profiles),
        ("read_only_detector_dry_run_results", "broker_readiness/dry_run/read_only_detector_dry_run_results.jsonl", "artifacts/broker_readiness/dry_run/read_only_detector_dry_run_results.jsonl", True, audit_profiles + full_profiles),
        ("dry_run_boundary_blocks", "broker_readiness/dry_run/dry_run_boundary_blocks.jsonl", "artifacts/broker_readiness/dry_run/dry_run_boundary_blocks.jsonl", True, audit_profiles + full_profiles),
        ("future_detector_contract", "broker_readiness/dry_run/future_detector_contract.md", "artifacts/broker_readiness/dry_run/future_detector_contract.md", True, audit_profiles + full_profiles),
        ("read_only_detector_dry_run_summary", "broker_readiness/dry_run/read_only_detector_dry_run_summary.json", "artifacts/broker_readiness/dry_run/read_only_detector_dry_run_summary.json", True, audit_profiles + full_profiles),
        ("read_only_detector_dry_run_proof", "broker_readiness/dry_run/read_only_detector_dry_run_proof.jsonl", "artifacts/broker_readiness/dry_run/read_only_detector_dry_run_proof.jsonl", True, audit_profiles + full_profiles),
        ("approval_intake_requests", "broker_readiness/approval_intake/approval_intake_requests.jsonl", "artifacts/broker_readiness/approval_intake/approval_intake_requests.jsonl", True, audit_profiles + full_profiles),
        ("approval_scope_validations", "broker_readiness/approval_intake/approval_scope_validations.jsonl", "artifacts/broker_readiness/approval_intake/approval_scope_validations.jsonl", True, audit_profiles + full_profiles),
        ("approval_intake_results", "broker_readiness/approval_intake/approval_intake_results.jsonl", "artifacts/broker_readiness/approval_intake/approval_intake_results.jsonl", True, audit_profiles + full_profiles),
        ("approval_forbidden_terms", "broker_readiness/approval_intake/approval_forbidden_terms.json", "artifacts/broker_readiness/approval_intake/approval_forbidden_terms.json", True, audit_profiles + full_profiles),
        ("approval_boundary_blocks", "broker_readiness/approval_intake/approval_boundary_blocks.jsonl", "artifacts/broker_readiness/approval_intake/approval_boundary_blocks.jsonl", True, audit_profiles + full_profiles),
        ("approval_incident_escalations", "broker_readiness/approval_intake/approval_incident_escalations.jsonl", "artifacts/broker_readiness/approval_intake/approval_incident_escalations.jsonl", True, audit_profiles + full_profiles),
        ("approval_intake_summary", "broker_readiness/approval_intake/approval_intake_summary.json", "artifacts/broker_readiness/approval_intake/approval_intake_summary.json", True, audit_profiles + full_profiles),
        ("approval_intake_proof", "broker_readiness/approval_intake/approval_intake_proof.jsonl", "artifacts/broker_readiness/approval_intake/approval_intake_proof.jsonl", True, audit_profiles + full_profiles),
        ("handoff_inputs", "broker_readiness/approval_to_run_handoff/handoff_inputs.jsonl", "artifacts/broker_readiness/approval_to_run_handoff/handoff_inputs.jsonl", True, audit_profiles + full_profiles),
        ("future_detector_run_envelopes", "broker_readiness/approval_to_run_handoff/future_detector_run_envelopes.jsonl", "artifacts/broker_readiness/approval_to_run_handoff/future_detector_run_envelopes.jsonl", True, audit_profiles + full_profiles),
        ("approval_to_run_gate_decisions", "broker_readiness/approval_to_run_handoff/approval_to_run_gate_decisions.jsonl", "artifacts/broker_readiness/approval_to_run_handoff/approval_to_run_gate_decisions.jsonl", True, audit_profiles + full_profiles),
        ("disabled_handoff_command_templates", "broker_readiness/approval_to_run_handoff/disabled_handoff_command_templates.jsonl", "artifacts/broker_readiness/approval_to_run_handoff/disabled_handoff_command_templates.jsonl", True, audit_profiles + full_profiles),
        ("handoff_boundary_blocks", "broker_readiness/approval_to_run_handoff/handoff_boundary_blocks.jsonl", "artifacts/broker_readiness/approval_to_run_handoff/handoff_boundary_blocks.jsonl", True, audit_profiles + full_profiles),
        ("handoff_incident_escalations", "broker_readiness/approval_to_run_handoff/handoff_incident_escalations.jsonl", "artifacts/broker_readiness/approval_to_run_handoff/handoff_incident_escalations.jsonl", True, audit_profiles + full_profiles),
        ("approval_to_run_handoff_summary", "broker_readiness/approval_to_run_handoff/approval_to_run_handoff_summary.json", "artifacts/broker_readiness/approval_to_run_handoff/approval_to_run_handoff_summary.json", True, audit_profiles + full_profiles),
        ("approval_to_run_handoff_proof", "broker_readiness/approval_to_run_handoff/approval_to_run_handoff_proof.jsonl", "artifacts/broker_readiness/approval_to_run_handoff/approval_to_run_handoff_proof.jsonl", True, audit_profiles + full_profiles),
        ("pre_run_safety_scan_inputs", "broker_readiness/pre_run_safety/pre_run_safety_scan_inputs.jsonl", "artifacts/broker_readiness/pre_run_safety/pre_run_safety_scan_inputs.jsonl", True, audit_profiles + full_profiles),
        ("pre_run_boundary_scan_results", "broker_readiness/pre_run_safety/pre_run_boundary_scan_results.jsonl", "artifacts/broker_readiness/pre_run_safety/pre_run_boundary_scan_results.jsonl", True, audit_profiles + full_profiles),
        ("pre_run_safety_decisions", "broker_readiness/pre_run_safety/pre_run_safety_decisions.jsonl", "artifacts/broker_readiness/pre_run_safety/pre_run_safety_decisions.jsonl", True, audit_profiles + full_profiles),
        ("pre_run_forbidden_boundary_patterns", "broker_readiness/pre_run_safety/pre_run_forbidden_boundary_patterns.json", "artifacts/broker_readiness/pre_run_safety/pre_run_forbidden_boundary_patterns.json", True, audit_profiles + full_profiles),
        ("pre_run_boundary_classifications", "broker_readiness/pre_run_safety/pre_run_boundary_classifications.jsonl", "artifacts/broker_readiness/pre_run_safety/pre_run_boundary_classifications.jsonl", True, audit_profiles + full_profiles),
        ("pre_run_incident_escalations", "broker_readiness/pre_run_safety/pre_run_incident_escalations.jsonl", "artifacts/broker_readiness/pre_run_safety/pre_run_incident_escalations.jsonl", True, audit_profiles + full_profiles),
        ("pre_run_safety_summary", "broker_readiness/pre_run_safety/pre_run_safety_summary.json", "artifacts/broker_readiness/pre_run_safety/pre_run_safety_summary.json", True, audit_profiles + full_profiles),
        ("pre_run_safety_proof", "broker_readiness/pre_run_safety/pre_run_safety_proof.jsonl", "artifacts/broker_readiness/pre_run_safety/pre_run_safety_proof.jsonl", True, audit_profiles + full_profiles),
        ("read_only_detector_run_requests", "broker_readiness/read_only_detector/read_only_detector_run_requests.jsonl", "artifacts/broker_readiness/read_only_detector/read_only_detector_run_requests.jsonl", True, audit_profiles + full_profiles),
        ("read_only_capability_records", "broker_readiness/read_only_detector/read_only_capability_records.jsonl", "artifacts/broker_readiness/read_only_detector/read_only_capability_records.jsonl", True, audit_profiles + full_profiles),
        ("read_only_blocked_write_execute_records", "broker_readiness/read_only_detector/read_only_blocked_write_execute_records.jsonl", "artifacts/broker_readiness/read_only_detector/read_only_blocked_write_execute_records.jsonl", True, audit_profiles + full_profiles),
        ("read_only_provider_boundary_results", "broker_readiness/read_only_detector/read_only_provider_boundary_results.jsonl", "artifacts/broker_readiness/read_only_detector/read_only_provider_boundary_results.jsonl", True, audit_profiles + full_profiles),
        ("read_only_detector_run_results", "broker_readiness/read_only_detector/read_only_detector_run_results.jsonl", "artifacts/broker_readiness/read_only_detector/read_only_detector_run_results.jsonl", True, audit_profiles + full_profiles),
        ("read_only_detector_post_run_evidence", "broker_readiness/read_only_detector/read_only_detector_post_run_evidence.json", "artifacts/broker_readiness/read_only_detector/read_only_detector_post_run_evidence.json", True, audit_profiles + full_profiles),
        ("read_only_detector_incident_escalations", "broker_readiness/read_only_detector/read_only_detector_incident_escalations.jsonl", "artifacts/broker_readiness/read_only_detector/read_only_detector_incident_escalations.jsonl", True, audit_profiles + full_profiles),
        ("read_only_detector_summary", "broker_readiness/read_only_detector/read_only_detector_summary.json", "artifacts/broker_readiness/read_only_detector/read_only_detector_summary.json", True, audit_profiles + full_profiles),
        ("read_only_detector_proof", "broker_readiness/read_only_detector/read_only_detector_proof.jsonl", "artifacts/broker_readiness/read_only_detector/read_only_detector_proof.jsonl", True, audit_profiles + full_profiles),
        ("evidence_contract", "broker_readiness/evidence_contract/evidence_contract.json", "artifacts/broker_readiness/evidence_contract/evidence_contract.json", True, audit_profiles + full_profiles),
        ("evidence_items", "broker_readiness/evidence_contract/evidence_items.jsonl", "artifacts/broker_readiness/evidence_contract/evidence_items.jsonl", True, audit_profiles + full_profiles),
        ("boundary_assertions", "broker_readiness/evidence_contract/boundary_assertions.jsonl", "artifacts/broker_readiness/evidence_contract/boundary_assertions.jsonl", True, audit_profiles + full_profiles),
        ("evidence_validation_results", "broker_readiness/evidence_contract/evidence_validation_results.jsonl", "artifacts/broker_readiness/evidence_contract/evidence_validation_results.jsonl", True, audit_profiles + full_profiles),
        ("evidence_promotion_decisions", "broker_readiness/evidence_contract/evidence_promotion_decisions.jsonl", "artifacts/broker_readiness/evidence_contract/evidence_promotion_decisions.jsonl", True, audit_profiles + full_profiles),
        ("evidence_contract_summary", "broker_readiness/evidence_contract/evidence_contract_summary.json", "artifacts/broker_readiness/evidence_contract/evidence_contract_summary.json", True, audit_profiles + full_profiles),
        ("evidence_contract_proof", "broker_readiness/evidence_contract/evidence_contract_proof.jsonl", "artifacts/broker_readiness/evidence_contract/evidence_contract_proof.jsonl", True, audit_profiles + full_profiles),
        ("history_dataset_manifest", "history/history_dataset_manifest.json", "artifacts/history/history_dataset_manifest.json", True, audit_profiles + full_profiles),
        ("history_dataset_validation", "history/history_dataset_validation.json", "artifacts/history/history_dataset_validation.json", True, audit_profiles + full_profiles),
        ("history_symbol_coverage", "history/history_symbol_coverage.jsonl", "artifacts/history/history_symbol_coverage.jsonl", True, audit_profiles + full_profiles),
        ("history_quality_flags", "history/history_quality_flags.jsonl", "artifacts/history/history_quality_flags.jsonl", True, audit_profiles + full_profiles),
        ("history_loader_proof", "history/history_loader_proof.jsonl", "artifacts/history/history_loader_proof.jsonl", True, audit_profiles + full_profiles),
        ("history_spine_summary", "history/history_spine_summary.json", "artifacts/history/history_spine_summary.json", True, audit_profiles + full_profiles),
        ("iv_solver_validation", "model_repricing/iv_solver_validation.json", "artifacts/model_repricing/iv_solver_validation.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("vol_surface_model", "model_repricing/vol_surface_model.json", "artifacts/model_repricing/vol_surface_model.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("model_repricing_cases", "model_repricing/model_repricing_cases.jsonl", "artifacts/model_repricing/model_repricing_cases.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("model_repricing_results", "model_repricing/model_repricing_results.jsonl", "artifacts/model_repricing/model_repricing_results.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("model_repricing_quality_flags", "model_repricing/model_repricing_quality_flags.jsonl", "artifacts/model_repricing/model_repricing_quality_flags.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("model_repricing_summary", "model_repricing/model_repricing_summary.json", "artifacts/model_repricing/model_repricing_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("model_repricing_proof", "model_repricing/model_repricing_proof.jsonl", "artifacts/model_repricing/model_repricing_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("signal_engine_input_summary", "signals/signal_engine_input_summary.json", "artifacts/signals/signal_engine_input_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("momentum_signals", "signals/momentum_signals.jsonl", "artifacts/signals/momentum_signals.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("breakout_signals", "signals/breakout_signals.jsonl", "artifacts/signals/breakout_signals.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("fakeout_signals", "signals/fakeout_signals.jsonl", "artifacts/signals/fakeout_signals.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("trend_pullback_signals", "signals/trend_pullback_signals.jsonl", "artifacts/signals/trend_pullback_signals.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("volatility_regime_signals", "signals/volatility_regime_signals.jsonl", "artifacts/signals/volatility_regime_signals.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("relative_strength_signals", "signals/relative_strength_signals.jsonl", "artifacts/signals/relative_strength_signals.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("market_regime_signals", "signals/market_regime_signals.jsonl", "artifacts/signals/market_regime_signals.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("directional_setup_signals", "signals/directional_setup_signals.jsonl", "artifacts/signals/directional_setup_signals.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("signal_quality_flags", "signals/signal_quality_flags.jsonl", "artifacts/signals/signal_quality_flags.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("signal_engine_summary", "signals/signal_engine_summary.json", "artifacts/signals/signal_engine_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("signal_engine_proof", "signals/signal_engine_proof.jsonl", "artifacts/signals/signal_engine_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("backtest_signal_inputs", "backtest/backtest_signal_inputs.jsonl", "artifacts/backtest/backtest_signal_inputs.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("backtest_trade_intents", "backtest/backtest_trade_intents.jsonl", "artifacts/backtest/backtest_trade_intents.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("backtest_entry_decisions", "backtest/backtest_entry_decisions.jsonl", "artifacts/backtest/backtest_entry_decisions.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("backtest_exit_decisions", "backtest/backtest_exit_decisions.jsonl", "artifacts/backtest/backtest_exit_decisions.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("backtest_position_states", "backtest/backtest_position_states.jsonl", "artifacts/backtest/backtest_position_states.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("backtest_mark_records", "backtest/backtest_mark_records.jsonl", "artifacts/backtest/backtest_mark_records.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("backtest_trade_records", "backtest/backtest_trade_records.jsonl", "artifacts/backtest/backtest_trade_records.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("backtest_quality_flags", "backtest/backtest_quality_flags.jsonl", "artifacts/backtest/backtest_quality_flags.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("backtest_run_summary", "backtest/backtest_run_summary.json", "artifacts/backtest/backtest_run_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("backtest_proof", "backtest/backtest_proof.jsonl", "artifacts/backtest/backtest_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("statistical_truth_input", "stats/statistical_truth_input.json", "artifacts/stats/statistical_truth_input.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("backtest_sample_profile", "stats/backtest_sample_profile.json", "artifacts/stats/backtest_sample_profile.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("backtest_metric_set", "stats/backtest_metric_set.json", "artifacts/stats/backtest_metric_set.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("bootstrap_confidence_intervals", "stats/bootstrap_confidence_intervals.json", "artifacts/stats/bootstrap_confidence_intervals.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("baseline_comparisons", "stats/baseline_comparisons.jsonl", "artifacts/stats/baseline_comparisons.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("multiple_testing_adjustment", "stats/multiple_testing_adjustment.json", "artifacts/stats/multiple_testing_adjustment.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("deflated_sharpe_result", "stats/deflated_sharpe_result.json", "artifacts/stats/deflated_sharpe_result.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("statistical_truth_decision", "stats/statistical_truth_decision.json", "artifacts/stats/statistical_truth_decision.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("statistical_truth_quality_flags", "stats/statistical_truth_quality_flags.jsonl", "artifacts/stats/statistical_truth_quality_flags.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("statistical_truth_summary", "stats/statistical_truth_summary.json", "artifacts/stats/statistical_truth_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("statistical_truth_proof", "stats/statistical_truth_proof.jsonl", "artifacts/stats/statistical_truth_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("fitness_input", "fitness/fitness_input.json", "artifacts/fitness/fitness_input.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("fitness_metric_components", "fitness/fitness_metric_components.jsonl", "artifacts/fitness/fitness_metric_components.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("fitness_penalties", "fitness/fitness_penalties.jsonl", "artifacts/fitness/fitness_penalties.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("fitness_scorecards", "fitness/fitness_scorecards.jsonl", "artifacts/fitness/fitness_scorecards.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("fitness_rank_records", "fitness/fitness_rank_records.jsonl", "artifacts/fitness/fitness_rank_records.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("fitness_promotion_gate", "fitness/fitness_promotion_gate.json", "artifacts/fitness/fitness_promotion_gate.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("fitness_decision", "fitness/fitness_decision.json", "artifacts/fitness/fitness_decision.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("proxy_fitness_quarantine_findings", "fitness/proxy_fitness_quarantine_findings.jsonl", "artifacts/fitness/proxy_fitness_quarantine_findings.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("fitness_quality_flags", "fitness/fitness_quality_flags.jsonl", "artifacts/fitness/fitness_quality_flags.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("fitness_replacement_summary", "fitness/fitness_replacement_summary.json", "artifacts/fitness/fitness_replacement_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("fitness_replacement_proof", "fitness/fitness_replacement_proof.jsonl", "artifacts/fitness/fitness_replacement_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("data_ingestion_plan", "data_ingestion/data_ingestion_plan.json", "artifacts/data_ingestion/data_ingestion_plan.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("dataset_requirements", "data_ingestion/dataset_requirements.jsonl", "artifacts/data_ingestion/dataset_requirements.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("provider_candidates", "data_ingestion/provider_candidates.jsonl", "artifacts/data_ingestion/provider_candidates.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("local_staging_contract", "data_ingestion/local_staging_contract.json", "artifacts/data_ingestion/local_staging_contract.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("schema_contracts", "data_ingestion/schema_contracts.jsonl", "artifacts/data_ingestion/schema_contracts.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("license_provenance_requirements", "data_ingestion/license_provenance_requirements.jsonl", "artifacts/data_ingestion/license_provenance_requirements.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("data_quality_gates", "data_ingestion/data_quality_gates.jsonl", "artifacts/data_ingestion/data_quality_gates.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("import_readiness_decision", "data_ingestion/import_readiness_decision.json", "artifacts/data_ingestion/import_readiness_decision.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("ingestion_plan_quality_flags", "data_ingestion/ingestion_plan_quality_flags.jsonl", "artifacts/data_ingestion/ingestion_plan_quality_flags.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("data_ingestion_plan_summary", "data_ingestion/data_ingestion_plan_summary.json", "artifacts/data_ingestion/data_ingestion_plan_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("data_ingestion_plan_proof", "data_ingestion/data_ingestion_plan_proof.jsonl", "artifacts/data_ingestion/data_ingestion_plan_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("local_ohlcv_import_input", "local_ohlcv_import/local_ohlcv_import_input.json", "artifacts/local_ohlcv_import/local_ohlcv_import_input.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("local_ohlcv_file_inventory", "local_ohlcv_import/local_ohlcv_file_inventory.jsonl", "artifacts/local_ohlcv_import/local_ohlcv_file_inventory.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("local_ohlcv_schema_results", "local_ohlcv_import/local_ohlcv_schema_results.jsonl", "artifacts/local_ohlcv_import/local_ohlcv_schema_results.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("local_ohlcv_quality_results", "local_ohlcv_import/local_ohlcv_quality_results.jsonl", "artifacts/local_ohlcv_import/local_ohlcv_quality_results.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("local_ohlcv_license_provenance_results", "local_ohlcv_import/local_ohlcv_license_provenance_results.jsonl", "artifacts/local_ohlcv_import/local_ohlcv_license_provenance_results.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("local_ohlcv_import_decision", "local_ohlcv_import/local_ohlcv_import_decision.json", "artifacts/local_ohlcv_import/local_ohlcv_import_decision.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("local_ohlcv_import_summary", "local_ohlcv_import/local_ohlcv_import_summary.json", "artifacts/local_ohlcv_import/local_ohlcv_import_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("local_ohlcv_import_proof", "local_ohlcv_import/local_ohlcv_import_proof.jsonl", "artifacts/local_ohlcv_import/local_ohlcv_import_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_ohlcv_history_spine_upgrade", "history/real_ohlcv_history_spine_upgrade.json", "artifacts/history/real_ohlcv_history_spine_upgrade.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_ohlcv_history_spine_activation", "history/real_ohlcv_history_spine_activation.json", "artifacts/history/real_ohlcv_history_spine_activation.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_ohlcv_history_symbol_coverage", "history/real_ohlcv_history_symbol_coverage.jsonl", "artifacts/history/real_ohlcv_history_symbol_coverage.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_ohlcv_history_date_coverage", "history/real_ohlcv_history_date_coverage.jsonl", "artifacts/history/real_ohlcv_history_date_coverage.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_ohlcv_history_quality_flags", "history/real_ohlcv_history_quality_flags.jsonl", "artifacts/history/real_ohlcv_history_quality_flags.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_ohlcv_history_activation_quality_flags", "history/real_ohlcv_history_activation_quality_flags.jsonl", "artifacts/history/real_ohlcv_history_activation_quality_flags.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_ohlcv_history_spine_proof", "history/real_ohlcv_history_spine_proof.jsonl", "artifacts/history/real_ohlcv_history_spine_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_ohlcv_history_activation_proof", "history/real_ohlcv_history_activation_proof.jsonl", "artifacts/history/real_ohlcv_history_activation_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_signal_validation_input", "real_signal_validation/real_signal_validation_input.json", "artifacts/real_signal_validation/real_signal_validation_input.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_signal_records", "real_signal_validation/real_signal_records.jsonl", "artifacts/real_signal_validation/real_signal_records.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_directional_setup_records", "real_signal_validation/real_directional_setup_records.jsonl", "artifacts/real_signal_validation/real_directional_setup_records.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_signal_quality_flags", "real_signal_validation/real_signal_quality_flags.jsonl", "artifacts/real_signal_validation/real_signal_quality_flags.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_signal_validation_summary", "real_signal_validation/real_signal_validation_summary.json", "artifacts/real_signal_validation/real_signal_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_signal_validation_proof", "real_signal_validation/real_signal_validation_proof.jsonl", "artifacts/real_signal_validation/real_signal_validation_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("options_chain_quote_contract", "options_data_contract/options_chain_quote_contract.json", "artifacts/options_data_contract/options_chain_quote_contract.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("options_schema_contracts", "options_data_contract/options_schema_contracts.jsonl", "artifacts/options_data_contract/options_schema_contracts.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("options_quality_gate_plan", "options_data_contract/options_quality_gate_plan.jsonl", "artifacts/options_data_contract/options_quality_gate_plan.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("options_import_readiness_decision", "options_data_contract/options_import_readiness_decision.json", "artifacts/options_data_contract/options_import_readiness_decision.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("options_data_contract_summary", "options_data_contract/options_data_contract_summary.json", "artifacts/options_data_contract/options_data_contract_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("options_data_contract_proof", "options_data_contract/options_data_contract_proof.jsonl", "artifacts/options_data_contract/options_data_contract_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_data_validation_stack_summary", "real_data_validation_stack/real_data_validation_stack_summary.json", "artifacts/real_data_validation_stack/real_data_validation_stack_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_data_validation_stack_proof", "real_data_validation_stack/real_data_validation_stack_proof.jsonl", "artifacts/real_data_validation_stack/real_data_validation_stack_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("oss_candidate_registry", "open_source/oss_candidate_registry.jsonl", "artifacts/open_source/oss_candidate_registry.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("oss_license_security_results", "open_source/oss_license_security_results.jsonl", "artifacts/open_source/oss_license_security_results.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("oss_candidate_scorecard", "open_source/oss_candidate_scorecard.json", "artifacts/open_source/oss_candidate_scorecard.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("oss_discovery_summary", "open_source/oss_discovery_summary.json", "artifacts/open_source/oss_discovery_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("oss_discovery_proof", "open_source/oss_discovery_proof.jsonl", "artifacts/open_source/oss_discovery_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("oss_sandbox_import_plan", "open_source/oss_sandbox_import_plan.json", "artifacts/open_source/oss_sandbox_import_plan.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("oss_capability_extraction_plan", "open_source/oss_capability_extraction_plan.jsonl", "artifacts/open_source/oss_capability_extraction_plan.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("oss_adapter_contracts", "open_source/oss_adapter_contracts.jsonl", "artifacts/open_source/oss_adapter_contracts.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("free_data_candidate_registry", "free_data/free_data_candidate_registry.jsonl", "artifacts/free_data/free_data_candidate_registry.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("free_data_provenance_gate_results", "free_data/free_data_provenance_gate_results.jsonl", "artifacts/free_data/free_data_provenance_gate_results.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("free_data_candidate_summary", "free_data/free_data_candidate_summary.json", "artifacts/free_data/free_data_candidate_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("free_data_candidate_proof", "free_data/free_data_candidate_proof.jsonl", "artifacts/free_data/free_data_candidate_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("local_ohlcv_import_fix_advice", "local_ohlcv_import/local_ohlcv_import_fix_advice.json", "artifacts/local_ohlcv_import/local_ohlcv_import_fix_advice.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_ohlcv_history_activation_blockers", "history/real_ohlcv_history_activation_blockers.jsonl", "artifacts/history/real_ohlcv_history_activation_blockers.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("open_source_quant_stack_and_free_data_path_summary", "open_source_path/open_source_quant_stack_and_free_data_path_summary.json", "artifacts/open_source_path/open_source_quant_stack_and_free_data_path_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("open_source_quant_stack_and_free_data_path_quality_flags", "open_source_path/open_source_quant_stack_and_free_data_path_quality_flags.jsonl", "artifacts/open_source_path/open_source_quant_stack_and_free_data_path_quality_flags.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("open_source_quant_stack_and_free_data_path_proof", "open_source_path/open_source_quant_stack_and_free_data_path_proof.jsonl", "artifacts/open_source_path/open_source_quant_stack_and_free_data_path_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("local_free_ohlcv_validation_and_activation_stack_summary", "local_free_ohlcv_stack/local_free_ohlcv_validation_and_activation_stack_summary.json", "artifacts/local_free_ohlcv_stack/local_free_ohlcv_validation_and_activation_stack_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("local_free_ohlcv_validation_and_activation_stack_quality_flags", "local_free_ohlcv_stack/local_free_ohlcv_validation_and_activation_stack_quality_flags.jsonl", "artifacts/local_free_ohlcv_stack/local_free_ohlcv_validation_and_activation_stack_quality_flags.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("local_free_ohlcv_validation_and_activation_stack_proof", "local_free_ohlcv_stack/local_free_ohlcv_validation_and_activation_stack_proof.jsonl", "artifacts/local_free_ohlcv_stack/local_free_ohlcv_validation_and_activation_stack_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("manual_free_ohlcv_source_candidates", "manual_ohlcv_staging/manual_free_ohlcv_source_candidates.jsonl", "artifacts/manual_ohlcv_staging/manual_free_ohlcv_source_candidates.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("manual_ohlcv_staging_checklist", "manual_ohlcv_staging/manual_ohlcv_staging_checklist.json", "artifacts/manual_ohlcv_staging/manual_ohlcv_staging_checklist.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("manual_ohlcv_hash_records", "manual_ohlcv_staging/manual_ohlcv_hash_records.jsonl", "artifacts/manual_ohlcv_staging/manual_ohlcv_hash_records.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("manual_ohlcv_manifest_draft", "manual_ohlcv_staging/manual_ohlcv_manifest_draft.json", "artifacts/manual_ohlcv_staging/manual_ohlcv_manifest_draft.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("manual_ohlcv_preflight_results", "manual_ohlcv_staging/manual_ohlcv_preflight_results.jsonl", "artifacts/manual_ohlcv_staging/manual_ohlcv_preflight_results.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("manual_ohlcv_preflight_summary", "manual_ohlcv_staging/manual_ohlcv_preflight_summary.json", "artifacts/manual_ohlcv_staging/manual_ohlcv_preflight_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("manual_ohlcv_import_fix_plan", "manual_ohlcv_staging/manual_ohlcv_import_fix_plan.json", "artifacts/manual_ohlcv_staging/manual_ohlcv_import_fix_plan.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("manual_ohlcv_import_fix_items", "manual_ohlcv_staging/manual_ohlcv_import_fix_items.jsonl", "artifacts/manual_ohlcv_staging/manual_ohlcv_import_fix_items.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("manual_ohlcv_staging_summary", "manual_ohlcv_staging/manual_ohlcv_staging_summary.json", "artifacts/manual_ohlcv_staging/manual_ohlcv_staging_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("manual_ohlcv_staging_proof", "manual_ohlcv_staging/manual_ohlcv_staging_proof.jsonl", "artifacts/manual_ohlcv_staging/manual_ohlcv_staging_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("manual_ohlcv_export_timeout_note", "manual_ohlcv_staging/export_verifier_timeout_note.json", "artifacts/manual_ohlcv_staging/export_verifier_timeout_note.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_reviewed_ohlcv_stage_input", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_stage_input.json", "artifacts/operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_stage_input.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_ohlcv_source_review_contract", "operator_reviewed_ohlcv_stage/operator_ohlcv_source_review_contract.json", "artifacts/operator_reviewed_ohlcv_stage/operator_ohlcv_source_review_contract.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_ohlcv_source_review_status", "operator_reviewed_ohlcv_stage/operator_ohlcv_source_review_status.json", "artifacts/operator_reviewed_ohlcv_stage/operator_ohlcv_source_review_status.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_reviewed_ohlcv_staged_file_status", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_staged_file_status.json", "artifacts/operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_staged_file_status.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_reviewed_ohlcv_staged_file_inventory", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_staged_file_inventory.jsonl", "artifacts/operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_staged_file_inventory.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_reviewed_ohlcv_manifest_candidate", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_manifest_candidate.json", "artifacts/operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_manifest_candidate.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_reviewed_ohlcv_final_manifest_status", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_final_manifest_status.json", "artifacts/operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_final_manifest_status.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_reviewed_ohlcv_rerun_steps", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_rerun_steps.jsonl", "artifacts/operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_rerun_steps.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_reviewed_ohlcv_rerun_decision", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_rerun_decision.json", "artifacts/operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_rerun_decision.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_reviewed_ohlcv_evidence_boundary", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_evidence_boundary.json", "artifacts/operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_evidence_boundary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_reviewed_ohlcv_action_packet", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_action_packet.json", "artifacts/operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_action_packet.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_reviewed_ohlcv_action_packet_markdown", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_action_packet.md", "artifacts/operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_action_packet.md", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_reviewed_ohlcv_stage_rerun_summary", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_stage_rerun_summary.json", "artifacts/operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_stage_rerun_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_reviewed_ohlcv_stage_rerun_quality_flags", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_stage_rerun_quality_flags.jsonl", "artifacts/operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_stage_rerun_quality_flags.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("operator_reviewed_ohlcv_stage_rerun_proof", "operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_stage_rerun_proof.jsonl", "artifacts/operator_reviewed_ohlcv_stage/operator_reviewed_ohlcv_stage_rerun_proof.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("autonomous_admissibility_kernel_summary", "autonomy/autonomous_admissibility_kernel_summary.json", "artifacts/autonomy/autonomous_admissibility_kernel_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("autonomous_source_admissibility_records", "autonomy/autonomous_source_admissibility_records.jsonl", "artifacts/autonomy/autonomous_source_admissibility_records.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("autonomous_oss_discovery_summary", "open_source_autonomy/autonomous_oss_discovery_summary.json", "artifacts/open_source_autonomy/autonomous_oss_discovery_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("autonomous_oss_scorecard", "open_source_autonomy/autonomous_oss_scorecard.json", "artifacts/open_source_autonomy/autonomous_oss_scorecard.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("autonomous_open_data_source_summary", "open_data_autonomy/autonomous_open_data_source_summary.json", "artifacts/open_data_autonomy/autonomous_open_data_source_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("open_data_quarantine_fetch_summary", "open_data_autonomy/open_data_quarantine_fetch_summary.json", "artifacts/open_data_autonomy/open_data_quarantine_fetch_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("open_ohlcv_normalization_summary", "open_data_autonomy/open_ohlcv_normalization_summary.json", "artifacts/open_data_autonomy/open_ohlcv_normalization_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("autonomous_open_data_manifest_summary", "open_data_autonomy/autonomous_open_data_manifest_summary.json", "artifacts/open_data_autonomy/autonomous_open_data_manifest_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("autonomous_open_data_validator_bridge_summary", "open_data_autonomy/autonomous_open_data_validator_bridge_summary.json", "artifacts/open_data_autonomy/autonomous_open_data_validator_bridge_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("open_options_data_autonomy_summary", "options_autonomy/open_options_data_autonomy_summary.json", "artifacts/options_autonomy/open_options_data_autonomy_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("autonomous_research_engine_summary", "research_autonomy/autonomous_research_engine_summary.json", "artifacts/research_autonomy/autonomous_research_engine_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("autonomous_backtest_stat_fitness_summary", "research_autonomy/autonomous_backtest_stat_fitness_summary.json", "artifacts/research_autonomy/autonomous_backtest_stat_fitness_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("autonomous_research_promotion_decision", "research_autonomy/autonomous_research_promotion_decision.json", "artifacts/research_autonomy/autonomous_research_promotion_decision.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("autonomous_paper_trading_loop_summary", "paper_autonomy/autonomous_paper_trading_loop_summary.json", "artifacts/paper_autonomy/autonomous_paper_trading_loop_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("s_tier_options_benchmark_summary", "research_autonomy/s_tier_options_benchmark_summary.json", "artifacts/research_autonomy/s_tier_options_benchmark_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("full_open_source_autonomous_orchestrator_summary", "full_autonomy/full_open_source_autonomous_orchestrator_summary.json", "artifacts/full_autonomy/full_open_source_autonomous_orchestrator_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("full_autonomy_validation_summary", "full_autonomy/full_autonomy_validation_summary.json", "artifacts/full_autonomy/full_autonomy_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("full_autonomy_action_gap_packet", "full_autonomy/full_autonomy_action_gap_packet.json", "artifacts/full_autonomy/full_autonomy_action_gap_packet.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("exhaustive_open_data_discovery_matrix_summary", "open_data_breakthrough/exhaustive_open_data_discovery_matrix_summary.json", "artifacts/open_data_breakthrough/exhaustive_open_data_discovery_matrix_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("machine_license_terms_summary", "open_data_breakthrough/machine_license_terms_summary.json", "artifacts/open_data_breakthrough/machine_license_terms_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("quarantine_download_summary", "open_data_breakthrough/quarantine_download_summary.json", "artifacts/open_data_breakthrough/quarantine_download_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("open_data_validator_bridge_summary", "open_data_breakthrough/open_data_validator_bridge_summary.json", "artifacts/open_data_breakthrough/open_data_validator_bridge_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("quote_priced_options_unlock_gate", "backtest/quote_priced_options_unlock_gate.json", "artifacts/backtest/quote_priced_options_unlock_gate.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("model_priced_options_research_summary", "research_autonomy/model_priced_options_research_summary.json", "artifacts/research_autonomy/model_priced_options_research_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("exhaustive_discovery_proof_report", "open_data_breakthrough/exhaustive_discovery_proof_report.json", "artifacts/open_data_breakthrough/exhaustive_discovery_proof_report.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("open_data_breakthrough_full_completion_summary", "open_data_breakthrough/open_data_breakthrough_full_completion_summary.json", "artifacts/open_data_breakthrough/open_data_breakthrough_full_completion_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("open_data_breakthrough_validation_summary", "open_data_breakthrough/open_data_breakthrough_validation_summary.json", "artifacts/open_data_breakthrough/open_data_breakthrough_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("openbb_provider_registry_summary", "openbb_autonomy/openbb_provider_registry_summary.json", "artifacts/openbb_autonomy/openbb_provider_registry_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("openbb_no_key_source_probe_summary", "openbb_autonomy/openbb_no_key_source_probe_summary.json", "artifacts/openbb_autonomy/openbb_no_key_source_probe_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("openbb_ohlcv_normalization_summary", "openbb_autonomy/openbb_ohlcv_normalization_summary.json", "artifacts/openbb_autonomy/openbb_ohlcv_normalization_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("openbb_validator_bridge_summary", "openbb_autonomy/openbb_validator_bridge_summary.json", "artifacts/openbb_autonomy/openbb_validator_bridge_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("model_priced_v2_research_summary", "research_autonomy/model_priced_v2_research_summary.json", "artifacts/research_autonomy/model_priced_v2_research_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("s_tier_v2_summary", "research_autonomy/s_tier_v2_summary.json", "artifacts/research_autonomy/s_tier_v2_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("paper_rotation_engine_summary", "paper_autonomy/paper_rotation_engine_summary.json", "artifacts/paper_autonomy/paper_rotation_engine_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("remaining_gap_eliminator_summary", "full_autonomy/remaining_gap_eliminator_summary.json", "artifacts/full_autonomy/remaining_gap_eliminator_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("finish_everything_orchestrator_summary", "finish_everything/finish_everything_orchestrator_summary.json", "artifacts/finish_everything/finish_everything_orchestrator_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("finish_everything_validation_summary", "finish_everything/finish_everything_validation_summary.json", "artifacts/finish_everything/finish_everything_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("runtime_bootstrap_summary", "runtime_bootstrap/local_dependency_bootstrap_summary.json", "artifacts/runtime_bootstrap/local_dependency_bootstrap_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("market_data_lake_summary", "market_intake/market_data_lake_summary.json", "artifacts/market_intake/market_data_lake_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("chart_vision_summary", "chart_vision/chart_vision_summary.json", "artifacts/chart_vision/chart_vision_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("aggressive_signal_engine_summary", "signals/aggressive_signal_engine_summary.json", "artifacts/signals/aggressive_signal_engine_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("model_priced_trade_constructor_summary", "options_engine/model_priced_trade_constructor_summary.json", "artifacts/options_engine/model_priced_trade_constructor_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("paper_money_tournament_summary", "tournament/paper_money_tournament_summary.json", "artifacts/tournament/paper_money_tournament_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("pnl_scoreboard_summary", "scoreboard/pnl_scoreboard_summary.json", "artifacts/scoreboard/pnl_scoreboard_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("performance_cockpit_html", "scoreboard/performance_cockpit.html", "artifacts/scoreboard/performance_cockpit.html", True, reporting_profiles + full_profiles),
        ("risk_throttle_summary", "risk/risk_throttle_summary.json", "artifacts/risk/risk_throttle_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("evolution_loop_summary", "evolution/evolution_loop_summary.json", "artifacts/evolution/evolution_loop_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("live_gate_status", "live_gate/live_gate_status.json", "artifacts/live_gate/live_gate_status.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("wealth_engine_full_completion_summary", "wealth_engine/wealth_engine_full_completion_summary.json", "artifacts/wealth_engine/wealth_engine_full_completion_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("wealth_engine_validation_summary", "wealth_engine/wealth_engine_validation_summary.json", "artifacts/wealth_engine/wealth_engine_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("provider_install_repair_summary", "provider_install/provider_install_repair_summary.json", "artifacts/provider_install/provider_install_repair_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("provider_health_diagnostics_summary", "market_intake/provider_health_diagnostics_summary.json", "artifacts/market_intake/provider_health_diagnostics_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_ohlcv_provider_ladder_v2_summary", "market_intake/public_ohlcv_provider_ladder_v2_summary.json", "artifacts/market_intake/public_ohlcv_provider_ladder_v2_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_ohlcv_fetch_successes_v2", "market_intake/public_ohlcv_fetch_successes_v2.jsonl", "artifacts/market_intake/public_ohlcv_fetch_successes_v2.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_ohlcv_fetch_failures_v2", "market_intake/public_ohlcv_fetch_failures_v2.jsonl", "artifacts/market_intake/public_ohlcv_fetch_failures_v2.jsonl", True, audit_profiles + full_profiles + reporting_profiles),
        ("market_data_cache_summary", "market_intake/market_data_cache_summary.json", "artifacts/market_intake/market_data_cache_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("market_lake_public_promotion_summary", "market_intake/market_lake_public_promotion_summary.json", "artifacts/market_intake/market_lake_public_promotion_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_public_market_wealth_rerun_summary", "real_public_wealth/real_public_market_wealth_rerun_summary.json", "artifacts/real_public_wealth/real_public_market_wealth_rerun_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("real_public_market_wealth_validation_summary", "real_public_wealth/real_public_market_wealth_validation_summary.json", "artifacts/real_public_wealth/real_public_market_wealth_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_vs_fixture_scoreboard_split", "scoreboard/public_vs_fixture_scoreboard_split.json", "artifacts/scoreboard/public_vs_fixture_scoreboard_split.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_lake_freeze_guard_summary", "public_champion_evolution/public_lake_freeze_guard_summary.json", "artifacts/public_champion_evolution/public_lake_freeze_guard_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_universe_expansion_v2_summary", "public_champion_evolution/public_universe_expansion_v2_summary.json", "artifacts/public_champion_evolution/public_universe_expansion_v2_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("model_priced_path_simulator_v3_summary", "options_engine/model_priced_path_simulator_v3_summary.json", "artifacts/options_engine/model_priced_path_simulator_v3_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_mutation_factory_v3_summary", "signals/public_signal_mutation_factory_v3_summary.json", "artifacts/signals/public_signal_mutation_factory_v3_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_walk_forward_tournament_v3_summary", "tournament/public_walk_forward_tournament_v3_summary.json", "artifacts/tournament/public_walk_forward_tournament_v3_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_paper_champion_gate_summary", "champions/public_paper_champion_gate_summary.json", "artifacts/champions/public_paper_champion_gate_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_scoreboard_v3", "scoreboard/public_champion_scoreboard_v3.json", "artifacts/scoreboard/public_champion_scoreboard_v3.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_dashboard_v3_html", "scoreboard/public_champion_dashboard_v3.html", "artifacts/scoreboard/public_champion_dashboard_v3.html", True, reporting_profiles + full_profiles),
        ("public_champion_evolution_summary", "evolution/public_champion_evolution_summary.json", "artifacts/evolution/public_champion_evolution_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_risk_summary_v3", "risk/public_champion_risk_summary_v3.json", "artifacts/risk/public_champion_risk_summary_v3.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_lake_final_state_lock_v2_summary", "public_signal_deepening/public_lake_final_state_lock_v2_summary.json", "artifacts/public_signal_deepening/public_lake_final_state_lock_v2_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("strategy_cohort_summary", "public_signal_deepening/strategy_cohort_summary.json", "artifacts/public_signal_deepening/strategy_cohort_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_mutation_factory_v4_summary", "signals/public_signal_mutation_factory_v4_summary.json", "artifacts/signals/public_signal_mutation_factory_v4_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("model_priced_path_simulator_v4_summary", "options_engine/model_priced_path_simulator_v4_summary.json", "artifacts/options_engine/model_priced_path_simulator_v4_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_cohort_walk_forward_tournament_v4_summary", "tournament/public_cohort_walk_forward_tournament_v4_summary.json", "artifacts/tournament/public_cohort_walk_forward_tournament_v4_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_paper_champion_gate_v2_summary", "champions/public_paper_champion_gate_v2_summary.json", "artifacts/champions/public_paper_champion_gate_v2_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_deepening_loop_v2_summary", "evolution/public_signal_deepening_loop_v2_summary.json", "artifacts/evolution/public_signal_deepening_loop_v2_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_deepening_scoreboard_v4", "scoreboard/public_signal_deepening_scoreboard_v4.json", "artifacts/scoreboard/public_signal_deepening_scoreboard_v4.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_deepening_live_gate_status_v2", "live_gate/public_signal_deepening_live_gate_status_v2.json", "artifacts/live_gate/public_signal_deepening_live_gate_status_v2.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_market_signal_mutation_deepening_v2_summary", "public_signal_deepening/public_market_signal_mutation_deepening_v2_summary.json", "artifacts/public_signal_deepening/public_market_signal_mutation_deepening_v2_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_market_signal_mutation_deepening_v2_validation_summary", "public_signal_deepening/public_market_signal_mutation_deepening_v2_validation_summary.json", "artifacts/public_signal_deepening/public_market_signal_mutation_deepening_v2_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("champion_hardening_preflight_summary", "champion_hardening/champion_hardening_preflight_summary.json", "artifacts/champion_hardening/champion_hardening_preflight_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_artifact_cleaner_summary", "champion_hardening/public_signal_artifact_cleaner_summary.json", "artifacts/champion_hardening/public_signal_artifact_cleaner_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_inventory_v1_summary", "champion_hardening/public_champion_inventory_v1_summary.json", "artifacts/champion_hardening/public_champion_inventory_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_deep_stress_matrix_v1_summary", "champion_hardening/public_champion_deep_stress_matrix_v1_summary.json", "artifacts/champion_hardening/public_champion_deep_stress_matrix_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_holdout_expansion_v1_summary", "champion_hardening/public_champion_holdout_expansion_v1_summary.json", "artifacts/champion_hardening/public_champion_holdout_expansion_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_decay_monitor_v1_summary", "champion_hardening/public_champion_decay_monitor_v1_summary.json", "artifacts/champion_hardening/public_champion_decay_monitor_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_hardening_gate_v1_summary", "champion_hardening/public_champion_hardening_gate_v1_summary.json", "artifacts/champion_hardening/public_champion_hardening_gate_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_hardening_scoreboard_v1", "scoreboard/public_champion_hardening_scoreboard_v1.json", "artifacts/scoreboard/public_champion_hardening_scoreboard_v1.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_hardening_live_gate_status_v3", "live_gate/public_champion_hardening_live_gate_status_v3.json", "artifacts/live_gate/public_champion_hardening_live_gate_status_v3.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_paper_champion_hardening_and_deep_stress_v1_summary", "champion_hardening/public_paper_champion_hardening_and_deep_stress_v1_summary.json", "artifacts/champion_hardening/public_paper_champion_hardening_and_deep_stress_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_paper_champion_hardening_and_deep_stress_v1_validation_summary", "champion_hardening/public_paper_champion_hardening_and_deep_stress_v1_validation_summary.json", "artifacts/champion_hardening/public_paper_champion_hardening_and_deep_stress_v1_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_repair_preflight_v1_summary", "champion_repair/public_champion_repair_preflight_v1_summary.json", "artifacts/champion_repair/public_champion_repair_preflight_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_artifact_guard_v1_summary", "champion_repair/public_champion_artifact_guard_v1_summary.json", "artifacts/champion_repair/public_champion_artifact_guard_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("conditional_champion_retune_hardening_gate_v1_summary", "champion_repair/conditional_champion_retune_hardening_gate_v1_summary.json", "artifacts/champion_repair/conditional_champion_retune_hardening_gate_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_repair_and_retune_v1_summary", "champion_repair/public_champion_repair_and_retune_v1_summary.json", "artifacts/champion_repair/public_champion_repair_and_retune_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_repair_and_retune_v1_validation_summary", "champion_repair/public_champion_repair_and_retune_v1_validation_summary.json", "artifacts/champion_repair/public_champion_repair_and_retune_v1_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_preflight_v1_summary", "signal_research/public_signal_research_preflight_v1_summary.json", "artifacts/signal_research/public_signal_research_preflight_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_breakthrough_gate_v1_summary", "signal_research/research_breakthrough_gate_v1_summary.json", "artifacts/signal_research/research_breakthrough_gate_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v1_summary", "signal_research/public_signal_research_breakthrough_v1_summary.json", "artifacts/signal_research/public_signal_research_breakthrough_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v1_validation_summary", "signal_research/public_signal_research_breakthrough_v1_validation_summary.json", "artifacts/signal_research/public_signal_research_breakthrough_v1_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_v2_preflight_summary", "signal_research_v2/public_signal_research_v2_preflight_summary.json", "artifacts/signal_research_v2/public_signal_research_v2_preflight_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_breakthrough_gate_v2_summary", "signal_research_v2/research_breakthrough_gate_v2_summary.json", "artifacts/signal_research_v2/research_breakthrough_gate_v2_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v2_summary", "signal_research_v2/public_signal_research_breakthrough_v2_summary.json", "artifacts/signal_research_v2/public_signal_research_breakthrough_v2_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v2_validation_summary", "signal_research_v2/public_signal_research_breakthrough_v2_validation_summary.json", "artifacts/signal_research_v2/public_signal_research_breakthrough_v2_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_v3_preflight_summary", "signal_research_v3/public_signal_research_v3_preflight_summary.json", "artifacts/signal_research_v3/public_signal_research_v3_preflight_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_breakthrough_gate_v3_summary", "signal_research_v3/research_breakthrough_gate_v3_summary.json", "artifacts/signal_research_v3/research_breakthrough_gate_v3_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v3_summary", "signal_research_v3/public_signal_research_breakthrough_v3_summary.json", "artifacts/signal_research_v3/public_signal_research_breakthrough_v3_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v3_validation_summary", "signal_research_v3/public_signal_research_breakthrough_v3_validation_summary.json", "artifacts/signal_research_v3/public_signal_research_breakthrough_v3_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_v4_preflight_summary", "signal_research_v4/public_signal_research_v4_preflight_summary.json", "artifacts/signal_research_v4/public_signal_research_v4_preflight_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_breakthrough_gate_v4_summary", "signal_research_v4/research_breakthrough_gate_v4_summary.json", "artifacts/signal_research_v4/research_breakthrough_gate_v4_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_tournament_v4_summary", "signal_research_v4/research_tournament_v4_summary.json", "artifacts/signal_research_v4/research_tournament_v4_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v4_summary", "signal_research_v4/public_signal_research_breakthrough_v4_summary.json", "artifacts/signal_research_v4/public_signal_research_breakthrough_v4_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v4_validation_summary", "signal_research_v4/public_signal_research_breakthrough_v4_validation_summary.json", "artifacts/signal_research_v4/public_signal_research_breakthrough_v4_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("zero_dte_replay_outcomes_artifact_guard_v2_summary", "active_policy/zero_dte_replay_outcomes_artifact_guard_v2_summary.json", "artifacts/active_policy/zero_dte_replay_outcomes_artifact_guard_v2_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_scoreboard_v4", "scoreboard/public_signal_research_scoreboard_v4.json", "artifacts/scoreboard/public_signal_research_scoreboard_v4.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_live_gate_status_v4", "live_gate/public_signal_research_live_gate_status_v4.json", "artifacts/live_gate/public_signal_research_live_gate_status_v4.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_v5_preflight_summary", "signal_research_v5/public_signal_research_v5_preflight_summary.json", "artifacts/signal_research_v5/public_signal_research_v5_preflight_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_v5_baseline_freeze_summary", "signal_research_v5/public_signal_research_v5_baseline_freeze_summary.json", "artifacts/signal_research_v5/public_signal_research_v5_baseline_freeze_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_mutation_queue_executor_v5_summary", "signal_research_v5/research_mutation_queue_executor_v5_summary.json", "artifacts/signal_research_v5/research_mutation_queue_executor_v5_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("no_trade_filter_optimizer_v5_summary", "signal_research_v5/no_trade_filter_optimizer_v5_summary.json", "artifacts/signal_research_v5/no_trade_filter_optimizer_v5_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_candidate_generator_v5_summary", "signal_research_v5/research_candidate_generator_v5_summary.json", "artifacts/signal_research_v5/research_candidate_generator_v5_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("profit_holdout_split_scorer_v5_summary", "signal_research_v5/profit_holdout_split_scorer_v5_summary.json", "artifacts/signal_research_v5/profit_holdout_split_scorer_v5_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_path_simulator_v5_summary", "signal_research_v5/research_path_simulator_v5_summary.json", "artifacts/signal_research_v5/research_path_simulator_v5_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_tournament_v5_summary", "signal_research_v5/research_tournament_v5_summary.json", "artifacts/signal_research_v5/research_tournament_v5_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_breakthrough_gate_v5_summary", "signal_research_v5/research_breakthrough_gate_v5_summary.json", "artifacts/signal_research_v5/research_breakthrough_gate_v5_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_mutation_queue_v5_summary", "signal_research_v5/research_mutation_queue_v5_summary.json", "artifacts/signal_research_v5/research_mutation_queue_v5_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_scoreboard_v5", "scoreboard/public_signal_research_scoreboard_v5.json", "artifacts/scoreboard/public_signal_research_scoreboard_v5.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_live_gate_status_v5", "live_gate/public_signal_research_live_gate_status_v5.json", "artifacts/live_gate/public_signal_research_live_gate_status_v5.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v5_summary", "signal_research_v5/public_signal_research_breakthrough_v5_summary.json", "artifacts/signal_research_v5/public_signal_research_breakthrough_v5_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v5_validation_summary", "signal_research_v5/public_signal_research_breakthrough_v5_validation_summary.json", "artifacts/signal_research_v5/public_signal_research_breakthrough_v5_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_v6_preflight_summary", "signal_research_v6/public_signal_research_v6_preflight_summary.json", "artifacts/signal_research_v6/public_signal_research_v6_preflight_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_v6_baseline_freeze_summary", "signal_research_v6/public_signal_research_v6_baseline_freeze_summary.json", "artifacts/signal_research_v6/public_signal_research_v6_baseline_freeze_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("v5_gate_rejection_analyzer_v6_summary", "signal_research_v6/v5_gate_rejection_analyzer_v6_summary.json", "artifacts/signal_research_v6/v5_gate_rejection_analyzer_v6_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_mutation_queue_executor_v6_summary", "signal_research_v6/research_mutation_queue_executor_v6_summary.json", "artifacts/signal_research_v6/research_mutation_queue_executor_v6_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("breakthrough_blocker_repair_policy_v6_summary", "signal_research_v6/breakthrough_blocker_repair_policy_v6_summary.json", "artifacts/signal_research_v6/breakthrough_blocker_repair_policy_v6_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_candidate_generator_v6_summary", "signal_research_v6/research_candidate_generator_v6_summary.json", "artifacts/signal_research_v6/research_candidate_generator_v6_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("profit_holdout_split_scorer_v6_summary", "signal_research_v6/profit_holdout_split_scorer_v6_summary.json", "artifacts/signal_research_v6/profit_holdout_split_scorer_v6_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_path_simulator_v6_summary", "signal_research_v6/research_path_simulator_v6_summary.json", "artifacts/signal_research_v6/research_path_simulator_v6_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_tournament_v6_summary", "signal_research_v6/research_tournament_v6_summary.json", "artifacts/signal_research_v6/research_tournament_v6_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_breakthrough_gate_v6_summary", "signal_research_v6/research_breakthrough_gate_v6_summary.json", "artifacts/signal_research_v6/research_breakthrough_gate_v6_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_mutation_queue_v6_summary", "signal_research_v6/research_mutation_queue_v6_summary.json", "artifacts/signal_research_v6/research_mutation_queue_v6_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_scoreboard_v6", "scoreboard/public_signal_research_scoreboard_v6.json", "artifacts/scoreboard/public_signal_research_scoreboard_v6.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_live_gate_status_v6", "live_gate/public_signal_research_live_gate_status_v6.json", "artifacts/live_gate/public_signal_research_live_gate_status_v6.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v6_summary", "signal_research_v6/public_signal_research_breakthrough_v6_summary.json", "artifacts/signal_research_v6/public_signal_research_breakthrough_v6_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v6_validation_summary", "signal_research_v6/public_signal_research_breakthrough_v6_validation_summary.json", "artifacts/signal_research_v6/public_signal_research_breakthrough_v6_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        # DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7
        ("public_signal_research_v7_preflight_summary", "signal_research_v7/public_signal_research_v7_preflight_summary.json", "artifacts/signal_research_v7/public_signal_research_v7_preflight_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_v7_baseline_freeze_summary", "signal_research_v7/public_signal_research_v7_baseline_freeze_summary.json", "artifacts/signal_research_v7/public_signal_research_v7_baseline_freeze_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("no_trade_contribution_audit_v7_summary", "signal_research_v7/no_trade_contribution_audit_v7_summary.json", "artifacts/signal_research_v7/no_trade_contribution_audit_v7_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("v6_watchlist_diagnosis_v7_summary", "signal_research_v7/v6_watchlist_diagnosis_v7_summary.json", "artifacts/signal_research_v7/v6_watchlist_diagnosis_v7_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_mutation_queue_executor_v7_summary", "signal_research_v7/research_mutation_queue_executor_v7_summary.json", "artifacts/signal_research_v7/research_mutation_queue_executor_v7_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("trade_active_repair_policy_v7_summary", "signal_research_v7/trade_active_repair_policy_v7_summary.json", "artifacts/signal_research_v7/trade_active_repair_policy_v7_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_candidate_generator_v7_summary", "signal_research_v7/research_candidate_generator_v7_summary.json", "artifacts/signal_research_v7/research_candidate_generator_v7_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("profit_holdout_split_scorer_v7_summary", "signal_research_v7/profit_holdout_split_scorer_v7_summary.json", "artifacts/signal_research_v7/profit_holdout_split_scorer_v7_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_path_simulator_v7_summary", "signal_research_v7/research_path_simulator_v7_summary.json", "artifacts/signal_research_v7/research_path_simulator_v7_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_tournament_v7_summary", "signal_research_v7/research_tournament_v7_summary.json", "artifacts/signal_research_v7/research_tournament_v7_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_breakthrough_gate_v7_summary", "signal_research_v7/research_breakthrough_gate_v7_summary.json", "artifacts/signal_research_v7/research_breakthrough_gate_v7_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("research_mutation_queue_v7_summary", "signal_research_v7/research_mutation_queue_v7_summary.json", "artifacts/signal_research_v7/research_mutation_queue_v7_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_scoreboard_v7", "scoreboard/public_signal_research_scoreboard_v7.json", "artifacts/scoreboard/public_signal_research_scoreboard_v7.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_live_gate_status_v7", "live_gate/public_signal_research_live_gate_status_v7.json", "artifacts/live_gate/public_signal_research_live_gate_status_v7.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v7_summary", "signal_research_v7/public_signal_research_breakthrough_v7_summary.json", "artifacts/signal_research_v7/public_signal_research_breakthrough_v7_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_signal_research_breakthrough_v7_validation_summary", "signal_research_v7/public_signal_research_breakthrough_v7_validation_summary.json", "artifacts/signal_research_v7/public_signal_research_breakthrough_v7_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("zero_dte_replay_outcomes_artifact_repair_v1_summary", "active_policy/zero_dte_replay_outcomes_artifact_repair_v1_summary.json", "artifacts/active_policy/zero_dte_replay_outcomes_artifact_repair_v1_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_champion_live_gate_status", "live_gate/public_champion_live_gate_status.json", "artifacts/live_gate/public_champion_live_gate_status.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_market_paper_champion_evolution_summary", "public_champion_evolution/public_market_paper_champion_evolution_summary.json", "artifacts/public_champion_evolution/public_market_paper_champion_evolution_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_market_paper_champion_validation_summary", "public_champion_evolution/public_market_paper_champion_validation_summary.json", "artifacts/public_champion_evolution/public_market_paper_champion_validation_summary.json", True, audit_profiles + full_profiles + reporting_profiles),
        ("public_market_paper_champion_timeout_records", "public_champion_evolution/public_market_paper_champion_timeout_records.jsonl", "artifacts/public_champion_evolution/public_market_paper_champion_timeout_records.jsonl", False, audit_profiles + full_profiles + reporting_profiles),
        ("meta_governor_registry", "meta_governor/meta_governor_registry.jsonl", "artifacts/meta_governor/meta_governor_registry.jsonl", True, full_profiles),
        ("meta_governor_decisions", "meta_governor/meta_governor_decisions.jsonl", "artifacts/meta_governor/meta_governor_decisions.jsonl", True, full_profiles),
        ("meta_governor_proof", "meta_governor/meta_governor_proof.jsonl", "artifacts/meta_governor/meta_governor_proof.jsonl", True, full_profiles),
        ("ensemble_registry", "ensemble_allocator/ensemble_allocation_registry.jsonl", "artifacts/ensemble_allocator/ensemble_allocation_registry.jsonl", True, full_profiles),
        ("ensemble_replay", "ensemble_allocator/ensemble_replay.jsonl", "artifacts/ensemble_allocator/ensemble_replay.jsonl", True, full_profiles),
        ("tournament_ledger", "tournaments/dopey_tournament.jsonl", "artifacts/tournaments/dopey_tournament.jsonl", True, full_profiles),
        ("champion_registry", "champion_registry/champion_registry.jsonl", "artifacts/champion_registry/champion_registry.jsonl", True, full_profiles),
        ("champion_consistency", "champion_registry/champion_consistency.jsonl", "artifacts/champion_registry/champion_consistency.jsonl", False, full_profiles),
        ("champion_corpus_v2", "champion_registry/champion_corpus_v2.jsonl", "artifacts/champion_registry/champion_corpus_v2.jsonl", False, full_profiles),
        ("walk_forward_ledger", "walk_forward/dopey_walk_forward.jsonl", "artifacts/walk_forward/dopey_walk_forward.jsonl", True, full_profiles),
        ("walk_forward_consistency_registry", "walk_forward_consistency/consistency_registry.jsonl", "artifacts/walk_forward_consistency/consistency_registry.jsonl", True, full_profiles),
        ("walk_forward_consistency_proof", "walk_forward_consistency/consistency_proof.jsonl", "artifacts/walk_forward_consistency/consistency_proof.jsonl", True, full_profiles),
        ("regime_holdout_corpus_v2_registry", "regime_holdout_corpus_v2/corpus_registry.jsonl", "artifacts/regime_holdout_corpus_v2/corpus_registry.jsonl", True, full_profiles),
        ("regime_holdout_corpus_v2_replay", "regime_holdout_corpus_v2/corpus_v2_replay.jsonl", "artifacts/regime_holdout_corpus_v2/corpus_v2_replay.jsonl", True, full_profiles),
        ("regime_holdout_corpus_v2_coverage", "regime_holdout_corpus_v2/corpus_coverage.jsonl", "artifacts/regime_holdout_corpus_v2/corpus_coverage.jsonl", True, full_profiles),
        ("regime_holdout_corpus_v2_proof", "regime_holdout_corpus_v2/corpus_v2_proof.jsonl", "artifacts/regime_holdout_corpus_v2/corpus_v2_proof.jsonl", True, full_profiles),
        ("macro_event_registry", "macro_events/macro_event_registry.jsonl", "artifacts/macro_events/macro_event_registry.jsonl", True, full_profiles),
        ("macro_event_ledger", "macro_events/macro_event_bundle.jsonl", "artifacts/macro_events/macro_event_bundle.jsonl", True, full_profiles),
        ("iv_surface_registry", "iv_surface/iv_surface_registry.jsonl", "artifacts/iv_surface/iv_surface_registry.jsonl", True, full_profiles),
        ("iv_surface_ledger", "iv_surface/iv_surface_skew_bundle.jsonl", "artifacts/iv_surface/iv_surface_skew_bundle.jsonl", True, full_profiles),
        ("fundamental_registry", "fundamental_fixtures/fundamental_registry.jsonl", "artifacts/fundamental_fixtures/fundamental_registry.jsonl", True, full_profiles),
        ("fundamental_coverage", "fundamental_fixtures/fundamental_coverage.jsonl", "artifacts/fundamental_fixtures/fundamental_coverage.jsonl", True, full_profiles),
        ("fundamental_ledger", "fundamental_fixtures/fundamental_bundle.jsonl", "artifacts/fundamental_fixtures/fundamental_bundle.jsonl", True, full_profiles),
        ("failure_mode_registry", "failure_modes/failure_mode_registry.jsonl", "artifacts/failure_modes/failure_mode_registry.jsonl", True, full_profiles),
        ("failure_feedback_registry", "failure_feedback/failure_feedback_registry.jsonl", "artifacts/failure_feedback/failure_feedback_registry.jsonl", True, full_profiles),
        ("feedback_optimizer_ledger", "failure_feedback/feedback_optimizer.jsonl", "artifacts/failure_feedback/feedback_optimizer.jsonl", True, full_profiles),
        ("mutation_registry", "mutations/mutation_registry.jsonl", "artifacts/mutations/mutation_registry.jsonl", True, full_profiles),
        ("mutation_population_ledger", "mutations/dopey_mutation_population_bundle.jsonl", "artifacts/mutations/dopey_mutation_population_bundle.jsonl", True, full_profiles),
        ("paper_pipeline_ledger", "proof_ledger/dopey_paper_pipeline.jsonl", "artifacts/proof_ledger/dopey_paper_pipeline.jsonl", True, full_profiles),
        ("optional_operator_export_notes", "exports/operator_export_notes.json", "notes/operator_export_notes.json", False, full_profiles),
        ("blunder_integrity_status", "exports/blunder_integrity_status.json", "integrity/blunder_integrity_status.json", True, full_profiles + ["minimal_proof", "audit_only"]),
    ]
    for artifact_id, source_rel, export_rel, required, profiles in artifact_specs:
        rules.append(_rule(
            artifact_id=artifact_id,
            artifact_type=artifact_id,
            source_path=f"artifacts/dopey/{source_rel}",
            relative_export_path=export_rel,
            required=required,
            profiles=profiles,
            notes=["selected proof/report/dashboard artifact"],
        ))
    return rules


def _record_count_and_parse_status(path: Path) -> tuple[int, str]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".jsonl":
            count = 0
            parse_lines = path.stat().st_size <= JSONL_PARSE_THRESHOLD_BYTES
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    if parse_lines:
                        json.loads(line)
                    count += 1
            return count, "ok" if parse_lines else "ok_stream_counted"
        if suffix == ".json":
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                return 0, "empty"
            parsed = json.loads(text)
            return (len(parsed) if isinstance(parsed, list) else 1), "ok"
        if suffix in {".md", ".txt", ".html"}:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for _ in handle:
                    pass
            return 1, "ok"
        return 1, "ok"
    except json.JSONDecodeError as exc:
        return 0, f"json_error: {exc}"
    except UnicodeDecodeError as exc:
        return 0, f"text_error: {exc}"


def build_export_artifact_from_rule(rule: ExportSelectionRule) -> ExportArtifact:
    source_path = repo_relative_path(rule.source_path)
    source = resolve_repo_path(source_path)
    record_count, parse_status = _record_count_and_parse_status(source)
    return ExportArtifact(
        artifact_id=rule.artifact_id,
        artifact_type=rule.artifact_type,
        source_path=source_path,
        relative_export_path=rule.relative_export_path,
        size_bytes=source.stat().st_size,
        sha256=sha256_file(source),
        record_count=record_count,
        parse_status=parse_status,
        required=rule.required,
        safety_scan_status="not_scanned",
        notes=rule.notes,
    )


def write_blunder_integrity_status() -> Path:
    manifest = Path("C:/Users/CH/.local/share/kilo/plans/dopey_blunder_sha256_baseline.txt")
    checked = 0
    missing = 0
    mismatches: list[str] = []
    if manifest.exists():
        import hashlib
        for line in manifest.read_text(encoding="utf-8-sig").splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) != 2:
                continue
            expected, raw_path = parts
            candidate = Path(raw_path)
            if not candidate.exists():
                missing += 1
                continue
            actual = hashlib.sha256(candidate.read_bytes()).hexdigest().upper()
            checked += 1
            if actual != expected.upper():
                mismatches.append(candidate.name)
    record = {
        "blunder_integrity_status_version": "dopey-export-blunder-integrity-reference-v1",
        "manifest_reference": "dopey_blunder_sha256_baseline.txt",
        "manifest_present": manifest.exists(),
        "checked": checked,
        "missing": missing,
        "mismatches": mismatches,
        "status": "ok" if checked > 0 and not mismatches else ("skipped" if not mismatches else "warning"),
        "notes": [
            "hash reference only; original Blunder source is not exported",
            "paths are intentionally not expanded into the handoff manifest",
        ],
    }
    record["reproducibility_hash"] = canonical_export_hash(record)
    BLUNDER_INTEGRITY_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    BLUNDER_INTEGRITY_STATUS_PATH.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return BLUNDER_INTEGRITY_STATUS_PATH


def select_export_artifacts(profile_name: str, state: dict) -> ExportBundlePlan:
    profile = export_profile_for(profile_name)
    selected: list[ExportArtifact] = []
    missing_required: list[str] = []
    missing_optional: list[str] = []
    skipped: list[dict] = []
    write_blunder_integrity_status()
    for rule in export_selection_rules():
        if profile.profile_name not in rule.profiles:
            continue
        if is_excluded_path(rule.source_path) and "exports/blunder_integrity_status.json" not in rule.source_path:
            skipped.append({"artifact_id": rule.artifact_id, "source_path": rule.source_path, "reason": "excluded_path"})
            continue
        source = resolve_repo_path(repo_relative_path(rule.source_path))
        if not source.exists():
            if rule.required:
                missing_required.append(rule.artifact_id)
            else:
                missing_optional.append(rule.artifact_id)
            skipped.append({"artifact_id": rule.artifact_id, "source_path": rule.source_path, "reason": "missing"})
            continue
        selected.append(build_export_artifact_from_rule(rule))
    bundle_identity = canonical_export_hash({
        "profile": profile.profile_name,
        "artifact_ids": [artifact.artifact_id for artifact in selected],
        "relative_export_paths": [artifact.relative_export_path for artifact in selected],
    })
    bundle_id = f"dopey-export-{profile.profile_name.replace('_', '-')}-{bundle_identity[:12]}"
    required_ids = [artifact.artifact_id for artifact in selected if artifact.required]
    optional_ids = [artifact.artifact_id for artifact in selected if not artifact.required]
    plan_seed = {
        "bundle_id": bundle_id,
        "profile": profile.profile_name,
        "selected": [artifact.to_dict() for artifact in selected],
        "missing_required_artifacts": missing_required,
        "missing_optional_artifacts": missing_optional,
        "skipped_artifacts": skipped,
        "safety_state": state,
    }
    return ExportBundlePlan(
        bundle_id=bundle_id,
        profile=profile.profile_name,
        selected_artifacts=selected,
        missing_required_artifacts=missing_required,
        missing_optional_artifacts=missing_optional,
        skipped_artifacts=skipped,
        required_artifacts=required_ids,
        optional_artifacts=optional_ids,
        safety_state=state,
        reproducibility_hash=canonical_export_hash(plan_seed),
    )
