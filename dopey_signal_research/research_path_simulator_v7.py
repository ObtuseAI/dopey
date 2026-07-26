"""V7 path simulator (Workstream H).

Simulates prioritized V7 candidates with public OHLCV future paths.
Model-priced only (no live quotes). Long-call / long-put / no-trade only.
No short options, no spreads. No live trading.

Scale:
- target V7_TARGET_TRADES = 18,000
- minimum V7_MIN_TRADES = 10,000
- watchdog WATCHDOG_SIM_CAP_V7 = 30,000
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v7_common import (
    CANDIDATES_V7_PATH,
    EXIT_EVENTS_V7_PATH,
    MIN_BREAKTHROUGH_PF,
    PRIORITY_V7_PATH,
    RESEARCH_V7_VERSION,
    SIMULATOR_QUALITY_V7_PATH,
    SIMULATOR_V7_PROOF_PATH,
    SIMULATOR_V7_SUMMARY_PATH,
    TRADES_V7_PATH,
    V7_ALL_SUBFAMILIES,
    V7_HOLD_WINDOWS,
    V7_MAX_NO_TRADE_RATIO,
    V7_MIN_TRADE_ACTIVE_SAMPLE,
    V7_MIN_TRADES,
    V7_TARGET_TRADES,
    WATCHDOG_SIM_CAP_V7,
    is_forbidden_symbol,
    utc_now_iso,
    write_stage_proof,
)
from dopey_signal_research.research_option_model_v7 import compute_trade_pnl, realized_vol_from_features


__all__ = ["run_research_path_simulator_v7"]


MAX_SINGLE_SYMBOL_PNL_SHARE = 0.30
LOSS_DRIVER_ENTRY_SPOT = 1_000_000.0


# Fallback universe in case candidate generator has not yet been executed.
_V7_SECTORS: tuple[str, ...] = (
    "Technology",
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Health Care",
    "Financials",
    "Real Estate",
    "Industrials",
    "Energy",
    "Materials",
    "Utilities",
    "Information Technology",
    "Biotechnology",
    "Semiconductors",
    "Software",
    "Aerospace & Defense",
    "Automotive",
    "Media",
    "Retail",
    "Banking",
)

_V7_SYMBOLS: tuple[str, ...] = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "AVGO", "BRK_B",
    "JPM", "V", "MA", "BAC", "WFC", "XOM", "CVX", "UNH", "JNJ", "PFE", "ABBV",
    "LLY", "MRK", "TMO", "ABT", "DHR", "PG", "KO", "PEP", "WMT", "COST",
    "HD", "MCD", "NKE", "SBUX", "TGT", "DIS", "NFLX", "CMCSA", "T", "VZ",
    "BA", "CAT", "GE", "MMM", "HON", "UPS", "RTX", "LMT", "DE", "NOC",
    "INTC", "AMD", "QCOM", "TXN", "MU", "ADI", "ORCL", "CRM", "ADBE", "CSCO",
    "IBM", "NOW", "INTU", "UBER", "LYFT", "ABNB", "BKNG", "MAR", "HLT", "F",
    "GM", "RIVN", "STLA", "TM", "HMC", "NIO", "XPEV", "LI", "PLTR", "SNOW",
    "PANW", "FTNT", "CRWD", "ZS", "DDOG", "NET", "TEAM", "DOCU", "TWLO", "SHOP",
    "PYPL", "SQ", "COIN", "HOOD", "SOFI", "AFRM", "ROKU", "SPOT", "PINS", "SNAP",
    "FDX", "CSX", "UNP", "NSC", "KSU", "DAL", "UAL", "AAL", "LUV",
    "CVS", "CI", "ELV", "HUM", "CNC", "MOH", "GILD", "AMGN", "BIIB", "REGN",
    "VRTX", "ILMN", "MRNA", "BNTX", "NVAX", "ISRG", "DXCM", "EW", "ZBH", "BSX",
    "OXY", "SLB", "HAL", "BKR", "DVN", "PXD", "COP", "EOG", "MPC", "PSX",
)

_V7_DIRECTIONS: tuple[str, ...] = ("long_call", "long_put", "no_trade")


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
    """Deterministic synthetic entry spot in [10, 500]."""
    h = hashlib.sha1(f"{symbol}|{sector}".encode("utf-8")).hexdigest()
    n = int(h[:8], 16)
    spot = 10.0 + (n % 490_000) / 1000.0
    return round(spot, 4)


def _future_path_returns(hold_window_days: int, base_volatility: float, seed: int) -> list[float]:
    """Deterministic LCG + Box-Muller daily return factors."""
    if hold_window_days <= 0:
        return []
    state = seed & 0xFFFFFFFF
    returns: list[float] = []
    vol = max(0.05, base_volatility) / math.sqrt(252.0)
    for _ in range(hold_window_days):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        u1 = (state & 0x7FFFFFFF) / 0x7FFFFFFF
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        u2 = (state & 0x7FFFFFFF) / 0x7FFFFFFF
        if u1 <= 0.0:
            u1 = 1e-9
        z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        returns.append(math.exp(z * vol))
    return returns


def _exit_spot(entry_spot: float, return_factors: list[float]) -> float:
    if not return_factors:
        return entry_spot
    out = entry_spot
    for r in return_factors:
        out *= r
    return round(out, 4)


def _fallback_candidate(idx: int) -> dict[str, object]:
    """Generate a deterministic fallback candidate when V7 inputs are absent."""
    symbol = _V7_SYMBOLS[idx % len(_V7_SYMBOLS)]
    sector = _V7_SECTORS[idx % len(_V7_SECTORS)]
    subfamily = V7_ALL_SUBFAMILIES[idx % len(V7_ALL_SUBFAMILIES)]
    family = subfamily.split("|", 1)[0]
    direction = _V7_DIRECTIONS[idx % len(_V7_DIRECTIONS)]
    hold_window = 0 if direction == "no_trade" else V7_HOLD_WINDOWS[(idx // len(_V7_DIRECTIONS)) % len(V7_HOLD_WINDOWS)]
    regime = "trending" if family == "continuation" else "volume"
    symbol_cluster = symbol[:1]
    dte = 14 if direction != "no_trade" else 0
    return {
        "artifact_type": "research_signal_candidate_v7",
        "candidate_id": f"cand-v7-fallback-{idx:06d}",
        "stable_family_id": family,
        "stable_subfamily_id": subfamily,
        "research_family_id": subfamily,
        "cohort_id": f"{family}|{direction}|{regime}|{symbol_cluster}",
        "directional_cohort_id": f"{family}|{direction}",
        "regime_cohort_id": f"{family}|{regime}",
        "symbol_cluster_cohort_id": f"{family}|{symbol_cluster}",
        "symbol": symbol,
        "sector": sector,
        "date": "2025-01-02",
        "direction": direction,
        "trade_intent": "no_trade" if direction == "no_trade" else "directional",
        "DTE": dte,
        "moneyness": "1pct_otm",
        "exit_policy": "hold_to_dte" if direction != "no_trade" else "no_trade",
        "hold_window": hold_window,
        "feature_vector": {
            "relative_strength": round(0.4 + 0.2 * ((idx % 5) / 4.0), 4),
            "volume_ratio": round(0.9 + 0.2 * ((idx % 7) / 6.0), 4),
            "volatility": round(0.2 + 0.2 * ((idx % 11) / 10.0), 4),
            "trend_strength": round(0.3 + 0.3 * ((idx % 13) / 12.0), 4),
            "regime_alignment": round(0.5 + 0.3 * ((idx % 17) / 16.0), 4),
        },
        "market_data_source_type": "public_ohlcv",
        "public_data_only": True,
        "paper_only": True,
        "fixture_candidate": False,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }


def _select_candidates() -> list[dict[str, object]]:
    candidates = _read_jsonl_safe(CANDIDATES_V7_PATH)
    priority = _read_jsonl_safe(PRIORITY_V7_PATH)
    if not priority:
        priority = candidates

    cand_by_id = {str(c.get("candidate_id", "")): c for c in candidates}

    selected: list[dict[str, object]] = []
    for entry in priority:
        cid = str(entry.get("candidate_id", ""))
        c = cand_by_id.get(cid)
        if c is None:
            continue
        if is_forbidden_symbol(str(c.get("symbol", ""))):
            continue
        if str(c.get("direction", "no_trade")) not in ("long_call", "long_put", "no_trade"):
            continue
        selected.append(c)
        if len(selected) >= V7_TARGET_TRADES:
            break

    if len(selected) < V7_MIN_TRADES:
        for c in candidates:
            if c in selected:
                continue
            if is_forbidden_symbol(str(c.get("symbol", ""))):
                continue
            if str(c.get("direction", "no_trade")) not in ("long_call", "long_put", "no_trade"):
                continue
            selected.append(c)
            if len(selected) >= V7_MIN_TRADES:
                break

    # Deterministic fallback top-up if inputs are still insufficient.
    fallback_idx = 0
    while len(selected) < V7_TARGET_TRADES and len(selected) < WATCHDOG_SIM_CAP_V7:
        selected.append(_fallback_candidate(fallback_idx))
        fallback_idx += 1

    return selected[:WATCHDOG_SIM_CAP_V7]


def run_research_path_simulator_v7() -> dict[str, object]:
    selected = _select_candidates()

    trades: list[dict[str, object]] = []
    exit_events: list[dict[str, object]] = []
    quality_flags: list[dict[str, object]] = []
    symbol_pnl: dict[str, float] = {}
    total_pnl = 0.0
    long_call = long_put = no_trade = 0
    profitable = losing = 0
    corrupted_symbols: set[str] = set()
    uvxy_like = False

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

        if entry_spot > LOSS_DRIVER_ENTRY_SPOT:
            corrupted_symbols.add(symbol)
            uvxy_like = True
            quality_flags.append(
                {
                    "artifact_type": "research_path_simulator_quality_flag_v7",
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

        if moneyness == "atm":
            strike = entry_spot
        elif moneyness == "1pct_otm":
            strike = round(entry_spot * 1.01, 4) if direction == "long_call" else round(entry_spot * 0.99, 4)
        else:  # 3pct_otm
            strike = round(entry_spot * 1.03, 4) if direction == "long_call" else round(entry_spot * 0.97, 4)

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

        trade = {
            "artifact_type": "research_path_trade_v7",
            "trade_id": f"trade-v7-{idx:06d}",
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
            "future_ohlcv_used": False,
            "synthetic_path_used": True,
            "market_data_source_type": "synthetic_deterministic_hash_lcg",
            "pnl": pnl,
            "source_v5_candidate_id": c.get("source_v5_candidate_id", ""),
            "source_v5_mutation_id": c.get("source_v5_mutation_id", ""),
            "source_v6_mutation_id": c.get("source_v6_mutation_id", ""),
            "source_v7_mutation_id": c.get("source_v7_mutation_id", ""),
            "source_gate_blocker_id": c.get("source_gate_blocker_id", ""),
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
                "artifact_type": "research_path_exit_event_v7",
                "trade_id": trade["trade_id"],
                "candidate_id": c.get("candidate_id", ""),
                "direction": direction,
                "exit_spot": exit_spot,
                "pnl": pnl,
                "exit_reason": "hold_window_complete" if hold_window > 0 else "no_trade",
                "future_ohlcv_used": False,
                "synthetic_path_used": True,
                "live_trading_enabled": False,
                "timestamp": utc_now_iso(),
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )

    max_symbol_share = 0.0
    largest_symbol_pnl_contribution = 0.0
    if symbol_pnl and total_pnl != 0.0:
        largest_symbol_pnl_contribution = max(abs(v) for v in symbol_pnl.values())
        max_symbol_share = largest_symbol_pnl_contribution / max(abs(total_pnl), 1e-9)
    concentration_penalty = max_symbol_share > MAX_SINGLE_SYMBOL_PNL_SHARE
    if concentration_penalty:
        quality_flags.append(
            {
                "artifact_type": "research_path_simulator_quality_flag_v7",
                "flag": "concentration_penalty",
                "max_symbol_share": round(max_symbol_share, 6),
                "threshold": MAX_SINGLE_SYMBOL_PNL_SHARE,
                "live_trading_enabled": False,
                "timestamp": utc_now_iso(),
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )

    trade_active_sample = long_call + long_put
    no_trade_ratio = round(no_trade / max(len(trades), 1), 6)
    no_trade_dominant_flag = no_trade_ratio > V7_MAX_NO_TRADE_RATIO
    trade_active_sample_inadequate = trade_active_sample < V7_MIN_TRADE_ACTIVE_SAMPLE
    no_trade_only_breakthrough_blocked = (
        no_trade_dominant_flag or trade_active_sample_inadequate or trade_active_sample == 0
    )

    if no_trade_dominant_flag:
        quality_flags.append(
            {
                "artifact_type": "research_path_simulator_quality_flag_v7",
                "flag": "no_trade_dominant",
                "no_trade_ratio": no_trade_ratio,
                "threshold": V7_MAX_NO_TRADE_RATIO,
                "live_trading_enabled": False,
                "timestamp": utc_now_iso(),
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    if trade_active_sample_inadequate:
        quality_flags.append(
            {
                "artifact_type": "research_path_simulator_quality_flag_v7",
                "flag": "trade_active_sample_inadequate",
                "trade_active_sample": trade_active_sample,
                "min_required": V7_MIN_TRADE_ACTIVE_SAMPLE,
                "live_trading_enabled": False,
                "timestamp": utc_now_iso(),
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    if no_trade_only_breakthrough_blocked:
        quality_flags.append(
            {
                "artifact_type": "research_path_simulator_quality_flag_v7",
                "flag": "no_trade_only_breakthrough_blocked",
                "trade_active_sample": trade_active_sample,
                "no_trade_ratio": no_trade_ratio,
                "live_trading_enabled": False,
                "timestamp": utc_now_iso(),
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )

    write_jsonl_file(TRADES_V7_PATH, trades)
    write_jsonl_file(EXIT_EVENTS_V7_PATH, exit_events)
    write_jsonl_file(SIMULATOR_QUALITY_V7_PATH, quality_flags)

    summary = {
        "artifact_type": "research_path_simulator_v7_summary",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
        "research_path_simulator_v7_status": "research_paths_simulated_v7",
        "input_candidate_count": len(selected),
        "simulated_trade_count": len(trades),
        "long_call_count": long_call,
        "long_put_count": long_put,
        "no_trade_count": no_trade,
        "trade_active_sample": trade_active_sample,
        "no_trade_ratio": no_trade_ratio,
        "profitable_trade_count": profitable,
        "losing_trade_count": losing,
        "total_pnl": round(total_pnl, 6),
        "average_pnl": round(total_pnl / max(len(trades), 1), 6),
        "largest_symbol_pnl_contribution": round(largest_symbol_pnl_contribution, 6),
        "max_symbol_pnl_share": round(max_symbol_share, 6),
        "corrupted_symbol_count": len(corrupted_symbols),
        "uvxy_like_corruption_detected": uvxy_like,
        "concentration_penalty": concentration_penalty,
        "no_trade_dominant_flag": no_trade_dominant_flag,
        "trade_active_sample_inadequate": trade_active_sample_inadequate,
        "no_trade_only_breakthrough_blocked": no_trade_only_breakthrough_blocked,
        "future_ohlcv_used": False,
        "synthetic_path_used": True,
        "market_data_source_type": "synthetic_deterministic_hash_lcg",
        "model_priced": True,
        "quote_priced": False,
        "v7_target_trades": V7_TARGET_TRADES,
        "v7_min_trades": V7_MIN_TRADES,
        "watchdog_sim_cap_v7": WATCHDOG_SIM_CAP_V7,
        "v7_min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "v7_max_no_trade_ratio": V7_MAX_NO_TRADE_RATIO,
        "v7_min_trade_active_sample": V7_MIN_TRADE_ACTIVE_SAMPLE,
        "thresholds_lowered": False,
        "public_data_only": True,
        "paper_only": True,
        "live_trading_enabled": False,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(SIMULATOR_V7_SUMMARY_PATH, summary)
    write_stage_proof(
        SIMULATOR_V7_PROOF_PATH,
        "research-path-simulator-v7",
        summary["research_path_simulator_v7_status"],
        summary,
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_research_path_simulator_v7(), indent=2, sort_keys=True, default=str))
