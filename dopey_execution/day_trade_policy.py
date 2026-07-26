"""Configurable conservative no-day-trade policy for offline paper accounts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


DAY_TRADE_POLICY_VERSION = "dopey-day-trade-policy-v1"


@dataclass(frozen=True)
class DayTradePolicy:
    policy_id: str
    policy_version: str
    same_day_round_trip_blocked: bool
    zero_dte_special_lifecycle_enabled: bool
    rolling_window_tracking_enabled: bool
    rolling_window_days: int
    max_day_trade_events: int
    minimum_close_delay: str
    allow_next_trading_day_close: bool
    allow_multi_day_rotation: bool
    allow_overnight_hold: bool
    allow_zero_dte_special_exit: bool
    require_explicit_zero_dte_reason: bool
    require_zero_dte_liquidity_approval: bool
    require_zero_dte_risk_cap_approval: bool
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_day_trade_policy() -> DayTradePolicy:
    return DayTradePolicy(
        policy_id="dopey-conservative-no-day-trade-policy",
        policy_version=DAY_TRADE_POLICY_VERSION,
        same_day_round_trip_blocked=True,
        zero_dte_special_lifecycle_enabled=True,
        rolling_window_tracking_enabled=True,
        rolling_window_days=5,
        max_day_trade_events=0,
        minimum_close_delay="next_trading_day",
        allow_next_trading_day_close=True,
        allow_multi_day_rotation=True,
        allow_overnight_hold=True,
        allow_zero_dte_special_exit=True,
        require_explicit_zero_dte_reason=True,
        require_zero_dte_liquidity_approval=True,
        require_zero_dte_risk_cap_approval=True,
        paper_only=True,
        live_blocked=True,
    )


def policy_snapshot(policy: DayTradePolicy) -> dict[str, Any]:
    return {
        **policy.to_dict(),
        "policy_posture": "conservative offline PDT-safe simulation, not legal advice",
        "legal_advice": False,
    }


def day_trade_limit_exceeded(day_trade_events: list[dict[str, Any]], policy: DayTradePolicy) -> bool:
    if not policy.rolling_window_tracking_enabled:
        return False
    allowed_events = [
        event for event in day_trade_events
        if event.get("same_trading_day") is True and event.get("allowed") is True
    ]
    return len(allowed_events) > policy.max_day_trade_events
