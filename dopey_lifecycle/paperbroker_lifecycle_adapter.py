"""PaperBroker adapter for active option lifecycle simulation."""
from __future__ import annotations

from typing import Any

from dopey_execution.execution_intent import ExecutionIntent
from dopey_execution.paper_broker import PaperBroker
from dopey_execution.position_lifecycle import ACTIVE_BUY_TO_OPEN, ACTIVE_SELL_TO_CLOSE, ACTIVE_SELL_TO_OPEN


class PaperBrokerLifecycleAdapter:
    def __init__(self, broker: PaperBroker):
        self.broker = broker

    def open_lifecycle_position(self, case: dict[str, Any]) -> dict[str, Any]:
        intent = build_open_intent(case)
        if intent.order_action == ACTIVE_SELL_TO_OPEN:
            return _blocked_result("sell_to_open_rejected", intent)
        if intent.live_allowed:
            return _blocked_result("live_order_rejected", intent)
        result = self.broker.place_order(intent)
        return _normalize_result(result, intent)

    def close_lifecycle_position(self, case: dict[str, Any], trade_date: str, lifecycle_state: str, reason_code: str) -> dict[str, Any]:
        intent = build_close_intent(case, trade_date, lifecycle_state, reason_code)
        if intent.live_allowed:
            return _blocked_result("live_order_rejected", intent)
        result = self.broker.place_order(intent)
        return _normalize_result(result, intent)


def build_open_intent(case: dict[str, Any]) -> ExecutionIntent:
    option_type = str(case["option_type"])
    zero_dte = int(case["days_to_expiry"]) == 0
    symbol = str(case["synthetic_underlying_symbol"])
    expiry = str(case["expiry"])
    action = str(case.get("open_action", ACTIVE_BUY_TO_OPEN))
    decision = _zero_dte_decision(case) if zero_dte else {}
    return ExecutionIntent(
        intent_id=f"{case['candidate_id']}-open",
        symbol=symbol,
        structure="long_call" if option_type == "call" else "long_put",
        legs=[{
            "side": "buy" if action != ACTIVE_SELL_TO_OPEN else "sell",
            "option_type": option_type,
            "expiry": expiry,
            "dte": int(case["days_to_expiry"]),
            "symbol": f"{symbol}-{expiry}-{option_type.upper()}",
        }],
        quantity=1,
        defined_risk=bool(case.get("defined_risk", True)),
        live_allowed=bool(case.get("live_flag_injection", False)),
        tif="DAY",
        paper=True,
        broker_preference="paper",
        strategy_id=str(case["strategy_type"]),
        max_loss=1.0,
        target_profit=0.0,
        invalidation_rule="fixture_exit_rule",
        proof_score=0.9,
        aggression_tier="paper",
        order_action=action,
        trade_date=str(case["trade_date"]),
        position_id=str(case["lifecycle_id"]),
        related_open_position_id="",
        lifecycle_state="zero_dte_special_lifecycle" if zero_dte else "normal_hold",
        zero_dte=zero_dte,
        active_policy_required=True,
        liquidity_approved=bool(case.get("liquidity_approved", True)),
        risk_cap_approved=bool(case.get("risk_cap_approved", True)),
        reason_code="paper_open",
        zero_dte_risk_decision=decision,
        zero_dte_replay_feedback={},
    )


def build_close_intent(case: dict[str, Any], trade_date: str, lifecycle_state: str, reason_code: str) -> ExecutionIntent:
    option_type = str(case["option_type"])
    symbol = str(case["synthetic_underlying_symbol"])
    expiry = str(case["expiry"])
    zero_dte = int(case["days_to_expiry"]) == 0
    return ExecutionIntent(
        intent_id=f"{case['candidate_id']}-close-{trade_date}",
        symbol=symbol,
        structure="long_call" if option_type == "call" else "long_put",
        legs=[{
            "side": "sell",
            "option_type": option_type,
            "expiry": expiry,
            "dte": int(case["days_to_expiry"]),
            "symbol": f"{symbol}-{expiry}-{option_type.upper()}",
        }],
        quantity=1,
        defined_risk=True,
        live_allowed=bool(case.get("live_flag_injection", False)),
        tif="DAY",
        paper=True,
        broker_preference="paper",
        strategy_id=str(case["strategy_type"]),
        max_loss=1.0,
        target_profit=0.0,
        invalidation_rule="fixture_exit_rule",
        proof_score=0.9,
        aggression_tier="paper",
        order_action=ACTIVE_SELL_TO_CLOSE,
        trade_date=trade_date,
        position_id=str(case["lifecycle_id"]),
        related_open_position_id=str(case["lifecycle_id"]),
        lifecycle_state=lifecycle_state,
        zero_dte=zero_dte,
        active_policy_required=True,
        liquidity_approved=bool(case.get("liquidity_approved", True)),
        risk_cap_approved=bool(case.get("risk_cap_approved", True)),
        reason_code=reason_code,
        zero_dte_risk_decision=_zero_dte_decision(case),
        zero_dte_replay_feedback={},
    )


def _zero_dte_decision(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": "approved_for_paper_open",
        "special_close_allowed": bool(case.get("special_close_allowed", True)),
        "max_paper_premium_at_risk": 1.0 if bool(case.get("risk_cap_approved", True)) else 0.0,
        "max_contracts_paper": 1,
        "expiry_handling_plan": "special_close_or_expiry_simulation",
        "reason_codes": ["fixture_zero_dte_lifecycle"],
        "paper_only": True,
        "live_blocked": True,
    }


def _blocked_result(reason_code: str, intent: ExecutionIntent) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "rejected_by_lifecycle_adapter",
        "errors": [reason_code],
        "reason_code": reason_code,
        "intent": intent.to_dict(),
        "paper_only": True,
        "live_blocked": True,
        "paperbroker_override_allowed": False,
    }


def _normalize_result(result: dict[str, Any], intent: ExecutionIntent) -> dict[str, Any]:
    errors = result.get("errors", [])
    if not isinstance(errors, list):
        errors = [str(errors)]
    return {
        "ok": bool(result.get("ok", False)),
        "status": str(result.get("status", "simulated_paper_filled" if result.get("ok") else "rejected")),
        "errors": [str(item) for item in errors],
        "reason_code": str(result.get("reason_code", errors[0] if errors else "")),
        "order_id": str(result.get("order_id", "")),
        "account_ledger_hash": str(result.get("account_ledger_hash", "")),
        "intent": intent.to_dict(),
        "paper_only": True,
        "live_blocked": True,
        "paperbroker_override_allowed": False,
    }
