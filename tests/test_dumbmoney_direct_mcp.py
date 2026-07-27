from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
import requests

from dopey_live import service as live_service
from dopey_live import robinhood_gateway as gateway_module
from dopey_live.robinhood_gateway import (
    RobinhoodAgenticGateway,
    RobinhoodGatewayError,
    RobinhoodPlacementAmbiguousError,
)
from dopey_live.robinhood_mcp_direct import DeterministicRobinhoodMcpClient


TOKEN = "sealed-robinhood-profile"
ACCOUNT_ID = "agentic-account-1"
ACCOUNT_HASH = hashlib.sha256(ACCOUNT_ID.encode()).hexdigest()


@dataclass
class FakeResponse:
    status_code: int
    payload: dict[str, Any] | None
    headers: dict[str, str]

    @property
    def content(self) -> bytes:
        if self.payload is None:
            return b""
        return json.dumps(
            self.payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()


class FakeSession:
    def __init__(
        self,
        *,
        drift_schema: bool = False,
        fail_after_place_call: bool = False,
    ) -> None:
        self.trust_env = True
        self.drift_schema = drift_schema
        self.fail_after_place_call = fail_after_place_call
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        payload = kwargs.get("json")
        if method == "DELETE":
            return FakeResponse(202, None, {})
        if payload["method"] == "initialize":
            return FakeResponse(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "serverInfo": {"name": "robinhood", "version": "1"},
                    },
                },
                {
                    "Content-Type": "application/json",
                    "Mcp-Session-Id": "session-1",
                },
            )
        if payload["method"] == "notifications/initialized":
            return FakeResponse(202, None, {})
        if payload["method"] == "tools/list":
            properties = {
                "side": {"type": "string"},
                "amount": {"type": "number"},
                "symbol": {"type": "string"},
                "quantity": {"type": "number"},
                "order_type": {"type": "string"},
                "limit_price": {"type": "number"},
                "time_in_force": {"type": "string"},
            }
            if self.drift_schema:
                properties["destination"] = {"type": "string"}
            return FakeResponse(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "tools": [
                            {
                                "name": "get_accounts",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                    "required": [],
                                },
                            },
                            {
                                "name": "place_equity_order",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": properties,
                                    "required": ["side", "symbol", "order_type"],
                                },
                            },
                        ]
                    },
                },
                {"Content-Type": "application/json"},
            )
        assert payload["method"] == "tools/call"
        if payload["params"]["name"] == "get_accounts":
            return FakeResponse(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "structuredContent": {
                            "accounts": [
                                {
                                    "account_number": ACCOUNT_ID,
                                    "account_label": "Agentic",
                                    "brokerage_account_type": "individual",
                                }
                            ]
                        },
                        "isError": False,
                    },
                },
                {"Content-Type": "application/json"},
            )
        if self.fail_after_place_call:
            raise requests.ConnectionError("connection lost after request write")
        return FakeResponse(
            200,
            {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "structuredContent": {
                        **payload["params"]["arguments"],
                        "placed": True,
                        "order_id": "order-1",
                        "status": "queued",
                    },
                    "isError": False,
                },
            },
            {"Content-Type": "application/json"},
        )


class ReadSchemaSession:
    def __init__(self, *, type_drift: bool) -> None:
        self.trust_env = True
        self.type_drift = type_drift
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        payload = kwargs.get("json")
        if method == "DELETE":
            return FakeResponse(202, None, {})
        if payload["method"] == "initialize":
            return FakeResponse(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                    },
                },
                {
                    "Content-Type": "application/json",
                    "Mcp-Session-Id": "read-session-1",
                },
            )
        if payload["method"] == "notifications/initialized":
            return FakeResponse(202, None, {})
        if payload["method"] == "tools/list":
            return FakeResponse(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "tools": [
                            {
                                "name": "get_portfolio",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "account_number": {
                                            "type": (
                                                "integer"
                                                if self.type_drift
                                                else "string"
                                            )
                                        }
                                    },
                                    "required": ["account_number"],
                                },
                            }
                        ]
                    },
                },
                {"Content-Type": "application/json"},
            )
        assert payload["method"] == "tools/call"
        return FakeResponse(
            200,
            {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "structuredContent": {
                        "buying_power": "100",
                        "total_equity": "100",
                    },
                    "isError": False,
                },
            },
            {"Content-Type": "application/json"},
        )


