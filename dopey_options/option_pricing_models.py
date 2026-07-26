"""Deterministic option pricing records for DOPEY's offline model repricer."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any


MODEL_REPRICING_VERSION = "dopey-model-repricer-v1"
PRICING_SOURCE_TIERS: frozenset[str] = frozenset({"fixture_only", "model_priced", "quote_priced"})
_HASH_FIELDS: frozenset[str] = frozenset({
    "input_hash",
    "result_hash",
    "point_hash",
    "snapshot_hash",
    "path_hash",
    "flag_hash",
    "reproducibility_hash",
})


@dataclass(frozen=True)
class OptionPricingInput:
    symbol: str
    option_type: str
    strike: float
    expiry: str
    valuation_date: str
    underlying_price: float
    time_to_expiry_years: float
    implied_vol: float
    risk_free_rate: float
    dividend_yield: float
    pricing_source_tier: str
    paper_only: bool
    live_blocked: bool
    input_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["paper_only"] = True
        record["live_blocked"] = True
        record["input_hash"] = stable_model_repricing_hash(record)
        return record


@dataclass(frozen=True)
class OptionPricingResult:
    symbol: str
    option_type: str
    strike: float
    expiry: str
    valuation_date: str
    underlying_price: float
    time_to_expiry_years: float
    implied_vol: float
    risk_free_rate: float
    dividend_yield: float
    model_price: float
    intrinsic_value: float
    extrinsic_value: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    pricing_source_tier: str
    quality_flags: list[str]
    paper_only: bool
    live_blocked: bool
    result_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["quality_flags"] = sorted(self.quality_flags)
        record["paper_only"] = True
        record["live_blocked"] = True
        record["result_hash"] = stable_model_repricing_hash(record)
        return record


@dataclass(frozen=True)
class ImpliedVolResult:
    symbol: str
    option_type: str
    strike: float
    expiry: str
    valuation_date: str
    underlying_price: float
    option_price: float
    time_to_expiry_years: float
    risk_free_rate: float
    dividend_yield: float
    iv: float
    solver_status: str
    iterations: int
    price_error: float
    method_used: str
    reason_codes: list[str]
    pricing_source_tier: str
    paper_only: bool
    live_blocked: bool
    result_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["reason_codes"] = sorted(self.reason_codes)
        record["paper_only"] = True
        record["live_blocked"] = True
        record["result_hash"] = stable_model_repricing_hash(record)
        return record


@dataclass(frozen=True)
class VolSurfacePoint:
    symbol: str
    option_type: str
    strike: float
    expiry_days: int
    moneyness: float
    implied_vol: float
    unclamped_implied_vol: float
    clamp_applied: bool
    pricing_source_tier: str
    paper_only: bool
    live_blocked: bool
    point_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["paper_only"] = True
        record["live_blocked"] = True
        record["point_hash"] = stable_model_repricing_hash(record)
        return record


@dataclass(frozen=True)
class VolSurfaceSnapshot:
    surface_id: str
    symbol: str
    valuation_date: str
    underlying_price: float
    atm_iv: float
    skew_slope: float
    term_slope: float
    floor_iv: float
    cap_iv: float
    real_option_chain_absent: bool
    points: list[VolSurfacePoint]
    pricing_source_tier: str
    paper_only: bool
    live_blocked: bool
    snapshot_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["points"] = [
            point.to_dict()
            for point in sorted(self.points, key=lambda item: (item.expiry_days, item.option_type, item.strike))
        ]
        record["paper_only"] = True
        record["live_blocked"] = True
        record["snapshot_hash"] = stable_model_repricing_hash(record)
        return record


@dataclass(frozen=True)
class RepricingPathInput:
    path_id: str
    symbol: str
    option_type: str
    strike: float
    expiry: str
    path_rows: list[dict[str, Any]]
    surface_snapshot: dict[str, Any]
    risk_free_rate: float
    dividend_yield: float
    history_dataset_status: str
    real_option_chain_present: bool
    pricing_source_tier: str
    paper_only: bool
    live_blocked: bool
    path_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["path_rows"] = sorted(self.path_rows, key=lambda row: str(row.get("valuation_date", "")))
        record["paper_only"] = True
        record["live_blocked"] = True
        record["path_hash"] = stable_model_repricing_hash(record)
        return record


@dataclass(frozen=True)
class RepricingQualityFlag:
    artifact_type: str
    flag_id: str
    path_id: str
    symbol: str
    valuation_date: str
    severity: str
    reason_code: str
    message: str
    pricing_source_tier: str
    paper_only: bool
    live_blocked: bool
    flag_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["paper_only"] = True
        record["live_blocked"] = True
        record["flag_hash"] = stable_model_repricing_hash(record)
        return record


@dataclass(frozen=True)
class RepricingPathResult:
    path_id: str
    symbol: str
    option_type: str
    strike: float
    expiry: str
    step_count: int
    repricing_results: list[dict[str, Any]]
    mark_to_market_path: list[float]
    path_pnl: float
    max_adverse_excursion: float
    max_favorable_excursion: float
    terminal_premium: float
    pricing_source_tier: str
    quality_flags: list[dict[str, Any]]
    real_history_absent: bool
    real_option_chain_absent: bool
    paper_only: bool
    live_blocked: bool
    result_hash: str

    def to_dict(self) -> dict[str, Any]:
        record = asdict(self)
        record["quality_flags"] = sorted(self.quality_flags, key=lambda item: str(item.get("flag_id", "")))
        record["paper_only"] = True
        record["live_blocked"] = True
        record["result_hash"] = stable_model_repricing_hash(record)
        return record


def stable_model_repricing_hash(payload: dict[str, Any]) -> str:
    normalized = _strip_hash_fields(payload)
    encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_pricing_source_tier(pricing_source_tier: str, real_option_chain_present: bool) -> str:
    if pricing_source_tier not in PRICING_SOURCE_TIERS:
        raise ValueError(f"unsupported pricing_source_tier: {pricing_source_tier}")
    if pricing_source_tier == "quote_priced" and not real_option_chain_present:
        raise ValueError("quote_priced requires real option quote or chain data")
    return pricing_source_tier


def intrinsic_value(option_type: str, underlying_price: float, strike: float) -> float:
    _validate_option_type(option_type)
    if option_type == "call":
        return round(max(0.0, underlying_price - strike), 10)
    return round(max(0.0, strike - underlying_price), 10)


def option_price_upper_bound(option_type: str, underlying_price: float, strike: float) -> float:
    _validate_option_type(option_type)
    if option_type == "call":
        return round(max(0.0, underlying_price), 10)
    return round(max(0.0, strike), 10)


def price_european_option(pricing_input: OptionPricingInput) -> OptionPricingResult:
    tier = validate_pricing_source_tier(pricing_input.pricing_source_tier, False)
    _validate_pricing_input(pricing_input)
    intrinsic = intrinsic_value(pricing_input.option_type, pricing_input.underlying_price, pricing_input.strike)
    if pricing_input.time_to_expiry_years == 0.0 or pricing_input.implied_vol == 0.0:
        return _zero_time_result(pricing_input, intrinsic, tier)
    d1, d2 = _d1d2(
        pricing_input.underlying_price,
        pricing_input.strike,
        pricing_input.time_to_expiry_years,
        pricing_input.risk_free_rate,
        pricing_input.dividend_yield,
        pricing_input.implied_vol,
    )
    discount_rate = math.exp(-pricing_input.risk_free_rate * pricing_input.time_to_expiry_years)
    discount_yield = math.exp(-pricing_input.dividend_yield * pricing_input.time_to_expiry_years)
    pdf = _norm_pdf(d1)
    sqrt_time = math.sqrt(pricing_input.time_to_expiry_years)
    if pricing_input.option_type == "call":
        model_price = (
            pricing_input.underlying_price * discount_yield * _norm_cdf(d1)
            - pricing_input.strike * discount_rate * _norm_cdf(d2)
        )
        delta = discount_yield * _norm_cdf(d1)
        theta = (
            -(pricing_input.underlying_price * discount_yield * pdf * pricing_input.implied_vol) / (2.0 * sqrt_time)
            - pricing_input.risk_free_rate * pricing_input.strike * discount_rate * _norm_cdf(d2)
            + pricing_input.dividend_yield * pricing_input.underlying_price * discount_yield * _norm_cdf(d1)
        ) / 365.0
        rho = pricing_input.strike * pricing_input.time_to_expiry_years * discount_rate * _norm_cdf(d2) / 100.0
    else:
        model_price = (
            pricing_input.strike * discount_rate * _norm_cdf(-d2)
            - pricing_input.underlying_price * discount_yield * _norm_cdf(-d1)
        )
        delta = -discount_yield * _norm_cdf(-d1)
        theta = (
            -(pricing_input.underlying_price * discount_yield * pdf * pricing_input.implied_vol) / (2.0 * sqrt_time)
            + pricing_input.risk_free_rate * pricing_input.strike * discount_rate * _norm_cdf(-d2)
            - pricing_input.dividend_yield * pricing_input.underlying_price * discount_yield * _norm_cdf(-d1)
        ) / 365.0
        rho = -pricing_input.strike * pricing_input.time_to_expiry_years * discount_rate * _norm_cdf(-d2) / 100.0
    gamma = discount_yield * pdf / (pricing_input.underlying_price * pricing_input.implied_vol * sqrt_time)
    vega = pricing_input.underlying_price * discount_yield * sqrt_time * pdf / 100.0
    price = round(max(0.0, model_price), 6)
    result = OptionPricingResult(
        symbol=pricing_input.symbol,
        option_type=pricing_input.option_type,
        strike=round(pricing_input.strike, 6),
        expiry=pricing_input.expiry,
        valuation_date=pricing_input.valuation_date,
        underlying_price=round(pricing_input.underlying_price, 6),
        time_to_expiry_years=round(pricing_input.time_to_expiry_years, 10),
        implied_vol=round(pricing_input.implied_vol, 10),
        risk_free_rate=round(pricing_input.risk_free_rate, 10),
        dividend_yield=round(pricing_input.dividend_yield, 10),
        model_price=price,
        intrinsic_value=round(intrinsic, 6),
        extrinsic_value=round(max(0.0, price - intrinsic), 6),
        delta=round(delta, 6),
        gamma=round(gamma, 6),
        theta=round(theta, 6),
        vega=round(vega, 6),
        rho=round(rho, 6),
        pricing_source_tier=tier,
        quality_flags=[],
        paper_only=True,
        live_blocked=True,
        result_hash="",
    )
    return OptionPricingResult(**result.to_dict())


def option_pricing_input(
    symbol: str,
    option_type: str,
    strike: float,
    expiry: str,
    valuation_date: str,
    underlying_price: float,
    time_to_expiry_years: float,
    implied_vol: float,
    risk_free_rate: float,
    dividend_yield: float,
    pricing_source_tier: str,
) -> OptionPricingInput:
    record = OptionPricingInput(
        symbol=symbol,
        option_type=option_type,
        strike=round(float(strike), 6),
        expiry=expiry,
        valuation_date=valuation_date,
        underlying_price=round(float(underlying_price), 6),
        time_to_expiry_years=round(float(time_to_expiry_years), 10),
        implied_vol=round(float(implied_vol), 10),
        risk_free_rate=round(float(risk_free_rate), 10),
        dividend_yield=round(float(dividend_yield), 10),
        pricing_source_tier=pricing_source_tier,
        paper_only=True,
        live_blocked=True,
        input_hash="",
    )
    return OptionPricingInput(**record.to_dict())


def _zero_time_result(pricing_input: OptionPricingInput, intrinsic: float, pricing_source_tier: str) -> OptionPricingResult:
    result = OptionPricingResult(
        symbol=pricing_input.symbol,
        option_type=pricing_input.option_type,
        strike=round(pricing_input.strike, 6),
        expiry=pricing_input.expiry,
        valuation_date=pricing_input.valuation_date,
        underlying_price=round(pricing_input.underlying_price, 6),
        time_to_expiry_years=round(pricing_input.time_to_expiry_years, 10),
        implied_vol=round(pricing_input.implied_vol, 10),
        risk_free_rate=round(pricing_input.risk_free_rate, 10),
        dividend_yield=round(pricing_input.dividend_yield, 10),
        model_price=round(intrinsic, 6),
        intrinsic_value=round(intrinsic, 6),
        extrinsic_value=0.0,
        delta=0.0,
        gamma=0.0,
        theta=0.0,
        vega=0.0,
        rho=0.0,
        pricing_source_tier=pricing_source_tier,
        quality_flags=["expiry_intrinsic_pricing"],
        paper_only=True,
        live_blocked=True,
        result_hash="",
    )
    return OptionPricingResult(**result.to_dict())


def _validate_pricing_input(pricing_input: OptionPricingInput) -> None:
    _validate_option_type(pricing_input.option_type)
    if pricing_input.underlying_price <= 0.0:
        raise ValueError("underlying_price must be positive")
    if pricing_input.strike <= 0.0:
        raise ValueError("strike must be positive")
    if pricing_input.time_to_expiry_years < 0.0:
        raise ValueError("time_to_expiry_years must be nonnegative")
    if pricing_input.implied_vol < 0.0:
        raise ValueError("implied_vol must be nonnegative")


def _validate_option_type(option_type: str) -> None:
    if option_type not in {"call", "put"}:
        raise ValueError(f"unsupported option_type: {option_type}")


def _d1d2(
    underlying_price: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    implied_vol: float,
) -> tuple[float, float]:
    denominator = implied_vol * math.sqrt(time_to_expiry_years)
    d1 = (
        math.log(underlying_price / strike)
        + (risk_free_rate - dividend_yield + 0.5 * implied_vol * implied_vol) * time_to_expiry_years
    ) / denominator
    return d1, d1 - denominator


def _norm_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _norm_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def _strip_hash_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_hash_fields(item) for key, item in value.items() if key not in _HASH_FIELDS}
    if isinstance(value, list):
        return [_strip_hash_fields(item) for item in value]
    return value
