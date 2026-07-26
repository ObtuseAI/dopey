"""Minimal offline volatility surface model for DOPEY model-priced repricing."""
from __future__ import annotations

from .option_pricing_models import VolSurfacePoint, VolSurfaceSnapshot


VOL_SURFACE_MODEL_VERSION = "dopey-model-repricer-vol-surface-v1"


def build_minimal_vol_surface_snapshot(
    symbol: str,
    valuation_date: str,
    underlying_price: float,
    atm_iv: float,
    skew_slope: float,
    term_slope: float,
    floor_iv: float,
    cap_iv: float,
    expiry_days: list[int],
    strike_multipliers: list[float],
    real_option_chain_present: bool,
) -> VolSurfaceSnapshot:
    _validate_surface_inputs(underlying_price, atm_iv, floor_iv, cap_iv, expiry_days, strike_multipliers)
    points: list[VolSurfacePoint] = []
    for days in sorted(expiry_days):
        for multiplier in sorted(strike_multipliers):
            strike = round(underlying_price * multiplier, 6)
            for option_type in ["call", "put"]:
                points.append(surface_point(
                    symbol,
                    option_type,
                    strike,
                    days,
                    underlying_price,
                    atm_iv,
                    skew_slope,
                    term_slope,
                    floor_iv,
                    cap_iv,
                ))
    snapshot = VolSurfaceSnapshot(
        surface_id=f"{symbol.lower()}-{valuation_date}-model-surface",
        symbol=symbol,
        valuation_date=valuation_date,
        underlying_price=round(float(underlying_price), 6),
        atm_iv=round(float(atm_iv), 10),
        skew_slope=round(float(skew_slope), 10),
        term_slope=round(float(term_slope), 10),
        floor_iv=round(float(floor_iv), 10),
        cap_iv=round(float(cap_iv), 10),
        real_option_chain_absent=not real_option_chain_present,
        points=points,
        pricing_source_tier="model_priced",
        paper_only=True,
        live_blocked=True,
        snapshot_hash="",
    )
    return snapshot


def surface_point(
    symbol: str,
    option_type: str,
    strike: float,
    expiry_days: int,
    underlying_price: float,
    atm_iv: float,
    skew_slope: float,
    term_slope: float,
    floor_iv: float,
    cap_iv: float,
) -> VolSurfacePoint:
    if option_type not in {"call", "put"}:
        raise ValueError(f"unsupported option_type: {option_type}")
    _validate_surface_inputs(underlying_price, atm_iv, floor_iv, cap_iv, [expiry_days], [strike / underlying_price])
    moneyness = (strike / underlying_price) - 1.0
    term_component = term_slope * ((float(expiry_days) - 30.0) / 365.0)
    if option_type == "put":
        skew_component = -moneyness * skew_slope
    else:
        skew_component = moneyness * skew_slope
    wing_component = abs(moneyness) * abs(skew_slope) * 0.20
    raw_iv = atm_iv + skew_component + term_component + wing_component
    clamped_iv = _clamp(raw_iv, floor_iv, cap_iv)
    point = VolSurfacePoint(
        symbol=symbol,
        option_type=option_type,
        strike=round(float(strike), 6),
        expiry_days=int(expiry_days),
        moneyness=round(moneyness, 10),
        implied_vol=round(clamped_iv, 10),
        unclamped_implied_vol=round(raw_iv, 10),
        clamp_applied=round(raw_iv, 10) != round(clamped_iv, 10),
        pricing_source_tier="model_priced",
        paper_only=True,
        live_blocked=True,
        point_hash="",
    )
    return VolSurfacePoint(**point.to_dict())


def model_iv_from_snapshot(
    snapshot: VolSurfaceSnapshot,
    option_type: str,
    strike: float,
    expiry_days: int,
) -> VolSurfacePoint:
    return surface_point(
        snapshot.symbol,
        option_type,
        strike,
        expiry_days,
        snapshot.underlying_price,
        snapshot.atm_iv,
        snapshot.skew_slope,
        snapshot.term_slope,
        snapshot.floor_iv,
        snapshot.cap_iv,
    )


def model_iv_from_snapshot_record(
    snapshot: dict,
    option_type: str,
    strike: float,
    expiry_days: int,
) -> VolSurfacePoint:
    return surface_point(
        str(snapshot["symbol"]),
        option_type,
        strike,
        expiry_days,
        float(snapshot["underlying_price"]),
        float(snapshot["atm_iv"]),
        float(snapshot["skew_slope"]),
        float(snapshot["term_slope"]),
        float(snapshot["floor_iv"]),
        float(snapshot["cap_iv"]),
    )


def _validate_surface_inputs(
    underlying_price: float,
    atm_iv: float,
    floor_iv: float,
    cap_iv: float,
    expiry_days: list[int],
    strike_multipliers: list[float],
) -> None:
    if underlying_price <= 0.0:
        raise ValueError("underlying_price must be positive")
    if atm_iv <= 0.0:
        raise ValueError("atm_iv must be positive")
    if floor_iv <= 0.0:
        raise ValueError("floor_iv must be positive")
    if cap_iv <= floor_iv:
        raise ValueError("cap_iv must exceed floor_iv")
    if any(days < 0 for days in expiry_days):
        raise ValueError("expiry_days must be nonnegative")
    if any(multiplier <= 0.0 for multiplier in strike_multipliers):
        raise ValueError("strike_multipliers must be positive")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
