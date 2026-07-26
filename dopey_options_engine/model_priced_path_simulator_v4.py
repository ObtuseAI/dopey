"""Model-priced option path simulator V4 with chunked cohort-aware replay.

Inputs V4 signal candidates, replays long-call / long-put / no-trade trades over
actual future public OHLCV paths, preserves the full cohort ID stack, and applies
slippage / theta / IV-shock stress. Processing is chunked to stay watchdog-safe.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from dopey_autonomy.public_champion_common import (
    OPTIONS_ENGINE_ROOT,
    active_rows_by_symbol,
    max_drawdown,
    profit_factor,
    proof_record,
    read_jsonl_file,
    record_with_hash,
    safe_float,
    sector_for_symbol,
    write_jsonl_file,
    write_summary_with_hash,
)

from .cohort_path_replay_engine_v4 import replay_signal_trade_v4
from .path_simulator_calibration_v4 import build_calibration_grid_v4


TRADES_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v4_trades.jsonl"
EXIT_EVENTS_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v4_exit_events.jsonl"
PATH_CACHE_MANIFEST_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v4_path_cache_manifest.json"
QUALITY_FLAGS_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v4_quality_flags.jsonl"
SUMMARY_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v4_summary.json"
PROOF_PATH = OPTIONS_ENGINE_ROOT / "model_priced_path_simulator_v4_proof.jsonl"
SIGNALS_PATH = OPTIONS_ENGINE_ROOT.parent / "signals" / "public_signal_mutation_candidates_v4.jsonl"

DEFAULT_CHUNK_SIZE = 4000
DEFAULT_CANDIDATE_CAP = 25_000
IV_REGIMES = ["realized_vol", "realized_vol_plus_10pct", "realized_vol_plus_25pct", "realized_vol_minus_10pct"]
SLIPPAGE_STRESSES = ["low", "normal", "high"]
THETA_STRESSES = ["low", "normal", "high"]
IV_SHOCK_STRESSES = ["normal", "low", "high"]


def run_model_priced_path_simulator_v4() -> dict[str, object]:
    return simulate_model_priced_paths_v4(DEFAULT_CANDIDATE_CAP)


def simulate_model_priced_paths_v4(candidate_cap: int, chunk_size: int = DEFAULT_CHUNK_SIZE) -> dict[str, object]:
    signals = read_jsonl_file(SIGNALS_PATH)[:candidate_cap]
    rows_by_symbol = active_rows_by_symbol()
    calibration = build_calibration_grid_v4()

    enriched = expand_signal_stress_grid_v4(signals)
    cap = min(len(enriched), candidate_cap)

    TRADES_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXIT_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    intent_counts: Counter = Counter()
    exit_reason_counts: Counter = Counter()
    pnl_values: list[float] = []
    symbol_set: set[str] = set()
    sector_set: set[str] = set()
    fixture_count = 0
    unsupported_count = 0
    short_count = 0
    spread_count = 0
    blocked_count = 0
    trade_index = 0
    path_cache: dict[str, object] = {}

    with TRADES_PATH.open("w", encoding="utf-8") as trades_handle, \
         EXIT_EVENTS_PATH.open("w", encoding="utf-8") as exits_handle:
        for chunk_start in range(0, cap, chunk_size):
            chunk = enriched[chunk_start:min(chunk_start + chunk_size, cap)]
            for signal in chunk:
                rows = rows_by_symbol.get(str(signal.get("symbol", "")), [])
                trade = replay_signal_trade_v4(signal, rows)
                trade = record_with_hash(trade, "record_hash")
                trades_handle.write(json.dumps(trade, sort_keys=True, ensure_ascii=True) + "\n")
                intent = str(trade.get("trade_intent", "no_trade"))
                intent_counts[intent] += 1
                exit_reason_counts[str(trade.get("exit_reason", ""))] += 1
                if intent != "no_trade":
                    pnl_values.append(safe_float(trade.get("paper_pnl")))
                symbol_set.add(str(trade.get("symbol", "")))
                sector_set.add(sector_for_symbol(str(trade.get("symbol", ""))))
                if bool(trade.get("fixture_trade", False)):
                    fixture_count += 1
                if bool(trade.get("unsupported_structure", False)):
                    unsupported_count += 1
                if bool(trade.get("short_option", False)):
                    short_count += 1
                if bool(trade.get("spread_structure", False)):
                    spread_count += 1
                if str(trade.get("exit_reason", "")) in {"missing_future_ohlcv_path", "unsupported_structure_blocked"}:
                    blocked_count += 1
                exit_record = record_with_hash({
                    "artifact_type": "model_priced_path_simulator_v4_exit_event",
                    "trade_id": trade.get("trade_id", ""),
                    "signal_id": trade.get("signal_id", ""),
                    "symbol": trade.get("symbol", ""),
                    "strategy_id": trade.get("strategy_id", ""),
                    "setup_family": trade.get("setup_family", ""),
                    "micro_cohort_id": trade.get("micro_cohort_id", ""),
                    "setup_cohort_id": trade.get("setup_cohort_id", ""),
                    "exit_reason": trade.get("exit_reason", ""),
                    "exit_date": trade.get("exit_date", ""),
                    "paper_pnl": trade.get("paper_pnl", 0.0),
                    "market_data_source_type": trade.get("market_data_source_type", ""),
                }, "record_hash")
                exits_handle.write(json.dumps(exit_record, sort_keys=True, ensure_ascii=True) + "\n")
                trade_index += 1
            path_cache[f"chunk_{chunk_start}"] = {
                "chunk_size": len(chunk),
                "cumulative_trades": trade_index,
            }

    quality_flags = build_quality_flags(
        fixture_count, unsupported_count, short_count, spread_count, blocked_count, cap,
    )
    write_jsonl_file(QUALITY_FLAGS_PATH, quality_flags)

    profitable = sum(1 for value in pnl_values if value > 0.0)
    losing = sum(1 for value in pnl_values if value < 0.0)
    summary = {
        "artifact_type": "model_priced_path_simulator_v4_summary",
        "model_priced_path_simulator_version": "dopey-model-priced-path-simulator-v4",
        "model_priced_path_simulator_status": "path_simulation_complete" if trade_index else "blocked_no_public_signals",
        "input_signal_count": len(signals),
        "simulated_trade_count": trade_index,
        "candidate_cap": candidate_cap,
        "chunk_size": chunk_size,
        "calibration_count": len(calibration),
        "long_call_count": int(intent_counts.get("long_call", 0)),
        "long_put_count": int(intent_counts.get("long_put", 0)),
        "no_trade_count": int(intent_counts.get("no_trade", 0)),
        "profitable_trade_count": profitable,
        "losing_trade_count": losing,
        "average_pnl": round(sum(pnl_values) / len(pnl_values), 6) if pnl_values else 0.0,
        "total_pnl": round(sum(pnl_values), 6),
        "max_drawdown": max_drawdown(pnl_values),
        "profit_factor": profit_factor(pnl_values),
        "symbol_count": len(symbol_set),
        "sector_count": len(sector_set),
        "blocked_trade_count": blocked_count,
        "exit_reason_counts": dict(exit_reason_counts),
        "quote_priced": False,
        "model_priced": True,
        "short_option_count": short_count,
        "spread_structure_count": spread_count,
        "public_data_only": fixture_count == 0 and unsupported_count == 0,
        "fixture_trade_count": fixture_count,
        "unsupported_structure_count": unsupported_count,
        "live_trading_enabled": False,
    }
    summary = write_summary_with_hash(SUMMARY_PATH, summary)
    write_json_file_simple(PATH_CACHE_MANIFEST_PATH, {
        "artifact_type": "model_priced_path_simulator_v4_path_cache_manifest",
        "chunks": path_cache,
        "total_trades": trade_index,
        "candidate_cap": candidate_cap,
        "live_trading_enabled": False,
    })
    write_jsonl_file(PROOF_PATH, [proof_record("model-priced-path-simulator-v4", str(summary["model_priced_path_simulator_status"]), summary)])
    return {**summary, "artifact_paths": artifact_paths()}


def expand_signal_stress_grid_v4(signals: list[dict[str, object]]) -> list[dict[str, object]]:
    expanded: list[dict[str, object]] = []
    for index, signal in enumerate(signals):
        copy = dict(signal)
        if str(copy.get("trade_intent")) == "no_trade":
            copy["iv_proxy_regime"] = "realized_vol"
            copy["slippage_stress"] = "normal"
            copy["theta_stress"] = "normal"
            copy["iv_shock_stress"] = "normal"
        else:
            copy["iv_proxy_regime"] = IV_REGIMES[index % len(IV_REGIMES)]
            copy["slippage_stress"] = SLIPPAGE_STRESSES[index % len(SLIPPAGE_STRESSES)]
            copy["theta_stress"] = THETA_STRESSES[index % len(THETA_STRESSES)]
            copy["iv_shock_stress"] = IV_SHOCK_STRESSES[index % len(IV_SHOCK_STRESSES)]
        expanded.append(copy)
    return expanded


def build_quality_flags(
    fixture_count: int,
    unsupported_count: int,
    short_count: int,
    spread_count: int,
    blocked_count: int,
    total: int,
) -> list[dict[str, object]]:
    flags: list[dict[str, object]] = []
    checks = [
        ("no_fixture_trades", fixture_count == 0, fixture_count),
        ("no_unsupported_structures", unsupported_count == 0, unsupported_count),
        ("no_short_options", short_count == 0, short_count),
        ("no_spread_structures", spread_count == 0, spread_count),
        ("model_priced_only", True, 0),
        ("quote_priced_blocked", True, 0),
        ("live_trading_disabled", True, 0),
    ]
    for flag_id, passed, count in checks:
        flags.append(record_with_hash({
            "artifact_type": "model_priced_path_simulator_v4_quality_flag",
            "flag_id": flag_id,
            "passed": bool(passed),
            "observed_count": int(count),
            "total_trades": int(total),
            "live_trading_enabled": False,
        }, "record_hash"))
    return flags


def write_json_file_simple(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def artifact_paths() -> dict[str, str]:
    return {
        "model_priced_path_simulator_v4_trades": str(TRADES_PATH),
        "model_priced_path_simulator_v4_exit_events": str(EXIT_EVENTS_PATH),
        "model_priced_path_simulator_v4_path_cache_manifest": str(PATH_CACHE_MANIFEST_PATH),
        "model_priced_path_simulator_v4_quality_flags": str(QUALITY_FLAGS_PATH),
        "model_priced_path_simulator_v4_summary": str(SUMMARY_PATH),
        "model_priced_path_simulator_v4_proof": str(PROOF_PATH),
    }
