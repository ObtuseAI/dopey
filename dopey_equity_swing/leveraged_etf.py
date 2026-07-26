"""Underlying-chart-authoritative leveraged ETF swing planning."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, TypedDict

from .market_structure import Bar, analyze_multi_timeframe_structure
from .thesis import build_equity_swing_thesis, technical_confirmation


ExposureDirection = Literal["bullish", "bearish"]
AnalysisRelationship = Literal["exact_underlying", "benchmark_proxy"]
ProductCategory = Literal[
    "single_stock",
    "broad_market",
    "sector",
    "fixed_income",
    "international",
    "commodity",
    "crypto_linked",
]


class LeveragedEtfSpec(TypedDict):
    pair_id: str
    trade_symbol: str
    analysis_symbol: str
    exposure_direction: ExposureDirection
    daily_leverage_multiple: float
    analysis_relationship: AnalysisRelationship
    product_category: ProductCategory
    execution_priority: int
    target_benchmark: str
    issuer: str
    official_source_url: str


def _pair_specs(
    pair_id: str,
    bull_symbol: str,
    bear_symbol: str,
    analysis_symbol: str,
    bull_multiple: float,
    bear_multiple: float,
    analysis_relationship: AnalysisRelationship,
    product_category: ProductCategory,
    execution_priority: int,
    target_benchmark: str,
    issuer: str,
    official_source_url: str,
) -> tuple[LeveragedEtfSpec, LeveragedEtfSpec]:
    return (
        {
            "pair_id": pair_id,
            "trade_symbol": bull_symbol,
            "analysis_symbol": analysis_symbol,
            "exposure_direction": "bullish",
            "daily_leverage_multiple": bull_multiple,
            "analysis_relationship": analysis_relationship,
            "product_category": product_category,
            "execution_priority": execution_priority,
            "target_benchmark": target_benchmark,
            "issuer": issuer,
            "official_source_url": official_source_url,
        },
        {
            "pair_id": pair_id,
            "trade_symbol": bear_symbol,
            "analysis_symbol": analysis_symbol,
            "exposure_direction": "bearish",
            "daily_leverage_multiple": bear_multiple,
            "analysis_relationship": analysis_relationship,
            "product_category": product_category,
            "execution_priority": execution_priority,
            "target_benchmark": target_benchmark,
            "issuer": issuer,
            "official_source_url": official_source_url,
        },
    )


DIREXION_SINGLE_STOCK_SOURCE = "https://www.direxion.com/single-stock-etfs"
PROSHARES_GEARED_SOURCE = (
    "https://www.proshares.com/our-etfs/find-leveraged-and-inverse-etfs"
)


LEVERAGED_ETF_CATALOG: tuple[LeveragedEtfSpec, ...] = (
    *_pair_specs(
        "mstr_2x",
        "MSTU",
        "MSTZ",
        "MSTR",
        2.0,
        -2.0,
        "exact_underlying",
        "single_stock",
        1,
        "Strategy Inc. common stock (MSTR)",
        "T-REX ETFs",
        "https://www.rexshares.com/mstz/",
    ),
    *_pair_specs(
        "tsla_daily",
        "TSLL",
        "TSLS",
        "TSLA",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Tesla, Inc. common stock (TSLA)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "aapl_daily",
        "AAPU",
        "AAPD",
        "AAPL",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Apple Inc. common stock (AAPL)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "amd_daily",
        "AMUU",
        "AMDD",
        "AMD",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Advanced Micro Devices, Inc. common stock (AMD)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "amzn_daily",
        "AMZU",
        "AMZD",
        "AMZN",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Amazon.com, Inc. common stock (AMZN)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "avgo_daily",
        "AVL",
        "AVS",
        "AVGO",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Broadcom Inc. common stock (AVGO)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "csco_daily",
        "CSCL",
        "CSCS",
        "CSCO",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Cisco Systems, Inc. common stock (CSCO)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "googl_daily",
        "GGLL",
        "GGLS",
        "GOOGL",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Alphabet Inc. Class A common stock (GOOGL)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "meta_daily",
        "METU",
        "METD",
        "META",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Meta Platforms, Inc. common stock (META)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "msft_daily",
        "MSFU",
        "MSFD",
        "MSFT",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Microsoft Corporation common stock (MSFT)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "mu_daily",
        "MUU",
        "MUD",
        "MU",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Micron Technology, Inc. common stock (MU)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "nflx_daily",
        "NFXL",
        "NFXS",
        "NFLX",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Netflix, Inc. common stock (NFLX)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "nvda_daily",
        "NVDU",
        "NVDD",
        "NVDA",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "NVIDIA Corporation common stock (NVDA)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "orcl_daily",
        "ORCU",
        "ORCS",
        "ORCL",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Oracle Corporation common stock (ORCL)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "panw_daily",
        "PALU",
        "PALD",
        "PANW",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Palo Alto Networks, Inc. common stock (PANW)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "pltr_daily",
        "PLTU",
        "PLTD",
        "PLTR",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Palantir Technologies Inc. common stock (PLTR)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "qcom_daily",
        "QCMU",
        "QCMD",
        "QCOM",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "QUALCOMM Incorporated common stock (QCOM)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "tsm_daily",
        "TSMX",
        "TSMZ",
        "TSM",
        2.0,
        -1.0,
        "exact_underlying",
        "single_stock",
        1,
        "Taiwan Semiconductor Manufacturing Co. ADR (TSM)",
        "Direxion",
        DIREXION_SINGLE_STOCK_SOURCE,
    ),
    *_pair_specs(
        "nasdaq100_3x",
        "TQQQ",
        "SQQQ",
        "QQQ",
        3.0,
        -3.0,
        "benchmark_proxy",
        "broad_market",
        1,
        "Nasdaq-100 Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "nasdaq100_2x",
        "QLD",
        "QID",
        "QQQ",
        2.0,
        -2.0,
        "benchmark_proxy",
        "broad_market",
        2,
        "Nasdaq-100 Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "sp500_direxion_3x",
        "SPXL",
        "SPXS",
        "SPY",
        3.0,
        -3.0,
        "benchmark_proxy",
        "broad_market",
        1,
        "S&P 500 Index",
        "Direxion",
        "https://www.direxion.com/product/daily-sp-500-bull-bear-3x-etfs",
    ),
    *_pair_specs(
        "sp500_proshares_3x",
        "UPRO",
        "SPXU",
        "SPY",
        3.0,
        -3.0,
        "benchmark_proxy",
        "broad_market",
        2,
        "S&P 500 Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "sp500_proshares_2x",
        "SSO",
        "SDS",
        "SPY",
        2.0,
        -2.0,
        "benchmark_proxy",
        "broad_market",
        3,
        "S&P 500 Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "russell2000_3x",
        "URTY",
        "SRTY",
        "IWM",
        3.0,
        -3.0,
        "benchmark_proxy",
        "broad_market",
        1,
        "Russell 2000 Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "russell2000_2x",
        "UWM",
        "TWM",
        "IWM",
        2.0,
        -2.0,
        "benchmark_proxy",
        "broad_market",
        2,
        "Russell 2000 Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "dow30_3x",
        "UDOW",
        "SDOW",
        "DIA",
        3.0,
        -3.0,
        "benchmark_proxy",
        "broad_market",
        1,
        "Dow Jones Industrial Average",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "technology_2x",
        "ROM",
        "REW",
        "XLK",
        2.0,
        -2.0,
        "benchmark_proxy",
        "sector",
        1,
        "S&P Technology Select Sector Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "healthcare_2x",
        "RXL",
        "RXD",
        "XLV",
        2.0,
        -2.0,
        "benchmark_proxy",
        "sector",
        1,
        "S&P Health Care Select Sector Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "real_estate_2x",
        "URE",
        "SRS",
        "IYR",
        2.0,
        -2.0,
        "benchmark_proxy",
        "sector",
        1,
        "S&P Real Estate Select Sector Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "consumer_discretionary_2x",
        "UCC",
        "SCC",
        "XLY",
        2.0,
        -2.0,
        "benchmark_proxy",
        "sector",
        1,
        "S&P Consumer Discretionary Select Sector Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "utilities_2x",
        "UPW",
        "SDP",
        "XLU",
        2.0,
        -2.0,
        "benchmark_proxy",
        "sector",
        1,
        "S&P Utilities Select Sector Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "industrials_2x",
        "UXI",
        "SIJ",
        "XLI",
        2.0,
        -2.0,
        "benchmark_proxy",
        "sector",
        1,
        "S&P Industrials Select Sector Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "materials_2x",
        "UYM",
        "SMN",
        "XLB",
        2.0,
        -2.0,
        "benchmark_proxy",
        "sector",
        1,
        "S&P Materials Select Sector Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "financials_2x",
        "UYG",
        "SKF",
        "XLF",
        2.0,
        -2.0,
        "benchmark_proxy",
        "sector",
        1,
        "S&P Financial Select Sector Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "consumer_staples_2x",
        "UGE",
        "SZK",
        "XLP",
        2.0,
        -2.0,
        "benchmark_proxy",
        "sector",
        1,
        "S&P Consumer Staples Select Sector Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "semiconductors_direxion_3x",
        "SOXL",
        "SOXS",
        "SOXX",
        3.0,
        -3.0,
        "benchmark_proxy",
        "sector",
        1,
        "NYSE Semiconductor Index",
        "Direxion",
        "https://www.direxion.com/product/daily-semiconductor-bull-bear-3x-etfs",
    ),
    *_pair_specs(
        "semiconductors_proshares_2x",
        "USD",
        "SSG",
        "SOXX",
        2.0,
        -2.0,
        "benchmark_proxy",
        "sector",
        2,
        "Dow Jones U.S. Semiconductors Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "treasury_7_10y_2x",
        "UST",
        "PST",
        "IEF",
        2.0,
        -2.0,
        "benchmark_proxy",
        "fixed_income",
        1,
        "ICE U.S. Treasury 7-10 Year Bond Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "treasury_20y_2x",
        "UBT",
        "TBT",
        "TLT",
        2.0,
        -2.0,
        "benchmark_proxy",
        "fixed_income",
        1,
        "ICE U.S. Treasury 20+ Year Bond Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "emerging_markets_2x",
        "EET",
        "EEV",
        "EEM",
        2.0,
        -2.0,
        "benchmark_proxy",
        "international",
        1,
        "MSCI Emerging Markets Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "eafe_2x",
        "EFO",
        "EFU",
        "EFA",
        2.0,
        -2.0,
        "benchmark_proxy",
        "international",
        1,
        "MSCI EAFE Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "high_yield_2x",
        "UJB",
        "SJB",
        "HYG",
        2.0,
        -1.0,
        "benchmark_proxy",
        "fixed_income",
        1,
        "Markit iBoxx $ Liquid High Yield Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "gold_2x",
        "UGL",
        "GLL",
        "GLD",
        2.0,
        -2.0,
        "benchmark_proxy",
        "commodity",
        1,
        "Bloomberg Gold Subindex",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "silver_2x",
        "AGQ",
        "ZSL",
        "SLV",
        2.0,
        -2.0,
        "benchmark_proxy",
        "commodity",
        1,
        "Bloomberg Silver Subindex",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "crude_oil_2x",
        "UCO",
        "SCO",
        "USO",
        2.0,
        -2.0,
        "benchmark_proxy",
        "commodity",
        1,
        "Bloomberg Commodity Balanced WTI Crude Oil Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "natural_gas_2x",
        "BOIL",
        "KOLD",
        "UNG",
        2.0,
        -2.0,
        "benchmark_proxy",
        "commodity",
        1,
        "Bloomberg Natural Gas Subindex",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "bitcoin_2x",
        "BITU",
        "SBIT",
        "IBIT",
        2.0,
        -2.0,
        "benchmark_proxy",
        "crypto_linked",
        1,
        "Bloomberg Bitcoin Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
    *_pair_specs(
        "nasdaq_biotech_2x",
        "BIB",
        "BIS",
        "IBB",
        2.0,
        -2.0,
        "benchmark_proxy",
        "sector",
        1,
        "Nasdaq Biotechnology Index",
        "ProShares",
        PROSHARES_GEARED_SOURCE,
    ),
)

MAX_LEVERAGED_ETF_HOLDING_SESSIONS = 5
MAX_LEVERAGED_ETF_GROSS_ALLOCATION_FRACTION = 0.20
MAX_LEVERAGED_ETF_PRODUCT_ALLOCATION_FRACTION = 0.10


def build_leveraged_etf_swing_plans(
    source_theses: list[dict[str, Any]],
    histories: dict[str, list[Bar]],
) -> list[dict[str, Any]]:
    """Build one auditable plan per supported product from its analysis chart."""
    validate_leveraged_etf_catalog(LEVERAGED_ETF_CATALOG)
    thesis_by_symbol = {
        str(record.get("symbol", "")): record
        for record in source_theses
        if isinstance(record, dict)
    }
    chart_theses: dict[str, dict[str, Any]] = {}
    for analysis_symbol in sorted(
        {spec["analysis_symbol"] for spec in LEVERAGED_ETF_CATALOG}
    ):
        rows = histories.get(analysis_symbol, [])
        if not rows:
            continue
        chart_theses[analysis_symbol] = thesis_by_symbol.get(
            analysis_symbol
        ) or _build_chart_only_thesis(
            analysis_symbol,
            rows,
            histories,
        )
    plans = [
        _build_product_plan(spec, chart_theses.get(spec["analysis_symbol"]), histories)
        for spec in LEVERAGED_ETF_CATALOG
    ]
    return sorted(plans, key=lambda record: str(record["trade_symbol"]))


def leveraged_trade_symbols() -> frozenset[str]:
    return frozenset(spec["trade_symbol"] for spec in LEVERAGED_ETF_CATALOG)


def validate_leveraged_etf_catalog(
    catalog: tuple[LeveragedEtfSpec, ...],
) -> dict[str, int]:
    trade_symbols = [spec["trade_symbol"] for spec in catalog]
    if len(trade_symbols) != len(set(trade_symbols)):
        raise ValueError("leveraged ETF catalog contains duplicate trade symbols")
    pairs: dict[str, list[LeveragedEtfSpec]] = {}
    for spec in catalog:
        pairs.setdefault(spec["pair_id"], []).append(spec)
        leverage = float(spec["daily_leverage_multiple"])
        if spec["exposure_direction"] == "bullish" and leverage < 1.0:
            raise ValueError(
                "bull leveraged ETF must have daily target >= 1x: "
                f"symbol={spec['trade_symbol']}, target={leverage}"
            )
        if spec["exposure_direction"] == "bearish" and leverage > -1.0:
            raise ValueError(
                "bear inverse ETF must have daily target <= -1x: "
                f"symbol={spec['trade_symbol']}, target={leverage}"
            )
        if spec["execution_priority"] <= 0:
            raise ValueError(
                f"execution priority must be positive: symbol={spec['trade_symbol']}"
            )
    for pair_id, pair in sorted(pairs.items()):
        directions = {spec["exposure_direction"] for spec in pair}
        analysis_symbols = {spec["analysis_symbol"] for spec in pair}
        if len(pair) != 2 or directions != {"bullish", "bearish"}:
            raise ValueError(
                f"leveraged ETF pair requires one bull and one bear product: pair_id={pair_id}"
            )
        if len(analysis_symbols) != 1:
            raise ValueError(
                f"leveraged ETF pair must share one analysis symbol: pair_id={pair_id}"
            )
    return {
        "pair_count": len(pairs),
        "product_count": len(catalog),
        "analysis_symbol_count": len({spec["analysis_symbol"] for spec in catalog}),
    }


def preferred_leveraged_etf_plans(
    plans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Select one ranked execution vehicle per analysis symbol."""
    preferred: dict[str, dict[str, Any]] = {}
    for plan in sorted(
        plans,
        key=lambda record: (
            int(record.get("execution_priority", 0)),
            str(record.get("trade_symbol", "")),
        ),
    ):
        analysis_symbol = str(plan.get("analysis_symbol", ""))
        if analysis_symbol and analysis_symbol not in preferred:
            preferred[analysis_symbol] = plan
    return [preferred[symbol] for symbol in sorted(preferred)]


