"""Offline model repricing engine for long-premium call and put paths."""
from __future__ import annotations

from typing import Any

from .option_pricing_models import (
    OptionPricingResult,
    RepricingPathInput,
    RepricingPathResult,
    RepricingQualityFlag,
    option_pricing_input,
    price_european_option,
    validate_pricing_source_tier,
)
from .vol_surface_model import model_iv_from_snapshot_record


MODEL_REPRICING_ENGINE_VERSION = "dopey-model-repricing-engine-v1"


def repricing_path_input(
    path_id: str,
    symbol: str,
    option_type: str,
    strike: float,
    expiry: str,
    path_rows: list[dict[str, Any]],
    surface_snapshot: dict[str, Any],
    risk_free_rate: float,
    dividend_yield: float,
    history_dataset_status: str,
    real_option_chain_present: bool,
    pricing_source_tier: str,
) -> RepricingPathInput:
    tier = validate_pricing_source_tier(pricing_source_tier, real_option_chain_present)
    if option_type not in {"call", "put"}:
        raise ValueError(f"unsupported option_type: {option_type}")
    if strike <= 0.0:
        raise ValueError("strike must be positive")
    if not path_rows:
        raise ValueError("path_rows must not be empty")
    record = RepricingPathInput(
        path_id=path_id,
        symbol=symbol,
        option_type=option_type,
        strike=round(float(strike), 6),
        expiry=expiry,
        path_rows=[dict(row) for row in path_rows],
        surface_snapshot=dict(surface_snapshot),
        risk_free_rate=round(float(risk_free_rate), 10),
        dividend_yield=round(float(dividend_yield), 10),
        history_dataset_status=history_dataset_status,
        real_option_chain_present=real_option_chain_present,
        pricing_source_tier=tier,
        paper_only=True,
        live_blocked=True,
        path_hash="",
    )
    return RepricingPathInput(**record.to_dict())


def reprice_long_option_path(path_input: RepricingPathInput) -> RepricingPathResult:
    tier = validate_pricing_source_tier(path_input.pricing_source_tier, path_input.real_option_chain_present)
    sorted_rows = sorted(path_input.path_rows, key=lambda row: str(row.get("valuation_date", "")))
    pricing_results: list[OptionPricingResult] = []
    quality_flags = _base_quality_flags(path_input)
    for row in sorted_rows:
        valuation_date = _string_row_value(row, "valuation_date")
        underlying_price = _float_row_value(row, "underlying_price")
        days_to_expiry = _int_row_value(row, "days_to_expiry")
        if underlying_price <= 0.0:
            raise ValueError(f"underlying_price must be positive for path {path_input.path_id} on {valuation_date}")
        if days_to_expiry < 0:
            raise ValueError(f"days_to_expiry must be nonnegative for path {path_input.path_id} on {valuation_date}")
        implied_vol = _implied_vol_for_row(path_input, row, days_to_expiry)
        pricing_results.append(price_european_option(option_pricing_input(
            path_input.symbol,
            path_input.option_type,
            path_input.strike,
            path_input.expiry,
            valuation_date,
            underlying_price,
            round(days_to_expiry / 365.0, 10),
            implied_vol,
            path_input.risk_free_rate,
            path_input.dividend_yield,
            tier,
        )))
    marks = [result.model_price for result in pricing_results]
    entry_premium = marks[0]
    pnl_path = [round(mark - entry_premium, 6) for mark in marks]
    repricing_results = [result.to_dict() for result in pricing_results]
    flags = [flag.to_dict() for flag in quality_flags]
    record = RepricingPathResult(
        path_id=path_input.path_id,
        symbol=path_input.symbol,
        option_type=path_input.option_type,
        strike=round(path_input.strike, 6),
        expiry=path_input.expiry,
        step_count=len(repricing_results),
        repricing_results=repricing_results,
        mark_to_market_path=marks,
        path_pnl=round(marks[-1] - entry_premium, 6),
        max_adverse_excursion=round(min(pnl_path), 6),
        max_favorable_excursion=round(max(pnl_path), 6),
        terminal_premium=round(marks[-1], 6),
        pricing_source_tier=tier,
        quality_flags=flags,
        real_history_absent=path_input.history_dataset_status == "missing_real_dataset",
        real_option_chain_absent=not path_input.real_option_chain_present,
        paper_only=True,
        live_blocked=True,
        result_hash="",
    )
    return RepricingPathResult(**record.to_dict())


def _base_quality_flags(path_input: RepricingPathInput) -> list[RepricingQualityFlag]:
    flags: list[RepricingQualityFlag] = []
    if path_input.history_dataset_status == "missing_real_dataset":
        flags.append(_quality_flag(
            f"{path_input.path_id}-missing-real-history",
            path_input.path_id,
            path_input.symbol,
            "",
            "warning",
            "missing_real_history",
            "history_dataset_status is missing_real_dataset; only model-pricer demo cases were repriced",
            path_input.pricing_source_tier,
        ))
    if not path_input.real_option_chain_present:
        flags.append(_quality_flag(
            f"{path_input.path_id}-real-option-chain-absent",
            path_input.path_id,
            path_input.symbol,
            "",
            "warning",
            "real_option_chain_absent",
            "real options quote or chain data is absent; quote_priced output is forbidden",
            path_input.pricing_source_tier,
        ))
    return flags


def _quality_flag(
    flag_id: str,
    path_id: str,
    symbol: str,
    valuation_date: str,
    severity: str,
    reason_code: str,
    message: str,
    pricing_source_tier: str,
) -> RepricingQualityFlag:
    record = RepricingQualityFlag(
        artifact_type="model_repricing_quality_flag",
        flag_id=flag_id,
        path_id=path_id,
        symbol=symbol,
        valuation_date=valuation_date,
        severity=severity,
        reason_code=reason_code,
        message=message,
        pricing_source_tier=pricing_source_tier,
        paper_only=True,
        live_blocked=True,
        flag_hash="",
    )
    return RepricingQualityFlag(**record.to_dict())


def _implied_vol_for_row(path_input: RepricingPathInput, row: dict[str, Any], days_to_expiry: int) -> float:
    if "implied_vol" in row:
        implied_vol = float(row["implied_vol"])
        if implied_vol <= 0.0:
            raise ValueError(f"implied_vol must be positive for path {path_input.path_id}")
        return round(implied_vol, 10)
    surface_point = model_iv_from_snapshot_record(
        path_input.surface_snapshot,
        path_input.option_type,
        path_input.strike,
        days_to_expiry,
    )
    return surface_point.implied_vol


def _string_row_value(row: dict[str, Any], key: str) -> str:
    value = row[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a nonempty string")
    return value


def _float_row_value(row: dict[str, Any], key: str) -> float:
    value = row[key]
    if isinstance(value, bool):
        raise TypeError(f"{key} must be numeric")
    return float(value)


def _int_row_value(row: dict[str, Any], key: str) -> int:
    value = row[key]
    if isinstance(value, bool):
        raise TypeError(f"{key} must be int")
    return int(value)
