"""Research mutation queue V4.

Reuses V3 implementation pattern. 17 mutation types. Mutates
breakthroughs if present, else improved watchlist, else near-breakthrough
or top PF/holdout/split repair candidates. Queue must not be empty
if watchlist / near-breakthrough exists.
"""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import read_json_file, read_jsonl_file, record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v4_common import (
    BREAKTHROUGH_V4_PATH,
    GATE_V4_SUMMARY_PATH,
    MUTATION_QUEUE_V4_PATH,
    MUTATION_QUEUE_V4_PROOF_PATH,
    MUTATION_QUEUE_V4_SUMMARY_PATH,
    PRIORITY_V4_PATH,
    RESEARCH_V4_ROOT,
    WATCHLIST_V4_PATH,
    write_stage_proof,
    write_summary_with_hash,
)


MUTATION_TYPES_V4 = (
    "profit_factor_repair_above_110",
    "holdout_repair",
    "split_repair",
    "expectancy_repair",
    "drawdown_repair",
    "no_trade_filter_injection",
    "symbol_pruning",
    "sector_pruning",
    "subfamily_split",
    "dte_retune",
    "moneyness_retune",
    "exit_policy_retune",
    "risk_filter_retune",
    "relative_strength_threshold_retune",
    "volatility_threshold_retune",
    "volume_threshold_retune",
    "stop_target_retune",
)


def run_research_mutation_queue_v4() -> dict[str, object]:
    RESEARCH_V4_ROOT.mkdir(parents=True, exist_ok=True)
    gate = read_json_file(GATE_V4_SUMMARY_PATH)
    breakthroughs = read_jsonl_file(BREAKTHROUGH_V4_PATH)
    watchlist = read_jsonl_file(WATCHLIST_V4_PATH)
    priorities = read_jsonl_file(PRIORITY_V4_PATH)
    queue: list[dict[str, object]] = []
    type_counts: Counter[str] = Counter()

    sources = breakthroughs if breakthroughs else watchlist
    near_breakthrough = [row for row in priorities if float(row.get("priority_score", 0.0)) >= 0.7]
    if not sources and near_breakthrough:
        sources = near_breakthrough[:10]

    for source in sources:
        subfamily_id = str(
            source.get("stable_subfamily_id", source.get("discovery_subfamily_id", source.get("family_id", "")))
        )
        family_id = str(source.get("stable_family_id", subfamily_id))
        seed_id = str(source.get("watchlist_seed_id", subfamily_id))
        for mutation_type in MUTATION_TYPES_V4[:8]:
            type_counts[mutation_type] += 1
            queue.append(
                record_with_hash(
                    {
                        "artifact_type": "research_mutation_queue_v4",
                        "stable_subfamily_id": subfamily_id,
                        "stable_family_id": family_id,
                        "watchlist_seed_id": seed_id,
                        "mutation_type": mutation_type,
                        "source_type": "breakthrough" if breakthroughs else "watchlist",
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )

    if (
        int(gate.get("watchlist_count", 0)) > 0 or near_breakthrough
    ) and not queue:
        for mutation_type in MUTATION_TYPES_V4:
            queue.append(
                record_with_hash(
                    {
                        "artifact_type": "research_mutation_queue_v4",
                        "mutation_type": mutation_type,
                        "source_type": "watchlist_fallback",
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )
            type_counts[mutation_type] += 1

    status = "research_mutation_queue_written_v4"
    summary = {
        "artifact_type": "research_mutation_queue_v4_summary",
        "research_mutation_queue_v4_version": "dopey-public-research-mutation-queue-v4",
        "research_mutation_queue_v4_status": status,
        "source_breakthrough_count": len(breakthroughs),
        "source_watchlist_count": len(watchlist) or int(gate.get("watchlist_count", 0)),
        "source_near_breakthrough_count": len(near_breakthrough),
        "mutation_queue_count": len(queue),
        "mutation_type_counts": dict(type_counts),
        "live_trading_enabled": False,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(MUTATION_QUEUE_V4_SUMMARY_PATH, summary)
    write_jsonl_file(MUTATION_QUEUE_V4_PATH, queue)
    write_stage_proof(MUTATION_QUEUE_V4_PROOF_PATH, "research-mutation-queue-v4", status, summary)
    return {**summary, "artifact_paths": {"research_mutation_queue_v4_summary": str(MUTATION_QUEUE_V4_SUMMARY_PATH)}}
