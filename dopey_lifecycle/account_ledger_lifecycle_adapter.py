"""Account ledger adapter for active option lifecycle simulation."""
from __future__ import annotations

from typing import Any

from dopey_execution.account_ledger import account_ledger_summary, close_position, create_paper_account_ledger, add_open_position
from dopey_execution.day_trade_policy import default_day_trade_policy
from dopey_execution.execution_intent import ExecutionIntent

from .paperbroker_lifecycle_adapter import build_close_intent, build_open_intent


class AccountLedgerLifecycleAdapter:
    def __init__(self) -> None:
        self.policy = default_day_trade_policy()
        self.ledger = create_paper_account_ledger("dopey-active-lifecycle-ledger", self.policy)

    def record_open(self, case: dict[str, Any]) -> dict[str, Any]:
        intent = build_open_intent(case)
        result = add_open_position(self.ledger, intent, self.policy)
        self.ledger = result.ledger
        return _ledger_result(result.to_dict(), "open")

    def record_close(self, case: dict[str, Any], trade_date: str, lifecycle_state: str, reason_code: str) -> dict[str, Any]:
        intent = build_close_intent(case, trade_date, lifecycle_state, reason_code)
        result = close_position(self.ledger, intent, self.policy)
        self.ledger = result.ledger
        return _ledger_result(result.to_dict(), "close")

    def reject_close_without_open(self, case: dict[str, Any]) -> dict[str, Any]:
        intent = build_close_intent(case, str(case["trade_date"]), "normal_hold", "")
        result = close_position(self.ledger, intent, self.policy)
        self.ledger = result.ledger
        return _ledger_result(result.to_dict(), "close_without_open")

    def summary(self, trade_date: str) -> dict[str, Any]:
        return account_ledger_summary(self.ledger, trade_date)


def evaluate_no_day_trade_result(case: dict[str, Any], trade_date: str, lifecycle_state: str, reason_code: str) -> dict[str, Any]:
    adapter = AccountLedgerLifecycleAdapter()
    open_intent = build_open_intent(case)
    open_result = add_open_position(adapter.ledger, open_intent, adapter.policy)
    close_intent = build_close_intent(case, trade_date, lifecycle_state, reason_code)
    close_result = close_position(open_result.ledger, close_intent, adapter.policy)
    return {
        "accepted": close_result.accepted,
        "decision": close_result.decision,
        "reason_codes": close_result.reason_codes,
        "paper_only": True,
        "live_blocked": True,
    }


def _ledger_result(result: dict[str, Any], action: str) -> dict[str, Any]:
    reason_codes = result.get("reason_codes", [])
    if not isinstance(reason_codes, list):
        reason_codes = [str(reason_codes)]
    ledger = result.get("ledger", {}) if isinstance(result.get("ledger", {}), dict) else {}
    position = result.get("position", {}) if isinstance(result.get("position", {}), dict) else {}
    return {
        "action": action,
        "accepted": bool(result.get("accepted", False)),
        "decision": str(result.get("decision", "")),
        "reason_codes": [str(item) for item in reason_codes],
        "ledger_hash": str(ledger.get("ledger_hash", "")),
        "close_eligible_date": str(position.get("close_eligible_date", "")),
        "lifecycle_state": str(position.get("lifecycle_state", "")),
        "paper_only": True,
        "live_blocked": True,
    }
