"""Provider-neutral dataset requirements for DOPEY real-data planning."""
from __future__ import annotations

from .ingestion_plan_models import DATA_INGESTION_PLAN_VERSION, DatasetRequirement


NEXT_IMPORT_BUNDLE = "DOPEY_LOCAL_OHLCV_IMPORT_VALIDATOR_V1"


def build_dataset_requirement_catalog() -> list[DatasetRequirement]:
    return [
        _requirement(
            "daily_ohlcv",
            "Required for real signal validation and real backtest date paths.",
            ["real_signal_validation", "real_backtest_date_paths"],
            ["date", "symbol", "open", "high", "low", "close", "adjusted_close", "volume"],
            ["source", "dividend", "split_factor"],
            ["date", "symbol"],
            "3 to 5 years of daily history",
            "start with DOPEY liquid universe from history spine",
            [
                "Acquire outside DOPEY from a licensed provider or manual export.",
                "Stage only local files under dopey_data/real/raw/daily_ohlcv/.",
            ],
        ),
        _requirement(
            "corporate_actions",
            "Required for adjusted price validation.",
            ["adjusted_price_validation"],
            ["date", "symbol", "action_type", "split_ratio", "dividend_amount", "source", "provider_record_id"],
            [],
            ["date", "symbol", "action_type", "provider_record_id"],
            "cover full OHLCV date range",
            "same symbols as daily_ohlcv",
            ["Acquire split and dividend records with provider record ids."],
        ),
        _requirement(
            "historical_options_chain",
            "Required for real options backtesting.",
            ["real_options_backtesting"],
            [
                "snapshot_date", "underlying_symbol", "expiration_date", "strike", "option_type",
                "bid", "ask", "mid", "last", "volume", "open_interest", "implied_volatility",
                "source", "provider_record_id",
            ],
            ["delta", "gamma", "theta", "vega", "rho"],
            ["snapshot_date", "underlying_symbol", "expiration_date", "strike", "option_type", "provider_record_id"],
            "match backtest window where licensed data is available",
            "optionable subset of DOPEY liquid universe",
            ["Prefer provider exports with daily close snapshots and complete option chains."],
        ),
        _requirement(
            "historical_options_quotes",
            "Required for spread and slippage realism.",
            ["spread_realism", "slippage_realism"],
            [
                "timestamp", "underlying_symbol", "contract_symbol", "expiration_date", "strike",
                "option_type", "bid", "ask", "bid_size", "ask_size", "last", "volume",
                "open_interest", "source",
            ],
            [],
            ["timestamp", "contract_symbol"],
            "daily close or selected timestamp snapshots",
            "optionable subset of DOPEY liquid universe",
            ["Prefer quote snapshots at daily close or a documented selected timestamp."],
        ),
        _requirement(
            "fundamentals",
            "Required for fundamental analysis.",
            ["fundamental_analysis"],
            [
                "period_end_date", "symbol", "revenue", "gross_profit", "operating_income",
                "net_income", "eps", "free_cash_flow", "cash", "debt", "shares_outstanding",
                "source", "provider_record_id",
            ],
            [],
            ["period_end_date", "symbol", "provider_record_id"],
            "quarterly and annual coverage for OHLCV window where available",
            "symbols in research universe",
            ["Use licensed fundamentals exports or filings-derived offline records."],
        ),
        _requirement(
            "earnings_calendar",
            "Required for catalyst and event gates.",
            ["catalyst_gates", "event_gates"],
            [
                "symbol", "earnings_date", "report_time", "eps_estimate", "eps_actual",
                "revenue_estimate", "revenue_actual", "source",
            ],
            [],
            ["symbol", "earnings_date", "report_time"],
            "cover real signal/backtest window where available",
            "symbols in research universe",
            ["Track whether estimates and actuals are historical point-in-time records."],
        ),
        _requirement(
            "market_context",
            "Required for market regimes.",
            ["regime_detection"],
            ["date", "symbol", "open", "high", "low", "close", "adjusted_close", "volume"],
            ["source", "dividend", "split_factor"],
            ["date", "symbol"],
            "3 to 5 years daily history",
            "SPY, QQQ, IWM, DIA, VIX or equivalent, sector ETFs, rates proxy if available",
            ["Use the same OHLCV contract as daily market data."],
        ),
        _requirement(
            "benchmark_and_universe_metadata",
            "Required for survivorship and coverage tracking.",
            ["survivorship_tracking", "coverage_tracking"],
            [
                "symbol", "name", "asset_type", "sector", "industry", "optionable",
                "start_date", "end_date", "included_in_universe", "source",
            ],
            [],
            ["symbol", "start_date", "end_date"],
            "point-in-time universe membership where available",
            "DOPEY liquid universe plus benchmark/index constituents",
            ["Do not infer survivorship from current membership only."],
        ),
    ]


def dataset_requirement_records() -> list[dict]:
    return [requirement.to_dict() for requirement in build_dataset_requirement_catalog()]


def _requirement(
    dataset_family: str,
    purpose: str,
    required_for: list[str],
    required_fields: list[str],
    optional_fields: list[str],
    primary_key_fields: list[str],
    target_history: str,
    source_universe: str,
    acquisition_notes: list[str],
) -> DatasetRequirement:
    return DatasetRequirement(
        artifact_type="dataset_requirement",
        ingestion_plan_version=DATA_INGESTION_PLAN_VERSION,
        requirement_id=f"requirement-{dataset_family}",
        dataset_family=dataset_family,
        purpose=purpose,
        required_for=required_for,
        required_fields=required_fields,
        optional_fields=optional_fields,
        primary_key_fields=primary_key_fields,
        target_history=target_history,
        source_universe=source_universe,
        acquisition_notes=acquisition_notes,
        allowed_import_bundles=[NEXT_IMPORT_BUNDLE],
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        requirement_hash="",
    )
