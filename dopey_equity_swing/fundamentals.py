"""Real-snapshot fundamental scoring for equity-first swing direction confirmation."""

from __future__ import annotations

import csv
import hashlib
import math
from datetime import date
from pathlib import Path
from typing import Any, TypedDict


MINIMUM_VALUATION_PEER_COUNT = 5


class FundamentalSnapshot(TypedDict):
    path: Path
    snapshot_date: str
    sha256: str
    source_row_count: int
    snapshot_row_count: int
    in_universe_symbol_count: int
    historical_row_count_excluded: int
    future_row_count_excluded: int
    maximum_staleness_calendar_days: int
    point_in_time_status: str
    rows: list[dict[str, Any]]


_REQUIRED_FUNDAMENTAL_FIELDS = {
    "date",
    "symbol",
    "theme",
    "in_universe",
    "market_cap",
    "trailing_pe",
    "forward_pe",
    "price_to_sales",
    "price_to_book",
    "profit_margin",
    "revenue_growth",
    "free_cashflow",
    "total_debt",
    "total_cash",
}


def resolve_fundamental_snapshot(
    path: Path,
    market_as_of_date: date,
) -> FundamentalSnapshot:
    """Select only the exact market-frontier observation slice.

    The source file is an append-only sequence of provider fetch-date snapshots.
    Its current schema has no earlier availability timestamp, so an exact match to
    the validated market frontier is the only governed boundary. Historical rows
    and later fetches remain in the source ledger but are never consumed here.
    """
    if not path.is_file():
        raise FileNotFoundError(f"fundamental snapshot is missing: {path}")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            actual_fields = set(reader.fieldnames or ())
            if not _REQUIRED_FUNDAMENTAL_FIELDS.issubset(actual_fields):
                raise ValueError(
                    "fundamental snapshot schema is incomplete: "
                    f"path={path}, required={sorted(_REQUIRED_FUNDAMENTAL_FIELDS)}, "
                    f"actual={sorted(actual_fields)}"
                )
            source_rows = [dict(row) for row in reader]
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError(
            f"fundamental snapshot is unreadable: path={path}, error={error}"
        ) from error
    if not source_rows:
        raise ValueError(f"fundamental snapshot is empty: {path}")

    selected_rows: list[dict[str, Any]] = []
    selected_symbols: set[str] = set()
    historical_row_count = 0
    future_row_count = 0
    for line_number, source_row in enumerate(source_rows, start=2):
        raw_observation_date = str(source_row.get("date", "")).strip()
        try:
            observation_date = date.fromisoformat(raw_observation_date)
        except ValueError as error:
            raise ValueError(
                "fundamental observation date is invalid: "
                f"path={path}, line={line_number}, value={raw_observation_date!r}"
            ) from error
        symbol = str(source_row.get("symbol", "")).strip().upper()
        theme = str(source_row.get("theme", "")).strip()
        in_universe = str(source_row.get("in_universe", "")).strip()
        if not symbol or not theme or in_universe not in {"0", "1"}:
            raise ValueError(
                "fundamental observation identity is invalid: "
                f"path={path}, line={line_number}, symbol={symbol!r}, "
                f"theme={theme!r}, in_universe={in_universe!r}"
            )
        if observation_date < market_as_of_date:
            historical_row_count += 1
            continue
        if observation_date > market_as_of_date:
            future_row_count += 1
            continue
        if symbol in selected_symbols:
            raise ValueError(
                "fundamental snapshot contains a duplicate frontier symbol: "
                f"path={path}, date={market_as_of_date.isoformat()}, symbol={symbol}"
            )
        selected_symbols.add(symbol)
        selected_rows.append(
            {
                **source_row,
                "date": market_as_of_date.isoformat(),
                "symbol": symbol,
                "theme": theme,
                "in_universe": in_universe,
            }
        )
    if not selected_rows:
        raise ValueError(
            "fundamental snapshot has no exact market-frontier slice; stale fallback is prohibited: "
            f"path={path}, market_as_of_date={market_as_of_date.isoformat()}"
        )
    return {
        "path": path,
        "snapshot_date": market_as_of_date.isoformat(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_row_count": len(source_rows),
        "snapshot_row_count": len(selected_rows),
        "in_universe_symbol_count": sum(
            str(row["in_universe"]) == "1" for row in selected_rows
        ),
        "historical_row_count_excluded": historical_row_count,
        "future_row_count_excluded": future_row_count,
        "maximum_staleness_calendar_days": 0,
        "point_in_time_status": "exact_market_frontier_snapshot",
        "rows": selected_rows,
    }


def load_earnings_dates(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"earnings snapshot is missing: {path}")
    output: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row["symbol"]).strip().upper()
            earnings_date = str(row["earnings_date"]).strip()
            current = output.get(symbol)
            if current is None or earnings_date < current:
                output[symbol] = earnings_date
    return output


