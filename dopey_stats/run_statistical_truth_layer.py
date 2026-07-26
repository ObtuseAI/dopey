"""CLI runner for DOPEY's statistical truth layer."""
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

from .baseline_comparison import build_baseline_comparisons
from .bootstrap_truth_engine import bootstrap_confidence_intervals, default_bootstrap_truth_config
from .deflated_sharpe import build_deflated_sharpe_result
from .multiple_testing_guard import build_multiple_testing_adjustment
from .statistical_metric_calculator import (
    build_sample_profile,
    calculate_metric_set,
    load_json,
    load_jsonl,
    pnl_values_from_records,
)
from .statistical_truth_gate import evaluate_statistical_truth_decision
from .statistical_truth_models import (
    STATISTICAL_TRUTH_VERSION,
    StatisticalTruthInput,
    StatisticalTruthProofRecord,
    StatisticalTruthQualityFlag,
    stable_truth_hash,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
STATS_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "stats"
STATS_FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "stats"
BACKTEST_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "backtest"
BACKTEST_RUN_SUMMARY_PATH = BACKTEST_ARTIFACT_DIR / "backtest_run_summary.json"
BACKTEST_TRADE_RECORDS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_trade_records.jsonl"
BACKTEST_QUALITY_FLAGS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_quality_flags.jsonl"
STATISTICAL_TRUTH_INPUT_PATH = STATS_ARTIFACT_DIR / "statistical_truth_input.json"
BACKTEST_SAMPLE_PROFILE_PATH = STATS_ARTIFACT_DIR / "backtest_sample_profile.json"
BACKTEST_METRIC_SET_PATH = STATS_ARTIFACT_DIR / "backtest_metric_set.json"
BOOTSTRAP_CONFIDENCE_INTERVALS_PATH = STATS_ARTIFACT_DIR / "bootstrap_confidence_intervals.json"
BASELINE_COMPARISONS_PATH = STATS_ARTIFACT_DIR / "baseline_comparisons.jsonl"
MULTIPLE_TESTING_ADJUSTMENT_PATH = STATS_ARTIFACT_DIR / "multiple_testing_adjustment.json"
DEFLATED_SHARPE_RESULT_PATH = STATS_ARTIFACT_DIR / "deflated_sharpe_result.json"
STATISTICAL_TRUTH_DECISION_PATH = STATS_ARTIFACT_DIR / "statistical_truth_decision.json"
STATISTICAL_TRUTH_QUALITY_FLAGS_PATH = STATS_ARTIFACT_DIR / "statistical_truth_quality_flags.jsonl"
STATISTICAL_TRUTH_SUMMARY_PATH = STATS_ARTIFACT_DIR / "statistical_truth_summary.json"
STATISTICAL_TRUTH_PROOF_PATH = STATS_ARTIFACT_DIR / "statistical_truth_proof.jsonl"
STATS_METRIC_CASES_PATH = STATS_FIXTURE_DIR / "statistical_truth_metric_cases.json"
STATS_BOOTSTRAP_CASES_PATH = STATS_FIXTURE_DIR / "statistical_truth_bootstrap_cases.json"
STATS_GATE_CASES_PATH = STATS_FIXTURE_DIR / "statistical_truth_gate_cases.json"
STATS_REPORT_PATH = REPORTS_DIR / "DOPEY_STATISTICAL_TRUTH_LAYER_REPORT.md"
STATS_LEDGER_PATH = REPORTS_DIR / "DOPEY_STATISTICAL_TRUTH_LAYER_ARTIFACT_LEDGER.md"


def run_statistical_truth_layer() -> dict[str, Any]:
    ensure_backtest_artifacts()
    fixture_bundle = build_stats_fixture_bundle()
    _write_fixture_files(fixture_bundle)
    backtest_summary = load_json(BACKTEST_RUN_SUMMARY_PATH)
    ledger_resolution = resolve_default_backtest_trade_ledger()
    trade_records = list(iter_verified_trade_records(ledger_resolution))
    backtest_quality_flags = load_jsonl(BACKTEST_QUALITY_FLAGS_PATH)
    truth_input = _truth_input(backtest_summary)
    sample_profile = build_sample_profile(backtest_summary, trade_records)
    metric_set = calculate_metric_set(backtest_summary, trade_records)
    bootstrap_ci = bootstrap_confidence_intervals(
        pnl_values_from_records(trade_records),
        int(sample_profile["real_sample_size"]),
        default_bootstrap_truth_config(),
    )
    baseline_comparisons = build_baseline_comparisons(metric_set, trade_records)
    multiple_testing = build_multiple_testing_adjustment(trade_records)
    deflated_sharpe = build_deflated_sharpe_result(
        metric_set, multiple_testing, pnls=pnl_values_from_records(trade_records)
    )
    quality_flags = _quality_flags(backtest_summary, sample_profile)
    decision = evaluate_statistical_truth_decision(
        backtest_summary,
        sample_profile,
        metric_set,
        bootstrap_ci,
        multiple_testing,
        deflated_sharpe,
        backtest_quality_flags,
        [],
    )
    summary = _summary(
        decision,
        sample_profile,
        metric_set,
        bootstrap_ci,
        baseline_comparisons,
        multiple_testing,
        deflated_sharpe,
        quality_flags,
        backtest_summary,
    )
    proof = _proof(summary)
    STATS_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(STATISTICAL_TRUTH_INPUT_PATH, truth_input)
    _write_json(BACKTEST_SAMPLE_PROFILE_PATH, sample_profile)
    _write_json(BACKTEST_METRIC_SET_PATH, metric_set)
    _write_json(BOOTSTRAP_CONFIDENCE_INTERVALS_PATH, bootstrap_ci)
    _write_jsonl(BASELINE_COMPARISONS_PATH, baseline_comparisons)
    _write_json(MULTIPLE_TESTING_ADJUSTMENT_PATH, multiple_testing)
    _write_json(DEFLATED_SHARPE_RESULT_PATH, deflated_sharpe)
    _write_json(STATISTICAL_TRUTH_DECISION_PATH, decision)
    _write_jsonl(STATISTICAL_TRUTH_QUALITY_FLAGS_PATH, quality_flags)
    _write_json(STATISTICAL_TRUTH_SUMMARY_PATH, summary)
    _write_jsonl(STATISTICAL_TRUTH_PROOF_PATH, [proof])
    _write_report(summary, sample_profile, metric_set, bootstrap_ci, baseline_comparisons, multiple_testing, deflated_sharpe, decision)
    _write_ledger(summary)
    return {
        "truth_status": summary["truth_status"],
        "truth_decision": summary["truth_decision"],
        "sample_count": summary["sample_count"],
        "real_sample_size": summary["real_sample_size"],
        "fixture_model_sample_size": summary["fixture_model_sample_size"],
        "win_rate": summary["win_rate"],
        "average_model_unit_pnl": summary["average_model_unit_pnl"],
        "median_model_unit_pnl": summary["median_model_unit_pnl"],
        "total_model_unit_pnl": summary["total_model_unit_pnl"],
        "max_drawdown_model_units": summary["max_drawdown_model_units"],
        "bootstrap_mean_ci": summary["bootstrap_mean_ci"],
        "bootstrap_win_rate_ci": summary["bootstrap_win_rate_ci"],
        "significance_claim_allowed": summary["significance_claim_allowed"],
        "real_alpha_claim_allowed": summary["real_alpha_claim_allowed"],
        "profitability_claim_allowed": summary["profitability_claim_allowed"],
        "live_readiness_claim_allowed": summary["live_readiness_claim_allowed"],
        "promotion_allowed": summary["promotion_allowed"],
        "quality_flags": summary["quality_flags"],
        "paper_only": summary["paper_only"],
        "live_blocked": summary["live_blocked"],
        "next_recommended_target": summary["next_recommended_target"],
        "artifact_paths": stats_artifact_paths(),
    }


def ensure_backtest_artifacts() -> None:
    if BACKTEST_RUN_SUMMARY_PATH.exists() and BACKTEST_TRADE_RECORDS_PATH.exists() and BACKTEST_QUALITY_FLAGS_PATH.exists():
        return
    from dopey_backtest.run_honest_backtester import run_honest_backtester

    run_honest_backtester()


def stats_artifact_paths() -> dict[str, str]:
    return {
        "statistical_truth_input": str(STATISTICAL_TRUTH_INPUT_PATH),
        "backtest_sample_profile": str(BACKTEST_SAMPLE_PROFILE_PATH),
        "backtest_metric_set": str(BACKTEST_METRIC_SET_PATH),
        "bootstrap_confidence_intervals": str(BOOTSTRAP_CONFIDENCE_INTERVALS_PATH),
        "baseline_comparisons": str(BASELINE_COMPARISONS_PATH),
        "multiple_testing_adjustment": str(MULTIPLE_TESTING_ADJUSTMENT_PATH),
        "deflated_sharpe_result": str(DEFLATED_SHARPE_RESULT_PATH),
        "statistical_truth_decision": str(STATISTICAL_TRUTH_DECISION_PATH),
        "statistical_truth_quality_flags": str(STATISTICAL_TRUTH_QUALITY_FLAGS_PATH),
        "statistical_truth_summary": str(STATISTICAL_TRUTH_SUMMARY_PATH),
        "statistical_truth_proof": str(STATISTICAL_TRUTH_PROOF_PATH),
        "statistical_truth_metric_cases": str(STATS_METRIC_CASES_PATH),
        "statistical_truth_bootstrap_cases": str(STATS_BOOTSTRAP_CASES_PATH),
        "statistical_truth_gate_cases": str(STATS_GATE_CASES_PATH),
        "statistical_truth_report": str(STATS_REPORT_PATH),
        "statistical_truth_artifact_ledger": str(STATS_LEDGER_PATH),
    }


def build_stats_fixture_bundle() -> dict[str, Any]:
    return {
        "metric_cases": _fixture_record("statistical_truth_metric_cases", _metric_cases()),
        "bootstrap_cases": _fixture_record("statistical_truth_bootstrap_cases", _bootstrap_cases()),
        "gate_cases": _fixture_record("statistical_truth_gate_cases", _gate_cases()),
    }


def _truth_input(backtest_summary: dict[str, Any]) -> dict[str, Any]:
    truth_input = StatisticalTruthInput(
        artifact_type="statistical_truth_input",
        statistical_truth_version=STATISTICAL_TRUTH_VERSION,
        backtest_summary_path=str(BACKTEST_RUN_SUMMARY_PATH),
        backtest_trade_records_path=str(BACKTEST_TRADE_RECORDS_PATH),
        backtest_quality_flags_path=str(BACKTEST_QUALITY_FLAGS_PATH),
        backtest_status=str(backtest_summary.get("backtest_status", "missing_real_history_fixture_validation_only")),
        history_dataset_status=str(backtest_summary.get("history_dataset_status", "missing_real_dataset")),
        real_history_used=bool(backtest_summary.get("real_history_used", False)),
        real_option_chain_used=False,
        quote_priced_trade_count=int(backtest_summary.get("quote_priced_trade_count", 0)),
        not_real_backtest_evidence=bool(backtest_summary.get("not_real_backtest_evidence", True)),
        not_profitability_claim=bool(backtest_summary.get("not_profitability_claim", True)),
        not_live_ready=bool(backtest_summary.get("not_live_ready", True)),
        paper_only=True,
        live_blocked=True,
        not_real_statistical_evidence=True,
        input_hash="",
    )
    return truth_input.to_dict()


def _summary(
    decision: dict[str, Any],
    sample_profile: dict[str, Any],
    metric_set: dict[str, Any],
    bootstrap_ci: dict[str, Any],
    baseline_comparisons: list[dict[str, Any]],
    multiple_testing: dict[str, Any],
    deflated_sharpe: dict[str, Any],
    quality_flags: list[dict[str, Any]],
    backtest_summary: dict[str, Any],
) -> dict[str, Any]:
    reason_codes = sorted({str(flag["reason_code"]) for flag in quality_flags})
    summary = {
        "artifact_type": "statistical_truth_summary",
        "statistical_truth_version": STATISTICAL_TRUTH_VERSION,
        "truth_status": decision["truth_status"],
        "truth_decision": decision["truth_decision"],
        "backtest_status": backtest_summary.get("backtest_status", ""),
        "history_dataset_status": backtest_summary.get("history_dataset_status", "missing_real_dataset"),
        "sample_count": metric_set["sample_count"],
        "real_sample_size": sample_profile["real_sample_size"],
        "fixture_model_sample_size": sample_profile["fixture_model_sample_size"],
        "win_rate": metric_set["win_rate"],
        "average_model_unit_pnl": metric_set["average_model_unit_pnl"],
        "median_model_unit_pnl": metric_set["median_model_unit_pnl"],
        "total_model_unit_pnl": metric_set["total_model_unit_pnl"],
        "max_drawdown_model_units": metric_set["max_drawdown_model_units"],
        "bootstrap_mean_ci": bootstrap_ci["mean_pnl_ci"],
        "bootstrap_win_rate_ci": bootstrap_ci["win_rate_ci"],
        "baseline_comparison_count": len(baseline_comparisons),
        "multiple_testing_applied": True,
        "deflated_sharpe_diagnostic": deflated_sharpe["diagnostic_only"],
        "significance_claim_allowed": False,
        "real_alpha_claim_allowed": False,
        "profitability_claim_allowed": False,
        "live_readiness_claim_allowed": False,
        "promotion_allowed": False,
        "not_real_statistical_evidence": True,
        "not_real_backtest_evidence": True,
        "not_profitability_claim": True,
        "not_live_ready": True,
        "paper_only": True,
        "live_blocked": True,
        "quality_flags": reason_codes,
        "artifact_paths": stats_artifact_paths(),
        "next_recommended_target": "DOPEY_FITNESS_FUNCTION_REPLACEMENT_V1",
        "run_hash": "",
    }
    summary["run_hash"] = stable_truth_hash(summary)
    return summary


def _quality_flags(backtest_summary: dict[str, Any], sample_profile: dict[str, Any]) -> list[dict[str, Any]]:
    templates = [
        ("stats-fixture-model-only", "warning", "fixture_model_statistics_only", "statistics are fixture/model diagnostics only", True),
        ("stats-no-real-evidence", "warning", "not_real_statistical_evidence", "fixture/model validation cannot support real statistical evidence", True),
        ("stats-no-promotion", "warning", "promotion_blocked", "strategy promotion is blocked until real data thresholds pass", True),
        ("stats-no-significance", "warning", "significance_claim_blocked", "statistical significance claims are blocked", True),
        ("stats-no-alpha", "warning", "real_alpha_claim_blocked", "real alpha claims are blocked", True),
        ("stats-no-profit", "warning", "profitability_claim_blocked", "profitability claims are blocked", True),
        ("stats-no-live-ready", "warning", "live_readiness_claim_blocked", "live readiness claims are blocked", True),
        ("stats-missing-options-chain", "warning", "missing_real_option_chain", "real options-chain evidence is absent", True),
    ]
    if not bool(backtest_summary.get("real_history_used", False)):
        templates.append(("stats-missing-history", "warning", "missing_real_history", "real OHLCV evidence is absent", True))
    if int(sample_profile.get("real_sample_size", 0)) == 0:
        templates.append(("stats-zero-real-sample", "warning", "insufficient_real_sample", "real sample size is zero", True))
    records: list[dict[str, Any]] = []
    for flag_id, severity, reason_code, message, model_priced in templates:
        flag = StatisticalTruthQualityFlag(
            artifact_type="statistical_truth_quality_flag",
            flag_id=flag_id,
            severity=severity,
            reason_code=reason_code,
            message=message,
            fixture_only=True,
            model_priced=model_priced,
            quote_priced=False,
            real_history_used=False,
            real_option_chain_used=False,
            promotion_allowed=False,
            paper_only=True,
            live_blocked=True,
            not_real_statistical_evidence=True,
            flag_hash="",
        )
        records.append(flag.to_dict())
    return records


def _proof(summary: dict[str, Any]) -> dict[str, Any]:
    proof = StatisticalTruthProofRecord(
        artifact_type="statistical_truth_proof",
        proof_id="dopey-statistical-truth-layer-v1-proof",
        statistical_truth_version=STATISTICAL_TRUTH_VERSION,
        truth_status=str(summary["truth_status"]),
        truth_decision=str(summary["truth_decision"]),
        sample_count=int(summary["sample_count"]),
        real_sample_size=int(summary["real_sample_size"]),
        significance_claim_allowed=False,
        real_alpha_claim_allowed=False,
        profitability_claim_allowed=False,
        live_readiness_claim_allowed=False,
        promotion_allowed=False,
        no_broker=True,
        no_credentials=True,
        no_scheduler=True,
        no_real_sizing=True,
        no_orders=True,
        paper_only=True,
        live_blocked=True,
        not_real_statistical_evidence=True,
        next_recommended_target="DOPEY_FITNESS_FUNCTION_REPLACEMENT_V1",
        proof_hash="",
    )
    return proof.to_dict()


def _metric_cases() -> list[dict[str, Any]]:
    families = ["mean_pnl", "median_pnl", "win_rate", "drawdown", "payoff_ratio", "profit_factor"]
    return [_fixture_case(f"metric-{index:03d}", families[index % len(families)], "model_unit_metric_diagnostic") for index in range(24)]


def _bootstrap_cases() -> list[dict[str, Any]]:
    families = ["bootstrap_mean_ci", "bootstrap_win_rate_ci", "bootstrap_drawdown_ci", "bootstrap_median_ci", "insufficient_sample"]
    return [_fixture_case(f"bootstrap-{index:03d}", families[index % len(families)], "deterministic_seed_ci_diagnostic") for index in range(24)]


def _gate_cases() -> list[dict[str, Any]]:
    families = [
        "missing_real_history",
        "missing_options_chain",
        "no_promotion",
        "no_significance_claim",
        "no_profitability_claim",
        "no_live_readiness_claim",
        "terminal_block_safety_leak",
        "baseline_diagnostic_only",
    ]
    return [_fixture_case(f"gate-{index:03d}", families[index % len(families)], "claim_blocking_gate") for index in range(24)]


def _fixture_record(artifact_type: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    record = {
        "artifact_type": artifact_type,
        "statistical_truth_version": STATISTICAL_TRUTH_VERSION,
        "case_count": len(cases),
        "case_family_distribution": dict(sorted(Counter(case["case_family"] for case in cases).items())),
        "fixture_only": True,
        "model_priced": True,
        "quote_priced": False,
        "real_history_used": False,
        "real_option_chain_used": False,
        "not_real_statistical_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
        "cases": cases,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    return record


def _fixture_case(case_id: str, case_family: str, expected_guard: str) -> dict[str, Any]:
    record = {
        "case_id": case_id,
        "case_family": case_family,
        "expected_guard": expected_guard,
        "fixture_only": True,
        "model_priced": True,
        "quote_priced": False,
        "real_history_used": False,
        "real_option_chain_used": False,
        "not_real_statistical_evidence": True,
        "promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    record["case_hash"] = stable_truth_hash(record)
    return record


def _write_fixture_files(fixture_bundle: dict[str, Any]) -> None:
    STATS_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(STATS_METRIC_CASES_PATH, fixture_bundle["metric_cases"])
    _write_json(STATS_BOOTSTRAP_CASES_PATH, fixture_bundle["bootstrap_cases"])
    _write_json(STATS_GATE_CASES_PATH, fixture_bundle["gate_cases"])


def _write_report(
    summary: dict[str, Any],
    sample_profile: dict[str, Any],
    metric_set: dict[str, Any],
    bootstrap_ci: dict[str, Any],
    baseline_comparisons: list[dict[str, Any]],
    multiple_testing: dict[str, Any],
    deflated_sharpe: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    lines = [
        "# DOPEY Statistical Truth Layer Report",
        "",
        "## Objective",
        "Build a deterministic paper-only truth layer that decides which statistical conclusions are allowed, blocked, incomplete, or manual-review-only.",
        "",
        "## Input Sources",
        f"- backtest summary: `{BACKTEST_RUN_SUMMARY_PATH}`",
        f"- backtest trade records: `{BACKTEST_TRADE_RECORDS_PATH}`",
        f"- backtest quality flags: `{BACKTEST_QUALITY_FLAGS_PATH}`",
        "",
        "## Sample Profile",
        f"- sample_count: `{sample_profile['sample_count']}`",
        f"- real_sample_size: `{sample_profile['real_sample_size']}`",
        f"- fixture_model_sample_size: `{sample_profile['fixture_model_sample_size']}`",
        f"- real_evidence_thresholds_met: `{str(sample_profile['real_evidence_thresholds_met']).lower()}`",
        "",
        "## Metric Definitions",
        "- Metrics use abstract model-unit premium P&L only.",
        "- Win rate, expectancy, payoff ratio, profit factor, Sharpe-like, Sortino-like, and drawdown are diagnostics, not real profitability.",
        f"- average_model_unit_pnl: `{metric_set['average_model_unit_pnl']}`",
        f"- median_model_unit_pnl: `{metric_set['median_model_unit_pnl']}`",
        f"- total_model_unit_pnl: `{metric_set['total_model_unit_pnl']}`",
        f"- max_drawdown_model_units: `{metric_set['max_drawdown_model_units']}`",
        "",
        "## Bootstrap Method",
        f"- fixed_seed: `{bootstrap_ci['seed']}`",
        f"- iterations: `{bootstrap_ci['iterations']}`",
        f"- mean_pnl_ci: `{bootstrap_ci['mean_pnl_ci']}`",
        f"- win_rate_ci: `{bootstrap_ci['win_rate_ci']}`",
        "- Bootstrap intervals are fixture/model diagnostics only.",
        "",
        "## Baseline Comparisons",
        f"- comparison_count: `{len(baseline_comparisons)}`",
        "- Baselines include zero-return, random-direction fixture, always-long-call, always-long-put, no-trade, and shuffled-signal diagnostics.",
        "- No superiority or real alpha claim is allowed.",
        "",
        "## Multiple-Testing Guard",
        f"- strategy_family_count: `{multiple_testing['strategy_family_count']}`",
        f"- tested_signal_family_count: `{multiple_testing['tested_signal_family_count']}`",
        "- P-values are blocked because the current run is not real statistical evidence.",
        "",
        "## Deflated Sharpe Diagnostic",
        f"- observed_sharpe_like_model_units: `{deflated_sharpe['observed_sharpe_like_model_units']}`",
        f"- deflated_sharpe_model_units: `{deflated_sharpe['deflated_sharpe_model_units']}`",
        "- Diagnostic-only placeholder; no significance claim is reported.",
        "",
        "## Truth Decision Gate",
        f"- truth_status: `{decision['truth_status']}`",
        f"- truth_decision: `{decision['truth_decision']}`",
        f"- blocked_reason_codes: `{decision['blocked_reason_codes']}`",
        "",
        "## Current Fixture/Model-Only Limitation",
        "- Real OHLCV and real options-chain data remain absent.",
        "- Current statistics are not real statistical evidence.",
        "",
        "## Claim-Blocking Policy",
        "- significance_claim_allowed: `false`",
        "- real_alpha_claim_allowed: `false`",
        "- profitability_claim_allowed: `false`",
        "- live_readiness_claim_allowed: `false`",
        "- promotion_allowed: `false`",
        "",
        "## Safety State",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "- broker_connection: `none`",
        "- credentials: `none`",
        "- scheduler: `none`",
        "- real_sizing: `none`",
        "- live_orders: `false`",
        "",
        "## Validation Summary",
        f"- quality_flags: `{summary['quality_flags']}`",
        f"- run_hash: `{summary['run_hash']}`",
        "",
        "## Limitations",
        "- Model-unit P&L is not money and not profitability.",
        "- Fixture/model statistics cannot promote strategies.",
        "- Real evidence thresholds currently fail with real_sample_size=0.",
        "",
        "## Next Target",
        "- `DOPEY_FITNESS_FUNCTION_REPLACEMENT_V1`",
    ]
    STATS_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ledger(summary: dict[str, Any]) -> None:
    paths = stats_artifact_paths()
    lines = [
        "# DOPEY Statistical Truth Layer Artifact Ledger",
        "",
        "## Source Files",
        "- `dopey_stats/statistical_truth_models.py`",
        "- `dopey_stats/statistical_metric_calculator.py`",
        "- `dopey_stats/bootstrap_truth_engine.py`",
        "- `dopey_stats/baseline_comparison.py`",
        "- `dopey_stats/multiple_testing_guard.py`",
        "- `dopey_stats/deflated_sharpe.py`",
        "- `dopey_stats/statistical_truth_gate.py`",
        "- `dopey_stats/run_statistical_truth_layer.py`",
        "- `tests/test_statistical_truth_layer.py`",
        "",
        "## Fixture Files",
        f"- `{STATS_METRIC_CASES_PATH}` records=`{_fixture_case_count(STATS_METRIC_CASES_PATH)}` sha256=`{_file_sha256(STATS_METRIC_CASES_PATH)}`",
        f"- `{STATS_BOOTSTRAP_CASES_PATH}` records=`{_fixture_case_count(STATS_BOOTSTRAP_CASES_PATH)}` sha256=`{_file_sha256(STATS_BOOTSTRAP_CASES_PATH)}`",
        f"- `{STATS_GATE_CASES_PATH}` records=`{_fixture_case_count(STATS_GATE_CASES_PATH)}` sha256=`{_file_sha256(STATS_GATE_CASES_PATH)}`",
        "",
        "## Artifact Files",
    ]
    for key in [
        "statistical_truth_input",
        "backtest_sample_profile",
        "backtest_metric_set",
        "bootstrap_confidence_intervals",
        "baseline_comparisons",
        "multiple_testing_adjustment",
        "deflated_sharpe_result",
        "statistical_truth_decision",
        "statistical_truth_quality_flags",
        "statistical_truth_summary",
        "statistical_truth_proof",
    ]:
        path = Path(paths[key])
        lines.append(f"- `{path}` records=`{_record_count(path)}` sha256=`{_file_sha256(path)}`")
    lines.extend([
        "",
        "## Record Counts",
        f"- sample_count: `{summary['sample_count']}`",
        f"- real_sample_size: `{summary['real_sample_size']}`",
        f"- fixture_model_sample_size: `{summary['fixture_model_sample_size']}`",
        f"- baseline_comparison_count: `{summary['baseline_comparison_count']}`",
        "",
        "## Hashes",
        f"- statistical_truth_summary.run_hash: `{summary['run_hash']}`",
        "",
        "## Safety State",
        "- paper_only: `true`",
        "- live_blocked: `true`",
        "- not_real_statistical_evidence: `true`",
        "- promotion_allowed: `false`",
        "- no broker, credentials, scheduler, real sizing, or orders created",
    ])
    STATS_LEDGER_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def main() -> int:
    result = run_statistical_truth_layer()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
