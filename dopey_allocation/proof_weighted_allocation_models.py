"""Deterministic proof-weighted opportunity models."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


ALLOWED_STRATEGY_TYPES: frozenset[str] = frozenset({
    "zero_dte_long_call",
    "zero_dte_long_put",
    "swing_long_call",
    "swing_long_put",
    "delayed_rotation_long_call",
    "delayed_rotation_long_put",
    "no_trade",
})

ALLOWED_CANDIDATE_LIFECYCLES: frozenset[str] = frozenset({
    "zero_dte_special_lifecycle",
    "swing_multi_day",
    "next_day_close_eligible",
    "delayed_rotation",
    "blocked",
    "no_trade",
})

FORBIDDEN_ALLOCATION_TOKENS: frozenset[str] = frozenset({
    "api_key",
    "secret_key",
    "access_token",
    "refresh_token",
    "password",
    "buying_power",
    "account_balance",
    "robinhood_order",
    "alpaca_order",
    "tradier_order",
    "live_order",
})


@dataclass(frozen=True)
class ProofWeightedOpportunity:
    opportunity_id: str
    source_pair_id: str
    underlying_family_id: str
    synthetic_underlying_symbol: str
    regime_family: str
    option_type: str
    candidate_lifecycle: str
    preferred_path: str
    strategy_type: str
    proof_score: float
    signal_confidence: float
    risk_tier: str
    liquidity_score: float
    slippage_score: float
    spread_pct: float
    theta_pressure: float
    gamma_instability: float
    iv_overpayment_risk: float
    event_risk: float
    macro_risk: float
    overnight_gap_risk: float
    no_day_trade_constraint: str
    zero_dte_special_lifecycle_required: bool
    swing_next_day_close_eligible: bool
    delayed_rotation_required: bool
    threshold_survival_status: str
    hybrid_preference_score: float
    coverage_score: float
    contradiction_score: float
    paper_only: bool
    live_blocked: bool

    def __post_init__(self) -> None:
        _validate_opportunity(self)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ProofWeightedOpportunity":
        return cls(
            opportunity_id=str(record["opportunity_id"]),
            source_pair_id=str(record["source_pair_id"]),
            underlying_family_id=str(record["underlying_family_id"]),
            synthetic_underlying_symbol=str(record["synthetic_underlying_symbol"]),
            regime_family=str(record["regime_family"]),
            option_type=str(record["option_type"]),
            candidate_lifecycle=str(record["candidate_lifecycle"]),
            preferred_path=str(record["preferred_path"]),
            strategy_type=str(record["strategy_type"]),
            proof_score=float(record["proof_score"]),
            signal_confidence=float(record["signal_confidence"]),
            risk_tier=str(record["risk_tier"]),
            liquidity_score=float(record["liquidity_score"]),
            slippage_score=float(record["slippage_score"]),
            spread_pct=float(record["spread_pct"]),
            theta_pressure=float(record["theta_pressure"]),
            gamma_instability=float(record["gamma_instability"]),
            iv_overpayment_risk=float(record["iv_overpayment_risk"]),
            event_risk=float(record["event_risk"]),
            macro_risk=float(record["macro_risk"]),
            overnight_gap_risk=float(record["overnight_gap_risk"]),
            no_day_trade_constraint=str(record["no_day_trade_constraint"]),
            zero_dte_special_lifecycle_required=bool(record["zero_dte_special_lifecycle_required"]),
            swing_next_day_close_eligible=bool(record["swing_next_day_close_eligible"]),
            delayed_rotation_required=bool(record["delayed_rotation_required"]),
            threshold_survival_status=str(record["threshold_survival_status"]),
            hybrid_preference_score=float(record["hybrid_preference_score"]),
            coverage_score=float(record["coverage_score"]),
            contradiction_score=float(record["contradiction_score"]),
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
        )


def stable_allocation_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _validate_opportunity(opportunity: ProofWeightedOpportunity) -> None:
    if opportunity.strategy_type not in ALLOWED_STRATEGY_TYPES:
        raise ValueError(f"unsupported allocation strategy_type: {opportunity.strategy_type}")
    if opportunity.candidate_lifecycle not in ALLOWED_CANDIDATE_LIFECYCLES:
        raise ValueError(f"unsupported candidate_lifecycle: {opportunity.candidate_lifecycle}")
    if opportunity.option_type not in {"call", "put", "none"}:
        raise ValueError(f"unsupported option_type: {opportunity.option_type}")
    if not opportunity.synthetic_underlying_symbol.startswith("SYN_"):
        raise ValueError(f"allocation opportunity must use synthetic symbol: {opportunity.synthetic_underlying_symbol}")
    if opportunity.paper_only is not True or opportunity.live_blocked is not True:
        raise ValueError("allocation opportunity must be paper_only and live_blocked")
    encoded = json.dumps(opportunity.to_dict(), sort_keys=True, ensure_ascii=False).lower()
    if any(token in encoded for token in FORBIDDEN_ALLOCATION_TOKENS):
        raise ValueError("allocation opportunity contains forbidden live, broker, credential, or real sizing reference")
