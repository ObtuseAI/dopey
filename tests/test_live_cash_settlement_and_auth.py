"""Cash-account settlement model + MCP auth-failure classification.

The agentic account is a CASH account: sale proceeds settle T+1. The system
must size entries with settled funds only (a buy funded by unsettled proceeds
becomes a good-faith violation the moment that position is sold early - and
the owner can sell at any time). Fail-closed on unknown history. Separately,
an expired Robinhood MCP OAuth session must classify as auth_required and
raise the typed non-retryable error instead of the misleading
"required MCP calls were not observed".
"""
from __future__ import annotations

from datetime import date

import pytest

from dopey_live.models import AccountSnapshot
from dopey_live.robinhood_gateway import (
    MCP_AUTH_REQUIRED_SIGNATURE,
    _mcp_attach_failure_kind,
    reauth_remediation,
)
from dopey_live.settlement import (
    SettlementModelError,
    equity_settlement_date,
    estimate_settled_funds,
)


def _account(
    buying_power: float,
    orders: tuple[dict, ...] = (),
    history_complete: bool = True,
) -> AccountSnapshot:
    return AccountSnapshot(
        authenticated=True,
        account_type="individual",
        buying_power_usd=buying_power,
        total_equity_usd=buying_power,
        equity_positions=(),
        option_positions=(),
        recent_equity_orders=orders,
        recent_option_orders=(),
        equity_order_history_complete=history_complete,
        option_order_history_complete=True,
        error="",
    )


def _sell(order_id: str, market_date: str, quantity: float, price: float, status: str = "filled") -> dict:
    return {
        "order_id": order_id,
        "symbol": "GOOGL",
        "side": "sell",
        "status": status,
        "market_date": market_date,
        "filled_quantity": quantity,
        "average_fill_price": price,
    }


# ---------- settlement date arithmetic ----------


def test_weekday_sale_settles_next_trading_day() -> None:
    # Wednesday 2026-07-22 -> Thursday 2026-07-23
    assert equity_settlement_date(date(2026, 7, 22)) == date(2026, 7, 23)


def test_friday_sale_settles_monday() -> None:
    # Friday 2026-07-24 -> Monday 2026-07-27
    assert equity_settlement_date(date(2026, 7, 24)) == date(2026, 7, 27)


def test_sale_before_holiday_rolls_past_it() -> None:
    # Thursday 2026-07-02; Friday 2026-07-03 is an XNYS holiday -> Monday 2026-07-06
    assert equity_settlement_date(date(2026, 7, 2)) == date(2026, 7, 6)


# ---------- settled-funds estimate ----------


def test_unsettled_sale_reduces_spendable() -> None:
    account = _account(1000.0, (_sell("s1", "2026-07-22", 2.0, 300.0),))
    estimate = estimate_settled_funds(account, date(2026, 7, 22))
    assert estimate.unsettled_sale_proceeds_usd == 600.0
    assert estimate.spendable_settled_usd == 400.0
    assert estimate.unsettled_sales[0].settles_on == "2026-07-23"
    assert estimate.fail_closed_reason == ""


def test_settled_sale_frees_spendable_next_trading_day() -> None:
    account = _account(1000.0, (_sell("s1", "2026-07-22", 2.0, 300.0),))
    estimate = estimate_settled_funds(account, date(2026, 7, 23))
    assert estimate.unsettled_sale_proceeds_usd == 0.0
    assert estimate.spendable_settled_usd == 1000.0


def test_friday_sale_stays_unsettled_through_weekend() -> None:
    account = _account(500.0, (_sell("s1", "2026-07-24", 1.0, 200.0),))
    # Saturday and Sunday: still unsettled; Monday: settled.
    for as_of in (date(2026, 7, 24), date(2026, 7, 25), date(2026, 7, 26)):
        estimate = estimate_settled_funds(account, as_of)
        assert estimate.spendable_settled_usd == 300.0, as_of
    assert estimate_settled_funds(account, date(2026, 7, 27)).spendable_settled_usd == 500.0


def test_incomplete_order_history_fails_closed_to_zero() -> None:
    account = _account(1000.0, (), history_complete=False)
    estimate = estimate_settled_funds(account, date(2026, 7, 22))
    assert estimate.spendable_settled_usd == 0.0
    assert estimate.fail_closed_reason == "equity_order_history_incomplete_recent_sales_unknown"


