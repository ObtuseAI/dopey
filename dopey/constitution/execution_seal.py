"""Fail-closed execution seal with no unlock function."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from .invariants import CONSTITUTION_VERSION


class ExecutionSealViolation(PermissionError):
    """Raised when research content crosses the permanent execution boundary."""


FORBIDDEN_CAPABILITY_TERMS: Final[tuple[str, ...]] = (
    "broker",
    "credential",
    "funded_account",
    "live_execution",
    "live_trade",
    "order_builder",
    "order_constructor",
    "order_submit",
    "place_order",
    "cancel_order",
    "replace_order",
    "session_cookie",
)

FORBIDDEN_OUTPUT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "broker_command",
        "credential",
        "live_order",
        "order_payload",
        "order_request",
        "real_capital_dollars",
    }
)

FORBIDDEN_NESTED_KEY_FRAGMENTS: Final[tuple[str, ...]] = (
    "api_key",
    "auth_token",
    "broker_command",
    "broker_connection",
    "broker_credential",
    "credential",
    "funded_account",
    "live_allowed",
    "live_execution",
    "live_order",
    "live_trade",
    "order_builder",
    "order_constructor",
    "order_payload",
    "order_request",
    "order_submit",
    "password",
    "private_key",
    "secret",
    "session_cookie",
)


def execution_seal_state() -> dict[str, bool | str]:
    return {
        "constitution_version": CONSTITUTION_VERSION,
        "paper_only": True,
        "live_blocked": True,
        "broker_authority": False,
        "order_authority": False,
        "order_construction_authority": False,
        "credential_access": False,
        "self_unlock_available": False,
    }


def assert_capabilities_research_only(capabilities: Sequence[str]) -> None:
    violations = sorted(
        capability
        for capability in capabilities
        if any(term in capability.lower() for term in FORBIDDEN_CAPABILITY_TERMS)
    )
    if violations:
        raise ExecutionSealViolation(
            "research capability set crosses the execution seal: "
            f"violations={violations}"
        )


def assert_output_research_only(output: Mapping[str, Any]) -> None:
    assert_no_forbidden_nested_payload(output, "output")
    forbidden_keys = sorted(FORBIDDEN_OUTPUT_KEYS.intersection(output))
    if forbidden_keys:
        raise ExecutionSealViolation(
            "research output contains execution-shaped fields: "
            f"forbidden_keys={forbidden_keys}"
        )
    if output.get("paper_only") is not True:
        raise ExecutionSealViolation("research output requires paper_only=true")
    if output.get("live_blocked") is not True:
        raise ExecutionSealViolation("research output requires live_blocked=true")
    if output.get("action_ready") is True or output.get("live_allowed") is True:
        raise ExecutionSealViolation(
            "research output cannot claim action or live readiness"
        )


def assert_no_forbidden_nested_payload(value: Any, path: str) -> None:
    """Reject execution-shaped or credential-shaped keys at any nesting depth."""

    if isinstance(value, Mapping):
        for raw_key, nested_value in value.items():
            key = str(raw_key).strip().lower()
            if any(fragment in key for fragment in FORBIDDEN_NESTED_KEY_FRAGMENTS):
                # Explicit negative assertions are constitutional evidence, not
                # execution capability. Only the literal boolean false is safe.
                if nested_value is False:
                    continue
                raise ExecutionSealViolation(
                    "research payload contains a forbidden nested key: "
                    f"path={path}.{raw_key}"
                )
            assert_no_forbidden_nested_payload(nested_value, f"{path}.{raw_key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested_value in enumerate(value):
            assert_no_forbidden_nested_payload(nested_value, f"{path}[{index}]")
