"""PDT-safe paper rotation planner for long-premium options."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .account_ledger import (
    ARTIFACT_DIR,
    close_position,
    find_open_position,
    add_open_position,
)
from .account_models import PaperAccountLedger, RotationEvent, with_refreshed_hash
from .day_trade_policy import DayTradePolicy
from .execution_intent import ExecutionIntent
from .position_lifecycle import expiry_for_intent


ROTATION_PLANNER_VERSION = "dopey-pdt-safe-rotation-planner-v1"
ROTATION_PLAN_PATH = ARTIFACT_DIR / "rotation_plan.json"
ROTATION_PLANNER_PROOF_PATH = ARTIFACT_DIR / "rotation_planner_proof.jsonl"


@dataclass(frozen=True)
class RotationPlanDecision:
    candidate_id: str
    decision_type: str
    allowed: bool
    reason_codes: list[str]
    action_date: str
    related_position_id: str
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DelayedExitPlan:
    position_id: str
    earliest_exit_date: str
    reason_code: str
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AllowedEntryPlan:
    candidate_id: str
    action_date: str
    structure: str
    option_type: str
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BlockedActionPlan:
    candidate_id: str
    action_date: str
    decision_type: str
    reason_codes: list[str]
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RotationPlan:
    plan_id: str
    plan_date: str
    decisions: list[RotationPlanDecision] = field(default_factory=list)
    delayed_exits: list[DelayedExitPlan] = field(default_factory=list)
    allowed_entries: list[AllowedEntryPlan] = field(default_factory=list)
    blocked_actions: list[BlockedActionPlan] = field(default_factory=list)
    rotation_events: list[RotationEvent] = field(default_factory=list)
    paper_only: bool = True
    live_blocked: bool = True
    rotation_planner_version: str = ROTATION_PLANNER_VERSION
    plan_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["plan_hash"] = rotation_plan_hash(self)
        return payload


def build_rotation_plan(
    ledger: PaperAccountLedger,
    candidate_entries: list[ExecutionIntent],
    candidate_exits: list[ExecutionIntent],
    policy: DayTradePolicy,
    risk_throttle_summary: dict[str, Any],
    liquidity_summary: dict[str, Any],
    proof_scores: dict[str, float],
) -> RotationPlan:
    decisions: list[RotationPlanDecision] = []
    delayed_exits: list[DelayedExitPlan] = []
    allowed_entries: list[AllowedEntryPlan] = []
    blocked_actions: list[BlockedActionPlan] = []
    rotation_events: list[RotationEvent] = []
    plan_date = _plan_date(candidate_entries, candidate_exits)

    for exit_intent in candidate_exits:
        result = close_position(ledger, exit_intent, policy)
        related_position_id = exit_intent.related_open_position_id or exit_intent.position_id
        if result.accepted:
            decision = _decision(exit_intent.intent_id, "close_allowed", True, [], exit_intent.trade_date, related_position_id)
            decisions.append(decision)
        elif "same_day_round_trip_rejected" in result.reason_codes:
            matched = find_open_position(ledger, exit_intent)
            earliest = matched.close_eligible_date if matched is not None else ""
            decisions.append(_decision(exit_intent.intent_id, "close_delayed_until_next_trading_day", False, result.reason_codes, exit_intent.trade_date, related_position_id))
            delayed_exits.append(DelayedExitPlan(related_position_id, earliest, "same_day_round_trip_rejected", True, True))
            blocked_actions.append(_blocked(exit_intent.intent_id, exit_intent.trade_date, "blocked_same_day_round_trip", result.reason_codes))
        else:
            decision_type = _blocked_decision_type(result.reason_codes)
            decisions.append(_decision(exit_intent.intent_id, decision_type, False, result.reason_codes, exit_intent.trade_date, related_position_id))
            blocked_actions.append(_blocked(exit_intent.intent_id, exit_intent.trade_date, decision_type, result.reason_codes))

    for entry_intent in sorted(candidate_entries, key=lambda intent: proof_scores.get(intent.intent_id, 0.0), reverse=True):
        entry_blockers = _entry_blockers(entry_intent, risk_throttle_summary, liquidity_summary)
        if entry_blockers:
            decision_type = _blocked_decision_type(entry_blockers)
            decisions.append(_decision(entry_intent.intent_id, decision_type, False, entry_blockers, entry_intent.trade_date, ""))
            blocked_actions.append(_blocked(entry_intent.intent_id, entry_intent.trade_date, decision_type, entry_blockers))
            continue
        open_result = add_open_position(ledger, entry_intent, policy)
        if open_result.accepted:
            decisions.append(_decision(entry_intent.intent_id, "open_allowed", True, [], entry_intent.trade_date, ""))
            allowed_entries.append(AllowedEntryPlan(
                candidate_id=entry_intent.intent_id,
                action_date=entry_intent.trade_date,
                structure=entry_intent.structure,
                option_type=_option_type(entry_intent),
                paper_only=True,
                live_blocked=True,
            ))
        else:
            decision_type = _blocked_decision_type(open_result.reason_codes)
            decisions.append(_decision(entry_intent.intent_id, decision_type, False, open_result.reason_codes, entry_intent.trade_date, ""))
            blocked_actions.append(_blocked(entry_intent.intent_id, entry_intent.trade_date, decision_type, open_result.reason_codes))

    for delayed in delayed_exits:
        for allowed in allowed_entries:
            rotation_events.append(RotationEvent(
                rotation_id=f"rotation-{delayed.position_id}-{allowed.candidate_id}",
                from_position_id=delayed.position_id,
                to_candidate_id=allowed.candidate_id,
                rotation_date=plan_date,
                exit_allowed=False,
                entry_allowed=True,
                delayed_exit_required=True,
                same_day_round_trip_risk=True,
                zero_dte_exception_required=False,
                decision="rotate_allowed_after_delayed_exit",
                reason_codes=[delayed.reason_code],
            ))

    plan = RotationPlan(
        plan_id=f"rotation-plan-{plan_date}",
        plan_date=plan_date,
        decisions=decisions,
        delayed_exits=delayed_exits,
        allowed_entries=allowed_entries,
        blocked_actions=blocked_actions,
        rotation_events=rotation_events,
    )
    return RotationPlan(
        plan_id=plan.plan_id,
        plan_date=plan.plan_date,
        decisions=plan.decisions,
        delayed_exits=plan.delayed_exits,
        allowed_entries=plan.allowed_entries,
        blocked_actions=plan.blocked_actions,
        rotation_events=plan.rotation_events,
        paper_only=True,
        live_blocked=True,
        plan_hash=rotation_plan_hash(plan),
    )


def ledger_with_rotation_plan(ledger: PaperAccountLedger, plan: RotationPlan) -> PaperAccountLedger:
    updated = PaperAccountLedger(
        account_id=ledger.account_id,
        mode=ledger.mode,
        paper_only=ledger.paper_only,
        live_blocked=ledger.live_blocked,
        positions=list(ledger.positions),
        orders=list(ledger.orders),
        day_trade_events=list(ledger.day_trade_events),
        rotation_events=[*ledger.rotation_events, *plan.rotation_events],
        policy_snapshots=list(ledger.policy_snapshots),
    )
    return with_refreshed_hash(updated)


def write_rotation_plan_artifacts(plan: RotationPlan) -> dict[str, str]:
    ROTATION_PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROTATION_PLAN_PATH.write_text(json.dumps(plan.to_dict(), sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    proof_record = {
        "rotation_planner_version": ROTATION_PLANNER_VERSION,
        "artifact_type": "rotation_planner_proof",
        "plan": plan.to_dict(),
        "paper_only": True,
        "live_blocked": True,
    }
    proof_record["reproducibility_hash"] = _stable_hash(proof_record)
    with ROTATION_PLANNER_PROOF_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(proof_record, sort_keys=True, ensure_ascii=False) + "\n")
    return {
        "rotation_plan": str(ROTATION_PLAN_PATH),
        "rotation_planner_proof": str(ROTATION_PLANNER_PROOF_PATH),
    }


def rotation_plan_hash(plan: RotationPlan) -> str:
    payload = asdict(plan)
    payload["plan_hash"] = ""
    return _stable_hash(payload)


def _entry_blockers(
    intent: ExecutionIntent,
    risk_throttle_summary: dict[str, Any],
    liquidity_summary: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if intent.live_allowed:
        blockers.append("blocked_live_path")
    if risk_throttle_summary.get("entry_allowed", True) is False:
        blockers.append("blocked_risk_throttle")
    if liquidity_summary.get("entry_allowed", True) is False:
        blockers.append("blocked_liquidity")
    blockers.extend(_zero_dte_entry_blockers(intent))
    blockers.extend(_zero_dte_replay_entry_blockers(intent))
    return blockers


def _zero_dte_entry_blockers(intent: ExecutionIntent) -> list[str]:
    zero = intent.zero_dte or (bool(intent.trade_date) and expiry_for_intent(intent) == intent.trade_date)
    if not zero:
        return []
    decision = intent.zero_dte_risk_decision if isinstance(intent.zero_dte_risk_decision, dict) else {}
    if not decision:
        return ["zero_dte_risk_model_approval_required"]
    decision_name = str(decision.get("decision", ""))
    if decision_name == "prefer_non_zero_dte_alternative":
        return ["prefer_non_zero_dte_alternative"]
    if decision_name not in {"approved_for_paper_open", "approved_with_throttle"}:
        reason_codes = decision.get("reason_codes", [])
        extra = [str(reason) for reason in reason_codes] if isinstance(reason_codes, list) else []
        return _dedupe(["zero_dte_risk_model_rejected", *extra])
    return []


def _zero_dte_replay_entry_blockers(intent: ExecutionIntent) -> list[str]:
    zero = intent.zero_dte or (bool(intent.trade_date) and expiry_for_intent(intent) == intent.trade_date)
    if not zero:
        return []
    feedback = intent.zero_dte_replay_feedback if isinstance(intent.zero_dte_replay_feedback, dict) else {}
    if not feedback:
        return []
    recommendations = feedback.get("threshold_feedback", [])
    outcome_type = str(feedback.get("outcome_type", ""))
    if isinstance(recommendations, list) and "prefer_later_expiry_more_often" in recommendations:
        return ["zero_dte_replay_feedback_prefers_later_expiry"]
    if outcome_type == "prefer_later_expiry_confirmed":
        return ["zero_dte_replay_feedback_prefers_later_expiry"]
    return []


def _blocked_decision_type(reason_codes: list[str]) -> str:
    if "blocked_live_path" in reason_codes or "live_order_rejected" in reason_codes:
        return "blocked_live_path"
    if "blocked_risk_throttle" in reason_codes:
        return "blocked_risk_throttle"
    if "blocked_liquidity" in reason_codes:
        return "blocked_liquidity"
    if "prefer_non_zero_dte_alternative" in reason_codes or "later_expiry_alternative_preferred" in reason_codes or "zero_dte_replay_feedback_prefers_later_expiry" in reason_codes:
        return "prefer_non_zero_dte_alternative"
    if "zero_dte_risk_model_approval_required" in reason_codes or "zero_dte_risk_model_rejected" in reason_codes:
        return "blocked_zero_dte_risk_model"
    if "same_day_round_trip_rejected" in reason_codes:
        return "blocked_same_day_round_trip"
    if any(reason.startswith("zero_dte") for reason in reason_codes):
        return "blocked_zero_dte_missing_lifecycle"
    return "blocked_policy_violation"


def _decision(
    candidate_id: str,
    decision_type: str,
    allowed: bool,
    reason_codes: list[str],
    action_date: str,
    related_position_id: str,
) -> RotationPlanDecision:
    return RotationPlanDecision(candidate_id, decision_type, allowed, reason_codes, action_date, related_position_id, True, True)


def _blocked(candidate_id: str, action_date: str, decision_type: str, reason_codes: list[str]) -> BlockedActionPlan:
    return BlockedActionPlan(candidate_id, action_date, decision_type, reason_codes, True, True)


def _plan_date(candidate_entries: list[ExecutionIntent], candidate_exits: list[ExecutionIntent]) -> str:
    for intent in [*candidate_exits, *candidate_entries]:
        if intent.trade_date:
            return intent.trade_date
    return "1970-01-01"


def _option_type(intent: ExecutionIntent) -> str:
    if intent.structure == "long_call":
        return "call"
    if intent.structure == "long_put":
        return "put"
    for leg in intent.legs:
        value = leg.get("option_type", "")
        if isinstance(value, str) and value:
            return value
    return ""


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
