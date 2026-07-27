"""Deterministic, model-inaccessible Robinhood MCP write transport.

The local agent never receives these tools.  This client opens one bounded
Streamable HTTP MCP session, verifies the selected tool schema, makes exactly
one typed call, and closes the session.  It has no retry path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Final

import requests

from .control import OFFICIAL_ROBINHOOD_MCP
from .robinhood_gateway import (
    READ_ONLY_ROBINHOOD_TOOLS,
    RobinhoodGatewayError,
    _agentic_account,
    _direct_call_evidence,
)


MCP_PROTOCOL_VERSION: Final[str] = "2025-06-18"
MAXIMUM_MCP_RESPONSE_BYTES: Final[int] = 2_097_152
EXPECTED_TOOL_PROPERTIES: Final[dict[str, frozenset[str]]] = {
    "review_equity_order": frozenset(
        {
            "side",
            "symbol",
            "quantity",
            "order_type",
            "limit_price",
            "time_in_force",
        }
    ),
    "place_equity_order": frozenset(
        {
            "side",
            "amount",
            "symbol",
            "quantity",
            "order_type",
            "limit_price",
            "time_in_force",
        }
    ),
    "cancel_equity_order": frozenset({"order_id"}),
}
EXPECTED_REQUIRED_PROPERTIES: Final[dict[str, frozenset[str]]] = {
    "review_equity_order": frozenset({"side", "symbol"}),
    "place_equity_order": frozenset({"side", "symbol", "order_type"}),
    "cancel_equity_order": frozenset({"order_id"}),
}
READ_ARGUMENT_CONTRACTS: Final[dict[str, dict[str, str]]] = {
    "get_accounts": {},
    "get_portfolio": {"account_number": "string"},
    "get_equity_positions": {"account_number": "string"},
    "get_option_positions": {"account_number": "string"},
    "get_equity_orders": {
        "account_number": "string",
        "limit": "integer",
    },
    "get_option_orders": {
        "account_number": "string",
        "limit": "integer",
    },
    "get_equity_quotes": {"symbols": "string_array"},
    "get_equity_tradability": {"symbols": "string_array"},
}


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RobinhoodGatewayError(f"{label} contains a duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise RobinhoodGatewayError(f"{label} contains a non-finite number: {value}")

    try:
        payload = json.loads(
            raw,
            object_pairs_hook=reject_duplicate,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RobinhoodGatewayError(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise RobinhoodGatewayError(f"{label} must be a JSON object")
    return payload


def _json_rpc_from_response(
    response: requests.Response,
    request_id: int,
) -> dict[str, Any]:
    body = bytes(response.content)
    if not 1 <= len(body) <= MAXIMUM_MCP_RESPONSE_BYTES:
        raise RobinhoodGatewayError("Robinhood MCP response size is invalid")
    content_type = response.headers.get("Content-Type", "").lower()
    candidates: list[dict[str, Any]] = []
    if "text/event-stream" in content_type:
        for line in body.splitlines():
            if not line.startswith(b"data:"):
                continue
            raw_event = line.removeprefix(b"data:").strip()
            if raw_event:
                candidates.append(_strict_json(raw_event, "Robinhood MCP SSE event"))
    elif "application/json" in content_type:
        candidates.append(_strict_json(body, "Robinhood MCP response"))
    else:
        raise RobinhoodGatewayError(
            "Robinhood MCP response Content-Type is unsupported"
        )
    matches = [
        item
        for item in candidates
        if item.get("jsonrpc") == "2.0" and item.get("id") == request_id
    ]
    if len(matches) != 1:
        raise RobinhoodGatewayError(
            "Robinhood MCP response does not bind one request ID"
        )
    message = matches[0]
    if "error" in message:
        raise RobinhoodGatewayError("Robinhood MCP returned a JSON-RPC error")
    result = message.get("result")
    if not isinstance(result, dict):
        raise RobinhoodGatewayError("Robinhood MCP result must be an object")
    return result


def _verify_tool_schema(tool: str, tools_result: dict[str, Any]) -> None:
    tools = tools_result.get("tools")
    if not isinstance(tools, list):
        raise RobinhoodGatewayError("Robinhood MCP tools/list result is invalid")
    matches = [
        item for item in tools if isinstance(item, dict) and item.get("name") == tool
    ]
    if len(matches) != 1:
        raise RobinhoodGatewayError(
            "Robinhood MCP selected tool is absent or ambiguous"
        )
    schema = matches[0].get("inputSchema")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise RobinhoodGatewayError(
            "Robinhood MCP selected tool input schema is invalid"
        )
    properties = schema.get("properties")
    required = schema.get("required", [])
    if (
        not isinstance(properties, dict)
        or frozenset(properties) != EXPECTED_TOOL_PROPERTIES[tool]
        or not isinstance(required, list)
        or not all(isinstance(item, str) for item in required)
        or frozenset(required) != EXPECTED_REQUIRED_PROPERTIES[tool]
    ):
        raise RobinhoodGatewayError(
            "Robinhood MCP selected tool schema drifted from the sealed contract"
        )


def _verify_read_tool_schema(
    tool: str,
    arguments: dict[str, Any],
    tools_result: dict[str, Any],
) -> None:
    tools = tools_result.get("tools")
    if not isinstance(tools, list):
        raise RobinhoodGatewayError("Robinhood MCP tools/list result is invalid")
    matches = [
        item for item in tools if isinstance(item, dict) and item.get("name") == tool
    ]
    if len(matches) != 1:
        raise RobinhoodGatewayError(
            "Robinhood MCP selected read tool is absent or ambiguous"
        )
    schema = matches[0].get("inputSchema")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise RobinhoodGatewayError(
            "Robinhood MCP selected read tool input schema is invalid"
        )
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    expected_contract = READ_ARGUMENT_CONTRACTS.get(tool)
    if expected_contract is None or frozenset(arguments) != frozenset(
        expected_contract
    ):
        raise RobinhoodGatewayError(
            "Robinhood MCP read arguments differ from the sealed contract"
        )
    if (
        not isinstance(properties, dict)
        or not isinstance(required, list)
        or not all(isinstance(item, str) for item in required)
        or not frozenset(arguments).issubset(properties)
        or not frozenset(required).issubset(arguments)
    ):
        raise RobinhoodGatewayError(
            "Robinhood MCP read arguments do not satisfy the live tool schema"
        )
    for field, expected_type in expected_contract.items():
        property_schema = properties.get(field)
        if not isinstance(property_schema, dict):
            raise RobinhoodGatewayError("Robinhood MCP read property schema is invalid")
        if expected_type == "string":
            valid_schema = property_schema.get("type") == "string"
            valid_value = (
                isinstance(arguments[field], str)
                and bool(arguments[field].strip())
                and len(arguments[field]) <= 512
            )
        elif expected_type == "integer":
            valid_schema = property_schema.get("type") == "integer"
            valid_value = (
                not isinstance(arguments[field], bool)
                and isinstance(arguments[field], int)
                and arguments[field] == 1_000
            )
        else:
            items = property_schema.get("items")
            valid_schema = (
                property_schema.get("type") == "array"
                and isinstance(items, dict)
                and items.get("type") == "string"
            )
            value = arguments[field]
            valid_value = (
                isinstance(value, list)
                and 1 <= len(value) <= 2
                and all(isinstance(item, str) and bool(item.strip()) for item in value)
                and value == sorted(set(value))
            )
        if not valid_schema or not valid_value:
            raise RobinhoodGatewayError(
                "Robinhood MCP read property type drifted from the sealed contract"
            )


def _verify_arguments(tool: str, arguments: dict[str, Any]) -> None:
    keys = frozenset(arguments)
    if not EXPECTED_REQUIRED_PROPERTIES[tool].issubset(keys):
        raise RobinhoodGatewayError(
            "Deterministic Robinhood MCP call lacks required arguments"
        )
    if not keys.issubset(EXPECTED_TOOL_PROPERTIES[tool]):
        raise RobinhoodGatewayError(
            "Deterministic Robinhood MCP call contains unexpected arguments"
        )
    if tool in {"review_equity_order", "place_equity_order"}:
        if "amount" in keys or "quantity" not in keys:
            raise RobinhoodGatewayError(
                "Deterministic equity orders require exact quantity mode"
            )


@dataclass
class DeterministicRobinhoodMcpClient:
    """One-shot official MCP caller unavailable to the generative subprocess."""

    bearer_token: str
    expected_account_hash: str
    session: requests.Session | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.bearer_token, str)
            or not 16 <= len(self.bearer_token) <= 16_384
            or self.bearer_token != self.bearer_token.strip()
            or any(character in self.bearer_token for character in "\r\n\0")
        ):
            raise ValueError("Robinhood MCP bearer profile is invalid")
        if (
            not isinstance(self.expected_account_hash, str)
            or len(self.expected_account_hash) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.expected_account_hash
            )
        ):
            raise ValueError("Robinhood MCP expected account hash is invalid")
        if self.session is None:
            self.session = requests.Session()
        self.session.trust_env = False

    def _request(
        self,
        method: str,
        payload: dict[str, Any] | None,
        timeout_seconds: int,
        *,
        request_id: int | None,
        session_id: str | None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if self.session is None:
            raise RobinhoodGatewayError("Robinhood MCP HTTP session is unavailable")
        headers = {
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.bearer_token}",
            "Cache-Control": "no-store",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        }
        if session_id is not None:
            headers["Mcp-Session-Id"] = session_id
        try:
            response = self.session.request(
                method,
                OFFICIAL_ROBINHOOD_MCP,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
                allow_redirects=False,
            )
        except requests.RequestException as error:
            raise RobinhoodGatewayError(
                "Robinhood MCP deterministic transport failed"
            ) from error
        if response.status_code not in {200, 202}:
            raise RobinhoodGatewayError(
                "Robinhood MCP deterministic transport returned a non-success status"
            )
        returned_session = response.headers.get("Mcp-Session-Id")
        if returned_session is not None and (
            not returned_session
            or len(returned_session) > 512
            or any(character in returned_session for character in "\r\n\0")
        ):
            raise RobinhoodGatewayError("Robinhood MCP session ID is invalid")
        if request_id is None:
            return None, returned_session
        return _json_rpc_from_response(response, request_id), returned_session

    def _call_initialized(
        self,
        tool: str,
        arguments: dict[str, Any],
        timeout_seconds: int,
        session_id: str | None,
        pre_call_guard: Callable[[], None] | None,
    ) -> dict[str, Any]:
        self._request(
            "POST",
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            },
            timeout_seconds,
            request_id=None,
            session_id=session_id,
        )
        tools_result, _ = self._request(
            "POST",
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
            timeout_seconds,
            request_id=2,
            session_id=session_id,
        )
        if tools_result is None:
            raise RobinhoodGatewayError("Robinhood MCP tools/list result is absent")
        if tool in EXPECTED_TOOL_PROPERTIES:
            _verify_tool_schema(tool, tools_result)
        else:
            _verify_read_tool_schema(tool, arguments, tools_result)
        next_request_id = 3
        if tool in EXPECTED_TOOL_PROPERTIES:
            _verify_read_tool_schema("get_accounts", {}, tools_result)
            account_result, _ = self._request(
                "POST",
                {
                    "jsonrpc": "2.0",
                    "id": next_request_id,
                    "method": "tools/call",
                    "params": {
                        "name": "get_accounts",
                        "arguments": {},
                    },
                },
                timeout_seconds,
                request_id=next_request_id,
                session_id=session_id,
            )
            if account_result is None:
                raise RobinhoodGatewayError("Robinhood MCP account proof is absent")
            account = _agentic_account(
                (
                    _direct_call_evidence(
                        "get_accounts",
                        {},
                        account_result,
                    ),
                )
            )
            if (
                hashlib.sha256(account.account_id.encode("utf-8")).hexdigest()
                != self.expected_account_hash
            ):
                raise RobinhoodGatewayError(
                    "Robinhood MCP session is not bound to the pinned Agentic account"
                )
            next_request_id += 1
        if tool == "place_equity_order":
            if pre_call_guard is None:
                raise RobinhoodGatewayError(
                    "Robinhood placement requires an immediate authority guard"
                )
            pre_call_guard()
        elif pre_call_guard is not None:
            raise RobinhoodGatewayError(
                "Immediate authority guard is only valid for placement"
            )
        call_result, _ = self._request(
            "POST",
            {
                "jsonrpc": "2.0",
                "id": next_request_id,
                "method": "tools/call",
                "params": {
                    "name": tool,
                    "arguments": dict(arguments),
                },
            },
            timeout_seconds,
            request_id=next_request_id,
            session_id=session_id,
        )
        if call_result is None:
            raise RobinhoodGatewayError("Robinhood MCP tools/call result is absent")
        return call_result

    def __call__(
        self,
        tool: str,
        arguments: dict[str, Any],
        timeout_seconds: int,
        pre_call_guard: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        if tool not in EXPECTED_TOOL_PROPERTIES and tool not in (
            READ_ONLY_ROBINHOOD_TOOLS
        ):
            raise RobinhoodGatewayError(
                "Robinhood deterministic tool is outside the sealed allowlist"
            )
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 1 <= timeout_seconds <= 60
        ):
            raise ValueError("Robinhood deterministic timeout is invalid")
        if tool in EXPECTED_TOOL_PROPERTIES:
            _verify_arguments(tool, arguments)
        elif pre_call_guard is not None:
            raise RobinhoodGatewayError(
                "Immediate authority guard is only valid for placement"
            )
        initialize, session_id = self._request(
            "POST",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "DumbMoneyDopeyRobinhood",
                        "version": "1",
                    },
                },
            },
            timeout_seconds,
            request_id=1,
            session_id=None,
        )
        try:
            if initialize is None or initialize.get("protocolVersion") != (
                MCP_PROTOCOL_VERSION
            ):
                raise RobinhoodGatewayError(
                    "Robinhood MCP protocol version is not the sealed version"
                )
            return self._call_initialized(
                tool,
                arguments,
                timeout_seconds,
                session_id,
                pre_call_guard,
            )
        finally:
            if session_id is not None:
                try:
                    self._request(
                        "DELETE",
                        None,
                        timeout_seconds,
                        request_id=None,
                        session_id=session_id,
                    )
                except RobinhoodGatewayError:
                    pass
