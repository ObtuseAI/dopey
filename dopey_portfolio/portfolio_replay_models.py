"""Paper portfolio replay state models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .portfolio_hashing import stable_portfolio_hash


@dataclass(frozen=True)
class PaperPortfolioState:
    state_id: str
    portfolio_id: str
    trading_day_index: int
    timestamp_label: str
    open_positions: list[dict[str, Any]]
    pending_entries: list[dict[str, Any]]
    pending_exits: list[dict[str, Any]]
    delayed_rotations: list[dict[str, Any]]
    paper_shadow_positions: list[dict[str, Any]]
    watchlist_items: list[dict[str, Any]]
    rejected_items: list[dict[str, Any]]
    exposure_snapshot: dict[str, Any]
    constraint_snapshot: dict[str, Any]
    paper_only: bool
    live_blocked: bool
    state_hash: str

    def __post_init__(self) -> None:
        if self.trading_day_index < 0:
            raise ValueError("portfolio replay trading_day_index must be non-negative")
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("portfolio replay state must be paper_only and live_blocked")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "PaperPortfolioState":
        return cls(
            state_id=str(record["state_id"]),
            portfolio_id=str(record["portfolio_id"]),
            trading_day_index=int(record["trading_day_index"]),
            timestamp_label=str(record["timestamp_label"]),
            open_positions=[dict(value) for value in record["open_positions"]],
            pending_entries=[dict(value) for value in record["pending_entries"]],
            pending_exits=[dict(value) for value in record["pending_exits"]],
            delayed_rotations=[dict(value) for value in record["delayed_rotations"]],
            paper_shadow_positions=[dict(value) for value in record["paper_shadow_positions"]],
            watchlist_items=[dict(value) for value in record["watchlist_items"]],
            rejected_items=[dict(value) for value in record["rejected_items"]],
            exposure_snapshot=dict(record["exposure_snapshot"]),
            constraint_snapshot=dict(record["constraint_snapshot"]),
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            state_hash=str(record.get("state_hash", "")),
        )


def portfolio_state_hash(state: PaperPortfolioState) -> str:
    payload = state.to_dict()
    payload["state_hash"] = ""
    return stable_portfolio_hash(payload)

