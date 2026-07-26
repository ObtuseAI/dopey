"""Build deterministic intraday paths for cross-underlying 0DTE v2 cases."""
from __future__ import annotations

from typing import Any

from .zero_dte_cross_underlying_fixture_models import ZeroDTECrossUnderlyingRegimeCase
from .zero_dte_underlying_family_models import ZeroDTEUnderlyingFamily, stable_cross_underlying_hash


def build_zero_dte_cross_underlying_intraday_paths(
    families: list[ZeroDTEUnderlyingFamily],
    cases: list[ZeroDTECrossUnderlyingRegimeCase],
) -> list[dict[str, Any]]:
    family_by_id = {family.underlying_family_id: family for family in families}
    return [_build_path(family_by_id[case.underlying_family_id], case) for case in cases]


def _build_path(family: ZeroDTEUnderlyingFamily, case: ZeroDTECrossUnderlyingRegimeCase) -> dict[str, Any]:
    states = [_state(family, case, minute, index) for index, minute in enumerate([0, 40, 115, 235, 375])]
    record = {
        "path_id": f"path-{case.case_id}",
        "case_id": case.case_id,
        "underlying_family_id": case.underlying_family_id,
        "synthetic_underlying_symbol": case.synthetic_underlying_symbol,
        "regime_family": case.regime_family,
        "option_type": case.option_type,
        "underlying_path": [state["underlying_price"] for state in states],
        "option_bid_mid_ask_path": [{"bid": state["option_bid"], "mid": state["option_mid"], "ask": state["option_ask"]} for state in states],
        "spread_path": [state["spread_pct"] for state in states],
        "slippage_path": [state["estimated_slippage"] for state in states],
        "liquidity_score_path": [state["liquidity_score"] for state in states],
        "delta_path": [state["delta"] for state in states],
        "gamma_path": [state["gamma"] for state in states],
        "theta_path": [state["theta"] for state in states],
        "vega_path": [state["vega"] for state in states],
        "iv_path": [state["implied_volatility"] for state in states],
        "event_macro_stress_path": [state["event_macro_stress_score"] for state in states],
        "close_signal_path": [state["close_signal"] for state in states],
        "special_close_signal_path": [state["special_close_signal"] for state in states],
        "expiry_pressure_path": [state["expiry_pressure_score"] for state in states],
        "pin_risk_state": "pin_risk" in case.risk_vectors or case.regime_family == "pin_near_strike",
        "pin_risk_state_path": [("pin_risk" in case.risk_vectors or case.regime_family == "pin_near_strike") for _ in states],
        "states": states,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
    }
    record["path_hash"] = stable_cross_underlying_hash(record)
    return record


def _state(family: ZeroDTEUnderlyingFamily, case: ZeroDTECrossUnderlyingRegimeCase, minute: int, index: int) -> dict[str, Any]:
    direction = 1.0 if case.option_type == "call" else -1.0
    base = 100.0 + int(case.case_id[-3:]) % 29
    move = _regime_move(case.regime_family, index) * direction
    underlying = round(base + move, 4)
    base_mid = 1.0 + (int(case.case_id[-3:]) % 7) * 0.07
    decay = index * (0.13 if "theta_bleed" in case.risk_vectors else 0.04)
    iv_drag = index * (0.12 if "iv_crush" in case.risk_vectors else 0.0)
    mid = round(max(0.02, base_mid + max(move, 0.0) * 0.04 - max(-move, 0.0) * 0.03 - decay - iv_drag), 4)
    spread = _spread(case, family, index)
    bid = round(max(0.01, mid * (1.0 - spread / 2.0)), 4)
    ask = round(max(bid + 0.01, mid * (1.0 + spread / 2.0)), 4)
    liquidity = round(max(0.04, _base_liquidity(family) - index * _liquidity_decay(case)), 6)
    return {
        "state_id": f"{case.case_id}-s{index}",
        "minute_index": minute,
        "underlying_price": underlying,
        "option_mid": mid,
        "option_bid": bid,
        "option_ask": ask,
        "spread_pct": round(spread, 6),
        "estimated_slippage": round(spread * (1.35 if "slippage_spike" in case.risk_vectors else 0.7), 6),
        "liquidity_score": liquidity,
        "delta": round((0.42 + index * 0.025) * direction, 6),
        "gamma": round(0.035 + index * (0.035 if "gamma_reversal" in case.risk_vectors else 0.012), 6),
        "theta": round(-0.045 - index * (0.055 if "theta_bleed" in case.risk_vectors else 0.016), 6),
        "vega": round(0.075 + index * 0.011, 6),
        "implied_volatility": round(0.34 + _iv_shift(case, index), 6),
        "event_macro_stress_score": round(_event_macro(case, index), 6),
        "close_signal": "close" if index == 3 and case.case_family in {"special_close_stress", "policy_loophole_adversarial"} else "",
        "special_close_signal": "special_close" if index == 3 and case.case_family == "special_close_stress" else "",
        "expiry_pressure_score": round(0.12 + index * (0.18 if case.case_family == "expiry_management_stress" else 0.07), 6),
    }


