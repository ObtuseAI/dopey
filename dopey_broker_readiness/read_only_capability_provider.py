"""Read-only capability providers for detector fixtures and approved stubs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .read_only_detector_models import ReadOnlyCapabilityRecord, read_only_capability_record_hash


FORBIDDEN_SCHEMA_FIELDS: list[str] = [
    "account_balance",
    "buying_power",
    "credential",
    "token",
    "api_key",
    "place_order",
    "cancel_order",
    "review_live_order",
    "exercise_option",
    "assign_option",
    "real_sizing",
]


class ReadOnlyCapabilityProvider(Protocol):
    provider_type: str

    def list_capabilities(self) -> list[ReadOnlyCapabilityRecord]:
        raise NotImplementedError

    def list_read_only_shapes(self) -> list[ReadOnlyCapabilityRecord]:
        raise NotImplementedError

    def list_blocked_write_execute_shapes(self) -> list[ReadOnlyCapabilityRecord]:
        raise NotImplementedError

    def health_check_read_only_boundary(self) -> dict[str, bool | str]:
        raise NotImplementedError


def _record(
    capability_id: str,
    broker_name: str,
    capability_family: str,
    capability_name: str,
    read_only: bool,
    write_or_execute: bool,
    available: bool,
    unavailable_reason: str,
    schema_shape: dict[str, str | list[str] | bool],
    allowed_now: bool,
    blocked_now: bool,
    reason_codes: list[str],
) -> ReadOnlyCapabilityRecord:
    seed = ReadOnlyCapabilityRecord(
        capability_id=capability_id,
        broker_name=broker_name,
        capability_family=capability_family,
        capability_name=capability_name,
        read_only=read_only,
        write_or_execute=write_or_execute,
        available=available,
        unavailable_reason=unavailable_reason,
        schema_shape=dict(schema_shape),
        forbidden_fields=FORBIDDEN_SCHEMA_FIELDS,
        allowed_now=allowed_now,
        blocked_now=blocked_now,
        reason_codes=sorted(set(reason_codes)),
        paper_only=True,
        live_blocked=True,
        record_hash="",
    )
    return ReadOnlyCapabilityRecord(**{**seed.to_dict(), "record_hash": read_only_capability_record_hash(seed)})


@dataclass(frozen=True)
class FixtureOnlyCapabilityProvider:
    provider_type: str = "fixture_only"
    broker_name: str = "FIXTURE_ONLY_READ_ONLY_OPTIONS"

    def list_capabilities(self) -> list[ReadOnlyCapabilityRecord]:
        return self.list_read_only_shapes() + self.list_blocked_write_execute_shapes()

    def list_read_only_shapes(self) -> list[ReadOnlyCapabilityRecord]:
        specs = [
            ("tool-inventory", "tool_inventory", "read_only_tool_inventory", {"tools": ["list_capabilities", "list_read_only_shapes"], "read_only": True}),
            ("account-metadata-shape", "account_metadata_shape", "account_metadata_shape", {"fields": ["account_id_hash", "broker_label", "capabilities"], "read_only": True}),
            ("option-chain-shape", "option_chain_shape", "option_chain_shape", {"fields": ["symbol", "expiry", "strike", "option_type"], "read_only": True}),
            ("option-quote-shape", "option_quote_shape", "option_quote_shape", {"fields": ["symbol", "bid_shape", "ask_shape", "mid_shape"], "read_only": True}),
            ("option-position-shape", "option_position_shape", "option_position_shape", {"fields": ["symbol", "quantity_shape", "open_close_shape"], "read_only": True}),
            ("option-order-status-shape", "option_order_status_shape", "option_order_status_shape", {"fields": ["order_id_hash", "status_shape", "submitted_at_shape"], "read_only": True}),
            ("option-error-shape", "option_error_shape", "option_error_shape", {"fields": ["error_code", "error_family", "safe_message"], "read_only": True}),
        ]
        return [
            _record(
                capability_id=f"detector-capability-{index:03d}",
                broker_name=self.broker_name,
                capability_family=family,
                capability_name=name,
                read_only=True,
                write_or_execute=False,
                available=True,
                unavailable_reason="",
                schema_shape=shape,
                allowed_now=True,
                blocked_now=False,
                reason_codes=["fixture_read_only_capability_inventory", "no_broker_mutation"],
            )
            for index, (suffix, family, name, shape) in enumerate(specs, start=1)
            for _ in [suffix]
        ]

    def list_blocked_write_execute_shapes(self) -> list[ReadOnlyCapabilityRecord]:
        specs = [
            ("option_order_review_blocked", "live_order_review", "live order review remains blocked"),
            ("option_order_placement_blocked", "place_option_order", "order placement remains blocked"),
            ("option_order_cancellation_blocked", "cancel_option_order", "order cancellation remains blocked"),
            ("credential_block", "credential_request", "credential request remains blocked"),
            ("scheduler_block", "scheduler_creation", "scheduler creation remains blocked"),
            ("live_execution_block", "live_execution", "live execution remains blocked"),
        ]
        return [
            _record(
                capability_id=f"detector-blocked-capability-{index:03d}",
                broker_name=self.broker_name,
                capability_family=family,
                capability_name=name,
                read_only=False,
                write_or_execute=True,
                available=False,
                unavailable_reason=reason,
                schema_shape={"blocked_operation": name, "blocked": True},
                allowed_now=False,
                blocked_now=True,
                reason_codes=["write_execute_forbidden", "blocked_before_broker_mutation", family],
            )
            for index, (family, name, reason) in enumerate(specs, start=1)
        ]

    def health_check_read_only_boundary(self) -> dict[str, bool | str]:
        return {
            "provider_type": self.provider_type,
            "read_only": True,
            "credentials_required": False,
            "credential_access_attempted": False,
            "broker_connection_attempted": False,
            "write_execute_available": False,
            "live_order_tool_available": False,
            "scheduler_available": False,
            "real_sizing_available": False,
            "account_balance_dependency": False,
            "buying_power_dependency": False,
            "broker_mutation_attempted": False,
        }


@dataclass(frozen=True)
class HumanApprovedReadOnlyProviderStub:
    approval_valid: bool
    pre_run_clean: bool
    provider_type: str = "human_approved_read_only_stub"

    def _delegate(self) -> FixtureOnlyCapabilityProvider:
        if self.approval_valid is not True or self.pre_run_clean is not True:
            raise PermissionError("human-approved read-only provider stub requires valid approval and clean pre-run scan")
        return FixtureOnlyCapabilityProvider(provider_type=self.provider_type, broker_name="HUMAN_APPROVED_READ_ONLY_STUB")

    def list_capabilities(self) -> list[ReadOnlyCapabilityRecord]:
        return self._delegate().list_capabilities()

    def list_read_only_shapes(self) -> list[ReadOnlyCapabilityRecord]:
        return self._delegate().list_read_only_shapes()

    def list_blocked_write_execute_shapes(self) -> list[ReadOnlyCapabilityRecord]:
        return self._delegate().list_blocked_write_execute_shapes()

    def health_check_read_only_boundary(self) -> dict[str, bool | str]:
        return self._delegate().health_check_read_only_boundary()


@dataclass(frozen=True)
class DisabledFutureProviderAdapter:
    provider_type: str = "future_provider_adapter_disabled"

    def list_capabilities(self) -> list[ReadOnlyCapabilityRecord]:
        raise PermissionError("future provider adapter is disabled")

    def list_read_only_shapes(self) -> list[ReadOnlyCapabilityRecord]:
        raise PermissionError("future provider adapter is disabled")

    def list_blocked_write_execute_shapes(self) -> list[ReadOnlyCapabilityRecord]:
        raise PermissionError("future provider adapter is disabled")

    def health_check_read_only_boundary(self) -> dict[str, bool | str]:
        return {
            "provider_type": self.provider_type,
            "read_only": False,
            "disabled": True,
            "credentials_required": False,
            "write_execute_available": False,
        }
