"""Deep stress matrix for public paper champions."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import (
    HARDENING_ROOT,
    apply_stress_case,
    champion_records,
    live_safety_fields,
    load_public_trades,
    stress_case_definitions,
    stress_metrics,
    stress_survived,
    trades_for_champion,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file


RESULTS_PATH = HARDENING_ROOT / "public_champion_deep_stress_results_v1.jsonl"
FAILURES_PATH = HARDENING_ROOT / "public_champion_deep_stress_failures_v1.jsonl"
SURVIVORS_PATH = HARDENING_ROOT / "public_champion_deep_stress_survivors_v1.jsonl"
SUMMARY_PATH = HARDENING_ROOT / "public_champion_deep_stress_matrix_v1_summary.json"
PROOF_PATH = HARDENING_ROOT / "public_champion_deep_stress_matrix_v1_proof.jsonl"


def run_public_champion_deep_stress_matrix_v1() -> dict[str, object]:
    champions = champion_records()
    trades = load_public_trades()
    cases = stress_case_definitions()
    results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    survivors: list[dict[str, object]] = []
    failure_reasons: Counter[str] = Counter()
    champion_core_survival: dict[str, bool] = {}

    for champion in champions:
        champion_key = str(champion.get("cohort_id", ""))
        cohort_trades = trades_for_champion(champion, trades)
        core_failures = 0
        core_total = sum(1 for case in cases if bool(case.get("core")))
        for case in cases:
            stressed_trades = apply_stress_case(cohort_trades, case)
            metrics = stress_metrics(stressed_trades)
            survived, reason = stress_survived(metrics)
            result = record_with_hash({
                "artifact_type": "public_champion_deep_stress_result_v1",
                "champion_name": champion_key,
                "cohort_level": champion.get("cohort_level", ""),
                "stress_id": case.get("stress_id", ""),
                "stress_family": case.get("stress_family", ""),
                "core_stress": bool(case.get("core")),
                "net_pnl": metrics.get("net_pnl", 0.0),
                "expectancy": metrics.get("expectancy", 0.0),
                "profit_factor": metrics.get("profit_factor", 0.0),
                "max_drawdown": metrics.get("max_drawdown", 0.0),
                "win_rate": metrics.get("win_rate", 0.0),
                "sample_count": metrics.get("sample_count", 0),
                "survival_flag": survived,
                "failure_reason": reason,
                **live_safety_fields(),
            }, "record_hash")
            results.append(result)
            if not survived:
                failures.append(result)
                if reason:
                    failure_reasons[reason] += 1
                if bool(case.get("core")):
                    core_failures += 1
            elif bool(case.get("core")):
                survivors.append(result)
        champion_core_survival[champion_key] = core_failures == 0

    champions_survived_core = sum(1 for survived in champion_core_survival.values() if survived)
    champions_survived_all = sum(
        1 for champion in champions
        if all(
            row.get("survival_flag")
            for row in results
            if row.get("champion_name") == champion.get("cohort_id")
        )
    )
    summary = {
        "artifact_type": "public_champion_deep_stress_matrix_v1_summary",
        "public_champion_deep_stress_version": "dopey-public-champion-deep-stress-matrix-v1",
        "deep_stress_status": "deep_stress_matrix_complete",
        "champions_tested": len(champions),
        "stress_case_count": len(cases),
        "stress_result_count": len(results),
        "champions_survived_all": champions_survived_all,
        "champions_survived_core": champions_survived_core,
        "champions_failed": len(champions) - champions_survived_core,
        "top_failure_reasons": dict(failure_reasons.most_common(10)),
        "champion_core_survival": champion_core_survival,
        "public_data_only": True,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(RESULTS_PATH, results)
    write_jsonl_file(FAILURES_PATH, failures)
    write_jsonl_file(SURVIVORS_PATH, survivors)
    write_stage_proof(PROOF_PATH, "public-champion-deep-stress-matrix-v1", str(summary["deep_stress_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_deep_stress_results_v1": str(RESULTS_PATH),
        "public_champion_deep_stress_failures_v1": str(FAILURES_PATH),
        "public_champion_deep_stress_survivors_v1": str(SURVIVORS_PATH),
        "public_champion_deep_stress_matrix_v1_summary": str(SUMMARY_PATH),
        "public_champion_deep_stress_matrix_v1_proof": str(PROOF_PATH),
    }
