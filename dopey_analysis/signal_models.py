"""Typed records for DOPEY offline computed signal engines."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


SIGNAL_ENGINE_VERSION = "dopey-real-signal-engines-v1"
ALLOWED_SIGNAL_DATA_SOURCE_TIERS: frozenset[str] = frozenset({
    "fixture_only",
    "local_real_history",
    "missing_real_history",
})
SIGNAL_DIRECTIONS: frozenset[str] = frozenset({"bullish", "bearish", "neutral"})
SIGNAL_FAMILIES: frozenset[str] = frozenset({
    "momentum",
    "breakout",
    "fakeout",
    "trend_pullback",
    "volatility_regime",
    "relative_strength",
    "market_regime",
    "directional_setup",
})
SIGNAL_HASH_FIELDS: frozenset[str] = frozenset({
    "record_hash",
    "series_hash",
    "flag_hash",
    "run_hash",
    "proof_hash",
    "reproducibility_hash",
})


@dataclass(frozen=True)
class PriceBar:
    artifact_type: str
    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int
    data_source_tier: str
    real_history_used: bool
    fixture_only: bool
    not_real_signal_evidence: bool
    paper_only: bool
    live_blocked: bool
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["symbol"] = normalize_signal_symbol(self.symbol)
        record["data_source_tier"] = validate_signal_data_source_tier(self.data_source_tier)
        record["real_history_used"] = bool(self.real_history_used)
        record["fixture_only"] = bool(self.fixture_only)
        record["not_real_signal_evidence"] = bool(self.not_real_signal_evidence)
        record["paper_only"] = True
        record["live_blocked"] = True
        record["record_hash"] = stable_signal_hash(record)
        return record

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PriceBar":
        record = cls(
            artifact_type=_string_value(data, "artifact_type"),
            symbol=normalize_signal_symbol(_string_value(data, "symbol")),
            date=_string_value(data, "date"),
            open=_float_value(data, "open"),
            high=_float_value(data, "high"),
            low=_float_value(data, "low"),
            close=_float_value(data, "close"),
            adjusted_close=_float_value(data, "adjusted_close"),
            volume=_int_value(data, "volume"),
            data_source_tier=validate_signal_data_source_tier(_string_value(data, "data_source_tier")),
            real_history_used=_bool_value(data, "real_history_used"),
            fixture_only=_bool_value(data, "fixture_only"),
            not_real_signal_evidence=_bool_value(data, "not_real_signal_evidence"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
            record_hash=_string_or_empty(data, "record_hash"),
        )
        return cls(**record.to_dict())


@dataclass(frozen=True)
class SignalSeries:
    artifact_type: str
    symbol: str
    bars: list[PriceBar]
    data_source_tier: str
    real_history_used: bool
    fixture_only: bool
    not_real_signal_evidence: bool
    paper_only: bool
    live_blocked: bool
    series_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["symbol"] = normalize_signal_symbol(self.symbol)
        record["bars"] = [
            bar.to_dict()
            for bar in sorted(self.bars, key=lambda item: (item.date, item.symbol))
        ]
        record["data_source_tier"] = validate_signal_data_source_tier(self.data_source_tier)
        record["real_history_used"] = bool(self.real_history_used)
        record["fixture_only"] = bool(self.fixture_only)
        record["not_real_signal_evidence"] = bool(self.not_real_signal_evidence)
        record["paper_only"] = True
        record["live_blocked"] = True
        record["series_hash"] = stable_signal_hash(record)
        return record


@dataclass(frozen=True)
class MomentumSignal:
    artifact_type: str
    signal_id: str
    symbol: str
    signal_date: str
    lookback_window: int
    signal_family: str
    raw_value: float
    normalized_score: float
    direction: str
    confidence_proxy: float
    data_source_tier: str
    real_history_used: bool
    fixture_only: bool
    not_real_signal_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    return_5d: float
    return_10d: float
    return_20d: float
    momentum_slope: float
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _signal_record_dict(asdict(self), "momentum")


@dataclass(frozen=True)
class BreakoutSignal:
    artifact_type: str
    signal_id: str
    symbol: str
    signal_date: str
    lookback_window: int
    signal_family: str
    raw_value: float
    normalized_score: float
    direction: str
    confidence_proxy: float
    data_source_tier: str
    real_history_used: bool
    fixture_only: bool
    not_real_signal_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    prior_high: float
    prior_low: float
    close_price: float
    volume: int
    average_volume_20d: float
    volume_confirmed: bool
    breakout_distance: float
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _signal_record_dict(asdict(self), "breakout")


@dataclass(frozen=True)
class FakeoutSignal:
    artifact_type: str
    signal_id: str
    symbol: str
    signal_date: str
    lookback_window: int
    signal_family: str
    raw_value: float
    normalized_score: float
    direction: str
    confidence_proxy: float
    data_source_tier: str
    real_history_used: bool
    fixture_only: bool
    not_real_signal_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    prior_breakout_attempt: bool
    close_back_inside_prior_range: bool
    failed_breakout_direction: str
    reversal_magnitude: float
    prior_range_high: float
    prior_range_low: float
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _signal_record_dict(asdict(self), "fakeout")


@dataclass(frozen=True)
class TrendPullbackSignal:
    artifact_type: str
    signal_id: str
    symbol: str
    signal_date: str
    lookback_window: int
    signal_family: str
    raw_value: float
    normalized_score: float
    direction: str
    confidence_proxy: float
    data_source_tier: str
    real_history_used: bool
    fixture_only: bool
    not_real_signal_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    moving_average_20d: float
    moving_average_50d: float
    trend_slope: float
    pullback_to_ma_distance: float
    continuation_confirmed: bool
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _signal_record_dict(asdict(self), "trend_pullback")


@dataclass(frozen=True)
class VolatilityRegimeSignal:
    artifact_type: str
    signal_id: str
    symbol: str
    signal_date: str
    lookback_window: int
    signal_family: str
    raw_value: float
    normalized_score: float
    direction: str
    confidence_proxy: float
    data_source_tier: str
    real_history_used: bool
    fixture_only: bool
    not_real_signal_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    realized_volatility: float
    realized_volatility_ratio: float
    rolling_range_compression: float
    expansion_trigger: bool
    compression_trigger: bool
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _signal_record_dict(asdict(self), "volatility_regime")


@dataclass(frozen=True)
class RelativeStrengthSignal:
    artifact_type: str
    signal_id: str
    symbol: str
    signal_date: str
    lookback_window: int
    signal_family: str
    raw_value: float
    normalized_score: float
    direction: str
    confidence_proxy: float
    data_source_tier: str
    real_history_used: bool
    fixture_only: bool
    not_real_signal_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    symbol_return: float
    benchmark_symbol: str
    benchmark_return: float
    relative_return: float
    relative_strength_rank: float
    missing_benchmark: bool
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _signal_record_dict(asdict(self), "relative_strength")


@dataclass(frozen=True)
class MarketRegimeSignal:
    artifact_type: str
    signal_id: str
    symbol: str
    signal_date: str
    lookback_window: int
    signal_family: str
    raw_value: float
    normalized_score: float
    direction: str
    confidence_proxy: float
    data_source_tier: str
    real_history_used: bool
    fixture_only: bool
    not_real_signal_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    trend_state: str
    volatility_state: str
    drawdown_state: str
    risk_proxy_state: str
    regime_label: str
    drawdown: float
    realized_volatility: float
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _signal_record_dict(asdict(self), "market_regime")


@dataclass(frozen=True)
class DirectionalSetupSignal:
    artifact_type: str
    signal_id: str
    symbol: str
    signal_date: str
    lookback_window: int
    signal_family: str
    raw_value: float
    normalized_score: float
    direction: str
    confidence_proxy: float
    data_source_tier: str
    real_history_used: bool
    fixture_only: bool
    not_real_signal_evidence: bool
    paper_only: bool
    live_blocked: bool
    reason_codes: list[str]
    source_signal_id: str
    source_signal_family: str
    candidate_strategy: str
    option_structure: str
    long_call_candidate: bool
    long_put_candidate: bool
    no_trade: bool
    spread_created: bool
    short_vol_created: bool
    naked_selling_created: bool
    same_day_churn_allowed: bool
    real_sizing_used: bool
    broker_required: bool
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _signal_record_dict(asdict(self), "directional_setup")


@dataclass(frozen=True)
class SignalQualityFlag:
    artifact_type: str
    flag_id: str
    severity: str
    symbol: str
    signal_date: str
    signal_family: str
    reason_code: str
    message: str
    data_source_tier: str
    real_history_used: bool
    fixture_only: bool
    not_real_signal_evidence: bool
    paper_only: bool
    live_blocked: bool
    flag_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["data_source_tier"] = validate_signal_data_source_tier(self.data_source_tier)
        record["paper_only"] = True
        record["live_blocked"] = True
        record["flag_hash"] = stable_signal_hash(record)
        return record


@dataclass(frozen=True)
class SignalEngineRunResult:
    artifact_type: str
    signal_engine_version: str
    signal_engine_status: str
    history_dataset_status: str
    real_history_used: bool
    fixture_only_case_count: int
    local_real_history_case_count: int
    signal_family_distribution: dict[str, int]
    direction_distribution: dict[str, int]
    long_call_candidate_count: int
    long_put_candidate_count: int
    no_trade_count: int
    quality_flags: list[str]
    not_real_edge_evidence: bool
    paper_only: bool
    live_blocked: bool
    next_recommended_target: str
    artifact_paths: dict[str, str]
    run_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["quality_flags"] = sorted(self.quality_flags)
        record["signal_family_distribution"] = dict(sorted(self.signal_family_distribution.items()))
        record["direction_distribution"] = dict(sorted(self.direction_distribution.items()))
        record["not_real_edge_evidence"] = True
        record["paper_only"] = True
        record["live_blocked"] = True
        record["run_hash"] = stable_signal_hash(record)
        return record


def make_price_bar(
    symbol: str,
    date: str,
    open_price: float,
    high: float,
    low: float,
    close: float,
    adjusted_close: float,
    volume: int,
    data_source_tier: str,
    real_history_used: bool,
    fixture_only: bool,
    not_real_signal_evidence: bool,
) -> PriceBar:
    if high < max(open_price, low, close):
        raise ValueError(f"high must be >= open, low, and close for {symbol} on {date}")
    if low > min(open_price, high, close):
        raise ValueError(f"low must be <= open, high, and close for {symbol} on {date}")
    if min(open_price, high, low, close, adjusted_close) <= 0.0:
        raise ValueError(f"OHLC adjusted_close values must be positive for {symbol} on {date}")
    if volume < 0:
        raise ValueError(f"volume must be nonnegative for {symbol} on {date}")
    record = PriceBar(
        artifact_type="price_bar",
        symbol=normalize_signal_symbol(symbol),
        date=date,
        open=round(float(open_price), 6),
        high=round(float(high), 6),
        low=round(float(low), 6),
        close=round(float(close), 6),
        adjusted_close=round(float(adjusted_close), 6),
        volume=int(volume),
        data_source_tier=validate_signal_data_source_tier(data_source_tier),
        real_history_used=real_history_used,
        fixture_only=fixture_only,
        not_real_signal_evidence=not_real_signal_evidence,
        paper_only=True,
        live_blocked=True,
        record_hash="",
    )
    return PriceBar(**record.to_dict())


def make_signal_series(
    symbol: str,
    bars: list[PriceBar],
    data_source_tier: str,
    real_history_used: bool,
    fixture_only: bool,
    not_real_signal_evidence: bool,
) -> SignalSeries:
    if not bars:
        raise ValueError(f"signal series must not be empty for {symbol}")
    normalized_symbol = normalize_signal_symbol(symbol)
    if any(bar.symbol != normalized_symbol for bar in bars):
        raise ValueError(f"all bars must match signal series symbol {normalized_symbol}")
    record = SignalSeries(
        artifact_type="signal_series",
        symbol=normalized_symbol,
        bars=sorted(bars, key=lambda item: item.date),
        data_source_tier=validate_signal_data_source_tier(data_source_tier),
        real_history_used=real_history_used,
        fixture_only=fixture_only,
        not_real_signal_evidence=not_real_signal_evidence,
        paper_only=True,
        live_blocked=True,
        series_hash="",
    )
    hashed = record.to_dict()
    return SignalSeries(
        artifact_type=record.artifact_type,
        symbol=record.symbol,
        bars=record.bars,
        data_source_tier=record.data_source_tier,
        real_history_used=record.real_history_used,
        fixture_only=record.fixture_only,
        not_real_signal_evidence=record.not_real_signal_evidence,
        paper_only=True,
        live_blocked=True,
        series_hash=str(hashed["series_hash"]),
    )


def stable_signal_hash(payload: dict[str, Any]) -> str:
    normalized = _strip_hash_fields(payload)
    encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_signal_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty")
    return normalized


def validate_signal_data_source_tier(data_source_tier: str) -> str:
    if data_source_tier not in ALLOWED_SIGNAL_DATA_SOURCE_TIERS:
        raise ValueError(f"unsupported signal data_source_tier: {data_source_tier}")
    return data_source_tier


def validate_signal_direction(direction: str) -> str:
    if direction not in SIGNAL_DIRECTIONS:
        raise ValueError(f"unsupported signal direction: {direction}")
    return direction


def validate_signal_family(signal_family: str) -> str:
    if signal_family not in SIGNAL_FAMILIES:
        raise ValueError(f"unsupported signal_family: {signal_family}")
    return signal_family


def _signal_record_dict(record: dict[str, Any], expected_family: str) -> dict[str, Any]:
    record["symbol"] = normalize_signal_symbol(str(record["symbol"]))
    record["signal_family"] = validate_signal_family(str(record["signal_family"]))
    if record["signal_family"] != expected_family:
        raise ValueError(f"expected signal_family {expected_family}, got {record['signal_family']}")
    record["direction"] = validate_signal_direction(str(record["direction"]))
    record["data_source_tier"] = validate_signal_data_source_tier(str(record["data_source_tier"]))
    record["normalized_score"] = round(float(record["normalized_score"]), 6)
    record["confidence_proxy"] = round(float(record["confidence_proxy"]), 6)
    record["raw_value"] = round(float(record["raw_value"]), 10)
    record["reason_codes"] = sorted(str(code) for code in record["reason_codes"])
    record["paper_only"] = True
    record["live_blocked"] = True
    record["record_hash"] = stable_signal_hash(record)
    return record


def _strip_hash_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_hash_fields(item)
            for key, item in value.items()
            if key not in SIGNAL_HASH_FIELDS
        }
    if isinstance(value, list):
        return [_strip_hash_fields(item) for item in value]
    return value


def _string_value(data: dict[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a nonempty string")
    return value


def _string_or_empty(data: dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _float_value(data: dict[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool):
        raise TypeError(f"{key} must be numeric")
    return round(float(value), 6)


def _int_value(data: dict[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool):
        raise TypeError(f"{key} must be int")
    return int(value)


def _bool_value(data: dict[str, Any], key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value
