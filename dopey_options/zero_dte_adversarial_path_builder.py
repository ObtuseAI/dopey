"""Deterministic intraday path builder for 0DTE adversarial fixtures."""
from __future__ import annotations

from typing import Any

from .zero_dte_adversarial_fixture_models import ZeroDTEAdversarialFixtureCase, stable_adversarial_hash


def build_zero_dte_adversarial_intraday_paths(
    cases: list[ZeroDTEAdversarialFixtureCase],
) -> list[dict[str, Any]]:
    return [_build_path(case) for case in cases]


def _build_path(case: ZeroDTEAdversarialFixtureCase) -> dict[str, Any]:
    states = [_state(case, minute, position) for position, minute in enumerate([0, 45, 120, 240, 375])]
    record = {
        "path_id": f"path-{case.case_id}",
        "case_id": case.case_id,
        "underlying": case.underlying,
        "option_type": case.option_type,
        "fixture_shape": case.adversarial_theme,
        "underlying_path": [state["underlying_price"] for state in states],
        "option_bid_mid_ask_path": [
            {"bid": state["option_bid"], "mid": state["option_mid"], "ask": state["option_ask"]}
            for state in states
        ],
        "spread_path": [state["spread_pct"] for state in states],
        "slippage_shock_path": [state["estimated_slippage"] for state in states],
        "liquidity_score_path": [state["liquidity_score"] for state in states],
        "delta_path": [state["delta"] for state in states],
        "gamma_path": [state["gamma"] for state in states],
        "theta_path": [state["theta"] for state in states],
        "vega_path": [state["vega"] for state in states],
        "iv_path": [state["implied_volatility"] for state in states],
        "event_shock_timing": _timing(case.event_stress_type, 120),
        "macro_reversal_timing": _timing(case.primary_risk_vector, 240),
        "close_signal_timing": 240 if case.case_family == "special_close_stress" else -1,
        "special_close_signal_timing": 240 if case.case_family == "special_close_stress" else -1,
        "expiry_pressure_path": [state["expiry_pressure_score"] for state in states],
        "pin_risk_state": case.primary_risk_vector == "pin_risk" or "pin_risk" in case.secondary_risk_vectors,
        "states": states,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
    }
    record["path_hash"] = stable_adversarial_hash(record)
    return record


def _state(case: ZeroDTEAdversarialFixtureCase, minute: int, position: int) -> dict[str, Any]:
    direction = 1 if case.option_type == "call" else -1
    base_underlying = 500.0 + (int(case.case_id[-3:]) % 13)
    shock = _shock(case.primary_risk_vector, position) * direction
    underlying = round(base_underlying + shock, 4)
    base_mid = 1.2 + (int(case.case_id[-3:]) % 5) * 0.08
    decay = position * 0.12 if case.primary_risk_vector in {"theta_bleed", "iv_crush", "iv_overpayment"} else position * 0.03
    favorable = max(0.0, shock * 0.05)
    adverse = max(0.0, -shock * 0.04)
    mid = round(max(0.02, base_mid + favorable - adverse - decay), 4)
    spread = _spread(case.primary_risk_vector, position)
    bid = round(max(0.01, mid * (1.0 - spread / 2.0)), 4)
    ask = round(max(bid + 0.01, mid * (1.0 + spread / 2.0)), 4)
    return {
        "state_id": f"{case.case_id}-s{position}",
        "minute_index": minute,
        "underlying_price": underlying,
        "option_mid": mid,
        "option_bid": bid,
        "option_ask": ask,
        "spread_pct": round(spread, 6),
        "estimated_slippage": round(spread * (1.2 if case.primary_risk_vector == "slippage_spike" else 0.65), 6),
        "delta": round((0.45 + position * 0.03) * direction, 6),
        "gamma": round(0.04 + (0.08 if case.primary_risk_vector == "gamma_reversal" and position >= 2 else 0.01 * position), 6),
        "theta": round(-0.05 - (0.09 if case.primary_risk_vector == "theta_bleed" else 0.015 * position), 6),
        "vega": round(0.08 + position * 0.01, 6),
        "implied_volatility": round(0.31 - (0.08 * position if case.primary_risk_vector == "iv_crush" else 0.01 * position), 6),
        "liquidity_score": round(max(0.05, 0.86 - (0.16 * position if case.primary_risk_vector in {"liquidity_decay", "late_day_liquidity_collapse"} else 0.03 * position)), 6),
        "signal_state": case.primary_risk_vector,
        "risk_event": case.primary_risk_vector if position in {2, 3} else "",
        "close_signal": "special_close" if case.case_family == "special_close_stress" and position == 3 else "",
        "expiry_pressure_score": round(0.12 + position * (0.2 if case.case_family == "expiry_management_stress" else 0.08), 6),
    }


def _shock(primary: str, position: int) -> float:
    if primary in {"false_breakout", "false_breakdown", "gamma_reversal", "macro_reversal"}:
        return [0.0, 2.0, 4.0, -3.2, -4.5][position]
    if primary in {"theta_bleed", "iv_crush", "iv_overpayment"}:
        return [0.0, 0.3, 0.5, 0.2, -0.1][position]
    if primary in {"event_shock", "pin_risk"}:
        return [0.0, 0.8, -1.4, 0.1, 0.0][position]
    return [0.0, 0.9, 1.6, 1.2, 0.8][position]


def _spread(primary: str, position: int) -> float:
    if primary in {"spread_explosion", "slippage_spike", "late_day_liquidity_collapse"}:
        return round(0.08 + position * 0.07, 6)
    return round(0.04 + position * 0.015, 6)


def _timing(value: str, minute: int) -> int:
    return minute if value in {"high", "macro_reversal", "event_shock"} else -1
