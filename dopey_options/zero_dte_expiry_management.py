"""Paper-only expiry management simulation for 0DTE replay."""
from __future__ import annotations

from typing import Any

from .zero_dte_outcome_models import (
    ZeroDTEExpiryManagementRecord,
    ZeroDTEIntradayState,
    ZeroDTEReplayInput,
)


def simulate_zero_dte_expiry_management(
    replay_input: ZeroDTEReplayInput,
    states: list[ZeroDTEIntradayState],
    special_close_used: bool,
    special_close_would_reduce_risk: bool,
) -> ZeroDTEExpiryManagementRecord:
    if not states:
        raise ValueError("expiry management requires at least one intraday state")
    final_state = states[-1]
    intrinsic_value = intrinsic_value_estimate(
        replay_input.option_type,
        replay_input.strike,
        final_state.underlying_price,
    )
    expiry_state = expiry_state_for(replay_input, final_state, intrinsic_value, special_close_used)
    exit_value = intrinsic_value if intrinsic_value > 0.0 else final_state.option_bid
    premium_outcome_pct = round(((exit_value - replay_input.open_price) / max(replay_input.open_price, 0.01)) * 100.0, 6)
    risk_flags = expiry_risk_flags(final_state, intrinsic_value, replay_input.open_price)
    return ZeroDTEExpiryManagementRecord(
        replay_id=replay_input.replay_id,
        candidate_id=replay_input.candidate_id,
        expiry_state=expiry_state,
        intrinsic_value_estimate=round(intrinsic_value, 6),
        paper_premium_outcome_pct=premium_outcome_pct,
        risk_flags=risk_flags,
        special_close_would_reduce_risk=special_close_would_reduce_risk,
        expiry_managed_only_decision_correct=_expiry_managed_only_correct(replay_input, expiry_state, premium_outcome_pct),
        broker_instruction="none_simulated_only",
        paper_only=True,
        live_blocked=True,
    )


def intrinsic_value_estimate(option_type: str, strike: float, underlying_price: float) -> float:
    if option_type == "call":
        return round(max(0.0, underlying_price - strike), 6)
    if option_type == "put":
        return round(max(0.0, strike - underlying_price), 6)
    raise ValueError(f"unsupported 0DTE option_type for expiry replay: {option_type}")


def expiry_state_for(
    replay_input: ZeroDTEReplayInput,
    final_state: ZeroDTEIntradayState,
    intrinsic_value: float,
    special_close_used: bool,
) -> str:
    if final_state.risk_event == "pin_risk":
        return "pin_risk_simulated"
    if final_state.risk_event == "exercise_assignment_flag":
        return "assignment_exercise_risk_flagged_simulated_only"
    if special_close_used:
        return "expiry_managed_special_close"
    if replay_input.decision == "expiry_managed_only":
        return "expiry_managed_hold_to_close"
    if intrinsic_value > 0.0:
        return "expires_itm_intrinsic_value_simulated"
    return "expires_worthless_simulated"


def expiry_risk_flags(
    final_state: ZeroDTEIntradayState,
    intrinsic_value: float,
    open_price: float,
) -> list[str]:
    flags: list[str] = []
    if final_state.risk_event == "pin_risk":
        flags.append("pin_risk_simulated")
    if final_state.risk_event == "exercise_assignment_flag":
        flags.append("assignment_exercise_risk_flagged_simulated_only")
    if intrinsic_value <= 0.0:
        flags.append("expires_worthless_simulated")
    if intrinsic_value > 0.0:
        flags.append("expires_itm_intrinsic_value_simulated")
    if final_state.liquidity_score < 0.50:
        flags.append("late_day_liquidity_decay")
    if final_state.option_bid < open_price * 0.50:
        flags.append("premium_decay_exceeds_half")
    return _dedupe(flags)


def expiry_management_record_from_dict(record: dict[str, Any]) -> ZeroDTEExpiryManagementRecord:
    return ZeroDTEExpiryManagementRecord(
        replay_id=str(record["replay_id"]),
        candidate_id=str(record["candidate_id"]),
        expiry_state=str(record["expiry_state"]),
        intrinsic_value_estimate=float(record["intrinsic_value_estimate"]),
        paper_premium_outcome_pct=float(record["paper_premium_outcome_pct"]),
        risk_flags=[str(item) for item in record["risk_flags"]],
        special_close_would_reduce_risk=bool(record["special_close_would_reduce_risk"]),
        expiry_managed_only_decision_correct=bool(record["expiry_managed_only_decision_correct"]),
        broker_instruction=str(record["broker_instruction"]),
        paper_only=bool(record["paper_only"]),
        live_blocked=bool(record["live_blocked"]),
    )


def _expiry_managed_only_correct(replay_input: ZeroDTEReplayInput, expiry_state: str, premium_outcome_pct: float) -> bool:
    if replay_input.decision != "expiry_managed_only":
        return False
    if expiry_state == "pin_risk_simulated":
        return False
    return premium_outcome_pct >= -100.0


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output
