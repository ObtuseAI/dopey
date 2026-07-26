"""Execute the V3 mutation queue for V4.

Reads the V3 mutation queue and the V3 supporting artifacts
(tournament scores, breakthrough gate rejections, watchlist candidates,
stable family templates, no-trade filter records) and emits an
execution plan for each of the 8 queued mutations.
"""
from __future__ import annotations

import hashlib
from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v3_common import (
    MUTATION_QUEUE_V3_PATH,
    RESEARCH_V3_ROOT,
    STABLE_FAMILY_VOLUME,
    normalize_stable_family_id,
)
from dopey_autonomy.public_champion_common import read_json_file, read_jsonl_file, record_with_hash, write_jsonl_file
from dopey_autonomy.signal_research_v4_common import (
    MUTATION_EXEC_FAILURES_PATH,
    MUTATION_EXEC_PROOF_PATH,
    MUTATION_EXEC_RECORDS_PATH,
    MUTATION_EXEC_SUMMARY_PATH,
    RESEARCH_V4_ROOT,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_signal_research.research_mutation_execution_models_v4 import (
    CANDIDATE_PLAN_BASE,
    MUTATION_EVALUATION_AXIS_V4,
    MUTATION_INTENDED_FIX_V4,
    SOURCE_REJECTION_BY_MUTATION_V4,
)


def run_research_mutation_queue_executor_v4() -> dict[str, object]:
    RESEARCH_V4_ROOT.mkdir(parents=True, exist_ok=True)
    queue = read_jsonl_file(MUTATION_QUEUE_V3_PATH)
    v3_tournament = read_json_file(RESEARCH_V3_ROOT / "research_tournament_v3_summary.json")
    v3_gate = read_json_file(RESEARCH_V3_ROOT / "research_breakthrough_gate_v3_summary.json")
    v3_watchlist = read_jsonl_file(RESEARCH_V3_ROOT / "research_watchlist_candidates_v3.jsonl")
    v3_rejections = read_jsonl_file(RESEARCH_V3_ROOT / "research_breakthrough_rejections_v3.jsonl")
    v3_no_trade = read_jsonl_file(RESEARCH_V3_ROOT / "research_no_trade_filter_records_v3.jsonl")

    records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    type_counts: Counter[str] = Counter()
    applicable_count = 0
    skipped_count = 0
    plan_total = 0

    for index, mutation in enumerate(queue):
        v3_type = str(mutation.get("mutation_type", ""))
        family_id = normalize_stable_family_id(str(mutation.get("discovery_family_id", "")))
        seed_id = str(mutation.get("watchlist_seed_id", ""))
        mutation_id = f"mut-exec-v4-{hashlib.sha256(f'{index}|{family_id}|{v3_type}'.encode()).hexdigest()[:12]}"
        try:
            applicable, why_skipped = _is_applicable(v3_type, family_id, v3_tournament, v3_gate, v3_watchlist, v3_no_trade)
            plan = CANDIDATE_PLAN_BASE.get(v3_type, 400) + (200 if family_id == STABLE_FAMILY_VOLUME else 0)
            plan_total += plan if applicable else 0
            type_counts[v3_type] += 1
            if applicable:
                applicable_count += 1
            else:
                skipped_count += 1
            records.append(
                record_with_hash(
                    {
                        "artifact_type": "research_mutation_execution_record_v4",
                        "mutation_id": mutation_id,
                        "parent_mutation_id_v3": str(mutation.get("mutation_id", "")),
                        "parent_family_id": family_id,
                        "parent_cohort_id": family_id.split("|")[0],
                        "mutation_type": v3_type,
                        "intended_fix": MUTATION_INTENDED_FIX_V4.get(v3_type, "repair_research_slice"),
                        "expected_evaluation_axis": MUTATION_EVALUATION_AXIS_V4.get(v3_type, "profit_factor"),
                        "source_rejection_reason": SOURCE_REJECTION_BY_MUTATION_V4.get(v3_type, "profit_factor_below_threshold"),
                        "source_mutation_type_v3": v3_type,
                        "watchlist_seed_id": seed_id,
                        "candidate_generation_plan_count": plan,
                        "applicable": applicable,
                        "skipped_reason": why_skipped,
                        "v3_top_profit_factor": v3_tournament.get("top_profit_factor", 0.0),
                        "v3_top_net_pnl": v3_tournament.get("top_net_pnl", 0.0),
                        "v3_breakthrough_candidate_count": v3_gate.get("breakthrough_candidate_count", 0),
                        "v3_watchlist_count": v3_gate.get("watchlist_count", 0),
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
                        "artifact_type": "research_mutation_execution_failure_v4",
                        "mutation_id": mutation_id,
                        "error": str(exc),
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )

    status = "research_mutation_queue_executed_v4" if records and not failures else "research_mutation_queue_execution_partial_v4"
    if not queue:
        status = "research_mutation_queue_empty_v4"
    summary = {
        "artifact_type": "research_mutation_queue_executor_v4_summary",
        "research_mutation_queue_executor_v4_version": "dopey-public-research-mutation-queue-executor-v4",
        "research_mutation_queue_executor_v4_status": status,
        "input_mutation_count": len(queue),
        "executed_mutation_count": applicable_count,
        "failed_mutation_count": len(failures),
        "skipped_mutation_count": skipped_count,
        "candidate_generation_plan_count": plan_total,
        "mutation_type_counts": dict(type_counts),
        "v3_top_profit_factor": v3_tournament.get("top_profit_factor", 0.0),
        "v3_top_net_pnl": v3_tournament.get("top_net_pnl", 0.0),
        "v3_watchlist_count": v3_gate.get("watchlist_count", 0),
        "v3_breakthrough_candidate_count": v3_gate.get("breakthrough_candidate_count", 0),
        "v3_no_trade_filter_record_count": len(v3_no_trade),
        "v3_rejection_count": len(v3_rejections),
        "public_data_only": True,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(MUTATION_EXEC_SUMMARY_PATH, summary)
    write_jsonl_file(MUTATION_EXEC_RECORDS_PATH, records)
    write_jsonl_file(MUTATION_EXEC_FAILURES_PATH, failures)
    write_stage_proof(MUTATION_EXEC_PROOF_PATH, "research-mutation-queue-executor-v4", status, summary)
    return {**summary, "artifact_paths": {"research_mutation_queue_executor_v4_summary": str(MUTATION_EXEC_SUMMARY_PATH)}}


def _is_applicable(
    mutation_type: str,
    family_id: str,
    v3_tournament: dict[str, object],
    v3_gate: dict[str, object],
    v3_watchlist: list[dict[str, object]],
    v3_no_trade: list[dict[str, object]],
) -> tuple[bool, str]:
    """Return (applicable, why_skipped_or_empty). All V3-queued mutations
    are applicable in V4 because the V3 state is preserved and the
    mutations are exactly what V4 must execute. We do, however, mark
    'volume-only' family_id as N/A when the source mutation is a
    continuation-only mutation (e.g. symbol_pruning) so we do not
    silently mis-attribute work.
    """
    if not mutation_type:
        return False, "empty_mutation_type"
    if family_id == STABLE_FAMILY_VOLUME and mutation_type not in {"volume_threshold_retune", "no_trade_filter_injection", "family_template_split"}:
        return False, "mutation_not_applicable_to_volume_family"
    if mutation_type in {"profit_factor_repair", "holdout_repair", "split_repair", "expectancy_repair"}:
        if float(v3_tournament.get("top_profit_factor", 0.0)) >= 1.10:
            return False, "v3_already_above_pf_threshold"
    return True, ""
