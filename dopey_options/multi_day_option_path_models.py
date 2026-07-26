"""Multi-day option path models for hybrid swing replay."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class MultiDayOptionState:
    state_id: str
    trading_day_index: int
    minute_index: int
    underlying_price: float
    option_mid: float
    option_bid: float
    option_ask: float
    spread_pct: float
    estimated_slippage: float
    delta: float
    gamma: float
    theta: float
    vega: float
    implied_volatility: float
    liquidity_score: float
    signal_state: str
    risk_event: str
    close_signal: str
    overnight_gap_state: str
    expiry_pressure_score: float
    paper_only: bool
    live_blocked: bool

    def __post_init__(self) -> None:
        if self.paper_only is not True or self.live_blocked is not True:
            raise ValueError("multi-day option state must be paper_only and live_blocked")
        if self.option_bid > self.option_mid or self.option_mid > self.option_ask:
            raise ValueError("option bid/mid/ask must be ordered")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "MultiDayOptionState":
        return cls(
            state_id=str(record["state_id"]),
            trading_day_index=int(record["trading_day_index"]),
            minute_index=int(record["minute_index"]),
            underlying_price=float(record["underlying_price"]),
            option_mid=float(record["option_mid"]),
            option_bid=float(record["option_bid"]),
            option_ask=float(record["option_ask"]),
            spread_pct=float(record["spread_pct"]),
            estimated_slippage=float(record["estimated_slippage"]),
            delta=float(record["delta"]),
            gamma=float(record["gamma"]),
            theta=float(record["theta"]),
            vega=float(record["vega"]),
            implied_volatility=float(record["implied_volatility"]),
            liquidity_score=float(record["liquidity_score"]),
            signal_state=str(record["signal_state"]),
            risk_event=str(record["risk_event"]),
            close_signal=str(record["close_signal"]),
            overnight_gap_state=str(record["overnight_gap_state"]),
            expiry_pressure_score=float(record["expiry_pressure_score"]),
            paper_only=bool(record["paper_only"]),
            live_blocked=bool(record["live_blocked"]),
        )
