"""Robinhood connector with parent-only broker authority and legacy read-only Codex."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Final
from zoneinfo import ZoneInfo

from .control import OFFICIAL_ROBINHOOD_MCP
from .models import (
    AccountSnapshot,
    EQUITY_SNAPSHOT_SOURCE,
    EquityExecutionSnapshot,
    EquityQuoteSnapshot,
    GatewayCancelResult,
    GatewayOrderResult,
    LiveExecutionIntent,
)


MCP_SERVER_NAME: Final[str] = "robinhood-trading"
LOCAL_MODEL_PROVIDER: Final[str] = "ollama"
LOCAL_MODEL_BASE_URL: Final[str] = "http://127.0.0.1:11434/v1"
LOCAL_MODEL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*:"
    r"[a-z0-9][a-z0-9._-]{0,63}$"
)
PRE_SUBMIT_SAFETY_MARGIN_SECONDS: Final[int] = 5
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
DISABLED_CODEX_FEATURES: Final[tuple[str, ...]] = (
    "apps",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "code_mode",
    "computer_use",
    "enable_fanout",
    "enable_mcp_apps",
    "in_app_browser",
    "multi_agent",
    "multi_agent_v2",
    "plugins",
    "remote_plugin",
    "shell_tool",
    "standalone_web_search",
    "tool_suggest",
    "unified_exec",
)
READ_ONLY_ROBINHOOD_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "get_accounts",
        "get_equity_orders",
        "get_equity_positions",
        "get_equity_quotes",
        "get_equity_tradability",
        "get_option_orders",
        "get_option_positions",
        "get_portfolio",
    }
)
DETERMINISTIC_WRITE_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "cancel_equity_order",
        "place_equity_order",
        "review_equity_order",
    }
)
PLACED_ORDER_STATUSES: Final[frozenset[str]] = frozenset(
    {"queued", "pending", "open", "confirmed", "partially_filled", "filled"}
)
RECOGNIZED_ORDER_STATUSES: Final[frozenset[str]] = frozenset(
    {
        *PLACED_ORDER_STATUSES,
        "cancelled",
        "canceled",
        "rejected",
        "expired",
        "failed",
        "voided",
    }
)
ACCOUNT_IDENTIFIER_FIELDS: Final[frozenset[str]] = frozenset(
    {"account_id", "account_number"}
)
ACCOUNT_LABEL_FIELDS: Final[frozenset[str]] = frozenset(
    {"account_label", "account_name", "label", "name", "nickname"}
)
ACCOUNT_TYPE_FIELDS: Final[frozenset[str]] = frozenset(
    {"account_type", "brokerage_account_type"}
)
SYMBOL_FIELDS: Final[frozenset[str]] = frozenset(
    {"symbol", "instrument_symbol", "ticker"}
)
SIDE_FIELDS: Final[frozenset[str]] = frozenset({"side"})
QUANTITY_FIELDS: Final[frozenset[str]] = frozenset(
    {"asset_quantity", "quantity", "share_quantity", "shares"}
)
NOTIONAL_FIELDS: Final[frozenset[str]] = frozenset(
    {"amount", "dollar_amount", "notional", "notional_usd"}
)
LIMIT_PRICE_FIELDS: Final[frozenset[str]] = frozenset({"limit", "limit_price"})
ORDER_TYPE_FIELDS: Final[frozenset[str]] = frozenset({"order_type", "type"})
TIME_IN_FORCE_FIELDS: Final[frozenset[str]] = frozenset(
    {"time_in_force", "timeInForce"}
)
EXTENDED_HOURS_FIELDS: Final[frozenset[str]] = frozenset(
    {"extended_hours", "extendedHours"}
)
ORDER_ARGUMENT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        *ACCOUNT_IDENTIFIER_FIELDS,
        *SYMBOL_FIELDS,
        *SIDE_FIELDS,
        *QUANTITY_FIELDS,
        *NOTIONAL_FIELDS,
        *LIMIT_PRICE_FIELDS,
        *ORDER_TYPE_FIELDS,
        *TIME_IN_FORCE_FIELDS,
        *EXTENDED_HOURS_FIELDS,
    }
)
ORDER_ID_FIELDS: Final[frozenset[str]] = frozenset({"order_id"})
ORDER_STATUS_FIELDS: Final[frozenset[str]] = frozenset({"status", "state"})
CANCEL_ARGUMENT_FIELDS: Final[frozenset[str]] = (
    ACCOUNT_IDENTIFIER_FIELDS | ORDER_ID_FIELDS
)
CANCEL_RESULT_STATUSES: Final[frozenset[str]] = frozenset(
    {
        *RECOGNIZED_ORDER_STATUSES,
        "canceling",
        "cancelling",
        "cancel_requested",
        "not_open",
    }
)
ORDER_HISTORY_LIMIT: Final[int] = 1_000
LOGGER = logging.getLogger(__name__)
Runner = Callable[..., subprocess.CompletedProcess[str]]


class RobinhoodGatewayError(RuntimeError):
    """Raised when the official Robinhood Agentic gateway cannot complete a request."""


class RobinhoodPlacementAmbiguousError(RobinhoodGatewayError):
    """Raised when an attempted placement cannot be proven placed or not placed."""


class RobinhoodPreSubmitGuardError(RobinhoodGatewayError):
    """Raised when authority is denied before the broker place call begins."""


class RobinhoodCancellationAmbiguousError(RobinhoodGatewayError):
    """Raised when an attempted cancellation cannot be proven requested or absent."""


class RobinhoodAuthRequiredError(RobinhoodGatewayError):
    """The MCP server refused the handshake for lack of OAuth - operator must re-login.

    Distinct from generic gateway errors so the cycle can surface the exact
    remediation instead of the misleading "required MCP calls were not
    observed" (the agent genuinely cannot call tools on a server that never
    attached). Non-retryable: burning attempts on an expired OAuth session
    cannot succeed.
    """


class RobinhoodConsentRequiredError(RobinhoodGatewayError):
    """A tool call was cancelled awaiting interactive per-call consent.

    Robinhood's Agentic MCP can require the account holder to approve each
    tool call; in an unattended run there is nobody to approve, so the call
    auto-cancels ("user cancelled MCP tool call"). OAuth is FINE in this state
    - the server attached and the call started. Non-retryable unattended: the
    cycle must be run attended (approving the prompts) or per-call approval
    relaxed in the agentic account / codex client settings.
    """


def consent_remediation() -> str:
    return (
        "Robinhood MCP tool calls are being cancelled awaiting interactive "
        "consent (OAuth itself is valid). Operator remediation: run the live "
        "branch cycle ATTENDED and approve each tool-call prompt in the codex "
        "client, or enable standing tool approval for this server in the codex "
        "/ Robinhood agentic-account settings if offered, then re-run."
    )


# codex rmcp-client stderr signatures. "Auth required" is the auth-specific
# handshake refusal; the other two are attach failures that may be transient
# (network) and stay retryable, but their stderr evidence must reach the error.
MCP_AUTH_REQUIRED_SIGNATURE: Final[str] = "Auth required"
MCP_ATTACH_FAILURE_SIGNATURES: Final[tuple[str, ...]] = (
    "MCP startup failed",
    "handshaking with MCP server failed",
)


def _mcp_attach_failure_kind(stderr_text: str) -> str | None:
    """Classify codex stderr: 'auth_required', 'attach_failure', or None."""
    if MCP_AUTH_REQUIRED_SIGNATURE in stderr_text:
        return "auth_required"
    if any(signature in stderr_text for signature in MCP_ATTACH_FAILURE_SIGNATURES):
        return "attach_failure"
    return None


def reauth_remediation() -> str:
    return (
        "Robinhood MCP OAuth session is missing or expired; codex could not attach "
        f"the '{MCP_SERVER_NAME}' server so no trading tools were available. "
        f"Operator remediation: run `codex mcp login {MCP_SERVER_NAME}` "
        "(interactive browser OAuth), then re-run the cycle."
    )


@dataclass(frozen=True)
class McpToolCallEvidence:
    """Authoritative machine-readable evidence for one completed MCP tool call."""

    call_id: str
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True)
class GatewayEnvelope:
    """Agent normalization plus the independent Codex MCP transcript."""

    payload: dict[str, Any]
    calls: tuple[McpToolCallEvidence, ...]


@dataclass(frozen=True)
class AccountAttestation:
    """In-memory account binding; the identifier is never serialized by DOPEY."""

    account_id: str
    account_label: str
    account_type: str


def _json_object_text(value: str, context: str) -> dict[str, Any] | list[Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise RobinhoodGatewayError(
            f"Robinhood MCP transcript result is not JSON: context={context}, error={error}"
        ) from error
    if not isinstance(parsed, (dict, list)):
        raise RobinhoodGatewayError(
            "Robinhood MCP transcript JSON must be an object or array: "
            f"context={context}, actual={type(parsed).__name__}"
        )
    return parsed


def _mcp_result_value(call: McpToolCallEvidence) -> dict[str, Any] | list[Any]:
    structured = call.result.get("structured_content")
    if isinstance(structured, (dict, list)):
        return structured
    content = call.result.get("content")
    if not isinstance(content, list) or not content:
        raise RobinhoodGatewayError(
            f"Robinhood MCP result lacks structured JSON evidence: tool={call.tool}"
        )
    text_blocks: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            raise RobinhoodGatewayError(
                f"Robinhood MCP result content item must be an object: tool={call.tool}"
            )
        if block.get("type") != "text" or not isinstance(block.get("text"), str):
            raise RobinhoodGatewayError(
                f"Robinhood MCP result content must be JSON text: tool={call.tool}"
            )
        text_blocks.append(str(block["text"]))
    return _json_object_text("".join(text_blocks), f"tool={call.tool}")


def _mcp_transcript(stdout: str) -> tuple[McpToolCallEvidence, ...]:
    started: dict[str, tuple[str, dict[str, Any]]] = {}
    completed: dict[str, McpToolCallEvidence] = {}
    thread_started_count = 0
    turn_completed_count = 0
    for line_number, raw_line in enumerate(stdout.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise RobinhoodGatewayError(
                "Codex JSONL transcript contains invalid JSON: "
                f"line={line_number}, error={error}"
            ) from error
        if not isinstance(event, dict):
            raise RobinhoodGatewayError(
                f"Codex JSONL transcript event must be an object: line={line_number}"
            )
        event_type = event.get("type")
        if event_type == "thread.started":
            thread_started_count += 1
        elif event_type == "turn.completed":
            turn_completed_count += 1
        elif event_type in {"error", "turn.failed"}:
            raise RobinhoodGatewayError(
                f"Codex JSONL transcript contains a terminal error: type={event_type}"
            )
        if event_type not in {"item.started", "item.completed"}:
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            raise RobinhoodGatewayError(
                f"Codex JSONL item event lacks an object item: line={line_number}"
            )
        item_type = item.get("type")
        if item_type == "error":
            raise RobinhoodGatewayError(
                "Codex JSONL transcript reports an item error; tool evidence may be incomplete"
            )
        if item_type != "mcp_tool_call":
            continue
        call_id = str(item.get("id", "")).strip()
        server = str(item.get("server", "")).strip()
        tool = str(item.get("tool", "")).strip()
        arguments = item.get("arguments")
        if not call_id or server != MCP_SERVER_NAME or not tool:
            raise RobinhoodGatewayError(
                "Codex MCP transcript call identity is missing or mismatched"
            )
        if not isinstance(arguments, dict) or not all(
            isinstance(key, str) for key in arguments
        ):
            raise RobinhoodGatewayError(
                f"Codex MCP transcript arguments must be an object: tool={tool}"
            )
        if event_type == "item.started":
            if call_id in started:
                raise RobinhoodGatewayError(
                    f"Codex MCP transcript contains duplicate call start: tool={tool}"
                )
            started[call_id] = (tool, arguments)
            continue
        if item.get("status") != "completed" or item.get("error") is not None:
            error_text = str(item.get("error") or "")
            if "cancel" in error_text.lower():
                raise RobinhoodConsentRequiredError(
                    f"tool={tool}: {consent_remediation()}"
                )
            raise RobinhoodGatewayError(
                f"Codex MCP transcript contains an incomplete or failed call: tool={tool}"
            )
        result = item.get("result")
        if not isinstance(result, dict):
            raise RobinhoodGatewayError(
                f"Codex MCP transcript completed call lacks a result envelope: tool={tool}"
            )
        if call_id in completed:
            raise RobinhoodGatewayError(
                f"Codex MCP transcript contains duplicate call completion: tool={tool}"
            )
        completed[call_id] = McpToolCallEvidence(
            call_id=call_id,
            tool=tool,
            arguments=dict(arguments),
            result=dict(result),
        )
    if thread_started_count != 1 or turn_completed_count != 1:
        raise RobinhoodGatewayError(
            "Codex JSONL transcript lifecycle is incomplete: "
            f"thread_started={thread_started_count}, turn_completed={turn_completed_count}"
        )
    if set(started) != set(completed):
        raise RobinhoodGatewayError(
            "Codex MCP transcript start/completion sets differ; evidence may have been dropped"
        )
    for call_id, evidence in completed.items():
        started_tool, started_arguments = started[call_id]
        if started_tool != evidence.tool or started_arguments != evidence.arguments:
            raise RobinhoodGatewayError(
                f"Codex MCP transcript call mutated between start and completion: tool={evidence.tool}"
            )
    return tuple(completed[call_id] for call_id in started)


def _tool_calls(
    calls: tuple[McpToolCallEvidence, ...],
    tool: str,
) -> tuple[McpToolCallEvidence, ...]:
    return tuple(call for call in calls if call.tool == tool)


def _recursive_field_values(
    value: Any,
    field_names: frozenset[str],
) -> tuple[Any, ...]:
    values: list[Any] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in field_names:
                values.append(nested)
            values.extend(_recursive_field_values(nested, field_names))
    elif isinstance(value, list):
        for nested in value:
            values.extend(_recursive_field_values(nested, field_names))
    return tuple(values)


def _single_string_field(
    value: Any,
    field_names: frozenset[str],
    field_label: str,
) -> str:
    values = _recursive_field_values(value, field_names)
    normalized = {str(item).strip() for item in values if str(item).strip()}
    if len(normalized) != 1:
        raise RobinhoodGatewayError(
            "Robinhood MCP transcript does not expose one unambiguous field: "
            f"field={field_label}, observed_count={len(normalized)}"
        )
    return next(iter(normalized))


def _decimal_value(value: Any, field_label: str) -> Decimal:
    if isinstance(value, bool):
        raise RobinhoodGatewayError(
            f"Robinhood MCP transcript numeric field is boolean: field={field_label}"
        )
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise RobinhoodGatewayError(
            f"Robinhood MCP transcript numeric field is invalid: field={field_label}"
        ) from error
    if not decimal_value.is_finite():
        raise RobinhoodGatewayError(
            f"Robinhood MCP transcript numeric field is not finite: field={field_label}"
        )
    return decimal_value


def _single_decimal_field(
    value: Any,
    field_names: frozenset[str],
    field_label: str,
) -> Decimal:
    values = _recursive_field_values(value, field_names)
    scalar_values = tuple(item for item in values if not isinstance(item, (dict, list)))
    decimals = {_decimal_value(item, field_label) for item in scalar_values}
    if len(decimals) != 1:
        raise RobinhoodGatewayError(
            "Robinhood MCP transcript does not expose one unambiguous numeric field: "
            f"field={field_label}, observed_count={len(decimals)}"
        )
    return next(iter(decimals))


def _account_records(value: Any) -> tuple[dict[str, Any], ...]:
    candidates: list[dict[str, Any]] = []
    if isinstance(value, list):
        if not all(isinstance(item, dict) for item in value):
            raise RobinhoodGatewayError(
                "Robinhood get_accounts result contains a non-object account item"
            )
        candidates.extend(value)
    elif isinstance(value, dict):
        containers = [value]
        data = value.get("data")
        if isinstance(data, dict):
            containers.append(data)
        for container in containers:
            for key in ("accounts", "results"):
                nested = container.get(key)
                if isinstance(nested, list):
                    if not all(isinstance(item, dict) for item in nested):
                        raise RobinhoodGatewayError(
                            "Robinhood get_accounts result contains a non-object account item"
                        )
                    candidates.extend(nested)
    if not candidates:
        raise RobinhoodGatewayError(
            "Robinhood get_accounts result does not expose an account array"
        )
    return tuple(candidates)


def _agentic_account(calls: tuple[McpToolCallEvidence, ...]) -> AccountAttestation:
    account_calls = _tool_calls(calls, "get_accounts")
    if len(account_calls) != 1:
        raise RobinhoodGatewayError(
            "Robinhood account attestation requires exactly one get_accounts call"
        )
    matches: list[AccountAttestation] = []
    for record in _account_records(_mcp_result_value(account_calls[0])):
        labels = {
            str(value).strip()
            for value in _recursive_field_values(record, ACCOUNT_LABEL_FIELDS)
            if str(value).strip()
        }
        if not any("agentic" in label.casefold() for label in labels):
            continue
        account_id = _single_string_field(
            record,
            ACCOUNT_IDENTIFIER_FIELDS,
            "agentic_account_id",
        )
        account_type = _single_string_field(
            record,
            ACCOUNT_TYPE_FIELDS,
            "agentic_account_type",
        )
        label = sorted(
            labels, key=lambda item: ("agentic" not in item.casefold(), item)
        )[0]
        matches.append(
            AccountAttestation(
                account_id=account_id,
                account_label=label,
                account_type=account_type,
            )
        )
    if len(matches) != 1:
        raise RobinhoodGatewayError(
            "Robinhood account attestation requires exactly one labeled Agentic account: "
            f"observed_count={len(matches)}"
        )
    return matches[0]


def _attest_account_scope(
    calls: tuple[McpToolCallEvidence, ...],
    account_scoped_tools: tuple[str, ...],
) -> AccountAttestation:
    account = _agentic_account(calls)
    for tool in account_scoped_tools:
        matching = _tool_calls(calls, tool)
        if len(matching) != 1:
            raise RobinhoodGatewayError(
                f"Robinhood account attestation requires exactly one call: tool={tool}"
            )
        observed_id = _single_string_field(
            matching[0].arguments,
            ACCOUNT_IDENTIFIER_FIELDS,
            f"{tool}_account_id",
        )
        if observed_id != account.account_id:
            raise RobinhoodGatewayError(
                f"Robinhood MCP call is not bound to the labeled Agentic account: tool={tool}"
            )
    return account


def _assert_account_identifier_redacted(
    payload: dict[str, Any],
    account_id: str,
    context: str,
) -> None:
    exposed_fields = _recursive_field_values(payload, ACCOUNT_IDENTIFIER_FIELDS)
    if exposed_fields:
        raise RobinhoodGatewayError(
            f"Robinhood normalized payload exposes an account identifier field: context={context}"
        )
    sensitive_texts: list[str] = []
    for field in ("error", "warnings"):
        value = payload.get(field)
        if isinstance(value, str):
            sensitive_texts.append(value)
        elif isinstance(value, list):
            sensitive_texts.extend(item for item in value if isinstance(item, str))
    if account_id and any(account_id in text for text in sensitive_texts):
        raise RobinhoodGatewayError(
            f"Robinhood normalized payload leaks the Agentic account identifier: context={context}"
        )


def _single_bool_field(
    value: Any,
    field_names: frozenset[str],
    field_label: str,
) -> bool:
    values = _recursive_field_values(value, field_names)
    if not values or not all(type(item) is bool for item in values):
        raise RobinhoodGatewayError(
            "Robinhood MCP transcript does not expose a typed boolean field: "
            f"field={field_label}"
        )
    unique = set(values)
    if len(unique) != 1:
        raise RobinhoodGatewayError(
            "Robinhood MCP transcript exposes conflicting boolean fields: "
            f"field={field_label}"
        )
    return bool(next(iter(unique)))


def _result_items(
    call: McpToolCallEvidence,
    collection_fields: frozenset[str],
    item_label: str,
) -> tuple[dict[str, Any], ...]:
    result_value = _mcp_result_value(call)
    if isinstance(result_value, list):
        raw_items = result_value
    else:
        arrays = tuple(
            value
            for value in _recursive_field_values(result_value, collection_fields)
            if isinstance(value, list)
        )
        if len(arrays) != 1:
            raise RobinhoodGatewayError(
                "Robinhood MCP result does not expose one unambiguous item array: "
                f"item={item_label}, observed_count={len(arrays)}"
            )
        raw_items = arrays[0]
    if not all(isinstance(item, dict) for item in raw_items):
        raise RobinhoodGatewayError(
            f"Robinhood MCP result contains a non-object item: item={item_label}"
        )
    return tuple(dict(item) for item in raw_items)


def _field_values_equal(field: str, normalized: Any, raw: Any) -> bool:
    numeric_fields = {
        "ask_price",
        "average_cost",
        "average_fill_price",
        "bid_price",
        "filled_quantity",
        "fees_usd",
        "last_price",
        "limit_price",
        "market_price",
        "market_value",
        "notional_usd",
        "quantity",
        "strike",
        "unrealized_pnl",
    }
    casefold_fields = {
        "option_type",
        "order_type",
        "side",
        "status",
        "symbol",
        "time_in_force",
    }
    if field in numeric_fields:
        try:
            return _decimal_value(normalized, field) == _decimal_value(raw, field)
        except RobinhoodGatewayError:
            return False
    if field in casefold_fields:
        return str(normalized).strip().casefold() == str(raw).strip().casefold()
    return bool(normalized == raw)


def _bind_normalized_items(
    normalized_items: tuple[dict[str, Any], ...],
    raw_items: tuple[dict[str, Any], ...],
    identity_fields: tuple[str, ...],
    required_fields: tuple[str, ...],
    item_label: str,
) -> None:
    if len(normalized_items) != len(raw_items):
        raise RobinhoodGatewayError(
            "Robinhood normalized item count differs from the MCP response: "
            f"item={item_label}"
        )

    def identity(item: dict[str, Any]) -> tuple[str, ...]:
        values = tuple(
            str(item.get(field, "")).strip().casefold() for field in identity_fields
        )
        if any(not value for value in values):
            raise RobinhoodGatewayError(
                f"Robinhood MCP item identity is incomplete: item={item_label}"
            )
        return values

    raw_by_identity: dict[tuple[str, ...], dict[str, Any]] = {}
    for raw_item in raw_items:
        raw_identity = identity(raw_item)
        if raw_identity in raw_by_identity:
            raise RobinhoodGatewayError(
                f"Robinhood MCP response contains a duplicate item identity: item={item_label}"
            )
        raw_by_identity[raw_identity] = raw_item
    observed_normalized: set[tuple[str, ...]] = set()
    for normalized_item in normalized_items:
        normalized_identity = identity(normalized_item)
        if normalized_identity in observed_normalized:
            raise RobinhoodGatewayError(
                f"Robinhood normalized response contains a duplicate item: item={item_label}"
            )
        observed_normalized.add(normalized_identity)
        matched_raw_item = raw_by_identity.get(normalized_identity)
        if matched_raw_item is None:
            raise RobinhoodGatewayError(
                f"Robinhood normalized item is absent from the MCP response: item={item_label}"
            )
        for field in required_fields:
            if field not in normalized_item or field not in matched_raw_item:
                raise RobinhoodGatewayError(
                    "Robinhood normalized or raw item lacks a required field: "
                    f"item={item_label}, field={field}"
                )
            if not _field_values_equal(
                field,
                normalized_item[field],
                matched_raw_item[field],
            ):
                raise RobinhoodGatewayError(
                    "Robinhood normalized item differs from the MCP response: "
                    f"item={item_label}, field={field}"
                )


def _bind_optional_item_fields(
    normalized_items: tuple[dict[str, Any], ...],
    raw_items: tuple[dict[str, Any], ...],
    identity_field: str,
    optional_fields: tuple[str, ...],
    item_label: str,
) -> None:
    raw_by_identity = {
        str(item.get(identity_field, "")).strip(): item for item in raw_items
    }
    for normalized in normalized_items:
        identity = str(normalized.get(identity_field, "")).strip()
        raw = raw_by_identity.get(identity)
        if raw is None:
            raise RobinhoodGatewayError(
                f"Robinhood optional-field identity is absent: item={item_label}"
            )
        for field in optional_fields:
            normalized_has = field in normalized
            raw_has = field in raw
            if normalized_has is not raw_has:
                raise RobinhoodGatewayError(
                    "Robinhood normalized optional economics differ from MCP evidence: "
                    f"item={item_label}, field={field}"
                )
            if normalized_has and not _field_values_equal(
                field,
                normalized[field],
                raw[field],
            ):
                raise RobinhoodGatewayError(
                    "Robinhood normalized optional economics differ from MCP evidence: "
                    f"item={item_label}, field={field}"
                )


def _attest_order_history_results(
    calls: tuple[McpToolCallEvidence, ...],
) -> tuple[bool, bool]:
    completeness: list[bool] = []
    for tool in ("get_equity_orders", "get_option_orders"):
        matching = _tool_calls(calls, tool)
        if len(matching) != 1:
            raise RobinhoodGatewayError(
                f"Robinhood history attestation requires exactly one call: tool={tool}"
            )
        call = matching[0]
        result_value = _mcp_result_value(call)
        raw_limit = call.arguments.get("limit")
        if (
            isinstance(raw_limit, bool)
            or not isinstance(raw_limit, int)
            or raw_limit != ORDER_HISTORY_LIMIT
        ):
            raise RobinhoodGatewayError(
                "Robinhood history attestation requires the exact bounded "
                f"history limit: tool={tool}, limit={ORDER_HISTORY_LIMIT}"
            )
        items = _result_items(
            call,
            frozenset({"orders", "results"}),
            f"{tool}_history",
        )
        explicit_values = _recursive_field_values(
            result_value,
            frozenset({"history_complete", "order_history_complete"}),
        )
        explicit_complete = (
            _single_bool_field(
                result_value,
                frozenset({"history_complete", "order_history_complete"}),
                f"{tool}_history_complete",
            )
            if explicit_values
            else True
        )
        continuation_values = _recursive_field_values(
            result_value,
            frozenset({"next", "next_cursor"}),
        )
        has_continuation = any(
            value is not None and str(value).strip() for value in continuation_values
        )
        has_filter = any(
            key not in ACCOUNT_IDENTIFIER_FIELDS
            and key != "limit"
            and value is not None
            and str(value).strip()
            for key, value in call.arguments.items()
        )
        completeness.append(
            explicit_complete
            and not has_continuation
            and not has_filter
            and len(items) < ORDER_HISTORY_LIMIT
        )
    return completeness[0], completeness[1]


def _market_date_from_timestamp(value: Any) -> str:
    timestamp = str(value).strip()
    if not timestamp:
        return ""
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        return ""
    return parsed.astimezone(ZoneInfo("America/New_York")).date().isoformat()


def _canonical_raw_broker_item(
    raw_item: dict[str, Any],
    item_label: str,
) -> dict[str, Any]:
    if item_label in {"equity_position", "option_position"}:
        canonical = {
            **raw_item,
            "symbol": raw_item.get("symbol", raw_item.get("chain_symbol", "")),
            "quantity": raw_item.get("quantity", 0.0),
            "average_cost": raw_item.get(
                "average_cost",
                raw_item.get("average_buy_price", raw_item.get("average_price", 0.0)),
            ),
            "market_price": raw_item.get("market_price", 0.0),
            "market_value": raw_item.get("market_value", 0.0),
        }
        if "unrealized_pnl" in raw_item:
            canonical["unrealized_pnl"] = raw_item["unrealized_pnl"]
        if item_label == "option_position":
            canonical["contract_id"] = raw_item.get(
                "contract_id",
                raw_item.get("option_id", raw_item.get("instrument_id", "")),
            )
        return canonical
    if item_label not in {"equity_order", "option_order"}:
        raise ValueError(f"Unsupported broker item label: {item_label}")
    status = str(raw_item.get("status", raw_item.get("state", ""))).strip().lower()
    submitted_at = raw_item.get("submitted_at", raw_item.get("created_at", ""))
    filled_at = raw_item.get("filled_at", "")
    if not filled_at and status in {"filled", "partially_filled"}:
        filled_at = raw_item.get("last_transaction_at", "")
    canonical = {
        **raw_item,
        "order_id": raw_item.get("order_id", raw_item.get("id", "")),
        "symbol": raw_item.get("symbol", raw_item.get("chain_symbol", "")),
        "side": raw_item.get("side", ""),
        "status": status,
        "submitted_at": submitted_at,
        "filled_at": filled_at,
        "filled_quantity": raw_item.get(
            "filled_quantity",
            raw_item.get(
                "cumulative_quantity",
                raw_item.get("processed_quantity", 0.0),
            ),
        ),
        "average_fill_price": raw_item.get(
            "average_fill_price",
            raw_item.get("average_price", 0.0),
        ),
        "market_date": raw_item.get(
            "market_date",
            _market_date_from_timestamp(filled_at or submitted_at),
        ),
    }
    optional_aliases = {
        "order_type": ("order_type", "type"),
        "time_in_force": ("time_in_force", "timeInForce"),
        "limit_price": ("limit_price", "limit", "price"),
        "quantity": ("quantity", "asset_quantity", "share_quantity", "shares"),
        "notional_usd": ("notional_usd", "notional", "amount", "dollar_amount"),
        "fees_usd": ("fees_usd", "fees", "total_fees"),
    }
    for canonical_field, aliases in optional_aliases.items():
        for alias in aliases:
            if alias in raw_item:
                canonical[canonical_field] = raw_item[alias]
                break
    if item_label == "option_order":
        canonical.update(
            {
                "expiry": raw_item.get(
                    "expiry",
                    raw_item.get("expiration_date", ""),
                ),
                "strike": raw_item.get(
                    "strike",
                    raw_item.get("strike_price", 0.0),
                ),
                "option_type": raw_item.get("option_type", ""),
                "contract_id": raw_item.get(
                    "contract_id",
                    raw_item.get("option_id", raw_item.get("instrument_id", "")),
                ),
            }
        )
    return canonical


def _strict_alias_text(
    raw_item: dict[str, Any],
    aliases: tuple[str, ...],
    field_label: str,
) -> str:
    values = [
        str(raw_item[alias]).strip()
        for alias in aliases
        if alias in raw_item and str(raw_item[alias]).strip()
    ]
    normalized = {value for value in values}
    if len(normalized) != 1:
        raise RobinhoodGatewayError(
            "Deterministic Robinhood result has a missing or conflicting "
            f"text field: field={field_label}"
        )
    return next(iter(normalized))


def _strict_alias_number(
    raw_item: dict[str, Any],
    aliases: tuple[str, ...],
    field_label: str,
) -> Any:
    values = [
        raw_item[alias]
        for alias in aliases
        if alias in raw_item and raw_item[alias] is not None
    ]
    if not values:
        raise RobinhoodGatewayError(
            f"Deterministic Robinhood result is missing field={field_label}"
        )
    decimals = {_decimal_value(value, field_label) for value in values}
    if len(decimals) != 1:
        raise RobinhoodGatewayError(
            "Deterministic Robinhood result has conflicting numeric aliases: "
            f"field={field_label}"
        )
    return values[0]


def _strict_parent_position(
    raw_item: dict[str, Any],
    *,
    option: bool,
) -> dict[str, Any]:
    if not isinstance(raw_item, dict):
        raise RobinhoodGatewayError(
            "Deterministic Robinhood position item must be an object"
        )
    canonical: dict[str, Any] = {
        "symbol": _strict_alias_text(
            raw_item,
            ("symbol", "chain_symbol"),
            "position.symbol",
        ),
        "quantity": _strict_alias_number(
            raw_item,
            ("quantity",),
            "position.quantity",
        ),
        "average_cost": _strict_alias_number(
            raw_item,
            ("average_cost", "average_buy_price", "average_price"),
            "position.average_cost",
        ),
        "market_price": _strict_alias_number(
            raw_item,
            ("market_price",),
            "position.market_price",
        ),
        "market_value": _strict_alias_number(
            raw_item,
            ("market_value",),
            "position.market_value",
        ),
        "unrealized_pnl": _strict_alias_number(
            raw_item,
            ("unrealized_pnl",),
            "position.unrealized_pnl",
        ),
    }
    if option:
        canonical["contract_id"] = _strict_alias_text(
            raw_item,
            ("contract_id", "option_id", "instrument_id"),
            "position.contract_id",
        )
    return canonical


def _direct_records_with_fields(
    value: Any,
    required_fields: frozenset[str],
) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if required_fields.issubset(value):
            records.append(dict(value))
        else:
            for nested in value.values():
                records.extend(_direct_records_with_fields(nested, required_fields))
    elif isinstance(value, list):
        for nested in value:
            records.extend(_direct_records_with_fields(nested, required_fields))
    return tuple(records)


def _requested_symbols(arguments: dict[str, Any]) -> frozenset[str]:
    raw_values = _recursive_field_values(
        arguments,
        frozenset({"symbol", "symbols"}),
    )
    symbols: set[str] = set()
    for raw_value in raw_values:
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        if not all(isinstance(value, str) for value in values):
            raise RobinhoodGatewayError(
                "Robinhood quote request symbol arguments must be strings"
            )
        symbols.update(
            str(value).strip().upper() for value in values if str(value).strip()
        )
    if not symbols:
        raise RobinhoodGatewayError(
            "Robinhood quote request does not expose requested symbols"
        )
    return frozenset(symbols)


def _attest_equity_execution_snapshot(
    calls: tuple[McpToolCallEvidence, ...],
    intent: LiveExecutionIntent,
    snapshot: EquityExecutionSnapshot,
) -> None:
    expected_symbols = frozenset({intent.symbol, intent.analysis_symbol})
    quote_calls = _tool_calls(calls, "get_equity_quotes")
    tradability_calls = _tool_calls(calls, "get_equity_tradability")
    if len(quote_calls) != 1 or len(tradability_calls) != 1:
        raise RobinhoodGatewayError(
            "Robinhood quote attestation requires exactly one quote and tradability call"
        )
    for call in (quote_calls[0], tradability_calls[0]):
        if _requested_symbols(call.arguments) != expected_symbols:
            raise RobinhoodGatewayError(
                f"Robinhood quote request symbol set mismatch: tool={call.tool}"
            )
    normalized_by_symbol = {
        quote.symbol: quote.to_dict()
        for quote in (snapshot.execution_quote, snapshot.analysis_quote)
    }
    normalized_quotes = tuple(
        normalized_by_symbol[symbol] for symbol in sorted(normalized_by_symbol)
    )
    quote_records = _direct_records_with_fields(
        _mcp_result_value(quote_calls[0]),
        frozenset({"symbol", "bid_price", "ask_price", "last_price", "observed_at"}),
    )
    _bind_normalized_items(
        normalized_quotes,
        quote_records,
        ("symbol",),
        ("symbol", "bid_price", "ask_price", "last_price", "observed_at"),
        "equity_quote",
    )
    normalized_tradability = tuple(
        {
            "symbol": quote["symbol"],
            "tradable": quote["tradable"],
        }
        for quote in normalized_quotes
    )
    tradability_records = _direct_records_with_fields(
        _mcp_result_value(tradability_calls[0]),
        frozenset({"symbol", "tradable"}),
    )
    _bind_normalized_items(
        normalized_tradability,
        tradability_records,
        ("symbol",),
        ("symbol", "tradable"),
        "equity_tradability",
    )


def _nonnegative_finite_number(payload: dict[str, Any], field: str) -> float:
    try:
        value = float(payload.get(field, 0.0))
    except (TypeError, ValueError) as error:
        raise RobinhoodGatewayError(
            f"Robinhood Agentic field must be numeric: field={field}, value={payload.get(field)!r}"
        ) from error
    if not math.isfinite(value) or value < 0.0:
        raise RobinhoodGatewayError(
            f"Robinhood Agentic field must be finite and nonnegative: field={field}, value={value}"
        )
    return value


def _required_finite_item_number(
    item: dict[str, Any],
    field: str,
    item_label: str,
    nonnegative: bool,
) -> float:
    if field not in item or isinstance(item[field], bool):
        raise RobinhoodGatewayError(
            f"Robinhood broker item is missing a numeric field: item={item_label}, field={field}"
        )
    try:
        value = float(item[field])
    except (TypeError, ValueError) as error:
        raise RobinhoodGatewayError(
            f"Robinhood broker item field must be numeric: item={item_label}, field={field}"
        ) from error
    if not math.isfinite(value) or (nonnegative and value < 0.0):
        raise RobinhoodGatewayError(
            "Robinhood broker item numeric field violates its domain: "
            f"item={item_label}, field={field}"
        )
    return value


def _aware_timestamp(value: Any, field: str, item_label: str, allow_empty: bool) -> str:
    timestamp = str(value).strip()
    if not timestamp:
        if allow_empty:
            return ""
        raise RobinhoodGatewayError(
            f"Robinhood broker item timestamp is missing: item={item_label}, field={field}"
        )
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise RobinhoodGatewayError(
            f"Robinhood broker item timestamp is invalid: item={item_label}, field={field}"
        ) from error
    if parsed.tzinfo is None:
        raise RobinhoodGatewayError(
            f"Robinhood broker item timestamp must be timezone-aware: item={item_label}, field={field}"
        )
    return timestamp


def _validated_equity_position(item: Any, index: int) -> dict[str, Any]:
    item_label = f"equity_position[{index}]"
    if not isinstance(item, dict):
        raise RobinhoodGatewayError(
            f"Robinhood broker position item must be an object: item={item_label}"
        )
    symbol = str(item.get("symbol", "")).strip().upper()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise RobinhoodGatewayError(
            f"Robinhood broker position symbol is invalid: item={item_label}"
        )
    quantity = _required_finite_item_number(item, "quantity", item_label, True)
    if quantity <= 0.0:
        raise RobinhoodGatewayError(
            f"Robinhood broker position quantity must be positive: item={item_label}"
        )
    for field in ("average_cost", "market_price", "market_value"):
        _required_finite_item_number(item, field, item_label, True)
    _required_finite_item_number(item, "unrealized_pnl", item_label, False)
    return dict(item)


def _validated_option_position(item: Any, index: int) -> dict[str, Any]:
    item_label = f"option_position[{index}]"
    if not isinstance(item, dict):
        raise RobinhoodGatewayError(
            f"Robinhood broker position item must be an object: item={item_label}"
        )
    _validated_equity_position(item, index)
    if not str(item.get("contract_id", "")).strip():
        raise RobinhoodGatewayError(
            f"Robinhood option position contract_id is missing: item={item_label}"
        )
    return dict(item)


def _validated_order(item: Any, index: int, option: bool) -> dict[str, Any]:
    item_label = f"{'option' if option else 'equity'}_order[{index}]"
    if not isinstance(item, dict):
        raise RobinhoodGatewayError(
            f"Robinhood broker order item must be an object: item={item_label}"
        )
    if not str(item.get("order_id", "")).strip():
        raise RobinhoodGatewayError(
            f"Robinhood broker order_id is missing: item={item_label}"
        )
    symbol = str(item.get("symbol", "")).strip().upper()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise RobinhoodGatewayError(
            f"Robinhood broker order symbol is invalid: item={item_label}"
        )
    if str(item.get("side", "")).strip().lower() not in {"buy", "sell"}:
        raise RobinhoodGatewayError(
            f"Robinhood broker order side is invalid: item={item_label}"
        )
    status = str(item.get("status", "")).strip().lower()
    if status not in RECOGNIZED_ORDER_STATUSES:
        raise RobinhoodGatewayError(
            f"Robinhood broker order status is invalid: item={item_label}"
        )
    _aware_timestamp(item.get("submitted_at"), "submitted_at", item_label, False)
    _aware_timestamp(item.get("filled_at"), "filled_at", item_label, True)
    filled_quantity = _required_finite_item_number(
        item, "filled_quantity", item_label, True
    )
    average_fill_price = _required_finite_item_number(
        item, "average_fill_price", item_label, True
    )
    if status in {"filled", "partially_filled"} and filled_quantity <= 0.0:
        raise RobinhoodGatewayError(
            f"Robinhood filled order quantity must be positive: item={item_label}"
        )
    if status == "filled" and average_fill_price <= 0.0:
        raise RobinhoodGatewayError(
            f"Robinhood filled order average price must be positive: item={item_label}"
        )
    for field in ("limit_price", "quantity", "notional_usd", "fees_usd"):
        if field in item:
            value = _required_finite_item_number(item, field, item_label, True)
            if value < 0.0:
                raise RobinhoodGatewayError(
                    f"Robinhood broker order economics must be nonnegative: "
                    f"item={item_label}, field={field}"
                )
    for field in ("order_type", "time_in_force"):
        if field in item and not str(item.get(field, "")).strip():
            raise RobinhoodGatewayError(
                f"Robinhood broker order field must be nonempty: "
                f"item={item_label}, field={field}"
            )
    try:
        date.fromisoformat(str(item.get("market_date", "")))
    except ValueError as error:
        raise RobinhoodGatewayError(
            f"Robinhood broker order market_date is invalid: item={item_label}"
        ) from error
    if option:
        if not str(item.get("contract_id", "")).strip():
            raise RobinhoodGatewayError(
                f"Robinhood option order contract_id is missing: item={item_label}"
            )
        try:
            date.fromisoformat(str(item.get("expiry", "")))
        except ValueError as error:
            raise RobinhoodGatewayError(
                f"Robinhood option order expiry is invalid: item={item_label}"
            ) from error
        if str(item.get("option_type", "")).strip().lower() not in {"call", "put"}:
            raise RobinhoodGatewayError(
                f"Robinhood option order type is invalid: item={item_label}"
            )
        strike = _required_finite_item_number(item, "strike", item_label, True)
        if strike <= 0.0:
            raise RobinhoodGatewayError(
                f"Robinhood option order strike must be positive: item={item_label}"
            )
    return dict(item)


def _validated_items(
    values: list[Any],
    validator: Callable[[Any, int], dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    return tuple(validator(value, index) for index, value in enumerate(values))


def _assert_exact_text(
    value: Any,
    field_names: frozenset[str],
    expected: str,
    field_label: str,
) -> None:
    observed = _single_string_field(value, field_names, field_label)
    if observed.casefold() != expected.casefold():
        raise RobinhoodGatewayError(
            f"Robinhood MCP exact order attestation mismatch: field={field_label}"
        )


def _assert_exact_decimal(
    value: Any,
    field_names: frozenset[str],
    expected: float,
    field_label: str,
) -> None:
    observed = _single_decimal_field(value, field_names, field_label)
    if observed != Decimal(str(expected)):
        raise RobinhoodGatewayError(
            f"Robinhood MCP exact order attestation mismatch: field={field_label}"
        )


def _assert_absent_or_zero(
    value: Any,
    field_names: frozenset[str],
    field_label: str,
) -> None:
    values = _recursive_field_values(value, field_names)
    if any(_decimal_value(item, field_label) != Decimal("0") for item in values):
        raise RobinhoodGatewayError(
            f"Robinhood MCP exact order attestation found a conflicting amount: field={field_label}"
        )


def _assert_absent_or_false(
    value: Any,
    field_names: frozenset[str],
    field_label: str,
) -> None:
    values = _recursive_field_values(value, field_names)
    if any(item is not False for item in values):
        raise RobinhoodGatewayError(
            "Robinhood MCP exact order attestation found a truthy or non-boolean flag: "
            f"field={field_label}"
        )


def _attest_order_argument_allowlist(arguments: dict[str, Any], tool: str) -> None:
    unexpected = sorted(set(arguments) - set(ORDER_ARGUMENT_FIELDS))
    if unexpected:
        raise RobinhoodGatewayError(
            "Robinhood MCP order call contains unexpected arguments: "
            f"tool={tool}, unexpected={unexpected}"
        )


def _attest_exact_order_fields(value: Any, intent: LiveExecutionIntent) -> None:
    _assert_exact_text(value, SYMBOL_FIELDS, intent.symbol, "symbol")
    _assert_exact_text(value, SIDE_FIELDS, intent.side, "side")
    _assert_exact_text(value, ORDER_TYPE_FIELDS, intent.order_type, "order_type")
    _assert_exact_text(
        value,
        TIME_IN_FORCE_FIELDS,
        intent.time_in_force,
        "time_in_force",
    )
    if intent.order_type == "market":
        _assert_absent_or_zero(value, LIMIT_PRICE_FIELDS, "limit_price")
    else:
        _assert_exact_decimal(
            value,
            LIMIT_PRICE_FIELDS,
            intent.limit_price,
            "limit_price",
        )
    _assert_absent_or_false(value, EXTENDED_HOURS_FIELDS, "extended_hours")
    if intent.quantity > 0.0:
        _assert_exact_decimal(value, QUANTITY_FIELDS, intent.quantity, "quantity")
        _assert_absent_or_zero(value, NOTIONAL_FIELDS, "notional")
    else:
        _assert_exact_decimal(value, NOTIONAL_FIELDS, intent.notional_usd, "notional")
        _assert_absent_or_zero(value, QUANTITY_FIELDS, "quantity")


def _attest_order_call(
    call: McpToolCallEvidence,
    intent: LiveExecutionIntent,
    account_id: str | None,
) -> dict[str, Any] | list[Any]:
    _attest_order_argument_allowlist(call.arguments, call.tool)
    if account_id is None:
        if _recursive_field_values(call.arguments, ACCOUNT_IDENTIFIER_FIELDS):
            raise RobinhoodGatewayError(
                "Deterministic Robinhood order call unexpectedly supplied an "
                f"account identifier: tool={call.tool}"
            )
    else:
        observed_account_id = _single_string_field(
            call.arguments,
            ACCOUNT_IDENTIFIER_FIELDS,
            f"{call.tool}_account_id",
        )
        if observed_account_id != account_id:
            raise RobinhoodGatewayError(
                "Robinhood order call is not bound to the labeled Agentic "
                f"account: tool={call.tool}"
            )
    _attest_exact_order_fields(call.arguments, intent)
    result_value = _mcp_result_value(call)
    _attest_exact_order_fields(result_value, intent)
    return result_value


def _equity_quote_snapshot(
    payload: dict[str, Any],
    field: str,
    expected_symbol: str,
) -> EquityQuoteSnapshot:
    raw_quote = payload.get(field)
    if not isinstance(raw_quote, dict):
        raise RobinhoodGatewayError(
            f"Robinhood Agentic equity quote must be an object: field={field}, value={raw_quote!r}"
        )
    symbol = str(raw_quote.get("symbol", "")).strip().upper()
    if symbol != expected_symbol:
        raise RobinhoodGatewayError(
            "Robinhood Agentic equity quote symbol mismatch: "
            f"field={field}, expected={expected_symbol}, actual={symbol!r}"
        )
    observed_at = str(raw_quote.get("observed_at", "")).strip()
    if not observed_at:
        raise RobinhoodGatewayError(
            f"Robinhood Agentic equity quote is missing observed_at: field={field}"
        )
    if type(raw_quote.get("tradable")) is not bool:
        raise RobinhoodGatewayError(
            "Robinhood Agentic equity tradability must be boolean: "
            f"field={field}, value={raw_quote.get('tradable')!r}"
        )
    return EquityQuoteSnapshot(
        symbol=symbol,
        bid_price=_nonnegative_finite_number(raw_quote, "bid_price"),
        ask_price=_nonnegative_finite_number(raw_quote, "ask_price"),
        last_price=_nonnegative_finite_number(raw_quote, "last_price"),
        observed_at=observed_at,
        tradable=raw_quote["tradable"] is True,
    )


def _equity_execution_snapshot(
    payload: dict[str, Any],
    intent: LiveExecutionIntent,
) -> EquityExecutionSnapshot:
    source = str(payload.get("source", "")).strip()
    if source != EQUITY_SNAPSHOT_SOURCE:
        raise RobinhoodGatewayError(
            "Robinhood Agentic equity snapshot source mismatch: "
            f"expected={EQUITY_SNAPSHOT_SOURCE!r}, actual={source!r}"
        )
    return EquityExecutionSnapshot(
        execution_quote=_equity_quote_snapshot(
            payload,
            "execution_quote",
            intent.symbol,
        ),
        analysis_quote=_equity_quote_snapshot(
            payload,
            "analysis_quote",
            intent.analysis_symbol,
        ),
        source=source,
    )


def _codex_exec_command(
    executable: str,
    working_directory: str,
    result_path: Path,
    allowed_tools: tuple[str, ...],
    bearer_token_env_var: str | None = None,
    local_model: str | None = None,
) -> list[str]:
    if not allowed_tools:
        raise ValueError("allowed_tools must contain at least one MCP tool")
    if bearer_token_env_var is not None:
        raise ValueError(
            "Broker bearer material is prohibited from generative subprocesses"
        )
    if local_model is not None and (
        not LOCAL_MODEL_PATTERN.fullmatch(local_model)
        or local_model.endswith((":latest", ":cloud"))
    ):
        raise ValueError("local_model must be an explicit non-cloud Ollama tag")
    enabled_tools = json.dumps(
        sorted(set(allowed_tools)),
        ensure_ascii=True,
        separators=(",", ":"),
    )
    command = [
        executable,
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--color",
        "never",
        "--json",
    ]
    if local_model is not None:
        command.extend(
            (
                "--oss",
                "--local-provider",
                LOCAL_MODEL_PROVIDER,
                "--model",
                local_model,
                "-c",
                (
                    f"model_providers.{LOCAL_MODEL_PROVIDER}.base_url="
                    f'"{LOCAL_MODEL_BASE_URL}"'
                ),
            )
        )
    if local_model is None:
        command.extend(
            (
                "-c",
                f'mcp_servers.{MCP_SERVER_NAME}.url="{OFFICIAL_ROBINHOOD_MCP}"',
            )
        )
        command.extend(
            (
                "-c",
                f"mcp_servers.{MCP_SERVER_NAME}.enabled_tools={enabled_tools}",
                "-c",
                f'mcp_servers.{MCP_SERVER_NAME}.default_tools_approval_mode="writes"',
            )
        )
        for tool in sorted(set(allowed_tools) & READ_ONLY_ROBINHOOD_TOOLS):
            command.extend(
                (
                    "-c",
                    (
                        f"mcp_servers.{MCP_SERVER_NAME}.tools."
                        f'{tool}.approval_mode="approve"'
                    ),
                )
            )
    for feature in DISABLED_CODEX_FEATURES:
        command.extend(("--disable", feature))
    command.extend(
        (
            "-C",
            working_directory,
            "-o",
            str(result_path),
            "-",
        )
    )
    return command


def _direct_call_evidence(
    tool: str,
    arguments: dict[str, Any],
    raw_result: dict[str, Any],
) -> McpToolCallEvidence:
    if raw_result.get("isError") is True or raw_result.get("is_error") is True:
        raise RobinhoodGatewayError(
            f"Deterministic Robinhood MCP tool returned an error: tool={tool}"
        )
    structured = raw_result.get(
        "structuredContent",
        raw_result.get("structured_content"),
    )
    content = raw_result.get("content")
    normalized: dict[str, Any] = {}
    if isinstance(structured, (dict, list)):
        normalized["structured_content"] = structured
    if isinstance(content, list):
        normalized["content"] = content
    if not normalized:
        raise RobinhoodGatewayError(
            f"Deterministic Robinhood MCP result lacks typed evidence: tool={tool}"
        )
    return McpToolCallEvidence(
        call_id=f"deterministic-{tool}",
        tool=tool,
        arguments=dict(arguments),
        result=normalized,
    )


def _direct_result_warnings(value: Any) -> tuple[str, ...]:
    warnings: list[str] = []
    for item in _recursive_field_values(
        value,
        frozenset({"alerts", "warning", "warnings"}),
    ):
        if isinstance(item, str):
            warnings.append(item)
        elif isinstance(item, list) and all(isinstance(entry, str) for entry in item):
            warnings.extend(item)
        else:
            raise RobinhoodGatewayError(
                "Deterministic Robinhood MCP warnings are not typed strings"
            )
    if len(warnings) > 64 or any(len(warning) > 2_048 for warning in warnings):
        raise RobinhoodGatewayError(
            "Deterministic Robinhood MCP warnings exceed bounded limits"
        )
    return tuple(warnings)


def _optional_direct_decimal(
    value: Any,
    field_names: frozenset[str],
    field_label: str,
) -> float:
    values = _recursive_field_values(value, field_names)
    scalar_values = tuple(item for item in values if not isinstance(item, (dict, list)))
    if not scalar_values:
        return 0.0
    decimals = {_decimal_value(item, field_label) for item in scalar_values}
    if len(decimals) != 1:
        raise RobinhoodGatewayError(
            "Deterministic Robinhood MCP result contains an ambiguous number: "
            f"field={field_label}"
        )
    return float(next(iter(decimals)))


def _optional_direct_string(
    value: Any,
    field_names: frozenset[str],
    field_label: str,
) -> str:
    values = _recursive_field_values(value, field_names)
    normalized = {str(item).strip() for item in values if str(item).strip()}
    if not normalized:
        return ""
    if len(normalized) != 1:
        raise RobinhoodGatewayError(
            "Deterministic Robinhood MCP result contains ambiguous text: "
            f"field={field_label}"
        )
    return next(iter(normalized))


def _gateway_order_result(
    payload: dict[str, Any],
    review_tool: str,
    place_tool: str,
    intent: LiveExecutionIntent,
    calls: tuple[McpToolCallEvidence, ...],
    account_id: str,
) -> GatewayOrderResult:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list) or not all(
        isinstance(value, str) for value in warnings
    ):
        raise RobinhoodGatewayError(
            f"Robinhood Agentic warnings must be an array of strings: value={warnings!r}"
        )
    observed = tuple(sorted({call.tool for call in calls}))
    review_calls = _tool_calls(calls, review_tool)
    place_calls = _tool_calls(calls, place_tool)
    review_call_count = len(review_calls)
    place_call_count = len(place_calls)
    if review_call_count > 1 or place_call_count > 1:
        raise RobinhoodPlacementAmbiguousError(
            "Robinhood MCP transcript contains duplicate review or placement calls: "
            f"review_count={review_call_count}, place_count={place_call_count}"
        )
    if (
        review_call_count == 1
        and place_call_count == 1
        and calls.index(review_calls[0]) >= calls.index(place_calls[0])
    ):
        raise RobinhoodPlacementAmbiguousError(
            "Robinhood MCP placement was observed before its exact review"
        )
    try:
        _assert_account_identifier_redacted(payload, account_id, "order_result")
    except RobinhoodGatewayError as error:
        if place_calls:
            raise RobinhoodPlacementAmbiguousError(
                "Robinhood order result leaked account identity after a placement call"
            ) from error
        raise
    review_result: dict[str, Any] | list[Any] | None = None
    if review_calls:
        try:
            review_result = _attest_order_call(review_calls[0], intent, account_id)
        except RobinhoodGatewayError as error:
            if place_calls:
                raise RobinhoodPlacementAmbiguousError(
                    "Robinhood reviewed or placed an order whose exact intent is not attested"
                ) from error
            raise
    place_result: dict[str, Any] | list[Any] | None = None
    if place_calls:
        try:
            place_result = _attest_order_call(place_calls[0], intent, account_id)
        except RobinhoodGatewayError as error:
            raise RobinhoodPlacementAmbiguousError(
                "Robinhood placement call does not prove the exact typed intent"
            ) from error
    placed = payload.get("placed") is True
    reviewed = payload.get("review_succeeded") is True
    order_id = str(payload.get("order_id", "")).strip()
    status = str(payload.get("status", "")).strip().lower()
    error_text = str(payload.get("error", "")).strip()
    if payload.get("order_history_complete") is not True:
        if placed or place_call_count > 0:
            raise RobinhoodPlacementAmbiguousError(
                "Robinhood Agentic attempted placement without complete order history"
            )
        return GatewayOrderResult(
            review_succeeded=False,
            placed=False,
            order_id="",
            status="blocked_order_history_incomplete",
            filled_quantity=0.0,
            average_fill_price=0.0,
            submitted_at="",
            filled_at="",
            warnings=tuple(warnings),
            error=error_text,
            observed_tools=observed,
        )
    if placed:
        invariant_failures: list[str] = []
        if not reviewed or review_call_count != 1:
            invariant_failures.append("exactly_one_successful_review_required")
        if place_call_count != 1:
            invariant_failures.append("exactly_one_place_call_required")
        if not order_id:
            invariant_failures.append("broker_order_id_required")
        if status not in PLACED_ORDER_STATUSES:
            invariant_failures.append(f"recognized_placed_status_required:{status!r}")
        if error_text:
            invariant_failures.append("error_must_be_empty_after_placement")
        if review_result is None:
            invariant_failures.append("machine_readable_review_result_required")
        else:
            try:
                transcript_reviewed = _single_bool_field(
                    review_result,
                    frozenset({"approved", "review_succeeded"}),
                    "review_succeeded",
                )
            except RobinhoodGatewayError as error:
                raise RobinhoodPlacementAmbiguousError(
                    "Robinhood review response lacks machine-readable approval proof"
                ) from error
            if transcript_reviewed is not reviewed:
                invariant_failures.append("review_result_transcript_mismatch")
        if place_result is None:
            invariant_failures.append("machine_readable_place_result_required")
        else:
            try:
                transcript_placed = _single_bool_field(
                    place_result,
                    frozenset({"placed"}),
                    "placed",
                )
                transcript_order_id = _single_string_field(
                    place_result,
                    ORDER_ID_FIELDS,
                    "placed_order_id",
                )
                transcript_status = _single_string_field(
                    place_result,
                    ORDER_STATUS_FIELDS,
                    "placed_order_status",
                ).lower()
            except RobinhoodGatewayError as error:
                raise RobinhoodPlacementAmbiguousError(
                    "Robinhood placement response lacks machine-readable broker outcome proof"
                ) from error
            if transcript_placed is not placed:
                invariant_failures.append("placed_result_transcript_mismatch")
            if transcript_order_id != order_id:
                invariant_failures.append("broker_order_id_transcript_mismatch")
            if transcript_status != status:
                invariant_failures.append("broker_order_status_transcript_mismatch")
        filled_quantity = _nonnegative_finite_number(payload, "filled_quantity")
        average_fill_price = _nonnegative_finite_number(payload, "average_fill_price")
        if place_result is not None:
            try:
                transcript_filled_quantity = _single_decimal_field(
                    place_result,
                    frozenset({"filled_quantity"}),
                    "filled_quantity",
                )
                transcript_average_fill_price = _single_decimal_field(
                    place_result,
                    frozenset({"average_fill_price"}),
                    "average_fill_price",
                )
            except RobinhoodGatewayError as error:
                raise RobinhoodPlacementAmbiguousError(
                    "Robinhood placement response lacks machine-readable fill proof"
                ) from error
            if transcript_filled_quantity != Decimal(str(filled_quantity)):
                invariant_failures.append("filled_quantity_transcript_mismatch")
            if transcript_average_fill_price != Decimal(str(average_fill_price)):
                invariant_failures.append("average_fill_price_transcript_mismatch")
        if status in {"filled", "partially_filled"} and filled_quantity <= 0.0:
            invariant_failures.append(
                "positive_filled_quantity_required_for_fill_status"
            )
        if status == "filled" and average_fill_price <= 0.0:
            invariant_failures.append(
                "positive_average_fill_price_required_for_filled_status"
            )
        if invariant_failures:
            raise RobinhoodPlacementAmbiguousError(
                "Robinhood Agentic placement result violated invariants: "
                f"failures={invariant_failures}, order_id={order_id!r}, status={status!r}"
            )
        return GatewayOrderResult(
            review_succeeded=True,
            placed=True,
            order_id=order_id,
            status=status,
            filled_quantity=filled_quantity,
            average_fill_price=average_fill_price,
            submitted_at=str(payload.get("submitted_at", "")),
            filled_at=str(payload.get("filled_at", "")),
            warnings=tuple(warnings),
            error="",
            observed_tools=observed,
        )
    if place_call_count > 0 or order_id:
        raise RobinhoodPlacementAmbiguousError(
            "Robinhood Agentic reported no placement after observing placement evidence: "
            f"place_call_count={place_call_count}, order_id={order_id!r}, status={status!r}"
        )
    if reviewed and review_call_count != 1:
        raise RobinhoodGatewayError(
            f"Robinhood Agentic review count is invalid: review_call_count={review_call_count}"
        )
    if not status:
        raise RobinhoodGatewayError(
            "Robinhood Agentic omitted status for a non-placed order"
        )
    return GatewayOrderResult(
        review_succeeded=reviewed,
        placed=False,
        order_id="",
        status=status,
        filled_quantity=0.0,
        average_fill_price=0.0,
        submitted_at="",
        filled_at="",
        warnings=tuple(warnings),
        error=error_text,
        observed_tools=observed,
    )


def _gateway_cancel_result(
    payload: dict[str, Any],
    cancel_tool: str,
    expected_order_id: str,
    calls: tuple[McpToolCallEvidence, ...],
    account_id: str,
) -> GatewayCancelResult:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list) or not all(
        isinstance(value, str) for value in warnings
    ):
        raise RobinhoodCancellationAmbiguousError(
            "Robinhood Agentic cancellation warnings must be an array of strings"
        )
    cancel_calls = _tool_calls(calls, cancel_tool)
    if len(cancel_calls) > 1:
        raise RobinhoodCancellationAmbiguousError(
            "Robinhood MCP transcript contains duplicate cancellation calls"
        )
    cancel_requested = payload.get("cancel_requested")
    if type(cancel_requested) is not bool:
        raise RobinhoodCancellationAmbiguousError(
            "Robinhood cancellation result must contain boolean cancel_requested"
        )
    order_id = str(payload.get("order_id", "")).strip()
    status = str(payload.get("status", "")).strip().lower()
    error_text = str(payload.get("error", "")).strip()
    if order_id and order_id != expected_order_id:
        raise RobinhoodCancellationAmbiguousError(
            "Robinhood cancellation result references a different order"
        )
    if status not in CANCEL_RESULT_STATUSES:
        raise RobinhoodCancellationAmbiguousError(
            f"Robinhood cancellation status is unrecognized: status={status!r}"
        )
    if cancel_calls:
        call = cancel_calls[0]
        unexpected = sorted(set(call.arguments) - set(CANCEL_ARGUMENT_FIELDS))
        if unexpected:
            raise RobinhoodCancellationAmbiguousError(
                "Robinhood cancellation call contains unexpected arguments: "
                f"unexpected={unexpected}"
            )
        observed_account_id = _single_string_field(
            call.arguments,
            ACCOUNT_IDENTIFIER_FIELDS,
            "cancel_account_id",
        )
        observed_order_id = _single_string_field(
            call.arguments,
            ORDER_ID_FIELDS,
            "cancel_order_id",
        )
        if observed_account_id != account_id or observed_order_id != expected_order_id:
            raise RobinhoodCancellationAmbiguousError(
                "Robinhood cancellation call is not bound to the exact Agentic order"
            )
        result_value = _mcp_result_value(call)
        transcript_order_id = _single_string_field(
            result_value,
            ORDER_ID_FIELDS,
            "cancel_result_order_id",
        )
        transcript_status = _single_string_field(
            result_value,
            ORDER_STATUS_FIELDS,
            "cancel_result_status",
        ).lower()
        if (
            transcript_order_id != expected_order_id
            or transcript_status != status
            or not cancel_requested
        ):
            raise RobinhoodCancellationAmbiguousError(
                "Robinhood normalized cancellation result is not bound to the MCP transcript"
            )
    elif cancel_requested:
        raise RobinhoodCancellationAmbiguousError(
            "Robinhood reported a cancellation request without a cancellation tool call"
        )
    if cancel_requested and (not order_id or error_text):
        raise RobinhoodCancellationAmbiguousError(
            "Robinhood accepted cancellation with contradictory normalized fields"
        )
    return GatewayCancelResult(
        cancel_requested=cancel_requested,
        order_id=order_id,
        status=status,
        warnings=tuple(warnings),
        error=error_text,
        observed_tools=tuple(sorted({call.tool for call in calls})),
    )


class RobinhoodAgenticGateway:
    """Connector class; trading decisions remain in pure upstream functions."""

    def __init__(
        self,
        runner: Runner,
        timeout_seconds: int,
        *,
        write_timeout_seconds: int | None = None,
        mcp_bearer_token: str | None = None,
        temporary_root: Path | None = None,
        codex_executable_path: Path | None = None,
        codex_executable_sha256: str | None = None,
        local_model: str | None = None,
        local_model_verifier: Callable[[], None] | None = None,
        expected_account_hash: str | None = None,
        deterministic_mcp_call: (
            Callable[
                [str, dict[str, Any], int, Callable[[], None] | None],
                dict[str, Any],
            ]
            | None
        ) = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive: {timeout_seconds}")
        if write_timeout_seconds is None:
            write_timeout_seconds = min(30, timeout_seconds)
        if (
            isinstance(write_timeout_seconds, bool)
            or not isinstance(write_timeout_seconds, int)
            or write_timeout_seconds <= 0
            or write_timeout_seconds > timeout_seconds
        ):
            raise ValueError(
                "write_timeout_seconds must be a positive integer no greater "
                "than timeout_seconds"
            )
        if mcp_bearer_token is not None:
            raise ValueError(
                "Broker bearer material is prohibited from the generative gateway; "
                "use the deterministic parent-side MCP transport"
            )
        if deterministic_mcp_call is not None and (
            not isinstance(expected_account_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_account_hash)
        ):
            raise ValueError(
                "Deterministic parent-side MCP requires the pinned account hash"
            )
        if deterministic_mcp_call is None and expected_account_hash is not None:
            raise ValueError(
                "expected_account_hash requires deterministic parent-side MCP"
            )
        if local_model is not None and (
            not LOCAL_MODEL_PATTERN.fullmatch(local_model)
            or local_model.endswith((":latest", ":cloud"))
        ):
            raise ValueError("local_model must be an explicit non-cloud Ollama tag")
        if (local_model is None) != (local_model_verifier is None):
            raise ValueError(
                "local_model and local_model_verifier must be supplied together"
            )
        if codex_executable_path is None:
            if codex_executable_sha256 is not None:
                raise ValueError(
                    "codex_executable_sha256 requires codex_executable_path"
                )
            if deterministic_mcp_call is not None:
                executable = ""
            else:
                discovered_executable = shutil.which("codex")
                if discovered_executable is None:
                    raise RobinhoodGatewayError(
                        "Codex CLI is required for the Robinhood Trading MCP gateway"
                    )
                executable = discovered_executable
            self._codex_sha256: str | None = None
        else:
            if not codex_executable_path.is_absolute():
                raise ValueError("Codex executable path must be absolute")
            executable_path = codex_executable_path.resolve()
            if not executable_path.is_file():
                raise RobinhoodGatewayError(
                    "Pinned Codex CLI executable is unavailable"
                )
            if not isinstance(codex_executable_sha256, str) or not re.fullmatch(
                r"[0-9a-f]{64}", codex_executable_sha256
            ):
                raise ValueError("Pinned Codex executable requires lowercase SHA-256")
            executable = str(executable_path)
            self._codex_sha256 = codex_executable_sha256
        self._runner = runner
        self._timeout_seconds = timeout_seconds
        self._write_timeout_seconds = write_timeout_seconds
        self._codex = executable
        self._verify_codex_executable()
        self._local_model = local_model
        self._local_model_verifier = local_model_verifier
        self._deterministic_mcp_call = deterministic_mcp_call
        self._parent_only_mode = deterministic_mcp_call is not None
        self._expected_account_hash = expected_account_hash
        self._temporary_root = (
            temporary_root.resolve() if temporary_root is not None else None
        )
        if self._temporary_root is not None:
            self._temporary_root.mkdir(parents=True, exist_ok=True)
        self._bearer_token_env_var: str | None = None
        self._subprocess_env: dict[str, str] | None = None

    def _verify_codex_executable(self) -> None:
        if self._codex_sha256 is None:
            return
        digest = hashlib.sha256()
        try:
            with Path(self._codex).open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as error:
            raise RobinhoodGatewayError(
                "Pinned Codex CLI executable cannot be read"
            ) from error
        if digest.hexdigest() != self._codex_sha256:
            raise RobinhoodGatewayError("Pinned Codex CLI executable SHA-256 mismatch")

    def _verify_local_model(self) -> None:
        if self._local_model_verifier is None:
            return
        try:
            self._local_model_verifier()
        except Exception as error:
            raise RobinhoodGatewayError(
                "Pinned local Ollama model verification failed"
            ) from error

    def _call_deterministic_mcp(
        self,
        tool: str,
        arguments: dict[str, Any],
        timeout_seconds: int,
        *,
        pre_call_guard: Callable[[], None] | None = None,
    ) -> McpToolCallEvidence:
        if (
            self._deterministic_mcp_call is None
            or tool not in DETERMINISTIC_WRITE_TOOLS
        ):
            raise RobinhoodGatewayError(
                "Deterministic Robinhood MCP write transport is unavailable"
            )
        try:
            raw_result = self._deterministic_mcp_call(
                tool,
                dict(arguments),
                timeout_seconds,
                pre_call_guard,
            )
        except RobinhoodGatewayError:
            raise
        except Exception as error:
            raise RobinhoodGatewayError(
                "Deterministic Robinhood MCP call failed: "
                f"tool={tool}, error={type(error).__name__}"
            ) from error
        if not isinstance(raw_result, dict):
            raise RobinhoodGatewayError(
                f"Deterministic Robinhood MCP result is not an object: tool={tool}"
            )
        return _direct_call_evidence(tool, arguments, raw_result)

    def _call_deterministic_read(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> McpToolCallEvidence:
        if (
            self._deterministic_mcp_call is None
            or tool not in READ_ONLY_ROBINHOOD_TOOLS
        ):
            raise RobinhoodGatewayError(
                "Deterministic parent-side Robinhood read transport is unavailable"
            )
        try:
            raw_result = self._deterministic_mcp_call(
                tool,
                dict(arguments),
                self._timeout_seconds,
                None,
            )
        except RobinhoodGatewayError:
            raise
        except Exception as error:
            raise RobinhoodGatewayError(
                "Deterministic parent-side Robinhood read failed: "
                f"tool={tool}, error={type(error).__name__}"
            ) from error
        if not isinstance(raw_result, dict):
            raise RobinhoodGatewayError(
                f"Deterministic Robinhood read result is not an object: tool={tool}"
            )
        return _direct_call_evidence(tool, arguments, raw_result)

    def _get_account_snapshot_deterministically(self) -> AccountSnapshot:
        calls: list[McpToolCallEvidence] = [
            self._call_deterministic_read("get_accounts", {})
        ]
        account = _agentic_account(tuple(calls))
        observed_account_hash = hashlib.sha256(
            account.account_id.encode("utf-8")
        ).hexdigest()
        if observed_account_hash != self._expected_account_hash:
            raise RobinhoodGatewayError(
                "Deterministic Robinhood read is not bound to the pinned "
                "Agentic account"
            )
        account_arguments = {"account_number": account.account_id}
        for tool in (
            "get_portfolio",
            "get_equity_positions",
            "get_option_positions",
        ):
            calls.append(self._call_deterministic_read(tool, account_arguments))
        for tool in ("get_equity_orders", "get_option_orders"):
            calls.append(
                self._call_deterministic_read(
                    tool,
                    {
                        **account_arguments,
                        "limit": ORDER_HISTORY_LIMIT,
                    },
                )
            )
        evidence = tuple(calls)
        attested_account = _attest_account_scope(
            evidence,
            (
                "get_portfolio",
                "get_equity_positions",
                "get_option_positions",
                "get_equity_orders",
                "get_option_orders",
            ),
        )
        portfolio = _mcp_result_value(_tool_calls(evidence, "get_portfolio")[0])
        buying_power = float(
            _single_decimal_field(
                portfolio,
                frozenset({"buying_power", "buying_power_usd"}),
                "buying_power_usd",
            )
        )
        total_equity = float(
            _single_decimal_field(
                portfolio,
                frozenset(
                    {
                        "equity",
                        "portfolio_value",
                        "total_equity",
                        "total_equity_usd",
                        "total_value",
                    }
                ),
                "total_equity_usd",
            )
        )
        if (
            not math.isfinite(buying_power)
            or buying_power < 0.0
            or not math.isfinite(total_equity)
            or total_equity < 0.0
        ):
            raise RobinhoodGatewayError(
                "Deterministic Robinhood portfolio values must be finite "
                "and nonnegative"
            )
        equity_positions = tuple(
            _validated_equity_position(
                _strict_parent_position(item, option=False),
                index,
            )
            for index, item in enumerate(
                _result_items(
                    _tool_calls(evidence, "get_equity_positions")[0],
                    frozenset({"equity_positions", "positions", "results"}),
                    "equity_position",
                )
            )
        )
        option_positions = tuple(
            _validated_option_position(
                _strict_parent_position(item, option=True),
                index,
            )
            for index, item in enumerate(
                _result_items(
                    _tool_calls(evidence, "get_option_positions")[0],
                    frozenset({"option_positions", "positions", "results"}),
                    "option_position",
                )
            )
        )
        equity_orders = tuple(
            _validated_order(
                _canonical_raw_broker_item(item, "equity_order"),
                index,
                False,
            )
            for index, item in enumerate(
                _result_items(
                    _tool_calls(evidence, "get_equity_orders")[0],
                    frozenset({"equity_orders", "orders", "results"}),
                    "equity_order",
                )
            )
        )
        option_orders = tuple(
            _validated_order(
                _canonical_raw_broker_item(item, "option_order"),
                index,
                True,
            )
            for index, item in enumerate(
                _result_items(
                    _tool_calls(evidence, "get_option_orders")[0],
                    frozenset({"option_orders", "orders", "results"}),
                    "option_order",
                )
            )
        )
        equity_complete, option_complete = _attest_order_history_results(evidence)
        errors: list[str] = []
        if not equity_complete:
            errors.append("equity_order_history_incomplete")
        if not option_complete:
            errors.append("option_order_history_incomplete")
        return AccountSnapshot(
            authenticated=True,
            account_type=attested_account.account_type,
            buying_power_usd=buying_power,
            total_equity_usd=total_equity,
            equity_positions=equity_positions,
            option_positions=option_positions,
            recent_equity_orders=equity_orders,
            recent_option_orders=option_orders,
            equity_order_history_complete=equity_complete,
            option_order_history_complete=option_complete,
            error=";".join(errors),
            account_hash=observed_account_hash,
        )

    def _get_equity_snapshot_deterministically(
        self,
        intent: LiveExecutionIntent,
    ) -> EquityExecutionSnapshot:
        expected_symbols = frozenset({intent.symbol, intent.analysis_symbol})
        arguments = {"symbols": sorted(expected_symbols)}
        quote_call = self._call_deterministic_read(
            "get_equity_quotes",
            arguments,
        )
        tradability_call = self._call_deterministic_read(
            "get_equity_tradability",
            arguments,
        )
        quote_records = _direct_records_with_fields(
            _mcp_result_value(quote_call),
            frozenset(
                {
                    "symbol",
                    "bid_price",
                    "ask_price",
                    "last_price",
                    "observed_at",
                }
            ),
        )
        tradability_records = _direct_records_with_fields(
            _mcp_result_value(tradability_call),
            frozenset({"symbol", "tradable"}),
        )
        quotes_by_symbol = {
            str(item["symbol"]).strip().upper(): item for item in quote_records
        }
        tradability_by_symbol = {
            str(item["symbol"]).strip().upper(): item for item in tradability_records
        }
        if (
            len(quotes_by_symbol) != len(quote_records)
            or len(tradability_by_symbol) != len(tradability_records)
            or frozenset(quotes_by_symbol) != expected_symbols
            or frozenset(tradability_by_symbol) != expected_symbols
        ):
            raise RobinhoodGatewayError(
                "Deterministic Robinhood quote response is missing, duplicated, "
                "or contains an unrequested symbol"
            )

        def quote(symbol: str) -> EquityQuoteSnapshot:
            raw_quote = quotes_by_symbol[symbol]
            raw_tradability = tradability_by_symbol[symbol]
            _aware_timestamp(
                raw_quote["observed_at"],
                "observed_at",
                f"equity_quote[{symbol}]",
                False,
            )
            return _equity_quote_snapshot(
                {
                    "quote": {
                        "symbol": symbol,
                        "bid_price": raw_quote["bid_price"],
                        "ask_price": raw_quote["ask_price"],
                        "last_price": raw_quote["last_price"],
                        "observed_at": raw_quote["observed_at"],
                        "tradable": raw_tradability["tradable"],
                    }
                },
                "quote",
                symbol,
            )

        snapshot = EquityExecutionSnapshot(
            execution_quote=quote(intent.symbol),
            analysis_quote=quote(intent.analysis_symbol),
            source=EQUITY_SNAPSHOT_SOURCE,
        )
        _attest_equity_execution_snapshot(
            (quote_call, tradability_call),
            intent,
            snapshot,
        )
        return snapshot

    @staticmethod
    def _deterministic_equity_arguments(
        intent: LiveExecutionIntent,
    ) -> dict[str, Any]:
        if intent.instrument != "equity":
            raise RobinhoodGatewayError(
                "Deterministic live execution is currently equity-only"
            )
        if not math.isfinite(intent.quantity) or intent.quantity <= 0.0:
            raise RobinhoodGatewayError(
                "Deterministic equity execution requires an exact positive quantity"
            )
        arguments: dict[str, Any] = {
            "side": intent.side,
            "symbol": intent.symbol,
            "quantity": intent.quantity,
            "order_type": intent.order_type,
            "time_in_force": intent.time_in_force,
        }
        if intent.order_type == "limit":
            arguments["limit_price"] = intent.limit_price
        return arguments

    def _place_equity_order_deterministically(
        self,
        intent: LiveExecutionIntent,
        pre_submit_guard: Callable[[], datetime] | None,
    ) -> GatewayOrderResult:
        arguments = self._deterministic_equity_arguments(intent)
        review_call = self._call_deterministic_mcp(
            "review_equity_order",
            arguments,
            self._write_timeout_seconds,
        )
        review_result = _attest_order_call(review_call, intent, None)
        review_succeeded = _single_bool_field(
            review_result,
            frozenset({"approved", "review_succeeded"}),
            "review_succeeded",
        )
        warnings = _direct_result_warnings(review_result)
        if not review_succeeded:
            return GatewayOrderResult(
                review_succeeded=False,
                placed=False,
                order_id="",
                status="blocked_by_broker_review",
                filled_quantity=0.0,
                average_fill_price=0.0,
                submitted_at="",
                filled_at="",
                warnings=warnings,
                error="broker_review_denied",
                observed_tools=("review_equity_order",),
            )
        try:
            place_call = self._call_deterministic_mcp(
                "place_equity_order",
                arguments,
                self._write_timeout_seconds,
                pre_call_guard=(
                    None
                    if pre_submit_guard is None
                    else lambda: self._validate_pre_submit_guard(pre_submit_guard)
                ),
            )
            place_result = _attest_order_call(place_call, intent, None)
            placed = _single_bool_field(
                place_result,
                frozenset({"placed"}),
                "placed",
            )
            order_id = _single_string_field(
                place_result,
                ORDER_ID_FIELDS,
                "order_id",
            )
            status = _single_string_field(
                place_result,
                ORDER_STATUS_FIELDS,
                "status",
            ).lower()
            if not placed or status not in PLACED_ORDER_STATUSES:
                raise RobinhoodGatewayError(
                    "Deterministic Robinhood placement result is not a "
                    "recognized placed order"
                )
            return GatewayOrderResult(
                review_succeeded=True,
                placed=True,
                order_id=order_id,
                status=status,
                filled_quantity=_optional_direct_decimal(
                    place_result,
                    frozenset({"filled_quantity"}),
                    "filled_quantity",
                ),
                average_fill_price=_optional_direct_decimal(
                    place_result,
                    frozenset({"average_fill_price"}),
                    "average_fill_price",
                ),
                submitted_at=_optional_direct_string(
                    place_result,
                    frozenset({"submitted_at"}),
                    "submitted_at",
                ),
                filled_at=_optional_direct_string(
                    place_result,
                    frozenset({"filled_at"}),
                    "filled_at",
                ),
                warnings=tuple(
                    dict.fromkeys((*warnings, *_direct_result_warnings(place_result)))
                ),
                error="",
                observed_tools=(
                    "place_equity_order",
                    "review_equity_order",
                ),
            )
        except RobinhoodPreSubmitGuardError:
            raise
        except RobinhoodGatewayError as error:
            raise RobinhoodPlacementAmbiguousError(
                "Deterministic Robinhood placement has an unknown broker "
                "outcome and must not be retried"
            ) from error

    def _validate_pre_submit_guard(
        self,
        pre_submit_guard: Callable[[], datetime],
    ) -> None:
        try:
            authority_deadline = pre_submit_guard()
        except RobinhoodPreSubmitGuardError:
            raise
        except Exception as error:
            raise RobinhoodPreSubmitGuardError(
                "Final broker-sink pre-submit guard denied the write: "
                f"{type(error).__name__}: {error}"
            ) from error
        if (
            not isinstance(authority_deadline, datetime)
            or authority_deadline.tzinfo is None
            or authority_deadline.utcoffset() is None
        ):
            raise RobinhoodPreSubmitGuardError(
                "Final broker-sink guard must return an aware authority deadline"
            )
        remaining_seconds = (
            authority_deadline.astimezone(timezone.utc) - datetime.now(timezone.utc)
        ).total_seconds()
        required_seconds = (
            self._write_timeout_seconds + PRE_SUBMIT_SAFETY_MARGIN_SECONDS
        )
        if remaining_seconds <= required_seconds:
            raise RobinhoodPreSubmitGuardError(
                "Capital authority has insufficient remaining validity for "
                "the bounded external write operation"
            )

    def _run(
        self,
        operation: str,
        prompt: str,
        required_tools: tuple[str, ...],
        allowed_tools: tuple[str, ...],
        attempt_limit: int,
        timeout_seconds: int | None = None,
    ) -> GatewayEnvelope:
        if self._parent_only_mode:
            raise RobinhoodGatewayError(
                "Parent-only broker mode prohibits generative MCP fallback"
            )
        if attempt_limit <= 0:
            raise ValueError(f"attempt_limit must be positive: {attempt_limit}")
        if self._bearer_token_env_var is not None and not set(allowed_tools).issubset(
            READ_ONLY_ROBINHOOD_TOOLS
        ):
            forbidden = sorted(set(allowed_tools) - READ_ONLY_ROBINHOOD_TOOLS)
            raise RobinhoodGatewayError(
                "Credential-bound model execution may expose only read-only "
                f"Robinhood tools: forbidden={forbidden}"
            )
        effective_timeout = (
            self._timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        if effective_timeout <= 0 or effective_timeout > self._timeout_seconds:
            raise ValueError(
                "operation timeout must be positive and no greater than "
                "the gateway timeout"
            )
        last_error = ""
        for attempt in range(1, attempt_limit + 1):
            self._verify_codex_executable()
            self._verify_local_model()
            with tempfile.TemporaryDirectory(
                prefix="dopey-robinhood-agentic-",
                dir=self._temporary_root,
            ) as temporary:
                result_path = Path(temporary) / "result.json"
                command = _codex_exec_command(
                    self._codex,
                    temporary,
                    result_path,
                    allowed_tools,
                    self._bearer_token_env_var,
                    self._local_model,
                )
                try:
                    completed = self._runner(
                        command,
                        input=prompt,
                        text=True,
                        encoding="utf-8",
                        errors="strict",
                        capture_output=True,
                        timeout=effective_timeout,
                        check=False,
                        env=self._subprocess_env,
                    )
                except (OSError, subprocess.TimeoutExpired) as error:
                    last_error = f"{type(error).__name__}: {error}"
                    LOGGER.warning(
                        "Robinhood Agentic gateway attempt failed",
                        extra={
                            "operation": operation,
                            "attempt": attempt,
                            "error": last_error,
                        },
                    )
                    continue
                attach_failure = _mcp_attach_failure_kind(completed.stderr or "")
                if attach_failure == "auth_required":
                    # codex can exit 0 with a clean-looking transcript while the
                    # robinhood server never attached; without this check the
                    # failure surfaces as the misleading "required MCP calls
                    # were not observed" after burning every retry attempt.
                    raise RobinhoodAuthRequiredError(
                        f"operation={operation}: {reauth_remediation()}"
                    )
                if attach_failure == "attach_failure":
                    stderr_tail = (completed.stderr or "")[-500:]
                    last_error = (
                        "MCP server attach failed (possibly transient): "
                        f"stderr_tail={stderr_tail!r}"
                    )
                    LOGGER.warning(
                        "Robinhood Agentic gateway could not attach the MCP server",
                        extra={
                            "operation": operation,
                            "attempt": attempt,
                            "error": last_error,
                        },
                    )
                    continue
                if completed.returncode != 0:
                    last_error = (
                        f"return_code={completed.returncode}, "
                        f"stderr_length={len(completed.stderr)}"
                    )
                    LOGGER.warning(
                        "Robinhood Agentic gateway returned nonzero",
                        extra={
                            "operation": operation,
                            "attempt": attempt,
                            "error": last_error,
                        },
                    )
                    continue
                try:
                    calls = _mcp_transcript(completed.stdout)
                except RobinhoodConsentRequiredError:
                    raise  # unattended consent cannot succeed on retry
                except RobinhoodGatewayError as error:
                    last_error = str(error)
                    LOGGER.warning(
                        "Robinhood Agentic gateway emitted invalid MCP evidence",
                        extra={
                            "operation": operation,
                            "attempt": attempt,
                            "error": last_error,
                        },
                    )
                    continue
                observed_tool_counts = {
                    tool: sum(call.tool == tool for call in calls)
                    for tool in sorted({call.tool for call in calls})
                }
                extra_tools = sorted(set(observed_tool_counts) - set(allowed_tools))
                if extra_tools:
                    last_error = (
                        f"disallowed MCP calls were observed: tools={extra_tools}"
                    )
                    LOGGER.warning(
                        "Robinhood Agentic gateway used disallowed tools",
                        extra={
                            "operation": operation,
                            "attempt": attempt,
                            "error": last_error,
                        },
                    )
                    continue
                missing_tools = [
                    tool for tool in required_tools if tool not in observed_tool_counts
                ]
                if missing_tools:
                    last_error = (
                        f"required MCP calls were not observed: tools={missing_tools}"
                    )
                    LOGGER.warning(
                        "Robinhood Agentic gateway omitted required tools",
                        extra={
                            "operation": operation,
                            "attempt": attempt,
                            "error": last_error,
                        },
                    )
                    continue
                try:
                    payload = json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    last_error = (
                        f"invalid result JSON: path={result_path}, error={error}"
                    )
                    LOGGER.warning(
                        "Robinhood Agentic gateway emitted invalid JSON",
                        extra={
                            "operation": operation,
                            "attempt": attempt,
                            "error": last_error,
                        },
                    )
                    continue
                if not isinstance(payload, dict) or not all(
                    isinstance(key, str) for key in payload
                ):
                    last_error = f"gateway result must be a JSON object: type={type(payload).__name__}"
                    continue
                payload["observed_tools"] = sorted(observed_tool_counts)
                payload["observed_tool_call_counts"] = observed_tool_counts
                return GatewayEnvelope(payload=payload, calls=calls)
        raise RobinhoodGatewayError(
            "Robinhood Agentic gateway failed after bounded attempts: "
            f"operation={operation}, attempts={attempt_limit}, error={last_error}"
        )

    def get_account_snapshot(self) -> AccountSnapshot:
        if getattr(self, "_deterministic_mcp_call", None) is not None:
            return self._get_account_snapshot_deterministically()
        prompt = """Standing owner authorization applies. Use only Robinhood Trading MCP tools
