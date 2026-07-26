"""Breakthrough blocker repair policy for V6.

Creates explicit, auditable repair rules for each V5->V6 breakthrough blocker.
Every rule is required to:
- use only pre-entry features or prior historical statistics
- avoid future path leakage
- avoid realized future P&L labels at candidate time
- avoid holdout-outcome leakage
- avoid pruning that invalidates gate coverage unless labeled experimental
- never lower MIN_BREAKTHROUGH_PF
"""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_json_file, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v6_common import (
    BLOCKER_REPAIR_POLICY_V6_PATH,
    BLOCKER_REPAIR_POLICY_V6_PROOF_PATH,
    BLOCKER_REPAIR_POLICY_V6_SUMMARY_PATH,
    BLOCKER_REPAIR_RULES_V6_PATH,
    FUTURE_LEAKAGE_GUARD_V6_PATH,
    MIN_BREAKTHROUGH_PF,
    RESEARCH_V6_VERSION,
    research_v6_proof_record,
    utc_now_iso,
)
from dopey_signal_research.future_leakage_guard_v6 import run_v6_leakage_guard_audit


__all__ = ["run_breakthrough_blocker_repair_policy_v6"]


_REPAIR_RULES: list[dict[str, object]] = [
    {
        "rule_id": "repair-drawdown-001",
        "rule_type": "drawdown_repair",
        "blocker_axis": "drawdown_exceeds_max",
        "description": (
            "Tighten pre-entry stop levels and reduce per-trade risk. "
            "Use only historical volatility, ATR, and prior swing statistics computed before entry. "
            "No future path data, no realized P&L labels, no holdout outcomes."
        ),
        "allowed_features": ["historical_volatility", "atr", "prior_swing_low", "position_size"],
        "forbidden_features": ["future_ohlcv", "realized_pnl", "holdout_outcome", "post_exit_pnl"],
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "repair-holdout-002",
        "rule_type": "holdout_survival_repair",
        "blocker_axis": "holdout_survival_failed",
        "description": (
            "Strengthen pre-entry filters and require consistency across prior holdout windows. "
            "Features are computed only from data available before the candidate bar. "
            "Holdout labels are used only for evaluation, never as candidate-generation features."
        ),
        "allowed_features": ["pre_entry_feature_zscore", "historical_win_rate", "regime_persistence"],
        "forbidden_features": ["holdout_outcome", "future_path", "realized_pnl"],
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "repair-split-003",
        "rule_type": "split_pass_repair",
        "blocker_axis": "split_pass_rate_below_threshold",
        "description": (
            "Stabilize cohort across time-based splits by requiring minimum per-split sample counts "
            "and symmetric in-sample / out-of-sample criteria. No split-outcome leakage into candidates."
        ),
        "allowed_features": ["calendar_features", "prior_split_sample_count", "regime_label_prior_to_split"],
        "forbidden_features": ["split_outcome_label", "future_ohlcv", "realized_pnl"],
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "repair-concentration-004",
        "rule_type": "concentration_repair",
        "blocker_axis": "concentration_exceeds_max",
        "description": (
            "Reduce top-symbol and top-sector concentration by broadening candidate eligibility. "
            "Coverage pruning is labeled experimental if it risks reducing symbol/sector coverage below gate minima."
        ),
        "allowed_features": ["historical_symbol_universe", "sector_breadth", "equal_weight_allocation"],
        "forbidden_features": ["future_performance_rank", "realized_pnl", "holdout_outcome"],
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "repair-expectancy-005",
        "rule_type": "expectancy_repair",
        "blocker_axis": "expectancy_below_threshold",
        "description": (
            "Filter low-expectancy contexts using pre-entry edge estimates from prior historical bins. "
            "No use of realized trade outcomes at candidate time."
        ),
        "allowed_features": ["historical_expectancy_by_context", "pre_entry_edge", "risk_reward_prior"],
        "forbidden_features": ["realized_pnl", "actual_outcome", "future_path"],
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "repair-stress-006",
        "rule_type": "stress_survival_repair",
        "blocker_axis": "stress_survival_failed",
        "description": (
            "Add stress-period filters derived from historically observed regimes and macro proxies. "
            "Stress labels are retained for evaluation only."
        ),
        "allowed_features": ["historical_stress_regime", "vix_proxy", "macro_proxy_prior"],
        "forbidden_features": ["stress_outcome_label", "future_ohlcv", "realized_pnl"],
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "repair-outlier-007",
        "rule_type": "outlier_dependence_repair",
        "blocker_axis": "outlier_dependence_high",
        "description": (
            "Cap dependence on extreme trades by winsorizing P&L attribution windows and requiring "
            "robustness across bootstrapped prior samples."
        ),
        "allowed_features": ["historical_pnl_percentiles", "bootstrap_robustness", "prior_sample_size"],
        "forbidden_features": ["future_outlier_flag", "realized_pnl", "holdout_outcome"],
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "repair-symbol-coverage-008",
        "rule_type": "symbol_broadening",
        "blocker_axis": "symbol_coverage_below_min",
        "description": (
            "Expand symbol coverage using historically available liquid underliers. "
            "Any pruning that would drop coverage below gate minima is experimental and gated separately."
        ),
        "allowed_features": ["historical_liquid_universe", "sector_map", "avg_volume_prior"],
        "forbidden_features": ["future_return_rank", "realized_pnl"],
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "repair-sector-coverage-009",
        "rule_type": "sector_broadening",
        "blocker_axis": "sector_coverage_below_min",
        "description": (
            "Expand sector coverage using prior sector classification. "
            "Coverage-reducing pruning is experimental only."
        ),
        "allowed_features": ["historical_sector_breadth", "sector_etf_membership"],
        "forbidden_features": ["future_sector_performance", "realized_pnl"],
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": False,
        "no_threshold_lowering": True,
        "experimental": False,
    },
    {
        "rule_id": "repair-coverage-prune-exp-010",
        "rule_type": "coverage_pruning_experimental",
        "blocker_axis": "coverage_pruning_experimental",
        "description": (
            "Experimental: prune symbols or sectors only when accompanied by a coverage audit that proves "
            "gate minima remain satisfied. Allowed only under the experimental label."
        ),
        "allowed_features": ["coverage_audit_prior"],
        "forbidden_features": ["future_path", "realized_pnl"],
        "uses_future_information": False,
        "uses_realized_outcome_label": False,
        "uses_holdout_outcome": False,
        "invalidates_gate_coverage": True,
        "no_threshold_lowering": True,
        "experimental": True,
    },
]


