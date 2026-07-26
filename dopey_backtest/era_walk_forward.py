"""Era walk-forward stability analysis for the real-history honest lane.

Splits the real trade records into market eras and demands sign-consistent,
PF-consistent behavior across all of them before a cohort can be called
regime-robust. A cohort that only worked in one era is a regime bet, not an
edge. Deterministic, paper-only, not edge evidence by itself.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash
from dopey_core.repo_paths import REPORTS_DIR

from .trade_records_recovery import (
    iter_verified_trade_records,
    resolve_default_backtest_trade_ledger,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKTEST_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "backtest"
BACKTEST_TRADE_RECORDS_PATH = BACKTEST_ARTIFACT_DIR / "backtest_trade_records.jsonl"
ERA_COHORT_STATS_PATH = BACKTEST_ARTIFACT_DIR / "era_walk_forward_cohort_stats.jsonl"
ERA_SUMMARY_PATH = BACKTEST_ARTIFACT_DIR / "era_walk_forward_summary.json"
ERA_REPORT_PATH = REPORTS_DIR / "DOPEY_ERA_WALK_FORWARD_REPORT.md"

ERAS: tuple[tuple[str, str, str], ...] = (
    ("2015_2019_low_vol_bull", "2015-01-01", "2019-12-31"),
    ("2020_2022_covid_and_bear", "2020-01-01", "2022-12-31"),
    ("2023_2026_ai_bull", "2023-01-01", "2026-12-31"),
)
MIN_ERA_SAMPLE = 30
ERA_POLICY_VERSION = "dopey-era-robustness-v2"


def run_era_walk_forward() -> dict[str, Any]:
    if not BACKTEST_TRADE_RECORDS_PATH.exists():
        summary = {"artifact_type": "era_walk_forward_summary", "era_status": "blocked_missing_backtest_records"}
        _write_json(ERA_SUMMARY_PATH, summary)
        return summary
    ledger_resolution = resolve_default_backtest_trade_ledger()
    trades = list(iter_verified_trade_records(ledger_resolution))
    trades = [record for record in trades if record.get("real_history_used") is True]
    if not trades:
        summary = {"artifact_type": "era_walk_forward_summary", "era_status": "blocked_no_real_trades"}
        _write_json(ERA_SUMMARY_PATH, summary)
        return summary
    cohorts: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in trades:
        cohorts[(str(record["signal_family"]), str(record["candidate_strategy"]))].append(record)
    stats: list[dict[str, Any]] = []
    robust_cohorts: list[str] = []
    cohort_diagnostics: list[dict[str, Any]] = []
    for (family, strategy), records in sorted(cohorts.items()):
        era_rows = []
        for era_name, era_start, era_end in ERAS:
            era_pnls = [
                float(record["path_pnl"])
                for record in records
                if era_start <= str(record.get("entry_date", "")) <= era_end
            ]
            era_rows.append(_era_stats(f"{family}|{strategy}", family, strategy, era_name, era_pnls))
        stats.extend(era_rows)
        diagnostic = _cohort_regime_diagnostic(f"{family}|{strategy}", era_rows)
        cohort_diagnostics.append(diagnostic)
        if diagnostic["regime_robust"]:
            robust_cohorts.append(f"{family}|{strategy}")
    near_robust_cohorts = [
        str(record["cohort_id"])
        for record in cohort_diagnostics
        if record["diagnostic_status"] == "near_robust_two_of_three_eras"
    ]
    summary = {
        "artifact_type": "era_walk_forward_summary",
        "era_status": "era_walk_forward_complete",
        "backtest_trade_resolution_status": ledger_resolution["status"],
        "backtest_trade_resolved_sha256": ledger_resolution["resolved_sha256"],
        "backtest_trade_verified_record_count": ledger_resolution[
            "verified_record_hash_count"
        ],
        "eras": [{"era": name, "start": start, "end": end} for name, start, end in ERAS],
        "min_era_sample": MIN_ERA_SAMPLE,
        "cohort_count": len(cohorts),
        "era_stat_row_count": len(stats),
        "regime_robust_cohorts": robust_cohorts,
        "regime_robust_count": len(robust_cohorts),
        "near_robust_cohorts": near_robust_cohorts,
        "near_robust_count": len(near_robust_cohorts),
        "cohort_diagnostics": cohort_diagnostics,
        "era_policy_version": ERA_POLICY_VERSION,
        "data_source_tier": "local_real_history",
        "real_history_used": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    _write_jsonl(ERA_COHORT_STATS_PATH, stats)
    _write_json(ERA_SUMMARY_PATH, summary)
    _write_report(summary, stats)
    return summary


def _cohort_regime_diagnostic(
    cohort_id: str,
    era_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    failing_eras: list[dict[str, Any]] = []
    passing_era_count = 0
    for row in era_rows:
        reasons: list[str] = []
        if int(row["sample_count"]) < MIN_ERA_SAMPLE:
            reasons.append("sample_below_minimum")
        if float(row["net_pnl"]) <= 0.0:
            reasons.append("net_pnl_not_positive")
        if float(row["profit_factor"]) <= 1.0:
            reasons.append("profit_factor_not_above_one")
        if reasons:
            failing_eras.append({
                "era": str(row["era"]),
                "reason_codes": reasons,
                "sample_count": int(row["sample_count"]),
                "average_pnl": float(row["average_pnl"]),
                "profit_factor": float(row["profit_factor"]),
            })
        else:
            passing_era_count += 1
    regime_robust = passing_era_count == len(ERAS)
    if regime_robust:
        diagnostic_status = "regime_robust"
    elif passing_era_count == len(ERAS) - 1:
        diagnostic_status = "near_robust_two_of_three_eras"
    else:
        diagnostic_status = "not_regime_robust"
    return {
        "cohort_id": cohort_id,
        "diagnostic_status": diagnostic_status,
        "passing_era_count": passing_era_count,
        "required_passing_era_count": len(ERAS),
        "regime_robust": regime_robust,
        "failing_eras": failing_eras,
        "worst_era_average_pnl": min(float(row["average_pnl"]) for row in era_rows),
        "paper_only": True,
        "live_blocked": True,
    }


def _era_stats(
    cohort_id: str,
    family: str,
    strategy: str,
    era_name: str,
    pnls: list[float],
) -> dict[str, Any]:
    gross_profit = sum(value for value in pnls if value > 0.0)
    gross_loss = -sum(value for value in pnls if value < 0.0)
    wins = sum(1 for value in pnls if value > 0.0)
    return {
        "artifact_type": "era_walk_forward_cohort_stats",
        "cohort_id": cohort_id,
        "signal_family": family,
        "candidate_strategy": strategy,
        "era": era_name,
        "sample_count": len(pnls),
        "net_pnl": round(sum(pnls), 6),
        "win_rate": round(wins / len(pnls), 6) if pnls else 0.0,
        # an all-winning era is PASSING, not PF=0: use a large JSON-safe sentinel
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0.0 else (999.0 if gross_profit > 0.0 else 0.0),
        "pf_undefined_no_losses": gross_loss == 0.0 and gross_profit > 0.0,
        "average_pnl": round(sum(pnls) / len(pnls), 6) if pnls else 0.0,
        "meets_min_sample": len(pnls) >= MIN_ERA_SAMPLE,
        "paper_only": True,
        "live_blocked": True,
    }


def _write_report(summary: dict[str, Any], stats: list[dict[str, Any]]) -> None:
    lines = [
        "# DOPEY Era Walk-Forward Report",
        "",
        "## Question",
        "Which cohorts hold up across ALL market eras (net > 0 and PF > 1 in every era with",
        f"at least {MIN_ERA_SAMPLE} trades) - and which are single-regime bets?",
        "",
        f"- regime-robust cohorts: `{summary['regime_robust_count']}` -> `{summary['regime_robust_cohorts']}`",
        f"- near-robust (two of three eras): `{summary['near_robust_count']}` -> `{summary['near_robust_cohorts']}`",
        "",
        "## Per-era cohort stats (net model units, post-cost)",
    ]
    by_cohort: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in stats:
        by_cohort[row["cohort_id"]].append(row)
    for cohort_id, rows in sorted(by_cohort.items()):
        parts = ", ".join(
            f"{row['era']}: n={row['sample_count']} net={row['net_pnl']} PF={row['profit_factor']}" for row in rows
        )
        lines.append(f"- `{cohort_id}`: {parts}")
    lines.extend(
        [
            "",
            "## Honest Limits",
            "- Era robustness is necessary, not sufficient; baseline arbitration and real chains still gate claims.",
            "- paper_only: `true`; live_blocked: `true`.",
        ]
    )
    ERA_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
