"""Portfolio rotation decision models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .portfolio_hashing import stable_portfolio_hash


ALLOWED_PORTFOLIO_ROTATION_DECISIONS: frozenset[str] = frozenset({
    "open_position",
    "hold_position",
    "close_position_allowed",
    "close_delayed_same_day_block",
    "rotate_allowed",
    "rotate_delayed",
    "paper_shadow_only",
    "watchlist_only",
    "reject_policy",
    "reject_exposure",
    "reject_live_path",
})


@dataclass(frozen=True)
class PortfolioRotationDecision:
    rotation_decision_id: str
    source_allocation_id: str
    decision_type: str
    from_position_id: str
    to_opportunity_id: str
    trading_day_index: int
    entry_allowed: bool
    exit_allowed: bool
    same_day_close_blocked: bool
    delayed_until_day_index: int
    reason_codes: list[str]
    exposure_effect: dict[str, Any]
    paper_only: bool
    live_blocked: bool
    decision_hash: str

    def __post_init__(self) -> None:
        if self.decision_type not in ALLOWED_PORTFOLIO_ROTATION_DECISIONS:
            raise ValueError(f"unsupported portfolio rotation decision: {self.decision_type}")
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("portfolio rotation decision must be paper_only and live_blocked")
        if self.trading_day_index < 0 or self.delayed_until_day_index < 0:
            raise ValueError("portfolio rotation day indexes must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "PortfolioRotationDecision":
        return cls(
            rotation_decision_id=str(record["rotation_decision_id"]),
            source_allocation_id=str(record["source_allocation_id"]),
            decision_type=str(record["decision_type"]),
            from_position_id=str(record["from_position_id"]),
            to_opportunity_id=str(record["to_opportunity_id"]),
            trading_day_index=int(record["trading_day_index"]),
            entry_allowed=bool(record["entry_allowed"]),
            exit_allowed=bool(record["exit_allowed"]),
            same_day_close_blocked=bool(record["same_day_close_blocked"]),
            delayed_until_day_index=int(record["delayed_until_day_index"]),
            reason_codes=[str(value) for value in record["reason_codes"]],
            exposure_effect=dict(record["exposure_effect"]),
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            decision_hash=str(record.get("decision_hash", "")),
        )


def portfolio_rotation_decision_hash(decision: PortfolioRotationDecision) -> str:
    payload = decision.to_dict()
    payload["decision_hash"] = ""
    return stable_portfolio_hash(payload)

