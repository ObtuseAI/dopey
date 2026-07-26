"""US equity market calendar backed by a bounded local XNYS session table.

Used by the operator fetch lane (skip closed sessions) and the data-freshness
sentinel (count how many sessions behind an artifact is). The installed
exchange-calendars table is constructed explicitly for 1950 through 2100 so
calendar-aware history validation can cover every currently governed series.
Reviewed NYSE dates remain as a narrow fallback if the dependency is absent.
"""
from __future__ import annotations

from datetime import date, timedelta

US_MARKET_HOLIDAYS: frozenset[str] = frozenset(
    {
        # 2026
        "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
        "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
        # 2027
        "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
        "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
        # 2028 - NYSE official calendar; New Year's Day falls on Saturday and
        # is not observed on the preceding Friday.
        "2028-01-17", "2028-02-21", "2028-04-14", "2028-05-29", "2028-06-19",
        "2028-07-04", "2028-09-04", "2028-11-23", "2028-12-25",
    }
)


try:  # exchange_calendars (Apache-2.0): authoritative XNYS sessions when installed
    import exchange_calendars as _xc

    _XNYS = _xc.get_calendar("XNYS", start="1950-01-01", end="2100-12-31")
except Exception:  # noqa: BLE001 - degrade to the reviewed static list
    _XNYS = None


def is_trading_day(day: date) -> bool:
    if _XNYS is not None:
        try:
            iso = day.isoformat()
            if _XNYS.first_session.date() <= day <= _XNYS.last_session.date():
                return bool(_XNYS.is_session(iso))
        except Exception:  # noqa: BLE001 - out-of-range or parser drift: fall through
            pass
    return day.weekday() < 5 and day.isoformat() not in US_MARKET_HOLIDAYS


def trading_days_between(earlier: date, later: date) -> int:
    """Trading sessions in the half-open interval (earlier, later]. 0 when later <= earlier."""
    if later <= earlier:
        return 0
    count = 0
    cursor = earlier + timedelta(days=1)
    while cursor <= later:
        if is_trading_day(cursor):
            count += 1
        cursor += timedelta(days=1)
    return count


def previous_trading_day(day: date) -> date:
    cursor = day - timedelta(days=1)
    while not is_trading_day(cursor):
        cursor -= timedelta(days=1)
    return cursor
