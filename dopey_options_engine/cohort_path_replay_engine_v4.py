"""Cohort-aware path replay engine V4.

Replays model-priced long-premium option trades over realized future OHLCV
paths while preserving the full strategy-cohort ID stack. Outputs only
long_call / long_put / no_trade structures (no shorts, no spreads).
"""
from __future__ import annotations

import math

from dopey_autonomy.public_champion_common import realized_volatility, safe_float
from dopey_strategy_cohorts.strategy_id_canonicalizer import attach_cohort_ids

from .option_exit_policy_v3 import choose_exit_event


def replay_signal_trade_v4(signal: dict[str, object], rows: list[dict[str, str]]) -> dict[str, object]:
    """Return a single v4 trade record for the given signal over future rows."""
    intent = str(signal.get("trade_intent", "no_trade"))
    if intent == "no_trade":
        return _no_trade_record_v4(signal)
    if intent not in {"long_call", "long_put"}:
        return _blocked_trade_v4(signal, "unsupported_structure_blocked")
    entry_index = find_entry_index(rows, str(signal.get("timestamp", signal.get("date", ""))))
    if entry_index < 0 or entry_index >= len(rows) - 2:
        return _blocked_trade_v4(signal, "missing_future_ohlcv_path")
    entry_spot = safe_float(rows[entry_index]["close"])
    prior_closes = [safe_float(row["close"]) for row in rows[max(0, entry_index - 30):entry_index + 1]]
    realized_vol = realized_volatility(prior_closes)
    iv_proxy = iv_proxy_for_signal(realized_vol, signal)
    dte = int(signal.get("dte_bucket", 14))
    strike = strike_for_signal(entry_spot, signal)
    entry_mid = black_scholes_price(entry_spot, strike, dte, iv_proxy, intent)
    slippage = slippage_cost(entry_mid, str(signal.get("slippage_stress", "normal")))
    entry_premium = max(entry_mid + slippage, 0.01)
    theta_decay = theta_decay_cost(entry_premium, dte, str(signal.get("slippage_stress", "normal")))
    hold_window = max(int(signal.get("hold_window", 5)), 1)
    future_rows = rows[entry_index:min(len(rows), entry_index + hold_window + 1)]
    path_marks = build_path_marks_v4(future_rows, strike, dte, iv_proxy, intent)
    exit_event = choose_exit_event(signal, entry_premium, path_marks)
    exit_value = safe_float(exit_event["exit_option_value"])
    paper_pnl = round(exit_value - entry_premium, 6)
    best_mark = max(path_marks, key=lambda item: safe_float(item["option_value"])) if path_marks else {}
    worst_mark = min(path_marks, key=lambda item: safe_float(item["option_value"])) if path_marks else {}
    max_loss = round(entry_premium + theta_decay, 6)
    trade = {
        "artifact_type": "model_priced_path_simulator_v4_trade",
        "trade_id": f"path-v4-{signal.get('signal_id', '')}",
        "signal_id": signal.get("signal_id", ""),
        "symbol": signal.get("symbol", ""),
        "sector": signal.get("sector", ""),
        "setup_family": signal.get("setup_family", ""),
        "strategy_id": signal.get("strategy_id", ""),
        "entry_date": signal.get("timestamp", signal.get("date", "")),
        "entry_spot": round(entry_spot, 6),
        "exit_date": exit_event.get("exit_date", ""),
        "exit_spot": exit_event.get("exit_spot", 0.0),
        "hold_days": exit_event.get("hold_days", 0),
        "trade_intent": intent,
        "option_side": "call" if intent == "long_call" else "put",
        "option_position": "long",
        "option_structure": intent,
        "unsupported_structure": False,
        "short_option": False,
        "spread_structure": False,
        "strike_proxy": round(strike, 6),
        "dte_bucket": dte,
        "moneyness_bucket": signal.get("moneyness_bucket", "ATM"),
        "exit_policy": signal.get("exit_policy", ""),
        "entry_option_premium": round(entry_premium, 6),
        "entry_mid_proxy": round(entry_mid, 6),
        "slippage_cost": round(slippage, 6),
        "theta_decay_cost": round(theta_decay, 6),
        "exit_option_value": exit_value,
        "paper_pnl": paper_pnl,
        "max_loss": max_loss,
        "exit_reason": exit_event.get("exit_reason", ""),
        "target_price": signal.get("target_price", 0.0),
        "invalidation_level": signal.get("invalidation_level", 0.0),
        "best_path_option_value": round(safe_float(best_mark.get("option_value")), 6) if best_mark else 0.0,
        "worst_path_option_value": round(safe_float(worst_mark.get("option_value")), 6) if worst_mark else 0.0,
        "realized_vol_proxy": round(realized_vol, 6),
        "iv_proxy": round(iv_proxy, 6),
        "iv_proxy_regime": signal.get("iv_proxy_regime", "realized_vol"),
        "slippage_stress": signal.get("slippage_stress", "normal"),
        "theta_stress": signal.get("theta_stress", "normal"),
        "iv_shock_stress": signal.get("iv_shock_stress", "normal"),
        "model_uncertainty": round(abs(iv_proxy - realized_vol) + slippage / max(entry_premium, 0.01), 6),
        "market_data_source_type": signal.get("market_data_source_type", "public_live_fetch"),
        "data_source_label": signal.get("data_source_label", "public_live_fetch"),
        "regime": signal.get("regime", signal.get("volatility_regime", "")),
        "trend_regime": signal.get("trend_regime", ""),
        "public_data_only": True,
        "fixture_trade": False,
        "quote_priced": False,
        "model_priced": True,
        "live_trading_enabled": False,
    }
    return attach_cohort_ids(trade)


