"""Dopey trade permission kernel: aggregates gates into a single permission verdict.

DOPEY-native. Combines the LiveOrderGate + capability + budget into one verdict. In the default
research-only config it NEVER permits a live order. First-pass tests rely on this.
"""
from __future__ import annotations

from .live_order_gate import LiveOrderGate, GateConfig


class TradePermissionKernel:
    def __init__(self, gate: LiveOrderGate | None = None):
        self.gate = gate or LiveOrderGate(GateConfig())

    def request_live(self, intent: dict, capability: dict, proof: dict, budget_decision: dict) -> dict:
        verdict = self.gate.evaluate(intent=intent, capability=capability, proof=proof,
                                     budget_decision=budget_decision)
        verdict["kernel"] = "trade_permission"
        return verdict

    def request_paper(self, intent: dict) -> dict:
        # paper requests are allowed by default (paper_trading_enabled), but never live
        if intent.get("live_allowed", False):
            return {"allowed": False, "reasons": ["paper request carries live_allowed=true"],
                    "kernel": "trade_permission"}
        return {"allowed": True, "paper": True, "kernel": "trade_permission"}
