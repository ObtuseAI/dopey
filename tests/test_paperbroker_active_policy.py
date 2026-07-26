"""Tests: PaperBroker independently enforces active trading policy."""
from __future__ import annotations

import pytest

from dopey_execution.errors import LiveTradingDisabledError
from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker


def _intent(intent_id: str, structure: str, side: str, action: str, trade_date: str, option_type: str = "call") -> ExecutionIntent:
    return ExecutionIntent(
        intent_id=intent_id,
        symbol="SPY_FIXTURE",
        structure=structure,
        legs=[{"side": side, "symbol": f"{intent_id}_OPT", "option_type": option_type, "expiry": "2026-07-17", "dte": 14}],
        max_loss=1.0,
        target_profit=2.0,
        order_action=action,
        trade_date=trade_date,
        position_id=intent_id,
        active_policy_required=True,
        lifecycle_state="normal_hold",
    )


def test_paper_broker_rejects_live_allowed_true() -> None:
    intent = _intent("live", "long_call", "buy", "buy_to_open", "2026-07-01")
    intent.live_allowed = True
    with pytest.raises(LiveTradingDisabledError):
        PaperBroker().place_order(intent)


def test_paper_broker_rejects_sell_to_open() -> None:
    result = PaperBroker().place_order(_intent("sell-open", "long_call", "sell", "sell_to_open", "2026-07-01"))
    assert result["ok"] is False
    assert "unsupported_short_option_leg" in result["errors"]


def test_paper_broker_rejects_same_day_close() -> None:
    broker = PaperBroker()
    open_intent = _intent("open-call", "long_call", "buy", "buy_to_open", "2026-07-01")
    assert broker.place_order(open_intent)["ok"] is True
    close_intent = _intent("close-call", "long_call", "sell", "sell_to_close", "2026-07-01")
    close_intent.related_open_position_id = "open-call"
    result = broker.place_order(close_intent)
    assert result["ok"] is False
    assert result["reason_code"] == "same_day_round_trip_rejected"


def test_paper_broker_accepts_next_day_sell_to_close() -> None:
    broker = PaperBroker()
    open_intent = _intent("open-put", "long_put", "buy", "buy_to_open", "2026-07-01", option_type="put")
    assert broker.place_order(open_intent)["ok"] is True
    close_intent = _intent("close-put", "long_put", "sell", "sell_to_close", "2026-07-02", option_type="put")
    close_intent.related_open_position_id = "open-put"
    result = broker.place_order(close_intent)
    assert result["ok"] is True
    assert result["active_policy_state"]["lifecycle_state"] == "paper_closed"


def test_paper_broker_records_policy_rejection_reason() -> None:
    ledger: list[dict] = []
    result = PaperBroker(ledger=ledger).place_order(_intent("sell-open-ledger", "long_call", "sell", "sell_to_open", "2026-07-01"))
    assert result["reason_code"] == "unsupported_short_option_leg"
    assert ledger[-1]["reason_code"] == "unsupported_short_option_leg"


def test_paper_broker_records_zero_dte_policy_state() -> None:
    broker = PaperBroker()
    intent = _intent("zero-dte", "long_call", "buy", "buy_to_open", "2026-07-01")
    intent.zero_dte = True
    intent.legs[0]["dte"] = 0
    intent.lifecycle_state = "zero_dte_special_lifecycle"
    intent.liquidity_approved = True
    intent.risk_cap_approved = True
    # The account ledger fail-closes zero-DTE opens that arrive without a
    # paper risk-model approval decision - approvals alone are not enough.
    rejected = broker.place_order(intent)
    assert rejected["ok"] is False
    assert "zero_dte_risk_model_approval_required" in rejected["errors"]
    intent.zero_dte_risk_decision = {
        "decision": "approved_for_paper_open",
        "paper_only": True,
        "live_blocked": True,
        "max_paper_premium_at_risk": 1.0,
        "max_contracts_paper": 1,
        "expiry_handling_plan": "paper_close_or_expire_worthless_same_day",
    }
    result = broker.place_order(intent)
    assert result["ok"] is True
    assert result["active_policy_state"]["zero_dte"] is True
    assert result["active_policy_state"]["lifecycle_state"] == "zero_dte_open"
