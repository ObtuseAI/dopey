"""Strict value models for squeeze and bubble evidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShortCrowdingEvidence:
    as_of_date: str
    shares_short: float | None
    shares_short_prior_month: float | None
    short_percent_float: float | None
    days_to_cover: float | None
    float_shares: float | None
    shares_outstanding: float | None
    institutional_ownership: float | None
    insider_ownership: float | None
    average_volume: float | None
    borrow_fee_percent: float | None
    borrow_utilization: float | None
    borrow_available_shares: float | None
    daily_short_volume_ratio: float | None
    daily_short_volume_observations: int
    daily_short_volume_elevated_sessions: int
    daily_short_volume_median_ratio: float | None
    daily_short_volume_ratio_dispersion: float | None
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class SettlementEvidence:
    as_of_date: str
    latest_fails: float | None
    fails_to_float: float | None
    observation_count: int
    elevated_fail_sessions: int
    threshold_condition_proxy: bool
    official_threshold_listed: bool | None
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class FundamentalEvidence:
    as_of_date: str
    theme: str
    market_cap: float | None
    enterprise_value: float | None
    total_revenue: float | None
    trailing_pe: float | None
    forward_pe: float | None
    price_to_sales: float | None
    price_to_book: float | None
    profit_margin: float | None
    revenue_growth: float | None
    free_cashflow: float | None
    total_debt: float | None
    total_cash: float | None
    first_trade_date: str
    days_since_first_trade: int | None
    ipo_offer_price: float | None
    ipo_offer_amount: float | None
    ipo_status: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class OptionsPressureEvidence:
    as_of_date: str
    quote_derived: bool
    contract_rows: int
    call_open_interest: float | None
    put_open_interest: float | None
    call_volume: float | None
    put_volume: float | None
    put_call_open_interest_ratio: float | None
    put_call_volume_ratio: float | None
    total_gex_dollar_per_pct: float | None
    gamma_flip_strike: float | None
    atm_implied_vol: float | None
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class MarketLeverageEvidence:
    as_of_month: str
    margin_debit_millions: float | None
    free_credit_millions: float | None
    debit_to_free_credit_ratio: float | None
    debit_growth_3m: float | None
    debit_growth_12m: float | None
    observation_count: int
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class TechnicalState:
    as_of_date: str
    close: float
    average_dollar_volume_20d: float
    average_dollar_volume_5d: float
    dollar_volume_ratio_5d_20d: float
    signed_volume_pressure_20d: float
    return_5d: float
    return_20d: float
    return_63d: float | None
    return_252d: float | None
    volume_ratio_20d: float
    distance_sma20: float
    distance_sma50: float | None
    distance_sma200: float | None
    distance_52w_high: float | None
    realized_vol_20d: float
    realized_vol_ratio_20d_60d: float
    rsi14: float
    breakout_20d: bool
    breakdown_20d: bool


@dataclass(frozen=True)
class EmpiricalIntegrityEvidence:
    observed_at_utc: str
    path_containment_verified: bool
    technical_source_id: str
    lane_age_days: tuple[tuple[str, int | None], ...]
    lane_observation_counts: tuple[tuple[str, int], ...]
    stale_lanes: tuple[str, ...]
    future_dated_lanes: tuple[str, ...]
    contradiction_flags: tuple[str, ...]


@dataclass(frozen=True)
class SymbolEvidence:
    symbol: str
    technical: TechnicalState
    short_crowding: ShortCrowdingEvidence
    settlement: SettlementEvidence
    fundamentals: FundamentalEvidence
    options: OptionsPressureEvidence
    market_leverage: MarketLeverageEvidence
    integrity: EmpiricalIntegrityEvidence


@dataclass(frozen=True)
class IntelligencePolicy:
    minimum_average_dollar_volume: float
    minimum_squeeze_pressure: float
    minimum_squeeze_ignition: float
    minimum_squeeze_completeness: float
    minimum_bubble_fragility: float
    minimum_bubble_watch_fragility: float
    minimum_unwind_trigger: float
    minimum_bubble_completeness: float
    maximum_source_age_days: int
    maximum_technical_age_days: int
    minimum_squeeze_persistence: float
    minimum_bubble_persistence: float
    minimum_lane_robustness: float
    minimum_independent_sources: int
    minimum_options_contract_rows: int
    maximum_contradiction_count: int
    forward_horizons: tuple[int, ...]
    minimum_settled_observations: int


def default_policy() -> IntelligencePolicy:
    """Return the conservative v1 research policy."""

    return IntelligencePolicy(
        minimum_average_dollar_volume=10_000_000.0,
        minimum_squeeze_pressure=0.45,
        minimum_squeeze_ignition=0.50,
        minimum_squeeze_completeness=0.45,
        minimum_bubble_fragility=0.58,
        minimum_bubble_watch_fragility=0.20,
        minimum_unwind_trigger=0.42,
        minimum_bubble_completeness=0.55,
        maximum_source_age_days=45,
        maximum_technical_age_days=7,
        minimum_squeeze_persistence=0.45,
        minimum_bubble_persistence=0.40,
        minimum_lane_robustness=0.60,
        minimum_independent_sources=3,
        minimum_options_contract_rows=25,
        maximum_contradiction_count=0,
        forward_horizons=(2, 5, 10),
        minimum_settled_observations=30,
    )