def _regime_move(regime: str, index: int) -> float:
    paths = {
        "bull_trend": [0.0, 0.8, 1.6, 2.2, 2.8],
        "bear_trend": [0.0, -0.8, -1.5, -2.1, -2.7],
        "chop_decay": [0.0, 0.2, -0.1, 0.1, -0.2],
        "false_breakout": [0.0, 1.2, 2.0, -0.8, -1.5],
        "false_breakdown": [0.0, -1.2, -2.0, 0.8, 1.5],
        "gap_and_fade": [1.9, 1.1, 0.2, -0.4, -0.8],
        "gap_and_go": [1.4, 2.0, 2.6, 3.0, 3.4],
        "iv_expansion": [0.0, 0.4, 0.7, 0.3, 0.2],
        "iv_crush": [0.0, 0.6, 0.8, 0.5, 0.1],
        "macro_shock": [0.0, -0.4, -1.8, 1.0, -0.6],
        "event_whipsaw": [0.0, 1.5, -1.4, 1.0, -0.8],
        "late_day_liquidity_decay": [0.0, 0.4, 0.9, 0.7, 0.2],
        "pin_near_strike": [0.0, 0.4, -0.3, 0.1, 0.0],
        "mean_reversion": [0.0, -1.2, -1.8, -0.5, 0.6],
        "trend_persistence": [0.0, 0.6, 1.4, 2.0, 2.7],
        "range_bound": [0.0, 0.3, -0.2, 0.2, -0.1],
    }
    return paths[regime][index]


def _base_liquidity(family: ZeroDTEUnderlyingFamily) -> float:
    return {"deep": 0.9, "medium": 0.72, "thin": 0.42}.get(family.option_liquidity_archetype, 0.68)


def _liquidity_decay(case: ZeroDTECrossUnderlyingRegimeCase) -> float:
    return 0.16 if "liquidity_decay" in case.risk_vectors or "late_day_liquidity_collapse" in case.risk_vectors else 0.035


def _spread(case: ZeroDTECrossUnderlyingRegimeCase, family: ZeroDTEUnderlyingFamily, index: int) -> float:
    base = 0.04 if family.spread_archetype == "tight" else 0.08
    if family.spread_archetype in {"wide", "wide_on_gap", "wide_near_close"}:
        base = 0.14
    if "spread_explosion" in case.risk_vectors or "slippage_spike" in case.risk_vectors:
        return base + index * 0.065
    return base + index * 0.014


def _iv_shift(case: ZeroDTECrossUnderlyingRegimeCase, index: int) -> float:
    if "iv_crush" in case.risk_vectors:
        return -index * 0.055
    if case.regime_family in {"iv_expansion", "event_whipsaw", "macro_shock"}:
        return index * 0.035
    return -index * 0.006


def _event_macro(case: ZeroDTECrossUnderlyingRegimeCase, index: int) -> float:
    if case.regime_family in {"macro_shock", "event_whipsaw"} or any(risk in case.risk_vectors for risk in {"event_shock", "macro_reversal"}):
        return [0.0, 0.3, 0.8, 0.65, 0.45][index]
    return [0.0, 0.05, 0.08, 0.06, 0.04][index]
