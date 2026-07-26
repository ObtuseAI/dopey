"""Retune hardening gate for conditional champion repairs."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import (
    apply_stress_case,
    load_public_trades,
    stress_case_definitions,
    stress_metrics,
    stress_survived,
    trades_for_champion,
)
from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.champion_repair_common import (
    REPAIR_ROOT,
    RETUNE_TRADES_PATH,
    conditional_champion_names,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, safe_float, write_jsonl_file


RESULTS_PATH = REPAIR_ROOT / "conditional_champion_retune_hardening_results_v1.jsonl"
REJECTIONS_PATH = REPAIR_ROOT / "conditional_champion_retune_rejections_v1.jsonl"
PROMOTIONS_PATH = REPAIR_ROOT / "conditional_champion_retune_promotions_v1.jsonl"
SUMMARY_PATH = REPAIR_ROOT / "conditional_champion_retune_hardening_gate_v1_summary.json"
PROOF_PATH = REPAIR_ROOT / "conditional_champion_retune_hardening_gate_v1_proof.jsonl"


def run_conditional_champion_retune_hardening_gate_v1() -> dict[str, object]:
    parents = conditional_champion_names()
    retune_trades = read_jsonl_file(RETUNE_TRADES_PATH)
    original_trades = load_public_trades()
    core_cases = [case for case in stress_case_definitions() if bool(case.get("core"))]
    results: list[dict[str, object]] = []
    rejections: list[dict[str, object]] = []
    promotions: list[dict[str, object]] = []

    hardened: list[str] = []
    conditional: list[str] = []
    demoted: list[str] = []

    for parent in parents:
        before = trades_for_champion({"cohort_level": "variant_id", "cohort_id": parent}, original_trades)
        after = [t for t in retune_trades if str(t.get("parent_champion_id", "")) == parent and str(t.get("trade_intent", "")) in {"long_call", "long_put"}]
        before_metrics = stress_metrics(before)
        after_metrics = stress_metrics(after)
        core_pass = 0
        for case in core_cases:
            stressed = apply_stress_case(after, case)
            metrics = stress_metrics(stressed)
            survived, _ = stress_survived(metrics, min_sample=10)
            if survived:
                core_pass += 1
        core_rate = core_pass / max(len(core_cases), 1)
        improved = safe_float(after_metrics.get("expectancy")) > safe_float(before_metrics.get("expectancy"))
        status, reasons = classify_retune(parent, core_rate, after_metrics, before_metrics, improved)
        if status == "retuned_hardened_public_paper_champion":
            hardened.append(parent)
            promotions.append(record_with_hash({"artifact_type": "conditional_champion_retune_promotion_v1", "champion_name": parent, "status": status, **live_safety_fields()}, "record_hash"))
        elif status == "retuned_conditional_public_paper_champion":
            conditional.append(parent)
        else:
            demoted.append(parent)
            rejections.append(record_with_hash({"artifact_type": "conditional_champion_retune_rejection_v1", "champion_name": parent, "status": status, "reasons": reasons, **live_safety_fields()}, "record_hash"))
        results.append(record_with_hash({
            "artifact_type": "conditional_champion_retune_hardening_result_v1",
            "champion_name": parent,
            "hardening_status": status,
            "core_stress_survival_rate": round(core_rate, 6),
            "before_expectancy": before_metrics.get("expectancy", 0.0),
            "after_expectancy": after_metrics.get("expectancy", 0.0),
            "after_profit_factor": after_metrics.get("profit_factor", 0.0),
            "after_sample_count": after_metrics.get("sample_count", 0),
            "improved_vs_original": improved,
            "rejection_reasons": reasons,
            "thresholds_lowered": False,
            **live_safety_fields(),
        }, "record_hash"))

    gate_status = (
        "retuned_hardened_champions_found" if hardened else
        "conditional_champions_improved_require_more_repair" if conditional else
        "conditional_champions_demoted_after_retune"
    )
    summary = {
        "artifact_type": "conditional_champion_retune_hardening_gate_v1_summary",
        "conditional_champion_retune_hardening_version": "dopey-public-champion-retune-hardening-gate-v1",
        "conditional_champion_retune_hardening_status": gate_status,
        "input_conditional_champion_count": len(parents),
        "retuned_hardened_count": len(hardened),
        "retuned_conditional_count": len(conditional),
        "retuned_demoted_count": len(demoted),
        "retuned_hardened_names": hardened,
        "retuned_conditional_names": conditional,
        "retuned_demoted_names": demoted,
        "thresholds_lowered": False,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(RESULTS_PATH, results)
    write_jsonl_file(REJECTIONS_PATH, rejections)
    write_jsonl_file(PROMOTIONS_PATH, promotions)
    write_stage_proof(PROOF_PATH, "conditional-champion-retune-hardening-gate-v1", gate_status, summary)
    return {**summary, "artifact_paths": artifact_paths()}


def classify_retune(parent: str, core_rate: float, after: dict[str, object], before: dict[str, object], improved: bool) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if int(after.get("sample_count", 0)) < 30:
        reasons.append("sample_count_inadequate")
    if safe_float(after.get("profit_factor", 0.0)) <= 1.10:
        reasons.append("profit_factor_below_hardening_threshold")
    if safe_float(after.get("expectancy", 0.0)) <= 0.0:
        reasons.append("expectancy_not_positive")
    if core_rate < 0.70:
        reasons.append("core_deep_stress_failure")
    if not improved:
        reasons.append("no_improvement_vs_original")
    if not reasons and core_rate >= 0.85:
        return "retuned_hardened_public_paper_champion", []
    if core_rate >= 0.55 and improved:
        return "retuned_conditional_public_paper_champion", reasons
    if core_rate < 0.45:
        return "retune_failed_demoted", reasons
    return "retuned_watchlist_repair_required", reasons


def artifact_paths() -> dict[str, str]:
    return {
        "conditional_champion_retune_hardening_gate_v1_summary": str(SUMMARY_PATH),
    }