def find_entry_index(rows: list[dict[str, str]], entry_date: str) -> int:
    for index, row in enumerate(rows):
        if str(row.get("date", "")) == entry_date:
            return index
    return -1


def strike_for_signal(entry_spot: float, signal: dict[str, object]) -> float:
    bucket = str(signal.get("moneyness_bucket", "ATM"))
    pct = {"ATM": 0.0, "1pct_otm": 0.01, "2pct_otm": 0.02, "3pct_otm": 0.03}.get(bucket, 0.0)
    if str(signal.get("trade_intent")) == "long_put":
        return entry_spot * (1.0 - pct)
    return entry_spot * (1.0 + pct)


def iv_proxy_for_signal(realized_vol: float, signal: dict[str, object]) -> float:
    regime = str(signal.get("iv_proxy_regime", "realized_vol"))
    iv_shock = str(signal.get("iv_shock_stress", "normal"))
    multiplier = 1.0
    if regime == "realized_vol_plus_25pct":
        multiplier = 1.25
    elif regime == "realized_vol_plus_10pct":
        multiplier = 1.10
    elif regime == "realized_vol_minus_10pct":
        multiplier = 0.90
    if iv_shock == "high":
        multiplier *= 1.20
    elif iv_shock == "low":
        multiplier *= 0.85
    return min(max(realized_vol * multiplier, 0.10), 2.00)


def slippage_cost(entry_mid: float, slippage_stress: str) -> float:
    multiplier = {"low": 0.015, "normal": 0.04, "high": 0.085}.get(slippage_stress, 0.04)
    return max(entry_mid * multiplier, 0.01)


def theta_decay_cost(entry_premium: float, dte: int, theta_stress: str) -> float:
    if dte <= 0:
        return 0.0
    daily = entry_premium * (0.004 if dte <= 7 else 0.002)
    factor = {"high": 1.4, "low": 0.6, "normal": 1.0}.get(theta_stress, 1.0)
    return round(daily * min(dte, 20) * factor, 6)


