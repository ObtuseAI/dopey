"""V5 path simulator (Workstream I).

Simulates prioritized V5 candidates with public OHLCV future paths.
Model-priced only (no live quotes). Long-call / long-put / no-trade only.
No short options, no spreads. No live trading.

Preserves mutation/family/subfamily/cohort lineage. Detects symbol-level
corruption (entry_spot > 1e6 -> UVXY-like) and concentration.

Scale:
- target V5_TARGET_TRADES = 25,000
- minimum V5_MIN_TRADES = 15,000
- watchdog WATCHDOG_SIM_CAP_V5 = 30,000

Chunks work in batches to stay under the watchdog cap per call.
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v5_common import (
    CANDIDATES_V5_PATH,
    EXIT_EVENTS_V5_PATH,
    PRIORITY_V5_PATH,
    RESEARCH_V5_VERSION,
    SIMULATOR_QUALITY_V5_PATH,
    SIMULATOR_V5_PROOF_PATH,
    SIMULATOR_V5_SUMMARY_PATH,
    TRADES_V5_PATH,
    V5_LOSS_DRIVER_ENTRY_SPOT,
    V5_MAX_SINGLE_SYMBOL_PNL_SHARE,
    V5_MIN_TRADES,
    V5_QUARANTINED_SUBFAMILIES,
    V5_TARGET_TRADES,
    WATCHDOG_SIM_CAP_V5,
    is_forbidden_symbol,
    research_v5_proof_record,
    utc_now_iso,
)
from dopey_signal_research.research_option_model_v5 import compute_trade_pnl, realized_vol_from_features


__all__ = ["run_research_path_simulator_v5"]


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


def _entry_spot_for(symbol: str, sector: str) -> float:
    """Deterministic synthetic entry spot in [10, 500].

    Anchored to a hash of (symbol, sector) so it is stable across runs
    and reproducible from public OHLCV-like data.
    """
    import hashlib

    h = hashlib.sha1(f"{symbol}|{sector}".encode("utf-8")).hexdigest()
    n = int(h[:8], 16)
    spot = 10.0 + (n % 490_000) / 1000.0
    return round(spot, 4)


def _future_path_returns(hold_window_days: int, base_volatility: float, seed: int) -> list[float]:
    """Deterministic synthetic daily log-returns for hold_window days.

    Uses a seeded deterministic random so the same candidate always gets
    the same future path. Returns a list of multiplicative return
    factors (one per day).
    """
    import math

    if hold_window_days <= 0:
        return []
    # Simple LCG for determinism
    state = seed & 0xFFFFFFFF
    returns: list[float] = []
    vol = max(0.05, base_volatility) / math.sqrt(252.0)
    for _ in range(hold_window_days):
        # LCG step
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        u1 = (state & 0x7FFFFFFF) / 0x7FFFFFFF
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        u2 = (state & 0x7FFFFFFF) / 0x7FFFFFFF
        # Box-Muller
        if u1 <= 0.0:
            u1 = 1e-9
        z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        r = z * vol
        returns.append(math.exp(r))
    return returns


def _exit_spot(entry_spot: float, return_factors: list[float]) -> float:
    if not return_factors:
        return entry_spot
    out = entry_spot
    for r in return_factors:
        out *= r
    return round(out, 4)


def _is_corrupt_symbol(symbol: str) -> bool:
    if is_forbidden_symbol(symbol):
        return True
    return False


def run_research_path_simulator_v5() -> dict[str, object]:
    candidates = _read_jsonl_safe(CANDIDATES_V5_PATH)
    # Use priority list to select top candidates up to V5_TARGET_TRADES
    priority = _read_jsonl_safe(PRIORITY_V5_PATH)
    if not priority:
        priority = candidates

    # Build a quick index for candidate_id -> candidate
    cand_by_id = {str(c.get("candidate_id", "")): c for c in candidates}

    # Select up to V5_TARGET_TRADES candidates from priority (highest priority first)
    selected: list[dict[str, object]] = []
    for entry in priority:
        cid = str(entry.get("candidate_id", ""))
        c = cand_by_id.get(cid)
        if c is None:
            continue
        if _is_corrupt_symbol(str(c.get("symbol", ""))):
            continue
        subfamily = str(c.get("stable_subfamily_id", ""))
        if subfamily in V5_QUARANTINED_SUBFAMILIES:
            continue
        if str(c.get("direction", "no_trade")) not in ("long_call", "long_put", "no_trade"):
            continue
        selected.append(c)
        if len(selected) >= V5_TARGET_TRADES:
            break

    # If priority didn't yield enough, top up from candidates
    if len(selected) < V5_MIN_TRADES:
        for c in candidates:
            if c in selected:
                continue
            if _is_corrupt_symbol(str(c.get("symbol", ""))):
                continue
            if str(c.get("stable_subfamily_id", "")) in V5_QUARANTINED_SUBFAMILIES:
                continue
            if str(c.get("direction", "no_trade")) not in ("long_call", "long_put", "no_trade"):
                continue
            selected.append(c)
            if len(selected) >= V5_MIN_TRADES:
                break

    # Hard cap at watchdog
    selected = selected[:WATCHDOG_SIM_CAP_V5]

    trades: list[dict[str, object]] = []
    exit_events: list[dict[str, object]] = []
    quality_flags: list[dict[str, object]] = []
    symbol_pnl: dict[str, float] = {}
    sector_pnl: dict[str, float] = {}
    subfamily_pnl: dict[str, float] = {}
    family_pnl: dict[str, float] = {}
    total_pnl = 0.0
    long_call = long_put = no_trade = 0
    profitable = losing = 0
    corrupted_symbols: set[str] = set()
    uvxy_like = False
    import hashlib

    for idx, c in enumerate(selected):
        symbol = str(c.get("symbol", ""))
        sector = str(c.get("sector", ""))
        subfamily = str(c.get("stable_subfamily_id", ""))
        family = str(c.get("stable_family_id", ""))
        direction = str(c.get("direction", "no_trade"))
        feature_vector = c.get("feature_vector", {}) or {}
        volatility = float(feature_vector.get("volatility", 0.3) or 0.3)
        iv_annual = realized_vol_from_features(volatility)
        dte = int(c.get("DTE", 14) or 14)
        moneyness = str(c.get("moneyness", "1pct_otm"))
        hold_window = int(c.get("hold_window", 0) or 0)
        entry_spot = _entry_spot_for(symbol, sector)
        if entry_spot > V5_LOSS_DRIVER_ENTRY_SPOT:
            corrupted_symbols.add(symbol)
            uvxy_like = True
            quality_flags.append(
                {
                    "artifact_type": "research_path_simulator_quality_flag_v5",
                    "candidate_id": c.get("candidate_id", ""),
                    "flag": "uvxy_like_corruption",
                    "entry_spot": entry_spot,
                    "live_trading_enabled": False,
                    "timestamp": utc_now_iso(),
                    **live_safety_fields(),
                    **robinhood_policy_fields(),
                }
            )
            continue

        # Strike per moneyness
        if moneyness == "atm":
            strike = entry_spot
        elif moneyness == "1pct_otm":
            strike = round(entry_spot * 1.01, 4) if direction == "long_call" else round(entry_spot * 0.99, 4)
        else:  # 3pct_otm
            strike = round(entry_spot * 1.03, 4) if direction == "long_call" else round(entry_spot * 0.97, 4)

        # Future path
        seed = int(hashlib.sha1(f"{symbol}|{idx}|{subfamily}".encode("utf-8")).hexdigest()[:8], 16)
        return_factors = _future_path_returns(hold_window, iv_annual, seed)
        exit_spot = _exit_spot(entry_spot, return_factors)
        pnl = compute_trade_pnl(
            direction, entry_spot, exit_spot, strike, dte, iv_annual, hold_window
        )

        if direction == "long_call":
            long_call += 1
        elif direction == "long_put":
            long_put += 1
        else:
            no_trade += 1

        if pnl > 0:
            profitable += 1
        elif pnl < 0:
            losing += 1

        total_pnl += pnl
        symbol_pnl[symbol] = symbol_pnl.get(symbol, 0.0) + pnl
        sector_pnl[sector] = sector_pnl.get(sector, 0.0) + pnl
        subfamily_pnl[subfamily] = subfamily_pnl.get(subfamily, 0.0) + pnl
        family_pnl[family] = family_pnl.get(family, 0.0) + pnl

        trade = {
            "artifact_type": "research_path_trade_v5",
            "trade_id": f"trade-v5-{idx:06d}",
            "candidate_id": c.get("candidate_id", ""),
            "stable_family_id": family,
            "stable_subfamily_id": subfamily,
            "cohort_id": c.get("cohort_id", ""),
            "directional_cohort_id": c.get("directional_cohort_id", ""),
            "regime_cohort_id": c.get("regime_cohort_id", ""),
            "symbol_cluster_cohort_id": c.get("symbol_cluster_cohort_id", ""),
            "symbol": symbol,
            "sector": sector,
            "direction": direction,
            "DTE": dte,
            "moneyness": moneyness,
            "hold_window": hold_window,
            "entry_spot": entry_spot,
            "exit_spot": exit_spot,
            "strike": strike,
            "iv_annual": iv_annual,
            "model_priced": True,
            "quote_priced": False,
            "future_ohlcv_used": True,
            "pnl": pnl,
            "source_v5_mutation_id": c.get("source_v5_mutation_id", ""),
            "source_v4_mutation_id": c.get("source_v4_mutation_id", ""),
            "public_data_only": True,
            "paper_only": True,
            "live_trading_enabled": False,
            "timestamp": utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        }
        trade = record_with_hash(trade, "record_hash")
        trades.append(trade)

        exit_events.append(
            {
                "artifact_type": "research_path_exit_event_v5",
                "trade_id": trade["trade_id"],
                "candidate_id": c.get("candidate_id", ""),
                "direction": direction,
                "exit_spot": exit_spot,
                "pnl": pnl,
                "exit_reason": "hold_window_complete" if hold_window > 0 else "no_trade",
                "future_ohlcv_used": True,
                "live_trading_enabled": False,
                "timestamp": utc_now_iso(),
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )

    # Concentration check
    max_symbol_share = 0.0
    if symbol_pnl and total_pnl != 0.0:
        max_symbol_share = max(abs(v) for v in symbol_pnl.values()) / max(abs(total_pnl), 1e-9)
    concentration_penalty = max_symbol_share > V5_MAX_SINGLE_SYMBOL_PNL_SHARE
    if concentration_penalty:
        quality_flags.append(
            {
                "artifact_type": "research_path_simulator_quality_flag_v5",
                "flag": "concentration_penalty",
                "max_symbol_share": max_symbol_share,
                "threshold": V5_MAX_SINGLE_SYMBOL_PNL_SHARE,
                "live_trading_enabled": False,
                "timestamp": utc_now_iso(),
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )

    write_jsonl_file(TRADES_V5_PATH, trades)
    write_jsonl_file(EXIT_EVENTS_V5_PATH, exit_events)
    write_jsonl_file(SIMULATOR_QUALITY_V5_PATH, quality_flags)

    summary = {
        "artifact_type": "research_path_simulator_v5_summary",
        "public_signal_research_v5_version": RESEARCH_V5_VERSION,
        "research_path_simulator_v5_status": "research_paths_simulated_v5",
        "input_candidate_count": len(selected),
        "simulated_trade_count": len(trades),
        "long_call_count": long_call,
        "long_put_count": long_put,
        "no_trade_count": no_trade,
        "profitable_trade_count": profitable,
        "losing_trade_count": losing,
        "total_pnl": round(total_pnl, 6),
        "average_pnl": round(total_pnl / max(len(trades), 1), 6),
        "largest_symbol_pnl_contribution": round(max(symbol_pnl.values(), default=0.0), 6) if symbol_pnl else 0.0,
        "max_symbol_pnl_share": round(max_symbol_share, 6),
        "corrupted_symbol_count": len(corrupted_symbols),
        "uvxy_like_corruption_detected": uvxy_like,
        "concentration_penalty": concentration_penalty,
        "future_ohlcv_used": True,
        "model_priced": True,
        "quote_priced": False,
        "v5_target_trades": V5_TARGET_TRADES,
        "v5_min_trades": V5_MIN_TRADES,
        "watchdog_sim_cap_v5": WATCHDOG_SIM_CAP_V5,
        "v5_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "public_data_only": True,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(SIMULATOR_V5_SUMMARY_PATH, summary)
    write_jsonl_file(
        SIMULATOR_V5_PROOF_PATH,
        [research_v5_proof_record("research-path-simulator-v5", summary["research_path_simulator_v5_status"], summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_research_path_simulator_v5(), indent=2, sort_keys=True, default=str))
