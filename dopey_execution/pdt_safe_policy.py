"""PDT-safe offline policy facade.

This module intentionally models conservative offline constraints only. It is
not legal advice and does not claim regulatory sufficiency.
"""
from __future__ import annotations

from .day_trade_policy import DayTradePolicy, default_day_trade_policy, policy_snapshot


PDT_SAFE_POLICY_VERSION = "dopey-pdt-safe-offline-policy-v1"


def default_pdt_safe_policy() -> DayTradePolicy:
    policy = default_day_trade_policy()
    return DayTradePolicy(
        policy_id="dopey-configurable-pdt-safe-offline-policy",
        policy_version=PDT_SAFE_POLICY_VERSION,
        same_day_round_trip_blocked=policy.same_day_round_trip_blocked,
        zero_dte_special_lifecycle_enabled=policy.zero_dte_special_lifecycle_enabled,
        rolling_window_tracking_enabled=policy.rolling_window_tracking_enabled,
        rolling_window_days=policy.rolling_window_days,
        max_day_trade_events=policy.max_day_trade_events,
        minimum_close_delay=policy.minimum_close_delay,
        allow_next_trading_day_close=policy.allow_next_trading_day_close,
        allow_multi_day_rotation=policy.allow_multi_day_rotation,
        allow_overnight_hold=policy.allow_overnight_hold,
        allow_zero_dte_special_exit=policy.allow_zero_dte_special_exit,
        require_explicit_zero_dte_reason=policy.require_explicit_zero_dte_reason,
        require_zero_dte_liquidity_approval=policy.require_zero_dte_liquidity_approval,
        require_zero_dte_risk_cap_approval=policy.require_zero_dte_risk_cap_approval,
        paper_only=True,
        live_blocked=True,
    )


def pdt_safe_policy_snapshot(policy: DayTradePolicy) -> dict:
    snapshot = policy_snapshot(policy)
    snapshot["pdt_safe_policy_version"] = PDT_SAFE_POLICY_VERSION
    return snapshot