def build_path_marks_v4(
    future_rows: list[dict[str, str]],
    strike: float,
    dte: int,
    entry_iv_proxy: float,
    intent: str,
) -> list[dict[str, object]]:
    closes = [safe_float(row["close"]) for row in future_rows]
    marks: list[dict[str, object]] = []
    for index, row in enumerate(future_rows):
        spot = safe_float(row["close"])
        dte_remaining = max(dte - index, 1)
        local_vol = realized_volatility(closes[max(0, index - 5):index + 1]) if index >= 3 else entry_iv_proxy
        iv_proxy = min(max((entry_iv_proxy * 0.7) + (local_vol * 0.3), 0.08), 2.00)
        option_value = black_scholes_price(spot, strike, dte_remaining, iv_proxy, intent)
        marks.append({
            "date": row["date"],
            "day_index": index,
            "spot": spot,
            "dte_remaining": dte_remaining,
            "entry_iv_proxy": entry_iv_proxy,
            "iv_proxy": iv_proxy,
            "option_value": option_value,
        })
    return marks


def black_scholes_price(spot: float, strike: float, dte: int, iv: float, intent: str) -> float:
    if spot <= 0.0 or strike <= 0.0:
        return 0.0
    t = max(dte, 1) / 365.0
    sigma = max(iv, 0.01)
    sqrt_t = math.sqrt(t)
    d1 = (math.log(spot / strike) + 0.5 * sigma * sigma * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    if intent == "long_put":
        value = strike * normal_cdf(-d2) - spot * normal_cdf(-d1)
    else:
        value = spot * normal_cdf(d1) - strike * normal_cdf(d2)
    intrinsic = max(0.0, spot - strike) if intent == "long_call" else max(0.0, strike - spot)
    return round(max(value, intrinsic, 0.01), 6)


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _no_trade_record_v4(signal: dict[str, object]) -> dict[str, object]:
    record = {
        "artifact_type": "model_priced_path_simulator_v4_trade",
        "trade_id": f"path-v4-{signal.get('signal_id', '')}",
        "signal_id": signal.get("signal_id", ""),
        "symbol": signal.get("symbol", ""),
        "sector": signal.get("sector", ""),
        "setup_family": signal.get("setup_family", ""),
        "strategy_id": signal.get("strategy_id", ""),
        "entry_date": signal.get("timestamp", signal.get("date", "")),
        "exit_date": signal.get("timestamp", signal.get("date", "")),
        "trade_intent": "no_trade",
        "option_side": "none",
        "option_position": "none",
        "option_structure": "no_trade",
        "unsupported_structure": False,
        "short_option": False,
        "spread_structure": False,
        "entry_option_premium": 0.0,
        "exit_option_value": 0.0,
        "paper_pnl": 0.0,
        "max_loss": 0.0,
        "exit_reason": "no_trade_capital_preservation",
        "iv_proxy_regime": signal.get("iv_proxy_regime", "realized_vol"),
        "slippage_stress": signal.get("slippage_stress", "normal"),
        "theta_stress": signal.get("theta_stress", "normal"),
        "iv_shock_stress": signal.get("iv_shock_stress", "normal"),
        "market_data_source_type": signal.get("market_data_source_type", "public_live_fetch"),
        "data_source_label": signal.get("data_source_label", "public_live_fetch"),
        "regime": signal.get("regime", signal.get("volatility_regime", "")),
        "trend_regime": signal.get("trend_regime", ""),
        "public_data_only": True,
        "fixture_trade": False,
        "quote_priced": False,
        "model_priced": True,
        "live_trading_enabled": False,
    }
    return attach_cohort_ids(record)


def _blocked_trade_v4(signal: dict[str, object], reason: str) -> dict[str, object]:
    record = _no_trade_record_v4(signal)
    record["trade_intent"] = str(signal.get("trade_intent", "no_trade"))
    record["exit_reason"] = reason
    return record