def _place_arguments() -> dict[str, Any]:
    return {
        "side": "buy",
        "symbol": "SPY",
        "quantity": 0.125,
        "order_type": "limit",
        "limit_price": 600.00,
        "time_in_force": "day",
    }


class ParentReadTransport:
    def __init__(
        self,
        *,
        account_id: str = ACCOUNT_ID,
        buying_power: Any = "1000.00",
        total_equity: Any = "1250.00",
        equity_positions: list[dict[str, Any]] | None = None,
        quote_observed_at: str = "2099-01-01T00:00:00Z",
        extra_quote_symbol: str = "",
        history_next: str | None = None,
        fail_tool: str = "",
    ) -> None:
        self.account_id = account_id
        self.buying_power = buying_power
        self.total_equity = total_equity
        self.equity_positions = [] if equity_positions is None else equity_positions
        self.quote_observed_at = quote_observed_at
        self.extra_quote_symbol = extra_quote_symbol
        self.history_next = history_next
        self.fail_tool = fail_tool
        self.calls: list[tuple[str, dict[str, Any], Any]] = []

    def __call__(
        self,
        tool: str,
        arguments: dict[str, Any],
        _timeout: int,
        pre_call_guard: Any,
    ) -> dict[str, Any]:
        self.calls.append((tool, dict(arguments), pre_call_guard))
        if tool == self.fail_tool:
            raise RobinhoodGatewayError("parent read failed")
        if pre_call_guard is not None:
            raise AssertionError("read calls must not carry a write guard")
        if tool == "get_accounts":
            value: dict[str, Any] = {
                "accounts": [
                    {
                        "account_number": self.account_id,
                        "account_label": "Agentic",
                        "brokerage_account_type": "individual",
                    }
                ]
            }
        elif tool == "get_portfolio":
            value = {
                "buying_power": self.buying_power,
                "total_equity": self.total_equity,
            }
        elif tool == "get_equity_positions":
            value = {"positions": self.equity_positions}
        elif tool == "get_option_positions":
            value = {"positions": []}
        elif tool in {"get_equity_orders", "get_option_orders"}:
            value = {
                "orders": [],
                "history_complete": True,
                "next": self.history_next,
            }
        elif tool == "get_equity_quotes":
            symbols = [
                *arguments["symbols"],
                *([self.extra_quote_symbol] if self.extra_quote_symbol else []),
            ]
            value = {
                "quotes": [
                    {
                        "symbol": symbol,
                        "bid_price": "99.90",
                        "ask_price": "100.00",
                        "last_price": "99.95",
                        "observed_at": self.quote_observed_at,
                    }
                    for symbol in symbols
                ]
            }
        elif tool == "get_equity_tradability":
            symbols = [
                *arguments["symbols"],
                *([self.extra_quote_symbol] if self.extra_quote_symbol else []),
            ]
            value = {
                "results": [{"symbol": symbol, "tradable": True} for symbol in symbols]
            }
        else:
            raise AssertionError(f"unexpected tool: {tool}")
        return {"structuredContent": value, "isError": False}