def score_fundamental_snapshot(
    rows: list[dict[str, Any]],
    market_as_of_date: date,
) -> dict[str, dict[str, Any]]:
    _validate_frontier_rows(rows, market_as_of_date)
    numeric_rows = [
        _numeric_row(row) for row in rows if str(row.get("in_universe", "0")) == "1"
    ]
    if not numeric_rows:
        raise ValueError(
            "fundamental snapshot contains no in-universe symbols at the market frontier: "
            f"market_as_of_date={market_as_of_date.isoformat()}"
        )
    by_theme: dict[str, list[dict[str, Any]]] = {}
    for row in numeric_rows:
        by_theme.setdefault(str(row["theme"]), []).append(row)
    output: dict[str, dict[str, Any]] = {}
    for row in numeric_rows:
        theme_rows = by_theme[str(row["theme"])]
        growth = _percentile_score(
            row.get("revenue_growth"), _values(theme_rows, "revenue_growth"), True
        )
        margin = _percentile_score(
            row.get("profit_margin"), _values(theme_rows, "profit_margin"), True
        )
        fcf_yield = _ratio(row.get("free_cashflow"), row.get("market_cap"))
        fcf = _percentile_score(
            fcf_yield,
            [
                _ratio(peer.get("free_cashflow"), peer.get("market_cap"))
                for peer in theme_rows
            ],
            True,
        )
        balance_value = _balance_value(row)
        balance = _percentile_score(
            balance_value, [_balance_value(peer) for peer in theme_rows], True
        )
        forward_pe_peers = _positive_values(theme_rows, "forward_pe")
        sales_peers = _positive_values(theme_rows, "price_to_sales")
        forward_pe_value = _positive_value(row.get("forward_pe"))
        sales_value = _positive_value(row.get("price_to_sales"))
        valuation_components: list[tuple[float, float]] = []
        if (
            forward_pe_value is not None
            and _available_count(forward_pe_peers) >= MINIMUM_VALUATION_PEER_COUNT
        ):
            valuation_components.append(
                (
                    0.55,
                    _percentile_score(forward_pe_value, forward_pe_peers, False),
                )
            )
        if (
            sales_value is not None
            and _available_count(sales_peers) >= MINIMUM_VALUATION_PEER_COUNT
        ):
            valuation_components.append(
                (0.45, _percentile_score(sales_value, sales_peers, False))
            )
        valuation_weight = sum(weight for weight, _ in valuation_components)
        valuation = (
            sum(weight * score for weight, score in valuation_components)
            / valuation_weight
            if valuation_weight > 0.0
            else 0.5
        )
        valuation_status = (
            "peer_relative_scored_sufficient"
            if valuation_components
            else "blocked_missing_positive_valuation_metrics"
            if forward_pe_value is None and sales_value is None
            else "blocked_insufficient_peer_cohort"
        )
        quality = 0.40 * margin + 0.30 * fcf + 0.30 * balance
        bullish = _clamp01(
            0.30 * growth + 0.30 * quality + 0.20 * valuation + 0.20 * balance
        )
        bearish = _clamp01(
            0.25 * (1.0 - growth)
            + 0.30 * (1.0 - quality)
            + 0.25 * (1.0 - balance)
            + 0.20 * (1.0 - valuation)
        )
        direction = (
            "bullish"
            if bullish - bearish >= 0.12
            else "bearish"
            if bearish - bullish >= 0.12
            else "neutral"
        )
        flags: list[str] = []
        if growth >= 0.65:
            flags.append("peer_relative_growth_support")
        if quality >= 0.65:
            flags.append("quality_and_cashflow_support")
        if valuation <= 0.30:
            flags.append("peer_relative_valuation_stretch")
        if balance <= 0.30:
            flags.append("balance_sheet_fragility")
        if row.get("profit_margin") is not None and float(row["profit_margin"]) < 0.0:
            flags.append("negative_profit_margin")
        if row.get("revenue_growth") is not None and float(row["revenue_growth"]) < 0.0:
            flags.append("negative_revenue_growth")
        if row.get("forward_pe") is not None and float(row["forward_pe"]) <= 0.0:
            flags.append("nonpositive_forward_pe_not_meaningful")
        if valuation_status == "blocked_insufficient_peer_cohort":
            flags.append("insufficient_valuation_peer_cohort")
        if valuation_status == "blocked_missing_positive_valuation_metrics":
            flags.append("valuation_metrics_unavailable")
        output[str(row["symbol"])] = {
            "artifact_type": "equity_fundamental_confirmation",
            "symbol": row["symbol"],
            "as_of_date": row["date"],
            "theme": row["theme"],
            "fundamental_status": "real_snapshot_scored",
            "point_in_time_status": "exact_market_frontier_snapshot",
            "maximum_staleness_calendar_days": 0,
            "future_observation_consumed": False,
            "bullish_support_score": round(bullish, 6),
            "bearish_support_score": round(bearish, 6),
            "fundamental_direction": direction,
            "growth_score": round(growth, 6),
            "quality_score": round(quality, 6),
            "valuation_support_score": round(valuation, 6),
            "valuation_evidence_status": valuation_status,
            "valuation_minimum_peer_count": MINIMUM_VALUATION_PEER_COUNT,
            "valuation_peer_counts": {
                "forward_pe": _available_count(forward_pe_peers),
                "price_to_sales": _available_count(sales_peers),
            },
            "valuation_metric_count": len(valuation_components),
            "balance_sheet_score": round(balance, 6),
            "cashflow_score": round(fcf, 6),
            "raw_metrics": {
                key: row.get(key)
                for key in (
                    "market_cap",
                    "trailing_pe",
                    "forward_pe",
                    "price_to_sales",
                    "price_to_book",
                    "profit_margin",
                    "revenue_growth",
                    "free_cashflow",
                    "total_debt",
                    "total_cash",
                )
            },
            "reason_codes": flags,
            "directional_use": "confirmation_or_contradiction_only",
            "paper_only": True,
            "live_blocked": True,
        }
    return output


