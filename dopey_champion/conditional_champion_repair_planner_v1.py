"""Conditional champion repair planner V1."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import (
    HARDENING_ROOT,
    load_public_trades,
    stress_metrics,
    trades_for_champion,
)
from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.champion_repair_common import (
    REPAIR_ROOT,
    conditional_champion_names,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, write_jsonl_file


PLANS_PATH = REPAIR_ROOT / "conditional_champion_repair_plans_v1.jsonl"
FAILURES_PATH = REPAIR_ROOT / "conditional_champion_failure_profiles_v1.jsonl"
VARIANTS_PATH = REPAIR_ROOT / "conditional_champion_related_variants_v1.jsonl"
SUMMARY_PATH = REPAIR_ROOT / "conditional_champion_repair_planner_v1_summary.json"
PROOF_PATH = REPAIR_ROOT / "conditional_champion_repair_planner_v1_proof.jsonl"

STRESS_RESULTS_PATH = HARDENING_ROOT / "public_champion_deep_stress_results_v1.jsonl"
HOLDOUT_RESULTS_PATH = HARDENING_ROOT / "public_champion_holdout_expansion_results_v1.jsonl"
GATE_RESULTS_PATH = HARDENING_ROOT / "public_champion_hardening_gate_results_v1.jsonl"
INVENTORY_PATH = HARDENING_ROOT / "public_champion_inventory_v1.jsonl"


def run_conditional_champion_repair_planner_v1() -> dict[str, object]:
    champions = conditional_champion_names()
    trades = load_public_trades()
    stress_results = read_jsonl_file(STRESS_RESULTS_PATH)
    holdout_results = read_jsonl_file(HOLDOUT_RESULTS_PATH)
    gate_results = {str(r.get("champion_name", "")): r for r in read_jsonl_file(GATE_RESULTS_PATH)}
    inventory = {str(r.get("champion_name", "")): r for r in read_jsonl_file(INVENTORY_PATH)}

    plans: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    variants: list[dict[str, object]] = []
    repair_types: Counter[str] = Counter()

    for champion_name in champions:
        champion_row = inventory.get(champion_name, {"cohort_level": "variant_id", "cohort_id": champion_name})
        cohort_trades = trades_for_champion({"cohort_level": champion_row.get("cohort_level", "variant_id"), "cohort_id": champion_name}, trades)
        metrics = stress_metrics(cohort_trades)
        champion_stress = [r for r in stress_results if r.get("champion_name") == champion_name and not r.get("survival_flag")]
        champion_holdout = [r for r in holdout_results if r.get("champion_name") == champion_name and not r.get("survival_flag")]
        gate = gate_results.get(champion_name, {})
        failure_reasons = list(gate.get("rejection_reasons", []))
        top_stress_failures = Counter(str(r.get("failure_reason", "")) for r in champion_stress).most_common(5)

        repair_actions = derive_repair_actions(failure_reasons, top_stress_failures, metrics)
        for action in repair_actions:
            repair_types[action] += 1
            plans.append(record_with_hash({
                "artifact_type": "conditional_champion_repair_plan_v1",
                "champion_name": champion_name,
                "repair_plan_id": f"repair-{champion_name}-{action}",
                "repair_type": action,
                "parent_champion_id": champion_name,
                **live_safety_fields(),
            }, "record_hash"))

        failures.append(record_with_hash({
            "artifact_type": "conditional_champion_failure_profile_v1",
            "champion_name": champion_name,
            "stress_failure_count": len(champion_stress),
            "holdout_failure_count": len(champion_holdout),
            "top_stress_failures": dict(top_stress_failures),
            "sample_count": metrics.get("sample_count", 0),
            "profit_factor": metrics.get("profit_factor", 0.0),
            "top_symbol_share": metrics.get("top_symbol_trade_share", 0.0),
            "top_sector_share": metrics.get("top_sector_trade_share", 0.0),
            "rejection_reasons": failure_reasons,
            **live_safety_fields(),
        }, "record_hash"))

        related = {str(t.get("variant_id", "")) for t in cohort_trades}
        for variant_id in sorted(related)[:25]:
            variants.append(record_with_hash({
                "artifact_type": "conditional_champion_related_variant_v1",
                "champion_name": champion_name,
                "variant_id": variant_id,
                "trade_count": sum(1 for t in cohort_trades if str(t.get("variant_id", "")) == variant_id),
                **live_safety_fields(),
            }, "record_hash"))

    summary = {
        "artifact_type": "conditional_champion_repair_planner_v1_summary",
        "conditional_champion_repair_planner_version": "dopey-public-champion-repair-planner-v1",
        "conditional_champion_repair_planner_status": "conditional_repair_plans_written",
        "conditional_champion_count": len(champions),
        "repair_plan_count": len(plans),
        "top_repair_types": dict(repair_types.most_common(10)),
        "sample_expansion_targets": [name for name in champions],
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(PLANS_PATH, plans)
    write_jsonl_file(FAILURES_PATH, failures)
    write_jsonl_file(VARIANTS_PATH, variants)
    write_stage_proof(PROOF_PATH, "conditional-champion-repair-planner-v1", str(summary["conditional_champion_repair_planner_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def derive_repair_actions(failure_reasons: list[str], stress_failures, metrics: dict[str, object]) -> list[str]:
    actions: list[str] = []
    mapping = {
        "core_deep_stress_failure": ["slippage_hardening", "theta_hardening", "iv_shock_hardening"],
        "holdout_partition_failure": ["recent_market_reinforcement", "sample_expansion"],
        "outlier_dependence": ["outlier_dependence_reduction"],
        "single_symbol_sector_regime_dependence": ["symbol_concentration_reduction", "sector_concentration_reduction", "regime_diversification"],
        "profit_factor_below_hardening_threshold": ["stop_target_adjustment", "exit_policy_adjustment"],
        "sample_count_inadequate": ["sample_expansion"],
    }
    for reason in failure_reasons:
        actions.extend(mapping.get(reason, ["sample_expansion"]))
    for reason, _ in stress_failures:
        if reason == "profit_factor_below_core_threshold":
            actions.append("exit_policy_adjustment")
        if reason == "sample_count_inadequate":
            actions.append("sample_expansion")
        if reason == "net_pnl_not_positive":
            actions.extend(["slippage_hardening", "theta_hardening"])
    if int(metrics.get("sample_count", 0)) < 60:
        actions.append("sample_expansion")
    actions.extend(["dte_migration", "moneyness_migration"])
    return sorted(set(actions))


def artifact_paths() -> dict[str, str]:
    return {
        "conditional_champion_repair_plans_v1": str(PLANS_PATH),
        "conditional_champion_failure_profiles_v1": str(FAILURES_PATH),
        "conditional_champion_repair_planner_v1_summary": str(SUMMARY_PATH),
    }
