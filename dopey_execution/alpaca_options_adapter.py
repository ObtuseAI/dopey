"""Dopey Alpaca options adapter: paper/sandbox-ready broker stub (no creds in first pass)."""
from __future__ import annotations

from .broker_interface import BrokerInterface
from .execution_intent import ExecutionIntent
from .errors import LiveTradingDisabledError


class AlpacaOptionsAdapter(BrokerInterface):
    def __init__(self, live_enabled: bool = False):
        if live_enabled:
            raise ValueError("live_enabled cannot be true in the DOPEY research repository")
        self.live_enabled = False

    def get_capabilities(self) -> dict:
        return {
            "broker": "alpaca_options",
            "options_exec_supported": True,
            "options_exec_known": True,
            "supported_structures": ["single", "vertical"],
            "live": False,
        }

    def get_account_snapshot(self) -> dict:
        return {"broker": "alpaca_options", "funded": False, "cash": 0.0, "positions": [], "paper": True}

    def get_option_chain(self, symbol: str) -> dict:
        return {"ok": False, "reason": "no network in first pass; paper/sandbox stub", "symbol": symbol}

    def preview_order(self, intent: ExecutionIntent) -> dict:
        return {"preview": True, "paper": True, "valid": not intent.validate(), "errors": intent.validate()}

    def place_order(self, intent: ExecutionIntent) -> dict:
        if intent.live_allowed and not self.live_enabled:
            raise LiveTradingDisabledError("Alpaca adapter is paper/sandbox-only in the first pass")
        if intent.live_allowed:
            raise LiveTradingDisabledError("live trading not enabled in first pass")
        return {"ok": True, "order_id": "alpaca-paper-stub", "paper": True, "status": "simulated_paper_filled"}

    def cancel_order(self, order_id: str) -> dict:
        return {"ok": True, "order_id": order_id, "paper": True}
