"""No-day-trade guard for active DOPEY paper option lifecycles."""
from __future__ import annotations

from dataclasses import asdict, dataclass


NO_DAY_TRADE_GUARD_VERSION = "dopey-no-day-trade-guard-v1"

SAME_DAY_ROUND_TRIP_REJECTED = "same_day_round_trip_rejected"


@dataclass(frozen=True)
class NoDayTradeDecision:
    allowed: bool
    reason_code: str
    lifecycle_state: str
    no_day_trade_guard_version: str = NO_DAY_TRADE_GUARD_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_no_day_trade(
    open_date: str,
    close_date: str,
    zero_dte: bool,
    lifecycle_state: str,
    reason_code: str,
    liquidity_approved: bool,
    risk_cap_approved: bool,
) -> NoDayTradeDecision:
    if not open_date:
        return NoDayTradeDecision(False, "close_without_open_position_rejected", "rejected")
    if not close_date:
        return NoDayTradeDecision(False, "missing_close_date_rejected", "rejected")
    if close_date < open_date:
        return NoDayTradeDecision(False, "close_before_open_rejected", "rejected")
    if close_date > open_date:
        return NoDayTradeDecision(True, "next_trading_day_or_later_close_allowed", "close_eligible_next_trading_day")
    if zero_dte and lifecycle_state == "zero_dte_expiry_managed":
        if not reason_code:
            return NoDayTradeDecision(False, "zero_dte_special_close_requires_explicit_reason_code", "rejected")
        if not liquidity_approved:
            return NoDayTradeDecision(False, "zero_dte_missing_liquidity_approval", "rejected")
        if not risk_cap_approved:
            return NoDayTradeDecision(False, "zero_dte_missing_risk_cap", "rejected")
        return NoDayTradeDecision(True, "zero_dte_expiry_managed_not_normal_day_trade", "zero_dte_expiry_managed")
    return NoDayTradeDecision(False, SAME_DAY_ROUND_TRIP_REJECTED, "blocked_same_day_round_trip")


def is_next_day_or_later(open_date: str, close_date: str) -> bool:
    return bool(open_date and close_date and close_date > open_date)
