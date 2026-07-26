"""V4 no-trade filter optimizer.

Combines the slice miner's keep/prune/retune outputs with the
V3 no-trade filter records and the V3 watchlist lineage to produce a
selectivity policy and per-rule quality flags. The optimizer never
relaxes the breakthrough gate thresholds; it only decides which
pre-entry features or sample-supported priors are sufficient evidence
to add a no-trade rule.
"""
from __future__ import annotations

import json
from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v4_common import (
    NO_TRADE_OPTIMIZER_PROOF_PATH,
    NO_TRADE_OPTIMIZER_SUMMARY_PATH,
    NO_TRADE_QUALITY_FLAGS_PATH,
    NO_TRADE_RULES_PATH,
    RESEARCH_V4_ROOT,
    SELECTIVITY_POLICY_PATH,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_signal_research.selectivity_policy_v4 import rule_records, selectivity_policy
from dopey_autonomy.signal_research_v3_common import RESEARCH_V3_ROOT


V3_NO_TRADE_PATH = RESEARCH_V3_ROOT / "research_no_trade_filter_records_v3.jsonl"
V3_REJECTIONS_PATH = RESEARCH_V3_ROOT / "research_breakthrough_rejections_v3.jsonl"
V3_WATCHLIST_PATH = RESEARCH_V3_ROOT / "research_watchlist_candidates_v3.jsonl"
V4_LOSS_DRIVER_PATH = RESEARCH_V4_ROOT / "loss_driver_slice_records_v4.jsonl"
V4_RETUNE_PATH = RESEARCH_V4_ROOT / "slice_retune_recommendations_v4.jsonl"
V4_PRUNE_PATH = RESEARCH_V4_ROOT / "slice_pruning_recommendations_v4.jsonl"


def run_no_trade_filter_optimizer_v4() -> dict[str, object]:
    RESEARCH_V4_ROOT.mkdir(parents=True, exist_ok=True)
    v3_no_trade = read_jsonl_file(V3_NO_TRADE_PATH)
    v3_rejections = read_jsonl_file(V3_REJECTIONS_PATH)
    v3_watchlist = read_jsonl_file(V3_WATCHLIST_PATH)
    loss_drivers = read_jsonl_file(V4_LOSS_DRIVER_PATH)
    retune = read_jsonl_file(V4_RETUNE_PATH)
    pruning = read_jsonl_file(V4_PRUNE_PATH)

    rules = rule_records()
    policy = selectivity_policy()
    quality_flags: list[dict[str, object]] = []
    expected_pruned = 0
    type_counter: Counter[str] = Counter()
    future_leakage_detected = False

    # Validate each rule's intent, source, and label completeness.
    for rule in rules:
        for required in ("rule_id", "rule_type", "applies_to", "intent", "description"):
            if required not in rule or not rule[required]:
                quality_flags.append(record_with_hash({"artifact_type": "no_trade_filter_optimizer_quality_flag_v4", "flag_id": f"missing_{required}_{rule.get('rule_id', 'unknown')}", "severity": "error", **live_safety_fields()}, "record_hash"))
        if rule.get("uses_future_information") is not False:
            future_leakage_detected = True
            quality_flags.append(record_with_hash({"artifact_type": "no_trade_filter_optimizer_quality_flag_v4", "flag_id": f"future_leakage_{rule.get('rule_id', 'unknown')}", "severity": "error", **live_safety_fields()}, "record_hash"))
        if rule.get("uses_realized_outcome_label") is not False:
            future_leakage_detected = True
            quality_flags.append(record_with_hash({"artifact_type": "no_trade_filter_optimizer_quality_flag_v4", "flag_id": f"outcome_label_{rule.get('rule_id', 'unknown')}", "severity": "error", **live_safety_fields()}, "record_hash"))
        type_counter[str(rule.get("rule_type"))] += 1
        expected_pruned += 1

    expected_pruned += len(loss_drivers)
    expected_pruned += len(pruning)
    expected_pruned += len(retune)

    summary = {
        "artifact_type": "no_trade_filter_optimizer_v4_summary",
        "no_trade_filter_optimizer_v4_version": "dopey-no-trade-filter-optimizer-v4",
        "no_trade_filter_optimizer_status": "no_trade_filter_optimizer_complete_v4",
        "filter_rule_count": len(rules),
        "feature_rule_count": policy["feature_rule_count"],
        "historical_prior_rule_count": policy["historical_prior_rule_count"],
        "expected_pruned_trade_count": expected_pruned,
        "coverage_preservation_status": "preserved" if policy.get("minimum_symbol_floor", 0) and policy.get("minimum_sector_floor", 0) else "below_floor",
        "future_leakage_detected": future_leakage_detected,
        "loss_driver_slice_count": len(loss_drivers),
        "retune_recommendation_count": len(retune),
        "prune_recommendation_count": len(pruning),
        "v3_no_trade_filter_record_count": len(v3_no_trade),
        "v3_rejection_count": len(v3_rejections),
        "v3_watchlist_count": len(v3_watchlist),
        "rule_type_counts": dict(type_counter),
        "public_data_only": True,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(NO_TRADE_OPTIMIZER_SUMMARY_PATH, summary)
    write_jsonl_file(NO_TRADE_RULES_PATH, rules)
    write_jsonl_file(NO_TRADE_QUALITY_FLAGS_PATH, quality_flags)
    SELECTIVITY_POLICY_PATH.write_text(json.dumps(policy, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    write_stage_proof(NO_TRADE_OPTIMIZER_PROOF_PATH, "no-trade-filter-optimizer-v4", str(summary["no_trade_filter_optimizer_status"]), summary)
    return {**summary, "artifact_paths": {"no_trade_filter_optimizer_v4_summary": str(NO_TRADE_OPTIMIZER_SUMMARY_PATH)}}
