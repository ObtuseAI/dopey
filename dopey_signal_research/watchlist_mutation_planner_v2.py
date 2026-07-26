"""Watchlist mutation planner V2."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v2_common import RESEARCH_V2_ROOT, V1_LEADERBOARD_PATH, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, safe_float, write_jsonl_file
from dopey_signal_research.watchlist_candidate_extractor_v2 import WATCHLIST_PATH, load_watchlist_seeds


QUEUE_PATH = RESEARCH_V2_ROOT / "watchlist_mutation_queue_v2.jsonl"
PLAN_PATH = RESEARCH_V2_ROOT / "watchlist_mutation_plan_v2.jsonl"
PRIORITY_PATH = RESEARCH_V2_ROOT / "watchlist_mutation_priority_v2.jsonl"
SUMMARY_PATH = RESEARCH_V2_ROOT / "watchlist_mutation_planner_v2_summary.json"
PROOF_PATH = RESEARCH_V2_ROOT / "watchlist_mutation_planner_v2_proof.jsonl"


def run_watchlist_mutation_planner_v2() -> dict[str, object]:
    RESEARCH_V2_ROOT.mkdir(parents=True, exist_ok=True)
    seeds = load_watchlist_seeds() if WATCHLIST_PATH.exists() else []
    if not seeds:
        from .watchlist_candidate_extractor_v2 import run_watchlist_candidate_extractor_v2
        run_watchlist_candidate_extractor_v2()
        seeds = load_watchlist_seeds()
    leaderboard = read_jsonl_file(V1_LEADERBOARD_PATH)
    queue: list[dict[str, object]] = []
    plans: list[dict[str, object]] = []
    priorities: list[dict[str, object]] = []
    type_counts: Counter[str] = Counter()

    sources = list(seeds)
    for row in leaderboard:
        if safe_float(row.get("net_pnl", 0.0)) > 0.0 and int(row.get("symbol_count", 0)) < 8:
            sources.append({"discovery_family_id": str(row.get("family_id", "")), "watchlist_seed_id": f"proxy-{row.get('family_id', '')}", "v1_rejection_reasons": ["symbol_count_below_minimum"]})

    for seed in sources:
        family_id = str(seed.get("discovery_family_id", seed.get("v1_family_label", "")))
        seed_id = str(seed.get("watchlist_seed_id", family_id))
        reasons = list(seed.get("v1_rejection_reasons", []))
        mutations = plan_mutations(reasons)
        for mutation_type in mutations:
            type_counts[mutation_type] += 1
            queue.append(record_with_hash({
                "artifact_type": "watchlist_mutation_queue_v2",
                "watchlist_seed_id": seed_id,
                "discovery_family_id": family_id,
                "mutation_type": mutation_type,
                "priority": priority_for(mutation_type),
                **live_safety_fields(),
            }, "record_hash"))
        plans.append(record_with_hash({
            "artifact_type": "watchlist_mutation_plan_v2",
            "watchlist_seed_id": seed_id,
            "discovery_family_id": family_id,
            "mutation_types": mutations,
            **live_safety_fields(),
        }, "record_hash"))
        priorities.append(record_with_hash({
            "artifact_type": "watchlist_mutation_priority_v2",
            "watchlist_seed_id": seed_id,
            "priority": "high",
            **live_safety_fields(),
        }, "record_hash"))

    summary = {
        "artifact_type": "watchlist_mutation_planner_v2_summary",
        "watchlist_mutation_planner_version": "dopey-public-watchlist-mutation-planner-v2",
        "watchlist_mutation_status": "watchlist_mutation_planned",
        "watchlist_seed_count": len(seeds),
        "mutation_queue_count": len(queue),
        "symbol_expansion_mutation_count": type_counts.get("symbol_expansion", 0),
        "sector_expansion_mutation_count": type_counts.get("sector_expansion", 0),
        "profit_factor_repair_mutation_count": type_counts.get("profit_factor_repair", 0),
        "holdout_repair_mutation_count": type_counts.get("holdout_repair", 0),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(QUEUE_PATH, queue)
    write_jsonl_file(PLAN_PATH, plans)
    write_jsonl_file(PRIORITY_PATH, priorities)
    write_stage_proof(PROOF_PATH, "watchlist-mutation-planner-v2", str(summary["watchlist_mutation_status"]), summary)
    return {**summary, "artifact_paths": {"watchlist_mutation_planner_v2_summary": str(SUMMARY_PATH)}}


def plan_mutations(reasons: list[str]) -> list[str]:
    mutations = ["symbol_expansion", "sector_expansion", "regime_expansion"]
    reason_set = set(reasons)
    if "symbol_count_below_minimum" in reason_set:
        mutations.extend(["symbol_expansion", "sector_expansion"])
    if "profit_factor_below_threshold" in reason_set:
        mutations.append("profit_factor_repair")
    if "holdout_survival_failed" in reason_set:
        mutations.append("holdout_repair")
    if "split_pass_rate_below_threshold" in reason_set:
        mutations.append("split_pass_repair")
    if "expectancy_not_positive" in reason_set:
        mutations.append("expectancy_repair")
    mutations.extend(["dte_retune", "moneyness_retune", "exit_policy_retune", "no_trade_filter_injection"])
    return list(dict.fromkeys(mutations))


def priority_for(mutation_type: str) -> str:
    if mutation_type in {"symbol_expansion", "sector_expansion", "holdout_repair", "profit_factor_repair"}:
        return "high"
    return "medium"
