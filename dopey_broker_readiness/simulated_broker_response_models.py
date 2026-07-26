"""Builders for deterministic simulated broker capability responses."""
from __future__ import annotations

from .dry_run_detector_models import (
    SimulatedBrokerCapabilityResponse,
    simulated_response_hash,
)
from .dry_run_schema_models import forbidden_shape_library, read_only_shape_library


def make_simulated_response(
    response_id: str,
    simulated_broker_name: str,
    capability_family: str,
    capability_name: str,
    read_only_shape_available: bool,
    write_or_execute_shape_blocked: bool,
    simulated_schema: dict,
    forbidden_fields: list[str],
    reason_codes: list[str],
) -> SimulatedBrokerCapabilityResponse:
    seed = SimulatedBrokerCapabilityResponse(
        response_id=response_id,
        simulated_broker_name=simulated_broker_name,
        capability_family=capability_family,
        capability_name=capability_name,
        read_only_shape_available=read_only_shape_available,
        write_or_execute_shape_blocked=write_or_execute_shape_blocked,
        requires_manual_approval=True,
        simulated_schema=simulated_schema,
        forbidden_fields=forbidden_fields,
        reason_codes=reason_codes,
        paper_only=True,
        live_blocked=True,
        response_hash="",
    )
    return SimulatedBrokerCapabilityResponse(**{**seed.to_dict(), "response_hash": simulated_response_hash(seed)})


def build_base_simulated_capability_responses() -> list[SimulatedBrokerCapabilityResponse]:
    shapes = read_only_shape_library()
    forbidden = forbidden_shape_library()
    return [
        make_simulated_response("sim-response-001", "SIMULATED_ROBINHOOD_AGENTIC_OPTIONS", "capability_discovery", "read_only_tool_inventory", True, True, shapes["capability_discovery"], [], ["fixture_only_shape"]),
        make_simulated_response("sim-response-002", "SIMULATED_GENERIC_OPTIONS_BROKER", "account_metadata_shape", "account_metadata_shape_only", True, True, shapes["account_metadata_shape"], forbidden["real_sizing_fields"]["blocked_fields"], ["no_account_balance_values"]),
        make_simulated_response("sim-response-003", "SIMULATED_ROBINHOOD_AGENTIC_OPTIONS", "option_chain_shape", "option_chain_schema_only", True, True, shapes["option_chain_shape"], [], ["no_real_market_data"]),
        make_simulated_response("sim-response-004", "SIMULATED_GENERIC_OPTIONS_BROKER", "option_quote_shape", "option_quote_schema_only", True, True, shapes["option_quote_shape"], forbidden["network_fields"]["blocked_fields"], ["quote_shape_no_fetch"]),
        make_simulated_response("sim-response-005", "SIMULATED_ROBINHOOD_AGENTIC_OPTIONS", "option_position_shape", "option_position_schema_only", True, True, shapes["option_position_shape"], forbidden["broker_connection_fields"]["blocked_fields"], ["position_shape_no_account_access"]),
        make_simulated_response("sim-response-006", "SIMULATED_GENERIC_OPTIONS_BROKER", "option_order_status_shape", "order_status_schema_only", True, True, shapes["option_order_status_shape"], ["real_order_id"], ["fixture_order_id_only"]),
        make_simulated_response("sim-response-007", "SIMULATED_ROBINHOOD_AGENTIC_OPTIONS", "option_order_review_shape_simulated", "simulated_order_review_shape_only", True, True, shapes["option_order_review_shape_simulated"], forbidden["live_order_fields"]["blocked_fields"], ["simulated_review_no_live_review"]),
        make_simulated_response("sim-response-008", "SIMULATED_GENERIC_OPTIONS_BROKER", "order_placement_block", "order_placement_blocked", False, True, {"shape_id": "blocked-order-placement", "fixture_only": True, "write_execute_blocked": True}, ["order_payload", "live_execution"], ["order_placement_forbidden"]),
        make_simulated_response("sim-response-009", "SIMULATED_ROBINHOOD_AGENTIC_OPTIONS", "order_cancellation_block", "order_cancellation_blocked", False, True, {"shape_id": "blocked-order-cancellation", "fixture_only": True, "write_execute_blocked": True}, ["cancel_payload", "real_order_id"], ["order_cancellation_forbidden"]),
        make_simulated_response("sim-response-010", "SIMULATED_GENERIC_OPTIONS_BROKER", "credential_block", "credential_access_blocked", False, True, {"shape_id": "blocked-credentials", "fixture_only": True}, forbidden["credential_fields"]["blocked_fields"], ["credentials_forbidden"]),
        make_simulated_response("sim-response-011", "SIMULATED_ROBINHOOD_AGENTIC_OPTIONS", "scheduler_block", "scheduler_creation_blocked", False, True, {"shape_id": "blocked-scheduler", "fixture_only": True}, forbidden["scheduler_fields"]["blocked_fields"], ["scheduler_forbidden"]),
        make_simulated_response("sim-response-012", "SIMULATED_GENERIC_OPTIONS_BROKER", "live_execution_block", "live_execution_blocked", False, True, {"shape_id": "blocked-live-execution", "fixture_only": True}, ["live_execution", "broker_write", "broker_execute"], ["live_execution_forbidden"]),
    ]