def test_direct_mcp_makes_one_exact_call_after_schema_verification() -> None:
    session = FakeSession()
    client = DeterministicRobinhoodMcpClient(  # type: ignore[arg-type]
        TOKEN,
        ACCOUNT_HASH,
        session,
    )
    guard_observations: list[int] = []

    result = client(
        "place_equity_order",
        _place_arguments(),
        30,
        lambda: guard_observations.append(len(session.calls)),
    )

    assert result["structuredContent"]["order_id"] == "order-1"
    tool_calls = [
        call
        for call in session.calls
        if isinstance(call.get("json"), dict)
        and call["json"].get("method") == "tools/call"
        and call["json"]["params"]["name"] == "place_equity_order"
    ]
    assert len(tool_calls) == 1
    assert guard_observations == [4]
    assert tool_calls[0]["json"]["params"] == {
        "name": "place_equity_order",
        "arguments": _place_arguments(),
    }
    assert session.trust_env is False
    assert all(call["allow_redirects"] is False for call in session.calls)
    assert all(
        call["headers"]["Authorization"] == f"Bearer {TOKEN}" for call in session.calls
    )


def test_direct_mcp_blocks_schema_drift_before_the_write_call() -> None:
    session = FakeSession(drift_schema=True)
    client = DeterministicRobinhoodMcpClient(  # type: ignore[arg-type]
        TOKEN,
        ACCOUNT_HASH,
        session,
    )

    with pytest.raises(RobinhoodGatewayError, match="schema drifted"):
        client("place_equity_order", _place_arguments(), 30)

    assert not any(
        isinstance(call.get("json"), dict)
        and call["json"].get("method") == "tools/call"
        for call in session.calls
    )


def test_direct_mcp_rejects_notional_mode_and_unknown_tools_locally() -> None:
    client = DeterministicRobinhoodMcpClient(
        TOKEN,
        ACCOUNT_HASH,
        FakeSession(),  # type: ignore[arg-type]
    )
    with pytest.raises(RobinhoodGatewayError, match="exact quantity mode"):
        client(
            "place_equity_order",
            {
                "side": "buy",
                "symbol": "SPY",
                "amount": 10.0,
                "order_type": "market",
            },
            30,
        )
    with pytest.raises(RobinhoodGatewayError, match="outside the sealed allowlist"):
        client("place_option_order", {}, 30)


def test_direct_read_schema_type_drift_blocks_and_closes_session() -> None:
    session = ReadSchemaSession(type_drift=True)
    client = DeterministicRobinhoodMcpClient(  # type: ignore[arg-type]
        TOKEN,
        ACCOUNT_HASH,
        session,
    )

    with pytest.raises(RobinhoodGatewayError, match="property type drifted"):
        client(
            "get_portfolio",
            {"account_number": ACCOUNT_ID},
            30,
        )

    assert not any(
        isinstance(call.get("json"), dict)
        and call["json"].get("method") == "tools/call"
        for call in session.calls
    )
    assert [call["method"] for call in session.calls].count("DELETE") == 1


def test_direct_mcp_account_mismatch_blocks_before_place() -> None:
    session = FakeSession()
    client = DeterministicRobinhoodMcpClient(  # type: ignore[arg-type]
        TOKEN,
        "f" * 64,
        session,
    )

    with pytest.raises(RobinhoodGatewayError, match="pinned Agentic account"):
        client(
            "place_equity_order",
            _place_arguments(),
            30,
            lambda: None,
        )

    assert not any(
        isinstance(call.get("json"), dict)
        and call["json"].get("method") == "tools/call"
        and call["json"]["params"]["name"] == "place_equity_order"
        for call in session.calls
    )


def test_direct_mcp_connection_loss_after_place_call_is_not_retried() -> None:
    session = FakeSession(fail_after_place_call=True)
    client = DeterministicRobinhoodMcpClient(  # type: ignore[arg-type]
        TOKEN,
        ACCOUNT_HASH,
        session,
    )

    with pytest.raises(RobinhoodGatewayError, match="transport failed"):
        client(
            "place_equity_order",
            _place_arguments(),
            30,
            lambda: None,
        )

    place_calls = [
        call
        for call in session.calls
        if isinstance(call.get("json"), dict)
        and call["json"].get("method") == "tools/call"
        and call["json"]["params"]["name"] == "place_equity_order"
    ]
    assert len(place_calls) == 1


