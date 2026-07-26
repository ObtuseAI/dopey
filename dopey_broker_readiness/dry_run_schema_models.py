"""Named schema fragments used by the fixture-only detector dry run."""
from __future__ import annotations

from typing import Any


def read_only_shape_library() -> dict[str, dict[str, Any]]:
    return {
        "capability_discovery": {
            "shape_id": "shape-capability-discovery",
            "fields": ["tool_family", "read_only_supported", "write_supported_fixture_blocked"],
            "fixture_only": True,
        },
        "account_metadata_shape": {
            "shape_id": "shape-account-metadata",
            "fields": ["account_type_shape", "permissions_shape", "options_level_shape"],
            "fixture_only": True,
        },
        "option_chain_shape": {
            "shape_id": "shape-option-chain",
            "fields": ["underlier_symbol_shape", "expiry_shape", "strike_shape", "contract_type_shape"],
            "fixture_only": True,
        },
        "option_quote_shape": {
            "shape_id": "shape-option-quote",
            "fields": ["bid_shape", "ask_shape", "mark_shape", "iv_shape", "greeks_shape"],
            "fixture_only": True,
        },
        "option_position_shape": {
            "shape_id": "shape-option-position",
            "fields": ["position_id_fixture", "symbol_shape", "quantity_shape", "open_state_shape"],
            "fixture_only": True,
        },
        "option_order_status_shape": {
            "shape_id": "shape-option-order-status",
            "fields": ["fixture_order_id", "status_shape", "submitted_at_shape", "filled_quantity_shape"],
            "fixture_only": True,
        },
        "option_order_review_shape_simulated": {
            "shape_id": "shape-option-order-review-simulated",
            "fields": ["fixture_review_id", "estimated_cost_shape", "warnings_shape", "write_execute_blocked"],
            "fixture_only": True,
        },
    }


def forbidden_shape_library() -> dict[str, dict[str, Any]]:
    return {
        "credential_fields": {"blocked_fields": ["credential", "credentials", "token", "api_key", ".env"]},
        "broker_connection_fields": {"blocked_fields": ["broker_connection", "connection_handle"]},
        "network_fields": {"blocked_fields": ["network_url", "market_data_url", "real_quote_endpoint"]},
        "live_order_fields": {"blocked_fields": ["live_order_review", "order_payload", "cancel_payload"]},
        "real_sizing_fields": {"blocked_fields": ["account_balance", "buying_power", "real_sizing"]},
        "scheduler_fields": {"blocked_fields": ["scheduler", "autonomous_live_loop"]},
    }
