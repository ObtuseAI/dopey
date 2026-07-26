"""Schema contracts and sample-only templates for manually staged data."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .ingestion_plan_models import DATA_INGESTION_PLAN_VERSION, DatasetSchemaContract
from .local_staging_contract import TEMPLATE_DIR


SCHEMA_VERSION = "dopey-real-data-schema-contract-v1"


def schema_definitions() -> dict[str, dict[str, object]]:
    return {
        "daily_ohlcv": _schema(["date", "symbol", "open", "high", "low", "close", "adjusted_close", "volume"], ["source", "dividend", "split_factor"], ["date", "symbol"]),
        "corporate_actions": _schema(["date", "symbol", "action_type", "split_ratio", "dividend_amount", "source", "provider_record_id"], [], ["date", "symbol", "action_type", "provider_record_id"]),
        "historical_options_chain": _schema(["snapshot_date", "underlying_symbol", "expiration_date", "strike", "option_type", "bid", "ask", "mid", "last", "volume", "open_interest", "implied_volatility", "source", "provider_record_id"], ["delta", "gamma", "theta", "vega", "rho"], ["snapshot_date", "underlying_symbol", "expiration_date", "strike", "option_type", "provider_record_id"]),
        "historical_options_quotes": _schema(["timestamp", "underlying_symbol", "contract_symbol", "expiration_date", "strike", "option_type", "bid", "ask", "bid_size", "ask_size", "last", "volume", "open_interest", "source"], [], ["timestamp", "contract_symbol"]),
        "fundamentals": _schema(["period_end_date", "symbol", "revenue", "gross_profit", "operating_income", "net_income", "eps", "free_cash_flow", "cash", "debt", "shares_outstanding", "source", "provider_record_id"], [], ["period_end_date", "symbol", "provider_record_id"]),
        "earnings_calendar": _schema(["symbol", "earnings_date", "report_time", "eps_estimate", "eps_actual", "revenue_estimate", "revenue_actual", "source"], [], ["symbol", "earnings_date", "report_time"]),
        "market_context": _schema(["date", "symbol", "open", "high", "low", "close", "adjusted_close", "volume"], ["source", "dividend", "split_factor"], ["date", "symbol"]),
        "benchmark_and_universe_metadata": _schema(["symbol", "name", "asset_type", "sector", "industry", "optionable", "start_date", "end_date", "included_in_universe", "source"], [], ["symbol", "start_date", "end_date"]),
    }


def build_schema_contracts(write_templates: bool) -> list[DatasetSchemaContract]:
    definitions = schema_definitions()
    if write_templates:
        write_schema_templates(definitions)
        write_sample_templates()
    return [
        DatasetSchemaContract(
            artifact_type="dataset_schema_contract",
            ingestion_plan_version=DATA_INGESTION_PLAN_VERSION,
            schema_id=f"schema-{family}",
            dataset_family=family,
            schema_version=SCHEMA_VERSION,
            template_path=f"dopey_data/real/templates/{_template_file_name(family)}",
            required_columns=list(definition["required_columns"]),
            optional_columns=list(definition["optional_columns"]),
            primary_key_columns=list(definition["primary_key_columns"]),
            column_types=dict(definition["column_types"]),
            accepted_file_formats=["csv", "jsonl", "parquet_export_manifest"],
            sample_template_paths=_sample_paths_for(family),
            sample_rows_allowed_as_real=False,
            paper_only=True,
            live_blocked=True,
            not_real_data_ingested=True,
            schema_hash="",
        )
        for family, definition in definitions.items()
    ]


def schema_contract_records(write_templates: bool) -> list[dict]:
    return [contract.to_dict() for contract in build_schema_contracts(write_templates)]


def write_schema_templates(definitions: dict[str, dict[str, object]]) -> list[Path]:
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for family, definition in definitions.items():
        path = TEMPLATE_DIR / _template_file_name(family)
        record = {
            "schema_id": f"schema-{family}",
            "schema_version": SCHEMA_VERSION,
            "dataset_family": family,
            "required_columns": definition["required_columns"],
            "optional_columns": definition["optional_columns"],
            "primary_key_columns": definition["primary_key_columns"],
            "column_types": definition["column_types"],
            "sample_only_rows_allowed_as_real": False,
            "paper_only": True,
            "live_blocked": True,
            "not_real_data_ingested": True,
        }
        path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def write_sample_templates() -> list[Path]:
    samples = {
        "sample_daily_ohlcv.csv": ["date", "symbol", "open", "high", "low", "close", "adjusted_close", "volume", "source", "sample_only", "not_real_data"],
        "sample_options_chain.csv": ["snapshot_date", "underlying_symbol", "expiration_date", "strike", "option_type", "bid", "ask", "mid", "last", "volume", "open_interest", "implied_volatility", "source", "provider_record_id", "sample_only", "not_real_data"],
        "sample_options_quotes.csv": ["timestamp", "underlying_symbol", "contract_symbol", "expiration_date", "strike", "option_type", "bid", "ask", "bid_size", "ask_size", "last", "volume", "open_interest", "source", "sample_only", "not_real_data"],
        "sample_fundamentals.csv": ["period_end_date", "symbol", "revenue", "gross_profit", "operating_income", "net_income", "eps", "free_cash_flow", "cash", "debt", "shares_outstanding", "source", "provider_record_id", "sample_only", "not_real_data"],
    }
    row = {
        "date": "2000-01-03",
        "timestamp": "2000-01-03T21:00:00Z",
        "snapshot_date": "2000-01-03",
        "period_end_date": "2000-03-31",
        "symbol": "SAMPLE_ONLY",
        "underlying_symbol": "SAMPLE_ONLY",
        "contract_symbol": "SAMPLE_ONLY200001C00100000",
        "expiration_date": "2000-02-18",
        "strike": "100.0",
        "option_type": "call",
        "open": "100.0",
        "high": "101.0",
        "low": "99.0",
        "close": "100.5",
        "adjusted_close": "100.5",
        "volume": "1",
        "bid": "1.0",
        "ask": "1.2",
        "mid": "1.1",
        "last": "1.1",
        "bid_size": "1",
        "ask_size": "1",
        "open_interest": "1",
        "implied_volatility": "0.2",
        "source": "SAMPLE_ONLY",
        "provider_record_id": "SAMPLE_ONLY",
        "revenue": "1",
        "gross_profit": "1",
        "operating_income": "1",
        "net_income": "1",
        "eps": "0.01",
        "free_cash_flow": "1",
        "cash": "1",
        "debt": "0",
        "shares_outstanding": "1",
        "sample_only": "true",
        "not_real_data": "true",
    }
    paths: list[Path] = []
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    for file_name, fieldnames in samples.items():
        path = TEMPLATE_DIR / file_name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow({field: row.get(field, "SAMPLE_ONLY") for field in fieldnames})
        paths.append(path)
    return paths


def sample_template_paths() -> list[str]:
    return [
        str(TEMPLATE_DIR / "sample_daily_ohlcv.csv"),
        str(TEMPLATE_DIR / "sample_options_chain.csv"),
        str(TEMPLATE_DIR / "sample_options_quotes.csv"),
        str(TEMPLATE_DIR / "sample_fundamentals.csv"),
    ]


def sample_row_is_real_candidate(row: dict[str, str]) -> bool:
    return not (
        row.get("sample_only", "").lower() == "true"
        or row.get("not_real_data", "").lower() == "true"
        or row.get("symbol") == "SAMPLE_ONLY"
        or row.get("underlying_symbol") == "SAMPLE_ONLY"
    )


def _schema(required_columns: list[str], optional_columns: list[str], primary_key_columns: list[str]) -> dict[str, object]:
    column_types = {column: _type_for_column(column) for column in [*required_columns, *optional_columns]}
    return {
        "required_columns": required_columns,
        "optional_columns": optional_columns,
        "primary_key_columns": primary_key_columns,
        "column_types": column_types,
    }


def _type_for_column(column: str) -> str:
    if column in {"date", "snapshot_date", "expiration_date", "period_end_date", "earnings_date", "start_date", "end_date"}:
        return "date"
    if column == "timestamp":
        return "timestamp"
    if column in {"symbol", "underlying_symbol", "contract_symbol", "option_type", "source", "provider_record_id", "name", "asset_type", "sector", "industry", "action_type", "report_time"}:
        return "string"
    if column in {"volume", "open_interest", "bid_size", "ask_size", "symbol_counts", "shares_outstanding"}:
        return "integer"
    if column in {"optionable", "included_in_universe"}:
        return "boolean"
    return "number"


def _template_file_name(family: str) -> str:
    names = {
        "daily_ohlcv": "daily_ohlcv_schema.json",
        "corporate_actions": "corporate_actions_schema.json",
        "historical_options_chain": "options_chain_schema.json",
        "historical_options_quotes": "options_quotes_schema.json",
        "fundamentals": "fundamentals_schema.json",
        "earnings_calendar": "earnings_calendar_schema.json",
        "market_context": "market_context_schema.json",
        "benchmark_and_universe_metadata": "universe_metadata_schema.json",
    }
    return names[family]


def _sample_paths_for(family: str) -> list[str]:
    paths = {
        "daily_ohlcv": ["dopey_data/real/templates/sample_daily_ohlcv.csv"],
        "historical_options_chain": ["dopey_data/real/templates/sample_options_chain.csv"],
        "historical_options_quotes": ["dopey_data/real/templates/sample_options_quotes.csv"],
        "fundamentals": ["dopey_data/real/templates/sample_fundamentals.csv"],
    }
    return paths.get(family, [])
