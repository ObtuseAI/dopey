"""Evidence-gated aggressiveness and sharpness tuning for DOPEY.

This layer turns baseline, era, forward, exit, volatility, attention, and
allocation evidence into deterministic paper-only decisions. It never mutates
signals, live settings, broker state, or the source allocation fixtures.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Callable

from dopey_backtest.baseline_arbitration import BASELINE_POLICY_VERSION
from dopey_backtest.era_walk_forward import ERA_POLICY_VERSION
from dopey_backtest.forward_evidence_integrity import (
    POLICY_REPLAY_PATH,
    classify_outcomes,
)
from dopey_backtest.trade_records_recovery import (
    iter_verified_trade_records,
    resolve_default_backtest_trade_ledger,
)
from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_core.repo_paths import REPORTS_DIR

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_ROOT = REPO_ROOT / "artifacts" / "dopey"
BACKTEST_ROOT = ARTIFACT_ROOT / "backtest"
FORWARD_ROOT = ARTIFACT_ROOT / "forward_walk"
SHARPNESS_ROOT = ARTIFACT_ROOT / "sharpness"

BASELINE_VERDICTS_PATH = BACKTEST_ROOT / "baseline_arbitration_verdicts.jsonl"
BASELINE_SUMMARY_PATH = BACKTEST_ROOT / "baseline_arbitration_summary.json"
ERA_STATS_PATH = BACKTEST_ROOT / "era_walk_forward_cohort_stats.jsonl"
ERA_SUMMARY_PATH = BACKTEST_ROOT / "era_walk_forward_summary.json"
TRADE_RECORDS_PATH = BACKTEST_ROOT / "backtest_trade_records.jsonl"
FORWARD_SUMMARY_PATH = FORWARD_ROOT / "forward_walk_summary.json"
FORWARD_LEDGER_PATH = FORWARD_ROOT / "forward_walk_ledger.json"
READINESS_GATE_PATH = ARTIFACT_ROOT / "broker_readiness" / "action_readiness_gate.json"
FOUNDRY_SUMMARY_PATH = ARTIFACT_ROOT / "indicator_foundry" / "indicator_foundry_summary.json"
COHORT_EXIT_SHADOW_SOURCE_PATH = ARTIFACT_ROOT / "evolution" / "cohort_exit_policy_shadow_results.jsonl"
RAW_ALLOCATION_PLAN_PATH = ARTIFACT_ROOT / "allocation" / "paper_allocation_plan.json"
RAW_ALLOCATION_DECISIONS_PATH = ARTIFACT_ROOT / "allocation" / "paper_allocation_decisions.jsonl"
VOL_TERM_PATH = REPO_ROOT / "dopey_data" / "real" / "raw" / "macro_context" / "vol_term_structure.csv"
ATTENTION_PATH = REPO_ROOT / "dopey_data" / "real" / "raw" / "macro_context" / "wikipedia_pageviews.csv"

COHORT_DECISIONS_PATH = SHARPNESS_ROOT / "cohort_starvation_decisions.jsonl"
SURVIVOR_RANKINGS_PATH = SHARPNESS_ROOT / "cohort_survivor_rankings.jsonl"
SHADOW_RANKINGS_PATH = SHARPNESS_ROOT / "cohort_shadow_rankings.jsonl"
COHORT_EXIT_DECISIONS_PATH = SHARPNESS_ROOT / "cohort_exit_shadow_decisions.jsonl"
FILTER_EXPERIMENTS_PATH = SHARPNESS_ROOT / "shadow_filter_experiments.jsonl"
PORTFOLIO_AGGRESSION_GATE_PATH = SHARPNESS_ROOT / "portfolio_aggression_gate.json"
EVIDENCE_GATED_ALLOCATION_PLAN_PATH = SHARPNESS_ROOT / "evidence_gated_paper_allocation_plan.json"
EVIDENCE_GATED_ALLOCATION_DECISIONS_PATH = SHARPNESS_ROOT / "evidence_gated_paper_allocation_decisions.jsonl"
SHARPNESS_SUMMARY_PATH = SHARPNESS_ROOT / "sharpness_tuning_summary.json"
SHARPNESS_REPORT_PATH = REPORTS_DIR / "DOPEY_SHARPNESS_TUNING_REPORT.md"

MIN_FILTER_SAMPLE = 30
ATTENTION_LOOKBACK = 60
CONFIDENCE_Z_95 = 1.959963984540054


def run_sharpness_tuning() -> dict[str, Any]:
    verdicts = _read_jsonl_required(BASELINE_VERDICTS_PATH)
    baseline_summary = _read_json_required(BASELINE_SUMMARY_PATH)
    era_stats = _read_jsonl_required(ERA_STATS_PATH)
    era_summary = _read_json_required(ERA_SUMMARY_PATH)
    fixture_trade_source = (
        baseline_summary.get("not_readiness_evidence") is True
        and era_summary.get("not_readiness_evidence") is True
    )
    if fixture_trade_source:
        trades = _read_jsonl_required(TRADE_RECORDS_PATH)
    else:
        ledger_resolution = resolve_default_backtest_trade_ledger()
        trades = list(iter_verified_trade_records(ledger_resolution))
    forward_summary = _read_json_required(FORWARD_SUMMARY_PATH)
    forward_ledger = _read_json_required(FORWARD_LEDGER_PATH)
    forward_policy_replay = _read_json_required(POLICY_REPLAY_PATH) if POLICY_REPLAY_PATH.exists() else {}
    readiness = _read_json_required(READINESS_GATE_PATH)
    foundry = _read_json_required(FOUNDRY_SUMMARY_PATH)
    cohort_exit_results = _read_jsonl_required(COHORT_EXIT_SHADOW_SOURCE_PATH)
    raw_allocation_plan = _read_json_required(RAW_ALLOCATION_PLAN_PATH)
    raw_allocation_decisions = _read_jsonl_required(RAW_ALLOCATION_DECISIONS_PATH)

    cohort_decisions = build_cohort_starvation_decisions(verdicts, era_summary)
    trade_quality = build_cohort_trade_quality(trades)
    survivor_rankings, shadow_rankings = build_cohort_rankings(cohort_decisions, era_stats, trade_quality)
    exit_decisions = build_cohort_exit_shadow_decisions(cohort_exit_results, cohort_decisions)
    filter_experiments = build_shadow_filter_experiments(
        trades,
        _read_csv_required(VOL_TERM_PATH),
        _read_csv_required(ATTENTION_PATH),
        cohort_decisions,
    )
    aggression_gate = build_portfolio_aggression_gate(
        baseline_summary,
        era_summary,
        forward_summary,
        forward_ledger,
        forward_policy_replay,
        readiness,
    )
    gated_plan = build_evidence_gated_allocation_plan(raw_allocation_plan, aggression_gate)
    gated_decisions = build_evidence_gated_allocation_decisions(raw_allocation_decisions, aggression_gate)
    summary = build_sharpness_summary(
        cohort_decisions,
        survivor_rankings,
        shadow_rankings,
        exit_decisions,
        filter_experiments,
        aggression_gate,
        foundry,
        gated_plan,
    )

    _write_jsonl(COHORT_DECISIONS_PATH, cohort_decisions)
    _write_jsonl(SURVIVOR_RANKINGS_PATH, survivor_rankings)
    _write_jsonl(SHADOW_RANKINGS_PATH, shadow_rankings)
    _write_jsonl(COHORT_EXIT_DECISIONS_PATH, exit_decisions)
    _write_jsonl(FILTER_EXPERIMENTS_PATH, filter_experiments)
    _write_json(PORTFOLIO_AGGRESSION_GATE_PATH, aggression_gate)
    _write_json(EVIDENCE_GATED_ALLOCATION_PLAN_PATH, gated_plan)
    _write_jsonl(EVIDENCE_GATED_ALLOCATION_DECISIONS_PATH, gated_decisions)
    _write_json(SHARPNESS_SUMMARY_PATH, summary)
    SHARPNESS_REPORT_PATH.write_text(render_sharpness_report(summary, aggression_gate), encoding="utf-8")
    return summary


def build_cohort_starvation_decisions(
    verdicts: list[dict[str, Any]],
    era_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    robust = {str(value) for value in era_summary.get("regime_robust_cohorts", [])}
    decisions: list[dict[str, Any]] = []
    for verdict in sorted(verdicts, key=lambda record: str(record["cohort_id"])):
        cohort_id = str(verdict["cohort_id"])
        reason_codes: list[str] = []
        if bool(verdict.get("worse_than_baseline_ci", False)):
            decision = "starve"
            reason_codes.append("baseline_95ci_upper_bound_below_zero")
        elif not bool(verdict.get("beats_baseline_ci", False)):
            decision = "shadow_only"
            reason_codes.append("baseline_95ci_not_cleared")
        elif cohort_id not in robust:
            decision = "shadow_only"
            reason_codes.append("not_robust_across_all_eras")
        else:
            decision = "survivor"
            reason_codes.append("baseline_and_era_gates_cleared")
        if cohort_id not in robust and "not_robust_across_all_eras" not in reason_codes:
            reason_codes.append("not_robust_across_all_eras")
        decisions.append(
            {
                "artifact_type": "cohort_starvation_decision",
                "cohort_id": cohort_id,
                "signal_family": str(verdict["signal_family"]),
                "candidate_strategy": str(verdict["candidate_strategy"]),
                "decision": decision,
                "baseline_difference_mean": float(verdict["mean_difference"]),
                "baseline_difference_ci_low": float(verdict["difference_ci_low"]),
                "baseline_difference_ci_high": float(verdict["difference_ci_high"]),
                "regime_robust": cohort_id in robust,
                "reason_codes": reason_codes,
                "deletion_allowed": False,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return decisions


def build_cohort_trade_quality(trades: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        cohort_id = f"{trade['signal_family']}|{trade['candidate_strategy']}"
        grouped[cohort_id].append(trade)
    quality: dict[str, dict[str, float]] = {}
    for cohort_id, records in sorted(grouped.items()):
        entry_premium = sum(max(float(record.get("entry_premium", 0.0)), 0.0) for record in records)
        costs = sum(max(float(record.get("trade_cost_premium_units", 0.0)), 0.0) for record in records)
        liquidity_efficiency = _clamp01(1.0 - costs / entry_premium) if entry_premium > 0.0 else 0.0
        iv_values = sorted(float(record.get("iv_proxy_used", 0.0)) for record in records)
        iv_threshold = iv_values[min(int(len(iv_values) * 0.75), len(iv_values) - 1)] if iv_values else 0.0
        high_iv = [record for record in records if float(record.get("iv_proxy_used", 0.0)) >= iv_threshold]
        iv_resilience = (
            sum(1 for record in high_iv if float(record.get("path_pnl", 0.0)) > 0.0) / len(high_iv)
            if high_iv
            else 0.0
        )
        quality[cohort_id] = {
            "liquidity_efficiency": round(liquidity_efficiency, 6),
            "iv_crush_resilience_proxy": round(iv_resilience, 6),
            "high_iv_trade_count": float(len(high_iv)),
        }
    return quality


def build_cohort_rankings(
    decisions: list[dict[str, Any]],
    era_stats: list[dict[str, Any]],
    trade_quality: dict[str, dict[str, float]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    era_by_cohort: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in era_stats:
        era_by_cohort[str(row["cohort_id"])].append(row)
    eligible = [record for record in decisions if record["decision"] != "starve"]
    feature_rows: list[dict[str, Any]] = []
    for decision in eligible:
        cohort_id = str(decision["cohort_id"])
        evaluable_eras = [row for row in era_by_cohort.get(cohort_id, []) if bool(row.get("meets_min_sample", False))]
        era_lower_bound = min((float(row["average_pnl"]) for row in evaluable_eras), default=-1.0)
        quality = trade_quality.get(cohort_id, {})
        feature_rows.append(
            {
                **decision,
                "oos_lower_bound": float(decision["baseline_difference_ci_low"]),
                "era_stability_lower_bound": era_lower_bound,
                "liquidity_efficiency": float(quality.get("liquidity_efficiency", 0.0)),
                "iv_crush_resilience_proxy": float(quality.get("iv_crush_resilience_proxy", 0.0)),
            }
        )
    oos_scores = _minmax([float(row["oos_lower_bound"]) for row in feature_rows])
    era_scores = _minmax([float(row["era_stability_lower_bound"]) for row in feature_rows])
    ranked: list[dict[str, Any]] = []
    for index, row in enumerate(feature_rows):
        rank_score = (
            0.45 * oos_scores[index]
            + 0.25 * era_scores[index]
            + 0.15 * float(row["liquidity_efficiency"])
            + 0.15 * float(row["iv_crush_resilience_proxy"])
        )
        ranked.append(
            {
                "artifact_type": "cohort_evidence_ranking",
                "cohort_id": row["cohort_id"],
                "eligibility": row["decision"],
                "rank_score": round(rank_score, 6),
                "rank_components": {
                    "oos_lower_bound": row["oos_lower_bound"],
                    "era_stability_lower_bound": row["era_stability_lower_bound"],
                    "liquidity_efficiency": row["liquidity_efficiency"],
                    "iv_crush_resilience_proxy": row["iv_crush_resilience_proxy"],
                },
                "ranking_formula": "45% OOS lower bound + 25% worst-era mean + 15% liquidity efficiency + 15% high-IV win-rate proxy",
                "paper_only": True,
                "live_blocked": True,
            }
        )
    ranked.sort(key=lambda record: (-float(record["rank_score"]), str(record["cohort_id"])))
    survivors = [record for record in ranked if record["eligibility"] == "survivor"]
    shadows = [record for record in ranked if record["eligibility"] == "shadow_only"]
    return _add_ranks(survivors), _add_ranks(shadows)


def build_cohort_exit_shadow_decisions(
    exit_results: list[dict[str, Any]],
    cohort_decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cohort_status = {str(record["cohort_id"]): str(record["decision"]) for record in cohort_decisions}
    output: list[dict[str, Any]] = []
    for result in sorted(exit_results, key=lambda record: str(record["cohort_id"])):
        cohort_id = str(result["cohort_id"])
        evidence_status = cohort_status.get(cohort_id, "missing_baseline_verdict")
        if evidence_status == "missing_baseline_verdict":
            decision = "blocked_missing_baseline_verdict"
        elif evidence_status == "starve":
            decision = "rejected_starved_cohort"
        elif evidence_status != "survivor":
            decision = "shadow_only_baseline_or_era_gate_missing"
        elif not bool(result.get("local_exit_promotion_eligible", False)):
            decision = "shadow_only_exit_gate_missing"
        else:
            decision = "shadow_challenger_forward_validation_required"
        output.append(
            {
                **result,
                "artifact_type": "cohort_exit_shadow_decision",
                "cohort_evidence_status": evidence_status,
                "sharpness_decision": decision,
                "automatic_policy_mutation_allowed": False,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return output


def build_shadow_filter_experiments(
    trades: list[dict[str, Any]],
    vol_rows: list[dict[str, str]],
    attention_rows: list[dict[str, str]],
    cohort_decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    vol_features = _build_volatility_features(vol_rows)
    attention_features = _build_attention_features(attention_rows)
    filters: list[tuple[str, Callable[[dict[str, Any]], bool | None]]] = [
        ("vix_below_prior_60d_median", lambda trade: _volatility_filter(trade, vol_features, "vix_below_prior_median")),
        ("front_vol_contango_vix9d_below_vix3m", lambda trade: _volatility_filter(trade, vol_features, "contango")),
        ("attention_contrarian_directional", lambda trade: _attention_filter(trade, attention_features)),
    ]
    experiments: list[dict[str, Any]] = []
    for filter_id, predicate in filters:
        experiments.extend(_evaluate_filter(filter_id, trades, predicate))
    status_by_cohort = {
        str(record["cohort_id"]): str(record["decision"])
        for record in cohort_decisions
    }
    output: list[dict[str, Any]] = []
    for experiment in experiments:
        cohort_id = str(experiment["cohort_id"])
        evidence_status = (
            "portfolio_research_only"
            if cohort_id == "ALL"
            else status_by_cohort.get(cohort_id, "missing_baseline_verdict")
        )
        output.append(
            {
                **experiment,
                "cohort_evidence_status": evidence_status,
                "eligible_for_continued_shadow": evidence_status in {"shadow_only", "survivor"},
            }
        )
    return output


def build_portfolio_aggression_gate(
    baseline_summary: dict[str, Any],
    era_summary: dict[str, Any],
    forward_summary: dict[str, Any],
    forward_ledger: dict[str, Any],
    forward_policy_replay: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    outcomes = classify_outcomes(forward_ledger, forward_policy_replay)
    closed_trades = outcomes["validated"]
    forward_pnls = [float(record.get("path_pnl", 0.0)) for record in closed_trades]
    forward_mean, forward_ci_low, forward_ci_high = _mean_ci_95(forward_pnls)
    required = int(readiness.get("evidence_eta", {}).get("closed_required", 100))
    halt = forward_ledger.get("last_discipline_halt")
    halt_active = isinstance(halt, dict) and int(halt.get("cooldown_sessions_remaining", 0)) > 0
    checks = {
        "cohort_baseline_policy_current": baseline_summary.get("baseline_policy_version") == BASELINE_POLICY_VERSION,
        "any_cohort_beats_matched_baseline_familywise": (
            baseline_summary.get("baseline_policy_version") == BASELINE_POLICY_VERSION
            and int(baseline_summary.get("cohorts_beating_baseline", 0)) > 0
        ),
        "cohort_era_policy_current": era_summary.get("era_policy_version") == ERA_POLICY_VERSION,
        "any_cohort_regime_robust": int(era_summary.get("regime_robust_count", 0)) > 0,
        "forward_sample_sufficient": len(forward_pnls) >= required,
        "forward_mean_positive": forward_mean > 0.0,
        "forward_95ci_low_positive": forward_ci_low > 0.0,
        "no_active_discipline_halt": not halt_active,
    }
    increased_sizing_allowed = all(checks.values())
    if halt_active:
        state = "discipline_halt_starvation_only"
        multiplier = 0.0
    elif not all(
        checks[key]
        for key in (
            "cohort_baseline_policy_current",
            "any_cohort_beats_matched_baseline_familywise",
            "cohort_era_policy_current",
            "any_cohort_regime_robust",
        )
    ):
        state = "shadow_only_minimum_sizing"
        multiplier = 0.10
    elif not all(checks[key] for key in ("forward_sample_sufficient", "forward_mean_positive", "forward_95ci_low_positive")):
        state = "normal_paper_capped_forward_evidence_accruing"
        multiplier = 1.0
    else:
        state = "aggressive_paper_earned"
        multiplier = 1.25
    return {
        "artifact_type": "portfolio_aggression_gate",
        "aggression_state": state,
        "new_paper_risk_multiplier": multiplier,
        "increased_paper_sizing_allowed": increased_sizing_allowed,
        "checks": checks,
        "forward_evidence": {
            "raw_closed_record_count": sum(len(records) for records in outcomes.values()),
            "closed_trade_count": len(forward_pnls),
            "closed_trade_count_required": required,
            "censored_outcome_count": len(outcomes["censored"]),
            "quarantined_outcome_count": len(outcomes["quarantined"]),
            "statistics_exclude_censored_and_quarantined_outcomes": True,
            "mean_pnl": round(forward_mean, 6),
            "mean_pnl_ci_low_95": round(forward_ci_low, 6),
            "mean_pnl_ci_high_95": round(forward_ci_high, 6),
        },
        "discipline_halt": halt,
        "sizing_rule": "paper sizing can exceed 1.0x only after current-policy matched baseline, era, positive forward mean, positive forward 95% CI, sample, and discipline gates all pass",
        "paper_only": True,
        "live_blocked": True,
    }


def build_evidence_gated_allocation_plan(
    raw_plan: dict[str, Any],
    aggression_gate: dict[str, Any],
) -> dict[str, Any]:
    multiplier = float(aggression_gate["new_paper_risk_multiplier"])
    raw_units = float(raw_plan.get("total_paper_premium_risk_units", 0.0))
    return {
        "artifact_type": "evidence_gated_paper_allocation_plan",
        "plan_id": "dopey-evidence-gated-paper-allocation-plan-v1",
        "source_plan_id": str(raw_plan.get("plan_id", "")),
        "source_plan_hash": str(raw_plan.get("plan_hash", "")),
        "aggression_state": str(aggression_gate["aggression_state"]),
        "new_paper_risk_multiplier": multiplier,
        "source_paper_premium_risk_units": raw_units,
        "evidence_gated_paper_premium_risk_units": round(raw_units * multiplier, 6),
        "new_paper_risk_allowed": multiplier > 0.0,
        "increased_paper_sizing_allowed": bool(aggression_gate["increased_paper_sizing_allowed"]),
        "canonical_use": "governs_new_paper_allocations_source_fixture_plan_remains_research_input",
        "paper_only": True,
        "live_blocked": True,
    }


def build_evidence_gated_allocation_decisions(
    raw_decisions: list[dict[str, Any]],
    aggression_gate: dict[str, Any],
) -> list[dict[str, Any]]:
    multiplier = float(aggression_gate["new_paper_risk_multiplier"])
    output: list[dict[str, Any]] = []
    for raw in raw_decisions:
        source_risk = float(raw.get("paper_premium_risk_units", 0.0))
        source_contracts = int(raw.get("max_paper_contract_units", 0))
        gated_risk = round(source_risk * multiplier, 6)
        gated_contracts = 0 if multiplier == 0.0 else source_contracts
        output.append(
            {
                "artifact_type": "evidence_gated_paper_allocation_decision",
                "allocation_id": str(raw["allocation_id"]),
                "opportunity_id": str(raw["opportunity_id"]),
                "source_decision": str(raw["decision"]),
                "evidence_gated_decision": (
                    "evidence_starved_no_new_paper_risk"
                    if source_risk > 0.0 and multiplier == 0.0
                    else str(raw["decision"])
                ),
                "source_paper_premium_risk_units": source_risk,
                "evidence_gated_paper_premium_risk_units": gated_risk,
                "source_max_paper_contract_units": source_contracts,
                "evidence_gated_max_paper_contract_units": gated_contracts,
                "research_attention_weight": float(raw.get("paper_attention_weight", 0.0)),
                "aggression_state": str(aggression_gate["aggression_state"]),
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return output


def build_sharpness_summary(
    cohort_decisions: list[dict[str, Any]],
    survivor_rankings: list[dict[str, Any]],
    shadow_rankings: list[dict[str, Any]],
    exit_decisions: list[dict[str, Any]],
    filter_experiments: list[dict[str, Any]],
    aggression_gate: dict[str, Any],
    foundry: dict[str, Any],
    gated_plan: dict[str, Any],
) -> dict[str, Any]:
    return {
        "artifact_type": "sharpness_tuning_summary",
        "sharpness_status": "complete_paper_only",
        "cohort_count": len(cohort_decisions),
        "starved_cohort_count": sum(record["decision"] == "starve" for record in cohort_decisions),
        "shadow_cohort_count": sum(record["decision"] == "shadow_only" for record in cohort_decisions),
        "survivor_cohort_count": len(survivor_rankings),
        "ranked_shadow_cohort_count": len(shadow_rankings),
        "cohort_exit_shadow_decision_count": len(exit_decisions),
        "shadow_filter_experiment_count": len(filter_experiments),
        "positive_sufficient_filter_result_count": sum(
            bool(record["minimum_sample_sufficient"])
            and bool(record["eligible_for_continued_shadow"])
            and float(record["delta_mean_pnl"]) > 0.0
            for record in filter_experiments
        ),
        "foundry_promoted_indicator_count": int(foundry.get("promoted_count", 0)),
        "aggression_state": aggression_gate["aggression_state"],
        "new_paper_risk_multiplier": aggression_gate["new_paper_risk_multiplier"],
        "increased_paper_sizing_allowed": aggression_gate["increased_paper_sizing_allowed"],
        "evidence_gated_paper_premium_risk_units": gated_plan["evidence_gated_paper_premium_risk_units"],
        "live_blocked": True,
        "paper_only": True,
        "artifact_paths": {
            "cohort_starvation_decisions": str(COHORT_DECISIONS_PATH),
            "cohort_survivor_rankings": str(SURVIVOR_RANKINGS_PATH),
            "cohort_shadow_rankings": str(SHADOW_RANKINGS_PATH),
            "cohort_exit_shadow_decisions": str(COHORT_EXIT_DECISIONS_PATH),
            "shadow_filter_experiments": str(FILTER_EXPERIMENTS_PATH),
            "portfolio_aggression_gate": str(PORTFOLIO_AGGRESSION_GATE_PATH),
            "evidence_gated_paper_allocation_plan": str(EVIDENCE_GATED_ALLOCATION_PLAN_PATH),
            "evidence_gated_paper_allocation_decisions": str(EVIDENCE_GATED_ALLOCATION_DECISIONS_PATH),
            "sharpness_report": str(SHARPNESS_REPORT_PATH),
        },
    }


def render_sharpness_report(summary: dict[str, Any], gate: dict[str, Any]) -> str:
    checks = gate["checks"]
    lines = [
        "# DOPEY Sharpness Tuning Report",
        "",
        "## Outcome",
        f"- status: `{summary['sharpness_status']}`",
        f"- aggression state: `{summary['aggression_state']}`",
        f"- new paper risk multiplier: `{summary['new_paper_risk_multiplier']}`",
        f"- increased paper sizing allowed: `{str(summary['increased_paper_sizing_allowed']).lower()}`",
        f"- starved / shadow / survivor cohorts: `{summary['starved_cohort_count']}` / `{summary['shadow_cohort_count']}` / `{summary['survivor_cohort_count']}`",
        f"- shadow filter results: `{summary['shadow_filter_experiment_count']}`",
        "",
        "## Evidence gates",
    ]
    lines.extend(f"- [{'x' if passed else ' '}] `{name}`" for name, passed in checks.items())
    lines.extend(
        [
            "",
            "## Boundary",
            "- Existing allocation fixtures remain research inputs.",
            "- The evidence-gated plan governs new paper risk.",
            "- No live sizing, broker action, credential use, or order placement is allowed.",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_volatility_features(rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    by_date: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        by_date[str(row["date"])][str(row["symbol"])] = float(row["close"])
    vix_history: list[float] = []
    features: dict[str, dict[str, float]] = {}
    for date in sorted(by_date):
        values = by_date[date]
        current_vix = values.get("VIX")
        if current_vix is None:
            continue
        prior = vix_history[-60:]
        record: dict[str, float] = {"vix": current_vix}
        if len(prior) >= 20:
            record["prior_vix_median_60"] = median(prior)
        if "VIX9D" in values and "VIX3M" in values:
            record["vix9d"] = values["VIX9D"]
            record["vix3m"] = values["VIX3M"]
        features[date] = record
        vix_history.append(current_vix)
    return features


def _build_attention_features(rows: list[dict[str, str]]) -> dict[tuple[str, str], float]:
    by_symbol: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_symbol[str(row["symbol"])].append(row)
    output: dict[tuple[str, str], float] = {}
    for symbol, symbol_rows in sorted(by_symbol.items()):
        history: list[float] = []
        for row in sorted(symbol_rows, key=lambda record: str(record["date"])):
            views = float(row["views"])
            prior = history[-ATTENTION_LOOKBACK:]
            if len(prior) >= ATTENTION_LOOKBACK:
                mean = sum(prior) / len(prior)
                variance = sum((value - mean) ** 2 for value in prior) / (len(prior) - 1)
                deviation = math.sqrt(variance)
                if deviation > 0.0:
                    output[(symbol, str(row["date"]))] = (views - mean) / deviation
            history.append(views)
    return output


def _volatility_filter(
    trade: dict[str, Any],
    features: dict[str, dict[str, float]],
    mode: str,
) -> bool | None:
    record = features.get(str(trade.get("signal_date", "")))
    if record is None:
        return None
    if mode == "vix_below_prior_median":
        if "prior_vix_median_60" not in record:
            return None
        return record["vix"] <= record["prior_vix_median_60"]
    if mode == "contango":
        if "vix9d" not in record or "vix3m" not in record:
            return None
        return record["vix9d"] < record["vix3m"]
    raise ValueError(f"unsupported volatility filter mode: {mode}")


def _attention_filter(
    trade: dict[str, Any],
    features: dict[tuple[str, str], float],
) -> bool | None:
    key = (str(trade.get("symbol", "")), str(trade.get("signal_date", "")))
    attention_z = features.get(key)
    if attention_z is None:
        return None
    strategy = str(trade.get("candidate_strategy", ""))
    if strategy == "long_put":
        return attention_z >= 1.0
    if strategy == "long_call":
        return attention_z <= -1.0
    return False


def _evaluate_filter(
    filter_id: str,
    trades: list[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool | None],
) -> list[dict[str, Any]]:
    comparable: dict[str, list[dict[str, Any]]] = defaultdict(list)
    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        keep = predicate(trade)
        if keep is None:
            continue
        cohort_id = f"{trade['signal_family']}|{trade['candidate_strategy']}"
        for scope in ("ALL", cohort_id):
            comparable[scope].append(trade)
            if keep:
                selected[scope].append(trade)
    results: list[dict[str, Any]] = []
    for scope in sorted(comparable):
        base = comparable[scope]
        kept = selected.get(scope, [])
        base_mean = _mean([float(record["path_pnl"]) for record in base])
        selected_mean = _mean([float(record["path_pnl"]) for record in kept])
        sufficient = len(kept) >= MIN_FILTER_SAMPLE
        results.append(
            {
                "artifact_type": "shadow_filter_experiment",
                "filter_id": filter_id,
                "cohort_id": scope,
                "comparable_trade_count": len(base),
                "selected_trade_count": len(kept),
                "selection_rate": round(len(kept) / len(base), 6) if base else 0.0,
                "comparable_mean_pnl": round(base_mean, 6),
                "selected_mean_pnl": round(selected_mean, 6),
                "delta_mean_pnl": round(selected_mean - base_mean, 6),
                "minimum_sample_required": MIN_FILTER_SAMPLE,
                "minimum_sample_sufficient": sufficient,
                "experiment_status": (
                    "shadow_positive_delta" if sufficient and selected_mean > base_mean else
                    "shadow_nonpositive_delta" if sufficient else
                    "insufficient_sample_accruing"
                ),
                "promotion_allowed": False,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return results


def _mean_ci_95(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    mean = _mean(values)
    if len(values) < 2:
        return mean, mean, mean
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    margin = CONFIDENCE_Z_95 * math.sqrt(variance / len(values))
    return mean, mean - margin, mean + margin


def _minmax(values: list[float]) -> list[float]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if math.isclose(low, high):
        return [0.5 for _ in values]
    return [(value - low) / (high - low) for value in values]


def _add_ranks(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**record, "evidence_rank": index} for index, record in enumerate(records, start=1)]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _read_json_required(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required sharpness input is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"required sharpness JSON input must be an object: {path}")
    return payload


def _read_jsonl_required(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"required sharpness input is missing: {path}")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(record, dict) for record in records):
        raise ValueError(f"required sharpness JSONL input contains a non-object: {path}")
    return records


def _read_csv_required(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"required sharpness input is missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_json(path: Path, record: dict[str, Any]) -> None:
    payload = dict(record)
    payload["reproducibility_hash"] = reproducibility_hash(
        {key: value for key, value in payload.items() if key != "reproducibility_hash"}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    output: list[dict[str, Any]] = []
    for record in records:
        payload = dict(record)
        payload["reproducibility_hash"] = reproducibility_hash(
            {key: value for key, value in payload.items() if key != "reproducibility_hash"}
        )
        output.append(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record, sort_keys=True, ensure_ascii=False) for record in output)
        + ("\n" if output else ""),
        encoding="utf-8",
    )
