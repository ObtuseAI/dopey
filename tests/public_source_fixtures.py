"""Deterministic clean-slate inputs for public-source integration tests."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import TypedDict

from dopey_data.history_models import (
    ALLOWED_HISTORY_FORMATS,
    OPTIONAL_HISTORY_COLUMNS,
    REQUIRED_HISTORY_COLUMNS,
    history_manifest_hash,
)


class VNextGovernedInputs(TypedDict):
    macro_manifest: Path
    options_manifest: Path
    earnings_directory: Path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return path


def write_empty_vnext_governed_inputs(
    repository_root: Path,
    created_at: str,
) -> VNextGovernedInputs:
    fundamental_reference = "dopey_data/real/raw/macro_context/fundamentals.csv"
    fundamental_path = repository_root / Path(fundamental_reference)
    fundamental_path.parent.mkdir(parents=True, exist_ok=True)
    fundamental_path.write_text(
        (
            "date,symbol,theme,in_universe,market_cap,trailing_pe,forward_pe,"
            "price_to_sales,price_to_book,profit_margin,revenue_growth,"
            "free_cashflow,total_debt,total_cash,source\n"
        ),
        encoding="utf-8",
    )
    governance = {
        "created_at": created_at,
        "license_status": "reviewed_test_fixture_only",
        "paper_only": True,
        "live_blocked": True,
        "not_real_data": False,
        "template_only": False,
        "not_broker_data": True,
        "not_credentials": True,
        "provider_terms_reviewed": True,
        "fixture_only": True,
        "not_readiness_evidence": True,
    }
    macro_manifest = _write_json(
        repository_root / "dopey_data" / "real" / "manifests" / "macro_context_manifest.json",
        {
            **governance,
            "dataset_family": "empty_public_source_macro_fixture",
            "manifest_id": "empty-public-source-macro-fixture-v1",
            "provider_name": "deterministic_test_fixture",
            "file_hashes": {
                fundamental_reference: _file_sha256(fundamental_path),
            },
            "row_counts": {
                fundamental_reference: 0,
            },
            "local_file_paths": [fundamental_reference],
            "per_file_sources": {
                fundamental_reference: "integration_test_only_not_readiness_evidence",
            },
        },
    )
    options_manifest = _write_json(
        repository_root / "dopey_data" / "real" / "manifests" / "options_data_manifest.json",
        {
            **governance,
            "dataset_family": "empty_public_source_options_fixture",
            "manifest_id": "empty-public-source-options-fixture-v1",
            "provider_name": "deterministic_test_fixture",
            "file_hashes": {},
            "row_counts": {},
            "local_file_paths": [],
            "per_file_sources": {},
            "snapshot_dates": [],
        },
    )
    earnings_directory = repository_root / "dopey_data" / "real" / "raw" / "earnings_calendar"
    earnings_directory.mkdir(parents=True, exist_ok=True)
    return {
        "macro_manifest": macro_manifest,
        "options_manifest": options_manifest,
        "earnings_directory": earnings_directory,
    }


def write_synthetic_history_manifest(
    history_root: Path,
    symbol: str,
    rows: Sequence[Mapping[str, object]],
) -> Path:
    return write_synthetic_histories_manifest(
        history_root,
        {symbol: rows},
    )


def write_synthetic_histories_manifest(
    history_root: Path,
    rows_by_symbol: Mapping[str, Sequence[Mapping[str, object]]],
) -> Path:
    if not rows_by_symbol:
        raise ValueError("synthetic history fixture requires at least one symbol")
    raw_directory = history_root / "raw"
    raw_directory.mkdir(parents=True, exist_ok=True)
    headers = (*REQUIRED_HISTORY_COLUMNS, *OPTIONAL_HISTORY_COLUMNS)
    data_files: list[dict[str, object]] = []
    normalized_symbols: list[str] = []
    for symbol, rows in sorted(rows_by_symbol.items()):
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("synthetic history fixture requires non-empty symbols")
        normalized_symbols.append(normalized_symbol)
        data_path = raw_directory / f"{normalized_symbol}.csv"
        with data_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in headers})
        data_files.append(
            {
                "path": data_path.name,
                "format": "csv",
                "symbols": [normalized_symbol],
                "sha256": _file_sha256(data_path),
                "source": "integration_test_only_not_readiness_evidence",
                "row_count": len(rows),
            }
        )
    manifest: dict[str, object] = {
        "artifact_type": "history_dataset_manifest",
        "history_dataset_manifest_version": "public-source-integration-fixture-v1",
        "dataset_id": "public-source-history-integration-fixture",
        "dataset_status": "operator_staged_real_dataset",
        "raw_data_directory": "raw",
        "required_universe": normalized_symbols,
        "required_columns": list(REQUIRED_HISTORY_COLUMNS),
        "optional_columns": list(OPTIONAL_HISTORY_COLUMNS),
        "allowed_formats": list(ALLOWED_HISTORY_FORMATS),
        "data_files": data_files,
        "generated_real_data": False,
        "network_fetch_performed": False,
        "credential_required": False,
        "paper_only": True,
        "live_blocked": True,
        "manifest_reproducibility_hash": "",
    }
    manifest["manifest_reproducibility_hash"] = history_manifest_hash(manifest)
    return _write_json(history_root / "history_dataset_manifest.json", manifest)


def build_synthetic_history_rows(
    symbol: str,
    row_count: int,
) -> list[dict[str, object]]:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("synthetic history rows require a symbol")
    if row_count < 1:
        raise ValueError(f"synthetic history rows require a positive row count: row_count={row_count}")
    start = date(2024, 1, 2)
    rows: list[dict[str, object]] = []
    for index in range(row_count):
        close = 100.0 + index * 0.05
        rows.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "symbol": normalized_symbol,
                "open": close - 0.2,
                "high": close + 0.8,
                "low": close - 0.8,
                "close": close,
                "adjusted_close": close,
                "volume": 1_000_000 + index * 100,
                "source": "integration_test_only_not_readiness_evidence",
            }
        )
    return rows


def write_empty_history_manifest(history_root: Path) -> Path:
    manifest: dict[str, object] = {
        "artifact_type": "history_dataset_manifest",
        "history_dataset_manifest_version": "public-source-empty-fixture-v1",
        "dataset_id": "public-source-empty-history-fixture",
        "dataset_status": "operator_staged_real_dataset",
        "raw_data_directory": "raw",
        "required_universe": [],
        "required_columns": list(REQUIRED_HISTORY_COLUMNS),
        "optional_columns": list(OPTIONAL_HISTORY_COLUMNS),
        "allowed_formats": list(ALLOWED_HISTORY_FORMATS),
        "data_files": [],
        "generated_real_data": False,
        "network_fetch_performed": False,
        "credential_required": False,
        "paper_only": True,
        "live_blocked": True,
        "manifest_reproducibility_hash": "",
    }
    manifest["manifest_reproducibility_hash"] = history_manifest_hash(manifest)
    return _write_json(history_root / "history_dataset_manifest.json", manifest)
