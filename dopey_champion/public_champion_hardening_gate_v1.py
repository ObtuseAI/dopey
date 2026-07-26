"""Public champion hardening gate V1."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import (
    GATE_RESULTS_PATH,
    HARDENING_ROOT,
    HOLDOUT_SURVIVAL_RATE,
    champion_records,
    live_safety_fields,
    robinhood_policy_fields,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, safe_float, write_jsonl_file


RESULTS_PATH = HARDENING_ROOT / "public_champion_hardening_gate_results_v1.jsonl"
REJECTIONS_PATH = HARDENING_ROOT / "public_champion_hardening_rejections_v1.jsonl"
REPAIR_QUEUE_PATH = HARDENING_ROOT / "public_champion_hardening_repair_queue_v1.jsonl"
SUMMARY_PATH = HARDENING_ROOT / "public_champion_hardening_gate_v1_summary.json"
PROOF_PATH = HARDENING_ROOT / "public_champion_hardening_gate_v1_proof.jsonl"

STRESS_SUMMARY_PATH = HARDENING_ROOT / "public_champion_deep_stress_matrix_v1_summary.json"
HOLDOUT_SUMMARY_PATH = HARDENING_ROOT / "public_champion_holdout_expansion_v1_summary.json"
DECAY_SUMMARY_PATH = HARDENING_ROOT / "public_champion_decay_monitor_v1_summary.json"
STRESS_RESULTS_PATH = HARDENING_ROOT / "public_champion_deep_stress_results_v1.jsonl"
HOLDOUT_RESULTS_PATH = HARDENING_ROOT / "public_champion_holdout_expansion_results_v1.jsonl"
DECAY_ALERTS_PATH = HARDENING_ROOT / "public_champion_decay_alerts_v1.jsonl"


def _source_artifact_hashes(paths: tuple[Path, ...]) -> dict[str, str]:
    return {
        path.relative_to(HARDENING_ROOT.parent).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        if path.exists()
        else ""
        for path in paths
    }


def run_public_champion_hardening_gate_v1() -> dict[str, object]:
    champions = champion_records()
    stress_results = read_jsonl_file(STRESS_RESULTS_PATH)
    holdout_results = read_jsonl_file(HOLDOUT_RESULTS_PATH)
    decay_alerts = read_jsonl_file(DECAY_ALERTS_PATH)
    gate_results: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    repair_queue: list[dict[str, object]] = []

    hardened: list[str] = []
    conditional: list[str] = []
    demoted: list[str] = []

    for champion in champions:
        champion_key = str(champion.get("cohort_id", ""))
        core_stress = [
            row for row in stress_results
            if row.get("champion_name") == champion_key and bool(row.get("core_stress"))
        ]
        core_survived = sum(1 for row in core_stress if bool(row.get("survival_flag")))
        core_total = len(core_stress) or 1
        holdout_rows = [row for row in holdout_results if row.get("champion_name") == champion_key]
        holdout_survived = sum(1 for row in holdout_rows if bool(row.get("survival_flag")))
        holdout_total = len(holdout_rows) or 1
        alert_count = sum(1 for alert in decay_alerts if alert.get("champion_name") == champion_key)
        concentration_flags = [
            row for row in core_stress
            if "concentration" in str(row.get("stress_id", "")) and not bool(row.get("survival_flag"))
        ]
        outlier_flags = [
            row for row in core_stress
            if "outlier" in str(row.get("stress_id", "")) and not bool(row.get("survival_flag"))
        ]
        status, reasons = classify_champion(
            core_survived=core_survived,
            core_total=core_total,
            holdout_survived=holdout_survived,
            holdout_total=holdout_total,
            alert_count=alert_count,
            concentration_failures=len(concentration_flags),
            outlier_failures=len(outlier_flags),
            champion=champion,
        )
        if status == "hardened_public_paper_champion":
            hardened.append(champion_key)
        elif status == "conditional_public_paper_champion":
            conditional.append(champion_key)
        else:
            demoted.append(champion_key)
        gate_results.append(record_with_hash({
            "artifact_type": "public_champion_hardening_gate_result_v1",
            "champion_name": champion_key,
            "hardening_status": status,
            "core_stress_survival_rate": round(core_survived / core_total, 6),
            "holdout_survival_rate": round(holdout_survived / holdout_total, 6),
            "decay_alert_count": alert_count,
            "rejection_reasons": reasons,
            "live_gate_locked": True,
            "public_data_only": True,
            "fixture_champion_count": 0,
            **live_safety_fields(),
        }, "record_hash"))
        if reasons:
            rejections.append(record_with_hash({
                "artifact_type": "public_champion_hardening_rejection_v1",
                "champion_name": champion_key,
                "hardening_status": status,
                "rejection_reasons": reasons,
                **live_safety_fields(),
            }, "record_hash"))
        if status != "hardened_public_paper_champion":
            repair_queue.extend(build_repair_items(champion_key, status, reasons))

    summary = {
        "artifact_type": "public_champion_hardening_gate_v1_summary",
        "public_champion_hardening_gate_version": "dopey-public-champion-hardening-gate-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_artifact_hashes": _source_artifact_hashes(
            (
                GATE_RESULTS_PATH,
                STRESS_RESULTS_PATH,
                HOLDOUT_RESULTS_PATH,
                DECAY_ALERTS_PATH,
            )
        ),
        "champion_hardening_gate_status": gate_status(hardened, conditional, demoted),
        "input_public_champion_count": len(champions),
        "hardened_champion_count": len(hardened),
        "conditional_champion_count": len(conditional),
        "demoted_champion_count": len(demoted),
        "repair_queue_count": len(repair_queue),
        "hardened_champion_names": hardened,
        "conditional_champion_names": conditional,
        "demoted_champion_names": demoted,
        "public_data_only": True,
        "fixture_champion_count": 0,
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(RESULTS_PATH, gate_results)
    write_jsonl_file(REJECTIONS_PATH, rejections)
    write_jsonl_file(REPAIR_QUEUE_PATH, repair_queue)
    write_stage_proof(PROOF_PATH, "public-champion-hardening-gate-v1", str(summary["champion_hardening_gate_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def classify_champion(
    *,
    core_survived: int,
    core_total: int,
    holdout_survived: int,
    holdout_total: int,
    alert_count: int,
    concentration_failures: int,
    outlier_failures: int,
    champion: dict[str, object],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    core_rate = core_survived / max(core_total, 1)
    holdout_rate = holdout_survived / max(holdout_total, 1)
    if core_rate < 0.70:
        reasons.append("core_deep_stress_failure")
    if holdout_rate < HOLDOUT_SURVIVAL_RATE:
        reasons.append("holdout_partition_failure")
    if alert_count >= 2:
        reasons.append("decay_monitor_severe_alert")
    if concentration_failures >= 2:
        reasons.append("single_symbol_sector_regime_dependence")
    if outlier_failures >= 2:
        reasons.append("outlier_dependence")
    if safe_float(champion.get("profit_factor", 0.0)) <= 1.10:
        reasons.append("profit_factor_below_hardening_threshold")
    if int(champion.get("sample_count", 0)) < 30:
        reasons.append("sample_count_inadequate")
    if not reasons:
        return "hardened_public_paper_champion", []
    if core_rate < 0.50 or holdout_rate < 0.45:
        if "core_deep_stress_failure" in reasons:
            return "demoted_failed_deep_stress", reasons
        return "demoted_sample_or_holdout_failure", reasons
    if alert_count >= 3:
        return "watchlist_repair_required", reasons
    return "conditional_public_paper_champion", reasons


def gate_status(hardened: list[str], conditional: list[str], demoted: list[str]) -> str:
    if hardened:
        return "hardened_public_paper_champions_found_live_gate_locked"
    if conditional:
        return "conditional_public_champions_require_repair"
    return "all_public_champions_demoted_after_deep_stress"


def build_repair_items(champion_name: str, status: str, reasons: list[str]) -> list[dict[str, object]]:
    mapping = {
        "core_deep_stress_failure": ["slippage_robustness_repair", "theta_robustness_repair", "iv_shock_repair"],
        "holdout_partition_failure": ["recent_market_repair", "split_pass_repair"],
        "decay_monitor_severe_alert": ["exit_policy_repair", "recent_market_repair"],
        "single_symbol_sector_regime_dependence": ["symbol_concentration_repair", "sector_concentration_repair", "regime_concentration_repair"],
        "outlier_dependence": ["outlier_dependence_repair", "sample_expansion"],
        "profit_factor_below_hardening_threshold": ["stop_target_repair", "exit_policy_repair"],
        "sample_count_inadequate": ["sample_expansion", "split_pass_repair"],
    }
    items: list[dict[str, object]] = []
    for reason in reasons:
        for repair_type in mapping.get(reason, ["sample_expansion"]):
            items.append(record_with_hash({
                "artifact_type": "public_champion_hardening_repair_queue_v1",
                "champion_name": champion_name,
                "hardening_status": status,
                "repair_type": repair_type,
                "trigger_reason": reason,
                **live_safety_fields(),
            }, "record_hash"))
    return items


def artifact_paths() -> dict[str, str]:
    return {
        "public_champion_hardening_gate_results_v1": str(RESULTS_PATH),
        "public_champion_hardening_rejections_v1": str(REJECTIONS_PATH),
        "public_champion_hardening_repair_queue_v1": str(REPAIR_QUEUE_PATH),
        "public_champion_hardening_gate_v1_summary": str(SUMMARY_PATH),
        "public_champion_hardening_gate_v1_proof": str(PROOF_PATH),
    }
