"""Deterministic swing option candidate models for hybrid 0DTE replay."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from .zero_dte_adversarial_fixture_models import FORBIDDEN_LIVE_MARKET_TOKENS
from .zero_dte_underlying_family_models import SYNTHETIC_SYMBOLS_BY_FAMILY


ALLOWED_SWING_OPTION_TYPES: set[str] = {"call", "put"}
ALLOWED_SWING_ACTIONS: set[str] = {"buy_to_open", "sell_to_close"}
DISALLOWED_SWING_STRUCTURES: set[str] = {
    "sell_to_open",
    "naked_sale",
    "uncovered_writing",
    "undefined_risk_structure",
    "unsupported_spread",
    "live_path",
}


@dataclass(frozen=True)
class SwingOptionCandidate:
    candidate_id: str
    underlying_family_id: str
    synthetic_underlying_symbol: str
    option_type: str
    trade_date: str
    expiry: str
    days_to_expiry: int
    strike: float
    moneyness: str
    open_price: float
    risk_tier: str
    proof_score: float
    signal_confidence: float
    liquidity_score: float
    slippage_score: float
    spread_pct: float
    delta: float
    gamma: float
    theta: float
    vega: float
    implied_volatility: float
    event_risk_score: float
    regime_score: float
    expected_hold_days: int
    explicit_thesis: str
    explicit_exit_plan: str
    entry_action: str
    exit_action: str
    paper_only: bool
    live_blocked: bool
    candidate_hash: str

    def __post_init__(self) -> None:
        _validate_swing_candidate(self)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "SwingOptionCandidate":
        return cls(
            candidate_id=str(record["candidate_id"]),
            underlying_family_id=str(record["underlying_family_id"]),
            synthetic_underlying_symbol=str(record["synthetic_underlying_symbol"]),
            option_type=str(record["option_type"]),
            trade_date=str(record["trade_date"]),
            expiry=str(record["expiry"]),
            days_to_expiry=int(record["days_to_expiry"]),
            strike=float(record["strike"]),
            moneyness=str(record["moneyness"]),
            open_price=float(record["open_price"]),
            risk_tier=str(record["risk_tier"]),
            proof_score=float(record["proof_score"]),
            signal_confidence=float(record["signal_confidence"]),
            liquidity_score=float(record["liquidity_score"]),
            slippage_score=float(record["slippage_score"]),
            spread_pct=float(record["spread_pct"]),
            delta=float(record["delta"]),
            gamma=float(record["gamma"]),
            theta=float(record["theta"]),
            vega=float(record["vega"]),
            implied_volatility=float(record["implied_volatility"]),
            event_risk_score=float(record["event_risk_score"]),
            regime_score=float(record["regime_score"]),
            expected_hold_days=int(record["expected_hold_days"]),
            explicit_thesis=str(record["explicit_thesis"]),
            explicit_exit_plan=str(record["explicit_exit_plan"]),
            entry_action=str(record.get("entry_action", "buy_to_open")),
            exit_action=str(record.get("exit_action", "sell_to_close")),
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
            candidate_hash=str(record.get("candidate_hash", "")),
        )


def swing_option_candidate_hash(candidate: SwingOptionCandidate) -> str:
    payload = candidate.to_dict()
    payload["candidate_hash"] = ""
    return stable_hybrid_hash(payload)


def stable_hybrid_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _validate_swing_candidate(candidate: SwingOptionCandidate) -> None:
    if candidate.option_type not in ALLOWED_SWING_OPTION_TYPES:
        raise ValueError(f"unsupported swing option_type: {candidate.option_type}")
    if not candidate.synthetic_underlying_symbol.startswith("SYN_"):
        raise ValueError(f"swing candidate must use synthetic symbol: {candidate.synthetic_underlying_symbol}")
    if candidate.synthetic_underlying_symbol not in set(SYNTHETIC_SYMBOLS_BY_FAMILY.values()):
        raise ValueError(f"unknown synthetic symbol: {candidate.synthetic_underlying_symbol}")
    if candidate.entry_action != "buy_to_open":
        raise ValueError(f"swing entry must be buy_to_open, got {candidate.entry_action}")
    if candidate.exit_action != "sell_to_close":
        raise ValueError(f"swing exit must be sell_to_close, got {candidate.exit_action}")
    if any(value in {candidate.entry_action, candidate.exit_action, candidate.risk_tier} for value in DISALLOWED_SWING_STRUCTURES):
        raise ValueError("swing candidate contains disallowed structure or action")
    if candidate.days_to_expiry < 1:
        raise ValueError("swing candidate must have at least one day to expiry")
    if candidate.expected_hold_days < 1:
        raise ValueError("swing candidate expected_hold_days must be positive")
    if not candidate.explicit_thesis:
        raise ValueError("swing candidate requires explicit_thesis")
    if not candidate.explicit_exit_plan:
        raise ValueError("swing candidate requires explicit_exit_plan")
    if candidate.paper_only is not True or candidate.live_blocked is not True:
        raise ValueError("swing candidate must be paper_only and live_blocked")
    encoded = json.dumps(candidate.to_dict(), sort_keys=True, ensure_ascii=False).lower()
    if any(token in encoded for token in FORBIDDEN_LIVE_MARKET_TOKENS):
        raise ValueError("swing candidate contains forbidden live market reference")
