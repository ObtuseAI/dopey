"""Summarize a hash-pinned options chain as research evidence."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path, PurePosixPath
from statistics import median
from typing import Any

from dopey.constitution.evidence_law import validate_evidence_record
from dopey.protocols.governed_data import load_governed_manifest, read_validated_csv
from dopey.protocols.identity import canonical_hash


OPTIONS_COLUMNS = (
    "snapshot_date", "symbol", "expiry", "dte_calendar", "option_type", "strike", "bid",
    "ask", "mid", "last", "volume", "open_interest", "implied_vol", "underlying_spot", "source",
)


def _file_symbol(file_reference: str) -> str:
    name = PurePosixPath(file_reference).name
    return name.removesuffix("_chain.csv").upper()


def _build_record(
    evidence_type: str,
    status: str,
    symbol: str,
    observed_at: str,
    source_uri: str,
    values: dict[str, Any],
    limitations: list[str],
) -> dict[str, Any]:
    body = {
        "evidence_type": evidence_type,
        "evidence_status": status,
        "symbol": symbol,
        "observed_at": observed_at,
        "source_uri": source_uri,
        "schema_version": "dopey-options-surface-evidence-v1",
        "provenance": "hash_and_row_pinned_operator_staged_options_chain_snapshot",
        "values": values,
        "limitations": limitations,
        "dealer_position_inference_allowed": False,
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


def build_options_surface_evidence(
    symbol: str,
    event_time: str,
    market_time: str,
    manifest_path: Path,
) -> dict[str, Any]:
    normalized_symbol = symbol.strip().upper()
    market_date = datetime.fromisoformat(market_time.replace("Z", "+00:00")).date()
    manifest = load_governed_manifest(manifest_path, event_time)
    references = [
        str(reference)
        for reference in manifest.get("local_file_paths", [])
        if _file_symbol(str(reference)) == normalized_symbol
        and date.fromisoformat(PurePosixPath(str(reference)).parent.name) <= market_date
    ]
    if not references:
        return _build_record(
            "options_surface_data_gap",
            "unavailable_no_point_in_time_symbol_chain",
            normalized_symbol,
            str(manifest["created_at"]),
            f"local://{manifest_path}",
            {"market_date": market_date.isoformat(), "manifest_id": manifest.get("manifest_id", "")},
            ["absence_is_not_options_evidence", "dealer_state_remains_unknown"],
        )
    file_reference = max(references, key=lambda value: PurePosixPath(value).parent.name)
    rows, proof = read_validated_csv(manifest_path, manifest, file_reference, OPTIONS_COLUMNS)
    snapshot_dates = {row["snapshot_date"] for row in rows}
    symbols = {row["symbol"].strip().upper() for row in rows}
    if len(snapshot_dates) != 1 or len(symbols) != 1 or symbols != {normalized_symbol}:
        raise ValueError(
            "options chain rows do not identify one requested symbol snapshot: "
            f"file_reference={file_reference}, snapshot_dates={sorted(snapshot_dates)}, symbols={sorted(symbols)}"
        )
    snapshot_date = date.fromisoformat(next(iter(snapshot_dates)))
    if snapshot_date > market_date:
        raise ValueError(
            "options chain snapshot is after the market time: "
            f"snapshot_date={snapshot_date}, market_date={market_date}, symbol={normalized_symbol}"
        )
    option_types = {row["option_type"].strip().lower() for row in rows}
    if not option_types <= {"call", "put"} or not option_types:
        raise ValueError(f"options chain has invalid option types: symbol={normalized_symbol}, types={option_types}")
    call_oi = sum(max(int(float(row["open_interest"] or 0)), 0) for row in rows if row["option_type"].lower() == "call")
    put_oi = sum(max(int(float(row["open_interest"] or 0)), 0) for row in rows if row["option_type"].lower() == "put")
    implied_vols = [float(row["implied_vol"]) for row in rows if float(row["implied_vol"] or 0.0) > 0.0]
    quoted = [row for row in rows if float(row["bid"] or 0.0) >= 0.0 and float(row["ask"] or 0.0) >= float(row["bid"] or 0.0)]
    put_call_ratio = put_oi / call_oi if call_oi > 0 else None
    open_interest_state = (
        "put_open_interest_heavy" if put_call_ratio is not None and put_call_ratio >= 1.35
        else "call_open_interest_heavy" if put_call_ratio is not None and put_call_ratio <= 0.65
        else "open_interest_balanced" if put_call_ratio is not None
        else "open_interest_ratio_unavailable"
    )
    values = {
        "snapshot_date": snapshot_date.isoformat(),
        "row_count": len(rows),
        "expiry_count": len({row["expiry"] for row in rows}),
        "call_open_interest": call_oi,
        "put_open_interest": put_oi,
        "put_call_open_interest_ratio": round(put_call_ratio, 6) if put_call_ratio is not None else None,
        "open_interest_state": open_interest_state,
        "median_implied_volatility": round(median(implied_vols), 6) if implied_vols else None,
        "valid_quote_fraction": round(len(quoted) / max(len(rows), 1), 6),
        "manifest_proof": proof,
    }
    return _build_record(
        "validated_options_surface",
        "complete_point_in_time_chain_snapshot",
        normalized_symbol,
        str(manifest["created_at"]),
        f"local://{file_reference}",
        values,
        [
            "open_interest_is_not_dealer_inventory",
            "snapshot_has_no_intraday_quote_continuity_proof",
            "provider_greeks_not_present_and_not_synthesized",
            "surface_context_is_not_an_action_recommendation",
        ],
    )
