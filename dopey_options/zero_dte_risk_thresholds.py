"""Strict deterministic threshold config for the 0DTE special lifecycle model."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ZERO_DTE_RISK_THRESHOLD_VERSION = "dopey-zero-dte-risk-thresholds-v1"
REPO_ROOT = Path(__file__).resolve().parent.parent
ZERO_DTE_RISK_THRESHOLDS_FIXTURE_PATH = (
    REPO_ROOT / "dopey_data" / "fixtures" / "active_trading_policy" / "zero_dte_risk_thresholds.json"
)


@dataclass(frozen=True)
class ZeroDTERiskThresholds:
    threshold_version: str
    max_spread_pct: float
    minimum_volume: int
    minimum_open_interest: int
    minimum_liquidity_score: float
    max_slippage_score: float
    max_spread_adjusted_entry_penalty: float
    max_gamma_instability_score: float
    max_theta_decay_pressure: float
    minimum_abs_delta: float
    maximum_abs_delta: float
    max_iv_shock_score: float
    max_premium_overpayment_score: float
    min_iv_rank_fixture: float
    max_iv_rank_fixture: float
    max_implied_volatility: float
    max_event_risk_score: float
    max_macro_risk_score: float
    minimum_regime_score: float
    minimum_proof_score: float
    minimum_signal_confidence: float
    explicit_thesis_required: bool
    explicit_exit_plan_required: bool
    max_paper_premium_at_risk_per_trade: float
    max_paper_premium_at_risk_per_day: float
    max_zero_dte_candidates_approved_per_day: int
    max_zero_dte_exposure_share: float
    throttle_risk_score: float
    block_risk_score: float
    default_max_contracts_paper: int
    throttle_max_contracts_paper: int
    throttle_premium_factor: float
    special_lifecycle_required: bool
    explicit_same_day_special_close_reason_required: bool
    expiry_managed_state_required: bool
    paper_only: bool
    live_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ZeroDTERiskThresholds":
        return cls(
            threshold_version=_string_value(data, "threshold_version"),
            max_spread_pct=_float_value(data, "max_spread_pct"),
            minimum_volume=_int_value(data, "minimum_volume"),
            minimum_open_interest=_int_value(data, "minimum_open_interest"),
            minimum_liquidity_score=_float_value(data, "minimum_liquidity_score"),
            max_slippage_score=_float_value(data, "max_slippage_score"),
            max_spread_adjusted_entry_penalty=_float_value(data, "max_spread_adjusted_entry_penalty"),
            max_gamma_instability_score=_float_value(data, "max_gamma_instability_score"),
            max_theta_decay_pressure=_float_value(data, "max_theta_decay_pressure"),
            minimum_abs_delta=_float_value(data, "minimum_abs_delta"),
            maximum_abs_delta=_float_value(data, "maximum_abs_delta"),
            max_iv_shock_score=_float_value(data, "max_iv_shock_score"),
            max_premium_overpayment_score=_float_value(data, "max_premium_overpayment_score"),
            min_iv_rank_fixture=_float_value(data, "min_iv_rank_fixture"),
            max_iv_rank_fixture=_float_value(data, "max_iv_rank_fixture"),
            max_implied_volatility=_float_value(data, "max_implied_volatility"),
            max_event_risk_score=_float_value(data, "max_event_risk_score"),
            max_macro_risk_score=_float_value(data, "max_macro_risk_score"),
            minimum_regime_score=_float_value(data, "minimum_regime_score"),
            minimum_proof_score=_float_value(data, "minimum_proof_score"),
            minimum_signal_confidence=_float_value(data, "minimum_signal_confidence"),
            explicit_thesis_required=_bool_value(data, "explicit_thesis_required"),
            explicit_exit_plan_required=_bool_value(data, "explicit_exit_plan_required"),
            max_paper_premium_at_risk_per_trade=_float_value(data, "max_paper_premium_at_risk_per_trade"),
            max_paper_premium_at_risk_per_day=_float_value(data, "max_paper_premium_at_risk_per_day"),
            max_zero_dte_candidates_approved_per_day=_int_value(data, "max_zero_dte_candidates_approved_per_day"),
            max_zero_dte_exposure_share=_float_value(data, "max_zero_dte_exposure_share"),
            throttle_risk_score=_float_value(data, "throttle_risk_score"),
            block_risk_score=_float_value(data, "block_risk_score"),
            default_max_contracts_paper=_int_value(data, "default_max_contracts_paper"),
            throttle_max_contracts_paper=_int_value(data, "throttle_max_contracts_paper"),
            throttle_premium_factor=_float_value(data, "throttle_premium_factor"),
            special_lifecycle_required=_bool_value(data, "special_lifecycle_required"),
            explicit_same_day_special_close_reason_required=_bool_value(data, "explicit_same_day_special_close_reason_required"),
            expiry_managed_state_required=_bool_value(data, "expiry_managed_state_required"),
            paper_only=_bool_value(data, "paper_only"),
            live_blocked=_bool_value(data, "live_blocked"),
        )


def default_zero_dte_risk_thresholds() -> ZeroDTERiskThresholds:
    return ZeroDTERiskThresholds(
        threshold_version=ZERO_DTE_RISK_THRESHOLD_VERSION,
        max_spread_pct=0.04,
        minimum_volume=1_000,
        minimum_open_interest=2_000,
        minimum_liquidity_score=0.74,
        max_slippage_score=0.30,
        max_spread_adjusted_entry_penalty=0.12,
        max_gamma_instability_score=0.58,
        max_theta_decay_pressure=0.50,
        minimum_abs_delta=0.20,
        maximum_abs_delta=0.72,
        max_iv_shock_score=0.72,
        max_premium_overpayment_score=0.70,
        min_iv_rank_fixture=0.05,
        max_iv_rank_fixture=0.78,
        max_implied_volatility=0.75,
        max_event_risk_score=0.55,
        max_macro_risk_score=0.55,
        minimum_regime_score=0.62,
        minimum_proof_score=0.72,
        minimum_signal_confidence=0.68,
        explicit_thesis_required=True,
        explicit_exit_plan_required=True,
        max_paper_premium_at_risk_per_trade=500.0,
        max_paper_premium_at_risk_per_day=1_500.0,
        max_zero_dte_candidates_approved_per_day=3,
        max_zero_dte_exposure_share=0.015,
        throttle_risk_score=0.34,
        block_risk_score=0.65,
        default_max_contracts_paper=2,
        throttle_max_contracts_paper=1,
        throttle_premium_factor=0.50,
        special_lifecycle_required=True,
        explicit_same_day_special_close_reason_required=True,
        expiry_managed_state_required=True,
        paper_only=True,
        live_blocked=True,
    )


def load_zero_dte_risk_thresholds(path: Path | str) -> ZeroDTERiskThresholds:
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    thresholds = record.get("thresholds", record)
    if not isinstance(thresholds, dict):
        raise TypeError("zero_dte_risk_thresholds fixture must contain an object")
    return ZeroDTERiskThresholds.from_dict(thresholds)


def load_default_zero_dte_risk_thresholds() -> ZeroDTERiskThresholds:
    if ZERO_DTE_RISK_THRESHOLDS_FIXTURE_PATH.exists():
        return load_zero_dte_risk_thresholds(ZERO_DTE_RISK_THRESHOLDS_FIXTURE_PATH)
    return default_zero_dte_risk_thresholds()


def _string_value(data: dict[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str")
    if not value:
        raise ValueError(f"{key} must not be empty")
    return value


def _bool_value(data: dict[str, Any], key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value


def _int_value(data: dict[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be int")
    return value


def _float_value(data: dict[str, Any], key: str) -> float:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{key} must be numeric")
    return float(value)
