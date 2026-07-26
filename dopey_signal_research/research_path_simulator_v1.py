"""Research path simulator V1."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.signal_research_common import CANDIDATES_PATH, RESEARCH_ROOT, TRADES_PATH, write_stage_proof, write_summary_with_hash
from dopey_autonomy.public_champion_common import active_rows_by_symbol, is_test_symbol, read_jsonl_file, record_with_hash, safe_float, write_jsonl_file
from dopey_options_engine.cohort_path_replay_engine_v4 import replay_signal_trade_v4
from dopey_signal_research.research_option_model_v1 import STRESS_PROFILES, apply_stress_profile


EXIT_EVENTS_PATH = RESEARCH_ROOT / "research_path_exit_events_v1.jsonl"
QUALITY_FLAGS_PATH = RESEARCH_ROOT / "research_path_simulator_quality_flags_v1.jsonl"
SUMMARY_PATH = RESEARCH_ROOT / "research_path_simulator_v1_summary.json"
PROOF_PATH = RESEARCH_ROOT / "research_path_simulator_v1_proof.jsonl"


def run_research_path_simulator_v1(max_candidates: int = 20_000) -> dict[str, object]:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    candidates = read_jsonl_file(CANDIDATES_PATH)
    rows_by_symbol = active_rows_by_symbol()
    trades: list[dict[str, object]] = []
    exit_events: list[dict[str, object]] = []
    quality_flags: list[dict[str, object]] = []
    intent_counts: Counter[str] = Counter()
    fixture_count = 0

    for signal in candidates[:max_candidates]:
        symbol = str(signal.get("symbol", ""))
        if is_test_symbol(symbol):
            fixture_count += 1
            continue
        rows = rows_by_symbol.get(symbol, [])
        stressed = apply_stress_profile(signal, STRESS_PROFILES[len(trades) % len(STRESS_PROFILES)])
        trade = replay_signal_trade_v4(stressed, rows)
        trade["family_cohort_id"] = signal.get("family_cohort_id", "")
        trade["research_signal_id"] = signal.get("signal_id", "")
        trade = record_with_hash(trade, "record_hash")
        trades.append(trade)
        intent_counts[str(trade.get("trade_intent", ""))] += 1
        if trade.get("exit_reason"):
            exit_events.append(record_with_hash({
                "artifact_type": "research_path_exit_event_v1",
                "trade_id": trade.get("trade_id", ""),
                "exit_reason": trade.get("exit_reason", ""),
                **live_safety_fields(),
            }, "record_hash"))
        if bool(trade.get("short_option")) or bool(trade.get("spread_structure")):
            quality_flags.append(record_with_hash({
                "artifact_type": "research_path_simulator_quality_flag_v1",
                "flag_id": "unsupported_structure_detected",
                "trade_id": trade.get("trade_id", ""),
                **live_safety_fields(),
            }, "record_hash"))

    pnl_values = [safe_float(trade.get("paper_pnl")) for trade in trades if str(trade.get("trade_intent", "")) in {"long_call", "long_put"}]
    summary = {
        "artifact_type": "research_path_simulator_v1_summary",
        "research_path_simulator_version": "dopey-public-research-path-simulator-v1",
        "research_path_simulator_status": "research_paths_simulated",
        "input_candidate_count": min(len(candidates), max_candidates),
        "simulated_trade_count": len(trades),
        "long_call_count": intent_counts.get("long_call", 0),
        "long_put_count": intent_counts.get("long_put", 0),
        "no_trade_count": intent_counts.get("no_trade", 0),
        "profitable_trade_count": sum(1 for value in pnl_values if value > 0.0),
        "losing_trade_count": sum(1 for value in pnl_values if value < 0.0),
        "total_pnl": round(sum(pnl_values), 6),
        "average_pnl": round(sum(pnl_values) / len(pnl_values), 6) if pnl_values else 0.0,
        "public_data_only": True,
        "fixture_trade_count": fixture_count,
        "quote_priced": False,
        "model_priced": True,
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(TRADES_PATH, trades)
    write_jsonl_file(EXIT_EVENTS_PATH, exit_events[:5000])
    write_jsonl_file(QUALITY_FLAGS_PATH, quality_flags)
    write_stage_proof(PROOF_PATH, "research-path-simulator-v1", str(summary["research_path_simulator_status"]), summary)
    return {**summary, "artifact_paths": {"research_path_simulator_v1_summary": str(SUMMARY_PATH)}}


def artifact_paths() -> dict[str, str]:
    return {"research_path_trades_v1": str(TRADES_PATH), "research_path_simulator_v1_summary": str(SUMMARY_PATH)}
