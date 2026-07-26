"""Provider-candidate records only. No provider integration or API calls."""
from __future__ import annotations

from .ingestion_plan_models import DATA_INGESTION_PLAN_VERSION, ProviderCandidate


def build_provider_candidate_registry() -> list[ProviderCandidate]:
    return [
        _provider("Polygon", ["daily_ohlcv", "corporate_actions", "historical_options_chain", "historical_options_quotes"], "paid/free tiers", True, True, True, "review plan terms; redistribution commonly restricted", "multi-year depending plan", "available on paid plans", "available", "limited/reference", ["csv", "json"], "candidate for licensed manual offline export"),
        _provider("Cboe DataShop", ["historical_options_chain", "historical_options_quotes", "volatility_indices"], "paid", True, True, True, "strict exchange data terms", "deep historical options", "strong", "limited", "not primary", ["csv"], "candidate for purchased historical options exports"),
        _provider("ORATS", ["historical_options_chain", "historical_options_quotes"], "paid", True, True, True, "review redistribution and derived-data terms", "deep options history", "strong", "limited", "not primary", ["csv", "parquet"], "candidate for options backtest inputs"),
        _provider("OptionMetrics", ["historical_options_chain", "historical_options_quotes"], "paid", True, True, True, "institutional license review required", "deep options history", "strong", "limited", "not primary", ["csv", "database_export"], "candidate for institutional options research exports"),
        _provider("Nasdaq Data Link", ["daily_ohlcv", "corporate_actions", "fundamentals", "market_context"], "free/paid datasets", True, True, True, "dataset-specific redistribution limits", "varies by dataset", "dataset dependent", "dataset dependent", "available on selected datasets", ["csv", "json"], "candidate for manual dataset downloads after terms review"),
        _provider("Alpha Vantage", ["daily_ohlcv", "fundamentals", "earnings_calendar", "market_context"], "free/paid tiers", True, True, True, "API terms review required", "varies by endpoint", "limited", "adjusted daily available", "available", ["csv", "json"], "candidate only; API integration explicitly out of scope"),
        _provider("Tiingo", ["daily_ohlcv", "corporate_actions", "fundamentals", "market_context"], "paid/free tiers", True, True, True, "terms review required", "multi-year equities", "not primary", "available", "available", ["csv", "json"], "candidate for licensed manual export"),
        _provider("Stooq", ["daily_ohlcv", "market_context"], "free", True, False, True, "terms/provenance review required", "multi-year daily", "absent", "limited", "absent", ["csv"], "candidate for manual download only after license review"),
        _provider("Yahoo Finance manual download", ["daily_ohlcv", "corporate_actions", "market_context"], "free/manual", True, False, True, "terms and reliability review required", "varies", "absent", "adjusted prices and actions vary", "limited", ["csv"], "candidate only; not accepted without terms and provenance"),
        _provider("SEC EDGAR", ["fundamentals"], "free", True, False, True, "public filings; derived extraction provenance required", "deep filings history", "absent", "not primary", "filings metadata/source facts", ["json", "xml", "txt"], "candidate for offline filings/fundamentals metadata exports"),
        _provider("FRED", ["market_context"], "free", True, False, True, "terms review required", "deep macro/rates history", "absent", "not applicable", "macro only", ["csv", "json"], "candidate for manually staged rates context"),
    ]


def provider_candidate_records() -> list[dict]:
    return [provider.to_dict() for provider in build_provider_candidate_registry()]


def _provider(
    provider_name: str,
    dataset_families_available: list[str],
    free_or_paid_status: str,
    license_terms_review_required: bool,
    credential_required: bool,
    network_access_required: bool,
    redistribution_restrictions: str,
    historical_depth: str,
    options_data_availability: str,
    corporate_actions_availability: str,
    fundamental_data_availability: str,
    export_format_availability: list[str],
    recommended_use: str,
) -> ProviderCandidate:
    status = "manual_review_required" if credential_required or license_terms_review_required else "candidate_only_not_integrated"
    return ProviderCandidate(
        artifact_type="provider_candidate",
        ingestion_plan_version=DATA_INGESTION_PLAN_VERSION,
        provider_name=provider_name,
        dataset_families_available=dataset_families_available,
        free_or_paid_status=free_or_paid_status,
        license_terms_review_required=license_terms_review_required,
        credential_required=credential_required,
        network_access_required=network_access_required,
        redistribution_restrictions=redistribution_restrictions,
        historical_depth=historical_depth,
        options_data_availability=options_data_availability,
        corporate_actions_availability=corporate_actions_availability,
        fundamental_data_availability=fundamental_data_availability,
        export_format_availability=export_format_availability,
        recommended_use=recommended_use,
        status=status,
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        provider_hash="",
    )