def _rule_record(rule: dict[str, object]) -> dict[str, object]:
    rec = {
        "artifact_type": "breakthrough_blocker_repair_rule_v6",
        **dict(rule),
        "v6_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    return record_with_hash(rec, "rule_hash")


def run_breakthrough_blocker_repair_policy_v6() -> dict[str, object]:
    rules = [_rule_rule for _rule_rule in (_REPAIR_RULES)]  # copy
    rule_records = [_rule_rule for _rule_rule in map(_rule_record, rules)]

    guard_summary = run_v6_leakage_guard_audit(rules)
    guard_records = []
    from dopey_signal_research.future_leakage_guard_v6 import audit_v6_no_leakage

    guard_records = audit_v6_no_leakage(rules)
    write_jsonl_file(FUTURE_LEAKAGE_GUARD_V6_PATH, guard_records)

    policy = {
        "artifact_type": "breakthrough_blocker_repair_policy_v6",
        "public_signal_research_v6_version": RESEARCH_V6_VERSION,
        "breakthrough_blocker_repair_policy_status": "repair_policy_defined_v6",
        "repair_rule_count": len(rules),
        "repair_rules": rules,
        "future_leakage_detected": guard_summary["future_leakage_detected"],
        "thresholds_lowered": False,
        "v6_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_json_file(BLOCKER_REPAIR_POLICY_V6_PATH, policy)
    write_jsonl_file(BLOCKER_REPAIR_RULES_V6_PATH, rule_records)

    summary = {
        "artifact_type": "breakthrough_blocker_repair_policy_v6_summary",
        "public_signal_research_v6_version": RESEARCH_V6_VERSION,
        "breakthrough_blocker_repair_policy_status": "repair_policy_defined_v6",
        "repair_rule_count": len(rules),
        "future_leakage_detected": guard_summary["future_leakage_detected"],
        "thresholds_lowered": False,
        "v6_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(BLOCKER_REPAIR_POLICY_V6_SUMMARY_PATH, summary)
    write_jsonl_file(
        BLOCKER_REPAIR_POLICY_V6_PROOF_PATH,
        [research_v6_proof_record("breakthrough-blocker-repair-policy-v6", "repair_policy_defined_v6", summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_breakthrough_blocker_repair_policy_v6(), indent=2, sort_keys=True, default=str))
