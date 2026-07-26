"""Paper account ledger models for active long-premium options."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


ACCOUNT_LEDGER_MODEL_VERSION = "dopey-paper-account-ledger-v1"


@dataclass(frozen=True)
class PaperOptionPosition:
    position_id: str
    underlying: str
    option_type: str
    expiry: str
    strike: float
    quantity: int
    open_date: str
    open_timestamp: str
    open_order_id: str
    lifecycle_state: str
    zero_dte: bool
    same_day_close_blocked: bool
    close_eligible_date: str
    close_status: str
    policy_flags: dict[str, Any]
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DayTradeEvent:
    event_id: str
    position_id: str
    underlying: str
    option_type: str
    open_date: str
    close_date: str
    same_trading_day: bool
    zero_dte_special_lifecycle: bool
    allowed: bool
    rejection_reason: str
    audit_required: bool
    paper_only: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RotationEvent:
    rotation_id: str
    from_position_id: str
    to_candidate_id: str
    rotation_date: str
    exit_allowed: bool
    entry_allowed: bool
    delayed_exit_required: bool
    same_day_round_trip_risk: bool
    zero_dte_exception_required: bool
    decision: str
    reason_codes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PaperAccountLedger:
    account_id: str
    mode: str
    paper_only: bool
    live_blocked: bool
    positions: list[PaperOptionPosition] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)
    day_trade_events: list[DayTradeEvent] = field(default_factory=list)
    rotation_events: list[RotationEvent] = field(default_factory=list)
    policy_snapshots: list[dict[str, Any]] = field(default_factory=list)
    ledger_hash: str = ""
    account_ledger_model_version: str = ACCOUNT_LEDGER_MODEL_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ledger_hash"] = ledger_hash(self)
        return payload


def ledger_hash(ledger: PaperAccountLedger) -> str:
    payload = asdict(ledger)
    payload["ledger_hash"] = ""
    return _stable_hash(payload)


def with_refreshed_hash(ledger: PaperAccountLedger) -> PaperAccountLedger:
    return PaperAccountLedger(
        account_id=ledger.account_id,
        mode=ledger.mode,
        paper_only=ledger.paper_only,
        live_blocked=ledger.live_blocked,
        positions=list(ledger.positions),
        orders=list(ledger.orders),
        day_trade_events=list(ledger.day_trade_events),
        rotation_events=list(ledger.rotation_events),
        policy_snapshots=list(ledger.policy_snapshots),
        ledger_hash=ledger_hash(ledger),
    )


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
