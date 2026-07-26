"""Model-priced path simulator for conditional champion retune signals."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.champion_repair_common import RETUNE_CANDIDATES_PATH, RETUNE_TRADES_PATH, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import (
    OPTIONS_ENGINE_ROOT,
    active_rows_by_symbol,
    is_test_symbol,
    read_jsonl_file,
    record_with_hash,
    safe_float,
    write_jsonl_file,
)
from dopey_options_engine.cohort_path_replay_engine_v4 import replay_signal_trade_v4


CHUNK_SIZE = 1000
EXIT_EVENTS_PATH = OPTIONS_ENGINE_ROOT / "conditional_champion_retune_exit_events_v1.jsonl"
QUALITY_FLAGS_PATH = OPTIONS_ENGINE_ROOT / "conditional_champion_retune_path_quality_flags_v1.jsonl"
SUMMARY_PATH = OPTIONS_ENGINE_ROOT / "conditional_champion_retune_path_simulator_v1_summary.json"
PROOF_PATH = OPTIONS_ENGINE_ROOT / "conditional_champion_retune_path_simulator_v1_proof.jsonl"


def run_conditional_champion_retune_path_simulator_v1(max_signals: int = 8000) -> dict[str, object]:
    signals = read_jsonl_file(RETUNE_CANDIDATES_PATH)
    rows_by_symbol = active_rows_by_symbol()
    trades: list[dict[str, object]] = []
    exit_events: list[dict[str, object]] = []
    quality_flags: list[dict[str, object]] = []
    intent_counts: Counter[str] = Counter()

    for index, signal in enumerate(signals[:max_signals]):
        symbol = str(signal.get("symbol", ""))
        if is_test_symbol(symbol):
            continue
        rows = rows_by_symbol.get(symbol, [])
        trade = replay_signal_trade_v4(signal, rows)
        trade["parent_champion_id"] = signal.get("parent_champion_id", "")
        trade["repair_plan_id"] = signal.get("repair_plan_id", "")
        trade["repair_type"] = signal.get("repair_type", "")
        trade = record_with_hash(trade, "record_hash")
        trades.append(trade)
        intent_counts[str(trade.get("trade_intent", ""))] += 1
        if trade.get("exit_reason"):
            exit_events.append(record_with_hash({
                "artifact_type": "conditional_champion_retune_exit_event_v1",
                "trade_id": trade.get("trade_id", ""),
                "exit_reason": trade.get("exit_reason", ""),
                **live_safety_fields(),
            }, "record_hash"))
        if bool(trade.get("short_option")) or bool(trade.get("spread_structure")):
            quality_flags.append(record_with_hash({
                "artifact_type": "conditional_champion_retune_path_quality_flag_v1",
                "flag_id": "unsupported_structure_detected",
                "trade_id": trade.get("trade_id", ""),
                **live_safety_fields(),
            }, "record_hash"))

    pnl_values = [safe_float(t.get("paper_pnl")) for t in trades if str(t.get("trade_intent", "")) in {"long_call", "long_put"}]
    summary = {
        "artifact_type": "conditional_champion_retune_path_simulator_v1_summary",
        "conditional_champion_retune_path_simulator_version": "dopey-public-champion-retune-path-simulator-v1",
        "conditional_champion_retune_path_status": "conditional_retune_paths_simulated",
        "input_signal_count": min(len(signals), max_signals),
        "simulated_trade_count": len(trades),
        "long_call_count": intent_counts.get("long_call", 0),
        "long_put_count": intent_counts.get("long_put", 0),
        "no_trade_count": intent_counts.get("no_trade", 0),
        "profitable_trade_count": sum(1 for value in pnl_values if value > 0.0),
        "losing_trade_count": sum(1 for value in pnl_values if value < 0.0),
        "total_pnl": round(sum(pnl_values), 6),
        "average_pnl": round(sum(pnl_values) / len(pnl_values), 6) if pnl_values else 0.0,
        "public_data_only": True,
        "fixture_trade_count": 0,
        "quote_priced": False,
        "model_priced": True,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(RETUNE_TRADES_PATH, trades)
    write_jsonl_file(EXIT_EVENTS_PATH, exit_events[:5000])
    write_jsonl_file(QUALITY_FLAGS_PATH, quality_flags)
    write_stage_proof(PROOF_PATH, "conditional-champion-retune-path-simulator-v1", str(summary["conditional_champion_retune_path_status"]), summary)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "conditional_champion_retune_trades_v1": str(RETUNE_TRADES_PATH),
        "conditional_champion_retune_path_simulator_v1_summary": str(SUMMARY_PATH),
    }