def _validate_frontier_rows(
    rows: list[dict[str, Any]],
    market_as_of_date: date,
) -> None:
    if not rows:
        raise ValueError(
            "fundamental scoring requires nonempty exact-frontier observations"
        )
    expected = market_as_of_date.isoformat()
    symbols: set[str] = set()
    for index, row in enumerate(rows):
        observed = str(row.get("date", "")).strip()
        symbol = str(row.get("symbol", "")).strip().upper()
        if observed != expected:
            raise ValueError(
                "fundamental scoring rejected a non-frontier observation: "
                f"index={index}, symbol={symbol!r}, observed={observed!r}, expected={expected}"
            )
        if not symbol or symbol in symbols:
            raise ValueError(
                "fundamental scoring requires unique nonempty symbols: "
                f"index={index}, symbol={symbol!r}, market_as_of_date={expected}"
            )
        symbols.add(symbol)


def _numeric_row(row: dict[str, Any]) -> dict[str, Any]:
    numeric_fields = (
        "market_cap",
        "trailing_pe",
        "forward_pe",
        "price_to_sales",
        "price_to_book",
        "profit_margin",
        "revenue_growth",
        "free_cashflow",
        "total_debt",
        "total_cash",
    )
    output: dict[str, Any] = {
        "date": str(row["date"]),
        "symbol": str(row["symbol"]),
        "theme": str(row["theme"]),
    }
    for field in numeric_fields:
        output[field] = _optional_float(row.get(field))
    return output


def _optional_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _values(rows: list[dict[str, Any]], field: str) -> list[float | None]:
    return [row.get(field) for row in rows]


def _positive_values(rows: list[dict[str, Any]], field: str) -> list[float | None]:
    return [_positive_value(row.get(field)) for row in rows]


def _positive_value(value: float | None) -> float | None:
    if value is None or not math.isfinite(float(value)) or float(value) <= 0.0:
        return None
    return float(value)


def _available_count(values: list[float | None]) -> int:
    return sum(value is not None for value in values)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0.0:
        return None
    return numerator / denominator


def _balance_value(row: dict[str, Any]) -> float | None:
    market_cap = row.get("market_cap")
    debt = row.get("total_debt")
    cash = row.get("total_cash")
    if market_cap is None or market_cap <= 0.0 or debt is None or cash is None:
        return None
    return (float(cash) - float(debt)) / float(market_cap)


def _percentile_score(
    value: float | None, peers: list[float | None], higher_is_better: bool
) -> float:
    valid = sorted(
        float(peer) for peer in peers if peer is not None and math.isfinite(float(peer))
    )
    if value is None or not valid:
        return 0.5
    below = sum(peer < value for peer in valid)
    equal = sum(peer == value for peer in valid)
    rank = (below + 0.5 * equal) / len(valid)
    return _clamp01(rank if higher_is_better else 1.0 - rank)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
