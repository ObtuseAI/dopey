"""Trade Memory Graph: case-based conditional retrieval over trade history.

Rather than forever hunting new strategies, DOPEY should learn from its own
history: for a candidate setup, find similar past trades and report their
CONDITIONAL outcomes - "this resembles N prior long_put/relative_strength
trades; they lost more when the stock was already stretched above its 20-day
average." That is far more useful than a generic score, and it compounds:
every trade the system settles makes the memory sharper.

The corpus is the honest backtest trade ledger (real-history, cost-aware,
321k+ records with MFE/MAE and exit reasons). Each record is enriched with
point-in-time conditions from the spine AT THE SIGNAL DATE - distance from the
20-day average, trailing realized volatility, trailing 5-day return - so the
memory can slice outcomes by the market context a candidate is actually in.

Deterministic and measure-only: it retrieves and summarizes prior outcomes;
it never scores, sizes, or promotes. Historical conditional outcomes are
context for a human or an adversarial reviewer, not an edge claim.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

MEMORY_VERSION = "dopey-trade-memory-v3"
OUTCOME_UNIT = "fractional_model_return"
CORRUPTION_GUARD_VERSION = "dopey-trade-memory-corruption-guard-v1"

# Condition buckets a candidate can be matched on. Edges are inclusive-low.
STRETCH_BUCKETS = (  # close / SMA20 - 1
    ("deep_below", -1.0, -0.08),
    ("below", -0.08, -0.02),
    ("near", -0.02, 0.02),
    ("above", 0.02, 0.08),
    ("stretched_above", 0.08, 1.0),
)
RVOL_BUCKETS = (  # annualized 20-day realized vol
    ("low", 0.0, 0.20),
    ("medium", 0.20, 0.40),
    ("high", 0.40, 0.80),
    ("extreme", 0.80, 10.0),
)


class TradeMemoryCorruptionError(ValueError):
    """A source outcome violates long-premium accounting identities."""

    def __init__(self, reason_code: str, context: str) -> None:
        self.reason_code = reason_code
        super().__init__(
            f"trade-memory source outcome quarantined: "
            f"reason_code={reason_code}, {context}"
        )


def _bucket(value: float, buckets: Sequence[tuple[str, float, float]]) -> str:
    if not math.isfinite(value):
        return "unknown"
    for name, low, high in buckets:
        if low <= value < high:
            return name
    return buckets[-1][0] if value >= buckets[-1][2] else buckets[0][0]


def spine_conditions(
    closes: Sequence[float], dates: Sequence[str], signal_date: str
) -> dict[str, Any]:
    """Point-in-time stretch / realized-vol / trailing-return at signal_date."""
    index = None
    for position, day in enumerate(dates):
        if day == signal_date:
            index = position
            break
    if index is None or index < 21:
        return {"stretch_bucket": "unknown", "rvol_bucket": "unknown"}
    window = closes[index - 20 : index]
    sma20 = sum(window) / 20
    stretch = closes[index] / sma20 - 1.0 if sma20 > 0 else math.nan
    rets = [
        closes[position] / closes[position - 1] - 1.0
        for position in range(index - 19, index + 1)
        if closes[position - 1] > 0
    ]
    if len(rets) >= 2:
        mean = sum(rets) / len(rets)
        rvol = (sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5 * math.sqrt(252)
    else:
        rvol = math.nan
    trailing_5 = closes[index] / closes[index - 5] - 1.0 if index >= 5 and closes[index - 5] > 0 else math.nan
    return {
        "stretch": round(stretch, 5) if math.isfinite(stretch) else None,
        "stretch_bucket": _bucket(stretch, STRETCH_BUCKETS),
        "rvol": round(rvol, 5) if math.isfinite(rvol) else None,
        "rvol_bucket": _bucket(rvol, RVOL_BUCKETS),
        "trailing_5d_return": round(trailing_5, 5) if math.isfinite(trailing_5) else None,
    }


def enrich_record(
    record: Mapping[str, Any],
    spine_by_symbol: Mapping[str, tuple[Sequence[float], Sequence[str]]],
) -> dict[str, Any] | None:
    """Compact memory record: family/direction/conditions/outcome. None if unusable."""
    family = str(record.get("signal_family", ""))
    strategy = str(record.get("candidate_strategy", ""))
    symbol = str(record.get("symbol", ""))
    signal_date = str(record.get("signal_date", ""))
    pnl = record.get("path_pnl")
    if not family or not symbol or pnl is None:
        return None
    path_pnl = _finite(pnl)
    if path_pnl is None:
        raise TradeMemoryCorruptionError(
            "non_finite_path_pnl",
            (
                f"family={family}, symbol={symbol}, signal_date={signal_date}, "
                f"path_pnl={pnl}"
            ),
        )
    trade_return = _finite(record.get("trade_return_model_units"))
    if trade_return is None:
        raise ValueError(
            "trade-memory outcome requires finite trade_return_model_units: "
            f"family={family}, symbol={symbol}, signal_date={signal_date}"
        )
    raw_entry_premium = record.get("entry_premium")
    if raw_entry_premium is None:
        raise TradeMemoryCorruptionError(
            "missing_entry_premium",
            (
                f"family={family}, symbol={symbol}, signal_date={signal_date}"
            ),
        )
    entry_premium = _finite(raw_entry_premium)
    if entry_premium is None:
        raise TradeMemoryCorruptionError(
            "non_finite_entry_premium",
            (
                f"family={family}, symbol={symbol}, signal_date={signal_date}, "
                f"entry_premium={raw_entry_premium}"
            ),
        )
    if trade_return < -1.000001:
        raise TradeMemoryCorruptionError(
            "long_premium_return_below_total_loss",
            (
                f"family={family}, symbol={symbol}, signal_date={signal_date}, "
                f"trade_return_model_units={trade_return}"
            ),
        )
    if entry_premium <= 0.0:
        raise TradeMemoryCorruptionError(
            "non_positive_entry_premium",
            (
                f"family={family}, symbol={symbol}, "
                f"signal_date={signal_date}, entry_premium={entry_premium}"
            ),
        )
    tolerance = max(0.000001, entry_premium * 0.000001)
    if path_pnl < -entry_premium - tolerance:
        raise TradeMemoryCorruptionError(
            "path_pnl_below_long_premium_maximum_loss",
            (
                f"family={family}, symbol={symbol}, signal_date={signal_date}, "
                f"path_pnl={path_pnl}, entry_premium={entry_premium}"
            ),
        )
    expected_return = path_pnl / entry_premium
    if abs(expected_return - trade_return) > 0.001:
        raise TradeMemoryCorruptionError(
            "fractional_return_pnl_identity_mismatch",
            (
                f"family={family}, symbol={symbol}, signal_date={signal_date}, "
                f"path_pnl={path_pnl}, entry_premium={entry_premium}, "
                f"trade_return_model_units={trade_return}"
            ),
        )
    conditions = {"stretch_bucket": "unknown", "rvol_bucket": "unknown"}
    if symbol in spine_by_symbol:
        closes, dates = spine_by_symbol[symbol]
        conditions = spine_conditions(closes, dates, signal_date)
    return {
        "family": family,
        "strategy": strategy,
        "direction": str(record.get("direction", "")),
        "symbol": symbol,
        "signal_date": signal_date,
        "path_pnl": path_pnl,
        "trade_return_model_units": trade_return,
        "win": trade_return > 0.0,
        "mfe": _finite(record.get("max_favorable_excursion")),
        "mae": _finite(record.get("max_adverse_excursion")),
        "exit_reason": str(record.get("exit_reason", "")),
        "holding_steps": int(record.get("holding_steps", 0) or 0),
        **conditions,
    }


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _outcome_stats(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Outcome distribution INCLUDING the miss pattern (golf course management:
    aim where the miss is safe - the downside quantiles and the catastrophic-
    loss share matter as much as the mean, because a mild mean with a fat
    total-loss tail is worse for long options than a worse mean with tight
    dispersion)."""
    if not records:
        return {"count": 0, "outcome_unit": OUTCOME_UNIT}
    returns: list[float] = []
    for index, record in enumerate(records):
        trade_return = _finite(record.get("trade_return_model_units"))
        if trade_return is None:
            raise ValueError(
                "trade-memory statistics require finite "
                f"trade_return_model_units: record_index={index}"
            )
        returns.append(trade_return)
    returns.sort()
    wins = sum(1 for r in records if r["win"])
    maes = [r["mae"] for r in records if r.get("mae") is not None]
    n = len(returns)
    catastrophic = sum(1 for value in returns if value <= -0.9)
    return {
        "count": n,
        "outcome_unit": OUTCOME_UNIT,
        "win_rate": round(wins / n, 4),
        "mean_trade_return_model_units": round(sum(returns) / n, 5),
        "median_trade_return_model_units": round(returns[n // 2], 5),
        "p10_trade_return_model_units": round(
            returns[max(0, int(0.10 * n) - 1)],
            5,
        ),
        "worst_trade_return_model_units": round(returns[0], 5),
        "catastrophic_loss_share": round(catastrophic / n, 4),
        "mean_max_adverse_excursion_premium_units": (
            round(sum(maes) / len(maes), 5) if maes else None
        ),
    }


def retrieve_similar(
    index: Sequence[Mapping[str, Any]],
    family: str,
    stretch_bucket: str | None = None,
    rvol_bucket: str | None = None,
    strategy: str | None = None,
) -> dict[str, Any]:
    """Prior trades matching family (+ optional condition buckets) and their stats.

    Also returns the CONDITIONAL breakdown across stretch buckets so a reviewer
    can see where the family historically did better or worse.
    """
    family_records = [r for r in index if r["family"] == family]
    if strategy:
        family_records = [r for r in family_records if r["strategy"] == strategy]
    matched = family_records
    if stretch_bucket:
        matched = [r for r in matched if r.get("stretch_bucket") == stretch_bucket]
    if rvol_bucket:
        matched = [r for r in matched if r.get("rvol_bucket") == rvol_bucket]
    by_stretch = {
        name: _outcome_stats([r for r in family_records if r.get("stretch_bucket") == name])
        for name, _low, _high in STRETCH_BUCKETS
    }
    return {
        "family": family,
        "strategy_filter": strategy,
        "matched_conditions": {"stretch_bucket": stretch_bucket, "rvol_bucket": rvol_bucket},
        "family_total": _outcome_stats(family_records),
        "matched": _outcome_stats(matched),
        "conditional_by_stretch": {k: v for k, v in by_stretch.items() if v["count"] > 0},
        "outcome_unit": OUTCOME_UNIT,
        "not_edge_evidence": True,
        "promotion_allowed": False,
    }


def build_memory_index(
    records: Iterable[Mapping[str, Any]],
    spine_by_symbol: Mapping[str, tuple[Sequence[float], Sequence[str]]],
) -> list[dict[str, Any]]:
    index: list[dict[str, Any]] = []
    for record in records:
        enriched = enrich_record(record, spine_by_symbol)
        if enriched is not None:
            index.append(enriched)
    return index
