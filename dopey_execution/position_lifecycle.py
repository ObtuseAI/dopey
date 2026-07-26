"""Offline active-policy position lifecycle ledger for DOPEY paper options."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .execution_intent import ExecutionIntent
from .no_day_trade_guard import evaluate_no_day_trade
from .zero_dte_lifecycle import evaluate_zero_dte_lifecycle


POSITION_LIFECYCLE_VERSION = "dopey-active-position-lifecycle-v1"

ACTIVE_ALLOWED_STRUCTURES: frozenset[str] = frozenset({"long_call", "long_put", "single"})
ACTIVE_ALLOWED_OPTION_TYPES: frozenset[str] = frozenset({"call", "put"})
ACTIVE_BUY_TO_OPEN = "buy_to_open"
ACTIVE_SELL_TO_CLOSE = "sell_to_close"
ACTIVE_SELL_TO_OPEN = "sell_to_open"

ACTIVE_REJECTION_CODES: tuple[str, ...] = (
    "unsupported_short_option_leg",
    "naked_option_sale_rejected",
    "undefined_risk_structure_rejected",
    "same_day_round_trip_rejected",
    "close_without_open_position_rejected",
    "unsupported_multileg_structure_rejected",
    "live_order_rejected",
    "zero_dte_requires_special_lifecycle",
    "zero_dte_policy_violation",
)


@dataclass(frozen=True)
class PositionLifecycleRecord:
    position_id: str
    option_symbol: str
    underlying_symbol: str
    expiry: str
    option_type: str
    open_date: str
    close_date: str
    open_action: str
    close_action: str
    zero_dte: bool
    normal_swing_or_rotation: bool
    lifecycle_state: str
    close_eligible: bool
    reason_code: str
    paper_only: bool
    live_blocked: bool
    position_lifecycle_version: str = POSITION_LIFECYCLE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PositionLifecycleLedger:
    records: list[PositionLifecycleRecord] = field(default_factory=list)

    def open_position(self, intent: ExecutionIntent) -> PositionLifecycleRecord:
        record = build_open_position_record(intent)
        self.records.append(record)
        return record

    def close_position(self, intent: ExecutionIntent) -> PositionLifecycleRecord:
        decision = evaluate_close_intent(intent, [record.to_dict() for record in self.records])
        record = build_close_position_record(intent, decision)
        self.records.append(record)
        return record

    def to_dict(self) -> dict:
        return {
            "position_lifecycle_version": POSITION_LIFECYCLE_VERSION,
            "records": [record.to_dict() for record in self.records],
        }


def active_policy_applies(intent: ExecutionIntent) -> bool:
    return (
        intent.active_policy_required
        or intent.order_action in {ACTIVE_BUY_TO_OPEN, ACTIVE_SELL_TO_CLOSE, ACTIVE_SELL_TO_OPEN}
        or intent.structure in {"long_call", "long_put"}
    )


def intent_dte(intent: ExecutionIntent) -> int:
    if intent.zero_dte:
        return 0
    for leg in intent.legs:
        if "dte" in leg:
            try:
                return int(leg["dte"])
            except (TypeError, ValueError):
                return -1
    return -1


def option_type_for_intent(intent: ExecutionIntent) -> str:
    if intent.structure == "long_call":
        return "call"
    if intent.structure == "long_put":
        return "put"
    option_types = {str(leg.get("option_type", "")) for leg in intent.legs if str(leg.get("option_type", ""))}
    return next(iter(option_types)) if len(option_types) == 1 else "multi"


def option_symbol_for_intent(intent: ExecutionIntent) -> str:
    if not intent.legs:
        return ""
    return str(intent.legs[0].get("symbol", ""))


def expiry_for_intent(intent: ExecutionIntent) -> str:
    if not intent.legs:
        return ""
    return str(intent.legs[0].get("expiry", ""))


def active_policy_errors_for_open(intent: ExecutionIntent) -> list[str]:
    errors: list[str] = []
    if intent.live_allowed:
        errors.append("live_order_rejected")
    if not intent.defined_risk:
        errors.append("undefined_risk_structure_rejected")
    if intent.structure not in ACTIVE_ALLOWED_STRUCTURES:
        errors.append("unsupported_multileg_structure_rejected")
    if len(intent.legs) != 1:
        errors.append("unsupported_multileg_structure_rejected")
    option_type = option_type_for_intent(intent)
    if option_type not in ACTIVE_ALLOWED_OPTION_TYPES:
        errors.append("unsupported_multileg_structure_rejected")
    if intent.order_action == ACTIVE_SELL_TO_OPEN:
        errors.append("unsupported_short_option_leg")
        errors.append("naked_option_sale_rejected")
    for leg in intent.legs:
        side = str(leg.get("side", ""))
        effect = str(leg.get("position_effect", ""))
        if side == "sell" or effect == "open_short":
            errors.append("unsupported_short_option_leg")
            errors.append("naked_option_sale_rejected")
    dte = intent_dte(intent)
    zero = dte == 0 or intent.zero_dte
    if zero:
        zero_decision = evaluate_zero_dte_lifecycle(
            0,
            intent.lifecycle_state,
            intent.liquidity_approved,
            intent.risk_cap_approved,
            intent.reason_code,
            False,
        )
        if not zero_decision.allowed:
            errors.append(_normalized_zero_dte_code(zero_decision.reason_code))
    return _dedupe(errors)


def active_policy_errors_for_close(intent: ExecutionIntent, open_positions: list[dict] | None) -> list[str]:
    errors: list[str] = []
    if intent.live_allowed:
        errors.append("live_order_rejected")
    if intent.order_action == ACTIVE_SELL_TO_OPEN:
        errors.append("unsupported_short_option_leg")
        errors.append("naked_option_sale_rejected")
    open_position = find_matching_open_position(intent, open_positions or [])
    if open_position is None:
        errors.append("close_without_open_position_rejected")
        return _dedupe(errors)
    dte = intent_dte(intent)
    zero = bool(open_position.get("zero_dte", False)) or dte == 0 or intent.zero_dte
    if zero:
        zero_decision = evaluate_zero_dte_lifecycle(
            0,
            intent.lifecycle_state,
            intent.liquidity_approved,
            intent.risk_cap_approved,
            intent.reason_code,
            str(intent.trade_date) == str(open_position.get("open_date", "")),
        )
        if not zero_decision.allowed:
            errors.append(_normalized_zero_dte_code(zero_decision.reason_code))
            return _dedupe(errors)
    guard = evaluate_no_day_trade(
        str(open_position.get("open_date", "")),
        intent.trade_date,
        zero,
        intent.lifecycle_state,
        intent.reason_code,
        intent.liquidity_approved,
        intent.risk_cap_approved,
    )
    if not guard.allowed:
        errors.append(guard.reason_code)
    return _dedupe(errors)


def find_matching_open_position(intent: ExecutionIntent, open_positions: list[dict]) -> dict | None:
    target_position_id = intent.related_open_position_id or intent.position_id
    target_symbol = option_symbol_for_intent(intent)
    for position in open_positions:
        if str(position.get("lifecycle_state", "")) in {"paper_closed", "rejected"}:
            continue
        if target_position_id and str(position.get("position_id", "")) == target_position_id:
            return position
        if target_symbol and str(position.get("option_symbol", "")) == target_symbol:
            return position
    return None


def validate_active_order_intent(intent: ExecutionIntent, open_positions: list[dict] | None) -> list[str]:
    if not active_policy_applies(intent):
        return []
    if intent.order_action in {"open", ACTIVE_BUY_TO_OPEN}:
        return active_policy_errors_for_open(intent)
    if intent.order_action == ACTIVE_SELL_TO_CLOSE:
        return active_policy_errors_for_close(intent, open_positions)
    if intent.order_action == ACTIVE_SELL_TO_OPEN:
        return _dedupe(["unsupported_short_option_leg", "naked_option_sale_rejected"])
    return [f"unsupported_order_action_rejected:{intent.order_action}"]


def build_open_position_record(intent: ExecutionIntent) -> PositionLifecycleRecord:
    zero = intent.zero_dte or intent_dte(intent) == 0
    state = "zero_dte_special_lifecycle" if zero else "paper_open"
    if not zero:
        state = "normal_hold"
    return PositionLifecycleRecord(
        position_id=intent.position_id or intent.intent_id,
        option_symbol=option_symbol_for_intent(intent),
        underlying_symbol=intent.symbol,
        expiry=expiry_for_intent(intent),
        option_type=option_type_for_intent(intent),
        open_date=intent.trade_date,
        close_date="",
        open_action=ACTIVE_BUY_TO_OPEN,
        close_action="",
        zero_dte=zero,
        normal_swing_or_rotation=not zero,
        lifecycle_state=state,
        close_eligible=False,
        reason_code="approved_for_paper_open",
        paper_only=True,
        live_blocked=True,
    )


def build_close_position_record(intent: ExecutionIntent, decision: dict) -> PositionLifecycleRecord:
    matched = decision.get("matched_position", {}) if isinstance(decision.get("matched_position"), dict) else {}
    allowed = bool(decision.get("allowed", False))
    return PositionLifecycleRecord(
        position_id=str(matched.get("position_id", intent.related_open_position_id or intent.position_id or intent.intent_id)),
        option_symbol=str(matched.get("option_symbol", option_symbol_for_intent(intent))),
        underlying_symbol=intent.symbol,
        expiry=str(matched.get("expiry", expiry_for_intent(intent))),
        option_type=str(matched.get("option_type", option_type_for_intent(intent))),
        open_date=str(matched.get("open_date", "")),
        close_date=intent.trade_date,
        open_action=ACTIVE_BUY_TO_OPEN,
        close_action=ACTIVE_SELL_TO_CLOSE,
        zero_dte=bool(matched.get("zero_dte", intent.zero_dte)),
        normal_swing_or_rotation=not bool(matched.get("zero_dte", intent.zero_dte)),
        lifecycle_state="paper_closed" if allowed else str(decision.get("lifecycle_state", "rejected")),
        close_eligible=allowed,
        reason_code=str(decision.get("reason_code", "")),
        paper_only=True,
        live_blocked=True,
    )


def evaluate_close_intent(intent: ExecutionIntent, open_positions: list[dict]) -> dict:
    matched = find_matching_open_position(intent, open_positions)
    errors = active_policy_errors_for_close(intent, open_positions)
    if errors:
        return {
            "allowed": False,
            "reason_code": errors[0],
            "errors": errors,
            "lifecycle_state": "rejected" if errors[0] != "same_day_round_trip_rejected" else "blocked_same_day_round_trip",
            "matched_position": matched or {},
        }
    return {
        "allowed": True,
        "reason_code": "sell_to_close_allowed",
        "errors": [],
        "lifecycle_state": "paper_closed",
        "matched_position": matched or {},
    }


def _normalized_zero_dte_code(reason_code: str) -> str:
    if reason_code == "zero_dte_requires_special_lifecycle":
        return reason_code
    return "zero_dte_policy_violation"


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
