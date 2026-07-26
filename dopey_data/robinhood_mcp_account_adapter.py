"""Dopey Robinhood MCP account adapter: DISCOVERY-ONLY stub (no creds, no private API, no exec).

DOPEY-native. In the first pass the Robinhood path is discovery-only via the official MCP
interface. No credentials, no unofficial Robinhood private API, and no order placement. The
adapter reports unknown/disabled options-exec capability unless a future explicit live mode
discovers otherwise.
"""
from __future__ import annotations

from .source_scorecard import SourceScorecard


class RobinhoodMCPAccountAdapter:
    PLANNED_USE = "Account + tool discovery only; no order placement in first pass"

    def __init__(self, allow_unofficial_api: bool = False):
        if allow_unofficial_api:
            raise ValueError("allow_unofficial_robinhood_api must be false in the first pass")
        self.allow_unofficial_api = False
        self.scorecard = SourceScorecard(
            source_id="robinhood_mcp",
            authority=0.7,
            freshness=0.7,
            license_class="OFFICIAL_REFERENCE",
            research_only=True,
            credentialed=False,
            notes="discovery-only via official MCP; no private API; no creds; no order placement",
        )

    def discover_tools(self) -> dict:
        """Return a discovery-only capability report. No creds, no order placement."""
        return {
            "source_id": "robinhood_mcp",
            "discovery_only": True,
            "tools_discovered": [],
            "options_exec_supported": False,
            "options_exec_known": False,
            "account_snapshot_available": False,
            "allow_unofficial_api": False,
            "order_placement_allowed": False,
            "note": "Discovery-only in first pass. Options exec defaults to disabled/unknown.",
        }

    def get_account_snapshot(self) -> dict:
        return {"ok": False, "reason": "discovery-only in first pass; no account snapshot"}

    def get_option_chain(self, _symbol: str) -> dict:
        return {"ok": False, "reason": "discovery-only in first pass; no chain fetch"}

    def place_order(self, _intent) -> dict:
        from dopey_execution.errors import LiveTradingDisabledError
        raise LiveTradingDisabledError(
            "Robinhood MCP adapter is discovery-only in the first pass; order placement disabled by default")
