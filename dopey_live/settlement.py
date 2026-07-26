"""Cash-account settlement model: entries are sized with SETTLED funds only.

The dedicated agentic account is a CASH account. Equity sale proceeds settle
T+1 (the next trading day after the sale's market date). Robinhood's reported
buying power in a cash account can include unsettled sale proceeds - spending
those is legal, but selling a position that was BOUGHT with unsettled proceeds
before those proceeds settle is a good-faith violation (GFV). The owner (not
the system) may sell any position at any time, so the only robust way to make
a system-caused GFV impossible is to never buy with unsettled funds at all.

Model, deliberately conservative in every direction:

- spendable_settled = max(0, buying_power - unsettled equity sale proceeds)
- a sale's proceeds are unsettled through every market date STRICTLY BEFORE
  its settlement date (next trading day after its market_date, rolling over
  weekends and XNYS holidays via dopey_core.market_calendar)
- partially filled sales count their filled portion as unsettled proceeds
- incomplete broker order history -> spendable 0 (fail closed: unknown recent
  sales could mean any dollar of buying power is unsettled)
- if buying power already excludes unsettled proceeds broker-side, this model
  double-subtracts and under-spends; conservative, never dangerous

This module is pure (no I/O, no broker calls): AccountSnapshot in, estimate
out. The service layer feeds the estimate's spendable figure to entry sizing
in place of raw buying power and embeds the whole estimate in the cycle
artifact so every sizing decision is auditable.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

from dopey_core.market_calendar import is_trading_day

from .models import AccountSnapshot

SETTLEMENT_MODEL_VERSION = "dopey-cash-settlement-v1"
EQUITY_SETTLEMENT_TRADING_DAYS = 1  # T+1 (US equities since 2024-05)
# Sales older than this many calendar days cannot still be unsettled under
# T+1 even across the longest exchange-holiday cluster; bounds the scan.
MAX_UNSETTLED_LOOKBACK_CALENDAR_DAYS = 7

MODEL_ASSUMPTIONS: tuple[str, ...] = (
    "cash_account_no_margin",
    "equity_sale_proceeds_settle_next_trading_day",
    "buying_power_may_include_unsettled_proceeds_so_they_are_subtracted",
    "incomplete_order_history_fails_closed_to_zero_spendable",
    "owner_manual_sells_expected_so_system_buys_settled_funds_only",
)


class SettlementModelError(ValueError):
    """Raised when broker order data cannot be interpreted safely."""


@dataclass(frozen=True)
class UnsettledSale:
    order_id: str
    symbol: str
    market_date: str
    settles_on: str
    proceeds_usd: float


@dataclass(frozen=True)
class SettledFundsEstimate:
    model_version: str
    as_of_market_date: str
    buying_power_usd: float
    unsettled_sale_proceeds_usd: float
    spendable_settled_usd: float
    unsettled_sales: tuple[UnsettledSale, ...]
    order_history_complete: bool
    fail_closed_reason: str
    assumptions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def equity_settlement_date(sale_market_date: date) -> date:
    """Next trading day after the sale's market date (T+1, holiday-aware)."""
    cursor = sale_market_date
    remaining = EQUITY_SETTLEMENT_TRADING_DAYS
    while remaining > 0:
        cursor = cursor + timedelta(days=1)
        if is_trading_day(cursor):
            remaining -= 1
    return cursor


def _sale_proceeds(order: dict[str, Any]) -> float:
    quantity = float(order.get("filled_quantity", 0.0))
    price = float(order.get("average_fill_price", 0.0))
    if not math.isfinite(quantity) or not math.isfinite(price) or quantity < 0.0 or price < 0.0:
        raise SettlementModelError(
            f"broker sale order has non-finite or negative fill fields: order_id={order.get('order_id')!r}"
        )
    return quantity * price


def estimate_settled_funds(
    account: AccountSnapshot,
    as_of_market_date: date,
) -> SettledFundsEstimate:
    buying_power = float(account.buying_power_usd)
    if not math.isfinite(buying_power) or buying_power < 0.0:
        buying_power = 0.0
    if not account.equity_order_history_complete:
        return SettledFundsEstimate(
            model_version=SETTLEMENT_MODEL_VERSION,
            as_of_market_date=as_of_market_date.isoformat(),
            buying_power_usd=buying_power,
            unsettled_sale_proceeds_usd=0.0,
            spendable_settled_usd=0.0,
            unsettled_sales=(),
            order_history_complete=False,
            fail_closed_reason="equity_order_history_incomplete_recent_sales_unknown",
            assumptions=MODEL_ASSUMPTIONS,
        )
    earliest_relevant = as_of_market_date - timedelta(
        days=MAX_UNSETTLED_LOOKBACK_CALENDAR_DAYS
    )
    unsettled: list[UnsettledSale] = []
    for order in account.recent_equity_orders:
        if str(order.get("side", "")).strip().lower() != "sell":
            continue
        if str(order.get("status", "")).strip().lower() not in {"filled", "partially_filled"}:
            continue
        raw_market_date = str(order.get("market_date", ""))
        try:
            sale_date = date.fromisoformat(raw_market_date)
        except ValueError as error:
            raise SettlementModelError(
                f"broker sale order market_date is invalid: order_id={order.get('order_id')!r}, "
                f"market_date={raw_market_date!r}"
            ) from error
        if sale_date < earliest_relevant:
            continue
        settles_on = equity_settlement_date(sale_date)
        if settles_on <= as_of_market_date:
            continue  # already settled
        proceeds = _sale_proceeds(order)
        if proceeds <= 0.0:
            continue
        unsettled.append(
            UnsettledSale(
                order_id=str(order.get("order_id", "")),
                symbol=str(order.get("symbol", "")),
                market_date=raw_market_date,
                settles_on=settles_on.isoformat(),
                proceeds_usd=round(proceeds, 2),
            )
        )
    unsettled_total = round(sum(sale.proceeds_usd for sale in unsettled), 2)
    spendable = max(0.0, round(buying_power - unsettled_total, 2))
    return SettledFundsEstimate(
        model_version=SETTLEMENT_MODEL_VERSION,
        as_of_market_date=as_of_market_date.isoformat(),
        buying_power_usd=buying_power,
        unsettled_sale_proceeds_usd=unsettled_total,
        spendable_settled_usd=spendable,
        unsettled_sales=tuple(sorted(unsettled, key=lambda sale: sale.order_id)),
        order_history_complete=True,
        fail_closed_reason="",
        assumptions=MODEL_ASSUMPTIONS,
    )
