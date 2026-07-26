"""Paper-only transaction-cost and execution-quality measurement.

The measurements follow the execution-quality vocabulary used by SEC Rule
605 while keeping simulated, model-priced, and observed evidence distinct.
This module evaluates completed paper observations; it cannot construct or
submit an order.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal

from dopey.protocols.identity import canonical_hash


ExecutionSide = Literal["buy", "sell"]
FillStatus = Literal["filled", "partial", "missed", "cancelled"]
ExecutionEvidenceClass = Literal[
    "observed_nbbo",
    "observed_consolidated_quote",
    "public_snapshot_quote",
    "simulated_quote",
    "model_price",
]


@dataclass(frozen=True, slots=True)
class ExecutionQualityPolicy:
    maximum_quote_age_ms: float
    maximum_effective_to_quoted_ratio: float
    require_one_minute_markout: bool
    require_five_minute_markout: bool
    observed_evidence_classes: tuple[ExecutionEvidenceClass, ...]


@dataclass(frozen=True, slots=True)
class PaperExecutionQualityInput:
    observation_id: str
    instrument_id: str
    side: ExecutionSide
    fill_status: FillStatus
    quantity: int
    package_leg_count: int
    arrival_bid: float
    arrival_ask: float
    arrival_benchmark_price: float
    executed_price: float | None
    post_trade_mid_1m: float | None
    post_trade_mid_5m: float | None
    fees: float
    quote_age_ms: float
    evidence_class: ExecutionEvidenceClass
    observed_at: str
    paper_only: bool
    live_blocked: bool


def v1_execution_quality_policy() -> ExecutionQualityPolicy:
    return ExecutionQualityPolicy(
        maximum_quote_age_ms=1_000.0,
        maximum_effective_to_quoted_ratio=1.0,
        require_one_minute_markout=True,
        require_five_minute_markout=True,
        observed_evidence_classes=(
            "observed_nbbo",
            "observed_consolidated_quote",
        ),
    )


def _validate_finite(value: float | None, field_name: str) -> None:
    if value is not None and not math.isfinite(value):
        raise ValueError(f"paper execution quality field must be finite: field={field_name}, value={value}")


def _validate_input(value: PaperExecutionQualityInput) -> None:
    if not value.observation_id.strip() or not value.instrument_id.strip():
        raise ValueError("paper execution quality identity fields cannot be empty")
    if value.paper_only is not True or value.live_blocked is not True:
        raise ValueError("paper execution quality input weakened the execution seal")
    if value.quantity <= 0 or value.package_leg_count <= 0:
        raise ValueError("paper execution quality quantity and package leg count must be positive")
    for field_name in (
        "arrival_bid",
        "arrival_ask",
        "arrival_benchmark_price",
        "executed_price",
        "post_trade_mid_1m",
        "post_trade_mid_5m",
        "fees",
        "quote_age_ms",
    ):
        _validate_finite(getattr(value, field_name), field_name)
    if value.arrival_bid < 0.0 or value.arrival_ask < 0.0:
        raise ValueError("paper execution quality arrival quote cannot be negative")
    if value.arrival_ask < value.arrival_bid:
        raise ValueError("paper execution quality arrival quote is crossed")
    if value.arrival_benchmark_price < 0.0 or value.fees < 0.0 or value.quote_age_ms < 0.0:
        raise ValueError("paper execution benchmark, fees, and quote age must be nonnegative")
    if value.fill_status in {"filled", "partial"} and value.executed_price is None:
        raise ValueError("filled paper execution quality input requires an executed price")
    if value.fill_status in {"missed", "cancelled"} and value.executed_price is not None:
        raise ValueError("unfilled paper execution quality input cannot contain an executed price")
    if value.executed_price is not None and value.executed_price < 0.0:
        raise ValueError("paper execution quality executed price cannot be negative")


def _customer_markout(side: ExecutionSide, executed_price: float, later_mid: float) -> float:
    return later_mid - executed_price if side == "buy" else executed_price - later_mid


def evaluate_paper_execution_quality(
    value: PaperExecutionQualityInput,
    policy: ExecutionQualityPolicy,
) -> dict[str, object]:
    """Return deterministic execution diagnostics without profitability credit."""

    _validate_input(value)
    if policy.maximum_quote_age_ms <= 0.0:
        raise ValueError("execution quality maximum quote age must be positive")
    if policy.maximum_effective_to_quoted_ratio <= 0.0:
        raise ValueError("execution quality spread-ratio limit must be positive")

    arrival_mid = (value.arrival_bid + value.arrival_ask) / 2.0
    quoted_spread = value.arrival_ask - value.arrival_bid
    observed_class = value.evidence_class in policy.observed_evidence_classes
    quote_fresh = value.quote_age_ms <= policy.maximum_quote_age_ms
    filled = value.fill_status in {"filled", "partial"}
    reason_codes: list[str] = []
    if not observed_class:
        reason_codes.append("execution_evidence_not_observed")
    if not quote_fresh:
        reason_codes.append("arrival_quote_stale")
    if not filled:
        reason_codes.append(f"paper_execution_{value.fill_status}")
    if policy.require_one_minute_markout and value.post_trade_mid_1m is None:
        reason_codes.append("missing_one_minute_markout")
    if policy.require_five_minute_markout and value.post_trade_mid_5m is None:
        reason_codes.append("missing_five_minute_markout")

    effective_spread: float | None = None
    effective_to_quoted: float | None = None
    price_improvement: float | None = None
    implementation_shortfall: float | None = None
    markout_1m: float | None = None
    markout_5m: float | None = None
    if value.executed_price is not None:
        effective_spread = 2.0 * abs(value.executed_price - arrival_mid)
        if quoted_spread > 0.0:
            effective_to_quoted = effective_spread / quoted_spread
            if effective_to_quoted > policy.maximum_effective_to_quoted_ratio:
                reason_codes.append("effective_spread_exceeds_policy")
        else:
            reason_codes.append("arrival_quote_zero_width")
        price_improvement = (
            value.arrival_ask - value.executed_price
            if value.side == "buy"
            else value.executed_price - value.arrival_bid
        )
        signed_price_difference = (
            value.executed_price - value.arrival_benchmark_price
            if value.side == "buy"
            else value.arrival_benchmark_price - value.executed_price
        )
        implementation_shortfall = signed_price_difference * value.quantity + value.fees
        if value.post_trade_mid_1m is not None:
            markout_1m = _customer_markout(value.side, value.executed_price, value.post_trade_mid_1m)
        if value.post_trade_mid_5m is not None:
            markout_5m = _customer_markout(value.side, value.executed_price, value.post_trade_mid_5m)

    calibration_eligible = observed_class and quote_fresh and filled and not reason_codes
    if not filled:
        status = "unfilled_no_execution_measurement"
    elif not observed_class:
        status = "uncalibrated_simulated_execution"
    elif calibration_eligible:
        status = "observed_execution_quality_validated"
    else:
        status = "observed_execution_quality_degraded"

    result: dict[str, object] = {
        "artifact_type": "paper_execution_quality_observation",
        "schema_version": "dopey-paper-execution-quality-v1",
        "observation_id": value.observation_id,
        "instrument_id": value.instrument_id,
        "status": status,
        "side": value.side,
        "fill_status": value.fill_status,
        "quantity": value.quantity,
        "package_leg_count": value.package_leg_count,
        "arrival_mid": round(arrival_mid, 10),
        "quoted_spread": round(quoted_spread, 10),
        "effective_spread": None if effective_spread is None else round(effective_spread, 10),
        "effective_to_quoted_ratio": None if effective_to_quoted is None else round(effective_to_quoted, 10),
        "price_improvement": None if price_improvement is None else round(price_improvement, 10),
        "implementation_shortfall": None if implementation_shortfall is None else round(implementation_shortfall, 10),
        "customer_markout_1m": None if markout_1m is None else round(markout_1m, 10),
        "customer_markout_5m": None if markout_5m is None else round(markout_5m, 10),
        "quote_fresh": quote_fresh,
        "observed_execution_evidence": observed_class,
        "execution_calibration_eligible": calibration_eligible,
        "strategy_profitability_evidence_eligible": False,
        "reason_codes": sorted(set(reason_codes)),
        "research_basis": [
            "SEC Rule 605 execution quality: quoted spread, effective spread, realized spread, and price improvement",
            "arrival-price implementation shortfall",
            "post-fill markout for adverse-selection diagnosis",
        ],
        "input": asdict(value),
        "policy": asdict(policy),
        "paper_only": True,
        "live_blocked": True,
        "order_construction_available": False,
    }
    result["reproducibility_hash"] = canonical_hash(result)
    return result
