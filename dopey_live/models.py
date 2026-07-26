"""Strict value models for Live Branch execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final, Literal


InstrumentKind = Literal["equity", "option"]
OrderSide = Literal["buy", "sell"]
AnalysisRelationship = Literal["self", "exact_underlying", "benchmark_proxy"]
EQUITY_SNAPSHOT_SOURCE: Final[str] = "official_robinhood_trading_mcp"


@dataclass(frozen=True)
class AccountSnapshot:
    authenticated: bool
    account_type: str
    buying_power_usd: float
    total_equity_usd: float
    equity_positions: tuple[dict[str, Any], ...]
    option_positions: tuple[dict[str, Any], ...]
    recent_equity_orders: tuple[dict[str, Any], ...]
    recent_option_orders: tuple[dict[str, Any], ...]
    equity_order_history_complete: bool
    option_order_history_complete: bool
    error: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EquityQuoteSnapshot:
    symbol: str
    bid_price: float
    ask_price: float
    last_price: float
    observed_at: str
    tradable: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EquityExecutionSnapshot:
    execution_quote: EquityQuoteSnapshot
    analysis_quote: EquityQuoteSnapshot
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiveExecutionIntent:
    intent_id: str
    instrument: InstrumentKind
    symbol: str
    side: OrderSide
    order_type: str
    limit_price: float
    time_in_force: str
    extended_hours: bool
    notional_usd: float
    quantity: float
    source_as_of_date: str
    source_hash: str
    thesis_direction: str
    analysis_symbol: str
    analysis_relationship: AnalysisRelationship
    analysis_reference_price: float
    analysis_invalidation_price: float
    analysis_target_price: float
    daily_leverage_multiple: float
    daily_reset: bool
    maximum_holding_sessions: int
    reference_price: float
    invalidation_price: float
    target_price: float
    expected_hold_trading_days: int
    execution_snapshot: EquityExecutionSnapshot | None
    option_contract: dict[str, Any]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def live_execution_intent_from_dict(payload: dict[str, Any]) -> LiveExecutionIntent:
    """Read current intents and migrate pre-analysis-symbol ledger rows safely."""
    migrated = dict(payload)
    symbol = str(migrated.get("symbol", ""))
    migrated["analysis_symbol"] = str(migrated.get("analysis_symbol", symbol))
    migrated["analysis_relationship"] = str(
        migrated.get("analysis_relationship", "self")
    )
    migrated["analysis_reference_price"] = float(
        migrated.get("analysis_reference_price", migrated.get("reference_price", 0.0))
    )
    migrated["analysis_invalidation_price"] = float(
        migrated.get(
            "analysis_invalidation_price", migrated.get("invalidation_price", 0.0)
        )
    )
    migrated["analysis_target_price"] = float(
        migrated.get("analysis_target_price", migrated.get("target_price", 0.0))
    )
    migrated["daily_leverage_multiple"] = float(
        migrated.get("daily_leverage_multiple", 1.0)
    )
    migrated["daily_reset"] = migrated.get("daily_reset") is True
    migrated["maximum_holding_sessions"] = int(
        migrated.get(
            "maximum_holding_sessions", migrated.get("expected_hold_trading_days", 0)
        )
    )
    raw_option_contract = migrated.get("option_contract", {})
    if not isinstance(raw_option_contract, dict):
        raise ValueError("Option contract must be an object")
    migrated["option_contract"] = dict(raw_option_contract)
    migrated["limit_price"] = float(
        migrated.get(
            "limit_price",
            raw_option_contract.get("limit_price", 0.0),
        )
    )
    raw_execution_snapshot = migrated.get("execution_snapshot")
    if raw_execution_snapshot is None:
        migrated["execution_snapshot"] = None
    elif isinstance(raw_execution_snapshot, dict):
        raw_execution_quote = raw_execution_snapshot.get("execution_quote")
        raw_analysis_quote = raw_execution_snapshot.get("analysis_quote")
        if not isinstance(raw_execution_quote, dict) or not isinstance(
            raw_analysis_quote, dict
        ):
            raise ValueError("Equity execution snapshot quote payloads must be objects")
        migrated["execution_snapshot"] = EquityExecutionSnapshot(
            execution_quote=EquityQuoteSnapshot(**raw_execution_quote),
            analysis_quote=EquityQuoteSnapshot(**raw_analysis_quote),
            source=str(raw_execution_snapshot.get("source", "")),
        )
    else:
        raise ValueError("Equity execution snapshot must be an object or null")
    migrated["reason_codes"] = tuple(
        str(value) for value in migrated.get("reason_codes", ())
    )
    return LiveExecutionIntent(**migrated)


@dataclass(frozen=True)
class GatewayOrderResult:
    review_succeeded: bool
    placed: bool
    order_id: str
    status: str
    filled_quantity: float
    average_fill_price: float
    submitted_at: str
    filled_at: str
    warnings: tuple[str, ...]
    error: str
    observed_tools: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