def test_gateway_deterministically_reviews_then_places_exact_quantity_once() -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    runner_calls: list[bool] = []

    def direct_call(
        tool: str,
        arguments: dict[str, Any],
        _timeout: int,
        pre_call_guard: Any,
    ) -> dict[str, Any]:
        if tool == "place_equity_order":
            assert pre_call_guard is not None
            pre_call_guard()
        else:
            assert pre_call_guard is None
        calls.append((tool, arguments))
        common = {
            **arguments,
            "warnings": [],
        }
        if tool == "review_equity_order":
            return {
                "structuredContent": {
                    **common,
                    "review_succeeded": True,
                }
            }
        return {
            "structuredContent": {
                **common,
                "placed": True,
                "order_id": "order-1",
                "status": "queued",
            }
        }

    gateway = RobinhoodAgenticGateway(
        lambda *_args, **_kwargs: runner_calls.append(True),  # type: ignore[arg-type]
        60,
        write_timeout_seconds=30,
        expected_account_hash=ACCOUNT_HASH,
        deterministic_mcp_call=direct_call,
    )
    intent = SimpleNamespace(
        instrument="equity",
        side="buy",
        symbol="SPY",
        quantity=0.125,
        notional_usd=75.0,
        order_type="limit",
        limit_price=600.0,
        time_in_force="day",
        extended_hours=False,
        execution_snapshot=object(),
        intent_id="intent-1",
    )
    guard_calls: list[bool] = []

    result = gateway.place_order(  # type: ignore[arg-type]
        intent,
        "a" * 64,
        pre_submit_guard=lambda: (
            guard_calls.append(True)
            or datetime.now(timezone.utc) + timedelta(seconds=60)
        ),
    )

    expected = _place_arguments()
    assert calls == [
        ("review_equity_order", expected),
        ("place_equity_order", expected),
    ]
    assert len(guard_calls) == 2
    assert result.placed is True
    assert result.order_id == "order-1"
    assert runner_calls == []


def test_gateway_marks_post_call_connection_loss_ambiguous_without_retry() -> None:
    calls: list[str] = []
    guard_calls: list[bool] = []

    def direct_call(
        tool: str,
        arguments: dict[str, Any],
        _timeout: int,
        pre_call_guard: Any,
    ) -> dict[str, Any]:
        calls.append(tool)
        if tool == "review_equity_order":
            return {
                "structuredContent": {
                    **arguments,
                    "review_succeeded": True,
                    "warnings": [],
                }
            }
        assert pre_call_guard is not None
        pre_call_guard()
        raise RobinhoodGatewayError("connection lost after write")

    gateway = RobinhoodAgenticGateway(
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("model runner must never receive broker authority")
        ),
        60,
        write_timeout_seconds=30,
        expected_account_hash=ACCOUNT_HASH,
        deterministic_mcp_call=direct_call,
    )
    intent = SimpleNamespace(
        instrument="equity",
        side="buy",
        symbol="SPY",
        quantity=0.125,
        notional_usd=75.0,
        order_type="limit",
        limit_price=600.0,
        time_in_force="day",
        extended_hours=False,
        execution_snapshot=object(),
        intent_id="intent-loss",
    )

    with pytest.raises(
        RobinhoodPlacementAmbiguousError,
        match="unknown broker outcome",
    ):
        gateway.place_order(  # type: ignore[arg-type]
            intent,
            "a" * 64,
            pre_submit_guard=lambda: (
                guard_calls.append(True)
                or datetime.now(timezone.utc) + timedelta(seconds=60)
            ),
        )

    assert calls == ["review_equity_order", "place_equity_order"]
    assert len(guard_calls) == 2


