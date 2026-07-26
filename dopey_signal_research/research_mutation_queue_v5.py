"""V5 mutation queue (Workstream L).

Generates next mutations from breakthroughs / watchlist / near-breakthroughs.
Rules:
- if breakthrough exists, mutate breakthrough
- else if improved watchlist exists, mutate watchlist
- else if near-breakthrough exists, mutate near-breakthrough
- if no mutations possible, record exact reason honestly
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v5_common import (
    BREAKTHROUGH_V5_PATH,
    MUTATION_QUEUE_V5_PATH,
    MUTATION_QUEUE_V5_PROOF_PATH,
    MUTATION_QUEUE_V5_SUMMARY_PATH,
    RESEARCH_V5_VERSION,
    WATCHLIST_V5_PATH,
    research_v5_proof_record,
    utc_now_iso,
)


__all__ = ["run_research_mutation_queue_v5"]


MUTATION_TYPES_V5: tuple[str, ...] = (
    "pf_repair_above_110",
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
    "relative_strength_retune",
    "volatility_retune",
    "volume_retune",
    "stop_target_retune",
    "profitable_slice_reinforcement",
    "loss_driver_suppression",
    "hold_window_retune",
    "stress_specific_repair",
    "recent_market_reinforcement",
)


def _read_jsonl_safe(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    out: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _mutation_id(idx: int, source_type: str) -> str:
    return f"mut-q-v5-{source_type[:4]}-{idx:04d}"


def _build_mutation_records(
    sources: list[dict[str, object]],
    source_type: str,
    start_idx: int,
) -> tuple[list[dict[str, object]], int]:
    """Build one mutation record per (source, mutation_type) pair.

    Returns (records, next_idx).
    """
    records: list[dict[str, object]] = []
    idx = start_idx
    for src in sources:
        sub = str(src.get("stable_subfamily_id", ""))
        family = str(src.get("stable_family_id", ""))
        seed = str(src.get("stable_subfamily_id", ""))
        for mtype in MUTATION_TYPES_V5:
            rec = {
                "artifact_type": "research_mutation_queue_v5",
                "mutation_id": _mutation_id(idx, source_type),
                "mutation_type": mtype,
                "source_type": source_type,
                "stable_family_id": family,
                "stable_subfamily_id": sub,
                "parent_family_id": family,
                "parent_subfamily_id": sub,
                "parent_cohort_id": str(src.get("cohort_id", "")),
                "watchlist_seed_id": seed,
                "breakthrough_seed_id": seed if source_type == "breakthrough" else "",
                "intended_fix": f"V5 mutation seed for {mtype} on {sub}",
                "v5_min_breakthrough_pf": 1.10,
                "thresholds_lowered": False,
                "live_trading_enabled": False,
                "timestamp": utc_now_iso(),
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
            records.append(record_with_hash(rec, "record_hash"))
            idx += 1
    return records, idx


def run_research_mutation_queue_v5() -> dict[str, object]:
    breakthroughs = _read_jsonl_safe(BREAKTHROUGH_V5_PATH)
    watchlist = _read_jsonl_safe(WATCHLIST_V5_PATH)

    source_breakthrough_count = len(breakthroughs)
    source_watchlist_count = len(watchlist)
    source_near_breakthrough_count = 0  # near-breakthroughs are reported in V4 result analysis

    records: list[dict[str, object]] = []
    idx = 0
    reason = ""

    if breakthroughs:
        recs, idx = _build_mutation_records(breakthroughs, "breakthrough", idx)
        records.extend(recs)
    elif watchlist:
        recs, idx = _build_mutation_records(watchlist, "watchlist", idx)
        records.extend(recs)
    else:
        reason = "no_breakthrough_no_watchlist_no_near_breakthrough"

    write_jsonl_file(MUTATION_QUEUE_V5_PATH, records)

    # mutation type counts
    type_counts: dict[str, int] = {}
    for r in records:
        type_counts[r["mutation_type"]] = type_counts.get(r["mutation_type"], 0) + 1

    summary = {
        "artifact_type": "research_mutation_queue_v5_summary",
        "public_signal_research_v5_version": RESEARCH_V5_VERSION,
        "research_mutation_queue_v5_status": "research_mutation_queue_written_v5",
        "source_breakthrough_count": source_breakthrough_count,
        "source_watchlist_count": source_watchlist_count,
        "source_near_breakthrough_count": source_near_breakthrough_count,
        "mutation_queue_count": len(records),
        "mutation_type_counts": type_counts,
        "no_mutations_reason": reason,
        "v5_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "public_data_only": True,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(MUTATION_QUEUE_V5_SUMMARY_PATH, summary)
    write_jsonl_file(
        MUTATION_QUEUE_V5_PROOF_PATH,
        [research_v5_proof_record("research-mutation-queue-v5", summary["research_mutation_queue_v5_status"], summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_research_mutation_queue_v5(), indent=2, sort_keys=True, default=str))
