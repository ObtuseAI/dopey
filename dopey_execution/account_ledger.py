"""Offline paper account ledger and no-day-trade enforcement."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dopey_options.zero_dte_risk_model import ZERO_DTE_OPEN_APPROVAL_DECISIONS

from .account_models import DayTradeEvent, PaperAccountLedger, PaperOptionPosition, with_refreshed_hash
from .day_trade_policy import DayTradePolicy, policy_snapshot
from .execution_intent import ExecutionIntent
from .position_lifecycle import (
    ACTIVE_BUY_TO_OPEN,
    ACTIVE_SELL_TO_CLOSE,
    ACTIVE_SELL_TO_OPEN,
    active_policy_errors_for_open,
    expiry_for_intent,
    option_symbol_for_intent,
    option_type_for_intent,
)
from .trading_calendar import is_next_trading_day_or_later, next_trading_day, same_trading_day
from .zero_dte_lifecycle import evaluate_zero_dte_lifecycle


ACCOUNT_LEDGER_VERSION = "dopey-offline-account-ledger-v1"
REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "account_ledger"
PAPER_ACCOUNT_LEDGER_PATH = ARTIFACT_DIR / "paper_account_ledger.json"
DAY_TRADE_POLICY_PATH = ARTIFACT_DIR / "day_trade_policy.json"
PDT_SAFE_POLICY_PATH = ARTIFACT_DIR / "pdt_safe_policy.json"
DAY_TRADE_EVENT_LOG_PATH = ARTIFACT_DIR / "day_trade_event_log.jsonl"
ZERO_DTE_ACCOUNT_LIFECYCLE_PROOF_PATH = ARTIFACT_DIR / "zero_dte_account_lifecycle_proof.jsonl"
PAPERBROKER_ACCOUNT_LEDGER_PROOF_PATH = ARTIFACT_DIR / "paperbroker_account_ledger_proof.jsonl"


@dataclass(frozen=True)
class LedgerActionResult:
    accepted: bool
    decision: str
    reason_codes: list[str]
    ledger: PaperAccountLedger
    position: dict[str, Any]
    day_trade_event: dict[str, Any]
    order_record: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "decision": self.decision,
            "reason_codes": self.reason_codes,
            "ledger": self.ledger.to_dict(),
            "position": self.position,
            "day_trade_event": self.day_trade_event,
            "order_record": self.order_record,
        }


def create_paper_account_ledger(account_id: str, policy: DayTradePolicy) -> PaperAccountLedger:
    ledger = PaperAccountLedger(
        account_id=account_id,
        mode="RESEARCH",
        paper_only=True,
        live_blocked=True,
        policy_snapshots=[policy_snapshot(policy)],
    )
    return with_refreshed_hash(ledger)


def open_positions(ledger: PaperAccountLedger) -> list[PaperOptionPosition]:
    return [position for position in ledger.positions if position.close_status == "open"]


def close_eligible_positions(ledger: PaperAccountLedger, trade_date: str) -> list[PaperOptionPosition]:
    return [
        position for position in open_positions(ledger)
        if is_next_trading_day_or_later(position.open_date, trade_date)
    ]


def same_day_blocked_positions(ledger: PaperAccountLedger, trade_date: str) -> list[PaperOptionPosition]:
    return [
        position for position in open_positions(ledger)
        if position.same_day_close_blocked and same_trading_day(position.open_date, trade_date)
    ]


def legacy_lifecycle_positions(ledger: PaperAccountLedger) -> list[dict[str, Any]]:
    return [
        {
            "position_id": position.position_id,
            "option_symbol": _option_symbol(position),
            "underlying_symbol": position.underlying,
            "expiry": position.expiry,
            "option_type": position.option_type,
            "open_date": position.open_date,
            "zero_dte": position.zero_dte,
            "lifecycle_state": "paper_closed" if position.close_status == "closed" else position.lifecycle_state,
        }
        for position in ledger.positions
    ]


def add_open_position(
    ledger: PaperAccountLedger,
    intent: ExecutionIntent,
    policy: DayTradePolicy,
) -> LedgerActionResult:
    errors = _open_rejection_reasons(intent, policy)
    if errors:
        rejected_order = _order_record(intent, "rejected_by_account_ledger", errors, {})
        return LedgerActionResult(False, "blocked_policy_violation", errors, _append_order(ledger, rejected_order), {}, {}, rejected_order)
    zero = _intent_is_zero_dte(intent)
    position = PaperOptionPosition(
        position_id=intent.position_id or intent.intent_id,
        underlying=intent.symbol,
        option_type=option_type_for_intent(intent),
        expiry=expiry_for_intent(intent),
        strike=_strike_for_intent(intent),
        quantity=intent.quantity,
        open_date=intent.trade_date,
        open_timestamp=_open_timestamp(intent),
        open_order_id=intent.intent_id,
        lifecycle_state="zero_dte_open" if zero else "normal_hold",
        zero_dte=zero,
        same_day_close_blocked=not zero,
        close_eligible_date=intent.trade_date if zero else next_trading_day(intent.trade_date),
        close_status="open",
        policy_flags={
            "buy_to_open_only": True,
            "long_premium_only": True,
            "same_day_close_blocked": not zero,
            "zero_dte_special_lifecycle": zero,
            "zero_dte_risk_decision": _zero_dte_risk_decision(intent),
            "zero_dte_replay_feedback": _zero_dte_replay_feedback(intent),
            "zero_dte_max_paper_premium_at_risk": _zero_dte_max_premium(intent),
            "zero_dte_max_contracts_paper": _zero_dte_max_contracts(intent),
            "zero_dte_expiry_handling_plan": _zero_dte_expiry_plan(intent),
        },
        paper_only=True,
        live_blocked=True,
    )
    order = _order_record(intent, "simulated_paper_open_recorded", [], position.to_dict())
    updated = PaperAccountLedger(
        account_id=ledger.account_id,
        mode=ledger.mode,
        paper_only=ledger.paper_only,
        live_blocked=ledger.live_blocked,
        positions=[*ledger.positions, position],
        orders=[*ledger.orders, order],
        day_trade_events=list(ledger.day_trade_events),
        rotation_events=list(ledger.rotation_events),
        policy_snapshots=_policy_snapshots(ledger, policy),
    )
    return LedgerActionResult(True, "open_allowed", [], with_refreshed_hash(updated), position.to_dict(), {}, order)


def close_position(
    ledger: PaperAccountLedger,
    intent: ExecutionIntent,
    policy: DayTradePolicy,
) -> LedgerActionResult:
    matched = find_open_position(ledger, intent)
    if matched is None:
        order = _order_record(intent, "rejected_by_account_ledger", ["close_without_open_position_rejected"], {})
        return LedgerActionResult(False, "blocked_policy_violation", ["close_without_open_position_rejected"], _append_order(ledger, order), {}, {}, order)
    errors = _close_rejection_reasons(matched, intent, policy)
    event = _day_trade_event(matched, intent, not errors, errors[0] if errors else "")
    order = _order_record(intent, "simulated_paper_close_recorded" if not errors else "rejected_by_account_ledger", errors, matched.to_dict())
    updated_positions = [
        _closed_position(position, intent) if position.position_id == matched.position_id and not errors else position
        for position in ledger.positions
    ]
    updated = PaperAccountLedger(
        account_id=ledger.account_id,
        mode=ledger.mode,
        paper_only=ledger.paper_only,
        live_blocked=ledger.live_blocked,
        positions=updated_positions,
        orders=[*ledger.orders, order],
        day_trade_events=[*ledger.day_trade_events, event],
        rotation_events=list(ledger.rotation_events),
        policy_snapshots=_policy_snapshots(ledger, policy),
    )
    decision = "close_allowed" if not errors else _close_block_decision(errors[0])
    return LedgerActionResult(not errors, decision, errors, with_refreshed_hash(updated), matched.to_dict(), event.to_dict(), order)


def find_open_position(ledger: PaperAccountLedger, intent: ExecutionIntent) -> PaperOptionPosition | None:
    target_id = intent.related_open_position_id or intent.position_id
    target_symbol = option_symbol_for_intent(intent)
    for position in open_positions(ledger):
        if target_id and position.position_id == target_id:
            return position
        if target_symbol and _option_symbol(position) == target_symbol:
            return position
    return None


def account_ledger_summary(ledger: PaperAccountLedger, trade_date: str) -> dict[str, Any]:
    open_count = len(open_positions(ledger))
    eligible = close_eligible_positions(ledger, trade_date)
    blocked = same_day_blocked_positions(ledger, trade_date)
    zero_dte = [position for position in open_positions(ledger) if position.zero_dte]
    replay_feedback = [
        position
        for position in open_positions(ledger)
        if isinstance(position.policy_flags.get("zero_dte_replay_feedback", {}), dict)
        and bool(position.policy_flags.get("zero_dte_replay_feedback", {}))
    ]
    return {
        "account_ledger_version": ACCOUNT_LEDGER_VERSION,
        "account_id": ledger.account_id,
        "open_positions_count": open_count,
        "close_eligible_positions_count": len(eligible),
        "same_day_blocked_positions_count": len(blocked),
        "zero_dte_open_positions_count": len(zero_dte),
        "zero_dte_replay_feedback_positions_count": len(replay_feedback),
        "day_trade_events_count": len(ledger.day_trade_events),
        "rotation_events_count": len(ledger.rotation_events),
        "ledger_hash": ledger.ledger_hash,
        "paper_only": True,
        "live_blocked": True,
    }


def write_account_ledger_artifacts(
    ledger: PaperAccountLedger,
    day_trade_policy: DayTradePolicy,
    pdt_policy: DayTradePolicy,
) -> dict[str, str]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(PAPER_ACCOUNT_LEDGER_PATH, ledger.to_dict())
    _write_json(DAY_TRADE_POLICY_PATH, policy_snapshot(day_trade_policy))
    _write_json(PDT_SAFE_POLICY_PATH, policy_snapshot(pdt_policy))
    _write_jsonl(DAY_TRADE_EVENT_LOG_PATH, [event.to_dict() for event in ledger.day_trade_events])
    return account_ledger_artifact_paths()


def account_ledger_artifact_paths() -> dict[str, str]:
    return {
        "paper_account_ledger": str(PAPER_ACCOUNT_LEDGER_PATH),
        "day_trade_policy": str(DAY_TRADE_POLICY_PATH),
        "pdt_safe_policy": str(PDT_SAFE_POLICY_PATH),
        "day_trade_event_log": str(DAY_TRADE_EVENT_LOG_PATH),
        "zero_dte_account_lifecycle_proof": str(ZERO_DTE_ACCOUNT_LIFECYCLE_PROOF_PATH),
        "paperbroker_account_ledger_proof": str(PAPERBROKER_ACCOUNT_LEDGER_PROOF_PATH),
    }


def _open_rejection_reasons(intent: ExecutionIntent, policy: DayTradePolicy) -> list[str]:
    errors: list[str] = []
    if intent.live_allowed:
        errors.append("blocked_live_path")
    if intent.order_action == ACTIVE_SELL_TO_OPEN:
        errors.append("sell_to_open_rejected")
    if intent.order_action not in {"open", ACTIVE_BUY_TO_OPEN}:
        errors.append(f"unsupported_order_action_rejected:{intent.order_action}")
    errors.extend(active_policy_errors_for_open(intent))
    if option_type_for_intent(intent) not in {"call", "put"}:
        errors.append("ledger_rejects_non_call_put_option_type")
    if _intent_is_zero_dte(intent):
        errors.extend(_zero_dte_open_risk_errors(intent))
        zero_decision = evaluate_zero_dte_lifecycle(
            0,
            intent.lifecycle_state,
            intent.liquidity_approved,
            intent.risk_cap_approved,
            intent.reason_code,
            False,
        )
        if not zero_decision.allowed:
            errors.append(zero_decision.reason_code)
        if not policy.zero_dte_special_lifecycle_enabled:
            errors.append("zero_dte_special_lifecycle_disabled")
    return _dedupe(errors)


def _close_rejection_reasons(
    position: PaperOptionPosition,
    intent: ExecutionIntent,
    policy: DayTradePolicy,
) -> list[str]:
    errors: list[str] = []
    if intent.live_allowed:
        errors.append("blocked_live_path")
    if intent.order_action != ACTIVE_SELL_TO_CLOSE:
        errors.append(f"unsupported_order_action_rejected:{intent.order_action}")
    same_day = same_trading_day(position.open_date, intent.trade_date)
    if same_day and not position.zero_dte and policy.same_day_round_trip_blocked:
        errors.append("same_day_round_trip_rejected")
    if same_day and position.zero_dte:
        errors.extend(_zero_dte_close_risk_errors(position, intent))
        zero_decision = evaluate_zero_dte_lifecycle(
            0,
            intent.lifecycle_state,
            intent.liquidity_approved,
            intent.risk_cap_approved,
            intent.reason_code,
            True,
        )
        if not zero_decision.allowed:
            errors.append(zero_decision.reason_code)
        if not policy.allow_zero_dte_special_exit:
            errors.append("zero_dte_special_exit_disabled")
    if not same_day and not is_next_trading_day_or_later(position.open_date, intent.trade_date):
        errors.append("close_before_open_rejected")
    return _dedupe(errors)


def _zero_dte_open_risk_errors(intent: ExecutionIntent) -> list[str]:
    decision = _zero_dte_risk_decision(intent)
    if not decision:
        return ["zero_dte_risk_model_approval_required"]
    decision_name = str(decision.get("decision", ""))
    if decision_name not in ZERO_DTE_OPEN_APPROVAL_DECISIONS:
        reason_codes = _zero_dte_reason_codes(decision)
        return _dedupe(["zero_dte_risk_model_rejected", *reason_codes])
    if decision.get("paper_only") is not True or decision.get("live_blocked") is not True:
        return ["zero_dte_risk_model_requires_paper_only_live_blocked"]
    if float(decision.get("max_paper_premium_at_risk", 0.0)) <= 0.0:
        return ["zero_dte_risk_model_missing_risk_cap"]
    return []


def _zero_dte_close_risk_errors(position: PaperOptionPosition, intent: ExecutionIntent) -> list[str]:
    decision = _zero_dte_risk_decision(intent) or _position_zero_dte_risk_decision(position)
    if not decision:
        return ["zero_dte_risk_model_approval_required"]
    if decision.get("special_close_allowed") is not True:
        return ["zero_dte_special_close_not_approved_by_risk_model"]
    if decision.get("paper_only") is not True or decision.get("live_blocked") is not True:
        return ["zero_dte_risk_model_requires_paper_only_live_blocked"]
    if float(decision.get("max_paper_premium_at_risk", 0.0)) <= 0.0:
        return ["zero_dte_risk_model_missing_risk_cap"]
    return []


def _zero_dte_risk_decision(intent: ExecutionIntent) -> dict[str, Any]:
    value = intent.zero_dte_risk_decision
    if isinstance(value, dict):
        return dict(value)
    return {}


def account_ledger_zero_dte_replay_feedback_summary(feedback: dict[str, Any]) -> dict[str, Any]:
    recommendations = feedback.get("threshold_feedback", [])
    tags = feedback.get("recursive_improvement_tags", [])
    return {
        "outcome_type": str(feedback.get("outcome_type", "")),
        "risk_model_alignment": str(feedback.get("risk_model_alignment", "")),
        "threshold_feedback": [str(item) for item in recommendations] if isinstance(recommendations, list) else [],
        "recursive_improvement_tags": [str(item) for item in tags] if isinstance(tags, list) else [],
        "advisory_only": True,
        "auto_approval_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _zero_dte_replay_feedback(intent: ExecutionIntent) -> dict[str, Any]:
    value = intent.zero_dte_replay_feedback
    if isinstance(value, dict):
        return account_ledger_zero_dte_replay_feedback_summary(dict(value)) if value else {}
    return {}


def _position_zero_dte_risk_decision(position: PaperOptionPosition) -> dict[str, Any]:
    value = position.policy_flags.get("zero_dte_risk_decision", {})
    if isinstance(value, dict):
        return dict(value)
    return {}


def _zero_dte_reason_codes(decision: dict[str, Any]) -> list[str]:
    value = decision.get("reason_codes", [])
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _zero_dte_max_premium(intent: ExecutionIntent) -> float:
    decision = _zero_dte_risk_decision(intent)
    value = decision.get("max_paper_premium_at_risk", 0.0)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return float(value)


def _zero_dte_max_contracts(intent: ExecutionIntent) -> int:
    decision = _zero_dte_risk_decision(intent)
    value = decision.get("max_contracts_paper", 0)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _zero_dte_expiry_plan(intent: ExecutionIntent) -> str:
    decision = _zero_dte_risk_decision(intent)
    value = decision.get("expiry_handling_plan", "")
    return value if isinstance(value, str) else ""


def _closed_position(position: PaperOptionPosition, intent: ExecutionIntent) -> PaperOptionPosition:
    state = "zero_dte_special_close_allowed" if position.zero_dte else "paper_closed"
    return PaperOptionPosition(
        position_id=position.position_id,
        underlying=position.underlying,
        option_type=position.option_type,
        expiry=position.expiry,
        strike=position.strike,
        quantity=position.quantity,
        open_date=position.open_date,
        open_timestamp=position.open_timestamp,
        open_order_id=position.open_order_id,
        lifecycle_state=state,
        zero_dte=position.zero_dte,
        same_day_close_blocked=position.same_day_close_blocked,
        close_eligible_date=position.close_eligible_date,
        close_status="closed",
        policy_flags={**position.policy_flags, "close_order_id": intent.intent_id, "close_date": intent.trade_date},
        paper_only=True,
        live_blocked=True,
    )


def _day_trade_event(
    position: PaperOptionPosition,
    intent: ExecutionIntent,
    allowed: bool,
    rejection_reason: str,
) -> DayTradeEvent:
    same_day = same_trading_day(position.open_date, intent.trade_date)
    return DayTradeEvent(
        event_id=f"day-trade-event-{position.position_id}-{intent.intent_id}",
        position_id=position.position_id,
        underlying=position.underlying,
        option_type=position.option_type,
        open_date=position.open_date,
        close_date=intent.trade_date,
        same_trading_day=same_day,
        zero_dte_special_lifecycle=position.zero_dte and intent.lifecycle_state == "zero_dte_expiry_managed",
        allowed=allowed,
        rejection_reason=rejection_reason,
        audit_required=True,
        paper_only=True,
    )


def _append_order(ledger: PaperAccountLedger, order: dict[str, Any]) -> PaperAccountLedger:
    updated = PaperAccountLedger(
        account_id=ledger.account_id,
        mode=ledger.mode,
        paper_only=ledger.paper_only,
        live_blocked=ledger.live_blocked,
        positions=list(ledger.positions),
        orders=[*ledger.orders, order],
        day_trade_events=list(ledger.day_trade_events),
        rotation_events=list(ledger.rotation_events),
        policy_snapshots=list(ledger.policy_snapshots),
    )
    return with_refreshed_hash(updated)


def _order_record(
    intent: ExecutionIntent,
    status: str,
    reason_codes: list[str],
    position: dict[str, Any],
) -> dict[str, Any]:
    record = {
        "order_id": intent.intent_id,
        "intent": intent.to_dict(),
        "status": status,
        "reason_codes": reason_codes,
        "position": position,
        "paper_only": True,
        "live_blocked": True,
    }
    record["reproducibility_hash"] = _stable_hash(record)
    return record


def _intent_is_zero_dte(intent: ExecutionIntent) -> bool:
    expiry = expiry_for_intent(intent)
    return intent.zero_dte or bool(expiry and intent.trade_date and expiry == intent.trade_date)


def _strike_for_intent(intent: ExecutionIntent) -> float:
    if not intent.legs:
        return 0.0
    value = intent.legs[0].get("strike", 0.0)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return float(value)


def _open_timestamp(intent: ExecutionIntent) -> str:
    if intent.legs:
        value = intent.legs[0].get("open_timestamp", "")
        if isinstance(value, str) and value:
            return value
    return f"{intent.trade_date}T00:00:00Z"


def _option_symbol(position: PaperOptionPosition) -> str:
    side = "C" if position.option_type == "call" else "P"
    strike = int(position.strike) if position.strike.is_integer() else position.strike
    return f"{position.underlying}_{side}_{strike}_{position.expiry}"


def _policy_snapshots(ledger: PaperAccountLedger, policy: DayTradePolicy) -> list[dict[str, Any]]:
    snapshots = list(ledger.policy_snapshots)
    latest = policy_snapshot(policy)
    if latest not in snapshots:
        snapshots.append(latest)
    return snapshots


def _close_block_decision(reason: str) -> str:
    if reason == "same_day_round_trip_rejected":
        return "blocked_same_day_round_trip"
    if reason.startswith("zero_dte"):
        return "blocked_zero_dte_missing_lifecycle"
    if reason == "blocked_live_path":
        return "blocked_live_path"
    return "blocked_policy_violation"


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, sort_keys=True, ensure_ascii=False) for record in records) + ("\n" if records else ""), encoding="utf-8")


def _stable_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
