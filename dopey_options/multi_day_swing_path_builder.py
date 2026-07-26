"""Build deterministic multi-day swing option paths for hybrid v3."""
from __future__ import annotations

from typing import Any

from .hybrid_replay_models import HybridOpportunityPair
from .multi_day_option_path_models import MultiDayOptionState
from .swing_option_models import SwingOptionCandidate, stable_hybrid_hash


def build_multi_day_swing_paths_v3(
    pairs: list[HybridOpportunityPair],
    swing_candidates: list[SwingOptionCandidate],
) -> list[dict[str, Any]]:
    swing_by_id = {candidate.candidate_id: candidate for candidate in swing_candidates}
    return [_build_path(pair, swing_by_id[pair.swing_candidate_id]) for pair in pairs]


def _build_path(pair: HybridOpportunityPair, candidate: SwingOptionCandidate) -> dict[str, Any]:
    day_count = 5 if candidate.expected_hold_days >= 5 else 3
    states: list[dict[str, Any]] = []
    for day_index in range(day_count):
        for minute in ([0, 210, 390] if day_index == 0 else [0, 390]):
            state = _state(pair, candidate, day_index, minute)
            states.append(state.to_dict())
    record = {
        "artifact_type": "hybrid_multi_day_path",
        "path_id": f"multi-day-path-{pair.pair_id}",
        "pair_id": pair.pair_id,
        "swing_candidate_id": candidate.candidate_id,
        "underlying_family_id": pair.underlying_family_id,
        "synthetic_underlying_symbol": pair.synthetic_underlying_symbol,
        "regime_family": pair.regime_family,
        "option_type": pair.option_type,
        "states": states,
        "entry_day_present": any(state["trading_day_index"] == 0 for state in states),
        "overnight_gap_present": any(state["overnight_gap_state"] != "none" for state in states),
        "next_day_close_eligible_present": any(state["trading_day_index"] == 1 and state["close_signal"] == "close_eligible" for state in states),
        "day_three_present": any(state["trading_day_index"] == 2 for state in states),
        "delayed_rotation_event": pair.expected_rotation_action.startswith("delay_rotation"),
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
    }
    record["path_hash"] = stable_hybrid_hash(record)
    return record


def _state(pair: HybridOpportunityPair, candidate: SwingOptionCandidate, day_index: int, minute: int) -> MultiDayOptionState:
    direction = 1.0 if pair.option_type == "call" else -1.0
    base = 100.0 + int(pair.pair_id[-3:]) % 23
    regime_move = _regime_move(pair.regime_family, day_index) * direction
    underlying = round(base + regime_move, 4)
    spread = round(max(0.02, candidate.spread_pct + day_index * 0.01), 4)
    decay = abs(candidate.theta) * day_index * 0.22
    gap_bonus = 0.18 if day_index > 0 and pair.expected_no_day_trade_result == "overnight_gap_risk_recorded" else 0.0
    mid = round(max(0.05, candidate.open_price + max(regime_move, 0.0) * 0.05 - max(-regime_move, 0.0) * 0.04 - decay - gap_bonus), 4)
    bid = round(max(0.01, mid * (1.0 - spread / 2.0)), 4)
    ask = round(max(bid + 0.01, mid * (1.0 + spread / 2.0)), 4)
    return MultiDayOptionState(
        state_id=f"{pair.pair_id}-d{day_index}-m{minute}",
        trading_day_index=day_index,
        minute_index=minute,
        underlying_price=underlying,
        option_mid=mid,
        option_bid=bid,
        option_ask=ask,
        spread_pct=spread,
        estimated_slippage=round(spread * 0.55, 4),
        delta=candidate.delta,
        gamma=round(max(0.01, candidate.gamma - day_index * 0.004), 4),
        theta=round(candidate.theta - day_index * 0.015, 4),
        vega=round(max(0.03, candidate.vega - day_index * 0.01), 4),
        implied_volatility=round(max(0.08, candidate.implied_volatility - (0.04 if pair.regime_family == "iv_crush" else 0.0) * day_index), 4),
        liquidity_score=round(max(0.05, candidate.liquidity_score - day_index * 0.035), 4),
        signal_state=_signal_state(pair, day_index),
        risk_event=_risk_event(pair, day_index),
        close_signal="close_blocked_same_day" if day_index == 0 else "close_eligible",
        overnight_gap_state="gap_risk" if day_index == 1 and pair.expected_no_day_trade_result == "overnight_gap_risk_recorded" else ("modeled_gap" if day_index == 1 else "none"),
        expiry_pressure_score=round(min(1.0, 0.18 + day_index * 0.12), 4),
        paper_only=True,
        live_blocked=True,
    )


def _regime_move(regime: str, day_index: int) -> float:
    moves = {
        "bull_trend": [0.6, 1.4, 2.2, 2.7, 3.1],
        "bear_trend": [0.5, 1.2, 2.0, 2.5, 2.9],
        "gap_and_go": [0.9, 2.1, 3.0, 3.3, 3.5],
        "gap_and_fade": [0.8, -0.6, -1.2, -1.4, -1.5],
        "false_breakout": [0.7, -0.9, -1.5, -1.7, -1.8],
        "false_breakdown": [0.7, -0.9, -1.5, -1.7, -1.8],
        "trend_persistence": [0.5, 1.0, 1.7, 2.4, 2.9],
        "mean_reversion": [0.4, -0.3, 0.6, 0.8, 0.9],
    }.get(regime, [0.2, 0.1, -0.1, 0.0, 0.1])
    return moves[min(day_index, len(moves) - 1)]


def _signal_state(pair: HybridOpportunityPair, day_index: int) -> str:
    if pair.expected_preference == "prefer_no_trade":
        return "signal_rejected"
    if pair.expected_preference == "prefer_delayed_rotation" and day_index == 0:
        return "delay_until_close_eligible"
    return "signal_active" if day_index <= 2 else "signal_aging"


def _risk_event(pair: HybridOpportunityPair, day_index: int) -> str:
    if day_index == 1 and pair.expected_no_day_trade_result == "overnight_gap_risk_recorded":
        return "overnight_gap_risk"
    if pair.regime_family in {"macro_shock", "event_whipsaw"}:
        return "event_macro_risk"
    if pair.regime_family == "iv_crush":
        return "iv_crush_risk"
    return "none"
