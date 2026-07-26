"""0DTE special lifecycle evaluator for active DOPEY paper options."""
from __future__ import annotations

from dataclasses import asdict, dataclass


ZERO_DTE_LIFECYCLE_VERSION = "dopey-zero-dte-lifecycle-v1"

ZERO_DTE_ALLOWED_STATES: frozenset[str] = frozenset({
    "hold_to_expiration_worthless_tolerant",
    "exercise_capable",
    "forced_broker_liquidation_tolerant",
    "zero_dte_special_lifecycle",
    "zero_dte_expiry_managed",
})


@dataclass(frozen=True)
class ZeroDteDecision:
    allowed: bool
    reason_code: str
    lifecycle_state: str
    is_normal_day_trade: bool
    zero_dte_lifecycle_version: str = ZERO_DTE_LIFECYCLE_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_zero_dte_lifecycle(
    dte: int,
    lifecycle_state: str,
    liquidity_approved: bool,
    risk_cap_approved: bool,
    reason_code: str,
    same_day_close_requested: bool,
) -> ZeroDteDecision:
    if dte != 0:
        return ZeroDteDecision(True, "not_zero_dte", lifecycle_state or "normal_hold", False)
    if lifecycle_state not in ZERO_DTE_ALLOWED_STATES:
        return ZeroDteDecision(False, "zero_dte_requires_special_lifecycle", "rejected", False)
    if not liquidity_approved:
        return ZeroDteDecision(False, "zero_dte_policy_violation_missing_liquidity_approval", "rejected", False)
    if not risk_cap_approved:
        return ZeroDteDecision(False, "zero_dte_policy_violation_missing_risk_cap", "rejected", False)
    if same_day_close_requested and not reason_code:
        return ZeroDteDecision(False, "zero_dte_special_close_requires_explicit_reason_code", "rejected", False)
    if same_day_close_requested:
        return ZeroDteDecision(True, "zero_dte_expiry_managed_not_normal_day_trade", "zero_dte_expiry_managed", False)
    return ZeroDteDecision(True, "zero_dte_special_lifecycle_approved", "zero_dte_special_lifecycle", False)
