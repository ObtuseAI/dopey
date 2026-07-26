"""Research mutation queue V3."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v3_common import (
    MUTATION_QUEUE_V3_PATH,
    PRIORITY_V3_PATH,
    RESEARCH_V3_ROOT,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import read_json_file, read_jsonl_file, record_with_hash, write_jsonl_file


SUMMARY_PATH = RESEARCH_V3_ROOT / "research_mutation_queue_v3_summary.json"
PROOF_PATH = RESEARCH_V3_ROOT / "research_mutation_queue_v3_proof.jsonl"

MUTATION_TYPES_V3 = (
    "profit_factor_repair",
    "holdout_repair",
    "split_repair",
    "expectancy_repair",
    "drawdown_repair",
    "no_trade_filter_injection",
    "symbol_pruning",
    "sector_pruning",
    "dte_retune",
    "moneyness_retune",
    "exit_policy_retune",
    "risk_filter_retune",
    "relative_strength_threshold_retune",
    "volatility_threshold_retune",
    "volume_threshold_retune",
    "stop_target_retune",
    "family_template_split",
)


def run_research_mutation_queue_v3() -> dict[str, object]:
    RESEARCH_V3_ROOT.mkdir(parents=True, exist_ok=True)
    gate = read_json_file(RESEARCH_V3_ROOT / "research_breakthrough_gate_v3_summary.json")
    breakthroughs = read_jsonl_file(RESEARCH_V3_ROOT / "research_breakthrough_candidates_v3.jsonl")
    watchlist = read_jsonl_file(RESEARCH_V3_ROOT / "research_watchlist_candidates_v3.jsonl")
    priorities = read_jsonl_file(PRIORITY_V3_PATH)
    queue: list[dict[str, object]] = []
    type_counts: Counter[str] = Counter()

    sources = breakthroughs if breakthroughs else watchlist
    near_breakthrough = [row for row in priorities if float(row.get("priority_score", 0.0)) >= 0.7]
    if not sources and near_breakthrough:
        sources = near_breakthrough[:10]

    for source in sources:
        family_id = str(source.get("discovery_family_id", source.get("family_id", source.get("stable_family_template_id", ""))))
        seed_id = str(source.get("watchlist_seed_id", family_id))
        for mutation_type in MUTATION_TYPES_V3[:8]:
            type_counts[mutation_type] += 1
            queue.append(
                record_with_hash(
                    {
                        "artifact_type": "research_mutation_queue_v3",
                        "discovery_family_id": family_id,
                        "watchlist_seed_id": seed_id,
                        "mutation_type": mutation_type,
                        "source_type": "breakthrough" if breakthroughs else "watchlist",
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )

    if (int(gate.get("watchlist_count", 0)) > 0 or near_breakthrough) and not queue:
        for mutation_type in MUTATION_TYPES_V3:
            queue.append(
                record_with_hash(
                    {
                        "artifact_type": "research_mutation_queue_v3",
                        "mutation_type": mutation_type,
                        "source_type": "watchlist_fallback",
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )
            type_counts[mutation_type] += 1

    status = "research_mutation_queue_written_v3"
    summary = {
        "artifact_type": "research_mutation_queue_v3_summary",
        "research_mutation_queue_v3_version": "dopey-public-research-mutation-queue-v3",
        "research_mutation_queue_v3_status": status,
        "source_breakthrough_count": len(breakthroughs),
        "source_watchlist_count": len(watchlist) or int(gate.get("watchlist_count", 0)),
        "source_near_breakthrough_count": len(near_breakthrough),
        "mutation_queue_count": len(queue),
        "mutation_type_counts": dict(type_counts),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(MUTATION_QUEUE_V3_PATH, queue)
    write_stage_proof(PROOF_PATH, "research-mutation-queue-v3", status, summary)
    return {**summary, "artifact_paths": {"research_mutation_queue_v3_summary": str(SUMMARY_PATH)}}