def test_parent_only_reads_exact_account_and_quote_sequences_without_model() -> None:
    transport = ParentReadTransport()
    runner_calls: list[bool] = []
    gateway = RobinhoodAgenticGateway(
        lambda *_args, **_kwargs: runner_calls.append(True),  # type: ignore[arg-type]
        60,
        expected_account_hash=ACCOUNT_HASH,
        deterministic_mcp_call=transport,
    )

    account = gateway.get_account_snapshot()
    intent = SimpleNamespace(
        instrument="equity",
        side="buy",
        symbol="SPY",
        analysis_symbol="SPY",
    )
    quote = gateway.get_equity_execution_snapshot(intent)  # type: ignore[arg-type]

    assert account.account_hash == ACCOUNT_HASH
    assert account.authenticated is True
    assert quote.execution_quote.symbol == "SPY"
    assert runner_calls == []
    assert [(tool, arguments) for tool, arguments, _ in transport.calls] == [
        ("get_accounts", {}),
        ("get_portfolio", {"account_number": ACCOUNT_ID}),
        ("get_equity_positions", {"account_number": ACCOUNT_ID}),
        ("get_option_positions", {"account_number": ACCOUNT_ID}),
        (
            "get_equity_orders",
            {"account_number": ACCOUNT_ID, "limit": 1000},
        ),
        (
            "get_option_orders",
            {"account_number": ACCOUNT_ID, "limit": 1000},
        ),
        ("get_equity_quotes", {"symbols": ["SPY"]}),
        ("get_equity_tradability", {"symbols": ["SPY"]}),
    ]


def test_parent_read_wrong_account_stops_before_scoped_calls() -> None:
    transport = ParentReadTransport(account_id="other-agentic-account")
    gateway = RobinhoodAgenticGateway(
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("model fallback is prohibited")
        ),
        60,
        expected_account_hash=ACCOUNT_HASH,
        deterministic_mcp_call=transport,
    )

    with pytest.raises(RobinhoodGatewayError, match="pinned Agentic account"):
        gateway.get_account_snapshot()

    assert [tool for tool, _, _ in transport.calls] == ["get_accounts"]


@pytest.mark.parametrize(
    ("buying_power", "total_equity"),
    [
        ("-1", "100"),
        ("100", "1e9999"),
    ],
)
def test_parent_read_rejects_negative_or_overflow_portfolio(
    buying_power: str,
    total_equity: str,
) -> None:
    transport = ParentReadTransport(
        buying_power=buying_power,
        total_equity=total_equity,
    )
    gateway = RobinhoodAgenticGateway(
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("model fallback is prohibited")
        ),
        60,
        expected_account_hash=ACCOUNT_HASH,
        deterministic_mcp_call=transport,
    )

    with pytest.raises(RobinhoodGatewayError, match="finite and nonnegative"):
        gateway.get_account_snapshot()


def test_parent_read_does_not_zero_fill_missing_position_economics() -> None:
    transport = ParentReadTransport(
        equity_positions=[
            {
                "symbol": "SPY",
                "quantity": "1",
                "market_price": "100",
                "market_value": "100",
                "unrealized_pnl": "0",
            }
        ]
    )
    gateway = RobinhoodAgenticGateway(
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("model fallback is prohibited")
        ),
        60,
        expected_account_hash=ACCOUNT_HASH,
        deterministic_mcp_call=transport,
    )

    with pytest.raises(RobinhoodGatewayError, match="position.average_cost"):
        gateway.get_account_snapshot()


def test_parent_read_rejects_conflicting_position_aliases() -> None:
    transport = ParentReadTransport(
        equity_positions=[
            {
                "symbol": "SPY",
                "quantity": "1",
                "average_cost": "99",
                "average_price": "100",
                "market_price": "100",
                "market_value": "100",
                "unrealized_pnl": "1",
            }
        ]
    )
    gateway = RobinhoodAgenticGateway(
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("model fallback is prohibited")
        ),
        60,
        expected_account_hash=ACCOUNT_HASH,
        deterministic_mcp_call=transport,
    )

    with pytest.raises(RobinhoodGatewayError, match="conflicting numeric aliases"):
        gateway.get_account_snapshot()


