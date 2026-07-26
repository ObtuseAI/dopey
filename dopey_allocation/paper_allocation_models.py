"""Paper allocation plan models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .proof_weighted_allocation_models import stable_allocation_hash


@dataclass(frozen=True)
class PaperAllocationPlan:
    plan_id: str
    source_run_ids: list[str]
    opportunity_count: int
    allocated_count: int
    throttled_count: int
    shadow_only_count: int
    delayed_rotation_count: int
    watchlist_count: int
    rejected_count: int
    total_paper_attention_weight: float
    total_paper_premium_risk_units: float
    allocation_by_strategy_type: dict[str, float]
    allocation_by_underlying_family: dict[str, float]
    allocation_by_regime_family: dict[str, float]
    allocation_by_option_type: dict[str, float]
    allocation_by_lifecycle: dict[str, float]
    constraint_summary: dict[str, Any]
    risk_summary: dict[str, Any]
    proof_summary: dict[str, Any]
    paper_only: bool
    live_blocked: bool
    plan_hash: str

    def __post_init__(self) -> None:
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("paper allocation plan must be paper_only and live_blocked")
        if self.total_paper_attention_weight < 0.0 or self.total_paper_premium_risk_units < 0.0:
            raise ValueError("paper allocation plan totals must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "PaperAllocationPlan":
        return cls(
            plan_id=str(record["plan_id"]),
            source_run_ids=[str(value) for value in record["source_run_ids"]],
            opportunity_count=int(record["opportunity_count"]),
            allocated_count=int(record["allocated_count"]),
            throttled_count=int(record["throttled_count"]),
            shadow_only_count=int(record["shadow_only_count"]),
            delayed_rotation_count=int(record["delayed_rotation_count"]),
            watchlist_count=int(record["watchlist_count"]),
            rejected_count=int(record["rejected_count"]),
            total_paper_attention_weight=float(record["total_paper_attention_weight"]),
            total_paper_premium_risk_units=float(record["total_paper_premium_risk_units"]),
            allocation_by_strategy_type={str(key): float(value) for key, value in record["allocation_by_strategy_type"].items()},
            allocation_by_underlying_family={str(key): float(value) for key, value in record["allocation_by_underlying_family"].items()},
            allocation_by_regime_family={str(key): float(value) for key, value in record["allocation_by_regime_family"].items()},
            allocation_by_option_type={str(key): float(value) for key, value in record["allocation_by_option_type"].items()},
            allocation_by_lifecycle={str(key): float(value) for key, value in record["allocation_by_lifecycle"].items()},
            constraint_summary=dict(record["constraint_summary"]),
            risk_summary=dict(record["risk_summary"]),
            proof_summary=dict(record["proof_summary"]),
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            plan_hash=str(record.get("plan_hash", "")),
        )


def paper_allocation_plan_hash(plan: PaperAllocationPlan) -> str:
    payload = plan.to_dict()
    payload["plan_hash"] = ""
    return stable_allocation_hash(payload)
