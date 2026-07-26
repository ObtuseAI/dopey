"""Dopey execution intent: the order-intent dataclass (stdlib only, no pydantic).

DOPEY-native. ExecutionIntent is the ONLY object that may cross into the execution layer. It
defaults to live_allowed=false and defined_risk=true. No intent may place a live order;
the LiveOrderGate permanently denies every live request.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class ExecutionIntent:
    intent_id: str
    symbol: str
    structure: str              # e.g. "vertical", "single"
    legs: list[dict] = field(default_factory=list)
    quantity: int = 1
    defined_risk: bool = True
    live_allowed: bool = False  # Permanent research-only invariant
    tif: str = "DAY"
    paper: bool = True          # DEFAULT: paper only
    # ---- additive pipeline fields (defaults keep existing constructors working) ----
    broker_preference: str = "paper"
    strategy_id: str = ""
    max_loss: float = 0.0
    target_profit: float = 0.0
    invalidation_rule: str = ""
    proof_score: float = 0.0
    aggression_tier: str = ""
    # ---- active-trading-policy lifecycle fields (restored: the dataclass lost
    # them in the branch-switch file loss while their consumers - account_ledger,
    # position_lifecycle, the lifecycle paper-broker adapter, active_policy_audit -
    # kept using them). Defaults are fail-closed: an intent that does not
    # explicitly declare an order_action / approvals is REJECTED by the ledger
    # validators, never assumed approved.
    order_action: str = ""
    trade_date: str = ""
    position_id: str = ""
    related_open_position_id: str = ""
    lifecycle_state: str = ""
    zero_dte: bool = False
    active_policy_required: bool = False
    liquidity_approved: bool = False
    risk_cap_approved: bool = False
    reason_code: str = ""
    zero_dte_risk_decision: dict = field(default_factory=dict)
    zero_dte_replay_feedback: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ExecutionIntent":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def validate(self) -> list[str]:
        """Return a list of validation errors ([] == valid)."""
        errs = []
        if not self.intent_id:
            errs.append("missing intent_id")
        if not self.symbol:
            errs.append("missing symbol")
        if not self.legs:
            errs.append("missing legs")
        if self.quantity <= 0:
            errs.append("quantity must be positive")
        if not self.defined_risk:
            errs.append("undefined-risk structures are blocked by default (defined_risk must be true)")
        if self.live_allowed:
            errs.append("live_allowed must be false (live trading disabled by default)")
        if "paper" not in self.broker_preference.lower():
            errs.append("broker_preference must include 'paper'")
        return errs
