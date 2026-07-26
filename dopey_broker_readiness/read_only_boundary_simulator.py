"""Fixture-only read-only boundary simulator for future broker-facing requests."""
from __future__ import annotations

from .broker_readiness_models import ReadOnlyBoundarySimulation, make_boundary_simulation


READ_ONLY_REQUESTS: tuple[tuple[str, str, str], ...] = (
    ("broker_capability_discovery", "discover_broker_capabilities", "fixture_only_read"),
    ("account_metadata_read", "read_account_metadata", "fixture_only_read"),
    ("option_chain_read", "read_option_chain", "fixture_only_read"),
    ("option_quote_read", "read_option_quote", "fixture_only_read"),
    ("position_read", "read_option_position", "fixture_only_read"),
    ("order_status_read", "read_order_status", "fixture_only_read"),
    ("order_review_simulated", "review_option_order_simulated", "fixture_only_not_broker_review"),
)

BLOCKED_REQUESTS: tuple[tuple[str, str, str], ...] = (
    ("order_place_blocked", "place_option_order_blocked", "order_placement_blocked"),
    ("order_cancel_blocked", "cancel_order_blocked", "order_cancel_blocked"),
    ("credential_request_blocked", "request_credentials_blocked", "credential_request_blocked"),
    ("credential_request_blocked", "read_env_blocked", "env_access_blocked"),
    ("scheduler_request_blocked", "create_scheduler_blocked", "scheduler_request_blocked"),
    ("network_request_blocked", "network_market_data_blocked", "network_request_blocked"),
    ("live_execution_blocked", "live_execution_blocked", "live_execution_blocked"),
    ("broker_capability_discovery", "robinhood_path_before_approval_blocked", "manual_approval_required"),
    ("broker_capability_discovery", "broker_integration_before_approval_blocked", "manual_approval_required"),
    ("account_metadata_read", "real_account_balance_read_blocked", "real_sizing_blocked"),
    ("account_metadata_read", "buying_power_read_blocked", "real_sizing_blocked"),
    ("order_review_simulated", "live_order_review_against_broker_blocked", "broker_review_blocked"),
    ("live_execution_blocked", "real_sizing_logic_blocked", "real_sizing_blocked"),
    ("network_request_blocked", "market_data_scrape_blocked", "network_request_blocked"),
    ("scheduler_request_blocked", "auto_live_migration_scheduler_blocked", "scheduler_request_blocked"),
    ("credential_request_blocked", "credential_setup_before_approval_blocked", "credential_request_blocked"),
    ("network_request_blocked", "network_option_quote_before_approval_blocked", "network_request_blocked"),
)


def run_read_only_boundary_simulations() -> list[ReadOnlyBoundarySimulation]:
    simulations: list[ReadOnlyBoundarySimulation] = []
    for index, (boundary_type, request_type, reason) in enumerate(READ_ONLY_REQUESTS, start=1):
        simulations.append(make_boundary_simulation(
            f"broker-readonly-sim-{index:03d}",
            boundary_type,
            request_type,
            True,
            False,
            request_type == "discover_broker_capabilities",
            [reason, "paper_only", "live_blocked", "no_broker_connection"],
        ))
    offset = len(simulations)
    for index, (boundary_type, request_type, reason) in enumerate(BLOCKED_REQUESTS, start=1):
        simulations.append(make_boundary_simulation(
            f"broker-boundary-block-{offset + index:03d}",
            boundary_type,
            request_type,
            False,
            True,
            "approval" in request_type or "robinhood" in request_type or "integration" in request_type,
            [reason, "blocked_before_broker", "paper_only", "live_blocked"],
        ))
    return simulations
