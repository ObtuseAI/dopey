"""Paper portfolio position models."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .portfolio_hashing import stable_portfolio_hash


ALLOWED_PORTFOLIO_OPTION_TYPES: frozenset[str] = frozenset({"call", "put"})
ALLOWED_PORTFOLIO_STRATEGY_TYPES: frozenset[str] = frozenset({
    "zero_dte_long_call",
    "zero_dte_long_put",
    "swing_long_call",
    "swing_long_put",
    "delayed_rotation_long_call",
    "delayed_rotation_long_put",
})
FORBIDDEN_PORTFOLIO_TOKENS: frozenset[str] = frozenset({
    "sell_to_open",
    "naked",
    "uncovered",
    "undefined_risk",
    "unsupported_spread",
    "api_key",
    "secret_key",
    "access_token",
    "refresh_token",
    "password",
    "buying_power",
    "account_balance",
    "usd",
    "$",
    "live_order",
    "robinhood_order",
    "alpaca_order",
    "tradier_order",
    "place_order",
})


@dataclass(frozen=True)
class PaperPortfolioPosition:
    portfolio_position_id: str
    source_allocation_id: str
    opportunity_id: str
    underlying_family_id: str
    synthetic_underlying_symbol: str
    regime_family: str
    option_type: str
    strategy_type: str
    lifecycle: str
    open_day_index: int
    close_eligible_day_index: int
    planned_close_day_index: int
    paper_attention_weight: float
    paper_premium_risk_units: float
    max_paper_contract_units: int
    current_paper_state: str
    same_day_close_blocked: bool
    zero_dte_special_lifecycle: bool
    delayed_rotation_flag: bool
    paper_shadow_flag: bool
    paper_only: bool
    live_blocked: bool

    def __post_init__(self) -> None:
        _validate_position(self)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "PaperPortfolioPosition":
        return cls(
            portfolio_position_id=str(record["portfolio_position_id"]),
            source_allocation_id=str(record["source_allocation_id"]),
            opportunity_id=str(record["opportunity_id"]),
            underlying_family_id=str(record["underlying_family_id"]),
            synthetic_underlying_symbol=str(record["synthetic_underlying_symbol"]),
            regime_family=str(record["regime_family"]),
            option_type=str(record["option_type"]),
            strategy_type=str(record["strategy_type"]),
            lifecycle=str(record["lifecycle"]),
            open_day_index=int(record["open_day_index"]),
            close_eligible_day_index=int(record["close_eligible_day_index"]),
            planned_close_day_index=int(record["planned_close_day_index"]),
            paper_attention_weight=float(record["paper_attention_weight"]),
            paper_premium_risk_units=float(record["paper_premium_risk_units"]),
            max_paper_contract_units=int(record["max_paper_contract_units"]),
            current_paper_state=str(record["current_paper_state"]),
            same_day_close_blocked=bool(record["same_day_close_blocked"]),
            zero_dte_special_lifecycle=bool(record["zero_dte_special_lifecycle"]),
            delayed_rotation_flag=bool(record["delayed_rotation_flag"]),
            paper_shadow_flag=bool(record["paper_shadow_flag"]),
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
        )


def portfolio_position_hash(position: PaperPortfolioPosition) -> str:
    payload = position.to_dict()
    return stable_portfolio_hash(payload)


def _validate_position(position: PaperPortfolioPosition) -> None:
    if position.option_type not in ALLOWED_PORTFOLIO_OPTION_TYPES:
        raise ValueError(f"unsupported portfolio option_type: {position.option_type}")
    if position.strategy_type not in ALLOWED_PORTFOLIO_STRATEGY_TYPES:
        raise ValueError(f"unsupported portfolio strategy_type: {position.strategy_type}")
    if not position.synthetic_underlying_symbol.startswith("SYN_"):
        raise ValueError(f"portfolio position must use synthetic symbol: {position.synthetic_underlying_symbol}")
    if position.paper_attention_weight < 0.0 or position.paper_premium_risk_units < 0.0:
        raise ValueError("portfolio position abstract units must be non-negative")
    if position.max_paper_contract_units < 0:
        raise ValueError("portfolio position contract units must be non-negative")
    if position.close_eligible_day_index < position.open_day_index:
        raise ValueError("close eligibility cannot precede open day")
    if position.planned_close_day_index < position.open_day_index:
        raise ValueError("planned close cannot precede open day")
    if position.paper_only is not True or position.live_blocked is not True:
        raise ValueError("portfolio position must be paper_only and live_blocked")
    encoded = json.dumps(position.to_dict(), sort_keys=True, ensure_ascii=False).lower()
    if "live_path" in encoded:
        raise ValueError("portfolio position cannot contain live path")
    if any(token in encoded for token in FORBIDDEN_PORTFOLIO_TOKENS):
        raise ValueError("portfolio position contains forbidden live, broker, credential, or real sizing reference")

