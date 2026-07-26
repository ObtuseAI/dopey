"""Hybrid 0DTE versus swing replay models."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .swing_option_models import stable_hybrid_hash
from .zero_dte_adversarial_fixture_models import FORBIDDEN_LIVE_MARKET_TOKENS
from .zero_dte_cross_underlying_fixture_models import CROSS_UNDERLYING_REGIME_FAMILIES
from .zero_dte_underlying_family_models import SYNTHETIC_SYMBOLS_BY_FAMILY


HYBRID_EXPECTED_PREFERENCES: set[str] = {
    "prefer_zero_dte",
    "prefer_swing",
    "prefer_delayed_rotation",
    "prefer_no_trade",
    "inconclusive_needs_more_fixture_coverage",
}

HYBRID_PREFERRED_PATHS: set[str] = {
    "zero_dte",
    "swing",
    "delayed_rotation",
    "no_trade",
    "inconclusive_more_fixtures",
}

PREFERENCE_TO_PATH: dict[str, str] = {
    "prefer_zero_dte": "zero_dte",
    "prefer_swing": "swing",
    "prefer_delayed_rotation": "delayed_rotation",
    "prefer_no_trade": "no_trade",
    "inconclusive_needs_more_fixture_coverage": "inconclusive_more_fixtures",
}


@dataclass(frozen=True)
class HybridOpportunityPair:
    pair_id: str
    underlying_family_id: str
    synthetic_underlying_symbol: str
    regime_family: str
    option_type: str
    zero_dte_candidate_id: str
    swing_candidate_id: str
    shared_signal_id: str
    shared_thesis: str
    zero_dte_expected_decision: str
    swing_expected_decision: str
    expected_preference: str
    expected_rotation_action: str
    expected_no_day_trade_result: str
    paper_only: bool
    live_blocked: bool
    pair_hash: str

    def __post_init__(self) -> None:
        _validate_pair(self)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "HybridOpportunityPair":
        return cls(
            pair_id=str(record["pair_id"]),
            underlying_family_id=str(record["underlying_family_id"]),
            synthetic_underlying_symbol=str(record["synthetic_underlying_symbol"]),
            regime_family=str(record["regime_family"]),
            option_type=str(record["option_type"]),
            zero_dte_candidate_id=str(record["zero_dte_candidate_id"]),
            swing_candidate_id=str(record["swing_candidate_id"]),
            shared_signal_id=str(record["shared_signal_id"]),
            shared_thesis=str(record["shared_thesis"]),
            zero_dte_expected_decision=str(record["zero_dte_expected_decision"]),
            swing_expected_decision=str(record["swing_expected_decision"]),
            expected_preference=str(record["expected_preference"]),
            expected_rotation_action=str(record["expected_rotation_action"]),
            expected_no_day_trade_result=str(record["expected_no_day_trade_result"]),
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            pair_hash=str(record.get("pair_hash", "")),
        )


@dataclass(frozen=True)
class HybridReplayOutcome:
    hybrid_replay_id: str
    pair_id: str
    underlying_family_id: str
    regime_family: str
    option_type: str
    zero_dte_outcome_type: str
    swing_outcome_type: str
    preferred_path: str
    preference_score: float
    risk_adjusted_preference: str
    zero_dte_premium_outcome_pct: float
    swing_premium_outcome_pct: float
    zero_dte_max_adverse_excursion_pct: float
    swing_max_adverse_excursion_pct: float
    zero_dte_theta_decay_realized: float
    swing_theta_decay_realized: float
    zero_dte_gamma_instability: float
    swing_gamma_instability: float
    liquidity_penalty_comparison: str
    expiry_risk_comparison: str
    no_day_trade_constraint_result: str
    rotation_plan_result: str
    threshold_feedback: list[str]
    capital_allocator_tags: list[str]
    recursive_improvement_tags: list[str]
    paper_only: bool
    live_blocked: bool
    hybrid_replay_hash: str

    def __post_init__(self) -> None:
        if self.preferred_path not in HYBRID_PREFERRED_PATHS:
            raise ValueError(f"unsupported preferred_path: {self.preferred_path}")
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("hybrid replay outcome must be paper_only and live_blocked")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "HybridReplayOutcome":
        return cls(
            hybrid_replay_id=str(record["hybrid_replay_id"]),
            pair_id=str(record["pair_id"]),
            underlying_family_id=str(record["underlying_family_id"]),
            regime_family=str(record["regime_family"]),
            option_type=str(record["option_type"]),
            zero_dte_outcome_type=str(record["zero_dte_outcome_type"]),
            swing_outcome_type=str(record["swing_outcome_type"]),
            preferred_path=str(record["preferred_path"]),
            preference_score=float(record["preference_score"]),
            risk_adjusted_preference=str(record["risk_adjusted_preference"]),
            zero_dte_premium_outcome_pct=float(record["zero_dte_premium_outcome_pct"]),
            swing_premium_outcome_pct=float(record["swing_premium_outcome_pct"]),
            zero_dte_max_adverse_excursion_pct=float(record["zero_dte_max_adverse_excursion_pct"]),
            swing_max_adverse_excursion_pct=float(record["swing_max_adverse_excursion_pct"]),
            zero_dte_theta_decay_realized=float(record["zero_dte_theta_decay_realized"]),
            swing_theta_decay_realized=float(record["swing_theta_decay_realized"]),
            zero_dte_gamma_instability=float(record["zero_dte_gamma_instability"]),
            swing_gamma_instability=float(record["swing_gamma_instability"]),
            liquidity_penalty_comparison=str(record["liquidity_penalty_comparison"]),
            expiry_risk_comparison=str(record["expiry_risk_comparison"]),
            no_day_trade_constraint_result=str(record["no_day_trade_constraint_result"]),
            rotation_plan_result=str(record["rotation_plan_result"]),
            threshold_feedback=[str(value) for value in record["threshold_feedback"]],
            capital_allocator_tags=[str(value) for value in record["capital_allocator_tags"]],
            recursive_improvement_tags=[str(value) for value in record["recursive_improvement_tags"]],
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            hybrid_replay_hash=str(record.get("hybrid_replay_hash", "")),
        )


def hybrid_pair_hash(pair: HybridOpportunityPair) -> str:
    payload = pair.to_dict()
    payload["pair_hash"] = ""
    return stable_hybrid_hash(payload)


def hybrid_replay_hash(outcome: HybridReplayOutcome) -> str:
    payload = outcome.to_dict()
    payload["hybrid_replay_hash"] = ""
    return stable_hybrid_hash(payload)


def _validate_pair(pair: HybridOpportunityPair) -> None:
    if pair.option_type not in {"call", "put"}:
        raise ValueError(f"unsupported hybrid option_type: {pair.option_type}")
    if not pair.synthetic_underlying_symbol.startswith("SYN_"):
        raise ValueError(f"hybrid pair must use synthetic symbol: {pair.synthetic_underlying_symbol}")
    if pair.synthetic_underlying_symbol not in set(SYNTHETIC_SYMBOLS_BY_FAMILY.values()):
        raise ValueError(f"unknown synthetic symbol: {pair.synthetic_underlying_symbol}")
    if pair.regime_family not in CROSS_UNDERLYING_REGIME_FAMILIES:
        raise ValueError(f"unsupported hybrid regime: {pair.regime_family}")
    if not pair.zero_dte_candidate_id or not pair.swing_candidate_id:
        raise ValueError("hybrid pair requires zero_dte_candidate_id and swing_candidate_id")
    if pair.expected_preference not in HYBRID_EXPECTED_PREFERENCES:
        raise ValueError(f"unsupported expected preference: {pair.expected_preference}")
    if pair.paper_only is not True or pair.live_blocked is not True:
        raise ValueError("hybrid pair must be paper_only and live_blocked")
    encoded = json.dumps(pair.to_dict(), sort_keys=True, ensure_ascii=False).lower()
    if any(token in encoded for token in FORBIDDEN_LIVE_MARKET_TOKENS):
        raise ValueError("hybrid pair contains forbidden live market reference")