get_accounts, get_portfolio, get_equity_positions, get_option_positions, get_equity_orders,
and get_option_orders. Do not call any
review, place, replace, cancel, watchlist-write, or scan-write tool. Select the dedicated Agentic
trading account. The get_accounts result must expose exactly one account explicitly labeled Agentic,
and every later account-scoped tool call must pass that exact account ID in its arguments. Never put
account numbers, account IDs, tokens, or credentials in the final response. Return only a
compact JSON object with: authenticated (boolean), account_type (string), buying_power_usd
(number), total_equity_usd (number), equity_positions (array of objects containing only symbol,
quantity, average_cost, market_price, market_value, and unrealized_pnl), option_positions (array
of objects containing only symbol, contract_id, quantity, average_cost, market_price,
market_value, and unrealized_pnl), recent_equity_orders (array containing only orders from the
        current and immediately prior Robinhood trading session with symbol, side, status, submitted_at,
        filled_at, filled_quantity, average_fill_price, market_date, and every broker-exposed order_type,
        time_in_force, limit_price, quantity, notional_usd, and fees_usd field), recent_option_orders (the same
        fields plus expiry, strike, option_type, and contract_id), and error (string). Use an empty array
when a position collection is unavailable. Every nonzero position must retain broker-exposed
quantity, average_cost, market_price, market_value, and unrealized_pnl; if any one is unavailable,
leave it absent and explain the omission in error. fees_usd and order economics must likewise remain
absent when the MCP result does not expose them; never infer, zero-fill, or fabricate those fields.
Include equity_order_history_complete and option_order_history_complete booleans; set
each true only when the corresponding order-history tool completed successfully and the returned
array covers the current and immediately prior Robinhood trading session. Include order_id in every
order object. Set account_type to the selected account's brokerage_account_type, never its
brokerage trading type field named type. Call each order-history tool exactly once with limit=1000
and without any
created_at, state, symbol, placed_agent, order_id, chain, or other history-truncating filter. Return
every order in the unfiltered result, including older orders. If either result exposes a non-empty
continuation cursor or returns exactly 1000 orders, set that history-complete boolean false and
explain it in error. Explain every omission or incomplete history in error."""
        envelope = self._run(
            "account_snapshot",
            prompt,
            (
                "get_accounts",
                "get_portfolio",
                "get_equity_positions",
                "get_option_positions",
                "get_equity_orders",
                "get_option_orders",
            ),
            (
                "get_accounts",
                "get_portfolio",
                "get_equity_positions",
                "get_option_positions",
                "get_equity_orders",
                "get_option_orders",
            ),
            2,
        )
        payload = envelope.payload
        account_attestation = _attest_account_scope(
            envelope.calls,
            (
                "get_portfolio",
                "get_equity_positions",
                "get_option_positions",
                "get_equity_orders",
                "get_option_orders",
            ),
        )
        _assert_account_identifier_redacted(
            payload,
            account_attestation.account_id,
            "account_snapshot",
        )
        if type(payload.get("authenticated")) is not bool:
            raise RobinhoodGatewayError(
                "Robinhood Agentic authenticated field must be boolean"
            )
        if (
            not isinstance(payload.get("account_type"), str)
            or not str(payload.get("account_type", "")).strip()
        ):
            raise RobinhoodGatewayError(
                "Robinhood Agentic account_type must be a nonempty string"
            )
        if (
            str(payload.get("account_type", "")).strip().casefold()
            != account_attestation.account_type.casefold()
        ):
            raise RobinhoodGatewayError(
                "Robinhood normalized account_type is not bound to get_accounts"
            )
        if (
            type(payload.get("equity_order_history_complete")) is not bool
            or type(payload.get("option_order_history_complete")) is not bool
        ):
            raise RobinhoodGatewayError(
                "Robinhood Agentic order-history completeness fields must be boolean"
            )
        if not isinstance(payload.get("error"), str):
            raise RobinhoodGatewayError(
                "Robinhood Agentic error field must be a string"
            )
        buying_power = _nonnegative_finite_number(payload, "buying_power_usd")
        total_equity = _nonnegative_finite_number(payload, "total_equity_usd")
        portfolio_calls = _tool_calls(envelope.calls, "get_portfolio")
        portfolio_value = _mcp_result_value(portfolio_calls[0])
        if _single_decimal_field(
            portfolio_value,
            frozenset({"buying_power", "buying_power_usd"}),
            "buying_power_usd",
        ) != Decimal(str(buying_power)):
            raise RobinhoodGatewayError(
                "Robinhood normalized buying power is not bound to get_portfolio"
            )
        if _single_decimal_field(
            portfolio_value,
            frozenset(
                {
                    "equity",
                    "portfolio_value",
                    "total_equity",
                    "total_equity_usd",
                    "total_value",
                }
            ),
            "total_equity_usd",
        ) != Decimal(str(total_equity)):
            raise RobinhoodGatewayError(
                "Robinhood normalized total equity is not bound to get_portfolio"
            )
        equity_positions = payload.get("equity_positions", [])
        option_positions = payload.get("option_positions", [])
        recent_equity_orders = payload.get("recent_equity_orders", [])
        recent_option_orders = payload.get("recent_option_orders", [])
        if not all(
            isinstance(value, list)
            for value in (
                equity_positions,
                option_positions,
                recent_equity_orders,
                recent_option_orders,
            )
        ):
            raise RobinhoodGatewayError(
                "Agentic position and order-history payloads must all be arrays"
            )
        validated_equity_positions = _validated_items(
            equity_positions,
            _validated_equity_position,
        )
        validated_option_positions = _validated_items(
            option_positions,
            _validated_option_position,
        )
        validated_equity_orders = tuple(
            _validated_order(item, index, False)
            for index, item in enumerate(recent_equity_orders)
        )
        validated_option_orders = tuple(
            _validated_order(item, index, True)
            for index, item in enumerate(recent_option_orders)
        )
        equity_history_complete, option_history_complete = (
            _attest_order_history_results(envelope.calls)
        )
        if (
            payload["equity_order_history_complete"] is not equity_history_complete
            or payload["option_order_history_complete"] is not option_history_complete
        ):
            raise RobinhoodGatewayError(
                "Robinhood normalized history completeness is not bound to MCP results"
            )
        equity_position_call = _tool_calls(envelope.calls, "get_equity_positions")[0]
        option_position_call = _tool_calls(envelope.calls, "get_option_positions")[0]
        equity_order_call = _tool_calls(envelope.calls, "get_equity_orders")[0]
        option_order_call = _tool_calls(envelope.calls, "get_option_orders")[0]
        _bind_normalized_items(
            validated_equity_positions,
            tuple(
                _canonical_raw_broker_item(item, "equity_position")
                for item in _result_items(
                    equity_position_call,
                    frozenset({"equity_positions", "positions", "results"}),
                    "equity_position",
                )
            ),
            ("symbol",),
            (
                "symbol",
                "quantity",
                "average_cost",
                "market_price",
                "market_value",
                "unrealized_pnl",
            ),
            "equity_position",
        )
        _bind_normalized_items(
            validated_option_positions,
            tuple(
                _canonical_raw_broker_item(item, "option_position")
                for item in _result_items(
                    option_position_call,
                    frozenset({"option_positions", "positions", "results"}),
                    "option_position",
                )
            ),
            ("contract_id",),
            (
                "symbol",
                "contract_id",
                "quantity",
                "average_cost",
                "market_price",
                "market_value",
                "unrealized_pnl",
            ),
            "option_position",
        )
        equity_order_fields = (
            "order_id",
            "symbol",
            "side",
            "status",
            "submitted_at",
            "filled_at",
            "filled_quantity",
            "average_fill_price",
            "market_date",
        )
        raw_equity_orders = tuple(
            _canonical_raw_broker_item(item, "equity_order")
            for item in _result_items(
                equity_order_call,
                frozenset({"equity_orders", "orders", "results"}),
                "equity_order",
            )
        )
        raw_option_orders = tuple(
            _canonical_raw_broker_item(item, "option_order")
            for item in _result_items(
                option_order_call,
                frozenset({"option_orders", "orders", "results"}),
                "option_order",
            )
        )
        _bind_normalized_items(
            validated_equity_orders,
            raw_equity_orders,
            ("order_id",),
            equity_order_fields,
            "equity_order",
        )
        _bind_normalized_items(
            validated_option_orders,
            raw_option_orders,
            ("order_id",),
            (
                *equity_order_fields,
                "expiry",
                "strike",
                "option_type",
                "contract_id",
            ),
            "option_order",
        )
        optional_order_economics = (
            "order_type",
            "time_in_force",
            "limit_price",
            "quantity",
            "notional_usd",
            "fees_usd",
        )
        _bind_optional_item_fields(
            validated_equity_orders,
            raw_equity_orders,
            "order_id",
            optional_order_economics,
            "equity_order",
        )
        _bind_optional_item_fields(
            validated_option_orders,
            raw_option_orders,
            "order_id",
            optional_order_economics,
            "option_order",
        )
        return AccountSnapshot(
            authenticated=payload.get("authenticated") is True,
            account_type=str(payload.get("account_type", "")),
            buying_power_usd=buying_power,
            total_equity_usd=total_equity,
            equity_positions=validated_equity_positions,
            option_positions=validated_option_positions,
            recent_equity_orders=validated_equity_orders,
            recent_option_orders=validated_option_orders,
            equity_order_history_complete=payload.get("equity_order_history_complete")
            is True,
            option_order_history_complete=payload.get("option_order_history_complete")
            is True,
            error=str(payload.get("error", "")),
            account_hash=hashlib.sha256(
                account_attestation.account_id.encode("utf-8")
            ).hexdigest(),
        )

    def get_equity_execution_snapshot(
        self,
        intent: LiveExecutionIntent,
    ) -> EquityExecutionSnapshot:
        if intent.instrument != "equity" or intent.side != "buy":
            raise RobinhoodGatewayError(
                "Equity execution snapshots are limited to long-equity entries"
            )
        if not SYMBOL_PATTERN.fullmatch(intent.symbol) or not SYMBOL_PATTERN.fullmatch(
            intent.analysis_symbol
        ):
            raise RobinhoodGatewayError(
                "Equity execution snapshot requires valid execution and analysis symbols"
            )
        if getattr(self, "_deterministic_mcp_call", None) is not None:
            return self._get_equity_snapshot_deterministically(intent)
        prompt = f"""Use only Robinhood Trading MCP tools get_equity_quotes and
