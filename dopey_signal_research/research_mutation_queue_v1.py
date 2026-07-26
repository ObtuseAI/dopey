"""Research mutation queue V1."""
from __future__ import annotations

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_common import BREAKTHROUGH_PATH, RESEARCH_ROOT, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, write_jsonl_file


QUEUE_PATH = RESEARCH_ROOT / "research_mutation_queue_v1.jsonl"
SUMMARY_PATH = RESEARCH_ROOT / "research_mutation_queue_v1_summary.json"
PROOF_PATH = RESEARCH_ROOT / "research_mutation_queue_v1_proof.jsonl"

MUTATION_TYPES = (
    "expand_sample_count",
    "alter_dte",
    "alter_moneyness",
    "alter_exit_policy",
    "tighten_risk_filter",
    "add_regime_condition",
    "sector_specific_variant",
    "relative_strength_threshold_retune",
    "volatility_threshold_retune",
    "stop_target_retune",
)


def run_research_mutation_queue_v1() -> dict[str, object]:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    breakthroughs = read_jsonl_file(BREAKTHROUGH_PATH)
    queue: list[dict[str, object]] = []
    for row in breakthroughs:
        family_id = str(row.get("family_id", ""))
        for mutation_type in MUTATION_TYPES[:6]:
            queue.append(record_with_hash({
                "artifact_type": "research_mutation_queue_v1",
                "family_id": family_id,
                "mutation_type": mutation_type,
                "priority": "high" if mutation_type in {"expand_sample_count", "alter_dte"} else "medium",
                **live_safety_fields(),
            }, "record_hash"))
    summary = {
        "artifact_type": "research_mutation_queue_v1_summary",
        "research_mutation_queue_version": "dopey-public-research-mutation-queue-v1",
        "research_mutation_queue_status": "research_mutation_queue_written",
        "mutation_queue_count": len(queue),
        "source_breakthrough_count": len(breakthroughs),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(QUEUE_PATH, queue)
    write_stage_proof(PROOF_PATH, "research-mutation-queue-v1", str(summary["research_mutation_queue_status"]), summary)
    return {**summary, "artifact_paths": {"research_mutation_queue_v1_summary": str(SUMMARY_PATH)}}
