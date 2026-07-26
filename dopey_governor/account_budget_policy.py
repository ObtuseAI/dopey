"""Dopey account budget policy: paper budget approval (recommend-only, no funded account).

DOPEY-native stub. Approves paper-budget allocations only; never touches a funded account.
"""
from __future__ import annotations


class AccountBudgetPolicy:
    def __init__(self, paper_budget: float = 100000.0, max_position_fraction: float = 0.05):
        self.paper_budget = paper_budget
        self.max_position_fraction = max_position_fraction

    def approves(self, notional: float) -> dict:
        max_alloc = self.paper_budget * self.max_position_fraction
        ok = notional <= max_alloc and notional > 0
        return {
            "approved": bool(ok),
            "paper": True,
            "notional": notional,
            "max_alloc": round(max_alloc, 6),
            "reason": "within_paper_budget" if ok else "exceeds_paper_budget_or_nonpositive",
        }
