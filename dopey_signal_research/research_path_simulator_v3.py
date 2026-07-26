"""Research path simulator V3."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_v3_common import (
    CANDIDATES_V3_PATH,
    MINIMUM_SIM_CAP,
    PRIORITY_V3_PATH,
    RESEARCH_V3_ROOT,
    TRADES_V3_PATH,
    WATCHDOG_SIM_CAP,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_autonomy.public_champion_common import active_rows_by_symbol, is_test_symbol, read_jsonl_file, record_with_hash, safe_float, write_jsonl_file
from dopey_options_engine.cohort_path_replay_engine_v4 import replay_signal_trade_v4
from dopey_signal_research.research_option_model_v3 import STRESS_PROFILES, apply_stress_profile


EXIT_EVENTS_PATH = RESEARCH_V3_ROOT / "research_path_exit_events_v3.jsonl"
QUALITY_FLAGS_PATH = RESEARCH_V3_ROOT / "research_path_simulator_quality_flags_v3.jsonl"
SUMMARY_PATH = RESEARCH_V3_ROOT / "research_path_simulator_v3_summary.json"
PROOF_PATH = RESEARCH_V3_ROOT / "research_path_simulator_v3_proof.jsonl"


def run_research_path_simulator_v3(max_candidates: int = WATCHDOG_SIM_CAP) -> dict[str, object]:
    RESEARCH_V3_ROOT.mkdir(parents=True, exist_ok=True)
    cap = max(min(max_candidates, WATCHDOG_SIM_CAP), MINIMUM_SIM_CAP)
    priorities = read_jsonl_file(PRIORITY_V3_PATH)
    candidates = read_jsonl_file(CANDIDATES_V3_PATH)
    if priorities:
        priority_ids = [str(row.get("candidate_id", "")) for row in priorities]
        candidate_map = {str(c.get("candidate_id", "")): c for c in candidates}
        ordered = [candidate_map[cid] for cid in priority_ids if cid in candidate_map]
        ordered.extend(c for c in candidates if str(c.get("candidate_id", "")) not in priority_ids)
        candidates = ordered

    rows_by_symbol = active_rows_by_symbol()
    trades: list[dict[str, object]] = []
    exit_events: list[dict[str, object]] = []
    quality_flags: list[dict[str, object]] = []
    intent_counts: Counter[str] = Counter()

    for signal in candidates:
        if len(trades) >= cap:
            break
        symbol = str(signal.get("symbol", ""))
        if is_test_symbol(symbol) or str(signal.get("trade_intent", "")) == "no_trade":
            continue
        rows = rows_by_symbol.get(symbol, [])
        stressed = apply_stress_profile(signal, STRESS_PROFILES[len(trades) % len(STRESS_PROFILES)])
        trade = replay_signal_trade_v4(stressed, rows)
        trade["discovery_family_id"] = signal.get("discovery_family_id", "")
        trade["stable_family_template_id"] = signal.get("stable_family_template_id", "")
        trade["source_mutation_id"] = signal.get("source_mutation_id", "")
        trade["watchlist_seed_id"] = signal.get("watchlist_seed_id", "")
        trade = record_with_hash(trade, "record_hash")
        trades.append(trade)
        intent_counts[str(trade.get("trade_intent", ""))] += 1
        if trade.get("exit_reason"):
            exit_events.append(
                record_with_hash(
                    {
                        "artifact_type": "research_path_exit_event_v3",
                        "trade_id": trade.get("trade_id", ""),
                        "exit_reason": trade.get("exit_reason", ""),
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )
        if bool(trade.get("short_option")) or bool(trade.get("spread_structure")):
            quality_flags.append(
                record_with_hash(
                    {"artifact_type": "research_path_simulator_quality_flag_v3", "flag_id": "unsupported_structure_detected", **live_safety_fields()},
                    "record_hash",
                )
            )

    pnl_values = [safe_float(t.get("paper_pnl")) for t in trades if str(t.get("trade_intent", "")) in {"long_call", "long_put"}]
    summary = {
        "artifact_type": "research_path_simulator_v3_summary",
        "research_path_simulator_v3_version": "dopey-public-research-path-simulator-v3",
        "research_path_simulator_v3_status": "research_paths_simulated_v3",
        "input_candidate_count": min(len(candidates), cap),
        "simulated_trade_count": len(trades),
        "long_call_count": intent_counts.get("long_call", 0),
        "long_put_count": intent_counts.get("long_put", 0),
        "no_trade_count": intent_counts.get("no_trade", 0),
        "profitable_trade_count": sum(1 for v in pnl_values if v > 0.0),
        "losing_trade_count": sum(1 for v in pnl_values if v < 0.0),
        "total_pnl": round(sum(pnl_values), 6),
        "average_pnl": round(sum(pnl_values) / len(pnl_values), 6) if pnl_values else 0.0,
        "public_data_only": True,
        "quote_priced": False,
        "model_priced": True,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(TRADES_V3_PATH, trades)
    write_jsonl_file(EXIT_EVENTS_PATH, exit_events[:5000])
    write_jsonl_file(QUALITY_FLAGS_PATH, quality_flags)
    write_stage_proof(PROOF_PATH, "research-path-simulator-v3", str(summary["research_path_simulator_v3_status"]), summary)
    return {**summary, "artifact_paths": {"research_path_simulator_v3_summary": str(SUMMARY_PATH)}}
