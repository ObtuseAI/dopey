"""Chronos adapter for deterministic XNYS settlement-session truth."""

from __future__ import annotations

from datetime import date
from typing import Any

from dopey_core.market_calendar import is_trading_day, previous_trading_day, trading_days_between


CALENDAR_VERSION = "dopey-chronos-xnys-v1"


def build_market_session_evidence(day: date) -> dict[str, Any]:
    return {
        "artifact_type": "chronos_market_session_evidence",
        "calendar_version": CALENDAR_VERSION,
        "exchange": "XNYS",
        "session_date": day.isoformat(),
        "is_trading_day": is_trading_day(day),
        "authority": "local_exchange_calendars_xnys_with_reviewed_nyse_fallback",
        "official_calendar_url": "https://www.nyse.com/trade/hours-calendars",
        "network_accessed": False,
        "paper_only": True,
        "live_blocked": True,
        "not_execution_authority": True,
    }


__all__ = [
    "CALENDAR_VERSION",
    "build_market_session_evidence",
    "is_trading_day",
    "previous_trading_day",
    "trading_days_between",
]
