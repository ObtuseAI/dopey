"""Read-only broker capability detector that never grants live authority."""
from __future__ import annotations


class BrokerCapabilityDetector:
    def __init__(self):
        self._discovered: dict[str, dict] = {}

    def detect(self, broker_capabilities: dict, requested_structure: str,
               allow_live: bool = False) -> dict:
        """Return a capability decision. Defaults to disabled/unknown for options exec."""
        broker = broker_capabilities.get("broker", "unknown")
        options_supported = bool(broker_capabilities.get("options_exec_supported", False))
        known = bool(broker_capabilities.get("options_exec_known", False))
        supports_structure = requested_structure in broker_capabilities.get("supported_structures", [])
        live = False

        # Discovery may describe paper features, but it cannot establish live authority.
        if broker == "robinhood_mcp":
            options_supported = False
        del allow_live

        decision = {
            "broker": broker,
            "options_exec_supported": options_supported,
            "options_exec_known": known,
            "supports_structure": supports_structure,
            "broker_live": live,
            "live_allowed": False,  # detector never grants live; the LiveOrderGate decides
            "requested_structure": requested_structure,
        }
        self._discovered[broker] = decision
        return decision

    def last_decision(self, broker: str) -> dict | None:
        return self._discovered.get(broker)
