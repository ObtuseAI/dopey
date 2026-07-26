"""Execute V2 mutation queue entries for V3 repair."""
from __future__ import annotations

import hashlib
from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v2_common import MUTATION_QUEUE_V2_PATH
from dopey_autonomy.signal_research_v3_common import (
    RESEARCH_V3_ROOT,
    normalize_stable_family_id,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import read_jsonl_file, record_with_hash, write_jsonl_file
from dopey_signal_research.research_mutation_execution_models_v3 import (
    MUTATION_EVALUATION_AXIS,
    MUTATION_INTENDED_FIX,
    SOURCE_REJECTION_BY_MUTATION,
    V2_TO_V3_MUTATION_MAP,
)


EXECUTION_RECORDS_PATH = RESEARCH_V3_ROOT / "research_mutation_execution_records_v3.jsonl"
FAILURES_PATH = RESEARCH_V3_ROOT / "research_mutation_execution_failures_v3.jsonl"
SUMMARY_PATH = RESEARCH_V3_ROOT / "research_mutation_queue_executor_v3_summary.json"
PROOF_PATH = RESEARCH_V3_ROOT / "research_mutation_queue_executor_v3_proof.jsonl"


def run_research_mutation_queue_executor_v3() -> dict[str, object]:
    RESEARCH_V3_ROOT.mkdir(parents=True, exist_ok=True)
    queue = read_jsonl_file(MUTATION_QUEUE_V2_PATH)
    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    type_counts: Counter[str] = Counter()
    plan_count = 0

    for index, mutation in enumerate(queue):
        v2_type = str(mutation.get("mutation_type", ""))
        exec_type = V2_TO_V3_MUTATION_MAP.get(v2_type, v2_type or "repair_profit_factor")
        family_id = normalize_stable_family_id(str(mutation.get("discovery_family_id", "")))
        seed_id = str(mutation.get("watchlist_seed_id", ""))
        mutation_id = f"mut-exec-v3-{hashlib.sha256(f'{index}|{family_id}|{exec_type}'.encode()).hexdigest()[:12]}"
        try:
            generated = candidate_plan_count(exec_type, family_id)
            plan_count += generated
            type_counts[exec_type] += 1
            records.append(
                record_with_hash(
                    {
                        "artifact_type": "research_mutation_execution_record_v3",
                        "mutation_id": mutation_id,
                        "parent_family_id": family_id,
                        "parent_cohort_id": family_id.split("|")[0],
                        "mutation_type": exec_type,
                        "intended_fix": MUTATION_INTENDED_FIX.get(exec_type, "repair_research_slice"),
                        "generated_candidate_count": generated,
                        "expected_evaluation_axis": MUTATION_EVALUATION_AXIS.get(exec_type, "profit_factor"),
                        "source_rejection_reason": SOURCE_REJECTION_BY_MUTATION.get(exec_type, "profit_factor_below_threshold"),
                        "source_mutation_type_v2": v2_type,
                        "watchlist_seed_id": seed_id,
                        "public_data_only": True,
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(
                record_with_hash(
                    {
                        "artifact_type": "research_mutation_execution_failure_v3",
                        "mutation_id": mutation_id,
                        "error": str(exc),
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )

    status = "mutation_queue_executed_v3" if records and not failures else "mutation_queue_execution_partial_v3"
    if not queue:
        status = "mutation_queue_empty_v3"
    summary = {
        "artifact_type": "research_mutation_queue_executor_v3_summary",
        "research_mutation_queue_executor_v3_version": "dopey-public-research-mutation-queue-executor-v3",
        "research_mutation_queue_executor_status": status,
        "input_mutation_count": len(queue),
        "executed_mutation_count": len(records),
        "failed_mutation_count": len(failures),
        "candidate_generation_plan_count": plan_count,
        "mutation_type_counts": dict(type_counts),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(EXECUTION_RECORDS_PATH, records)
    write_jsonl_file(FAILURES_PATH, failures)
    write_stage_proof(PROOF_PATH, "research-mutation-queue-executor-v3", status, summary)
    return {**summary, "artifact_paths": {"research_mutation_queue_executor_v3_summary": str(SUMMARY_PATH)}}


def candidate_plan_count(exec_type: str, family_id: str) -> int:
    base = 400 if "volume" in family_id else 350
    if exec_type in {"repair_profit_factor", "repair_holdout_weakness", "repair_split_weakness"}:
        return base + 150
    if exec_type == "add_no_trade_filter":
        return base + 100
    if exec_type in {"broaden_symbols", "broaden_sectors"}:
        return base
    return max(base - 50, 200)
