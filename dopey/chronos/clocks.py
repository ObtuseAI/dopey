"""Explicit clock domains and timestamp validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum


class ClockDomain(StrEnum):
    QUOTE = "quote"
    INTRADAY = "intraday"
    SESSION = "session"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    EARNINGS = "earnings"
    MACRO_RELEASE = "macro_release"
    SETTLEMENT = "settlement"
    EVOLUTION = "evolution"


@dataclass(frozen=True)
class ClockStamp:
    domain: ClockDomain
    event_time: str
    market_time: str
    data_version: str
    agent_version: str
    policy_version: str
    model_version: str
    parent_event_id: str
    session_id: str

    def to_dict(self) -> dict[str, str]:
        record = asdict(self)
        record["domain"] = self.domain.value
        return record


def _parse_aware_timestamp(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "clock timestamp is not ISO-8601: "
            f"field={field_name}, value={value}"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError(
            "clock timestamp requires an explicit timezone: "
            f"field={field_name}, value={value}"
        )
    return parsed


def validate_clock_stamp(stamp: ClockStamp) -> None:
    event_time = _parse_aware_timestamp(stamp.event_time, "event_time")
    market_time = _parse_aware_timestamp(stamp.market_time, "market_time")
    if market_time > event_time:
        raise ValueError(
            "market_time cannot be after event_time: "
            f"market_time={stamp.market_time}, event_time={stamp.event_time}"
        )
    required = {
        "data_version": stamp.data_version,
        "agent_version": stamp.agent_version,
        "policy_version": stamp.policy_version,
        "model_version": stamp.model_version,
        "session_id": stamp.session_id,
    }
    missing = sorted(key for key, value in required.items() if not value)
    if missing:
        raise ValueError(f"clock stamp requires version identity: missing_fields={missing}")
