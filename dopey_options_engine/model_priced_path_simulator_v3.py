"""Model-priced option path simulator V3 using future public OHLCV paths."""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.public_champion_common import (
    OPTIONS_ENGINE_ROOT,
    active_rows_by_symbol,
    max_drawdown,
    proof_record,
    read_jsonl_file,
    record_with_hash,
    safe_float,
    write_jsonl_file,
    write_summary_with_hash,
)

from .realized_path_trade_replayer import replay_signal_trade_v3


TRADES_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v3_trades.jsonl"
EXIT_EVENTS_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v3_exit_events.jsonl"
MISSED_WINNERS_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v3_missed_winners.jsonl"
AVOIDED_LOSERS_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v3_avoided_losers.jsonl"
SUMMARY_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v3_summary.json"
PROOF_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v3_proof.jsonl"
SIGNALS_PATH = OPTIONS_ENGINE_ROOT.parent / "signals" / "public_signal_mutation_candidates_v3.jsonl"


def run_model_priced_path_simulator_v3() -> dict[str, object]:
    return simulate_model_priced_paths_v3(5000)


def simulate_model_priced_paths_v3(candidate_cap: int) -> dict[str, object]:
    signals = read_jsonl_file(SIGNALS_PATH)[:candidate_cap]
    rows_by_symbol = active_rows_by_symbol()
    enriched_signals = expand_signal_stress_grid(signals)
    trades: list[dict[str, object]] = []
    exit_events: list[dict[str, object]] = []
    missed_winners: list[dict[str, object]] = []
    avoided_losers: list[dict[str, object]] = []
    for signal in enriched_signals:
        rows = rows_by_symbol.get(str(signal.get("symbol", "")), [])
        trade, exits, missed, avoided = replay_signal_trade_v3(signal, rows)
        trades.append(record_with_hash(trade, "record_hash"))
        exit_events.extend(record_with_hash(exit_event, "record_hash") for exit_event in exits)
        if missed:
            missed_winners.append(record_with_hash(missed, "record_hash"))
        if avoided:
            avoided_losers.append(record_with_hash(avoided, "record_hash"))
    counts = Counter(str(trade.get("trade_intent", "")) for trade in trades)
    exit_policy_pnl: dict[str, float] = {}
    for trade in trades:
        policy = str(trade.get("exit_policy", "no_policy"))
        exit_policy_pnl[policy] = exit_policy_pnl.get(policy, 0.0) + safe_float(trade.get("paper_pnl"))
    pnl_values = [safe_float(trade.get("paper_pnl")) for trade in trades if str(trade.get("trade_intent")) != "no_trade"]
    summary = {
        "artifact_type": "model_priced_path_simulator_v3_summary",
        "model_priced_path_simulator_version": "dopey-model-priced-path-simulator-v3",
        "model_priced_path_simulator_status": "path_simulation_complete" if trades else "blocked_no_public_signals",
        "input_signal_count": len(signals),
        "simulated_trade_count": len(trades),
        "long_call_count": int(counts.get("long_call", 0)),
        "long_put_count": int(counts.get("long_put", 0)),
        "no_trade_count": int(counts.get("no_trade", 0)),
        "profitable_trade_count": sum(1 for value in pnl_values if value > 0.0),
        "losing_trade_count": sum(1 for value in pnl_values if value < 0.0),
        "average_pnl": round(sum(pnl_values) / len(pnl_values), 6) if pnl_values else 0.0,
        "total_pnl": round(sum(pnl_values), 6),
        "max_drawdown": max_drawdown(pnl_values),
        "best_exit_policy": best_policy(exit_policy_pnl),
        "worst_exit_policy": worst_policy(exit_policy_pnl),
        "exit_event_count": len(exit_events),
        "missed_winner_count": len(missed_winners),
        "avoided_loser_count": len(avoided_losers),
        "quote_priced": False,
        "model_priced": True,
        "public_data_only": all(bool(trade.get("public_data_only", False)) for trade in trades),
        "fixture_trade_count": sum(1 for trade in trades if bool(trade.get("fixture_trade", False))),
        "unsupported_structure_count": sum(1 for trade in trades if bool(trade.get("unsupported_structure", False))),
        "live_trading_enabled": False,
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_jsonl_file(TRADES_PATH, trades)
    write_jsonl_file(EXIT_EVENTS_PATH, exit_events)
    write_jsonl_file(MISSED_WINNERS_PATH, missed_winners)
    write_jsonl_file(AVOIDED_LOSERS_PATH, avoided_losers)
    write_jsonl_file(PROOF_PATH, [proof_record("model-priced-path-simulator-v3", str(summary["model_priced_path_simulator_status"]), summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def expand_signal_stress_grid(signals: list[dict[str, object]]) -> list[dict[str, object]]:
    iv_regimes = ["realized_vol", "realized_vol_plus_10pct", "realized_vol_plus_25pct", "realized_vol_minus_10pct"]
    slippage_stresses = ["low", "normal", "high"]
    expanded: list[dict[str, object]] = []
    for index, signal in enumerate(signals):
        copy = dict(signal)
        if str(copy.get("trade_intent")) == "no_trade":
            copy["iv_proxy_regime"] = "realized_vol"
            copy["slippage_stress"] = "normal"
        else:
            copy["iv_proxy_regime"] = iv_regimes[index % len(iv_regimes)]
            copy["slippage_stress"] = slippage_stresses[index % len(slippage_stresses)]
        expanded.append(copy)
    return expanded


def best_policy(policy_pnl: dict[str, float]) -> str:
    if not policy_pnl:
        return ""
    return sorted(policy_pnl.items(), key=lambda item: item[1], reverse=True)[0][0]


def worst_policy(policy_pnl: dict[str, float]) -> str:
    if not policy_pnl:
        return ""
    return sorted(policy_pnl.items(), key=lambda item: item[1])[0][0]


def artifact_paths() -> dict[str, str]:
    return {
        "model_priced_path_simulator_v3_trades": str(TRADES_PATH),
        "model_priced_path_simulator_v3_exit_events": str(EXIT_EVENTS_PATH),
        "model_priced_path_simulator_v3_missed_winners": str(MISSED_WINNERS_PATH),
        "model_priced_path_simulator_v3_avoided_losers": str(AVOIDED_LOSERS_PATH),
        "model_priced_path_simulator_v3_summary": str(SUMMARY_PATH),
        "model_priced_path_simulator_v3_proof": str(PROOF_PATH),
    }

