"""Dopey Robinhood MCP adapter: DISCOVERY-ONLY broker stub (no creds, no private API, no exec).

DOPEY-native. Wraps the Robinhood MCP account adapter under the BrokerInterface contract.
discover_tools() is the only supported action; place_order() always raises
LiveTradingDisabledError. No constructor flag can unlock order authority.
"""
from __future__ import annotations

from .broker_interface import BrokerInterface
from .execution_intent import ExecutionIntent
from .errors import LiveTradingDisabledError
from .broker_capability_detector import BrokerCapabilityDetector


class RobinhoodMCPAdapter(BrokerInterface):
    def __init__(self, allow_unofficial_api: bool = False, live_enabled: bool = False):
        if allow_unofficial_api:
            raise ValueError("allow_unofficial_robinhood_api must be false")
        if live_enabled:
            raise ValueError("live_enabled cannot be true in the DOPEY research repository")
        from dopey_data.robinhood_mcp_account_adapter import RobinhoodMCPAccountAdapter
        self.account = RobinhoodMCPAccountAdapter(allow_unofficial_api=False)
        self.live_enabled = False
        self.detector = BrokerCapabilityDetector()
        self._tools = None

    def discover_tools(self) -> dict:
        self._tools = self.account.discover_tools()
        return self._tools

    def get_capabilities(self) -> dict:
        if self._tools is None:
            self._tools = self.discover_tools()
        return self.detector.detect(
            {
                "broker": "robinhood_mcp",
                "options_exec_supported": self._tools.get("options_exec_supported", False),
                "options_exec_known": self._tools.get("options_exec_known", False),
                "supported_structures": [],
                "live": False,
            },
            requested_structure="",
            allow_live=False,
        )

    def get_account_snapshot(self) -> dict:
        return self.account.get_account_snapshot()

    def get_option_chain(self, symbol: str) -> dict:
        return self.account.get_option_chain(symbol)

    def preview_order(self, intent: ExecutionIntent) -> dict:
        if intent.live_allowed:
            return {"preview": False, "reason": "live authority is permanently denied", "live_enabled": False}
        return {"preview": True, "paper": True, "discovery_only": True, "live_enabled": False}

    def cancel_order(self, order_id: str) -> dict:
        return {"ok": False, "order_id": order_id, "reason": "discovery-only in first pass; no order management"}

    def place_order(self, intent: ExecutionIntent) -> dict:
        del intent
        raise LiveTradingDisabledError(
            "Robinhood MCP adapter is permanently discovery-only; live order placement is absent"
        )
