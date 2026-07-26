"""Governed local intake for squeeze and bubble evidence lanes."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import fmean, median, pstdev
from typing import Any, Final

from dopey.strategy_engineering.swing_target_discovery import load_ohlcv_history

from .models import (
    EmpiricalIntegrityEvidence,
    FundamentalEvidence,
    MarketLeverageEvidence,
    OptionsPressureEvidence,
    SettlementEvidence,
    ShortCrowdingEvidence,
    SymbolEvidence,
    TechnicalState,
)


SHORT_CROWDING_FIELDS: Final[tuple[str, ...]] = (
    "date",
    "symbol",
    "shares_short",
    "shares_short_prior_month",
    "short_percent_float",
    "short_ratio",
    "float_shares",
    "shares_outstanding",
    "held_percent_institutions",
    "held_percent_insiders",
    "average_volume",
    "market_cap",
    "source",
)
SHORT_FLOW_FIELDS: Final[tuple[str, ...]] = (
    "date",
    "symbol",
    "short_volume",
    "short_exempt_volume",
    "total_volume",
)
FUNDAMENTAL_FIELDS: Final[tuple[str, ...]] = (
    "date",
    "symbol",
    "theme",
    "in_universe",
    "market_cap",
    "enterprise_value",
    "total_revenue",
    "trailing_pe",
    "forward_pe",
    "price_to_sales",
    "price_to_book",
    "profit_margin",
    "revenue_growth",
    "free_cashflow",
    "total_debt",
    "total_cash",
    "first_trade_date",
)
FTD_FIELDS: Final[tuple[str, ...]] = (
    "settlement_date",
    "cusip",
    "symbol",
    "quantity_fails",
    "description",
    "price",
    "archive_url",
    "fetched_at",
)
BORROW_FIELDS: Final[tuple[str, ...]] = (
    "date",
    "symbol",
    "borrow_fee_percent",
    "utilization",
    "available_shares",
    "source",
)
THRESHOLD_FIELDS: Final[tuple[str, ...]] = (
    "date",
    "symbol",
    "exchange",
    "source",
)
MARGIN_FIELDS: Final[tuple[str, ...]] = (
    "month",
    "debit_balances_millions",
    "free_credit_cash_millions",
    "free_credit_margin_millions",
    "source",
)
IPO_FIELDS: Final[tuple[str, ...]] = (
    "event_date",
    "symbol",
    "company_name",
    "exchange",
    "offer_price",
    "shares_offered",
    "offer_amount",
    "status",
    "source",
)


@dataclass(frozen=True)
class IntelligencePaths:
    repository_root: Path
    history_root: Path
    short_crowding_path: Path
    short_flow_path: Path
    fundamentals_path: Path
    ftd_path: Path
    borrow_path: Path
    threshold_path: Path
    margin_path: Path
    ipo_calendar_path: Path
    chain_metrics_path: Path


class EvidencePathContainmentError(ValueError):
    """Raised before evidence can be read from outside the governed root."""


@dataclass(frozen=True)
class _ShortFlowSummary:
    as_of_date: str
    mean_ratio: float
    observation_count: int
    elevated_sessions: int
    median_ratio: float
    ratio_dispersion: float


def require_contained_path(
    repository_root: Path,
    candidate_path: Path,
    lane: str,
) -> Path:
    """Resolve one governed path and reject symlink or traversal escapes."""

    root = repository_root.resolve()
    candidate = candidate_path.resolve()
    if not candidate.is_relative_to(root):
        raise EvidencePathContainmentError(
            "squeeze/bubble path escapes repository root: "
            f"lane={lane}, root={root}, path={candidate}"
        )
    return candidate


def validate_intelligence_paths(paths: IntelligencePaths) -> None:
    """Fail closed before reading any uncontained evidence path."""

    root = paths.repository_root.resolve()
    if not root.is_dir():
        raise EvidencePathContainmentError(
            f"squeeze/bubble repository root is unavailable: root={root}"
        )
    governed_paths = (
        ("history", paths.history_root),
        ("short_crowding", paths.short_crowding_path),
        ("short_flow", paths.short_flow_path),
        ("fundamentals", paths.fundamentals_path),
        ("fails_to_deliver", paths.ftd_path),
        ("borrow", paths.borrow_path),
        ("threshold", paths.threshold_path),
        ("margin", paths.margin_path),
        ("ipo", paths.ipo_calendar_path),
        ("options", paths.chain_metrics_path),
    )
    for lane, candidate in governed_paths:
        require_contained_path(root, candidate, lane)


def default_paths(repository_root: Path) -> IntelligencePaths:
    root = repository_root.resolve()
    macro = root / "dopey_data" / "real" / "raw" / "macro_context"
    quant = root / "dopey_data" / "real" / "raw" / "quant_context"
    return IntelligencePaths(
        repository_root=root,
        history_root=root / "dopey_data" / "history" / "raw",
        short_crowding_path=macro / "short_crowding.csv",
        short_flow_path=macro / "finra_short_volume.csv",
        fundamentals_path=macro / "fundamentals.csv",
        ftd_path=quant / "sec_fails_to_deliver.csv",
        borrow_path=macro / "borrow_context.csv",
        threshold_path=macro / "threshold_securities.csv",
        margin_path=macro / "finra_margin_statistics.csv",
        ipo_calendar_path=macro / "ipo_calendar.csv",
        chain_metrics_path=(
            root
            / "artifacts"
            / "dopey"
            / "chain_analytics"
            / "real_chain_positioning_metrics.jsonl"
        ),
    )


def _optional_csv(
    path: Path,
    expected_fields: tuple[str, ...],
    gap_id: str,
) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    if not path.exists():
        return [], (gap_id,)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise OSError(
            f"unable to read evidence lane: path={path}, error={error}"
        ) from error
    reader = csv.DictReader(text.splitlines())
    actual_fields = tuple(reader.fieldnames or ())
    if actual_fields != expected_fields:
        raise ValueError(
            "evidence lane schema mismatch: "
            f"path={path}, expected={expected_fields}, actual={actual_fields}"
        )
    return list(reader), ()


def _optional_jsonl(
    path: Path,
    gap_id: str,
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    if not path.exists():
        return [], (gap_id,)
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise OSError(
            f"unable to read evidence lane: path={path}, error={error}"
        ) from error
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"evidence JSONL is invalid: path={path}, line={line_number}, error={error}"
            ) from error
        if not isinstance(value, dict):
            raise TypeError(
                f"evidence JSONL row must be an object: path={path}, line={line_number}"
            )
        records.append(value)
    return records, ()


def _float(value: object, field: str, context: str) -> float | None:
    if value is None or str(value).strip() in {"", "."}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"evidence field must be numeric: context={context}, field={field}, value={value!r}"
        ) from error
    if not math.isfinite(number):
        raise ValueError(
            f"evidence field must be finite: context={context}, field={field}, value={value!r}"
        )
    return number


def _latest_by_symbol(
    rows: list[dict[str, str]],
    date_field: str,
) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        observed = str(row.get(date_field, "")).strip()
        if not symbol or not observed:
            raise ValueError(
                f"symbol evidence row requires symbol and date: date_field={date_field}, row={row}"
            )
        if symbol not in latest or observed > str(latest[symbol].get(date_field, "")):
            latest[symbol] = row
    return latest


def _file_source_id(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"local:{path.name}:sha256:{digest}"


def _age_days(
    raw_date: str,
    observed_at: datetime,
) -> int:
    try:
        parsed = (
            datetime.strptime(raw_date, "%Y%m%d").date()
            if len(raw_date) == 8 and raw_date.isdigit()
            else date.fromisoformat(raw_date[:10])
        )
    except ValueError as error:
        raise ValueError(f"evidence date is invalid: value={raw_date!r}") from error
    return (observed_at.astimezone(timezone.utc).date() - parsed).days


def _optional_age_days(
    raw_date: str,
    observed_at: datetime,
) -> int | None:
    return _age_days(raw_date, observed_at) if raw_date else None


def _freshness_disposition(
    raw_date: str,
    observed_at: datetime,
    maximum_age_days: int,
) -> str:
    age = _age_days(raw_date, observed_at)
    if age < 0:
        return "future_dated"
    if age > maximum_age_days:
        return "stale"
    return "fresh"


def _return(closes: list[float], lookback: int) -> float:
    if len(closes) <= lookback or closes[-1 - lookback] <= 0.0:
        return 0.0
    return closes[-1] / closes[-1 - lookback] - 1.0


def _sma(values: list[float], window: int) -> float | None:
    return fmean(values[-window:]) if len(values) >= window else None


def _realized_volatility(closes: list[float], window: int) -> float:
    returns = [
        closes[index] / closes[index - 1] - 1.0
        for index in range(max(1, len(closes) - window), len(closes))
        if closes[index - 1] > 0.0
    ]
    return pstdev(returns) * math.sqrt(252.0) if len(returns) >= 2 else 0.0


def _rsi14(closes: list[float]) -> float:
    if len(closes) < 15:
        return 50.0
    changes = [
        closes[index] - closes[index - 1]
        for index in range(len(closes) - 14, len(closes))
    ]
    gains = sum(max(change, 0.0) for change in changes) / 14.0
    losses = sum(max(-change, 0.0) for change in changes) / 14.0
    if losses == 0.0:
        return 100.0 if gains > 0.0 else 50.0
    strength = gains / losses
    return 100.0 - 100.0 / (1.0 + strength)


def _technical_state(bars: list[dict[str, float]]) -> TechnicalState:
    if len(bars) < 21:
        raise ValueError(
            f"squeeze/bubble technical state requires at least 21 bars: actual={len(bars)}"
        )
    closes = [float(bar["close"]) for bar in bars]
    volumes = [max(float(bar.get("volume", 0.0)), 0.0) for bar in bars]
    close = closes[-1]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    if sma20 is None or sma20 <= 0.0:
        raise ValueError("20-session moving average is unavailable or nonpositive")
    average_dollar_volume = fmean(
        price * volume
        for price, volume in zip(closes[-20:], volumes[-20:], strict=True)
    )
    average_dollar_volume_5d = fmean(
        price * volume for price, volume in zip(closes[-5:], volumes[-5:], strict=True)
    )
    signed_volume = 0.0
    total_directional_volume = 0.0
    for index in range(len(closes) - 20, len(closes)):
        direction = math.copysign(1.0, closes[index] - closes[index - 1])
        if closes[index] == closes[index - 1]:
            direction = 0.0
        signed_volume += direction * volumes[index]
        total_directional_volume += volumes[index]
    prior_volume_average = fmean(volumes[-21:-1])
    prior_high_20 = max(float(bar["high"]) for bar in bars[-21:-1])
    prior_low_20 = min(float(bar["low"]) for bar in bars[-21:-1])
    high_52w = max(closes[-252:]) if len(closes) >= 252 else None
    realized_20 = _realized_volatility(closes, 20)
    realized_60 = _realized_volatility(closes, 60)
    return TechnicalState(
        as_of_date=str(bars[-1]["date"]),
        close=close,
        average_dollar_volume_20d=average_dollar_volume,
        average_dollar_volume_5d=average_dollar_volume_5d,
        dollar_volume_ratio_5d_20d=(
            average_dollar_volume_5d / average_dollar_volume
            if average_dollar_volume > 0.0
            else 0.0
        ),
        signed_volume_pressure_20d=(
            signed_volume / total_directional_volume
            if total_directional_volume > 0.0
            else 0.0
        ),
        return_5d=_return(closes, 5),
        return_20d=_return(closes, 20),
        return_63d=_return(closes, 63) if len(closes) >= 64 else None,
        return_252d=_return(closes, 252) if len(closes) >= 253 else None,
        volume_ratio_20d=(
            volumes[-1] / prior_volume_average if prior_volume_average > 0.0 else 0.0
        ),
        distance_sma20=close / sma20 - 1.0,
        distance_sma50=(
            close / sma50 - 1.0 if sma50 is not None and sma50 > 0.0 else None
        ),
        distance_sma200=close / sma200 - 1.0 if sma200 and sma200 > 0.0 else None,
        distance_52w_high=close / high_52w - 1.0 if high_52w else None,
        realized_vol_20d=realized_20,
        realized_vol_ratio_20d_60d=(
            realized_20 / realized_60 if realized_60 > 0.0 else 1.0
        ),
        rsi14=_rsi14(closes),
        breakout_20d=close > prior_high_20,
        breakdown_20d=close < prior_low_20,
    )


def _short_flow_by_symbol(
    rows: list[dict[str, str]],
) -> dict[str, _ShortFlowSummary]:
    grouped: dict[str, list[tuple[str, float]]] = {}
    for row in rows:
        symbol = str(row["symbol"]).strip().upper()
        short_volume = _float(row["short_volume"], "short_volume", symbol)
        total_volume = _float(row["total_volume"], "total_volume", symbol)
        if short_volume is None or total_volume is None or total_volume <= 0.0:
            continue
        grouped.setdefault(symbol, []).append(
            (str(row["date"]), short_volume / total_volume)
        )
    output: dict[str, _ShortFlowSummary] = {}
    for symbol, points in grouped.items():
        recent = sorted(points)[-5:]
        ratios = [value for _, value in recent]
        output[symbol] = _ShortFlowSummary(
            as_of_date=recent[-1][0],
            mean_ratio=fmean(ratios),
            observation_count=len(ratios),
            elevated_sessions=sum(value >= 0.45 for value in ratios),
            median_ratio=median(ratios),
            ratio_dispersion=pstdev(ratios) if len(ratios) >= 2 else 0.0,
        )
    return output


def _short_crowding_evidence(
    symbol: str,
    row: dict[str, str] | None,
    short_flow: _ShortFlowSummary | None,
    borrow_row: dict[str, str] | None,
    source_ids: tuple[str, ...],
) -> ShortCrowdingEvidence:
    context = f"short_crowding:{symbol}"
    return ShortCrowdingEvidence(
        as_of_date=str((row or {}).get("date", "")),
        shares_short=_float((row or {}).get("shares_short"), "shares_short", context),
        shares_short_prior_month=_float(
            (row or {}).get("shares_short_prior_month"),
            "shares_short_prior_month",
            context,
        ),
        short_percent_float=_float(
            (row or {}).get("short_percent_float"),
            "short_percent_float",
            context,
        ),
        days_to_cover=_float((row or {}).get("short_ratio"), "short_ratio", context),
        float_shares=_float((row or {}).get("float_shares"), "float_shares", context),
        shares_outstanding=_float(
            (row or {}).get("shares_outstanding"),
            "shares_outstanding",
            context,
        ),
        institutional_ownership=_float(
            (row or {}).get("held_percent_institutions"),
            "held_percent_institutions",
            context,
        ),
        insider_ownership=_float(
            (row or {}).get("held_percent_insiders"),
            "held_percent_insiders",
            context,
        ),
        average_volume=_float(
            (row or {}).get("average_volume"),
            "average_volume",
            context,
        ),
        borrow_fee_percent=_float(
            (borrow_row or {}).get("borrow_fee_percent"),
            "borrow_fee_percent",
            context,
        ),
        borrow_utilization=_float(
            (borrow_row or {}).get("utilization"),
            "utilization",
            context,
        ),
        borrow_available_shares=_float(
            (borrow_row or {}).get("available_shares"),
            "available_shares",
            context,
        ),
        daily_short_volume_ratio=(
            short_flow.mean_ratio if short_flow is not None else None
        ),
        daily_short_volume_observations=(
            short_flow.observation_count if short_flow is not None else 0
        ),
        daily_short_volume_elevated_sessions=(
            short_flow.elevated_sessions if short_flow is not None else 0
        ),
        daily_short_volume_median_ratio=(
            short_flow.median_ratio if short_flow is not None else None
        ),
        daily_short_volume_ratio_dispersion=(
            short_flow.ratio_dispersion if short_flow is not None else None
        ),
        source_ids=source_ids,
    )


def _settlement_evidence(
    symbol: str,
    rows: list[dict[str, str]],
    threshold_row: dict[str, str] | None,
    short: ShortCrowdingEvidence,
    source_ids: tuple[str, ...],
) -> SettlementEvidence:
    points = sorted(
        (
            str(row["settlement_date"]),
            float(row["quantity_fails"]),
        )
        for row in rows
        if str(row["symbol"]).strip().upper() == symbol
    )
    latest_fails = points[-1][1] if points else None
    denominator = short.shares_outstanding or short.float_shares
    fails_to_float = (
        latest_fails / denominator
        if latest_fails is not None and denominator is not None and denominator > 0.0
        else None
    )
    threshold_floor = (
        max(10_000.0, 0.005 * denominator)
        if denominator is not None and denominator > 0.0
        else None
    )
    elevated = 0
    if threshold_floor is not None:
        for _observed, quantity in reversed(points):
            if quantity < threshold_floor:
                break
            elevated += 1
    return SettlementEvidence(
        as_of_date=points[-1][0] if points else "",
        latest_fails=latest_fails,
        fails_to_float=fails_to_float,
        observation_count=len(points),
        elevated_fail_sessions=elevated,
        threshold_condition_proxy=elevated >= 5,
        official_threshold_listed=(True if threshold_row is not None else None),
        source_ids=source_ids,
    )


def _fundamental_evidence(
    symbol: str,
    row: dict[str, str] | None,
    ipo_row: dict[str, str] | None,
    market_as_of_date: str,
    source_ids: tuple[str, ...],
) -> FundamentalEvidence:
    context = f"fundamentals:{symbol}"
    first_trade_date = str(
        (ipo_row or {}).get("event_date") or (row or {}).get("first_trade_date", "")
    )
    days_since_first_trade: int | None = None
    if first_trade_date:
        try:
            days_since_first_trade = (
                date.fromisoformat(market_as_of_date)
                - date.fromisoformat(first_trade_date)
            ).days
        except ValueError as error:
            raise ValueError(
                "listing evidence contains an invalid date: "
                f"symbol={symbol}, first_trade_date={first_trade_date!r}, "
                f"market_as_of_date={market_as_of_date!r}"
            ) from error
        if days_since_first_trade < 0:
            raise ValueError(
                "listing evidence is later than the market evidence: "
                f"symbol={symbol}, first_trade_date={first_trade_date}, "
                f"market_as_of_date={market_as_of_date}"
            )
    return FundamentalEvidence(
        as_of_date=str((row or {}).get("date", "")),
        theme=str((row or {}).get("theme", "")),
        market_cap=_float((row or {}).get("market_cap"), "market_cap", context),
        enterprise_value=_float(
            (row or {}).get("enterprise_value"),
            "enterprise_value",
            context,
        ),
        total_revenue=_float(
            (row or {}).get("total_revenue"),
            "total_revenue",
            context,
        ),
        trailing_pe=_float((row or {}).get("trailing_pe"), "trailing_pe", context),
        forward_pe=_float((row or {}).get("forward_pe"), "forward_pe", context),
        price_to_sales=_float(
            (row or {}).get("price_to_sales"), "price_to_sales", context
        ),
        price_to_book=_float(
            (row or {}).get("price_to_book"), "price_to_book", context
        ),
        profit_margin=_float(
            (row or {}).get("profit_margin"), "profit_margin", context
        ),
        revenue_growth=_float(
            (row or {}).get("revenue_growth"), "revenue_growth", context
        ),
        free_cashflow=_float(
            (row or {}).get("free_cashflow"), "free_cashflow", context
        ),
        total_debt=_float((row or {}).get("total_debt"), "total_debt", context),
        total_cash=_float((row or {}).get("total_cash"), "total_cash", context),
        first_trade_date=first_trade_date,
        days_since_first_trade=days_since_first_trade,
        ipo_offer_price=_float(
            (ipo_row or {}).get("offer_price"),
            "offer_price",
            f"ipo:{symbol}",
        ),
        ipo_offer_amount=_float(
            (ipo_row or {}).get("offer_amount"),
            "offer_amount",
            f"ipo:{symbol}",
        ),
        ipo_status=str((ipo_row or {}).get("status", "")),
        source_ids=source_ids,
    )


def _options_evidence(
    symbol: str,
    record: dict[str, Any] | None,
    source_ids: tuple[str, ...],
) -> OptionsPressureEvidence:
    context = f"options:{symbol}"
    value = record or {}
    return OptionsPressureEvidence(
        as_of_date=str(value.get("snapshot_date", "")),
        quote_derived=value.get("quote_derived") is True,
        contract_rows=int(value.get("contract_rows", 0)),
        call_open_interest=_float(
            value.get("call_open_interest"), "call_open_interest", context
        ),
        put_open_interest=_float(
            value.get("put_open_interest"), "put_open_interest", context
        ),
        call_volume=_float(value.get("call_volume"), "call_volume", context),
        put_volume=_float(value.get("put_volume"), "put_volume", context),
        put_call_open_interest_ratio=_float(
            value.get("put_call_oi_ratio"), "put_call_oi_ratio", context
        ),
        put_call_volume_ratio=_float(
            value.get("put_call_volume_ratio"), "put_call_volume_ratio", context
        ),
        total_gex_dollar_per_pct=_float(
            value.get("total_gex_dollar_per_pct"),
            "total_gex_dollar_per_pct",
            context,
        ),
        gamma_flip_strike=_float(
            value.get("gamma_flip_strike"), "gamma_flip_strike", context
        ),
        atm_implied_vol=_float(
            value.get("atm_implied_vol"), "atm_implied_vol", context
        ),
        source_ids=source_ids,
    )


def _market_leverage(
    rows: list[dict[str, str]],
    source_ids: tuple[str, ...],
) -> MarketLeverageEvidence:
    points = sorted(
        (
            str(row["month"]),
            float(row["debit_balances_millions"]),
            float(row["free_credit_cash_millions"])
            + float(row["free_credit_margin_millions"]),
        )
        for row in rows
    )
    if not points:
        return MarketLeverageEvidence(
            as_of_month="",
            margin_debit_millions=None,
            free_credit_millions=None,
            debit_to_free_credit_ratio=None,
            debit_growth_3m=None,
            debit_growth_12m=None,
            observation_count=0,
            source_ids=(),
        )
    latest_month, debit, free_credit = points[-1]
    growth_3m = debit / points[-4][1] - 1.0 if len(points) >= 4 else None
    growth_12m = debit / points[-13][1] - 1.0 if len(points) >= 13 else None
    return MarketLeverageEvidence(
        as_of_month=latest_month,
        margin_debit_millions=debit,
        free_credit_millions=free_credit,
        debit_to_free_credit_ratio=debit / free_credit if free_credit > 0.0 else None,
        debit_growth_3m=growth_3m,
        debit_growth_12m=growth_12m,
        observation_count=len(points),
        source_ids=source_ids,
    )


def _relative_disagreement(
    reported: float,
    derived: float,
    materiality_floor: float,
) -> bool:
    denominator = max(abs(reported), abs(derived), materiality_floor)
    return abs(reported - derived) / denominator > 0.25


def _contradiction_flags(
    short: ShortCrowdingEvidence,
    settlement: SettlementEvidence,
    fundamentals: FundamentalEvidence,
    options: OptionsPressureEvidence,
) -> tuple[str, ...]:
    flags: list[str] = []
    if (
        short.shares_short is not None
        and short.float_shares is not None
        and short.float_shares > 0.0
        and short.short_percent_float is not None
        and _relative_disagreement(
            short.short_percent_float,
            short.shares_short / short.float_shares,
            0.01,
        )
    ):
        flags.append("squeeze:reported_short_percent_disagrees_with_share_counts")
    if (
        short.shares_short is not None
        and short.average_volume is not None
        and short.average_volume > 0.0
        and short.days_to_cover is not None
        and _relative_disagreement(
            short.days_to_cover,
            short.shares_short / short.average_volume,
            1.0,
        )
    ):
        flags.append("squeeze:reported_days_to_cover_disagrees_with_share_counts")
    if (
        short.float_shares is not None
        and short.shares_outstanding is not None
        and short.float_shares > short.shares_outstanding
    ):
        flags.append("squeeze:float_exceeds_shares_outstanding")
    ownership_values = (
        short.institutional_ownership,
        short.insider_ownership,
    )
    if any(value is not None and not 0.0 <= value <= 1.0 for value in ownership_values):
        flags.append("squeeze:ownership_fraction_out_of_range")
    if (
        short.borrow_utilization is not None
        and not 0.0 <= short.borrow_utilization <= 1.0
    ):
        flags.append("squeeze:borrow_utilization_out_of_range")
    if (
        short.daily_short_volume_ratio is not None
        and not 0.0 <= short.daily_short_volume_ratio <= 1.0
    ):
        flags.append("squeeze:daily_short_volume_ratio_out_of_range")
    if settlement.latest_fails is not None and settlement.latest_fails < 0.0:
        flags.append("squeeze:negative_fails_to_deliver")

    if options.quote_derived and options.contract_rows <= 0:
        flags.append("shared:quote_derived_options_without_contract_rows")
    if (
        options.put_call_open_interest_ratio is not None
        and options.put_open_interest is not None
        and options.call_open_interest is not None
        and options.call_open_interest > 0.0
        and _relative_disagreement(
            options.put_call_open_interest_ratio,
            options.put_open_interest / options.call_open_interest,
            0.05,
        )
    ):
        flags.append("shared:put_call_open_interest_ratio_disagrees_with_totals")
    if (
        options.put_call_volume_ratio is not None
        and options.put_volume is not None
        and options.call_volume is not None
        and options.call_volume > 0.0
        and _relative_disagreement(
            options.put_call_volume_ratio,
            options.put_volume / options.call_volume,
            0.05,
        )
    ):
        flags.append("shared:put_call_volume_ratio_disagrees_with_totals")

    nonnegative_fundamentals = (
        ("market_cap", fundamentals.market_cap),
        ("total_revenue", fundamentals.total_revenue),
        ("price_to_sales", fundamentals.price_to_sales),
        ("price_to_book", fundamentals.price_to_book),
        ("total_debt", fundamentals.total_debt),
        ("total_cash", fundamentals.total_cash),
    )
    for field, value in nonnegative_fundamentals:
        if value is not None and value < 0.0:
            flags.append(f"bubble:negative_{field}")
    if fundamentals.ipo_offer_price is not None and fundamentals.ipo_offer_price <= 0.0:
        flags.append("bubble:nonpositive_ipo_offer_price")
    if (
        fundamentals.ipo_offer_amount is not None
        and fundamentals.ipo_offer_amount <= 0.0
    ):
        flags.append("bubble:nonpositive_ipo_offer_amount")
    return tuple(sorted(set(flags)))


def _lane_age_pairs(
    evidence_dates: tuple[tuple[str, str], ...],
    observed_at: datetime,
) -> tuple[tuple[str, int | None], ...]:
    return tuple(
        sorted(
            (
                lane,
                _optional_age_days(raw_date, observed_at),
            )
            for lane, raw_date in evidence_dates
        )
    )


def load_symbol_evidence(
    paths: IntelligencePaths,
    observed_at: datetime,
    maximum_source_age_days: int,
) -> tuple[tuple[SymbolEvidence, ...], dict[str, Any]]:
    """Load every local lane and return symbol evidence plus explicit gaps."""

    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    validate_intelligence_paths(paths)
    short_rows, short_gaps = _optional_csv(
        paths.short_crowding_path,
        SHORT_CROWDING_FIELDS,
        "missing_actual_short_interest_lane",
    )
    flow_rows, flow_gaps = _optional_csv(
        paths.short_flow_path,
        SHORT_FLOW_FIELDS,
        "missing_daily_short_volume_lane",
    )
    fundamental_rows, fundamental_gaps = _optional_csv(
        paths.fundamentals_path,
        FUNDAMENTAL_FIELDS,
        "missing_fundamental_fragility_lane",
    )
    ftd_rows, ftd_gaps = _optional_csv(
        paths.ftd_path,
        FTD_FIELDS,
        "missing_sec_fails_to_deliver_lane",
    )
    borrow_rows, borrow_gaps = _optional_csv(
        paths.borrow_path,
        BORROW_FIELDS,
        "missing_borrow_cost_and_utilization_lane",
    )
    threshold_rows, threshold_gaps = _optional_csv(
        paths.threshold_path,
        THRESHOLD_FIELDS,
        "missing_official_threshold_securities_lane",
    )
    threshold_coverage_gaps = (
        ("official_threshold_coverage_nasdaq_only",)
        if threshold_rows
        and {str(row.get("exchange", "")).strip().upper() for row in threshold_rows}
        == {"XNAS"}
        else ()
    )
    margin_rows, margin_gaps = _optional_csv(
        paths.margin_path,
        MARGIN_FIELDS,
        "missing_finra_margin_leverage_lane",
    )
    ipo_rows, ipo_gaps = _optional_csv(
        paths.ipo_calendar_path,
        IPO_FIELDS,
        "missing_recent_ipo_calendar_lane",
    )
    chain_rows, chain_gaps = _optional_jsonl(
        paths.chain_metrics_path,
        "missing_quote_derived_chain_pressure_lane",
    )
    histories = load_ohlcv_history(paths.history_root)
    if not histories:
        raise ValueError(
            f"squeeze/bubble intelligence requires local OHLCV history: path={paths.history_root}"
        )

    short_latest = _latest_by_symbol(short_rows, "date") if short_rows else {}
    flow_latest = _short_flow_by_symbol(flow_rows)
    fundamental_latest = (
        _latest_by_symbol(fundamental_rows, "date") if fundamental_rows else {}
    )
    borrow_latest = _latest_by_symbol(borrow_rows, "date") if borrow_rows else {}
    threshold_latest = (
        _latest_by_symbol(threshold_rows, "date") if threshold_rows else {}
    )
    ipo_latest = _latest_by_symbol(ipo_rows, "event_date") if ipo_rows else {}
    chain_latest: dict[str, dict[str, Any]] = {}
    for record in chain_rows:
        symbol = str(record.get("symbol", "")).strip().upper()
        snapshot_date = str(record.get("snapshot_date", ""))
        if not symbol or not snapshot_date:
            raise ValueError(
                f"chain metric requires symbol and snapshot_date: record={record}"
            )
        if symbol not in chain_latest or snapshot_date > str(
            chain_latest[symbol].get("snapshot_date", "")
        ):
            chain_latest[symbol] = record

    source_ids: dict[str, tuple[str, ...]] = {}
    for lane, path in (
        ("short", paths.short_crowding_path),
        ("flow", paths.short_flow_path),
        ("fundamentals", paths.fundamentals_path),
        ("ftd", paths.ftd_path),
        ("borrow", paths.borrow_path),
        ("threshold", paths.threshold_path),
        ("margin", paths.margin_path),
        ("ipo", paths.ipo_calendar_path),
        ("options", paths.chain_metrics_path),
    ):
        source_ids[lane] = (_file_source_id(path),) if path.exists() else ()

    history_source_paths = {
        path.stem.upper(): path for path in sorted(paths.history_root.glob("*.csv"))
    }
    chain_observation_counts: dict[str, int] = {}
    for record in chain_rows:
        symbol = str(record.get("symbol", "")).strip().upper()
        chain_observation_counts[symbol] = chain_observation_counts.get(symbol, 0) + 1

    market_leverage = _market_leverage(margin_rows, source_ids["margin"])
    margin_disposition = (
        _freshness_disposition(
            market_leverage.as_of_month,
            observed_at,
            maximum_source_age_days,
        )
        if market_leverage.as_of_month
        else "missing"
    )
    if margin_disposition in {"future_dated", "stale"}:
        market_leverage = _market_leverage([], ())
    evidence_records: list[SymbolEvidence] = []
    stale_counts: dict[str, int] = {}
    for symbol, bars in sorted(histories.items()):
        if len(bars) < 21:
            continue
        technical = _technical_state(bars)
        stale_lanes: set[str] = set()
        future_lanes: set[str] = set()
        technical_age = _age_days(technical.as_of_date, observed_at)
        if technical_age < 0:
            future_lanes.add("technical")
        elif technical_age > maximum_source_age_days:
            stale_lanes.add("technical")
        if margin_disposition == "future_dated":
            future_lanes.add("market_leverage")
        elif margin_disposition == "stale":
            stale_lanes.add("market_leverage")

        short_row = short_latest.get(symbol)
        if short_row is not None:
            disposition = _freshness_disposition(
                str(short_row["date"]),
                observed_at,
                maximum_source_age_days,
            )
            if disposition != "fresh":
                short_row = None
                stale_counts["short_crowding"] = (
                    stale_counts.get("short_crowding", 0) + 1
                )
                (future_lanes if disposition == "future_dated" else stale_lanes).add(
                    "short_crowding"
                )

        flow = flow_latest.get(symbol)
        if flow is not None:
            disposition = _freshness_disposition(
                flow.as_of_date,
                observed_at,
                maximum_source_age_days,
            )
            if disposition != "fresh":
                flow = None
                stale_counts["short_flow"] = stale_counts.get("short_flow", 0) + 1
                (future_lanes if disposition == "future_dated" else stale_lanes).add(
                    "short_flow"
                )

        fundamental_row = fundamental_latest.get(symbol)
        if fundamental_row is not None:
            disposition = _freshness_disposition(
                str(fundamental_row["date"]),
                observed_at,
                maximum_source_age_days,
            )
            if disposition != "fresh":
                fundamental_row = None
                stale_counts["fundamentals"] = stale_counts.get("fundamentals", 0) + 1
                (future_lanes if disposition == "future_dated" else stale_lanes).add(
                    "fundamentals"
                )

        borrow_row = borrow_latest.get(symbol)
        if borrow_row is not None:
            disposition = _freshness_disposition(
                str(borrow_row["date"]),
                observed_at,
                maximum_source_age_days,
            )
            if disposition != "fresh":
                borrow_row = None
                stale_counts["borrow"] = stale_counts.get("borrow", 0) + 1
                (future_lanes if disposition == "future_dated" else stale_lanes).add(
                    "borrow"
                )

        threshold_row = threshold_latest.get(symbol)
        if threshold_row is not None:
            disposition = _freshness_disposition(
                str(threshold_row["date"]),
                observed_at,
                maximum_source_age_days,
            )
            if disposition != "fresh":
                threshold_row = None
                stale_counts["threshold"] = stale_counts.get("threshold", 0) + 1
                (future_lanes if disposition == "future_dated" else stale_lanes).add(
                    "threshold"
                )

        option_record = chain_latest.get(symbol)
        if option_record is not None:
            disposition = _freshness_disposition(
                str(option_record["snapshot_date"]),
                observed_at,
                maximum_source_age_days,
            )
            if disposition != "fresh":
                option_record = None
                stale_counts["options"] = stale_counts.get("options", 0) + 1
                (future_lanes if disposition == "future_dated" else stale_lanes).add(
                    "options"
                )

        ipo_row = ipo_latest.get(symbol)
        if ipo_row is not None and str(ipo_row["event_date"]) > technical.as_of_date:
            ipo_row = None
            stale_counts["ipo_future_dated"] = (
                stale_counts.get("ipo_future_dated", 0) + 1
            )
            future_lanes.add("ipo")

        symbol_ftd_rows = [
            row for row in ftd_rows if str(row["symbol"]).strip().upper() == symbol
        ]
        if symbol_ftd_rows:
            latest_ftd_date = max(
                str(row["settlement_date"]) for row in symbol_ftd_rows
            )
            disposition = _freshness_disposition(
                latest_ftd_date,
                observed_at,
                maximum_source_age_days,
            )
            if disposition != "fresh":
                symbol_ftd_rows = []
                stale_counts["fails_to_deliver"] = (
                    stale_counts.get("fails_to_deliver", 0) + 1
                )
                (future_lanes if disposition == "future_dated" else stale_lanes).add(
                    "fails_to_deliver"
                )

        short = _short_crowding_evidence(
            symbol,
            short_row,
            flow,
            borrow_row,
            tuple(
                sorted(
                    {
                        *(source_ids["short"] if short_row is not None else ()),
                        *(source_ids["flow"] if flow is not None else ()),
                        *(source_ids["borrow"] if borrow_row is not None else ()),
                    }
                )
            ),
        )
        settlement = _settlement_evidence(
            symbol,
            symbol_ftd_rows,
            threshold_row,
            short,
            tuple(
                sorted(
                    {
                        *(source_ids["ftd"] if symbol_ftd_rows else ()),
                        *(source_ids["threshold"] if threshold_row is not None else ()),
                    }
                )
            ),
        )
        fundamentals = _fundamental_evidence(
            symbol,
            fundamental_row,
            ipo_row,
            technical.as_of_date,
            tuple(
                sorted(
                    {
                        *(
                            source_ids["fundamentals"]
                            if fundamental_row is not None
                            else ()
                        ),
                        *(source_ids["ipo"] if ipo_row is not None else ()),
                    }
                )
            ),
        )
        options = _options_evidence(
            symbol,
            option_record,
            source_ids["options"] if option_record is not None else (),
        )
        history_source_path = history_source_paths.get(symbol)
        if history_source_path is None:
            raise ValueError(
                "technical history source is missing for loaded evidence: "
                f"symbol={symbol}, root={paths.history_root}"
            )
        technical_source_id = _file_source_id(history_source_path)
        contradiction_flags = _contradiction_flags(
            short,
            settlement,
            fundamentals,
            options,
        )
        integrity = EmpiricalIntegrityEvidence(
            observed_at_utc=(
                f"{observed_at.astimezone(timezone.utc).date().isoformat()}"
                "T00:00:00+00:00"
            ),
            path_containment_verified=True,
            technical_source_id=technical_source_id,
            lane_age_days=_lane_age_pairs(
                (
                    ("technical", technical.as_of_date),
                    ("short_crowding", short.as_of_date),
                    (
                        "short_flow",
                        flow.as_of_date if flow is not None else "",
                    ),
                    (
                        "borrow",
                        str((borrow_row or {}).get("date", "")),
                    ),
                    ("fails_to_deliver", settlement.as_of_date),
                    (
                        "threshold",
                        str((threshold_row or {}).get("date", "")),
                    ),
                    ("fundamentals", fundamentals.as_of_date),
                    ("options", options.as_of_date),
                    ("market_leverage", market_leverage.as_of_month),
                    (
                        "ipo",
                        str((ipo_row or {}).get("event_date", "")),
                    ),
                ),
                observed_at,
            ),
            lane_observation_counts=tuple(
                sorted(
                    (
                        ("technical", len(bars)),
                        (
                            "short_crowding",
                            (
                                2
                                if short.shares_short_prior_month is not None
                                else (1 if short.shares_short is not None else 0)
                            ),
                        ),
                        (
                            "short_flow",
                            short.daily_short_volume_observations,
                        ),
                        ("borrow", 1 if borrow_row is not None else 0),
                        (
                            "fails_to_deliver",
                            settlement.observation_count,
                        ),
                        ("threshold", 1 if threshold_row is not None else 0),
                        (
                            "fundamentals",
                            1 if fundamental_row is not None else 0,
                        ),
                        (
                            "options",
                            (
                                chain_observation_counts.get(symbol, 0)
                                if option_record is not None
                                else 0
                            ),
                        ),
                        (
                            "market_leverage",
                            market_leverage.observation_count,
                        ),
                        ("ipo", 1 if ipo_row is not None else 0),
                    )
                )
            ),
            stale_lanes=tuple(sorted(stale_lanes)),
            future_dated_lanes=tuple(sorted(future_lanes)),
            contradiction_flags=contradiction_flags,
        )
        evidence_records.append(
            SymbolEvidence(
                symbol=symbol,
                technical=technical,
                short_crowding=short,
                settlement=settlement,
                fundamentals=fundamentals,
                options=options,
                market_leverage=market_leverage,
                integrity=integrity,
            )
        )

    gaps = tuple(
        sorted(
            {
                *short_gaps,
                *flow_gaps,
                *fundamental_gaps,
                *ftd_gaps,
                *borrow_gaps,
                *threshold_gaps,
                *threshold_coverage_gaps,
                *margin_gaps,
                *ipo_gaps,
                *chain_gaps,
            }
        )
    )
    intake = {
        "artifact_type": "squeeze_bubble_intake_summary",
        "intake_version": "dopey-squeeze-bubble-intake-v2",
        "symbols_with_technical_evidence": len(evidence_records),
        "lane_gaps": gaps,
        "stale_record_counts": dict(sorted(stale_counts.items())),
        "daily_short_volume_is_short_interest": False,
        "ftd_is_proof_of_short_selling": False,
        "borrow_lane_required_for_full_pressure_completeness": True,
        "recent_ipo_discovery_lane_present": not ipo_gaps,
        "path_containment_verified": True,
        "stale_evidence_consumed": False,
        "future_dated_evidence_consumed": False,
        "source_ids": tuple(
            sorted(source_id for values in source_ids.values() for source_id in values)
        ),
    }
    return tuple(evidence_records), intake
