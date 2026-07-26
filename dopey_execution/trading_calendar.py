"""Deterministic offline trading-calendar helpers."""
from __future__ import annotations

from datetime import date, timedelta


TRADING_CALENDAR_VERSION = "dopey-offline-trading-calendar-v1"


def parse_trading_date(value: str) -> date:
    if not value:
        raise ValueError("trading date must not be empty")
    return date.fromisoformat(value)


def format_trading_date(value: date) -> str:
    return value.isoformat()


def is_trading_day(value: str) -> bool:
    parsed = parse_trading_date(value)
    return parsed.weekday() < 5


def next_trading_day(value: str) -> str:
    parsed = parse_trading_date(value)
    candidate = parsed + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate = candidate + timedelta(days=1)
    return format_trading_date(candidate)


def same_trading_day(left: str, right: str) -> bool:
    return parse_trading_date(left) == parse_trading_date(right)


def is_next_trading_day_or_later(open_date: str, close_date: str) -> bool:
    return parse_trading_date(close_date) >= parse_trading_date(next_trading_day(open_date))
