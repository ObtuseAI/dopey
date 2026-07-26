"""Quote validation and explicit three-price separation for paper research."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Literal

from .identity import canonical_hash, parse_utc, require_sha256, require_utc_iso


PaperPriceDirection = Literal["debit", "credit"]
QuoteEvidenceTier = Literal[
    "public_snapshot_quote",
    "nbbo_quote",
    "broker_preview",
    "paper_executable_model",
    "realized_fill",
]


@dataclass(frozen=True, slots=True)
class QuoteSnapshot:
    contract_id: str
    chain_id: str
    observed_at: str
    received_at: str
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    last: float
    volume: int
    open_interest: int
    source_uri: str
    source_record_hash: str
    content_hash: str
    venue: str
    quote_condition: Literal["regular", "fast", "halted", "nonfirm", "unknown"]
    evidence_tier: QuoteEvidenceTier
    chain_complete: bool
    option_style: Literal["american", "european"]
    settlement_type: Literal["physical", "cash"]
    contract_multiplier: int
    deliverable: str
    adjustment_required: bool
    adjustment_validated: bool
    underlying: str
    option_type: Literal["call", "put"]
    expiry: str
    strike: float


@dataclass(frozen=True, slots=True)
class QuoteGatePolicy:
    maximum_age_seconds: float
    maximum_relative_spread: float
    minimum_bid: float
    minimum_volume: int
    minimum_open_interest: int


@dataclass(frozen=True, slots=True)
class QuoteGateDecision:
    passed: bool
    reason_codes: tuple[str, ...]
    age_seconds: float
    relative_spread: float


@dataclass(frozen=True, slots=True)
class PriceTriple:
    contract_id: str
    contract_identity_hash: str
    quote_snapshot: QuoteSnapshot
    quote_source_hash: str
    quote_content_hash: str
    quote_gate_hash: str
    decision_timestamp: str
    contract_multiplier: int
    observed_midpoint: float
    model_fair_value: float
    conservative_paper_executable: float
    price_direction: PaperPriceDirection
    slippage_basis_points: float
    commission_per_contract: float
    paper_executable_is_simulated: bool
    profitability_evidence_eligible: bool


@dataclass(frozen=True, slots=True)
class LaterFairValueWitness:
    contract_id: str
    witnessed_at: str
    source_record_hash: str
    fair_value: float
    underlying_price: float
    implied_volatility: float


def quote_snapshot_content_hash(quote: QuoteSnapshot) -> str:
    return canonical_hash(
        {
            "contract_id": quote.contract_id,
            "chain_id": quote.chain_id,
            "observed_at": quote.observed_at,
            "received_at": quote.received_at,
            "bid": quote.bid,
            "ask": quote.ask,
            "bid_size": quote.bid_size,
            "ask_size": quote.ask_size,
            "last": quote.last,
            "volume": quote.volume,
            "open_interest": quote.open_interest,
            "source_uri": quote.source_uri,
            "source_record_hash": quote.source_record_hash,
            "venue": quote.venue,
            "quote_condition": quote.quote_condition,
            "evidence_tier": quote.evidence_tier,
            "chain_complete": quote.chain_complete,
            "option_style": quote.option_style,
            "settlement_type": quote.settlement_type,
            "contract_multiplier": quote.contract_multiplier,
            "deliverable": quote.deliverable,
            "adjustment_required": quote.adjustment_required,
            "adjustment_validated": quote.adjustment_validated,
            "underlying": quote.underlying,
            "option_type": quote.option_type,
            "expiry": quote.expiry,
            "strike": quote.strike,
        }
    )


def contract_identity_hash(
    contract_id: str,
    underlying: str,
    option_type: str,
    expiry: str,
    strike: float,
    contract_multiplier: int,
    deliverable: str,
    option_style: str,
    settlement_type: str,
) -> str:
    return canonical_hash(
        {
            "contract_id": contract_id,
            "underlying": underlying,
            "option_type": option_type,
            "expiry": expiry,
            "strike": strike,
            "contract_multiplier": contract_multiplier,
            "deliverable": deliverable,
            "option_style": option_style,
            "settlement_type": settlement_type,
        }
    )


def quote_contract_identity_hash(quote: QuoteSnapshot) -> str:
    return contract_identity_hash(
        quote.contract_id,
        quote.underlying,
        quote.option_type,
        quote.expiry,
        quote.strike,
        quote.contract_multiplier,
        quote.deliverable,
        quote.option_style,
        quote.settlement_type,
    )


def validate_quote_snapshot_identity(quote: QuoteSnapshot) -> None:
    require_sha256(quote.source_record_hash, "quote.source_record_hash")
    require_sha256(quote.content_hash, "quote.content_hash")
    if not isinstance(quote.underlying, str) or not quote.underlying:
        raise ValueError("quote underlying must be a non-empty string")
    if not isinstance(quote.option_type, str) or quote.option_type not in ("call", "put"):
        raise ValueError(f"unsupported quote option type: option_type={quote.option_type!r}")
    if not isinstance(quote.expiry, str):
        raise ValueError("quote expiry must be a string")
    try:
        date.fromisoformat(quote.expiry)
    except ValueError as error:
        raise ValueError(f"quote expiry must be an ISO date: expiry={quote.expiry!r}") from error
    if not isinstance(quote.strike, (int, float)) or isinstance(quote.strike, bool):
        raise ValueError("quote strike must be numeric")
    if not math.isfinite(float(quote.strike)) or float(quote.strike) <= 0.0:
        raise ValueError("quote strike must be positive and finite")
    if quote.content_hash != quote_snapshot_content_hash(quote):
        raise ValueError("quote content hash does not match the quote fields")


def quote_gate_hash(
    contract_id: str,
    quote_source_hash: str,
    quote_content_hash: str,
    decision_timestamp: str,
    gate: QuoteGateDecision,
) -> str:
    return canonical_hash(
        {
            "contract_id": contract_id,
            "quote_source_hash": quote_source_hash,
            "quote_content_hash": quote_content_hash,
            "decision_timestamp": decision_timestamp,
            "age_seconds": gate.age_seconds,
            "relative_spread": gate.relative_spread,
            "reason_codes": list(gate.reason_codes),
            "passed": gate.passed,
        }
    )


def relative_spread(bid: float, ask: float) -> float:
    midpoint = (bid + ask) / 2.0
    return (ask - bid) / midpoint if midpoint > 0.0 else math.inf


def evaluate_quote_gate(
    quote: QuoteSnapshot,
    decision_timestamp: str,
    policy: QuoteGatePolicy,
) -> QuoteGateDecision:
    require_utc_iso(quote.observed_at)
    require_utc_iso(quote.received_at)
    require_utc_iso(decision_timestamp)
    policy_values = (
        policy.maximum_age_seconds,
        policy.maximum_relative_spread,
        policy.minimum_bid,
    )
    if not all(math.isfinite(value) and value >= 0.0 for value in policy_values):
        raise ValueError("quote-gate numeric policy fields must be finite and nonnegative")
    if not 0.0 < policy.maximum_relative_spread < 1.0:
        raise ValueError("maximum relative spread must be within (0, 1)")
    if policy.minimum_volume < 0 or policy.minimum_open_interest < 0:
        raise ValueError("quote-gate volume and open-interest floors cannot be negative")
    reasons: list[str] = []
    if (
        not quote.contract_id
        or not quote.chain_id
        or not quote.source_uri
        or not quote.venue
    ):
        reasons.append("quote_identity_incomplete")
    try:
        validate_quote_snapshot_identity(quote)
    except ValueError:
        reasons.append("quote_identity_incomplete")
    if quote.evidence_tier != "nbbo_quote":
        reasons.append(f"quote_tier_not_paper_executable:{quote.evidence_tier}")
    if quote.quote_condition != "regular":
        reasons.append(f"quote_condition_not_firm:{quote.quote_condition}")
    if not quote.chain_complete:
        reasons.append("chain_incomplete")
    if (
        not isinstance(quote.bid_size, int)
        or isinstance(quote.bid_size, bool)
        or not isinstance(quote.ask_size, int)
        or isinstance(quote.ask_size, bool)
        or quote.bid_size <= 0
        or quote.ask_size <= 0
    ):
        reasons.append("quote_size_missing")
    if quote.contract_multiplier <= 0 or not quote.deliverable:
        reasons.append("contract_terms_incomplete")
    if quote.option_style not in {"american", "european"} or quote.settlement_type not in {"physical", "cash"}:
        reasons.append("contract_terms_incomplete")
    if not all(math.isfinite(value) for value in (quote.bid, quote.ask, quote.last)):
        reasons.append("quote_non_finite")
    if quote.bid < 0.0:
        reasons.append("negative_bid")
    if quote.ask <= 0.0:
        reasons.append("nonpositive_ask")
    if quote.ask < quote.bid:
        reasons.append("crossed_market")
    if quote.bid < policy.minimum_bid:
        reasons.append("bid_below_policy_floor")
    spread = relative_spread(quote.bid, quote.ask)
    if spread > policy.maximum_relative_spread:
        reasons.append("relative_spread_above_limit")
    if quote.volume < 0 or quote.open_interest < 0:
        reasons.append("negative_participation_measurement")
    if quote.volume < policy.minimum_volume:
        reasons.append("volume_below_limit")
    if quote.open_interest < policy.minimum_open_interest:
        reasons.append("open_interest_below_limit")
    if quote.adjustment_required and not quote.adjustment_validated:
        reasons.append("contract_adjustment_unvalidated")
    observed_time = parse_utc(quote.observed_at)
    received_time = parse_utc(quote.received_at)
    decision_time = parse_utc(decision_timestamp)
    if received_time < observed_time:
        reasons.append("receipt_precedes_observation")
    if received_time > decision_time:
        reasons.append("quote_not_available_at_decision")
    age_seconds = (decision_time - observed_time).total_seconds()
    if age_seconds < 0.0:
        reasons.append("future_quote_leakage")
    if age_seconds > policy.maximum_age_seconds:
        reasons.append("stale_quote")
    return QuoteGateDecision(
        passed=not reasons,
        reason_codes=tuple(sorted(set(reasons))),
        age_seconds=age_seconds,
        relative_spread=spread,
    )


def build_price_triple(
    quote: QuoteSnapshot,
    decision_timestamp: str,
    policy: QuoteGatePolicy,
    model_fair_value: float,
    price_direction: PaperPriceDirection,
    slippage_basis_points: float,
    commission_per_contract: float,
    contract_multiplier: int,
) -> PriceTriple:
    gate = evaluate_quote_gate(quote, decision_timestamp, policy)
    if not gate.passed:
        raise ValueError(
            "conservative paper executable price requires a passing quote gate: "
            f"reason_codes={gate.reason_codes}"
        )
    if quote.bid < 0.0 or quote.ask <= 0.0 or quote.ask < quote.bid:
        raise ValueError(
            "price triple requires a valid, uncrossed quote: "
            f"bid={quote.bid}, ask={quote.ask}"
        )
    if not math.isfinite(model_fair_value) or model_fair_value <= 0.0:
        raise ValueError(f"model fair value must be positive and finite: value={model_fair_value}")
    if (
        not math.isfinite(slippage_basis_points)
        or not math.isfinite(commission_per_contract)
        or slippage_basis_points < 0.0
        or commission_per_contract < 0.0
    ):
        raise ValueError("slippage and commission cannot be negative")
    if contract_multiplier <= 0:
        raise ValueError("contract multiplier must be positive")
    if contract_multiplier != quote.contract_multiplier:
        raise ValueError(
            "contract multiplier does not match quote identity: "
            f"requested={contract_multiplier}, quote={quote.contract_multiplier}"
        )
    midpoint = (quote.bid + quote.ask) / 2.0
    slippage_fraction = slippage_basis_points / 10_000.0
    unit_commission = commission_per_contract / float(contract_multiplier)
    if price_direction == "debit":
        paper_price = quote.ask * (1.0 + slippage_fraction) + unit_commission
    elif price_direction == "credit":
        paper_price = max(0.0, quote.bid * (1.0 - slippage_fraction) - unit_commission)
    else:
        raise ValueError(f"unsupported paper price direction: direction={price_direction!r}")
    return PriceTriple(
        contract_id=quote.contract_id,
        contract_identity_hash=quote_contract_identity_hash(quote),
        quote_snapshot=quote,
        quote_source_hash=quote.source_record_hash,
        quote_content_hash=quote.content_hash,
        quote_gate_hash=quote_gate_hash(
            quote.contract_id,
            quote.source_record_hash,
            quote.content_hash,
            decision_timestamp,
            gate,
        ),
        decision_timestamp=decision_timestamp,
        contract_multiplier=contract_multiplier,
        observed_midpoint=round(midpoint, 8),
        model_fair_value=round(model_fair_value, 8),
        conservative_paper_executable=round(paper_price, 8),
        price_direction=price_direction,
        slippage_basis_points=slippage_basis_points,
        commission_per_contract=commission_per_contract,
        paper_executable_is_simulated=True,
        profitability_evidence_eligible=False,
    )


def validate_later_fair_value_witness(
    witness: LaterFairValueWitness,
    decision_timestamp: str,
) -> None:
    require_utc_iso(witness.witnessed_at)
    require_utc_iso(decision_timestamp)
    if parse_utc(witness.witnessed_at) <= parse_utc(decision_timestamp):
        raise ValueError(
            "later fair-value witness must occur after the frozen decision: "
            f"decision_timestamp={decision_timestamp}, witnessed_at={witness.witnessed_at}"
        )
    if len(witness.source_record_hash) != 64 or any(
        character not in "0123456789abcdef" for character in witness.source_record_hash
    ):
        raise ValueError("later fair-value witness requires a hexadecimal SHA-256 source identity")
    values = (witness.fair_value, witness.underlying_price, witness.implied_volatility)
    if not all(math.isfinite(value) and value >= 0.0 for value in values):
        raise ValueError("later fair-value witness values must be finite and nonnegative")