get_equity_tradability. Do not call account, portfolio, order-history, review, place, replace,
cancel, watchlist, scan, shell, browser, search, or any other tool. Request current quotes and
tradability for execution symbol {intent.symbol} and analysis symbol {intent.analysis_symbol}; when
the symbols are identical, one quote and tradability lookup may supply both objects. Preserve the
quote provider's update time and convert it to a timezone-aware ISO-8601 observed_at value. Never
return account identifiers or credentials. Return only JSON with source exactly
{EQUITY_SNAPSHOT_SOURCE!r}, execution_quote, and analysis_quote. Each quote object must contain only
symbol, bid_price, ask_price, last_price, observed_at, and tradable. Missing quote timestamps,
prices, or tradability must remain missing or false; never infer or fabricate them."""
        envelope = self._run(
            "equity_execution_snapshot",
            prompt,
            ("get_equity_quotes", "get_equity_tradability"),
            ("get_equity_quotes", "get_equity_tradability"),
            2,
        )
        snapshot = _equity_execution_snapshot(envelope.payload, intent)
        _attest_equity_execution_snapshot(envelope.calls, intent, snapshot)
        return snapshot

    def cancel_order(
        self,
        instrument: str,
        order_id: str,
    ) -> GatewayCancelResult:
        """Cancel one exact open order through the official Agentic MCP only."""
        normalized_order_id = order_id.strip()
        if (
            not normalized_order_id
            or len(normalized_order_id) > 256
            or any(character.isspace() for character in normalized_order_id)
        ):
            raise RobinhoodGatewayError("Cancellation requires a safe broker order_id")
        if instrument == "equity":
            cancel_tool = "cancel_equity_order"
        elif instrument == "option":
            cancel_tool = "cancel_option_order"
        else:
            raise RobinhoodGatewayError(
                f"Unsupported cancellation instrument: {instrument!r}"
            )
        if self._deterministic_mcp_call is None:
            raise RobinhoodGatewayError(
                "Live cancellation requires deterministic parent-side MCP"
            )
        if instrument != "equity":
            raise RobinhoodGatewayError(
                "Deterministic live cancellation is currently equity-only"
            )
        try:
            call = self._call_deterministic_mcp(
                cancel_tool,
                {"order_id": normalized_order_id},
                self._write_timeout_seconds,
            )
            result = _mcp_result_value(call)
            observed_order_id = _single_string_field(
                result,
                ORDER_ID_FIELDS,
                "order_id",
            )
            if observed_order_id != normalized_order_id:
                raise RobinhoodGatewayError(
                    "Deterministic Robinhood cancellation result changed "
                    "the exact order ID"
                )
            status = _single_string_field(
                result,
                ORDER_STATUS_FIELDS,
                "status",
            ).lower()
            if status not in RECOGNIZED_ORDER_STATUSES | {
                "canceling",
                "cancelling",
            }:
                raise RobinhoodGatewayError(
                    "Deterministic Robinhood cancellation status is unknown"
                )
            return GatewayCancelResult(
                cancel_requested=True,
                order_id=normalized_order_id,
                status=status,
                warnings=_direct_result_warnings(result),
                error="",
                observed_tools=(cancel_tool,),
            )
        except RobinhoodGatewayError as error:
            raise RobinhoodCancellationAmbiguousError(
                "Deterministic Robinhood cancellation has an unknown "
                "broker outcome; poll order history before another attempt"
            ) from error

    def place_order(
        self,
        intent: LiveExecutionIntent,
        paper_twin_record_hash: str,
        *,
        pre_submit_guard: Callable[[], datetime] | None = None,
    ) -> GatewayOrderResult:
        if not SYMBOL_PATTERN.fullmatch(intent.symbol):
            raise RobinhoodGatewayError(f"Invalid order symbol: {intent.symbol!r}")
        if intent.side not in {"buy", "sell"}:
            raise RobinhoodGatewayError(f"Invalid order side: {intent.side!r}")
        if not math.isfinite(intent.notional_usd) or not math.isfinite(intent.quantity):
            raise RobinhoodGatewayError("Order amount must be finite")
        if intent.notional_usd <= 0.0 and intent.quantity <= 0.0:
            raise RobinhoodGatewayError(
                "Order requires positive notional_usd or quantity"
            )
        if intent.instrument == "equity" and intent.side == "buy":
            if (
                intent.order_type != "limit"
                or not math.isfinite(intent.limit_price)
                or intent.limit_price <= 0.0
                or intent.execution_snapshot is None
            ):
                raise RobinhoodGatewayError(
                    "Long-equity entries require a validated snapshot and positive limit_price"
                )
        if intent.instrument not in {"equity", "option"}:
            raise RobinhoodGatewayError(
                f"Unsupported instrument: {intent.instrument!r}"
            )
        if intent.instrument != "equity":
            raise RobinhoodGatewayError(
                "Deterministic live execution is currently equity-only"
            )
        if pre_submit_guard is None:
            raise RobinhoodGatewayError(
                "Deterministic placement requires the final signed-authority guard"
            )
        self._validate_pre_submit_guard(pre_submit_guard)
        if getattr(self, "_deterministic_mcp_call", None) is None:
            raise RobinhoodGatewayError(
                "Live placement requires deterministic parent-side MCP"
            )
        return self._place_equity_order_deterministically(
            intent,
            pre_submit_guard,
        )
