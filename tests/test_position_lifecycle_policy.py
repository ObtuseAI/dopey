"""Tests: active order-intent validation, no-day-trade guard, and 0DTE lifecycle."""
from __future__ import annotations

from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.no_day_trade_guard import evaluate_no_day_trade
from dopey_execution.order_intent_validator import validate_intent
from dopey_execution.position_lifecycle import build_open_position_record
from dopey_execution.zero_dte_lifecycle import evaluate_zero_dte_lifecycle


def _intent(
    intent_id: str,
    structure: str,
    side: str,
    action: str,
    trade_date: str,
    option_type: str,
    dte: int = 14,
    lifecycle_state: str = "normal_hold",
    liquidity_approved: bool = False,
    risk_cap_approved: bool = False,
    reason_code: str = "",
) -> ExecutionIntent:
    return ExecutionIntent(
        intent_id=intent_id,
        symbol="SPY_FIXTURE",
        structure=structure,
        legs=[{"side": side, "symbol": f"{intent_id}_OPT", "option_type": option_type, "expiry": "2026-07-17", "dte": dte}],
        max_loss=1.0,
        target_profit=2.0,
        order_action=action,
        trade_date=trade_date,
        position_id=intent_id,
        lifecycle_state=lifecycle_state,
        zero_dte=dte == 0,
        active_policy_required=True,
        liquidity_approved=liquidity_approved,
        risk_cap_approved=risk_cap_approved,
        reason_code=reason_code,
    )


def _open_record(option_type: str, trade_date: str = "2026-07-01") -> dict:
    structure = "long_call" if option_type == "call" else "long_put"
    return build_open_position_record(_intent(f"open-{option_type}", structure, "buy", "buy_to_open", trade_date, option_type)).to_dict()


def test_buy_to_open_call_allowed() -> None:
    assert validate_intent(_intent("call-open", "long_call", "buy", "buy_to_open", "2026-07-01", "call"))["valid"] is True


def test_buy_to_open_put_allowed() -> None:
    assert validate_intent(_intent("put-open", "long_put", "buy", "buy_to_open", "2026-07-01", "put"))["valid"] is True


def test_sell_to_close_existing_call_allowed_next_day() -> None:
    close = _intent("call-close", "long_call", "sell", "sell_to_close", "2026-07-02", "call")
    close.related_open_position_id = "open-call"
    assert validate_intent(close, open_positions=[_open_record("call")])["valid"] is True


def test_sell_to_close_existing_put_allowed_next_day() -> None:
    close = _intent("put-close", "long_put", "sell", "sell_to_close", "2026-07-02", "put")
    close.related_open_position_id = "open-put"
    assert validate_intent(close, open_positions=[_open_record("put")])["valid"] is True


def test_sell_to_open_call_rejected() -> None:
    verdict = validate_intent(_intent("sell-open-call", "long_call", "sell", "sell_to_open", "2026-07-01", "call"))
    assert "unsupported_short_option_leg" in verdict["errors"]


def test_sell_to_open_put_rejected() -> None:
    verdict = validate_intent(_intent("sell-open-put", "long_put", "sell", "sell_to_open", "2026-07-01", "put"))
    assert "unsupported_short_option_leg" in verdict["errors"]


def test_naked_option_sale_rejected() -> None:
    verdict = validate_intent(_intent("naked", "long_call", "sell", "sell_to_open", "2026-07-01", "call"))
    assert "naked_option_sale_rejected" in verdict["errors"]


def test_undefined_risk_structure_rejected() -> None:
    intent = _intent("undefined", "long_call", "buy", "buy_to_open", "2026-07-01", "call")
    intent.defined_risk = False
    verdict = validate_intent(intent)
    assert "undefined_risk_structure_rejected" in verdict["errors"]


