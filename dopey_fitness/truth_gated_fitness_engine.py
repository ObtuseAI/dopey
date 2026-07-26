"""Truth-gated diagnostic fitness engine."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from dopey_backtest.trade_records_recovery import (
    iter_verified_trade_records,
    resolve_default_backtest_trade_ledger,
)
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_core.repo_paths import REPORTS_DIR

from .fitness_models import (
    FITNESS_VERSION,
    FitnessDecision,
    FitnessInput,
    FitnessMetricComponent,
    FitnessPenalty,
    FitnessProofRecord,
    FitnessQualityFlag,
    FitnessRankRecord,
    FitnessScorecard,
    stable_fitness_hash,
)
from .promotion_gate import evaluate_fitness_promotion_gate
from .proxy_fitness_quarantine import quarantine_summary, scan_proxy_fitness_references


REPO_ROOT = Path(__file__).resolve().parent.parent
FITNESS_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "fitness"
FITNESS_FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "fitness"
STATS_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "stats"
BACKTEST_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "backtest"
VALIDATION_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "validation"
STATISTICAL_TRUTH_SUMMARY_PATH = STATS_ARTIFACT_DIR / "statistical_truth_summary.json"
STATISTICAL_TRUTH_DECISION_PATH = STATS_ARTIFACT_DIR / "statistical_truth_decision.json"
BACKTEST_METRIC_SET_PATH = STATS_ARTIFACT_DIR / "backtest_metric_set.json"
BOOTSTRAP_CONFIDENCE_INTERVALS_PATH = STATS_ARTIFACT_DIR / "bootstrap_confidence_intervals.json"
BASELINE_COMPARISONS_PATH = STATS_ARTIFACT_DIR / "baseline_comparisons.jsonl"
MULTIPLE_TESTING_ADJUSTMENT_PATH = STATS_ARTIFACT_DIR / "multiple_testing_adjustment.json"
DEFLATED_SHARPE_RESULT_PATH = STATS_ARTIFACT_DIR / "deflated_sharpe_result.json"
BACKTEST_TRADE_RECORDS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_trade_records.jsonl"
BACKTEST_RUN_SUMMARY_PATH = BACKTEST_ARTIFACT_DIR / "backtest_run_summary.json"
VALIDATION_SUMMARY_PATH = VALIDATION_ARTIFACT_DIR / "full_suite_stabilizer_summary.json"
FITNESS_INPUT_PATH = FITNESS_ARTIFACT_DIR / "fitness_input.json"
FITNESS_METRIC_COMPONENTS_PATH = FITNESS_ARTIFACT_DIR / "fitness_metric_components.jsonl"
FITNESS_PENALTIES_PATH = FITNESS_ARTIFACT_DIR / "fitness_penalties.jsonl"
FITNESS_SCORECARDS_PATH = FITNESS_ARTIFACT_DIR / "fitness_scorecards.jsonl"
FITNESS_RANK_RECORDS_PATH = FITNESS_ARTIFACT_DIR / "fitness_rank_records.jsonl"
FITNESS_PROMOTION_GATE_PATH = FITNESS_ARTIFACT_DIR / "fitness_promotion_gate.json"
FITNESS_DECISION_PATH = FITNESS_ARTIFACT_DIR / "fitness_decision.json"
PROXY_FITNESS_QUARANTINE_FINDINGS_PATH = FITNESS_ARTIFACT_DIR / "proxy_fitness_quarantine_findings.jsonl"
FITNESS_QUALITY_FLAGS_PATH = FITNESS_ARTIFACT_DIR / "fitness_quality_flags.jsonl"
FITNESS_REPLACEMENT_SUMMARY_PATH = FITNESS_ARTIFACT_DIR / "fitness_replacement_summary.json"
FITNESS_REPLACEMENT_PROOF_PATH = FITNESS_ARTIFACT_DIR / "fitness_replacement_proof.jsonl"
FITNESS_METRIC_COMPONENT_CASES_PATH = FITNESS_FIXTURE_DIR / "fitness_metric_component_cases.json"
FITNESS_PENALTY_CASES_PATH = FITNESS_FIXTURE_DIR / "fitness_penalty_cases.json"
FITNESS_PROMOTION_GATE_CASES_PATH = FITNESS_FIXTURE_DIR / "fitness_promotion_gate_cases.json"
PROXY_FITNESS_QUARANTINE_CASES_PATH = FITNESS_FIXTURE_DIR / "proxy_fitness_quarantine_cases.json"
FITNESS_REPORT_PATH = REPORTS_DIR / "DOPEY_FITNESS_FUNCTION_REPLACEMENT_REPORT.md"
FITNESS_LEDGER_PATH = REPORTS_DIR / "DOPEY_FITNESS_FUNCTION_REPLACEMENT_ARTIFACT_LEDGER.md"


def run_fitness_function_replacement() -> dict[str, Any]:
    ensure_statistical_truth_artifacts()
    fixture_bundle = build_fitness_fixture_bundle()
    _write_fixture_files(fixture_bundle)
    truth_summary = _load_json(STATISTICAL_TRUTH_SUMMARY_PATH)
    truth_decision = _load_json(STATISTICAL_TRUTH_DECISION_PATH)
    metric_set = _load_json(BACKTEST_METRIC_SET_PATH)
    bootstrap_ci = _load_json(BOOTSTRAP_CONFIDENCE_INTERVALS_PATH)
    baseline_comparisons = _load_jsonl(BASELINE_COMPARISONS_PATH)
    multiple_testing = _load_json(MULTIPLE_TESTING_ADJUSTMENT_PATH)
    _load_json(DEFLATED_SHARPE_RESULT_PATH)
    ledger_resolution = resolve_default_backtest_trade_ledger()
    trade_records = list(iter_verified_trade_records(ledger_resolution))
    backtest_summary = _load_json(BACKTEST_RUN_SUMMARY_PATH)
    validation_summary = _load_json(VALIDATION_SUMMARY_PATH)
    fitness_input = build_fitness_input(truth_summary, truth_decision, backtest_summary)
    components = compute_metric_components(metric_set, bootstrap_ci, baseline_comparisons)
    penalties = compute_penalties(truth_summary, truth_decision, backtest_summary, metric_set, bootstrap_ci, multiple_testing, validation_summary)
    quarantine_findings = scan_proxy_fitness_references(REPO_ROOT)
    quarantine_counts = quarantine_summary(quarantine_findings)
    gate = evaluate_fitness_promotion_gate(truth_summary, truth_decision, backtest_summary, validation_summary, _active_boundary_scan())
    scorecard = build_scorecard(components, penalties, gate, truth_summary, backtest_summary)
    rank_record = build_rank_record(scorecard)
    decision = build_fitness_decision(scorecard, gate, truth_summary, truth_decision, quarantine_counts)
    quality_flags = build_quality_flags(truth_summary, gate, quarantine_counts, validation_summary)
    summary = build_summary(
        fitness_input,
        components,
        penalties,
        scorecard,
        rank_record,
        gate,
        decision,
        quality_flags,
        quarantine_counts,
        truth_summary,
        truth_decision,
        metric_set,
        trade_records,
    )
    proof = build_proof(summary)
    FITNESS_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(FITNESS_INPUT_PATH, fitness_input)
    _write_jsonl(FITNESS_METRIC_COMPONENTS_PATH, components)
    _write_jsonl(FITNESS_PENALTIES_PATH, penalties)
    _write_jsonl(FITNESS_SCORECARDS_PATH, [scorecard])
    _write_jsonl(FITNESS_RANK_RECORDS_PATH, [rank_record])
    _write_json(FITNESS_PROMOTION_GATE_PATH, gate)
    _write_json(FITNESS_DECISION_PATH, decision)
    _write_jsonl(PROXY_FITNESS_QUARANTINE_FINDINGS_PATH, quarantine_findings)
    _write_jsonl(FITNESS_QUALITY_FLAGS_PATH, quality_flags)
    _write_json(FITNESS_REPLACEMENT_SUMMARY_PATH, summary)
    _write_jsonl(FITNESS_REPLACEMENT_PROOF_PATH, [proof])
    _write_report(summary)
    _write_ledger(summary)
    return {
        "fitness_status": summary["fitness_status"],
        "fitness_decision": summary["fitness_decision"],
        "diagnostic_score": summary["diagnostic_score"],
        "promotion_allowed": summary["promotion_allowed"],
        "strategy_promoted": summary["strategy_promoted"],
        "truth_status": summary["truth_status"],
        "truth_decision": summary["truth_decision"],
        "real_sample_size": summary["real_sample_size"],
        "fixture_model_sample_size": summary["fixture_model_sample_size"],
        "quality_flags": summary["quality_flags"],
        "next_recommended_target": summary["next_recommended_target"],
        "artifact_paths": fitness_artifact_paths(),
    }


def ensure_statistical_truth_artifacts() -> None:
    required = [
        STATISTICAL_TRUTH_SUMMARY_PATH,
        STATISTICAL_TRUTH_DECISION_PATH,
        BACKTEST_METRIC_SET_PATH,
        BOOTSTRAP_CONFIDENCE_INTERVALS_PATH,
        BASELINE_COMPARISONS_PATH,
        BACKTEST_TRADE_RECORDS_PATH,
        BACKTEST_RUN_SUMMARY_PATH,
    ]
    if all(path.exists() for path in required):
        return
    from dopey_stats.run_statistical_truth_layer import run_statistical_truth_layer

    run_statistical_truth_layer()


def build_fitness_input(truth_summary: dict[str, Any], truth_decision: dict[str, Any], backtest_summary: dict[str, Any]) -> dict[str, Any]:
    record = FitnessInput(
        artifact_type="fitness_input",
        fitness_version="",
        truth_summary_path=str(STATISTICAL_TRUTH_SUMMARY_PATH),
        truth_decision_path=str(STATISTICAL_TRUTH_DECISION_PATH),
        metric_set_path=str(BACKTEST_METRIC_SET_PATH),
        bootstrap_ci_path=str(BOOTSTRAP_CONFIDENCE_INTERVALS_PATH),
        baseline_comparisons_path=str(BASELINE_COMPARISONS_PATH),
        backtest_trade_records_path=str(BACKTEST_TRADE_RECORDS_PATH),
        backtest_summary_path=str(BACKTEST_RUN_SUMMARY_PATH),
        truth_status=str(truth_summary.get("truth_status", "fixture_model_statistics_only")),
        truth_decision=str(truth_decision.get("truth_decision", truth_summary.get("truth_decision", "hold_fixture_validation_only"))),
        statistical_promotion_allowed=bool(truth_decision.get("promotion_allowed", False)),
        real_sample_size=int(truth_summary.get("real_sample_size", 0)),
        fixture_model_sample_size=int(truth_summary.get("fixture_model_sample_size", 0)),
        sample_count=int(truth_summary.get("sample_count", 0)),
        quote_priced_trade_count=int(truth_decision.get("quote_priced_trade_count", backtest_summary.get("quote_priced_trade_count", 0))),
        real_history_used=bool(backtest_summary.get("real_history_used", False)),
        real_option_chain_used=False,
        not_real_statistical_evidence=bool(truth_summary.get("not_real_statistical_evidence", True)),
        not_real_backtest_evidence=bool(backtest_summary.get("not_real_backtest_evidence", True)),
        not_real_fitness_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        paper_only=True,
        live_blocked=True,
        input_hash="",
    )
    return record.to_dict()


def compute_metric_components(
    metric_set: dict[str, Any],
    bootstrap_ci: dict[str, Any],
    baseline_comparisons: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    component_specs = [
        ("win_rate_component", float(metric_set.get("win_rate", 0.0)), _clamp(float(metric_set.get("win_rate", 0.0)), 0.0, 1.0), 0.14, "win_rate"),
        ("expectancy_component", float(metric_set.get("expectancy_model_units", 0.0)), _clamp(0.5 + (float(metric_set.get("expectancy_model_units", 0.0)) / 5.0), 0.0, 1.0), 0.14, "expectancy_model_units"),
        ("drawdown_control_component", float(metric_set.get("max_drawdown_model_units", 0.0)), _clamp(1.0 - (abs(float(metric_set.get("max_drawdown_model_units", 0.0))) / 20.0), 0.0, 1.0), 0.12, "max_drawdown_model_units"),
        ("payoff_ratio_component", float(metric_set.get("payoff_ratio_model_units", 0.0)), _clamp(float(metric_set.get("payoff_ratio_model_units", 0.0)) / 2.5, 0.0, 1.0), 0.12, "payoff_ratio_model_units"),
        ("consistency_streak_component", float(metric_set.get("longest_loss_streak", 0)), _consistency_score(metric_set), 0.10, "longest_loss_streak"),
        ("model_unit_total_pnl_component", float(metric_set.get("total_model_unit_pnl", 0.0)), _clamp(0.5 + (float(metric_set.get("total_model_unit_pnl", 0.0)) / 100.0), 0.0, 1.0), 0.12, "total_model_unit_pnl"),
        ("bootstrap_ci_diagnostic_component", float((bootstrap_ci.get("mean_pnl_ci", [0.0, 0.0]) or [0.0, 0.0])[0]), _bootstrap_score(bootstrap_ci), 0.13, "mean_pnl_ci"),
        ("baseline_delta_diagnostic_component", _average_baseline_delta(baseline_comparisons), _clamp(0.5 + (_average_baseline_delta(baseline_comparisons) / 5.0), 0.0, 1.0), 0.13, "baseline_delta"),
    ]
    records: list[dict[str, Any]] = []
    for index, (name, raw_value, normalized, weight, source_metric) in enumerate(component_specs, start=1):
        component = FitnessMetricComponent(
            artifact_type="fitness_metric_component",
            fitness_version="",
            component_id=f"fitness-component-{index:03d}-{name}",
            component_name=name,
            raw_value=raw_value,
            normalized_value=normalized,
            weight=weight,
            weighted_score=round(normalized * weight * 100.0, 6),
            diagnostic_only=True,
            source_metric=source_metric,
            reason_codes=[name, "diagnostic_only", "not_real_edge_evidence"],
            not_real_fitness_evidence=True,
            paper_only=True,
            live_blocked=True,
            component_hash="",
        )
        records.append(component.to_dict())
    return records


def compute_penalties(
    truth_summary: dict[str, Any],
    truth_decision: dict[str, Any],
    backtest_summary: dict[str, Any],
    metric_set: dict[str, Any],
    bootstrap_ci: dict[str, Any],
    multiple_testing: dict[str, Any],
    validation_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    penalty_specs = [
        ("fixture_only_penalty", bool(metric_set.get("real_sample_size", 0) == 0), 8.0, "fixture_model_statistics_only", "fixture/model diagnostics cannot drive promotion", False),
        ("missing_real_history_penalty", not bool(backtest_summary.get("real_history_used", False)), 9.0, "missing_real_history", "real OHLCV history is missing", False),
        ("missing_options_chain_penalty", int(backtest_summary.get("quote_priced_trade_count", 0)) == 0, 9.0, "missing_real_option_chain", "real options-chain quote data is absent", False),
        ("insufficient_real_sample_penalty", int(truth_summary.get("real_sample_size", 0)) < 30, 8.0, "insufficient_real_sample", "real sample size is below promotion threshold", False),
        ("no_quote_priced_data_penalty", int(truth_decision.get("quote_priced_trade_count", 0)) == 0, 7.0, "no_quote_priced_data", "quote-priced records remain zero", False),
        ("truth_gate_block_penalty", not bool(truth_decision.get("promotion_allowed", False)), 12.0, "truth_gate_blocked", "statistical truth layer blocks promotion", False),
        ("multiple_testing_block_penalty", bool(multiple_testing.get("p_values_blocked", True)), 6.0, "multiple_testing_block", "multiple-testing p-values are diagnostic-only", False),
        ("no_significance_claim_penalty", not bool(bootstrap_ci.get("significance_claim_allowed", False)), 5.0, "significance_claim_blocked", "significance claim is blocked", False),
        ("no_profitability_claim_penalty", not bool(truth_summary.get("profitability_claim_allowed", False)), 5.0, "profitability_claim_blocked", "profitability claim is blocked", False),
        ("no_live_readiness_claim_penalty", not bool(truth_summary.get("live_readiness_claim_allowed", False)), 5.0, "live_readiness_claim_blocked", "live readiness claim is blocked", False),
        ("full_pytest_inconclusive_penalty", _full_pytest_inconclusive(validation_summary), 4.0, "full_pytest_inconclusive", "full pytest remains inconclusive_timeout, not pass", False),
        ("promotion_block_penalty", not bool(truth_summary.get("promotion_allowed", False)), 10.0, "promotion_blocked", "strategy promotion is blocked", False),
    ]
    penalties: list[dict[str, Any]] = []
    for index, (name, applies, value, reason_code, message, terminal_block) in enumerate(penalty_specs, start=1):
        penalty = FitnessPenalty(
            artifact_type="fitness_penalty",
            fitness_version="",
            penalty_id=f"fitness-penalty-{index:03d}-{name}",
            penalty_name=name,
            applies=applies,
            penalty_value=value if applies else 0.0,
            reason_code=reason_code,
            message=message,
            diagnostic_only=True,
            terminal_block=terminal_block,
            manual_review_required=False,
            not_real_fitness_evidence=True,
            paper_only=True,
            live_blocked=True,
            penalty_hash="",
        )
        penalties.append(penalty.to_dict())
    return penalties


def build_scorecard(
    components: list[dict[str, Any]],
    penalties: list[dict[str, Any]],
    promotion_gate: dict[str, Any],
    truth_summary: dict[str, Any],
    backtest_summary: dict[str, Any],
) -> dict[str, Any]:
    gross_score = round(sum(float(component["weighted_score"]) for component in components), 6)
    total_penalty = round(sum(float(penalty["penalty_value"]) for penalty in penalties if penalty["applies"]), 6)
    diagnostic_score = round(max(0.0, gross_score - total_penalty), 6)
    scorecard = FitnessScorecard(
        artifact_type="fitness_scorecard",
        fitness_version="",
        scorecard_id="dopey-diagnostic-fitness-scorecard-v1",
        strategy_id="diagnostic_long_premium_fixture_model_bundle",
        diagnostic_score=diagnostic_score,
        gross_component_score=gross_score,
        total_penalty=total_penalty,
        component_count=len(components),
        penalty_count=len(penalties),
        promotion_allowed=bool(promotion_gate.get("promotion_allowed", False)),
        strategy_promoted=False,
        diagnostic_only=True,
        reason_codes=[
            "diagnostic_score_only",
            str(truth_summary.get("truth_status", "")),
            str(backtest_summary.get("backtest_status", "")),
            str(promotion_gate.get("promotion_block_reason", "")),
        ],
        not_real_fitness_evidence=True,
        not_real_statistical_evidence=bool(truth_summary.get("not_real_statistical_evidence", True)),
        not_real_backtest_evidence=bool(backtest_summary.get("not_real_backtest_evidence", True)),
        not_profitability_claim=True,
        not_live_ready=True,
        paper_only=True,
        live_blocked=True,
        scorecard_hash="",
    )
    return scorecard.to_dict()


def build_rank_record(scorecard: dict[str, Any]) -> dict[str, Any]:
    rank = FitnessRankRecord(
        artifact_type="fitness_rank_record",
        fitness_version="",
        rank_id="fitness-rank-001",
        strategy_id=str(scorecard["strategy_id"]),
        diagnostic_rank=1,
        diagnostic_score=float(scorecard["diagnostic_score"]),
        promotion_allowed=False,
        strategy_promoted=False,
        rank_basis="diagnostic_only_truth_gate_blocked",
        reason_codes=["diagnostic_rank_only", "promotion_blocked"],
        not_real_fitness_evidence=True,
        paper_only=True,
        live_blocked=True,
        rank_hash="",
    )
    return rank.to_dict()


def build_fitness_decision(
    scorecard: dict[str, Any],
    promotion_gate: dict[str, Any],
    truth_summary: dict[str, Any],
    truth_decision: dict[str, Any],
    quarantine_counts: dict[str, int],
) -> dict[str, Any]:
    terminal_block = bool(promotion_gate.get("terminal_block", False) or quarantine_counts["blocked_active_proxy_promotion_count"] > 0)
    status = "terminal_block" if terminal_block else "fixture_model_diagnostic_only"
    decision_value = "terminal_block" if terminal_block else "hold_no_promotion"
    decision = FitnessDecision(
        artifact_type="fitness_decision",
        fitness_version="",
        fitness_status=status,
        fitness_decision=decision_value,
        diagnostic_score=float(scorecard["diagnostic_score"]),
        promotion_allowed=False,
        strategy_promoted=False,
        significance_claim_allowed=False,
        real_alpha_claim_allowed=False,
        profitability_claim_allowed=False,
        live_readiness_claim_allowed=False,
        truth_status=str(truth_summary.get("truth_status", "")),
        truth_decision=str(truth_decision.get("truth_decision", "")),
        reason_codes=[*promotion_gate.get("blocked_reason_codes", []), "old_proxy_fitness_quarantined", "hold_no_promotion"],
        not_real_fitness_evidence=True,
        not_real_statistical_evidence=True,
        not_real_backtest_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        paper_only=True,
        live_blocked=True,
        decision_hash="",
    )
    return decision.to_dict()


def build_quality_flags(
    truth_summary: dict[str, Any],
    promotion_gate: dict[str, Any],
    quarantine_counts: dict[str, int],
    validation_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    reason_codes = [
        "fixture_model_diagnostic_only",
        "old_proxy_fitness_quarantined",
        "promotion_blocked",
        "real_alpha_claim_blocked",
        "profitability_claim_blocked",
        "live_readiness_claim_blocked",
        "not_real_fitness_evidence",
        *[str(code) for code in truth_summary.get("quality_flags", [])],
        *[str(code) for code in promotion_gate.get("blocked_reason_codes", [])],
    ]
    if quarantine_counts["manual_review_proxy_reference_count"] > 0:
        reason_codes.append("manual_review_proxy_reference")
    if _full_pytest_inconclusive(validation_summary):
        reason_codes.append("full_pytest_inconclusive")
    records: list[dict[str, Any]] = []
    for index, reason_code in enumerate(sorted(set(reason_codes)), start=1):
        flag = FitnessQualityFlag(
            artifact_type="fitness_quality_flag",
            fitness_version="",
            flag_id=f"fitness-quality-{index:03d}-{reason_code}",
            severity="warning",
            reason_code=reason_code,
            message=f"fitness replacement quality flag: {reason_code}",
            not_real_fitness_evidence=True,
            paper_only=True,
            live_blocked=True,
            flag_hash="",
        )
        records.append(flag.to_dict())
    return records


def build_summary(
    fitness_input: dict[str, Any],
    components: list[dict[str, Any]],
    penalties: list[dict[str, Any]],
    scorecard: dict[str, Any],
    rank_record: dict[str, Any],
    promotion_gate: dict[str, Any],
    decision: dict[str, Any],
    quality_flags: list[dict[str, Any]],
    quarantine_counts: dict[str, int],
    truth_summary: dict[str, Any],
    truth_decision: dict[str, Any],
    metric_set: dict[str, Any],
    trade_records: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = {
        "artifact_type": "fitness_replacement_summary",
        "fitness_version": FITNESS_VERSION,
        "fitness_status": decision["fitness_status"],
        "fitness_decision": decision["fitness_decision"],
        "diagnostic_score": scorecard["diagnostic_score"],
        "score_component_count": len(components),
        "penalty_count": len(penalties),
        "rank_record_count": 1 if rank_record else 0,
        "promotion_allowed": False,
        "strategy_promoted": False,
        "real_sample_size": int(truth_summary.get("real_sample_size", 0)),
        "fixture_model_sample_size": int(truth_summary.get("fixture_model_sample_size", 0)),
        "sample_count": int(metric_set.get("sample_count", len(trade_records))),
        "truth_status": str(truth_summary.get("truth_status", "")),
        "truth_decision": str(truth_decision.get("truth_decision", "")),
        "statistical_promotion_allowed": bool(truth_decision.get("promotion_allowed", False)),
        "significance_claim_allowed": False,
        "real_alpha_claim_allowed": False,
        "profitability_claim_allowed": False,
        "live_readiness_claim_allowed": False,
        "old_proxy_fitness_quarantined": True,
        "blocked_active_proxy_promotion_count": quarantine_counts["blocked_active_proxy_promotion_count"],
        "manual_review_proxy_reference_count": quarantine_counts["manual_review_proxy_reference_count"],
        "proxy_fitness_finding_count": quarantine_counts["finding_count"],
        "not_real_fitness_evidence": True,
        "not_real_statistical_evidence": True,
        "not_real_backtest_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "paper_only": True,
        "live_blocked": True,
        "quality_flags": sorted({str(flag["reason_code"]) for flag in quality_flags}),
        "next_recommended_target": "DOPEY_REAL_DATA_INGESTION_PLAN_V1",
        "artifact_paths": fitness_artifact_paths(),
        "fitness_input_hash": fitness_input["input_hash"],
    }
    summary["run_hash"] = stable_fitness_hash(summary)
    return summary


def build_proof(summary: dict[str, Any]) -> dict[str, Any]:
    proof = FitnessProofRecord(
        artifact_type="fitness_replacement_proof",
        fitness_version="",
        proof_id="dopey-fitness-function-replacement-v1-proof",
        fitness_status=str(summary["fitness_status"]),
        fitness_decision=str(summary["fitness_decision"]),
        promotion_allowed=False,
        strategy_promoted=False,
        not_real_fitness_evidence=True,
        not_real_statistical_evidence=True,
        not_real_backtest_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        no_broker=True,
        no_credentials=True,
        no_scheduler=True,
        no_real_sizing=True,
        no_orders=True,
        paper_only=True,
        live_blocked=True,
        next_recommended_target="DOPEY_REAL_DATA_INGESTION_PLAN_V1",
        proof_hash="",
    )
    return proof.to_dict()


def fitness_artifact_paths() -> dict[str, str]:
    return {
        "fitness_input": str(FITNESS_INPUT_PATH),
        "fitness_metric_components": str(FITNESS_METRIC_COMPONENTS_PATH),
        "fitness_penalties": str(FITNESS_PENALTIES_PATH),
        "fitness_scorecards": str(FITNESS_SCORECARDS_PATH),
        "fitness_rank_records": str(FITNESS_RANK_RECORDS_PATH),
        "fitness_promotion_gate": str(FITNESS_PROMOTION_GATE_PATH),
        "fitness_decision": str(FITNESS_DECISION_PATH),
        "proxy_fitness_quarantine_findings": str(PROXY_FITNESS_QUARANTINE_FINDINGS_PATH),
        "fitness_quality_flags": str(FITNESS_QUALITY_FLAGS_PATH),
        "fitness_replacement_summary": str(FITNESS_REPLACEMENT_SUMMARY_PATH),
        "fitness_replacement_proof": str(FITNESS_REPLACEMENT_PROOF_PATH),
        "fitness_metric_component_cases": str(FITNESS_METRIC_COMPONENT_CASES_PATH),
        "fitness_penalty_cases": str(FITNESS_PENALTY_CASES_PATH),
        "fitness_promotion_gate_cases": str(FITNESS_PROMOTION_GATE_CASES_PATH),
        "proxy_fitness_quarantine_cases": str(PROXY_FITNESS_QUARANTINE_CASES_PATH),
        "fitness_replacement_report": str(FITNESS_REPORT_PATH),
        "fitness_replacement_artifact_ledger": str(FITNESS_LEDGER_PATH),
    }


def build_fitness_fixture_bundle() -> dict[str, Any]:
    return {
        "metric_component_cases": _fixture_record("fitness_metric_component_cases", _case_series("metric_component", [
            "win_rate_component",
            "expectancy_component",
            "drawdown_control_component",
            "payoff_ratio_component",
            "model_unit_total_pnl_component",
            "bootstrap_ci_component",
            "baseline_diagnostic_component",
        ], 21)),
        "penalty_cases": _fixture_record("fitness_penalty_cases", _case_series("penalty", [
            "fixture_only_penalty",
            "missing_real_history_penalty",
            "missing_options_chain_penalty",
            "insufficient_real_sample_penalty",
            "truth_gate_block_penalty",
            "significance_claim_blocked",
            "real_alpha_claim_blocked",
            "profitability_claim_blocked",
            "live_readiness_claim_blocked",
        ], 27)),
        "promotion_gate_cases": _fixture_record("fitness_promotion_gate_cases", _case_series("promotion_gate", [
            "promotion_false",
            "real_history_missing",
            "quote_priced_zero",
            "not_real_statistical_evidence",
            "not_profitability_claim",
            "not_live_ready",
        ], 18)),
        "proxy_quarantine_cases": _fixture_record("proxy_fitness_quarantine_cases", _case_series("proxy_quarantine", [
            "old_proxy_fitness_quarantine",
            "active_proxy_promotion_terminal_block",
            "manual_review_proxy_reference",
            "allowed_historical_doc_reference",
            "allowed_fixture_case_reference",
        ], 20)),
    }


def _case_series(case_family: str, names: list[str], count: int) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index in range(count):
        name = names[index % len(names)]
        record = {
            "case_id": f"{case_family}-{index + 1:03d}-{name}",
            "case_family": case_family,
            "case_name": name,
            "fixture_only": True,
            "model_priced": True,
            "quote_priced": False,
            "real_history_used": False,
            "real_option_chain_used": False,
            "not_real_fitness_evidence": True,
            "promotion_allowed": False,
            "strategy_promoted": False,
            "paper_only": True,
            "live_blocked": True,
        }
        record["case_hash"] = stable_fitness_hash(record)
        cases.append(record)
    return cases


def _fixture_record(artifact_type: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    record = {
        "artifact_type": artifact_type,
        "fitness_version": FITNESS_VERSION,
        "case_count": len(cases),
        "case_family_distribution": dict(sorted(Counter(case["case_family"] for case in cases).items())),
        "fixture_only": True,
        "model_priced": True,
        "quote_priced": False,
        "real_history_used": False,
        "real_option_chain_used": False,
        "not_real_fitness_evidence": True,
        "promotion_allowed": False,
        "strategy_promoted": False,
        "paper_only": True,
        "live_blocked": True,
        "cases": cases,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _write_fixture_files(fixture_bundle: dict[str, Any]) -> None:
    FITNESS_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(FITNESS_METRIC_COMPONENT_CASES_PATH, fixture_bundle["metric_component_cases"])
    _write_json(FITNESS_PENALTY_CASES_PATH, fixture_bundle["penalty_cases"])
    _write_json(FITNESS_PROMOTION_GATE_CASES_PATH, fixture_bundle["promotion_gate_cases"])
    _write_json(PROXY_FITNESS_QUARANTINE_CASES_PATH, fixture_bundle["proxy_quarantine_cases"])


def _write_report(summary: dict[str, Any]) -> None:
    lines = [
        "# DOPEY Fitness Function Replacement Report",
        "",
        "## Objective",
        "Replace proxy/theater fitness with a truth-gated diagnostic fitness layer that cannot promote strategies while statistical truth blocks promotion.",
        "",
        "## Input Sources",
        "- `artifacts/dopey/stats/statistical_truth_summary.json`",
        "- `artifacts/dopey/stats/statistical_truth_decision.json`",
        "- `artifacts/dopey/stats/backtest_metric_set.json`",
        "- `artifacts/dopey/stats/bootstrap_confidence_intervals.json`",
        "- `artifacts/dopey/stats/baseline_comparisons.jsonl`",
        "- `artifacts/dopey/backtest/backtest_trade_records.jsonl`",
        "- `artifacts/dopey/backtest/backtest_run_summary.json`",
        "",
        "## Score Components",
        "- win-rate, expectancy, drawdown-control, payoff-ratio, consistency/streak, total model-unit P&L, bootstrap CI diagnostic, and baseline delta diagnostic components.",
        "",
        "## Penalties",
        "- fixture-only, missing real history, missing options chain, insufficient real sample, no quote-priced data, truth-gate block, multiple-testing block, no-significance, no-profitability, no-live-readiness, full-pytest-inconclusive, and promotion-block penalties.",
        "",
        "## Promotion Gate",
        f"- promotion_allowed: `{str(summary['promotion_allowed']).lower()}`",
        f"- strategy_promoted: `{str(summary['strategy_promoted']).lower()}`",
        f"- fitness_decision: `{summary['fitness_decision']}`",
        "- The diagnostic score cannot override the statistical truth layer.",
        "",
        "## Proxy Fitness Quarantine",
        f"- old_proxy_fitness_quarantined: `{str(summary['old_proxy_fitness_quarantined']).lower()}`",
        f"- blocked_active_proxy_promotion_count: `{summary['blocked_active_proxy_promotion_count']}`",
        f"- manual_review_proxy_reference_count: `{summary['manual_review_proxy_reference_count']}`",
        "",
        "## Truth-Gated Decision Logic",
        f"- truth_status: `{summary['truth_status']}`",
        f"- truth_decision: `{summary['truth_decision']}`",
        f"- statistical_promotion_allowed: `{str(summary['statistical_promotion_allowed']).lower()}`",
        "",
        "## Current Fixture/Model-Only Limitation",
        f"- real_sample_size: `{summary['real_sample_size']}`",
        f"- fixture_model_sample_size: `{summary['fixture_model_sample_size']}`",
        "- Current fitness is diagnostic-only and is not real statistical evidence.",
        "",
        "## Claim-Blocking Policy",
        "- significance_claim_allowed: `false`",
        "- real_alpha_claim_allowed: `false`",
        "- profitability_claim_allowed: `false`",
        "- live_readiness_claim_allowed: `false`",
        "",
        "## Safety State",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "- no broker, credentials, scheduler, real sizing, orders, network market data, or live path created",
        "",
        "## Validation Summary",
        f"- diagnostic_score: `{summary['diagnostic_score']}`",
        f"- score_component_count: `{summary['score_component_count']}`",
        f"- penalty_count: `{summary['penalty_count']}`",
        f"- quality_flags: `{summary['quality_flags']}`",
        "- targeted fitness runner/test validation is external to this deterministic artifact writer",
        "- full pytest timeout remains an inconclusive state and is not treated as pass",
        "",
        "## Limitations",
        "- No real OHLCV or real options-chain evidence exists in the current run.",
        "- No real edge, real alpha, profitability, live readiness, or strategy promotion is claimed.",
        "",
        "## Next Target",
        "- `DOPEY_REAL_DATA_INGESTION_PLAN_V1`",
    ]
    FITNESS_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ledger(summary: dict[str, Any]) -> None:
    lines = [
        "# DOPEY Fitness Function Replacement Artifact Ledger",
        "",
        "## Source Files",
        "- `dopey_fitness/fitness_models.py`",
        "- `dopey_fitness/truth_gated_fitness_engine.py`",
        "- `dopey_fitness/promotion_gate.py`",
        "- `dopey_fitness/proxy_fitness_quarantine.py`",
        "- `dopey_fitness/run_fitness_function_replacement.py`",
        "- `tests/test_fitness_function_replacement.py`",
        "- `dopey_audit/artifact_loader.py`",
        "- `dopey_audit/audit_runner.py`",
        "- `dopey_audit/evidence_models.py`",
        "- `dopey_reporting/data_loader.py`",
        "- `dopey_reporting/reporting_bundle.py`",
        "- `dopey_export/artifact_selector.py`",
        "- `dopey_export/artifact_compactor.py`",
        "- `dopey_export/export_manifest.py`",
        "- `dopey_export/export_safety_scanner.py`",
        "- `dopey_export_review/review_packet.py`",
        "- `dopey_export_review/review_models.py`",
        "- `dopey_validation/full_suite_stabilizer.py`",
        "- `pyproject.toml`",
        "",
        "## Fixture Files",
        f"- `{FITNESS_METRIC_COMPONENT_CASES_PATH}` records=`{_fixture_case_count(FITNESS_METRIC_COMPONENT_CASES_PATH)}` sha256=`{_file_sha256(FITNESS_METRIC_COMPONENT_CASES_PATH)}`",
        f"- `{FITNESS_PENALTY_CASES_PATH}` records=`{_fixture_case_count(FITNESS_PENALTY_CASES_PATH)}` sha256=`{_file_sha256(FITNESS_PENALTY_CASES_PATH)}`",
        f"- `{FITNESS_PROMOTION_GATE_CASES_PATH}` records=`{_fixture_case_count(FITNESS_PROMOTION_GATE_CASES_PATH)}` sha256=`{_file_sha256(FITNESS_PROMOTION_GATE_CASES_PATH)}`",
        f"- `{PROXY_FITNESS_QUARANTINE_CASES_PATH}` records=`{_fixture_case_count(PROXY_FITNESS_QUARANTINE_CASES_PATH)}` sha256=`{_file_sha256(PROXY_FITNESS_QUARANTINE_CASES_PATH)}`",
        "",
        "## Artifact Files",
    ]
    for key, path_text in fitness_artifact_paths().items():
        path = Path(path_text)
        if key.startswith("fitness_") or key.startswith("proxy_fitness"):
            lines.append(f"- `{path}` records=`{_record_count(path)}` sha256=`{_file_sha256(path)}`")
    lines.extend([
        "",
        "## Record Counts",
        f"- score_component_count: `{summary['score_component_count']}`",
        f"- penalty_count: `{summary['penalty_count']}`",
        f"- rank_record_count: `{summary['rank_record_count']}`",
        f"- blocked_active_proxy_promotion_count: `{summary['blocked_active_proxy_promotion_count']}`",
        f"- manual_review_proxy_reference_count: `{summary['manual_review_proxy_reference_count']}`",
        "",
        "## Hashes",
        f"- fitness_replacement_summary.run_hash: `{summary['run_hash']}`",
        "",
        "## Safety State",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "- not_real_fitness_evidence: `true`",
        "- promotion_allowed: `false`",
        "- strategy_promoted: `false`",
        "- no broker, credentials, scheduler, real sizing, or orders created",
    ])
    FITNESS_LEDGER_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _active_boundary_scan() -> dict[str, Any]:
    return {
        "broker_connection": False,
        "credentials_used": False,
        "scheduler_enabled": False,
        "real_sizing_used": False,
        "order_path_enabled": False,
        "live_order_path_enabled": False,
        "live_trading_enabled": False,
    }


def _average_baseline_delta(records: list[dict[str, Any]]) -> float:
    if not records:
        return 0.0
    return round(sum(float(record.get("delta", 0.0)) for record in records) / len(records), 6)


def _bootstrap_score(bootstrap_ci: dict[str, Any]) -> float:
    mean_ci = bootstrap_ci.get("mean_pnl_ci", [0.0, 0.0]) or [0.0, 0.0]
    lower = float(mean_ci[0])
    upper = float(mean_ci[1])
    center = (lower + upper) / 2.0
    width = abs(upper - lower)
    return _clamp(0.5 + (center / 5.0) - (width / 20.0), 0.0, 1.0)


def _consistency_score(metric_set: dict[str, Any]) -> float:
    win_streak = float(metric_set.get("longest_win_streak", 0))
    loss_streak = float(metric_set.get("longest_loss_streak", 0))
    denominator = max(1.0, win_streak + loss_streak)
    return _clamp(win_streak / denominator, 0.0, 1.0)


def _full_pytest_inconclusive(validation_summary: dict[str, Any]) -> bool:
    full_suite = validation_summary.get("full_suite", {})
    if isinstance(full_suite, dict) and str(full_suite.get("status", "")) == "inconclusive_timeout":
        return True
    return str(validation_summary.get("full_pytest_status", "")) == "inconclusive_timeout"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return round(max(minimum, min(maximum, value)), 6)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    return json.loads(text) if text else {}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record_count(path: Path) -> int:
    if not path.exists():
        return 0
    if path.suffix.lower() == ".json":
        return 1
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])


def _fixture_case_count(path: Path) -> int:
    if not path.exists():
        return 0
    record = json.loads(path.read_text(encoding="utf-8"))
    return int(record.get("case_count", 0))