def _build_chart_only_thesis(
    symbol: str,
    rows: list[Bar],
    histories: dict[str, list[Bar]],
) -> dict[str, Any]:
    benchmark = histories.get("SPY")
    if benchmark is None:
        raise ValueError("leveraged ETF chart thesis requires SPY history")
    structure = analyze_multi_timeframe_structure(symbol, rows)
    technical = technical_confirmation(rows, benchmark, None, structure)
    neutral_fundamental = {
        "artifact_type": "non_directional_fundamental_placeholder",
        "fundamental_status": "not_applicable_for_index_or_benchmark_proxy",
        "bullish_support_score": 0.5,
        "bearish_support_score": 0.5,
        "directional_information_added": False,
    }
    thesis = build_equity_swing_thesis(
        symbol,
        rows,
        structure,
        technical,
        neutral_fundamental,
        None,
    )
    return {
        **thesis,
        "artifact_type": "underlying_chart_swing_thesis",
        "source_thesis_kind": "underlying_chart_only",
        "direction_source_policy": (
            "analysis_symbol_daily_weekly_monthly_chart_technicals_only_"
            "neutral_placeholder_adds_no_direction"
        ),
    }


def _build_product_plan(
    spec: LeveragedEtfSpec,
    thesis: dict[str, Any] | None,
    histories: dict[str, list[Bar]],
) -> dict[str, Any]:
    analysis_symbol = spec["analysis_symbol"]
    rows = histories.get(analysis_symbol, [])
    chart_hash = _history_hash(rows)
    chart_as_of_date = str(rows[-1]["date"]) if rows else ""
    source_as_of_date = str(thesis.get("as_of_date", "")) if thesis else ""
    source_direction = str(thesis.get("direction", "neutral")) if thesis else "neutral"
    source_actionable = bool(
        thesis
        and thesis.get("thesis_status") == "actionable_shadow_thesis"
        and thesis.get("trade_intent") != "no_trade"
    )
    provenance_complete = bool(
        thesis
        and rows
        and source_as_of_date == chart_as_of_date
        and isinstance(thesis.get("technical_confirmation"), dict)
        and isinstance(thesis.get("structure_reference"), dict)
    )
    direction_matches = source_direction == spec["exposure_direction"]
    levels_complete = bool(
        thesis
        and float(thesis.get("entry_reference_price") or 0.0) > 0.0
        and float(thesis.get("invalidation_price") or 0.0) > 0.0
        and float(thesis.get("target_price") or 0.0) > 0.0
    )
    actionable = (
        source_actionable
        and provenance_complete
        and direction_matches
        and levels_complete
    )
    if not rows:
        plan_status = "blocked_missing_analysis_symbol_history"
    elif thesis is None:
        plan_status = "blocked_missing_underlying_chart_thesis"
    elif not provenance_complete:
        plan_status = "blocked_underlying_chart_provenance_incomplete"
    elif not source_actionable:
        plan_status = "no_trade_underlying_chart_thesis_not_actionable"
    elif not direction_matches:
        plan_status = "no_trade_exposure_direction_mismatch"
    elif not levels_complete:
        plan_status = "blocked_underlying_chart_levels_incomplete"
    else:
        plan_status = "actionable_shadow_leveraged_etf_plan"
    leverage = float(spec["daily_leverage_multiple"])
    source_hold = int(thesis.get("expected_hold_trading_days", 0)) if thesis else 0
    expected_hold = (
        min(max(source_hold, 2), MAX_LEVERAGED_ETF_HOLDING_SESSIONS)
        if actionable
        else 0
    )
    source_hash = _record_hash(thesis) if thesis else ""
    analysis_reference = (
        float(thesis.get("entry_reference_price") or 0.0) if thesis else 0.0
    )
    analysis_invalidation = (
        float(thesis.get("invalidation_price") or 0.0) if thesis else 0.0
    )
    analysis_target = float(thesis.get("target_price") or 0.0) if thesis else 0.0
    entry_operator = ">=" if spec["exposure_direction"] == "bullish" else "<="
    invalidation_operator = "<=" if spec["exposure_direction"] == "bullish" else ">="
    target_operator = ">=" if spec["exposure_direction"] == "bullish" else "<="
    reason_codes = [
        "underlying_chart_is_direction_authority",
        "leveraged_etf_is_execution_vehicle_only",
        "daily_reset_compounding_risk_capped",
        "no_averaging_down_or_martingale",
        "long_shares_only",
    ]
    if spec["exposure_direction"] == "bearish":
        reason_codes.append("bearish_exposure_via_long_inverse_etf_not_short_sale")
    if spec["analysis_relationship"] == "benchmark_proxy":
        reason_codes.append("benchmark_proxy_basis_risk")
    return {
        "artifact_type": "leveraged_etf_swing_plan",
        "schema_version": "dopey-leveraged-etf-swing-plan-v2",
        "plan_status": plan_status,
        "pair_id": spec["pair_id"],
        "trade_symbol": spec["trade_symbol"],
        "analysis_symbol": analysis_symbol,
        "analysis_relationship": spec["analysis_relationship"],
        "product_category": spec["product_category"],
        "execution_priority": spec["execution_priority"],
        "target_benchmark": spec["target_benchmark"],
        "exposure_direction": spec["exposure_direction"],
        "position_construction": "long_shares",
        "daily_leverage_multiple": leverage,
        "daily_reset": True,
        "issuer": spec["issuer"],
        "official_source_url": spec["official_source_url"],
        "source_as_of_date": source_as_of_date,
        "source_thesis_hash": source_hash,
        "source_thesis_kind": str(
            thesis.get("source_thesis_kind", "equity_first_contextual")
        )
        if thesis
        else "",
        "setup_quality_score": float(thesis.get("setup_quality_score", 0.0))
        if thesis
        else 0.0,
        "reward_risk_ratio": float(thesis.get("reward_risk_ratio", 0.0))
        if thesis
        else 0.0,
        "underlying_bullish_score": float(thesis.get("equity_bullish_score", 0.0))
        if thesis
        else 0.0,
        "underlying_bearish_score": float(thesis.get("equity_bearish_score", 0.0))
        if thesis
        else 0.0,
        "underlying_chart_evidence": {
            "analysis_symbol": analysis_symbol,
            "bar_count": len(rows),
            "as_of_date": chart_as_of_date,
            "ohlcv_sha256": chart_hash,
            "timeframes": ["daily", "weekly", "monthly"],
            "technical_confirmation": thesis.get("technical_confirmation", {})
            if thesis
            else {},
            "structure_reference": thesis.get("structure_reference", {})
            if thesis
            else {},
        },
        "entry_plan": {
            "chart_authority": analysis_symbol,
            "operator": entry_operator,
            "analysis_reference_price": round(analysis_reference, 6),
            "execution_rule": "buy_long_shares_after_fresh_broker_tradeability_and_quote_review",
        },
        "exit_plan": {
            "chart_authority": analysis_symbol,
            "invalidation_operator": invalidation_operator,
            "analysis_invalidation_price": round(analysis_invalidation, 6),
            "target_operator": target_operator,
            "analysis_target_price": round(analysis_target, 6),
            "maximum_holding_sessions": MAX_LEVERAGED_ETF_HOLDING_SESSIONS,
            "no_same_session_round_trip": True,
        },
        "expected_hold_trading_days": expected_hold,
        "max_notional_fraction": round(
            min(
                MAX_LEVERAGED_ETF_PRODUCT_ALLOCATION_FRACTION,
                MAX_LEVERAGED_ETF_GROSS_ALLOCATION_FRACTION / abs(leverage),
            ),
            6,
        ),
        "portfolio_gross_leveraged_etf_cap_fraction": MAX_LEVERAGED_ETF_GROSS_ALLOCATION_FRACTION,
        "reason_codes": reason_codes,
        "actionable": actionable,
        "not_edge_evidence": True,
        "paper_twin_required": True,
        "live_branch_candidate_route": "independent_freshness_tradeability_and_paper_twin_gates",
        "direct_short_sale_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }


def _history_hash(rows: list[Bar]) -> str:
    if not rows:
        return ""
    encoded = json.dumps(
        rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _record_hash(record: dict[str, Any] | None) -> str:
    if record is None:
        return ""
    encoded = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
