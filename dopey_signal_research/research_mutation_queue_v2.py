"""Research mutation queue V2."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v2_common import MUTATION_QUEUE_V2_PATH, RESEARCH_V2_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import read_json_file, read_jsonl_file, record_with_hash, write_jsonl_file
from dopey_signal_research.watchlist_mutation_models_v2 import MUTATION_TYPES


SUMMARY_PATH = RESEARCH_V2_ROOT / "research_mutation_queue_v2_summary.json"
PROOF_PATH = RESEARCH_V2_ROOT / "research_mutation_queue_v2_proof.jsonl"


def run_research_mutation_queue_v2() -> dict[str, object]:
    RESEARCH_V2_ROOT.mkdir(parents=True, exist_ok=True)
    gate = read_json_file(RESEARCH_V2_ROOT / "research_breakthrough_gate_v2_summary.json")
    breakthroughs = read_jsonl_file(RESEARCH_V2_ROOT / "research_breakthrough_candidates_v2.jsonl")
    watchlist = read_jsonl_file(RESEARCH_V2_ROOT / "research_watchlist_candidates_v2.jsonl")
    planner_queue = read_jsonl_file(RESEARCH_V2_ROOT / "watchlist_mutation_queue_v2.jsonl")
    queue: list[dict[str, object]] = []
    type_counts: Counter[str] = Counter()

    sources = breakthroughs if breakthroughs else watchlist
    if not sources and planner_queue:
        queue = list(planner_queue)
    else:
        for source in sources:
            family_id = str(source.get("discovery_family_id", source.get("family_id", "")))
            seed_id = str(source.get("watchlist_seed_id", family_id))
            for mutation_type in MUTATION_TYPES[:10]:
                type_counts[mutation_type] += 1
                queue.append(record_with_hash({
                    "artifact_type": "research_mutation_queue_v2",
                    "discovery_family_id": family_id,
                    "watchlist_seed_id": seed_id,
                    "mutation_type": mutation_type,
                    "source_type": "breakthrough" if breakthroughs else "watchlist",
                    **live_safety_fields(),
                }, "record_hash"))
        if not queue and int(gate.get("watchlist_count", 0)) > 0:
            for row in planner_queue:
                queue.append(row)
                type_counts[str(row.get("mutation_type", ""))] += 1

    if int(gate.get("watchlist_count", 0)) > 0 and not queue:
        for mutation_type in MUTATION_TYPES:
            queue.append(record_with_hash({
                "artifact_type": "research_mutation_queue_v2",
                "mutation_type": mutation_type,
                "source_type": "watchlist_fallback",
                **live_safety_fields(),
            }, "record_hash"))
            type_counts[mutation_type] += 1

    summary = {
        "artifact_type": "research_mutation_queue_v2_summary",
        "research_mutation_queue_v2_version": "dopey-public-research-mutation-queue-v2",
        "research_mutation_queue_v2_status": "research_mutation_queue_written_v2",
        "source_breakthrough_count": len(breakthroughs),
        "source_watchlist_count": len(watchlist) or int(gate.get("watchlist_count", 0)),
        "mutation_queue_count": len(queue),
        "mutation_type_counts": dict(type_counts),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(MUTATION_QUEUE_V2_PATH, queue)
    write_stage_proof(PROOF_PATH, "research-mutation-queue-v2", str(summary["research_mutation_queue_v2_status"]), summary)
    return {**summary, "artifact_paths": {"research_mutation_queue_v2_summary": str(SUMMARY_PATH)}}
