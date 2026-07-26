"""Holdout expansion for public paper champions."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import (
    HARDENING_ROOT,
    apply_holdout,
    champion_records,
    holdout_definitions,
    holdout_survived,
    live_safety_fields,
    load_public_trades,
    stress_metrics,
    trades_for_champion,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import record_with_hash, safe_float, write_jsonl_file


RESULTS_PATH = HARDENING_ROOT / "public_champion_holdout_expansion_results_v1.jsonl"
FAILURES_PATH = HARDENING_ROOT / "public_champion_holdout_failures_v1.jsonl"
SURVIVORS_PATH = HARDENING_ROOT / "public_champion_holdout_survivors_v1.jsonl"
SUMMARY_PATH = HARDENING_ROOT / "public_champion_holdout_expansion_v1_summary.json"
PROOF_PATH = HARDENING_ROOT / "public_champion_holdout_expansion_v1_proof.jsonl"


def run_public_champion_holdout_expansion_v1() -> dict[str, object]:
    champions = champion_records()
    trades = load_public_trades()
    holdouts = holdout_definitions()
    results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    survivors: list[dict[str, object]] = []
    champion_survival_counts: dict[str, int] = {}

    for champion in champions:
        champion_key = str(champion.get("cohort_id", ""))
        cohort_trades = trades_for_champion(champion, trades)
        baseline = stress_metrics(cohort_trades)
        survived_count = 0
        for holdout in holdouts:
            holdout_trades = apply_holdout(cohort_trades, holdout)
            metrics = stress_metrics(holdout_trades)
            survived, reason = holdout_survived(metrics, baseline)
            degradation = 0.0
            if safe_float(baseline.get("expectancy")) > 0.0:
                degradation = round(
                    (safe_float(baseline.get("expectancy")) - safe_float(metrics.get("expectancy")))
                    / safe_float(baseline.get("expectancy")),
                    6,
                )
            result = record_with_hash({
                "artifact_type": "public_champion_holdout_expansion_result_v1",
                "champion_name": champion_key,
                "holdout_id": holdout.get("holdout_id", ""),
                "core_holdout": bool(holdout.get("core")),
                "net_pnl": metrics.get("net_pnl", 0.0),
                "expectancy": metrics.get("expectancy", 0.0),
                "profit_factor": metrics.get("profit_factor", 0.0),
                "max_drawdown": metrics.get("max_drawdown", 0.0),
                "sample_count": metrics.get("sample_count", 0),
                "survival_flag": survived,
                "failure_reason": reason,
                "degradation_vs_baseline": degradation,
                **live_safety_fields(),
            }, "record_hash")
            results.append(result)
            if survived:
                survivors.append(result)
                survived_count += 1
            else:
                failures.append(result)
        champion_survival_counts[champion_key] = survived_count

    summary = {
        "artifact_type": "public_champion_holdout_expansion_v1_summary",
        "public_champion_holdout_expansion_version": "dopey-public-champion-holdout-expansion-v1",
        "holdout_expansion_status": "holdout_expansion_complete",
        "champions_tested": len(champions),
        "holdout_count": len(holdouts),
        "holdout_result_count": len(results),
        "holdout_survivor_count": len(survivors),
        "holdout_failure_count": len(failures),
        "champion_holdout_survival_counts": champion_survival_counts,
        "public_data_only": True,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(RESULTS_PATH, results)
    write_jsonl_file(FAILURES_PATH, failures)
    write_jsonl_file(SURVIVORS_PATH, survivors)
    write_stage_proof(PROOF_PATH, "public-champion-holdout-expansion-v1", str(summary["holdout_expansion_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_holdout_expansion_results_v1": str(RESULTS_PATH),
        "public_champion_holdout_failures_v1": str(FAILURES_PATH),
        "public_champion_holdout_survivors_v1": str(SURVIVORS_PATH),
        "public_champion_holdout_expansion_v1_summary": str(SUMMARY_PATH),
        "public_champion_holdout_expansion_v1_proof": str(PROOF_PATH),
    }
