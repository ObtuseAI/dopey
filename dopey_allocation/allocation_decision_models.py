"""Paper allocation decision models."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .proof_weighted_allocation_models import stable_allocation_hash


ALLOWED_ALLOCATION_DECISIONS: frozenset[str] = frozenset({
    "allocate_paper",
    "allocate_paper_throttled",
    "allocate_paper_shadow_only",
    "reserve_for_delayed_rotation",
    "watchlist_only",
    "needs_more_fixture_coverage",
    "reject_no_trade",
    "reject_policy_violation",
    "reject_risk_excess",
    "reject_liquidity",
    "reject_no_day_trade_constraint",
    "reject_live_path",
})

ALLOWED_ALLOCATION_TIERS: frozenset[str] = frozenset({
    "none",
    "watchlist",
    "paper_shadow",
    "small_paper",
    "standard_paper",
    "aggressive_paper_capped",
})


@dataclass(frozen=True)
class PaperAllocationDecision:
    allocation_id: str
    opportunity_id: str
    decision: str
    paper_attention_weight: float
    paper_premium_risk_units: float
    max_paper_contract_units: int
    allocation_tier: str
    risk_throttle: str
    block_reason_codes: list[str]
    proof_reason_codes: list[str]
    constraint_reason_codes: list[str]
    allocator_tags: list[str]
    requires_more_fixture_coverage: list[str]
    paper_only: bool
    live_blocked: bool
    decision_hash: str

    def __post_init__(self) -> None:
        _validate_decision(self)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "PaperAllocationDecision":
        return cls(
            allocation_id=str(record["allocation_id"]),
            opportunity_id=str(record["opportunity_id"]),
            decision=str(record["decision"]),
            paper_attention_weight=float(record["paper_attention_weight"]),
            paper_premium_risk_units=float(record["paper_premium_risk_units"]),
            max_paper_contract_units=int(record["max_paper_contract_units"]),
            allocation_tier=str(record["allocation_tier"]),
            risk_throttle=str(record["risk_throttle"]),
            block_reason_codes=[str(value) for value in record["block_reason_codes"]],
            proof_reason_codes=[str(value) for value in record["proof_reason_codes"]],
            constraint_reason_codes=[str(value) for value in record["constraint_reason_codes"]],
            allocator_tags=[str(value) for value in record["allocator_tags"]],
            requires_more_fixture_coverage=[str(value) for value in record["requires_more_fixture_coverage"]],
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            decision_hash=str(record.get("decision_hash", "")),
        )


def paper_allocation_decision_hash(decision: PaperAllocationDecision) -> str:
    payload = decision.to_dict()
    payload["decision_hash"] = ""
    return stable_allocation_hash(payload)


def _validate_decision(decision: PaperAllocationDecision) -> None:
    if decision.decision not in ALLOWED_ALLOCATION_DECISIONS:
        raise ValueError(f"unsupported allocation decision: {decision.decision}")
    if decision.allocation_tier not in ALLOWED_ALLOCATION_TIERS:
        raise ValueError(f"unsupported allocation tier: {decision.allocation_tier}")
    if decision.paper_attention_weight < 0.0:
        raise ValueError("paper_attention_weight must be non-negative")
    if decision.paper_premium_risk_units < 0.0:
        raise ValueError("paper_premium_risk_units must be non-negative")
    if decision.max_paper_contract_units < 0:
        raise ValueError("max_paper_contract_units must be non-negative")
    if decision.paper_only is not True or decision.live_blocked is not True:
        raise ValueError("paper allocation decision must be paper_only and live_blocked")
    encoded = json.dumps(decision.to_dict(), sort_keys=True, ensure_ascii=False).lower()
    if any(token in encoded for token in {"dollar", "buying_power", "account_balance", "usd", "$"}):
        raise ValueError("paper allocation decision must not contain real capital sizing references")