def test_spendable_never_negative() -> None:
    account = _account(100.0, (_sell("s1", "2026-07-22", 10.0, 50.0),))
    estimate = estimate_settled_funds(account, date(2026, 7, 22))
    assert estimate.spendable_settled_usd == 0.0


def test_buys_and_unfilled_sells_do_not_count() -> None:
    orders = (
        {**_sell("b1", "2026-07-22", 2.0, 300.0), "side": "buy"},
        _sell("s2", "2026-07-22", 2.0, 300.0, status="cancelled"),
        _sell("s3", "2026-07-22", 0.0, 0.0),  # zero-proceeds fill records nothing
    )
    estimate = estimate_settled_funds(_account(1000.0, orders), date(2026, 7, 22))
    assert estimate.unsettled_sale_proceeds_usd == 0.0
    assert estimate.spendable_settled_usd == 1000.0


def test_partial_fill_counts_filled_portion() -> None:
    account = _account(1000.0, (_sell("s1", "2026-07-22", 1.5, 100.0, status="partially_filled"),))
    estimate = estimate_settled_funds(account, date(2026, 7, 22))
    assert estimate.unsettled_sale_proceeds_usd == 150.0


def test_invalid_sale_market_date_raises() -> None:
    account = _account(1000.0, (_sell("s1", "not-a-date", 1.0, 100.0),))
    with pytest.raises(SettlementModelError):
        estimate_settled_funds(account, date(2026, 7, 22))


def test_old_settled_sales_are_ignored_by_lookback() -> None:
    account = _account(1000.0, (_sell("s1", "2026-07-01", 1.0, 100.0),))
    estimate = estimate_settled_funds(account, date(2026, 7, 22))
    assert estimate.unsettled_sale_proceeds_usd == 0.0


# ---------- MCP auth-failure classification ----------


def test_auth_required_stderr_classifies_as_auth_required() -> None:
    stderr = (
        "2026-07-21T20:11:00Z ERROR codex_core::tools::router: error=... "
        "MCP startup failed: handshaking with MCP server failed: Send message error "
        f"Transport [...] error: {MCP_AUTH_REQUIRED_SIGNATURE}, when send initialize request"
    )
    assert _mcp_attach_failure_kind(stderr) == "auth_required"


def test_attach_failure_without_auth_is_transient_class() -> None:
    assert (
        _mcp_attach_failure_kind("ERROR ...: MCP startup failed: connection refused")
        == "attach_failure"
    )


def test_clean_stderr_classifies_none() -> None:
    assert _mcp_attach_failure_kind("") is None
    assert _mcp_attach_failure_kind("INFO thread started") is None


def test_remediation_names_the_login_command() -> None:
    text = reauth_remediation()
    assert "codex mcp login robinhood-trading" in text


# ---------- interactive-consent classification ----------


def test_cancelled_tool_call_classifies_as_consent_required() -> None:
    import json as _json

    from dopey_live.robinhood_gateway import (
        RobinhoodConsentRequiredError,
        _mcp_transcript,
        consent_remediation,
    )

    lines = [
        {"type": "thread.started"},
        {"type": "item.started", "item": {"type": "mcp_tool_call", "id": "c1", "server": "robinhood-trading", "tool": "get_accounts", "arguments": {}}},
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "id": "c1", "server": "robinhood-trading", "tool": "get_accounts", "arguments": {}, "status": "failed", "error": {"message": "user cancelled MCP tool call"}}},
        {"type": "turn.completed"},
    ]
    stdout = "\n".join(_json.dumps(line) for line in lines)
    with pytest.raises(RobinhoodConsentRequiredError):
        _mcp_transcript(stdout)
    assert "ATTENDED" in consent_remediation()


def test_non_cancel_failure_stays_generic_gateway_error() -> None:
    import json as _json

    from dopey_live.robinhood_gateway import (
        RobinhoodConsentRequiredError,
        RobinhoodGatewayError,
        _mcp_transcript,
    )

    lines = [
        {"type": "thread.started"},
        {"type": "item.started", "item": {"type": "mcp_tool_call", "id": "c1", "server": "robinhood-trading", "tool": "get_accounts", "arguments": {}}},
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "id": "c1", "server": "robinhood-trading", "tool": "get_accounts", "arguments": {}, "status": "failed", "error": {"message": "server timeout"}}},
        {"type": "turn.completed"},
    ]
    stdout = "\n".join(_json.dumps(line) for line in lines)
    with pytest.raises(RobinhoodGatewayError) as excinfo:
        _mcp_transcript(stdout)
    assert not isinstance(excinfo.value, RobinhoodConsentRequiredError)
