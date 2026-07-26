"""Build conservative evidence from validated local fundamental snapshots."""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any

from dopey.constitution.evidence_law import validate_evidence_record
from dopey.protocols.governed_data import file_sha256, load_governed_manifest, read_validated_csv
from dopey.protocols.identity import canonical_hash


FUNDAMENTAL_COLUMNS = (
    "date", "symbol", "theme", "in_universe", "market_cap", "trailing_pe", "forward_pe",
    "price_to_sales", "price_to_book", "profit_margin", "revenue_growth", "free_cashflow",
    "total_debt", "total_cash",
)


def _optional_float(row: dict[str, str], field: str) -> float | None:
    value = row.get(field, "").strip()
    if not value or value.lower() in {"nan", "none", "null"}:
        return None
    return float(value)


def _evidence_record(
    evidence_type: str,
    status: str,
    symbol: str,
    observed_at: str,
    source_uri: str,
    provenance: str,
    values: dict[str, Any],
    limitations: list[str],
) -> dict[str, Any]:
    body = {
        "evidence_type": evidence_type,
        "evidence_status": status,
        "symbol": symbol,
        "observed_at": observed_at,
        "source_uri": source_uri,
        "schema_version": "dopey-fundamental-evidence-v1",
        "provenance": provenance,
        "values": values,
        "limitations": limitations,
        "not_trade_decision": True,
        "not_readiness_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    content_hash = canonical_hash(body)
    record = {
        **body,
        "evidence_id": f"{evidence_type}:{content_hash[:24]}",
        "content_hash": content_hash,
    }
    validate_evidence_record(record)
    return record


def build_fundamental_evidence(
    symbol: str,
    event_time: str,
    market_time: str,
    manifest_path: Path,
    file_reference: str,
) -> dict[str, Any]:
    normalized_symbol = symbol.strip().upper()
    manifest = load_governed_manifest(manifest_path, event_time)
    rows, proof = read_validated_csv(
        manifest_path,
        manifest,
        file_reference,
        FUNDAMENTAL_COLUMNS,
    )
    market_date = datetime.fromisoformat(market_time.replace("Z", "+00:00")).date()
    candidates = [
        row for row in rows
        if row.get("symbol", "").strip().upper() == normalized_symbol
        and date.fromisoformat(row["date"]) <= market_date
    ]
    if not candidates:
        return _evidence_record(
            "fundamental_data_gap",
            "unavailable_no_point_in_time_symbol_snapshot",
            normalized_symbol,
            str(manifest["created_at"]),
            f"local://{file_reference}",
            "validated_operator_staged_manifest_without_requested_symbol_snapshot",
            {"manifest_proof": proof},
            ["symbol_snapshot_missing", "absence_is_not_fundamental_evidence"],
        )
    selected = max(candidates, key=lambda row: row["date"])
    metrics = {
        field: _optional_float(selected, field)
        for field in FUNDAMENTAL_COLUMNS
        if field not in {"date", "symbol", "theme", "in_universe"}
    }
    available = [value for value in metrics.values() if value is not None]
    values = {
        "snapshot_date": selected["date"],
        "theme": selected.get("theme", ""),
        "in_universe": selected.get("in_universe", "").lower() == "true",
        "metrics": metrics,
        "available_metric_count": len(available),
        "positive_metric_median": median([value for value in available if value > 0.0])
        if any(value > 0.0 for value in available) else None,
        "manifest_proof": proof,
    }
    return _evidence_record(
        "validated_fundamental_evidence",
        "complete_point_in_time_snapshot",
        normalized_symbol,
        str(manifest["created_at"]),
        f"local://{file_reference}",
        "hash_and_row_pinned_operator_staged_fundamental_snapshot",
        values,
        [
            "single_snapshot_not_restatement_aware_history",
            "provider_fields_may_be_lagged_or_null",
            "not_survivorship_free_cross_sectional_fundamental_history",
        ],
    )


def build_earnings_event_evidence(
    symbol: str,
    event_time: str,
    market_time: str,
    earnings_directory: Path,
) -> dict[str, Any]:
    normalized_symbol = symbol.strip().upper()
    event_timestamp = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
    market_date = datetime.fromisoformat(market_time.replace("Z", "+00:00")).date()
    candidates: list[tuple[date, Path, dict[str, str]]] = []
    for path in sorted(earnings_directory.glob("*_earnings.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"snapshot_date", "symbol", "earnings_date", "source"}
            missing = sorted(required - set(reader.fieldnames or ()))
            if missing:
                raise ValueError(
                    "earnings snapshot lacks required columns: "
                    f"path={path}, missing_columns={missing}"
                )
            for row in reader:
                snapshot_date = date.fromisoformat(row["snapshot_date"])
                if row["symbol"].strip().upper() == normalized_symbol and snapshot_date <= market_date:
                    candidates.append((snapshot_date, path, dict(row)))
    if not candidates:
        return _evidence_record(
            "earnings_event_data_gap",
            "unavailable_no_symbol_event_snapshot",
            normalized_symbol,
            event_time,
            f"local://{earnings_directory}",
            "local_earnings_directory_scanned_without_symbol_event",
            {"market_date": market_date.isoformat()},
            ["absence_is_not_proof_of_no_future_earnings_event"],
        )
    snapshot_date, path, selected = max(candidates, key=lambda value: value[0])
    file_modified = datetime.fromtimestamp(path.stat().st_mtime, tz=event_timestamp.tzinfo)
    if file_modified > event_timestamp:
        return _evidence_record(
            "earnings_event_data_gap",
            "excluded_file_modified_after_research_event",
            normalized_symbol,
            event_time,
            f"local://{path}",
            "local_snapshot_failed_point_in_time_file_mtime_check",
            {"file_modified_at": file_modified.isoformat(), "research_event_time": event_time},
            ["point_in_time_identity_not_established"],
        )
    source = selected.get("source", "").strip()
    if not source or any(term in source.lower() for term in ("fixture", "synthetic", "sample")):
        raise ValueError(f"earnings snapshot source is invalid: path={path}, source={source}")
    return _evidence_record(
        "validated_earnings_event",
        "complete_local_snapshot_with_file_identity",
        normalized_symbol,
        file_modified.isoformat(),
        f"local://{path}",
        "schema_validated_local_earnings_snapshot_with_content_hash_and_mtime_bound",
        {
            "snapshot_date": snapshot_date.isoformat(),
            "earnings_date": selected["earnings_date"],
            "source": source,
            "file_sha256": file_sha256(path),
        },
        [
            "file_mtime_is_weaker_than_an_operator_signed_manifest",
            "event_date_may_change_after_snapshot",
            "not_an_earnings_outcome_prediction",
        ],
    )