def test_parent_read_preserves_incomplete_history_as_blocking_evidence() -> None:
    transport = ParentReadTransport(history_next="next-page")
    gateway = RobinhoodAgenticGateway(
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("model fallback is prohibited")
        ),
        60,
        expected_account_hash=ACCOUNT_HASH,
        deterministic_mcp_call=transport,
    )

    account = gateway.get_account_snapshot()

    assert account.equity_order_history_complete is False
    assert account.option_order_history_complete is False
    assert "equity_order_history_incomplete" in account.error
    assert "option_order_history_incomplete" in account.error


def test_parent_read_rejects_naive_quote_timestamp_and_never_falls_back() -> None:
    transport = ParentReadTransport(
        quote_observed_at="2099-01-01T00:00:00",
    )
    runner_calls: list[bool] = []
    gateway = RobinhoodAgenticGateway(
        lambda *_args, **_kwargs: runner_calls.append(True),  # type: ignore[arg-type]
        60,
        expected_account_hash=ACCOUNT_HASH,
        deterministic_mcp_call=transport,
    )
    intent = SimpleNamespace(
        instrument="equity",
        side="buy",
        symbol="SPY",
        analysis_symbol="SPY",
    )

    with pytest.raises(RobinhoodGatewayError, match="timezone-aware"):
        gateway.get_equity_execution_snapshot(intent)  # type: ignore[arg-type]

    assert runner_calls == []


def test_parent_read_rejects_unrequested_quote_symbol() -> None:
    transport = ParentReadTransport(extra_quote_symbol="QQQ")
    gateway = RobinhoodAgenticGateway(
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("model fallback is prohibited")
        ),
        60,
        expected_account_hash=ACCOUNT_HASH,
        deterministic_mcp_call=transport,
    )
    intent = SimpleNamespace(
        instrument="equity",
        side="buy",
        symbol="SPY",
        analysis_symbol="SPY",
    )

    with pytest.raises(RobinhoodGatewayError, match="unrequested symbol"):
        gateway.get_equity_execution_snapshot(intent)  # type: ignore[arg-type]


def test_parent_read_transport_failure_never_falls_back_to_model() -> None:
    transport = ParentReadTransport(fail_tool="get_accounts")
    runner_calls: list[bool] = []
    gateway = RobinhoodAgenticGateway(
        lambda *_args, **_kwargs: runner_calls.append(True),  # type: ignore[arg-type]
        60,
        expected_account_hash=ACCOUNT_HASH,
        deterministic_mcp_call=transport,
    )

    with pytest.raises(RobinhoodGatewayError, match="parent read failed"):
        gateway.get_account_snapshot()

    assert runner_calls == []


def test_operator_default_gateway_cannot_place_or_cancel_through_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner_calls: list[bool] = []
    monkeypatch.setattr(
        live_service.subprocess,
        "run",
        lambda *_args, **_kwargs: runner_calls.append(True),
    )
    monkeypatch.setattr(
        gateway_module.shutil,
        "which",
        lambda executable: sys.executable if executable == "codex" else None,
    )
    gateway = live_service.default_gateway()
    intent = SimpleNamespace(
        instrument="equity",
        side="sell",
        symbol="SPY",
        quantity=0.125,
        notional_usd=0.0,
        order_type="limit",
        limit_price=600.0,
        time_in_force="day",
        extended_hours=False,
        execution_snapshot=None,
        intent_id="legacy-denied",
    )

    with pytest.raises(
        RobinhoodGatewayError,
        match="deterministic parent-side MCP",
    ):
        gateway.place_order(  # type: ignore[arg-type]
            intent,
            "a" * 64,
            pre_submit_guard=lambda: datetime.now(timezone.utc) + timedelta(seconds=60),
        )
    with pytest.raises(
        RobinhoodGatewayError,
        match="deterministic parent-side MCP",
    ):
        gateway.cancel_order("equity", "order-1")

    assert runner_calls == []
