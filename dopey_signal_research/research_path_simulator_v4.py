"""V4 research path simulator.

Simulates prioritized V4 candidates using public OHLCV future paths.
Reuses ``cohort_path_replay_engine_v4`` and stress profiles from
``research_option_model_v3``. Model-priced only; long-call / long-put /
no-trade only. No short options, no spreads.
"""
from __future__ import annotations

from collections import Counter

from dopey_autonomy.champion_hardening_common import live_safety_fields
from dopey_autonomy.public_champion_common import (
    active_rows_by_symbol,
    is_test_symbol,
    read_jsonl_file,
    record_with_hash,
    safe_float,
    write_jsonl_file,
)
from dopey_autonomy.signal_research_v4_common import (
    EXIT_EVENTS_V4_PATH,
    PRIORITY_V4_PATH,
    RESEARCH_V4_ROOT,
    SIMULATOR_PROOF_PATH,
    SIMULATOR_QUALITY_FLAGS_PATH,
    SIMULATOR_SUMMARY_PATH,
    TRADES_V4_PATH,
    V4_MIN_TRADES,
    V4_TARGET_TRADES,
    WATCHDOG_SIM_CAP,
    write_stage_proof,
    write_summary_with_hash,
)
from dopey_options_engine.cohort_path_replay_engine_v4 import replay_signal_trade_v4
from dopey_signal_research.research_option_model_v4 import STRESS_PROFILES, apply_stress_profile
def run_research_path_simulator_v4(max_candidates: int = V4_TARGET_TRADES) -> dict[str, object]:
    RESEARCH_V4_ROOT.mkdir(parents=True, exist_ok=True)
    cap = max(min(max_candidates, WATCHDOG_SIM_CAP), V4_MIN_TRADES)
    priorities = read_jsonl_file(PRIORITY_V4_PATH)
    candidates = read_jsonl_file(RESEARCH_V4_ROOT / "research_signal_candidates_v4.jsonl")
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
        if is_test_symbol(symbol) or any(t in symbol.upper() for t in ("SIM", "TEST", "FIXTURE", "SYNTH")):
            continue
        if str(signal.get("trade_intent", "")) == "no_trade":
            continue
        rows = rows_by_symbol.get(symbol, [])
        if not rows:
            continue
        # Filter out invalid exit policies early.
        if str(signal.get("exit_policy", "")) not in {"fast_scalp", "trend_follow", "invalidation_strict", "theta_protective", "volatility_expansion_hunter"}:
            continue
        # Sanity: skip obviously corrupted rows (entry_spot > 1e6 means
        # the OHLCV row is bad and would explode the option pricing).
        if rows and safe_float(rows[0].get("close", 0)) > 1e6:
            continue
        # Build a replay-compatible signal by adding default fields.
        sim_signal = dict(signal)
        sim_signal.setdefault("dte_bucket", sim_signal.get("DTE", 14))
        sim_signal.setdefault("moneyness_bucket", sim_signal.get("moneyness", "1pct_otm"))
        sim_signal.setdefault("hold_window", sim_signal.get("hold_window", 5))
        sim_signal.setdefault("exit_policy", sim_signal.get("exit_policy", "trend_follow"))
        sim_signal.setdefault("target_price", 0.0)
        sim_signal.setdefault("invalidation_level", 0.0)
        sim_signal.setdefault("slippage_stress", "normal")
        sim_signal.setdefault("entry_price", 0.0)
        sim_signal.setdefault("timestamp", sim_signal.get("date", ""))
        sim_signal.setdefault("signal_id", sim_signal.get("candidate_id", ""))
        sim_signal.setdefault("setup_family", sim_signal.get("cohort_id", ""))
        sim_signal.setdefault("strategy_id", sim_signal.get("research_family_id", ""))
        stressed = apply_stress_profile(sim_signal, STRESS_PROFILES[len(trades) % len(STRESS_PROFILES)])
        try:
            trade = replay_signal_trade_v4(stressed, rows)
        except Exception as exc:  # noqa: BLE001
            quality_flags.append(
                record_with_hash(
                    {
                        "artifact_type": "research_path_simulator_quality_flag_v4",
                        "flag_id": "replay_failure",
                        "error": str(exc),
                        "candidate_id": signal.get("candidate_id", ""),
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )
            continue
        # Inject V4 lineage and replay-compatible aliases.
        dte_value = signal.get("DTE", 14)
        moneyness_value = signal.get("moneyness", "1pct_otm")
        trade["stable_family_id"] = signal.get("stable_family_id", "")
        trade["stable_subfamily_id"] = signal.get("stable_subfamily_id", "")
        trade["research_family_id"] = signal.get("research_family_id", "")
        trade["cohort_id"] = signal.get("cohort_id", "")
        trade["directional_cohort_id"] = signal.get("directional_cohort_id", "")
        trade["regime_cohort_id"] = signal.get("regime_cohort_id", "")
        trade["symbol_cluster_cohort_id"] = signal.get("symbol_cluster_cohort_id", "")
        trade["source_mutation_id"] = signal.get("source_mutation_id", "")
        trade["source_slice_id"] = signal.get("source_slice_id", "")
        trade["watchlist_seed_id"] = signal.get("watchlist_seed_id", "")
        trade["hold_window"] = signal.get("hold_window", 5)
        trade["exit_policy"] = signal.get("exit_policy", "trend_follow")
        trade["DTE"] = dte_value
        trade["dte_bucket"] = dte_value
        trade["moneyness"] = moneyness_value
        trade["moneyness_bucket"] = moneyness_value
        trade = record_with_hash(trade, "record_hash")
        # Sanity: drop trades where the model produced an implausible
        # entry_spot / option premium (data corruption guard).
        if safe_float(trade.get("entry_spot", 0.0)) > 1e6:
            quality_flags.append(
                record_with_hash(
                    {
                        "artifact_type": "research_path_simulator_quality_flag_v4",
                        "flag_id": "data_corruption_skipped",
                        "candidate_id": signal.get("candidate_id", ""),
                        "entry_spot": trade.get("entry_spot", 0.0),
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )
            continue
        trades.append(trade)
        intent_counts[str(trade.get("trade_intent", ""))] += 1
        if trade.get("exit_reason"):
            exit_events.append(
                record_with_hash(
                    {
                        "artifact_type": "research_path_exit_event_v4",
                        "trade_id": trade.get("trade_id", ""),
                        "candidate_id": signal.get("candidate_id", ""),
                        "exit_reason": trade.get("exit_reason", ""),
                        "hold_days": trade.get("hold_days", 0),
                        "paper_pnl": trade.get("paper_pnl", 0.0),
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )
        if bool(trade.get("short_option")) or bool(trade.get("spread_structure")):
            quality_flags.append(
                record_with_hash(
                    {
                        "artifact_type": "research_path_simulator_quality_flag_v4",
                        "flag_id": "unsupported_structure_detected",
                        "candidate_id": signal.get("candidate_id", ""),
                        **live_safety_fields(),
                    },
                    "record_hash",
                )
            )

    pnl_values = [safe_float(t.get("paper_pnl")) for t in trades if str(t.get("trade_intent", "")) in {"long_call", "long_put"}]
    summary = {
        "artifact_type": "research_path_simulator_v4_summary",
        "research_path_simulator_v4_version": "dopey-public-research-path-simulator-v4",
        "research_path_simulator_v4_status": "research_paths_simulated_v4",
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
        "future_ohlcv_used": True,
        "stress_profile_count": len(STRESS_PROFILES),
        **live_safety_fields(),
    }
    summary = write_summary_with_hash(SIMULATOR_SUMMARY_PATH, summary)
    write_jsonl_file(TRADES_V4_PATH, trades)
    write_jsonl_file(EXIT_EVENTS_V4_PATH, exit_events[:5000])
    write_jsonl_file(SIMULATOR_QUALITY_FLAGS_PATH, quality_flags)
    write_stage_proof(SIMULATOR_PROOF_PATH, "research-path-simulator-v4", str(summary["research_path_simulator_v4_status"]), summary)
    return {**summary, "artifact_paths": {"research_path_simulator_v4_summary": str(SIMULATOR_SUMMARY_PATH)}}
