"""Defined-but-not-run data quality gates for future local imports."""
from __future__ import annotations

from .ingestion_plan_models import DATA_INGESTION_PLAN_VERSION, DataLicenseProvenanceRequirement, DataQualityGate


GATE_STATUS_DEFINED = "gate_defined_not_run"


def build_data_quality_gates() -> list[DataQualityGate]:
    gates: list[DataQualityGate] = []
    for family in [
        "daily_ohlcv",
        "corporate_actions",
        "historical_options_chain",
        "historical_options_quotes",
        "fundamentals",
        "earnings_calendar",
        "market_context",
        "benchmark_and_universe_metadata",
    ]:
        gates.extend(_common_gates(family))
    gates.extend(_ohlcv_gates("daily_ohlcv"))
    gates.extend(_ohlcv_gates("market_context"))
    gates.extend(_options_gates("historical_options_chain"))
    gates.extend(_options_gates("historical_options_quotes"))
    gates.extend(_fundamental_gates())
    return gates


def data_quality_gate_records() -> list[dict]:
    return [gate.to_dict() for gate in build_data_quality_gates()]


def build_license_provenance_requirements() -> list[DataLicenseProvenanceRequirement]:
    families = [
        "daily_ohlcv",
        "corporate_actions",
        "historical_options_chain",
        "historical_options_quotes",
        "fundamentals",
        "earnings_calendar",
        "market_context",
        "benchmark_and_universe_metadata",
    ]
    return [
        DataLicenseProvenanceRequirement(
            artifact_type="license_provenance_requirement",
            ingestion_plan_version=DATA_INGESTION_PLAN_VERSION,
            requirement_id=f"license-provenance-{family}",
            dataset_family=family,
            provider_name_required=True,
            license_status_required=True,
            provider_terms_review_required=True,
            redistribution_allowed_required=True,
            provenance_fields_required=[
                "provider_name",
                "provider_terms_reviewed",
                "license_status",
                "source",
                "provider_record_id",
                "file_hashes",
                "local_file_paths",
                "manual_operator_note",
            ],
            valid_license_statuses=["reviewed_allowed_internal_research", "reviewed_restricted_internal_research"],
            invalid_license_statuses=["unknown", "unreviewed", "missing", "unlicensed"],
            paper_only=True,
            live_blocked=True,
            not_real_data_ingested=True,
            license_hash="",
        )
        for family in families
    ]


def license_provenance_requirement_records() -> list[dict]:
    return [requirement.to_dict() for requirement in build_license_provenance_requirements()]


def _common_gates(dataset_family: str) -> list[DataQualityGate]:
    names = [
        ("schema_parse", "schema parses under the provider-neutral schema contract", True, False),
        ("required_columns_present", "all required columns are present", True, False),
        ("no_duplicate_primary_keys", "primary keys are unique", True, False),
        ("valid_date_timestamp_formats", "dates and timestamps parse deterministically", True, False),
        ("row_count_gt_zero_for_import_readiness", "row count must be greater than zero before import readiness", False, True),
        ("provider_name_present", "provider name is present in manifest/provenance", True, False),
        ("source_provenance_present", "source and provenance are present", True, False),
        ("license_status_not_unknown", "license status is not unknown", True, False),
        ("hash_manifest_present", "hash manifest exists and references staged files", True, False),
        ("no_sample_only_rows_accepted_as_real", "sample-only rows are rejected from real data paths", True, False),
        ("no_future_dates_beyond_current_date", "dates do not exceed current validation date", True, False),
        ("no_credentials_or_tokens_in_files", "staged files contain no credentials or tokens", True, False),
    ]
    return [_gate(dataset_family, gate_name, description, terminal, manual) for gate_name, description, terminal, manual in names]


def _ohlcv_gates(dataset_family: str) -> list[DataQualityGate]:
    names = [
        ("positive_ohlc", "open, high, low, and close are positive", True, False),
        ("high_ge_open_close_low", "high is greater than or equal to open, close, and low", True, False),
        ("low_le_open_close_high", "low is less than or equal to open, close, and high", True, False),
        ("adjusted_close_positive", "adjusted_close is positive", True, False),
        ("volume_nonnegative", "volume is nonnegative", True, False),
        ("split_dividend_adjustment_consistency_placeholder", "placeholder for split/dividend adjustment consistency", False, True),
        ("missing_day_count", "missing trading-day count is computed", False, True),
        ("stale_symbol_count", "stale-symbol count is computed", False, True),
    ]
    return [_gate(dataset_family, gate_name, description, terminal, manual) for gate_name, description, terminal, manual in names]


def _options_gates(dataset_family: str) -> list[DataQualityGate]:
    names = [
        ("bid_ask_nonnegative", "bid and ask are nonnegative", True, False),
        ("ask_ge_bid", "ask is greater than or equal to bid", True, False),
        ("mid_between_bid_and_ask", "mid is between bid and ask", True, False),
        ("strike_positive", "strike is positive", True, False),
        ("expiry_ge_quote_or_snapshot_date", "expiration date is on or after quote/snapshot date", True, False),
        ("option_type_call_or_put", "option_type is call or put", True, False),
        ("implied_volatility_nonnegative_if_present", "implied volatility is nonnegative if present", True, False),
        ("open_interest_nonnegative", "open interest is nonnegative", True, False),
        ("volume_nonnegative", "volume is nonnegative", True, False),
        ("contract_uniqueness", "contract identity is unique at the selected timestamp/snapshot", True, False),
    ]
    return [_gate(dataset_family, gate_name, description, terminal, manual) for gate_name, description, terminal, manual in names]


def _fundamental_gates() -> list[DataQualityGate]:
    names = [
        ("period_end_date_parse", "period_end_date parses as a date", True, False),
        ("symbol_coverage", "symbol coverage is measured", False, True),
        ("numeric_columns_parse", "numeric columns parse deterministically", True, False),
        ("fiscal_period_duplicates_detected", "duplicate fiscal periods are detected", True, False),
        ("source_provenance_present", "source and provenance are present", True, False),
    ]
    return [_gate("fundamentals", gate_name, description, terminal, manual) for gate_name, description, terminal, manual in names]


def _gate(
    dataset_family: str,
    gate_name: str,
    gate_description: str,
    terminal_on_failure: bool,
    manual_review_on_failure: bool,
) -> DataQualityGate:
    return DataQualityGate(
        artifact_type="data_quality_gate",
        ingestion_plan_version=DATA_INGESTION_PLAN_VERSION,
        gate_id=f"gate-{dataset_family}-{gate_name}",
        dataset_family=dataset_family,
        gate_name=gate_name,
        gate_description=gate_description,
        status=GATE_STATUS_DEFINED,
        terminal_on_failure=terminal_on_failure,
        manual_review_on_failure=manual_review_on_failure,
        paper_only=True,
        live_blocked=True,
        not_real_data_ingested=True,
        gate_hash="",
    )
