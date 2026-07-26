"""Fixture-only broker capability records; no broker is contacted."""
from __future__ import annotations

from .broker_readiness_models import BrokerCapabilityFixture, make_capability_fixture


def build_broker_capability_fixtures() -> list[BrokerCapabilityFixture]:
    definitions = [
        ("SIMULATED_ROBINHOOD_AGENTIC_OPTIONS", "capability_discovery", "discover_options_capabilities", True, True, False, True, False, True),
        ("SIMULATED_ROBINHOOD_AGENTIC_OPTIONS", "option_market_data", "read_option_chain_fixture", True, True, False, True, False, True),
        ("SIMULATED_ROBINHOOD_AGENTIC_OPTIONS", "option_market_data", "read_option_quote_fixture", True, True, False, True, False, True),
        ("SIMULATED_ROBINHOOD_AGENTIC_OPTIONS", "positions", "read_option_position_fixture", True, True, False, True, False, True),
        ("SIMULATED_ROBINHOOD_AGENTIC_OPTIONS", "orders", "place_option_order", False, False, True, False, True, True),
        ("SIMULATED_ROBINHOOD_AGENTIC_OPTIONS", "orders", "cancel_order", False, False, True, False, True, True),
        ("SIMULATED_BROKER_GENERIC_OPTIONS", "credentials", "request_credentials", False, False, True, False, True, True),
        ("SIMULATED_BROKER_GENERIC_OPTIONS", "scheduler", "create_live_scheduler", False, False, True, False, True, True),
        ("SIMULATED_BROKER_GENERIC_OPTIONS", "network", "network_market_data", False, False, True, False, True, True),
        ("SIMULATED_BROKER_GENERIC_OPTIONS", "sizing", "read_buying_power", False, False, True, False, True, True),
        ("SIMULATED_BROKER_GENERIC_OPTIONS", "sizing", "read_real_account_balance", False, False, True, False, True, True),
        ("SIMULATED_BROKER_GENERIC_OPTIONS", "execution", "live_execution", False, False, True, False, True, True),
    ]
    return [
        make_capability_fixture(
            f"broker-capability-fixture-{index:03d}",
            broker_name,
            family,
            capability,
            supported,
            read_only,
            write_or_execute,
            allowed_now,
            blocked_now,
            manual_approval,
            ["fixture_only", "paper_only", "live_blocked", "no_real_broker_connection"],
        )
        for index, (broker_name, family, capability, supported, read_only, write_or_execute, allowed_now, blocked_now, manual_approval)
        in enumerate(definitions, start=1)
    ]