def test_unsupported_spread_rejected() -> None:
    intent = ExecutionIntent(
        intent_id="spread",
        symbol="SPY_FIXTURE",
        structure="vertical",
        legs=[
            {"side": "buy", "symbol": "A", "option_type": "call", "expiry": "2026-07-17", "dte": 14},
            {"side": "sell", "symbol": "B", "option_type": "call", "expiry": "2026-07-17", "dte": 14},
        ],
        max_loss=1.0,
        order_action="buy_to_open",
        trade_date="2026-07-01",
        active_policy_required=True,
    )
    assert "unsupported_multileg_structure_rejected" in validate_intent(intent)["errors"]


def test_close_without_open_position_rejected() -> None:
    verdict = validate_intent(_intent("close-missing", "long_call", "sell", "sell_to_close", "2026-07-02", "call"), open_positions=[])
    assert "close_without_open_position_rejected" in verdict["errors"]


def test_same_day_round_trip_rejected_for_normal_call() -> None:
    close = _intent("call-close-same", "long_call", "sell", "sell_to_close", "2026-07-01", "call")
    close.related_open_position_id = "open-call"
    assert "same_day_round_trip_rejected" in validate_intent(close, open_positions=[_open_record("call")])["errors"]


def test_same_day_round_trip_rejected_for_normal_put() -> None:
    close = _intent("put-close-same", "long_put", "sell", "sell_to_close", "2026-07-01", "put")
    close.related_open_position_id = "open-put"
    assert "same_day_round_trip_rejected" in validate_intent(close, open_positions=[_open_record("put")])["errors"]


def test_next_day_close_allowed_for_call() -> None:
    decision = evaluate_no_day_trade("2026-07-01", "2026-07-02", False, "normal_hold", "", False, False)
    assert decision.allowed is True


def test_next_day_close_allowed_for_put() -> None:
    decision = evaluate_no_day_trade("2026-07-01", "2026-07-02", False, "normal_hold", "", False, False)
    assert decision.lifecycle_state == "close_eligible_next_trading_day"


def test_rotation_between_different_positions_allowed_if_no_same_day_round_trip() -> None:
    call = validate_intent(_intent("rotate-call", "long_call", "buy", "buy_to_open", "2026-07-01", "call"))
    put = validate_intent(_intent("rotate-put", "long_put", "buy", "buy_to_open", "2026-07-01", "put"))
    assert call["valid"] is True and put["valid"] is True


def test_zero_dte_call_requires_special_lifecycle() -> None:
    verdict = validate_intent(_intent("z-call", "long_call", "buy", "buy_to_open", "2026-07-01", "call", dte=0, lifecycle_state=""))
    assert "zero_dte_requires_special_lifecycle" in verdict["errors"]


def test_zero_dte_put_requires_special_lifecycle() -> None:
    verdict = validate_intent(_intent("z-put", "long_put", "buy", "buy_to_open", "2026-07-01", "put", dte=0, lifecycle_state=""))
    assert "zero_dte_requires_special_lifecycle" in verdict["errors"]


def test_zero_dte_rejects_missing_liquidity_approval() -> None:
    decision = evaluate_zero_dte_lifecycle(0, "zero_dte_special_lifecycle", False, True, "", False)
    assert decision.allowed is False


def test_zero_dte_rejects_missing_risk_cap() -> None:
    decision = evaluate_zero_dte_lifecycle(0, "zero_dte_special_lifecycle", True, False, "", False)
    assert decision.reason_code == "zero_dte_policy_violation_missing_risk_cap"


def test_zero_dte_expiry_managed_state_is_not_normal_day_trade() -> None:
    decision = evaluate_zero_dte_lifecycle(0, "zero_dte_expiry_managed", True, True, "expiry_window", True)
    assert decision.allowed is True
    assert decision.is_normal_day_trade is False


def test_zero_dte_special_close_requires_explicit_reason_code() -> None:
    decision = evaluate_zero_dte_lifecycle(0, "zero_dte_expiry_managed", True, True, "", True)
    assert decision.reason_code == "zero_dte_special_close_requires_explicit_reason_code"
